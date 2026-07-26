"""Property / invariant tests for the candidate engine (Task 5).

Uses Hypothesis to assert invariants that must hold for ANY eligible context:
forbidden exercises never appear, candidate IDs are unique, no two candidates
share a movement-purpose set, every candidate is recommendation-ready /
goal-matched / equipment-compatible / non-contraindicated / (when conservative)
conservative-eligible, and output order is always sorted. Non-eligible gates
always yield zero candidates.
"""
from __future__ import annotations

from datetime import datetime, timezone

from hypothesis import given, settings, strategies as st

from app.training.candidates import select_candidates
from app.training.knowledge import build_index, load_catalog, recommendation_ready
from app.training.policy import load_training_policy
from app.training.safety import classify_safety, load_safety_policy
from app.training.schemas import TrainingSafetyContext

CATALOG = load_catalog("app/training/data/exercises.v1.json")
SPOLICY = load_safety_policy("app/training/data/training_safety_policy.v1.json")
TPOLICY = load_training_policy("app/training/data/training_policy.v1.json")
EVAL_AT = datetime(2026, 7, 26, 1, 30, tzinfo=timezone.utc)

INDEX = build_index(CATALOG)
READY_IDS = {e.exercise_id for e in CATALOG.exercises
             if recommendation_ready(e, INDEX, CATALOG.published_at).ready}

GOALS = ["basic_strength", "fat_loss", "mobility",
         "posture_improvement", "general_wellness"]
POSTURE_ISSUES = ["head_neck", "shoulder_thorax", "pelvis_spine", "lower_limb"]
PAIN_REGIONS = list(SPOLICY.body_region_aliases.keys())


def _no_screen():
    return {q: "no" for q in (
        "underage", "pregnancy_or_postpartum", "recent_surgery_or_major_injury",
        "major_chronic_condition", "eating_disorder_concern",
        "professional_instruction_limitations")}


def _build(goal, bw, band, posture_goals, pain_regions, experience):
    health = {
        "configured": True, "fitness_goal": goal,
        "training_experience": experience, "weekly_frequency": 3,
        "session_duration_minutes": 30,
        "equipment_bodyweight": bw, "equipment_resistance_band": band,
        "pain_limitations": [
            {"body_area_raw": r, "status_raw": "aching",
             "body_area_canonical": r, "status_canonical": "aching"}
            for r in sorted(set(pain_regions))
        ],
        "risk_screen": _no_screen(), "profile_version": 1,
        "profile_updated_at": EVAL_AT,
    }
    return TrainingSafetyContext.model_validate({
        "health": health,
        "checkin": {"present": True, "local_date": "2026-07-26",
                    "recomputed_risk": "normal", "token": "t"},
        "retained_pain": [],
        "posture": {"active_signals_digest": "empty-signals-digest", "global_risk_tier": "normal",
                    "risk_version": "rv",
                    "goals": [{
                        "issue_id": i, "active": True, "blocked": False,
                        "confirmed_at": EVAL_AT, "suggestion_id": "s1",
                        "profile_version": "pv1", "rule_version": "rv1",
                        "risk_version": "rv",
                    }
                              for i in posture_goals]},
        "request": {"fitness_goal": goal, "equipment_bodyweight": bw,
                    "equipment_resistance_band": band,
                    "weekly_frequency": 3, "session_duration_minutes": 30,
                    "iana_timezone": "Asia/Shanghai"},
        "versions": {"policy_version": "v1", "catalog_version":
                     CATALOG.content_version, "source_manifest_version": "v1",
                     "schema_version": "v1"},
        "eval": {"evaluated_at_utc": EVAL_AT, "iana_timezone": "Asia/Shanghai",
                 "current_local_date": "2026-07-26", "timezone_trusted": True},
    })


def _run(ctx):
    decision = classify_safety(ctx, SPOLICY)
    return decision, select_candidates(ctx, decision, CATALOG, TPOLICY, SPOLICY)


_eligible_contexts = st.builds(
    _build,
    goal=st.sampled_from(GOALS),
    bw=st.booleans(),
    band=st.booleans(),
    posture_goals=st.lists(st.sampled_from(POSTURE_ISSUES), min_size=1,
                           max_size=4, unique=True),
    pain_regions=st.lists(st.sampled_from(PAIN_REGIONS), max_size=3),
    experience=st.sampled_from(["beginner", "experienced"]),
).filter(lambda c: (c.request.equipment_bodyweight
                    or c.request.equipment_resistance_band))


@settings(max_examples=60, deadline=None)
@given(ctx=_eligible_contexts)
def test_invariants_for_any_eligible_context(ctx):
    decision, result = _run(ctx)
    # Eligible-family gate (eligible or eligible_conservative).
    assert decision.gate_status.value in ("eligible", "eligible_conservative")

    ids = [c.exercise_id for c in result.candidates]
    # Unique IDs.
    assert len(ids) == len(set(ids))
    # Every candidate is recommendation-ready.
    assert all(i in READY_IDS for i in ids)
    # Every candidate matches the requested goal.
    for c in result.candidates:
        ex = next(e for e in CATALOG.exercises if e.exercise_id == c.exercise_id)
        assert ctx.request.fitness_goal in {g.value for g in ex.goals}
        # Equipment-compatible.
        req = set()
        if ctx.request.equipment_bodyweight:
            req.add("bodyweight")
        if ctx.request.equipment_resistance_band:
            req.add("resistance_band")
        assert req & {q.value for q in ex.equipment}
        # Not contraindicated by the user's pain regions.
        pain_regions = {lim.body_area_canonical
                        for lim in ctx.health.pain_limitations or []}
        assert not (set(ex.contraindications.body_regions) & pain_regions)
        # Conservative-eligible when conservative.
        if result.conservative:
            assert ex.prescription.conservative_eligible is True
    # No two candidates share a movement-purpose set.
    purpose_sets = [frozenset(c.movement_purposes) for c in result.candidates]
    assert len(purpose_sets) == len(set(purpose_sets))
    # Order is sorted by sort_key.
    assert [c.sort_key for c in result.candidates] == sorted(
        c.sort_key for c in result.candidates)


@settings(max_examples=20, deadline=None)
@given(ctx=_eligible_contexts)
def test_red_flag_overrides_to_zero_candidates(ctx):
    # Force a red-flag check-in on top of an otherwise eligible context.
    mutated = ctx.model_copy(update={"checkin": ctx.checkin.model_copy(
        update={"recomputed_risk": "red_flag"})})
    decision, result = _run(mutated)
    assert decision.gate_status.value == "red_flag"
    assert result.candidates == []
    assert result.excluded == []


def test_restricted_user_gets_zero_candidates():
    screen = _no_screen()
    screen["pregnancy_or_postpartum"] = "yes"
    ctx = _build("basic_strength", True, False, ["lower_limb"], [], "experienced")
    ctx = ctx.model_copy(update={"health": ctx.health.model_copy(
        update={"risk_screen": screen})})
    decision, result = _run(ctx)
    assert decision.gate_status.value == "restricted"
    assert result.candidates == []
