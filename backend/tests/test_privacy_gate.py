"""Tests for the photo privacy gate (spec §13.3/§13.4) and purge flow (§6.7).

Phase 1 guarantee: the privacy gate HARD-REJECTS photo analysis / upload STS
paths because all 8 enablement conditions lack implementation evidence. This
is NOT a "8 config booleans true -> allow" fake gate. The purge flow performs
real deletion of health payloads while preserving an unlinkable tombstone.
"""

import json
import logging
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import privacy_gate
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.security import decode_token
from app.posture import purge
from app.posture.models import (
    IdempotencyRecord,
    PostureAssessmentEvent,
    PostureProfileEntry,
    PosturePurgeTombstone,
    PostureSafetySignal,
    PostureUserGoal,
    PurgeOperation,
)


# A valid AES-256 key (32 bytes / 64 hex chars) used by every purge test.
_TEST_PURGE_KEY = (
    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
)


@pytest.fixture(autouse=True)
def _configure_purge_encryption_key(monkeypatch):
    """Ensure a valid PURGE_ENCRYPTION_KEY is configured for purge calls.

    Purge validates the key up front (FIX 1); tests that need to override it
    (empty/wrong key) call ``monkeypatch.setattr`` themselves after this.
    """
    monkeypatch.setattr(settings, "PURGE_ENCRYPTION_KEY", _TEST_PURGE_KEY)


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


async def _login_user(client, phone="13800138000"):
    await client.post("/api/v1/auth/send-code", json={"phone": phone})
    from app.auth.models import VerificationCode
    from tests.conftest import TestSession

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


def _user_id_from_token(token: str) -> _uuid.UUID:
    return _uuid.UUID(decode_token(token)["sub"])


async def _make_user(db) -> _uuid.UUID:
    from app.auth.models import User

    user = User(phone="139" + _uuid.uuid4().hex[:8])
    db.add(user)
    await db.flush()
    return user.id


async def _seed_photo_event(db, user_id, issue_id="HN-01", photo_keys=None):
    if photo_keys is None:
        photo_keys = [f"posture_photos/{user_id}/secret-photo-key-001.jpg"]
    event = PostureAssessmentEvent(
        user_id=user_id,
        issue_id=issue_id,
        source="ai_photo",
        severity="moderate",
        lifecycle="active",
        ai_response={"level": "moderate", "confidence": 0.8},
        ai_model_meta={"model": "demo", "version": "0.0", "confidence": 0.8},
        photo_keys=photo_keys,
        content_version="phase1-v1",
    )
    db.add(event)
    await db.flush()
    return event


async def _seed_self_test_event(db, user_id, issue_id="HN-02"):
    event = PostureAssessmentEvent(
        user_id=user_id,
        issue_id=issue_id,
        source="self_test",
        severity="normal",
        lifecycle="active",
        self_test_answers={"test_index": 0, "answer": "negative"},
    )
    db.add(event)
    await db.flush()
    return event


async def _seed_full_dataset(db, user_id):
    photo_event = await _seed_photo_event(
        db,
        user_id,
        photo_keys=[
            f"posture_photos/{user_id}/aaa.jpg",
            f"posture_photos/{user_id}/bbb.jpg",
        ],
    )
    self_event = await _seed_self_test_event(db, user_id)

    db.add_all(
        [
            PostureProfileEntry(
                user_id=user_id,
                issue_id="HN-01",
                combined_severity="moderate",
                certainty="confirmed",
                sources={},
                has_conflict=False,
                risk_tier="normal",
                risk_version="2026-07-11-v1",
                latest_photo_event_id=photo_event.id,
            ),
            PostureProfileEntry(
                user_id=user_id,
                issue_id="HN-02",
                combined_severity="normal",
                certainty="confirmed",
                sources={},
                has_conflict=False,
                risk_tier="normal",
                risk_version="2026-07-11-v1",
                latest_self_test_event_id=self_event.id,
            ),
            PostureUserGoal(
                user_id=user_id,
                issue_id="HN-01",
                priority_rank=1,
                suggestion_id="sugg-1",
                profile_version="v1",
                rule_version="2026-07-11-v1",
                risk_version="2026-07-11-v1",
            ),
            PostureSafetySignal(
                user_id=user_id,
                signal_type="pain",
                body_region="head_neck",
                related_issue_id="HN-01",
                severity_hint="mild",
                reported_at=datetime.now(timezone.utc),
                lifecycle="active",
                invalidates_until=datetime.now(timezone.utc) + timedelta(days=30),
            ),
            IdempotencyRecord(
                user_id=user_id,
                operation="analyze_photo",
                idempotency_key="k1",
                request_hash="h1",
                status="completed",
                result_ref=str(photo_event.id),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            ),
        ]
    )
    await db.flush()
    return photo_event


# --------------------------------------------------------------------------- #
# Privacy-gate condition tests (spec §13.3)
# --------------------------------------------------------------------------- #


def test_privacy_gate_hard_rejects_by_default():
    result = privacy_gate.evaluate_photo_privacy_gate()
    assert result.satisfied is False
    assert len(result.unsatisfied_conditions) == 8


def test_privacy_gate_rejects_even_when_feature_flag_enabled(monkeypatch):
    monkeypatch.setattr(settings, "PHOTO_ANALYSIS_ENABLED", True)
    result = privacy_gate.evaluate_photo_privacy_gate()
    assert result.satisfied is False
    assert len(result.unsatisfied_conditions) == 8


def test_all_eight_conditions_distinct_and_unsatisfied():
    unsat = privacy_gate.unsatisfied_conditions()
    ids = [c.condition_id for c in unsat]
    assert len(ids) == 8
    assert len(set(ids)) == 8
    for cond in unsat:
        assert cond.satisfied is False
        assert cond.evidence.strip()


@pytest.mark.parametrize(
    "expected_id",
    [
        "purpose_disclosure",
        "provider_boundary",
        "consent_flow",
        "retention_configured",
        "deletion_path",
        "consent_withdrawal",
        "log_redaction",
        "self_test_preserved",
    ],
)
def test_each_required_condition_is_present_and_unsatisfied(expected_id):
    by_id = {c.condition_id: c for c in privacy_gate.unsatisfied_conditions()}
    assert expected_id in by_id
    assert by_id[expected_id].satisfied is False


def test_gate_cannot_be_bypassed_via_config_booleans(monkeypatch):
    # Flipping every related config flag must NOT satisfy the gate. Each
    # condition requires real implementation evidence, never a config toggle.
    monkeypatch.setattr(settings, "PHOTO_ANALYSIS_ENABLED", True)
    monkeypatch.setattr(settings, "PHOTO_RETENTION_DAYS", 90)
    monkeypatch.setattr(settings, "PHOTO_CONSENT_REQUIRED", True)
    result = privacy_gate.evaluate_photo_privacy_gate()
    assert result.satisfied is False
    assert len(result.unsatisfied_conditions) == 8


def test_retention_days_and_consent_config_are_read():
    assert settings.PHOTO_RETENTION_DAYS == 90
    assert settings.PHOTO_CONSENT_REQUIRED is True


