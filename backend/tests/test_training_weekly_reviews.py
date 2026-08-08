from __future__ import annotations

import uuid
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.auth.models import User
from app.core.exceptions import AppException
from app.health.models import DailyCheckIn
from app.nutrition.models import NutritionRecommendation
from app.posture.models import PostureAssessmentEvent
from app.training import review_service
from app.training.models import (
    PostureRecheckDismissal,
    TrainingDayAdjustment,
    TrainingPlanVersion,
    TrainingSession,
    TrainingSessionFeedback,
    TrainingWeeklyReview,
)
from app.training.schemas import PlanPrescription, PlanSession, TrainingPlanDraft
from app.training.schemas_api import (
    ExecutionTrendView,
    NutritionReviewView,
    PostureReviewView,
    ReviewGenerateRequest,
    ReviewMutationRequest,
    ReviewProposalView,
    WeightTrendView,
)
from tests.conftest import TestSession
from tests.test_nutrition_persistence import PINS, _payload


TZ = "Asia/Shanghai"
NOW = datetime(2026, 8, 8, 12, tzinfo=timezone.utc)


async def _seed_plan(
    db,
    *,
    confirmed_at=datetime(2026, 7, 27, 1, tzinfo=timezone.utc),
    outcomes=("completed", None),
):
    uid = uuid.uuid4()
    db.add(User(id=uid, phone=f"138{str(uid.int)[-8:]}"))
    plan = TrainingPlanVersion(
        user_id=uid,
        requested_goal="general_wellness",
        source_context_fingerprint="a" * 64,
        profile_version=1,
        catalog_version=review_service.training_service.catalog().content_version,
        policy_version=review_service.training_service.TRAINING_POLICY.policy_version,
        source_manifest_version=(
            review_service.training_service.catalog().source_manifest_version
        ),
        weekly_frequency=2,
        session_duration_minutes=30,
        status="active",
        change_reason="test",
        decision_gate="eligible",
        decision_fingerprint="b" * 64,
        generated_at=confirmed_at,
        confirmed_at=confirmed_at,
    )
    db.add(plan)
    await db.flush()
    sessions = []
    for order, day in enumerate((1, 3), start=1):
        session = TrainingSession(
            plan_version_id=plan.plan_version_id,
            week_index=1,
            day_of_week=day,
            session_order=order,
            target_minutes=30,
        )
        db.add(session)
        sessions.append(session)
    await db.flush()
    period_start = review_service._plan_start(plan, TZ)
    for session, outcome in zip(sessions, outcomes):
        if outcome is not None:
            db.add(
                TrainingSessionFeedback(
                    user_id=uid,
                    plan_version_id=plan.plan_version_id,
                    session_id=session.session_id,
                    local_date=period_start + timedelta(
                        days=session.day_of_week - 1
                    ),
                    outcome_state=outcome,
                )
            )
    await db.commit()
    return str(uid), plan, sessions


def _normal_checkin(user_id: str, local_date) -> DailyCheckIn:
    return DailyCheckIn(
        user_id=uuid.UUID(user_id),
        local_date=local_date,
        sleep_quality="good",
        energy="normal",
        muscle_soreness="none",
        available_time="45_min_plus",
        daily_status="ok",
        abnormal_pain=False,
        pain_followup=None,
        risk_summary="normal",
        risk_version="test-v1",
    )


