"""Phase 2 health profile tracking: health_profiles table.

Revision ID: 0004_health_profile_tracking
Revises: 0003_posture_contract
Create Date: 2026-07-22

Phase 2 Task 1 (spec ``2026-07-22-health-profile-checkins-trends.md`` Domain
Model, plan Task 1): create the ``health_profiles`` table that stores one
current structured health profile per user.

- One row per user, enforced by UNIQUE(user_id).
- Optional training / diet / pain fields are nullable: a missing value stays
  missing and is never replaced by a default that looks user-provided.
- Sensitive JSON payloads (allergies, pain_injury_limitations, diet_exclusions,
  risk_screen) are stored as JSONB.
- ``version`` is a monotonic integer counter (default 1 via the ORM) used by
  future recommendation requests to detect stale snapshots.

Bounds on ``weekly_frequency`` (2-5) and ``session_duration_minutes``
(15/30/45/60) are enforced at the application / Pydantic layer, consistent
with the posture domain (no DB value CHECK), so SQLite tests and PostgreSQL
stay in parity.

The table is new in Phase 2, so no backfill runs. Downgrade drops the table;
a documented local reset path (``alembic downgrade base``) remains available
for personal development.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0004_health_profile_tracking"
down_revision: Union[str, None] = "0003_posture_contract"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "health_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fitness_goal", sa.String(length=30), nullable=True),
        sa.Column("training_experience", sa.String(length=30), nullable=True),
        sa.Column("weekly_frequency", sa.Integer(), nullable=True),
        sa.Column("session_duration_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "equipment",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "pain_injury_limitations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "risk_screen",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "allergies",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "diet_exclusions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            name="uq_health_profiles_user_id",
        ),
    )


def downgrade() -> None:
    # The UNIQUE(user_id) constraint and its implicit index are dropped with
    # the table; no separate index drop is needed.
    op.drop_table("health_profiles")
