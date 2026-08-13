from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest_pg import pg_available, requires_pg, skip_reason


BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_URL = "postgresql+asyncpg://user:password@localhost:5432/posture_app"


def _alembic(*args: str, database_url: str = DEFAULT_DB_URL):
    env = dict(os.environ)
    env["DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )


def test_0011_offline_upgrade_and_downgrade_are_scoped():
    upgrade = _alembic(
        "upgrade", "0010_nutrition_recommendations:0011_adaptive_reviews", "--sql"
    )
    assert upgrade.returncode == 0, upgrade.stderr
    sql = upgrade.stdout
    for table in (
        "training_day_adjustments",
        "training_day_adjustment_items",
        "training_weekly_reviews",
        "posture_recheck_dismissals",
    ):
        assert f"CREATE TABLE {table}" in sql
    assert "uq_training_day_adjustments_decision" in sql
    assert "uq_training_weekly_reviews_fingerprint" in sql
    assert "uq_posture_recheck_dismissals_cycle" in sql
    assert "raw_note" not in sql
    assert "pain_note" not in sql
    assert "photo" not in sql

    downgrade = _alembic(
        "downgrade", "0011_adaptive_reviews:0010_nutrition_recommendations", "--sql"
    )
    assert downgrade.returncode == 0, downgrade.stderr
    down = downgrade.stdout
    assert "DROP TABLE training_day_adjustment_items" in down
    assert "DROP TABLE training_day_adjustments" in down
    assert "DROP TABLE training_weekly_reviews" in down
    assert "DROP TABLE posture_recheck_dismissals" in down
    assert "DROP TABLE training_plan_versions" not in down
    assert "DROP TABLE nutrition_recommendations" not in down


def test_0011_online_sqlite_upgrade_and_downgrade(tmp_path):
    database = tmp_path / "adaptive-0011.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database.as_posix()}"
    stamp = _alembic(
        "stamp", "0010_nutrition_recommendations", database_url=database_url
    )
    assert stamp.returncode == 0, stamp.stderr
    upgrade = _alembic("upgrade", "0011_adaptive_reviews", database_url=database_url)
    assert upgrade.returncode == 0, upgrade.stderr
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "training_day_adjustments",
            "training_day_adjustment_items",
            "training_weekly_reviews",
            "posture_recheck_dismissals",
        }.issubset(tables)
        adjustment_unique_columns = {
            tuple(
                column[2]
                for column in connection.execute(
                    f"PRAGMA index_info('{index_row[1]}')"
                )
            )
            for index_row in connection.execute(
                "PRAGMA index_list('training_day_adjustments')"
            )
            if index_row[2]
        }
        assert (
            "plan_version_id",
            "source_session_id",
            "source_local_date",
            "source_context_fingerprint",
            "adaptive_policy_version",
            "adjustment_kind",
        ) in adjustment_unique_columns
        review_unique_columns = {
            tuple(
                column[2]
                for column in connection.execute(
                    f"PRAGMA index_info('{index_row[1]}')"
                )
            )
            for index_row in connection.execute(
                "PRAGMA index_list('training_weekly_reviews')"
            )
            if index_row[2]
        }
        assert (
            "plan_version_id",
            "week_index",
            "input_fingerprint",
        ) in review_unique_columns

    downgrade = _alembic(
        "downgrade", "0010_nutrition_recommendations", database_url=database_url
    )
    assert downgrade.returncode == 0, downgrade.stderr
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "training_day_adjustments" not in tables
        assert "training_weekly_reviews" not in tables


@requires_pg
@pytest.mark.requires_pg
def test_0011_postgresql_downgrade_and_upgrade(pg_dsn):
    if not pg_available:
        pytest.skip(skip_reason)
    downgrade = _alembic(
        "downgrade", "0010_nutrition_recommendations", database_url=pg_dsn
    )
    assert downgrade.returncode == 0, downgrade.stderr
    upgrade = _alembic("upgrade", "0011_adaptive_reviews", database_url=pg_dsn)
    assert upgrade.returncode == 0, upgrade.stderr
    # This fixture database is shared across PostgreSQL tests. Verify 0011 at
    # its own boundary, then restore the current schema for later ORM tests.
    restore = _alembic("upgrade", "head", database_url=pg_dsn)
    assert restore.returncode == 0, restore.stderr