@pytest.mark.asyncio
async def test_review_missing_execution_is_unavailable_and_replay_is_stable():
    async with TestSession() as db:
        uid, plan, sessions = await _seed_plan(db)
        plan_id = plan.plan_version_id
        second_session_id = sessions[1].session_id
        request = ReviewGenerateRequest(idempotency_key="review-1", iana_timezone=TZ)
        first = await review_service.generate_review(
            db, uid, 1, request, now=NOW
        )
        replay = await review_service.generate_review(
            db, uid, 1, request, now=NOW
        )

        assert first.review_id == replay.review_id
        assert first.review_version == 1
        assert first.execution.scheduled == 2
        assert first.execution.completed == 1
        assert first.execution.unavailable == 1
        assert first.execution.too_busy == 0
        assert all(item.code != "keep_current_plan" for item in first.proposals)

        plan = await db.get(TrainingPlanVersion, plan_id)
        period_start = review_service._plan_start(plan, TZ)
        db.add(
            TrainingSessionFeedback(
                user_id=uuid.UUID(uid),
                plan_version_id=plan.plan_version_id,
                session_id=second_session_id,
                local_date=period_start.replace(day=period_start.day + 2),
                outcome_state="completed",
            )
        )
        await db.commit()
        changed = await review_service.generate_review(
            db,
            uid,
            1,
            ReviewGenerateRequest(idempotency_key="review-2", iana_timezone=TZ),
            now=NOW,
        )
        assert changed.review_id != first.review_id
        assert changed.review_version == 2
        assert changed.execution.completed == 2
        assert changed.execution.unavailable == 0

        plan.status = "superseded"
        replacement = TrainingPlanVersion(
            user_id=uuid.UUID(uid),
            requested_goal=plan.requested_goal,
            source_context_fingerprint="e" * 64,
            profile_version=plan.profile_version,
            catalog_version=plan.catalog_version,
            policy_version=plan.policy_version,
            source_manifest_version=plan.source_manifest_version,
            weekly_frequency=plan.weekly_frequency,
            session_duration_minutes=plan.session_duration_minutes,
            status="active",
            change_reason="test_replacement",
            decision_gate="eligible",
            decision_fingerprint="f" * 64,
            generated_at=NOW,
            confirmed_at=NOW,
        )
        db.add(replacement)
        await db.commit()
        historical = await review_service.get_review(db, uid, 1)
        assert historical.review_id == changed.review_id


def test_weight_direction_cannot_change_training_proposal():
    execution = {
        "scheduled": 3,
        "effective": 3,
        "completed": 1,
        "partial": 0,
        "too_busy": 2,
        "intentional_rest": 0,
        "discomfort": 0,
        "active_rest": 0,
        "safety_adjustment": 0,
        "unavailable": 0,
    }
    adjustments = {
        "shortened": 0,
        "recovery": 0,
        "deferred": 0,
        "active_rest": 0,
        "unchanged": 0,
        "missing": 0,
        "unavailable": 0,
    }
    expected = review_service.training_proposal(
        execution,
        adjustments,
        weekly_frequency=3,
        session_duration_minutes=30,
    )
    for _weight_direction in ("rising", "falling", "stable", None):
        assert review_service.training_proposal(
            execution,
            adjustments,
            weekly_frequency=3,
            session_duration_minutes=30,
        ) == expected
    assert expected == "conservative_duration"
    assert review_service.training_proposal(
        execution,
        adjustments,
        weekly_frequency=3,
        session_duration_minutes=30,
        safety_blocked=True,
    ) is None


def test_progression_requires_explicit_complete_cycle_gate():
    execution = {
        "scheduled": 2,
        "effective": 2,
        "completed": 2,
        "partial": 0,
        "too_busy": 0,
        "intentional_rest": 0,
        "discomfort": 0,
        "active_rest": 0,
        "safety_adjustment": 0,
        "unavailable": 0,
    }
    adjustments = {key: 0 for key in (
        "shortened", "recovery", "deferred", "active_rest", "unchanged",
        "missing", "unavailable",
    )}
    assert review_service.training_proposal(
        execution,
        adjustments,
        weekly_frequency=2,
        session_duration_minutes=30,
    ) is None
    assert review_service.training_proposal(
        execution,
        adjustments,
        weekly_frequency=2,
        session_duration_minutes=30,
        cycle_progression_eligible=True,
    ) == "progression"


def test_no_data_trend_and_overlapping_pressure_fail_closed():
    no_data = {
        "effective": 2,
        "completed": 0,
        "unavailable": 2,
    }
    observed = {
        "effective": 2,
        "completed": 1,
        "unavailable": 0,
    }
    assert review_service._trend(no_data, observed) == {
        "available": False,
        "direction": None,
    }
    execution = {
        "scheduled": 2,
        "effective": 2,
        "completed": 1,
        "partial": 0,
        "too_busy": 1,
        "intentional_rest": 0,
        "discomfort": 0,
        "active_rest": 0,
        "safety_adjustment": 0,
        "unavailable": 0,
    }
    adjustments = {
        key: (1 if key == "deferred" else 0)
        for key in (
            "shortened",
            "recovery",
            "deferred",
            "active_rest",
            "unchanged",
            "missing",
            "unavailable",
        )
    }
    assert review_service.training_proposal(
        execution,
        adjustments,
        weekly_frequency=3,
        session_duration_minutes=30,
        schedule_pressure_count=1,
    ) is None


