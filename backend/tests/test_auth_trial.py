from datetime import timedelta
import asyncio
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.auth import service
from app.auth.models import TrialCredential, TrialInvitation
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.core.config import Settings, settings
from tests.conftest import TestSession
from tests.conftest_pg import pg_available, requires_pg, skip_reason


ACCOUNT = "synthetic-tester-01"
PASSWORD = "Synthetic-passphrase-01"
DEVICE = "synthetic-device-key-0000000000000001"
BACKEND_DIR = Path(__file__).resolve().parent.parent


async def _provision(**kwargs):
    async with TestSession() as db:
        return await service.provision_trial_account(
            db, account_name=ACCOUNT, password=PASSWORD, **kwargs
        )


def _candidate_settings(**overrides):
    values = {
        "DEPLOYMENT_PROFILE": "controlled_trial_candidate",
        "AUTH_MODE": "controlled_trial",
        "SECRET_KEY": "synthetic-secret-key-that-is-long-enough",
        "AUTH_AUDIT_HMAC_KEY": "synthetic-audit-key-that-is-long-enough",
        "DATABASE_URL": "postgresql+asyncpg://synthetic:synthetic@localhost/synthetic",
        "ACCESS_TOKEN_EXPIRE_MINUTES": 15,
        "JWT_ISSUER": "synthetic-controlled-trial-issuer",
        "JWT_AUDIENCE": "synthetic-controlled-trial-client",
        "DEV_MODE": False,
        "DEV_ADMIN_PHONE": "",
        "DEV_ADMIN_PASSWORD": "",
        "PHOTO_ANALYSIS_ENABLED": False,
        "AGENT_RUNTIME_ENABLED": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    "override",
    [
        {"SECRET_KEY": "CHANGE-ME-IN-PRODUCTION"},
        {"DATABASE_URL": "postgresql+asyncpg://user:password@localhost:5432/posture_app"},
        {"AUTH_AUDIT_HMAC_KEY": ""},
        {"JWT_ISSUER": "posture-app"},
        {"JWT_AUDIENCE": "posture-app-client"},
        {"AUTH_MODE": "legacy"},
        {"DEV_MODE": True},
        {"DEV_ADMIN_PASSWORD": "synthetic"},
        {"PHOTO_ANALYSIS_ENABLED": True},
        {"AGENT_RUNTIME_ENABLED": True},
        {"ACCESS_TOKEN_EXPIRE_MINUTES": 16},
    ],
)
def test_candidate_configuration_rejects_unsafe_values(override):
    with pytest.raises(ValidationError, match="controlled-trial configuration rejected"):
        _candidate_settings(**override)


def test_candidate_configuration_accepts_complete_synthetic_values():
    configured = _candidate_settings()
    assert configured.AUTH_MODE == "controlled_trial"


@pytest.mark.asyncio
async def test_activation_consumes_invitation_once_and_profile_uses_account_name(client):
    provisioned = await _provision()
    payload = {
        "invitation_code": provisioned.invitation_code,
        "account_name": ACCOUNT,
        "credential": PASSWORD,
        "device_key": DEVICE,
    }
    with patch.object(settings, "AUTH_MODE", "controlled_trial"):
        first = await client.post("/api/v1/auth/trial/activate", json=payload)
        replay = await client.post("/api/v1/auth/trial/activate", json=payload)
        profile = await client.get(
            "/api/v1/user/profile",
            headers={"Authorization": f"Bearer {first.json()['access_token']}"},
        )
    assert first.status_code == 200
    assert replay.status_code == 400
    assert replay.json()["code"] == "activation_failed"
    assert profile.status_code == 200
    assert profile.json()["phone"] is None
    assert profile.json()["account_name"] == ACCOUNT


@pytest.mark.asyncio
async def test_expired_and_revoked_invitations_fail_with_same_response(client):
    expired = await _provision(invitation_ttl=timedelta(seconds=-1))
    body = {
        "invitation_code": expired.invitation_code,
        "account_name": ACCOUNT,
        "credential": PASSWORD,
        "device_key": DEVICE,
    }
    with patch.object(settings, "AUTH_MODE", "controlled_trial"):
        response = await client.post("/api/v1/auth/trial/activate", json=body)
    assert response.status_code == 400
    assert response.json()["code"] == "activation_failed"


