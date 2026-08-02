"""Add nullable structured nutrition allergy and exclusion answers.

Revision ID: 0009_nutrition_profile_codes
Revises: 0008_agent_mvp
Create Date: 2026-08-01

No backfill is performed: NULL must continue to mean not answered. Existing
legacy free-text arrays remain untouched and block automatic nutrition until
the user resolves them into the structured fields.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009_nutrition_profile_codes"
down_revision: Union[str, None] = "0008_agent_mvp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "health_profiles",
        sa.Column(
            "food_allergen_codes",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
    )
    op.add_column(
        "health_profiles",
        sa.Column(
            "excluded_food_codes",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("health_profiles", "excluded_food_codes")
    op.drop_column("health_profiles", "food_allergen_codes")
