"""Phase 5 Agent MVP: consent / run / tool-event / proposal tables.

Revision ID: 0008_agent_mvp
Revises: 0007_training_plans
Create Date: 2026-07-29

Phase 5 Task 2 (spec ``2026-07-28-agent-mvp.md`` Persistence And State;
ADR-0004): create the four narrowly scoped Agent tables backing immutable
cloud-processing consent events, privacy-minimized run/Tool audit, and the
short-lived typed write-proposal lifecycle.

- ``agent_cloud_consents`` is an append-only event log. The current active
  state is the highest per-user ``sequence_no`` (serialized by the existing
  per-user transaction lock). ``UniqueConstraint(user_id, purpose,
  sequence_no)`` guarantees monotonic sequences with no timestamp-tie
  ambiguity. ``status`` is CHECK-constrained to granted/withdrawn.
- ``agent_runs`` is privacy-minimized run metadata: stable codes/versions, a
  keyed context fingerprint, counts, timing. There is NO column for user text,
  assistant prose, raw context, prompt, or model response. ``UniqueConstraint
  (user_id, client_turn_id)`` makes a duplicate turn return the prior status
  without creating a second proposal.
- ``agent_tool_events`` stores stable Tool metadata/fingerprints/result_ref
  only - never raw arguments or result payload. ``run_id`` cascades on run
  deletion.
- ``agent_action_proposals`` carries the 15-minute owned proposal lifecycle.
  ``status`` is CHECK-constrained to pending/executed/invalidated/expired/
  cancelled. ``arguments_json`` is nullable and scrubbed (NULL) on every
  terminal transition, withdrawal, Agent-data deletion, and lazy expiry; only
  ``pending`` rows retain arguments.

Idempotency is NOT a new table: Phase 5 reuses the existing
``idempotency_records`` table (ADR-0001) with three new ``operation`` values
(``agent_action_confirm``, ``agent_consent_grant``, ``agent_consent_withdraw``).

SQLite/PostgreSQL parity: status CHECK constraints are enforced by both
databases (SQLite always enforces CHECK); every legal transition is also
enforced deterministically in ``app.agent.persistence``, so neither dialect
relies on the other ignoring a constraint. FKs and ownership indexes mirror
the health/posture/training convention. The tables are new in Phase 5, so no
backfill runs. Downgrade drops the four tables in dependency order and never
touches posture/health/training tables or other operations' idempotency rows.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0008_agent_mvp"
down_revision: Union[str, None] = "0007_training_plans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_cloud_consents",
        sa.Column("consent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("provider_id", sa.String(length=60), nullable=False),
        sa.Column("disclosure_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("consent_id"),
        sa.UniqueConstraint(
            "user_id",
            "purpose",
            "sequence_no",
            name="uq_agent_cloud_consents_user_purpose_seq",
        ),
        sa.CheckConstraint(
            "status IN ('granted', 'withdrawn')",
            name="ck_agent_cloud_consents_status",
        ),
    )
    op.create_index(
        "ix_agent_cloud_consents_user",
        "agent_cloud_consents",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "agent_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_turn_id", sa.String(length=64), nullable=False),
        sa.Column("entry_type", sa.String(length=30), nullable=False),
        sa.Column("intent_code", sa.String(length=40), nullable=True),
        sa.Column("context_fingerprint", sa.String(length=64), nullable=True),
        sa.Column(
            "fingerprint_key_version", sa.String(length=40), nullable=True
        ),
        sa.Column("prompt_version", sa.String(length=40), nullable=True),
        sa.Column("provider_id", sa.String(length=60), nullable=True),
        sa.Column("model_version", sa.String(length=60), nullable=True),
        sa.Column("policy_version", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("result_code", sa.String(length=40), nullable=True),
        sa.Column("tool_call_count", sa.Integer(), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("run_id"),
        sa.UniqueConstraint(
            "user_id",
            "client_turn_id",
            name="uq_agent_runs_user_turn",
        ),
    )
    op.create_index(
        "ix_agent_runs_user", "agent_runs", ["user_id"], unique=False
    )
    op.create_index(
        "ix_agent_runs_expires_at", "agent_runs", ["expires_at"], unique=False
    )

    op.create_table(
        "agent_tool_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_name", sa.String(length=60), nullable=False),
        sa.Column("side_effect_class", sa.String(length=20), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
        sa.Column(
            "fingerprint_key_version", sa.String(length=40), nullable=True
        ),
        sa.Column("policy_version", sa.String(length=40), nullable=True),
        sa.Column("context_version", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("result_code", sa.String(length=40), nullable=True),
        sa.Column("result_ref", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["agent_runs.run_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_agent_tool_events_run",
        "agent_tool_events",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_tool_events_user",
        "agent_tool_events",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "agent_action_proposals",
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_name", sa.String(length=60), nullable=False),
        sa.Column("arguments_json", postgresql.JSONB(), nullable=True),
        sa.Column("arguments_hash", sa.String(length=64), nullable=False),
        sa.Column("context_version", sa.String(length=40), nullable=True),
        sa.Column("policy_version", sa.String(length=40), nullable=True),
        sa.Column(
            "fingerprint_key_version", sa.String(length=40), nullable=True
        ),
        sa.Column("context_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_ref", sa.String(length=64), nullable=True),
        sa.Column("result_code", sa.String(length=40), nullable=True),
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
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("proposal_id"),
        sa.CheckConstraint(
            "status IN ('pending', 'executed', 'invalidated', 'expired', 'cancelled')",
            name="ck_agent_action_proposals_status",
        ),
    )
    op.create_index(
        "ix_agent_action_proposals_user_status",
        "agent_action_proposals",
        ["user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_agent_action_proposals_run",
        "agent_action_proposals",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_action_proposals_expires_at",
        "agent_action_proposals",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    # Drop the four Phase 5 tables in reverse dependency order. Never touch
    # posture/health/training tables or other operations' idempotency_records
    # rows. Agent audit/proposal data is recreation-safe (regenerable from
    # deterministic engines / user re-confirmation), so downgrade is a safe
    # recovery path on a disposable / no-Agent-data database.
    op.drop_index(
        "ix_agent_action_proposals_expires_at",
        table_name="agent_action_proposals",
    )
    op.drop_index(
        "ix_agent_action_proposals_run", table_name="agent_action_proposals"
    )
    op.drop_index(
        "ix_agent_action_proposals_user_status",
        table_name="agent_action_proposals",
    )
    op.drop_table("agent_action_proposals")

    op.drop_index("ix_agent_tool_events_user", table_name="agent_tool_events")
    op.drop_index("ix_agent_tool_events_run", table_name="agent_tool_events")
    op.drop_table("agent_tool_events")

    op.drop_index("ix_agent_runs_expires_at", table_name="agent_runs")
    op.drop_index("ix_agent_runs_user", table_name="agent_runs")
    op.drop_table("agent_runs")

    op.drop_index("ix_agent_cloud_consents_user", table_name="agent_cloud_consents")
    op.drop_table("agent_cloud_consents")
