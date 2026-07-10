"""Tests for upload STS endpoint with photo analysis gate."""

import pytest
from unittest.mock import patch

from app.core.config import settings


@pytest.fixture(autouse=True)
def _force_photo_disabled():
    """Ensure PHOTO_ANALYSIS_ENABLED is False regardless of environment."""
    original = settings.PHOTO_ANALYSIS_ENABLED
    settings.PHOTO_ANALYSIS_ENABLED = False
    yield
    settings.PHOTO_ANALYSIS_ENABLED = original


async def _login_user(client, phone="13800138000"):
    await client.post("/api/v1/auth/send-code", json={"phone": phone})
    from tests.conftest import TestSession
    from app.auth.models import VerificationCode
    from sqlalchemy import select

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


@pytest.mark.asyncio
async def test_sts_token_returns_503_when_photo_disabled(client):
    """When PHOTO_ANALYSIS_ENABLED=false, STS endpoint returns 503."""
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/upload/sts-token",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503
    data = resp.json()
    assert data["detail"] == "照片分析在当前数据模式下未启用"
    assert data["code"] == "photo_analysis_disabled"


@pytest.mark.asyncio
async def test_sts_token_does_not_call_generate_sts_credentials_when_disabled(client):
    """When photo analysis is disabled, generate_sts_credentials must not be called."""
    token = await _login_user(client)
    with patch("app.upload.service.generate_sts_credentials") as mock_gen:
        await client.post(
            "/api/v1/upload/sts-token",
            headers={"Authorization": f"Bearer {token}"},
        )
        mock_gen.assert_not_called()


@pytest.mark.asyncio
async def test_sts_token_returns_401_when_unauthenticated(client):
    """Unauthenticated request must return 401, not 503 (auth before gate)."""
    resp = await client.post("/api/v1/upload/sts-token")
    assert resp.status_code == 401
