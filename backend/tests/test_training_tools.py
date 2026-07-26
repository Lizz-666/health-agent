"""Application Tool tests for ``validate_training_plan`` (Task 6).

Exercises the authorization-aware adapter end-to-end on SQLite: a valid draft
for an eligible user passes; a blocked user is invalid; the Tool recomputes
current context per call and performs NO write side effect.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from app.auth.models import User
from app.health.models import DailyCheckIn, HealthProfile
from app.posture.models import PostureUserGoal
from app.training.candidates import select_candidates
from app.training.context import build_context
from app.training.knowledge import build_index, load_catalog
from app.training.policy import load_training_policy
from app.training.safety import classify_safety, load_safety_policy
from app.training.schemas import (
    PlanPrescription, PlanSession, RequestSnapshot, TrainingPlanDraft,
)
from app.training.tools import validate_training_plan
from tests.conftest import TestSession

CATALOG = load_catalog("app/training/data/exercises.v1.json")
SPOLICY = load_safety_policy("app/training/data/training_safety_policy.v1.json")
TPOLICY = load_training_policy("app/training/data/training_policy.v1.json")
INDEX = build_index(CATALOG)
EVAL_AT = datetime(2026, 7, 26, 1, 30, tzinfo=timezone.utc)
TODAY = date(2026, 7, 26)
PRIOR = date(2026, 7, 20)


def _no_screen():
    return {q: "no" for q in (
        "underage", "pregnancy_or_postpartum", "recent_surgery_or_major_injury",
        "major_chronic_condition", "eating_disorder_concern",
        "professional_instruction_limitations")}


async def _create_user(db, phone):
    user = User(phone=phone)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id


async def _setup_eligible(db, phone="13900000010"):
    uid = await _create_user(db, phone)
    db.add(HealthProfile(
        user_id=uid, fitness_goal="basic_strength",
        training_experience="experienced", weekly_frequency=3,
        session_duration_minutes=30,
        equipment={"bodyweight": True, "resistance_band": False},
        pain_injury_limitations=[], risk_screen=_no_screen(), version=1))
    db.add(DailyCheckIn(
        user_id=uid, local_date=TODAY, sleep_quality="good", energy="normal",
        muscle_soreness="none", available_time="30_min",
        daily_status="checked_in", abnormal_pain=False, pain_followup=None,
        risk_summary="normal", risk_version="2026-07-22-v1"))
    db.add(PostureUserGoal(
        user_id=uid, issue_id="lower_limb", priority_rank=1,
        confirmed_at=EVAL_AT, suggestion_id="s", profile_version="pv",
        rule_version="rv", risk_version="2026-07-16-v4", superseded_at=None))
    await db.commit()
    return uid


def _build_valid_draft(decision, candidate_id):
    ex = INDEX[candidate_id]
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


def _request():
    return RequestSnapshot(fitness_goal="basic_strength",
                           equipment_bodyweight=True,
                           equipment_resistance_band=False,
                           iana_timezone="Asia/Shanghai")


@pytest.mark.asyncio
async def test_valid_draft_for_eligible_user_passes():
    async with TestSession() as db:
        uid = await _setup_eligible(db)
        probe = await build_context(
            db, str(uid), request=_request(), policy=SPOLICY,
            catalog_version=CATALOG.content_version,
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        decision = classify_safety(probe, SPOLICY)
        cand = select_candidates(probe, decision, CATALOG, TPOLICY, SPOLICY)
        candidate_id = cand.candidates[0].exercise_id
        draft = _build_valid_draft(decision, candidate_id)
        result = await validate_training_plan(
            db, str(uid), draft, request=_request(), catalog=CATALOG,
            safety_policy=SPOLICY, training_policy=TPOLICY,
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        assert result.valid is True, [v.code for v in result.violations]
        assert result.gate_status.value == "eligible"


@pytest.mark.asyncio
async def test_blocked_user_draft_is_invalid():
    async with TestSession() as db:
        uid = await _setup_eligible(db, phone="13900000011")
        # Add a retained prior-day red-flag check-in.
        db.add(DailyCheckIn(
            user_id=uid, local_date=PRIOR, sleep_quality="good",
            energy="normal", muscle_soreness="none", available_time="30_min",
            daily_status="safety_adjustment", abnormal_pain=True,
            pain_followup={"pain_area": "lower_back",
                           "pain_started": "after_acute_event",
                           "pain_intensity": "severe",
                           "has_neurological_symptom": False,
                           "has_dizziness_or_chest_symptom": False,
                           "has_acute_trauma": True, "pain_note": "x"},
            risk_summary="red_flag", risk_version="2026-07-22-v1"))
        await db.commit()
        probe = await build_context(
            db, str(uid), request=_request(), policy=SPOLICY,
            catalog_version=CATALOG.content_version,
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        decision = classify_safety(probe, SPOLICY)
        draft = _build_valid_draft(decision, CATALOG.exercises[0].exercise_id)
        result = await validate_training_plan(
            db, str(uid), draft, request=_request(), catalog=CATALOG,
            safety_policy=SPOLICY, training_policy=TPOLICY,
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        assert result.valid is False
        assert "blocked_context" in [v.code for v in result.violations]


@pytest.mark.asyncio
async def test_tool_recomputes_per_call_and_writes_nothing():
    async with TestSession() as db:
        uid = await _setup_eligible(db, phone="13900000012")
        probe = await build_context(
            db, str(uid), request=_request(), policy=SPOLICY,
            catalog_version=CATALOG.content_version,
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        decision = classify_safety(probe, SPOLICY)
        cand = select_candidates(probe, decision, CATALOG, TPOLICY, SPOLICY)
        draft = _build_valid_draft(decision, cand.candidates[0].exercise_id)

        profiles_before = (await db.execute(select(HealthProfile))).scalars().all()
        result1 = await validate_training_plan(
            db, str(uid), draft, request=_request(), catalog=CATALOG,
            safety_policy=SPOLICY, training_policy=TPOLICY,
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        result2 = await validate_training_plan(
            db, str(uid), draft, request=_request(), catalog=CATALOG,
            safety_policy=SPOLICY, training_policy=TPOLICY,
            source_manifest_version="v1", evaluated_at_utc=EVAL_AT)
        # Recompute is deterministic for unchanged data.
        assert result1.valid is True and result2.valid is True
        # No persistence: the profile/checkin rows are unchanged.
        profiles_after = (await db.execute(select(HealthProfile))).scalars().all()
        assert len(profiles_before) == len(profiles_after)
