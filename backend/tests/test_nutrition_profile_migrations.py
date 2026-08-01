"""Phase 6 Gate 1 migration contract for structured profile codes."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
DB_URL = "postgresql+asyncpg://user:password@localhost:5432/posture_app"


def _alembic(*args: str):
    env = dict(os.environ)
    env["DATABASE_URL"] = DB_URL
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env,
        capture_output=True, text=True,
    )


def test_0009_upgrade_adds_nullable_jsonb_columns_without_backfill():
    result = _alembic("upgrade", "0008_agent_mvp:0009_nutrition_profile_codes", "--sql")
    assert result.returncode == 0, result.stderr
    sql = result.stdout
    assert "ADD COLUMN food_allergen_codes JSONB" in sql
    assert "ADD COLUMN excluded_food_codes JSONB" in sql
    assert "UPDATE health_profiles" not in sql


def test_0009_downgrade_drops_only_new_columns():
    result = _alembic("downgrade", "0009_nutrition_profile_codes:0008_agent_mvp", "--sql")
    assert result.returncode == 0, result.stderr
    sql = result.stdout
    assert "DROP COLUMN excluded_food_codes" in sql
    assert "DROP COLUMN food_allergen_codes" in sql
    assert "DROP TABLE" not in sql


def test_health_profile_metadata_has_nullable_structured_columns():
    from app.health.models import HealthProfile
    table = HealthProfile.__table__
    assert table.c.food_allergen_codes.nullable is True
    assert table.c.excluded_food_codes.nullable is True
