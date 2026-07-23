"""Pydantic schemas for the Phase 2 health profile (spec Domain Model).

Conventions mirror ``app.posture.schemas``: ``(str, Enum)`` enums,
``ConfigDict(extra="forbid")`` to reject surprise fields, and bounded
``Field`` validation. Bounds on ``weekly_frequency`` (2-5) and
``session_duration_minutes`` (15/30/45/60) are enforced here at the
application layer (no DB value CHECK), keeping SQLite tests and PostgreSQL in
parity.

``HealthProfileData`` is the canonical structured profile: the input to
``app.health.risk`` classification and the shared shape for the Task 2 API
I/O. Every optional field defaults to ``None`` - missing stays missing.
"""

from datetime import date, datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums (app-layer enforcement; DB columns are nullable strings / ints)
# ---------------------------------------------------------------------------


class FitnessGoal(str, Enum):
    posture_improvement = "posture_improvement"
    fat_loss = "fat_loss"
    basic_strength = "basic_strength"
    mobility = "mobility"
    general_wellness = "general_wellness"


class TrainingExperience(str, Enum):
    beginner = "beginner"
    some_experience = "some_experience"
    experienced = "experienced"


class SessionDurationMinutes(int, Enum):
    """Allowed single-session durations in minutes."""

    fifteen = 15
    thirty = 30
    forty_five = 45
    sixty = 60


class YesNoUnknown(str, Enum):
    """Structured answer for risk_screen qualifiers. ``unknown`` is distinct
    from a missing answer (``None``): ``unknown`` means the user was asked and
    did not know; ``None`` means the question was never answered."""

    yes = "yes"
    no = "no"
    unknown = "unknown"


# ---------------------------------------------------------------------------
# Structured nested payloads
# ---------------------------------------------------------------------------


class Equipment(BaseModel):
    """Bodyweight / resistance-band availability. Missing on the parent
    (``None``) means the user has not answered; present-but-all-false is a
    distinct 'answered none' state that still counts as missing for readiness
    (spec Domain Model: at least one must be true)."""

    model_config = ConfigDict(extra="forbid")

    bodyweight: Optional[bool] = None
    resistance_band: Optional[bool] = None


class PainInjuryLimitation(BaseModel):
    """A single user-stated limitation.

    ``note`` is untrusted free text and is NEVER a safety-rule source (spec
    Domain Model, Safety). Classification consumes only structured fields.
    """

    model_config = ConfigDict(extra="forbid")

    body_area: str = Field(..., min_length=1, max_length=60)
    status: str = Field(..., min_length=1, max_length=30)
    note: Optional[str] = Field(None, max_length=500)
    updated_at: Optional[date] = None


class RiskScreen(BaseModel):
    """Structured yes/no/unknown qualifiers that drive deterministic
    ``restricted`` classification (safety-boundaries section 2)."""

    model_config = ConfigDict(extra="forbid")

    underage: Optional[YesNoUnknown] = None
    pregnancy_or_postpartum: Optional[YesNoUnknown] = None
    recent_surgery_or_major_injury: Optional[YesNoUnknown] = None
    major_chronic_condition: Optional[YesNoUnknown] = None
    eating_disorder_concern: Optional[YesNoUnknown] = None
    professional_instruction_limitations: Optional[YesNoUnknown] = None


