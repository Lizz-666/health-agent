"""Deterministic training candidate engine (Task 5).

Executes the exact filter order from the versioned policy and the spec
(Candidate Selection):

    validate context (gate) -> recommendation-ready -> equipment ->
    goal + confirmed-posture-signal -> contraindication / not-applicable ->
    conservative (when needed) -> de-duplicate by movement purpose ->
    resolve conflicts by explicit priority -> stable sort -> return trace.

Hard rules (spec: Candidate Selection, Safety):

- Non-eligible gates (red_flag / restricted / clarification_required) return
  ZERO candidates and ZERO excluded exercise IDs (restricted/red_flag expose no
  candidate IDs).
- Every returned exercise is recommendation-ready, equipment-compatible, goal-
  matched, posture-applicable, non-contraindicated and (when conservative)
  conservative-eligible.
- Contraindications always beat goals / applicability.
- Output order is deterministic; conflicts resolve by versioned priority, never
  random order or prose.

The engine is PURE: it consumes an already-built context + decision + catalog +
policy. No HTTP / DB / LLM.
"""
from __future__ import annotations

from typing import List

from app.training.knowledge import build_index, recommendation_ready
from app.training.policy import TrainingPolicy
from app.training.safety import SafetyPolicy
from app.training.schemas import (
    Candidate,
    CandidateResult,
    Exercise,
    ExerciseCatalog,
    GateStatus,
    ExcludedExercise,
    TrainingSafetyContext,
    TrainingSafetyDecision,
)

_BLOCKING_GATES = frozenset({
    GateStatus.red_flag,
    GateStatus.restricted,
    GateStatus.clarification_required,
})


def _sort_key(ex: Exercise, policy: TrainingPolicy) -> str:
    role_idx = policy.role_index([r.value for r in ex.training_roles])
    diff_idx = policy.difficulty_index(ex.difficulty)
    return f"{role_idx:02d}.{diff_idx:02d}.{ex.exercise_id}"


def _requested_equipment(ctx: TrainingSafetyContext) -> set:
    out = set()
    if ctx.request.equipment_bodyweight:
        out.add("bodyweight")
    if ctx.request.equipment_resistance_band:
        out.add("resistance_band")
    return out


def _exclude_reasons(
    ex: Exercise, ctx: TrainingSafetyContext, policy: TrainingPolicy,
    conservative: bool, ready_ids: set,
) -> List[str]:
    reasons: List[str] = []

    if ex.exercise_id not in ready_ids:
        reasons.append("not_recommendation_ready")

    req_equip = _requested_equipment(ctx)
    ex_equip = {e.value for e in ex.equipment}
    if req_equip and not (ex_equip & req_equip):
        reasons.append("equipment_incompatible")

    goal = ctx.request.fitness_goal
    ex_goals = {g.value for g in ex.goals}
    if goal and goal not in ex_goals:
        reasons.append("goal_not_matched")

    active_goal_issues = {
        g.issue_id for g in ctx.posture.goals if g.active and not g.blocked
    }
    applicable = set(ex.applicable_posture_signals)
    # General exercises (no posture mapping) are applicable to any goal; a
    # specific exercise must intersect at least one confirmed goal signal.
    if applicable and active_goal_issues and not (applicable & active_goal_issues):
        reasons.append("posture_signal_not_applicable")
    if set(ex.not_applicable_posture_signals) & active_goal_issues:
        reasons.append("posture_not_applicable")

    contra = ex.contraindications
    risk_screen = ctx.health.risk_screen or {}
    restricted_quals = {q for q, v in risk_screen.items() if v == "yes"}
    if set(contra.risk_qualifiers) & restricted_quals:
        reasons.append("contraindicated_risk_qualifier")
    pain_regions = {
        lim.body_area_canonical
        for lim in (ctx.health.pain_limitations or [])
        if lim.body_area_canonical
    }
    if set(contra.body_regions) & pain_regions:
        reasons.append("contraindicated_body_region")

    if (conservative and policy.conservative_requires_conservative_eligible
            and not ex.prescription.conservative_eligible):
        reasons.append("not_conservative_eligible")

    return reasons


def select_candidates(
    ctx: TrainingSafetyContext,
    decision: TrainingSafetyDecision,
    catalog: ExerciseCatalog,
    policy: TrainingPolicy,
    safety_policy: SafetyPolicy,  # noqa: ARG001  (reserved for future rule hooks)
) -> CandidateResult:
    """Select a deterministic candidate set for an eligible user."""
    gate = decision.gate_status
    conservative = gate is GateStatus.eligible_conservative

    # Gate filter: non-eligible gates produce no candidates and expose no IDs.
    if gate in _BLOCKING_GATES:
        return CandidateResult(
            gate_status=gate,
            decision_fingerprint=decision.fingerprint,
            candidates=[],
            excluded=[],
            policy_version=policy.policy_version,
            catalog_version=catalog.content_version,
            conservative=False,
        )

    index = build_index(catalog)
    ready_ids = {
        ex.exercise_id for ex in catalog.exercises
        if recommendation_ready(ex, index, catalog.published_at).ready
    }

    excluded: List[ExcludedExercise] = []
    survivors: List[Exercise] = []
    for ex in catalog.exercises:
        reasons = _exclude_reasons(ex, ctx, policy, conservative, ready_ids)
        if reasons:
            excluded.append(ExcludedExercise(
                exercise_id=ex.exercise_id, reason_codes=reasons))
        else:
            survivors.append(ex)

    # Stable sort by deterministic priority, then de-duplicate by movement
    # purpose set (keep the lowest sort key = highest priority).
    survivors.sort(key=lambda ex: _sort_key(ex, policy))
    deduped: List[Exercise] = []
    seen_purpose_sets = set()
    for ex in survivors:
        key = frozenset(ex.movement_purposes)
        if key in seen_purpose_sets:
            excluded.append(ExcludedExercise(
                exercise_id=ex.exercise_id,
                reason_codes=[policy.dedup_reason_code]))
            continue
        seen_purpose_sets.add(key)
        deduped.append(ex)

    candidates = [
        Candidate(
            exercise_id=ex.exercise_id,
            training_roles=[r.value for r in ex.training_roles],
            movement_purposes=list(ex.movement_purposes),
            sort_key=_sort_key(ex, policy),
        )
        for ex in deduped
    ]

    return CandidateResult(
        gate_status=gate,
        decision_fingerprint=decision.fingerprint,
        candidates=candidates,
        excluded=excluded,
        policy_version=policy.policy_version,
        catalog_version=catalog.content_version,
        conservative=conservative,
    )
