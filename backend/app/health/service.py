"""Health profile application service (Phase 2 Task 2 / Task 3 / Task 4).

Owns the GET / PUT / DELETE behaviour for the authenticated user's health
profile, daily check-ins, manual weight records, weight trend, and activity
grid. Ownership comes ONLY from the JWT-derived ``user_id`` (a string); the
service converts it to ``UUID`` for DB queries. No method accepts a
client-supplied ``user_id``, so cross-user access is impossible by
construction (spec API And State Contracts, Safety).

Safety / privacy:
- Readiness and check-in ``risk_summary`` are produced deterministically by
  ``app.health.risk`` only; free-text notes never affect the tier.
- The service never logs raw sensitive fields (allergies, pain notes, diet
  exclusions, follow-up payloads, body-weight values). Unhandled errors are
  reduced to a structured 503 by the global handler in ``app.main``.
- Missing optional fields stay ``None``; nothing is fabricated.
- ``abnormal_pain=true`` requires a complete ``pain_followup``; otherwise the
  service raises a deterministic ``pain_followup_required`` error.
- Weight trend never emits plan/diet adjustments, warnings, or pass/fail
  judgment; the activity grid projects Phase 2 check-in statuses only.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFound
from app.health.models import DailyCheckIn, HealthProfile, WeightRecord
from app.health.risk import classify_checkin, classify_readiness, restricted_reason
from app.health.schemas import (
    ActivityGridCell,
    ActivityGridResponse,
    CheckInCreate,
    CheckInResponse,
    HealthProfileData,
    HealthProfileResponse,
    HealthProfileResultResponse,
    HealthProfileUpdate,
    HealthReadinessResponse,
    WeightRecordCreate,
    WeightRecordResponse,
    WeightRecordUpdate,
    WeightTrendResponse,
)
from app.health.trends import compute_weight_trend

# Phase 2 has only manual weight entry.
WEIGHT_SOURCE_MANUAL = "manual"

# Activity grid default window / cap (inclusive days).
ACTIVITY_GRID_DEFAULT_DAYS = 28
ACTIVITY_GRID_MAX_DAYS = 366


def _to_uuid(user_id: str) -> UUID:
    """Convert the JWT ``sub`` (user id string) to ``UUID``.

    Mirrors ``app.posture.service``: the token carries the user id as a
    string; DB columns are ``UUID``.
    """
    return UUID(user_id)


def _response_from_row(row: HealthProfile) -> HealthProfileResponse:
    """Build the API response model from the ORM row.

    Stored values (strings / ints / JSON dicts) are coerced by Pydantic back
    into the typed enums / nested models. Missing fields are passed through as
    ``None``; they are never defaulted into user-provided-looking values.
    """
    return HealthProfileResponse(
        id=row.id,
        fitness_goal=row.fitness_goal,
        training_experience=row.training_experience,
        weekly_frequency=row.weekly_frequency,
        session_duration_minutes=row.session_duration_minutes,
        equipment=row.equipment,
        pain_injury_limitations=row.pain_injury_limitations,
        risk_screen=row.risk_screen,
        allergies=row.allergies,
        diet_exclusions=row.diet_exclusions,
        version=row.version,
        updated_at=row.updated_at,
        created_at=row.created_at,
    )


def _readiness_for(profile: Optional[HealthProfileData]) -> HealthReadinessResponse:
    """Compute the deterministic readiness response.

    When no profile exists yet, classification runs on an empty
    ``HealthProfileData`` and yields ``missing_required_data`` with every
    required field listed: an explicit not-ready state, never a fabricated
    'normal'.
    """
    data = profile if profile is not None else HealthProfileData()
    return HealthReadinessResponse.from_result(classify_readiness(data))


async def _fetch(db: AsyncSession, user_id: str) -> Optional[HealthProfile]:
    user_uuid = _to_uuid(user_id)
    result = await db.execute(
        select(HealthProfile).where(HealthProfile.user_id == user_uuid)
    )
    return result.scalar_one_or_none()


async def get_profile_result(
    db: AsyncSession, user_id: str
) -> HealthProfileResultResponse:
    """Return the caller's profile and deterministic readiness.

    If no profile exists, returns an explicit not-configured state
    (``configured=False``, ``profile=None``) with readiness computed from an
    empty profile. No defaults are fabricated.
    """
    row = await _fetch(db, user_id)
    if row is None:
        return HealthProfileResultResponse(
            configured=False,
            profile=None,
            readiness=_readiness_for(None),
        )
    profile = _response_from_row(row)
    return HealthProfileResultResponse(
        configured=True,
        profile=profile,
        readiness=_readiness_for(profile),
    )


async def upsert_profile_result(
    db: AsyncSession, user_id: str, data: HealthProfileUpdate
) -> HealthProfileResultResponse:
    """Full-replacement upsert of the caller's profile.

    The request body IS the profile: omitted optional fields are stored as
    missing (``None``), never converted into user-provided defaults. On update
    the existing row's editable fields are replaced and ``version`` is
    incremented deterministically; on first save ``version`` starts at 1.
    """
    user_uuid = _to_uuid(user_id)
    row = await _fetch(db, user_id)

    # JSON-native dict (enums -> values, nested models -> dicts); suitable for
    # direct assignment to JSONB / nullable columns.
    values = data.model_dump(mode="json")

    if row is None:
        row = HealthProfile(user_id=user_uuid, **values)
        db.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
        row.version = row.version + 1

    await db.commit()
    await db.refresh(row)

    profile = _response_from_row(row)
    return HealthProfileResultResponse(
        configured=True,
        profile=profile,
        readiness=_readiness_for(profile),
    )


async def delete_profile(db: AsyncSession, user_id: str) -> None:
    """Remove the caller's profile if present. Idempotent: a missing profile is
    a no-op (the post-delete state, no profile present, is what matters)."""
    row = await _fetch(db, user_id)
    if row is not None:
        await db.delete(row)
        await db.commit()


# ---------------------------------------------------------------------------
# Daily check-in (Task 3)
# ---------------------------------------------------------------------------

# Deterministic error code raised when abnormal_pain is true but no complete
# pain_followup object was supplied (spec API And State Contracts, Safety).
PAIN_FOLLOWUP_REQUIRED_CODE = "pain_followup_required"


async def _fetch_profile_data(db: AsyncSession, user_id: str) -> Optional[HealthProfileData]:
    """Return the caller's profile as typed data, or None when absent.

    Used only to surface the profile ``restricted`` qualifier into the check-in
    risk_summary. A missing profile yields no restricted qualifier (it does not
    block the check-in).
    """
    row = await _fetch(db, user_id)
    if row is None:
        return None
    return _response_from_row(row)


def _checkin_response(row: DailyCheckIn) -> CheckInResponse:
    """Build the API response model from the ORM row.

    Stored values (strings / JSON dict) are coerced by Pydantic back into the
    typed enums / nested ``PainFollowup`` model. ``risk_summary`` /
    ``risk_version`` are returned exactly as stored, so the stored and returned
    values are always consistent.
    """
    return CheckInResponse(
        id=row.id,
        local_date=row.local_date,
        sleep_quality=row.sleep_quality,
        energy=row.energy,
        muscle_soreness=row.muscle_soreness,
        available_time=row.available_time,
        daily_status=row.daily_status,
        abnormal_pain=row.abnormal_pain,
        pain_followup=row.pain_followup,
        risk_summary=row.risk_summary,
        risk_version=row.risk_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _fetch_checkin(
    db: AsyncSession, user_id: str, local_date: date
) -> Optional[DailyCheckIn]:
    user_uuid = _to_uuid(user_id)
    result = await db.execute(
        select(DailyCheckIn).where(
            DailyCheckIn.user_id == user_uuid,
            DailyCheckIn.local_date == local_date,
        )
    )
    return result.scalar_one_or_none()


async def get_today(
    db: AsyncSession, user_id: str, local_date: date
):
    """Return the caller's check-in for ``local_date`` (envelope).

    When no check-in exists, returns an explicit not-checked-in state
    (``checked_in=False``, ``checkin=None``). No defaults are fabricated.
    """
    from app.health.schemas import CheckInTodayResultResponse

    row = await _fetch_checkin(db, user_id, local_date)
    if row is None:
        return CheckInTodayResultResponse(checked_in=False, checkin=None)
    return CheckInTodayResultResponse(checked_in=True, checkin=_checkin_response(row))


async def upsert_today_core(
    db: AsyncSession, user_id: str, data: CheckInCreate
) -> CheckInResponse:
    """Transaction-neutral core of ``upsert_today``.

    Performs the deterministic safety gate, classification, and the insert/
    in-place replace, then ``flush`` + ``refresh`` so the caller receives the
    fully-populated row. It does NOT commit: the existing committing API
    wrapper and the Agent confirmation path both call this core so chat and
    button behaviour share one operation (ADR-0003; spec Write Confirmation
    Semantics). No business rule is duplicated.
    """
    if data.abnormal_pain and data.pain_followup is None:
        raise AppException(
            status_code=422,
            detail="abnormal_pain 为真时必须提供完整的 pain_followup 对象",
            code=PAIN_FOLLOWUP_REQUIRED_CODE,
        )

    # Free-text pain_note never influences classification; only structured
    # fields do (handled in app.health.risk). When abnormal_pain is false the
    # follow-up is meaningless and is not stored.
    followup = data.pain_followup.model_dump(mode="json") if data.abnormal_pain else None

    # Surface the profile restricted qualifier into the check-in risk_summary.
    # A missing profile contributes no restricted qualifier.
    profile = await _fetch_profile_data(db, user_id)
    restricted_qualifier = restricted_reason(profile) if profile is not None else None

    risk = classify_checkin(data, restricted_qualifier=restricted_qualifier)

    user_uuid = _to_uuid(user_id)
    row = await _fetch_checkin(db, user_id, data.local_date)

    if row is None:
        row = DailyCheckIn(
            user_id=user_uuid,
            local_date=data.local_date,
            sleep_quality=data.sleep_quality.value,
            energy=data.energy.value,
            muscle_soreness=data.muscle_soreness.value,
            available_time=data.available_time.value,
            daily_status=data.daily_status.value,
            abnormal_pain=data.abnormal_pain,
            pain_followup=followup,
            risk_summary=risk.risk_summary,
            risk_version=risk.risk_version,
        )
        db.add(row)
    else:
        row.sleep_quality = data.sleep_quality.value
        row.energy = data.energy.value
        row.muscle_soreness = data.muscle_soreness.value
        row.available_time = data.available_time.value
        row.daily_status = data.daily_status.value
        row.abnormal_pain = data.abnormal_pain
        row.pain_followup = followup
        row.risk_summary = risk.risk_summary
        row.risk_version = risk.risk_version

    await db.flush()
    await db.refresh(row)
    return _checkin_response(row)


async def upsert_today(
    db: AsyncSession, user_id: str, data: CheckInCreate
) -> CheckInResponse:
    """Create or fully replace the caller's check-in for ``data.local_date``.

    Thin committing wrapper around ``upsert_today_core``; existing button/API
    behaviour and signature are unchanged.
    """
    response = await upsert_today_core(db, user_id, data)
    await db.commit()
    return response


async def list_checkins(
    db: AsyncSession,
    user_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[CheckInResponse]:
    """Return the caller's check-in history, newest local_date first.

    Optional inclusive ``start_date`` / ``end_date`` bound the range. Results
    are scoped to the caller; another user's check-ins are never returned.
    """
    user_uuid = _to_uuid(user_id)
    stmt = select(DailyCheckIn).where(DailyCheckIn.user_id == user_uuid)
    if start_date is not None:
        stmt = stmt.where(DailyCheckIn.local_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(DailyCheckIn.local_date <= end_date)
    stmt = stmt.order_by(DailyCheckIn.local_date.desc(), DailyCheckIn.id.desc())
    result = await db.execute(stmt)
    return [_checkin_response(row) for row in result.scalars().all()]


async def delete_checkin(db: AsyncSession, user_id: str, checkin_id: UUID) -> None:
    """Delete the caller's check-in by id.

    Ownership-scoped: a check-in belonging to another user is not visible
    (looked up by id AND user_id) and surfaces as a deterministic 404 so no
    existence is leaked across users. A missing id is also a 404. ``checkin_id``
    is validated as a UUID by FastAPI before reaching the service.
    """
    user_uuid = _to_uuid(user_id)
    result = await db.execute(
        select(DailyCheckIn).where(
            DailyCheckIn.id == checkin_id,
            DailyCheckIn.user_id == user_uuid,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise NotFound("签到记录不存在")
    await db.delete(row)
    await db.commit()


# ---------------------------------------------------------------------------
# Weight records, trend, and activity grid (Task 4)
# ---------------------------------------------------------------------------


def _to_utc(dt: datetime) -> datetime:
    """Canonicalize a ``recorded_at`` to a timezone-aware UTC datetime.

    A naive datetime is assumed to be UTC. Storing a single canonical
    representation keeps range filters deterministic across SQLite and
    PostgreSQL. The raw value is never logged.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _weight_response(row: WeightRecord) -> WeightRecordResponse:
    """Build the API response model from the ORM row.

    ``weight_kg`` (Numeric(6,2)) is coerced to float for JSON; ``source`` is
    always ``manual``. Raw values are returned to the owner only.
    """
    return WeightRecordResponse(
        id=row.id,
        recorded_at=row.recorded_at,
        weight_kg=float(row.weight_kg),
        source=row.source,
        note=row.note,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _recorded_at_bounds(
    start_date: Optional[date], end_date: Optional[date]
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Build inclusive UTC datetime bounds from optional date params."""
    start_dt = (
        datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        if start_date is not None
        else None
    )
    end_dt = (
        datetime.combine(end_date, time.max, tzinfo=timezone.utc)
        if end_date is not None
        else None
    )
    return start_dt, end_dt


async def create_weight_record_core(
    db: AsyncSession, user_id: str, data: WeightRecordCreate
) -> WeightRecordResponse:
    """Transaction-neutral core of ``create_weight_record``.

    Inserts the row and ``flush`` + ``refresh`` without committing. Both the
    committing API wrapper and the Agent confirmation path call this core
    (ADR-0003). ``source`` is forced to ``manual`` server-side; raw weight
    values are never logged.
    """
    user_uuid = _to_uuid(user_id)
    row = WeightRecord(
        user_id=user_uuid,
        recorded_at=_to_utc(data.recorded_at),
        weight_kg=data.weight_kg,
        source=WEIGHT_SOURCE_MANUAL,
        note=data.note,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return _weight_response(row)


async def create_weight_record(
    db: AsyncSession, user_id: str, data: WeightRecordCreate
) -> WeightRecordResponse:
    """Create one manual weight record for the caller.

    Thin committing wrapper around ``create_weight_record_core``; existing
    button/API behaviour and signature are unchanged.
    """
    response = await create_weight_record_core(db, user_id, data)
    await db.commit()
    return response


async def list_weight_records(
    db: AsyncSession,
    user_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[WeightRecordResponse]:
    """Return the caller's weight records, newest recorded_at first.

    Optional inclusive ``start_date`` / ``end_date`` bound the range on
    ``recorded_at``. Results are scoped to the caller.
    """
    user_uuid = _to_uuid(user_id)
    start_dt, end_dt = _recorded_at_bounds(start_date, end_date)
    stmt = select(WeightRecord).where(WeightRecord.user_id == user_uuid)
    if start_dt is not None:
        stmt = stmt.where(WeightRecord.recorded_at >= start_dt)
    if end_dt is not None:
        stmt = stmt.where(WeightRecord.recorded_at <= end_dt)
    stmt = stmt.order_by(WeightRecord.recorded_at.desc(), WeightRecord.id.desc())
    result = await db.execute(stmt)
    return [_weight_response(row) for row in result.scalars().all()]


async def _fetch_weight(
    db: AsyncSession, user_id: str, record_id: UUID
) -> Optional[WeightRecord]:
    user_uuid = _to_uuid(user_id)
    result = await db.execute(
        select(WeightRecord).where(
            WeightRecord.id == record_id,
            WeightRecord.user_id == user_uuid,
        )
    )
    return result.scalar_one_or_none()


async def update_weight_record(
    db: AsyncSession, user_id: str, record_id: UUID, data: WeightRecordUpdate
) -> WeightRecordResponse:
    """Full-replace the editable fields of one caller-owned record.

    Ownership-scoped: a record belonging to another user (or a missing id)
    surfaces as a deterministic 404.
    """
    row = await _fetch_weight(db, user_id, record_id)
    if row is None:
        raise NotFound("体重记录不存在")
    row.recorded_at = _to_utc(data.recorded_at)
    row.weight_kg = data.weight_kg
    row.note = data.note
    await db.commit()
    await db.refresh(row)
    return _weight_response(row)


async def delete_weight_record(
    db: AsyncSession, user_id: str, record_id: UUID
) -> None:
    """Delete one caller-owned weight record. Ownership-scoped: not-owned or
    missing id surfaces as a deterministic 404."""
    row = await _fetch_weight(db, user_id, record_id)
    if row is None:
        raise NotFound("体重记录不存在")
    await db.delete(row)
    await db.commit()


async def get_weight_trend(
    db: AsyncSession,
    user_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    window: int = 7,
) -> WeightTrendResponse:
    """Return raw records plus the deterministic moving trend.

    Records are range-filtered and ordered ascending by ``recorded_at``. The
    trend is a point-based simple moving average over ``window`` records;
    ``sufficient`` is false and ``trend`` is empty when fewer than ``window``
    records exist. No recommendation / adjustment / warning text is produced.
    """
    user_uuid = _to_uuid(user_id)
    start_dt, end_dt = _recorded_at_bounds(start_date, end_date)
    stmt = select(WeightRecord).where(WeightRecord.user_id == user_uuid)
    if start_dt is not None:
        stmt = stmt.where(WeightRecord.recorded_at >= start_dt)
    if end_dt is not None:
        stmt = stmt.where(WeightRecord.recorded_at <= end_dt)
    stmt = stmt.order_by(WeightRecord.recorded_at.asc(), WeightRecord.id.asc())
    result = await db.execute(stmt)
    records = [_weight_response(row) for row in result.scalars().all()]
    return compute_weight_trend(records, window)


def _resolve_grid_range(
    start_date: Optional[date], end_date: Optional[date]
) -> tuple[date, date]:
    """Resolve the activity-grid date range with defaults + cap.

    When omitted, defaults to the last ``ACTIVITY_GRID_DEFAULT_DAYS`` days
    ending today. ``start`` must be on/before ``end`` and the inclusive span
    must not exceed ``ACTIVITY_GRID_MAX_DAYS``.
    """
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=ACTIVITY_GRID_DEFAULT_DAYS - 1)
    if start_date > end_date:
        raise AppException(
            status_code=422,
            detail="start_date 不能晚于 end_date",
            code="invalid_date_range",
        )
    if (end_date - start_date).days + 1 > ACTIVITY_GRID_MAX_DAYS:
        raise AppException(
            status_code=422,
            detail=f"日期范围不得超过 {ACTIVITY_GRID_MAX_DAYS} 天",
            code="invalid_date_range",
        )
    return start_date, end_date


async def get_activity_grid(
    db: AsyncSession,
    user_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> ActivityGridResponse:
    """Project the user's daily check-ins onto a per-day grid.

    Each day in the range gets a Phase 2 status only: ``checked_in``,
    ``active_rest``, or ``safety_adjustment`` when a check-in exists (its
    ``daily_status``), else ``none``. Plan-execution statuses
    (``partial_execution`` / ``main_plan_completed``) are never produced.
    ``active_rest`` and ``safety_adjustment`` are valid, non-failure states.
    """
    start, end = _resolve_grid_range(start_date, end_date)
    user_uuid = _to_uuid(user_id)
    result = await db.execute(
        select(DailyCheckIn).where(
            DailyCheckIn.user_id == user_uuid,
            DailyCheckIn.local_date >= start,
            DailyCheckIn.local_date <= end,
        )
    )
    status_by_date = {row.local_date: row.daily_status for row in result.scalars().all()}

    cells: List[ActivityGridCell] = []
    day = start
    while day <= end:
        cells.append(ActivityGridCell(date=day, status=status_by_date.get(day, "none")))
        day = day + timedelta(days=1)

    return ActivityGridResponse(start_date=start, end_date=end, cells=cells)
