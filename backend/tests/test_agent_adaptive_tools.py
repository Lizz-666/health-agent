from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.agent import action_tools as at
from app.agent import persistence as agent_persistence
from app.agent import read_tools
from app.agent import schemas as S
from app.agent.messages import AgentError
from app.agent.messages import ResultCode, render
from app.agent.models import AgentActionProposal, AgentToolEvent
from app.auth.models import User
from app.core.actor_context import ActorContext
from app.core.config import settings
from app.core.exceptions import AppException
from app.posture.models import IdempotencyRecord
from app.training import persistence as training_persistence
from app.training import review_service
from app.training.models import (
    TrainingDayAdjustment,
    TrainingSessionFeedback,
    TrainingWeeklyReview,
)
from tests.conftest import TestSession
from tests.test_training_weekly_reviews import NOW, TZ, _seed_plan


@pytest.fixture(autouse=True)
def _hmac_key(monkeypatch):
    monkeypatch.setattr(
        settings,
        "AGENT_AUDIT_HMAC_KEY",
        "test-agent-audit-key-0123456789abcdef",
    )
    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY_VERSION", "v1")


@pytest.mark.parametrize(
    "name, valid",
    [
        (S.GENERATE_WEEKLY_REVIEW, {"week_index": 1}),
        (S.APPLY_TODAY_ADJUSTMENT, {}),
        (S.CREATE_REVIEW_TRAINING_DRAFT, {"week_index": 1}),
        (S.CREATE_REVIEW_NUTRITION_DRAFT, {"week_index": 1}),
        (S.DISMISS_POSTURE_RECHECK, {"week_index": 4}),
    ],
)
def test_adaptive_action_arguments_are_identity_and_policy_free(name, valid):
    parsed = at.validate_arguments(name, valid)
    assert set(parsed.model_dump()) <= {"week_index"}
    for injected in (
        {**valid, "user_id": "attacker"},
        {**valid, "iana_timezone": "UTC"},
        {**valid, "expected_review_id": str(uuid.uuid4())},
        {**valid, "safety_status": "eligible"},
        {**valid, "target_local_date": "2026-08-09"},
    ):
        with pytest.raises(AgentError):
            at.validate_arguments(name, injected)


@pytest.mark.asyncio
async def test_adaptive_domain_unavailable_maps_to_reviewed_agent_code():
    async with TestSession() as db:
        user = User(phone="139" + uuid.uuid4().hex[:8])
        db.add(user)
        await db.commit()
        with pytest.raises(AppException) as exc:
            await at.prepare(
                db,
                S.GENERATE_WEEKLY_REVIEW,
                S.GenerateWeeklyReviewArguments(week_index=1),
                str(user.id),
                iana_timezone=TZ,
                now=NOW,
            )
        assert exc.value.code == ResultCode.ADAPTIVE_UNAVAILABLE
        assert render(exc.value.code)


async def _grant_and_run(db, user_id: str):
    await agent_persistence.grant_consent(
        db,
        user_id,
        accepted_provider_id="synthetic-provider",
        accepted_disclosure_version="synthetic-v1",
        current_provider_id="synthetic-provider",
        current_disclosure_version="synthetic-v1",
        idempotency_key="consent-" + uuid.uuid4().hex,
        now=NOW,
    )
    return (
        await agent_persistence.record_run(
            db,
            user_id,
            client_turn_id="turn-" + uuid.uuid4().hex,
            entry_type="general",
            now=NOW,
        )
    ).run


async def _async_value(value):
    return value


async def _weekly_review_proposal(db, user_id: str):
    args = S.GenerateWeeklyReviewArguments(week_index=1)
    prepared = await at.prepare(
        db,
        S.GENERATE_WEEKLY_REVIEW,
        args,
        user_id,
        iana_timezone=TZ,
        now=NOW,
    )
    arguments_fp = at.compute_arguments_fingerprint(args)
    context_fp = at.compute_context_fingerprint(
        prepared.context_fingerprint_payload
    )
    run = await _grant_and_run(db, user_id)
    return await agent_persistence.create_proposal(
        db,
        run_id=run.run_id,
        user_id=user_id,
        tool_name=S.GENERATE_WEEKLY_REVIEW,
        arguments_json=args.model_dump(mode="json"),
        arguments_hash=arguments_fp.value,
        context_fingerprint=context_fp.value,
        fingerprint_key_version=context_fp.key_version,
        iana_timezone=TZ,
        now=NOW,
    )


@pytest.mark.asyncio
async def test_generate_review_agent_action_writes_only_after_confirmation():
    async with TestSession() as db:
        user_id, _plan, _sessions = await _seed_plan(
            db, outcomes=("completed", "completed")
        )
        proposal = await _weekly_review_proposal(db, user_id)
        proposal_id = proposal.proposal_id
        before = await db.scalar(select(func.count(TrainingWeeklyReview.review_id)))
        assert before == 0

        result = await agent_persistence.confirm_proposal(
            db,
            user_id,
            proposal.proposal_id,
            idempotency_key="confirm-review",
            now=NOW,
        )
        replay = await agent_persistence.confirm_proposal(
            db,
            user_id,
            proposal.proposal_id,
            idempotency_key="confirm-review",
            now=NOW,
        )
        assert result.status == "executed"
        assert replay.status == "replayed"
        assert replay.result_ref == result.result_ref
        assert await db.scalar(
            select(func.count(TrainingWeeklyReview.review_id))
        ) == 1

        await training_persistence.delete_adaptive_data(db, user_id)
        assert await db.get(AgentActionProposal, proposal_id) is None
        assert await db.scalar(
            select(func.count(AgentToolEvent.event_id)).where(
                AgentToolEvent.user_id == uuid.UUID(user_id),
                AgentToolEvent.tool_name == S.GENERATE_WEEKLY_REVIEW,
            )
        ) == 0
        assert await db.scalar(
            select(func.count(IdempotencyRecord.id)).where(
                IdempotencyRecord.user_id == uuid.UUID(user_id),
                IdempotencyRecord.operation.in_(
                    {
                        training_persistence.OP_WEEKLY_REVIEW_GENERATE,
                        agent_persistence.OP_AGENT_ACTION_CONFIRM,
                    }
                ),
            )
        ) == 0
        assert await db.scalar(
            select(func.count(TrainingWeeklyReview.review_id))
        ) == 0


