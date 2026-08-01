"""Minimal owned Context Resolver (Task 1).

Resolves one turn's ``entry_type`` + optional ``entity_id`` into a minimal,
owned, typed context. Order and guarantees (spec Entry And Context Contracts):

1. A non-empty IANA timezone accepted by ``training.context.validate_iana_timezone``
   is required first; missing/blank/invalid returns ``invalid_timezone`` BEFORE
   any context read, Tool, or persistence side effect. The local date is derived
   only from the server UTC clock plus that timezone; there is no default.
2. ``entity_id`` is validated against the required/forbidden matrix, then against
   ownership using only what existing services already expose as current/owned
   (Decision 2): no new SQL, repository, or history path. Missing and cross-user
   identifiers collapse to the SAME non-enumerating ``agent_entity_not_found``.
3. Only minimal, non-sensitive presence/version codes are assembled by composing
   the read adapters' minimized ``provider_view`` projections. Identity,
   authorization, health payloads, and free text never enter the context.

``ActorContext`` and ``AsyncSession`` are server-injected positional arguments,
never model-controllable.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import read_tools, tool_registry
from app.agent.messages import AgentError, ResultCode
from app.agent.schemas import ContextProviderView, EntryType, ResolvedContext
from app.core.actor_context import ActorContext
from app.core.config import settings
from app.core.exceptions import AppException
from app.nutrition import service as nutrition_service
from app.nutrition.schemas import GateStatus, RecommendationPayload
from app.posture import service as posture_service
from app.posture.knowledge import get_issue_by_id
from app.training import service as training_service
from app.training.context import _active_goals, derive_local_date, validate_iana_timezone

_ENTITY_FORBIDDEN = frozenset({EntryType.general, EntryType.health_profile})
_ENTITY_REQUIRED = frozenset(
    {EntryType.posture_issue, EntryType.training_session, EntryType.training_exercise}
)

_FINGERPRINT_EXCLUDED_FIELDS = {
    # Reviewed catalog labels help the provider explain an owned entity but are
    # not proposal-relevant codes or versions and do not belong in audit input.
    "posture_issue_name_cn",
    "exercise_name_en",
    "exercise_name_zh",
}

async def resolve_context(
    db: AsyncSession,
    actor: ActorContext,
    *,
    entry_type: EntryType,
    entity_id: Optional[str],
    iana_timezone: Optional[str],
    now: Optional[datetime] = None,
) -> ResolvedContext:
    # (1) Timezone gate FIRST - before any read/side effect.
    if not validate_iana_timezone(iana_timezone):
        raise AgentError(ResultCode.INVALID_TIMEZONE)
    tz = iana_timezone.strip()
    now = now or datetime.now(timezone.utc)
    current_local_date = derive_local_date(now, tz)
    if current_local_date is None:  # defensive; validated above
        raise AgentError(ResultCode.INVALID_TIMEZONE)

    # (2) Entity required/forbidden matrix.
    entity_id = entity_id.strip() if isinstance(entity_id, str) else entity_id
    if entry_type in _ENTITY_FORBIDDEN and entity_id:
        raise AgentError(ResultCode.ENTITY_NOT_ALLOWED)
    if entry_type in _ENTITY_REQUIRED and not entity_id:
        raise AgentError(ResultCode.ENTITY_REQUIRED)

    # (3) Ownership resolution + minimal context assembly (Decision 2 / fix #3).
    base = ContextProviderView(
        entry_type=entry_type,
        entity_id=entity_id,
        current_local_date=current_local_date,
    )

    if entry_type is EntryType.general:
        ctx = await _resolve_general(db, actor, base, current_local_date, tz)
    elif entry_type is EntryType.health_profile:
        ctx = await _resolve_health_profile(db, actor, base, current_local_date)
    elif entry_type is EntryType.posture_issue:
        ctx = await _resolve_posture_issue(db, actor, base, entity_id, now)
    elif entry_type is EntryType.training_plan:
        ctx = await _resolve_training_plan(db, actor, base, entity_id)
    elif entry_type is EntryType.training_session:
        ctx = await _resolve_training_session(db, actor, base, entity_id, tz)
    elif entry_type is EntryType.training_exercise:
        ctx = await _resolve_training_exercise(db, actor, base, entity_id, tz)
    elif entry_type is EntryType.nutrition_plan:
        ctx = await _resolve_nutrition_plan(db, actor, base, entity_id, tz)
    else:  # pragma: no cover - closed enum
        raise AgentError(ResultCode.TOOL_NOT_ALLOWED)

    fingerprint = _build_fingerprint_payload(
        ctx, {"iana_timezone": tz, "current_local_date": current_local_date.isoformat()}
    )
    return ResolvedContext(
        entry_type=entry_type,
        entity_id=entity_id,
        iana_timezone=tz,
        current_local_date=current_local_date,
        allowed_tools=tool_registry.allowed_tools_for(entry_type),
        provider_context=ctx,
        fingerprint_payload=fingerprint,
    )


def _build_fingerprint_payload(
    ctx: ContextProviderView, extra: dict
) -> Dict[str, object]:
    """Fingerprint every minimized provider-context field, without free text."""
    payload = ctx.model_dump(
        mode="json",
        exclude_none=True,
        exclude=_FINGERPRINT_EXCLUDED_FIELDS,
    )
    payload.update(extra)
    return payload


# --------------------------------------------------------------------------- #
# Per-entry resolution (composes existing read adapters' minimized projections) #
# --------------------------------------------------------------------------- #


async def _resolve_general(
    db: AsyncSession,
    actor: ActorContext,
    base: ContextProviderView,
    local_date: date,
    tz: str,
) -> ContextProviderView:
    profile = await read_tools.adapt_health_profile_summary(db, actor)
    checkin = await read_tools.adapt_today_checkin(db, actor, local_date)
    active = await read_tools.adapt_get_active_training_plan(db, actor)
    today = await read_tools.adapt_get_today_training(db, actor, tz)
    pv = profile.provider_view
    cv = checkin.provider_view
    resolved = base.model_copy(
        update={
            "profile_configured": pv.configured,
            "health_profile_version": pv.profile_version,
            "readiness_code": pv.readiness_code,
            "health_risk_version": pv.risk_version,
            "restricted": pv.restricted,
            "today_checkin_present": cv.checked_in,
            "today_checkin_risk": cv.risk_summary_code,
            "today_checkin_risk_version": cv.risk_version,
            "active_plan_present": active.provider_view.has_active,
            "today_state": today.provider_view.state,
            "today_decision_gate": today.provider_view.decision_gate,
            "risk_gate_code": today.provider_view.decision_gate,
        }
    )
    if settings.NUTRITION_RUNTIME_ENABLED:
        resolved = await _resolve_nutrition_plan(db, actor, resolved, None, tz)
    return resolved


async def _resolve_health_profile(
    db: AsyncSession,
    actor: ActorContext,
    base: ContextProviderView,
    local_date: date,
) -> ContextProviderView:
    profile = await read_tools.adapt_health_profile_summary(db, actor)
    checkin = await read_tools.adapt_today_checkin(db, actor, local_date)
    trend = await read_tools.adapt_weight_trend_summary(db, actor)
    pv = profile.provider_view
    cv = checkin.provider_view
    tv = trend.provider_view
    return base.model_copy(
        update={
            "profile_configured": pv.configured,
            "health_profile_version": pv.profile_version,
            "readiness_code": pv.readiness_code,
            "health_risk_version": pv.risk_version,
            "restricted": pv.restricted,
            "health_fitness_goal": pv.fitness_goal,
            "health_training_experience": pv.training_experience,
            "health_weekly_frequency": pv.weekly_frequency,
            "health_session_duration_minutes": pv.session_duration_minutes,
            "today_checkin_present": cv.checked_in,
            "today_checkin_risk": cv.risk_summary_code,
            "today_checkin_risk_version": cv.risk_version,
            "weight_trend_sufficient": tv.sufficient,
            "weight_trend_window": tv.window,
            "weight_record_count": tv.record_count,
            "weight_trend_point_count": tv.trend_point_count,
        }
    )


async def _resolve_posture_issue(
    db: AsyncSession,
    actor: ActorContext,
    base: ContextProviderView,
    issue_id: str,
    now: datetime,
) -> ContextProviderView:
    # Public catalog entity: existence is a public fact. Unknown ids share the
    # same non-enumerating result as cross-user ids (Decision 2).
    if get_issue_by_id(issue_id) is None:
        raise AgentError(ResultCode.ENTITY_NOT_FOUND)
    detail = read_tools.adapt_get_posture_issue(issue_id).provider_view
    profile = (await read_tools.adapt_get_posture_profile(db, actor)).provider_view
    assessment = next(
        (entry for entry in profile.entries if entry.issue_id == issue_id), None
    )
    suggestions = await posture_service.get_priority_suggestions(
        db, actor.user_id, now=now
    )
    has_confirmed_goal = await _has_confirmed_goal(
        db, actor, issue_id, now, suggestions=suggestions
    )
    return base.model_copy(
        update={
            "posture_issue_id": issue_id,
            "posture_issue_name_cn": detail.name_cn,
            "posture_severity_levels": list(detail.severity_levels),
            "posture_self_test_count": detail.self_test_count,
            "posture_has_confirmed_goal": has_confirmed_goal,
            "posture_suggestion_id": suggestions.get("suggestion_id"),
            "posture_profile_version": suggestions.get("profile_version"),
            "posture_rule_version": suggestions.get("rule_version"),
            "posture_assessment_severity": (
                assessment.combined_severity if assessment is not None else None
            ),
            "posture_assessment_certainty": (
                assessment.certainty if assessment is not None else None
            ),
            "posture_assessment_source_codes": (
                list(assessment.source_codes) if assessment is not None else []
            ),
            "posture_risk_version": suggestions.get("risk_version"),
        }
    )


async def _has_confirmed_goal(
    db: AsyncSession,
    actor: ActorContext,
    issue_id: str,
    now: datetime,
    *,
    suggestions: Optional[dict] = None,
) -> bool:
    """Whether the user has an active confirmed posture goal for ``issue_id``.

    Reuses the only ownership-scoped active-goal read path: the existing
    ``training.context._active_goals`` reader (which reads ``PostureUserGoal``
    scoped to the caller) combined with ``posture.service.get_priority_suggestions``
    for the suggestions input it requires. No new SQL path is introduced.
    """
    if suggestions is None:
        suggestions = await posture_service.get_priority_suggestions(
            db, actor.user_id, now=now
        )
    goals = await _active_goals(db, actor.user_id, suggestions)
    return any(
        g.issue_id == issue_id
        and g.confirmed_at is not None
        and g.active
        and not g.blocked
        for g in goals
    )


async def _resolve_training_plan(
    db: AsyncSession,
    actor: ActorContext,
    base: ContextProviderView,
    entity_id: Optional[str],
) -> ContextProviderView:
    active = await training_service.get_active(db, actor.user_id)
    draft = await training_service.get_draft(db, actor.user_id)
    owned_ids = set()
    active_plan = active.plan if active.has_active else None
    draft_plan = draft.draft if draft.has_draft else None
    if active_plan is not None:
        owned_ids.add(active_plan.plan_version_id)
    if draft_plan is not None:
        owned_ids.add(draft_plan.plan_version_id)
    # entity_id None means "current"; a supplied id must be a current owned id.
    if entity_id is not None and entity_id not in owned_ids:
        raise AgentError(ResultCode.ENTITY_NOT_FOUND)
    if entity_id is not None:
        selected = (
            active_plan
            if active_plan and active_plan.plan_version_id == entity_id
            else draft_plan
        )
    else:
        selected = active_plan or draft_plan
    return base.model_copy(
        update={
            "active_plan_present": active.has_active,
            "draft_present": draft.has_draft,
            "plan_version_id": selected.plan_version_id if selected else None,
            "plan_status": selected.status if selected else None,
            "plan_decision_gate": selected.decision_gate if selected else None,
            "draft_decision_gate": draft.decision_gate,
            "plan_change_reason": getattr(selected, "change_reason", None),
            "plan_requested_goal": getattr(selected, "requested_goal", None),
            "plan_weekly_frequency": getattr(selected, "weekly_frequency", None),
            "plan_session_duration_minutes": (
                getattr(selected, "session_duration_minutes", None)
            ),
            "plan_session_count": (
                len(getattr(selected, "sessions", [])) if selected else None
            ),
            "plan_policy_version": getattr(selected, "policy_version", None),
            "catalog_version": getattr(selected, "catalog_version", None),
        }
    )


async def _resolve_training_session(
    db: AsyncSession,
    actor: ActorContext,
    base: ContextProviderView,
    session_id: str,
    tz: str,
) -> ContextProviderView:
    # Fix #4: only the CURRENT local-date session from ``get_today`` is accepted;
    # an active-plan session that is not today shares the same non-enumerating
    # ``agent_entity_not_found`` as a foreign/missing id.
    today = await training_service.get_today(db, actor.user_id, tz)
    projected = read_tools._project_today_training(today).provider_view
    if session_id != projected.session_id:
        raise AgentError(ResultCode.ENTITY_NOT_FOUND)
    return base.model_copy(
        update={
            "session_id": session_id,
            "today_state": projected.state,
            "today_decision_gate": projected.decision_gate,
            "risk_gate_code": projected.decision_gate,
            "prescription_ids": list(projected.prescription_ids),
            "prescription_exercise_ids": list(projected.exercise_ids),
            "feedback_outcome_state": projected.feedback_outcome_state,
            "substitution_applied": projected.substitution_applied,
        }
    )


async def _resolve_training_exercise(
    db: AsyncSession,
    actor: ActorContext,
    base: ContextProviderView,
    exercise_id: str,
    tz: str,
) -> ContextProviderView:
    today = await training_service.get_today(db, actor.user_id, tz)
    result = read_tools._project_training_exercise(today, exercise_id)
    exercise = result.provider_view
    session = today.session
    prescription = next(
        p for p in session.prescriptions if p.exercise_id == exercise_id
    )
    catalog = exercise.catalog
    return base.model_copy(
        update={
            "exercise_id": exercise_id,
            "session_id": session.session_id,
            "today_state": today.state,
            "today_decision_gate": today.decision_gate,
            "risk_gate_code": today.decision_gate,
            "exercise_prescription_id": prescription.prescription_id,
            "exercise_sets": exercise.sets,
            "exercise_reps": exercise.reps,
            "exercise_duration_seconds": exercise.duration_seconds,
            "exercise_rest_seconds": exercise.rest_seconds,
            "exercise_name_en": catalog.name_en,
            "exercise_name_zh": catalog.name_zh,
            "exercise_difficulty": catalog.difficulty,
            "exercise_training_roles": list(catalog.training_roles),
            "exercise_stop_condition_codes": list(exercise.stop_condition_codes),
            "catalog_version": training_service.catalog().content_version,
        }
    )


async def _resolve_nutrition_plan(
    db: AsyncSession,
    actor: ActorContext,
    base: ContextProviderView,
    recommendation_id: Optional[str],
    tz: str,
) -> ContextProviderView:
    try:
        state, row = await nutrition_service.resolve_agent_context(
            db, actor.user_id, tz, recommendation_id
        )
    except AppException as exc:
        if exc.code == "nutrition_runtime_disabled":
            raise AgentError(ResultCode.NUTRITION_DISABLED) from exc
        if exc.code == "not_owner_or_missing_recommendation":
            raise AgentError(ResultCode.ENTITY_NOT_FOUND) from exc
        raise
    versions = nutrition_service.versions()
    food_ids: list[str] = []
    if row is not None and state.decision.gate in {
        GateStatus.eligible,
        GateStatus.eligible_conservative,
    }:
        payload = RecommendationPayload.model_validate(row.payload)
        food_ids = sorted(
            {
                item.food_id
                for variant in payload.variants
                for meal in variant.meals
                for item in meal.items
            }
        )
    return base.model_copy(
        update={
            "nutrition_gate": state.decision.gate.value,
            "nutrition_reason_codes": list(state.decision.reason_codes),
            "nutrition_missing_field_codes": list(
                state.decision.missing_field_codes
            ),
            "nutrition_recommendation_id": (
                str(row.recommendation_id) if row is not None else None
            ),
            "nutrition_recommendation_status": row.status if row is not None else None,
            "nutrition_recommendation_version": row.version if row is not None else None,
            "nutrition_validation_codes": (
                list(row.validation_codes) if row is not None else []
            ),
            "nutrition_food_ids": food_ids,
            "nutrition_policy_version": versions.policy_version,
            "catalog_version": versions.catalog_version,
            "nutrition_source_manifest_version": versions.source_manifest_version,
            "nutrition_media_manifest_version": versions.media_manifest_version,
        }
    )


__all__ = ["resolve_context"]
