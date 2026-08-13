"""Phase 2 daily check-ins: health_checkins table.

Revision ID: 0005_health_checkins
Revises: 0004_health_profile_tracking
Create Date: 2026-07-23

Phase 2 Task 3 (spec ``2026-07-22-health-profile-checkins-trends.md`` Domain
Model, plan Task 3): create the ``health_checkins`` table that stores at most
one current check-in per user per local calendar day.

- UNIQUE(user_id, local_date) enforces daily uniqueness at the DB layer; the
  service also upserts on this key, so SQLite tests and PostgreSQL stay in
  parity.
- Enum fields (sleep_quality, energy, muscle_soreness, available_time,
  daily_status) are stored as strings and validated at the application /
  Pydantic layer (no DB CHECK), consistent with the profile and posture
  domains.
- ``pain_followup`` is a structured JSONB payload; the raw ``pain_note`` inside
  it is sensitive and must never be written to ordinary logs or audit.
- ``risk_summary`` (normal / caution / restricted / red_flag) and
  ``risk_version`` are the deterministic tier computed at write time and
  stored, so stored and returned values are always consistent.

The table is new in Phase 2, so no backfill runs. Downgrade drops the table; a
documented local reset path (``alembic downgrade base``) remains available for
personal development.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0005_health_checkins"
down_revision: Union[str, None] = "0004_health_profile_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "health_checkins",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("sleep_quality", sa.String(length=30), nullable=False),
        sa.Column("energy", sa.String(length=30), nullable=False),
        sa.Column("muscle_soreness", sa.String(length=30), nullable=False),
        sa.Column("available_time", sa.String(length=30), nullable=False),
        sa.Column("daily_status", sa.String(length=30), nullable=False),
        sa.Column("abnormal_pain", sa.Boolean(), nullable=False),
        sa.Column(
            "pain_followup",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("risk_summary", sa.String(length=30), nullable=False),
        sa.Column("risk_version", sa.String(length=40), nullable=False),
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
            "local_date",
            name="uq_health_checkins_user_date",
        ),
    )


def downgrade() -> None:
    # The UNIQUE(user_id, local_date) constraint and its implicit index are
    # dropped with the table; no separate index drop is needed.
    op.drop_table("health_checkins")
