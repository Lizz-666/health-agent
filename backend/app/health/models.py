import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
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

    # Monotonically incremented on each update; used by future recommendation
    # requests to detect stale profile snapshots (spec Domain Model `version`).
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
