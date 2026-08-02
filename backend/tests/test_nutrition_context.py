from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.nutrition.context as context_module
from app.auth.models import User
from app.health.models import WeightRecord
from app.health.schemas import (
    ExcludedFoodCode, FoodAllergenCode, HealthProfileData, RiskScreen,
    YesNoUnknown,
)
from app.health.service import get_latest_manual_weight_at
from app.nutrition.schemas import DayKind, NutritionVersions
from tests.conftest import TestSession

NOW = datetime(2026, 8, 1, 4, tzinfo=timezone.utc)
VERSIONS = NutritionVersions(policy_version="v1", catalog_version="v1",
                             source_manifest_version="v1", media_manifest_version="v1")


def _profile(**risk_overrides):
    risks = {field: YesNoUnknown.no for field in RiskScreen.model_fields}
    risks.update(risk_overrides)
    return HealthProfileData(
        risk_screen=RiskScreen(**risks),
        food_allergen_codes=[FoodAllergenCode.egg],
        excluded_food_codes=[ExcludedFoodCode.avoid_pork],
        allergies=[], diet_exclusions=[], version=4, updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_context_uses_manual_weight_before_account_and_server_owned_plan(monkeypatch):
    user = SimpleNamespace(age=30, height=170.0, weight=90.0, updated_at=NOW)
    manual = SimpleNamespace(id=uuid.uuid4(), recorded_at=NOW - timedelta(days=1),
                             updated_at=NOW, weight_kg=65.0)
    checkin = SimpleNamespace(id=uuid.uuid4(), local_date=date(2026, 8, 1),
                              updated_at=NOW, risk_version="risk-v1", risk_summary="normal",
                              abnormal_pain=False, pain_followup=None)
    active = SimpleNamespace(has_active=True, plan=SimpleNamespace(
        requested_goal="fat_loss", plan_version_id="plan-7"))
    today = SimpleNamespace(state="session", decision_gate="eligible")
    async def value(result): return result
    monkeypatch.setattr(context_module, "get_user_by_id", lambda *a, **k: value(user))
    monkeypatch.setattr(context_module.health_service, "get_profile_result",
                        lambda *a, **k: value(SimpleNamespace(profile=_profile())))
    monkeypatch.setattr(context_module.health_service, "get_latest_manual_weight_at",
                        lambda *a, **k: value(manual))
    monkeypatch.setattr(context_module.health_service, "list_checkins",
                        lambda *a, **k: value([checkin]))
    monkeypatch.setattr(context_module.training_service, "get_active",
                        lambda *a, **k: value(active))
    monkeypatch.setattr(context_module.training_service, "get_today",
                        lambda *a, **k: value(today))
    result = await context_module.resolve_nutrition_context(
        SimpleNamespace(), "00000000-0000-0000-0000-000000000001",
        "Asia/Shanghai", VERSIONS, now=NOW)
    assert result.weight_source.kind == "manual_record"
    assert result.weight_source.weight_kg == 65
    assert result.weight_source.recorded_at == manual.recorded_at
    assert result.active_plan_goal == "fat_loss"
    assert result.active_plan_version_id == "plan-7"
    assert result.training_decision_gate == "eligible"
    assert result.day_kind == DayKind.training_day
    assert result.food_allergen_codes == ["egg"]
    assert result.excluded_food_codes == ["avoid_pork"]
    assert result.checkin_risk == "normal"


@pytest.mark.asyncio
async def test_context_recomputes_checkin_risk_instead_of_trusting_stored_label(monkeypatch):
    user = SimpleNamespace(age=30, height=170.0, weight=65.0, updated_at=NOW)
    checkin = SimpleNamespace(
        id=uuid.uuid4(), local_date=date(2026, 8, 1), updated_at=NOW,
        risk_version="old-risk-version", risk_summary="normal",
        abnormal_pain=False, pain_followup=None,
    )

    async def value(result):
        return result

    restricted_profile = _profile(major_chronic_condition=YesNoUnknown.yes)
    monkeypatch.setattr(context_module, "get_user_by_id", lambda *a, **k: value(user))
    monkeypatch.setattr(
        context_module.health_service, "get_profile_result",
        lambda *a, **k: value(SimpleNamespace(profile=restricted_profile)),
    )
    monkeypatch.setattr(
        context_module.health_service, "get_latest_manual_weight_at",
        lambda *a, **k: value(None),
    )
    monkeypatch.setattr(
        context_module.health_service, "list_checkins",
        lambda *a, **k: value([checkin]),
    )
    monkeypatch.setattr(
        context_module.training_service, "get_active",
        lambda *a, **k: value(SimpleNamespace(has_active=True, plan=SimpleNamespace(
            requested_goal="posture_improvement", plan_version_id="plan-1"))),
    )
    monkeypatch.setattr(
        context_module.training_service, "get_today",
        lambda *a, **k: value(SimpleNamespace(state="blocked", decision_gate="restricted")),
    )
    result = await context_module.resolve_nutrition_context(
        SimpleNamespace(), str(uuid.uuid4()), "Asia/Shanghai", VERSIONS, now=NOW,
    )
    assert checkin.risk_summary == "normal"
    assert result.checkin_risk == "restricted"
    assert result.checkin_token is not None


@pytest.mark.asyncio
async def test_latest_weight_helper_rejects_future_and_cross_owner_records():
    owner_id, other_id = uuid.uuid4(), uuid.uuid4()
    async with TestSession() as db:
        db.add_all([User(id=owner_id, phone="13906000001"),
                    User(id=other_id, phone="13906000002")])
        db.add_all([
            WeightRecord(user_id=owner_id, recorded_at=NOW - timedelta(days=1),
                         weight_kg=65, source="manual"),
            WeightRecord(user_id=owner_id, recorded_at=NOW + timedelta(days=1),
                         weight_kg=66, source="manual"),
            WeightRecord(user_id=other_id, recorded_at=NOW - timedelta(hours=1),
                         weight_kg=99, source="manual"),
        ])
        await db.commit()
        result = await get_latest_manual_weight_at(db, str(owner_id), NOW)
    assert result is not None
    assert result.weight_kg == 65


@pytest.mark.asyncio
async def test_context_falls_back_to_account_weight_when_no_manual(monkeypatch):
    boundary_now = datetime(2026, 7, 31, 16, 1, tzinfo=timezone.utc)
    user = SimpleNamespace(age=30, height=170.0, weight=70.0, updated_at=boundary_now)
    seen_dates = {}

    async def value(result): return result

    async def list_checkins(*args, **kwargs):
        seen_dates.update(kwargs)
        return []

    monkeypatch.setattr(context_module, "get_user_by_id", lambda *a, **k: value(user))
    monkeypatch.setattr(context_module.health_service, "get_profile_result",
                        lambda *a, **k: value(SimpleNamespace(profile=_profile())))
    monkeypatch.setattr(context_module.health_service, "get_latest_manual_weight_at",
                        lambda *a, **k: value(None))
    monkeypatch.setattr(context_module.health_service, "list_checkins", list_checkins)
    monkeypatch.setattr(context_module.training_service, "get_active",
                        lambda *a, **k: value(SimpleNamespace(has_active=False, plan=None)))
    monkeypatch.setattr(context_module.training_service, "get_today",
                        lambda *a, **k: value(SimpleNamespace(state="no_active_plan", decision_gate=None)))
    result = await context_module.resolve_nutrition_context(
        SimpleNamespace(), str(uuid.uuid4()), "Asia/Shanghai", VERSIONS,
        now=boundary_now)
    assert result.weight_source.kind == "account"
    assert result.weight_source.weight_kg == 70
    assert result.checkin_present is False
    assert result.active_plan_present is False
    assert result.current_local_date == date(2026, 8, 1)
    assert seen_dates == {
        "start_date": date(2026, 8, 1),
        "end_date": date(2026, 8, 1),
    }


@pytest.mark.asyncio
async def test_invalid_timezone_is_rejected_before_any_read():
    with pytest.raises(ValueError, match="timezone"):
        await context_module.resolve_nutrition_context(
            SimpleNamespace(), str(uuid.uuid4()), "not/a-zone", VERSIONS, now=NOW)
