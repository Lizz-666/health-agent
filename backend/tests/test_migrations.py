"""Alembic migration contract tests.

关键设计：
``tests/conftest.py`` 在 import 时会 monkey-patch
``sqlalchemy.dialects.postgresql.UUID`` / ``JSONB`` 为 SQLite 兼容类型。
一旦 pytest 收集了 conftest，这些补丁在整个进程内生效。

因此本文件通过 **子进程** 调用 ``python -m alembic ... --sql`` 生成 SQL：
子进程是全新解释器，不 import 测试 conftest，PostgreSQL 方言类型保持原样。
在进程内我们只检查子进程输出文本和 ``Base.metadata`` 表名/列属性，
绝不在被 patch 的进程里渲染 PostgreSQL 类型。
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

# backend/ 目录（alembic.ini 所在处，子进程的工作目录）。
BACKEND_DIR = Path(__file__).resolve().parent.parent


DEFAULT_DB_URL = "postgresql+asyncpg://user:password@localhost:5432/posture_app"


def _run_alembic(
    *args: str, database_url: str = DEFAULT_DB_URL
) -> subprocess.CompletedProcess:
    """在 backend 目录下、以全新解释器运行 alembic。

    不继承 pytest 的已加载模块，因此不受 conftest 的 SQLite monkey patch 影响。
    ``database_url`` 默认使用确定的 PostgreSQL 方言 URL（离线渲染不需要真实连接/驱动）。
    """
    env = dict(os.environ)
    env["DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )


def _offline_upgrade_sql() -> str:
    proc = _run_alembic("upgrade", "head", "--sql")
    assert proc.returncode == 0, f"alembic upgrade --sql failed:\n{proc.stderr}"
    return proc.stdout


def _offline_downgrade_sql() -> str:
    proc = _run_alembic("downgrade", "head:base", "--sql")
    assert proc.returncode == 0, f"alembic downgrade --sql failed:\n{proc.stderr}"
    return proc.stdout


# 全部表名（重命名后的 events 表 + 6 个新表 + 平台表 + Phase 2 health_profiles
# + Phase 2 health_checkins + Phase 2 weight_records + Phase 4 training tables）。
ALL_TABLES = {
    "users",
    "verification_codes",
    "posture_assessment_events",
    "posture_profile_entries",
    "posture_user_goals",
    "posture_safety_signals",
    "idempotency_records",
    "posture_purge_tombstones",
    "purge_operations",
    "health_profiles",
    "health_checkins",
    "weight_records",
    # Phase 4 four-week training plan MVP (migration 0007).
    "training_plan_versions",
    "training_sessions",
    "training_prescriptions",
    "training_session_feedback",
    "training_session_substitutions",
    # Phase 5 Agent MVP (migration 0008).
    "agent_cloud_consents",
    "agent_runs",
    "agent_tool_events",
    "agent_action_proposals",
    # Phase 6 nutrition recommendation versions (migration 0010).
    "nutrition_recommendations",
    # Phase 7 adaptive execution/review foundations (migration 0011).
    "training_day_adjustments",
    "training_day_adjustment_items",
    "training_weekly_reviews",
    "posture_recheck_dismissals",
}

# Phase 1 expand 阶段新增的 6 张表。
NEW_TABLES = {
    "posture_profile_entries",
    "posture_user_goals",
    "posture_safety_signals",
    "idempotency_records",
    "posture_purge_tombstones",
    "purge_operations",
}


# ---------------------------------------------------------------------------
# head / 离线渲染基础
# ---------------------------------------------------------------------------


def test_single_head():
    """Alembic 只有一个 head，且为 0011_adaptive_reviews。"""
    proc = _run_alembic("heads")
    assert proc.returncode == 0, proc.stderr
    head_lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(head_lines) == 1, f"expected exactly one head, got: {head_lines}"
    assert head_lines[0].split()[0] == "0011_adaptive_reviews", head_lines[0]


def test_head_chains_to_initial_schema():
    """0003_posture_contract -> 0002 -> 0001_initial_schema（链路完整）。"""
    proc = _run_alembic("history")
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "0004_health_profile_tracking" in out
    assert "0003_posture_contract" in out
    assert "0002" in out
    assert "0001_initial_schema" in out


def test_offline_upgrade_sql_generates():
    """upgrade SQL 可以按 PostgreSQL 方言离线生成。"""
    sql = _offline_upgrade_sql()
    assert sql.strip(), "upgrade SQL is empty"


def test_offline_downgrade_sql_generates():
    """downgrade SQL 可以离线生成。"""
    sql = _offline_downgrade_sql()
    assert sql.strip(), "downgrade SQL is empty"


# ---------------------------------------------------------------------------
# 表 / 索引 / 外键（离线 SQL）
# ---------------------------------------------------------------------------


def test_upgrade_sql_contains_all_tables():
    """upgrade SQL 覆盖所有表（events 由 rename 产生，其余由 CREATE TABLE）。"""
    sql = _offline_upgrade_sql()

    # 6 张新表 + users/verification_codes 直接 CREATE TABLE。
    for table in NEW_TABLES | {"users", "verification_codes"}:
        assert f"CREATE TABLE {table}" in sql, f"missing CREATE TABLE {table}"

    # posture_assessment_events 由 posture_assessments 重命名产生。
    assert "CREATE TABLE posture_assessments" in sql  # 来自 0001
    assert (
        "ALTER TABLE posture_assessments RENAME TO posture_assessment_events"
        in sql
    ), "missing rename to posture_assessment_events"


def test_upgrade_sql_contains_indexes_and_fk():
    """关键索引与外键存在于离线 SQL。"""
    sql = _offline_upgrade_sql()

    # 平台表索引（不变）。
    assert "CREATE UNIQUE INDEX ix_users_phone ON users (phone)" in sql
    assert (
        "CREATE INDEX ix_verification_codes_phone ON verification_codes (phone)"
        in sql
    )

    # 重命名后 events 表的 user_id 索引（新名字）。
    assert (
        "CREATE INDEX ix_posture_assessment_events_user_id "
        "ON posture_assessment_events (user_id)" in sql
    )
    assert "CREATE UNIQUE INDEX ix_posture_assessment_events_user_id" not in sql

    # 旧索引名在 0002 中被删除（round-trip 一致性）。
    assert "DROP INDEX ix_posture_assessments_user_id" in sql

    # 关键外键：events.user_id -> users.id（来自 0001，rename 后保留）。
    assert "FOREIGN KEY(user_id) REFERENCES users (id)" in sql

    # PostgreSQL 专有类型（证明未走 SQLite monkey patch）。
    assert "UUID" in sql
    assert "JSONB" in sql


def test_upgrade_sql_six_new_tables_present():
    """Phase 1 expand 新增的 6 张表全部存在。"""
    sql = _offline_upgrade_sql()
    for table in NEW_TABLES:
        assert f"CREATE TABLE {table}" in sql, f"missing new table {table}"


def test_downgrade_sql_drops_all_tables_reverse_order():
    """downgrade 反序删除全部 9 张表，并恢复 rename。"""
    sql = _offline_downgrade_sql()

    # 6 张新表先被删除。
    for table in NEW_TABLES:
        assert f"DROP TABLE {table}" in sql, f"missing DROP TABLE {table}"

    # rename 被还原：events -> assessments。
    assert (
        "ALTER TABLE posture_assessment_events RENAME TO posture_assessments"
        in sql
    ), "missing rename back to posture_assessments"

    # 0001 的 downgrade 删除原始 3 表。
    for table in ("posture_assessments", "verification_codes", "users"):
        assert f"DROP TABLE {table}" in sql, f"missing DROP TABLE {table}"

    # 依赖反序：子表先于父表。
    # 新表先于 posture_assessments（0002 downgrade 先于 0001 downgrade）。
    assert sql.index("DROP TABLE posture_profile_entries") < sql.index(
        "DROP TABLE posture_assessments"
    )
    assert sql.index("DROP TABLE posture_assessments") < sql.index("DROP TABLE users")

    # 旧索引名在 downgrade 末尾被恢复。
    assert "CREATE INDEX ix_posture_assessments_user_id" in sql


def test_downgrade_drops_new_columns_and_restores_rename():
    """downgrade 删除 expand 阶段新增列并恢复 rename 与旧索引名。"""
    sql = _offline_downgrade_sql()
    for col in ("source", "severity", "lifecycle", "content_version", "ai_model_meta"):
        assert f"DROP COLUMN {col}" in sql, f"missing DROP COLUMN {col}"


# ---------------------------------------------------------------------------
# metadata 一致性（进程内读取属性，不渲染 PG 类型）
# ---------------------------------------------------------------------------


def test_migration_tables_match_base_metadata():
    """migration 表集合与 Base.metadata 表集合一致。"""
    from app.db.base import Base
    import app.auth.models  # noqa: F401
    import app.posture.models  # noqa: F401
    import app.health.models  # noqa: F401
    import app.training.models  # noqa: F401
    import app.agent.models  # noqa: F401
    import app.nutrition.models  # noqa: F401

    metadata_tables = set(Base.metadata.tables.keys())
    assert metadata_tables == ALL_TABLES

    sql = _offline_upgrade_sql()
    # 直接 CREATE TABLE 的表。
    created = {t for t in metadata_tables if f"CREATE TABLE {t}" in sql}
    # events 表由 rename 产生。
    renamed_ok = (
        "CREATE TABLE posture_assessments" in sql
        and "ALTER TABLE posture_assessments RENAME TO posture_assessment_events"
        in sql
    )
    assert created | (
        {"posture_assessment_events"} if renamed_ok else set()
    ) == metadata_tables


def test_alembic_env_imports_health_models():
    """Alembic target metadata must include Phase 2 health models."""
    env_text = (BACKEND_DIR / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "import app.health.models" in env_text


def test_alembic_env_imports_agent_models():
    """Alembic target metadata must include Phase 5 Agent models."""
    env_text = (BACKEND_DIR / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "import app.agent.models" in env_text


def test_assessment_event_columns_nullable_in_metadata():
    """0003 收紧 source/lifecycle 为 NOT NULL；severity 永久 nullable；method/result 已删除。"""
    from app.db.base import Base
    import app.auth.models  # noqa: F401
    import app.posture.models  # noqa: F401

    events = Base.metadata.tables["posture_assessment_events"]

    # source and lifecycle are NOT nullable after 0003 contract migration.
    for col in ("source", "lifecycle"):
        assert events.c[col].nullable is False, f"{col} must be NOT NULL after 0003"

    # severity remains permanently nullable.
    assert events.c["severity"].nullable is True, "severity must remain nullable"

    # content_version and ai_model_meta remain nullable.
    for col in ("content_version", "ai_model_meta"):
        assert events.c[col].nullable is True, f"{col} must be nullable"

    # method and result columns should NOT exist anymore after 0003.
    col_names = set(events.c.keys())
    assert "method" not in col_names, "method column must not exist after 0003"
    assert "result" not in col_names, "result column must not exist after 0003"

    # Remaining old columns stay NOT NULL.
    for col in ("issue_id", "user_id"):
        assert events.c[col].nullable is False, f"{col} should remain NOT NULL"


def test_assessment_event_columns_nullable_in_offline_sql():
    """新增列在离线 SQL 中不带 NOT NULL。"""
    sql = _offline_upgrade_sql()
    # severity 是永久 nullable 的代表；绝不能出现 NOT NULL。
    assert "severity VARCHAR(20) NOT NULL" not in sql
    assert "severity VARCHAR(20)" in sql
    # source 为 VARCHAR(20) 判别列（self_test/ai_photo），ai_model_meta 为 JSONB；均 nullable。
    assert "ADD COLUMN source VARCHAR(20)" in sql
    assert "source VARCHAR(20) NOT NULL" not in sql
    assert "ADD COLUMN ai_model_meta JSONB" in sql
    assert "ai_model_meta JSONB NOT NULL" not in sql


def test_assessment_alias_points_to_renamed_table():
    """PostureAssessment 别名指向重命名后的 events 模型（service.py 兼容契约）。"""
    from app.posture.models import (
        PostureAssessment,
        PostureAssessmentEvent,
    )

    assert PostureAssessment is PostureAssessmentEvent
    assert PostureAssessment.__tablename__ == "posture_assessment_events"


# ---------------------------------------------------------------------------
# purge_operations: user_id nullable + ON DELETE SET NULL
# ---------------------------------------------------------------------------


def test_purge_operations_user_id_nullable_in_metadata():
    """purge_operations.user_id 必须为 nullable FK。"""
    from app.db.base import Base
    import app.auth.models  # noqa: F401
    import app.posture.models  # noqa: F401

    purge = Base.metadata.tables["purge_operations"]
    assert purge.c.user_id.nullable is True, "purge_operations.user_id must be nullable"


def test_purge_operations_user_id_on_delete_set_null_in_sql():
    """purge_operations.user_id 外键带 ON DELETE SET NULL。"""
    sql = _offline_upgrade_sql()
    assert (
        "FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL" in sql
    ), "purge_operations.user_id FK must be ON DELETE SET NULL"


# ---------------------------------------------------------------------------
# tombstone: object_delete_status 仅完成态（CHECK）
# ---------------------------------------------------------------------------


_TOMBSTONE_COMPLETED = (
    "oss_deleted",
    "oss_not_applicable",
    "oss_deleted_or_not_found",
)


def test_tombstone_check_constraint_in_sql():
    """posture_purge_tombstones 含 CHECK：object_delete_status 仅完成态。"""
    sql = _offline_upgrade_sql()
    assert (
        "ck_posture_purge_tombstones_object_delete_status_completed" in sql
    ), "missing tombstone CHECK constraint name"
    for value in _TOMBSTONE_COMPLETED:
        assert "'{}'".format(value) in sql, f"missing completed value {value} in CHECK"


def test_tombstone_check_excludes_pending_failed():
    """CHECK 不允许 pending/failed 状态。"""
    sql = _offline_upgrade_sql()
    # 找到 tombstone 的 CHECK 子句文本。
    check_marker = "object_delete_status IN ("
    idx = sql.find(check_marker)
    assert idx != -1, "tombstone CHECK not found"
    # 截取 CHECK 子句片段（到下一个右括号）。
    fragment = sql[idx : sql.find(")", idx) + 1]
    for forbidden in ("pending", "failed", "oss_failed_retry_pending"):
        assert forbidden not in fragment, (
            f"forbidden status '{forbidden}' must not be allowed by tombstone CHECK"
        )


def test_tombstone_has_no_linkable_columns():
    """tombstone 表不得含 user_id / issue_id / event_id / 健康载荷列。"""
    from app.db.base import Base
    import app.auth.models  # noqa: F401
    import app.posture.models  # noqa: F401

    tomb = Base.metadata.tables["posture_purge_tombstones"]
    cols = set(tomb.c.keys())
    assert cols == {
        "receipt_id",
        "deleted_at",
        "purge_reason",
        "policy_version",
        "object_delete_status",
    }
    for forbidden in ("user_id", "issue_id", "event_id", "source"):
        assert forbidden not in cols, f"tombstone must not carry {forbidden}"


# ---------------------------------------------------------------------------
# 其它原有不变性
# ---------------------------------------------------------------------------


def test_offline_sql_independent_of_conftest_sqlite_patch():
    """migration 文件不依赖测试 conftest 的 SQLite monkey patch。"""
    sql = _offline_upgrade_sql()
    assert "UUID" in sql
    assert "JSONB" in sql
    assert "CHAR(36)" not in sql
    assert " JSON," not in sql and " JSON\n" not in sql


def test_env_does_not_leak_password_in_offline_output():
    """离线输出不包含数据库密码。"""
    sql = _offline_upgrade_sql()
    assert "password" not in sql.lower()


# --- URL 百分号转义回归 ---


def test_url_with_percent_escaped_password_succeeds():
    """DATABASE_URL 含百分号编码密码 (p%25%40ss) 时 alembic 仍成功且不泄露密码。"""
    percent_url = "postgresql+asyncpg://user:p%25%40ss@localhost:5432/posture_app"
    proc = _run_alembic("upgrade", "head", "--sql", database_url=percent_url)

    assert proc.returncode == 0, (
        f"alembic upgrade --sql failed with percent-encoded password:\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )

    combined = (proc.stdout + "\n" + proc.stderr).lower()
    for secret in ("password", "p%25%40ss", "p@ss", "p%40ss"):
        assert secret.lower() not in combined, f"leaked secret fragment: {secret}"

    assert "CREATE TABLE users" in proc.stdout


# --- users.phone schema 一致性 ---


def test_users_phone_unique_index_only():
    """upgrade SQL 对 users.phone 只创建一次唯一索引，且无 UNIQUE (phone) 约束。"""
    sql = _offline_upgrade_sql()
    assert sql.count("CREATE UNIQUE INDEX ix_users_phone") == 1
    assert "UNIQUE (phone)" not in sql


def test_orm_users_has_no_unique_constraint():
    """ORM users 表只有主键约束，phone 唯一性由唯一索引提供。"""
    from sqlalchemy import PrimaryKeyConstraint, UniqueConstraint
    from app.db.base import Base
    import app.auth.models  # noqa: F401
    import app.posture.models  # noqa: F401

    users = Base.metadata.tables["users"]

    constraint_types = {type(c) for c in users.constraints}
    assert PrimaryKeyConstraint in constraint_types
    assert UniqueConstraint not in constraint_types

    indexes = list(users.indexes)
    assert len(indexes) == 1
    idx = indexes[0]
    assert idx.name == "ix_users_phone"
    assert idx.unique is True


def test_new_models_unique_constraints():
    """新表的唯一约束按规格定义。"""
    from sqlalchemy import UniqueConstraint
    from app.db.base import Base
    import app.auth.models  # noqa: F401
    import app.posture.models  # noqa: F401

    def uniq_cols(table_name):
        t = Base.metadata.tables[table_name]
        return {
            tuple(c.name for c in uc.columns)
            for uc in t.constraints
            if isinstance(uc, UniqueConstraint)
        }

    assert ("user_id", "issue_id") in uniq_cols("posture_profile_entries")
    assert ("user_id", "operation", "idempotency_key") in uniq_cols(
        "idempotency_records"
    )


# --- 索引集合一致性：metadata vs offline SQL（防 SQLite/PG 漂移） ---


def test_metadata_indexes_match_offline_sql():
    """Base.metadata 的索引名 + 唯一约束名集合与 offline upgrade SQL 完全一致。

    migration 用 ``op.create_index`` / ``sa.UniqueConstraint`` 定义权威索引集；
    models.py 的 ``index=True`` / ``Index(...)`` / ``UniqueConstraint(...)``
    必须产生完全相同的集合，否则 SQLite ``create_all`` 测试 schema 与真实 PG
    迁移结果会漂移。仅比较领域相关表（posture + Phase 2 health；不含
    users/verification_codes/alembic_version，它们由 0001 定义且已有专门
    测试覆盖）。
    """
    import re

    from sqlalchemy import UniqueConstraint

    from app.db.base import Base
    import app.auth.models  # noqa: F401
    import app.posture.models  # noqa: F401
    import app.health.models  # noqa: F401
    import app.training.models  # noqa: F401
    import app.agent.models  # noqa: F401

    domain_tables = {
        "posture_assessment_events",
        "posture_profile_entries",
        "posture_user_goals",
        "posture_safety_signals",
        "idempotency_records",
        "posture_purge_tombstones",
        "purge_operations",
        "health_profiles",
        "health_checkins",
        "weight_records",
        # Phase 4 training tables (migration 0007).
        "training_plan_versions",
        "training_sessions",
        "training_prescriptions",
        "training_session_feedback",
        "training_session_substitutions",
        # Phase 5 Agent tables (migration 0008).
        "agent_cloud_consents",
        "agent_runs",
        "agent_tool_events",
        "agent_action_proposals",
        # Phase 6 nutrition recommendation versions (migration 0010).
        "nutrition_recommendations",
        # Phase 7 adaptive execution/review foundations (migration 0011).
        "training_day_adjustments",
        "training_day_adjustment_items",
        "training_weekly_reviews",
        "posture_recheck_dismissals",
    }

    # Indexes that exist ONLY in the migration SQL, by design (ADR-0002): the
    # "at most one active plan per user" partial UNIQUE index is materialized in
    # migration 0007 on PostgreSQL. It is intentionally NOT declared on the
    # model, because SQLAlchemy's ``postgresql_where`` is silently dropped by
    # ``create_all`` on SQLite while keeping ``unique=True`` (which would wrongly
    # enforce UNIQUE(user_id) for ALL rows on the SQLite test DB). persistence.py
    # enforces the invariant at the application level; a ``requires_pg`` test
    # proves the DB-level guarantee where the migration actually runs.
    SQL_ONLY_INDEXES = {"uq_training_plan_versions_one_active"}

    # 1. Base.metadata 中的索引名 + 命名 UNIQUE 约束名。
    metadata_names = set()
    for tname in domain_tables:
        table = Base.metadata.tables[tname]
        for idx in table.indexes:
            assert idx.name, f"index on {tname} has no name"
            metadata_names.add(idx.name)
        for cons in table.constraints:
            if isinstance(cons, UniqueConstraint) and cons.name:
                metadata_names.add(cons.name)

    # 2. offline upgrade SQL 中的 CREATE [UNIQUE] INDEX 名（限定领域表）
    #    + 命名 UNIQUE 约束名（全 SQL 中 posture 两表、health_profiles 与
    #    health_checkins 表声明了命名 UNIQUE，均纳入比较）。
    sql = _offline_upgrade_sql()
    sql_names = set()
    for m in re.finditer(r"CREATE (?:UNIQUE )?INDEX (\w+) ON (\w+)", sql):
        if m.group(2) in domain_tables:
            sql_names.add(m.group(1))
    for m in re.finditer(r"CONSTRAINT (\w+) UNIQUE \(", sql):
        sql_names.add(m.group(1))

    metadata_only = metadata_names - sql_names
    sql_only = sql_names - metadata_names
    assert metadata_only == set(), (
        "index/unique-constraint drift: names in metadata but not in SQL: "
        f"{sorted(metadata_only)}"
    )
    assert sql_only == SQL_ONLY_INDEXES, (
        "index/unique-constraint drift between Base.metadata and migration SQL:\n"
        f"  only in metadata: {sorted(metadata_only)}\n"
        f"  only in migration SQL (expected only {sorted(SQL_ONLY_INDEXES)}): "
        f"{sorted(sql_only)}"
    )


# ---------------------------------------------------------------------------
# profile backfill projection regression (review blockers fix)
#
# Two bugs were fixed in migration 0002's posture_profile_entries backfill:
#   1. ``COUNT(DISTINCT severity)`` is NULL-blind in PostgreSQL, so a
#      (null + moderate) pair was misjudged as confirmed/moderate. The fix
#      counts nulls explicitly via ``FILTER (WHERE severity IS NULL)``.
#   2. The old query aggregated ALL active history per (user_id, issue_id)
#      instead of only the LATEST active event PER SOURCE. The fix uses a
#      ``ROW_NUMBER() OVER (PARTITION BY ...)`` window CTE so same-source
#      older rows never participate.
# These tests pin the fixed SQL shape and guard against regression.
# ---------------------------------------------------------------------------

# Substrings that MUST be present in the fixed upgrade SQL.
_PROFILE_BACKFILL_PRESENT_NEEDLES = (
    "ROW_NUMBER()",                       # latest-per-source window function
    "PARTITION BY",                       # partition by (user, issue, source)
    "FILTER (WHERE severity IS NULL)",    # explicit null-aware severity count
    "ranked_events",                      # the window CTE
    "latest_per_source",                  # the rn = 1 projection
    "null_cnt",                           # null count consumed by certainty/combined
)


@pytest.mark.parametrize("needle", _PROFILE_BACKFILL_PRESENT_NEEDLES)
def test_profile_backfill_uses_latest_per_source_and_null_aware(needle):
    """Fixed backfill: latest-per-source window + null-aware combination."""
    sql = _offline_upgrade_sql()
    assert needle in sql, (
        f"profile backfill regression: expected {needle!r} in upgrade SQL"
    )


# Substrings that MUST NOT appear (the old broken logic).
_PROFILE_BACKFILL_ABSENT_SUBSTRINGS = (
    # Old logic grouped over ALL active history with the legacy alias and
    # judged certainty by COUNT(DISTINCT severity) alone (NULL-blind).
    "GROUP BY pae.user_id, pae.issue_id",
    "WHEN COUNT(DISTINCT pae.severity) = 1 THEN 'confirmed'",
)


@pytest.mark.parametrize("forbidden", _PROFILE_BACKFILL_ABSENT_SUBSTRINGS)
def test_profile_backfill_broken_logic_is_gone(forbidden):
    """Old NULL-blind / all-history backfill logic must no longer render."""
    sql = _offline_upgrade_sql()
    assert forbidden not in sql, (
        f"profile backfill regression: forbidden old logic {forbidden!r} "
        f"is still present in upgrade SQL"
    )


def test_profile_backfill_certainty_references_null_count():
    """certainty must NOT be decided by COUNT(DISTINCT severity) alone.

    The certainty CASE must reference the null count (null_cnt) or a NULL
    severity filter, so that a (null + moderate) pair resolves to
    'provisional' rather than being misjudged as 'confirmed'.
    """
    sql = _offline_upgrade_sql()
    idx = sql.lower().find("as certainty")
    assert idx != -1, "could not locate 'AS certainty' in upgrade SQL"
    # Inspect the CASE expression preceding 'AS certainty'.
    region = sql[max(0, idx - 600):idx]
    assert ("null_cnt" in region) or ("severity is null" in region.lower()), (
        "certainty CASE must reference the null count / a NULL severity "
        "filter, not DISTINCT severity alone"
    )


def test_profile_backfill_conflict_sets_certainty_conflict():
    """Non-null source disagreement must become certainty='conflict'.

    A prior review fix set has_conflict=true but still left certainty as
    'provisional' for mild+moderate. Downstream priority/UI logic routes
    conflict and provisional differently, so the migration must pin both.
    """
    sql = _offline_upgrade_sql()
    idx = sql.lower().find("as certainty")
    assert idx != -1, "could not locate 'AS certainty' in upgrade SQL"
    region = sql[max(0, idx - 700):idx]

    assert "g.distinct_non_null >= 2" in region
    assert "THEN 'conflict'" in region


# ---------------------------------------------------------------------------
# 0003_posture_contract specific tests
# ---------------------------------------------------------------------------


def _offline_upgrade_0003_sql() -> str:
    proc = _run_alembic("upgrade", "0002:0003_posture_contract", "--sql")
    assert proc.returncode == 0, f"alembic upgrade 0002:0003 failed:\n{proc.stderr}"
    return proc.stdout


def _offline_downgrade_0003_sql() -> str:
    proc = _run_alembic("downgrade", "0003_posture_contract:0002", "--sql")
    assert proc.returncode == 0, f"alembic downgrade 0003:0002 failed:\n{proc.stderr}"
    return proc.stdout


def test_0003_upgrade_sql_drops_method_result():
    """0003 upgrade drops method and result columns."""
    sql = _offline_upgrade_0003_sql()
    assert "DROP COLUMN method" in sql, "0003 must DROP COLUMN method"
    assert "DROP COLUMN result" in sql, "0003 must DROP COLUMN result"


def test_0003_upgrade_sql_tightens_source_lifecycle():
    """0003 upgrade sets source and lifecycle to NOT NULL."""
    sql = _offline_upgrade_0003_sql()
    assert "SET NOT NULL" in sql, "0003 must contain SET NOT NULL"
    # Verify both source and lifecycle are tightened.
    sql_lower = sql.lower()
    assert "source" in sql_lower and "set not null" in sql_lower, (
        "0003 must SET NOT NULL for source"
    )
    assert "lifecycle" in sql_lower and "set not null" in sql_lower, (
        "0003 must SET NOT NULL for lifecycle"
    )


def test_0003_downgrade_sql_restores_method_result():
    """0003 downgrade restores method and result columns."""
    sql = _offline_downgrade_0003_sql()
    assert "ADD COLUMN method" in sql, "0003 downgrade must ADD COLUMN method"
    assert "ADD COLUMN result" in sql, "0003 downgrade must ADD COLUMN result"


def test_0003_severity_never_tightened():
    """severity must never be tightened to NOT NULL in 0003 upgrade."""
    sql = _offline_upgrade_0003_sql()
    # severity SET NOT NULL should never appear in the 0003 upgrade SQL.
    assert "severity SET NOT NULL" not in sql, (
        "severity must never be tightened to NOT NULL in 0003"
    )
    assert "severity VARCHAR(20) NOT NULL" not in sql, (
        "severity must never be declared as NOT NULL in 0003"
    )


def test_0003_metadata_no_method_result_columns():
    """After 0003, method and result must not exist in Base.metadata table columns."""
    from app.db.base import Base
    import app.auth.models  # noqa: F401
    import app.posture.models  # noqa: F401

    events = Base.metadata.tables["posture_assessment_events"]
    col_names = set(events.c.keys())
    assert "method" not in col_names, "method must not exist in metadata after 0003"
    assert "result" not in col_names, "result must not exist in metadata after 0003"


# ---------------------------------------------------------------------------
# 0004_health_profile_tracking specific tests (Phase 2 Task 1)
# ---------------------------------------------------------------------------


def _offline_upgrade_0004_sql() -> str:
    proc = _run_alembic("upgrade", "0003_posture_contract:0004_health_profile_tracking", "--sql")
    assert proc.returncode == 0, f"alembic upgrade 0003:0004 failed:\n{proc.stderr}"
    return proc.stdout


def _offline_downgrade_0004_sql() -> str:
    proc = _run_alembic("downgrade", "0004_health_profile_tracking:0003_posture_contract", "--sql")
    assert proc.returncode == 0, f"alembic downgrade 0004:0003 failed:\n{proc.stderr}"
    return proc.stdout


def test_0004_upgrade_creates_health_profiles_table():
    """0004 upgrade creates health_profiles with required columns and constraints."""
    sql = _offline_upgrade_0004_sql()
    assert "CREATE TABLE health_profiles" in sql

    # Required columns exist.
    for col in (
        "id",
        "user_id",
        "fitness_goal",
        "training_experience",
        "weekly_frequency",
        "session_duration_minutes",
        "equipment",
        "pain_injury_limitations",
        "risk_screen",
        "allergies",
        "diet_exclusions",
        "version",
        "created_at",
        "updated_at",
    ):
        assert col in sql, f"missing column {col} in health_profiles"

    # Optional training fields are nullable (no NOT NULL); version is NOT NULL.
    assert "weekly_frequency INTEGER" in sql
    assert "weekly_frequency INTEGER NOT NULL" not in sql
    assert "session_duration_minutes INTEGER" in sql
    assert "session_duration_minutes INTEGER NOT NULL" not in sql
    assert "version INTEGER NOT NULL" in sql

    # JSONB payloads (proves PostgreSQL dialect, not the SQLite patch).
    assert "equipment JSONB" in sql
    assert "risk_screen JSONB" in sql

    # PK + FK + UNIQUE(user_id).
    assert "PRIMARY KEY (id)" in sql
    assert "FOREIGN KEY(user_id) REFERENCES users (id)" in sql
    assert "CONSTRAINT uq_health_profiles_user_id UNIQUE (user_id)" in sql


def test_0004_downgrade_drops_health_profiles_table():
    """0004 downgrade drops the health_profiles table."""
    sql = _offline_downgrade_0004_sql()
    assert "DROP TABLE health_profiles" in sql


def test_0004_health_profiles_unique_constraint_in_metadata():
    """ORM health_profiles carries the named UNIQUE(user_id) constraint and
    nullable optional fields (missing stays missing)."""
    from sqlalchemy import UniqueConstraint
    from app.db.base import Base
    import app.auth.models  # noqa: F401
    import app.posture.models  # noqa: F401
    import app.health.models  # noqa: F401

    table = Base.metadata.tables["health_profiles"]

    uniq = {
        tuple(c.name for c in uc.columns)
        for uc in table.constraints
        if isinstance(uc, UniqueConstraint)
    }
    assert ("user_id",) in uniq

    # Optional fields stay nullable in metadata.
    for col in (
        "fitness_goal",
        "training_experience",
        "weekly_frequency",
        "session_duration_minutes",
        "equipment",
        "pain_injury_limitations",
        "risk_screen",
        "allergies",
        "diet_exclusions",
    ):
        assert table.c[col].nullable is True, f"{col} must be nullable"

    # version and user_id are NOT NULL.
    assert table.c["version"].nullable is False
    assert table.c["user_id"].nullable is False


# ---------------------------------------------------------------------------
# 0005_health_checkins specific tests (Phase 2 Task 3)
# ---------------------------------------------------------------------------


def _offline_upgrade_0005_sql() -> str:
    proc = _run_alembic("upgrade", "0004_health_profile_tracking:0005_health_checkins", "--sql")
    assert proc.returncode == 0, f"alembic upgrade 0004:0005 failed:\n{proc.stderr}"
    return proc.stdout


def _offline_downgrade_0005_sql() -> str:
    proc = _run_alembic("downgrade", "0005_health_checkins:0004_health_profile_tracking", "--sql")
    assert proc.returncode == 0, f"alembic downgrade 0005:0004 failed:\n{proc.stderr}"
    return proc.stdout


def test_0005_upgrade_creates_health_checkins_table():
    """0005 upgrade creates health_checkins with required columns and the
    per-user daily uniqueness constraint."""
    sql = _offline_upgrade_0005_sql()
    assert "CREATE TABLE health_checkins" in sql

    # Required columns exist.
    for col in (
        "id",
        "user_id",
        "local_date",
        "sleep_quality",
        "energy",
        "muscle_soreness",
        "available_time",
        "daily_status",
        "abnormal_pain",
        "pain_followup",
        "risk_summary",
        "risk_version",
        "created_at",
        "updated_at",
    ):
        assert col in sql, f"missing column {col} in health_checkins"

    # Core completed-check-in fields are NOT NULL; pain_followup is nullable.
    assert "abnormal_pain BOOLEAN NOT NULL" in sql
    assert "daily_status VARCHAR(30) NOT NULL" in sql
    assert "risk_summary VARCHAR(30) NOT NULL" in sql
    assert "local_date DATE NOT NULL" in sql
    assert "pain_followup JSONB" in sql
    assert "pain_followup JSONB NOT NULL" not in sql

    # PK + FK + UNIQUE(user_id, local_date) daily uniqueness.
    assert "PRIMARY KEY (id)" in sql
    assert "FOREIGN KEY(user_id) REFERENCES users (id)" in sql
    assert (
        "CONSTRAINT uq_health_checkins_user_date UNIQUE (user_id, local_date)"
        in sql
    )


def test_0005_downgrade_drops_health_checkins_table():
    """0005 downgrade drops the health_checkins table."""
    sql = _offline_downgrade_0005_sql()
    assert "DROP TABLE health_checkins" in sql


def test_0005_health_checkins_unique_constraint_in_metadata():
    """ORM health_checkins carries UNIQUE(user_id, local_date) (daily
    uniqueness) and the deterministic stored safety fields are NOT NULL."""
    from sqlalchemy import UniqueConstraint
    from app.db.base import Base
    import app.auth.models  # noqa: F401
    import app.posture.models  # noqa: F401
    import app.health.models  # noqa: F401

    table = Base.metadata.tables["health_checkins"]

    uniq = {
        tuple(c.name for c in uc.columns)
        for uc in table.constraints
        if isinstance(uc, UniqueConstraint)
    }
    assert ("user_id", "local_date") in uniq

    # pain_followup is nullable; the deterministic stored safety fields are not.
    assert table.c["pain_followup"].nullable is True
    for col in (
        "local_date",
        "daily_status",
        "abnormal_pain",
        "risk_summary",
        "risk_version",
        "user_id",
    ):
        assert table.c[col].nullable is False, f"{col} must be NOT NULL"


# ---------------------------------------------------------------------------
# 0006_health_weight_tracking specific tests (Phase 2 Task 4)
# ---------------------------------------------------------------------------


def _offline_upgrade_0006_sql() -> str:
    proc = _run_alembic("upgrade", "0005_health_checkins:0006_health_weight_tracking", "--sql")
    assert proc.returncode == 0, f"alembic upgrade 0005:0006 failed:\n{proc.stderr}"
    return proc.stdout


def _offline_downgrade_0006_sql() -> str:
    proc = _run_alembic("downgrade", "0006_health_weight_tracking:0005_health_checkins", "--sql")
    assert proc.returncode == 0, f"alembic downgrade 0006:0005 failed:\n{proc.stderr}"
    return proc.stdout


def test_0006_upgrade_creates_weight_records_table():
    """0006 upgrade creates weight_records with required columns, the manual
    source default, and the per-user trend index."""
    sql = _offline_upgrade_0006_sql()
    assert "CREATE TABLE weight_records" in sql

    for col in (
        "id",
        "user_id",
        "recorded_at",
        "weight_kg",
        "source",
        "note",
        "created_at",
        "updated_at",
    ):
        assert col in sql, f"missing column {col} in weight_records"

    # weight_kg is NUMERIC(6,2); recorded_at is a timestamp; note nullable.
    assert "weight_kg NUMERIC(6, 2) NOT NULL" in sql
    assert "recorded_at TIMESTAMP WITHOUT TIME ZONE" not in sql  # tz-aware
    assert "source VARCHAR(20)" in sql
    assert "DEFAULT 'manual'" in sql  # server-set manual source

    # PK + FK; no UNIQUE constraint (multiple records per user).
    assert "PRIMARY KEY (id)" in sql
    assert "FOREIGN KEY(user_id) REFERENCES users (id)" in sql
    assert "UNIQUE" not in sql.split("CREATE TABLE weight_records")[1].split(")")[0]

    # Composite trend index exists.
    assert "CREATE INDEX ix_weight_records_user_recorded_at" in sql
    assert "ON weight_records (user_id, recorded_at)" in sql


def test_0006_downgrade_drops_weight_records_table():
    """0006 downgrade drops the weight_records table and its index."""
    sql = _offline_downgrade_0006_sql()
    assert "DROP TABLE weight_records" in sql
    assert "DROP INDEX ix_weight_records_user_recorded_at" in sql


def test_0006_weight_records_index_in_metadata():
    """ORM weight_records carries the named (user_id, recorded_at) index and
    nullable note; weight_kg / recorded_at / source are NOT NULL."""
    from app.db.base import Base
    import app.auth.models  # noqa: F401
    import app.posture.models  # noqa: F401
    import app.health.models  # noqa: F401

    table = Base.metadata.tables["weight_records"]

    index_names = {idx.name for idx in table.indexes}
    assert "ix_weight_records_user_recorded_at" in index_names

    assert table.c["note"].nullable is True
    for col in ("user_id", "recorded_at", "weight_kg", "source"):
        assert table.c[col].nullable is False, f"{col} must be NOT NULL"


# ---------------------------------------------------------------------------
# Phase 5 Agent MVP (migration 0008)
# ---------------------------------------------------------------------------


def _offline_upgrade_0008_sql() -> str:
    proc = _run_alembic("upgrade", "0007_training_plans:0008_agent_mvp", "--sql")
    assert proc.returncode == 0, f"alembic upgrade 0007:0008 failed:\n{proc.stderr}"
    return proc.stdout


def _offline_downgrade_0008_sql() -> str:
    proc = _run_alembic("downgrade", "0008_agent_mvp:0007_training_plans", "--sql")
    assert proc.returncode == 0, f"alembic downgrade 0008:0007 failed:\n{proc.stderr}"
    return proc.stdout


def test_0008_upgrade_creates_four_agent_tables():
    """0008 upgrade single-head-extends 0007 and creates the four Agent tables
    with their PK/FK/UNIQUE/CHECK/ownership-index invariants."""
    sql = _offline_upgrade_0008_sql()
    for table in (
        "agent_cloud_consents",
        "agent_runs",
        "agent_tool_events",
        "agent_action_proposals",
    ):
        assert f"CREATE TABLE {table}" in sql, f"missing CREATE TABLE {table}"

    # consent: unique (user_id, purpose, sequence_no) + status CHECK + ownership index.
    consent = sql.split("CREATE TABLE agent_cloud_consents")[1]
    assert "PRIMARY KEY (consent_id)" in consent
    assert "FOREIGN KEY(user_id) REFERENCES users (id)" in consent
    assert "CONSTRAINT uq_agent_cloud_consents_user_purpose_seq UNIQUE" in consent
    assert "sequence_no" in consent and "provider_id" in consent
    assert "CHECK (status IN ('granted', 'withdrawn'))" in consent
    assert "CREATE INDEX ix_agent_cloud_consents_user" in sql

    # runs: unique (user_id, client_turn_id) + ownership + expiry indexes.
    assert "CONSTRAINT uq_agent_runs_user_turn UNIQUE" in sql
    assert "CREATE INDEX ix_agent_runs_user" in sql
    assert "CREATE INDEX ix_agent_runs_expires_at" in sql

    # tool_events: FK to runs with ondelete CASCADE + ownership index.
    te = sql.split("CREATE TABLE agent_tool_events")[1]
    assert "FOREIGN KEY(run_id) REFERENCES agent_runs (run_id)" in te
    assert "ON DELETE CASCADE" in te
    assert "CREATE INDEX ix_agent_tool_events_run" in sql
    assert "CREATE INDEX ix_agent_tool_events_user" in sql

    # proposals: status CHECK (closed lifecycle) + nullable arguments_json +
    # user/status + run + expiry indexes.
    pp = sql.split("CREATE TABLE agent_action_proposals")[1]
    assert "arguments_json JSON" in pp  # JSONB renders as JSON in offline SQL
    assert "arguments_hash" in pp
    assert "iana_timezone VARCHAR(60) NOT NULL" in pp
    assert "CONSTRAINT uq_agent_action_proposals_run UNIQUE (run_id)" in pp
    assert (
        "CHECK (status IN ('pending', 'executed', 'invalidated', 'expired', 'cancelled'))"
        in pp
    )
    assert "CREATE INDEX ix_agent_action_proposals_user_status" in sql
    assert "CREATE INDEX ix_agent_action_proposals_run" in sql
    assert "CREATE INDEX ix_agent_action_proposals_expires_at" in sql

    # No raw-text/context/prompt/provider-payload column names leak in.
    for forbidden in (
        "user_message",
        "assistant_message",
        "raw_context",
        "prompt_text",
        "provider_request",
        "provider_response",
        "tool_result_payload",
    ):
        assert forbidden not in sql, f"forbidden raw payload column {forbidden}"


def test_0008_downgrade_drops_four_agent_tables():
    """0008 downgrade drops indexes then the four tables in dependency order."""
    sql = _offline_downgrade_0008_sql()
    for table in (
        "agent_action_proposals",
        "agent_tool_events",
        "agent_runs",
        "agent_cloud_consents",
    ):
        assert f"DROP TABLE {table}" in sql, f"missing DROP TABLE {table}"
    # Posture/health/training tables are NOT touched by the Agent downgrade.
    for untouched in ("training_plan_versions", "health_checkins", "weight_records"):
        assert f"DROP TABLE {untouched}" not in sql


def test_0008_agent_models_metadata_parity():
    """Agent ORM metadata matches the migration: ownership indexes, named UNIQUE
    constraints, nullable arguments_json, and the cascade tool_events FK."""
    from app.db.base import Base
    import app.agent.models  # noqa: F401

    consents = Base.metadata.tables["agent_cloud_consents"]
    assert "ix_agent_cloud_consents_user" in {i.name for i in consents.indexes}
    assert "uq_agent_cloud_consents_user_purpose_seq" in {
        c.name for c in consents.constraints if c.name
    }
    assert consents.c["sequence_no"].nullable is False

    proposals = Base.metadata.tables["agent_action_proposals"]
    assert proposals.c["arguments_json"].nullable is True
    assert proposals.c["arguments_hash"].nullable is False
    assert proposals.c["iana_timezone"].nullable is False
    assert proposals.c["result_ref"].nullable is True
    assert "ix_agent_action_proposals_user_status" in {
        i.name for i in proposals.indexes
    }
    assert "uq_agent_action_proposals_run" in {
        c.name for c in proposals.constraints if c.name
    }

    events = Base.metadata.tables["agent_tool_events"]
    # The tool_events -> runs FK is declared ondelete CASCADE.
    te_fk = next(
        fk for fk in events.foreign_keys if fk.column.table.name == "agent_runs"
    )
    assert te_fk.ondelete == "CASCADE"

    runs = Base.metadata.tables["agent_runs"]
    assert "uq_agent_runs_user_turn" in {c.name for c in runs.constraints if c.name}
    assert "ix_agent_runs_expires_at" in {i.name for i in runs.indexes}
    assert runs.c["expires_at"].nullable is False
