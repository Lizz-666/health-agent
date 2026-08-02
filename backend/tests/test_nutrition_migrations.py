from __future__ import annotations

import os
import asyncio
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

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


def test_0010_upgrade_and_downgrade_are_isolated_and_reversible():
    upgrade = _alembic(
        "upgrade", "0009_nutrition_profile_codes:0010_nutrition_recommendations", "--sql"
    )
    assert upgrade.returncode == 0, upgrade.stderr
    sql = upgrade.stdout
    assert "CREATE TABLE nutrition_recommendations" in sql
    assert "ck_nutrition_recommendations_status" in sql
    assert "uq_nutrition_recommendations_user_version" in sql
    assert "CREATE UNIQUE INDEX uq_nutrition_recommendations_one_draft" in sql
    assert "status = 'draft'" in sql
    assert "CREATE UNIQUE INDEX uq_nutrition_recommendations_one_active" in sql
    assert "status = 'active'" in sql
    assert "meal_event" not in sql
    assert "intake" not in sql
    assert "completed_quantity" not in sql

    downgrade = _alembic(
        "downgrade", "0010_nutrition_recommendations:0009_nutrition_profile_codes", "--sql"
    )
    assert downgrade.returncode == 0, downgrade.stderr
    down = downgrade.stdout
    assert "DROP TABLE nutrition_recommendations" in down
    assert "health_profiles" not in down
    assert "training_plan_versions" not in down


def test_model_declares_sqlite_and_postgresql_partial_indexes():
    from app.nutrition.models import NutritionRecommendation

    indexes = {index.name: index for index in NutritionRecommendation.__table__.indexes}
    for name, status in (
        ("uq_nutrition_recommendations_one_draft", "draft"),
        ("uq_nutrition_recommendations_one_active", "active"),
    ):
        index = indexes[name]
        assert index.unique is True
        assert status in str(index.dialect_options["postgresql"]["where"])
        assert status in str(index.dialect_options["sqlite"]["where"])


def test_0010_online_sqlite_upgrade_and_downgrade(tmp_path):
    database = tmp_path / "nutrition-0010.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database.as_posix()}"
    stamp = _alembic("stamp", "0009_nutrition_profile_codes", database_url=database_url)
    assert stamp.returncode == 0, stamp.stderr
    upgrade = _alembic("upgrade", "0010_nutrition_recommendations", database_url=database_url)
    assert upgrade.returncode == 0, upgrade.stderr
    with sqlite3.connect(database) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='nutrition_recommendations'"
        ).fetchone()
        assert table == ("nutrition_recommendations",)
        indexes = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='index' "
                "AND tbl_name='nutrition_recommendations'"
            )
        }
        assert "WHERE status = 'draft'" in indexes[
            "uq_nutrition_recommendations_one_draft"
        ]
        assert "WHERE status = 'active'" in indexes[
            "uq_nutrition_recommendations_one_active"
        ]
    downgrade = _alembic("downgrade", "0009_nutrition_profile_codes", database_url=database_url)
    assert downgrade.returncode == 0, downgrade.stderr
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='nutrition_recommendations'"
        ).fetchone() is None


def test_0009_online_sqlite_nullable_columns_upgrade_and_downgrade(tmp_path):
    database = tmp_path / "nutrition-0009.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE health_profiles (id TEXT PRIMARY KEY, version INTEGER NOT NULL)"
        )
    database_url = f"sqlite+aiosqlite:///{database.as_posix()}"
    stamp = _alembic("stamp", "0008_agent_mvp", database_url=database_url)
    assert stamp.returncode == 0, stamp.stderr
    upgrade = _alembic("upgrade", "0009_nutrition_profile_codes", database_url=database_url)
    assert upgrade.returncode == 0, upgrade.stderr
    with sqlite3.connect(database) as connection:
        columns = {row[1]: row for row in connection.execute("PRAGMA table_info(health_profiles)")}
        assert columns["food_allergen_codes"][3] == 0
        assert columns["excluded_food_codes"][3] == 0
    downgrade = _alembic("downgrade", "0008_agent_mvp", database_url=database_url)
    assert downgrade.returncode == 0, downgrade.stderr
    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(health_profiles)")}
        assert "food_allergen_codes" not in columns
        assert "excluded_food_codes" not in columns


