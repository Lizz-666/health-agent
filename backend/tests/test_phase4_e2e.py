"""Phase 4 full-phase end-to-end acceptance tests (Task 7).

Cohesive synthetic journey tying the whole Phase 4 pipeline together:

    generate draft -> explicit confirm -> active plan -> today -> substitution
    -> feedback

plus a safety-matrix assertion that the deterministic engine blocks restricted /
red-flag / missing-data cases end-to-end (no plan can be produced or executed).
``service._classify`` is monkeypatched to an eligible context so the generator,
persistence, validation, freshness, and ownership orchestration run for real;
only the posture-backed context assembly is stubbed. Synthetic data only; no
LLM, no real health data.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from tests.conftest import TestSession  # noqa: E402

from app.auth.models import User
from app.training import service
from app.training.candidates import select_candidates
from app.training.generator import generate_plan_draft
from app.training.safety import classify_safety, load_safety_policy
from app.training.schemas import TrainingSafetyContext
from app.training.schemas_api import (
    ConfirmRequest,
    DraftRequest,
    FeedbackRequest,
    SubstitutionRequest,
)

SPOLICY = load_safety_policy("app/training/data/training_safety_policy.v1.json")
EVAL_AT = datetime(2026, 7, 27, 2, 0, tzinfo=timezone.utc)

_NO_SCREEN = {q: "no" for q in (
    "underage", "pregnancy_or_postpartum", "recent_surgery_or_major_injury",
    "major_chronic_condition", "eating_disorder_concern",
    "professional_instruction_limitations")}


def _eligible_ctx(*, goal="posture_improvement", freq=3):
    cat = service.catalog()
    return TrainingSafetyContext.model_validate({
        "health": {"configured": True, "fitness_goal": goal,
                   "training_experience": "experienced", "weekly_frequency": freq,
                   "session_duration_minutes": 30,
                   "equipment_bodyweight": True, "equipment_resistance_band": False,
                   "pain_limitations": [], "risk_screen": _NO_SCREEN,
                   "profile_version": 1, "profile_updated_at": EVAL_AT},
        "checkin": {"present": True, "local_date": "2026-07-27",
                    "recomputed_risk": "normal", "token": "t"},
        "retained_pain": [],
        "posture": {"active_signals_digest": "empty-signals-digest",
                    "global_risk_tier": "normal", "risk_version": "rv",
                    "goals": [{"issue_id": "lower_limb", "active": True,
                               "blocked": False, "confirmed_at": EVAL_AT,
                               "suggestion_id": "s1", "profile_version": "pv1",
                               "rule_version": "rv1", "risk_version": "rv"}]},
        "request": {"fitness_goal": goal, "equipment_bodyweight": True,
                    "equipment_resistance_band": False, "weekly_frequency": freq,
                    "session_duration_minutes": 30, "iana_timezone": "Asia/Shanghai"},
        "versions": {"policy_version": "v1", "catalog_version": cat.content_version,
                     "source_manifest_version": "v1", "schema_version": "v1"},
        "eval": {"evaluated_at_utc": EVAL_AT, "iana_timezone": "Asia/Shanghai",
                 "current_local_date": "2026-07-27", "timezone_trusted": True},
    })


def _draft_body(*, goal="posture_improvement", freq=3, key="k"):
    return {
        "fitness_goal": goal, "weekly_frequency": freq,
        "session_duration_minutes": 30, "equipment_bodyweight": True,
        "equipment_resistance_band": False, "iana_timezone": "Asia/Shanghai",
        "idempotency_key": key,
    }


@pytest.fixture
async def eligible_user(monkeypatch):
    uid = str(uuid.uuid4())
    async with TestSession() as db:
        db.add(User(id=uuid.UUID(uid), phone="13800020001"))
        await db.commit()
    ctx = _eligible_ctx()
    decision = classify_safety(ctx, SPOLICY)

    async def fake_classify(db, user_id, request, now=None):
        return ctx, decision

    monkeypatch.setattr(service, "_classify", fake_classify)
    return uid, ctx, decision


async def test_phase4_e2e_generate_confirm_today_substitute_feedback(eligible_user):
    """Full synthetic journey through one day of plan execution."""
    uid, _ctx, _decision = eligible_user
    async with TestSession() as db:
        # 1. Generate a draft.
        draft = await service.generate_draft(db, uid, DraftRequest(**_draft_body(key="gen")))
        assert draft.has_draft is True
        assert draft.draft.status == "draft"
        # Every prescription traces to a recommendation-ready catalog exercise.
        for s in draft.draft.sessions:
            assert s.prescriptions
            for p in s.prescriptions:
                assert p.exercise is not None

        # 2. Explicit confirm -> active, single active plan, version recorded.
        confirmed = await service.confirm(
            db,
            uid,
            ConfirmRequest(
                expected_plan_version_id=draft.draft.plan_version_id,
                **_draft_body(key="conf"),
            ),
        )
        assert confirmed.plan.status == "active"
        active = await service.get_active(db, uid)
        assert active.has_active is True
        assert active.plan.plan_version_id == confirmed.plan.plan_version_id

        # 3. Today: a session, rest day, or honest blocked state. When it is a
        #    session, every prescription is catalog-backed.
        today = await service.get_today(db, uid, "Asia/Shanghai")
        assert today.state in ("session", "rest_day", "blocked")
        if today.state == "session":
            session_id = today.session.session_id
            for p in today.session.prescriptions:
                assert p.exercise is not None

            # 4. One substitution within today's session (must be an allowed
            #    catalog relation).
            first = today.session.prescriptions[0]
            allowed = first.exercise.substitution_ids
            if allowed:
                repl = allowed[0]
                sub = await service.record_substitution(
                    db, uid, session_id, SubstitutionRequest(
                        original_exercise_id=first.exercise_id,
                        replacement_exercise_id=repl,
                        idempotency_key="sub"), "Asia/Shanghai")
                assert sub.status in ("recorded", "replayed")

            # 5. Daily feedback (one of the five outcome states).
            fb = await service.record_feedback(
                db, uid, session_id, FeedbackRequest(
                    outcome_state="completed", idempotency_key="fb"),
                "Asia/Shanghai")
            assert fb.status in ("recorded", "replayed")
            # Replay is idempotent (no second feedback row / same id).
            fb2 = await service.record_feedback(
                db, uid, session_id, FeedbackRequest(
                    outcome_state="completed", idempotency_key="fb"),
                "Asia/Shanghai")
            assert fb2.status == "replayed"


@pytest.mark.parametrize("gate_setup,expected_code", [
    ({"risk_screen_yes": "pregnancy_or_postpartum"}, "restricted_no_plan"),
    ({"checkin_risk": "red_flag"}, "red_flag_stop"),
    ({"missing_checkin": True}, "clarification_required"),
])
async def test_phase4_e2e_safety_matrix_blocks_generation(
    monkeypatch, gate_setup, expected_code
):
    """Restricted / red-flag / missing-data contexts never produce a plan."""
    uid = str(uuid.uuid4())
    async with TestSession() as db:
        db.add(User(id=uuid.UUID(uid), phone="13800020003"))
        await db.commit()

    base = {
        "fitness_goal": "posture_improvement", "weekly_frequency": 3,
        "session_duration_minutes": 30, "equipment_bodyweight": True,
        "equipment_resistance_band": False, "pain_limitations": [],
        "risk_screen": dict(_NO_SCREEN), "profile_version": 1,
        "profile_updated_at": EVAL_AT,
    }
    if "risk_screen_yes" in gate_setup:
        base["risk_screen"][gate_setup["risk_screen_yes"]] = "yes"
    checkin = {"present": True, "local_date": "2026-07-27",
               "recomputed_risk": gate_setup.get("checkin_risk", "normal"),
               "token": "t"}
    if gate_setup.get("missing_checkin"):
        checkin = {"present": False, "local_date": None,
                   "recomputed_risk": None, "token": None}

    cat = service.catalog()
    ctx = TrainingSafetyContext.model_validate({
        "health": {"configured": True, **base},
        "checkin": checkin,
        "retained_pain": [],
        "posture": {"active_signals_digest": "empty-signals-digest",
                    "global_risk_tier": "normal", "risk_version": "rv",
                    "goals": [{"issue_id": "lower_limb", "active": True,
                               "blocked": False, "confirmed_at": EVAL_AT,
                               "suggestion_id": "s1", "profile_version": "pv1",
                               "rule_version": "rv1", "risk_version": "rv"}]},
        "request": {"fitness_goal": "posture_improvement",
                    "equipment_bodyweight": True, "equipment_resistance_band": False,
                    "weekly_frequency": 3, "session_duration_minutes": 30,
                    "iana_timezone": "Asia/Shanghai"},
        "versions": {"policy_version": "v1", "catalog_version": cat.content_version,
                     "source_manifest_version": "v1", "schema_version": "v1"},
        "eval": {"evaluated_at_utc": EVAL_AT, "iana_timezone": "Asia/Shanghai",
                 "current_local_date": "2026-07-27", "timezone_trusted": True},
    })
    decision = classify_safety(ctx, SPOLICY)
    # The pure engine itself blocks at generation:
    cand = select_candidates(ctx, decision, cat, service.TRAINING_POLICY, SPOLICY)
    result = generate_plan_draft(ctx, decision, cand, cat, service.TRAINING_POLICY, SPOLICY)
    assert result.ok is False
    assert result.draft is None
    assert result.reason_codes[0] == expected_code


async def test_phase4_e2e_no_real_health_data_or_live_ai_in_engine():
    """The deterministic engine path used by Phase 4 calls no LLM/provider."""
    # generate_plan_draft is pure; it accepts only typed Phase 3 inputs and the
    # catalog/policy objects. There is no provider/HTTP import in the generator.
    import inspect
    from app.training import generator
    src = inspect.getsource(generator)
    for forbidden in ("openai", "anthropic", "dashscope", "requests.",
                      "httpx.", "urllib."):
        assert forbidden not in src, f"generator references {forbidden}"
