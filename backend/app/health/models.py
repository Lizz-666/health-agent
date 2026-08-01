import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HealthProfile(Base):
    """A user's current structured health profile (Phase 2 spec Domain Model).

    Exactly one current editable record per user, enforced by a UNIQUE
    constraint on ``user_id``. Every optional training / diet / pain field is
    a nullable SQL column: a missing value stays missing and is NEVER replaced
    by a default that could look user-provided (spec Domain Model, Safety).

    Sensitive JSON payloads (``allergies``, ``pain_injury_limitations``,
    ``diet_exclusions``, ``risk_screen``) are stored structured; they must not
    be written to ordinary logs or audit payloads (enforced in Task 2's audit
    module). Enum/bounds validation (weekly_frequency 2-5,
    session_duration_minutes 15/30/45/60) is enforced at the Pydantic /
    application layer, consistent with the posture domain.
    """

    __tablename__ = "health_profiles"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            name="uq_health_profiles_user_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Optional training inputs; nullable == missing (never inferred).
    fitness_goal: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    training_experience: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    weekly_frequency: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    session_duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    equipment: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Structured sensitive JSON payloads.
    pain_injury_limitations: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    risk_screen: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    allergies: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    diet_exclusions: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    food_allergen_codes: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    excluded_food_codes: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Monotonically incremented on each update; used by future recommendation
    # requests to detect stale profile snapshots (spec Domain Model `version`).
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DailyCheckIn(Base):
    """A user's daily check-in (Phase 2 spec Domain Model, Daily Check-In).

    At most one current check-in per user per ``local_date``, enforced by
    UNIQUE(user_id, local_date). ``PUT /api/v1/health/checkins/today`` upserts
    the row for the given local date.

    Enum / bounded fields (``sleep_quality``, ``energy``, ``muscle_soreness``,
    ``available_time``, ``daily_status``) are stored as strings and validated at
    the Pydantic / application layer (no DB CHECK), keeping SQLite tests and
    PostgreSQL in parity - same convention as the profile and posture domains.

    ``pain_followup`` is a structured JSON payload. It is sensitive: the raw
    ``pain_note`` inside it must NEVER be written to ordinary logs or audit
    payloads (spec Safety, Privacy; enforced in the service layer by not
    logging it).

    ``risk_summary`` is the deterministic check-in safety tier
    (``normal`` / ``caution`` / ``restricted`` / ``red_flag``) computed by
    ``app.health.risk.classify_checkin`` at write time and stored, so the
    stored and returned values are always consistent. ``risk_version`` records
    the policy version that produced it. A ``red_flag`` check-in is recorded so
    later recommendation paths cannot mistake it for ordinary readiness.
    """

    __tablename__ = "health_checkins"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "local_date",
            name="uq_health_checkins_user_date",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Core check-in fields (a complete check-in always carries these).
    sleep_quality: Mapped[str] = mapped_column(String(30), nullable=False)
    energy: Mapped[str] = mapped_column(String(30), nullable=False)
    muscle_soreness: Mapped[str] = mapped_column(String(30), nullable=False)
    available_time: Mapped[str] = mapped_column(String(30), nullable=False)
    daily_status: Mapped[str] = mapped_column(String(30), nullable=False)

    abnormal_pain: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Structured conditional follow-up; present only when abnormal_pain is true.
    pain_followup: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Deterministic check-in safety tier, computed and stored at write time.
    risk_summary: Mapped[str] = mapped_column(String(30), nullable=False)
    risk_version: Mapped[str] = mapped_column(String(40), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WeightRecord(Base):
    """A user's manual body-weight record (Phase 2 spec Domain Model, Weight
    Record And Trend; Task 4).

    Multiple records per user are allowed (no UNIQUE constraint). ``source`` is
    always ``manual`` in Phase 2 (no wearable / device import) and is set
    server-side, never accepted from the client. ``weight_kg`` is a bounded
    positive decimal; the realistic bounds (20.0-300.0 kg) are enforced at the
    Pydantic / application layer (no DB CHECK), keeping SQLite tests and
    PostgreSQL in parity - same convention as the profile / posture domains.

    ``weight_kg`` is sensitive (spec Privacy): raw values must NEVER be written
    to ordinary logs or audit payloads. The service layer never logs them, and
    unhandled errors are reduced to a structured 503 by the global handler.

    The ``(user_id, recorded_at)`` index backs the per-user trend query.
    Phase 2 trend output carries no plan/diet adjustments, no warnings, and no
    pass/fail judgment from single-day changes.
    """

    __tablename__ = "weight_records"
    __table_args__ = (
        Index(
            "ix_weight_records_user_recorded_at",
            "user_id",
            "recorded_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    weight_kg: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    # Phase 2 has only manual entry; server-set, never client-set.
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