def test_backend_review_state_combinations_match_flutter_contract():
    with pytest.raises(ValidationError):
        ExecutionTrendView(available=True, direction=None)
    with pytest.raises(ValidationError):
        WeightTrendView(available=False, direction="rising")
    with pytest.raises(ValidationError):
        PostureReviewView(
            status="comparison_available",
            comparison_signal="changed",
        )
    with pytest.raises(ValidationError):
        NutritionReviewView(
            state="unavailable",
            age_days=None,
            refresh_available=True,
            unavailable_reason="nutrition_runtime_disabled",
        )
    with pytest.raises(ValidationError):
        NutritionReviewView(
            state="active",
            age_days=1,
            refresh_available=False,
            unavailable_reason=None,
            recommendation_id=None,
            version=None,
        )
    with pytest.raises(ValidationError):
        ReviewProposalView(
            code="offer_training_draft",
            state="proposal",
        )


@pytest.mark.asyncio
async def test_nutrition_refresh_uses_phase6_candidate_pins(monkeypatch):
    payload = _payload()
    candidate = SimpleNamespace(payload=payload, pins=PINS)
    active = SimpleNamespace(
        recommendation_id=uuid.uuid4(),
        version=4,
        generated_at=NOW - timedelta(days=5),
        profile_version=PINS.profile_version,
        training_plan_version_id=PINS.training_plan_version_id,
        checkin_token=PINS.checkin_token,
        source_context_fingerprint=payload.source_context_fingerprint,
    )
    monkeypatch.setattr(
        review_service.nutrition_persistence,
        "get_active",
        lambda *_args, **_kwargs: _async_value(active),
    )
    monkeypatch.setattr(
        review_service.nutrition_service,
        "prepare_draft_domain",
        lambda *_args, **_kwargs: _async_value(candidate),
    )
    current = await review_service._nutrition_facts(
        None, "owner", TZ, NOW
    )
    assert current == {
        "state": "active",
        "age_days": 5,
        "refresh_available": False,
        "unavailable_reason": None,
        "recommendation_id": str(active.recommendation_id),
        "version": 4,
    }
    active.source_context_fingerprint = "f" * 64
    stale = await review_service._nutrition_facts(None, "owner", TZ, NOW)
    assert stale["state"] == "stale"
    assert stale["refresh_available"] is True

    async def blocked(*_args, **_kwargs):
        raise AppException(409, "blocked", "nutrition_restricted")

    monkeypatch.setattr(
        review_service.nutrition_service,
        "prepare_draft_domain",
        blocked,
    )
    unavailable = await review_service._nutrition_facts(
        None, "owner", TZ, NOW
    )
    assert unavailable["state"] == "unavailable"
    assert unavailable["refresh_available"] is False
    assert unavailable["unavailable_reason"] == "nutrition_restricted"


@pytest.mark.asyncio
async def test_nutrition_version_identity_creates_new_review(monkeypatch):
    async with TestSession() as db:
        uid, _plan, _sessions = await _seed_plan(
            db, outcomes=("completed", "completed")
        )
        payload = _payload()
        candidate = SimpleNamespace(payload=payload, pins=PINS)
        active = SimpleNamespace(
            recommendation_id=uuid.uuid4(),
            version=1,
            generated_at=NOW - timedelta(days=1),
            profile_version=PINS.profile_version,
            training_plan_version_id=PINS.training_plan_version_id,
            checkin_token=PINS.checkin_token,
            source_context_fingerprint=payload.source_context_fingerprint,
        )
        monkeypatch.setattr(
            review_service.nutrition_persistence,
            "get_active",
            lambda *_args, **_kwargs: _async_value(active),
        )
        monkeypatch.setattr(
            review_service.nutrition_service,
            "prepare_draft_domain",
            lambda *_args, **_kwargs: _async_value(candidate),
        )
        first = await review_service.generate_review(
            db,
            uid,
            1,
            ReviewGenerateRequest(
                idempotency_key="nutrition-version-1",
                iana_timezone=TZ,
            ),
            now=NOW,
        )
        active.recommendation_id = uuid.uuid4()
        active.version = 2
        second = await review_service.generate_review(
            db,
            uid,
            1,
            ReviewGenerateRequest(
                idempotency_key="nutrition-version-2",
                iana_timezone=TZ,
            ),
            now=NOW,
        )
        assert second.review_id != first.review_id
        assert second.review_version == first.review_version + 1
        assert second.nutrition.version == 2


