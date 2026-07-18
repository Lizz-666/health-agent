"""Tests for Phase 1 Task 7: posture Tool application layer (spec §10.0-§10.8).

Covers:
- ActorContext frozen / JWT-injected boundary
- Tool signature contract (no ``user_id`` business param; public Tools take
  no actor)
- All 8 Tools' typed contracts
- Auth / cross-user isolation
- PhotoOwnershipVerifier fail-closed default + owned/denied/unavailable fake;
  path prefix is never ownership proof; a fake-owned verifier alone does NOT
  enable the production photo gate
- Photo Tool gate ordering: closed gate -> PhotoAnalysisDisabled with ZERO
  ownership / idempotency / model / event calls
- Photo idempotency at the service orchestration layer (check before model,
  replay, conflict, purge 410, expiry, result_ref minimisation)
- Unified idempotency across photo / confirm_goals / safety_signal
- Priorities safety gate (recompute each call); confirm restricted/red_flag
  blocking; server-generated control values; ``priority_context_snapshot``
  rejected
- REST rewiring keeps paths / responses / error codes / OpenAPI compatible

All data is synthetic.
"""

import dataclasses
import inspect
import uuid as _uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import get_type_hints

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.actor_context import ActorContext, ConsentRecord, get_actor_context
from app.core.config import settings
from app.core.exceptions import AppException, NotFound
from app.posture import priority, service, tools
from app.posture.models import (
    IdempotencyRecord,
    PostureAssessmentEvent,
    PostureProfileEntry,
    PostureUserGoal,
)
from app.posture.risk_rules import RISK_VERSION
from app.posture.schemas import GoalInput, PhotoAssessRequest
from app.posture.tool_contracts import (
    PhotoAssessmentResult,
    PrioritySuggestionsResponse,
    SafetySignalResponse,
)
from app.upload import ownership
from tests.conftest import TestSession


# ---------------------------------------------------------------------------
# Helpers (mirror test_posture_priority / test_posture_safety)
# ---------------------------------------------------------------------------


