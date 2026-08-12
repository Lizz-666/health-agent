"""Add controlled-trial invitations, credentials, devices, and sessions.

Revision ID: 0013_controlled_trial_auth
Revises: 0012_review_draft_origins
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013_controlled_trial_auth"
down_revision = "0012_review_draft_origins"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column("phone", existing_type=sa.String(20), nullable=True)

    op.create_table(
        "trial_credentials",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("login_id", sa.String(64), nullable=False),
        sa.Column("credential_hash", sa.String(256), nullable=False),
        sa.Column("provider_id", sa.String(32), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_trial_credentials_login_id", "trial_credentials", ["login_id"], unique=True)

    op.create_table(
        "trial_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code_digest", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trial_invitations_code_digest", "trial_invitations", ["code_digest"], unique=True)
    op.create_index("ix_trial_invitations_user_id", "trial_invitations", ["user_id"], unique=False)

    op.create_table(
        "trial_device_enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_key_digest", sa.String(64), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trial_device_enrollments_user_id", "trial_device_enrollments", ["user_id"], unique=True)
    op.create_index("ix_trial_device_enrollments_device_key_digest", "trial_device_enrollments", ["device_key_digest"], unique=False)

    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("refresh_token_digest", sa.String(64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["trial_device_enrollments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["replaced_by_session_id"], ["auth_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"], unique=False)
    op.create_index("ix_auth_sessions_refresh_token_digest", "auth_sessions", ["refresh_token_digest"], unique=True)

    op.create_table(
        "auth_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subject_digest", sa.String(64), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("result_code", sa.String(32), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_attempts_subject_digest", "auth_attempts", ["subject_digest"], unique=False)
    op.create_index("ix_auth_attempts_source_digest", "auth_attempts", ["source_digest"], unique=False)
    op.create_index("ix_auth_attempts_attempted_at", "auth_attempts", ["attempted_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_auth_attempts_attempted_at", table_name="auth_attempts")
    op.drop_index("ix_auth_attempts_source_digest", table_name="auth_attempts")
    op.drop_index("ix_auth_attempts_subject_digest", table_name="auth_attempts")
    op.drop_table("auth_attempts")
    op.drop_index("ix_auth_sessions_refresh_token_digest", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_trial_device_enrollments_device_key_digest", table_name="trial_device_enrollments")
    op.drop_index("ix_trial_device_enrollments_user_id", table_name="trial_device_enrollments")
    op.drop_table("trial_device_enrollments")
    op.drop_index("ix_trial_invitations_user_id", table_name="trial_invitations")
    op.drop_index("ix_trial_invitations_code_digest", table_name="trial_invitations")
    op.drop_table("trial_invitations")
    op.drop_index("ix_trial_credentials_login_id", table_name="trial_credentials")
    op.drop_table("trial_credentials")
    # This intentionally fails if nullable-phone trial users remain. Operators
    # must remove/export candidate-only accounts before schema rollback.
    with op.batch_alter_table("users") as batch:
        batch.alter_column("phone", existing_type=sa.String(20), nullable=False)
