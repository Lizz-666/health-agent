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
3. Only minimal, non-sensitive presence/version codes are assembled. Identity,
   authorization, health payloads, and free text never enter the context.

``ActorContext`` and ``AsyncSession`` are server-injected positional arguments,
never model-controllable.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import tool_registry
from app.agent.messages import AgentError, ResultCode
from app.agent.schemas import ContextProviderView, EntryType, ResolvedContext
from app.core.actor_context import ActorContext
from app.health import service as health_service
from app.posture.knowledge import get_issue_by_id
from app.training import service as training_service
from app.training.context import derive_local_date, validate_iana_timezone

_ENTITY_FORBIDDEN = frozenset({EntryType.general, EntryType.health_profile})
_ENTITY_REQUIRED = frozenset(
    {EntryType.posture_issue, EntryType.training_session, EntryType.training_exercise}
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

    # (3) Ownership resolution + minimal context assembly (Decision 2).
    ctx = ContextProviderView(
        entry_type=entry_type,
        entity_id=entity_id,
        current_local_date=current_local_date,
    )
    fingerprint: Dict[str, object] = {
        "entry_type": entry_type.value,
        "entity_id": entity_id,
        "iana_timezone": tz,
        "current_local_date": current_local_date.isoformat(),
    }

    if entry_type is EntryType.general:
        pass  # no owned entity; bounded reads happen only via explicit Tool calls
    elif entry_type is EntryType.health_profile:
        ctx = ctx.model_copy(
            update=await _resolve_health_profile(db, actor, current_local_date)
        )
    elif entry_type is EntryType.posture_issue:
        ctx = ctx.model_copy(update=_resolve_posture_issue(entity_id))
    elif entry_type is EntryType.training_plan:
        ctx = ctx.model_copy(update=await _resolve_training_plan(db, actor, entity_id))
    elif entry_type is EntryType.training_session:
        ctx = ctx.model_copy(
            update=await _resolve_training_session(db, actor, entity_id, tz)
        )
    elif entry_type is EntryType.training_exercise:
        ctx = ctx.model_copy(
            update=await _resolve_training_exercise(db, actor, entity_id, tz)
        )

    for key in (
        "profile_configured",
        "today_checkin_present",
        "active_plan_present",
        "draft_present",
        "today_state",
        "posture_issue_id",
        "session_id",
        "exercise_id",
    ):
        value = getattr(ctx, key)
        if value is not None:
            fingerprint[key] = value

    return ResolvedContext(
        entry_type=entry_type,
        entity_id=entity_id,
        iana_timezone=tz,
        current_local_date=current_local_date,
        allowed_tools=tool_registry.allowed_tools_for(entry_type),
        provider_context=ctx,
        fingerprint_payload=fingerprint,
    )


async def _resolve_health_profile(
    db: AsyncSession, actor: ActorContext, local_date: date
) -> dict:
    profile = await health_service.get_profile_result(db, actor.user_id)
    today = await health_service.get_today(db, actor.user_id, local_date)
    return {
        "profile_configured": profile.configured,
        "today_checkin_present": today.checked_in,
    }


def _resolve_posture_issue(issue_id: str) -> dict:
    # Public catalog entity: existence is a public fact. Unknown ids share the
    # same non-enumerating result as cross-user ids (Decision 2).
    if get_issue_by_id(issue_id) is None:
        raise AgentError(ResultCode.ENTITY_NOT_FOUND)
    return {"posture_issue_id": issue_id}


async def _resolve_training_plan(
    db: AsyncSession, actor: ActorContext, entity_id: Optional[str]
) -> dict:
    active = await training_service.get_active(db, actor.user_id)
    draft = await training_service.get_draft(db, actor.user_id)
    owned_ids = set()
    if active.has_active and active.plan is not None:
        owned_ids.add(active.plan.plan_version_id)
    if draft.has_draft and draft.draft is not None:
        owned_ids.add(draft.draft.plan_version_id)
    # entity_id None means "current"; a supplied id must be a current owned id.
    if entity_id is not None and entity_id not in owned_ids:
        raise AgentError(ResultCode.ENTITY_NOT_FOUND)
    return {
        "active_plan_present": active.has_active,
        "draft_present": draft.has_draft,
    }


async def _resolve_training_session(
    db: AsyncSession, actor: ActorContext, session_id: str, tz: str
) -> dict:
    owned = await _owned_session_ids(db, actor, tz)
    if session_id not in owned:
        raise AgentError(ResultCode.ENTITY_NOT_FOUND)
    return {"session_id": session_id}


async def _resolve_training_exercise(
    db: AsyncSession, actor: ActorContext, exercise_id: str, tz: str
) -> dict:
    today = await training_service.get_today(db, actor.user_id, tz)
    session = today.session
    prescribed = (
        session is not None
        and any(p.exercise_id == exercise_id for p in session.prescriptions)
    )
    if not prescribed:
        raise AgentError(ResultCode.ENTITY_NOT_FOUND)
    return {
        "exercise_id": exercise_id,
        "session_id": session.session_id,
        "today_state": today.state,
    }


async def _owned_session_ids(db: AsyncSession, actor: ActorContext, tz: str) -> set:
    """Current owned session ids: today's session plus the active plan's sessions.

    Both come from existing services; no history query is introduced.
    """
    owned = set()
    today = await training_service.get_today(db, actor.user_id, tz)
    if today.session is not None:
        owned.add(today.session.session_id)
    active = await training_service.get_active(db, actor.user_id)
    if active.has_active and active.plan is not None:
        owned.update(s.session_id for s in active.plan.sessions)
    return owned


__all__ = ["resolve_context"]
