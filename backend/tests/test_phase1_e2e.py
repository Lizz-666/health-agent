"""Phase 1 Task 10: Final end-to-end acceptance (post Phase C migration).

This suite is the final acceptance gate for Phase 1 posture core
productization.  It exercises the complete user journey against the
post-Phase-C delivery shape (migration 0003: source/lifecycle NOT NULL,
severity nullable, method/result columns dropped).

Coverage (plan Task 10, spec section 17):
  1.  Alembic head = 0003_posture_contract
  2.  source/lifecycle NOT NULL, severity nullable, method/result deleted
  3.  Real PostgreSQL upgrade/downgrade/re-upgrade round-trip
  4.  Synthetic user registration + login
  5.  Browse issues + detail (extended self-test + structured source)
  6.  Complete self-test -> event + profile
  7.  Profile: evaluated vs unevaluated, combined_severity nullable
  8.  Conflict: no "take more severe" auto-merge
  9.  Priority three-way routing (normal / retest / safety_blocked)
  10. Confirm goals -> suggestion_id / profile_version contract
  11. Safety signal pain -> provisional + stale suggestion_id
  12. Old suggestion_id confirm -> 409 stale_priority
  13. acute_trauma -> restricted -> safety_blocked (not retest_required)
  14. Purge: photo_keys protection, OSS delete, encrypted_keys clear,
      DB delete, tombstone, no linkable residue
  15. Idempotency expiry + purge coverage
  16. /assess/photo -> 503 (privacy gate hard-reject)

All data is synthetic.  Photo analysis is disabled throughout.
"""

import os
import subprocess
import sys
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import decode_token
from app.posture import purge, service
from app.posture.models import (
    IdempotencyRecord,
    PostureAssessmentEvent,
    PostureProfileEntry,
    PosturePurgeTombstone,
    PostureSafetySignal,
    PostureUserGoal,
    PurgeOperation,
)
from app.posture.risk_rules import RISK_VERSION
from tests.conftest import TestSession


_BACKEND_DIR = Path(__file__).resolve().parent.parent
_TEST_PURGE_KEY = "0123456789abcdef" * 4  # 32-byte AES-256 key


# ---------------------------------------------------------------------------
# Shared helpers
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
    return decode_token(token)["sub"]


def _ai_result(level, **overrides):
    base = {
        "level": level,
        "confidence": 0.82,
        "evidence": ["evidence"],
        "suggestion": "suggestion",
        "need_retake": False,
        "retake_reason": "",
    }
    base.update(overrides)
    return base


async def _make_user(db) -> _uuid.UUID:
    from app.auth.models import User

    user = User(phone="139" + _uuid.uuid4().hex[:8], nickname="e2e_user")
    db.add(user)
    await db.flush()
    return user.id


async def _seed_photo_event(db, user_id, issue_id="HN-01", photo_keys=None):
    evt = PostureAssessmentEvent(
        user_id=user_id,
        issue_id=issue_id,
        source="ai_photo",
        severity="moderate",
        lifecycle="active",
        photo_keys=photo_keys or [],
        ai_response={"level": "moderate", "confidence": 0.8},
    )
    db.add(evt)
    await db.flush()
    return evt


@pytest.fixture
def _purge_key(monkeypatch):
    """Ensure a valid PURGE_ENCRYPTION_KEY is configured for purge calls."""
    monkeypatch.setattr(settings, "PURGE_ENCRYPTION_KEY", _TEST_PURGE_KEY)


# ===========================================================================
# Section A: Migration contract verification (points 1-2)
# ===========================================================================


