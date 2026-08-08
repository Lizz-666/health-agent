from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.auth.models import User
from app.nutrition.models import NutritionRecommendation
from app.training.models import TrainingPlanVersion, TrainingWeeklyReview
from tests.conftest_pg import pg_available, requires_pg, skip_reason
from tests.test_nutrition_persistence import PINS, _payload

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


def test_0012_offline_upgrade_and_downgrade_are_additive():
    upgrade = _alembic(
        "upgrade", "0011_adaptive_reviews:0012_review_draft_origins", "--sql"
    )
    assert upgrade.returncode == 0, upgrade.stderr
    sql = upgrade.stdout
    assert sql.count("origin_weekly_review_id") >= 2
    assert "ON DELETE SET NULL" in sql
    assert "DROP TABLE training_weekly_reviews" not in sql

    downgrade = _alembic(
        "downgrade", "0012_review_draft_origins:0011_adaptive_reviews", "--sql"
    )
    assert downgrade.returncode == 0, downgrade.stderr
    assert "DROP TABLE training_weekly_reviews" not in downgrade.stdout


def test_0012_online_sqlite_upgrade_and_downgrade(tmp_path):
    database = tmp_path / "review-origin-0012.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database.as_posix()}"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE training_weekly_reviews "
            "(review_id TEXT PRIMARY KEY)"
        )
        connection.execute(
            "CREATE TABLE training_plan_versions "
            "(plan_version_id TEXT PRIMARY KEY)"
        )
        connection.execute(
            "CREATE TABLE nutrition_recommendations "
            "(recommendation_id TEXT PRIMARY KEY)"
        )
    stamp = _alembic("stamp", "0011_adaptive_reviews", database_url=database_url)
    assert stamp.returncode == 0, stamp.stderr
    upgrade = _alembic("upgrade", "0012_review_draft_origins", database_url=database_url)
    assert upgrade.returncode == 0, upgrade.stderr
    with sqlite3.connect(database) as connection:
        for table in ("training_plan_versions", "nutrition_recommendations"):
            columns = {
                row[1] for row in connection.execute(f"PRAGMA table_info('{table}')")
            }
            assert "origin_weekly_review_id" in columns
            foreign_keys = list(
                connection.execute(f"PRAGMA foreign_key_list('{table}')")
            )
            assert any(
                row[2] == "training_weekly_reviews"
                and row[3] == "origin_weekly_review_id"
                and row[6] == "SET NULL"
                for row in foreign_keys
            )

    downgrade = _alembic("downgrade", "0011_adaptive_reviews", database_url=database_url)
    assert downgrade.returncode == 0, downgrade.stderr
    with sqlite3.connect(database) as connection:
        for table in ("training_plan_versions", "nutrition_recommendations"):
            columns = {
                row[1] for row in connection.execute(f"PRAGMA table_info('{table}')")
            }
            assert "origin_weekly_review_id" not in columns


@requires_pg
@pytest.mark.requires_pg
def test_0012_postgresql_downgrade_and_upgrade(pg_dsn):
    if not pg_available:
        pytest.skip(skip_reason)
    downgrade = _alembic(
        "downgrade", "0011_adaptive_reviews", database_url=pg_dsn
    )
    assert downgrade.returncode == 0, downgrade.stderr
    upgrade = _alembic(
        "upgrade", "0012_review_draft_origins", database_url=pg_dsn
    )
    assert upgrade.returncode == 0, upgrade.stderr


@requires_pg
@pytest.mark.requires_pg
@pytest.mark.asyncio
async def test_0012_postgresql_indexes_and_set_null_behavior(pg_session):
    if not pg_available:
        pytest.skip(skip_reason)
    db = pg_session
    indexes = set(
        (
            await db.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE indexname IN ("
                    "'ix_training_plan_versions_origin_weekly_review_id', "
                    "'ix_nutrition_recommendations_origin_weekly_review_id')"
                )
            )
        ).scalars().all()
    )
    assert indexes == {
        "ix_training_plan_versions_origin_weekly_review_id",
        "ix_nutrition_recommendations_origin_weekly_review_id",
    }
    delete_rules = {
        tuple(row)
        for row in (
            await db.execute(
                text(
                    "SELECT constraint_name, delete_rule "
                    "FROM information_schema.referential_constraints "
                    "WHERE constraint_name IN ("
                    "'fk_training_plan_versions_origin_weekly_review_id', "
                    "'fk_nutrition_recommendations_origin_weekly_review_id')"
                )
            )
        ).all()
    }
    assert delete_rules == {
        ("fk_training_plan_versions_origin_weekly_review_id", "SET NULL"),
        ("fk_nutrition_recommendations_origin_weekly_review_id", "SET NULL"),
    }

    user = User(phone="138" + uuid.uuid4().hex[:8])
    db.add(user)
    await db.flush()
    plan = TrainingPlanVersion(
        user_id=user.id,
        requested_goal="general_wellness",
        source_context_fingerprint="a" * 64,
        profile_version=1,
        catalog_version="test",
        policy_version="test",
        source_manifest_version="test",
        weekly_frequency=2,
        session_duration_minutes=30,
        status="active",
        change_reason="test",
        decision_gate="eligible",
        decision_fingerprint="b" * 64,
        generated_at=datetime.now(timezone.utc),
        confirmed_at=datetime.now(timezone.utc),
    )
    db.add(plan)
    await db.flush()
    review = TrainingWeeklyReview(
        user_id=user.id,
        plan_version_id=plan.plan_version_id,
        week_index=1,
        review_version=1,
        input_fingerprint="c" * 64,
        period_start=date(2026, 8, 3),
        period_end=date(2026, 8, 9),
        facts={},
        proposal_codes=[],
        adaptive_policy_version="test",
        training_policy_version="test",
        catalog_version="test",
        source_manifest_version="test",
    )
    db.add(review)
    await db.flush()
    plan.origin_weekly_review_id = review.review_id
    payload = _payload()
    recommendation = NutritionRecommendation(
        user_id=user.id,
        version=1,
        status="active",
        change_reason="test",
        origin_weekly_review_id=review.review_id,
        source_context_fingerprint=payload.source_context_fingerprint,
        profile_version=PINS.profile_version,
        training_plan_version_id=PINS.training_plan_version_id,
        checkin_token=PINS.checkin_token,
        policy_version=payload.versions.policy_version,
        catalog_version=payload.versions.catalog_version,
        source_manifest_version=payload.versions.source_manifest_version,
        media_manifest_version=payload.versions.media_manifest_version,
        decision_gate=payload.decision_gate.value,
        payload=payload.model_dump(mode="json"),
        validation_codes=["validated"],
        generated_at=datetime.now(timezone.utc),
        confirmed_at=datetime.now(timezone.utc),
    )
    db.add(recommendation)
    await db.flush()
    review_id = review.review_id
    await db.delete(review)
    await db.flush()
    await db.refresh(plan)
    await db.refresh(recommendation)
    assert plan.origin_weekly_review_id is None
    assert recommendation.origin_weekly_review_id is None
    assert await db.scalar(
        select(TrainingWeeklyReview.review_id).where(
            TrainingWeeklyReview.review_id == review_id
        )
    ) is None