class Allergy(BaseModel):
    """A user-stated allergy label with optional note. Phase 2 stores these
    only; it generates no nutrition advice (spec Domain Model)."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., min_length=1, max_length=60)
    note: Optional[str] = Field(None, max_length=500)


class DietExclusion(BaseModel):
    """A user-stated explicit food exclusion / preference. Stored only in
    Phase 2 (spec Domain Model)."""

    model_config = ConfigDict(extra="forbid")

    item: str = Field(..., min_length=1, max_length=60)
    note: Optional[str] = Field(None, max_length=500)


# ---------------------------------------------------------------------------
# Canonical profile data
# ---------------------------------------------------------------------------


class HealthProfileData(BaseModel):
    """Canonical structured health profile.

    The input to ``app.health.risk`` classification and the shared shape for
    the Task 2 API request/response wrappers. Missing fields stay ``None`` and
    must never be inferred from posture results, chat text, defaults or other
    accounts (spec Domain Model, Recommendation And AI Behavior).
    """

    model_config = ConfigDict(extra="forbid")

    fitness_goal: Optional[FitnessGoal] = None
    training_experience: Optional[TrainingExperience] = None
    weekly_frequency: Optional[int] = Field(None, ge=2, le=5)
    session_duration_minutes: Optional[SessionDurationMinutes] = None
    equipment: Optional[Equipment] = None
    pain_injury_limitations: Optional[List[PainInjuryLimitation]] = None
    risk_screen: Optional[RiskScreen] = None
    allergies: Optional[List[Allergy]] = None
    diet_exclusions: Optional[List[DietExclusion]] = None

    version: int = Field(1, ge=1)
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# API request / response DTOs (Task 2)
#
# ``HealthProfileUpdate`` is the PUT request body: the editable fields only
# (server controls ``id`` / ``version`` / timestamps). ``HealthProfileResponse``
# extends the canonical data with server-managed ``id`` / ``created_at``, so a
# response instance is itself a valid ``HealthProfileData`` and can be fed
# straight into ``app.health.risk.classify_readiness``.
# ---------------------------------------------------------------------------


class HealthProfileUpdate(BaseModel):
    """PUT /api/v1/health/profile request body.

    A full-replacement payload: omitted optional fields are stored as missing
    (``None``), never converted into user-provided defaults (spec API And State
    Contracts). ``version`` / timestamps are server-managed and therefore not
    accepted here. ``extra="forbid"`` rejects unknown fields.
    """

    model_config = ConfigDict(extra="forbid")

    fitness_goal: Optional[FitnessGoal] = None
    training_experience: Optional[TrainingExperience] = None
    weekly_frequency: Optional[int] = Field(None, ge=2, le=5)
    session_duration_minutes: Optional[SessionDurationMinutes] = None
    equipment: Optional[Equipment] = None
    pain_injury_limitations: Optional[List[PainInjuryLimitation]] = None
    risk_screen: Optional[RiskScreen] = None
    allergies: Optional[List[Allergy]] = None
    diet_exclusions: Optional[List[DietExclusion]] = None


class HealthProfileResponse(HealthProfileData):
    """Stored health profile returned by the API.

    Extends ``HealthProfileData`` with server-managed ``id`` / ``created_at``.
    Because it IS-A ``HealthProfileData``, it can be passed directly to the
    deterministic readiness classifier.
    """

    id: UUID
    created_at: datetime


class HealthReadinessResponse(BaseModel):
    """Serialised deterministic readiness result (from ``app.health.risk``).

    Carries no raw sensitive values: only the tier, a reason naming field
    names, the missing-field names, and the restricted qualifier name.
    """

    readiness: str
    risk_version: str
    reason: str
    missing_fields: List[str]
    restricted_reason: Optional[str] = None

    @classmethod
    def from_result(cls, result) -> "HealthReadinessResponse":
        return cls(
            readiness=result.readiness,
            risk_version=result.risk_version,
            reason=result.reason,
            missing_fields=list(result.missing_fields),
            restricted_reason=result.restricted_reason,
        )


class HealthProfileResultResponse(BaseModel):
    """GET / PUT /api/v1/health/profile response envelope.

    ``configured`` is false and ``profile`` is null when no profile exists yet
    (an explicit not-configured state; no defaults are fabricated). ``readiness``
    is always present so the client can show the missing-required-data state
    even before a profile is created.
    """

    configured: bool
    profile: Optional[HealthProfileResponse] = None
    readiness: HealthReadinessResponse


class HealthProfileDeleteResponse(BaseModel):
    """DELETE /api/v1/health/profile response (idempotent)."""

    deleted: bool
    configured: bool = False


# ---------------------------------------------------------------------------
# Daily check-in (Phase 2 spec Domain Model, Daily Check-In; Task 3)
# ---------------------------------------------------------------------------


class SleepQuality(str, Enum):
    poor = "poor"
    ok = "ok"
    good = "good"


class Energy(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"


class MuscleSoreness(str, Enum):
    none = "none"
    mild = "mild"
    significant = "significant"


class AvailableTime(str, Enum):
    none = "none"
    fifteen_min = "15_min"
    thirty_min = "30_min"
    forty_five_min_plus = "45_min_plus"


class DailyStatus(str, Enum):
    """Valid non-failure daily engagement states.

    ``active_rest`` and ``safety_adjustment`` are valid health-management
    states: they are NOT failures, gaps, or missed days (spec Domain Model,
    Activity Grid). ``checked_in`` is the ordinary completed check-in.
    """

    checked_in = "checked_in"
    active_rest = "active_rest"
    safety_adjustment = "safety_adjustment"


class PainStarted(str, Enum):
    today = "today"
    recent_days = "recent_days"
    ongoing = "ongoing"
    after_acute_event = "after_acute_event"


class PainIntensity(str, Enum):
    mild = "mild"
    moderate = "moderate"
    severe = "severe"


class PainFollowup(BaseModel):
    """Conditional follow-up required when ``abnormal_pain`` is true.

    Only the structured boolean / enum fields drive the deterministic
    ``red_flag`` classification (spec Safety). ``pain_note`` is untrusted
    free text: it is NEVER a safety-rule source and must never be logged.
    """

    model_config = ConfigDict(extra="forbid")

    pain_area: str = Field(..., min_length=1, max_length=60)
    pain_started: PainStarted
    pain_intensity: PainIntensity
    has_neurological_symptom: bool
    has_dizziness_or_chest_symptom: bool
    has_acute_trauma: bool
    pain_note: Optional[str] = Field(None, max_length=500)


class CheckInCreate(BaseModel):
    """PUT /api/v1/health/checkins/today request body.

    ``local_date`` is the user-local date and the per-user daily uniqueness key.
    ``abnormal_pain=true`` requires a complete ``pain_followup`` object (the
    completeness gate is enforced deterministically in the service layer, which
    raises ``pain_followup_required`` when it is missing). ``extra="forbid"``
    rejects unknown fields; enums / bounds are validated by Pydantic.
    """

    model_config = ConfigDict(extra="forbid")

    local_date: date
    sleep_quality: SleepQuality
    energy: Energy
    muscle_soreness: MuscleSoreness
    available_time: AvailableTime
    daily_status: DailyStatus
    abnormal_pain: bool
    pain_followup: Optional[PainFollowup] = None


class CheckInResponse(BaseModel):
    """Stored daily check-in returned by the API.

    ``risk_summary`` / ``risk_version`` are the deterministic tier and policy
    version computed at write time and stored, so the stored and returned
    values are always consistent. ``id`` / timestamps are server-managed.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    local_date: date
    sleep_quality: SleepQuality
    energy: Energy
    muscle_soreness: MuscleSoreness
    available_time: AvailableTime
    daily_status: DailyStatus
    abnormal_pain: bool
    pain_followup: Optional[PainFollowup] = None
    risk_summary: str
    risk_version: str
    created_at: datetime
    updated_at: datetime


class CheckInTodayResultResponse(BaseModel):
    """GET /api/v1/health/checkins/today response envelope.

    ``checked_in`` is false and ``checkin`` is null when no check-in exists for
    the requested local date (an explicit not-checked-in state; never a
    fabricated 'normal').
    """

    checked_in: bool
    checkin: Optional[CheckInResponse] = None


class CheckInDeleteResponse(BaseModel):
    """DELETE /api/v1/health/checkins/{checkin_id} response."""

    deleted: bool