@pytest.mark.asyncio
async def test_revoked_invitation_fails_and_storage_contains_no_raw_secret(client):
    provisioned = await _provision()
    async with TestSession() as db:
        invitation = await db.scalar(
            select(TrialInvitation).where(
                TrialInvitation.user_id == UUID(provisioned.user_id)
            )
        )
        stored = await db.scalar(
            select(TrialCredential).where(
                TrialCredential.user_id == UUID(provisioned.user_id)
            )
        )
        invitation.revoked_at = service._utcnow()
        await db.commit()
        assert invitation.code_digest != provisioned.invitation_code
        assert stored.credential_hash != PASSWORD
        assert PASSWORD not in stored.credential_hash
    with patch.object(settings, "AUTH_MODE", "controlled_trial"):
        response = await client.post(
            "/api/v1/auth/trial/activate",
            json={
                "invitation_code": provisioned.invitation_code,
                "account_name": ACCOUNT,
                "credential": PASSWORD,
                "device_key": DEVICE,
            },
        )
    assert response.status_code == 400
    assert response.json()["code"] == "activation_failed"


@pytest.mark.asyncio
async def test_login_does_not_enumerate_accounts_and_rate_limits(client):
    with (
        patch.object(settings, "AUTH_MODE", "controlled_trial"),
        patch.object(settings, "AUTH_LOGIN_MAX_ATTEMPTS", 2),
    ):
        unknown = await client.post(
            "/api/v1/auth/trial/login",
            json={"account_name": "synthetic-missing", "credential": PASSWORD, "device_key": DEVICE},
        )
        again = await client.post(
            "/api/v1/auth/trial/login",
            json={"account_name": "synthetic-missing", "credential": PASSWORD, "device_key": DEVICE},
        )
        limited = await client.post(
            "/api/v1/auth/trial/login",
            json={"account_name": "synthetic-missing", "credential": PASSWORD, "device_key": DEVICE},
        )
    assert unknown.status_code == again.status_code == 401
    assert unknown.json() == again.json()
    assert limited.status_code == 429
    assert limited.json()["code"] == "auth_rate_limited"


@pytest.mark.asyncio
async def test_device_conflict_refresh_rotation_and_logout_revoke(client):
    provisioned = await _provision()
    with patch.object(settings, "AUTH_MODE", "controlled_trial"):
        activated = await client.post(
            "/api/v1/auth/trial/activate",
            json={
                "invitation_code": provisioned.invitation_code,
                "account_name": ACCOUNT,
                "credential": PASSWORD,
                "device_key": DEVICE,
            },
        )
        conflict = await client.post(
            "/api/v1/auth/trial/login",
            json={
                "account_name": ACCOUNT,
                "credential": PASSWORD,
                "device_key": "other-synthetic-device-key-0000000001",
            },
        )
        old_refresh = activated.json()["refresh_token"]
        rotated = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        new_refresh = rotated.json()["refresh_token"]
        logout = await client.post("/api/v1/auth/trial/logout", json={"refresh_token": new_refresh})
        after_logout = await client.get(
            "/api/v1/user/profile",
            headers={"Authorization": f"Bearer {rotated.json()['access_token']}"},
        )
    assert conflict.status_code == 403
    assert conflict.json()["code"] == "trial_device_conflict"
    assert rotated.status_code == 200
    assert replay.status_code == 401
    assert logout.status_code == 204
    assert after_logout.status_code == 401


@pytest.mark.asyncio
async def test_trial_mode_hides_legacy_and_dev_auth(client):
    with patch.object(settings, "AUTH_MODE", "controlled_trial"):
        sms = await client.post("/api/v1/auth/send-code", json={"phone": "13800138000"})
        dev = await client.post(
            "/api/v1/auth/dev-login",
            json={"phone": "13800138000", "password": "synthetic-password"},
        )
    assert sms.status_code == dev.status_code == 404
    assert sms.json()["code"] == dev.json()["code"] == "auth_method_unavailable"


