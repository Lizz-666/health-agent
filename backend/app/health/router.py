"""Health profile and daily check-in REST routes (Phase 2 Task 2 / Task 3).

JWT-only: ownership is derived exclusively from ``Depends(get_current_user)``.
No endpoint accepts ``user_id`` as a request parameter, so cross-user read /
write / delete is impossible by construction (spec API And State Contracts).
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.health import service
from app.health.schemas import (
    CheckInCreate,
    CheckInDeleteResponse,
    CheckInResponse,
    CheckInTodayResultResponse,
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


# ---------------------------------------------------------------------------
# Daily check-in (Task 3)
# ---------------------------------------------------------------------------


@router.get("/checkins/today", response_model=CheckInTodayResultResponse)
async def get_checkin_today(
    local_date: date = Query(
        None,
        description="User-local date. Defaults to the server's current date.",
    ),
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the authenticated user's check-in for the given local date.

    When no check-in exists, returns an explicit not-checked-in state
    (``checked_in=false``, ``checkin=null``). No defaults are fabricated.
    """
    if local_date is None:
        local_date = date.today()
    return await service.get_today(db, user_id, local_date)


@router.put("/checkins/today", response_model=CheckInResponse)
async def put_checkin_today(
    request: CheckInCreate,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or fully replace the authenticated user's check-in for
    ``request.local_date``.

    Validation is enforced by the Pydantic request model (unknown fields, bad
    enums) and the service layer: ``abnormal_pain=true`` requires a complete
    ``pain_followup`` (else a deterministic ``pain_followup_required`` error).
    The deterministic ``risk_summary`` is computed from the structured
    follow-up signals plus the profile ``restricted`` qualifier, then stored.
    At most one check-in per user per local_date is kept.
    """
    return await service.upsert_today(db, user_id, request)


@router.get("/checkins", response_model=list[CheckInResponse])
async def list_checkins(
    start_date: date = Query(None, description="Inclusive range start."),
    end_date: date = Query(None, description="Inclusive range end."),
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the authenticated user's check-in history (newest first).

    Optional inclusive ``start_date`` / ``end_date`` bound the range. Results
    are scoped to the caller; another user's check-ins are never returned.
    """
    return await service.list_checkins(db, user_id, start_date, end_date)


@router.delete("/checkins/{checkin_id}", response_model=CheckInDeleteResponse)
async def delete_checkin(
    checkin_id: UUID,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete the authenticated user's check-in by id.

    Ownership-scoped: a check-in belonging to another user (or a missing id)
    surfaces as a deterministic 404, leaking no cross-user existence. An
    invalid id format is rejected by FastAPI as a deterministic 422.
    """
    await service.delete_checkin(db, user_id, checkin_id)
    return CheckInDeleteResponse(deleted=True)
