"""Pure draft-plan validator (Task 6).

``validate_plan`` checks a ``TrainingPlanDraft`` against the current safety
decision, candidate set, catalog and versioned policy. It is PURE and
side-effect-free: it never mutates the draft, substitutes an exercise, lowers
volume, persists a partial result, or calls an LLM.

Contract (spec: Draft plan validation contract, Tool contract):
- drafts have exactly four weeks; every session carries ``week_index`` 1-4,
  ``day_of_week`` 1-7 and a unique in-week ``session_order`` (the sole recovery
  / frequency timeline);
- a blocked (red_flag / restricted / clarification_required), stale-fingerprint
  or version-mismatched context is invalid;
- unknown / non-recommendation-ready / non-candidate exercises, out-of-bounds
  prescriptions, excessive session/weekly volume, inadequate recovery,
  intra-session duplication and relation misuse all produce structured codes;
- validator failure never becomes ``valid=True`` or a repaired plan.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from app.training.knowledge import build_index, recommendation_ready
from app.training.policy import TrainingPolicy
from app.training.safety import SafetyPolicy, classify_safety, compose_fingerprint
from app.training.schemas import (
    CandidateResult,
    ExerciseCatalog,
    GateStatus,
    PlanValidationResult,
    PlanViolation,
    TrainingPlanDraft,
    TrainingSafetyContext,
    TrainingSafetyDecision,
)

_BLOCKING_GATES = frozenset({
    GateStatus.red_flag,
    GateStatus.restricted,
    GateStatus.clarification_required,
})
_ALLOWED_RELATION_REASONS = frozenset({
    "progression", "regression", "substitution", "primary",
})


def _v(code: str, scope: str, detail: str) -> PlanViolation:
    return PlanViolation(code=code, scope=scope, detail=detail)


def validate_plan(
    draft: TrainingPlanDraft,
    context: TrainingSafetyContext,
    decision: TrainingSafetyDecision,
    candidate_result: CandidateResult,
    catalog: ExerciseCatalog,
    policy: TrainingPolicy,
    safety_policy: SafetyPolicy,
) -> PlanValidationResult:
    """Validate a draft plan. Pure; never mutates ``draft``."""
    supplied_decision = decision
    decision = classify_safety(context, safety_policy)
    gate = decision.gate_status
    conservative = gate is GateStatus.eligible_conservative
    violations: List[PlanViolation] = []
    if supplied_decision != decision:
        violations.append(_v(
            "stale_safety_decision", "plan",
            "supplied decision does not match current safety classification"))

    # Blocked context -> invalid (fail closed, no candidate checks).
    if gate in _BLOCKING_GATES:
        violations.append(_v(
            "blocked_context", "plan",
            f"gate={gate.value}; selection blocked"))
        return PlanValidationResult(
            valid=False, gate_status=gate,
            decision_fingerprint=decision.fingerprint, violations=violations,
            profile_version=context.health.profile_version,
            catalog_version=catalog.content_version,
            policy_version=policy.policy_version)

    # Fingerprint + version freshness. Every layer is bound to the same current
    # context; callers cannot splice an eligible decision or candidate set from
    # another user/version into this validation.
    current_fingerprint = compose_fingerprint(context)
    if decision.fingerprint != current_fingerprint:
        violations.append(_v(
            "stale_context_fingerprint", "plan",
            "decision fingerprint != current context fingerprint"))
    if candidate_result.decision_fingerprint != current_fingerprint:
        violations.append(_v(
            "stale_candidate_result", "plan",
            "candidate fingerprint != current context fingerprint"))
    if candidate_result.gate_status != gate:
        violations.append(_v(
            "stale_candidate_result", "plan",
            "candidate gate != current safety gate"))
    if draft.source_context_fingerprint != decision.fingerprint:
        violations.append(_v(
            "stale_context_fingerprint", "plan",
            "draft fingerprint != current decision fingerprint"))
    if draft.catalog_version != catalog.content_version:
        violations.append(_v(
            "version_mismatch", "plan", "catalog_version mismatch"))
    if (draft.policy_version != context.versions.policy_version
            or draft.policy_version != policy.policy_version
            or candidate_result.policy_version != policy.policy_version):
        violations.append(_v(
            "version_mismatch", "plan", "policy_version mismatch"))
    if (draft.source_manifest_version != context.versions.source_manifest_version
            or draft.source_manifest_version != catalog.source_manifest_version):
        violations.append(_v(
            "version_mismatch", "plan", "source_manifest_version mismatch"))
    if draft.profile_version != context.health.profile_version:
        violations.append(_v(
            "version_mismatch", "plan", "profile_version mismatch"))
    if candidate_result.catalog_version != catalog.content_version:
        violations.append(_v(
            "stale_candidate_result", "plan",
            "candidate catalog_version mismatch"))
    if context.versions.catalog_version != catalog.content_version:
        violations.append(_v(
            "version_mismatch", "plan", "context catalog_version mismatch"))
    if policy.policy_version not in catalog.policy_compatibility:
        violations.append(_v(
            "version_mismatch", "plan", "catalog/policy compatibility mismatch"))
    requested_goal = context.request.fitness_goal
    if hasattr(requested_goal, "value"):
        requested_goal = requested_goal.value
    if not requested_goal or draft.requested_goal != requested_goal:
        violations.append(_v(
            "requested_goal_mismatch", "plan",
            "draft requested_goal != current request goal"))

    # Timeline: exactly weeks 1-4; session_order unique within each week.
    weeks_present = sorted({s.week_index for s in draft.sessions})
    if weeks_present != [1, 2, 3, 4]:
        violations.append(_v(
            "timeline_invalid", "plan",
            f"weeks present {weeks_present} must be exactly [1, 2, 3, 4]"))
    by_week: Dict[int, List] = defaultdict(list)
    for s in draft.sessions:
        by_week[s.week_index].append(s)
    for week, sess in by_week.items():
        orders = [s.session_order for s in sess]
        if len(orders) != len(set(orders)):
            violations.append(_v(
                "timeline_invalid", f"week{week}",
                "duplicate session_order within the week"))
        chronological = sorted(sess, key=lambda item: item.day_of_week)
        expected_orders = list(range(1, len(chronological) + 1))
        if [item.session_order for item in chronological] != expected_orders:
            violations.append(_v(
                "timeline_invalid", f"week{week}",
                "session_order must be contiguous and follow day_of_week"))

    index = build_index(catalog)
    ready_ids = {
        e.exercise_id for e in catalog.exercises
        if recommendation_ready(e, index, catalog.published_at).ready
    }
    candidate_ids = {c.exercise_id for c in candidate_result.candidates}

    # Per-session / per-prescription checks.
    for s in draft.sessions:
        scope = f"week{s.week_index}.d{s.day_of_week}.o{s.session_order}"
        n_exercises = len(s.prescriptions)
        n_sets = sum(p.sets for p in s.prescriptions)
        if n_exercises > policy.max_exercises_per_session:
            violations.append(_v("session_volume_exceeded", scope,
                                 "too many exercises in one session"))
        if n_sets > policy.max_sets_per_session:
            violations.append(_v("session_volume_exceeded", scope,
                                 "too many sets in one session"))
        ex_ids = [p.exercise_id for p in s.prescriptions]
        if len(ex_ids) != len(set(ex_ids)):
            violations.append(_v(
                "duplicate_exercise_in_session", scope,
                "same exercise appears more than once in the session"))
        ex_id_set = set(ex_ids)
        incompatible_pairs = set()
        for exercise_id in ex_id_set:
            exercise = index.get(exercise_id)
            if exercise is None:
                continue
            related = set(
                exercise.progression_ids + exercise.regression_ids
                + exercise.substitution_ids)
            for other in ex_id_set & related:
                incompatible_pairs.add(tuple(sorted((exercise_id, other))))
        for first, second in sorted(incompatible_pairs):
            violations.append(_v(
                "incompatible_combination", scope,
                f"{first} and related variant {second} share one session"))
        for p in s.prescriptions:
            _check_prescription(
                p, index, ready_ids, candidate_ids, conservative,
                scope, violations)

    # Weekly frequency vs profile + policy cap.
    freq = context.health.weekly_frequency
    for week, sess in by_week.items():
        if freq is not None and len(sess) > freq:
            violations.append(_v(
                "weekly_frequency_exceeded", f"week{week}",
                f"{len(sess)} sessions > requested weekly_frequency {freq}"))
        if len(sess) > policy.max_sessions_per_week:
            violations.append(_v(
                "weekly_frequency_exceeded", f"week{week}",
                f"{len(sess)} sessions > policy cap "
                f"{policy.max_sessions_per_week}"))

    # Recovery: consecutive sessions + per-exercise recovery floor.
    ordered = sorted(
        draft.sessions,
        key=lambda s: ((s.week_index - 1) * 7 + (s.day_of_week - 1),
                       s.session_order))
    prev_ord: Optional[int] = None
    for s in ordered:
        ordinal = (s.week_index - 1) * 7 + (s.day_of_week - 1)
        if prev_ord is not None:
            gap_hours = (ordinal - prev_ord) * 24
            if gap_hours < policy.min_recovery_hours_between_sessions:
                violations.append(_v(
                    "recovery_violation", "plan",
                    "consecutive sessions closer than the minimum recovery"))
        prev_ord = ordinal

    exercise_days: Dict[str, List[int]] = defaultdict(list)
    exercise_week_days: Dict[tuple, set] = defaultdict(set)
    pattern_uses: Dict[str, Dict[int, tuple]] = defaultdict(dict)
    for s in draft.sessions:
        ordinal = (s.week_index - 1) * 7 + (s.day_of_week - 1)
        for p in s.prescriptions:
            exercise_days[p.exercise_id].append(ordinal)
            exercise_week_days[(p.exercise_id, s.week_index)].add(ordinal)
            ex = index.get(p.exercise_id)
            if ex is not None:
                for pattern in ex.movement_patterns:
                    existing = pattern_uses[pattern].get(ordinal)
                    floor = ex.prescription.recovery_hours_min
                    if existing is None or floor > existing[0]:
                        pattern_uses[pattern][ordinal] = (floor, p.exercise_id)
    for eid, days in exercise_days.items():
        ex = index.get(eid)
        floor = ex.prescription.recovery_hours_min if ex else 0
        unique_days = sorted(set(days))
        for a, b in zip(unique_days, unique_days[1:]):
            if (b - a) * 24 < floor:
                violations.append(_v(
                    "recovery_violation", f"exercise:{eid}",
                    f"re-used before its recovery_hours_min ({floor}h) elapsed"))
    for (eid, week), days in exercise_week_days.items():
        ex = index.get(eid)
        if ex and len(days) > ex.prescription.weekly_sessions_max:
            violations.append(_v(
                "weekly_exercise_frequency_exceeded", f"week{week}",
                f"{eid} exceeds weekly_sessions_max "
                f"{ex.prescription.weekly_sessions_max}"))
    for pattern, uses_by_day in pattern_uses.items():
        ordered_uses = sorted(
            (day, floor, eid)
            for day, (floor, eid) in uses_by_day.items())
        for previous, current in zip(ordered_uses, ordered_uses[1:]):
            prev_day, prev_floor, prev_eid = previous
            day, floor, eid = current
            required = max(prev_floor, floor)
            if (day - prev_day) * 24 < required:
                violations.append(_v(
                    "movement_pattern_recovery_violation", f"pattern:{pattern}",
                    f"{prev_eid} -> {eid} repeats before {required}h"))

    return PlanValidationResult(
        valid=not violations,
        gate_status=gate,
        decision_fingerprint=decision.fingerprint,
        violations=violations,
        profile_version=context.health.profile_version,
        catalog_version=catalog.content_version,
        policy_version=policy.policy_version,
    )


def _check_prescription(p, index, ready_ids, candidate_ids, conservative,
                        scope, violations: List[PlanViolation]) -> None:
    ex = index.get(p.exercise_id)
    if ex is None:
        violations.append(_v("unknown_exercise", scope,
                             f"exercise_id {p.exercise_id!r} not in catalog"))
        return
    if p.exercise_id not in ready_ids:
        violations.append(_v(
            "exercise_not_recommendation_ready", scope,
            f"{p.exercise_id} is not recommendation-ready"))
    if p.exercise_id not in candidate_ids:
        violations.append(_v(
            "exercise_not_candidate", scope,
            f"{p.exercise_id} is not in the current candidate set"))
    rx = ex.prescription
    sets_cap = (rx.conservative_sets_max if conservative else rx.sets_max)
    if p.sets < rx.sets_min or p.sets > sets_cap:
        violations.append(_v(
            "prescription_out_of_bounds", scope,
            f"{p.exercise_id} sets {p.sets} outside [{rx.sets_min}, {sets_cap}]"))
    if rx.mode.value == "reps":
        reps_cap = (rx.conservative_reps_max if conservative else rx.reps_max)
        if p.reps is None or p.reps < rx.reps_min or (reps_cap is not None and p.reps > reps_cap):
            violations.append(_v(
                "prescription_out_of_bounds", scope,
                f"{p.exercise_id} reps missing/out of bounds"))
        if p.duration_seconds is not None:
            violations.append(_v(
                "prescription_out_of_bounds", scope,
                f"{p.exercise_id} is reps-mode; duration_seconds not allowed"))
    else:
        dur_cap = (rx.conservative_duration_seconds_max if conservative
                   else rx.duration_seconds_max)
        if (p.duration_seconds is None or p.duration_seconds < rx.duration_seconds_min
                or (dur_cap is not None and p.duration_seconds > dur_cap)):
            violations.append(_v(
                "prescription_out_of_bounds", scope,
                f"{p.exercise_id} duration missing/out of bounds"))
        if p.reps is not None:
            violations.append(_v(
                "prescription_out_of_bounds", scope,
                f"{p.exercise_id} is duration-mode; reps not allowed"))
    if p.rest_seconds < rx.rest_seconds_min or p.rest_seconds > rx.rest_seconds_max:
        violations.append(_v(
            "prescription_out_of_bounds", scope,
            f"{p.exercise_id} rest {p.rest_seconds} outside bounds"))
    if p.relation_reason is not None:
        reason = p.relation_reason.strip()
        if reason not in _ALLOWED_RELATION_REASONS:
            violations.append(_v(
                "relation_misuse", scope,
                f"{p.exercise_id} relation_reason {reason!r} unknown"))
        elif reason == "primary":
            if p.relation_source_exercise_id is not None:
                violations.append(_v(
                    "relation_misuse", scope,
                    "primary exercise cannot declare a relation source"))
        elif reason in ("progression", "regression", "substitution"):
            source = index.get(p.relation_source_exercise_id or "")
            if source is None:
                violations.append(_v(
                    "relation_misuse", scope,
                    f"{reason} requires a valid relation_source_exercise_id"))
            else:
                rel_ids = {
                    "progression": source.progression_ids,
                    "regression": source.regression_ids,
                    "substitution": source.substitution_ids,
                }[reason]
                if p.exercise_id not in rel_ids:
                    violations.append(_v(
                        "relation_misuse", scope,
                        f"{p.exercise_id} is not a {reason} of "
                        f"{source.exercise_id}"))
    elif p.relation_source_exercise_id is not None:
        violations.append(_v(
            "relation_misuse", scope,
            "relation_source_exercise_id requires relation_reason"))
