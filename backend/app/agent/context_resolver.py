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
from app.posture import service as posture_service
from app.posture.knowledge import get_issue_by_id
from app.training import service as training_service
from app.training.context import _active_goals, derive_local_date, validate_iana_timezone

_ENTITY_FORBIDDEN = frozenset({EntryType.general, EntryType.health_profile})
_ENTITY_REQUIRED = frozenset(
    {EntryType.posture_issue, EntryType.training_session, EntryType.training_exercise}
)

# Context fields included in the canonical fingerprint payload: only structured
# codes, version, presence flags, and owned references (never raw text/values).
_FINGERPRINT_FIELDS = (
    "entry_type",
    "entity_id",
    "iana_timezone",
    "current_local_date",
    "profile_configured",
    "readiness_code",
    "restricted",
    "today_checkin_present",
    "today_checkin_risk",
    "risk_gate_code",
    "today_decision_gate",
    "active_plan_present",
    "draft_present",
    "plan_version_id",
    "plan_status",
    "plan_decision_gate",
    "draft_decision_gate",
    "today_state",
    "posture_issue_id",
    "posture_has_confirmed_goal",
    "session_id",
    "exercise_id",
    "prescription_exercise_ids",
    "exercise_stop_condition_codes",
    "health_risk_version",
    "posture_risk_version",
    "catalog_version",
)


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


def _build_fingerprint_payload(ctx: ContextProviderView, extra: dict) -> Dict[str, str]:
    payload: Dict[str, str] = {}
    for key in _FINGERPRINT_FIELDS:
        if key in extra:
            payload[key] = extra[key]
            continue
        value = getattr(ctx, key)
        if value is None or value == []:
            continue
        if isinstance(value, EntryType):
            payload[key] = value.value
        elif isinstance(value, (list, tuple)):
            payload[key] = list(value)
        else:
            payload[key] = value if isinstance(value, (str, int, bool)) else str(value)
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
    return base.model_copy(
        update={
            "profile_configured": pv.configured,
            "readiness_code": pv.readiness_code,
            "restricted": pv.restricted,
            "today_checkin_present": cv.checked_in,
            "today_checkin_risk": cv.risk_summary_code,
            "active_plan_present": active.provider_view.has_active,
            "today_state": today.provider_view.state,
            "today_decision_gate": today.provider_view.decision_gate,
            "risk_gate_code": today.provider_view.decision_gate,
        }
    )


async def _resolve_health_profile(
    db: AsyncSession,
    actor: ActorContext,
    base: ContextProviderView,
    local_date: date,
) -> ContextProviderView:
    profile = await read_tools.adapt_health_profile_summary(db, actor)
    checkin = await read_tools.adapt_today_checkin(db, actor, local_date)
    pv = profile.provider_view
    cv = checkin.provider_view
    return base.model_copy(
        update={
            "profile_configured": pv.configured,
            "readiness_code": pv.readiness_code,
            "restricted": pv.restricted,
            "today_checkin_present": cv.checked_in,
            "today_checkin_risk": cv.risk_summary_code,
        }
    )


def _health_risk_version(*_args, **_kwargs) -> Optional[str]:  # pragma: no cover
    # Retained as a documented no-op hook for a later batch that surfaces the
    # deterministic readiness ``risk_version`` without a new data-access path.
    return None


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
    has_confirmed_goal = await _has_confirmed_goal(db, actor, issue_id, now)
    return base.model_copy(
        update={
            "posture_issue_id": issue_id,
            "posture_issue_name_cn": detail.name_cn,
            "posture_severity_levels": list(detail.severity_levels),
            "posture_self_test_count": detail.self_test_count,
            "posture_has_confirmed_goal": has_confirmed_goal,
        }
    )


async def _has_confirmed_goal(
    db: AsyncSession, actor: ActorContext, issue_id: str, now: datetime
) -> bool:
    """Whether the user has an active confirmed posture goal for ``issue_id``.

    Reuses the only ownership-scoped active-goal read path: the existing
    ``training.context._active_goals`` reader (which reads ``PostureUserGoal``
    scoped to the caller) combined with ``posture.service.get_priority_suggestions``
    for the suggestions input it requires. No new SQL path is introduced.
    """
    suggestions = await posture_service.get_priority_suggestions(
        db, actor.user_id, now=now
    )
    goals = await _active_goals(db, actor.user_id, suggestions)
    return any(g.issue_id == issue_id and g.confirmed_at is not None for g in goals)


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
    return base.model_copy(
        update={
            "active_plan_present": active.has_active,
            "draft_present": draft.has_draft,
            "plan_version_id": (
                active_plan.plan_version_id if active_plan is not None else None
            ),
            "plan_status": active_plan.status if active_plan is not None else None,
            "plan_decision_gate": (
                active_plan.decision_gate if active_plan is not None else None
            ),
            "draft_decision_gate": draft.decision_gate,
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
    today_session_id = await _today_session_id(db, actor, tz)
    if session_id != today_session_id:
        raise AgentError(ResultCode.ENTITY_NOT_FOUND)
    today = await read_tools.adapt_get_today_training(db, actor, tz)
    return base.model_copy(
        update={
            "session_id": session_id,
            "today_state": today.provider_view.state,
            "today_decision_gate": today.provider_view.decision_gate,
            "risk_gate_code": today.provider_view.decision_gate,
            "prescription_exercise_ids": list(today.display_view.exercise_ids),
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
    session = today.session
    prescribed = (
        session is not None
        and any(p.exercise_id == exercise_id for p in session.prescriptions)
    )
    if not prescribed:
        raise AgentError(ResultCode.ENTITY_NOT_FOUND)
    # Stop-condition codes are read only after ownership is confirmed, reusing
    # the catalog index (same source as ``training.service``).
    stop_codes: list[str] = []
    catalog_exercise = training_service._index().get(exercise_id)
    if catalog_exercise is not None:
        stop_codes = [sc.code for sc in catalog_exercise.stop_conditions]
    return base.model_copy(
        update={
            "exercise_id": exercise_id,
            "session_id": session.session_id,
            "today_state": today.state,
            "today_decision_gate": today.decision_gate,
            "risk_gate_code": today.decision_gate,
            "exercise_stop_condition_codes": stop_codes,
        }
    )


async def _today_session_id(
    db: AsyncSession, actor: ActorContext, tz: str
) -> Optional[str]:
    """The current local-date session id exposed by ``get_today`` (today only)."""
    today = await training_service.get_today(db, actor.user_id, tz)
    return today.session.session_id if today.session is not None else None


async def _owned_session_ids(db: AsyncSession, actor: ActorContext, tz: str) -> set:
    """Current owned session ids: TODAY's session only (fix #4)."""
    owned = set()
    today = await training_service.get_today(db, actor.user_id, tz)
    if today.session is not None:
        owned.add(today.session.session_id)
    return owned


__all__ = ["resolve_context"]
