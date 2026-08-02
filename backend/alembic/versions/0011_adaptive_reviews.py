"""Add Phase 7 execution overlays and weekly-review foundations.

Revision ID: 0011_adaptive_reviews
Revises: 0010_nutrition_recommendations
Create Date: 2026-08-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0011_adaptive_reviews"
down_revision: Union[str, None] = "0010_nutrition_recommendations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JSON_VALUE = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "training_day_adjustments",
        sa.Column("adjustment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_local_date", sa.Date(), nullable=False),
        sa.Column("target_local_date", sa.Date(), nullable=True),
        sa.Column("adjustment_kind", sa.String(length=20), nullable=False),
        sa.Column("trigger_code", sa.String(length=40), nullable=False),
        sa.Column("reason_codes", JSON_VALUE, nullable=False),
        sa.Column("source_context_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("decision_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("adaptive_policy_version", sa.String(length=40), nullable=False),
        sa.Column("training_policy_version", sa.String(length=20), nullable=False),
        sa.Column("catalog_version", sa.String(length=40), nullable=False),
        sa.Column("source_manifest_version", sa.String(length=20), nullable=False),
        sa.Column("surface", sa.String(length=30), nullable=False),
        sa.Column("target_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            "adjustment_kind IN ('shortened','recovery','deferred','active_rest','unchanged')",
            name="ck_training_day_adjustments_kind",
        ),
        sa.CheckConstraint(
            "surface IN ('button','agent_confirmation')",
            name="ck_training_day_adjustments_surface",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["plan_version_id"], ["training_plan_versions.plan_version_id"]
        ),
        sa.ForeignKeyConstraint(
            ["source_session_id"], ["training_sessions.session_id"]
        ),
        sa.PrimaryKeyConstraint("adjustment_id"),
        sa.UniqueConstraint(
            "plan_version_id", "source_session_id", "source_local_date",
            "source_context_fingerprint", "adaptive_policy_version",
            "adjustment_kind", name="uq_training_day_adjustments_decision",
        ),
    )
    op.create_index(
        "ix_training_day_adjustments_user_source_date",
        "training_day_adjustments", ["user_id", "source_local_date"], unique=False,
    )
    op.create_index(
        "ix_training_day_adjustments_user_target_date",
        "training_day_adjustments", ["user_id", "target_local_date"], unique=False,
    )

    op.create_table(
        "training_day_adjustment_items",
        sa.Column("adjustment_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("adjustment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_prescription_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("item_action", sa.String(length=20), nullable=False),
        sa.Column("effective_exercise_id", sa.String(length=60), nullable=True),
        sa.Column("sets", sa.Integer(), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("rest_seconds", sa.Integer(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            "item_action IN ('keep','drop','replace')",
            name="ck_training_day_adjustment_items_action",
        ),
        sa.ForeignKeyConstraint(
            ["adjustment_id"], ["training_day_adjustments.adjustment_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_prescription_id"], ["training_prescriptions.prescription_id"]
        ),
        sa.PrimaryKeyConstraint("adjustment_item_id"),
        sa.UniqueConstraint(
            "adjustment_id", "source_prescription_id",
            name="uq_training_day_adjustment_items_source",
        ),
        sa.UniqueConstraint(
            "adjustment_id", "display_order",
            name="uq_training_day_adjustment_items_order",
        ),
    )
    op.create_index(
        "ix_training_day_adjustment_items_adjustment",
        "training_day_adjustment_items", ["adjustment_id"], unique=False,
    )

    op.create_table(
        "training_weekly_reviews",
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("week_index", sa.Integer(), nullable=False),
        sa.Column("review_version", sa.Integer(), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("facts", JSON_VALUE, nullable=False),
        sa.Column("proposal_codes", JSON_VALUE, nullable=False),
        sa.Column("adaptive_policy_version", sa.String(length=40), nullable=False),
        sa.Column("training_policy_version", sa.String(length=20), nullable=False),
        sa.Column("catalog_version", sa.String(length=40), nullable=False),
        sa.Column("source_manifest_version", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            "week_index >= 1 AND week_index <= 4",
            name="ck_training_weekly_reviews_week",
        ),
        sa.CheckConstraint(
            "review_version >= 1", name="ck_training_weekly_reviews_version"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["plan_version_id"], ["training_plan_versions.plan_version_id"]
        ),
        sa.PrimaryKeyConstraint("review_id"),
        sa.UniqueConstraint(
            "plan_version_id", "week_index", "input_fingerprint",
            name="uq_training_weekly_reviews_fingerprint",
        ),
        sa.UniqueConstraint(
            "plan_version_id", "week_index", "review_version",
            name="uq_training_weekly_reviews_version",
        ),
    )
    op.create_index(
        "ix_training_weekly_reviews_user",
        "training_weekly_reviews", ["user_id", "period_end"], unique=False,
    )

    op.create_table(
        "posture_recheck_dismissals",
        sa.Column("dismissal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("due_reason", sa.String(length=40), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["plan_version_id"], ["training_plan_versions.plan_version_id"]
        ),
        sa.PrimaryKeyConstraint("dismissal_id"),
        sa.UniqueConstraint(
            "user_id", "plan_version_id",
            name="uq_posture_recheck_dismissals_cycle",
        ),
    )
    op.create_index(
        "ix_posture_recheck_dismissals_user",
        "posture_recheck_dismissals", ["user_id"], unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_posture_recheck_dismissals_user",
        table_name="posture_recheck_dismissals",
    )
    op.drop_table("posture_recheck_dismissals")
    op.drop_index(
        "ix_training_weekly_reviews_user", table_name="training_weekly_reviews"
    )
    op.drop_table("training_weekly_reviews")
    op.drop_index(
        "ix_training_day_adjustment_items_adjustment",
        table_name="training_day_adjustment_items",
    )
    op.drop_table("training_day_adjustment_items")
    op.drop_index(
        "ix_training_day_adjustments_user_target_date",
        table_name="training_day_adjustments",
    )
    op.drop_index(
        "ix_training_day_adjustments_user_source_date",
        table_name="training_day_adjustments",
    )
    op.drop_table("training_day_adjustments")
