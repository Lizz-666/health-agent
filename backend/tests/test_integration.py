"""Cross-task integration tests for the Phase 1 integration branch.

Exercises the seams between the three merged feature sets:
  * Task 2  -- assessment dual-write + profile projection (``service.py``)
  * Task 6.5 -- safety signals + versioned risk classification (``safety.py``)
  * Task 9  -- privacy gate / health-data purge + write-freeze (``purge.py``)

These tests verify the *integration* wiring that no single feature's own test
file could cover:
  1. save -> safety signal -> risk overlay (projection connects to risk)
  2. risk preservation under a new assessment (overlay not reset to normal)
  3. write-freeze guard blocks both write paths during a purge
  4. freeze released after the purge reaches a terminal state
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.exceptions import AppException
from app.core.security import decode_token
from app.posture import safety, service
from app.posture.models import (
    PostureAssessmentEvent,
    PostureProfileEntry,
    PurgeOperation,
)
from tests.conftest import TestSession


# --------------------------------------------------------------------------- #
# Shared helpers (mirror tests/test_posture_profile.py patterns)
# --------------------------------------------------------------------------- #


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


async def _profile_for(issue_id: str):
    async with TestSession() as db:
        result = await db.execute(
            select(PostureProfileEntry).where(
                PostureProfileEntry.issue_id == issue_id
            )
        )
        return result.scalar_one_or_none()


async def _all_events():
    async with TestSession() as db:
        result = await db.execute(select(PostureAssessmentEvent))
        return result.scalars().all()


async def _all_profiles():
    async with TestSession() as db:
        result = await db.execute(select(PostureProfileEntry))
        return result.scalars().all()


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


def _seed_inflight_purge(user_id: str, status: str = "freezing"):
    """Persist a non-terminal purge_operation for ``user_id`` (write freeze)."""

    async def _seed():
        async with TestSession() as db:
            db.add(
                PurgeOperation(
                    user_id=UUID(user_id),
                    trigger="user_delete",
                    status=status,
                    attempt_count=0,
                    max_attempts=10,
                    expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                )
            )
            await db.commit()

    return _seed


# ===========================================================================
# 1. save -> safety signal -> risk overlay (Task 2 + 6.5)
# ===========================================================================


@pytest.mark.asyncio
async def test_save_then_safety_signal_applies_risk_overlay(client):
    """A fresh self-assessment creates a profile with risk_tier=normal; recording
    a structured safety signal reclassifies the user and the profile's
    risk_tier is downgraded immediately by the safety overlay."""
    token = await _login_user(client)
    user_id = decode_token(token)["sub"]

    # 1. self-assessment -> profile created with normal baseline risk
    async with TestSession() as db:
        result = await service.save_self_assessment(
            db, user_id, "HN-01", "positive", 0
        )
    assert result["result"] == "moderate"
    profile = await _profile_for("HN-01")
    assert profile is not None
    assert profile.risk_tier == "normal"
    assert profile.combined_severity == "moderate"

    # 2. record a moderate pain signal -> reclassify -> cautious
    async with TestSession() as db:
        resp = await safety.record_safety_signal(
            db,
            user_id,
            {
                "signal_type": "pain",
                "body_region": "cervical",
                "related_issue_id": "HN-01",
                "severity_hint": "moderate",
            },
            idempotency_key="integ-overlay-1",
        )
    assert resp["risk_tier"] == "cautious"

    profile = await _profile_for("HN-01")
    # overlay applied to the related issue's profile entry, not reset to normal
    assert profile.risk_tier == "cautious"
    assert profile.risk_tier != "normal"


# ===========================================================================
# 2. risk preservation under a new assessment (overlay re-derives on re-project)
# ===========================================================================


@pytest.mark.asyncio
async def test_risk_preserved_under_new_assessment(client):
    """Once a safety signal has set risk_tier=cautious, a subsequent assessment
    must NOT reset it to normal. The risk overlay in service.py re-derives the
    tier from the still-active signal on every projection recompute, while the
    projection fields (severity/certainty) refresh normally."""
    token = await _login_user(client)
    user_id = decode_token(token)["sub"]

    async with TestSession() as db:
        await service.save_self_assessment(db, user_id, "HN-01", "positive", 0)
    async with TestSession() as db:
        await safety.record_safety_signal(
            db,
            user_id,
            {
                "signal_type": "pain",
                "body_region": "cervical",
                "related_issue_id": "HN-01",
                "severity_hint": "moderate",
            },
            idempotency_key="integ-preserve-1",
        )
    profile = await _profile_for("HN-01")
    assert profile.risk_tier == "cautious"

    # new self-assessment (negative -> normal severity) triggers a re-project
    async with TestSession() as db:
        await service.save_self_assessment(db, user_id, "HN-01", "negative", 0)

    profile = await _profile_for("HN-01")
    # risk_tier stays cautious (overlay re-derived from the active signal),
    # NOT reset to the normal baseline
    assert profile.risk_tier == "cautious"
    # Active safety signals force certainty=provisional + combined_severity=None
    # (review fix #3): projection fields are overridden while signals are active.
    assert profile.combined_severity is None
    assert profile.certainty == "provisional"


# ===========================================================================
# 3. write-freeze guard blocks both write paths during a purge (Task 2 + 9)
# ===========================================================================


@pytest.mark.asyncio
async def test_freeze_guard_blocks_both_write_paths_during_purge(client):
    """While a non-terminal purge_operation exists, save_self_assessment AND
    save_photo_assessment are both rejected with 409 write_frozen_during_purge
    and leave no persisted event/profile behind."""
    token = await _login_user(client)
    user_id = decode_token(token)["sub"]

    await _seed_inflight_purge(user_id)()

    # self-assessment write path -> rejected
    async with TestSession() as db:
        with pytest.raises(AppException) as exc_self:
            await service.save_self_assessment(
                db, user_id, "HN-01", "positive", 0
            )
    assert exc_self.value.status_code == 409
    assert exc_self.value.code == "write_frozen_during_purge"

    # photo-assessment write path -> also rejected
    async with TestSession() as db:
        with pytest.raises(AppException) as exc_photo:
            await service.save_photo_assessment(
                db, user_id, "HN-01", ["fake.jpg"], _ai_result("moderate")
            )
    assert exc_photo.value.status_code == 409
    assert exc_photo.value.code == "write_frozen_during_purge"

    # nothing was persisted (guard fired before any event creation)
    assert await _all_events() == []
    assert await _all_profiles() == []


# ===========================================================================
# 4. freeze released after purge completes (Task 2 + 9)
# ===========================================================================


@pytest.mark.asyncio
async def test_save_works_again_after_purge_completes(client):
    """After a purge reaches a terminal state and its linkable user_id is
    scrubbed (spec §6.7.3 方案 B), the write freeze is released and a new
    assessment succeeds again."""
    from app.posture import purge

    token = await _login_user(client)
    user_id = decode_token(token)["sub"]

    # in-flight purge freezes writes
    await _seed_inflight_purge(user_id)()
    async with TestSession() as db:
        with pytest.raises(AppException):
            await service.save_self_assessment(db, user_id, "HN-01", "positive", 0)

    # the freeze guard itself reports frozen
    async with TestSession() as db:
        assert await purge.is_user_write_frozen(db, user_id) is True

    # purge completes: terminal status + linkable fields scrubbed (mirrors the
    # _finalize_purge contract in purge.py)
    async with TestSession() as db:
        op = (
            await db.execute(
                select(PurgeOperation).where(
                    PurgeOperation.user_id == UUID(user_id)
                )
            )
        ).scalar_one()
        op.status = "completed"
        op.user_id = None
        await db.commit()

    # freeze released
    async with TestSession() as db:
        assert await purge.is_user_write_frozen(db, user_id) is False

    # save works again
    async with TestSession() as db:
        result = await service.save_self_assessment(
            db, user_id, "HN-01", "positive", 0
        )
    assert result["result"] == "moderate"
    profile = await _profile_for("HN-01")
    assert profile is not None
    assert profile.combined_severity == "moderate"
