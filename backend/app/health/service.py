"""Health profile application service (Phase 2 Task 2).

Owns the GET / PUT / DELETE behaviour for the authenticated user's health
profile. Ownership comes ONLY from the JWT-derived ``user_id`` (a string);
the service converts it to ``UUID`` for DB queries. No method accepts a
client-supplied ``user_id``, so cross-user access is impossible by
construction (spec API And State Contracts, Safety).

Safety / privacy:
- Readiness is produced deterministically by ``app.health.risk`` only; free-
  text notes never affect the tier.
- The service never logs raw sensitive fields (allergies, pain notes, diet
  exclusions). Unhandled errors are reduced to a structured 503 by the global
  handler in ``app.main``.
- Missing optional fields stay ``None``; nothing is fabricated.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.health.models import HealthProfile
from app.health.risk import classify_readiness
from app.health.schemas import (
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
