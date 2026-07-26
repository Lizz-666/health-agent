"""Async adapter integration tests for the training safety context (Task 4).

Runs the read-adapter ``build_context`` against real sessions on both SQLite
(``TestSession``) and disposable PostgreSQL 16 (``pg_session``), verifying:
- health/posture composition from existing domain-owned read services;
- account isolation (a user never sees another user's sources);
- deleted / missing source behavior;
- the narrow active-posture-goal read query;
- recomputation that does not trust stored labels.

All data is synthetic. No posture/health domain code is modified.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest

from app.auth.models import User
from app.health.models import DailyCheckIn, HealthProfile
from app.posture.models import PostureUserGoal
from app.training.context import build_context
from app.training.safety import classify_safety, load_safety_policy
from app.training.schemas import GateStatus, RequestSnapshot
from tests.conftest import TestSession
from tests.conftest_pg import requires_pg

POLICY = load_safety_policy("app/training/data/training_safety_policy.v1.json")
EVAL_AT = datetime(2026, 7, 26, 1, 30, tzinfo=timezone.utc)
TODAY = date(2026, 7, 26)
PRIOR = date(2026, 7, 20)
HEALTH_RISK_VERSION = "2026-07-22-v1"


def _all_no_screen():
    return {q: "no" for q in (
        "underage", "pregnancy_or_postpartum", "recent_surgery_or_major_injury",
        "major_chronic_condition", "eating_disorder_concern",
        "professional_instruction_limitations")}


async def _create_user(db, phone: str) -> uuid.UUID:
    user = User(phone=phone)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id


async def _add_profile(db, uid, *, experience="experienced",
                       pain=None, risk_screen=None):
    db.add(HealthProfile(
        user_id=uid, fitness_goal="basic_strength",
        training_experience=experience, weekly_frequency=3,
        session_duration_minutes=30,
        equipment={"bodyweight": True, "resistance_band": False},
        pain_injury_limitations=pain if pain is not None else [],
        risk_screen=risk_screen or _all_no_screen(), version=1))
    await db.commit()


async def _add_checkin(db, uid, local_date, *, abnormal=False,
                       followup=None, risk_summary="normal"):
    db.add(DailyCheckIn(
        user_id=uid, local_date=local_date, sleep_quality="good",
        energy="normal", muscle_soreness="none", available_time="30_min",
        daily_status="checked_in", abnormal_pain=abnormal,
        pain_followup=followup, risk_summary=risk_summary,
        risk_version=HEALTH_RISK_VERSION))
    await db.commit()


async def _add_goal(db, uid, issue_id="lower_limb"):
    db.add(PostureUserGoal(
        user_id=uid, issue_id=issue_id, priority_rank=1,
        confirmed_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
        suggestion_id="sugg-1", profile_version="pv-1",
        rule_version="rv-1", risk_version="2026-07-16-v4",
        superseded_at=None))
    await db.commit()


def _red_flag_followup():
    return {
        "pain_area": "lower_back", "pain_started": "after_acute_event",
        "pain_intensity": "severe", "has_neurological_symptom": False,
        "has_dizziness_or_chest_symptom": False, "has_acute_trauma": True,
        "pain_note": "synthetic note",
    }


async def _assert_eligible_adapter(db):
    uid = await _create_user(db, "13900000001")
    await _add_profile(db, uid)
    await _add_checkin(db, uid, TODAY)
    await _add_goal(db, uid)
    ctx = await build_context(
        db, str(uid), request=RequestSnapshot(iana_timezone="Asia/Shanghai"),
        policy=POLICY, catalog_version="v1cat",
        source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
    assert ctx.health.configured
    assert ctx.health.fitness_goal == "basic_strength"
    assert ctx.checkin.present
    assert ctx.checkin.recomputed_risk == "normal"
    assert ctx.posture.goals, "narrow active-goal read must find the goal"
    assert ctx.posture.goals[0].issue_id == "lower_limb"
    assert ctx.posture.goals[0].active is True
    decision = classify_safety(ctx, POLICY)
    assert decision.gate_status is GateStatus.eligible


@pytest.mark.asyncio
async def test_adapter_builds_eligible_context_sqlite():
    async with TestSession() as db:
        await _assert_eligible_adapter(db)


@requires_pg
@pytest.mark.asyncio
async def test_adapter_builds_eligible_context_postgresql(pg_session):
    await _assert_eligible_adapter(pg_session)


@pytest.mark.asyncio
async def test_adapter_account_isolation_sqlite():
    async with TestSession() as db:
        a = await _create_user(db, "13900000001")
        b = await _create_user(db, "13900000002")
        await _add_profile(db, a)
        await _add_checkin(db, a, TODAY)
        await _add_goal(db, a)
        # User B has nothing of their own.
        ctx_b = await build_context(
            db, str(b), request=RequestSnapshot(iana_timezone="Asia/Shanghai"),
            policy=POLICY, catalog_version="v1cat",
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        assert ctx_b.health.configured is False
        assert ctx_b.checkin.present is False
        assert ctx_b.posture.goals == []
        assert (classify_safety(ctx_b, POLICY).gate_status
                is GateStatus.clarification_required)
        # User A still resolves to eligible.
        ctx_a = await build_context(
            db, str(a), request=RequestSnapshot(iana_timezone="Asia/Shanghai"),
            policy=POLICY, catalog_version="v1cat",
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        assert classify_safety(ctx_a, POLICY).gate_status is GateStatus.eligible


@pytest.mark.asyncio
async def test_adapter_missing_profile_yields_clarification():
    async with TestSession() as db:
        uid = await _create_user(db, "13900000003")
        # No profile / checkin / goal.
        ctx = await build_context(
            db, str(uid), request=RequestSnapshot(iana_timezone="Asia/Shanghai"),
            policy=POLICY, catalog_version="v1cat",
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        assert ctx.health.configured is False
        assert (classify_safety(ctx, POLICY).gate_status
                is GateStatus.clarification_required)


@pytest.mark.asyncio
async def test_adapter_missing_current_checkin_yields_clarification():
    async with TestSession() as db:
        uid = await _create_user(db, "13900000004")
        await _add_profile(db, uid)
        await _add_goal(db, uid)
        # No check-in for TODAY.
        ctx = await build_context(
            db, str(uid), request=RequestSnapshot(iana_timezone="Asia/Shanghai"),
            policy=POLICY, catalog_version="v1cat",
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        d = classify_safety(ctx, POLICY)
        assert d.gate_status is GateStatus.clarification_required
        assert "current_day_checkin" in d.missing_fields


@pytest.mark.asyncio
async def test_adapter_missing_posture_goal_yields_clarification():
    async with TestSession() as db:
        uid = await _create_user(db, "13900000005")
        await _add_profile(db, uid)
        await _add_checkin(db, uid, TODAY)
        # No posture goal.
        ctx = await build_context(
            db, str(uid), request=RequestSnapshot(iana_timezone="Asia/Shanghai"),
            policy=POLICY, catalog_version="v1cat",
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        d = classify_safety(ctx, POLICY)
        assert d.gate_status is GateStatus.clarification_required
        assert "confirmed_posture_goal" in d.missing_fields


@pytest.mark.asyncio
async def test_adapter_recomputes_retained_red_flag_not_trusting_stored_label():
    async with TestSession() as db:
        uid = await _create_user(db, "13900000006")
        await _add_profile(db, uid)
        await _add_checkin(db, uid, TODAY)
        await _add_goal(db, uid)
        # A prior-day abnormal check-in whose STORED label says "normal" but
        # whose structured follow-up recomputes to red_flag.
        await _add_checkin(db, uid, PRIOR, abnormal=True,
                           followup=_red_flag_followup(),
                           risk_summary="normal")  # stored label deliberately wrong
        ctx = await build_context(
            db, str(uid), request=RequestSnapshot(iana_timezone="Asia/Shanghai"),
            policy=POLICY, catalog_version="v1cat",
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        assert any(r.recomputed_risk == "red_flag" for r in ctx.retained_pain)
        assert (classify_safety(ctx, POLICY).gate_status
                is GateStatus.red_flag)


@pytest.mark.asyncio
async def test_adapter_source_correction_clears_retained_red_flag():
    # Same user but WITHOUT the prior red-flag record -> not red_flag.
    async with TestSession() as db:
        uid = await _create_user(db, "13900000007")
        await _add_profile(db, uid)
        await _add_checkin(db, uid, TODAY)
        await _add_goal(db, uid)
        ctx = await build_context(
            db, str(uid), request=RequestSnapshot(iana_timezone="Asia/Shanghai"),
            policy=POLICY, catalog_version="v1cat",
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        assert ctx.retained_pain == []
        assert (classify_safety(ctx, POLICY).gate_status
                is GateStatus.eligible)