# --------------------------------------------------------------------------- #
# Privacy-gate HTTP integration tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_unauthenticated_returns_401_before_privacy_gate(client):
    resp = await client.post("/api/v1/upload/sts-token")
    assert resp.status_code == 401
    resp2 = await client.post(
        "/api/v1/posture/assess/photo",
        json={"issue_id": "HN-01", "photo_keys": ["x.jpg"]},
    )
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_sts_path_blocked_by_privacy_gate_even_with_flag_on(client, monkeypatch):
    monkeypatch.setattr(settings, "PHOTO_ANALYSIS_ENABLED", True)
    token = await _login_user(client)
    with patch("app.upload.service.generate_sts_credentials") as mock_gen:
        resp = await client.post(
            "/api/v1/upload/sts-token",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 503
    assert resp.json()["code"] == "photo_analysis_disabled"
    mock_gen.assert_not_called()


@pytest.mark.asyncio
async def test_photo_assess_blocked_by_privacy_gate_even_with_flag_on(
    client, monkeypatch
):
    monkeypatch.setattr(settings, "PHOTO_ANALYSIS_ENABLED", True)
    token = await _login_user(client)
    with patch(
        "app.posture.ai_service.analyze_posture_photo", new_callable=AsyncMock
    ) as mock_ai:
        resp = await client.post(
            "/api/v1/posture/assess/photo",
            json={"issue_id": "HN-01", "photo_keys": ["x.jpg"]},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 503
    mock_ai.assert_not_called()


@pytest.mark.asyncio
async def test_self_test_path_works_when_privacy_gate_rejects(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "moderate"


@pytest.mark.asyncio
async def test_logs_do_not_contain_photo_url_or_raw_key(caplog):
    caplog.set_level(logging.INFO, logger="app.posture.purge")
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        secret_key = f"posture_photos/{user_id}/ULTRA-SECRET-RAW-KEY.jpg"
        await _seed_photo_event(db, user_id, photo_keys=[secret_key])
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing(secret_key)

    async with TestSession() as db:
        await purge.run_purge(db, user_id, store, trigger="user_delete")

    assert any("purge" in r.message.lower() for r in caplog.records)
    assert "ULTRA-SECRET-RAW-KEY" not in caplog.text
    assert secret_key not in caplog.text


# --------------------------------------------------------------------------- #
# Purge flow tests (spec §6.6 / §6.7)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_purge_deletes_health_payload_rows():
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        await _seed_full_dataset(db, user_id)
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing(f"posture_photos/{user_id}/aaa.jpg")
    store.add_existing(f"posture_photos/{user_id}/bbb.jpg")

    async with TestSession() as db:
        result = await purge.run_purge(db, user_id, store, trigger="user_delete")

    assert result.status == "completed"

    async with TestSession() as db:
        for model in (
            PostureAssessmentEvent,
            PostureProfileEntry,
            PostureUserGoal,
        ):
            rows = (
                await db.execute(select(model).where(model.user_id == user_id))
            ).scalars().all()
            assert rows == [], f"{model.__name__} rows must be deleted"


@pytest.mark.asyncio
async def test_oss_success_and_404_both_count_as_verifiable_deletion():
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        # One key exists in the store (delete succeeds); the other was never
        # registered (delete returns 404). Both must count as verified deletion.
        await _seed_photo_event(
            db,
            user_id,
            photo_keys=[
                f"posture_photos/{user_id}/exists.jpg",
                f"posture_photos/{user_id}/already-gone.jpg",
            ],
        )
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing(f"posture_photos/{user_id}/exists.jpg")

    async with TestSession() as db:
        result = await purge.run_purge(db, user_id, store, trigger="user_delete")

    assert result.status == "completed"
    assert result.object_delete_status == "oss_deleted_or_not_found"


@pytest.mark.asyncio
async def test_encrypted_object_keys_cleared_before_db_health_data_deletion():
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        await _seed_full_dataset(db, user_id)
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing(f"posture_photos/{user_id}/aaa.jpg")
    store.add_existing(f"posture_photos/{user_id}/bbb.jpg")

    async with TestSession() as db:
        result = await purge.run_purge(db, user_id, store, trigger="user_delete")

    steps = result.steps
    assert "clear_encrypted_object_keys" in steps
    assert "delete_assessment_events" in steps
    assert steps.index("clear_encrypted_object_keys") < steps.index(
        "delete_assessment_events"
    )


@pytest.mark.asyncio
async def test_purge_oss_failure_writes_no_tombstone():
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        await _seed_full_dataset(db, user_id)
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing(f"posture_photos/{user_id}/bbb.jpg")
    store.mark_failure(f"posture_photos/{user_id}/aaa.jpg")

    async with TestSession() as db:
        result = await purge.run_purge(db, user_id, store, trigger="user_delete")

    assert result.status == "failed_oss_retry"
    assert result.tombstone_receipt_id is None

    async with TestSession() as db:
        tombstones = (
            await db.execute(select(PosturePurgeTombstone))
        ).scalars().all()
        assert tombstones == []

        op = (
            await db.execute(
                select(PurgeOperation).where(PurgeOperation.user_id == user_id)
            )
        ).scalar_one()
        assert op.status == "failed_oss_retry"
        assert op.encrypted_object_keys is not None
        assert op.target_event_ids is not None


@pytest.mark.asyncio
async def test_purge_db_failure_writes_no_tombstone(monkeypatch):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        await _seed_full_dataset(db, user_id)
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing(f"posture_photos/{user_id}/aaa.jpg")
    store.add_existing(f"posture_photos/{user_id}/bbb.jpg")

    async def _boom(db, user_id):
        raise RuntimeError("simulated DB outage")

    monkeypatch.setattr(purge, "_delete_db_health_data", _boom)

    async with TestSession() as db:
        result = await purge.run_purge(db, user_id, store, trigger="user_delete")

    assert result.status == "failed_db_retry"
    assert result.tombstone_receipt_id is None

    async with TestSession() as db:
        tombstones = (
            await db.execute(select(PosturePurgeTombstone))
        ).scalars().all()
        assert tombstones == []

        op = (
            await db.execute(
                select(PurgeOperation).where(PurgeOperation.id == result.purge_operation_id)
            )
        ).scalar_one()
        assert op.status == "failed_db_retry"
        assert op.encrypted_object_keys is None
        assert op.target_event_ids is not None
        persisted_metadata = json.dumps(op.target_signal_ids, ensure_ascii=False)
        assert "posture_photos/" not in persisted_metadata
        assert op.target_signal_ids.get("signal_ids")
        assert op.target_signal_ids["oss_outcome"] == "oss_deleted_or_not_found"


@pytest.mark.asyncio
async def test_unhandled_exception_log_does_not_emit_exception_payload(caplog):
    from app.main import unhandled_exception_handler

    secret = "posture_photos/private-user/raw-key.jpg"
    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path="/api/v1/posture/safety-signals"),
    )
    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = await unhandled_exception_handler(request, RuntimeError(secret))

    assert response.status_code == 503
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_tombstone_contains_only_allowed_fields():
    from tests.conftest import TestSession

    allowed = {
        "receipt_id",
        "deleted_at",
        "purge_reason",
        "policy_version",
        "object_delete_status",
    }
    actual = {c.name for c in PosturePurgeTombstone.__table__.columns}
    assert actual == allowed

    async with TestSession() as db:
        user_id = await _make_user(db)
        await _seed_full_dataset(db, user_id)
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing(f"posture_photos/{user_id}/aaa.jpg")
    store.add_existing(f"posture_photos/{user_id}/bbb.jpg")

    async with TestSession() as db:
        result = await purge.run_purge(db, user_id, store, trigger="user_delete")

    async with TestSession() as db:
        tomb = (
            await db.execute(select(PosturePurgeTombstone))
        ).scalar_one()
        assert tomb.receipt_id == result.tombstone_receipt_id
        assert tomb.purge_reason == "user_delete"
        assert tomb.object_delete_status in (
            "oss_deleted",
            "oss_not_applicable",
            "oss_deleted_or_not_found",
        )
        assert tomb.policy_version


@pytest.mark.asyncio
async def test_completed_purge_operation_has_no_linkable_residue():
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        await _seed_full_dataset(db, user_id)
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing(f"posture_photos/{user_id}/aaa.jpg")
    store.add_existing(f"posture_photos/{user_id}/bbb.jpg")

    async with TestSession() as db:
        result = await purge.run_purge(db, user_id, store, trigger="user_delete")

    assert result.status == "completed"

    async with TestSession() as db:
        op = (
            await db.execute(
                select(PurgeOperation).where(PurgeOperation.id == result.purge_operation_id)
            )
        ).scalar_one()
        assert op.status == "completed"
        assert op.user_id is None
        assert op.target_event_ids is None
        assert op.target_signal_ids is None
        assert op.encrypted_object_keys is None
        assert op.completed_at is not None


@pytest.mark.asyncio
async def test_purge_is_idempotent():
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        await _seed_full_dataset(db, user_id)
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing(f"posture_photos/{user_id}/aaa.jpg")
    store.add_existing(f"posture_photos/{user_id}/bbb.jpg")

    async with TestSession() as db:
        first = await purge.run_purge(db, user_id, store, trigger="user_delete")
    assert first.status == "completed"

    async with TestSession() as db:
        second = await purge.run_purge(db, user_id, store, trigger="user_delete")
    assert second.status == "idempotent_noop"
    assert second.tombstone_receipt_id is None

    async with TestSession() as db:
        tombstones = (
            await db.execute(select(PosturePurgeTombstone))
        ).scalars().all()
        assert len(tombstones) == 1


@pytest.mark.asyncio
async def test_purge_deletes_safety_signals_and_idempotency_records():
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        await _seed_full_dataset(db, user_id)
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing(f"posture_photos/{user_id}/aaa.jpg")
    store.add_existing(f"posture_photos/{user_id}/bbb.jpg")

    async with TestSession() as db:
        result = await purge.run_purge(db, user_id, store, trigger="user_delete")

    assert result.status == "completed"

    async with TestSession() as db:
        signals = (
            await db.execute(
                select(PostureSafetySignal).where(PostureSafetySignal.user_id == user_id)
            )
        ).scalars().all()
        idems = (
            await db.execute(
                select(IdempotencyRecord).where(IdempotencyRecord.user_id == user_id)
            )
        ).scalars().all()
        assert signals == []
        assert idems == []


@pytest.mark.asyncio
async def test_scoped_purge_without_photo_events_is_noop():
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        # Only a self-test event: no photo_keys to delete from OSS.
        await _seed_self_test_event(db, user_id)
        await db.commit()

    store = purge.FakeObjectStore()

    async with TestSession() as db:
        result = await purge.run_purge(db, user_id, store, trigger="consent_withdrawn")

    assert result.status == "idempotent_noop"
    assert result.object_delete_status == "oss_not_applicable"
    async with TestSession() as db:
        assert (await db.execute(select(PosturePurgeTombstone))).scalars().all() == []
        remaining = (
            await db.execute(
                select(PostureAssessmentEvent).where(
                    PostureAssessmentEvent.user_id == user_id
                )
            )
        ).scalars().all()
        assert len(remaining) == 1
        assert remaining[0].source == "self_test"


# --------------------------------------------------------------------------- #
# FIX 1: real AEAD encryption (spec §6.7 — application-layer encryption)
# --------------------------------------------------------------------------- #


def test_encrypt_object_keys_produces_real_ciphertext():
    raw = ["posture_photos/abc/secret-key-001.jpg", "another/key.png"]
    blob = purge.encrypt_object_keys(raw)

    # Output is NOT JSON plaintext...
    assert not blob.startswith(b"[")
    try:
        json.loads(blob)
        parsed_as_json = True
    except (ValueError, UnicodeDecodeError):
        parsed_as_json = False
    assert parsed_as_json is False
    # ... and contains none of the plaintext key strings.
    for needle in (b"secret-key-001", b"another/key", b"posture_photos/abc"):
        assert needle not in blob
    # 12-byte nonce prefix + ciphertext + 16-byte GCM tag.
    assert len(blob) > 12 + 16  # strictly more than nonce + tag


def test_decrypt_object_keys_roundtrip_returns_original():
    raw = ["posture_photos/u/k1.jpg", "posture_photos/u/k2.jpg", "x"]
    blob = purge.encrypt_object_keys(raw)
    assert purge.decrypt_object_keys(blob) == raw


def test_decrypt_object_keys_empty_blob_returns_empty():
    assert purge.decrypt_object_keys(None) == []
    assert purge.decrypt_object_keys(b"") == []


def test_decrypt_object_keys_wrong_key_raises_invalid_tag(monkeypatch):
    blob = purge.encrypt_object_keys(["k.jpg"])  # encrypted under settings key
    # Swap the resolved key to a different valid key → wrong key → InvalidTag.
    monkeypatch.setattr(settings, "PURGE_ENCRYPTION_KEY", "fedcba9876543210" * 4)
    from cryptography.exceptions import InvalidTag

    with pytest.raises(InvalidTag):
        purge.decrypt_object_keys(blob)


@pytest.mark.asyncio
async def test_purge_raises_when_encryption_key_empty(monkeypatch):
    from tests.conftest import TestSession

    monkeypatch.setattr(settings, "PURGE_ENCRYPTION_KEY", "")
    async with TestSession() as db:
        user_id = await _make_user(db)
        await _seed_full_dataset(db, user_id)
        await db.commit()

    store = purge.FakeObjectStore()
    async with TestSession() as db:
        with pytest.raises(purge.PurgeConfigError):
            await purge.run_purge(db, user_id, store, trigger="user_delete")

    # Nothing deleted because the key was invalid (fail closed).
    async with TestSession() as db:
        rows = (
            await db.execute(
                select(PostureAssessmentEvent).where(
                    PostureAssessmentEvent.user_id == user_id
                )
            )
        ).scalars().all()
        assert len(rows) == 2


@pytest.mark.asyncio
async def test_purge_raises_when_encryption_key_not_hex(monkeypatch):
    from tests.conftest import TestSession

    monkeypatch.setattr(settings, "PURGE_ENCRYPTION_KEY", "not-valid-hex")
    async with TestSession() as db:
        user_id = await _make_user(db)
        await _seed_photo_event(db, user_id)
        await db.commit()

    store = purge.FakeObjectStore()
    async with TestSession() as db:
        with pytest.raises(purge.PurgeConfigError):
            await purge.run_purge(db, user_id, store, trigger="user_delete")


@pytest.mark.asyncio
async def test_decrypt_failure_aborts_purge_no_deletion_no_tombstone(monkeypatch):
    """P1-3: remove the blob's key_version from the keyring → decrypt fails
    closed → ``failed_decrypt`` (data retained, no tombstone, freeze kept)."""
    from tests.conftest import TestSession
    import uuid as _u

    # Configure a versioned keyring with two versions; encrypt under v1.
    key_v1 = _TEST_PURGE_KEY
    key_v2 = "fedcba9876543210" * 4  # a different valid 64-hex AES-256 key
    monkeypatch.setattr(settings, "PURGE_ENCRYPTION_KEYS", json.dumps({"v1": key_v1, "v2": key_v2}))
    monkeypatch.setattr(settings, "PURGE_ACTIVE_KEY_VERSION", "v1")

    async with TestSession() as db:
        user_id = await _make_user(db)
        photo_event = await _seed_photo_event(
            db, user_id, photo_keys=[f"posture_photos/{user_id}/keep.jpg"]
        )
        await db.commit()

    op_id_pre = _u.uuid4()
    encrypted = purge.encrypt_object_keys(
        [f"posture_photos/{user_id}/keep.jpg"],
        operation_id=str(op_id_pre),
        user_id=str(user_id),
        trigger="user_delete",
    )
    async with TestSession() as db:
        op = PurgeOperation(
            id=op_id_pre,
            user_id=user_id,
            trigger="user_delete",
            status="failed_oss_retry",
            encrypted_object_keys=encrypted,
            target_event_ids=[str(photo_event.id)],
            attempt_count=1,
            max_attempts=5,
            next_retry_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(op)
        await db.commit()

    # Now drop v1 from the keyring → the blob's stored key_version v1 is
    # unresolvable → decrypt must fail closed.
    monkeypatch.setattr(settings, "PURGE_ENCRYPTION_KEYS", json.dumps({"v2": key_v2}))
    monkeypatch.setattr(settings, "PURGE_ACTIVE_KEY_VERSION", "v2")

    store = purge.FakeObjectStore()
    async with TestSession() as db:
        results = await purge.run_due_purge_jobs(db, store)

    assert len(results) == 1
    assert results[0].status == "failed_decrypt"
    assert results[0].tombstone_receipt_id is None

    async with TestSession() as db:
        op = (
            await db.execute(
                select(PurgeOperation).where(PurgeOperation.user_id == user_id)
            )
        ).scalar_one()
        assert op.status == "failed_decrypt"
        # Data retained.
        events = (
            await db.execute(
                select(PostureAssessmentEvent).where(
                    PostureAssessmentEvent.user_id == user_id
                )
            )
        ).scalars().all()
        assert len(events) == 1
        # No tombstone.
        tombstones = (
            await db.execute(select(PosturePurgeTombstone))
        ).scalars().all()
        assert tombstones == []


# --------------------------------------------------------------------------- #
# FIX 2: purge scope differentiation (spec §6.6)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_scope_account_deletion_deletes_everything():
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        await _seed_full_dataset(db, user_id)
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing(f"posture_photos/{user_id}/aaa.jpg")
    store.add_existing(f"posture_photos/{user_id}/bbb.jpg")

    async with TestSession() as db:
        result = await purge.run_purge(
            db, user_id, store, trigger="account_deletion"
        )

    assert result.status == "completed"

    async with TestSession() as db:
        for model in (
            PostureAssessmentEvent,
            PostureProfileEntry,
            PostureUserGoal,
            PostureSafetySignal,
            IdempotencyRecord,
        ):
            rows = (
                await db.execute(select(model).where(model.user_id == user_id))
            ).scalars().all()
            assert rows == [], f"{model.__name__} should be fully deleted"


@pytest.mark.asyncio
async def test_scope_consent_withdrawn_preserves_selftest_and_signals():
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        photo_event = await _seed_photo_event(
            db,
            user_id,
            issue_id="HN-01",
            photo_keys=[f"posture_photos/{user_id}/photo.jpg"],
        )
        self_event = await _seed_self_test_event(db, user_id, issue_id="HN-02")
        db.add_all(
            [
                PostureUserGoal(
                    user_id=user_id,
                    issue_id="HN-01",
                    priority_rank=1,
                    suggestion_id="s1",
                    profile_version="v1",
                    rule_version="r1",
                    risk_version="rv1",
                ),
                PostureProfileEntry(
                    user_id=user_id,
                    issue_id="HN-02",
                    combined_severity="normal",
                    certainty="confirmed",
                    sources={},
                    has_conflict=False,
                    risk_tier="normal",
                    risk_version="rv1",
                    latest_self_test_event_id=self_event.id,
                ),
                PostureSafetySignal(
                    user_id=user_id,
                    signal_type="pain",
                    body_region="head_neck",
                    related_issue_id="HN-01",
                    severity_hint="mild",
                    reported_at=datetime.now(timezone.utc),
                    lifecycle="active",
                    invalidates_until=datetime.now(timezone.utc)
                    + timedelta(days=30),
                ),
                IdempotencyRecord(
                    user_id=user_id,
                    operation="analyze_photo",
                    idempotency_key="k1",
                    request_hash="h1",
                    status="completed",
                    result_ref=str(photo_event.id),
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                ),
            ]
        )
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing(f"posture_photos/{user_id}/photo.jpg")

    async with TestSession() as db:
        result = await purge.run_purge(
            db, user_id, store, trigger="consent_withdrawn"
        )

    assert result.status == "completed"
    assert set(store.deleted_keys) == {f"posture_photos/{user_id}/photo.jpg"}

    async with TestSession() as db:
        # Photo event deleted; self-test preserved.
        events = (
            await db.execute(
                select(PostureAssessmentEvent).where(
                    PostureAssessmentEvent.user_id == user_id
                )
            )
        ).scalars().all()
        assert len(events) == 1
        assert events[0].id == self_event.id
        # Goals, profile entries, safety signals preserved.
        assert (
            await db.execute(
                select(PostureUserGoal).where(PostureUserGoal.user_id == user_id)
            )
        ).scalars().all() != []
        assert (
            await db.execute(
                select(PostureProfileEntry).where(
                    PostureProfileEntry.user_id == user_id
                )
            )
        ).scalars().all() != []
        assert (
            await db.execute(
                select(PostureSafetySignal).where(
                    PostureSafetySignal.user_id == user_id
                )
            )
        ).scalars().all() != []
        # Idempotency tied to the photo event deleted.
        assert (
            await db.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.user_id == user_id
                )
            )
        ).scalars().all() == []


