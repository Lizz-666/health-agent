from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from tests.conftest import TestSession
from tests.conftest_pg import pg_available, requires_pg, skip_reason

from app.auth.models import User
from app.core.exceptions import AppException
from app.posture.models import IdempotencyRecord
from app.training import persistence as P
from app.training import service
from app.training.adaptive import (
    build_deferral_overlays,
    build_recovery_overlays,
    build_shortened_overlay,
    occupied_plan_dates,
)
from app.training.adaptive_policy import load_adaptive_policy
from app.training.models import PostureRecheckDismissal, TrainingWeeklyReview
from app.training.schemas import (
    Candidate,
    CandidateResult,
    GateStatus,
    PlanPrescription,
    PlanSession,
    TrainingPlanDraft,
)


TODAY = date(2026, 8, 2)
ADAPTIVE_POLICY = load_adaptive_policy(
    Path(__file__).resolve().parents[1]
    / "app"
    / "training"
    / "data"
    / "training_adaptive_policy.v1.json"
)


async def _seed_plan(db, user_id: str, phone: str = "13800000000"):
    db.add(User(id=uuid.UUID(user_id), phone=phone))
    await db.commit()
    draft = TrainingPlanDraft(
        draft_id="adaptive-test",
        requested_goal="general_wellness",
        source_context_fingerprint="a" * 64,
        profile_version=1,
        catalog_version="catalog-v1",
        policy_version="policy-v1",
        source_manifest_version="manifest-v1",
        sessions=[PlanSession(
            week_index=1,
            day_of_week=7,
            session_order=1,
            prescriptions=[PlanPrescription(
                exercise_id="ex-1", sets=2, reps=8, rest_seconds=30
            )],
        )],
    )
    result = await P.create_draft(
        db,
        user_id,
        draft=draft,
        weekly_frequency=2,
        session_duration_minutes=30,
        decision_gate="eligible",
        decision_fingerprint="b" * 64,
        generated_at=datetime.now(timezone.utc),
        change_reason="test",
        idempotency_key="draft-key",
        request_hash=P.hash_request({"draft": "adaptive-test"}),
    )
    session = (await P.load_sessions(db, result.plan_version_id))[0]
    prescription = (await P.load_prescriptions(db, session.session_id))[0]
    return result.plan_version_id, session.session_id, prescription.prescription_id


def _adjustment_args(plan_id, session_id, prescription_id, *, key="adjust-key"):
    return {
        "plan_version_id": plan_id,
        "source_session_id": session_id,
        "source_local_date": TODAY,
        "target_local_date": None,
        "adjustment_kind": "shortened",
        "trigger_code": "available_time",
        "reason_codes": ("available_time_shortened",),
        "source_context_fingerprint": "c" * 64,
        "decision_fingerprint": "d" * 64,
        "adaptive_policy_version": "adaptive-v1",
        "training_policy_version": "policy-v1",
        "catalog_version": "catalog-v1",
        "source_manifest_version": "manifest-v1",
        "surface": "button",
        "target_minutes": 15,
        "items": (P.AdjustmentItemInput(
            source_prescription_id=prescription_id,
            item_action="keep",
            effective_exercise_id="ex-1",
            sets=2,
            reps=8,
            duration_seconds=None,
            rest_seconds=30,
            display_order=0,
        ),),
        "idempotency_key": key,
        "request_hash": P.hash_request({"intent": "apply", "session": str(session_id)}),
    }


def _catalog_prescription(exercise):
    bounds = exercise.prescription
    return PlanPrescription(
        exercise_id=exercise.exercise_id,
        sets=bounds.sets_min,
        reps=bounds.reps_min if bounds.mode.value == "reps" else None,
        duration_seconds=(
            bounds.duration_seconds_min
            if bounds.mode.value == "duration"
            else None
        ),
        rest_seconds=bounds.rest_seconds_min,
    )


def _overlay_draft(*, prescriptions, days=(1, 3)):
    return TrainingPlanDraft(
        draft_id="overlay-test",
        requested_goal="general_wellness",
        source_context_fingerprint="a" * 64,
        profile_version=1,
        catalog_version=service.catalog().content_version,
        policy_version="v1",
        source_manifest_version="v1",
        sessions=[
            PlanSession(
                week_index=week,
                day_of_week=day,
                session_order=order,
                target_minutes=60,
                prescriptions=[item.model_copy(deep=True) for item in prescriptions],
            )
            for week in range(1, 5)
            for order, day in enumerate(days, start=1)
        ],
    )