@pytest.mark.asyncio
async def test_posture_identity_changes_fingerprint_before_cycle_end():
    async with TestSession() as db:
        uid, _plan, _sessions = await _seed_plan(
            db, outcomes=("completed", "completed")
        )
        first = await review_service.generate_review(
            db,
            uid,
            1,
            ReviewGenerateRequest(
                idempotency_key="posture-identity-1",
                iana_timezone=TZ,
            ),
            now=NOW,
        )
        db.add(
            PostureAssessmentEvent(
                user_id=uuid.UUID(uid),
                issue_id="forward_head",
                source="self_test",
                severity="mild",
                lifecycle="active",
                content_version="test-v2",
                created_at=NOW - timedelta(hours=1),
            )
        )
        await db.commit()
        second = await review_service.generate_review(
            db,
            uid,
            1,
            ReviewGenerateRequest(
                idempotency_key="posture-identity-2",
                iana_timezone=TZ,
            ),
            now=NOW,
        )
        assert first.posture.status == "not_due"
        assert second.posture.status == "not_due"
        assert second.review_id != first.review_id
        assert second.review_version == first.review_version + 1


@pytest.mark.asyncio
async def test_complete_four_week_cycle_offers_progression(monkeypatch):
    async with TestSession() as db:
        monkeypatch.setattr(
            review_service,
            "_current_training_safety",
            lambda *_args, **_kwargs: _async_value(
                {
                    "gate": "eligible",
                    "blocked": False,
                    "reason_codes": [],
                    "missing_fields": [],
                }
            ),
        )
        uid, plan, _sessions = await _seed_plan(
            db,
            confirmed_at=datetime(2026, 6, 29, 1, tzinfo=timezone.utc),
            outcomes=("completed", "completed"),
        )
        plan_start = review_service._plan_start(plan, TZ)
        checkin_dates = {
            plan_start + timedelta(days=day - 1) for day in (1, 3)
        }
        for week in (2, 3, 4):
            for order, day in enumerate((1, 3), start=1):
                session = TrainingSession(
                    plan_version_id=plan.plan_version_id,
                    week_index=week,
                    day_of_week=day,
                    session_order=order,
                    target_minutes=30,
                )
                db.add(session)
                await db.flush()
                db.add(
                    TrainingSessionFeedback(
                        user_id=uuid.UUID(uid),
                        plan_version_id=plan.plan_version_id,
                        session_id=session.session_id,
                        local_date=plan_start
                        + timedelta(days=(week - 1) * 7 + day - 1),
                        outcome_state="completed",
                    )
                )
                checkin_dates.add(
                    plan_start + timedelta(days=(week - 1) * 7 + day - 1)
                )
        db.add_all(
            [_normal_checkin(uid, local_date) for local_date in checkin_dates]
        )
        db.add(_normal_checkin(uid, plan_start + timedelta(days=1)))
        await db.commit()
        review = await review_service.generate_review(
            db,
            uid,
            4,
            ReviewGenerateRequest(
                idempotency_key="review-progression", iana_timezone=TZ
            ),
            now=NOW,
        )
        training = next(
            item for item in review.proposals
            if item.code == "offer_training_draft"
        )
        assert training.strategy == "progression"


@pytest.mark.asyncio
async def test_period_fatigue_blocks_progression_not_recovery_regression():
    async with TestSession() as db:
        uid, plan, _sessions = await _seed_plan(
            db, outcomes=("completed", "completed")
        )
        period_start, _period_end = review_service._period(plan, 1, TZ)
        first = _normal_checkin(uid, period_start)
        first.energy = "low"
        second = _normal_checkin(uid, period_start + timedelta(days=2))
        second.muscle_soreness = "significant"
        db.add_all([first, second])
        await db.commit()
        safety = await review_service._period_safety(
            db, uid, [period_start, period_start + timedelta(days=2)]
        )
        assert safety["blocked"] is False
        assert safety["progression_blocked"] is True
        execution = {
            "scheduled": 2,
            "effective": 2,
            "completed": 2,
            "partial": 0,
            "too_busy": 0,
            "intentional_rest": 0,
            "discomfort": 0,
            "active_rest": 0,
            "safety_adjustment": 2,
            "unavailable": 0,
        }
        adjustments = {
            key: (2 if key == "recovery" else 0)
            for key in (
                "shortened",
                "recovery",
                "deferred",
                "active_rest",
                "unchanged",
                "missing",
                "unavailable",
            )
        }
        assert review_service.training_proposal(
            execution,
            adjustments,
            weekly_frequency=2,
            session_duration_minutes=30,
            safety_blocked=safety["blocked"],
        ) == "regression"


