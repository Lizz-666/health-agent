"""Immutable owned nutrition recommendation versions."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    event,
    func,
    inspect,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NutritionRecommendation(Base):
    __tablename__ = "nutrition_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "version", name="uq_nutrition_recommendations_user_version"
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'superseded')",
            name="ck_nutrition_recommendations_status",
        ),
        Index("ix_nutrition_recommendations_user_status", "user_id", "status"),
        Index(
            "uq_nutrition_recommendations_one_draft",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'draft'"),
            sqlite_where=text("status = 'draft'"),
        ),
        Index(
            "uq_nutrition_recommendations_one_active",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    change_reason: Mapped[str] = mapped_column(String(50), nullable=False)
    source_recommendation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nutrition_recommendations.recommendation_id"),
        nullable=True,
    )
    superseded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nutrition_recommendations.recommendation_id"),
        nullable=True,
    )

    source_context_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    training_plan_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    checkin_token: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    catalog_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_manifest_version: Mapped[str] = mapped_column(String(40), nullable=False)
    media_manifest_version: Mapped[str] = mapped_column(String(40), nullable=False)
    decision_gate: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False
    )
    validation_codes: Mapped[list] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False
    )

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    superseded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=func.now(),
        nullable=False,
    )


_IMMUTABLE_FIELDS = (
    "recommendation_id",
    "user_id",
    "version",
    "source_recommendation_id",
    "source_context_fingerprint",
    "profile_version",
    "training_plan_version_id",
    "checkin_token",
    "policy_version",
    "catalog_version",
    "source_manifest_version",
    "media_manifest_version",
    "decision_gate",
    "payload",
    "validation_codes",
    "generated_at",
)


@event.listens_for(NutritionRecommendation, "before_update")
def _prevent_immutable_recommendation_updates(_mapper, _connection, target) -> None:
    state = inspect(target)
    changed = [field for field in _IMMUTABLE_FIELDS if state.attrs[field].history.has_changes()]
    if changed:
        raise ValueError("immutable nutrition recommendation fields cannot change")


__all__ = ["NutritionRecommendation"]
