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
) -> PlanValidationResult:
    """Validate a draft plan. Pure; never mutates ``draft``."""
    gate = decision.gate_status
    conservative = gate is GateStatus.eligible_conservative
    violations: List[PlanViolation] = []

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

    # Fingerprint + version freshness.
    if draft.source_context_fingerprint != decision.fingerprint:
        violations.append(_v(
            "stale_context_fingerprint", "plan",
            "draft fingerprint != current decision fingerprint"))
    if draft.catalog_version != catalog.content_version:
        violations.append(_v(
            "version_mismatch", "plan", "catalog_version mismatch"))
    if draft.policy_version != context.versions.policy_version:
        violations.append(_v(
            "version_mismatch", "plan", "policy_version mismatch"))
    if draft.source_manifest_version != context.versions.source_manifest_version:
        violations.append(_v(
            "version_mismatch", "plan", "source_manifest_version mismatch"))
    if (draft.profile_version is not None
            and draft.profile_version != context.health.profile_version):
        violations.append(_v(
            "version_mismatch", "plan", "profile_version mismatch"))

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
    for s in draft.sessions:
        ordinal = (s.week_index - 1) * 7 + (s.day_of_week - 1)
        for p in s.prescriptions:
            exercise_days[p.exercise_id].append(ordinal)
    for eid, days in exercise_days.items():
        ex = index.get(eid)
        floor = ex.prescription.recovery_hours_min if ex else 0
        unique_days = sorted(set(days))
        for a, b in zip(unique_days, unique_days[1:]):
            if (b - a) * 24 < floor:
                violations.append(_v(
                    "recovery_violation", f"exercise:{eid}",
                    f"re-used before its recovery_hours_min ({floor}h) elapsed"))

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
        elif reason in ("progression", "regression", "substitution"):
            rel_ids = {"progression": ex.progression_ids,
                       "regression": ex.regression_ids,
                       "substitution": ex.substitution_ids}[reason]
            if not rel_ids:
                violations.append(_v(
                    "relation_misuse", scope,
                    f"{p.exercise_id} has no {reason} relation defined"))
