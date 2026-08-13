from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from app.auth.models import User
from app.core.config import settings
from app.health import service as health_service
from app.health.models import DailyCheckIn, HealthProfile, WeightRecord
from app.nutrition.models import NutritionRecommendation
from app.posture import purge
from app.training.models import (
    TrainingPlanVersion,
    TrainingPrescription,
    TrainingSession,
    TrainingSessionFeedback,
    TrainingSessionSubstitution,
)
from tests.conftest import TestSession
from tests.conftest_pg import requires_pg


_PURGE_KEY = "0123456789abcdef" * 4


async def _add_user(db, *, phone: str) -> uuid.UUID:
    user = User(phone=phone)
    db.add(user)
    await db.flush()
    return user.id


def _plan(user_id: uuid.UUID) -> TrainingPlanVersion:
    now = datetime.now(timezone.utc)
    return TrainingPlanVersion(
        user_id=user_id,
        requested_goal="general_wellness",
        source_context_fingerprint="a" * 64,
        profile_version=1,
        catalog_version="catalog-v1",
        policy_version="policy-v1",
        source_manifest_version="manifest-v1",
        weekly_frequency=2,
        session_duration_minutes=30,
        status="active",
        change_reason="test",
        decision_gate="eligible",
        decision_fingerprint="b" * 64,
        generated_at=now,
        confirmed_at=now,
    )


