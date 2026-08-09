"""Phase 7 synthetic adaptive-closure end-to-end acceptance."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.agent.provider import DashScopeProvider
from app.auth.models import User
from app.core.config import settings
from app.core.security import create_access_token
from app.health.models import DailyCheckIn, HealthProfile, WeightRecord
from app.nutrition.models import NutritionRecommendation
from app.nutrition.schemas import (
    DayKind,
    NutritionContext,
    NutritionVersions,
    WeightSource,
)
from app.posture.models import PostureAssessmentEvent
from app.training import review_service, service as training_service
from app.training.models import (
    TrainingDayAdjustment,
    TrainingPlanVersion,
    TrainingSession,
    TrainingSessionFeedback,
    TrainingWeeklyReview,
)
from app.training.safety import classify_safety, load_safety_policy
from app.training.schemas import TrainingSafetyContext
from tests.conftest import TestSession

pytestmark = pytest.mark.asyncio

TZ = "Asia/Shanghai"
PLAN_START = datetime(2026, 7, 27, 1, tzinfo=timezone.utc)
REVIEW_NOW = datetime(2026, 8, 24, 1, tzinfo=timezone.utc)
SAFETY_POLICY = load_safety_policy(
    "app/training/data/training_safety_policy.v1.json"
)
NO_SCREEN = {
    "underage": "no",
    "pregnancy_or_postpartum": "no",
    "recent_surgery_or_major_injury": "no",
    "major_chronic_condition": "no",
    "eating_disorder_concern": "no",
    "professional_instruction_limitations": "no",
}
NUTRITION_VERSIONS = NutritionVersions(
    policy_version="v1",
    catalog_version="v1",
    source_manifest_version="v1",
    media_manifest_version="v1",
)


@pytest.fixture(autouse=True)
def _synthetic_runtime(monkeypatch):
    monkeypatch.setattr(settings, "NUTRITION_RUNTIME_ENABLED", True)

    async def forbidden_provider_call(*_args, **_kwargs):
        raise AssertionError("Phase 7 deterministic E2E must not call live AI")

    monkeypatch.setattr(DashScopeProvider, "decide", forbidden_provider_call)


async def _seed_user() -> tuple[str, dict[str, str]]:
    user_id = uuid.uuid4()
    async with TestSession() as db:
        db.add(
            User(
                id=user_id,
                phone="135" + uuid.uuid4().hex[:8],
                age=30,
                height=170,
                weight=65,
                gender="synthetic",
                updated_at=PLAN_START,
            )
        )
        db.add(
            HealthProfile(
                user_id=user_id,
                fitness_goal="basic_strength",
                training_experience="experienced",
                weekly_frequency=3,
                session_duration_minutes=30,
                equipment={"bodyweight": True, "resistance_band": False},
                pain_injury_limitations=[],
                risk_screen=dict(NO_SCREEN),
                allergies=[],
                diet_exclusions=[],
                food_allergen_codes=[],
                excluded_food_codes=[],
                version=1,
                updated_at=PLAN_START,
            )
        )
        await db.commit()
    token = create_access_token(str(user_id))
    return str(user_id), {"Authorization": f"Bearer {token}"}


def _context(
    local_date: date,
    *,
    goal: str = "basic_strength",
    frequency: int = 3,
    duration: int = 30,
    available_time: str = "45_min_plus",
    energy: str = "normal",
    muscle_soreness: str = "mild",
    daily_status: str = "checked_in",
    abnormal_pain: bool = False,
    recomputed_risk: str = "normal",
    risk_screen: dict[str, str] | None = None,
    token: str = "phase7-checkin-v1",
) -> TrainingSafetyContext:
    catalog = training_service.catalog()
    return TrainingSafetyContext.model_validate(
        {
            "health": {
                "configured": True,
                "fitness_goal": goal,
                "training_experience": "experienced",
                "weekly_frequency": frequency,
                "session_duration_minutes": duration,
                "equipment_bodyweight": True,
                "equipment_resistance_band": False,
                "pain_limitations": [],
                "risk_screen": risk_screen or dict(NO_SCREEN),
                "profile_version": 1,
                "profile_updated_at": PLAN_START,
            },
            "checkin": {
                "present": True,
                "local_date": local_date,
                "recomputed_risk": recomputed_risk,
                "energy": energy,
                "muscle_soreness": muscle_soreness,
                "available_time": available_time,
                "daily_status": daily_status,
                "abnormal_pain": abnormal_pain,
                "pain_area_canonical": "knee" if abnormal_pain else None,
                "token": token,
            },
            "retained_pain": [],
            "posture": {
                "active_signals_digest": "synthetic-empty-signals",
                "global_risk_tier": "normal",
                "risk_version": "synthetic-risk-v1",
                "goals": [
                    {
                        "issue_id": "lower_limb",
                        "active": True,
                        "blocked": False,
                        "confirmed_at": PLAN_START,
                        "suggestion_id": "synthetic-suggestion",
                        "profile_version": "synthetic-profile-v1",
                        "rule_version": "synthetic-rule-v1",
                        "risk_version": "synthetic-risk-v1",
                    }
                ],
            },
            "request": {
                "fitness_goal": goal,
                "equipment_bodyweight": True,
                "equipment_resistance_band": False,
                "weekly_frequency": frequency,
                "session_duration_minutes": duration,
                "iana_timezone": TZ,
            },
            "versions": {
                "policy_version": SAFETY_POLICY.policy_version,
                "catalog_version": catalog.content_version,
                "source_manifest_version": catalog.source_manifest_version,
                "schema_version": "v1",
            },
            "eval": {
                "evaluated_at_utc": PLAN_START,
                "iana_timezone": TZ,
                "current_local_date": local_date,
                "timezone_trusted": True,
            },
        }
    )


def _install_context(monkeypatch, holder: dict[str, TrainingSafetyContext]):
    async def classify_current(_db, _user_id, request, now=None):
        base = holder["context"]
        current = base.model_copy(
            update={
                "health": base.health.model_copy(
                    update={
                        "fitness_goal": request.fitness_goal,
                        "weekly_frequency": request.weekly_frequency,
                        "session_duration_minutes": request.session_duration_minutes,
                        "equipment_bodyweight": request.equipment_bodyweight,
                        "equipment_resistance_band": (
                            request.equipment_resistance_band
                        ),
                    }
                ),
                "request": request,
                "eval": base.eval.model_copy(
                    update={
                        "evaluated_at_utc": now or base.eval.evaluated_at_utc,
                        "current_local_date": base.checkin.local_date,
                    }
                ),
            }
        )
        return current, classify_safety(current, SAFETY_POLICY)

    monkeypatch.setattr(training_service, "_classify", classify_current)


def _plan_body(key: str, *, goal: str, frequency: int) -> dict:
    return {
        "fitness_goal": goal,
        "weekly_frequency": frequency,
        "session_duration_minutes": 30,
        "equipment_bodyweight": True,
        "equipment_resistance_band": False,
        "iana_timezone": TZ,
        "idempotency_key": key,
    }


async def _activate(client, headers, *, goal: str, frequency: int) -> dict:
    draft_body = _plan_body(
        f"phase7-draft-{uuid.uuid4().hex[:8]}", goal=goal, frequency=frequency
    )
    draft = await client.post(
        "/api/v1/training/plans:draft", headers=headers, json=draft_body
    )
    assert draft.status_code == 200, draft.text
    confirm_body = {
        **draft_body,
        "expected_plan_version_id": draft.json()["draft"]["plan_version_id"],
        "idempotency_key": f"phase7-confirm-{uuid.uuid4().hex[:8]}",
    }
    confirmed = await client.post(
        "/api/v1/training/plans:confirm", headers=headers, json=confirm_body
    )
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()["plan"]


def _adjustment_body(plan: dict, session_id: str, key: str) -> dict:
    return {
        "intent": "apply_today_adjustment",
        "expected_plan_version_id": plan["plan_version_id"],
        "expected_session_id": session_id,
        "iana_timezone": TZ,
        "idempotency_key": key,
    }


@pytest.mark.parametrize(
    (
        "now",
        "goal",
        "frequency",
        "context_updates",
        "expected_kind",
        "expected_reason",
    ),
    [
        (
            datetime(2026, 7, 27, 1, tzinfo=timezone.utc),
            "fat_loss",
            3,
            {"available_time": "15_min"},
            "shortened",
            "available_time_shortened",
        ),
        (
            datetime(2026, 7, 27, 1, tzinfo=timezone.utc),
            "fat_loss",
            3,
            {"energy": "low"},
            "recovery",
            "energy_recovery",
        ),
        (
            datetime(2026, 7, 28, 1, tzinfo=timezone.utc),
            "basic_strength",
            2,
            {"available_time": "none"},
            "deferred",
            "no_available_time",
        ),
    ],
)
async def test_adjustment_matrix_uses_authenticated_api_and_replays(
    client,
    monkeypatch,
    now,
    goal,
    frequency,
    context_updates,
    expected_kind,
    expected_reason,
):
    _user_id, headers = await _seed_user()
    local_date = training_service.derive_local_date(now, TZ)
    holder = {
        "context": _context(
            local_date, goal=goal, frequency=frequency, **context_updates
        )
    }
    _install_context(monkeypatch, holder)
    monkeypatch.setattr(training_service, "_utc_now", lambda: now)
    plan = await _activate(client, headers, goal=goal, frequency=frequency)
    today = await client.get(
        f"/api/v1/training/today?iana_timezone={TZ}", headers=headers
    )
    assert today.status_code == 200, today.text
    assert today.json()["state"] == "session", today.json()
    session_id = today.json()["original_session_id"]
    body = _adjustment_body(plan, session_id, f"phase7-adjust-{expected_kind}")

    recorded = await client.post(
        "/api/v1/training/today/adjustments", headers=headers, json=body
    )
    replayed = await client.post(
        "/api/v1/training/today/adjustments", headers=headers, json=body
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["adjustment_kind"] == expected_kind
    assert expected_reason in recorded.json()["reason_codes"]
    assert replayed.json()["status"] == "replayed"
    assert replayed.json()["adjustment_id"] == recorded.json()["adjustment_id"]

    effective = await client.get(
        f"/api/v1/training/today?iana_timezone={TZ}", headers=headers
    )
    assert effective.status_code == 200, effective.text
    assert effective.json()["adjustment_kind"] == expected_kind
    assert effective.json()["original_session_id"] == session_id
    if expected_kind == "deferred":
        assert effective.json()["state"] == "rest_day"
        assert effective.json()["target_local_date"] is not None
    else:
        assert effective.json()["state"] == "session"


async def test_no_legal_deferral_becomes_active_rest(client, monkeypatch):
    user_id, headers = await _seed_user()
    holder = {"context": _context(date(2026, 7, 27))}
    _install_context(monkeypatch, holder)
    clock = {"now": PLAN_START}
    monkeypatch.setattr(training_service, "_utc_now", lambda: clock["now"])
    plan = await _activate(client, headers, goal="basic_strength", frequency=3)

    clock["now"] = datetime(2026, 8, 23, 1, tzinfo=timezone.utc)
    holder["context"] = _context(
        date(2026, 8, 23), available_time="none", token="phase7-final-day"
    )
    async with TestSession() as db:
        target = await db.scalar(
            select(TrainingSession).where(
                TrainingSession.plan_version_id
                == uuid.UUID(plan["plan_version_id"]),
                TrainingSession.week_index == 4,
                TrainingSession.day_of_week == 5,
            )
        )
        assert target is not None
        target.day_of_week = 7
        await db.commit()
        session_id = str(target.session_id)

    response = await client.post(
        "/api/v1/training/today/adjustments",
        headers=headers,
        json=_adjustment_body(plan, session_id, "phase7-active-rest"),
    )
    assert response.status_code == 200, response.text
    assert response.json()["adjustment_kind"] == "active_rest"
    assert "active_rest_no_legal_deferral" in response.json()["reason_codes"]
    today = await client.get(
        f"/api/v1/training/today?iana_timezone={TZ}", headers=headers
    )
    assert today.json()["state"] == "rest_day"
    assert today.json()["adjustment_kind"] == "active_rest"
    assert today.json()["original_session_id"] == session_id

    async with TestSession() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(TrainingDayAdjustment)
            .where(TrainingDayAdjustment.user_id == uuid.UUID(user_id))
        )
    assert count == 1


@pytest.mark.parametrize(
    ("blocked_context", "expected_code"),
    [
        ({"abnormal_pain": True}, "pain_blocks_adjustment"),
        ({"recomputed_risk": "red_flag"}, "red_flag_stop"),
        (
            {
                "risk_screen": {
                    **NO_SCREEN,
                    "recent_surgery_or_major_injury": "yes",
                }
            },
            "restricted_no_plan",
        ),
    ],
)
async def test_pain_restricted_and_red_flag_make_zero_adjustment_writes(
    client, monkeypatch, blocked_context, expected_code
):
    user_id, headers = await _seed_user()
    holder = {"context": _context(date(2026, 7, 27))}
    _install_context(monkeypatch, holder)
    monkeypatch.setattr(training_service, "_utc_now", lambda: PLAN_START)
    plan = await _activate(client, headers, goal="basic_strength", frequency=3)
    today = await client.get(
        f"/api/v1/training/today?iana_timezone={TZ}", headers=headers
    )
    session_id = today.json()["original_session_id"]
    holder["context"] = _context(date(2026, 7, 27), **blocked_context)

    blocked = await client.post(
        "/api/v1/training/today/adjustments",
        headers=headers,
        json=_adjustment_body(plan, session_id, f"blocked-{expected_code}"),
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["code"] == expected_code
    async with TestSession() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(TrainingDayAdjustment)
            .where(TrainingDayAdjustment.user_id == uuid.UUID(user_id))
        )
    assert count == 0


async def test_changed_checkin_makes_overlay_stale_until_explicit_refresh(
    client, monkeypatch
):
    _user_id, headers = await _seed_user()
    holder = {
        "context": _context(date(2026, 7, 27), available_time="15_min")
    }
    _install_context(monkeypatch, holder)
    monkeypatch.setattr(training_service, "_utc_now", lambda: PLAN_START)
    plan = await _activate(client, headers, goal="basic_strength", frequency=3)
    today = await client.get(
        f"/api/v1/training/today?iana_timezone={TZ}", headers=headers
    )
    session_id = today.json()["original_session_id"]
    first = await client.post(
        "/api/v1/training/today/adjustments",
        headers=headers,
        json=_adjustment_body(plan, session_id, "phase7-stale-original"),
    )
    assert first.status_code == 200

    holder["context"] = _context(
        date(2026, 7, 27),
        available_time="45_min_plus",
        token="phase7-checkin-v2",
    )
    stale = await client.get(
        f"/api/v1/training/today?iana_timezone={TZ}", headers=headers
    )
    assert stale.json()["state"] == "blocked"
    assert stale.json()["change_reason"] == "adjustment_stale"
    assert stale.json()["decision_gate"] == "eligible"

    refreshed = await client.post(
        "/api/v1/training/today/adjustments",
        headers=headers,
        json=_adjustment_body(plan, session_id, "phase7-stale-refresh"),
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["adjustment_kind"] == "unchanged"


def _nutrition_context(plan_version_id: str) -> NutritionContext:
    return NutritionContext(
        age=30,
        height_cm=170,
        account_updated_at=REVIEW_NOW,
        weight_source=WeightSource(
            kind="account", timestamp=REVIEW_NOW, weight_kg=65
        ),
        profile_version=1,
        profile_updated_at=PLAN_START,
        risk_screen=dict(NO_SCREEN),
        food_allergen_codes=[],
        excluded_food_codes=[],
        checkin_present=True,
        checkin_risk="normal",
        checkin_token="d" * 64,
        posture_risk="normal",
        active_plan_present=True,
        active_plan_goal="basic_strength",
        active_plan_version_id=plan_version_id,
        training_decision_gate="eligible",
        day_kind=DayKind.rest_day,
        current_local_date=date(2026, 8, 24),
        iana_timezone=TZ,
        versions=NUTRITION_VERSIONS,
    )


def _walk_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _walk_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_keys(nested)


async def test_week4_review_creates_inactive_cross_domain_drafts_and_posture_due(
    client, monkeypatch
):
    user_id, headers = await _seed_user()
    holder = {"context": _context(date(2026, 7, 27))}
    _install_context(monkeypatch, holder)
    clock = {"now": PLAN_START}
    monkeypatch.setattr(training_service, "_utc_now", lambda: clock["now"])
    monkeypatch.setattr(review_service, "_now", lambda: clock["now"])
    plan = await _activate(client, headers, goal="basic_strength", frequency=3)
    plan_id = uuid.UUID(plan["plan_version_id"])

    async with TestSession() as db:
        sessions = list(
            (
                await db.execute(
                    select(TrainingSession)
                    .where(TrainingSession.plan_version_id == plan_id)
                    .order_by(
                        TrainingSession.week_index,
                        TrainingSession.day_of_week,
                    )
                )
            ).scalars()
        )
        for session in sessions:
            local_date = date(2026, 7, 27) + timedelta(
                days=(session.week_index - 1) * 7 + session.day_of_week - 1
            )
            outcome = "completed"
            if session.week_index == 4 and session.session_order == 1:
                outcome = "too_busy"
            elif session.week_index == 4 and session.session_order == 2:
                outcome = "intentional_rest"
            db.add(
                TrainingSessionFeedback(
                    user_id=uuid.UUID(user_id),
                    plan_version_id=plan_id,
                    session_id=session.session_id,
                    local_date=local_date,
                    outcome_state=outcome,
                )
            )
            db.add(
                DailyCheckIn(
                    user_id=uuid.UUID(user_id),
                    local_date=local_date,
                    sleep_quality="good",
                    energy="normal",
                    muscle_soreness="mild",
                    available_time="45_min_plus",
                    daily_status="checked_in",
                    abnormal_pain=False,
                    pain_followup=None,
                    risk_summary="normal",
                    risk_version="synthetic-v1",
                )
            )
        for index in range(8):
            db.add(
                WeightRecord(
                    user_id=uuid.UUID(user_id),
                    recorded_at=PLAN_START + timedelta(days=index * 3),
                    weight_kg=65 + index * 0.1,
                    source="manual",
                )
            )
        db.add(
            PostureAssessmentEvent(
                user_id=uuid.UUID(user_id),
                issue_id="forward_head",
                source="self_test",
                severity="mild",
                lifecycle="active",
                created_at=PLAN_START - timedelta(days=1),
            )
        )
        await db.commit()

    async def fixed_nutrition_context(*_args, **_kwargs):
        return _nutrition_context(str(plan_id))

    monkeypatch.setattr(
        review_service.nutrition_service,
        "resolve_nutrition_context",
        fixed_nutrition_context,
    )
    clock["now"] = REVIEW_NOW
    holder["context"] = _context(
        date(2026, 8, 24), token="phase7-review-current"
    )

    generated = await client.post(
        "/api/v1/training/reviews/weeks/4",
        headers=headers,
        json={"idempotency_key": "phase7-review", "iana_timezone": TZ},
    )
    assert generated.status_code == 200, generated.text
    review = generated.json()
    assert review["execution"]["too_busy"] == 1
    assert review["execution"]["intentional_rest"] == 1
    assert review["weight_trend"] == {"available": True, "direction": "rising"}
    assert review["posture"]["status"] == "due"
    proposals = {item["code"]: item for item in review["proposals"]}
    assert proposals["offer_training_draft"]["strategy"] == (
        "conservative_duration"
    )
    assert proposals["offer_nutrition_refresh"]["state"] == "proposal"
    assert proposals["posture_recheck_due"]["state"] == "proposal"
    assert "revisit_goal" in proposals
    assert not {
        "note",
        "pain_detail",
        "raw_body_value",
        "photo",
        "meal",
        "chat_text",
    } & set(_walk_keys(review))

    mutation = {
        "expected_review_id": review["review_id"],
        "expected_input_fingerprint": review["input_fingerprint"],
        "iana_timezone": TZ,
    }
    training_draft = await client.post(
        "/api/v1/training/reviews/weeks/4/training-drafts",
        headers=headers,
        json={**mutation, "idempotency_key": "phase7-review-training"},
    )
    nutrition_draft = await client.post(
        "/api/v1/training/reviews/weeks/4/nutrition-drafts",
        headers=headers,
        json={**mutation, "idempotency_key": "phase7-review-nutrition"},
    )
    dismissal = await client.post(
        "/api/v1/training/reviews/weeks/4/posture-recheck-dismissals",
        headers=headers,
        json={**mutation, "idempotency_key": "phase7-review-posture"},
    )
    assert training_draft.status_code == 200, training_draft.text
    assert nutrition_draft.status_code == 200, nutrition_draft.text
    assert dismissal.status_code == 200, dismissal.text

    async with TestSession() as db:
        review_row = await db.get(
            TrainingWeeklyReview, uuid.UUID(review["review_id"])
        )
        active_plan = await db.scalar(
            select(TrainingPlanVersion).where(
                TrainingPlanVersion.user_id == uuid.UUID(user_id),
                TrainingPlanVersion.status == "active",
            )
        )
        pending = await db.get(
            TrainingPlanVersion,
            uuid.UUID(training_draft.json()["draft_id"]),
        )
        nutrition = await db.get(
            NutritionRecommendation,
            uuid.UUID(nutrition_draft.json()["draft_id"]),
        )
    assert review_row is not None
    assert review_row.adaptive_policy_version == (
        training_service.ADAPTIVE_POLICY.policy_version
    )
    assert review_row.training_policy_version == (
        training_service.TRAINING_POLICY.policy_version
    )
    assert review_row.catalog_version == training_service.catalog().content_version
    assert review_row.source_manifest_version == (
        training_service.catalog().source_manifest_version
    )
    assert active_plan is not None and active_plan.plan_version_id == plan_id
    assert pending is not None and pending.status == "draft"
    assert pending.origin_weekly_review_id == uuid.UUID(review["review_id"])
    assert nutrition is not None and nutrition.status == "draft"
    assert nutrition.origin_weekly_review_id == uuid.UUID(review["review_id"])
