"""Phase 4 four-week training plan MVP: plan version/session/prescription/
feedback/substitution tables.

Revision ID: 0007_training_plans
Revises: 0006_health_weight_tracking
Create Date: 2026-07-27

Phase 4 Task 2 (spec ``2026-07-27-four-week-plan-mvp.md`` Domain And State Model;
ADR-0002): create the five Phase 4 tables backing deterministic plan generation,
immutable versioned plans, single-active-per-user, daily feedback, and one
same-day substitution.

- ``training_plan_versions`` carries the lifecycle status and freshness pins.
  A PostgreSQL partial UNIQUE index enforces at most one ``active`` plan per
  user (ADR-0002). On SQLite the invariant is application-checked.
- ``training_sessions`` / ``training_prescriptions`` store the four-week
  structure; catalog exercise references are by value (``exercise_id``), since
  the catalog is versioned JSON, not a DB table.
- ``training_session_feedback`` stores one day's outcome per
  ``(session_id, local_date)`` and never stores a free-text note.
- ``training_session_substitutions`` stores one same-day substitution delta per
  ``(session_id, local_date)``.

Idempotency is NOT a new table: Phase 4 reuses the existing
``idempotency_records`` table (ADR-0001) with new ``operation`` values.

The tables are new in Phase 4, so no backfill runs. Downgrade drops the five
Phase 4 tables in dependency order; it does not touch posture/health tables or
other operations' ``idempotency_records`` rows. Plan data is recreation-safe
(regenerable from the deterministic engine), so downgrade is a documented safe
recovery path (users regenerate after rollback).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0007_training_plans"
down_revision: Union[str, None] = "0006_health_weight_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "training_plan_versions",
        sa.Column("plan_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_goal", sa.String(length=30), nullable=False),
        sa.Column(
            "source_context_fingerprint", sa.String(length=64), nullable=False
        ),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("catalog_version", sa.String(length=40), nullable=False),
        sa.Column("policy_version", sa.String(length=20), nullable=False),
        sa.Column(
            "source_manifest_version", sa.String(length=20), nullable=False
        ),
        sa.Column("weekly_frequency", sa.Integer(), nullable=False),
        sa.Column(
            "session_duration_minutes", sa.Integer(), nullable=False
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("change_reason", sa.String(length=40), nullable=False),
        sa.Column("decision_gate", sa.String(length=30), nullable=False),
        sa.Column("decision_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "generated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("plan_version_id"),
    )
    # At most one active plan per user (ADR-0002). Partial unique index.
    op.create_index(
        "uq_training_plan_versions_one_active",
        "training_plan_versions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_training_plan_versions_user_status",
        "training_plan_versions",
        ["user_id", "status"],
        unique=False,
    )

    op.create_table(
        "training_sessions",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "plan_version_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("week_index", sa.Integer(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("session_order", sa.Integer(), nullable=False),
        sa.Column("target_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["plan_version_id"], ["training_plan_versions.plan_version_id"]
        ),
        sa.PrimaryKeyConstraint("session_id"),
        sa.UniqueConstraint(
            "plan_version_id",
            "week_index",
            "session_order",
            name="uq_training_sessions_version_week_order",
        ),
    )
    op.create_index(
        "ix_training_sessions_version",
        "training_sessions",
        ["plan_version_id"],
        unique=False,
    )

    op.create_table(
        "training_prescriptions",
        sa.Column(
            "prescription_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exercise_id", sa.String(length=60), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("rest_seconds", sa.Integer(), nullable=False),
        sa.Column("relation_reason", sa.String(length=30), nullable=True),
        sa.Column(
            "relation_source_exercise_id", sa.String(length=60), nullable=True
        ),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["training_sessions.session_id"]),
        sa.PrimaryKeyConstraint("prescription_id"),
    )
    op.create_index(
        "ix_training_prescriptions_session",
        "training_prescriptions",
        ["session_id"],
        unique=False,
    )

    op.create_table(
        "training_session_feedback",
        sa.Column("feedback_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "plan_version_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("outcome_state", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["plan_version_id"], ["training_plan_versions.plan_version_id"]
        ),
        sa.ForeignKeyConstraint(["session_id"], ["training_sessions.session_id"]),
        sa.PrimaryKeyConstraint("feedback_id"),
        sa.UniqueConstraint(
            "session_id",
            "local_date",
            name="uq_training_session_feedback_session_date",
        ),
    )
    op.create_index(
        "ix_training_session_feedback_user",
        "training_session_feedback",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "training_session_substitutions",
        sa.Column(
            "substitution_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "plan_version_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column(
            "original_exercise_id", sa.String(length=60), nullable=False
        ),
        sa.Column(
            "replacement_exercise_id", sa.String(length=60), nullable=False
        ),
        sa.Column("relation_reason", sa.String(length=30), nullable=False),
        sa.Column("decision_gate", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["plan_version_id"], ["training_plan_versions.plan_version_id"]
        ),
        sa.ForeignKeyConstraint(["session_id"], ["training_sessions.session_id"]),
        sa.PrimaryKeyConstraint("substitution_id"),
        sa.UniqueConstraint(
            "session_id",
            "local_date",
            name="uq_training_session_substitutions_session_date",
        ),
    )
    op.create_index(
        "ix_training_session_substitutions_user",
        "training_session_substitutions",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    # Drop Phase 4 tables in reverse dependency order. Never touch posture/health
    # tables or other operations' idempotency_records rows. Plan data is
    # recreation-safe, so downgrade is a documented safe recovery path.
    op.drop_index(
        "ix_training_session_substitutions_user",
        table_name="training_session_substitutions",
    )
    op.drop_table("training_session_substitutions")

    op.drop_index(
        "ix_training_session_feedback_user", table_name="training_session_feedback"
    )
    op.drop_table("training_session_feedback")

    op.drop_index(
        "ix_training_prescriptions_session", table_name="training_prescriptions"
    )
    op.drop_table("training_prescriptions")

    op.drop_index("ix_training_sessions_version", table_name="training_sessions")
    op.drop_table("training_sessions")

    op.drop_index(
        "ix_training_plan_versions_user_status", table_name="training_plan_versions"
    )
    op.drop_index(
        "uq_training_plan_versions_one_active", table_name="training_plan_versions"
    )
    op.drop_table("training_plan_versions")
