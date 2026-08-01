from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from app.auth.models import User
from app.agent.models import AgentActionProposal, AgentRun, AgentToolEvent
from app.core.exceptions import AppException
from app.health.models import HealthProfile
from app.nutrition import persistence as persistence
from app.nutrition.calculator import calculate_targets
from app.nutrition.generator import generate_recommendation, preview_replacement
from app.nutrition.knowledge import load_catalog, load_media_manifest, load_policy
from app.nutrition.models import NutritionRecommendation
from app.nutrition.schemas import (
    DayKind,
    GateStatus,
    MealName,
    NutritionDecision,
    NutritionVersions,
    RecommendationContextPins,
)
from app.posture.models import IdempotencyRecord
from tests.conftest import TestSession

DATA = Path(__file__).resolve().parents[1] / "app/nutrition/data"
NOW = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
VERSIONS = NutritionVersions(
    policy_version="v1",
    catalog_version="v1",
    source_manifest_version="v1",
    media_manifest_version="v1",
)
PINS = RecommendationContextPins(
    profile_version=3,
    training_plan_version_id=str(uuid.UUID(int=42)),
    checkin_token="b" * 64,
)


async def _seed_user(db, user_id: str, phone: str) -> None:
    db.add(User(id=uuid.UUID(user_id), phone=phone))
    await db.commit()


def _payload(goal: str = "posture_improvement"):
    catalog = load_catalog(DATA / "foods.v1.json")
    policy = load_policy(DATA / "nutrition_policy.v1.json")
    media = load_media_manifest(DATA / "media_manifest.v1.json")
    decision = NutritionDecision(
        gate=GateStatus.eligible,
        reason_codes=["supported_scope"],
        context_fingerprint="a" * 64,
    )
    return generate_recommendation(
        catalog=catalog,
        policy=policy,
        media_manifest=media,
        decision=decision,
        targets=calculate_targets(65, 170, 30),
        versions=VERSIONS,
        requested_goal=goal,
        allergen_codes=set(),
        excluded_food_ids=set(),
    )


def _hash(label: str) -> str:
    return persistence.hash_request({"operation": label})


async def test_draft_regeneration_is_versioned_single_current_and_idempotent():
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_id, "13810000001")
        first = await persistence.create_draft(
            db,
            user_id,
            payload=_payload(),
            pins=PINS,
            idempotency_key="draft-1",
            request_hash=_hash("draft-1"),
            now=NOW,
        )
        replay = await persistence.create_draft(
            db,
            user_id,
            payload=_payload(),
            pins=PINS,
            idempotency_key="draft-1",
            request_hash=_hash("draft-1"),
            now=NOW,
        )
        assert replay.status == "replayed"
        assert replay.recommendation_id == first.recommendation_id

        second = await persistence.create_draft(
            db,
            user_id,
            payload=_payload("basic_strength"),
            pins=PINS,
            idempotency_key="draft-2",
            request_hash=_hash("draft-2"),
            now=NOW,
        )
        assert second.superseded_recommendation_id == first.recommendation_id
        rows = list(
            await db.scalars(
                select(NutritionRecommendation)
                .where(NutritionRecommendation.user_id == uuid.UUID(user_id))
                .order_by(NutritionRecommendation.version)
            )
        )
        assert [(row.version, row.status) for row in rows] == [
            (1, "superseded"),
            (2, "draft"),
        ]
        assert rows[0].payload["requested_goal"] == "posture_improvement"


async def test_idempotency_conflict_and_partial_replay_fail_closed():
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_id, "13810000002")
        created = await persistence.create_draft(
            db,
            user_id,
            payload=_payload(),
            pins=PINS,
            idempotency_key="same",
            request_hash=_hash("one"),
            now=NOW,
        )
        with pytest.raises(AppException) as conflict:
            await persistence.create_draft(
                db,
                user_id,
                payload=_payload(),
                pins=PINS,
                idempotency_key="same",
                request_hash=_hash("two"),
                now=NOW,
            )
        assert conflict.value.code == "idempotency_key_conflict"

        await db.execute(
            delete(NutritionRecommendation).where(
                NutritionRecommendation.recommendation_id == created.recommendation_id
            )
        )
        await db.commit()
        with pytest.raises(AppException) as inconsistent:
            await persistence.create_draft(
                db,
                user_id,
                payload=_payload(),
                pins=PINS,
                idempotency_key="same",
                request_hash=_hash("one"),
                now=NOW,
            )
        assert inconsistent.value.code == "idempotency_state_inconsistent"


