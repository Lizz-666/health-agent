from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select

from app.auth import service as auth_service
from app.auth.models import (
    AuthSession,
    TrialCredential,
    TrialDeviceEnrollment,
    TrialInvitation,
    User,
)
from app.core.config import settings
from app.health.models import HealthProfile
from app.posture.models import PostureAssessmentEvent, PurgeOperation
from app.privacy.models import AccountDeletionMarker, SensitiveHealthConsentEvent
from app.privacy import service as privacy_service
from app.privacy.ledger import (
    DeletionLedgerError,
    build_deletion_ledger,
    merge_deletion_ledger,
)
from app.privacy.service import ensure_no_restored_deleted_subjects, subject_digest
from tests.conftest import TestSession
from tests.conftest_pg import pg_available, requires_pg, skip_reason


ACCOUNT = "synthetic-privacy-tester"
PASSWORD = "Synthetic-privacy-passphrase-01"
DEVICE = "synthetic-privacy-device-key-000000000001"
PURGE_KEY = "0123456789abcdef" * 4
PRIVACY_KEY = "synthetic-privacy-audit-key-that-is-long-enough"
BACKEND_DIR = Path(__file__).resolve().parents[1]


async def _activated(client, *, account: str = ACCOUNT):
    async with TestSession() as db:
        provisioned = await auth_service.provision_trial_account(
            db,
            account_name=account,
            password=PASSWORD,
        )
    response = await client.post(
        "/api/v1/auth/trial/activate",
        json={
            "invitation_code": provisioned.invitation_code,
            "account_name": account,
            "credential": PASSWORD,
            "device_key": DEVICE,
        },
    )
    assert response.status_code == 200, response.text
    return provisioned, {
        "Authorization": f"Bearer {response.json()['access_token']}"
    }


@pytest.fixture
def trial_settings(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "controlled_trial")
    monkeypatch.setattr(settings, "PRIVACY_AUDIT_HMAC_KEY", PRIVACY_KEY)
    monkeypatch.setattr(
        settings,
        "PRIVACY_NOTICE_VERSION",
        "controlled-trial-sensitive-health-v1",
    )
    monkeypatch.setattr(settings, "PURGE_ENCRYPTION_KEY", PURGE_KEY)
    monkeypatch.setattr(settings, "PURGE_ENCRYPTION_KEYS", "")


@pytest.mark.asyncio
async def test_health_data_requires_current_versioned_consent_but_rights_remain_available(
    client, trial_settings
):
    _provisioned, headers = await _activated(client)

    identity = await client.get("/api/v1/user/profile", headers=headers)
    public_knowledge = await client.get("/api/v1/posture/issues")
    blocked = await client.get("/api/v1/health/profile", headers=headers)
    stale = await client.post(
        "/api/v1/privacy/consent",
        headers=headers,
        json={"action": "grant", "notice_version": "obsolete-notice"},
    )
    granted = await client.post(
        "/api/v1/privacy/consent",
        headers=headers,
        json={
            "action": "grant",
            "notice_version": settings.PRIVACY_NOTICE_VERSION,
        },
    )
    allowed = await client.get("/api/v1/health/profile", headers=headers)
    withdrawn = await client.post(
        "/api/v1/privacy/consent",
        headers=headers,
        json={
            "action": "withdraw",
            "notice_version": settings.PRIVACY_NOTICE_VERSION,
        },
    )
    blocked_again = await client.get("/api/v1/health/profile", headers=headers)
    export_after_withdrawal = await client.get("/api/v1/privacy/export", headers=headers)

    assert identity.status_code == 200
    assert public_knowledge.status_code == 200
    assert identity.json()["account_name"] == ACCOUNT
    assert identity.json()["height"] is None
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "privacy_consent_required"
    assert stale.status_code == 409
    assert stale.json()["code"] == "privacy_notice_stale"
    assert granted.status_code == 200
    assert granted.json()["active"] is True
    assert granted.json()["sequence_no"] == 1
    assert allowed.status_code == 200
    assert withdrawn.status_code == 200
    assert withdrawn.json()["active"] is False
    assert withdrawn.json()["sequence_no"] == 2
    assert blocked_again.status_code == 403
    assert export_after_withdrawal.status_code == 200