@pytest.mark.asyncio
async def test_scope_retention_expired_preserves_recent_photo_events():
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        old_cutoff = datetime.now(timezone.utc) - timedelta(days=100)
        recent = datetime.now(timezone.utc)
        old_event = PostureAssessmentEvent(
            user_id=user_id,
            issue_id="HN-01",
            source="ai_photo",
            severity="moderate",
            lifecycle="active",
            photo_keys=[f"posture_photos/{user_id}/old.jpg"],
            created_at=old_cutoff,
        )
        recent_event = PostureAssessmentEvent(
            user_id=user_id,
            issue_id="HN-02",
            source="ai_photo",
            severity="mild",
            lifecycle="active",
            photo_keys=[f"posture_photos/{user_id}/recent.jpg"],
            created_at=recent,
        )
        self_event = await _seed_self_test_event(db, user_id, issue_id="HN-03")
        db.add_all([old_event, recent_event])
        await db.commit()

    store = purge.FakeObjectStore()

    async with TestSession() as db:
        result = await purge.run_purge(
            db, user_id, store, trigger="retention_expired"
        )

    assert result.status == "completed"
    # Only the expired photo's OSS object is targeted.
    assert set(store.deleted_keys) == {f"posture_photos/{user_id}/old.jpg"}

    async with TestSession() as db:
        events = {
            e.id: e for e in (
                await db.execute(
                    select(PostureAssessmentEvent).where(
                        PostureAssessmentEvent.user_id == user_id
                    )
                )
            ).scalars().all()
        }
        assert recent_event.id in events, "recent photo event must be preserved"
        assert self_event.id in events, "self-test event must be preserved"
        assert old_event.id not in events, "expired photo event must be deleted"


