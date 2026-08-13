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
from sqlalchemy import select

from app.auth.models import User
from app.health.models import DailyCheckIn, HealthProfile
from app.posture.models import PostureProfileEntry, PostureUserGoal
from app.posture.service import get_priority_suggestions
from app.training.candidates import select_candidates
from app.training.context import build_context
from app.training.knowledge import build_index, load_catalog
from app.training.policy import load_training_policy
from app.training.safety import classify_safety, load_safety_policy
from app.training.schemas import (
    GateStatus, PlanPrescription, PlanSession, RequestSnapshot,
    TrainingPlanDraft)
from app.training.tools import validate_training_plan
from tests.conftest import TestSession
from tests.conftest_pg import requires_pg

POLICY = load_safety_policy("app/training/data/training_safety_policy.v1.json")
TPOLICY = load_training_policy("app/training/data/training_policy.v1.json")
CATALOG = load_catalog("app/training/data/exercises.v1.json")
CATALOG_INDEX = build_index(CATALOG)
EVAL_AT = datetime(2026, 7, 26, 1, 30, tzinfo=timezone.utc)
TODAY = date(2026, 7, 26)
PRIOR = date(2026, 7, 20)
HEALTH_RISK_VERSION = "2026-07-22-v1"


def _tool_request():
    return RequestSnapshot(
        fitness_goal="basic_strength",
        equipment_bodyweight=True,
        equipment_resistance_band=False,
        weekly_frequency=3,
        session_duration_minutes=30,
        iana_timezone="Asia/Shanghai",
    )


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


async def _add_goal(db, uid, issue_id="LL-18"):
    db.add(PostureProfileEntry(
        user_id=uid, issue_id=issue_id, combined_severity="mild",
        certainty="confirmed", sources={}, has_conflict=False,
        risk_tier="normal", risk_version="2026-07-16-v4"))
    await db.commit()
    suggestions = await get_priority_suggestions(db, str(uid), now=EVAL_AT)
    candidate = next(
        item for item in suggestions["normal_candidates"]
        if item["issue_id"] == issue_id)
    assert candidate
    db.add(PostureUserGoal(
        user_id=uid, issue_id=issue_id, priority_rank=1,
        confirmed_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
        suggestion_id=suggestions["suggestion_id"],
        profile_version=suggestions["profile_version"],
        rule_version=suggestions["rule_version"],
        risk_version=suggestions["risk_version"],
        superseded_at=None))
    await db.commit()


def _red_flag_followup():
    return {
        "pain_area": "lower_back", "pain_started": "after_acute_event",
        "pain_intensity": "severe", "has_neurological_symptom": False,
        "has_dizziness_or_chest_symptom": False, "has_acute_trauma": True,
        "pain_note": "synthetic note",
    }


def _unknown_caution_followup():
    return {
        "pain_area": "unknown-zone", "pain_started": "recent_days",
        "pain_intensity": "mild", "has_neurological_symptom": False,
        "has_dizziness_or_chest_symptom": False, "has_acute_trauma": False,
        "pain_note": "synthetic note",
    }


