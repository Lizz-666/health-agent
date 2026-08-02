"""Training plan persistence plus Phase 7 immutable execution overlays.

Five tables back the four-week plan MVP (spec
``2026-07-27-four-week-plan-mvp.md`` Domain And State Model; ADR-0002):

- ``training_plan_versions``  immutable plan version (draft/active/superseded/
  cancelled); at most one ``active`` per user (DB partial unique index on
  PostgreSQL 16, application-checked on SQLite).
- ``training_sessions``       week/session within a version.
- ``training_prescriptions``  exercise prescription within a session.
- ``training_session_feedback``     one day's execution outcome per session.
- ``training_session_substitutions`` one same-day substitution delta per session.

Idempotency is NOT stored on these rows: it reuses the shared
``posture.idempotency_records`` table (ADR-0001) with Phase 4 ``operation``
names; ``result_ref`` points to the created entity id. No free-text feedback
note is stored (spec Failure Semantics / Privacy). Phase 7 adds adjustment,
weekly-review foundation, and posture-dismissal rows without mutating plans.

Catalog references are by value (``exercise_id`` string) because the catalog is
versioned JSON, not a DB table; a prescription whose exercise id is absent from
the current catalog is a read-time integrity failure (fail-closed display).
Conventions mirror ``app.health.models`` / ``app.posture.models``: SQLAlchemy 2.0
``Mapped`` columns, PostgreSQL ``UUID``/``JSONB`` (dual-patched for SQLite
tests). Phase 7 closed vocabularies are also enforced by matching DB CHECK
constraints in ORM metadata and Alembic migrations.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TrainingPlanVersion(Base):
    """An immutable plan version (one generated four-week draft lifecycle)."""

    __tablename__ = "training_plan_versions"
    __table_args__ = (
        # NOTE: the "at most one active plan per user" invariant is materialized
        # as a PostgreSQL partial UNIQUE index in migration 0007 (ADR-0002). It
        # is intentionally NOT declared here: SQLAlchemy's ``postgresql_where``
        # clause is silently dropped by ``create_all`` on SQLite while keeping
        # ``unique=True``, which would wrongly enforce UNIQUE(user_id) for ALL
        # rows on the SQLite test DB. persistence.py enforces the invariant at
        # the application level, and a ``requires_pg`` test proves the DB-level
        # guarantee on PostgreSQL 16 where the migration actually runs.
        Index(
            "ix_training_plan_versions_user_status",
            "user_id",
            "status",
        ),
    )

    plan_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    requested_goal: Mapped[str] = mapped_column(String(30), nullable=False)
    source_context_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    catalog_version: Mapped[str] = mapped_column(String(40), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    source_manifest_version: Mapped[str] = mapped_column(String(20), nullable=False)
    weekly_frequency: Mapped[int] = mapped_column(Integer, nullable=False)
    session_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    # Lifecycle status (app.training.state.PlanStatus values).
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # Stable rationale code from app.training.rationale (e.g. initial_confirmation).
    change_reason: Mapped[str] = mapped_column(String(40), nullable=False)

    # Safety decision recorded at generation/confirmation time (no raw health).
    decision_gate: Mapped[str] = mapped_column(String(30), nullable=False)
    decision_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TrainingSession(Base):
    """A session within a plan version's four-week timeline."""

    __tablename__ = "training_sessions"
    __table_args__ = (
        UniqueConstraint(
            "plan_version_id",
            "week_index",
            "session_order",
            name="uq_training_sessions_version_week_order",
        ),
        Index(
            "ix_training_sessions_version",
            "plan_version_id",
        ),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_plan_versions.plan_version_id"),
        nullable=False,
    )
    week_index: Mapped[int] = mapped_column(Integer, nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    session_order: Mapped[int] = mapped_column(Integer, nullable=False)
    target_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TrainingPrescription(Base):
    """An exercise prescription within a session."""

    __tablename__ = "training_prescriptions"
    __table_args__ = (
        Index(
            "ix_training_prescriptions_session",
            "session_id",
        ),
    )

    prescription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_sessions.session_id"),
        nullable=False,
    )
    exercise_id: Mapped[str] = mapped_column(String(60), nullable=False)
    sets: Mapped[int] = mapped_column(Integer, nullable=False)
    reps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rest_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    relation_reason: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    relation_source_exercise_id: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TrainingSessionFeedback(Base):
    """One day's execution outcome for one session of the active plan.

    At most one row per ``(session_id, local_date)``. No free-text note is
    stored (spec Privacy; free text is never a safety input). Replay is handled
    by the shared ``idempotency_records`` (result_ref = feedback id).
    """

    __tablename__ = "training_session_feedback"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "local_date",
            name="uq_training_session_feedback_session_date",
        ),
        Index(
            "ix_training_session_feedback_user",
            "user_id",
        ),
    )

    feedback_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    plan_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_plan_versions.plan_version_id"),
        nullable=False,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_sessions.session_id"),
        nullable=False,
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    outcome_state: Mapped[str] = mapped_column(String(20), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TrainingSessionSubstitution(Base):
    """One same-day substitution delta on a session of the active plan.

    At most one substitution per ``(session_id, local_date)``. Recorded as a
    delta, never a rewrite of the immutable plan version.
    """

    __tablename__ = "training_session_substitutions"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "local_date",
            name="uq_training_session_substitutions_session_date",
        ),
        Index(
            "ix_training_session_substitutions_user",
            "user_id",
        ),
    )

    substitution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    plan_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_plan_versions.plan_version_id"),
        nullable=False,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_sessions.session_id"),
        nullable=False,
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    original_exercise_id: Mapped[str] = mapped_column(String(60), nullable=False)
    replacement_exercise_id: Mapped[str] = mapped_column(String(60), nullable=False)
    relation_reason: Mapped[str] = mapped_column(String(30), nullable=False)
    decision_gate: Mapped[str] = mapped_column(String(30), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TrainingDayAdjustment(Base):
    """Append-only same-day execution decision; never mutates a plan version."""

    __tablename__ = "training_day_adjustments"
    __table_args__ = (
        CheckConstraint(
            "adjustment_kind IN ('shortened','recovery','deferred','active_rest','unchanged')",
            name="ck_training_day_adjustments_kind",
        ),
        CheckConstraint(
            "surface IN ('button','agent_confirmation')",
            name="ck_training_day_adjustments_surface",
        ),
        UniqueConstraint(
            "plan_version_id",
            "source_session_id",
            "source_local_date",
            "source_context_fingerprint",
            "adaptive_policy_version",
            "adjustment_kind",
            name="uq_training_day_adjustments_decision",
        ),
        Index(
            "ix_training_day_adjustments_user_source_date",
            "user_id",
            "source_local_date",
        ),
        Index(
            "ix_training_day_adjustments_user_target_date",
            "user_id",
            "target_local_date",
        ),
    )

    adjustment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    plan_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_plan_versions.plan_version_id"),
        nullable=False,
    )
    source_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("training_sessions.session_id"), nullable=False
    )
    source_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    target_local_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    adjustment_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger_code: Mapped[str] = mapped_column(String(40), nullable=False)
    reason_codes: Mapped[list] = mapped_column(JSONB, nullable=False)
    source_context_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    adaptive_policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    training_policy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    catalog_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_manifest_version: Mapped[str] = mapped_column(String(20), nullable=False)
    surface: Mapped[str] = mapped_column(String(30), nullable=False)
    target_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TrainingDayAdjustmentItem(Base):
    """Typed item delta/snapshot belonging to one adjustment decision."""

    __tablename__ = "training_day_adjustment_items"
    __table_args__ = (
        CheckConstraint(
            "item_action IN ('keep','drop','replace')",
            name="ck_training_day_adjustment_items_action",
        ),
        UniqueConstraint(
            "adjustment_id",
            "source_prescription_id",
            name="uq_training_day_adjustment_items_source",
        ),
        UniqueConstraint(
            "adjustment_id",
            "display_order",
            name="uq_training_day_adjustment_items_order",
        ),
        Index("ix_training_day_adjustment_items_adjustment", "adjustment_id"),
    )

    adjustment_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    adjustment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_day_adjustments.adjustment_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_prescription_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_prescriptions.prescription_id"),
        nullable=True,
    )
    item_action: Mapped[str] = mapped_column(String(20), nullable=False)
    effective_exercise_id: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True
    )
    sets: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rest_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TrainingWeeklyReview(Base):
    """Immutable input-fingerprinted review snapshot foundation for Gate 3."""

    __tablename__ = "training_weekly_reviews"
    __table_args__ = (
        CheckConstraint(
            "week_index >= 1 AND week_index <= 4",
            name="ck_training_weekly_reviews_week",
        ),
        CheckConstraint(
            "review_version >= 1",
            name="ck_training_weekly_reviews_version",
        ),
        UniqueConstraint(
            "plan_version_id",
            "week_index",
            "input_fingerprint",
            name="uq_training_weekly_reviews_fingerprint",
        ),
        UniqueConstraint(
            "plan_version_id",
            "week_index",
            "review_version",
            name="uq_training_weekly_reviews_version",
        ),
        Index("ix_training_weekly_reviews_user", "user_id", "period_end"),
    )

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    plan_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_plan_versions.plan_version_id"),
        nullable=False,
    )
    week_index: Mapped[int] = mapped_column(Integer, nullable=False)
    review_version: Mapped[int] = mapped_column(Integer, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    facts: Mapped[dict] = mapped_column(JSONB, nullable=False)
    proposal_codes: Mapped[list] = mapped_column(JSONB, nullable=False)
    adaptive_policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    training_policy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    catalog_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_manifest_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PostureRecheckDismissal(Base):
    """Ordinary in-app reminder dismissal scoped to one plan cycle."""

    __tablename__ = "posture_recheck_dismissals"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "plan_version_id",
            name="uq_posture_recheck_dismissals_cycle",
        ),
        Index("ix_posture_recheck_dismissals_user", "user_id"),
    )

    dismissal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    plan_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_plan_versions.plan_version_id"),
        nullable=False,
    )
    due_reason: Mapped[str] = mapped_column(String(40), nullable=False)
    dismissed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


__all__ = [
    "TrainingPlanVersion",
    "TrainingSession",
    "TrainingPrescription",
    "TrainingSessionFeedback",
    "TrainingSessionSubstitution",
    "TrainingDayAdjustment",
    "TrainingDayAdjustmentItem",
    "TrainingWeeklyReview",
    "PostureRecheckDismissal",
]