@pytest.mark.asyncio
async def test_export_is_owner_scoped_and_excludes_authenticators(
    client, trial_settings
):
    provisioned, headers = await _activated(client)
    await client.post(
        "/api/v1/privacy/consent",
        headers=headers,
        json={
            "action": "grant",
            "notice_version": settings.PRIVACY_NOTICE_VERSION,
        },
    )
    await client.put(
        "/api/v1/user/profile",
        headers=headers,
        json={"nickname": "合成测试者", "height": 170, "weight": 65, "age": 30},
    )
    response = await client.get("/api/v1/privacy/export", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    exported_data = {
        "identity": payload["identity"],
        "consent_history": payload["consent_history"],
        "domain_records": payload["domain_records"],
    }
    serialized = str(exported_data)
    assert payload["subject_id"] == provisioned.user_id
    assert payload["identity"]["account_name"] == ACCOUNT
    assert payload["identity"]["profile"]["nickname"] == "合成测试者"
    assert "credential_hash" not in serialized
    assert "code_digest" not in serialized
    assert "device_key_digest" not in serialized
    assert "refresh_token_digest" not in serialized
    assert PASSWORD not in serialized
    assert DEVICE not in serialized
    assert provisioned.invitation_code not in serialized
    assert set(payload["excluded_security_fields"]) >= {
        "credential_hash",
        "invitation_code_digest",
        "device_key_digest",
        "refresh_token_digest",
    }


@pytest.mark.asyncio
async def test_account_deletion_removes_trial_identity_and_leaves_unlinkable_marker(
    client, trial_settings
):
    provisioned, headers = await _activated(client)
    uid = UUID(provisioned.user_id)
    await client.post(
        "/api/v1/privacy/consent",
        headers=headers,
        json={
            "action": "grant",
            "notice_version": settings.PRIVACY_NOTICE_VERSION,
        },
    )
    async with TestSession() as db:
        db.add(HealthProfile(user_id=uid, version=1))
        await db.commit()

    response = await client.post(
        "/api/v1/privacy/account-deletion",
        headers=headers,
        json={
            "provider_id": "offline_password",
            "credential": PASSWORD,
            "device_key": DEVICE,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert response.json()["receipt_id"]

    async with TestSession() as db:
        assert await db.get(User, uid) is None
        for model in (
            TrialCredential,
            TrialInvitation,
            TrialDeviceEnrollment,
            AuthSession,
            SensitiveHealthConsentEvent,
            HealthProfile,
        ):
            assert await db.scalar(select(model).where(model.user_id == uid)) is None
        marker = await db.scalar(select(AccountDeletionMarker))
        assert marker is not None
        assert marker.subject_digest == subject_digest(uid)
        assert str(uid) not in marker.subject_digest
        assert ACCOUNT not in marker.subject_digest

    old_session = await client.get("/api/v1/privacy/export", headers=headers)
    assert old_session.status_code == 401


@pytest.mark.asyncio
async def test_account_deletion_requires_current_credential_and_device(
    client, trial_settings
):
    _provisioned, headers = await _activated(client)
    response = await client.post(
        "/api/v1/privacy/account-deletion",
        headers=headers,
        json={
            "provider_id": "offline_password",
            "credential": "wrong-synthetic-password",
            "device_key": DEVICE,
        },
    )
    assert response.status_code == 401
    assert response.json()["code"] == "reauthentication_failed"

    still_exists = await client.get("/api/v1/user/profile", headers=headers)
    assert still_exists.status_code == 200


@pytest.mark.asyncio
async def test_failed_object_deletion_keeps_account_disabled_and_frozen(
    client, trial_settings
):
    provisioned, headers = await _activated(
        client,
        account="synthetic-privacy-delete-failure",
    )
    uid = UUID(provisioned.user_id)
    async with TestSession() as db:
        db.add(
            PostureAssessmentEvent(
                user_id=uid,
                issue_id="HN-01",
                source="ai_photo",
                severity="moderate",
                lifecycle="active",
                photo_keys=[f"synthetic-photo/{uid}/blocked.jpg"],
            )
        )
        await db.commit()

    deletion = await client.post(
        "/api/v1/privacy/account-deletion",
        headers=headers,
        json={
            "provider_id": "offline_password",
            "credential": PASSWORD,
            "device_key": DEVICE,
        },
    )
    relogin = await client.post(
        "/api/v1/auth/trial/login",
        json={
            "account_name": "synthetic-privacy-delete-failure",
            "credential": PASSWORD,
            "device_key": DEVICE,
        },
    )

    assert deletion.status_code == 503
    assert deletion.json()["code"] == "account_deletion_pending"
    assert relogin.status_code == 401
    async with TestSession() as db:
        credential = await db.get(TrialCredential, uid)
        operation = await db.scalar(
            select(PurgeOperation).where(PurgeOperation.user_id == uid)
        )
        assert credential is not None and credential.disabled_at is not None
        assert operation is not None and operation.status == "failed_oss_retry"


@pytest.mark.asyncio
async def test_restore_guard_rejects_reanimated_deleted_identity(trial_settings):
    async with TestSession() as db:
        user = User()
        db.add(user)
        await db.flush()
        db.add(
            TrialCredential(
                user_id=user.id,
                login_id="synthetic-restored-account",
                provider_id="offline_password",
                credential_hash="synthetic-nonfunctional-hash",
            )
        )
        db.add(
            AccountDeletionMarker(
                subject_digest=subject_digest(user.id),
                deleted_at=auth_service._utcnow(),
                policy_version="synthetic-restore-exercise",
            )
        )
        await db.commit()

        with pytest.raises(RuntimeError, match="deleted trial subject was restored"):
            await ensure_no_restored_deleted_subjects(db)


@pytest.mark.asyncio
async def test_signed_deletion_ledger_merges_newer_marker_before_restore_check(
    trial_settings,
):
    deleted_id = UUID("00000000-0000-4000-8000-000000000099")
    async with TestSession() as db:
        marker = AccountDeletionMarker(
            subject_digest=subject_digest(deleted_id),
            deleted_at=auth_service._utcnow(),
            policy_version="synthetic-ledger-exercise",
        )
        db.add(marker)
        await db.commit()
        ledger = await build_deletion_ledger(db)
        await db.delete(marker)
        await db.commit()
        user = User(id=deleted_id)
        db.add(user)
        await db.flush()
        db.add(
            TrialCredential(
                user_id=deleted_id,
                login_id="synthetic-ledger-restored-account",
                provider_id="offline_password",
                credential_hash="synthetic-nonfunctional-hash",
            )
        )
        await db.commit()

        assert await merge_deletion_ledger(db, ledger) == 1
        with pytest.raises(RuntimeError, match="deleted trial subject was restored"):
            await ensure_no_restored_deleted_subjects(db)


@pytest.mark.asyncio
async def test_deletion_ledger_rejects_tampering(trial_settings):
    async with TestSession() as db:
        ledger = await build_deletion_ledger(db)
        ledger["generated_at"] = "tampered"
        with pytest.raises(DeletionLedgerError, match="integrity"):
            await merge_deletion_ledger(db, ledger)


@pytest.mark.asyncio
async def test_security_logs_are_correlated_and_do_not_contain_credentials(
    client, trial_settings, caplog
):
    secret = "Synthetic-secret-that-must-not-be-logged-01"
    request_id = "synthetic-request-0001"
    with caplog.at_level(logging.INFO):
        invalid = await client.post(
            "/api/v1/auth/trial/login",
            headers={"X-Request-ID": request_id},
            json={
                "account_name": ACCOUNT,
                "credential": secret,
                "device_key": DEVICE,
            },
        )

    assert invalid.status_code == 401
    response_request_id = invalid.headers["X-Request-ID"]
    assert response_request_id != request_id
    assert len(response_request_id) == 32
    assert "code=auth.trial_login outcome=rejected" in caplog.text
    assert f"request_id={response_request_id}" in caplog.text
    assert request_id not in caplog.text
    assert secret not in caplog.text
    assert ACCOUNT not in caplog.text
    assert DEVICE not in caplog.text


@requires_pg
@pytest.mark.requires_pg
@pytest.mark.asyncio
async def test_postgresql_consent_sequence_is_single_ordered_history(
    pg_session_factory, trial_settings
):
    if not pg_available:
        pytest.skip(skip_reason)
    seed = pg_session_factory()
    provisioned = await auth_service.provision_trial_account(
        seed,
        account_name="synthetic-pg-privacy",
        password=PASSWORD,
    )
    await auth_service.activate_trial_account(
        seed,
        invitation_code=provisioned.invitation_code,
        account_name="synthetic-pg-privacy",
        provider_id="offline_password",
        credential_value=PASSWORD,
        device_key=DEVICE,
        source_key="synthetic-pg-privacy-source",
    )
    await seed.close()

    async def record(action: str):
        db = pg_session_factory()
        try:
            return await privacy_service.record_consent(
                db,
                provisioned.user_id,
                action=action,
                notice_version=settings.PRIVACY_NOTICE_VERSION,
            )
        finally:
            await db.close()

    events = await asyncio.gather(record("grant"), record("withdraw"))
    assert sorted(event.sequence_no for event in events) == [1, 2]


@requires_pg
@pytest.mark.requires_pg
@pytest.mark.asyncio
async def test_postgresql_identity_deletion_leaves_only_unlinkable_marker(
    pg_session, trial_settings
):
    if not pg_available:
        pytest.skip(skip_reason)
    provisioned = await auth_service.provision_trial_account(
        pg_session,
        account_name="synthetic-pg-delete",
        password=PASSWORD,
    )
    await auth_service.activate_trial_account(
        pg_session,
        invitation_code=provisioned.invitation_code,
        account_name="synthetic-pg-delete",
        provider_id="offline_password",
        credential_value=PASSWORD,
        device_key=DEVICE,
        source_key="synthetic-pg-delete-source",
    )
    uid = UUID(provisioned.user_id)
    await privacy_service.record_consent(
        pg_session,
        provisioned.user_id,
        action="grant",
        notice_version=settings.PRIVACY_NOTICE_VERSION,
    )

    receipt_id = await privacy_service.finalize_trial_identity_deletion(
        pg_session,
        uid,
    )
    await pg_session.commit()

    assert await pg_session.get(User, uid) is None
    assert await pg_session.scalar(
        select(TrialCredential).where(TrialCredential.user_id == uid)
    ) is None
    assert await pg_session.scalar(
        select(SensitiveHealthConsentEvent).where(
            SensitiveHealthConsentEvent.user_id == uid
        )
    ) is None
    marker = await pg_session.get(AccountDeletionMarker, receipt_id)
    assert marker is not None
    assert marker.subject_digest == subject_digest(uid)
    assert str(uid) not in marker.subject_digest


@requires_pg
@pytest.mark.requires_pg
def test_postgresql_0014_downgrade_and_upgrade(pg_dsn):
    if not pg_available:
        pytest.skip(skip_reason)
    env = dict(os.environ)
    env["DATABASE_URL"] = pg_dsn
    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0013_controlled_trial_auth"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    assert downgrade.returncode == 0, downgrade.stderr
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    assert upgrade.returncode == 0, upgrade.stderr
