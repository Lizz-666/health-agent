"""Health profile REST routes (Phase 2 Task 2).

JWT-only: ownership is derived exclusively from ``Depends(get_current_user)``.
No endpoint accepts ``user_id`` as a request parameter, so cross-user read /
write / delete is impossible by construction (spec API And State Contracts).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.health import service
from app.health.schemas import (
    HealthProfileDeleteResponse,
    HealthProfileResultResponse,
    HealthProfileUpdate,
)

router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get("/profile", response_model=HealthProfileResultResponse)
async def get_profile(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the authenticated user's health profile and readiness.

    When no profile exists, returns an explicit not-configured state
    (``configured=false``, ``profile=null``) with readiness derived from an
    empty profile. Defaults are never fabricated.
    """
    return await service.get_profile_result(db, user_id)


@router.put("/profile", response_model=HealthProfileResultResponse)
async def put_profile(
    request: HealthProfileUpdate,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or fully replace the authenticated user's health profile.

    Validation is enforced by the Pydantic request model: unknown fields,
    out-of-range ``weekly_frequency`` (2-5), invalid ``session_duration_minutes``
    (15/30/45/60) and bad enums produce deterministic 422 errors. ``version``
    is incremented on update; timestamps are server-managed.
    """
    return await service.upsert_profile_result(db, user_id, request)


@router.delete("/profile", response_model=HealthProfileDeleteResponse)
async def delete_profile(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete the authenticated user's health profile.

    Idempotent: always reflects the post-delete state (no profile present),
    whether or not a profile existed.
    """
    await service.delete_profile(db, user_id)
    return HealthProfileDeleteResponse(deleted=True)
