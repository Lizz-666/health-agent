"""Deterministic four-week generator tests (Task 3).

Property grounding: for every supported (goal, frequency) the generator either
produces a draft that INDEPENDENTLY re-validates clean, or fails closed with a
known reason code (the real catalog may not support every high-frequency goal
with recovery<=24 candidates). Plus the safety matrix: normal, caution,
restricted, red_flag, clarification_required, unsupported goal, stale decision,
empty candidates. Synthetic data only; uses the real catalog/policies.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.training.candidates import select_candidates
from app.training.generator import SUPPORTED_GOALS, generate_plan_draft
from app.training.knowledge import build_index, load_catalog
from app.training.policy import load_training_policy
from app.training.safety import classify_safety, load_safety_policy
from app.training.schemas import TrainingSafetyContext
from app.training.validator import validate_plan

CATALOG = load_catalog("app/training/data/exercises.v1.json")
SPOLICY = load_safety_policy("app/training/data/training_safety_policy.v1.json")
TPOLICY = load_training_policy("app/training/data/training_policy.v1.json")
INDEX = build_index(CATALOG)
EVAL_AT = datetime(2026, 7, 26, 1, 30, tzinfo=timezone.utc)

_NO_SCREEN = {q: "no" for q in (
    "underage", "pregnancy_or_postpartum", "recent_surgery_or_major_injury",
    "major_chronic_condition", "eating_disorder_concern",
    "professional_instruction_limitations")}


def _ctx(*, goal="basic_strength", freq=3, duration=30, bodyweight=True,
         band=False, risk_screen=None, checkin_risk="normal", checkin_present=True,
         posture_goal="lower_limb", profile_version=1):
    return TrainingSafetyContext.model_validate({
        "health": {"configured": True, "fitness_goal": goal,
                   "training_experience": "experienced", "weekly_frequency": freq,
                   "session_duration_minutes": duration,
                   "equipment_bodyweight": bodyweight,
                   "equipment_resistance_band": band, "pain_limitations": [],
                   "risk_screen": risk_screen if risk_screen is not None else _NO_SCREEN,
                   "profile_version": profile_version,
                   "profile_updated_at": EVAL_AT},
        "checkin": {"present": checkin_present, "local_date": "2026-07-26",
                    "recomputed_risk": checkin_risk, "token": "t"},
        "retained_pain": [],
        "posture": {"active_signals_digest": "empty-signals-digest",
                    "global_risk_tier": "normal", "risk_version": "rv",
                    "goals": [{"issue_id": posture_goal, "active": True,
                               "blocked": False, "confirmed_at": EVAL_AT,
                               "suggestion_id": "s1", "profile_version": "pv1",
                               "rule_version": "rv1", "risk_version": "rv"}]},
        "request": {"fitness_goal": goal, "equipment_bodyweight": bodyweight,
                    "equipment_resistance_band": band, "weekly_frequency": freq,
                    "session_duration_minutes": duration,
                    "iana_timezone": "Asia/Shanghai"},
        "versions": {"policy_version": "v1",
                     "catalog_version": CATALOG.content_version,
                     "source_manifest_version": "v1", "schema_version": "v1"},
        "eval": {"evaluated_at_utc": EVAL_AT, "iana_timezone": "Asia/Shanghai",
                 "current_local_date": "2026-07-26", "timezone_trusted": True},
    })


def _gen(ctx):
    decision = classify_safety(ctx, SPOLICY)
    cand = select_candidates(ctx, decision, CATALOG, TPOLICY, SPOLICY)
    return generate_plan_draft(ctx, decision, cand, CATALOG, TPOLICY, SPOLICY), decision, cand


# --- property grounding across the real catalog ----------------------------


@pytest.mark.parametrize("goal", sorted(SUPPORTED_GOALS))
@pytest.mark.parametrize("freq", [2, 3, 4, 5])
def test_generate_either_valid_draft_or_clean_fail_closed(goal, freq):
    ctx = _ctx(goal=goal, freq=freq)
    result, decision, cand = _gen(ctx)
    if result.ok:
        # An ok draft MUST independently re-validate clean and be well-formed.
        assert result.draft is not None
        validation = validate_plan(
            result.draft, ctx, decision, cand, CATALOG, TPOLICY, SPOLICY)
        assert validation.valid, (
            f"generator produced a draft that fails validation: "
            f"{[v.code for v in validation.violations]}"
        )
        weeks = sorted({s.week_index for s in result.draft.sessions})
        assert weeks == [1, 2, 3, 4]
        for s in result.draft.sessions:
            assert s.week_index in (1, 2, 3, 4)
            assert 1 <= s.day_of_week <= 7
            assert s.prescriptions
        # Every prescribed exercise traces to the catalog.
        for s in result.draft.sessions:
            for p in s.prescriptions:
                assert p.exercise_id in INDEX
    else:
        # A failure must be fail-closed: no draft, a known reason code.
        assert result.draft is None
        assert result.reason_codes
        assert result.reason_codes[0] in {
            "no_eligible_candidates",
            "insufficient_candidates_for_frequency",
        }


def test_normal_basic_strength_freq3_generates_valid_draft():
    # The canonical case (mirrors the Phase 3 validator test's known-good setup).
    ctx = _ctx(goal="basic_strength", freq=3)
    result, _, _ = _gen(ctx)
    assert result.ok is True
    assert result.draft is not None
    # Frequency maps to the reviewed day schedule.
    days = sorted({s.day_of_week for s in result.draft.sessions
                   if s.week_index == 1})
    assert days == [1, 3, 5]
    assert {s.week_index for s in result.draft.sessions} == {1, 2, 3, 4}


def test_generation_is_deterministic_for_equal_inputs():
    ctx = _ctx(goal="posture_improvement", freq=3)
    r1, _, _ = _gen(ctx)
    r2, _, _ = _gen(ctx)
    assert r1.ok == r2.ok
    if r1.ok and r2.ok:
        d1 = r1.draft.model_dump_json()
        d2 = r2.draft.model_dump_json()
        assert d1 == d2


# --- safety matrix ---------------------------------------------------------


def test_restricted_user_gets_no_plan():
    screen = dict(_NO_SCREEN)
    screen["pregnancy_or_postpartum"] = "yes"
    ctx = _ctx(risk_screen=screen)
    decision = classify_safety(ctx, SPOLICY)
    assert decision.gate_status.value == "restricted"
    result, _, _ = _gen(ctx)
    assert result.ok is False
    assert result.draft is None
    assert result.reason_codes == ["restricted_no_plan"]


def test_red_flag_user_gets_no_plan():
    ctx = _ctx(checkin_risk="red_flag")
    decision = classify_safety(ctx, SPOLICY)
    assert decision.gate_status.value == "red_flag"
    result, _, _ = _gen(ctx)
    assert result.ok is False
    assert result.draft is None
    assert result.reason_codes == ["red_flag_stop"]


def test_missing_checkin_returns_clarification_required():
    ctx = _ctx(checkin_present=False)
    # Remove the recomputed risk so the checkin is genuinely missing.
    ctx = ctx.model_copy(update={"checkin": ctx.checkin.model_copy(update={"present": False, "recomputed_risk": None, "token": None, "local_date": None})})
    decision = classify_safety(ctx, SPOLICY)
    assert decision.gate_status.value == "clarification_required"
    result, _, _ = _gen(ctx)
    assert result.ok is False
    assert result.reason_codes == ["clarification_required"]


def test_unsupported_goal_returns_goal_not_supported_yet():
    # An eligible context but with a goal not supported for plan generation.
    ctx = _ctx(goal="mobility", freq=3)
    decision = classify_safety(ctx, SPOLICY)
    if decision.gate_status.value in {"red_flag", "restricted", "clarification_required"}:
        pytest.skip("catalog/profile does not yield an eligible gate for mobility here")
    result, _, _ = _gen(ctx)
    assert result.ok is False
    assert result.reason_codes == ["goal_not_supported_yet"]


def test_stale_decision_is_rejected():
    ctx = _ctx(goal="basic_strength", freq=3)
    decision = classify_safety(ctx, SPOLICY)
    cand = select_candidates(ctx, decision, CATALOG, TPOLICY, SPOLICY)
    # Tamper with the decision fingerprint to simulate a stale decision.
    stale = decision.model_copy(update={"fingerprint": "stale-" + decision.fingerprint})
    result = generate_plan_draft(ctx, stale, cand, CATALOG, TPOLICY, SPOLICY)
    assert result.ok is False
    assert result.reason_codes == ["stale_safety_decision"]
    assert result.draft is None


def test_self_validation_failure_is_fail_closed_and_reported():
    # Hand the generator an eligible context but an EMPTY candidate set: it must
    # not fabricate a draft; it fails closed with a known code.
    ctx = _ctx(goal="basic_strength", freq=3)
    decision = classify_safety(ctx, SPOLICY)
    empty_cand = select_candidates(ctx, decision, CATALOG, TPOLICY, SPOLICY).model_copy(
        update={"candidates": [], "excluded": []}
    )
    result = generate_plan_draft(ctx, decision, empty_cand, CATALOG, TPOLICY, SPOLICY)
    assert result.ok is False
    assert result.draft is None
    assert result.reason_codes == ["no_eligible_candidates"]
