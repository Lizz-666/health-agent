"""Server-injected actor identity boundary for posture Tools (spec §10.0).

``ActorContext`` carries the caller's identity and server-side privacy / risk
context. It is constructed by the REST layer from the JWT session (and, in the
future, by an Agent orchestrator from the server runtime) and passed into each
Tool. It is NEVER a model-controllable parameter: an Agent / LLM cannot supply
or override ``user_id`` / ``consent_record`` / ``risk_context`` -- those come
exclusively from authenticated server state.

The ``AsyncSession`` is intentionally NOT part of ``ActorContext``: identity is
kept separate from infrastructure. Tools receive ``db`` as an explicit,
server-injected first parameter and ``actor`` as the second, so neither is ever
selected by the model.

Phase 1 note: the photo privacy gate hard-rejects every photo request (see
``app.core.privacy_gate``), and there is no consent table yet, so
``consent_record`` is always ``None`` today. The field is retained so the
boundary is explicit and stable when a future task introduces consent state.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from fastapi import Depends

from app.core.dependencies import get_current_user


@dataclass(frozen=True)
class ConsentRecord:
    """Minimal immutable server-side consent snapshot for Tool authorization.

    Phase 1 has no persistence provider and therefore never constructs one.
    A future provider must load it from trusted server state; callers and
    models cannot submit it as a Tool business argument.
    """

    record_id: str
    purpose: str
    status: str
    granted_at: datetime
    withdrawn_at: Optional[datetime] = None

    def permits_posture_photo_analysis(self) -> bool:
        return (
            self.purpose == "posture_photo_analysis"
            and self.status == "active"
            and self.withdrawn_at is None
        )


@dataclass(frozen=True)
class ActorContext:
    """The authenticated caller's server-side identity and context.

    ``frozen=True`` prevents Tools from mutating ``user_id`` at runtime; any
    attempted reassignment raises ``dataclasses.FrozenInstanceError``.

    Attributes:
        user_id: Caller user id, sourced exclusively from the JWT (``sub``).
            Never a Tool / model parameter.
        consent_record: Server-side privacy / consent snapshot. Not exposed to
            the model. ``None`` throughout Phase 1 (no consent table; photo
            privacy gate hard-rejects).
        risk_context: Optional server-side risk snapshot. Lazy: read-only Tools
            do not populate it; only Tools that need a precomputed risk view
            (none today) would set it.
    """

    user_id: str
    consent_record: Optional[ConsentRecord] = None
    risk_context: Optional[dict] = None


async def get_actor_context(
    user_id: str = Depends(get_current_user),
) -> ActorContext:
    """FastAPI dependency: build an ``ActorContext`` from the JWT session.

    Depends on ``get_current_user`` so an unauthenticated request surfaces 401
    before any Tool runs. ``consent_record`` / ``risk_context`` are left
    ``None`` (Phase 1); a future task may extend this factory to enrich them
    from server-side privacy / risk state.
    """
    return ActorContext(user_id=user_id)