async def _assert_eligible_adapter(db):
    uid = await _create_user(db, "13900000001")
    await _add_profile(db, uid)
    await _add_checkin(db, uid, TODAY)
    await _add_goal(db, uid)
    ctx = await build_context(
        db, str(uid), request=_tool_request(),
        policy=POLICY, catalog_version="v1cat",
        source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
    assert ctx.health.configured
    assert ctx.health.fitness_goal == "basic_strength"
    assert ctx.checkin.present
    assert ctx.checkin.recomputed_risk == "normal"
    assert ctx.posture.goals, "narrow active-goal read must find the goal"
    assert ctx.posture.goals[0].issue_id == "LL-18"
    assert ctx.posture.goals[0].active is True
    decision = classify_safety(ctx, POLICY)
    assert decision.gate_status is GateStatus.eligible


@pytest.mark.asyncio
async def test_adapter_builds_eligible_context_sqlite():
    async with TestSession() as db:
        await _assert_eligible_adapter(db)


@requires_pg
@pytest.mark.requires_pg
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
            db, str(b), request=_tool_request(),
            policy=POLICY, catalog_version="v1cat",
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        assert ctx_b.health.configured is False
        assert ctx_b.checkin.present is False
        assert ctx_b.posture.goals == []
        assert (classify_safety(ctx_b, POLICY).gate_status
                is GateStatus.clarification_required)
        # User A still resolves to eligible.
        ctx_a = await build_context(
            db, str(a), request=_tool_request(),
            policy=POLICY, catalog_version="v1cat",
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        assert classify_safety(ctx_a, POLICY).gate_status is GateStatus.eligible


@pytest.mark.asyncio
async def test_adapter_missing_profile_yields_clarification():
    async with TestSession() as db:
        uid = await _create_user(db, "13900000003")
        # No profile / checkin / goal.
        ctx = await build_context(
            db, str(uid), request=_tool_request(),
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
            db, str(uid), request=_tool_request(),
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
            db, str(uid), request=_tool_request(),
            policy=POLICY, catalog_version="v1cat",
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        d = classify_safety(ctx, POLICY)
        assert d.gate_status is GateStatus.clarification_required
        assert "confirmed_posture_goal" in d.missing_fields


@pytest.mark.asyncio
async def test_adapter_invalidates_goal_when_profile_is_no_longer_confirmed():
    async with TestSession() as db:
        uid = await _create_user(db, "13900000015")
        await _add_profile(db, uid)
        await _add_checkin(db, uid, TODAY)
        await _add_goal(db, uid)
        entry = await db.scalar(select(PostureProfileEntry).where(
            PostureProfileEntry.user_id == uid,
            PostureProfileEntry.issue_id == "LL-18"))
        entry.certainty = "provisional"
        await db.commit()
        ctx = await build_context(
            db, str(uid), request=_tool_request(),
            policy=POLICY, catalog_version="v1cat",
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        assert ctx.posture.goals[0].active is False
        assert (classify_safety(ctx, POLICY).gate_status
                is GateStatus.clarification_required)


@pytest.mark.asyncio
async def test_adapter_unknown_current_pain_area_requires_clarification():
    async with TestSession() as db:
        uid = await _create_user(db, "13900000016")
        await _add_profile(db, uid)
        await _add_goal(db, uid)
        await _add_checkin(
            db, uid, TODAY, abnormal=True,
            followup=_unknown_caution_followup(), risk_summary="normal")
        ctx = await build_context(
            db, str(uid), request=_tool_request(),
            policy=POLICY, catalog_version="v1cat",
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        assert ctx.checkin.pain_area_canonical is None
        assert (classify_safety(ctx, POLICY).gate_status
                is GateStatus.clarification_required)


@pytest.mark.asyncio
async def test_adapter_unknown_retained_pain_area_requires_clarification():
    async with TestSession() as db:
        uid = await _create_user(db, "13900000017")
        await _add_profile(db, uid)
        await _add_goal(db, uid)
        await _add_checkin(db, uid, TODAY)
        await _add_checkin(
            db, uid, PRIOR, abnormal=True,
            followup=_unknown_caution_followup(), risk_summary="normal")
        ctx = await build_context(
            db, str(uid), request=_tool_request(),
            policy=POLICY, catalog_version="v1cat",
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        assert ctx.retained_pain[0].pain_area_canonical is None
        assert (classify_safety(ctx, POLICY).gate_status
                is GateStatus.clarification_required)


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
            db, str(uid), request=_tool_request(),
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
            db, str(uid), request=_tool_request(),
            policy=POLICY, catalog_version="v1cat",
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        assert ctx.retained_pain == []
        assert (classify_safety(ctx, POLICY).gate_status
                is GateStatus.eligible)


# ---------------------------------------------------------------------------
# Task 6 additive: validate_training_plan Tool end-to-end (SQLite + PostgreSQL)
# ---------------------------------------------------------------------------


def _valid_tool_draft(decision, candidate_id):
    ex = CATALOG_INDEX[candidate_id]
    rx = ex.prescription
    presc = PlanPrescription(
        exercise_id=candidate_id, sets=rx.sets_min,
        reps=rx.reps_min if rx.mode.value == "reps" else None,
        duration_seconds=(rx.duration_seconds_min
                          if rx.mode.value == "duration" else None),
        rest_seconds=rx.rest_seconds_min)
    sessions = []
    for week in (1, 2, 3, 4):
        for order, day in enumerate((1, 3, 5), start=1):
            sessions.append(PlanSession(
                week_index=week, day_of_week=day, session_order=order,
                prescriptions=[presc]))
    return TrainingPlanDraft.model_validate({
        "draft_id": "d1", "requested_goal": "basic_strength",
        "source_context_fingerprint": decision.fingerprint,
        "profile_version": 1, "catalog_version": CATALOG.content_version,
        "policy_version": "v1", "source_manifest_version": "v1",
        "sessions": sessions})


async def _assert_tool_validates(db):
    uid = await _create_user(db, "13900000020")
    await _add_profile(db, uid)
    await _add_checkin(db, uid, TODAY)
    await _add_goal(db, uid)
    probe = await build_context(
        db, str(uid), request=_tool_request(), policy=POLICY,
        catalog_version=CATALOG.content_version,
        source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
    decision = classify_safety(probe, POLICY)
    cand = select_candidates(probe, decision, CATALOG, TPOLICY, POLICY)
    draft = _valid_tool_draft(decision, cand.candidates[0].exercise_id)
    result = await validate_training_plan(
        db, str(uid), draft, request=_tool_request(), catalog=CATALOG,
        safety_policy=POLICY, training_policy=TPOLICY,
        source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
    assert result.valid is True, [v.code for v in result.violations]
    assert result.gate_status is GateStatus.eligible


@pytest.mark.asyncio
async def test_tool_validates_valid_draft_sqlite():
    async with TestSession() as db:
        await _assert_tool_validates(db)


@requires_pg
@pytest.mark.requires_pg
@pytest.mark.asyncio
async def test_tool_validates_valid_draft_postgresql(pg_session):
    await _assert_tool_validates(pg_session)


@pytest.mark.asyncio
async def test_tool_blocked_context_on_retained_red_flag_sqlite():
    async with TestSession() as db:
        uid = await _create_user(db, "13900000021")
        await _add_profile(db, uid)
        await _add_checkin(db, uid, TODAY)
        await _add_goal(db, uid)
        await _add_checkin(db, uid, PRIOR, abnormal=True,
                           followup=_red_flag_followup(),
                           risk_summary="red_flag")
        probe = await build_context(
            db, str(uid), request=_tool_request(), policy=POLICY,
            catalog_version=CATALOG.content_version,
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        decision = classify_safety(probe, POLICY)
        draft = _valid_tool_draft(decision, CATALOG.exercises[0].exercise_id)
        result = await validate_training_plan(
            db, str(uid), draft, request=_tool_request(), catalog=CATALOG,
            safety_policy=POLICY, training_policy=TPOLICY,
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        assert result.valid is False
        assert "blocked_context" in [v.code for v in result.violations]