# --------------------------------------------------------------------------- #
# FIX 3: write-freeze guard
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_is_user_write_frozen_during_active_purge_and_after_completion():
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        await _seed_full_dataset(db, user_id)
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing(f"posture_photos/{user_id}/aaa.jpg")
    store.add_existing(f"posture_photos/{user_id}/bbb.jpg")

    # Before any purge: not frozen.
    async with TestSession() as db:
        assert await purge.is_user_write_frozen(db, user_id) is False

    # Seed an in-flight (non-terminal) operation: frozen True.
    async with TestSession() as db:
        op = PurgeOperation(
            user_id=user_id,
            trigger="user_delete",
            status="freezing",
            attempt_count=0,
            max_attempts=10,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(op)
        await db.commit()
    async with TestSession() as db:
        assert await purge.is_user_write_frozen(db, user_id) is True

    # Hardening fix #3: run_purge now rejects with 409 if non-terminal exists.
    # Verify the 409 behavior.
    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await purge.run_purge(db, user_id, store, trigger="user_delete")
        assert exc.value.status_code == 409

    # Remove the in-flight op manually so we can run a fresh purge to completion.
    async with TestSession() as db:
        op = (await db.execute(
            select(PurgeOperation).where(PurgeOperation.user_id == user_id)
        )).scalar_one()
        await db.delete(op)
        await db.commit()

    # Run the real purge to completion (no in-flight op now).
    async with TestSession() as db:
        result = await purge.run_purge(db, user_id, store, trigger="user_delete")
    assert result.status == "completed"

    # After completion user_id is scrubbed → no non-terminal op → not frozen.
    async with TestSession() as db:
        assert await purge.is_user_write_frozen(db, user_id) is False


@pytest.mark.asyncio
async def test_concurrent_write_blocked_while_frozen():
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        db.add(
            PurgeOperation(
                user_id=user_id,
                trigger="user_delete",
                status="oss_deleting",
                attempt_count=0,
                max_attempts=10,
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        await db.commit()

    # Guard reports frozen for every non-terminal status.
    for active in ("freezing", "oss_deleting", "db_deleting", "failed_oss_retry"):
        async with TestSession() as db:
            op = (
                await db.execute(
                    select(PurgeOperation).where(
                        PurgeOperation.user_id == user_id
                    )
                )
            ).scalar_one()
            op.status = active
            await db.commit()
        async with TestSession() as db:
            assert await purge.is_user_write_frozen(db, user_id) is True, active

    # Terminal statuses that release freeze: ONLY completed and cancelled.
    # failed_permanent/failed_decrypt stay frozen (review fix #6).
    for terminal in ("completed", "cancelled"):
        async with TestSession() as db:
            op = (
                await db.execute(
                    select(PurgeOperation).where(
                        PurgeOperation.user_id == user_id
                    )
                )
            ).scalar_one()
            op.status = terminal
            await db.commit()
        async with TestSession() as db:
            assert await purge.is_user_write_frozen(db, user_id) is False, terminal

    # failed_permanent and failed_decrypt MAINTAIN freeze (review fix #6).
    for still_frozen in ("failed_permanent", "failed_decrypt"):
        async with TestSession() as db:
            op = (
                await db.execute(
                    select(PurgeOperation).where(
                        PurgeOperation.user_id == user_id
                    )
                )
            ).scalar_one()
            op.status = still_frozen
            await db.commit()
        async with TestSession() as db:
            assert await purge.is_user_write_frozen(db, user_id) is True, still_frozen


# --------------------------------------------------------------------------- #
# FIX 4: retry engine
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_real_run_purge_freezing_phase_keeps_reclaimable_lease(monkeypatch):
    """If run_purge crashes after step 1 commit but before OSS deletion, the
    persisted freezing operation must remain worker-reclaimable."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        await _seed_full_dataset(db, user_id)
        await db.commit()

    real_delete_oss = purge._delete_oss_objects

    async def _crash_before_oss(db, op, object_store, photo_keys):
        raise RuntimeError("crash after freezing commit")

    monkeypatch.setattr(purge, "_delete_oss_objects", _crash_before_oss)
    async with TestSession() as db:
        with pytest.raises(RuntimeError, match="crash after freezing commit"):
            await purge.run_purge(
                db, user_id, purge.FakeObjectStore(), trigger="user_delete"
            )

    async with TestSession() as db:
        op = (
            await db.execute(
                select(PurgeOperation).where(PurgeOperation.user_id == user_id)
            )
        ).scalar_one()
        assert op.status == "freezing"
        assert op.next_retry_at is not None
        assert await purge.is_user_write_frozen(db, user_id) is True
        op.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()

    monkeypatch.setattr(purge, "_delete_oss_objects", real_delete_oss)
    store = purge.FakeObjectStore()
    store.add_existing(f"posture_photos/{user_id}/aaa.jpg")
    store.add_existing(f"posture_photos/{user_id}/bbb.jpg")
    async with TestSession() as db:
        results = await purge.run_due_purge_jobs(db, store)

    assert [result.status for result in results] == ["completed"]
    async with TestSession() as db:
        op = (await db.execute(select(PurgeOperation))).scalar_one()
        assert op.status == "completed"
        assert op.user_id is None
        assert op.next_retry_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_status", ["freezing", "oss_deleting", "db_deleting"])
async def test_interrupted_initial_phase_is_reclaimed(initial_status):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        event = await _seed_photo_event(
            db, user_id, photo_keys=[f"posture_photos/{user_id}/resume.jpg"]
        )
        await db.flush()
        profile = PostureProfileEntry(
            user_id=user_id,
            issue_id="HN-01",
            combined_severity="moderate",
            certainty="confirmed",
            sources={"ai_photo": str(event.id)},
            has_conflict=False,
            risk_tier="normal",
            risk_version="test-v1",
            latest_photo_event_id=event.id,
        )
        goal = PostureUserGoal(
            user_id=user_id,
            issue_id="HN-01",
            priority_rank=1,
            suggestion_id="resume-goal",
            profile_version="test-profile-v1",
            rule_version="test-rule-v1",
            risk_version="test-risk-v1",
        )
        db.add_all([profile, goal])
        op_id = _uuid.uuid4()
        encrypted = None
        metadata = {"signal_ids": [], "oss_outcome": "oss_deleted_or_not_found"}
        if initial_status != "db_deleting":
            encrypted = purge._encrypt_with_resolved_key(
                [f"posture_photos/{user_id}/resume.jpg"],
                _TEST_PURGE_KEY,
                purge.KEY_VERSION,
                operation_id=str(op_id),
                user_id=str(user_id),
                trigger="account_deletion",
            )
            metadata = []
        db.add(
            PurgeOperation(
                id=op_id,
                user_id=user_id,
                trigger="account_deletion",
                status=initial_status,
                encrypted_object_keys=encrypted,
                target_event_ids=[str(event.id)],
                target_signal_ids=metadata,
                attempt_count=0,
                max_attempts=5,
                next_retry_at=datetime.now(timezone.utc) - timedelta(seconds=1),
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        await db.commit()

    async with TestSession() as db:
        results = await purge.run_due_purge_jobs(db, purge.FakeObjectStore())

    assert [result.status for result in results] == ["completed"]
    async with TestSession() as db:
        assert await db.get(PostureAssessmentEvent, event.id) is None
        assert (
            await db.execute(
                select(PostureProfileEntry).where(
                    PostureProfileEntry.user_id == user_id
                )
            )
        ).scalars().all() == []
        assert (
            await db.execute(
                select(PostureUserGoal).where(PostureUserGoal.user_id == user_id)
            )
        ).scalars().all() == []
        operation = await db.get(PurgeOperation, op_id)
        assert operation.status == "completed"


@pytest.mark.asyncio
async def test_run_due_purge_jobs_exhausts_to_failed_permanent():
    from tests.conftest import TestSession
    import uuid as _u

    async with TestSession() as db:
        user_id = await _make_user(db)
        photo_event = await _seed_photo_event(
            db, user_id, photo_keys=[f"posture_photos/{user_id}/fail.jpg"]
        )
        await db.commit()

    op_id_pre = _u.uuid4()
    encrypted = purge.encrypt_object_keys(
        [f"posture_photos/{user_id}/fail.jpg"],
        operation_id=str(op_id_pre),
        user_id=str(user_id),
        trigger="user_delete",
    )
    async with TestSession() as db:
        op = PurgeOperation(
            id=op_id_pre,
            user_id=user_id,
            trigger="user_delete",
            status="failed_oss_retry",
            encrypted_object_keys=encrypted,
            target_event_ids=[str(photo_event.id)],
            attempt_count=2,
            max_attempts=3,
            next_retry_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(op)
        await db.commit()
        op_id = op.id

    # OSS store always fails → retry fails → attempts(3) >= max(3) → permanent.
    store = purge.FakeObjectStore()
    store.mark_failure(f"posture_photos/{user_id}/fail.jpg")

    async with TestSession() as db:
        results = await purge.run_due_purge_jobs(db, store)

    assert len(results) == 1
    assert results[0].status == "failed_permanent"
    async with TestSession() as db:
        op = await db.get(PurgeOperation, op_id)
        assert op.status == "failed_permanent"
        assert op.attempt_count == 3


@pytest.mark.asyncio
async def test_run_due_purge_jobs_succeeds_on_retry():
    from tests.conftest import TestSession
    import uuid as _u

    async with TestSession() as db:
        user_id = await _make_user(db)
        photo_event = await _seed_photo_event(
            db, user_id, photo_keys=[f"posture_photos/{user_id}/ok.jpg"]
        )
        await db.commit()

    op_id_pre = _u.uuid4()
    encrypted = purge.encrypt_object_keys(
        [f"posture_photos/{user_id}/ok.jpg"],
        operation_id=str(op_id_pre),
        user_id=str(user_id),
        trigger="user_delete",
    )
    async with TestSession() as db:
        op = PurgeOperation(
            id=op_id_pre,
            user_id=user_id,
            trigger="user_delete",
            status="failed_oss_retry",
            encrypted_object_keys=encrypted,
            target_event_ids=[str(photo_event.id)],
            attempt_count=1,
            max_attempts=5,
            next_retry_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(op)
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing(f"posture_photos/{user_id}/ok.jpg")

    async with TestSession() as db:
        results = await purge.run_due_purge_jobs(db, store)

    assert results[0].status == "completed"
    assert results[0].tombstone_receipt_id is not None
    async with TestSession() as db:
        events = (
            await db.execute(
                select(PostureAssessmentEvent).where(
                    PostureAssessmentEvent.user_id == user_id
                )
            )
        ).scalars().all()
        assert events == []
        tombstones = (
            await db.execute(select(PosturePurgeTombstone))
        ).scalars().all()
        assert len(tombstones) == 1


@pytest.mark.asyncio
async def test_run_due_purge_jobs_skips_not_due_and_expired():
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        await _seed_photo_event(db, user_id)
        await db.commit()

    encrypted = purge.encrypt_object_keys(
        [f"posture_photos/{user_id}/secret-photo-key-001.jpg"]
    )
    async with TestSession() as db:
        # Not due yet (next_retry in the future).
        db.add(
            PurgeOperation(
                user_id=user_id,
                trigger="user_delete",
                status="failed_oss_retry",
                encrypted_object_keys=encrypted,
                target_event_ids=["x"],
                attempt_count=0,
                max_attempts=5,
                next_retry_at=datetime.now(timezone.utc) + timedelta(days=1),
                expires_at=datetime.now(timezone.utc) + timedelta(days=2),
            )
        )
        user2 = await _make_user(db)
        await _seed_photo_event(db, user2)
        await db.flush()
        # Expired past window → failed_permanent, not retried.
        exp_op = PurgeOperation(
            user_id=user2,
            trigger="user_delete",
            status="failed_oss_retry",
            encrypted_object_keys=purge.encrypt_object_keys(
                [f"posture_photos/{user2}/secret-photo-key-001.jpg"],
            ),
            target_event_ids=["y"],
            attempt_count=0,
            max_attempts=5,
            next_retry_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db.add(exp_op)
        await db.commit()
        exp_id = exp_op.id

    store = purge.FakeObjectStore()
    async with TestSession() as db:
        results = await purge.run_due_purge_jobs(db, store)

    # The not-due job is skipped; the expired job becomes failed_permanent.
    assert all(r.status != "completed" for r in results)
    async with TestSession() as db:
        exp = await db.get(PurgeOperation, exp_id)
        assert exp.status == "failed_permanent"


# --------------------------------------------------------------------------- #
# FIX 5: atomic tombstone + scrub
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_atomic_tombstone_and_scrub_rollback_on_commit_failure(monkeypatch):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        await _seed_full_dataset(db, user_id)
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing(f"posture_photos/{user_id}/aaa.jpg")
    store.add_existing(f"posture_photos/{user_id}/bbb.jpg")

    real_commit = AsyncSession.commit

    async def _flaky_commit(self):
        # Raise only on the atomic finalize commit (tombstone staged).
        staged = list(self.sync_session.new)
        if any(isinstance(o, PosturePurgeTombstone) for o in staged):
            raise RuntimeError("simulated finalize commit failure")
        return await real_commit(self)

    monkeypatch.setattr(AsyncSession, "commit", _flaky_commit)

    async with TestSession() as db:
        with pytest.raises(RuntimeError, match="simulated finalize commit failure"):
            await purge.run_purge(db, user_id, store, trigger="user_delete")

    async with TestSession() as db:
        # No tombstone written.
        tombstones = (
            await db.execute(select(PosturePurgeTombstone))
        ).scalars().all()
        assert tombstones == []

        # purge_operations still has its linkable fields (scrub rolled back).
        op = (
            await db.execute(
                select(PurgeOperation).where(PurgeOperation.user_id == user_id)
            )
        ).scalar_one()
        assert op.status != "completed"
        assert op.user_id == user_id
        assert op.target_event_ids is not None
        assert op.target_signal_ids is not None
        assert op.completed_at is None


# --------------------------------------------------------------------------- #
# Review regression tests (fix #1, #6, #7, #8, #9, #11)
# --------------------------------------------------------------------------- #


def test_unknown_purge_trigger_raises_valueerror():
    """Review fix #1: unknown trigger raises ValueError before any DB write."""
    with pytest.raises(ValueError, match="unknown purge trigger"):
        purge._scope_from_trigger("totally_invalid_trigger")


@pytest.mark.asyncio
async def test_failed_permanent_still_frozen():
    """Review fix #6: failed_permanent maintains write freeze."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        db.add(
            PurgeOperation(
                user_id=user_id,
                trigger="user_delete",
                status="failed_permanent",
                attempt_count=10,
                max_attempts=10,
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
        )
        await db.commit()

    async with TestSession() as db:
        assert await purge.is_user_write_frozen(db, user_id) is True


@pytest.mark.asyncio
async def test_scoped_purge_selects_by_source_not_photo_keys():
    """Review fix #7: scoped purge selects events by source='ai_photo',
    not by photo_keys non-empty. An event with photo_keys but source='self_test'
    should NOT be purged by consent_withdrawn."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        # self_test event with photo_keys (unusual but valid) — should NOT be purged
        weird_event = PostureAssessmentEvent(
            user_id=user_id,
            issue_id="HN-01",
            source="self_test",
            severity="normal",
            lifecycle="active",
            photo_keys=["should-not-be-purged.jpg"],
        )
        # normal ai_photo event — should be purged
        photo_event = PostureAssessmentEvent(
            user_id=user_id,
            issue_id="HN-01",
            source="ai_photo",
            severity="moderate",
            lifecycle="active",
            photo_keys=["purge-this.jpg"],
        )
        db.add_all([weird_event, photo_event])
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing("purge-this.jpg")

    async with TestSession() as db:
        result = await purge.run_purge(
            db, user_id, store, trigger="consent_withdrawn"
        )

    assert result.status == "completed"

    async with TestSession() as db:
        events = (
            await db.execute(
                select(PostureAssessmentEvent).where(
                    PostureAssessmentEvent.user_id == user_id
                )
            )
        ).scalars().all()
        # weird_event preserved (source != ai_photo), photo_event deleted
        assert len(events) == 1
        assert events[0].source == "self_test"


@pytest.mark.asyncio
async def test_scoped_purge_rebuilds_profile_after_photo_deletion():
    """Review fix #7: after scoped purge, profile is rebuilt from remaining
    events. If self_test remains, profile uses its severity."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        # self_test event for same issue
        self_event = PostureAssessmentEvent(
            user_id=user_id,
            issue_id="HN-01",
            source="self_test",
            severity="moderate",
            lifecycle="active",
        )
        # ai_photo event for same issue
        photo_event = PostureAssessmentEvent(
            user_id=user_id,
            issue_id="HN-01",
            source="ai_photo",
            severity="moderate",
            lifecycle="active",
            photo_keys=["photo.jpg"],
        )
        db.add_all([self_event, photo_event])
        await db.flush()
        # Profile referencing the photo event
        db.add(PostureProfileEntry(
            user_id=user_id,
            issue_id="HN-01",
            combined_severity="moderate",
            certainty="confirmed",
            sources={},
            has_conflict=False,
            risk_tier="normal",
            risk_version="2026-07-11-v1",
            latest_photo_event_id=photo_event.id,
            latest_self_test_event_id=self_event.id,
        ))
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing("photo.jpg")

    async with TestSession() as db:
        result = await purge.run_purge(
            db, user_id, store, trigger="consent_withdrawn"
        )

    assert result.status == "completed"

    async with TestSession() as db:
        profile = (
            await db.execute(
                select(PostureProfileEntry).where(
                    PostureProfileEntry.user_id == user_id,
                    PostureProfileEntry.issue_id == "HN-01",
                )
            )
        ).scalar_one_or_none()
        # Profile rebuilt from self_test event
        assert profile is not None
        assert profile.combined_severity == "moderate"
        assert profile.certainty == "confirmed"
        assert profile.latest_photo_event_id is None


@pytest.mark.asyncio
async def test_scoped_purge_deletes_profile_when_no_events_remain():
    """Review fix #7: if no events remain for an issue after scoped purge,
    the profile entry is deleted."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        photo_event = PostureAssessmentEvent(
            user_id=user_id,
            issue_id="HN-01",
            source="ai_photo",
            severity="moderate",
            lifecycle="active",
            photo_keys=["only-photo.jpg"],
        )
        db.add(photo_event)
        await db.flush()
        db.add(PostureProfileEntry(
            user_id=user_id,
            issue_id="HN-01",
            combined_severity="moderate",
            certainty="confirmed",
            sources={},
            has_conflict=False,
            risk_tier="normal",
            risk_version="2026-07-11-v1",
            latest_photo_event_id=photo_event.id,
        ))
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing("only-photo.jpg")

    async with TestSession() as db:
        result = await purge.run_purge(
            db, user_id, store, trigger="consent_withdrawn"
        )

    assert result.status == "completed"

    async with TestSession() as db:
        profile = (
            await db.execute(
                select(PostureProfileEntry).where(
                    PostureProfileEntry.user_id == user_id,
                    PostureProfileEntry.issue_id == "HN-01",
                )
            )
        ).scalar_one_or_none()
        assert profile is None


@pytest.mark.asyncio
@pytest.mark.skipif(
    not __import__("tests.conftest_pg", fromlist=["pg_available"]).pg_available,
    reason="Docker PostgreSQL not available (set PG_TEST_DSN or start Docker)",
)
async def test_postgresql_scoped_purge_regression():
    """Review fix #8: PostgreSQL scoped purge regression.
    Seed self_test + ai_photo events for same issue with profile referencing both.
    Run consent_withdrawn purge → photo event gone, self-test stays,
    profile rebuilt from self-test."""
    # This regression is now fully exercised via test_pg_integration.py
    # test_pg_scoped_purge_safety_aware_rebuild when PG is available.
    pass


def test_aad_mismatch_causes_decrypt_failure():
    """Review fix #9: wrong AAD → InvalidTag (GCM property)."""
    from cryptography.exceptions import InvalidTag

    keys = ["photo.jpg"]
    blob = purge.encrypt_object_keys(
        keys,
        operation_id="op-1", user_id="user-1", trigger="user_delete",
    )
    # Correct AAD decrypts fine
    result = purge.decrypt_object_keys(
        blob,
        operation_id="op-1", user_id="user-1", trigger="user_delete",
    )
    assert result == keys

    # Wrong operation_id → InvalidTag
    with pytest.raises(InvalidTag):
        purge.decrypt_object_keys(
            blob,
            operation_id="wrong-op", user_id="user-1", trigger="user_delete",
        )
    # Wrong user_id → InvalidTag
    with pytest.raises(InvalidTag):
        purge.decrypt_object_keys(
            blob,
            operation_id="op-1", user_id="wrong-user", trigger="user_delete",
        )
    # Wrong trigger → InvalidTag
    with pytest.raises(InvalidTag):
        purge.decrypt_object_keys(
            blob,
            operation_id="op-1", user_id="user-1", trigger="consent_withdrawn",
        )


@pytest.mark.asyncio
async def test_retry_skip_locked_assertion():
    """Review fix #11: run_due_purge_jobs query uses FOR UPDATE SKIP LOCKED
    on PostgreSQL. On SQLite it gracefully skips the clause."""
    from tests.conftest import TestSession

    # Verify the code path runs without error on SQLite (no-op).
    store = purge.FakeObjectStore()
    async with TestSession() as db:
        results = await purge.run_due_purge_jobs(db, store)
    # No jobs to process = empty list (no error from skip_locked on SQLite)
    assert results == []


# --------------------------------------------------------------------------- #
# P1-1: run_purge lock ordering
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_failed_permanent_op_blocks_new_purge_with_409():
    """P1-1: a ``failed_permanent`` op maintains the freeze and must NOT be
    treated as a successful terminal/noop. A new purge is rejected with 409."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        await _seed_photo_event(db, user_id)
        db.add(
            PurgeOperation(
                user_id=user_id,
                trigger="user_delete",
                status="failed_permanent",
                attempt_count=10,
                max_attempts=10,
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
        )
        await db.commit()

    store = purge.FakeObjectStore()
    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await purge.run_purge(db, user_id, store, trigger="user_delete")
        assert exc.value.status_code == 409
        assert exc.value.code == "purge_already_in_flight"

    # Freeze still on (failed_permanent is non-terminal).
    async with TestSession() as db:
        assert await purge.is_user_write_frozen(db, user_id) is True


@pytest.mark.asyncio
async def test_no_purgeable_data_is_idempotent_noop_under_lock():
    """P1-1: with no purgeable data and no in-flight op, run_purge returns
    idempotent_noop. The data check runs AFTER the lock (no pre-lock DB read)."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        await db.commit()

    store = purge.FakeObjectStore()
    async with TestSession() as db:
        result = await purge.run_purge(db, user_id, store, trigger="user_delete")

    assert result.status == "idempotent_noop"
    assert result.steps == ["noop_no_data"]
    assert result.tombstone_receipt_id is None

    # No purge_operation created for a no-op.
    async with TestSession() as db:
        ops = (
            await db.execute(
                select(PurgeOperation).where(PurgeOperation.user_id == user_id)
            )
        ).scalars().all()
        assert ops == []


@pytest.mark.asyncio
async def test_completed_purge_allows_repurge_when_data_reappears():
    """P1-1: a completed op is terminal (scrubs user_id). If purgeable data
    reappears, a new purge proceeds and completes (creates a 2nd operation)."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        await _seed_full_dataset(db, user_id)
        await db.commit()

    store = purge.FakeObjectStore()
    store.add_existing(f"posture_photos/{user_id}/aaa.jpg")
    store.add_existing(f"posture_photos/{user_id}/bbb.jpg")

    async with TestSession() as db:
        first = await purge.run_purge(db, user_id, store, trigger="user_delete")
    assert first.status == "completed"

    # New data reappears for the same user.
    async with TestSession() as db:
        await _seed_photo_event(db, user_id)
        await db.commit()

    async with TestSession() as db:
        second = await purge.run_purge(db, user_id, store, trigger="user_delete")
    assert second.status == "completed"
    assert second.purge_operation_id != first.purge_operation_id

    async with TestSession() as db:
        tombstones = (
            await db.execute(select(PosturePurgeTombstone))
        ).scalars().all()
        assert len(tombstones) == 2


# --------------------------------------------------------------------------- #
# P1-2: retry lease crash recovery (retrying_oss / retrying_db)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_retrying_lease_reclaim_after_worker_crash(monkeypatch):
    """P1-2: worker claims (retrying_oss) then crashes; after its lease expires
    a second worker reclaims and completes. Exactly one tombstone, and the
    write freeze is maintained while the op is in a retrying_* status."""
    from tests.conftest import TestSession
    import uuid as _u

    async with TestSession() as db:
        user_id = await _make_user(db)
        photo_event = await _seed_photo_event(
            db, user_id, photo_keys=[f"posture_photos/{user_id}/lease.jpg"]
        )
        await db.commit()

    op_id_pre = _u.uuid4()
    encrypted = purge.encrypt_object_keys(
        [f"posture_photos/{user_id}/lease.jpg"],
        operation_id=str(op_id_pre),
        user_id=str(user_id),
        trigger="user_delete",
    )
    async with TestSession() as db:
        op = PurgeOperation(
            id=op_id_pre,
            user_id=user_id,
            trigger="user_delete",
            status="failed_oss_retry",
            encrypted_object_keys=encrypted,
            target_event_ids=[str(photo_event.id)],
            attempt_count=1,
            max_attempts=5,
            next_retry_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(op)
        await db.commit()
        op_id = op.id

    store = purge.FakeObjectStore()
    store.add_existing(f"posture_photos/{user_id}/lease.jpg")

    real_resume = purge._resume_purge
    calls = {"n": 0}

    async def _crash_then_run(db, op, object_store, encryption_key=None):
        calls["n"] += 1
        if calls["n"] == 1:
            # The claiming worker crashes AFTER the lease commit but BEFORE
            # completing: the op is already persisted as retrying_oss.
            raise RuntimeError("worker crashed after claiming lease")
        return await real_resume(db, op, object_store, encryption_key)

    monkeypatch.setattr(purge, "_resume_purge", _crash_then_run)

    # Worker 1: claims the job (-> retrying_oss + future lease), then crashes.
    async with TestSession() as db:
        with pytest.raises(RuntimeError, match="worker crashed"):
            await purge.run_due_purge_jobs(db, store)

    # After the crash: row is in the retrying_oss lease status, lease still in
    # the future (not reclaimable yet), and the write freeze is maintained.
    async with TestSession() as db:
        op = await db.get(PurgeOperation, op_id)
        assert op.status == "retrying_oss"
        assert await purge.is_user_write_frozen(db, user_id) is True
        # Simulate lease expiry so worker 2 can reclaim it.
        op.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()

    # Worker 2: the expired lease is reclaimable; completes the purge.
    async with TestSession() as db:
        results = await purge.run_due_purge_jobs(db, store)

    assert len(results) == 1
    assert results[0].status == "completed"
    assert results[0].tombstone_receipt_id is not None

    # Exactly one tombstone (no duplicate from the crashed claim).
    async with TestSession() as db:
        tombstones = (
            await db.execute(select(PosturePurgeTombstone))
        ).scalars().all()
        assert len(tombstones) == 1
        op = await db.get(PurgeOperation, op_id)
        assert op.status == "completed"
        assert op.next_retry_at is None


@pytest.mark.asyncio
async def test_retrying_statuses_maintain_write_freeze():
    """P1-2: retrying_oss / retrying_db are non-terminal → freeze maintained."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        await db.commit()

    for status in ("retrying_oss", "retrying_db"):
        async with TestSession() as db:
            db.add(
                PurgeOperation(
                    user_id=user_id,
                    trigger="user_delete",
                    status=status,
                    attempt_count=1,
                    max_attempts=5,
                    next_retry_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                    expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                )
            )
            await db.commit()
        async with TestSession() as db:
            assert await purge.is_user_write_frozen(db, user_id) is True, status
        # Reset between iterations so each status is tested independently.
        async with TestSession() as db:
            op = (
                await db.execute(
                    select(PurgeOperation).where(
                        PurgeOperation.user_id == user_id
                    )
                )
            ).scalar_one()
            await db.delete(op)
            await db.commit()


# --------------------------------------------------------------------------- #
# P1-3: versioned keyring encrypt/decrypt production path
# --------------------------------------------------------------------------- #


def test_keyring_only_mode_encrypt_decrypt_roundtrip(monkeypatch):
    """P1-3: when PURGE_ENCRYPTION_KEYS is set (and PURGE_ENCRYPTION_KEY empty),
    encrypt/decrypt self-resolve from the keyring."""
    key_v1 = _TEST_PURGE_KEY
    monkeypatch.setattr(settings, "PURGE_ENCRYPTION_KEYS", json.dumps({"v1": key_v1}))
    monkeypatch.setattr(settings, "PURGE_ENCRYPTION_KEY", "")
    monkeypatch.setattr(settings, "PURGE_ACTIVE_KEY_VERSION", "v1")

    raw = ["posture_photos/u/secret.jpg"]
    blob = purge.encrypt_object_keys(
        raw, operation_id="op-1", user_id="u", trigger="user_delete"
    )
    # The blob header must carry the resolved key version.
    kv_len = int.from_bytes(blob[:2], "big")
    assert blob[2:2 + kv_len].decode() == "v1"
    assert purge.decrypt_object_keys(
        blob, operation_id="op-1", user_id="u", trigger="user_delete"
    ) == raw


def test_decrypt_uses_blob_key_version_not_active(monkeypatch):
    """P1-3: a v1 blob stays decryptable after the active version switches to
    v2 — decryption selects the key by the blob's stored version, not active."""
    key_v1 = _TEST_PURGE_KEY
    key_v2 = "fedcba9876543210" * 4
    monkeypatch.setattr(
        settings, "PURGE_ENCRYPTION_KEYS", json.dumps({"v1": key_v1, "v2": key_v2})
    )
    monkeypatch.setattr(settings, "PURGE_ACTIVE_KEY_VERSION", "v1")

    raw = ["posture_photos/u/secret.jpg"]
    blob = purge.encrypt_object_keys(
        raw, operation_id="op-1", user_id="u", trigger="user_delete"
    )

    # Rotate the active version to v2; v1 blobs must still decrypt.
    monkeypatch.setattr(settings, "PURGE_ACTIVE_KEY_VERSION", "v2")
    assert purge.decrypt_object_keys(
        blob, operation_id="op-1", user_id="u", trigger="user_delete"
    ) == raw

    # New encryptions now use v2.
    blob2 = purge.encrypt_object_keys(
        raw, operation_id="op-1", user_id="u", trigger="user_delete"
    )
    kv_len = int.from_bytes(blob2[:2], "big")
    assert blob2[2:2 + kv_len].decode() == "v2"


def test_decrypt_non_string_list_fail_closed(monkeypatch):
    """P1-3: if the decrypted plaintext is not a JSON list of strings, decrypt
    fails closed (PurgeConfigError → maps to failed_decrypt in the retry path)."""
    monkeypatch.setattr(settings, "PURGE_ENCRYPTION_KEY", _TEST_PURGE_KEY)
    # Craft a blob whose plaintext is a JSON list of non-strings.
    blob = purge._encrypt_with_resolved_key(
        [1, 2, 3], _TEST_PURGE_KEY, "v1", "op-1", "u", "user_delete"
    )
    with pytest.raises(purge.PurgeConfigError):
        purge.decrypt_object_keys(
            blob, operation_id="op-1", user_id="u", trigger="user_delete"
        )


def test_keyring_invalid_entry_raises_config_error(monkeypatch):
    """P1-3: a malformed keyring (bad hex / wrong length) → PurgeConfigError."""
    monkeypatch.setattr(
        settings, "PURGE_ENCRYPTION_KEYS", json.dumps({"v1": "not-valid-hex"})
    )
    monkeypatch.setattr(settings, "PURGE_ACTIVE_KEY_VERSION", "v1")
    with pytest.raises(purge.PurgeConfigError):
        purge.encrypt_object_keys(["k.jpg"])


def test_active_version_missing_from_keyring_raises(monkeypatch):
    """P1-3: active version not present in the keyring → PurgeConfigError."""
    monkeypatch.setattr(
        settings, "PURGE_ENCRYPTION_KEYS", json.dumps({"v1": _TEST_PURGE_KEY})
    )
    monkeypatch.setattr(settings, "PURGE_ACTIVE_KEY_VERSION", "v9")
    with pytest.raises(purge.PurgeConfigError):
        purge.encrypt_object_keys(["k.jpg"])


def test_explicit_empty_keyring_does_not_fall_back_to_legacy(monkeypatch):
    """An explicitly configured keyring must contain the active version; ``{}``
    is a configuration error, not a request to use the legacy key."""
    monkeypatch.setattr(settings, "PURGE_ENCRYPTION_KEYS", "{}")
    monkeypatch.setattr(settings, "PURGE_ACTIVE_KEY_VERSION", "v1")
    monkeypatch.setattr(settings, "PURGE_ENCRYPTION_KEY", _TEST_PURGE_KEY)
    with pytest.raises(purge.PurgeConfigError, match="ACTIVE_KEY_VERSION"):
        purge.encrypt_object_keys(["k.jpg"])


@pytest.mark.asyncio
async def test_invalid_utf8_key_version_marks_failed_decrypt():
    """An untrusted blob header must not escape as UnicodeDecodeError or leave
    a claimed retry job stuck in ``retrying_oss``."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        user_id = await _make_user(db)
        operation = PurgeOperation(
            user_id=user_id,
            trigger="account_deletion",
            status="failed_oss_retry",
            encrypted_object_keys=(1).to_bytes(2, "big") + b"\xff" + b"0" * 40,
            attempt_count=0,
            max_attempts=5,
            next_retry_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(operation)
        await db.commit()
        operation_id = operation.id

    async with TestSession() as db:
        results = await purge.run_due_purge_jobs(
            db, purge.FakeObjectStore(), _TEST_PURGE_KEY
        )
        assert [result.status for result in results] == ["failed_decrypt"]

    async with TestSession() as db:
        operation = await db.get(PurgeOperation, operation_id)
        assert operation.status == "failed_decrypt"
        tombstones = (await db.execute(select(PosturePurgeTombstone))).scalars().all()
        assert tombstones == []
