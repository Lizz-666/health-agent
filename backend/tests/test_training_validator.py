"""Pure draft-plan validator tests (Task 6).

Valid synthetic draft passes; each invalid case fails with a stable violation
code. The validator never mutates the input.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.training.candidates import select_candidates
from app.training.knowledge import build_index, load_catalog
from app.training.policy import load_training_policy
from app.training.safety import classify_safety, load_safety_policy
from app.training.schemas import (
    PlanPrescription, PlanSession, TrainingPlanDraft,
    TrainingSafetyContext,
)
from app.training.validator import validate_plan

CATALOG = load_catalog("app/training/data/exercises.v1.json")
SPOLICY = load_safety_policy("app/training/data/training_safety_policy.v1.json")
TPOLICY = load_training_policy("app/training/data/training_policy.v1.json")
INDEX = build_index(CATALOG)
EVAL_AT = datetime(2026, 7, 26, 1, 30, tzinfo=timezone.utc)


def _no_screen():
    return {q: "no" for q in (
        "underage", "pregnancy_or_postpartum", "recent_surgery_or_major_injury",
        "major_chronic_condition", "eating_disorder_concern",
        "professional_instruction_limitations")}


def _ctx():
    return TrainingSafetyContext.model_validate({
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
    })


CTX = _ctx()
DECISION = classify_safety(CTX, SPOLICY)
CANDIDATES = select_candidates(CTX, DECISION, CATALOG, TPOLICY, SPOLICY)
CAND_ID = CANDIDATES.candidates[0].exercise_id


def _presc(eid=CAND_ID, *, sets=None, reps=None, duration=None, rest=None,
           relation=None):
    ex = INDEX[eid]
    rx = ex.prescription
    return PlanPrescription(
        exercise_id=eid,
        sets=sets if sets is not None else rx.sets_min,
        reps=reps if reps is not None else (
            rx.reps_min if rx.mode.value == "reps" else None),
        duration_seconds=duration if duration is not None else (
            rx.duration_seconds_min if rx.mode.value == "duration" else None),
        rest_seconds=rest if rest is not None else rx.rest_seconds_min,
        relation_reason=relation,
    )


def _valid_draft(exercise_id=CAND_ID, fingerprint=None, **over):
    sessions = []
    for week in (1, 2, 3, 4):
        for order, day in enumerate((1, 3, 5), start=1):
            sessions.append(PlanSession(
                week_index=week, day_of_week=day, session_order=order,
                prescriptions=[_presc(exercise_id)]))
    base = {
        "draft_id": "d1", "requested_goal": "basic_strength",
        "source_context_fingerprint": fingerprint or DECISION.fingerprint,
        "profile_version": CTX.health.profile_version,
        "catalog_version": CATALOG.content_version, "policy_version": "v1",
        "source_manifest_version": "v1", "sessions": sessions,
    }
    base.update(over)
    return TrainingPlanDraft.model_validate(base)


def _validate(draft, ctx=CTX, decision=DECISION, cand=CANDIDATES):
    return validate_plan(
        draft, ctx, decision, cand, CATALOG, TPOLICY, SPOLICY)


def test_valid_draft_passes():
    result = _validate(_valid_draft())
    assert result.valid is True
    assert result.violations == []


def test_blocked_context_is_invalid():
    blocked = CTX.model_copy(update={"checkin": CTX.checkin.model_copy(
        update={"recomputed_risk": "red_flag"})})
    blocked_decision = classify_safety(blocked, SPOLICY)
    result = _validate(_valid_draft(), ctx=blocked, decision=blocked_decision)
    assert result.valid is False
    codes = [v.code for v in result.violations]
    assert "blocked_context" in codes


def test_validator_recomputes_and_rejects_forged_eligible_decision():
    blocked = CTX.model_copy(update={"checkin": CTX.checkin.model_copy(
        update={"recomputed_risk": "red_flag"})})
    result = _validate(_valid_draft(), ctx=blocked, decision=DECISION)
    codes = [v.code for v in result.violations]
    assert result.valid is False
    assert result.gate_status.value == "red_flag"
    assert "stale_safety_decision" in codes
    assert "blocked_context" in codes


def test_stale_fingerprint_is_invalid():
    draft = _valid_draft(fingerprint="stale-not-current")
    result = _validate(draft)
    assert result.valid is False
    assert "stale_context_fingerprint" in [v.code for v in result.violations]


def test_stale_candidate_result_is_invalid():
    stale = CANDIDATES.model_copy(update={"decision_fingerprint": "old"})
    result = _validate(_valid_draft(), cand=stale)
    assert "stale_candidate_result" in [v.code for v in result.violations]


def test_requested_goal_mismatch_is_invalid():
    result = _validate(_valid_draft(requested_goal="fat_loss"))
    assert "requested_goal_mismatch" in [v.code for v in result.violations]


def test_profile_version_is_required_by_draft_schema():
    payload = _valid_draft().model_dump()
    payload.pop("profile_version")
    with pytest.raises(Exception):
        TrainingPlanDraft.model_validate(payload)


def test_catalog_version_mismatch_is_invalid():
    draft = _valid_draft(catalog_version="wrong-version")
    result = _validate(draft)
    assert result.valid is False
    assert "version_mismatch" in [v.code for v in result.violations]


def test_unknown_exercise_is_invalid():
    draft = _valid_draft()
    draft.sessions[0].prescriptions[0] = PlanPrescription(
        exercise_id="ex_does_not_exist", sets=3, reps=10, rest_seconds=60)
    result = _validate(draft)
    codes = [v.code for v in result.violations]
    assert "unknown_exercise" in codes


def test_non_candidate_exercise_is_invalid():
    # Use a band-only exercise for a bodyweight-only user -> not a candidate.
    draft = _valid_draft("ex_strength_band_bicep_curl")
    result = _validate(draft)
    codes = [v.code for v in result.violations]
    assert "exercise_not_candidate" in codes


def test_prescription_out_of_bounds_sets():
    draft = _valid_draft()
    # 10 is schema-valid (<=10) but above the exercise sets_max (4) -> out of
    # bounds.
    draft.sessions[0].prescriptions[0] = _presc(sets=10)
    result = _validate(draft)
    codes = [v.code for v in result.violations]
    assert "prescription_out_of_bounds" in codes


def test_weekly_frequency_exceeded():
    # 4 sessions in week 1 while requested weekly_frequency is 3.
    sessions = []
    for week in (1, 2, 3, 4):
        days = (1, 2, 3, 4) if week == 1 else (1, 3, 5)
        for order, day in enumerate(days, start=1):
            sessions.append(PlanSession(
                week_index=week, day_of_week=day, session_order=order,
                prescriptions=[_presc()]))
    draft = TrainingPlanDraft.model_validate({
        "draft_id": "d1", "requested_goal": "basic_strength",
        "source_context_fingerprint": DECISION.fingerprint,
        "profile_version": CTX.health.profile_version,
        "catalog_version": CATALOG.content_version, "policy_version": "v1",
        "source_manifest_version": "v1", "sessions": sessions})
    result = _validate(draft)
    assert result.valid is False
    assert "weekly_frequency_exceeded" in [v.code for v in result.violations]


def test_recovery_violation_consecutive_days():
    # Two sessions on consecutive days -> below the 24h minimum recovery.
    sessions = []
    for week in (1, 2, 3, 4):
        for order, day in enumerate((1, 2, 3), start=1):  # Mon/Tue/Wed
            sessions.append(PlanSession(
                week_index=week, day_of_week=day, session_order=order,
                prescriptions=[_presc()]))
    draft = TrainingPlanDraft.model_validate({
        "draft_id": "d1", "requested_goal": "basic_strength",
        "source_context_fingerprint": DECISION.fingerprint,
        "profile_version": CTX.health.profile_version,
        "catalog_version": CATALOG.content_version, "policy_version": "v1",
        "source_manifest_version": "v1", "sessions": sessions})
    result = _validate(draft)
    codes = [v.code for v in result.violations]
    assert "recovery_violation" in codes
    assert "movement_pattern_recovery_violation" in codes


def test_exercise_weekly_frequency_limit_is_enforced():
    catalog = CATALOG.model_copy(deep=True)
    exercise = next(e for e in catalog.exercises if e.exercise_id == CAND_ID)
    exercise.prescription.weekly_sessions_max = 1
    result = validate_plan(
        _valid_draft(), CTX, DECISION, CANDIDATES, catalog, TPOLICY, SPOLICY)
    assert "weekly_exercise_frequency_exceeded" in [
        v.code for v in result.violations]


def test_duplicate_exercise_in_session():
    draft = _valid_draft()
    s = draft.sessions[0]
    s.prescriptions.append(_presc())  # same exercise twice
    result = _validate(draft)
    assert "duplicate_exercise_in_session" in [
        v.code for v in result.violations]


def test_related_variants_in_one_session_are_incompatible():
    draft = _valid_draft()
    source = INDEX[CAND_ID]
    related_id = (source.progression_ids + source.regression_ids
                  + source.substitution_ids)[0]
    draft.sessions[0].prescriptions.append(_presc(related_id))
    result = _validate(draft)
    assert "incompatible_combination" in [v.code for v in result.violations]


def test_relation_misuse_unknown_reason():
    draft = _valid_draft()
    draft.sessions[0].prescriptions[0] = _presc(relation="bogus_reason")
    result = _validate(draft)
    assert "relation_misuse" in [v.code for v in result.violations]


def test_relation_misuse_no_such_relation():
    # glute_bridge (CAND_ID) defines progression/substitution but NO regression,
    # so claiming "regression" is misuse.
    draft = _valid_draft()
    ex = INDEX[CAND_ID]
    assert not ex.regression_ids  # precondition
    draft.sessions[0].prescriptions[0] = _presc(relation="regression")
    result = _validate(draft)
    assert "relation_misuse" in [v.code for v in result.violations]


def test_timeline_invalid_only_three_weeks():
    sessions = [s for s in _valid_draft().sessions if s.week_index != 4]
    draft = TrainingPlanDraft.model_validate({
        "draft_id": "d1", "requested_goal": "basic_strength",
        "source_context_fingerprint": DECISION.fingerprint,
        "profile_version": CTX.health.profile_version,
        "catalog_version": CATALOG.content_version, "policy_version": "v1",
        "source_manifest_version": "v1", "sessions": sessions})
    result = _validate(draft)
    assert "timeline_invalid" in [v.code for v in result.violations]


def test_session_order_must_follow_day_chronology():
    draft = _valid_draft()
    week_one = [s for s in draft.sessions if s.week_index == 1]
    week_one[0].session_order = 3
    week_one[1].session_order = 1
    week_one[2].session_order = 2
    result = _validate(draft)
    assert "timeline_invalid" in [v.code for v in result.violations]


def test_validator_does_not_mutate_input():
    draft = _valid_draft()
    before = draft.model_dump_json()
    _validate(draft)
    assert draft.model_dump_json() == before


def test_valid_result_carries_no_raw_values():
    result = _validate(_valid_draft())
    blob = result.model_dump_json()
    assert "pain_note" not in blob
