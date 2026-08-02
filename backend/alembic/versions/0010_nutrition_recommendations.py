"""Add immutable nutrition recommendation version persistence.

Revision ID: 0010_nutrition_recommendations
Revises: 0009_nutrition_profile_codes
Create Date: 2026-08-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0010_nutrition_recommendations"
down_revision: Union[str, None] = "0009_nutrition_profile_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "nutrition_recommendations",
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("change_reason", sa.String(length=50), nullable=False),
        sa.Column("source_recommendation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_context_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("training_plan_version_id", sa.String(length=64), nullable=False),
        sa.Column("checkin_token", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=40), nullable=False),
        sa.Column("catalog_version", sa.String(length=40), nullable=False),
        sa.Column("source_manifest_version", sa.String(length=40), nullable=False),
        sa.Column("media_manifest_version", sa.String(length=40), nullable=False),
        sa.Column("decision_gate", sa.String(length=30), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "validation_codes",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'superseded')",
            name="ck_nutrition_recommendations_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["source_recommendation_id"], ["nutrition_recommendations.recommendation_id"]
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_id"], ["nutrition_recommendations.recommendation_id"]
        ),
        sa.PrimaryKeyConstraint("recommendation_id"),
        sa.UniqueConstraint(
            "user_id", "version", name="uq_nutrition_recommendations_user_version"
        ),
    )
    op.create_index(
        "ix_nutrition_recommendations_user_status",
        "nutrition_recommendations",
        ["user_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_nutrition_recommendations_one_draft",
        "nutrition_recommendations",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'draft'"),
        sqlite_where=sa.text("status = 'draft'"),
    )
    op.create_index(
        "uq_nutrition_recommendations_one_active",
        "nutrition_recommendations",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_nutrition_recommendations_one_active",
        table_name="nutrition_recommendations",
    )
    op.drop_index(
        "uq_nutrition_recommendations_one_draft",
        table_name="nutrition_recommendations",
    )
    op.drop_index(
        "ix_nutrition_recommendations_user_status",
        table_name="nutrition_recommendations",
    )
    op.drop_table("nutrition_recommendations")