def test_shortened_overlay_preserves_warmup_and_priority_without_mutating_plan():
    catalog = service.catalog()
    warmup = next(ex for ex in catalog.exercises if "warmup" in {
        role.value for role in ex.training_roles
    })
    others = [
        ex for ex in catalog.exercises
        if ex.exercise_id != warmup.exercise_id
    ][:7]
    source = [_catalog_prescription(ex) for ex in [warmup, *others]]
    draft = _overlay_draft(prescriptions=source)
    overlay = build_shortened_overlay(
        draft,
        week_index=1,
        day_of_week=1,
        target_minutes=15,
        adaptive_policy=ADAPTIVE_POLICY,
        catalog=catalog,
    )
    assert overlay is not None
    effective = overlay.draft.sessions[0]
    assert len(effective.prescriptions) == 3
    assert effective.prescriptions[0].exercise_id == warmup.exercise_id
    assert any(item.action == "drop" for item in overlay.items)
    assert len(draft.sessions[0].prescriptions) == 8


def test_shortened_snapshot_composes_a_later_retained_substitution():
    catalog = service.catalog()
    source = next(exercise for exercise in catalog.exercises if exercise.substitution_ids)
    replacement = next(
        exercise
        for exercise in catalog.exercises
        if exercise.exercise_id == source.substitution_ids[0]
    )
    draft = _overlay_draft(prescriptions=[_catalog_prescription(source)], days=(1,))
    source_id = uuid.uuid4()
    item = SimpleNamespace(
        item_action="keep",
        source_prescription_id=source_id,
        effective_exercise_id=source.exercise_id,
        sets=source.prescription.sets_min,
        reps=(
            source.prescription.reps_min
            if source.prescription.mode.value == "reps"
            else None
        ),
        duration_seconds=(
            source.prescription.duration_seconds_min
            if source.prescription.mode.value == "duration"
            else None
        ),
        rest_seconds=source.prescription.rest_seconds_min,
    )
    effective = service._apply_adjustment_snapshot(
        draft,
        SimpleNamespace(week_index=1, day_of_week=1),
        [item],
        15,
        (source.exercise_id, replacement.exercise_id),
    )
    assert effective is not None
    assert effective.prescriptions[0].exercise_id == replacement.exercise_id
    assert effective.prescriptions[0].relation_reason == "substitution"
    assert effective.prescriptions[0].relation_source_exercise_id == source.exercise_id


def test_recovery_builder_uses_only_current_candidates_and_complete_snapshot():
    catalog = service.catalog()
    warmup = next(ex for ex in catalog.exercises if "warmup" in {
        role.value for role in ex.training_roles
    })
    recovery = next(ex for ex in catalog.exercises if (
        ex.exercise_id != warmup.exercise_id
        and {role.value for role in ex.training_roles} & {"mobility", "recovery"}
    ))
    source = [_catalog_prescription(ex) for ex in [warmup, recovery]]
    draft = _overlay_draft(prescriptions=source)
    candidate_result = CandidateResult(
        gate_status=GateStatus.eligible,
        decision_fingerprint="a" * 64,
        candidates=[Candidate(
            exercise_id=ex.exercise_id,
            training_roles=[role.value for role in ex.training_roles],
            movement_purposes=ex.movement_purposes,
            sort_key=f"{idx:02d}",
        ) for idx, ex in enumerate([warmup, recovery])],
        policy_version="v1",
        catalog_version=catalog.content_version,
    )
    overlays = build_recovery_overlays(
        draft,
        week_index=1,
        day_of_week=1,
        adaptive_policy=ADAPTIVE_POLICY,
        catalog=catalog,
        candidates=candidate_result,
    )
    assert overlays
    assert all(item.action == "replace" for item in overlays[0].items)
    assert {p.exercise_id for p in overlays[0].draft.sessions[0].prescriptions} <= {
        warmup.exercise_id,
        recovery.exercise_id,
    }


