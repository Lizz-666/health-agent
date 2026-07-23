"""Phase 2 weight tracking: weight_records table.

Revision ID: 0006_health_weight_tracking
Revises: 0005_health_checkins
Create Date: 2026-07-23

Phase 2 Task 4 (spec ``2026-07-22-health-profile-checkins-trends.md`` Domain
Model, plan Task 4): create the ``weight_records`` table that stores the user's
manual body-weight records used by the trend endpoint.

- Multiple records per user (no UNIQUE constraint).
- ``weight_kg`` is a bounded positive decimal (Numeric(6,2)); the realistic
  bounds (20.0-300.0 kg) are enforced at the application / Pydantic layer (no
  DB CHECK), consistent with the profile / posture domains.
- ``source`` is always ``manual`` in Phase 2 (no wearable/device import); set
  server-side, never client-set. Stored with a server default of ``'manual'``.
- ``note`` is optional user text (bounded length).
- A composite ``(user_id, recorded_at)`` index backs the per-user trend query.

``weight_kg`` is sensitive (spec Privacy): raw values must never be written to
ordinary logs or audit payloads.

The table is new in Phase 2, so no backfill runs. Downgrade drops the table; a
documented local reset path (``alembic downgrade base``) remains available for
personal development.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0006_health_weight_tracking"
down_revision: Union[str, None] = "0005_health_checkins"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "weight_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column(
            "source",
            sa.String(length=20),
            server_default="manual",
            nullable=False,
        ),
        sa.Column("note", sa.String(length=500), nullable=True),
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
    )
    op.create_index(
        "ix_weight_records_user_recorded_at",
        "weight_records",
        ["user_id", "recorded_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_weight_records_user_recorded_at", table_name="weight_records"
    )
    op.drop_table("weight_records")
