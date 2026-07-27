"""Deterministic four-week plan generator (Task 3).

``generate_plan_draft`` is PURE given the Phase 3 engine inputs
(``TrainingSafetyContext`` + ``TrainingSafetyDecision`` + ``CandidateResult`` +
catalog + policies). It produces a complete, executable four-week
``TrainingPlanDraft`` and self-validates it with the Phase 3 pure validator
before returning. A blocked gate, an unsupported goal, an incompatible
frequency, or a self-validation failure yields ``ok=False`` with structured
reason codes and NO draft (fail-closed; never a half-plan).

Design (spec ``2026-07-27-four-week-plan-mvp.md`` Deterministic Generation):

- One consistent exercise set per session (deterministic, no random ordering).
- The day schedule per weekly frequency maximises spacing; the tightest inter-
  session gap (including the week boundary, since the weekly pattern repeats for
  four weeks) sets a per-frequency recovery ceiling. Exercises whose
  ``recovery_hours_min`` exceeds that ceiling, or whose ``weekly_sessions_max``
  is below the requested frequency, are excluded; if the candidate pool then
  cannot form a session, generation fails closed.
- Prescriptions use each exercise's minimum bounds (always within bounds for
  both normal and conservative paths; the conservative path is already reflected
  in ``CandidateResult`` by the Phase 3 candidate engine).
- The draft's fingerprints/versions are populated from the current decision and
  context, never accepted from a client.

No LLM, no HTTP, no DB, no mutation of inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.training.knowledge import build_index
from app.training.policy import TrainingPolicy
from app.training.safety import SafetyPolicy, classify_safety
from app.training.schemas import (
    CandidateResult,
    Exercise,
    ExerciseCatalog,
    GateStatus,
    PlanPrescription,
    PlanSession,
    PlanValidationResult,
    TrainingPlanDraft,
    TrainingSafetyContext,
    TrainingSafetyDecision,
)
from app.training.validator import validate_plan

# Roadmap Phase 4 goals only (vision/roadmap §8). mobility/general_wellness are
# not plan-generation goals in this MVP.
SUPPORTED_GOALS = frozenset({"posture_improvement", "fat_loss", "basic_strength"})

_BLOCKING_GATES = frozenset(
    {GateStatus.red_flag, GateStatus.restricted, GateStatus.clarification_required}
)

# Day-of-week schedule per weekly frequency, chosen to maximise spacing. The
# weekly pattern repeats for weeks 1-4, so the week-boundary gap (last day of a
# week -> first day of the next) is part of the recovery timeline.
_SCHEDULE: dict[int, Tuple[int, ...]] = {
    2: (2, 5),
    3: (1, 3, 5),
    4: (1, 3, 5, 7),
    5: (1, 2, 4, 5, 7),
}

# Tightest inter-session gap (hours), including the week boundary, per
# frequency. Selected exercises must have recovery_hours_min <= this ceiling.
#   freq 2: [2,5] -> within 3d, boundary 5->2 = 4d -> min 3d = 72h
#   freq 3: [1,3,5] -> within 2d, boundary 5->1 = 3d -> min 2d = 48h
#   freq 4: [1,3,5,7] -> within 2d, boundary 7->1 = 1d -> min 1d = 24h
#   freq 5: [1,2,4,5,7] -> within 1d (1->2), boundary 7->1 = 1d -> min 1d = 24h
_FREQ_RECOVERY_CEILING_HOURS: dict[int, int] = {2: 72, 3: 48, 4: 24, 5: 24}

# Target session composition (role preference order) capped by policy.
_ROLE_PREFERENCE = ("warmup", "strength", "corrective", "mobility", "recovery")
_TARGET_PER_ROLE = {"warmup": 1, "strength": 2, "corrective": 2, "mobility": 1, "recovery": 1}


@dataclass(frozen=True)
class GenerationResult:
    """Pure generation outcome (no raw health values)."""

    ok: bool
    gate_status: GateStatus
    requested_goal: Optional[str]
    draft: Optional[TrainingPlanDraft]
    reason_codes: List[str] = field(default_factory=list)
    validation_violations: List[str] = field(default_factory=list)
    decision_fingerprint: Optional[str] = None


def _goal_value(goal) -> Optional[str]:
    return goal.value if hasattr(goal, "value") else goal


def _select_session_exercises(
    candidate_result: CandidateResult,
    catalog: ExerciseCatalog,
    frequency: int,
    max_exercises: int,
) -> List[Exercise]:
    """Pick a deterministic, frequency-compatible exercise set for one session.

    Only candidates whose ``recovery_hours_min`` fits the frequency's tightest
    gap and whose ``weekly_sessions_max`` >= the frequency are eligible (the same
    set is used every session, so each exercise is used ``frequency`` times per
    week). Selection prefers role diversity in ``_ROLE_PREFERENCE`` order and
    NEVER includes two exercises that are related (progression / regression /
    substitution) to each other, which the validator rejects as an incompatible
    combination.
    """
    index = build_index(catalog)
    ceiling = _FREQ_RECOVERY_CEILING_HOURS[frequency]
    compatible: List[Exercise] = []
    seen = set()
    for cand in candidate_result.candidates:
        ex = index.get(cand.exercise_id)
        if ex is None or ex.exercise_id in seen:
            continue
        rx = ex.prescription
        if rx.recovery_hours_min > ceiling:
            continue
        if rx.weekly_sessions_max < frequency:
            continue
        seen.add(ex.exercise_id)
        compatible.append(ex)

    def relations(ex: Exercise) -> set:
        return set(
            list(ex.progression_ids) + list(ex.regression_ids)
            + list(ex.substitution_ids)
        )

    chosen: List[Exercise] = []
    chosen_ids: set = set()
    forbidden: set = set()  # ids that would clash with an already-chosen exercise

    def try_add(ex: Exercise) -> bool:
        if len(chosen) >= max_exercises:
            return False
        if ex.exercise_id in chosen_ids or ex.exercise_id in forbidden:
            return False
        rel = relations(ex)
        if chosen_ids & rel:
            return False
        chosen.append(ex)
        chosen_ids.add(ex.exercise_id)
        forbidden.add(ex.exercise_id)
        forbidden.update(rel)
        return True

    # Pass 1: role-targeted diversity (deterministic; candidate order is the
    # Phase 3 engine's stable sort).
    by_role: dict[str, List[Exercise]] = {}
    for ex in compatible:
        roles = {r.value for r in ex.training_roles}
        for role in _ROLE_PREFERENCE:
            if role in roles:
                by_role.setdefault(role, []).append(ex)
                break
    for role in _ROLE_PREFERENCE:
        target = _TARGET_PER_ROLE.get(role, 1)
        added = 0
        for ex in by_role.get(role, []):
            if added >= target:
                break
            if try_add(ex):
                added += 1

    # Pass 2: top up from the remaining compatible pool.
    for ex in compatible:
        if len(chosen) >= max_exercises:
            break
        try_add(ex)
    return chosen


def _prescription_for(ex: Exercise) -> PlanPrescription:
    """Minimum-bounds prescription (always in bounds for normal/conservative)."""
    rx = ex.prescription
    reps = rx.reps_min if rx.mode.value == "reps" and rx.reps_min is not None else None
    duration = (
        rx.duration_seconds_min
        if rx.mode.value == "duration" and rx.duration_seconds_min is not None
        else None
    )
    return PlanPrescription(
        exercise_id=ex.exercise_id,
        sets=rx.sets_min,
        reps=reps,
        duration_seconds=duration,
        rest_seconds=rx.rest_seconds_min,
    )


def generate_plan_draft(
    ctx: TrainingSafetyContext,
    decision: TrainingSafetyDecision,
    candidate_result: CandidateResult,
    catalog: ExerciseCatalog,
    policy: TrainingPolicy,
    safety_policy: SafetyPolicy,
) -> GenerationResult:
    """Generate a self-validated four-week draft. Pure; no side effects."""
    # Re-classify to guarantee the decision matches the current context (the
    # validator does the same; we surface a clean fail-closed result otherwise).
    current = classify_safety(ctx, safety_policy)
    gate = current.gate_status
    goal = _goal_value(ctx.request.fitness_goal)
    freq = ctx.health.weekly_frequency

    if gate in _BLOCKING_GATES:
        code = {
            GateStatus.clarification_required: "clarification_required",
            GateStatus.restricted: "restricted_no_plan",
            GateStatus.red_flag: "red_flag_stop",
        }[gate]
        return GenerationResult(
            ok=False, gate_status=gate, requested_goal=goal, draft=None,
            reason_codes=[code], decision_fingerprint=current.fingerprint,
        )

    if current != decision:
        return GenerationResult(
            ok=False, gate_status=gate, requested_goal=goal, draft=None,
            reason_codes=["stale_safety_decision"],
            decision_fingerprint=current.fingerprint,
        )

    if goal not in SUPPORTED_GOALS:
        return GenerationResult(
            ok=False, gate_status=gate, requested_goal=goal, draft=None,
            reason_codes=["goal_not_supported_yet"],
            decision_fingerprint=current.fingerprint,
        )

    if freq is None or freq not in _SCHEDULE:
        return GenerationResult(
            ok=False, gate_status=gate, requested_goal=goal, draft=None,
            reason_codes=["invalid_weekly_frequency"],
            decision_fingerprint=current.fingerprint,
        )

    if not candidate_result.candidates:
        return GenerationResult(
            ok=False, gate_status=gate, requested_goal=goal, draft=None,
            reason_codes=["no_eligible_candidates"],
            decision_fingerprint=current.fingerprint,
        )

    exercises = _select_session_exercises(
        candidate_result, catalog, freq, policy.max_exercises_per_session
    )
    if not exercises:
        return GenerationResult(
            ok=False, gate_status=gate, requested_goal=goal, draft=None,
            reason_codes=["insufficient_candidates_for_frequency"],
            decision_fingerprint=current.fingerprint,
        )

    days = _SCHEDULE[freq]
    sessions: List[PlanSession] = []
    for week in (1, 2, 3, 4):
        for order, day in enumerate(days, start=1):
            sessions.append(
                PlanSession(
                    week_index=week,
                    day_of_week=day,
                    session_order=order,
                    prescriptions=[_prescription_for(ex) for ex in exercises],
                )
            )

    draft = TrainingPlanDraft(
        draft_id="generated",
        requested_goal=goal,
        source_context_fingerprint=decision.fingerprint,
        profile_version=ctx.health.profile_version,
        catalog_version=catalog.content_version,
        policy_version=policy.policy_version,
        source_manifest_version=catalog.source_manifest_version,
        sessions=sessions,
    )

    validation: PlanValidationResult = validate_plan(
        draft, ctx, decision, candidate_result, catalog, policy, safety_policy
    )
    if not validation.valid:
        return GenerationResult(
            ok=False, gate_status=gate, requested_goal=goal, draft=None,
            reason_codes=["self_validation_failed"],
            validation_violations=[v.code for v in validation.violations],
            decision_fingerprint=current.fingerprint,
        )

    return GenerationResult(
        ok=True, gate_status=gate, requested_goal=goal, draft=draft,
        decision_fingerprint=current.fingerprint,
    )


__all__ = [
    "SUPPORTED_GOALS",
    "GenerationResult",
    "generate_plan_draft",
]
