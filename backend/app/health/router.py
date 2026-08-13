"""Health profile, daily check-in, weight, and activity-grid REST routes
(Phase 2 Task 2 / Task 3 / Task 4).

JWT-only: ownership is derived exclusively from ``Depends(get_current_user)``.
No endpoint accepts ``user_id`` as a request parameter, so cross-user read /
write / delete is impossible by construction (spec API And State Contracts).
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_sensitive_health_consent
from app.db.database import get_db
from app.health import service
from app.health.schemas import (
    ActivityGridResponse,
    CheckInCreate,
    CheckInDeleteResponse,
    CheckInResponse,
    CheckInTodayResultResponse,
    HealthProfileDeleteResponse,
    HealthProfileResultResponse,
    HealthProfileUpdate,
    WeightRecordCreate,
    WeightRecordDeleteResponse,
    WeightRecordResponse,
    WeightRecordUpdate,
    WeightTrendResponse,
)

router = APIRouter(
    prefix="/api/v1/health",
    tags=["health"],
    dependencies=[Depends(require_sensitive_health_consent)],
)


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


# ---------------------------------------------------------------------------
# Weight records, trend, and activity grid (Task 4)
# ---------------------------------------------------------------------------


@router.post("/weight-records", response_model=WeightRecordResponse)
async def create_weight_record(
    request: WeightRecordCreate,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create one manual weight record for the authenticated user.

    ``weight_kg`` is bounded (20.0-300.0 kg); out-of-range or non-numeric
    values produce a deterministic 422. ``source`` is server-set to ``manual``
    and never accepted from the client. Raw weight values are never logged.
    """
    return await service.create_weight_record(db, user_id, request)


@router.get("/weight-records", response_model=list[WeightRecordResponse])
async def list_weight_records(
    start_date: date = Query(None, description="Inclusive range start."),
    end_date: date = Query(None, description="Inclusive range end."),
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the authenticated user's weight records (newest first).

    Optional inclusive ``start_date`` / ``end_date`` bound the range. Results
    are scoped to the caller.
    """
    return await service.list_weight_records(db, user_id, start_date, end_date)


@router.put("/weight-records/{record_id}", response_model=WeightRecordResponse)
async def update_weight_record(
    record_id: UUID,
    request: WeightRecordUpdate,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Full-replace the editable fields of one caller-owned weight record.

    Ownership-scoped: a record belonging to another user (or a missing id)
    surfaces as a deterministic 404; an invalid id format is a 422.
    """
    return await service.update_weight_record(db, user_id, record_id, request)


@router.delete("/weight-records/{record_id}", response_model=WeightRecordDeleteResponse)
async def delete_weight_record(
    record_id: UUID,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete one caller-owned weight record.

    Ownership-scoped: not-owned or missing id surfaces as a deterministic 404.
    """
    await service.delete_weight_record(db, user_id, record_id)
    return WeightRecordDeleteResponse(deleted=True)


@router.get("/trends/weight", response_model=WeightTrendResponse)
async def get_weight_trend(
    start_date: date = Query(None, description="Inclusive range start."),
    end_date: date = Query(None, description="Inclusive range end."),
    window: int = Query(7, ge=2, le=14, description="Moving-average window."),
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return raw weight records plus a deterministic moving trend.

    The trend is a point-based simple moving average over ``window`` records.
    When fewer than ``window`` records exist, ``sufficient`` is false and
    ``trend`` is empty (insufficient data). Phase 2 emits no plan / diet
    adjustments, warnings, or pass/fail judgment from this endpoint.
    """
    return await service.get_weight_trend(db, user_id, start_date, end_date, window)


@router.get("/activity-grid", response_model=ActivityGridResponse)
async def get_activity_grid(
    start_date: date = Query(None, description="Inclusive range start."),
    end_date: date = Query(None, description="Inclusive range end."),
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Project the authenticated user's daily check-ins onto a per-day grid.

    Each day carries a Phase 2 status only: ``checked_in``, ``active_rest``,
    ``safety_adjustment``, or ``none``. Plan-execution statuses are never
    produced. Defaults to the last 28 days when no range is given (cap 366).
    """
    return await service.get_activity_grid(db, user_id, start_date, end_date)