async def test_confirmation_rejects_stale_without_changing_active_state():
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_id, "13810000003")
        draft = await persistence.create_draft(
            db,
            user_id,
            payload=_payload(),
            pins=PINS,
            idempotency_key="draft",
            request_hash=_hash("draft"),
            now=NOW,
        )
        with pytest.raises(AppException) as stale:
            await persistence.confirm_draft(
                db,
                user_id,
                draft_id=draft.recommendation_id,
                expected_version=1,
                expected_fingerprint="a" * 64,
                current_fingerprint="c" * 64,
                idempotency_key="confirm-stale",
                request_hash=_hash("confirm-stale"),
                now=NOW,
            )
        assert stale.value.code == "stale_context"
        assert await persistence.get_active(db, user_id) is None
        assert (await persistence.get_current_draft(db, user_id)).recommendation_id == draft.recommendation_id


async def test_confirming_new_draft_atomically_supersedes_prior_active():
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_id, "13810000009")
        first = await persistence.create_draft(
            db,
            user_id,
            payload=_payload(),
            pins=PINS,
            idempotency_key="draft-1",
            request_hash=_hash("draft-1"),
            now=NOW,
        )
        await persistence.confirm_draft(
            db,
            user_id,
            draft_id=first.recommendation_id,
            expected_version=1,
            expected_fingerprint="a" * 64,
            current_fingerprint="a" * 64,
            idempotency_key="confirm-1",
            request_hash=_hash("confirm-1"),
            now=NOW,
        )
        second = await persistence.create_draft(
            db,
            user_id,
            payload=_payload("basic_strength"),
            pins=PINS,
            idempotency_key="draft-2",
            request_hash=_hash("draft-2"),
            now=NOW,
        )
        result = await persistence.confirm_draft(
            db,
            user_id,
            draft_id=second.recommendation_id,
            expected_version=2,
            expected_fingerprint="a" * 64,
            current_fingerprint="a" * 64,
            idempotency_key="confirm-2",
            request_hash=_hash("confirm-2"),
            now=NOW,
        )
        assert result.superseded_recommendation_id == first.recommendation_id
        active = await persistence.get_active(db, user_id)
        assert active.recommendation_id == second.recommendation_id
        prior = await persistence.get_owned(db, user_id, first.recommendation_id)
        assert prior.status == "superseded"


async def test_confirm_and_replacement_create_single_active_immutable_versions():
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_id, "13810000004")
        draft = await persistence.create_draft(
            db,
            user_id,
            payload=_payload(),
            pins=PINS,
            idempotency_key="draft",
            request_hash=_hash("draft"),
            now=NOW,
        )
        confirmed = await persistence.confirm_draft(
            db,
            user_id,
            draft_id=draft.recommendation_id,
            expected_version=1,
            expected_fingerprint="a" * 64,
            current_fingerprint="a" * 64,
            idempotency_key="confirm",
            request_hash=_hash("confirm"),
            now=NOW,
        )
        assert confirmed.status == "confirmed"
        source = await persistence.get_active(db, user_id)
        source_payload = dict(source.payload)

        catalog = load_catalog(DATA / "foods.v1.json")
        policy = load_policy(DATA / "nutrition_policy.v1.json")
        typed = _payload()
        item = typed.variants[0].meals[1].items[1]
        replacement = preview_replacement(
            typed,
            catalog=catalog,
            policy=policy,
            day_kind=DayKind.training_day,
            meal=MealName.lunch,
            item_index=1,
            from_food_id=item.food_id,
            to_food_id=item.alternatives[0].food_id,
            allergen_codes=set(),
            excluded_food_ids=set(),
        )
        result = await persistence.create_replacement_active(
            db,
            user_id,
            source_id=source.recommendation_id,
            expected_version=source.version,
            expected_fingerprint="a" * 64,
            payload=replacement,
            pins=PINS,
            idempotency_key="replace",
            request_hash=_hash("replace"),
            now=NOW,
        )
        assert result.superseded_recommendation_id == source.recommendation_id
        active = await persistence.get_active(db, user_id)
        assert active.version == 2
        assert active.source_recommendation_id == source.recommendation_id
        await db.refresh(source)
        assert source.status == "superseded"
        assert source.payload == source_payload

        active.payload = {"tampered": True}
        with pytest.raises(ValueError, match="immutable"):
            await db.flush()
        await db.rollback()


async def test_cross_owner_read_and_confirm_are_non_enumerating():
    owner = str(uuid.uuid4())
    stranger = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, owner, "13810000005")
        await _seed_user(db, stranger, "13810000006")
        draft = await persistence.create_draft(
            db,
            owner,
            payload=_payload(),
            pins=PINS,
            idempotency_key="draft",
            request_hash=_hash("draft"),
            now=NOW,
        )
        assert await persistence.get_owned(db, stranger, draft.recommendation_id) is None
        with pytest.raises(AppException) as missing:
            await persistence.confirm_draft(
                db,
                stranger,
                draft_id=draft.recommendation_id,
                expected_version=1,
                expected_fingerprint="a" * 64,
                current_fingerprint="a" * 64,
                idempotency_key="confirm",
                request_hash=_hash("confirm"),
                now=NOW,
            )
        assert missing.value.code == "not_owner_or_missing_recommendation"


