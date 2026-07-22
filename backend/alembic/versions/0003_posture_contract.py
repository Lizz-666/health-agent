"""Posture migration phase C: contract source/lifecycle and drop old aliases.

Revision ID: 0003_posture_contract
Revises: 0002
Create Date: 2026-07-18

Phase C (contract / cleanup) of the posture core productization migration
(spec 2026-07-11-posture-core-productization.md section 16.1 / plan Task 10.5):

- Backfill residual NULLs in ``source`` from ``method`` and ``lifecycle`` to
  ``'active'`` for rows that were not backfilled in Phase B.
- Tighten ``source`` and ``lifecycle`` to NOT NULL.
- Keep ``severity`` permanently nullable. An absent severity is a legal state
  meaning "source produced no firm conclusion".
- Drop legacy database columns ``method`` and ``result``. API-facing
  compatibility fields are still computed in the service layer.

Downgrade restores the expand-phase state:

1. Re-add ``method`` and ``result`` as nullable columns.
2. Backfill ``method = source`` and
   ``result = COALESCE(severity, 'uncertain')``.
3. Tighten ``method`` and ``result`` to NOT NULL.
4. Restore ``source`` and ``lifecycle`` to nullable.
5. Leave ``severity`` nullable.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_posture_contract"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: deterministic backfill of residual NULLs from Phase A/B.
    op.execute(
        "UPDATE posture_assessment_events "
        "SET source = method WHERE source IS NULL"
    )
    op.execute(
        "UPDATE posture_assessment_events "
        "SET lifecycle = 'active' WHERE lifecycle IS NULL"
    )

    # Step 2: tighten source and lifecycle to NOT NULL.
    op.alter_column(
        "posture_assessment_events",
        "source",
        existing_type=sa.String(20),
        nullable=False,
    )
    op.alter_column(
        "posture_assessment_events",
        "lifecycle",
        existing_type=sa.String(20),
        nullable=False,
    )

    # Step 3: severity stays permanently nullable; no change.

    # Step 4: drop legacy database columns.
    op.drop_column("posture_assessment_events", "method")
    op.drop_column("posture_assessment_events", "result")


def downgrade() -> None:
    # Step 1: re-add method and result as nullable columns.
    op.add_column(
        "posture_assessment_events",
        sa.Column("method", sa.String(20), nullable=True),
    )
    op.add_column(
        "posture_assessment_events",
        sa.Column("result", sa.String(20), nullable=True),
    )

    # Step 2: backfill method/result compatibility columns.
    op.execute(
        "UPDATE posture_assessment_events "
        "SET method = source, result = COALESCE(severity, 'uncertain')"
    )

    # Step 3: tighten method and result to NOT NULL.
    op.alter_column(
        "posture_assessment_events",
        "method",
        existing_type=sa.String(20),
        nullable=False,
    )
    op.alter_column(
        "posture_assessment_events",
        "result",
        existing_type=sa.String(20),
        nullable=False,
    )

    # Step 4: restore source and lifecycle to nullable.
    op.alter_column(
        "posture_assessment_events",
        "source",
        existing_type=sa.String(20),
        nullable=True,
    )
    op.alter_column(
        "posture_assessment_events",
        "lifecycle",
        existing_type=sa.String(20),
        nullable=True,
    )

    # Step 5: severity stays nullable; no change.
