"""Alembic migration contract tests.

关键设计：
``tests/conftest.py`` 在 import 时会 monkey-patch
``sqlalchemy.dialects.postgresql.UUID`` / ``JSONB`` 为 SQLite 兼容类型。
一旦 pytest 收集了 conftest，这些补丁在整个进程内生效。

因此本文件通过 **子进程** 调用 ``python -m alembic ... --sql`` 生成 SQL：
子进程是全新解释器，不 import 测试 conftest，PostgreSQL 方言类型保持原样。
在进程内我们只检查子进程输出文本和 ``Base.metadata`` 表名集合，
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


def test_single_head():
    """Alembic 只有一个 head。"""
    proc = _run_alembic("heads")
    assert proc.returncode == 0, proc.stderr
    head_lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(head_lines) == 1, f"expected exactly one head, got: {head_lines}"
    assert "0001_initial_schema" in head_lines[0]


def test_offline_upgrade_sql_generates():
    """upgrade SQL 可以按 PostgreSQL 方言离线生成。"""
    sql = _offline_upgrade_sql()
    assert sql.strip(), "upgrade SQL is empty"


def test_offline_downgrade_sql_generates():
    """downgrade SQL 可以离线生成。"""
    sql = _offline_downgrade_sql()
    assert sql.strip(), "downgrade SQL is empty"


def test_upgrade_sql_contains_tables_indexes_fk():
    """生成 SQL 包含三张表、关键索引和外键。"""
    sql = _offline_upgrade_sql()

    # 三张表
    assert "CREATE TABLE users" in sql
    assert "CREATE TABLE verification_codes" in sql
    assert "CREATE TABLE posture_assessments" in sql

    # 关键索引
    assert "ix_users_phone" in sql
    assert "ix_verification_codes_phone" in sql
    assert "ix_posture_assessments_user_id" in sql

    # 外键
    assert "REFERENCES users" in sql

    # PostgreSQL 专有类型（证明未走 SQLite monkey patch）
    assert "UUID" in sql
    assert "JSONB" in sql


def test_downgrade_sql_drops_all_tables_reverse_order():
    """downgrade 反序删除三张表。"""
    sql = _offline_downgrade_sql()
    for table in ("posture_assessments", "verification_codes", "users"):
        assert f"DROP TABLE {table}" in sql, f"missing DROP TABLE {table}"

    # 依赖反序：子表 posture_assessments 必须先于父表 users 删除。
    assert sql.index("DROP TABLE posture_assessments") < sql.index("DROP TABLE users")


def test_migration_tables_match_base_metadata():
    """migration 表集合与 Base.metadata 表集合一致。

    只读取 Base.metadata 的表名集合（不渲染类型），因此即使 conftest 的
    monkey patch 已生效，也不会污染断言。
    """
    from app.db.base import Base
    import app.auth.models  # noqa: F401
    import app.posture.models  # noqa: F401

    metadata_tables = set(Base.metadata.tables.keys())
    assert metadata_tables == {
        "users",
        "verification_codes",
        "posture_assessments",
    }

    # migration 覆盖的表集合（从离线 SQL 提取）应等于 metadata 表集合。
    sql = _offline_upgrade_sql()
    migration_tables = {t for t in metadata_tables if f"CREATE TABLE {t}" in sql}
    assert migration_tables == metadata_tables


def test_offline_sql_independent_of_conftest_sqlite_patch():
    """migration 文件不依赖测试 conftest 的 SQLite monkey patch。

    子进程未加载 conftest，因此 PostgreSQL 方言类型未被替换。
    如果曾误用被 patch 的类型，SQLite 分支会输出 CHAR(36) / JSON，
    而不是 UUID / JSONB。断言这些 SQLite 产物不出现。
    """
    sql = _offline_upgrade_sql()
    assert "UUID" in sql
    assert "JSONB" in sql
    # SQLite patch 的痕迹不应出现在 PostgreSQL 离线 SQL 中。
    assert "CHAR(36)" not in sql
    # JSONB 存在即证明未降级为 SQLite 的 JSON；确保没有裸 " JSON " 列类型。
    assert " JSON," not in sql and " JSON\n" not in sql


def test_env_does_not_leak_password_in_offline_output():
    """离线输出不包含数据库密码。"""
    sql = _offline_upgrade_sql()
    assert "password" not in sql.lower()


# --- URL 百分号转义回归 ---


def test_url_with_percent_escaped_password_succeeds():
    """DATABASE_URL 含百分号编码密码 (p%25%40ss) 时 alembic 仍成功且不泄露密码。

    覆盖 ConfigParser 插值问题：``%`` 必须被转义为 ``%%`` 才能写入 Alembic Config。
    """
    percent_url = "postgresql+asyncpg://user:p%25%40ss@localhost:5432/posture_app"
    proc = _run_alembic("upgrade", "head", "--sql", database_url=percent_url)

    # 命令必须成功。
    assert proc.returncode == 0, (
        f"alembic upgrade --sql failed with percent-encoded password:\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )

    # stdout 和 stderr 都不得包含密码或凭据片段。
    combined = (proc.stdout + "\n" + proc.stderr).lower()
    for secret in ("password", "p%25%40ss", "p@ss", "p%40ss"):
        assert secret.lower() not in combined, f"leaked secret fragment: {secret}"

    # 仍生成有效的 schema SQL。
    assert "CREATE TABLE users" in proc.stdout


# --- users.phone schema 一致性 ---


def test_users_phone_unique_index_only():
    """upgrade SQL 对 users.phone 只创建一次唯一索引，且无 UNIQUE (phone) 约束。"""
    sql = _offline_upgrade_sql()

    # 唯一索引恰好出现一次。
    assert sql.count("CREATE UNIQUE INDEX ix_users_phone") == 1

    # 不得出现表级 UNIQUE (phone) 约束。
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
    assert UniqueConstraint not in constraint_types, (
        "users should not declare a table-level UniqueConstraint; "
        "phone uniqueness comes from the unique index"
    )

    # 恰好一个索引，名为 ix_users_phone 且 unique=True。
    indexes = list(users.indexes)
    assert len(indexes) == 1
    idx = indexes[0]
    assert idx.name == "ix_users_phone"
    assert idx.unique is True


def test_index_names_uniqueness_and_fk():
    """按三张表比较索引名称、唯一性与关键外键（不只比较表名）。"""
    sql = _offline_upgrade_sql()

    # users.phone: 唯一索引。
    assert "CREATE UNIQUE INDEX ix_users_phone ON users (phone)" in sql

    # verification_codes.phone: 非唯一索引。
    assert (
        "CREATE INDEX ix_verification_codes_phone ON verification_codes (phone)" in sql
    )
    assert "CREATE UNIQUE INDEX ix_verification_codes_phone" not in sql

    # posture_assessments.user_id: 非唯一索引。
    assert (
        "CREATE INDEX ix_posture_assessments_user_id ON posture_assessments (user_id)"
        in sql
    )
    assert "CREATE UNIQUE INDEX ix_posture_assessments_user_id" not in sql

    # 关键外键：posture_assessments.user_id -> users.id。
    assert "FOREIGN KEY(user_id) REFERENCES users (id)" in sql