@pytest.mark.asyncio
async def test_cross_week_deferral_is_counted_in_effective_target_week():
    async with TestSession() as db:
        uid, plan, sessions = await _seed_plan(
            db, outcomes=("completed", None)
        )
        week1_start, week1_end = review_service._period(plan, 1, TZ)
        week2_start, week2_end = review_service._period(plan, 2, TZ)
        target_date = week2_start
        db.add(
            TrainingDayAdjustment(
                user_id=uuid.UUID(uid),
                plan_version_id=plan.plan_version_id,
                source_session_id=sessions[1].session_id,
                source_local_date=week1_start + timedelta(days=2),
                target_local_date=target_date,
                adjustment_kind="deferred",
                trigger_code="no_time",
                reason_codes=["deferred"],
                source_context_fingerprint="c" * 64,
                decision_fingerprint="d" * 64,
                adaptive_policy_version=(
                    review_service.training_service.ADAPTIVE_POLICY.policy_version
                ),
                training_policy_version=plan.policy_version,
                catalog_version=plan.catalog_version,
                source_manifest_version=plan.source_manifest_version,
                surface="button",
                target_minutes=None,
            )
        )
        db.add(
            TrainingSessionFeedback(
                user_id=uuid.UUID(uid),
                plan_version_id=plan.plan_version_id,
                session_id=sessions[1].session_id,
                local_date=target_date,
                outcome_state="completed",
            )
        )
        await db.commit()
        week1, adjustments, _metrics = await review_service._execution_facts(
            db, uid, plan, 1, week1_start, week1_end
        )
        week2, _adjustments, _metrics = await review_service._execution_facts(
            db, uid, plan, 2, week2_start, week2_end
        )
        assert week1["scheduled"] == 2
        assert week1["effective"] == 1
        assert week1["completed"] == 1
        assert adjustments["deferred"] == 1
        assert week2["scheduled"] == 0
        assert week2["effective"] == 1
        assert week2["completed"] == 1


@pytest.mark.asyncio
async def test_review_training_draft_records_origin_without_activation(monkeypatch):
    async with TestSession() as db:
        monkeypatch.setattr(
            review_service.training_service,
            "_profile_equipment",
            lambda *_args, **_kwargs: _async_value((True, False)),
        )
        monkeypatch.setattr(
            review_service,
            "_current_training_safety",
            lambda *_args, **_kwargs: _async_value(
                {
                    "gate": "eligible",
                    "blocked": False,
                    "reason_codes": [],
                    "missing_fields": [],
                }
            ),
        )
        uid, active, _sessions = await _seed_plan(
            db, outcomes=("too_busy", "too_busy")
        )
        period_start = review_service._plan_start(active, TZ)
        db.add_all(
            [
                _normal_checkin(uid, period_start),
                _normal_checkin(uid, period_start + timedelta(days=2)),
            ]
        )
        await db.commit()
        review = await review_service.generate_review(
            db,
            uid,
            1,
            ReviewGenerateRequest(idempotency_key="review-busy", iana_timezone=TZ),
            now=NOW,
        )
        row = await db.get(TrainingWeeklyReview, uuid.UUID(review.review_id))
        assert row is not None

        draft = TrainingPlanDraft(
            draft_id="review-draft",
            requested_goal="general_wellness",
            source_context_fingerprint="c" * 64,
            profile_version=1,
            catalog_version=active.catalog_version,
            policy_version=active.policy_version,
            source_manifest_version=active.source_manifest_version,
            sessions=[
                PlanSession(
                    week_index=week,
                    day_of_week=1,
                    session_order=1,
                    target_minutes=15,
                    prescriptions=[
                        PlanPrescription(
                            exercise_id="synthetic_exercise",
                            sets=1,
                            reps=5,
                            rest_seconds=30,
                        )
                    ],
                )
                for week in range(1, 5)
            ],
        )
        monkeypatch.setattr(
            review_service.training_service,
            "evaluate_draft_request",
            lambda *_args, **_kwargs: _async_value(
                SimpleNamespace(
                    draft=draft,
                    weekly_frequency=2,
                    session_duration_minutes=15,
                    decision_gate="eligible",
                    decision_fingerprint="d" * 64,
                )
            ),
        )
        result = await review_service.create_training_draft(
            db,
            uid,
            1,
            ReviewMutationRequest(
                idempotency_key="review-training-draft",
                expected_review_id=row.review_id,
                expected_input_fingerprint=row.input_fingerprint,
                iana_timezone=TZ,
            ),
            now=NOW,
        )
        created = await db.get(TrainingPlanVersion, uuid.UUID(result.draft_id))
        await db.refresh(active)
        assert created is not None
        assert created.status == "draft"
        assert created.origin_weekly_review_id == row.review_id
        assert active.status == "active"
        created.status = "superseded"
        await db.commit()
        projected = await review_service.get_review(db, uid, 1)
        proposal = next(
            item
            for item in projected.proposals
            if item.code == "offer_training_draft"
        )
        assert proposal.state == "unavailable"


