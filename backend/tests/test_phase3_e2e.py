"""Phase 3 end-to-end exit tests (Task 7).

Ties the full pipeline together against the real catalog and versioned
policies: catalog load -> safety gate (normal / caution / missing / restricted
/ red-flag) -> deterministic candidates -> draft validation. Verifies the
workout.cool-pinned comparison concepts hold and that a red flag cannot be
bypassed by substitution or validation.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from app.training.candidates import select_candidates
from app.training.knowledge import build_index, load_catalog, recommendation_ready
from app.training.policy import load_training_policy
from app.training.safety import classify_safety, load_safety_policy
from app.training.schemas import (
    GateStatus, PlanPrescription, PlanSession, TrainingPlanDraft,
    TrainingSafetyContext,
)
from app.training.validator import validate_plan

CATALOG = load_catalog("app/training/data/exercises.v1.json")
SPOLICY = load_safety_policy("app/training/data/training_safety_policy.v1.json")
TPOLICY = load_training_policy("app/training/data/training_policy.v1.json")
INDEX = build_index(CATALOG)
EVAL_AT = datetime(2026, 7, 26, 1, 30, tzinfo=timezone.utc)
REPO_ROOT = Path(__file__).resolve().parents[2]


def _no_screen():
    return {q: "no" for q in (
        "underage", "pregnancy_or_postpartum", "recent_surgery_or_major_injury",
        "major_chronic_condition", "eating_disorder_concern",
        "professional_instruction_limitations")}


def _ctx(**over):
    base = {
        "health": {"configured": True, "fitness_goal": "basic_strength",
                   "training_experience": "experienced", "weekly_frequency": 3,
                   "session_duration_minutes": 30,
                   "equipment_bodyweight": True,
                   "equipment_resistance_band": False, "pain_limitations": [],
                   "risk_screen": _no_screen(), "profile_version": 1,
                   "profile_updated_at": EVAL_AT},
        "checkin": {"present": True, "local_date": "2026-07-26",
                    "recomputed_risk": "normal", "token": "t"},
        "retained_pain": [],
        "posture": {"active_signals_digest": "empty-signals-digest", "global_risk_tier": "normal",
                    "risk_version": "rv",
                    "goals": [{
                        "issue_id": "lower_limb", "active": True,
                        "blocked": False, "confirmed_at": EVAL_AT,
                        "suggestion_id": "s1", "profile_version": "pv1",
                        "rule_version": "rv1", "risk_version": "rv",
                    }]},
        "request": {"fitness_goal": "basic_strength",
                    "equipment_bodyweight": True,
                    "equipment_resistance_band": False,
                    "weekly_frequency": 3,
                    "session_duration_minutes": 30,
                    "iana_timezone": "Asia/Shanghai"},
        "versions": {"policy_version": "v1", "catalog_version":
                     CATALOG.content_version, "source_manifest_version": "v1",
                     "schema_version": "v1"},
        "eval": {"evaluated_at_utc": EVAL_AT, "iana_timezone": "Asia/Shanghai",
                 "current_local_date": "2026-07-26", "timezone_trusted": True},
    }
    base.update(over)
    return TrainingSafetyContext.model_validate(base)


def _run(ctx):
    decision = classify_safety(ctx, SPOLICY)
    cand = select_candidates(ctx, decision, CATALOG, TPOLICY, SPOLICY)
    return decision, cand


def _valid_draft(decision, candidate_id):
    ex = INDEX[candidate_id]
    rx = ex.prescription
    presc = PlanPrescription(
        exercise_id=candidate_id, sets=rx.sets_min,
        reps=rx.reps_min if rx.mode.value == "reps" else None,
        duration_seconds=(rx.duration_seconds_min
                          if rx.mode.value == "duration" else None),
        rest_seconds=rx.rest_seconds_min)
    sessions = []
    for week in (1, 2, 3, 4):
        for order, day in enumerate((1, 3, 5), start=1):
            sessions.append(PlanSession(
                week_index=week, day_of_week=day, session_order=order,
                prescriptions=[presc]))
    return TrainingPlanDraft.model_validate({
        "draft_id": "d1", "requested_goal": "basic_strength",
        "source_context_fingerprint": decision.fingerprint,
        "profile_version": 1, "catalog_version": CATALOG.content_version,
        "policy_version": "v1", "source_manifest_version": "v1",
        "sessions": sessions})


# ---------------------------------------------------------------------------
# Catalog + source audit
# ---------------------------------------------------------------------------


def test_catalog_loads_and_source_audit_is_clean():
    exercises = CATALOG.exercises
    assert 24 <= len(exercises) <= 36
    idx = build_index(CATALOG)
    assert all(recommendation_ready(e, idx, CATALOG.published_at).ready
               for e in exercises)
    # Every SVG exists with a matching sha256 and no external media.
    import re
    url_re = re.compile(r"https?://[^\s\"'<>]+")
    for ex in exercises:
        asset = REPO_ROOT / ex.illustration.asset_key
        assert asset.exists()
        raw = asset.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == (
            ex.illustration.provenance.content_hash)
        text = raw.decode("utf-8")
        assert "<script" not in text and "<image" not in text
        assert all(u == "http://www.w3.org/2000/svg"
                   for u in url_re.findall(text))


def test_third_party_notices_pin_upstream_commits():
    text = (REPO_ROOT / "backend/app/training/data/THIRD_PARTY_NOTICES.md"
            ).read_text(encoding="utf-8")
    assert "7455efae41b330c265e7cd4b78dfa848e7ce5ebd" in text
    assert "77f25a922b51be7d96bd051c5d2096959f0d61a8" in text
    assert "MIT License" in text and "Gym visual" in text


# ---------------------------------------------------------------------------
# Gate matrix -> candidates
# ---------------------------------------------------------------------------


def test_normal_gate_yields_eligible_and_candidates():
    decision, cand = _run(_ctx())
    assert decision.gate_status is GateStatus.eligible
    assert len(cand.candidates) > 0


def test_caution_gate_is_conservative_and_narrows():
    decision, cand = _run(_ctx(health={**_ctx().health.model_dump(),
        "training_experience": "beginner"}))
    assert decision.gate_status is GateStatus.eligible_conservative
    assert cand.conservative is True
    for c in cand.candidates:
        ex = INDEX[c.exercise_id]
        assert ex.prescription.conservative_eligible is True


def test_missing_data_gate_returns_no_candidates():
    decision, cand = _run(_ctx(checkin={"present": False}))
    assert decision.gate_status is GateStatus.clarification_required
    assert cand.candidates == []


def test_restricted_gate_returns_no_candidates():
    screen = _no_screen()
    screen["underage"] = "yes"
    decision, cand = _run(_ctx(health={**_ctx().health.model_dump(),
        "risk_screen": screen}))
    assert decision.gate_status is GateStatus.restricted
    assert cand.candidates == []


def test_red_flag_gate_returns_no_candidates():
    decision, cand = _run(_ctx(checkin={
        "present": True, "local_date": "2026-07-26",
        "recomputed_risk": "red_flag", "token": "t"}))
    assert decision.gate_status is GateStatus.red_flag
    assert cand.candidates == []


# ---------------------------------------------------------------------------
# Deterministic candidates + multi-posture conflict
# ---------------------------------------------------------------------------


def test_candidate_set_is_deterministic():
    _, c1 = _run(_ctx())
    _, c2 = _run(_ctx())
    assert [c.exercise_id for c in c1.candidates] == [
        c.exercise_id for c in c2.candidates]


def test_multi_posture_conflict_is_deterministic_and_deduped():
    health = _ctx().health.model_dump()
    health["fitness_goal"] = "posture_improvement"
    goal_controls = {
        "active": True, "blocked": False, "confirmed_at": EVAL_AT,
        "suggestion_id": "s1", "profile_version": "pv1",
        "rule_version": "rv1", "risk_version": "rv",
    }
    _, cand = _run(_ctx(
        health=health,
        posture={"active_signals_digest": "empty-signals-digest", "global_risk_tier": "normal",
                 "risk_version": "rv",
                 "goals": [{"issue_id": "shoulder_thorax", **goal_controls},
                           {"issue_id": "pelvis_spine", **goal_controls}]},
        request={"fitness_goal": "posture_improvement",
                 "equipment_bodyweight": True,
                 "equipment_resistance_band": False,
                 "weekly_frequency": 3,
                 "session_duration_minutes": 30,
                 "iana_timezone": "Asia/Shanghai"}))
    ids = [c.exercise_id for c in cand.candidates]
    assert len(ids) == len(set(ids))
    # No two survivors share a movement-purpose set.
    purpose_sets = [frozenset(c.movement_purposes) for c in cand.candidates]
    assert len(purpose_sets) == len(set(purpose_sets))
    # Deterministic re-run.
    _, cand2 = _run(_ctx(
        health=health,
        posture={"active_signals_digest": "empty-signals-digest", "global_risk_tier": "normal",
                 "risk_version": "rv",
                 "goals": [{"issue_id": "shoulder_thorax", **goal_controls},
                           {"issue_id": "pelvis_spine", **goal_controls}]},
        request={"fitness_goal": "posture_improvement",
                 "equipment_bodyweight": True,
                 "equipment_resistance_band": False,
                 "weekly_frequency": 3,
                 "session_duration_minutes": 30,
                 "iana_timezone": "Asia/Shanghai"}))
    assert ids == [c.exercise_id for c in cand2.candidates]


# ---------------------------------------------------------------------------
# Draft validation
# ---------------------------------------------------------------------------


def test_valid_draft_passes_validation():
    decision, cand = _run(_ctx())
    draft = _valid_draft(decision, cand.candidates[0].exercise_id)
    result = validate_plan(
        draft, _ctx(), decision, cand, CATALOG, TPOLICY, SPOLICY)
    assert result.valid is True


def test_invalid_draft_out_of_bounds_fails():
    decision, cand = _run(_ctx())
    draft = _valid_draft(decision, cand.candidates[0].exercise_id)
    draft.sessions[0].prescriptions[0] = PlanPrescription(
        exercise_id=draft.sessions[0].prescriptions[0].exercise_id,
        sets=10, reps=10, rest_seconds=60)
    result = validate_plan(
        draft, _ctx(), decision, cand, CATALOG, TPOLICY, SPOLICY)
    assert result.valid is False
    assert "prescription_out_of_bounds" in [v.code for v in result.violations]


def test_stale_catalog_version_fails_validation():
    decision, cand = _run(_ctx())
    draft = _valid_draft(decision, cand.candidates[0].exercise_id)
    draft = draft.model_copy(update={"catalog_version": "stale-version"})
    result = validate_plan(
        draft, _ctx(), decision, cand, CATALOG, TPOLICY, SPOLICY)
    assert result.valid is False
    assert "version_mismatch" in [v.code for v in result.violations]


def test_red_flag_cannot_be_bypassed_by_validation():
    # A red-flag gate invalidates ANY draft, even one built from a "safe"
    # eligible candidate and a matching fingerprint.
    red_ctx = _ctx(checkin={"present": True, "local_date": "2026-07-26",
                            "recomputed_risk": "red_flag", "token": "t"})
    red_decision = classify_safety(red_ctx, SPOLICY)
    red_cand = select_candidates(red_ctx, red_decision, CATALOG, TPOLICY, SPOLICY)
    assert red_cand.candidates == []
    # Craft a draft whose fingerprint matches the red decision (so the ONLY
    # blocker is the gate).
    safe_ex = CATALOG.exercises[0]
    draft = TrainingPlanDraft.model_validate({
        "draft_id": "d", "requested_goal": "basic_strength",
        "source_context_fingerprint": red_decision.fingerprint,
        "profile_version": 1, "catalog_version": CATALOG.content_version,
        "policy_version": "v1", "source_manifest_version": "v1",
        "sessions": [PlanSession(week_index=1, day_of_week=1, session_order=1,
            prescriptions=[PlanPrescription(exercise_id=safe_ex.exercise_id,
                sets=1, reps=8, rest_seconds=60)])] +
        [PlanSession(week_index=w, day_of_week=2, session_order=1,
            prescriptions=[PlanPrescription(exercise_id=safe_ex.exercise_id,
                sets=1, reps=8, rest_seconds=60)])
            for w in (2, 3, 4)]})
    result = validate_plan(
        draft, red_ctx, red_decision, red_cand, CATALOG, TPOLICY, SPOLICY)
    assert result.valid is False
    assert "blocked_context" in [v.code for v in result.violations]
