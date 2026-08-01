from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from app.auth.models import User
from app.core.config import settings
from app.core.security import create_access_token
from app.nutrition import service
from app.nutrition.schemas import DayKind, NutritionContext, NutritionVersions, WeightSource
from tests.conftest import TestSession

NOW = datetime(2026, 8, 1, 4, tzinfo=timezone.utc)


def _auth(user_id: str):
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


async def _seed_user(user_id: str, phone: str):
    async with TestSession() as db:
        db.add(User(id=uuid.UUID(user_id), phone=phone))
        await db.commit()


def _eligible_context():
    return NutritionContext(
        age=30,
        height_cm=170,
        account_updated_at=NOW,
        weight_source=WeightSource(kind="account", timestamp=NOW, weight_kg=65),
        profile_version=1,
        profile_updated_at=NOW,
        risk_screen={
            "underage": "no",
            "pregnancy_or_postpartum": "no",
            "recent_surgery_or_major_injury": "no",
            "major_chronic_condition": "no",
            "eating_disorder_concern": "no",
            "professional_instruction_limitations": "no",
        },
        food_allergen_codes=[],
        excluded_food_codes=[],
        checkin_present=True,
        checkin_risk="normal",
        checkin_token="b" * 64,
        active_plan_present=True,
        active_plan_goal="posture_improvement",
        active_plan_version_id=str(uuid.UUID(int=42)),
        training_decision_gate="eligible",
        day_kind=DayKind.training_day,
        current_local_date=date(2026, 8, 1),
        iana_timezone="Asia/Shanghai",
        versions=NutritionVersions(
            policy_version="v1",
            catalog_version="v1",
            source_manifest_version="v1",
            media_manifest_version="v1",
        ),
    )


async def test_openapi_has_strict_jwt_nutrition_contract_and_no_intake_schema(client):
    schema = (await client.get("/openapi.json")).json()
    paths = schema["paths"]
    expected = {
        "/api/v1/nutrition/eligibility": "get",
        "/api/v1/nutrition/targets": "get",
        "/api/v1/nutrition/foods": "get",
        "/api/v1/nutrition/foods/{food_id}": "get",
        "/api/v1/nutrition/recommendations/drafts": "post",
        "/api/v1/nutrition/recommendations/draft": "get",
        "/api/v1/nutrition/recommendations/active": "get",
        "/api/v1/nutrition/recommendations/{draft_id}:confirm": "post",
        "/api/v1/nutrition/recommendations/{active_id}/replacements:preview": "post",
        "/api/v1/nutrition/recommendations/{active_id}/replacements:confirm": "post",
        "/api/v1/nutrition/data": "delete",
    }
    for path, method in expected.items():
        operation = paths[path][method]
        assert operation.get("security")
        assert "200" in operation["responses"]
    assert "requestBody" not in paths["/api/v1/nutrition/data"]["delete"]
    serialized = str(schema["components"]["schemas"]).lower()
    for forbidden in ("meal_event", "eaten_quantity", "consumed_quantity", "intake_state"):
        assert forbidden not in serialized


async def test_runtime_disabled_is_scoped_and_default_fail_closed(client, monkeypatch):
    user_id = str(uuid.uuid4())
    await _seed_user(user_id, "13830000001")
    monkeypatch.setattr(settings, "NUTRITION_RUNTIME_ENABLED", False)
    response = await client.get(
        "/api/v1/nutrition/foods", headers=_auth(user_id)
    )
    assert response.status_code == 503
    assert response.json()["code"] == "nutrition_runtime_disabled"
    assert (await client.get("/health")).status_code == 200


async def test_every_nutrition_route_requires_auth(client):
    for method, path in (
        ("GET", "/api/v1/nutrition/foods"),
        ("GET", "/api/v1/nutrition/eligibility?iana_timezone=Asia%2FShanghai"),
        ("POST", "/api/v1/nutrition/recommendations/drafts"),
        ("DELETE", "/api/v1/nutrition/data"),
    ):
        response = await client.request(method, path, json={} if method == "POST" else None)
        assert response.status_code == 401


async def test_api_rejects_identity_override_unknown_fields_and_invalid_timezone(
    client, monkeypatch
):
    user_id = str(uuid.uuid4())
    await _seed_user(user_id, "13830000002")
    monkeypatch.setattr(settings, "NUTRITION_RUNTIME_ENABLED", True)
    response = await client.post(
        "/api/v1/nutrition/recommendations/drafts",
        headers=_auth(user_id),
        json={
            "idempotency_key": "draft",
            "iana_timezone": "Asia/Shanghai",
            "user_id": str(uuid.uuid4()),
            "risk_tier": "eligible",
        },
    )
    assert response.status_code == 422
    response = await client.get(
        "/api/v1/nutrition/eligibility?iana_timezone=not%2Fa-zone",
        headers=_auth(user_id),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_timezone"


async def test_http_draft_and_cross_owner_confirmation_are_isolated(client, monkeypatch):
    owner = str(uuid.uuid4())
    stranger = str(uuid.uuid4())
    await _seed_user(owner, "13830000003")
    await _seed_user(stranger, "13830000004")
    monkeypatch.setattr(settings, "NUTRITION_RUNTIME_ENABLED", True)

    async def resolve(*_args, **_kwargs):
        return _eligible_context()

    monkeypatch.setattr(service, "resolve_nutrition_context", resolve)
    response = await client.post(
        "/api/v1/nutrition/recommendations/drafts",
        headers=_auth(owner),
        json={"idempotency_key": "draft", "iana_timezone": "Asia/Shanghai"},
    )
    assert response.status_code == 200, response.text
    draft = response.json()["recommendation"]
    confirm = await client.post(
        f"/api/v1/nutrition/recommendations/{draft['recommendation_id']}:confirm",
        headers=_auth(stranger),
        json={
            "idempotency_key": "confirm",
            "iana_timezone": "Asia/Shanghai",
            "expected_version": draft["version"],
            "expected_fingerprint": draft["payload"]["source_context_fingerprint"],
        },
    )
    assert confirm.status_code == 404
    assert confirm.json()["code"] == "not_owner_or_missing_recommendation"


async def test_delete_accepts_no_body_even_when_runtime_disabled(client, monkeypatch):
    user_id = str(uuid.uuid4())
    await _seed_user(user_id, "13830000005")
    monkeypatch.setattr(settings, "NUTRITION_RUNTIME_ENABLED", False)
    rejected = await client.request(
        "DELETE",
        "/api/v1/nutrition/data",
        headers=_auth(user_id),
        json={"unexpected": True},
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "invalid_request"
    accepted = await client.delete("/api/v1/nutrition/data", headers=_auth(user_id))
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "deleted"
