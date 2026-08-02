"""Phase 6 synthetic full-flow and fail-closed exit acceptance."""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.agent.models import AgentRun
from app.agent.provider import DashScopeProvider
from app.auth.models import User
from app.core.config import settings
from app.core.security import create_access_token
from app.nutrition import knowledge, service as nutrition_service
from app.nutrition.models import NutritionRecommendation
from app.nutrition.schemas import DayKind, NutritionContext, NutritionVersions, WeightSource
from app.training import service as training_service
from app.training.safety import classify_safety, load_safety_policy
from app.training.schemas import TrainingSafetyContext
from app.training.schemas_api import ConfirmRequest, DraftRequest
from tests.conftest import TestSession

pytestmark = pytest.mark.asyncio

TIMEZONE = "Asia/Shanghai"
LOCAL_DATE = date(2026, 8, 2)
NOW = datetime(2026, 8, 2, 2, tzinfo=timezone.utc)
VERSIONS = NutritionVersions(
    policy_version="v1",
    catalog_version="v1",
    source_manifest_version="v1",
    media_manifest_version="v1",
)
NO_SCREEN = {
    "underage": "no",
    "pregnancy_or_postpartum": "no",
    "recent_surgery_or_major_injury": "no",
    "major_chronic_condition": "no",
    "eating_disorder_concern": "no",
    "professional_instruction_limitations": "no",
}


@pytest.fixture(autouse=True)
def _synthetic_runtime(monkeypatch):
    monkeypatch.setattr(settings, "NUTRITION_RUNTIME_ENABLED", True)


async def _seed_user(*, suffix: str) -> tuple[str, dict[str, str]]:
    user_id = uuid.uuid4()
    async with TestSession() as db:
        db.add(
            User(
                id=user_id,
                phone=f"13708{suffix:0>6}",
                age=30,
                height=170.0,
                weight=65.0,
                gender="synthetic",
                updated_at=NOW,
            )
        )
        await db.commit()
    token = create_access_token(str(user_id))
    return str(user_id), {"Authorization": f"Bearer {token}"}


def _training_context() -> TrainingSafetyContext:
    catalog = training_service.catalog()
    return TrainingSafetyContext.model_validate(
        {
            "health": {
                "configured": True,
                "fitness_goal": "basic_strength",
                "training_experience": "experienced",
                "weekly_frequency": 3,
                "session_duration_minutes": 30,
                "equipment_bodyweight": True,
                "equipment_resistance_band": False,
                "pain_limitations": [],
                "risk_screen": NO_SCREEN,
                "profile_version": 1,
                "profile_updated_at": NOW,
            },
            "checkin": {
                "present": True,
                "local_date": LOCAL_DATE,
                "recomputed_risk": "normal",
                "token": "synthetic-current-checkin",
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
                        "confirmed_at": NOW,
                        "suggestion_id": "synthetic-suggestion",
                        "profile_version": "synthetic-profile-v1",
                        "rule_version": "synthetic-rule-v1",
                        "risk_version": "synthetic-risk-v1",
                    }
                ],
            },
            "request": {
                "fitness_goal": "basic_strength",
                "equipment_bodyweight": True,
                "equipment_resistance_band": False,
                "weekly_frequency": 3,
                "session_duration_minutes": 30,
                "iana_timezone": TIMEZONE,
            },
            "versions": {
                "policy_version": "v1",
                "catalog_version": catalog.content_version,
                "source_manifest_version": "v1",
                "schema_version": "v1",
            },
            "eval": {
                "evaluated_at_utc": NOW,
                "iana_timezone": TIMEZONE,
                "current_local_date": LOCAL_DATE,
                "timezone_trusted": True,
            },
        }
    )


