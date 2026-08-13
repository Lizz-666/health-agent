"""Add nullable weekly-review origins to immutable draft versions.

Revision ID: 0012_review_draft_origins
Revises: 0011_adaptive_reviews
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012_review_draft_origins"
down_revision = "0011_adaptive_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("training_plan_versions", "nutrition_recommendations"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column(
                "origin_weekly_review_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ))
            batch.create_foreign_key(
                f"fk_{table}_origin_weekly_review_id",
                "training_weekly_reviews",
                ["origin_weekly_review_id"],
                ["review_id"],
                ondelete="SET NULL",
            )
            batch.create_index(
                f"ix_{table}_origin_weekly_review_id",
                ["origin_weekly_review_id"],
                unique=False,
            )


def downgrade() -> None:
    for table in ("nutrition_recommendations", "training_plan_versions"):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_origin_weekly_review_id")
            batch.drop_constraint(
                f"fk_{table}_origin_weekly_review_id",
                type_="foreignkey",
            )
            batch.drop_column("origin_weekly_review_id")
