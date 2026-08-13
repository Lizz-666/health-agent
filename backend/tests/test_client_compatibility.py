from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
import pytest

from app.core.compatibility import reject_incompatible_client
from app.core.config import Settings, settings


def _candidate_settings(**overrides) -> Settings:
    values = {
        "DEPLOYMENT_PROFILE": "controlled_trial_candidate",
        "AUTH_MODE": "controlled_trial",
        "AUTH_CREDENTIAL_PROVIDER": "offline_password",
        "DATABASE_URL": "postgresql+asyncpg://trial:trial@db/trial",
        "SECRET_KEY": "s" * 32,
        "AUTH_AUDIT_HMAC_KEY": "a" * 32,
        "PRIVACY_AUDIT_HMAC_KEY": "p" * 32,
        "JWT_ISSUER": "trial-issuer",
        "JWT_AUDIENCE": "trial-audience",
        "ACCESS_TOKEN_EXPIRE_MINUTES": 10,
        "PURGE_ENCRYPTION_KEY": "8" * 64,
        "MIN_ANDROID_CLIENT_VERSION_CODE": 1,
        "MAX_ANDROID_CLIENT_VERSION_CODE": 1,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_candidate_config_rejects_invalid_client_version_window():
    with pytest.raises(ValueError, match="client version window"):
        _candidate_settings(
            MIN_ANDROID_CLIENT_VERSION_CODE=2,
            MAX_ANDROID_CLIENT_VERSION_CODE=1,
        )


@pytest.mark.asyncio
async def test_candidate_rejects_incompatible_client_before_route_write(monkeypatch):
    monkeypatch.setattr(settings, "DEPLOYMENT_PROFILE", "controlled_trial_candidate")
    monkeypatch.setattr(settings, "MIN_ANDROID_CLIENT_VERSION_CODE", 1)
    monkeypatch.setattr(settings, "MAX_ANDROID_CLIENT_VERSION_CODE", 1)
    route_calls = 0
    app = FastAPI()

    @app.middleware("http")
    async def compatibility(request: Request, call_next):
        rejection = reject_incompatible_client(request)
        return rejection if rejection is not None else await call_next(request)

    @app.post("/api/v1/write")
    async def write():
        nonlocal route_calls
        route_calls += 1
        return {"status": "written"}

    cases = (
        {},
        {"X-Client-Platform": "ios", "X-Client-Version-Code": "1"},
        {"X-Client-Platform": "android", "X-Client-Version-Code": "bad"},
        {"X-Client-Platform": "android", "X-Client-Version-Code": "0"},
        {"X-Client-Platform": "android", "X-Client-Version-Code": "2"},
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for headers in cases:
            response = await client.post("/api/v1/write", headers=headers)
            assert response.status_code == 426
            assert response.json() == {
                "detail": "当前应用版本不兼容，请更新后重试",
                "code": "client_version_incompatible",
            }
        accepted = await client.post(
            "/api/v1/write",
            headers={
                "X-Client-Platform": "android",
                "X-Client-Version-Code": "1",
                "Host": "attacker.invalid/api/v1/bypass",
            },
        )

    assert accepted.status_code == 200
    assert route_calls == 1


@pytest.mark.asyncio
async def test_development_profile_does_not_require_candidate_headers(monkeypatch):
    monkeypatch.setattr(settings, "DEPLOYMENT_PROFILE", "development")
    request = Request({"type": "http", "path": "/api/v1/probe", "headers": []})
    assert reject_incompatible_client(request) is None
