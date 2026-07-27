"""Phase 4 plan persistence tests (Task 2) — SQLite coverage.

Covers atomic state transitions, the single-active invariant (application-
checked on SQLite; DB-enforced partial unique index on PostgreSQL 16, rehearsed
in test_training_plan_migrations.py / PG paths), idempotent replay/conflict,
ownership scoping, one-per-day feedback/substitution uniqueness, and rollback
after a refused transition leaves no partial state.

These tests use a direct ``TestSession`` (same pattern as posture/health tests).
Synthetic data only.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest

from tests.conftest import TestSession  # noqa: E402

from app.auth.models import User
from app.core.exceptions import AppException
from app.training import persistence as P
from app.training.schemas import PlanPrescription, PlanSession, TrainingPlanDraft
from app.training.state import PlanStatus


async def _seed_user(db, user_id: str, phone: str = "13800000000") -> None:
    db.add(User(id=uuid.UUID(user_id), phone=phone))
    await db.commit()


def _draft(draft_id: str = "draft-1", goal: str = "posture_improvement") -> TrainingPlanDraft:
    return TrainingPlanDraft(
        draft_id=draft_id,
        requested_goal=goal,
        source_context_fingerprint="f" * 64,
        profile_version=1,
        catalog_version="v1",
        policy_version="v1",
        source_manifest_version="v1",
        sessions=[
            PlanSession(
                week_index=1,
                day_of_week=1,
                session_order=1,
                prescriptions=[
                    PlanPrescription(
                        exercise_id="ex-1", sets=3, reps=10, rest_seconds=60
                    ),
                    PlanPrescription(
                        exercise_id="ex-2", sets=2, duration_seconds=45, rest_seconds=30
                    ),
                ],
            ),
            PlanSession(
                week_index=2,
                day_of_week=1,
                session_order=1,
                prescriptions=[
                    PlanPrescription(
                        exercise_id="ex-1", sets=3, reps=12, rest_seconds=60
                    ),
                ],
            ),
        ],
    )


def _gen_request_hash(goal: str = "posture_improvement", freq: int = 3) -> str:
    return P.hash_request({"goal": goal, "weekly_frequency": freq})


# --- create_draft -----------------------------------------------------------


async def test_create_draft_persists_version_sessions_prescriptions():
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_id)
        result = await P.create_draft(
            db, user_id,
            draft=_draft(),
            weekly_frequency=3,
            session_duration_minutes=30,
            decision_gate="eligible",
            decision_fingerprint="a" * 64,
            generated_at=datetime.now(timezone.utc),
            change_reason="initial_generation",
            idempotency_key="k1",
            request_hash=_gen_request_hash(),
        )
        assert result.status == "created"
        version = await P.get_pending_draft(db, user_id)
        assert version is not None
        assert version.status == PlanStatus.draft.value
        assert version.weekly_frequency == 3
        assert version.change_reason == "initial_generation"
        sessions = await P.load_sessions(db, version.plan_version_id)
        assert [s.week_index for s in sessions] == [1, 2]
        presc = await P.load_prescriptions(db, sessions[0].session_id)
        assert [p.exercise_id for p in presc] == ["ex-1", "ex-2"]
        assert presc[0].display_order == 0
        assert presc[1].display_order == 1


async def test_create_draft_replay_same_key_hash_returns_same_id_no_new_version():
    user_id = str(uuid.uuid4())
    h = _gen_request_hash()
    async with TestSession() as db:
        await _seed_user(db, user_id)
        first = await P.create_draft(
            db, user_id, draft=_draft(), weekly_frequency=3,
            session_duration_minutes=30, decision_gate="eligible",
            decision_fingerprint="a" * 64, generated_at=datetime.now(timezone.utc),
            change_reason="initial_generation", idempotency_key="k1", request_hash=h,
        )
        replay = await P.create_draft(
            db, user_id, draft=_draft(), weekly_frequency=3,
            session_duration_minutes=30, decision_gate="eligible",
            decision_fingerprint="a" * 64, generated_at=datetime.now(timezone.utc),
            change_reason="initial_generation", idempotency_key="k1", request_hash=h,
        )
        assert replay.status == "replayed"
        assert replay.plan_version_id == first.plan_version_id
        # Only one draft exists.
        async with TestSession() as db2:
            assert (await P.get_pending_draft(db2, user_id)) is not None


async def test_create_draft_same_key_different_request_is_conflict():
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_id)
        await P.create_draft(
            db, user_id, draft=_draft(), weekly_frequency=3,
            session_duration_minutes=30, decision_gate="eligible",
            decision_fingerprint="a" * 64, generated_at=datetime.now(timezone.utc),
            change_reason="initial_generation", idempotency_key="k1",
            request_hash=_gen_request_hash(freq=3),
        )
        with pytest.raises(AppException) as exc:
            await P.create_draft(
                db, user_id, draft=_draft(), weekly_frequency=5,
                session_duration_minutes=30, decision_gate="eligible",
                decision_fingerprint="a" * 64, generated_at=datetime.now(timezone.utc),
                change_reason="initial_generation", idempotency_key="k1",
                request_hash=_gen_request_hash(freq=5),
            )
        assert exc.value.code == "idempotency_key_conflict"


async def test_create_new_draft_supersedes_pending_draft_and_leaves_active_alone():
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_id)
        d1 = await P.create_draft(
            db, user_id, draft=_draft("d1"), weekly_frequency=3,
            session_duration_minutes=30, decision_gate="eligible",
            decision_fingerprint="a" * 64, generated_at=datetime.now(timezone.utc),
            change_reason="initial_generation", idempotency_key="k1",
            request_hash=_gen_request_hash(freq=3),
        )
        # Confirm d1 -> active.
        await P.confirm_and_activate(
            db, user_id, plan_version_id=d1.plan_version_id,
            confirmed_at=datetime.now(timezone.utc), change_reason="initial_confirmation",
            idempotency_key="c1", request_hash=P.hash_request({"plan": str(d1.plan_version_id)}),
        )
        # Generate a new pending draft (different key).
        d2 = await P.create_draft(
            db, user_id, draft=_draft("d2"), weekly_frequency=3,
            session_duration_minutes=30, decision_gate="eligible",
            decision_fingerprint="a" * 64, generated_at=datetime.now(timezone.utc),
            change_reason="initial_generation", idempotency_key="k2",
            request_hash=_gen_request_hash(freq=3),
        )
        # The active plan d1 is untouched; d2 is the single pending draft.
        assert (await P.get_active_version(db, user_id)).plan_version_id == d1.plan_version_id
        assert (await P.get_pending_draft(db, user_id)).plan_version_id == d2.plan_version_id


# --- confirm_and_activate ---------------------------------------------------


async def test_confirm_activates_draft_sets_confirmed_at_and_single_active():
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_id)
        d1 = await P.create_draft(
            db, user_id, draft=_draft("d1"), weekly_frequency=3,
            session_duration_minutes=30, decision_gate="eligible",
            decision_fingerprint="a" * 64, generated_at=datetime.now(timezone.utc),
            change_reason="initial_generation", idempotency_key="k1",
            request_hash=_gen_request_hash(),
        )
        confirmed_at = datetime.now(timezone.utc)
        result = await P.confirm_and_activate(
            db, user_id, plan_version_id=d1.plan_version_id,
            confirmed_at=confirmed_at, change_reason="initial_confirmation",
            idempotency_key="c1", request_hash=P.hash_request({"p": str(d1.plan_version_id)}),
        )
        assert result.status == "confirmed"
        assert result.superseded_version_id is None
        active = await P.get_active_version(db, user_id)
        assert active.plan_version_id == d1.plan_version_id
        assert active.status == PlanStatus.active.value
        assert active.confirmed_at is not None
        # No pending draft remains.
        assert await P.get_pending_draft(db, user_id) is None


async def test_confirm_second_draft_supersedes_prior_active_atomically():
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_id)
        d1 = await P.create_draft(
            db, user_id, draft=_draft("d1"), weekly_frequency=3,
            session_duration_minutes=30, decision_gate="eligible",
            decision_fingerprint="a" * 64, generated_at=datetime.now(timezone.utc),
            change_reason="initial_generation", idempotency_key="k1",
            request_hash=_gen_request_hash(),
        )
        await P.confirm_and_activate(
            db, user_id, plan_version_id=d1.plan_version_id,
            confirmed_at=datetime.now(timezone.utc), change_reason="initial_confirmation",
            idempotency_key="c1", request_hash=P.hash_request({"p": str(d1.plan_version_id)}),
        )
        d2 = await P.create_draft(
            db, user_id, draft=_draft("d2"), weekly_frequency=3,
            session_duration_minutes=30, decision_gate="eligible",
            decision_fingerprint="b" * 64, generated_at=datetime.now(timezone.utc),
            change_reason="initial_generation", idempotency_key="k2",
            request_hash=_gen_request_hash(),
        )
        result = await P.confirm_and_activate(
            db, user_id, plan_version_id=d2.plan_version_id,
            confirmed_at=datetime.now(timezone.utc), change_reason="initial_confirmation",
            idempotency_key="c2", request_hash=P.hash_request({"p": str(d2.plan_version_id)}),
        )
        assert result.status == "confirmed"
        assert result.superseded_version_id == d1.plan_version_id
        # Exactly one active; prior active now superseded.
        active = await P.get_active_version(db, user_id)
        assert active.plan_version_id == d2.plan_version_id
        prior = await P.get_version_owned(db, user_id, d1.plan_version_id)
        assert prior.status == PlanStatus.superseded.value
        assert prior.change_reason == "superseded_by_new_draft"


async def test_confirm_replay_is_idempotent():
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_id)
        d1 = await P.create_draft(
            db, user_id, draft=_draft("d1"), weekly_frequency=3,
            session_duration_minutes=30, decision_gate="eligible",
            decision_fingerprint="a" * 64, generated_at=datetime.now(timezone.utc),
            change_reason="initial_generation", idempotency_key="k1",
            request_hash=_gen_request_hash(),
        )
        h = P.hash_request({"p": str(d1.plan_version_id)})
        first = await P.confirm_and_activate(
            db, user_id, plan_version_id=d1.plan_version_id,
            confirmed_at=datetime.now(timezone.utc), change_reason="initial_confirmation",
            idempotency_key="c1", request_hash=h,
        )
        replay = await P.confirm_and_activate(
            db, user_id, plan_version_id=d1.plan_version_id,
            confirmed_at=datetime.now(timezone.utc), change_reason="initial_confirmation",
            idempotency_key="c1", request_hash=h,
        )
        assert replay.status == "replayed"
        assert replay.plan_version_id == first.plan_version_id


async def test_confirm_non_draft_is_rejected_and_leaves_no_partial_state():
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_id)
        d1 = await P.create_draft(
            db, user_id, draft=_draft("d1"), weekly_frequency=3,
            session_duration_minutes=30, decision_gate="eligible",
            decision_fingerprint="a" * 64, generated_at=datetime.now(timezone.utc),
            change_reason="initial_generation", idempotency_key="k1",
            request_hash=_gen_request_hash(),
        )
        await P.confirm_and_activate(
            db, user_id, plan_version_id=d1.plan_version_id,
            confirmed_at=datetime.now(timezone.utc), change_reason="initial_confirmation",
            idempotency_key="c1", request_hash=P.hash_request({"p": str(d1.plan_version_id)}),
        )
        # Confirming the already-active version must be refused.
        with pytest.raises(AppException) as exc:
            await P.confirm_and_activate(
                db, user_id, plan_version_id=d1.plan_version_id,
                confirmed_at=datetime.now(timezone.utc), change_reason="initial_confirmation",
                idempotency_key="cX", request_hash=P.hash_request({"p": "x"}),
            )
        assert exc.value.code == "no_pending_draft"
        # State unchanged: still exactly one active.
        active = await P.get_active_version(db, user_id)
        assert active.plan_version_id == d1.plan_version_id


# --- cancel -----------------------------------------------------------------


async def test_cancel_draft_then_terminal_rejects_repeat():
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_id)
        d1 = await P.create_draft(
            db, user_id, draft=_draft("d1"), weekly_frequency=3,
            session_duration_minutes=30, decision_gate="eligible",
            decision_fingerprint="a" * 64, generated_at=datetime.now(timezone.utc),
            change_reason="initial_generation", idempotency_key="k1",
            request_hash=_gen_request_hash(),
        )
        await P.cancel(db, user_id, plan_version_id=d1.plan_version_id)
        cancelled = await P.get_version_owned(db, user_id, d1.plan_version_id)
        assert cancelled.status == PlanStatus.cancelled.value
        with pytest.raises(AppException) as exc:
            await P.cancel(db, user_id, plan_version_id=d1.plan_version_id)
        assert exc.value.code == "already_terminal"


async def test_cancel_active_works():
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_id)
        d1 = await P.create_draft(
            db, user_id, draft=_draft("d1"), weekly_frequency=3,
            session_duration_minutes=30, decision_gate="eligible",
            decision_fingerprint="a" * 64, generated_at=datetime.now(timezone.utc),
            change_reason="initial_generation", idempotency_key="k1",
            request_hash=_gen_request_hash(),
        )
        await P.confirm_and_activate(
            db, user_id, plan_version_id=d1.plan_version_id,
            confirmed_at=datetime.now(timezone.utc), change_reason="initial_confirmation",
            idempotency_key="c1", request_hash=P.hash_request({"p": str(d1.plan_version_id)}),
        )
        await P.cancel(db, user_id, plan_version_id=d1.plan_version_id)
        assert await P.get_active_version(db, user_id) is None


# --- feedback / substitution ------------------------------------------------


async def _seed_active_plan(db, user_id: str):
    d = await P.create_draft(
        db, user_id, draft=_draft("d1"), weekly_frequency=3,
        session_duration_minutes=30, decision_gate="eligible",
        decision_fingerprint="a" * 64, generated_at=datetime.now(timezone.utc),
        change_reason="initial_generation", idempotency_key="k1",
        request_hash=_gen_request_hash(),
    )
    await P.confirm_and_activate(
        db, user_id, plan_version_id=d.plan_version_id,
        confirmed_at=datetime.now(timezone.utc), change_reason="initial_confirmation",
        idempotency_key="c1", request_hash=P.hash_request({"p": str(d.plan_version_id)}),
    )
    sessions = await P.load_sessions(db, d.plan_version_id)
    return d.plan_version_id, sessions[0].session_id


async def test_record_feedback_replay_and_same_day_conflict():
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_id)
        plan_id, session_id = await _seed_active_plan(db, user_id)
        h = P.hash_request({"s": str(session_id), "d": "2026-07-27", "o": "completed"})
        r1 = await P.record_feedback(
            db, user_id, plan_version_id=plan_id, session_id=session_id,
            local_date=date(2026, 7, 27), outcome_state="completed",
            idempotency_key="f1", request_hash=h,
        )
        assert r1.status == "recorded"
        # Replay same key+hash.
        r2 = await P.record_feedback(
            db, user_id, plan_version_id=plan_id, session_id=session_id,
            local_date=date(2026, 7, 27), outcome_state="completed",
            idempotency_key="f1", request_hash=h,
        )
        assert r2.status == "replayed"
        assert r2.feedback_id == r1.feedback_id
        # Different key, same (session, day) -> conflict 409.
        with pytest.raises(AppException) as exc:
            await P.record_feedback(
                db, user_id, plan_version_id=plan_id, session_id=session_id,
                local_date=date(2026, 7, 27), outcome_state="partial",
                idempotency_key="f2", request_hash=P.hash_request({"o": "partial"}),
            )
        assert exc.value.code == "feedback_already_recorded"


async def test_record_substitution_replay_and_same_day_conflict():
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_id)
        plan_id, session_id = await _seed_active_plan(db, user_id)
        h = P.hash_request({"orig": "ex-1", "repl": "ex-2"})
        r1 = await P.record_substitution(
            db, user_id, plan_version_id=plan_id, session_id=session_id,
            local_date=date(2026, 7, 27), original_exercise_id="ex-1",
            replacement_exercise_id="ex-2", relation_reason="substitution",
            decision_gate="eligible", idempotency_key="s1", request_hash=h,
        )
        assert r1.status == "recorded"
        r2 = await P.record_substitution(
            db, user_id, plan_version_id=plan_id, session_id=session_id,
            local_date=date(2026, 7, 27), original_exercise_id="ex-1",
            replacement_exercise_id="ex-2", relation_reason="substitution",
            decision_gate="eligible", idempotency_key="s1", request_hash=h,
        )
        assert r2.status == "replayed"
        with pytest.raises(AppException) as exc:
            await P.record_substitution(
                db, user_id, plan_version_id=plan_id, session_id=session_id,
                local_date=date(2026, 7, 27), original_exercise_id="ex-2",
                replacement_exercise_id="ex-1", relation_reason="substitution",
                decision_gate="eligible", idempotency_key="s2",
                request_hash=P.hash_request({"x": 2}),
            )
        assert exc.value.code == "substitution_limit_reached"


async def test_feedback_rejects_session_not_owned_by_user():
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_a, "13800000001")
        await _seed_user(db, user_b, "13800000002")
        plan_id, session_id = await _seed_active_plan(db, user_a)
        # user_b tries to record feedback against user_a's session.
        with pytest.raises(AppException) as exc:
            await P.record_feedback(
                db, user_b, plan_version_id=plan_id, session_id=session_id,
                local_date=date(2026, 7, 27), outcome_state="completed",
                idempotency_key="xb", request_hash=P.hash_request({"o": "x"}),
            )
        assert exc.value.code in ("not_owner_or_missing_plan_version", "not_owner_or_missing_session")


# --- ownership --------------------------------------------------------------


async def test_get_version_owned_isolates_users():
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_a, "13800000003")
        await _seed_user(db, user_b, "13800000004")
        d = await P.create_draft(
            db, user_a, draft=_draft("d1"), weekly_frequency=3,
            session_duration_minutes=30, decision_gate="eligible",
            decision_fingerprint="a" * 64, generated_at=datetime.now(timezone.utc),
            change_reason="initial_generation", idempotency_key="k1",
            request_hash=_gen_request_hash(),
        )
        # user_b cannot see user_a's plan.
        assert await P.get_version_owned(db, user_b, d.plan_version_id) is None
        assert await P.get_active_version(db, user_b) is None
        assert await P.get_pending_draft(db, user_b) is None


async def test_terminal_version_is_immutable_via_cancel_reject():
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        await _seed_user(db, user_id)
        d1 = await P.create_draft(
            db, user_id, draft=_draft("d1"), weekly_frequency=3,
            session_duration_minutes=30, decision_gate="eligible",
            decision_fingerprint="a" * 64, generated_at=datetime.now(timezone.utc),
            change_reason="initial_generation", idempotency_key="k1",
            request_hash=_gen_request_hash(),
        )
        await P.confirm_and_activate(
            db, user_id, plan_version_id=d1.plan_version_id,
            confirmed_at=datetime.now(timezone.utc), change_reason="initial_confirmation",
            idempotency_key="c1", request_hash=P.hash_request({"p": str(d1.plan_version_id)}),
        )
        # cancel then attempt to re-confirm the cancelled version -> refused.
        await P.cancel(db, user_id, plan_version_id=d1.plan_version_id)
        with pytest.raises(AppException):
            await P.confirm_and_activate(
                db, user_id, plan_version_id=d1.plan_version_id,
                confirmed_at=datetime.now(timezone.utc), change_reason="initial_confirmation",
                idempotency_key="cZ", request_hash=P.hash_request({"p": "z"}),
            )