@requires_pg
@pytest.mark.requires_pg
@pytest.mark.asyncio
async def test_pg_partial_indexes_reject_second_current_status(pg_session):
    if not pg_available:
        pytest.skip(skip_reason)
    from app.auth.models import User
    from app.nutrition.models import NutritionRecommendation

    session = pg_session
    user_id = uuid.uuid4()
    await session.execute(insert(User).values(id=user_id, phone="13810000999"))

    def row(status: str, version: int) -> NutritionRecommendation:
        return NutritionRecommendation(
            user_id=user_id,
            version=version,
            status=status,
            change_reason="test",
            source_context_fingerprint="a" * 64,
            profile_version=1,
            training_plan_version_id=str(uuid.UUID(int=42)),
            checkin_token="b" * 64,
            policy_version="v1",
            catalog_version="v1",
            source_manifest_version="v1",
            media_manifest_version="v1",
            decision_gate="eligible",
            payload={"schema_version": "test"},
            validation_codes=["recommendation_valid"],
            generated_at=datetime.now(timezone.utc),
        )

    session.add(row("active", 1))
    session.add(row("draft", 2))
    await session.flush()
    session.add(row("active", 3))
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()

    user_id = uuid.uuid4()
    await session.execute(insert(User).values(id=user_id, phone="13810000998"))
    session.add(row("draft", 1))
    await session.flush()
    session.add(row("draft", 2))
    with pytest.raises(IntegrityError):
        await session.flush()


@requires_pg
@pytest.mark.requires_pg
@pytest.mark.asyncio
async def test_pg_concurrent_confirmation_has_exactly_one_winner(pg_session_factory):
    if not pg_available:
        pytest.skip(skip_reason)
    from sqlalchemy import func, select

    from app.auth.models import User
    from app.core.exceptions import AppException
    from app.nutrition import persistence
    from app.nutrition.models import NutritionRecommendation

    user_id = uuid.uuid4()
    recommendation_id = uuid.uuid4()
    seed = pg_session_factory()
    seed.add(User(id=user_id, phone="13810000997"))
    seed.add(
        NutritionRecommendation(
            recommendation_id=recommendation_id,
            user_id=user_id,
            version=1,
            status="draft",
            change_reason="test",
            source_context_fingerprint="a" * 64,
            profile_version=1,
            training_plan_version_id=str(uuid.UUID(int=42)),
            checkin_token="b" * 64,
            policy_version="v1",
            catalog_version="v1",
            source_manifest_version="v1",
            media_manifest_version="v1",
            decision_gate="eligible",
            payload={"schema_version": "test"},
            validation_codes=["recommendation_valid"],
            generated_at=datetime.now(timezone.utc),
        )
    )
    await seed.commit()

    async def confirm(key: str):
        session = pg_session_factory()
        return await persistence.confirm_draft(
            session,
            str(user_id),
            draft_id=recommendation_id,
            expected_version=1,
            expected_fingerprint="a" * 64,
            current_fingerprint="a" * 64,
            idempotency_key=key,
            request_hash=persistence.hash_request({"key": key}),
        )

    results = await asyncio.gather(confirm("one"), confirm("two"), return_exceptions=True)
    assert sum(getattr(result, "status", None) == "confirmed" for result in results) == 1
    failures = [result for result in results if isinstance(result, AppException)]
    assert len(failures) == 1
    assert failures[0].code == "invalid_recommendation_state"

    verify = pg_session_factory()
    active_count = await verify.scalar(
        select(func.count()).select_from(NutritionRecommendation).where(
            NutritionRecommendation.user_id == user_id,
            NutritionRecommendation.status == "active",
        )
    )
    assert active_count == 1


@requires_pg
@pytest.mark.requires_pg
@pytest.mark.asyncio
async def test_pg_scoped_deletion_removes_self_referenced_version_chain(pg_session):
    if not pg_available:
        pytest.skip(skip_reason)
    from sqlalchemy import func, select

    from app.auth.models import User
    from app.nutrition import persistence
    from app.nutrition.models import NutritionRecommendation

    session = pg_session
    user_id = uuid.uuid4()
    await session.execute(insert(User).values(id=user_id, phone="13810000996"))

    def version(recommendation_id, number, status, source=None):
        return NutritionRecommendation(
            recommendation_id=recommendation_id,
            user_id=user_id,
            version=number,
            status=status,
            change_reason="test",
            source_recommendation_id=source,
            source_context_fingerprint="a" * 64,
            profile_version=1,
            training_plan_version_id=str(uuid.UUID(int=42)),
            checkin_token="b" * 64,
            policy_version="v1",
            catalog_version="v1",
            source_manifest_version="v1",
            media_manifest_version="v1",
            decision_gate="eligible",
            payload={"schema_version": "test"},
            validation_codes=["recommendation_valid"],
            generated_at=datetime.now(timezone.utc),
        )

    old_id, active_id = uuid.uuid4(), uuid.uuid4()
    old = version(old_id, 1, "superseded")
    session.add(old)
    await session.flush()
    active = version(active_id, 2, "active", source=old_id)
    session.add(active)
    await session.flush()
    old.superseded_by_id = active_id
    await session.commit()

    result = await persistence.delete_nutrition_data(session, str(user_id))
    assert result.recommendations_deleted == 2
    remaining = await session.scalar(
        select(func.count()).select_from(NutritionRecommendation).where(
            NutritionRecommendation.user_id == user_id
        )
    )
    assert remaining == 0