@pytest.mark.asyncio
async def test_trial_mode_rejects_legacy_stateless_tokens(client):
    provisioned = await _provision()
    with patch.object(settings, "AUTH_MODE", "controlled_trial"):
        access = await client.get(
            "/api/v1/user/profile",
            headers={
                "Authorization": f"Bearer {create_access_token(provisioned.user_id)}"
            },
        )
        refresh = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": create_refresh_token(provisioned.user_id)},
        )
    assert access.status_code == refresh.status_code == 401


@pytest.mark.asyncio
async def test_operator_reissue_revokes_old_device_and_allows_new_device(client):
    provisioned = await _provision()
    with patch.object(settings, "AUTH_MODE", "controlled_trial"):
        activated = await client.post(
            "/api/v1/auth/trial/activate",
            json={
                "invitation_code": provisioned.invitation_code,
                "account_name": ACCOUNT,
                "credential": PASSWORD,
                "device_key": DEVICE,
            },
        )
        async with TestSession() as db:
            new_invitation = await service.reissue_trial_invitation(
                db, account_name=ACCOUNT
            )
        old_access = await client.get(
            "/api/v1/user/profile",
            headers={"Authorization": f"Bearer {activated.json()['access_token']}"},
        )
        recovered = await client.post(
            "/api/v1/auth/trial/activate",
            json={
                "invitation_code": new_invitation,
                "account_name": ACCOUNT,
                "credential": PASSWORD,
                "device_key": "replacement-device-key-000000000000001",
            },
        )
    assert old_access.status_code == 401
    assert recovered.status_code == 200


@pytest.mark.asyncio
async def test_trial_validation_does_not_echo_secrets(client):
    raw_secret = "synthetic-secret-that-must-not-echo"
    with patch.object(settings, "AUTH_MODE", "controlled_trial"):
        response = await client.post(
            "/api/v1/auth/trial/login",
            json={
                "account_name": "bad",
                "credential": raw_secret,
                "device_key": "short",
            },
        )
    assert response.status_code == 422
    assert response.json()["code"] == "auth_invalid_request"
    assert raw_secret not in response.text


@requires_pg
@pytest.mark.requires_pg
@pytest.mark.asyncio
async def test_postgresql_invitation_and_refresh_are_single_winner(
    pg_session_factory,
):
    if not pg_available:
        pytest.skip(skip_reason)
    seed = pg_session_factory()
    provisioned = await service.provision_trial_account(
        seed, account_name=ACCOUNT, password=PASSWORD
    )
    await seed.close()

    async def activate():
        db = pg_session_factory()
        try:
            return await service.activate_trial_account(
                db,
                invitation_code=provisioned.invitation_code,
                account_name=ACCOUNT,
                provider_id="offline_password",
                credential_value=PASSWORD,
                device_key=DEVICE,
                source_key="synthetic-pg-source",
            )
        except Exception as error:
            return error
        finally:
            await db.close()

    activation_results = await asyncio.gather(activate(), activate())
    winners = [result for result in activation_results if isinstance(result, service.TrialTokens)]
    assert len(winners) == 1

    payload = decode_token(winners[0].refresh_token)

    async def rotate():
        db = pg_session_factory()
        try:
            return await service.rotate_trial_refresh(
                db, winners[0].refresh_token, payload
            )
        except Exception as error:
            return error
        finally:
            await db.close()

    rotation_results = await asyncio.gather(rotate(), rotate())
    assert sum(isinstance(result, service.TrialTokens) for result in rotation_results) == 1


@requires_pg
@pytest.mark.requires_pg
def test_postgresql_0013_downgrade_and_upgrade(pg_dsn):
    if not pg_available:
        pytest.skip(skip_reason)
    env = dict(os.environ)
    env["DATABASE_URL"] = pg_dsn
    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0012_review_draft_origins"],
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