async def test_request_hash_rejects_non_json_and_non_finite_values():
    for value in ({1, 2}, object(), float("nan"), float("inf")):
        with pytest.raises(AppException) as invalid:
            persistence.hash_request({"value": value})
        assert invalid.value.code == "invalid_request"


async def test_confirmation_rolls_back_status_when_idempotency_recording_fails(monkeypatch):
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_id, "13810000008")
        draft = await persistence.create_draft(
            db,
            user_id,
            payload=_payload(),
            pins=PINS,
            idempotency_key="draft",
            request_hash=_hash("draft"),
            now=NOW,
        )

        async def fail(*_args, **_kwargs):
            raise RuntimeError("synthetic persistence failure")

        monkeypatch.setattr(persistence, "_record_idempotency", fail)
        with pytest.raises(RuntimeError, match="synthetic"):
            await persistence.confirm_draft(
                db,
                user_id,
                draft_id=draft.recommendation_id,
                expected_version=1,
                expected_fingerprint="a" * 64,
                current_fingerprint="a" * 64,
                idempotency_key="confirm",
                request_hash=_hash("confirm"),
                now=NOW,
            )
        assert await persistence.get_active(db, user_id) is None
        current = await persistence.get_current_draft(db, user_id)
        assert current.recommendation_id == draft.recommendation_id


async def test_nutrition_deletion_is_scoped_idempotent_and_clears_structured_answers():
    user_id = str(uuid.uuid4())
    uid = uuid.UUID(user_id)
    async with TestSession() as db:
        await _seed_user(db, user_id, "13810000007")
        db.add(
            HealthProfile(
                user_id=uid,
                version=4,
                fitness_goal="basic_strength",
                allergies=["legacy-preserved"],
                food_allergen_codes=["egg"],
                excluded_food_codes=["avoid_pork"],
            )
        )
        general_run = AgentRun(
            user_id=uid,
            client_turn_id="general-turn",
            entry_type="general",
            status="completed",
            tool_call_count=1,
            started_at=NOW,
            completed_at=NOW,
            expires_at=NOW + timedelta(days=30),
        )
        nutrition_run = AgentRun(
            user_id=uid,
            client_turn_id="nutrition-turn",
            entry_type="nutrition_plan",
            status="completed",
            tool_call_count=1,
            started_at=NOW,
            completed_at=NOW,
            expires_at=NOW + timedelta(days=30),
        )
        db.add_all([general_run, nutrition_run])
        await db.flush()
        db.add_all(
            [
                AgentToolEvent(
                    run_id=general_run.run_id,
                    user_id=uid,
                    tool_name="get_health_profile",
                    side_effect_class="read",
                    status="completed",
                ),
                AgentToolEvent(
                    run_id=nutrition_run.run_id,
                    user_id=uid,
                    tool_name="generate_meal_plan_draft",
                    side_effect_class="proposal",
                    status="completed",
                ),
                AgentActionProposal(
                    run_id=nutrition_run.run_id,
                    user_id=uid,
                    tool_name="generate_meal_plan_draft",
                    arguments_json={},
                    arguments_hash="c" * 64,
                    iana_timezone="Asia/Shanghai",
                    status="pending",
                    expires_at=NOW + timedelta(minutes=10),
                ),
                IdempotencyRecord(
                    user_id=uid,
                    operation="plan_generate",
                    idempotency_key="training-preserved",
                    request_hash="d" * 64,
                    status="completed",
                    result_ref=str(uuid.uuid4()),
                    expires_at=NOW + timedelta(hours=1),
                ),
            ]
        )
        await db.commit()
        await persistence.create_draft(
            db,
            user_id,
            payload=_payload(),
            pins=PINS,
            idempotency_key="nutrition-delete",
            request_hash=_hash("nutrition-delete"),
            now=NOW,
        )

        result = await persistence.delete_nutrition_data(db, user_id)
        assert result.recommendations_deleted == 1
        assert result.idempotency_deleted == 1
        assert result.proposals_deleted == 1
        assert result.tool_events_deleted == 1
        assert result.runs_deleted == 1
        assert result.profile_updated is True

        profile = await db.scalar(select(HealthProfile).where(HealthProfile.user_id == uid))
        assert profile.version == 5
        assert profile.food_allergen_codes is None
        assert profile.excluded_food_codes is None
        assert profile.allergies == ["legacy-preserved"]
        assert await db.scalar(select(AgentRun).where(AgentRun.run_id == general_run.run_id))
        operations = set(
            await db.scalars(
                select(IdempotencyRecord.operation).where(IdempotencyRecord.user_id == uid)
            )
        )
        assert operations == {"plan_generate"}

        second = await persistence.delete_nutrition_data(db, user_id)
        assert second.recommendations_deleted == 0
        assert second.profile_updated is False