def test_deferral_candidates_are_earliest_first_and_never_cross_plan_end():
    catalog = service.catalog()
    exercise = catalog.exercises[0]
    draft = _overlay_draft(prescriptions=[_catalog_prescription(exercise)])
    plan_start = date(2026, 7, 27)
    occupied = occupied_plan_dates(draft, plan_start)
    overlays = build_deferral_overlays(
        draft,
        source_week_index=1,
        source_day_of_week=1,
        source_local_date=plan_start,
        occupied_dates=occupied,
    )
    assert overlays[0].target_local_date == date(2026, 7, 28)
    assert overlays[-1].target_local_date <= date(2026, 8, 23)
    assert draft.sessions[0].day_of_week == 1


async def test_adjustment_is_atomic_owned_and_replayable():
    owner = str(uuid.uuid4())
    other = str(uuid.uuid4())
    async with TestSession() as db:
        plan_id, session_id, prescription_id = await _seed_plan(db, owner)
        db.add(User(id=uuid.UUID(other), phone="13900000000"))
        await db.commit()
        args = _adjustment_args(plan_id, session_id, prescription_id)
        first = await P.record_adjustment(db, owner, **args)
        replay = await P.record_adjustment(db, owner, **args)
        assert first.status == "recorded"
        assert replay == P.AdjustmentResult(first.adjustment_id, "replayed")
        assert await P.get_adjustment_owned(db, other, first.adjustment_id) is None
        assert len(await P.load_adjustment_items(db, first.adjustment_id)) == 1


async def test_adjustment_same_key_different_request_conflicts():
    owner = str(uuid.uuid4())
    async with TestSession() as db:
        plan_id, session_id, prescription_id = await _seed_plan(db, owner)
        args = _adjustment_args(plan_id, session_id, prescription_id)
        await P.record_adjustment(db, owner, **args)
        changed = dict(args, request_hash=P.hash_request({"intent": "different"}))
        with pytest.raises(AppException) as exc:
            await P.record_adjustment(db, owner, **changed)
        assert exc.value.code == "idempotency_key_conflict"


async def test_same_decision_with_different_key_has_stable_collision():
    owner = str(uuid.uuid4())
    async with TestSession() as db:
        plan_id, session_id, prescription_id = await _seed_plan(db, owner)
        args = _adjustment_args(plan_id, session_id, prescription_id)
        await P.record_adjustment(db, owner, **args)
        with pytest.raises(AppException) as exc:
            await P.record_adjustment(
                db,
                owner,
                **dict(args, idempotency_key="different-key"),
            )
        assert exc.value.code == "adjustment_already_applied"


async def test_idempotency_failure_rolls_back_adjustment_and_items(monkeypatch):
    owner = str(uuid.uuid4())
    async with TestSession() as db:
        plan_id, session_id, prescription_id = await _seed_plan(db, owner)

        async def fail_record(*args, **kwargs):
            raise RuntimeError("synthetic idempotency failure")

        monkeypatch.setattr(P, "_record_idempotency", fail_record)
        with pytest.raises(RuntimeError, match="synthetic"):
            await P.record_adjustment(
                db, owner, **_adjustment_args(plan_id, session_id, prescription_id)
            )
        await db.rollback()
    async with TestSession() as verify:
        assert await P.get_latest_source_adjustment(
            verify, owner, plan_id, session_id, TODAY
        ) is None


async def test_delete_adaptive_data_is_owner_scoped_and_complete():
    owner = str(uuid.uuid4())
    other = str(uuid.uuid4())
    async with TestSession() as db:
        plan_id, session_id, prescription_id = await _seed_plan(db, owner)
        other_plan, other_session, other_rx = await _seed_plan(
            db, other, phone="13900000000"
        )
        owner_result = await P.record_adjustment(
            db, owner, **_adjustment_args(plan_id, session_id, prescription_id)
        )
        other_result = await P.record_adjustment(
            db,
            other,
            **_adjustment_args(
                other_plan, other_session, other_rx, key="other-adjust-key"
            ),
        )
        db.add(TrainingWeeklyReview(
            user_id=uuid.UUID(owner),
            plan_version_id=plan_id,
            week_index=1,
            review_version=1,
            input_fingerprint="e" * 64,
            period_start=TODAY,
            period_end=TODAY,
            facts={},
            proposal_codes=[],
            adaptive_policy_version="adaptive-v1",
            training_policy_version="policy-v1",
            catalog_version="catalog-v1",
            source_manifest_version="manifest-v1",
        ))
        db.add(PostureRecheckDismissal(
            user_id=uuid.UUID(owner),
            plan_version_id=plan_id,
            due_reason="cycle_complete",
            dismissed_at=datetime.now(timezone.utc),
        ))
        await db.commit()

        deleted = await P.delete_adaptive_data(db, owner)
        assert deleted == P.AdaptiveDeletionResult(1, 1, 1, 1, 1)
        assert await P.get_adjustment_owned(db, owner, owner_result.adjustment_id) is None
        assert await P.get_adjustment_owned(db, other, other_result.adjustment_id)