def _nutrition_context(
    plan_version_id: str,
    *,
    risk_screen: dict[str, str] | None = None,
    checkin_risk: str = "normal",
    has_legacy_allergies: bool = False,
) -> NutritionContext:
    return NutritionContext(
        age=30,
        height_cm=170,
        account_updated_at=NOW,
        weight_source=WeightSource(kind="account", timestamp=NOW, weight_kg=65),
        profile_version=1,
        profile_updated_at=NOW,
        risk_screen=risk_screen or dict(NO_SCREEN),
        food_allergen_codes=[],
        excluded_food_codes=[],
        has_legacy_allergies=has_legacy_allergies,
        has_legacy_diet_exclusions=False,
        checkin_present=True,
        checkin_risk=checkin_risk,
        checkin_token="c" * 64,
        posture_risk="normal",
        active_plan_present=True,
        active_plan_goal="basic_strength",
        active_plan_version_id=plan_version_id,
        training_decision_gate="eligible",
        day_kind=DayKind.training_day,
        current_local_date=LOCAL_DATE,
        iana_timezone=TIMEZONE,
        versions=VERSIONS,
    )


def _plan_request(key: str) -> dict:
    return {
        "fitness_goal": "basic_strength",
        "weekly_frequency": 3,
        "session_duration_minutes": 30,
        "equipment_bodyweight": True,
        "equipment_resistance_band": False,
        "iana_timezone": TIMEZONE,
        "idempotency_key": key,
    }


def _walk_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _walk_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_keys(nested)


