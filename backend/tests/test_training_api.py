"""Phase 4 training API tests (Task 4).

Two layers:

1. HTTP contract / auth / validation / ownership / blocking-gate error paths
   through the real FastAPI stack (no eligible posture context needed - blocking
   gates and empty-state responses do not require one).
2. Service-level happy path (generate -> confirm -> active -> today -> feedback
   -> substitute) with ``service._classify`` monkeypatched to an eligible
   context, so the generator, persistence, validation, freshness, and ownership
   orchestration run for real while only the posture-backed context assembly is
   stubbed. Synthetic data only.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import TestSession  # noqa: E402

from app.auth.models import User
from app.core.security import create_access_token
from app.training import service
from app.training.safety import classify_safety, load_safety_policy
from app.training.schemas import TrainingSafetyContext

SPOLICY = load_safety_policy("app/training/data/training_safety_policy.v1.json")
EVAL_AT = datetime(2026, 7, 27, 2, 0, tzinfo=timezone.utc)

_NO_SCREEN = {q: "no" for q in (
    "underage", "pregnancy_or_postpartum", "recent_surgery_or_major_injury",
    "major_chronic_condition", "eating_disorder_concern",
    "professional_instruction_limitations")}


def _eligible_ctx(*, goal="basic_strength", freq=3):
    from app.training import service as svc
    cat = svc.catalog()
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


# --- helpers ----------------------------------------------------------------


async def _seed_user(user_id: str, phone: str):
    async with TestSession() as db:
        db.add(User(id=uuid.UUID(user_id), phone=phone))
        await db.commit()


def _auth(user_id: str):
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def _draft_body(*, goal="basic_strength", freq=3, key="k1", tz="Asia/Shanghai"):
    return {
        "fitness_goal": goal, "weekly_frequency": freq,
        "session_duration_minutes": 30, "equipment_bodyweight": True,
        "equipment_resistance_band": False, "iana_timezone": tz,
        "idempotency_key": key,
    }


# === HTTP contract / auth / validation =====================================


async def test_openapi_exposes_training_endpoints_with_security(client):
    spec = (await client.get("/openapi.json")).json()
    paths = spec["paths"]
    expected = [
        ("/api/v1/training/plans:draft", "post"),
        ("/api/v1/training/plans/draft", "get"),
        ("/api/v1/training/plans:confirm", "post"),
        ("/api/v1/training/plans/active", "get"),
        ("/api/v1/training/plans/today", "get"),
    ]
    for path, method in expected:
        assert path in paths, f"missing path {path}"
        assert method in paths[path], f"missing {method} {path}"
    # Every training endpoint requires JWT security.
    for path, methods in paths.items():
        if path.startswith("/api/v1/training/"):
            for method, op in methods.items():
                if method in ("get", "post", "put", "delete"):
                    assert op.get("security"), f"{method} {path} has no security scheme"


@pytest.mark.parametrize("method,path", [
    ("post", "/api/v1/training/plans:draft"),
    ("get", "/api/v1/training/plans/draft"),
    ("post", "/api/v1/training/plans:confirm"),
    ("get", "/api/v1/training/plans/active"),
    ("get", "/api/v1/training/plans/today?iana_timezone=Asia/Shanghai"),
])
async def test_endpoints_require_auth(client, method, path):
    fn = getattr(client, method)
    resp = await fn(path, json={}) if method == "post" else await fn(path)
    assert resp.status_code == 401, (method, path, resp.status_code)


async def test_draft_rejects_invalid_body(client):
    uid = str(uuid.uuid4())
    await _seed_user(uid, "13800010001")
    # missing required fields
    resp = await client.post("/api/v1/training/plans:draft",
                             json={"idempotency_key": "k"}, headers=_auth(uid))
    assert resp.status_code == 422


async def test_get_draft_active_today_empty_for_new_user(client):
    uid = str(uuid.uuid4())
    await _seed_user(uid, "13800010002")
    h = _auth(uid)
    assert (await client.get("/api/v1/training/plans/draft", headers=h)).json()[
        "has_draft"] is False
    assert (await client.get("/api/v1/training/plans/active", headers=h)).json()[
        "has_active"] is False
    today = await client.get(
        "/api/v1/training/plans/today?iana_timezone=Asia/Shanghai", headers=h)
    assert today.json()["state"] == "no_active_plan"


async def test_confirm_without_pending_draft_is_409(client):
    uid = str(uuid.uuid4())
    await _seed_user(uid, "13800010003")
    resp = await client.post("/api/v1/training/plans:confirm",
                             json={**_draft_body(key="c1")}, headers=_auth(uid))
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_pending_draft"


async def test_feedback_substitute_without_active_plan_is_409(client):
    uid = str(uuid.uuid4())
    await _seed_user(uid, "13800010004")
    sid = str(uuid.uuid4())
    h = _auth(uid)
    fb = await client.post(
        f"/api/v1/training/plans/sessions/{sid}:feedback?iana_timezone=Asia/Shanghai",
        json={"outcome_state": "completed", "idempotency_key": "f1"}, headers=h)
    assert fb.status_code == 409
    # Use a real catalog substitution pair so the request reaches the
    # active-plan check (rather than failing on exercise validation).
    cat = service.catalog()
    pair = None
    for ex in cat.exercises:
        if ex.substitution_ids:
            pair = (ex.exercise_id, ex.substitution_ids[0])
            break
    assert pair is not None, "catalog has no substitution pair"
    orig, repl = pair
    sub = await client.post(
        f"/api/v1/training/plans/sessions/{sid}:substitute?iana_timezone=Asia/Shanghai",
        json={"original_exercise_id": orig, "replacement_exercise_id": repl,
              "idempotency_key": "s1"}, headers=h)
    assert sub.status_code == 409


async def test_restricted_user_cannot_generate(client):
    from app.health.models import HealthProfile
    uid = str(uuid.uuid4())
    await _seed_user(uid, "13800010005")
    screen = dict(_NO_SCREEN)
    screen["pregnancy_or_postpartum"] = "yes"
    async with TestSession() as db:
        db.add(HealthProfile(
            user_id=uuid.UUID(uid), fitness_goal="basic_strength",
            training_experience="experienced", weekly_frequency=3,
            session_duration_minutes=30,
            equipment={"bodyweight": True, "resistance_band": False},
            pain_injury_limitations=[], risk_screen=screen,
            allergies=[], diet_exclusions=[], version=1))
        await db.commit()
    resp = await client.post("/api/v1/training/plans:draft",
                             json=_draft_body(), headers=_auth(uid))
    assert resp.status_code == 409
    assert resp.json()["code"] == "restricted_no_plan"


async def test_cross_user_isolation(client):
    uid_a = str(uuid.uuid4())
    uid_b = str(uuid.uuid4())
    await _seed_user(uid_a, "13800010006")
    await _seed_user(uid_b, "13800010007")
    hb = _auth(uid_b)
    # User A has nothing; user B cannot conjure or read A's plans.
    assert (await client.get("/api/v1/training/plans/draft", headers=hb)).json()[
        "has_draft"] is False
    # Confirming as B yields no_pending_draft, not A's data.
    resp = await client.post("/api/v1/training/plans:confirm",
                             json={**_draft_body(key="c")}, headers=hb)
    assert resp.status_code == 409


# === service-level happy path (real generator/persistence/validation) ======


@pytest.fixture
async def eligible_user(monkeypatch):
    uid = str(uuid.uuid4())
    await _seed_user(uid, "13800010020")
    ctx = _eligible_ctx()
    decision = classify_safety(ctx, SPOLICY)

    async def fake_classify(db, user_id, request, now=None):
        return ctx, decision

    monkeypatch.setattr(service, "_classify", fake_classify)
    return uid, ctx, decision


async def test_service_generate_confirm_active_today_feedback_substitute(
        eligible_user, monkeypatch):
    from app.training import service as svc
    from app.training.schemas_api import (
        ConfirmRequest, DraftRequest, FeedbackRequest, SubstitutionRequest)

    uid, ctx, _decision = eligible_user
    fixed_now = datetime(2026, 7, 27, 1, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(svc, "_utc_now", lambda: fixed_now)

    async with TestSession() as db:
        draft = await svc.generate_draft(db, uid, DraftRequest(
            **{**_draft_body(key="gen1")}))
        assert draft.has_draft is True
        assert draft.draft.status == "draft"
        pending_id = draft.draft.plan_version_id

        # Replay (same key + body) returns the same pending draft.
        replay = await svc.generate_draft(db, uid, DraftRequest(
            **{**_draft_body(key="gen1")}))
        assert replay.draft.plan_version_id == pending_id

        confirmed = await svc.confirm(db, uid, ConfirmRequest(
            **{**_draft_body(key="conf1")}))
        assert confirmed.plan.status == "active"
        assert confirmed.plan.plan_version_id == pending_id

        active = await svc.get_active(db, uid)
        assert active.has_active is True
        assert active.plan.plan_version_id == pending_id

        # Confirm replay is idempotent.
        replay_confirm = await svc.confirm(db, uid, ConfirmRequest(
            **{**_draft_body(key="conf1")}))
        assert replay_confirm.plan.plan_version_id == pending_id

        # Today: deterministic weekday lookup against the server-derived date.
        today = await svc.get_today(db, uid, "Asia/Shanghai")
        assert today.state in ("session", "rest_day", "blocked")
        if today.state == "session":
            assert today.session.prescriptions
            session_id = today.session.session_id
            # Every prescription traces to a catalog exercise.
            for p in today.session.prescriptions:
                assert p.exercise is not None

            # One substitution per session/day; the replacement must be an
            # allowed substitution of the original.
            orig = today.session.prescriptions[0].exercise_id
            allowed = today.session.prescriptions[0].exercise.substitution_ids
            if allowed:
                repl = allowed[0]
                sub1 = await svc.record_substitution(
                    db, uid, session_id, SubstitutionRequest(
                        original_exercise_id=orig, replacement_exercise_id=repl,
                        idempotency_key="sub1"), "Asia/Shanghai")
                assert sub1.status == "recorded"
                effective_today = await svc.get_today(db, uid, "Asia/Shanghai")
                assert effective_today.substitution_applied is True
                assert effective_today.session.prescriptions[0].exercise_id == repl
                # Same (session, day) with a different key -> conflict (one per
                # session/day). Replay with the same key returns "replayed".
                replay_sub = await svc.record_substitution(
                    db, uid, session_id, SubstitutionRequest(
                        original_exercise_id=orig, replacement_exercise_id=repl,
                        idempotency_key="sub1"), "Asia/Shanghai")
                assert replay_sub.status == "replayed"
                with pytest.raises(Exception):
                    await svc.record_substitution(
                        db, uid, session_id, SubstitutionRequest(
                            original_exercise_id=orig, replacement_exercise_id=repl,
                            idempotency_key="sub2"), "Asia/Shanghai")

            # Feedback closes the day's execution state and is idempotent.
            fb1 = await svc.record_feedback(db, uid, session_id, FeedbackRequest(
                outcome_state="completed", idempotency_key="fb1"),
                "Asia/Shanghai")
            assert fb1.status == "recorded"
            execution_context = svc._execution_context

            async def must_not_recheck(*_args, **_kwargs):
                raise AssertionError("idempotent replay re-ran execution checks")

            monkeypatch.setattr(svc, "_execution_context", must_not_recheck)
            fb2 = await svc.record_feedback(db, uid, session_id, FeedbackRequest(
                outcome_state="completed", idempotency_key="fb1"),
                "Asia/Shanghai")
            assert fb2.status == "replayed"
            monkeypatch.setattr(svc, "_execution_context", execution_context)
            completed_today = await svc.get_today(db, uid, "Asia/Shanghai")
            assert completed_today.feedback_outcome_state == "completed"
            if allowed:
                replay_after_feedback = await svc.record_substitution(
                    db, uid, session_id, SubstitutionRequest(
                        original_exercise_id=orig,
                        replacement_exercise_id=repl,
                        idempotency_key="sub1"), "Asia/Shanghai")
                assert replay_after_feedback.status == "replayed"


async def test_service_confirm_rejects_stale_context(monkeypatch):
    from app.training import service as svc
    from app.training.schemas_api import ConfirmRequest, DraftRequest
    uid = str(uuid.uuid4())
    await _seed_user(uid, "13800010021")
    ctx = _eligible_ctx()
    decision = classify_safety(ctx, SPOLICY)

    async with TestSession() as db:
        async def fake(db, user_id, request, now=None):
            return ctx, decision
        monkeypatch.setattr(svc, "_classify", fake)
        await svc.generate_draft(db, uid, DraftRequest(**{**_draft_body(key="g")}))
        # Now change the context: a different profile_version makes the fingerprint
        # diverge, so confirm must reject as stale.
        stale_ctx = ctx.model_copy(update={
            "health": ctx.health.model_copy(update={"profile_version": 2})})

        async def fake_stale(db, user_id, request, now=None):
            return stale_ctx, classify_safety(stale_ctx, SPOLICY)
        monkeypatch.setattr(svc, "_classify", fake_stale)
        from app.core.exceptions import AppException
        with pytest.raises(AppException) as exc:
            await svc.confirm(db, uid, ConfirmRequest(**{**_draft_body(key="c")}))
        assert exc.value.code == "stale_context"


async def test_today_advances_by_confirmation_week_and_then_completes(
        eligible_user, monkeypatch):
    from app.training.schemas_api import ConfirmRequest, DraftRequest

    uid, _ctx, _decision = eligible_user
    confirmed_at = datetime(2026, 7, 27, 0, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(service, "_utc_now", lambda: confirmed_at)
    async with TestSession() as db:
        await service.generate_draft(db, uid, DraftRequest(**_draft_body(key="g-weeks")))
        await service.confirm(db, uid, ConfirmRequest(**_draft_body(key="c-weeks")))

        for expected_week in (1, 2, 3, 4):
            current = confirmed_at + timedelta(days=7 * (expected_week - 1))
            monkeypatch.setattr(service, "_utc_now", lambda current=current: current)
            today = await service.get_today(db, uid, "Asia/Shanghai")
            assert today.state == "session"
            assert today.session.week_index == expected_week

        monkeypatch.setattr(
            service, "_utc_now", lambda: confirmed_at + timedelta(days=28))
        complete = await service.get_today(db, uid, "Asia/Shanghai")
        assert complete.state == "plan_complete"
        assert complete.session is None


async def test_execution_writes_only_target_the_actual_local_day(
        eligible_user, monkeypatch):
    from app.core.exceptions import AppException
    from app.training import persistence as persistence
    from app.training.schemas_api import ConfirmRequest, DraftRequest, FeedbackRequest

    uid, _ctx, _decision = eligible_user
    now = datetime(2026, 7, 27, 0, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(service, "_utc_now", lambda: now)
    async with TestSession() as db:
        await service.generate_draft(db, uid, DraftRequest(**_draft_body(key="g-day")))
        confirmed = await service.confirm(
            db, uid, ConfirmRequest(**_draft_body(key="c-day")))
        sessions = await persistence.load_sessions(
            db, uuid.UUID(confirmed.plan.plan_version_id))
        future_session = next(
            session for session in sessions
            if session.week_index == 2 and session.day_of_week == 1)

        with pytest.raises(AppException) as exc:
            await service.record_feedback(
                db, uid, str(future_session.session_id), FeedbackRequest(
                    outcome_state="completed", idempotency_key="wrong-day"),
                "Asia/Shanghai")
        assert exc.value.code == "session_not_today"


async def test_draft_replay_returns_the_recorded_version(
        eligible_user, monkeypatch):
    from app.training.schemas_api import DraftRequest

    uid, _ctx, _decision = eligible_user
    async with TestSession() as db:
        first = await service.generate_draft(
            db, uid, DraftRequest(**_draft_body(key="draft-first")))
        second = await service.generate_draft(
            db, uid, DraftRequest(**_draft_body(key="draft-second")))

        async def must_not_reclassify(*_args, **_kwargs):
            raise AssertionError("idempotent replay re-ran safety classification")

        monkeypatch.setattr(service, "_classify", must_not_reclassify)
        replay = await service.generate_draft(
            db, uid, DraftRequest(**_draft_body(key="draft-first")))
        assert first.draft.plan_version_id != second.draft.plan_version_id
        assert replay.draft.plan_version_id == first.draft.plan_version_id


async def test_confirm_idempotency_covers_the_complete_request(eligible_user):
    from app.core.exceptions import AppException
    from app.training.schemas_api import ConfirmRequest, DraftRequest

    uid, _ctx, _decision = eligible_user
    async with TestSession() as db:
        await service.generate_draft(db, uid, DraftRequest(**_draft_body(key="g-hash")))
        await service.confirm(db, uid, ConfirmRequest(**_draft_body(key="same-confirm")))
        changed = _draft_body(key="same-confirm")
        changed["session_duration_minutes"] = 45
        with pytest.raises(AppException) as exc:
            await service.confirm(db, uid, ConfirmRequest(**changed))
        assert exc.value.code == "idempotency_key_conflict"


async def test_confirm_revalidates_the_stored_draft(eligible_user, monkeypatch):
    from app.core.exceptions import AppException
    from app.training.schemas import PlanValidationResult, PlanViolation
    from app.training.schemas_api import ConfirmRequest, DraftRequest

    uid, _ctx, _decision = eligible_user
    async with TestSession() as db:
        await service.generate_draft(db, uid, DraftRequest(**_draft_body(key="g-validate")))

        def reject(*_args, **_kwargs):
            return PlanValidationResult(
                valid=False,
                gate_status=_decision.gate_status,
                decision_fingerprint=_decision.fingerprint,
                violations=[PlanViolation(
                    code="test_rejection", scope="plan", detail="synthetic")],
                profile_version=1,
                catalog_version=service.catalog().content_version,
                policy_version=service.TRAINING_POLICY.policy_version,
            )

        monkeypatch.setattr(service, "validate_plan", reject)
        with pytest.raises(AppException) as exc:
            await service.confirm(
                db, uid, ConfirmRequest(**_draft_body(key="c-validate")))
        assert exc.value.code == "stored_draft_invalid"


async def test_today_blocks_when_current_plan_validation_fails(
        eligible_user, monkeypatch):
    from app.training.schemas import PlanValidationResult, PlanViolation
    from app.training.schemas_api import ConfirmRequest, DraftRequest

    uid, _ctx, decision = eligible_user
    now = datetime(2026, 7, 27, 1, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(service, "_utc_now", lambda: now)
    async with TestSession() as db:
        await service.generate_draft(
            db, uid, DraftRequest(**_draft_body(key="g-today-validate")))
        await service.confirm(
            db, uid, ConfirmRequest(**_draft_body(key="c-today-validate")))

        def reject(*_args, **_kwargs):
            return PlanValidationResult(
                valid=False,
                gate_status=decision.gate_status,
                decision_fingerprint=decision.fingerprint,
                violations=[PlanViolation(
                    code="exercise_not_candidate",
                    scope="week1.d1.o1",
                    detail="synthetic current-context exclusion",
                )],
                profile_version=1,
                catalog_version=service.catalog().content_version,
                policy_version=service.TRAINING_POLICY.policy_version,
            )

        monkeypatch.setattr(service, "validate_plan", reject)
        today = await service.get_today(db, uid, "Asia/Shanghai")
        assert today.state == "blocked"
        assert today.session is None
        assert today.change_reason == "safety_revalidation_failed"
