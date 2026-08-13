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

from app.posture.knowledge import get_issue_by_id
from app.training.knowledge import build_index, recommendation_ready
from app.training.policy import TrainingPolicy
from app.training.safety import SafetyPolicy, classify_safety, compose_fingerprint
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


def _context_is_current(
    ctx: TrainingSafetyContext,
    decision: TrainingSafetyDecision,
    catalog: ExerciseCatalog,
    policy: TrainingPolicy,
    safety_policy: SafetyPolicy,
) -> bool:
    """Bind selection to one complete, current request and version set."""
    request = ctx.request
    request_goal = (
        request.fitness_goal.value
        if hasattr(request.fitness_goal, "value") else request.fitness_goal
    )
    request_equipment = _requested_equipment(ctx)
    available_equipment = set()
    if ctx.health.equipment_bodyweight:
        available_equipment.add("bodyweight")
    if ctx.health.equipment_resistance_band:
        available_equipment.add("resistance_band")
    if any(value is None for value in (
            request_goal, request.weekly_frequency,
            request.session_duration_minutes)):
        return False
    if not request_equipment or not request_equipment.issubset(available_equipment):
        return False
    if request_goal != ctx.health.fitness_goal:
        return False
    if request.weekly_frequency != ctx.health.weekly_frequency:
        return False
    if request.session_duration_minutes != ctx.health.session_duration_minutes:
        return False
    if decision != classify_safety(ctx, safety_policy):
        return False
    if decision.training_policy_version != ctx.versions.policy_version:
        return False
    if safety_policy.policy_version != ctx.versions.policy_version:
        return False
    if policy.policy_version != ctx.versions.policy_version:
        return False
    if catalog.content_version != ctx.versions.catalog_version:
        return False
    if catalog.source_manifest_version != ctx.versions.source_manifest_version:
        return False
    if policy.policy_version not in catalog.policy_compatibility:
        return False
    return True


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
    if hasattr(goal, "value"):
        goal = goal.value
    ex_goals = {g.value for g in ex.goals}
    if goal and goal not in ex_goals:
        reasons.append("goal_not_matched")

    active_goal_issues = set()
    for goal in ctx.posture.goals:
        if not goal.active or goal.blocked:
            continue
        issue = get_issue_by_id(goal.issue_id)
        active_goal_issues.add(issue["category"] if issue else goal.issue_id)
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
    safety_policy: SafetyPolicy,
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

    if not _context_is_current(
            ctx, decision, catalog, policy, safety_policy):
        return CandidateResult(
            gate_status=GateStatus.clarification_required,
            decision_fingerprint=compose_fingerprint(ctx),
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

    # Stable sort by deterministic priority, then de-duplicate any overlapping
    # movement purpose (keep the lowest sort key = highest priority).
    survivors.sort(key=lambda ex: _sort_key(ex, policy))
    deduped: List[Exercise] = []
    seen_purposes = set()
    for ex in survivors:
        purposes = set(ex.movement_purposes)
        if purposes & seen_purposes:
            excluded.append(ExcludedExercise(
                exercise_id=ex.exercise_id,
                reason_codes=[policy.dedup_reason_code]))
            continue
        seen_purposes.update(purposes)
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
