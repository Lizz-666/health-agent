import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SensitiveHealthConsentEvent(Base):
    __tablename__ = "sensitive_health_consent_events"
    __table_args__ = (
        CheckConstraint(
            "action IN ('grant', 'withdraw')",
            name="ck_sensitive_health_consent_action",
        ),
        UniqueConstraint(
            "user_id", "purpose", "sequence_no",
            name="uq_sensitive_health_consent_user_purpose_sequence",
        ),
        Index(
            "ix_sensitive_health_consent_user_purpose_sequence",
            "user_id", "purpose", "sequence_no",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    notice_version: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AccountDeletionMarker(Base):
    __tablename__ = "account_deletion_markers"
    __table_args__ = (
        Index("ix_account_deletion_markers_deleted_at", "deleted_at"),
    )

    receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    subject_digest: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
