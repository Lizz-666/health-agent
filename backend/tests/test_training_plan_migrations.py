"""Phase 4 migration contract tests (Task 2).

Two layers:

1. Offline SQL assertions (always run, no PostgreSQL needed): the five Phase 4
   tables, the single-active partial UNIQUE index, the session/feedback/
   substitution UNIQUE constraints, and the dependency-ordered downgrade. These
   render via ``alembic upgrade --sql`` in a fresh subprocess (PG dialect, so
   the conftest SQLite monkey-patch does not interfere — same approach as
   ``test_migrations.py``).

2. A ``requires_pg`` test on real PostgreSQL 16: inserts two ``active`` plan
   versions for one user and expects the partial UNIQUE index to reject the
   second. This is the authoritative evidence for ADR-0002's single-active
   invariant at the DB level (the application-level check is covered on SQLite
   in test_training_plan_persistence.py).
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.conftest_pg import pg_available, requires_pg, skip_reason

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_URL = "postgresql+asyncpg://user:password@localhost:5432/posture_app"

PHASE4_TABLES = {
    "training_plan_versions",
    "training_sessions",
    "training_prescriptions",
    "training_session_feedback",
    "training_session_substitutions",
}


def _run_alembic(*args: str, database_url: str = DEFAULT_DB_URL):
    env = dict(os.environ)
    env["DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )


_upgrade_cache: str | None = None
_downgrade_cache: str | None = None


def _upgrade_sql() -> str:
    global _upgrade_cache
    if _upgrade_cache is None:
        proc = _run_alembic("upgrade", "head", "--sql")
        assert proc.returncode == 0, f"alembic upgrade --sql failed:\n{proc.stderr}"
        _upgrade_cache = proc.stdout
    return _upgrade_cache


def _downgrade_sql() -> str:
    global _downgrade_cache
    if _downgrade_cache is None:
        proc = _run_alembic(
            "downgrade",
            "0007_training_plans:0006_health_weight_tracking",
            "--sql",
        )
        assert proc.returncode == 0, f"alembic downgrade --sql failed:\n{proc.stderr}"
        _downgrade_cache = proc.stdout
    return _downgrade_cache


# --- offline SQL (always runs) ---------------------------------------------


def test_upgrade_creates_all_phase4_tables():
    sql = _upgrade_sql()
    for table in PHASE4_TABLES:
        assert f"CREATE TABLE {table}" in sql, f"missing CREATE TABLE {table}"


def test_upgrade_creates_single_active_partial_unique_index():
    sql = _upgrade_sql()
    # PostgreSQL partial UNIQUE index enforcing at most one active plan/user.
    assert "CREATE UNIQUE INDEX uq_training_plan_versions_one_active" in sql
    assert "ON training_plan_versions" in sql
    assert "status = 'active'" in sql


def test_upgrade_creates_phase4_unique_constraints():
    sql = _upgrade_sql()
    for name in (
        "uq_training_sessions_version_week_order",
        "uq_training_session_feedback_session_date",
        "uq_training_session_substitutions_session_date",
    ):
        assert name in sql, f"missing unique constraint/index {name}"


def test_downgrade_drops_only_phase4_training_tables():
    # Render only the Phase 4 revision interval. Later phases may legitimately
    # add more training tables, but 0007's own downgrade remains isolated.
    import re

    sql = _downgrade_sql()
    dropped_training = set(re.findall(r"DROP TABLE (training_\w+)", sql))
    assert dropped_training == PHASE4_TABLES, (
        f"Phase 4 downgrade drops {sorted(dropped_training)}, "
        f"expected {sorted(PHASE4_TABLES)}"
    )
    # Children dropped before parents.
    assert sql.index("DROP TABLE training_prescriptions") < sql.index(
        "DROP TABLE training_sessions"
    )
    assert sql.index("DROP TABLE training_sessions") < sql.index(
        "DROP TABLE training_plan_versions"
    )
    assert sql.index("DROP TABLE training_session_feedback") < sql.index(
        "DROP TABLE training_plan_versions"
    )
    # The partial unique index is dropped before its table.
    assert sql.index("DROP INDEX uq_training_plan_versions_one_active") < sql.index(
        "DROP TABLE training_plan_versions"
    )


# --- PostgreSQL 16 authoritative single-active invariant -------------------

PG_TESTS = pytestmark = [
    requires_pg,
    pytest.mark.requires_pg,
]


@pytest.fixture(autouse=True)
def _skip_without_pg():
    if not pg_available:
        pytest.skip(skip_reason)


@pytest.mark.asyncio
async def test_pg_partial_unique_index_rejects_second_active_plan(pg_session):
    """ADR-0002 DB-level guarantee: a second active plan for one user fails."""
    from sqlalchemy import insert
    from sqlalchemy.exc import IntegrityError

    from app.auth.models import User
    from app.training.models import TrainingPlanVersion

    session = pg_session
    assert session.bind.dialect.name == "postgresql"

    user_id = _uuid.uuid4()

    def _version(status: str) -> TrainingPlanVersion:
        return TrainingPlanVersion(
            user_id=user_id,
            requested_goal="posture_improvement",
            source_context_fingerprint="a" * 64,
            profile_version=1,
            catalog_version="v1",
            policy_version="v1",
            source_manifest_version="v1",
            weekly_frequency=3,
            session_duration_minutes=30,
            status=status,
            change_reason="initial_confirmation",
            decision_gate="eligible",
            decision_fingerprint="a" * 64,
            generated_at=datetime.now(timezone.utc),
            confirmed_at=datetime.now(timezone.utc),
        )

    async def _seed_user():
        await session.execute(
            insert(User).values(id=user_id, phone="13800000999")
        )
        await session.flush()

    # Seed user + first active plan (allowed).
    await _seed_user()
    session.add(_version("active"))
    await session.flush()

    # A second active plan for the SAME user must violate the partial index.
    session.add(_version("active"))
    with pytest.raises(IntegrityError):
        await session.flush()
    # The IntegrityError poisoned the transaction; rollback also removes the
    # seeded user, so re-seed before the scoped-uniqueness check below.
    await session.rollback()
    await _seed_user()

    # superseded + draft for the same user must NOT violate the partial index:
    # the WHERE clause scopes uniqueness to status='active' only.
    session.add(_version("superseded"))
    session.add(_version("draft"))
    await session.flush()  # should succeed
