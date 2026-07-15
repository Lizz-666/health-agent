"""posture core schema: rename events table, expand columns, add 6 new tables (expand phase)

Revision ID: 0002
Revises: 0001_initial_schema
Create Date: 2026-07-11

Phase A (expand) of the posture core productization migration
(spec ``2026-07-11-posture-core-productization.md`` §16.1 / plan Task 1):

- Rename ``posture_assessments`` -> ``posture_assessment_events``.
- Add nullable columns to the renamed table. NO NOT NULL tightening is
  performed in this phase; ``severity`` stays **permanently** nullable
  (an empty severity is a legal state meaning "source produced no firm
  severity conclusion"). Existing ``method`` / ``result`` columns are
  kept intact (NOT dropped) for the dual-write phase (Task 2) and later
  cleanup (Task 10.5); this migration backfills ``source`` /
  ``severity`` / ``lifecycle`` from them but leaves them in place so the
  legacy API keeps working (expand mode).
    * source           (String(20), nullable — discriminator: self_test / ai_photo)
    * severity         (String(20), nullable)
    * lifecycle        (String(20), nullable)
    * content_version  (String(20), nullable)
    * ai_model_meta    (JSONB, nullable)

- Create six new tables:
    * posture_profile_entries    (current-state projection per issue)
    * posture_user_goals         (confirmed improvement goals)
    * posture_safety_signals     (structured red-flag / risk input)
    * idempotency_records        (single idempotency mechanism for side-effect tools)
    * posture_purge_tombstones   (un-linkable purge receipt; CHECK: only completed states)
    * purge_operations           (persisted async purge job; user_id nullable FK ON DELETE SET NULL)

Backfill of source/severity/lifecycle and profile projection runs IN
this migration (plan Task 1 steps 2-3): existing legacy rows are
projected into the new columns / profile table conservatively (all
active, risk_tier 'normal', certainty 'confirmed' except where the
combined severity cannot be resolved -- conflict or all-null -- which
yields 'provisional'). The expand-mode schema changes keep the existing
API running unchanged.

Note on ``down_revision``: it points to the real revision id of the
initial schema, ``0001_initial_schema`` (the bare token ``0001`` is not a
registered revision id and would break the migration chain).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tombstone ``object_delete_status`` may ONLY store *completed* states.
# Pending / failed statuses (e.g. ``oss_failed_retry_pending``) are forbidden
# in the tombstone -- they live in ``purge_operations`` instead. See spec §6.6.
TOMBSTONE_OBJECT_DELETE_COMPLETED = (
    "oss_deleted",
    "oss_not_applicable",
    "oss_deleted_or_not_found",
)
_TOMBSTONE_CHECK_VALUES = ", ".join(
    "'{}'".format(v) for v in TOMBSTONE_OBJECT_DELETE_COMPLETED
)


def upgrade() -> None:
    # ---------------------------------------------------------------
    # 1. Rename posture_assessments -> posture_assessment_events
    # ---------------------------------------------------------------
    op.rename_table("posture_assessments", "posture_assessment_events")

    # The pre-existing user_id index was named after the old table; drop it
    # so it can be recreated under the new table name below.
    op.drop_index(
        "ix_posture_assessments_user_id",
        table_name="posture_assessment_events",
    )

    # ---------------------------------------------------------------
    # 2. Expand the renamed table with nullable columns.
    #    NO NOT NULL tightening. severity stays permanently nullable.
    #    Columns MUST be added before the composite index below, which
    #    references the new ``source`` / ``lifecycle`` columns.
    # ---------------------------------------------------------------
    op.add_column(
        "posture_assessment_events",
        sa.Column("source", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "posture_assessment_events",
        sa.Column("severity", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "posture_assessment_events",
        sa.Column("lifecycle", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "posture_assessment_events",
        sa.Column("content_version", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "posture_assessment_events",
        sa.Column("ai_model_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # Recreate the user_id index (new name) plus the spec-required composite
    # indexes, now that the referenced columns exist.
    op.create_index(
        op.f("ix_posture_assessment_events_user_id"),
        "posture_assessment_events",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_posture_assessment_events_user_issue_source_lifecycle",
        "posture_assessment_events",
        ["user_id", "issue_id", "source", "lifecycle"],
        unique=False,
    )
    op.create_index(
        "ix_posture_assessment_events_user_created_at",
        "posture_assessment_events",
        ["user_id", "created_at"],
        unique=False,
    )

    # ---------------------------------------------------------------
    # 3. posture_profile_entries (current-state projection per issue)
    # ---------------------------------------------------------------
    op.create_table(
        "posture_profile_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", sa.String(length=20), nullable=False),
        sa.Column(
            "latest_self_test_event_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "latest_photo_event_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("combined_severity", sa.String(length=20), nullable=True),
        sa.Column("certainty", sa.String(length=20), nullable=False),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("has_conflict", sa.Boolean(), nullable=False),
        sa.Column("risk_tier", sa.String(length=20), nullable=False),
        sa.Column("risk_version", sa.String(length=30), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["latest_self_test_event_id"],
            ["posture_assessment_events.id"],
        ),
        sa.ForeignKeyConstraint(
            ["latest_photo_event_id"],
            ["posture_assessment_events.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "issue_id",
            name="uq_posture_profile_entries_user_issue",
        ),
    )
    op.create_index(
        op.f("ix_posture_profile_entries_user_id"),
        "posture_profile_entries",
        ["user_id"],
        unique=False,
    )

    # ---------------------------------------------------------------
    # 4. posture_user_goals (confirmed improvement goals)
    # ---------------------------------------------------------------
    op.create_table(
        "posture_user_goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", sa.String(length=20), nullable=False),
        sa.Column("priority_rank", sa.Integer(), nullable=False),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("suggestion_id", sa.String(length=64), nullable=False),
        sa.Column("profile_version", sa.String(length=64), nullable=False),
        sa.Column("rule_version", sa.String(length=30), nullable=False),
        sa.Column("risk_version", sa.String(length=30), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_posture_user_goals_user_id"),
        "posture_user_goals",
        ["user_id"],
        unique=False,
    )

    # ---------------------------------------------------------------
    # 5. posture_safety_signals (structured red-flag / risk input)
    # ---------------------------------------------------------------
    op.create_table(
        "posture_safety_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_type", sa.String(length=30), nullable=False),
        sa.Column("body_region", sa.String(length=30), nullable=True),
        sa.Column("related_issue_id", sa.String(length=20), nullable=True),
        sa.Column("severity_hint", sa.String(length=20), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lifecycle", sa.String(length=20), nullable=False),
        sa.Column(
            "invalidates_until",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_basis", sa.String(length=30), nullable=True),
        sa.Column(
            "resolution_source",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "resolved_risk_version", sa.String(length=30), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_posture_safety_signals_user_reported",
        "posture_safety_signals",
        ["user_id", "reported_at"],
        unique=False,
    )
    op.create_index(
        "ix_posture_safety_signals_user_lifecycle",
        "posture_safety_signals",
        ["user_id", "lifecycle"],
        unique=False,
    )

    # ---------------------------------------------------------------
    # 6. idempotency_records (single idempotency mechanism for side-effect tools)
    # ---------------------------------------------------------------
    op.create_table(
        "idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("result_ref", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "operation",
            "idempotency_key",
            name="uq_idempotency_records_user_op_key",
        ),
    )
    op.create_index(
        "ix_idempotency_records_expires_at",
        "idempotency_records",
        ["expires_at"],
        unique=False,
    )

    # ---------------------------------------------------------------
    # 7. posture_purge_tombstones (un-linkable purge receipt)
    #    object_delete_status ONLY accepts completed states (CHECK).
    #    No user_id / issue_id / event_id / health payload is stored here
    #    (spec §6.6).
    # ---------------------------------------------------------------
    op.create_table(
        "posture_purge_tombstones",
        sa.Column("receipt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purge_reason", sa.String(length=30), nullable=False),
        sa.Column("policy_version", sa.String(length=40), nullable=False),
        sa.Column(
            "object_delete_status", sa.String(length=30), nullable=False
        ),
        sa.CheckConstraint(
            "object_delete_status IN ({values})".format(values=_TOMBSTONE_CHECK_VALUES),
            name="ck_posture_purge_tombstones_object_delete_status_completed",
        ),
        sa.PrimaryKeyConstraint("receipt_id"),
    )
    op.create_index(
        "ix_posture_purge_tombstones_deleted_at",
        "posture_purge_tombstones",
        ["deleted_at"],
        unique=False,
    )

    # ---------------------------------------------------------------
    # 8. purge_operations (persisted async purge job)
    #    user_id is a NULLABLE FK with ON DELETE SET NULL so that account
    #    deletion is never blocked by a NOT NULL FK (spec §6.7.3).
    # ---------------------------------------------------------------
    op.create_table(
        "purge_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trigger", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "encrypted_object_keys", postgresql.BYTEA(), nullable=True
        ),
        sa.Column(
            "target_event_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "target_signal_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_purge_operations_status_next_retry_at",
        "purge_operations",
        ["status", "next_retry_at"],
        unique=False,
    )

    # ---------------------------------------------------------------
    # 9. Backfill expanded columns + profile projection (spec §16.1
    #    Phase A, plan Task 1 steps 2-3). Conservative: every legacy
    #    row becomes an active event; the profile projection honours
    #    the null-severity rule (uncertain -> null / source conflict ->
    #    combined null) so certainty is 'provisional' wherever the
    #    combined severity cannot be resolved.
    # ---------------------------------------------------------------
    # 9a. Event columns: source from method, severity from result
    #     (uncertain -> NULL), lifecycle defaults to 'active'.
    op.execute(
        """
        UPDATE posture_assessment_events
        SET source = method,
            severity = CASE WHEN result = 'uncertain' THEN NULL ELSE result END,
            lifecycle = 'active'
        """
    )

    # 9b. posture_profile_entries: one row per (user_id, issue_id),
    #     projected from the LATEST active event PER SOURCE. A window CTE
    #     (ROW_NUMBER() OVER PARTITION BY user_id, issue_id, source ORDER
    #     BY created_at DESC, id DESC) picks exactly one row per source,
    #     so same-source older history never participates (spec §8.5).
    #
    #     Combination is NULL-aware: COUNT(*) FILTER (WHERE severity IS
    #     NULL) counts nulls explicitly, so a (null + moderate) pair is
    #     treated as provisional/combined-null, NOT as confirmed/moderate
    #     (which COUNT(DISTINCT severity) alone would wrongly imply).
    #     combined_severity / certainty are NULL on single-null,
    #     multi-any-null, or non-null disagreement (conflict). Confirmed
    #     only when every latest severity is non-null and they agree
    #     (distinct_non_null = 1). The sources array holds ONLY the
    #     multi-any-null, or non-null disagreement (conflict). Certainty is
    #     confirmed only when every latest severity is non-null and they agree;
    #     non-null disagreement is explicit conflict, not provisional. The
    #     sources array holds ONLY the latest-per-source rows. See spec §6.4
    #     / §8.5.
    op.execute(
        """
        WITH ranked_events AS (
            SELECT
                id, user_id, issue_id, source, severity, created_at,
                ROW_NUMBER() OVER (
                    PARTITION BY user_id, issue_id, source
                    ORDER BY created_at DESC, id DESC
                ) AS rn
            FROM posture_assessment_events
            WHERE lifecycle = 'active'
        ),
        latest_per_source AS (
            SELECT * FROM ranked_events WHERE rn = 1
        ),
        profile_groups AS (
            SELECT
                user_id,
                issue_id,
                COUNT(*)                                   AS src_cnt,
                COUNT(*) FILTER (WHERE severity IS NULL)   AS null_cnt,
                COUNT(DISTINCT severity)                   AS distinct_non_null,
                MIN(severity)                              AS min_sev
            FROM latest_per_source
            GROUP BY user_id, issue_id
        )
        INSERT INTO posture_profile_entries (
            id, user_id, issue_id,
            latest_self_test_event_id, latest_photo_event_id,
            combined_severity, certainty, sources, has_conflict,
            risk_tier, risk_version, updated_at
        )
        SELECT
            gen_random_uuid(),
            g.user_id,
            g.issue_id,
            (SELECT l.id FROM latest_per_source l
               WHERE l.user_id = g.user_id AND l.issue_id = g.issue_id
                 AND l.source = 'self_test'),
            (SELECT l.id FROM latest_per_source l
               WHERE l.user_id = g.user_id AND l.issue_id = g.issue_id
                 AND l.source = 'ai_photo'),
            CASE
                WHEN g.src_cnt = 1 AND g.null_cnt = 0
                     THEN g.min_sev                              -- single source, non-null
                WHEN g.src_cnt > 1 AND g.null_cnt = 0
                     AND g.distinct_non_null = 1
                     THEN g.min_sev                              -- multi, all non-null equal
                ELSE NULL                                        -- single-null / multi-any-null / conflict
            END AS combined_severity,
            CASE
                WHEN g.src_cnt = 1 AND g.null_cnt = 0
                     THEN 'confirmed'                            -- single source, non-null
                WHEN g.src_cnt > 1 AND g.null_cnt = 0
                     AND g.distinct_non_null = 1
                      THEN 'confirmed'                            -- multi, all non-null equal
                WHEN g.src_cnt > 1 AND g.null_cnt = 0
                     AND g.distinct_non_null >= 2
                      THEN 'conflict'                              -- multi, non-null disagreement
                ELSE 'provisional'                               -- single-null / multi-any-null
            END AS certainty,
            COALESCE(
                (SELECT jsonb_agg(jsonb_build_object(
                    'source', l.source, 'event_id', l.id,
                    'severity', l.severity, 'created_at', l.created_at
                 ) ORDER BY l.created_at DESC, l.id DESC)
                 FROM latest_per_source l
                 WHERE l.user_id = g.user_id AND l.issue_id = g.issue_id),
                '[]'::jsonb
            ) AS sources,
            (g.src_cnt > 1 AND g.null_cnt = 0 AND g.distinct_non_null >= 2)
                AS has_conflict,
            'normal', 'phase1-initial-v1', now()
        FROM profile_groups g
        """
    )


def downgrade() -> None:
    # Reverse order of upgrade: drop new tables/indexes, drop new columns,
    # restore the original user_id index name, then rename the table back.

    # --- purge_operations ---
    op.drop_index(
        "ix_purge_operations_status_next_retry_at",
        table_name="purge_operations",
    )
    op.drop_table("purge_operations")

    # --- posture_purge_tombstones ---
    op.drop_index(
        "ix_posture_purge_tombstones_deleted_at",
        table_name="posture_purge_tombstones",
    )
    op.drop_table("posture_purge_tombstones")

    # --- idempotency_records ---
    op.drop_index(
        "ix_idempotency_records_expires_at",
        table_name="idempotency_records",
    )
    op.drop_table("idempotency_records")

    # --- posture_safety_signals ---
    op.drop_index(
        "ix_posture_safety_signals_user_lifecycle",
        table_name="posture_safety_signals",
    )
    op.drop_index(
        "ix_posture_safety_signals_user_reported",
        table_name="posture_safety_signals",
    )
    op.drop_table("posture_safety_signals")

    # --- posture_user_goals ---
    op.drop_index(
        op.f("ix_posture_user_goals_user_id"),
        table_name="posture_user_goals",
    )
    op.drop_table("posture_user_goals")

    # --- posture_profile_entries ---
    op.drop_index(
        op.f("ix_posture_profile_entries_user_id"),
        table_name="posture_profile_entries",
    )
    op.drop_table("posture_profile_entries")

    # Drop the new indexes BEFORE dropping columns: PostgreSQL automatically
    # drops any index that references a dropped column, so dropping columns
    # first would make the explicit DROP INDEX statements below fail.
    op.drop_index(
        "ix_posture_assessment_events_user_created_at",
        table_name="posture_assessment_events",
    )
    op.drop_index(
        "ix_posture_assessment_events_user_issue_source_lifecycle",
        table_name="posture_assessment_events",
    )
    op.drop_index(
        op.f("ix_posture_assessment_events_user_id"),
        table_name="posture_assessment_events",
    )

    # --- drop expanded columns on assessment events ---
    op.drop_column("posture_assessment_events", "ai_model_meta")
    op.drop_column("posture_assessment_events", "content_version")
    op.drop_column("posture_assessment_events", "lifecycle")
    op.drop_column("posture_assessment_events", "severity")
    op.drop_column("posture_assessment_events", "source")

    # --- restore original index name & table name ---
    op.create_index(
        "ix_posture_assessments_user_id",
        "posture_assessment_events",
        ["user_id"],
        unique=False,
    )
    op.rename_table("posture_assessment_events", "posture_assessments")