@pytest.mark.asyncio
async def test_review_nutrition_draft_records_origin_without_activation(monkeypatch):
    async with TestSession() as db:
        monkeypatch.setattr(
            review_service.nutrition_service,
            "prepare_draft_domain",
            lambda *_args, **_kwargs: _async_value(
                SimpleNamespace(payload=_payload(), pins=PINS)
            ),
        )
        uid, _active, _sessions = await _seed_plan(
            db, outcomes=("completed", "completed")
        )
        review = await review_service.generate_review(
            db,
            uid,
            1,
            ReviewGenerateRequest(
                idempotency_key="review-nutrition", iana_timezone=TZ
            ),
            now=NOW,
        )
        row = await db.get(TrainingWeeklyReview, uuid.UUID(review.review_id))
        review_id = row.review_id
        request = ReviewMutationRequest(
            idempotency_key="review-nutrition-draft",
            expected_review_id=row.review_id,
            expected_input_fingerprint=row.input_fingerprint,
            iana_timezone=TZ,
        )
        created = await review_service.create_nutrition_draft(
            db, uid, 1, request, now=NOW
        )
        replay = await review_service.create_nutrition_draft(
            db, uid, 1, request, now=NOW
        )
        recommendation = await db.get(
            NutritionRecommendation, uuid.UUID(created.draft_id)
        )
        assert replay.draft_id == created.draft_id
        assert recommendation is not None
        assert recommendation.status == "draft"
        assert recommendation.origin_weekly_review_id == review_id
        active = await review_service.nutrition_persistence.get_active(db, uid)
        assert active is None

        await review_service.P.delete_adaptive_data(db, uid)
        preserved = await db.get(
            NutritionRecommendation, uuid.UUID(created.draft_id)
        )
        assert preserved is not None
        assert preserved.status == "draft"
        assert preserved.origin_weekly_review_id is None


async def _async_value(value):
    return value


@pytest.mark.asyncio
async def test_cycle_posture_dismissal_is_owner_scoped_and_idempotent():
    async with TestSession() as db:
        uid, plan, _sessions = await _seed_plan(
            db,
            confirmed_at=datetime(2026, 6, 29, 1, tzinfo=timezone.utc),
            outcomes=("completed", "completed"),
        )
        db.add(
            PostureAssessmentEvent(
                user_id=uuid.UUID(uid),
                issue_id="forward_head",
                source="self_test",
                severity="mild",
                lifecycle="active",
                created_at=datetime(2026, 6, 28, 1, tzinfo=timezone.utc),
            )
        )
        for week in (2, 3, 4):
            db.add(
                TrainingSession(
                    plan_version_id=plan.plan_version_id,
                    week_index=week,
                    day_of_week=1,
                    session_order=1,
                    target_minutes=30,
                )
            )
        await db.commit()
        review = await review_service.generate_review(
            db,
            uid,
            4,
            ReviewGenerateRequest(idempotency_key="review-cycle", iana_timezone=TZ),
            now=NOW,
        )
        assert review.posture.status == "due"
        row = await db.get(TrainingWeeklyReview, uuid.UUID(review.review_id))
        request = ReviewMutationRequest(
            idempotency_key="dismiss-cycle",
            expected_review_id=row.review_id,
            expected_input_fingerprint=row.input_fingerprint,
            iana_timezone=TZ,
        )
        first = await review_service.dismiss_posture_recheck(
            db, uid, 4, request, now=NOW
        )
        replay = await review_service.dismiss_posture_recheck(
            db, uid, 4, request, now=NOW
        )
        assert replay.dismissal_id == first.dismissal_id
        rows = list(
            (
                await db.execute(
                    select(PostureRecheckDismissal).where(
                        PostureRecheckDismissal.user_id == uuid.UUID(uid)
                    )
                )
            ).scalars().all()
        )
        assert len(rows) == 1
        projected = await review_service.get_review(db, uid, 4)
        assert projected.posture.status == "not_due"
        assert projected.posture.reason == "dismissed_for_cycle"
        assert projected.safety is not None
        assert all(
            proposal.code != "posture_recheck_due"
            for proposal in projected.proposals
        )
        db.add(
            PostureAssessmentEvent(
                user_id=uuid.UUID(uid),
                issue_id="forward_head",
                source="self_test",
                severity="normal",
                lifecycle="active",
                created_at=datetime(2026, 7, 27, 1, tzinfo=timezone.utc),
            )
        )
        await db.commit()
        comparison = await review_service.generate_review(
            db,
            uid,
            4,
            ReviewGenerateRequest(
                idempotency_key="review-cycle-after-comparison",
                iana_timezone=TZ,
            ),
            now=NOW,
        )
        assert comparison.posture.status == "comparison_available"
        assert any(
            proposal.code == "posture_comparison_available"
            for proposal in comparison.proposals
        )


