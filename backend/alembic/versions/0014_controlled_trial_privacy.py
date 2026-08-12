"""Add controlled-trial consent history and deletion markers.

Revision ID: 0014_controlled_trial_privacy
Revises: 0013_controlled_trial_auth
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014_controlled_trial_privacy"
down_revision = "0013_controlled_trial_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sensitive_health_consent_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("notice_version", sa.String(64), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('grant', 'withdraw')",
            name="ck_sensitive_health_consent_action",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "purpose", "sequence_no",
            name="uq_sensitive_health_consent_user_purpose_sequence",
        ),
    )
    op.create_index(
        "ix_sensitive_health_consent_user_purpose_sequence",
        "sensitive_health_consent_events",
        ["user_id", "purpose", "sequence_no"],
        unique=False,
    )
    op.create_table(
        "account_deletion_markers",
        sa.Column("receipt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_digest", sa.String(64), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("receipt_id"),
    )
    op.create_index(
        "ix_account_deletion_markers_subject_digest",
        "account_deletion_markers",
        ["subject_digest"],
        unique=True,
    )
    op.create_index(
        "ix_account_deletion_markers_deleted_at",
        "account_deletion_markers",
        ["deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_account_deletion_markers_deleted_at",
        table_name="account_deletion_markers",
    )
    op.drop_index(
        "ix_account_deletion_markers_subject_digest",
        table_name="account_deletion_markers",
    )
    op.drop_table("account_deletion_markers")
    op.drop_index(
        "ix_sensitive_health_consent_user_purpose_sequence",
        table_name="sensitive_health_consent_events",
    )
    op.drop_table("sensitive_health_consent_events")
