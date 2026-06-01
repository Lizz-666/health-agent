import pytest
from unittest.mock import patch
from app.core.config import settings

settings.DEV_MODE = True


@pytest.mark.asyncio
async def test_send_code(client):
    resp = await client.post("/api/v1/auth/send-code", json={"phone": "13800138000"})
    assert resp.status_code == 200
    assert resp.json()["message"] == "验证码已发送"


@pytest.mark.asyncio
async def test_verify_login_creates_user(client):
    with patch("app.auth.service.random.randint", return_value=123456):
        await client.post("/api/v1/auth/send-code", json={"phone": "13800138000"})
        resp = await client.post("/api/v1/auth/verify-login", json={"phone": "13800138000", "code": "123456"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["is_new_user"] is True


@pytest.mark.asyncio
async def test_verify_login_existing_user(client):
    with patch("app.auth.service.random.randint", side_effect=[111111, 222222]):
        with patch("app.auth.service.SEND_CODE_INTERVAL_SECONDS", 0):
            await client.post("/api/v1/auth/send-code", json={"phone": "13800138001"})
            resp1 = await client.post("/api/v1/auth/verify-login", json={"phone": "13800138001", "code": "111111"})
            assert resp1.json()["is_new_user"] is True

            await client.post("/api/v1/auth/send-code", json={"phone": "13800138001"})
            resp2 = await client.post("/api/v1/auth/verify-login", json={"phone": "13800138001", "code": "222222"})
    assert resp2.status_code == 200, f"Got {resp2.status_code}: {resp2.text}"
    assert resp2.json()["is_new_user"] is False


@pytest.mark.asyncio
async def test_verify_login_wrong_code(client):
    resp = await client.post("/api/v1/auth/verify-login", json={"phone": "13800138000", "code": "000000"})
    assert resp.status_code == 400