def _recommendation(user_id: uuid.UUID) -> NutritionRecommendation:
    return NutritionRecommendation(
        user_id=user_id,
        version=1,
        status="active",
        change_reason="test",
        source_context_fingerprint="c" * 64,
        profile_version=1,
        training_plan_version_id="synthetic-plan",
        checkin_token="d" * 64,
        policy_version="nutrition-v1",
        catalog_version="foods-v1",
        source_manifest_version="sources-v1",
        media_manifest_version="media-v1",
        decision_gate="eligible",
        payload={},
        validation_codes=["validated"],
        generated_at=datetime.now(timezone.utc),
        confirmed_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_account_deletion_detects_and_removes_health_only(monkeypatch):
    monkeypatch.setattr(settings, "PURGE_ENCRYPTION_KEY", _PURGE_KEY)
    async with TestSession() as db:
        owner = await _add_user(db, phone="13800001001")
        other = await _add_user(db, phone="13800001002")
        for user_id in (owner, other):
            db.add(HealthProfile(user_id=user_id, version=1))
            db.add(
                DailyCheckIn(
                    user_id=user_id,
                    local_date=date(2026, 8, 9),
                    sleep_quality="good",
                    energy="normal",
                    muscle_soreness="none",
                    available_time="30_min",
                    daily_status="ready",
                    abnormal_pain=False,
                    risk_summary="normal",
                    risk_version="risk-v1",
                )
            )
            db.add(
                WeightRecord(
                    user_id=user_id,
                    recorded_at=datetime.now(timezone.utc),
                    weight_kg=70,
                    source="manual",
                )
            )
        await db.commit()

    async with TestSession() as db:
        result = await purge.run_purge(
            db, owner, purge.FakeObjectStore(), trigger="account_deletion"
        )
        assert result.status == "completed"

    async with TestSession() as db:
        for model in (HealthProfile, DailyCheckIn, WeightRecord):
            assert await db.scalar(
                select(model).where(model.user_id == owner)
            ) is None
            assert await db.scalar(
                select(model).where(model.user_id == other)
            ) is not None


@pytest.mark.asyncio
async def test_account_deletion_detects_and_removes_base_training_graph(monkeypatch):
    monkeypatch.setattr(settings, "PURGE_ENCRYPTION_KEY", _PURGE_KEY)
    async with TestSession() as db:
        owner = await _add_user(db, phone="13800001003")
        other = await _add_user(db, phone="13800001013")
        plan = _plan(owner)
        other_plan = _plan(other)
        db.add(plan)
        db.add(other_plan)
        await db.flush()
        session = TrainingSession(
            plan_version_id=plan.plan_version_id,
            week_index=1,
            day_of_week=1,
            session_order=1,
            target_minutes=30,
        )
        db.add(session)
        other_session = TrainingSession(
            plan_version_id=other_plan.plan_version_id,
            week_index=1,
            day_of_week=1,
            session_order=1,
            target_minutes=30,
        )
        db.add(other_session)
        await db.flush()
        prescription = TrainingPrescription(
            session_id=session.session_id,
            exercise_id="ex-1",
            sets=2,
            reps=8,
            rest_seconds=30,
            display_order=0,
        )
        db.add(prescription)
        db.add(
            TrainingSessionFeedback(
                user_id=owner,
                plan_version_id=plan.plan_version_id,
                session_id=session.session_id,
                local_date=date(2026, 8, 9),
                outcome_state="completed",
            )
        )
        db.add(
            TrainingSessionSubstitution(
                user_id=owner,
                plan_version_id=plan.plan_version_id,
                session_id=session.session_id,
                local_date=date(2026, 8, 9),
                original_exercise_id="ex-1",
                replacement_exercise_id="ex-2",
                relation_reason="same_pattern",
                decision_gate="eligible",
            )
        )
        await db.commit()
        plan_id = plan.plan_version_id
        session_id = session.session_id
        prescription_id = prescription.prescription_id
        other_plan_id = other_plan.plan_version_id
        other_session_id = other_session.session_id

    async with TestSession() as db:
        result = await purge.run_purge(
            db, owner, purge.FakeObjectStore(), trigger="account_deletion"
        )
        assert result.status == "completed"

    async with TestSession() as db:
        assert await db.get(TrainingPlanVersion, plan_id) is None
        assert await db.get(TrainingSession, session_id) is None
        assert await db.get(TrainingPrescription, prescription_id) is None
        assert await db.get(TrainingPlanVersion, other_plan_id) is not None
        assert await db.get(TrainingSession, other_session_id) is not None
        assert await db.scalar(
            select(TrainingSessionFeedback).where(
                TrainingSessionFeedback.user_id == owner
            )
        ) is None
        assert await db.scalar(
            select(TrainingSessionSubstitution).where(
                TrainingSessionSubstitution.user_id == owner
            )
        ) is None


@pytest.mark.asyncio
async def test_account_deletion_detects_and_removes_nutrition_only(monkeypatch):
    monkeypatch.setattr(settings, "PURGE_ENCRYPTION_KEY", _PURGE_KEY)
    async with TestSession() as db:
        owner = await _add_user(db, phone="13800001004")
        other = await _add_user(db, phone="13800001005")
        owner_row = _recommendation(owner)
        other_row = _recommendation(other)
        db.add_all((owner_row, other_row))
        await db.commit()
        owner_id = owner_row.recommendation_id
        other_id = other_row.recommendation_id

    async with TestSession() as db:
        result = await purge.run_purge(
            db, owner, purge.FakeObjectStore(), trigger="account_deletion"
        )
        assert result.status == "completed"

    async with TestSession() as db:
        assert await db.get(NutritionRecommendation, owner_id) is None
        assert await db.get(NutritionRecommendation, other_id) is not None


@pytest.mark.asyncio
async def test_account_deletion_rolls_back_prior_domain_deletes_on_late_failure(
    monkeypatch,
):
    monkeypatch.setattr(settings, "PURGE_ENCRYPTION_KEY", _PURGE_KEY)
    async with TestSession() as db:
        owner = await _add_user(db, phone="13800001014")
        profile = HealthProfile(user_id=owner, version=1)
        plan = _plan(owner)
        recommendation = _recommendation(owner)
        db.add_all((profile, plan, recommendation))
        await db.commit()
        profile_id = profile.id
        plan_id = plan.plan_version_id
        recommendation_id = recommendation.recommendation_id

    async def fail_after_prior_domains(_db, _user_id):
        raise RuntimeError("synthetic late health-delete failure")

    monkeypatch.setattr(
        health_service,
        "delete_all_health_data",
        fail_after_prior_domains,
    )
    async with TestSession() as db:
        result = await purge.run_purge(
            db,
            owner,
            purge.FakeObjectStore(),
            trigger="account_deletion",
        )

    assert result.status == "failed_db_retry"
    assert result.tombstone_receipt_id is None
    async with TestSession() as db:
        assert await db.get(HealthProfile, profile_id) is not None
        assert await db.get(TrainingPlanVersion, plan_id) is not None
        assert await db.get(NutritionRecommendation, recommendation_id) is not None


@requires_pg
@pytest.mark.requires_pg
async def test_pg_account_deletion_removes_base_cross_domain_rows(pg_session):
    owner = await _add_user(pg_session, phone="13800001006")
    pg_session.add(HealthProfile(user_id=owner, version=1))
    plan = _plan(owner)
    pg_session.add(plan)
    await pg_session.flush()
    session = TrainingSession(
        plan_version_id=plan.plan_version_id,
        week_index=1,
        day_of_week=1,
        session_order=1,
        target_minutes=30,
    )
    pg_session.add(session)
    await pg_session.flush()
    prescription = TrainingPrescription(
        session_id=session.session_id,
        exercise_id="ex-1",
        sets=2,
        reps=8,
        rest_seconds=30,
        display_order=0,
    )
    recommendation = _recommendation(owner)
    pg_session.add_all((prescription, recommendation))
    await pg_session.commit()
    plan_id = plan.plan_version_id
    session_id = session.session_id
    prescription_id = prescription.prescription_id
    recommendation_id = recommendation.recommendation_id

    result = await purge.run_purge(
        pg_session,
        owner,
        purge.FakeObjectStore(),
        trigger="account_deletion",
        encryption_key=_PURGE_KEY,
    )
    assert result.status == "completed"
    assert result.steps.index("delete_training_data") < result.steps.index(
        "delete_nutrition_data"
    )
    assert result.steps.index("delete_nutrition_data") < result.steps.index(
        "delete_health_data"
    )
    assert await pg_session.scalar(
        select(HealthProfile).where(HealthProfile.user_id == owner)
    ) is None
    assert await pg_session.get(TrainingPlanVersion, plan_id) is None
    assert await pg_session.get(TrainingSession, session_id) is None
    assert await pg_session.get(TrainingPrescription, prescription_id) is None
    assert await pg_session.get(NutritionRecommendation, recommendation_id) is None