@pytest.mark.asyncio
async def test_cycle_posture_comparison_persists_only_structured_summary():
    async with TestSession() as db:
        uid, plan, _sessions = await _seed_plan(
            db,
            confirmed_at=datetime(2026, 6, 29, 1, tzinfo=timezone.utc),
            outcomes=("completed", "completed"),
        )
        baseline_at = datetime(2026, 6, 28, 1, tzinfo=timezone.utc)
        before_local_cycle_end = datetime(2026, 7, 26, 15, 30, tzinfo=timezone.utc)
        comparison_at = datetime(2026, 7, 26, 17, tzinfo=timezone.utc)
        comparison_later = datetime(2026, 7, 26, 18, tzinfo=timezone.utc)
        db.add_all(
            [
                PostureAssessmentEvent(
                    user_id=uuid.UUID(uid),
                    issue_id="forward_head",
                    source="self_test",
                    severity="mild",
                    lifecycle="active",
                    created_at=baseline_at,
                ),
                PostureAssessmentEvent(
                    user_id=uuid.UUID(uid),
                    issue_id="forward_head",
                    source="self_test",
                    severity="severe",
                    lifecycle="superseded",
                    created_at=before_local_cycle_end,
                ),
                PostureAssessmentEvent(
                    user_id=uuid.UUID(uid),
                    issue_id="forward_head",
                    source="self_test",
                    severity="normal",
                    lifecycle="active",
                    created_at=comparison_at,
                ),
                PostureAssessmentEvent(
                    user_id=uuid.UUID(uid),
                    issue_id="forward_head",
                    source="ai_photo",
                    severity="moderate",
                    lifecycle="active",
                    created_at=comparison_later,
                ),
            ]
        )
        for week in (2, 3, 4):
            db.add(
                TrainingSession(
                    plan_version_id=plan.plan_version_id,
                    week_index=week,
                    day_of_week=1,
                    session_order=1,
                    target_minutes=30,
                )
            )
        await db.commit()

        review = await review_service.generate_review(
            db,
            uid,
            4,
            ReviewGenerateRequest(
                idempotency_key="review-posture-comparison",
                iana_timezone=TZ,
            ),
            now=NOW,
        )
        assert review.posture.status == "comparison_available"
        assert review.posture.comparison_signal == "changed"
        assert review.posture.comparison_at == comparison_later
        assert review.posture.comparison_sources == ["ai_photo", "self_test"]
        row = await db.get(TrainingWeeklyReview, uuid.UUID(review.review_id))
        serialized = json.dumps(row.facts["posture"], sort_keys=True)
        assert set(row.facts["posture"]) == {
            "status",
            "comparison_signal",
            "baseline_at",
            "comparison_at",
            "baseline_sources",
            "comparison_sources",
            "_assessment_identity",
        }
        assert "photo_keys" not in serialized
        assert "ai_response" not in serialized
        assert "self_test_answers" not in serialized
        assert "note" not in serialized
