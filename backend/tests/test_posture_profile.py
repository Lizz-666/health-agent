"""Phase 1 Task 2: dual-write assessment events + profile projection.

Covers (spec §6.3 / §6.4 / §8.5 / §16.2, plan Task 2):

* the pure ``project_profile`` projection helper for EVERY severity combination
  (single/multi source, null handling, conflict) -- must mirror migration 0002
  backfill CTE branch-for-branch;
* ``save_self_assessment`` / ``save_photo_assessment`` dual-write + projection
  upsert, transactional atomicity, same-source supersede;
* photo-gate-disabled / AI-failed / need-retake no-ops;
* history API shape compatibility.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select, event

from app.core.config import settings
from app.core.exceptions import ServiceUnavailable
from app.posture.models import (
    PostureAssessment,
    PostureAssessmentEvent,
    PostureProfileEntry,
)
from app.posture.service import project_profile
from tests.conftest import TestSession, test_engine


# SQLite's default busy_timeout is 0, which makes two concurrent writers fail
# instantly with "database is locked". The concurrency regression test below
# runs two saves against the same file DB via asyncio.gather; give every
# connection a generous busy_timeout so the second writer waits for the first
# transaction to COMMIT instead of erroring. Harmless for the other tests.
@event.listens_for(test_engine.sync_engine, "connect")
def _sqlite_busy_timeout(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


# ---------------------------------------------------------------------------
# Shared helpers (mirror tests/test_posture.py patterns)
# ---------------------------------------------------------------------------


@pytest.fixture
def photo_analysis_enabled(monkeypatch):
    monkeypatch.setattr(settings, "PHOTO_ANALYSIS_ENABLED", True)


@pytest.fixture()
def _force_photo_disabled(monkeypatch):
    monkeypatch.setattr(settings, "PHOTO_ANALYSIS_ENABLED", False)


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


def _ev(source, severity, eid, ts):
    """Build a latest-per-source event dict for the pure projection tests."""
    return {"source": source, "severity": severity, "id": eid, "created_at": ts}


_TS1 = datetime(2026, 7, 11, 10, 0, 0, tzinfo=timezone.utc)
_TS2 = datetime(2026, 7, 11, 11, 0, 0, tzinfo=timezone.utc)


def _ai_result(level, **overrides):
    base = {
        "level": level,
        "confidence": 0.8,
        "evidence": ["evidence"],
        "suggestion": "建议",
        "need_retake": False,
        "retake_reason": "",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# DB read helpers
# ---------------------------------------------------------------------------


async def _profile_for(issue_id: str):
    async with TestSession() as db:
        result = await db.execute(
            select(PostureProfileEntry).where(
                PostureProfileEntry.issue_id == issue_id
            )
        )
        return result.scalar_one_or_none()


async def _events_for(issue_id: str):
    async with TestSession() as db:
        result = await db.execute(
            select(PostureAssessmentEvent)
            .where(PostureAssessmentEvent.issue_id == issue_id)
            .order_by(PostureAssessmentEvent.created_at.asc())
        )
        return result.scalars().all()


async def _all_events():
    async with TestSession() as db:
        result = await db.execute(select(PostureAssessmentEvent))
        return result.scalars().all()


async def _all_profiles():
    async with TestSession() as db:
        result = await db.execute(select(PostureProfileEntry))
        return result.scalars().all()


# ===========================================================================
# Pure projection helper -- mirrors migration 0002 backfill CTE
# ===========================================================================


class TestProjectProfilePure:
    """Every projection combination; output must equal the 0002 backfill."""

    def test_single_source_non_null_is_confirmed(self):
        out = project_profile([_ev("self_test", "normal", "a", _TS1)])
        assert out["combined_severity"] == "normal"
        assert out["certainty"] == "confirmed"
        assert out["has_conflict"] is False

    def test_single_source_moderate_is_confirmed(self):
        out = project_profile([_ev("self_test", "moderate", "a", _TS1)])
        assert out["combined_severity"] == "moderate"
        assert out["certainty"] == "confirmed"

    def test_single_source_null_is_provisional_combined_null(self):
        out = project_profile([_ev("self_test", None, "a", _TS1)])
        assert out["combined_severity"] is None
        assert out["certainty"] == "provisional"
        assert out["has_conflict"] is False

    def test_multi_null_plus_moderate_is_provisional_null(self):
        out = project_profile(
            [_ev("self_test", None, "a", _TS1), _ev("ai_photo", "moderate", "b", _TS2)]
        )
        assert out["combined_severity"] is None
        assert out["certainty"] == "provisional"
        assert out["has_conflict"] is False

    def test_multi_moderate_plus_null_is_provisional_null(self):
        out = project_profile(
            [_ev("self_test", "moderate", "a", _TS1), _ev("ai_photo", None, "b", _TS2)]
        )
        assert out["combined_severity"] is None
        assert out["certainty"] == "provisional"
        assert out["has_conflict"] is False

    def test_multi_null_plus_null_is_provisional_null(self):
        out = project_profile(
            [_ev("self_test", None, "a", _TS1), _ev("ai_photo", None, "b", _TS2)]
        )
        assert out["combined_severity"] is None
        assert out["certainty"] == "provisional"
        assert out["has_conflict"] is False

    def test_multi_mild_plus_moderate_is_conflict_null(self):
        out = project_profile(
            [_ev("self_test", "mild", "a", _TS1), _ev("ai_photo", "moderate", "b", _TS2)]
        )
        assert out["combined_severity"] is None
        assert out["certainty"] == "conflict"
        assert out["has_conflict"] is True

    def test_multi_moderate_plus_severe_is_conflict_null(self):
        out = project_profile(
            [_ev("self_test", "moderate", "a", _TS1), _ev("ai_photo", "severe", "b", _TS2)]
        )
        assert out["combined_severity"] is None
        assert out["certainty"] == "conflict"
        assert out["has_conflict"] is True

    def test_multi_same_moderate_is_confirmed_moderate(self):
        out = project_profile(
            [_ev("self_test", "moderate", "a", _TS1), _ev("ai_photo", "moderate", "b", _TS2)]
        )
        assert out["combined_severity"] == "moderate"
        assert out["certainty"] == "confirmed"
        assert out["has_conflict"] is False

    def test_multi_same_normal_is_confirmed_normal(self):
        out = project_profile(
            [_ev("self_test", "normal", "a", _TS1), _ev("ai_photo", "normal", "b", _TS2)]
        )
        assert out["combined_severity"] == "normal"
        assert out["certainty"] == "confirmed"

    def test_latest_event_ids_point_at_each_source(self):
        out = project_profile(
            [_ev("self_test", "moderate", "self-id", _TS1), _ev("ai_photo", "moderate", "photo-id", _TS2)]
        )
        assert out["latest_self_test_event_id"] == "self-id"
        assert out["latest_photo_event_id"] == "photo-id"

    def test_sources_holds_only_latest_per_source_newest_first(self):
        out = project_profile(
            [_ev("self_test", "moderate", "a", _TS1), _ev("ai_photo", "severe", "b", _TS2)]
        )
        sources = out["sources"]
        assert len(sources) == 2
        # newest (ai_photo @ _TS2) first, mirrors ORDER BY created_at DESC
        assert sources[0]["source"] == "ai_photo"
        assert sources[1]["source"] == "self_test"
        for entry in sources:
            assert set(entry.keys()) == {"source", "event_id", "severity", "created_at"}
            assert isinstance(entry["created_at"], str)

    def test_empty_input_is_provisional_defensive(self):
        out = project_profile([])
        assert out["combined_severity"] is None
        assert out["certainty"] == "provisional"
        assert out["has_conflict"] is False
        assert out["sources"] == []
        assert out["latest_self_test_event_id"] is None
        assert out["latest_photo_event_id"] is None


# ===========================================================================
# save_self_assessment: dual-write + projection (DB integration)
# ===========================================================================


@pytest.mark.asyncio
async def test_self_assessment_positive_dual_writes_and_projects(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "moderate"

    events = await _events_for("HN-01")
    assert len(events) == 1
    ev = events[0]
    # dual-write: method + source together, result + severity together
    assert ev.method == "self_test"
    assert ev.source == "self_test"
    assert ev.result == "moderate"
    assert ev.severity == "moderate"
    assert ev.lifecycle == "active"

    profile = await _profile_for("HN-01")
    assert profile is not None
    assert profile.combined_severity == "moderate"
    assert profile.certainty == "confirmed"
    assert profile.has_conflict is False
    assert profile.risk_tier == "normal"
    assert profile.risk_version == "phase1-initial-v1"
    assert profile.latest_self_test_event_id == ev.id
    assert profile.latest_photo_event_id is None


@pytest.mark.asyncio
async def test_self_assessment_negative_projects_normal(client):
    token = await _login_user(client)
    await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "negative"},
        headers={"Authorization": f"Bearer {token}"},
    )
    profile = await _profile_for("HN-01")
    assert profile.combined_severity == "normal"
    assert profile.certainty == "confirmed"


@pytest.mark.asyncio
async def test_self_assessment_uncertain_keeps_result_sets_severity_null(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "uncertain"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "uncertain"

    events = await _events_for("HN-01")
    assert len(events) == 1
    ev = events[0]
    # legacy result kept for compat, severity explicitly None
    assert ev.result == "uncertain"
    assert ev.severity is None

    profile = await _profile_for("HN-01")
    assert profile.combined_severity is None
    assert profile.certainty == "provisional"
    assert profile.has_conflict is False


@pytest.mark.asyncio
async def test_same_source_reassess_supersedes_old_and_uses_latest(client):
    """Same-source older history never participates: older moderate is
    superseded by a newer normal -> confirmed/normal, NOT a conflict."""
    token = await _login_user(client)
    # first self-test: positive -> moderate
    await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # second self-test: negative -> normal (supersedes the prior self_test)
    await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "negative"},
        headers={"Authorization": f"Bearer {token}"},
    )

    events = await _events_for("HN-01")
    assert len(events) == 2
    older, newer = events  # ordered asc by created_at
    assert older.result == "moderate"
    assert older.lifecycle == "superseded"
    assert newer.result == "normal"
    assert newer.lifecycle == "active"

    profile = await _profile_for("HN-01")
    # only the latest (normal) participates -> confirmed/normal, not conflict
    assert profile.combined_severity == "normal"
    assert profile.certainty == "confirmed"
    assert profile.has_conflict is False
    assert profile.latest_self_test_event_id == newer.id


@pytest.mark.asyncio
async def test_reassess_upserts_profile_in_place_not_duplicate(client):
    token = await _login_user(client)
    for answer in ("positive", "positive", "negative"):
        await client.post(
            "/api/v1/posture/assess",
            json={"issue_id": "HN-01", "test_index": 0, "answer": answer},
            headers={"Authorization": f"Bearer {token}"},
        )
    profiles = await _all_profiles()
    assert len(profiles) == 1  # unique (user, issue) upserted, never duplicated


# ===========================================================================
# save_photo_assessment: dual-write + projection (DB integration)
# ===========================================================================


@pytest.mark.asyncio
async def test_photo_assessment_dual_writes_and_projects(client):
    """The HTTP photo-assess path is privacy-gated in Phase 1 (hard-rejected
    even with PHOTO_ANALYSIS_ENABLED=true), so dual-write + projection is
    verified at the service layer rather than through the gated endpoint."""
    from app.core.security import decode_token
    from app.posture import service

    token = await _login_user(client)
    user_id = decode_token(token)["sub"]
    async with TestSession() as db:
        result = await service.save_photo_assessment(
            db, user_id, "HN-01", ["fake.jpg"], _ai_result("moderate")
        )
        assert result["result"] == "moderate"

    events = await _events_for("HN-01")
    assert len(events) == 1
    ev = events[0]
    assert ev.method == "ai_photo"
    assert ev.source == "ai_photo"
    assert ev.result == "moderate"
    assert ev.severity == "moderate"
    assert ev.lifecycle == "active"
    # raw AI response preserved verbatim
    assert ev.ai_response["level"] == "moderate"
    assert ev.photo_keys == ["fake.jpg"]

    profile = await _profile_for("HN-01")
    assert profile.combined_severity == "moderate"
    assert profile.certainty == "confirmed"
    assert profile.latest_photo_event_id == ev.id
    assert profile.latest_self_test_event_id is None


@pytest.mark.asyncio
async def test_photo_assessment_mild_mapped_to_moderate_in_projection(client):
    """AI mild is promoted to moderate for DB/severity while the original AI
    level is preserved in ``ai_response``. Verified at the service layer
    because the HTTP photo path is privacy-gated in Phase 1."""
    from app.core.security import decode_token
    from app.posture import service

    token = await _login_user(client)
    user_id = decode_token(token)["sub"]
    async with TestSession() as db:
        result = await service.save_photo_assessment(
            db, user_id, "HN-01", ["fake.jpg"], _ai_result("mild")
        )
        assert result["result"] == "moderate"

    events = await _events_for("HN-01")
    ev = events[0]
    # AI mild promoted to moderate for DB/severity, original kept in ai_response
    assert ev.result == "moderate"
    assert ev.severity == "moderate"
    assert ev.ai_response["level"] == "mild"

    profile = await _profile_for("HN-01")
    assert profile.combined_severity == "moderate"


@pytest.mark.asyncio
async def test_two_sources_same_severity_confirmed(client):
    from app.core.security import decode_token
    from app.posture import service

    token = await _login_user(client)
    user_id = decode_token(token)["sub"]
    await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    async with TestSession() as db:
        await service.save_photo_assessment(
            db, user_id, "HN-01", ["fake.jpg"], _ai_result("moderate")
        )

    events = await _events_for("HN-01")
    assert len(events) == 2
    assert {e.source for e in events} == {"self_test", "ai_photo"}
    assert all(e.lifecycle == "active" for e in events)

    profile = await _profile_for("HN-01")
    assert profile.combined_severity == "moderate"
    assert profile.certainty == "confirmed"
    assert profile.has_conflict is False
    assert profile.latest_self_test_event_id is not None
    assert profile.latest_photo_event_id is not None


@pytest.mark.asyncio
async def test_two_sources_disagreement_is_conflict(client):
    """self_test moderate + photo severe -> conflict, combined null."""
    from app.core.security import decode_token
    from app.posture import service

    token = await _login_user(client)
    user_id = decode_token(token)["sub"]
    await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    async with TestSession() as db:
        await service.save_photo_assessment(
            db, user_id, "HN-01", ["fake.jpg"], _ai_result("severe")
        )

    profile = await _profile_for("HN-01")
    assert profile.combined_severity is None
    assert profile.certainty == "conflict"
    assert profile.has_conflict is True


@pytest.mark.asyncio
async def test_two_sources_one_null_is_provisional(client, photo_analysis_enabled):
    """self_test uncertain (null) + photo moderate -> provisional, combined null."""
    token = await _login_user(client)
    await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "uncertain"},
        headers={"Authorization": f"Bearer {token}"},
    )
    with patch(
        "app.posture.ai_service.analyze_posture_photo",
        new_callable=AsyncMock,
        return_value=_ai_result("moderate"),
    ):
        await client.post(
            "/api/v1/posture/assess/photo",
            json={"issue_id": "HN-01", "photo_keys": ["fake.jpg"]},
            headers={"Authorization": f"Bearer {token}"},
        )

    profile = await _profile_for("HN-01")
    assert profile.combined_severity is None
    assert profile.certainty == "provisional"
    assert profile.has_conflict is False


@pytest.mark.asyncio
async def test_photo_reassess_supersedes_prior_photo_only(client):
    """A new photo assessment supersedes only prior photo events, leaving an
    active self-test untouched."""
    from app.core.security import decode_token
    from app.posture import service

    token = await _login_user(client)
    user_id = decode_token(token)["sub"]
    # active self-test stays
    await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    for level in ("moderate", "severe"):
        async with TestSession() as db:
            await service.save_photo_assessment(
                db, user_id, "HN-01", ["fake.jpg"], _ai_result(level)
            )

    events = await _events_for("HN-01")
    photo_events = [e for e in events if e.source == "ai_photo"]
    self_events = [e for e in events if e.source == "self_test"]
    assert len(photo_events) == 2
    assert photo_events[0].lifecycle == "superseded"
    assert photo_events[1].lifecycle == "active"
    assert self_events[0].lifecycle == "active"  # untouched

    # latest photo severe disagrees with self_test moderate -> conflict
    profile = await _profile_for("HN-01")
    assert profile.certainty == "conflict"
    assert profile.combined_severity is None
    assert profile.latest_photo_event_id == photo_events[1].id


# ===========================================================================
# Transactional atomicity
# ===========================================================================


@pytest.mark.asyncio
async def test_transaction_failure_leaves_no_half_state(client):
    """If projection fails after the event was flushed, the whole write
    (event + supersede) is rolled back -- no half-committed state.

    Calls the service directly (rather than via HTTP) so the assertion targets
    the transactional rollback contract, independent of HTTP error handling.
    """
    from app.auth.models import User
    from app.posture import service

    token = await _login_user(client)
    async with TestSession() as db:
        res = await db.execute(select(User).where(User.phone == "13800138000"))
        user_id = str(res.scalar_one().id)

    with patch(
        "app.posture.service._recompute_and_upsert_profile",
        new_callable=AsyncMock,
        side_effect=RuntimeError("projection boom"),
    ):
        async with TestSession() as db:
            with pytest.raises(RuntimeError):
                await service.save_self_assessment(
                    db, user_id, "HN-01", "positive", 0
                )

    # event INSERT + supersede UPDATE were flushed but never committed ->
    # a fresh session sees nothing.
    assert await _all_events() == []
    assert await _all_profiles() == []


# ===========================================================================
# Photo gate disabled / AI failure / need_retake -> no-op
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.usefixtures("_force_photo_disabled")
async def test_photo_gate_disabled_creates_no_event_or_profile(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess/photo",
        json={"issue_id": "HN-01", "photo_keys": ["fake.jpg"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503
    assert await _all_events() == []
    assert await _all_profiles() == []


@pytest.mark.asyncio
async def test_photo_ai_failure_creates_no_event_or_profile(client, photo_analysis_enabled):
    token = await _login_user(client)
    with patch(
        "app.posture.ai_service.analyze_posture_photo",
        new_callable=AsyncMock,
        side_effect=ServiceUnavailable("AI service failed"),
    ):
        resp = await client.post(
            "/api/v1/posture/assess/photo",
            json={"issue_id": "HN-01", "photo_keys": ["fake.jpg"]},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 503
    assert await _all_events() == []
    assert await _all_profiles() == []


@pytest.mark.asyncio
async def test_photo_need_retake_creates_no_event_or_profile(
    client, photo_analysis_enabled
):
    token = await _login_user(client)
    with patch(
        "app.posture.ai_service.analyze_posture_photo",
        new_callable=AsyncMock,
        side_effect=ServiceUnavailable("照片质量不足，请重新拍照"),
    ):
        resp = await client.post(
            "/api/v1/posture/assess/photo",
            json={"issue_id": "HN-01", "photo_keys": ["fake.jpg"]},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 503
    assert await _all_events() == []
    assert await _all_profiles() == []


# ===========================================================================
# History API shape compatibility (no regression)
# ===========================================================================


@pytest.mark.asyncio
async def test_history_api_keeps_legacy_shape(client):
    token = await _login_user(client)
    await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.get(
        "/api/v1/posture/history", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    records = resp.json()
    assert len(records) == 1
    # legacy fields present and unchanged
    rec = records[0]
    assert set(rec.keys()) == {
        "id",
        "issue_id",
        "issue_name",
        "method",
        "result",
        "created_at",
    }
    assert rec["method"] == "self_test"
    assert rec["result"] == "moderate"


# ===========================================================================
# Concurrency serialization (review FIX 1)
# ===========================================================================


@pytest.mark.asyncio
async def test_concurrent_same_source_never_two_active_events(client):
    """Two concurrent same-source saves must never leave two active events.

    SQLite (test DB) serializes writes through a single-writer file lock and
    the service-level profile lock is a no-op there, so this asserts the
    INVARIANT rather than true parallelism: after both saves complete there is
    exactly ONE active event for the (user, issue, source) triple. On
    PostgreSQL the ``_acquire_profile_lock`` row/advisory lock is what
    guarantees this invariant under real concurrency.
    """
    from app.auth.models import User
    from app.posture import service

    token = await _login_user(client)
    async with TestSession() as db:
        res = await db.execute(select(User).where(User.phone == "13800138000"))
        user_id = str(res.scalar_one().id)

    async def _one_save():
        async with TestSession() as db:
            await service.save_self_assessment(db, user_id, "HN-01", "positive", 0)

    await asyncio.gather(_one_save(), _one_save())

    events = await _events_for("HN-01")
    active = [e for e in events if e.lifecycle == "active"]
    # invariant: never two active same-source events
    assert len(active) == 1
    superseded = [e for e in events if e.lifecycle == "superseded"]
    assert len(superseded) == 1
    # exactly one profile row, projecting the single active event
    profiles = await _all_profiles()
    assert len(profiles) == 1
    assert profiles[0].latest_self_test_event_id == active[0].id


# ===========================================================================
# content_version provenance (review FIX 2)
# ===========================================================================


@pytest.mark.asyncio
async def test_self_assessment_stamps_extended_test_content_version(client):
    """An extended self_test (carrying content_version) is stamped onto the
    event for knowledge-base provenance. HN-01 self_tests[0] is the extended
    靠墙站立测试 with content_version == 'phase1-v1'."""
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    events = await _events_for("HN-01")
    assert len(events) == 1
    assert events[0].content_version == "phase1-v1"


@pytest.mark.asyncio
async def test_self_assessment_legacy_test_has_null_content_version(client):
    """A legacy self_test (no content_version) leaves the event's
    content_version as None. HN-01 self_tests[1] (侧面拍照法) is legacy."""
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 1, "answer": "positive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    events = await _events_for("HN-01")
    assert len(events) == 1
    assert events[0].content_version is None


@pytest.mark.asyncio
async def test_photo_assessment_has_null_content_version(client):
    """Photo assessments have no knowledge-base content version; the event's
    content_version stays None. Verified at the service layer because the HTTP
    photo path is privacy-gated in Phase 1."""
    from app.core.security import decode_token
    from app.posture import service

    token = await _login_user(client)
    user_id = decode_token(token)["sub"]
    async with TestSession() as db:
        await service.save_photo_assessment(
            db, user_id, "HN-01", ["fake.jpg"], _ai_result("moderate")
        )

    events = await _events_for("HN-01")
    assert len(events) == 1
    assert events[0].content_version is None


# ===========================================================================
# Risk-tier preservation (review FIX 3 / FIX 5)
# ===========================================================================


@pytest.mark.asyncio
async def test_projection_preserves_existing_risk_tier_and_version(client):
    """Once a non-normal risk_tier/risk_version is set (by the safety overlay),
    a new assessment must NOT reset them to the normal baseline.

    Simulates the safety system writing a 'cautious' tier before the
    projection runs; the subsequent save takes the UPDATE path and must leave
    risk_tier/risk_version untouched while still refreshing projection fields.
    """
    from app.auth.models import User

    token = await _login_user(client)
    async with TestSession() as db:
        res = await db.execute(select(User).where(User.phone == "13800138000"))
        user_id = res.scalar_one().id

    # Simulate the safety overlay writing a cautious risk tier first.
    async with TestSession() as db:
        db.add(
            PostureProfileEntry(
                id=uuid4(),
                user_id=user_id,
                issue_id="HN-01",
                combined_severity=None,
                certainty="provisional",
                sources=[],
                has_conflict=False,
                risk_tier="cautious",
                risk_version="2026-safety-v1",
            )
        )
        await db.commit()

    # New self-assessment -> UPDATE path; risk_tier/risk_version preserved.
    resp = await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    profile = await _profile_for("HN-01")
    assert profile is not None
    # NOT reset to normal / phase1-initial-v1
    assert profile.risk_tier == "cautious"
    assert profile.risk_version == "2026-safety-v1"
    # projection fields still refresh on the UPDATE
    assert profile.combined_severity == "moderate"
    assert profile.certainty == "confirmed"
    # still exactly one profile row (upsert, not duplicate)
    assert len(await _all_profiles()) == 1
