import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String,
    Integer,
    Boolean,
    DateTime,
    func,
    ForeignKey,
    LargeBinary,
    CheckConstraint,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


# Tombstone ``object_delete_status`` may ONLY store *completed* states.
# Pending / failed statuses are forbidden in the tombstone (they live in
# ``purge_operations`` instead). Mirrors the CHECK constraint in migration
# 0002 and spec §6.6.
TOMBSTONE_OBJECT_DELETE_COMPLETED = (
    "oss_deleted",
    "oss_not_applicable",
    "oss_deleted_or_not_found",
)


class PostureAssessmentEvent(Base):
    """Immutable assessment event log (renamed from ``posture_assessments``).

    Phase C (migration 0003): ``source`` and ``lifecycle`` are NOT NULL;
    ``severity`` stays permanently nullable (an absent severity is a legal
    state). Legacy ``method`` / ``result`` columns have been dropped from
    the database; the API-facing method/result fields are now computed from
    source/severity in the service layer.
    """

    __tablename__ = "posture_assessment_events"
    __table_args__ = (
        Index(
            "ix_posture_assessment_events_user_issue_source_lifecycle",
            "user_id",
            "issue_id",
            "source",
            "lifecycle",
        ),
        Index(
            "ix_posture_assessment_events_user_created_at",
            "user_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    issue_id: Mapped[str] = mapped_column(String(20), nullable=False)
    # Phase C: source and lifecycle are NOT NULL (tightened in migration 0003).
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    lifecycle: Mapped[str] = mapped_column(String(20), nullable=False)
    content_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ai_model_meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    self_test_answers: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ai_response: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    photo_keys: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Backward-compatible alias. ``app.posture.service`` and existing tests import
# ``PostureAssessment``. The alias keeps those callers working against the
# renamed table/model while Phase C removes only the old database columns.
PostureAssessment = PostureAssessmentEvent


class PostureProfileEntry(Base):
    """Current-state projection for a single issue per user (spec §8.5)."""

    __tablename__ = "posture_profile_entries"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "issue_id",
            name="uq_posture_profile_entries_user_issue",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    issue_id: Mapped[str] = mapped_column(String(20), nullable=False)
    latest_self_test_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posture_assessment_events.id"), nullable=True
    )
    latest_photo_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posture_assessment_events.id"), nullable=True
    )
    combined_severity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    certainty: Mapped[str] = mapped_column(String(20), nullable=False)
    sources: Mapped[dict] = mapped_column(JSONB, nullable=False)
    has_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_version: Mapped[str] = mapped_column(String(30), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PostureUserGoal(Base):
    """A user-confirmed primary improvement goal (spec §8.5)."""

    __tablename__ = "posture_user_goals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    issue_id: Mapped[str] = mapped_column(String(20), nullable=False)
    priority_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    suggestion_id: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(30), nullable=False)
    risk_version: Mapped[str] = mapped_column(String(30), nullable=False)
    superseded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PostureSafetySignal(Base):
    """Structured red-flag / risk signal reported by a user (spec §8.5/§12.2)."""

    __tablename__ = "posture_safety_signals"
    __table_args__ = (
        Index(
            "ix_posture_safety_signals_user_reported",
            "user_id",
            "reported_at",
        ),
        Index(
            "ix_posture_safety_signals_user_lifecycle",
            "user_id",
            "lifecycle",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(30), nullable=False)
    body_region: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    related_issue_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    severity_hint: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(20), nullable=False)
    invalidates_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_basis: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    resolution_source: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    resolved_risk_version: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IdempotencyRecord(Base):
    """Single idempotency mechanism for side-effect tools (spec §8.5)."""

    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "operation",
            "idempotency_key",
            name="uq_idempotency_records_user_op_key",
        ),
        Index("ix_idempotency_records_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    result_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PosturePurgeTombstone(Base):
    """Un-linkable purge receipt. Only completed object-delete states allowed."""

    __tablename__ = "posture_purge_tombstones"
    __table_args__ = (
        CheckConstraint(
            "object_delete_status IN ('oss_deleted', 'oss_not_applicable', 'oss_deleted_or_not_found')",
            name="ck_posture_purge_tombstones_object_delete_status_completed",
        ),
        Index("ix_posture_purge_tombstones_deleted_at", "deleted_at"),
    )

    receipt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    purge_reason: Mapped[str] = mapped_column(String(30), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    object_delete_status: Mapped[str] = mapped_column(String(30), nullable=False)


class PurgeOperation(Base):
    """Persisted asynchronous purge job (spec §6.7).

    ``user_id`` is a NULLABLE FK with ON DELETE SET NULL so account deletion
    is never blocked by a NOT NULL FK (spec §6.7.3).
    """

    __tablename__ = "purge_operations"
    __table_args__ = (
        Index(
            "ix_purge_operations_status_next_retry_at",
            "status",
            "next_retry_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    trigger: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    encrypted_object_keys: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    target_event_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    target_signal_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