@pytest.mark.asyncio
async def test_generate_review_confirmation_rejects_changed_context():
    async with TestSession() as db:
        user_id, plan, sessions = await _seed_plan(
            db, outcomes=("completed", None)
        )
        proposal = await _weekly_review_proposal(db, user_id)
        period_start = review_service._plan_start(plan, TZ)
        db.add(
            TrainingSessionFeedback(
                user_id=uuid.UUID(user_id),
                plan_version_id=plan.plan_version_id,
                session_id=sessions[1].session_id,
                local_date=period_start
                + timedelta(days=sessions[1].day_of_week - 1),
                outcome_state="completed",
            )
        )
        await db.commit()

        result = await agent_persistence.confirm_proposal(
            db,
            user_id,
            proposal.proposal_id,
            idempotency_key="confirm-stale-review",
            now=NOW,
        )
        assert result.status == "invalidated"
        assert result.result_code == "agent_context_stale"
        assert await db.scalar(
            select(func.count(TrainingWeeklyReview.review_id))
        ) == 0
        await training_persistence.delete_adaptive_data(db, user_id)
        assert await db.scalar(
            select(func.count(IdempotencyRecord.id)).where(
                IdempotencyRecord.user_id == uuid.UUID(user_id),
                IdempotencyRecord.operation
                == agent_persistence.OP_AGENT_ACTION_CONFIRM,
            )
        ) == 0


@pytest.mark.asyncio
async def test_adjustment_confirmation_persists_reviewed_agent_surface(
    monkeypatch,
):
    async with TestSession() as db:
        user_id, plan, sessions = await _seed_plan(
            db, outcomes=("completed", "completed")
        )
        source_date = review_service._plan_start(plan, TZ)
        evaluation = review_service.training_service.AdjustmentEvaluation(
            plan_version_id=plan.plan_version_id,
            source_session_id=sessions[0].session_id,
            source_local_date=source_date,
            target_local_date=None,
            adjustment_kind="active_rest",
            trigger_code="test_active_rest",
            reason_codes=("test_active_rest",),
            source_context_fingerprint="c" * 64,
            decision_fingerprint="d" * 64,
            training_policy_version=plan.policy_version,
            catalog_version=plan.catalog_version,
            source_manifest_version=plan.source_manifest_version,
            target_minutes=None,
            items=(),
        )
        monkeypatch.setattr(
            at.training_service,
            "get_today",
            lambda *_args, **_kwargs: _async_value(
                type("Today", (), {"original_session_id": str(sessions[0].session_id)})()
            ),
        )
        monkeypatch.setattr(
            at.training_service,
            "evaluate_adjustment",
            lambda *_args, **_kwargs: _async_value(evaluation),
        )
        args = S.ApplyTodayAdjustmentArguments()
        prepared = await at.prepare(
            db,
            S.APPLY_TODAY_ADJUSTMENT,
            args,
            user_id,
            iana_timezone=TZ,
            now=NOW,
        )
        arguments_fp = at.compute_arguments_fingerprint(args)
        context_fp = at.compute_context_fingerprint(
            prepared.context_fingerprint_payload
        )
        run = await _grant_and_run(db, user_id)
        proposal = await agent_persistence.create_proposal(
            db,
            run_id=run.run_id,
            user_id=user_id,
            tool_name=S.APPLY_TODAY_ADJUSTMENT,
            arguments_json={},
            arguments_hash=arguments_fp.value,
            context_fingerprint=context_fp.value,
            fingerprint_key_version=context_fp.key_version,
            iana_timezone=TZ,
            now=NOW,
        )
        result = await agent_persistence.confirm_proposal(
            db,
            user_id,
            proposal.proposal_id,
            idempotency_key="confirm-adjustment",
            now=NOW,
        )
        adjustment = await db.get(
            TrainingDayAdjustment, uuid.UUID(result.result_ref)
        )
        assert result.status == "executed"
        assert adjustment is not None
        assert adjustment.surface == "agent_confirmation"


@pytest.mark.asyncio
async def test_adaptive_read_tools_return_minimal_structured_states():
    async with TestSession() as db:
        user_id, _plan, _sessions = await _seed_plan(db)
        actor = ActorContext(user_id=user_id)
        availability = await read_tools.adapt_get_today_adjustment_availability(
            db, actor, TZ
        )
        assert set(availability.provider_view.model_dump()) == {
            "state",
            "can_apply",
            "safety_status",
            "adjustment_kind",
        }
        summary = await read_tools.adapt_get_weekly_review_summary(
            db, actor, 1
        )
        assert summary.provider_view.generated is False
        assert summary.provider_view.week_index == 1
        assert "input_fingerprint" not in summary.provider_view.model_dump()
        assert "weight" not in summary.provider_view.model_dump()
