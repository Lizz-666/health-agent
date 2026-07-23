"""Health profile application service (Phase 2 Task 2 / Task 3).

Owns the GET / PUT / DELETE behaviour for the authenticated user's health
profile and daily check-ins. Ownership comes ONLY from the JWT-derived
``user_id`` (a string); the service converts it to ``UUID`` for DB queries. No
method accepts a client-supplied ``user_id``, so cross-user access is
impossible by construction (spec API And State Contracts, Safety).

Safety / privacy:
- Readiness and check-in ``risk_summary`` are produced deterministically by
  ``app.health.risk`` only; free-text notes never affect the tier.
- The service never logs raw sensitive fields (allergies, pain notes, diet
  exclusions, follow-up payloads). Unhandled errors are reduced to a structured
  503 by the global handler in ``app.main``.
- Missing optional fields stay ``None``; nothing is fabricated.
- ``abnormal_pain=true`` requires a complete ``pain_followup``; otherwise the
  service raises a deterministic ``pain_followup_required`` error.
"""

from datetime import date
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFound
from app.health.models import DailyCheckIn, HealthProfile
from app.health.risk import classify_checkin, classify_readiness, restricted_reason
from app.health.schemas import (
    CheckInCreate,
    CheckInResponse,
    HealthProfileData,
    HealthProfileResponse,
    HealthProfileResultResponse,
    HealthProfileUpdate,
    HealthReadinessResponse,
)


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


async def upsert_today(
    db: AsyncSession, user_id: str, data: CheckInCreate
) -> CheckInResponse:
    """Create or fully replace the caller's check-in for ``data.local_date``.

    Safety gates (deterministic):
    - ``abnormal_pain=true`` requires a complete ``pain_followup``; otherwise a
      ``pain_followup_required`` error is raised and nothing is stored.
    - ``abnormal_pain=false`` discards any supplied follow-up (stored as None).
    - ``risk_summary`` is computed deterministically from the structured
      follow-up signals plus the profile ``restricted`` qualifier, then stored.

    At most one check-in per user per local_date: an existing row for that date
    is replaced in place; a different date creates a new row.
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

    await db.commit()
    await db.refresh(row)
    return _checkin_response(row)


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
