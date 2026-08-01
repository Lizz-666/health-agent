from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.auth.models import User
from app.core.config import settings
from app.core.exceptions import AppException
from app.nutrition import service
from app.nutrition.models import NutritionRecommendation
from app.nutrition.schemas import (
    DayKind,
    NutritionContext,
    NutritionVersions,
    WeightSource,
)
from app.nutrition.schemas_api import (
    ConfirmRequest,
    DraftRequest,
    ReplacementConfirmRequest,
    ReplacementRequest,
)
from tests.conftest import TestSession

NOW = datetime(2026, 8, 1, 4, tzinfo=timezone.utc)


def _context(*, profile_version=1, allergens=None, goal="posture_improvement"):
    return NutritionContext(
        age=30,
        height_cm=170,
        account_updated_at=NOW,
        weight_source=WeightSource(
            kind="account", timestamp=NOW, weight_kg=65
        ),
        profile_version=profile_version,
        profile_updated_at=NOW + timedelta(minutes=profile_version),
        risk_screen={
            "underage": "no",
            "pregnancy_or_postpartum": "no",
            "recent_surgery_or_major_injury": "no",
            "major_chronic_condition": "no",
            "eating_disorder_concern": "no",
            "professional_instruction_limitations": "no",
        },
        food_allergen_codes=allergens or [],
        excluded_food_codes=[],
        has_legacy_allergies=False,
        has_legacy_diet_exclusions=False,
        checkin_present=True,
        checkin_risk="normal",
        checkin_token="b" * 64,
        posture_risk=None,
        active_plan_present=True,
        active_plan_goal=goal,
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


async def _seed_user(db, user_id: str, phone: str) -> None:
    db.add(User(id=uuid.UUID(user_id), phone=phone))
    await db.commit()


def _install_context(monkeypatch, holder):
    async def resolve(*_args, **_kwargs):
        return holder["context"]

    monkeypatch.setattr(service, "resolve_nutrition_context", resolve)
    monkeypatch.setattr(settings, "NUTRITION_RUNTIME_ENABLED", True)


async def test_runtime_defaults_off_but_delete_is_independent(monkeypatch):
    monkeypatch.setattr(settings, "NUTRITION_RUNTIME_ENABLED", False)
    with pytest.raises(AppException) as disabled:
        await service.eligibility(None, str(uuid.uuid4()), "Asia/Shanghai")
    assert disabled.value.code == "nutrition_runtime_disabled"


async def test_generate_confirm_replace_and_replay_use_one_domain_path(monkeypatch):
    user_id = str(uuid.uuid4())
    holder = {"context": _context()}
    _install_context(monkeypatch, holder)
    async with TestSession() as db:
        await _seed_user(db, user_id, "13820000001")
        generated = await service.generate_draft(
            db,
            user_id,
            DraftRequest(idempotency_key="draft-1", iana_timezone="Asia/Shanghai"),
        )
        draft = generated.recommendation
        assert generated.operation_status == "created"
        assert draft.status == "draft"
        assert draft.payload.targets.energy_low_kcal % 100 == 0

        confirmed = await service.confirm(
            db,
            user_id,
            uuid.UUID(draft.recommendation_id),
            ConfirmRequest(
                idempotency_key="confirm-1",
                iana_timezone="Asia/Shanghai",
                expected_version=draft.version,
                expected_fingerprint=draft.payload.source_context_fingerprint,
            ),
        )
        active = confirmed.recommendation
        assert active.status == "active"
        assert confirmed.operation_status == "confirmed"

        location = next(
            (variant, meal, index, item)
            for variant in active.payload.variants
            for meal in variant.meals
            for index, item in enumerate(meal.items)
            if item.alternatives
        )
        variant, meal, item_index, item = location
        replacement_fields = dict(
            iana_timezone="Asia/Shanghai",
            expected_version=active.version,
            expected_fingerprint=active.payload.source_context_fingerprint,
            day_kind=variant.day_kind,
            meal=meal.meal,
            item_index=item_index,
            from_food_id=item.food_id,
            to_food_id=item.alternatives[0].food_id,
        )
        preview = await service.replacement_preview(
            db,
            user_id,
            uuid.UUID(active.recommendation_id),
            ReplacementRequest(**replacement_fields),
        )
        assert preview.operation_status == "preview"
        assert preview.preview_resulting_version == active.version + 1
        assert preview.recommendation.payload.replacement_diff is not None

        request = ReplacementConfirmRequest(
            **replacement_fields, idempotency_key="replace-1"
        )
        replaced = await service.replacement_confirm(
            db, user_id, uuid.UUID(active.recommendation_id), request
        )
        replay = await service.replacement_confirm(
            db, user_id, uuid.UUID(active.recommendation_id), request
        )
        assert replaced.recommendation.version == 2
        assert replay.operation_status == "replayed"
        assert replay.recommendation.recommendation_id == replaced.recommendation.recommendation_id
        count = await db.scalar(
            select(func.count()).select_from(NutritionRecommendation).where(
                NutritionRecommendation.user_id == uuid.UUID(user_id),
                NutritionRecommendation.status == "active",
            )
        )
        assert count == 1


async def test_confirmation_rebuilds_context_and_stale_change_writes_no_active(monkeypatch):
    user_id = str(uuid.uuid4())
    holder = {"context": _context()}
    _install_context(monkeypatch, holder)
    async with TestSession() as db:
        await _seed_user(db, user_id, "13820000002")
        generated = await service.generate_draft(
            db,
            user_id,
            DraftRequest(idempotency_key="draft", iana_timezone="Asia/Shanghai"),
        )
        draft = generated.recommendation
        holder["context"] = _context(profile_version=2)
        with pytest.raises(AppException) as stale:
            await service.confirm(
                db,
                user_id,
                uuid.UUID(draft.recommendation_id),
                ConfirmRequest(
                    idempotency_key="confirm",
                    iana_timezone="Asia/Shanghai",
                    expected_version=draft.version,
                    expected_fingerprint=draft.payload.source_context_fingerprint,
                ),
            )
        assert stale.value.code == "stale_context"
        assert await service.persistence.get_active(db, user_id) is None


async def test_no_safe_candidate_creates_zero_recommendations(monkeypatch):
    user_id = str(uuid.uuid4())
    holder = {"context": _context(allergens=["milk"])}
    _install_context(monkeypatch, holder)
    async with TestSession() as db:
        await _seed_user(db, user_id, "13820000003")
        with pytest.raises(AppException) as blocked:
            await service.generate_draft(
                db,
                user_id,
                DraftRequest(idempotency_key="draft", iana_timezone="Asia/Shanghai"),
            )
        assert blocked.value.code == "no_safe_candidate"
        count = await db.scalar(
            select(func.count()).select_from(NutritionRecommendation).where(
                NutritionRecommendation.user_id == uuid.UUID(user_id)
            )
        )
        assert count == 0


async def test_replacement_preview_rejects_draft_and_accounts_for_pending_version(monkeypatch):
    user_id = str(uuid.uuid4())
    holder = {"context": _context()}
    _install_context(monkeypatch, holder)
    async with TestSession() as db:
        await _seed_user(db, user_id, "13820000004")
        first = await service.generate_draft(
            db,
            user_id,
            DraftRequest(idempotency_key="draft-1", iana_timezone="Asia/Shanghai"),
        )
        draft = first.recommendation
        item = next(
            item
            for variant in draft.payload.variants
            for meal in variant.meals
            for item in meal.items
            if item.alternatives
        )
        location = next(
            (variant, meal, index)
            for variant in draft.payload.variants
            for meal in variant.meals
            for index, candidate in enumerate(meal.items)
            if candidate is item
        )
        variant, meal, item_index = location
        request = ReplacementRequest(
            iana_timezone="Asia/Shanghai",
            expected_version=draft.version,
            expected_fingerprint=draft.payload.source_context_fingerprint,
            day_kind=variant.day_kind,
            meal=meal.meal,
            item_index=item_index,
            from_food_id=item.food_id,
            to_food_id=item.alternatives[0].food_id,
        )
        with pytest.raises(AppException) as invalid:
            await service.replacement_preview(
                db, user_id, uuid.UUID(draft.recommendation_id), request
            )
        assert invalid.value.code == "invalid_recommendation_state"

        active = await service.confirm(
            db,
            user_id,
            uuid.UUID(draft.recommendation_id),
            ConfirmRequest(
                idempotency_key="confirm-1",
                iana_timezone="Asia/Shanghai",
                expected_version=draft.version,
                expected_fingerprint=draft.payload.source_context_fingerprint,
            ),
        )
        pending = await service.generate_draft(
            db,
            user_id,
            DraftRequest(idempotency_key="draft-2", iana_timezone="Asia/Shanghai"),
        )
        request.expected_version = active.recommendation.version
        preview = await service.replacement_preview(
            db,
            user_id,
            uuid.UUID(active.recommendation.recommendation_id),
            request,
        )
        assert pending.recommendation.version == 2
        assert preview.preview_resulting_version == 3