async def _login_user(client, phone="13800138000"):
    await client.post("/api/v1/auth/send-code", json={"phone": phone})
    from app.auth.models import VerificationCode

    async with TestSession() as db:
        result = await db.execute(
            select(VerificationCode)
            .where(VerificationCode.phone == phone)
            .order_by(VerificationCode.created_at.desc())
        )
        code = result.scalar_one().code
    resp = await client.post(
        "/api/v1/auth/verify-login", json={"phone": phone, "code": code}
    )
    return resp.json()["access_token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _uid(token):
    from app.core.security import decode_token

    return decode_token(token)["sub"]


def _actor(user_id: str) -> ActorContext:
    return ActorContext(user_id=user_id)


def _consented_actor(user_id: str) -> ActorContext:
    return ActorContext(
        user_id=user_id,
        consent_record=ConsentRecord(
            record_id="synthetic-consent",
            purpose="posture_photo_analysis",
            status="active",
            granted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
    )


def _ai_result(level, **overrides):
    base = {
        "level": level,
        "confidence": 0.82,
        "evidence": ["evidence"],
        "suggestion": "建议",
        "need_retake": False,
        "retake_reason": "",
    }
    base.update(overrides)
    return base


async def _seed_entry(
    user_id,
    issue_id,
    *,
    severity="moderate",
    certainty="confirmed",
    risk_tier="normal",
    risk_version="phase1-initial-v1",
    sources=None,
    has_conflict=False,
):
    if sources is None:
        sources = [
            {
                "source": "self_test",
                "event_id": str(_uuid.uuid4()),
                "severity": severity,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
    entry = PostureProfileEntry(
        id=_uuid.uuid4(),
        user_id=_uuid.UUID(user_id),
        issue_id=issue_id,
        certainty=certainty,
        combined_severity=severity,
        sources=sources,
        has_conflict=has_conflict,
        risk_tier=risk_tier,
        risk_version=risk_version,
    )
    async with TestSession() as db:
        db.add(entry)
        await db.commit()
    return entry


# ===========================================================================
# ActorContext contract
# ===========================================================================


def test_actor_context_is_frozen():
    actor = ActorContext(user_id="u1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        actor.user_id = "tampered"


def test_actor_context_defaults_consentrisk_to_none():
    """Phase 1: consent_record / risk_context are None (no consent table)."""
    actor = ActorContext(user_id="u1")
    assert actor.consent_record is None
    assert actor.risk_context is None


def test_consent_record_is_immutable_and_purpose_scoped():
    consent = _consented_actor("u1").consent_record
    assert consent.permits_posture_photo_analysis() is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        consent.status = "withdrawn"


async def test_get_actor_context_builds_from_jwt(client):
    token = await _login_user(client)
    user_id = _uid(token)
    # The dependency itself is normally resolved by FastAPI; call the inner
    # function with the resolved user_id to verify it wraps identity correctly.
    actor = await get_actor_context(user_id=user_id)
    assert isinstance(actor, ActorContext)
    assert actor.user_id == user_id


# ===========================================================================
# Tool signature contract (spec §10.0: no model-controllable identity params)
# ===========================================================================


def test_public_tools_have_no_actor_param():
    """spec §10.1 / §10.2: list/get issue are public -- no actor / db param."""
    list_sig = inspect.signature(tools.list_posture_issues)
    get_sig = inspect.signature(tools.get_posture_issue)
    assert "actor" not in list_sig.parameters
    assert "db" not in list_sig.parameters
    assert "actor" not in get_sig.parameters
    assert "user_id" not in list_sig.parameters
    assert "user_id" not in get_sig.parameters


def test_identity_tools_take_actor_not_user_id():
    """Every identity-bearing Tool takes ``actor`` and never a bare ``user_id``."""
    for name in (
        "guide_posture_self_test",
        "analyze_posture_photo",
        "get_posture_profile",
        "suggest_posture_priorities",
        "confirm_posture_goals",
        "report_safety_signal",
    ):
        fn = getattr(tools, name)
        params = inspect.signature(fn).parameters
        assert "actor" in params, f"{name} missing actor param"
        assert "user_id" not in params, f"{name} must not expose user_id"


def test_identity_tools_do_not_accept_db_beyond_first_param():
    """``db`` is the server-injected first param; never a business param.

    A model / Agent cannot choose the session: it is positional / leading and
    filled by the REST layer / orchestrator.
    """
    for name in (
        "guide_posture_self_test",
        "analyze_posture_photo",
        "get_posture_profile",
        "suggest_posture_priorities",
        "confirm_posture_goals",
        "report_safety_signal",
    ):
        fn = getattr(tools, name)
        params = list(inspect.signature(fn).parameters)
        assert params[0] == "db", f"{name} first param must be db (server-injected)"


def test_tool_return_annotations_are_typed_models():
    assert get_type_hints(tools.get_posture_issue)["return"] is not dict
    assert (
        get_type_hints(tools.analyze_posture_photo)["return"]
        is PhotoAssessmentResult
    )
    assert (
        get_type_hints(tools.suggest_posture_priorities)["return"]
        is PrioritySuggestionsResponse
    )
    assert (
        get_type_hints(tools.report_safety_signal)["return"]
        is SafetySignalResponse
    )


async def test_tool_input_validation_rejects_untyped_signal_fields():
    async with TestSession() as db:
        with pytest.raises(ValidationError):
            await tools.report_safety_signal(
                db,
                _actor(str(_uuid.uuid4())),
                {"signal_type": "not-valid"},
                "key",
            )


async def test_side_effect_tool_contracts_reject_blank_keys_and_photo_keys():
    user_id = str(_uuid.uuid4())
    signal = {
        "signal_type": "pain",
        "body_region": "head_neck",
        "related_issue_id": "HN-01",
        "severity_hint": "mild",
        "reported_at": None,
    }
    async with TestSession() as db:
        with pytest.raises(ValidationError):
            await tools.report_safety_signal(
                db, _actor(user_id), signal, "   "
            )
        with pytest.raises(ValidationError):
            await tools.analyze_posture_photo(
                db, _actor(user_id), "HN-01", ["   "], "photo-key"
            )


# ===========================================================================
# Tool: list_posture_issues / get_posture_issue (public)
# ===========================================================================


def test_list_posture_issues_returns_issue_summary_shape():
    issues = tools.list_posture_issues()
    assert len(issues) > 0
    for i in issues:
        assert set(i.model_dump()) == {
            "id", "name_cn", "category", "aliases", "definition"
        }


def test_list_posture_issues_category_filter():
    head_neck = tools.list_posture_issues("head_neck")
    assert all(i.category == "head_neck" for i in head_neck)


def test_list_posture_issues_invalid_category_raises_not_found():
    with pytest.raises(NotFound):
        tools.list_posture_issues("not-a-category")


def test_get_posture_issue_returns_detail():
    issue = tools.get_posture_issue("HN-01")
    assert issue.id == "HN-01"
    assert issue.self_tests


def test_get_posture_issue_unknown_raises_not_found():
    from app.core.exceptions import NotFound

    with pytest.raises(NotFound):
        tools.get_posture_issue("DOES-NOT-EXIST")


# ===========================================================================
# Tool: guide_posture_self_test
# ===========================================================================


async def test_guide_self_test_no_existing_result(client):
    token = await _login_user(client)
    user_id = _uid(token)
    async with TestSession() as db:
        guide = await tools.guide_posture_self_test(db, _actor(user_id), "HN-01")
    assert guide.issue_id == "HN-01"
    assert guide.has_existing_result is False
    assert len(guide.self_tests) >= 1
    # extended safety content is surfaced verbatim
    step = guide.self_tests[0]
    assert hasattr(step, "steps")
    assert hasattr(step, "stop_conditions")


async def test_guide_self_test_with_existing_result(client):
    token = await _login_user(client)
    user_id = _uid(token)
    await _seed_entry(user_id, "HN-01")
    async with TestSession() as db:
        guide = await tools.guide_posture_self_test(db, _actor(user_id), "HN-01")
    assert guide.has_existing_result is True


async def test_guide_self_test_unknown_issue(client):
    token = await _login_user(client)
    user_id = _uid(token)
    from app.core.exceptions import NotFound

    async with TestSession() as db:
        with pytest.raises(NotFound):
            await tools.guide_posture_self_test(db, _actor(user_id), "NOPE")


# ===========================================================================
# Tool: get_posture_profile + cross-user isolation
# ===========================================================================


async def test_get_posture_profile_empty_for_new_user(client):
    token = await _login_user(client)
    user_id = _uid(token)
    async with TestSession() as db:
        profile = await tools.get_posture_profile(db, _actor(user_id))
    assert profile.summary.total_evaluated == 0
    # unevaluated categories cover the whole catalog
    assert len(profile.unevaluated_categories) > 0


async def test_get_posture_profile_single_unknown_issue(client):
    token = await _login_user(client)
    user_id = _uid(token)
    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await tools.get_posture_profile(db, _actor(user_id), "NOPE")
    assert exc.value.status_code == 404
    assert exc.value.code == "issue_not_found"


async def test_get_posture_profile_single_no_entry(client):
    token = await _login_user(client)
    user_id = _uid(token)
    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await tools.get_posture_profile(db, _actor(user_id), "HN-01")
    assert exc.value.status_code == 404
    assert exc.value.code == "profile_entry_not_found"


async def test_get_posture_profile_cross_user_isolation(client):
    """A user can never read another user's single-issue entry (spec §9.2)."""
    token_a = await _login_user(client, phone="13800138001")
    token_b = await _login_user(client, phone="13800138002")
    user_a = _uid(token_a)
    user_b = _uid(token_b)
    await _seed_entry(user_a, "HN-01", severity="moderate")
    # user_b asks for HN-01: known issue, but no entry for b -> 404
    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await tools.get_posture_profile(db, _actor(user_b), "HN-01")
    assert exc.value.code == "profile_entry_not_found"


# ===========================================================================
# Tool: suggest_posture_priorities (safety gate)
# ===========================================================================


async def test_suggest_priorities_empty_for_new_user(client):
    token = await _login_user(client)
    user_id = _uid(token)
    async with TestSession() as db:
        suggestions = await tools.suggest_posture_priorities(db, _actor(user_id))
    # three empty buckets, never InsufficientData
    assert suggestions.normal_candidates == []
    assert suggestions.retest_required == []
    assert suggestions.safety_blocked == []
    # server control values present
    for key in ("suggestion_id", "profile_version", "rule_version", "risk_version"):
        assert getattr(suggestions, key)
    assert suggestions.rule_version == priority.PRIORITY_RULE_VERSION
    assert suggestions.risk_version == RISK_VERSION


async def test_suggest_priorities_recomputes_each_call(client):
    """Safety gate: a newly seeded candidate changes the suggestion_id."""
    token = await _login_user(client)
    user_id = _uid(token)
    async with TestSession() as db:
        before = await tools.suggest_posture_priorities(db, _actor(user_id))
    await _seed_entry(user_id, "HN-01", severity="moderate")
    async with TestSession() as db:
        after = await tools.suggest_posture_priorities(db, _actor(user_id))
    assert before.suggestion_id != after.suggestion_id
    assert any(c.issue_id == "HN-01" for c in after.normal_candidates)


# ===========================================================================
# Tool: confirm_posture_goals (restricted/red_flag blocking + idempotency)
# ===========================================================================


async def _suggest_then_confirm(user_id, issue_id, idempotency_key):
    async with TestSession() as db:
        suggestions = await tools.suggest_posture_priorities(db, _actor(user_id))
    goals = [GoalInput(issue_id=issue_id, priority_rank=1)]
    async with TestSession() as db:
        confirmed = await tools.confirm_posture_goals(
            db,
            _actor(user_id),
            suggestions.suggestion_id,
            suggestions.profile_version,
            goals,
            idempotency_key,
        )
    return suggestions, confirmed


async def test_confirm_goals_happy_path(client):
    token = await _login_user(client)
    user_id = _uid(token)
    await _seed_entry(user_id, "HN-01", severity="moderate")
    _, confirmed = await _suggest_then_confirm(user_id, "HN-01", "k1")
    assert confirmed.can_generate_plan is True
    assert len(confirmed.confirmed_goals) == 1
    assert confirmed.confirmed_goals[0].issue_id == "HN-01"
    assert confirmed.risk_version == RISK_VERSION


async def test_confirm_goals_restricted_blocked(client):
    """Escalate HN-01 to restricted via a real acute_trauma safety signal
    (product-policy gate) reported through the Tool, then confirm it -> 409
    restricted_blocked. The issue routes to safety_blocked, never retest."""
    token = await _login_user(client)
    user_id = _uid(token)
    await _seed_entry(user_id, "HN-01", severity="moderate")

    acute_signal = {
        "signal_type": "acute_trauma",
        "body_region": None,
        "related_issue_id": "HN-01",
        "severity_hint": None,
        "reported_at": None,
    }
    async with TestSession() as db:
        await tools.report_safety_signal(db, _actor(user_id), acute_signal, "k-at")

    async with TestSession() as db:
        suggestions = await tools.suggest_posture_priorities(db, _actor(user_id))
    sb = {s.issue_id: s for s in suggestions.safety_blocked}
    assert "HN-01" in sb
    assert sb["HN-01"].risk_tier == "restricted"
    # restricted wording must not pose as a clinical red flag
    assert "红旗" not in sb["HN-01"].reason

    goals = [GoalInput(issue_id="HN-01", priority_rank=1)]
    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await tools.confirm_posture_goals(
                db,
                _actor(user_id),
                suggestions.suggestion_id,
                suggestions.profile_version,
                goals,
                "k-restricted",
            )
    assert exc.value.status_code == 409
    assert exc.value.code == "restricted_blocked"


async def test_confirm_goals_red_flag_blocked(client, monkeypatch):
    """Phase 1 ships no red_flag rule; exercise the branch with a synthetic
    classification (mirrors test_posture_priority). Verifies the Tool surfaces
    409 red_flag_blocked."""
    token = await _login_user(client)
    user_id = _uid(token)
    await _seed_entry(user_id, "HN-01", severity="moderate")

    from app.posture import safety as safety_mod
    from app.posture.risk_rules import RiskClassification

    async def fake_classify(db, user_id, issue_id=None):
        return RiskClassification(
            risk_tier="red_flag",
            risk_version=RISK_VERSION,
            rule_id="synthetic-red-flag",
            reason="synthetic",
            sources=[],
        )

    monkeypatch.setattr(safety_mod, "compute_profile_risk", fake_classify)

    async with TestSession() as db:
        suggestions = await tools.suggest_posture_priorities(db, _actor(user_id))
    sb = {s.issue_id: s for s in suggestions.safety_blocked}
    assert "HN-01" in sb
    assert sb["HN-01"].risk_tier == "red_flag"

    goals = [GoalInput(issue_id="HN-01", priority_rank=1)]
    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await tools.confirm_posture_goals(
                db,
                _actor(user_id),
                suggestions.suggestion_id,
                suggestions.profile_version,
                goals,
                "k-redflag",
            )
    assert exc.value.status_code == 409
    assert exc.value.code == "red_flag_blocked"


async def test_confirm_goals_non_candidate_invalid(client):
    """Confirming a normal / unevaluated issue surfaces 400 invalid_goal."""
    token = await _login_user(client)
    user_id = _uid(token)
    # Seed a normal-severity confirmed entry -> excluded (not a candidate).
    await _seed_entry(user_id, "HN-01", severity="normal")
    async with TestSession() as db:
        suggestions = await tools.suggest_posture_priorities(db, _actor(user_id))
    goals = [GoalInput(issue_id="HN-01", priority_rank=1)]
    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await tools.confirm_posture_goals(
                db,
                _actor(user_id),
                suggestions.suggestion_id,
                suggestions.profile_version,
                goals,
                "k-invalid",
            )
    assert exc.value.status_code == 400
    assert exc.value.code == "invalid_goal"


async def test_confirm_goals_stale_suggestion(client):
    token = await _login_user(client)
    user_id = _uid(token)
    await _seed_entry(user_id, "HN-01", severity="moderate")
    async with TestSession() as db:
        suggestions = await tools.suggest_posture_priorities(db, _actor(user_id))
    # Change the profile so the suggestion goes stale.
    await _seed_entry(user_id, "ST-04", severity="severe")
    goals = [GoalInput(issue_id="HN-01", priority_rank=1)]
    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await tools.confirm_posture_goals(
                db,
                _actor(user_id),
                suggestions.suggestion_id,
                suggestions.profile_version,
                goals,
                "k-stale",
            )
    assert exc.value.status_code == 409
    assert exc.value.code == "stale_priority"


async def test_confirm_goals_idempotent_replay(client):
    """Same key + same request replays the first batch; no duplicate writes."""
    token = await _login_user(client)
    user_id = _uid(token)
    await _seed_entry(user_id, "HN-01", severity="moderate")
    _, confirmed1 = await _suggest_then_confirm(user_id, "HN-01", "k-idem")

    # Replay with the same control values + same key.
    async with TestSession() as db:
        suggestions = await tools.suggest_posture_priorities(db, _actor(user_id))
    goals = [GoalInput(issue_id="HN-01", priority_rank=1)]
    async with TestSession() as db:
        confirmed2 = await tools.confirm_posture_goals(
            db,
            _actor(user_id),
            suggestions.suggestion_id,
            suggestions.profile_version,
            goals,
            "k-idem",
        )
    # Same first-batch confirmed_at, no new rows.
    assert (
        confirmed1.confirmed_goals[0].confirmed_at
        == confirmed2.confirmed_goals[0].confirmed_at
    )
    async with TestSession() as db:
        rows = (
            await db.execute(
                select(PostureUserGoal).where(
                    PostureUserGoal.user_id == _uuid.UUID(user_id)
                )
            )
        ).scalars().all()
    assert len(rows) == 1  # original batch only


async def test_confirm_goals_idempotency_key_conflict(client):
    """Same key + DIFFERENT request hash -> 400 idempotency_key_conflict."""
    token = await _login_user(client)
    user_id = _uid(token)
    await _seed_entry(user_id, "HN-01", severity="moderate")
    await _seed_entry(user_id, "ST-04", severity="severe")
    _, _ = await _suggest_then_confirm(user_id, "HN-01", "k-conflict")

    async with TestSession() as db:
        suggestions = await tools.suggest_posture_priorities(db, _actor(user_id))
    # Same key but a DIFFERENT goal set -> different request hash.
    goals = [GoalInput(issue_id="ST-04", priority_rank=1)]
    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await tools.confirm_posture_goals(
                db,
                _actor(user_id),
                suggestions.suggestion_id,
                suggestions.profile_version,
                goals,
                "k-conflict",
            )
    assert exc.value.status_code == 400
    assert exc.value.code == "idempotency_key_conflict"


async def test_confirm_goals_purged_anchor_returns_410(client):
    token = await _login_user(client)
    user_id = _uid(token)
    await _seed_entry(user_id, "HN-01", severity="moderate")
    _, _ = await _suggest_then_confirm(user_id, "HN-01", "k-purge")

    # Simulate purge: delete the goal rows the anchor points at.
    async with TestSession() as db:
        rows = (
            await db.execute(
                select(PostureUserGoal).where(
                    PostureUserGoal.user_id == _uuid.UUID(user_id)
                )
            )
        ).scalars().all()
        for r in rows:
            await db.delete(r)
        await db.commit()

    async with TestSession() as db:
        suggestions = await tools.suggest_posture_priorities(db, _actor(user_id))
    goals = [GoalInput(issue_id="HN-01", priority_rank=1)]
    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await tools.confirm_posture_goals(
                db,
                _actor(user_id),
                suggestions.suggestion_id,
                suggestions.profile_version,
                goals,
                "k-purge",
            )
    assert exc.value.status_code == 410
    assert exc.value.code == "idempotency_result_gone"


# ===========================================================================
# Tool: report_safety_signal (thin wrapper over safety.record_safety_signal)
# ===========================================================================


async def test_report_safety_signal_records_via_tool(client):
    token = await _login_user(client)
    user_id = _uid(token)
    signal = {
        "signal_type": "pain",
        "body_region": "head_neck",
        "related_issue_id": "HN-01",
        "severity_hint": "mild",
        "reported_at": None,
    }
    async with TestSession() as db:
        result = await tools.report_safety_signal(db, _actor(user_id), signal, "k-sig-1")
    assert result.status == "recorded"
    assert result.lifecycle == "active"


async def test_report_safety_signal_idempotent_replay(client):
    token = await _login_user(client)
    user_id = _uid(token)
    signal = {
        "signal_type": "pain",
        "body_region": "head_neck",
        "related_issue_id": "HN-01",
        "severity_hint": "mild",
        "reported_at": None,
    }
    async with TestSession() as db:
        await tools.report_safety_signal(db, _actor(user_id), signal, "k-sig-2")
    async with TestSession() as db:
        result = await tools.report_safety_signal(db, _actor(user_id), signal, "k-sig-2")
    assert result.status == "deduplicated"


async def test_report_safety_signal_cross_user_isolation(client):
    """record_safety_signal is scoped by actor.user_id; signals are per-user."""
    token_a = await _login_user(client, phone="13800139001")
    token_b = await _login_user(client, phone="13800139002")
    user_a = _uid(token_a)
    user_b = _uid(token_b)
    signal = {
        "signal_type": "pain",
        "body_region": "head_neck",
        "related_issue_id": "HN-01",
        "severity_hint": "mild",
        "reported_at": None,
    }
    async with TestSession() as db:
        await tools.report_safety_signal(db, _actor(user_a), signal, "k-cross")
    # user_b reuses the same key -- different user, so it is NOT a conflict.
    async with TestSession() as db:
        result = await tools.report_safety_signal(
            db, _actor(user_b), signal, "k-cross"
        )
    assert result.status == "recorded"


# ===========================================================================
# PhotoOwnershipVerifier (fail-closed default + fake branches)
# ===========================================================================


class _FakeOwnedVerifier:
    async def verify(self, user_id, photo_keys):
        return None  # all keys "owned"


class _FakeDeniedVerifier:
    async def verify(self, user_id, photo_keys):
        raise ownership.PhotoOwnershipDenied()


class _FakeUnavailableVerifier:
    async def verify(self, user_id, photo_keys):
        raise ownership.PhotoOwnershipUnavailable()


async def test_default_verifier_fail_closed_unavailable():
    """Phase 1: no provider-backed verifier -> always unavailable."""
    with pytest.raises(ownership.PhotoOwnershipUnavailable):
        await ownership.get_photo_ownership_verifier().verify(
            "u1", ["posture_photos/u1/abc/img.jpg"]
        )


async def test_default_verifier_rejects_forged_prefix():
    """A path prefix that matches the caller's user_id is NOT ownership proof."""
    with pytest.raises(ownership.PhotoOwnershipUnavailable):
        await ownership.get_photo_ownership_verifier().verify(
            "u1", ["posture_photos/u1/forged/img.jpg"]
        )


async def test_fake_owned_verifier_passes():
    with ownership.using_photo_ownership_verifier(_FakeOwnedVerifier()):
        await ownership.get_photo_ownership_verifier().verify("u1", ["k1"])


async def test_fake_denied_verifier_raises_denied():
    with ownership.using_photo_ownership_verifier(_FakeDeniedVerifier()):
        with pytest.raises(ownership.PhotoOwnershipDenied):
            await ownership.get_photo_ownership_verifier().verify("u1", ["k1"])


async def test_fake_unavailable_verifier_raises_unavailable():
    with ownership.using_photo_ownership_verifier(_FakeUnavailableVerifier()):
        with pytest.raises(ownership.PhotoOwnershipUnavailable):
            await ownership.get_photo_ownership_verifier().verify("u1", ["k1"])


def test_verifier_swap_restores_previous():
    original = ownership.get_photo_ownership_verifier()
    fake = _FakeOwnedVerifier()
    with ownership.using_photo_ownership_verifier(fake):
        assert ownership.get_photo_ownership_verifier() is fake
    assert ownership.get_photo_ownership_verifier() is original


def test_ownership_exception_codes():
    assert ownership.PhotoOwnershipDenied().code == "photo_ownership_denied"
    assert ownership.PhotoOwnershipDenied().status_code == 400
    assert ownership.PhotoOwnershipUnavailable().code == "photo_ownership_unavailable"
    assert ownership.PhotoOwnershipUnavailable().status_code == 503


# ===========================================================================
# Photo Tool: gate ordering (closed gate -> zero downstream)
# ===========================================================================


async def test_photo_tool_closed_gate_zero_downstream(client, monkeypatch):
    """Closed privacy gate -> PhotoAnalysisDisabled with NO ownership / model /
    event / idempotency calls (plan Task 7 ordering)."""
    token = await _login_user(client)
    user_id = _uid(token)

    ownership_calls = {"n": 0}
    model_calls = {"n": 0}
    service_calls = {"n": 0}

    class _SpyVerifier:
        async def verify(self, user_id, photo_keys):
            ownership_calls["n"] += 1
            return None

    async def _spy_model(*a, **kw):
        model_calls["n"] += 1
        return _ai_result("moderate")

    async def _spy_service(*a, **kw):
        service_calls["n"] += 1

    # Install spies. The gate stays REAL (default closed), so the Tool must
    # short-circuit before any spy fires.
    monkeypatch.setattr(ownership, "_active_verifier", _SpyVerifier(), raising=False)
    monkeypatch.setattr(
        "app.posture.ai_service.analyze_posture_photo", _spy_model
    )
    monkeypatch.setattr(service, "analyze_and_save_photo", _spy_service)

    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await tools.analyze_posture_photo(
                db, _actor(user_id), "HN-01", ["k1"], "key-1"
            )
    assert exc.value.status_code == 503
    assert exc.value.code == "photo_analysis_disabled"
    assert ownership_calls["n"] == 0
    assert model_calls["n"] == 0
    assert service_calls["n"] == 0


async def test_photo_tool_fake_owned_does_not_enable_production_gate(
    client, monkeypatch
):
    """A fake-owned verifier ALONE cannot enable the photo path: the gate still
    hard-rejects (plan Task 7: 'test fake 不能启用生产门')."""
    token = await _login_user(client)
    user_id = _uid(token)

    model_calls = {"n": 0}

    async def _spy_model(*a, **kw):
        model_calls["n"] += 1
        return _ai_result("moderate")

    monkeypatch.setattr(
        "app.posture.ai_service.analyze_posture_photo", _spy_model
    )

    # Install a fake-OWNED verifier -- the gate is still real (closed).
    with ownership.using_photo_ownership_verifier(_FakeOwnedVerifier()):
        async with TestSession() as db:
            with pytest.raises(AppException) as exc:
                await tools.analyze_posture_photo(
                    db, _actor(user_id), "HN-01", ["k1"], "key-1"
                )
    assert exc.value.code == "photo_analysis_disabled"
    assert model_calls["n"] == 0


async def test_photo_tool_total_switch_blocks_even_when_evidence_gate_is_true(
    client, monkeypatch
):
    token = await _login_user(client)
    user_id = _uid(token)
    ownership_calls = {"n": 0}

    class _SpyVerifier:
        async def verify(self, user_id, photo_keys):
            ownership_calls["n"] += 1

    monkeypatch.setattr(settings, "PHOTO_ANALYSIS_ENABLED", False)
    monkeypatch.setattr(
        tools,
        "evaluate_photo_privacy_gate",
        lambda: SimpleNamespace(satisfied=True),
    )
    with ownership.using_photo_ownership_verifier(_SpyVerifier()):
        async with TestSession() as db:
            with pytest.raises(AppException) as exc:
                await tools.analyze_posture_photo(
                    db,
                    _consented_actor(user_id),
                    "HN-01",
                    ["k1"],
                    "key-switch",
                )
    assert exc.value.code == "photo_analysis_disabled"
    assert ownership_calls["n"] == 0


async def test_photo_tool_requires_server_consent_before_ownership(
    client, monkeypatch
):
    token = await _login_user(client)
    user_id = _uid(token)
    ownership_calls = {"n": 0}

    class _SpyVerifier:
        async def verify(self, user_id, photo_keys):
            ownership_calls["n"] += 1

    monkeypatch.setattr(settings, "PHOTO_ANALYSIS_ENABLED", True)
    monkeypatch.setattr(
        tools,
        "evaluate_photo_privacy_gate",
        lambda: SimpleNamespace(satisfied=True),
    )
    with ownership.using_photo_ownership_verifier(_SpyVerifier()):
        async with TestSession() as db:
            with pytest.raises(AppException) as exc:
                await tools.analyze_posture_photo(
                    db, _actor(user_id), "HN-01", ["k1"], "key-consent"
                )
    assert exc.value.status_code == 403
    assert exc.value.code == "consent_required"
    assert ownership_calls["n"] == 0


async def test_photo_tool_returns_typed_analysis_result_after_all_gates(
    client, monkeypatch
):
    token = await _login_user(client)
    user_id = _uid(token)

    async def _mock_model(issue_id, photo_keys, uid, db):
        return _ai_result("mild", confidence=0.71, evidence=["synthetic"])

    monkeypatch.setattr(settings, "PHOTO_ANALYSIS_ENABLED", True)
    monkeypatch.setattr(
        tools,
        "evaluate_photo_privacy_gate",
        lambda: SimpleNamespace(satisfied=True),
    )
    monkeypatch.setattr(
        "app.posture.ai_service.analyze_posture_photo", _mock_model
    )

    with ownership.using_photo_ownership_verifier(_FakeOwnedVerifier()):
        async with TestSession() as db:
            result = await tools.analyze_posture_photo(
                db,
                _consented_actor(user_id),
                "HN-01",
                ["k1"],
                "key-typed-photo",
            )
    assert isinstance(result, PhotoAssessmentResult)
    assert result.result == "moderate"  # legacy REST compatibility mapping
    assert result.severity.value == "mild"
    assert result.confidence == 0.71
    assert result.evidence == ["synthetic"]


# ===========================================================================
# Photo idempotency at the service orchestration layer
# ===========================================================================


async def test_photo_idempotency_replay_skips_model(client, monkeypatch):
    """Same key + same request -> replay; the model is called exactly once."""
    token = await _login_user(client)
    user_id = _uid(token)

    model_calls = {"n": 0}

    async def _mock_model(issue_id, photo_keys, uid, db):
        model_calls["n"] += 1
        return _ai_result("moderate")

    monkeypatch.setattr("app.posture.ai_service.analyze_posture_photo", _mock_model)

    async with TestSession() as db:
        r1 = await service.analyze_and_save_photo(
            db, user_id, "HN-01", ["k1", "k2"], "idem-1"
        )
    async with TestSession() as db:
        r2 = await service.analyze_and_save_photo(
            db, user_id, "HN-01", ["k1", "k2"], "idem-1"
        )
    assert model_calls["n"] == 1
    assert r1["id"] == r2["id"]
    assert r1["result"] == r2["result"]


async def test_photo_idempotency_preserves_image_order_in_request_hash(
    client, monkeypatch
):
    token = await _login_user(client)
    user_id = _uid(token)

    async def _mock_model(issue_id, photo_keys, uid, db):
        return _ai_result("moderate")

    monkeypatch.setattr(
        "app.posture.ai_service.analyze_posture_photo", _mock_model
    )
    async with TestSession() as db:
        await service.analyze_and_save_photo(
            db, user_id, "HN-01", ["front", "side"], "idem-order"
        )
    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await service.analyze_and_save_photo(
                db, user_id, "HN-01", ["side", "front"], "idem-order"
            )
    assert exc.value.code == "idempotency_key_conflict"


async def test_photo_idempotency_key_conflict(client, monkeypatch):
    token = await _login_user(client)
    user_id = _uid(token)

    async def _mock_model(issue_id, photo_keys, uid, db):
        return _ai_result("moderate")

    monkeypatch.setattr("app.posture.ai_service.analyze_posture_photo", _mock_model)

    async with TestSession() as db:
        await service.analyze_and_save_photo(db, user_id, "HN-01", ["k1"], "idem-c")
    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await service.analyze_and_save_photo(
                db, user_id, "HN-01", ["k9"], "idem-c"  # different keys
            )
    assert exc.value.status_code == 400
    assert exc.value.code == "idempotency_key_conflict"


async def test_photo_service_rejects_invalid_idempotency_key_before_model(
    client, monkeypatch
):
    token = await _login_user(client)
    user_id = _uid(token)
    model_calls = {"n": 0}

    async def _mock_model(issue_id, photo_keys, uid, db):
        model_calls["n"] += 1
        return _ai_result("moderate")

    monkeypatch.setattr(
        "app.posture.ai_service.analyze_posture_photo", _mock_model
    )
    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await service.analyze_and_save_photo(
                db, user_id, "HN-01", ["k1"], " "
            )
    assert exc.value.code == "invalid_idempotency_key"
    assert model_calls["n"] == 0


async def test_photo_idempotency_dangling_result_ref_returns_410(
    client, monkeypatch
):
    token = await _login_user(client)
    user_id = _uid(token)

    async def _mock_model(issue_id, photo_keys, uid, db):
        return _ai_result("moderate")

    monkeypatch.setattr("app.posture.ai_service.analyze_posture_photo", _mock_model)

    async with TestSession() as db:
        r1 = await service.analyze_and_save_photo(
            db, user_id, "HN-01", ["k1"], "idem-p"
        )

    # Simulate a dangling record (for example interrupted/manual cleanup).
    # A completed full purge deletes linked idempotency metadata too.
    async with TestSession() as db:
        event = await db.get(PostureAssessmentEvent, _uuid.UUID(r1["id"]))
        assert event is not None
        await db.delete(event)
        await db.commit()

    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await service.analyze_and_save_photo(
                db, user_id, "HN-01", ["k1"], "idem-p"
            )
    assert exc.value.status_code == 410
    assert exc.value.code == "idempotency_result_gone"


async def test_photo_idempotency_expired_record_reusable(client, monkeypatch):
    token = await _login_user(client)
    user_id = _uid(token)

    model_calls = {"n": 0}

    async def _mock_model(issue_id, photo_keys, uid, db):
        model_calls["n"] += 1
        return _ai_result("moderate")

    monkeypatch.setattr("app.posture.ai_service.analyze_posture_photo", _mock_model)

    # First call with an already-expired record (back-dated).
    async with TestSession() as db:
        await service.analyze_and_save_photo(
            db, user_id, "HN-01", ["k1"], "idem-e",
            now=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
    # The record expired at 2020-01-01 + 24h. A later call reuses the key.
    async with TestSession() as db:
        await service.analyze_and_save_photo(
            db, user_id, "HN-01", ["k1"], "idem-e",
            now=datetime(2020, 6, 1, tzinfo=timezone.utc),
        )
    assert model_calls["n"] == 2  # model ran both times (expired record reused)


async def test_photo_idempotency_record_stores_only_result_ref(
    client, monkeypatch
):
    """idempotency_records minimises data: only result_ref (event id), no full
    health response (spec §8.5)."""
    token = await _login_user(client)
    user_id = _uid(token)

    async def _mock_model(issue_id, photo_keys, uid, db):
        return _ai_result("moderate")

    monkeypatch.setattr("app.posture.ai_service.analyze_posture_photo", _mock_model)

    async with TestSession() as db:
        await service.analyze_and_save_photo(
            db, user_id, "HN-01", ["k1"], "idem-min"
        )
    async with TestSession() as db:
        rec = (
            await db.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.operation == "analyze_photo",
                    IdempotencyRecord.user_id == _uuid.UUID(user_id),
                )
            )
        ).scalar_one()
    assert rec.result_ref  # the event id
    assert rec.status == "completed"
    # No column on IdempotencyRecord stores the full health response (the model
    # only has request_hash + result_ref). Sanity-check the schema: there is no
    # ``response`` / ``payload`` / ``body`` attribute.
    for forbidden in ("response", "payload", "body", "ai_response"):
        assert not hasattr(rec, forbidden)


async def test_photo_idempotency_writes_event_profile_and_record_atomically(
    client, monkeypatch
):
    """One consistent transaction: event + profile projection + idempotency
    record all land together (plan Task 7)."""
    token = await _login_user(client)
    user_id = _uid(token)

    async def _mock_model(issue_id, photo_keys, uid, db):
        return _ai_result("moderate")

    monkeypatch.setattr("app.posture.ai_service.analyze_posture_photo", _mock_model)

    async with TestSession() as db:
        await service.analyze_and_save_photo(
            db, user_id, "HN-01", ["k1"], "idem-atomic"
        )

    async with TestSession() as db:
        event = (
            await db.execute(
                select(PostureAssessmentEvent).where(
                    PostureAssessmentEvent.user_id == _uuid.UUID(user_id),
                    PostureAssessmentEvent.issue_id == "HN-01",
                )
            )
        ).scalar_one()
        entry = (
            await db.execute(
                select(PostureProfileEntry).where(
                    PostureProfileEntry.user_id == _uuid.UUID(user_id),
                    PostureProfileEntry.issue_id == "HN-01",
                )
            )
        ).scalar_one()
        rec = (
            await db.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.operation == "analyze_photo"
                )
            )
        ).scalar_one()
    # All three present, and the idempotency record points at the event.
    assert event.source == "ai_photo"
    assert entry.certainty == "confirmed"
    assert rec.result_ref == str(event.id)


# ===========================================================================
# Unified idempotency: photo / confirm_goals / safety share the same table
# ===========================================================================


async def test_unified_idempotency_table_covers_three_operations(
    client, monkeypatch
):
    token = await _login_user(client)
    user_id = _uid(token)

    async def _mock_model(issue_id, photo_keys, uid, db):
        return _ai_result("moderate")

    monkeypatch.setattr("app.posture.ai_service.analyze_posture_photo", _mock_model)

    async with TestSession() as db:
        await service.analyze_and_save_photo(
            db, user_id, "HN-01", ["k1"], "shared-key"
        )
    await _seed_entry(user_id, "ST-04", severity="severe")
    async with TestSession() as db:
        suggestions = await tools.suggest_posture_priorities(db, _actor(user_id))
    goals = [GoalInput(issue_id="ST-04", priority_rank=1)]
    async with TestSession() as db:
        await tools.confirm_posture_goals(
            db,
            _actor(user_id),
            suggestions.suggestion_id,
            suggestions.profile_version,
            goals,
            "shared-key",  # SAME key, different operation -> NOT a conflict
        )
    signal = {
        "signal_type": "pain",
        "body_region": "head_neck",
        "related_issue_id": "HN-01",
        "severity_hint": "mild",
        "reported_at": None,
    }
    async with TestSession() as db:
        await tools.report_safety_signal(db, _actor(user_id), signal, "shared-key")

    async with TestSession() as db:
        ops = sorted(
            r.operation
            for r in (
                await db.execute(
                    select(IdempotencyRecord).where(
                        IdempotencyRecord.idempotency_key == "shared-key"
                    )
                )
            ).scalars().all()
        )
    assert ops == ["analyze_photo", "confirm_goals", "report_safety_signal"]


# ===========================================================================
# REST rewiring compatibility
# ===========================================================================


async def test_rest_list_issues_still_works(client):
    resp = await client.get("/api/v1/posture/issues")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert {"id", "name_cn", "category", "aliases", "definition"} <= set(
        resp.json()[0]
    )


async def test_rest_get_issue_still_works(client):
    resp = await client.get("/api/v1/posture/issues/HN-01")
    assert resp.status_code == 200
    assert resp.json()["id"] == "HN-01"


async def test_rest_get_issue_unknown_404(client):
    resp = await client.get("/api/v1/posture/issues/NOPE")
    assert resp.status_code == 404


async def test_rest_invalid_issue_category_404(client):
    resp = await client.get(
        "/api/v1/posture/issues", params={"category": "not-a-category"}
    )
    assert resp.status_code == 404


async def test_rest_unauthenticated_profile_401(client):
    resp = await client.get("/api/v1/posture/profile")
    assert resp.status_code == 401


async def test_rest_profile_via_tool(client):
    token = await _login_user(client)
    resp = await client.get(
        "/api/v1/posture/profile", headers=_headers(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["total_evaluated"] == 0


async def test_rest_priorities_via_tool(client):
    token = await _login_user(client)
    resp = await client.get(
        "/api/v1/posture/priorities", headers=_headers(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "suggestion_id" in body
    assert "safety_blocked" in body
    assert "red_flag_blocked" not in body  # renamed contract


def test_photo_request_requires_valid_client_idempotency_key():
    with pytest.raises(ValidationError):
        PhotoAssessRequest.model_validate(
            {"issue_id": "HN-01", "photo_keys": ["k1"]}
        )
    with pytest.raises(ValidationError):
        PhotoAssessRequest.model_validate(
            {
                "issue_id": "HN-01",
                "photo_keys": ["k1"],
                "idempotency_key": "   ",
            }
        )
    request = PhotoAssessRequest.model_validate(
        {
            "issue_id": "HN-01",
            "photo_keys": ["k1"],
            "idempotency_key": "photo-request-1",
        }
    )
    assert request.idempotency_key == "photo-request-1"


async def test_photo_openapi_documents_required_idempotency_key(client):
    schema = (await client.get("/openapi.json")).json()
    request_schema = schema["paths"]["/api/v1/posture/assess/photo"]["post"][
        "requestBody"
    ]["content"]["application/json"]["schema"]
    assert "idempotency_key" in request_schema["properties"]
    assert "idempotency_key" in request_schema["required"]


async def test_rest_photo_gate_503_before_body(client):
    """Phase 1 gate: /assess/photo returns 503 before any body validation."""
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess/photo",
        json={"issue_id": "HN-01", "photo_keys": ["k1"]},
        headers=_headers(token),
    )
    assert resp.status_code == 503
    assert resp.json()["code"] == "photo_analysis_disabled"


async def test_rest_safety_signal_via_tool(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json={
            "signal_type": "pain",
            "body_region": "head_neck",
            "related_issue_id": "HN-01",
            "severity_hint": "mild",
            "idempotency_key": "rest-sig-1",
        },
        headers=_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "recorded"


async def test_rest_confirm_rejects_priority_context_snapshot(client):
    """extra='forbid' on ConfirmGoalsRequest rejects client context snapshots."""
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/goals/confirm",
        json={
            "suggestion_id": "x",
            "profile_version": "y",
            "goals": [{"issue_id": "HN-01", "priority_rank": 1}],
            "idempotency_key": "snap-1",
            "priority_context_snapshot": {"injected": True},
        },
        headers=_headers(token),
    )
    assert resp.status_code == 400  # surfaces as 400 (manual body parse)


async def test_rest_self_assess_and_history_unchanged(client):
    """Endpoints with no Tool equivalent keep their original behaviour."""
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers=_headers(token),
    )
    assert resp.status_code == 200
    resp = await client.get(
        "/api/v1/posture/history", headers=_headers(token)
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1