def _run_alembic(*args):
    env = dict(os.environ)
    env["DATABASE_URL"] = (
        "postgresql+asyncpg://user:password@localhost:5432/posture_app"
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(_BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )


def test_e2e_migration_head_is_current():
    """Point 1: Alembic has exactly one head, at the current chain tip.

    This tracks the live migration head; it advances with each new migration.
    Currently ``0012_review_draft_origins`` (Phase 7), advanced from
    ``0010_nutrition_recommendations`` (Phase 6).
    """
    proc = _run_alembic("heads")
    assert proc.returncode == 0, proc.stderr
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1, f"expected exactly one head, got: {lines}"
    assert lines[0].split()[0] == "0013_controlled_trial_auth", lines[0]


def test_e2e_schema_source_lifecycle_not_null_severity_nullable():
    """Point 2: ORM metadata reflects Phase C contract.

    source / lifecycle NOT NULL; severity permanently nullable;
    method / result columns absent.
    """
    from app.db.base import Base
    import app.auth.models  # noqa: F401
    import app.posture.models  # noqa: F401

    events = Base.metadata.tables["posture_assessment_events"]
    assert events.c["source"].nullable is False, "source must be NOT NULL"
    assert events.c["lifecycle"].nullable is False, "lifecycle must be NOT NULL"
    assert events.c["severity"].nullable is True, "severity must be nullable"
    assert "method" not in events.c, "method column must be dropped"
    assert "result" not in events.c, "result column must be dropped"


# ===========================================================================
# Section B: PostgreSQL upgrade/downgrade/re-upgrade round-trip (point 3)
# ===========================================================================

from tests.conftest_pg import pg_available, skip_reason  # noqa: E402


@pytest.mark.skipif(not pg_available, reason=skip_reason)
@pytest.mark.asyncio
async def test_e2e_pg_upgrade_downgrade_reupgrade(pg_dsn):
    """Point 3: real PostgreSQL round-trip 0002 -> 0003 -> 0002 -> 0003.

    Synthetic rows cover normal severity, null severity (legacy uncertain),
    and null source/lifecycle (pre-backfill).
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    def _alembic(target, direction="upgrade"):
        env = dict(os.environ)
        env["DATABASE_URL"] = pg_dsn
        result = subprocess.run(
            [sys.executable, "-m", "alembic", direction, target],
            cwd=str(_BACKEND_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"alembic {direction} {target} failed:\n{result.stderr}"
        )

    engine = create_async_engine(pg_dsn, poolclass=NullPool)

    try:
        # --- Downgrade to 0002 ---
        _alembic("0002", direction="downgrade")

        # --- Seed synthetic data at 0002 level ---
        async with engine.begin() as conn:
            await conn.execute(text(
                "INSERT INTO users (id, phone, nickname, membership_level) "
                "VALUES ('c0000000-0000-0000-0000-000000000001'::uuid, "
                "'13900000099', 'rt_user', 'free') ON CONFLICT DO NOTHING"
            ))
            await conn.execute(text(
                "INSERT INTO posture_assessment_events "
                "(id, user_id, issue_id, method, result, source, severity, lifecycle) "
                "VALUES ("
                "'d0000000-0000-0000-0000-000000000001'::uuid, "
                "'c0000000-0000-0000-0000-000000000001'::uuid, "
                "'HN-01', 'self_test', 'moderate', 'self_test', 'moderate', 'active')"
            ))
            await conn.execute(text(
                "INSERT INTO posture_assessment_events "
                "(id, user_id, issue_id, method, result, source, severity, lifecycle) "
                "VALUES ("
                "'d0000000-0000-0000-0000-000000000002'::uuid, "
                "'c0000000-0000-0000-0000-000000000001'::uuid, "
                "'HN-02', 'ai_photo', 'uncertain', 'ai_photo', NULL, 'active')"
            ))
            await conn.execute(text(
                "INSERT INTO posture_assessment_events "
                "(id, user_id, issue_id, method, result, source, severity, lifecycle) "
                "VALUES ("
                "'d0000000-0000-0000-0000-000000000003'::uuid, "
                "'c0000000-0000-0000-0000-000000000001'::uuid, "
                "'ST-04', 'self_test', 'normal', NULL, 'normal', NULL)"
            ))

        # --- Upgrade to 0003 ---
        _alembic("0003_posture_contract")

        # --- Verify post-upgrade ---
        async with engine.begin() as conn:
            cols = await conn.execute(text(
                "SELECT column_name, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_name = 'posture_assessment_events'"
            ))
            col_map = {r[0]: r[1] for r in cols.fetchall()}
            assert "method" not in col_map
            assert "result" not in col_map
            assert col_map["source"] == "NO"
            assert col_map["lifecycle"] == "NO"
            assert col_map["severity"] == "YES"

            row3 = (await conn.execute(text(
                "SELECT source, lifecycle FROM posture_assessment_events "
                "WHERE id = 'd0000000-0000-0000-0000-000000000003'::uuid"
            ))).fetchone()
            assert row3[0] == "self_test"
            assert row3[1] == "active"

        # --- Downgrade back to 0002 ---
        _alembic("0002", direction="downgrade")

        # --- Verify post-downgrade ---
        async with engine.begin() as conn:
            cols = await conn.execute(text(
                "SELECT column_name, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_name = 'posture_assessment_events'"
            ))
            col_map = {r[0]: r[1] for r in cols.fetchall()}
            assert col_map["method"] == "NO"
            assert col_map["result"] == "NO"
            assert col_map["source"] == "YES"
            assert col_map["lifecycle"] == "YES"

            row2 = (await conn.execute(text(
                "SELECT method, result FROM posture_assessment_events "
                "WHERE id = 'd0000000-0000-0000-0000-000000000002'::uuid"
            ))).fetchone()
            assert row2[0] == "ai_photo"
            assert row2[1] == "uncertain"

        # --- Re-upgrade to 0003 ---
        _alembic("0003_posture_contract")

        # --- Verify re-upgrade ---
        async with engine.begin() as conn:
            cols = await conn.execute(text(
                "SELECT column_name, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_name = 'posture_assessment_events'"
            ))
            col_map = {r[0]: r[1] for r in cols.fetchall()}
            assert "method" not in col_map
            assert "result" not in col_map
            assert col_map["source"] == "NO"
            assert col_map["lifecycle"] == "NO"
            assert col_map["severity"] == "YES"
    finally:
        try:
            _alembic("head")
        except Exception:
            pass
        await engine.dispose()


# ===========================================================================
# Section C: Full user journey E2E (points 4-16)
# ===========================================================================


@pytest.mark.asyncio
async def test_e2e_full_user_journey(client):
    """Points 4-16: complete user journey from registration to safety gate.

    Exercises browse -> self-test -> profile -> conflict -> priorities ->
    confirm -> safety signal -> stale check -> acute_trauma ->
    safety_blocked -> photo gate 503.
    """
    # --- Point 4: register + login ---
    token = await _login_user(client)
    uid = _uid(token)
    h = _headers(token)

    # --- Point 5: browse issues + detail ---
    resp = await client.get("/api/v1/posture/issues", headers=h)
    assert resp.status_code == 200
    issues = resp.json()
    assert len(issues) == 26
    for item in issues:
        assert set(item.keys()) == {
            "id", "name_cn", "category", "aliases", "definition",
        }

    resp = await client.get("/api/v1/posture/issues/HN-01", headers=h)
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["name_cn"] == "头部前倾"
    for st in detail["self_tests"]:
        assert "correct_posture" in st
        assert "common_errors" in st
        assert "stop_conditions" in st
        assert "source" in st

    # --- Point 6: complete self-test HN-01 ---
    resp = await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "moderate"

    # --- Point 7: profile shows evaluated vs unevaluated ---
    resp = await client.get("/api/v1/posture/profile", headers=h)
    assert resp.status_code == 200
    profile = resp.json()
    assert len(profile["evaluated_issues"]) == 1
    assert profile["evaluated_issues"][0]["issue_id"] == "HN-01"
    assert profile["evaluated_issues"][0]["combined_severity"] == "moderate"
    assert profile["evaluated_issues"][0]["certainty"] == "confirmed"
    assert len(profile["unevaluated_categories"]) > 0

    # --- Self-test ST-04 to have a second evaluated issue ---
    resp = await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "ST-04", "test_index": 0, "answer": "positive"},
        headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "moderate"

    # --- Point 8: conflict (photo severe vs self-test moderate) ---
    # Photo HTTP endpoint is privacy-gated (503), so create via service layer.
    async with TestSession() as db:
        await service.save_photo_assessment(
            db, uid, "HN-01", ["e2e-photo.jpg"], _ai_result("severe"),
        )

    resp = await client.get("/api/v1/posture/profile", headers=h)
    assert resp.status_code == 200
    hn01 = next(
        e for e in resp.json()["evaluated_issues"] if e["issue_id"] == "HN-01"
    )
    assert hn01["certainty"] == "conflict"
    assert hn01["combined_severity"] is None
    assert hn01["has_conflict"] is True

    # --- Point 9: priority three-way routing ---
    resp = await client.get("/api/v1/posture/priorities", headers=h)
    assert resp.status_code == 200
    prio = resp.json()
    assert prio["suggestion_id"]
    assert prio["profile_version"]
    stale_suggestion_id = prio["suggestion_id"]
    stale_profile_version = prio["profile_version"]

    retest_ids = {r["issue_id"] for r in prio["retest_required"]}
    normal_ids = {c["issue_id"] for c in prio["normal_candidates"]}
    assert "HN-01" in retest_ids, "conflict issue must be in retest_required"
    assert "ST-04" in normal_ids, "confirmed moderate must be in normal_candidates"
    assert len(prio["safety_blocked"]) == 0

    # --- Point 10: confirm goals ---
    resp = await client.post(
        "/api/v1/posture/goals/confirm",
        json={
            "suggestion_id": stale_suggestion_id,
            "profile_version": stale_profile_version,
            "goals": [{"issue_id": "ST-04", "priority_rank": 1}],
            "idempotency_key": "e2e-confirm-1",
        },
        headers=h,
    )
    assert resp.status_code == 200
    confirmed = resp.json()
    assert len(confirmed["confirmed_goals"]) == 1
    assert confirmed["confirmed_goals"][0]["issue_id"] == "ST-04"
    assert confirmed["can_generate_plan"] is True
    assert confirmed["risk_version"] == RISK_VERSION

    # --- Point 11: safety signal pain -> provisional ---
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json={
            "signal_type": "pain",
            "body_region": "head_neck",
            "related_issue_id": "HN-01",
            "severity_hint": "mild",
            "idempotency_key": "e2e-pain-1",
        },
        headers=h,
    )
    assert resp.status_code == 200
    sig = resp.json()
    assert sig["status"] == "recorded"
    assert sig["risk_tier"] == "cautious"
    assert sig["risk_version"] == RISK_VERSION

    resp = await client.get(
        "/api/v1/posture/profile/HN-01", headers=h,
    )
    assert resp.status_code == 200
    hn01_detail = resp.json()
    assert hn01_detail["certainty"] == "provisional"
    assert hn01_detail["combined_severity"] is None

    # --- Point 12: old suggestion_id confirm -> 409 stale_priority ---
    resp = await client.post(
        "/api/v1/posture/goals/confirm",
        json={
            "suggestion_id": stale_suggestion_id,
            "profile_version": stale_profile_version,
            "goals": [{"issue_id": "ST-04", "priority_rank": 1}],
            "idempotency_key": "e2e-confirm-stale",
        },
        headers=h,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "stale_priority"

    # --- Point 13: acute_trauma -> restricted -> safety_blocked ---
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json={
            "signal_type": "acute_trauma",
            "related_issue_id": "ST-04",
            "idempotency_key": "e2e-acute-trauma-1",
        },
        headers=h,
    )
    assert resp.status_code == 200
    trauma = resp.json()
    assert trauma["risk_tier"] == "restricted"
    assert trauma["classification"]["rule_id"] == "RST-acute-trauma"
    assert trauma["risk_tier"] != "red_flag"

    resp = await client.get("/api/v1/posture/priorities", headers=h)
    assert resp.status_code == 200
    prio2 = resp.json()
    blocked_ids = {b["issue_id"] for b in prio2["safety_blocked"]}
    retest_ids2 = {r["issue_id"] for r in prio2["retest_required"]}
    assert "ST-04" in blocked_ids, (
        "acute_trauma restricted issue must be in safety_blocked"
    )
    assert "ST-04" not in retest_ids2, (
        "restricted issue must NOT be downgraded to retest_required "
        "even though certainty is provisional"
    )

    # --- Point 16: /assess/photo hard-rejects with 503 ---
    resp = await client.post(
        "/api/v1/posture/assess/photo",
        json={
            "issue_id": "HN-01",
            "photo_keys": ["test/photo.jpg"],
            "idempotency_key": "e2e-photo-1",
        },
        headers=h,
    )
    assert resp.status_code == 503
    assert resp.json()["code"] == "photo_analysis_disabled"


# ===========================================================================
# Section D: Purge E2E (points 14-15)
# ===========================================================================


@pytest.mark.asyncio
async def test_e2e_purge_full_flow(client, _purge_key):
    """Point 14: full account-deletion purge.

    Verifies: photo_keys encrypted -> OSS deletion -> encrypted_object_keys
    cleared -> DB health data deleted -> tombstone written -> purge_operation
    scrubbed -> no linkable residue.
    """
    async with TestSession() as db:
        user_id = await _make_user(db)
        secret_key = f"posture_photos/{user_id}/ULTRA-SECRET-e2e-key.jpg"
        await _seed_photo_event(
            db, user_id, issue_id="HN-01",
            photo_keys=[secret_key],
        )
        evt2 = PostureAssessmentEvent(
            user_id=user_id, issue_id="HN-02",
            source="self_test", severity="normal", lifecycle="active",
        )
        db.add(evt2)
        await db.flush()
        db.add(PostureProfileEntry(
            user_id=user_id, issue_id="HN-01",
            combined_severity="moderate", certainty="confirmed",
            sources={}, has_conflict=False,
            risk_tier="normal", risk_version="phase1-initial-v1",
        ))
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing(f"posture_photos/{user_id}/ULTRA-SECRET-e2e-key.jpg")

    async with TestSession() as db:
        result = await purge.run_purge(
            db, user_id, store, trigger="user_delete",
            encryption_key=_TEST_PURGE_KEY,
        )

    assert result.status == "completed"
    assert result.tombstone_receipt_id is not None

    # Step ordering: encrypted keys cleared BEFORE DB row deletion.
    steps = result.steps
    assert "clear_encrypted_object_keys" in steps
    assert "delete_assessment_events" in steps
    assert steps.index("clear_encrypted_object_keys") < steps.index(
        "delete_assessment_events"
    )
    assert steps.index("delete_oss_objects") < steps.index(
        "clear_encrypted_object_keys"
    )

    # OSS objects were deleted.
    assert len(store.deleted_keys) == 1

    # All health-data tables are empty for the user.
    async with TestSession() as db:
        for model in (
            PostureAssessmentEvent, PostureProfileEntry,
            PostureSafetySignal, PostureUserGoal, IdempotencyRecord,
        ):
            rows = (
                await db.execute(
                    select(model).where(model.user_id == user_id)
                )
            ).scalars().all()
            assert rows == [], f"{model.__name__} rows must be deleted"

        # Tombstone exists with only unlinkable fields.
        tomb = (
            await db.execute(select(PosturePurgeTombstone))
        ).scalar_one()
        assert tomb.receipt_id == result.tombstone_receipt_id
        assert tomb.purge_reason == "user_delete"
        assert tomb.object_delete_status in (
            "oss_deleted", "oss_not_applicable", "oss_deleted_or_not_found",
        )
        assert tomb.policy_version
        tomb_cols = {c.name for c in PosturePurgeTombstone.__table__.columns}
        for forbidden in ("user_id", "issue_id", "event_id", "source"):
            assert forbidden not in tomb_cols, (
                f"tombstone must not carry {forbidden}"
            )

        # PurgeOperation is scrubbed (no linkable fields).
        ops = (
            await db.execute(select(PurgeOperation))
        ).scalars().all()
        assert len(ops) == 1
        op = ops[0]
        assert op.status == "completed"
        assert op.user_id is None
        assert op.target_event_ids is None
        assert op.target_signal_ids is None
        assert op.encrypted_object_keys is None
        assert op.completed_at is not None


@pytest.mark.asyncio
async def test_e2e_idempotency_expiry_and_purge_coverage(client, _purge_key):
    """Point 15: idempotency records are covered by purge.

    Expired confirm idempotency records can be reused, and account-deletion
    purge deletes the surviving idempotency records for privacy.
    """
    token = await _login_user(client, phone="13800139000")
    uid = _uid(token)
    h = _headers(token)

    # Self-test + priorities + confirm to create an idempotency record.
    await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers=h,
    )
    prio = (await client.get("/api/v1/posture/priorities", headers=h)).json()
    confirm_resp = await client.post(
        "/api/v1/posture/goals/confirm",
        json={
            "suggestion_id": prio["suggestion_id"],
            "profile_version": prio["profile_version"],
            "goals": [{"issue_id": "HN-01", "priority_rank": 1}],
            "idempotency_key": "e2e-purge-idem-1",
        },
        headers=h,
    )
    assert confirm_resp.status_code == 200

    # Expired idempotency record is removed and the same key can be reused.
    async with TestSession() as db:
        user_uuid = _uuid.UUID(uid)
        record = (
            await db.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.user_id == user_uuid,
                    IdempotencyRecord.operation == "confirm_goals",
                    IdempotencyRecord.idempotency_key == "e2e-purge-idem-1",
                )
            )
        ).scalar_one()
        record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()

    confirm_reuse = await client.post(
        "/api/v1/posture/goals/confirm",
        json={
            "suggestion_id": prio["suggestion_id"],
            "profile_version": prio["profile_version"],
            "goals": [{"issue_id": "HN-01", "priority_rank": 1}],
            "idempotency_key": "e2e-purge-idem-1",
        },
        headers=h,
    )
    assert confirm_reuse.status_code == 200

    # Purge the user.
    async with TestSession() as db:
        await _seed_photo_event(
            db, user_uuid, issue_id="HN-01",
            photo_keys=["e2e-purge-idem-photo.jpg"],
        )
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing("e2e-purge-idem-photo.jpg")

    async with TestSession() as db:
        result = await purge.run_purge(
            db, user_uuid, store, trigger="user_delete",
            encryption_key=_TEST_PURGE_KEY,
        )
    assert result.status == "completed"

    # Idempotency records for the user are deleted.
    async with TestSession() as db:
        records = (
            await db.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.user_id == user_uuid
                )
            )
        ).scalars().all()
        assert records == [], "idempotency records must be purged"
