"""Phase 5 Agent confirmed-write execution tests (Task 3).

Proves the write-confirmation contract for the five actions: zero domain writes
before confirmation, exactly one after an idempotent confirmation, replay does
not duplicate, same-key-different-proposal conflicts, expired/foreign/cancelled/
inactive-consent proposals are rejected, stale context invalidates with no
write, the abnormal-pain check-in is preserved (safety route), weight notes stay
null, and a transient failure at any point rolls the whole unit of work back
leaving the proposal pending/retriable with no half-recorded side effect.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.agent import action_tools as at
from app.agent import persistence as ap
from app.agent import schemas as S
from app.auth.models import User
from app.core.config import settings
from app.core.exceptions import AppException
from app.health.models import DailyCheckIn, WeightRecord
from app.posture.models import IdempotencyRecord

pytestmark = pytest.mark.asyncio

HMAC_KEY = "test-agent-audit-key-0123456789abcdef"
HMAC_VERSION = "v1"
TZ = "Asia/Shanghai"


@pytest.fixture(autouse=True)
def _hmac_key(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY", HMAC_KEY)
    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY_VERSION", HMAC_VERSION)


async def _make_user(db) -> uuid.UUID:
    user = User(phone="139" + uuid.uuid4().hex[:8])
    db.add(user)
    await db.flush()
    return user.id


async def _grant_consent(db, uid: uuid.UUID):
    await ap.grant_consent(
        db, str(uid),
        accepted_provider_id="prov",
        accepted_disclosure_version="d1",
        current_provider_id="prov",
        current_disclosure_version="d1",
        idempotency_key="consent-" + uuid.uuid4().hex[:8],
    )


async def _seed_run(db, uid) -> uuid.UUID:
    res = await ap.record_run(db, str(uid), client_turn_id="turn-" + uuid.uuid4().hex[:6], entry_type="general")
    return res.run.run_id


async def _make_weight_proposal(db, uid, weight_kg=72.5, recorded_at=None):
    """Create an owned weight proposal WITH the correct current context
    fingerprint, so a confirm under unchanged context executes."""
    args = S.CreateWeightRecordArguments(
        recorded_at=recorded_at or datetime.now(timezone.utc), weight_kg=weight_kg
    )
    afp = at.compute_arguments_fingerprint(args)
    prepared = await at.prepare(db, S.CREATE_WEIGHT_RECORD, args, str(uid), iana_timezone=TZ)
    cfp = at.compute_context_fingerprint(prepared.context_fingerprint_payload)
    run_id = await _seed_run(db, uid)
    return await ap.create_proposal(
        db, run_id=run_id, user_id=str(uid), tool_name=S.CREATE_WEIGHT_RECORD,
        arguments_json=args.model_dump(mode="json"), arguments_hash=afp.value,
        context_fingerprint=cfp.value, fingerprint_key_version=cfp.key_version,
        iana_timezone=TZ,
    )


async def _weight_rows(db, uid):
    return (await db.execute(select(WeightRecord).where(WeightRecord.user_id == uid))).scalars().all()


# --------------------------------------------------------------------------- #
# Weight action                                                                #
# --------------------------------------------------------------------------- #


async def test_zero_domain_writes_before_confirm_then_exactly_one_after():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        await _grant_consent(db, uid)
        prop = await _make_weight_proposal(db, uid)
        await db.commit()
        # Before confirm: no weight record exists.
        assert await _weight_rows(db, uid) == []

        # Confirmation uses the validated timezone persisted with the proposal;
        # the confirm request itself does not carry a client-controlled timezone.
        res = await ap.confirm_proposal(
            db, str(uid), prop.proposal_id, idempotency_key="c1"
        )
        assert res.status == "executed"
        rows = await _weight_rows(db, uid)
        assert len(rows) == 1
        assert rows[0].note is None  # forced null
        assert float(rows[0].weight_kg) == 72.5


async def test_replay_does_not_duplicate_and_returns_same_ref():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        await _grant_consent(db, uid)
        prop = await _make_weight_proposal(db, uid)
        await db.commit()

        first = await ap.confirm_proposal(db, str(uid), prop.proposal_id, idempotency_key="k", iana_timezone=TZ)
        second = await ap.confirm_proposal(db, str(uid), prop.proposal_id, idempotency_key="k", iana_timezone=TZ)
        assert first.status == "executed"
        assert second.status == "replayed"
        assert second.result_ref == first.result_ref
        assert second.result_code == first.result_code
        assert len(await _weight_rows(db, uid)) == 1  # exactly one write


async def test_mutated_pending_arguments_fail_closed_before_write():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        await _grant_consent(db, uid)
        prop = await _make_weight_proposal(db, uid, weight_kg=72.5)
        proposal = await ap.load_owned_proposal(db, str(uid), prop.proposal_id)
        proposal.arguments_json = {
            **proposal.arguments_json,
            "weight_kg": 99.0,
        }
        await db.commit()

        res = await ap.confirm_proposal(
            db,
            str(uid),
            prop.proposal_id,
            idempotency_key="tampered",
            iana_timezone=TZ,
        )
        assert res.status == "invalidated"
        assert res.result_code == "agent_context_stale"
        assert await _weight_rows(db, uid) == []


async def test_same_key_different_proposal_conflicts():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        await _grant_consent(db, uid)
        p1 = await _make_weight_proposal(db, uid, weight_kg=70.0)
        p2 = await _make_weight_proposal(db, uid, weight_kg=71.0)
        await db.commit()

        await ap.confirm_proposal(db, str(uid), p1.proposal_id, idempotency_key="dup", iana_timezone=TZ)
        with pytest.raises(AppException) as exc:
            await ap.confirm_proposal(db, str(uid), p2.proposal_id, idempotency_key="dup", iana_timezone=TZ)
        assert exc.value.code == "idempotency_key_conflict"
        assert len(await _weight_rows(db, uid)) == 1


async def test_foreign_proposal_not_confirmable():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid_a = await _make_user(db)
        uid_b = await _make_user(db)
        await _grant_consent(db, uid_a)
        prop = await _make_weight_proposal(db, uid_a)
        await db.commit()
        # User B cannot even load the proposal -> 404 (non-enumerating).
        with pytest.raises(AppException) as exc:
            await ap.confirm_proposal(db, str(uid_b), prop.proposal_id, idempotency_key="c", iana_timezone=TZ)
        assert exc.value.status_code == 404
        assert await _weight_rows(db, uid_a) == []


async def test_expired_proposal_rejected():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        await _grant_consent(db, uid)
        prop = await _make_weight_proposal(db, uid)
        await db.commit()
        # Force expiry by winding the clock past the 15-min TTL.
        future = datetime.now(timezone.utc) + timedelta(minutes=20)
        res = await ap.confirm_proposal(db, str(uid), prop.proposal_id, idempotency_key="c", iana_timezone=TZ, now=future)
        assert res.status == "expired"
        assert await _weight_rows(db, uid) == []


async def test_inactive_consent_rejects_confirm(monkeypatch):
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        await _grant_consent(db, uid)
        prop = await _make_weight_proposal(db, uid)
        await db.commit()
        from app.agent.privacy_gate import ActiveConsentSnapshot

        async def _inactive(*args, **kwargs):
            return ActiveConsentSnapshot(active=False)

        monkeypatch.setattr(ap, "active_consent", _inactive)
        res = await ap.confirm_proposal(db, str(uid), prop.proposal_id, idempotency_key="c", iana_timezone=TZ)
        assert res.status == "invalidated"
        assert res.result_code == "agent_consent_required"
        assert await _weight_rows(db, uid) == []
        # Proposal scrubbed.
        proposal = await ap.load_owned_proposal(db, str(uid), prop.proposal_id)
        assert proposal.status == "invalidated"
        assert proposal.arguments_json is None
        replay = await ap.confirm_proposal(
            db,
            str(uid),
            prop.proposal_id,
            idempotency_key="c",
        )
        assert replay.status == "replayed"
        assert replay.result_code == "agent_consent_required"


# --------------------------------------------------------------------------- #
# Check-in action: abnormal-pain preservation + staleness                     #
# --------------------------------------------------------------------------- #


async def test_existing_abnormal_pain_checkin_is_not_overwritten():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        await _grant_consent(db, uid)
        # Seed a same-day abnormal_pain=true safety signal directly.
        db.add(
            DailyCheckIn(
                user_id=uid,
                local_date=__import__("datetime").date(2026, 7, 29),
                sleep_quality="good",
                energy="high",
                muscle_soreness="none",
                available_time="30_min",
                daily_status="checked_in",
                abnormal_pain=True,
                pain_followup={
                    "pain_area": "back", "pain_started": "within_week",
                    "pain_intensity": "moderate",
                    "has_neurological_symptom": False,
                    "has_dizziness_or_chest_symptom": False,
                    "has_acute_trauma": False,
                },
                risk_summary="red_flag",
                risk_version="risk-v1",
            )
        )
        await db.commit()

        args = S.UpsertTodayCheckinArguments(
            local_date=__import__("datetime").date(2026, 7, 29),
            sleep_quality="good", energy="high", muscle_soreness="none",
            available_time="30_min", daily_status="checked_in",
        )
        afp = at.compute_arguments_fingerprint(args)
        prepared = await at.prepare(db, S.UPSERT_TODAY_CHECKIN, args, str(uid), iana_timezone=TZ)
        cfp = at.compute_context_fingerprint(prepared.context_fingerprint_payload)
        run_id = await _seed_run(db, uid)
        prop = await ap.create_proposal(
            db, run_id=run_id, user_id=str(uid), tool_name=S.UPSERT_TODAY_CHECKIN,
            arguments_json=args.model_dump(mode="json"), arguments_hash=afp.value,
            context_fingerprint=cfp.value, fingerprint_key_version=cfp.key_version,
            iana_timezone=TZ,
        )
        await db.commit()

        res = await ap.confirm_proposal(db, str(uid), prop.proposal_id, idempotency_key="c", iana_timezone=TZ)
        # Refused + routed to safety flow; the existing abnormal-pain row is preserved.
        assert res.status == "invalidated"
        assert res.result_code == at.SAFETY_SIGNAL_ROUTE_CODE
        rows = (await db.execute(select(DailyCheckIn).where(DailyCheckIn.user_id == uid))).scalars().all()
        assert len(rows) == 1
        assert rows[0].abnormal_pain is True


async def test_stale_context_invalidates_with_no_write():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        await _grant_consent(db, uid)
        prop = await _make_weight_proposal(db, uid)
        await db.commit()
        # Corrupt the stored context fingerprint so confirmation sees stale context.
        proposal = await ap.load_owned_proposal(db, str(uid), prop.proposal_id)
        proposal.context_fingerprint = "0" * 64
        await db.commit()

        res = await ap.confirm_proposal(db, str(uid), prop.proposal_id, idempotency_key="c", iana_timezone=TZ)
        assert res.status == "invalidated"
        assert res.result_code == ap.AGENT_CONTEXT_STALE
        assert await _weight_rows(db, uid) == []


# --------------------------------------------------------------------------- #
# Transaction rollback: no half-recorded side effect, no false executed       #
# --------------------------------------------------------------------------- #


async def test_transient_failure_after_domain_flush_rolls_back_and_keeps_pending(monkeypatch):
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        await _grant_consent(db, uid)
        prop = await _make_weight_proposal(db, uid)
        await db.commit()

        # Inject a transient failure AFTER the domain side effect flushes but
        # BEFORE commit, by making the Tool-event recorder raise.
        original = ap.record_tool_event

        async def _boom(*a, **kw):
            raise RuntimeError("injected transient failure")

        monkeypatch.setattr(ap, "record_tool_event", _boom)
        with pytest.raises(RuntimeError):
            await ap.confirm_proposal(db, str(uid), prop.proposal_id, idempotency_key="c", iana_timezone=TZ)
        monkeypatch.setattr(ap, "record_tool_event", original)
        await db.rollback()

        # No half-recorded domain side effect...
        assert await _weight_rows(db, uid) == []
        # ...no false executed / agent idempotency record...
        proposal = await ap.load_owned_proposal(db, str(uid), prop.proposal_id)
        assert proposal.status == "pending"  # still retriable
        ide = (await db.execute(
            select(IdempotencyRecord).where(IdempotencyRecord.user_id == uid)
        )).scalars().all()
        assert all(r.operation != ap.OP_AGENT_ACTION_CONFIRM for r in ide)
        # ...and a fresh confirmation still succeeds exactly once.
        res = await ap.confirm_proposal(db, str(uid), prop.proposal_id, idempotency_key="c2", iana_timezone=TZ)
        assert res.status == "executed"
        assert len(await _weight_rows(db, uid)) == 1


# --------------------------------------------------------------------------- #
# Training draft: two-layer idempotency (agent_action_confirm + plan_generate)
# --------------------------------------------------------------------------- #


async def test_training_draft_confirm_records_both_idempotency_layers(monkeypatch):
    """A confirmed training draft writes the domain plan AND both idempotency
    records (agent_action_confirm + plan_generate) in one transaction."""
    from tests.conftest import TestSession
    from app.training import service as training_service
    from app.training.safety import classify_safety
    from app.training.models import TrainingPlanVersion
    from tests.test_training_api import _eligible_ctx, SPOLICY

    async with TestSession() as db:
        uid = await _make_user(db)
        await _grant_consent(db, uid)
        await db.commit()

        # Reuse the deterministic eligible-context pattern from the training
        # suite so evaluate_draft_request generates a real draft without the
        # heavy profile/posture seeding (validation is covered there).
        ctx = _eligible_ctx()
        decision = classify_safety(ctx, SPOLICY)

        async def _fake_classify(db2, user_id, request, now=None):
            return ctx, decision

        monkeypatch.setattr(training_service, "_classify", _fake_classify)

        args = S.GenerateTrainingPlanDraftArguments(
            fitness_goal="basic_strength",
            weekly_frequency=3,
            session_duration_minutes=30,
            equipment_bodyweight=True,
            equipment_resistance_band=False,
        )
        afp = at.compute_arguments_fingerprint(args)
        prepared = await at.prepare(db, S.GENERATE_TRAINING_PLAN_DRAFT, args, str(uid), iana_timezone=TZ)
        cfp = at.compute_context_fingerprint(prepared.context_fingerprint_payload)
        run_id = await _seed_run(db, uid)
        prop = await ap.create_proposal(
            db, run_id=run_id, user_id=str(uid), tool_name=S.GENERATE_TRAINING_PLAN_DRAFT,
            arguments_json=args.model_dump(mode="json"), arguments_hash=afp.value,
            context_fingerprint=cfp.value, fingerprint_key_version=cfp.key_version,
            iana_timezone=TZ,
        )
        await db.commit()

        # Zero domain plan writes before confirm.
        assert (await db.execute(
            select(TrainingPlanVersion).where(TrainingPlanVersion.user_id == uid)
        )).scalars().all() == []

        res = await ap.confirm_proposal(db, str(uid), prop.proposal_id, idempotency_key="c1", iana_timezone=TZ)
        assert res.status == "executed"

        # Exactly one draft plan, status draft (NOT activated by the Agent).
        plans = (await db.execute(
            select(TrainingPlanVersion).where(TrainingPlanVersion.user_id == uid)
        )).scalars().all()
        assert len(plans) == 1
        assert plans[0].status == "draft"

        # Both idempotency layers recorded, sharing the same result_ref.
        ops = {
            r.operation: r
            for r in (await db.execute(
                select(IdempotencyRecord).where(IdempotencyRecord.user_id == uid)
            )).scalars().all()
        }
        assert ap.OP_AGENT_ACTION_CONFIRM in ops
        assert training_service.P.OP_PLAN_GENERATE in ops
        assert ops[ap.OP_AGENT_ACTION_CONFIRM].result_ref == ops[training_service.P.OP_PLAN_GENERATE].result_ref

        # Replay returns the same result without a second plan.
        res2 = await ap.confirm_proposal(db, str(uid), prop.proposal_id, idempotency_key="c1", iana_timezone=TZ)
        assert res2.status == "replayed"
        assert len((await db.execute(
            select(TrainingPlanVersion).where(TrainingPlanVersion.user_id == uid)
        )).scalars().all()) == 1

        # Corrupt the atomic pair by removing only the domain idempotency row.
        # Agent-layer replay must fail closed rather than report success.
        await db.execute(
            delete(IdempotencyRecord).where(
                IdempotencyRecord.user_id == uid,
                IdempotencyRecord.operation == training_service.P.OP_PLAN_GENERATE,
            )
        )
        await db.commit()
        with pytest.raises(AppException) as exc:
            await ap.confirm_proposal(
                db,
                str(uid),
                prop.proposal_id,
                idempotency_key="c1",
            )
        assert exc.value.code == ap.AGENT_IDEMPOTENCY_INCONSISTENT
        assert len((await db.execute(
            select(TrainingPlanVersion).where(TrainingPlanVersion.user_id == uid)
        )).scalars().all()) == 1


async def test_training_partial_idempotency_inconsistency_fails_closed(monkeypatch):
    """If only the domain idempotency record exists (agent record missing), the
    confirmation fails closed: no second write, proposal invalidated."""
    from tests.conftest import TestSession
    from app.training import service as training_service
    from app.training.safety import classify_safety
    from tests.test_training_api import _eligible_ctx, SPOLICY

    async with TestSession() as db:
        uid = await _make_user(db)
        await _grant_consent(db, uid)
        await db.commit()
        ctx = _eligible_ctx()
        decision = classify_safety(ctx, SPOLICY)

        async def _fake_classify(db2, user_id, request, now=None):
            return ctx, decision

        monkeypatch.setattr(training_service, "_classify", _fake_classify)

        args = S.GenerateTrainingPlanDraftArguments(
            fitness_goal="basic_strength", weekly_frequency=3,
            session_duration_minutes=30, equipment_bodyweight=True,
            equipment_resistance_band=False,
        )
        afp = at.compute_arguments_fingerprint(args)
        prepared = await at.prepare(db, S.GENERATE_TRAINING_PLAN_DRAFT, args, str(uid), iana_timezone=TZ)
        cfp = at.compute_context_fingerprint(prepared.context_fingerprint_payload)
        run_id = await _seed_run(db, uid)
        prop = await ap.create_proposal(
            db, run_id=run_id, user_id=str(uid), tool_name=S.GENERATE_TRAINING_PLAN_DRAFT,
            arguments_json=args.model_dump(mode="json"), arguments_hash=afp.value,
            context_fingerprint=cfp.value, fingerprint_key_version=cfp.key_version,
            iana_timezone=TZ,
        )
        await db.commit()

        # Inject the partial-inconsistency: pre-create ONLY the domain record.
        domain_key = ap._domain_idempotency_key(prop.proposal_id)
        db.add(
            IdempotencyRecord(
                user_id=uid,
                operation=training_service.P.OP_PLAN_GENERATE,
                idempotency_key=domain_key,
                request_hash=prepared.domain_request_hash,
                status="completed",
                result_ref="orphan-plan-id",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        await db.commit()

        res = await ap.confirm_proposal(db, str(uid), prop.proposal_id, idempotency_key="c1", iana_timezone=TZ)
        assert res.status == "invalidated"
        assert res.result_code == ap.AGENT_IDEMPOTENCY_INCONSISTENT
        # No plan was written by this confirmation.
        from app.training.models import TrainingPlanVersion

        plans = (await db.execute(
            select(TrainingPlanVersion).where(TrainingPlanVersion.user_id == uid)
        )).scalars().all()
        assert plans == []


async def test_training_substitution_and_feedback_confirm_exactly_once(monkeypatch):
    """The two remaining training actions execute only through confirmation
    and record both Agent and domain idempotency evidence."""
    from tests.conftest import TestSession
    from app.training import service as training_service
    from app.training.models import (
        TrainingSessionFeedback,
        TrainingSessionSubstitution,
    )
    from app.training.safety import classify_safety
    from app.training.schemas_api import ConfirmRequest, DraftRequest
    from tests.test_training_api import _draft_body, _eligible_ctx, SPOLICY

    fixed_now = datetime(2026, 7, 27, 1, 0, tzinfo=timezone.utc)
    ctx = _eligible_ctx()
    decision = classify_safety(ctx, SPOLICY)

    async def _fake_classify(db2, user_id, request, now=None):
        return ctx, decision

    monkeypatch.setattr(training_service, "_classify", _fake_classify)
    monkeypatch.setattr(training_service, "_utc_now", lambda: fixed_now)

    async with TestSession() as db:
        uid = await _make_user(db)
        await _grant_consent(db, uid)
        await training_service.generate_draft(
            db, str(uid), DraftRequest(**_draft_body(key="agent-seed"))
        )
        await training_service.confirm(
            db, str(uid), ConfirmRequest(**_draft_body(key="agent-activate"))
        )
        today = await training_service.get_today(
            db, str(uid), TZ, now=fixed_now
        )
        assert today.state == "session"
        prescription = next(
            p for p in today.session.prescriptions if p.exercise.substitution_ids
        )
        replacement = prescription.exercise.substitution_ids[0]

        sub_args = S.SubstituteTodayExerciseArguments(
            original_exercise_id=prescription.exercise_id,
            replacement_exercise_id=replacement,
        )
        sub_prepared = await at.prepare(
            db,
            S.SUBSTITUTE_TODAY_EXERCISE,
            sub_args,
            str(uid),
            iana_timezone=TZ,
            now=fixed_now,
        )
        sub_afp = at.compute_arguments_fingerprint(sub_args)
        sub_cfp = at.compute_context_fingerprint(
            sub_prepared.context_fingerprint_payload
        )
        sub_run = await ap.record_run(
            db,
            str(uid),
            client_turn_id="sub-turn",
            entry_type="training_exercise",
            now=fixed_now,
        )
        sub_proposal = await ap.create_proposal(
            db,
            run_id=sub_run.run.run_id,
            user_id=str(uid),
            tool_name=S.SUBSTITUTE_TODAY_EXERCISE,
            arguments_json=sub_args.model_dump(mode="json"),
            arguments_hash=sub_afp.value,
            context_fingerprint=sub_cfp.value,
            fingerprint_key_version=sub_cfp.key_version,
            iana_timezone=TZ,
            now=fixed_now,
        )
        stale_sub_run = await ap.record_run(
            db,
            str(uid),
            client_turn_id="stale-sub-turn",
            entry_type="training_exercise",
            now=fixed_now,
        )
        stale_sub_proposal = await ap.create_proposal(
            db,
            run_id=stale_sub_run.run.run_id,
            user_id=str(uid),
            tool_name=S.SUBSTITUTE_TODAY_EXERCISE,
            arguments_json=sub_args.model_dump(mode="json"),
            arguments_hash=sub_afp.value,
            context_fingerprint=sub_cfp.value,
            fingerprint_key_version=sub_cfp.key_version,
            iana_timezone=TZ,
            now=fixed_now,
        )
        assert (
            await db.execute(select(TrainingSessionSubstitution))
        ).scalars().all() == []
        sub_result = await ap.confirm_proposal(
            db,
            str(uid),
            sub_proposal.proposal_id,
            idempotency_key="confirm-sub",
            now=fixed_now,
        )
        assert sub_result.status == "executed"
        assert len(
            (await db.execute(select(TrainingSessionSubstitution))).scalars().all()
        ) == 1
        replay_sub = await ap.confirm_proposal(
            db,
            str(uid),
            sub_proposal.proposal_id,
            idempotency_key="confirm-sub",
            now=fixed_now,
        )
        assert replay_sub.status == "replayed"
        stale_sub_result = await ap.confirm_proposal(
            db,
            str(uid),
            stale_sub_proposal.proposal_id,
            idempotency_key="confirm-stale-sub",
            now=fixed_now,
        )
        assert stale_sub_result.status == "invalidated"
        assert stale_sub_result.result_code == "substitution_limit_reached"
        assert len(
            (await db.execute(select(TrainingSessionSubstitution))).scalars().all()
        ) == 1

        feedback_args = S.RecordTrainingFeedbackArguments(
            outcome_state="completed"
        )
        feedback_prepared = await at.prepare(
            db,
            S.RECORD_TRAINING_FEEDBACK,
            feedback_args,
            str(uid),
            iana_timezone=TZ,
            now=fixed_now,
        )
        feedback_afp = at.compute_arguments_fingerprint(feedback_args)
        feedback_cfp = at.compute_context_fingerprint(
            feedback_prepared.context_fingerprint_payload
        )
        feedback_run = await ap.record_run(
            db,
            str(uid),
            client_turn_id="feedback-turn",
            entry_type="training_session",
            now=fixed_now,
        )
        feedback_proposal = await ap.create_proposal(
            db,
            run_id=feedback_run.run.run_id,
            user_id=str(uid),
            tool_name=S.RECORD_TRAINING_FEEDBACK,
            arguments_json=feedback_args.model_dump(mode="json"),
            arguments_hash=feedback_afp.value,
            context_fingerprint=feedback_cfp.value,
            fingerprint_key_version=feedback_cfp.key_version,
            iana_timezone=TZ,
            now=fixed_now,
        )
        stale_feedback_run = await ap.record_run(
            db,
            str(uid),
            client_turn_id="stale-feedback-turn",
            entry_type="training_session",
            now=fixed_now,
        )
        stale_feedback_proposal = await ap.create_proposal(
            db,
            run_id=stale_feedback_run.run.run_id,
            user_id=str(uid),
            tool_name=S.RECORD_TRAINING_FEEDBACK,
            arguments_json=feedback_args.model_dump(mode="json"),
            arguments_hash=feedback_afp.value,
            context_fingerprint=feedback_cfp.value,
            fingerprint_key_version=feedback_cfp.key_version,
            iana_timezone=TZ,
            now=fixed_now,
        )
        assert (
            await db.execute(select(TrainingSessionFeedback))
        ).scalars().all() == []
        feedback_result = await ap.confirm_proposal(
            db,
            str(uid),
            feedback_proposal.proposal_id,
            idempotency_key="confirm-feedback",
            now=fixed_now,
        )
        assert feedback_result.status == "executed"
        assert len(
            (await db.execute(select(TrainingSessionFeedback))).scalars().all()
        ) == 1
        stale_feedback_result = await ap.confirm_proposal(
            db,
            str(uid),
            stale_feedback_proposal.proposal_id,
            idempotency_key="confirm-stale-feedback",
            now=fixed_now,
        )
        assert stale_feedback_result.status == "invalidated"
        assert stale_feedback_result.result_code == "feedback_already_recorded"
        assert len(
            (await db.execute(select(TrainingSessionFeedback))).scalars().all()
        ) == 1

        operations = {
            row.operation
            for row in (
                await db.execute(
                    select(IdempotencyRecord).where(
                        IdempotencyRecord.user_id == uid
                    )
                )
            ).scalars().all()
        }
        assert ap.OP_AGENT_ACTION_CONFIRM in operations
        assert training_service.P.OP_SESSION_SUBSTITUTE in operations
        assert training_service.P.OP_SESSION_FEEDBACK in operations
