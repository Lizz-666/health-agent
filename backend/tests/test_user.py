import pytest


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

    resp = await client.post("/api/v1/auth/verify-login", json={"phone": phone, "code": code})
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_get_profile(client):
    token = await _login_user(client)
    resp = await client.get("/api/v1/user/profile", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["phone"] == "13800138000"


@pytest.mark.asyncio
async def test_update_profile(client):
    token = await _login_user(client)
    resp = await client.put(
        "/api/v1/user/profile",
        json={"height": 175.0, "weight": 70.0, "age": 25, "gender": "male"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["height"] == 175.0
