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
async def test_list_issues(client):
    token = await _login_user(client)
    resp = await client.get("/api/v1/posture/issues", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 26


@pytest.mark.asyncio
async def test_list_issues_by_category(client):
    token = await _login_user(client)
    resp = await client.get("/api/v1/posture/issues?category=head_neck", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    for issue in resp.json():
        assert issue["category"] == "head_neck"


@pytest.mark.asyncio
async def test_get_issue_detail(client):
    token = await _login_user(client)
    resp = await client.get("/api/v1/posture/issues/HN-01", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["name_cn"] == "头部前倾"


@pytest.mark.asyncio
async def test_self_assess(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "moderate"


@pytest.mark.asyncio
async def test_self_assess_negative(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "negative"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "normal"


@pytest.mark.asyncio
async def test_get_history(client):
    token = await _login_user(client)
    await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "negative"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.get("/api/v1/posture/history", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_get_related(client):
    token = await _login_user(client)
    resp = await client.get("/api/v1/posture/issues/HN-01/related", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert len(resp.json()) > 0