async def test_phase6_full_authenticated_lifecycle_and_scoped_delete(
    client, monkeypatch
):
    user_id, headers = await _seed_user(suffix="1")

    profile = await client.put(
        "/api/v1/health/profile",
        headers=headers,
        json={
            "fitness_goal": "basic_strength",
            "training_experience": "experienced",
            "weekly_frequency": 3,
            "session_duration_minutes": 30,
            "equipment": {"bodyweight": True, "resistance_band": False},
            "pain_injury_limitations": [],
            "risk_screen": NO_SCREEN,
            "allergies": [],
            "diet_exclusions": [],
            "food_allergen_codes": [],
            "excluded_food_codes": [],
        },
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["profile"]["food_allergen_codes"] == []

    checkin = await client.put(
        "/api/v1/health/checkins/today",
        headers=headers,
        json={
            "local_date": LOCAL_DATE.isoformat(),
            "sleep_quality": "good",
            "energy": "normal",
            "muscle_soreness": "mild",
            "available_time": "30_min",
            "daily_status": "checked_in",
            "abnormal_pain": False,
        },
    )
    assert checkin.status_code == 200, checkin.text
    assert checkin.json()["risk_summary"] == "normal"

    training_context = _training_context()
    training_policy = load_safety_policy(
        "app/training/data/training_safety_policy.v1.json"
    )
    training_decision = classify_safety(training_context, training_policy)
    async def fixed_training_context(*_args, **_kwargs):
        return training_context, training_decision

    monkeypatch.setattr(training_service, "_classify", fixed_training_context)
    async with TestSession() as db:
        draft = await training_service.generate_draft(
            db, user_id, DraftRequest(**_plan_request("phase6-training-draft"))
        )
        assert draft.has_draft
        active_plan = await training_service.confirm(
            db, user_id, ConfirmRequest(**_plan_request("phase6-training-confirm"))
    )
    assert active_plan.plan.plan_version_id

    original_resolve_context = nutrition_service.resolve_nutrition_context

    async def fixed_clock_nutrition_context(
        db, actor_id, timezone_name, versions, *, now=None
    ):
        return await original_resolve_context(
            db,
            actor_id,
            timezone_name,
            versions,
            now=NOW,
        )

    monkeypatch.setattr(
        nutrition_service, "resolve_nutrition_context", fixed_clock_nutrition_context
    )
    live_calls = 0

    async def forbidden_live_call(self, request):
        nonlocal live_calls
        live_calls += 1
        raise AssertionError("Phase 6 deterministic flow must not call live AI")

    monkeypatch.setattr(DashScopeProvider, "decide", forbidden_live_call)

    eligibility = await client.get(
        f"/api/v1/nutrition/eligibility?iana_timezone={TIMEZONE}", headers=headers
    )
    assert eligibility.status_code == 200
    assert eligibility.json()["gate"] == "eligible", eligibility.json()
    assert eligibility.json()["versions"] == VERSIONS.model_dump(mode="json")

    targets = await client.get(
        f"/api/v1/nutrition/targets?iana_timezone={TIMEZONE}", headers=headers
    )
    assert targets.status_code == 200
    assert targets.json()["targets"]["energy_low_kcal"] % 100 == 0
    assert targets.json()["targets"]["uncertainty_code"] == (
        "product_estimate_band_not_confidence_interval"
    )

    foods = await client.get("/api/v1/nutrition/foods", headers=headers)
    assert foods.status_code == 200
    food_ids = {food["food_id"] for food in foods.json()["foods"]}
    assert food_ids

    draft_response = await client.post(
        "/api/v1/nutrition/recommendations/drafts",
        headers=headers,
        json={
            "idempotency_key": "phase6-nutrition-draft",
            "iana_timezone": TIMEZONE,
        },
    )
    assert draft_response.status_code == 200, draft_response.text
    draft_view = draft_response.json()["recommendation"]
    assert draft_view["status"] == "draft"
    assert {variant["day_kind"] for variant in draft_view["payload"]["variants"]} == {
        "training_day",
        "rest_day",
    }
    assert draft_view["payload"]["guideline_source_codes"]
    assert "intake_state" not in set(_walk_keys(draft_view))
    assert "meal_completion" not in set(_walk_keys(draft_view))

    confirm = await client.post(
        f"/api/v1/nutrition/recommendations/{draft_view['recommendation_id']}:confirm",
        headers=headers,
        json={
            "idempotency_key": "phase6-nutrition-confirm",
            "iana_timezone": TIMEZONE,
            "expected_version": draft_view["version"],
            "expected_fingerprint": draft_view["payload"][
                "source_context_fingerprint"
            ],
        },
    )
    assert confirm.status_code == 200, confirm.text
    active = confirm.json()["recommendation"]
    assert active["status"] == "active"

    # A fresh request/session observes the persisted active recommendation.
    restarted = await client.get(
        f"/api/v1/nutrition/recommendations/active?iana_timezone={TIMEZONE}",
        headers=headers,
    )
    assert restarted.status_code == 200
    assert restarted.json()["recommendation"]["recommendation_id"] == active[
        "recommendation_id"
    ]

    replaceable = next(
        (variant, meal, index, item, item["alternatives"][0])
        for variant in active["payload"]["variants"]
        for meal in variant["meals"]
        for index, item in enumerate(meal["items"])
        if item["alternatives"]
    )
    variant, meal, item_index, item, alternative = replaceable
    replacement_body = {
        "iana_timezone": TIMEZONE,
        "expected_version": active["version"],
        "expected_fingerprint": active["payload"]["source_context_fingerprint"],
        "day_kind": variant["day_kind"],
        "meal": meal["meal"],
        "item_index": item_index,
        "from_food_id": item["food_id"],
        "to_food_id": alternative["food_id"],
    }
    preview = await client.post(
        f"/api/v1/nutrition/recommendations/{active['recommendation_id']}/replacements:preview",
        headers=headers,
        json=replacement_body,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["operation_status"] == "preview"
    assert preview.json()["recommendation"]["payload"]["replacement_diff"]

    replaced = await client.post(
        f"/api/v1/nutrition/recommendations/{active['recommendation_id']}/replacements:confirm",
        headers=headers,
        json={**replacement_body, "idempotency_key": "phase6-replacement-confirm"},
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["recommendation"]["version"] > active["version"]

    media = knowledge.load_media_manifest(
        "app/nutrition/data/media_manifest.v1.json"
    )
    media_assets = {item.asset_key for item in media.media}
    for variant in replaced.json()["recommendation"]["payload"]["variants"]:
        for meal_view in variant["meals"]:
            for item_view in meal_view["items"]:
                assert item_view["food_id"] in food_ids
                if item_view["image_key"]:
                    assert item_view["image_key"] in media_assets

    monkeypatch.setattr(settings, "NUTRITION_RUNTIME_ENABLED", False)
    disabled = await client.get(
        f"/api/v1/nutrition/recommendations/active?iana_timezone={TIMEZONE}",
        headers=headers,
    )
    assert disabled.status_code == 503
    assert disabled.json()["code"] == "nutrition_runtime_disabled"
    monkeypatch.setattr(settings, "NUTRITION_RUNTIME_ENABLED", True)
    recovered = await client.get(
        f"/api/v1/nutrition/recommendations/active?iana_timezone={TIMEZONE}",
        headers=headers,
    )
    assert recovered.status_code == 200
    assert recovered.json()["has_recommendation"] is True

    deleted = await client.delete("/api/v1/nutrition/data", headers=headers)
    assert deleted.status_code == 200
    # Initial draft is confirmed in place; replacement creates version 2.
    assert deleted.json()["recommendations_deleted"] == 2
    assert deleted.json()["profile_updated"] is True
    after_delete = await client.get(
        f"/api/v1/nutrition/recommendations/active?iana_timezone={TIMEZONE}",
        headers=headers,
    )
    assert after_delete.status_code == 200
    assert after_delete.json()["has_recommendation"] is False
    profile_after = await client.get("/api/v1/health/profile", headers=headers)
    assert profile_after.json()["profile"]["food_allergen_codes"] is None
    assert profile_after.json()["profile"]["excluded_food_codes"] is None

    async with TestSession() as db:
        recommendation_count = await db.scalar(
            select(func.count())
            .select_from(NutritionRecommendation)
            .where(NutritionRecommendation.user_id == uuid.UUID(user_id))
        )
        agent_run_count = await db.scalar(
            select(func.count())
            .select_from(AgentRun)
            .where(AgentRun.user_id == uuid.UUID(user_id))
        )
    assert recommendation_count == 0
    assert agent_run_count == 0
    assert live_calls == 0


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("restricted", "nutrition_restricted"),
        ("red_flag", "nutrition_red_flag"),
        ("legacy_allergy", "nutrition_clarification_required"),
    ],
)
async def test_phase6_blocked_contexts_make_zero_writes_and_no_provider_calls(
    client, monkeypatch, case, expected_code
):
    user_id, headers = await _seed_user(suffix=str(10 + len(case)))
    risk_screen = dict(NO_SCREEN)
    checkin_risk = "normal"
    legacy = False
    if case == "restricted":
        risk_screen["major_chronic_condition"] = "yes"
    elif case == "red_flag":
        checkin_risk = "red_flag"
    else:
        legacy = True
    context = _nutrition_context(
        "synthetic-plan",
        risk_screen=risk_screen,
        checkin_risk=checkin_risk,
        has_legacy_allergies=legacy,
    )

    async def fixed_context(*_args, **_kwargs):
        return context

    generator_calls = 0
    provider_calls = 0

    def forbidden_generator(*_args, **_kwargs):
        nonlocal generator_calls
        generator_calls += 1
        raise AssertionError("blocked context reached recommendation generation")

    async def forbidden_provider(self, request):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("blocked nutrition request reached live AI")

    monkeypatch.setattr(
        nutrition_service, "resolve_nutrition_context", fixed_context
    )
    monkeypatch.setattr(nutrition_service, "generate_recommendation", forbidden_generator)
    monkeypatch.setattr(DashScopeProvider, "decide", forbidden_provider)

    response = await client.post(
        "/api/v1/nutrition/recommendations/drafts",
        headers=headers,
        json={
            "idempotency_key": f"phase6-blocked-{case}",
            "iana_timezone": TIMEZONE,
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == expected_code
    async with TestSession() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(NutritionRecommendation)
            .where(NutritionRecommendation.user_id == uuid.UUID(user_id))
        )
    assert count == 0
    assert generator_calls == 0
    assert provider_calls == 0


async def test_phase6_release_audit_rechecks_every_local_source_and_media_asset():
    repo_root = Path(__file__).resolve().parents[2]
    knowledge.audit_release(
        repo_root / "backend/app/nutrition/data",
        repo_root / "app",
    )

    manifest = json.loads(
        (repo_root / "backend/app/nutrition/data/media_manifest.v1.json").read_text(
            encoding="utf-8"
        )
    )
    flutter_mapping = (
        repo_root / "app/lib/screens/nutrition/nutrition_media.dart"
    ).read_text(encoding="utf-8")
    assert len(
        re.findall(r":\s*NutritionMediaAttribution\(", flutter_mapping)
    ) == len(manifest["media"])
    for media in manifest["media"]:
        assert f"'{media['asset_key']}'" in flutter_mapping
        assert f"author: '{media['author']}'" in flutter_mapping
        assert f"license: '{media['license']}'" in flutter_mapping
        assert media["source_page_url"] in flutter_mapping