async def test_account_deletion_purge_removes_adaptive_rows(monkeypatch):
    from app.core.config import settings
    from app.posture import purge

    monkeypatch.setattr(
        settings,
        "PURGE_ENCRYPTION_KEY",
        "0123456789abcdef" * 4,
    )
    owner = str(uuid.uuid4())
    async with TestSession() as db:
        plan_id, session_id, prescription_id = await _seed_plan(db, owner)
        result = await P.record_adjustment(
            db, owner, **_adjustment_args(plan_id, session_id, prescription_id)
        )
    async with TestSession() as db:
        purged = await purge.run_purge(
            db, owner, purge.FakeObjectStore(), trigger="account_deletion"
        )
        assert purged.status == "completed"
    async with TestSession() as db:
        assert await P.get_adjustment_owned(db, owner, result.adjustment_id) is None


async def test_account_deletion_detects_review_and_dismissal_without_adjustment(
        monkeypatch):
    from app.core.config import settings
    from app.posture import purge

    monkeypatch.setattr(
        settings,
        "PURGE_ENCRYPTION_KEY",
        "0123456789abcdef" * 4,
    )
    owner = str(uuid.uuid4())
    async with TestSession() as db:
        plan_id, _session_id, _prescription_id = await _seed_plan(db, owner)
        db.add(TrainingWeeklyReview(
            user_id=uuid.UUID(owner),
            plan_version_id=plan_id,
            week_index=1,
            review_version=1,
            input_fingerprint="f" * 64,
            period_start=TODAY,
            period_end=TODAY,
            facts={},
            proposal_codes=[],
            adaptive_policy_version="adaptive-v1",
            training_policy_version="policy-v1",
            catalog_version="catalog-v1",
            source_manifest_version="manifest-v1",
        ))
        db.add(PostureRecheckDismissal(
            user_id=uuid.UUID(owner),
            plan_version_id=plan_id,
            due_reason="cycle_complete",
            dismissed_at=datetime.now(timezone.utc),
        ))
        await db.execute(
            delete(IdempotencyRecord).where(
                IdempotencyRecord.user_id == uuid.UUID(owner)
            )
        )
        await db.commit()

    async with TestSession() as db:
        purged = await purge.run_purge(
            db, owner, purge.FakeObjectStore(), trigger="account_deletion"
        )
        assert purged.status == "completed"
    async with TestSession() as db:
        reviews = await db.execute(
            select(TrainingWeeklyReview).where(
                TrainingWeeklyReview.user_id == uuid.UUID(owner)
            )
        )
        dismissals = await db.execute(
            select(PostureRecheckDismissal).where(
                PostureRecheckDismissal.user_id == uuid.UUID(owner)
            )
        )
        assert reviews.scalar_one_or_none() is None
        assert dismissals.scalar_one_or_none() is None


@requires_pg
@pytest.mark.requires_pg
async def test_pg_concurrent_same_adjustment_key_records_once(
        pg_session_factory):
    if not pg_available:
        pytest.skip(skip_reason)
    owner = str(uuid.uuid4())
    seed = pg_session_factory()
    plan_id, session_id, prescription_id = await _seed_plan(seed, owner)
    args = _adjustment_args(plan_id, session_id, prescription_id)

    async def write():
        session = pg_session_factory()
        return await P.record_adjustment(session, owner, **args)

    results = await asyncio.gather(write(), write())
    assert sorted(result.status for result in results) == ["recorded", "replayed"]
    assert results[0].adjustment_id == results[1].adjustment_id
    verify = pg_session_factory()
    rows = await P.list_plan_adjustments(verify, owner, plan_id)
    assert len(rows) == 1
