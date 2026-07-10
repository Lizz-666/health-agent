import pytest
from unittest.mock import patch, AsyncMock


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
async def test_list_issues(client):
    token = await _login_user(client)
    resp = await client.get(
        "/api/v1/posture/issues", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 26


@pytest.mark.asyncio
async def test_list_issues_by_category(client):
    token = await _login_user(client)
    resp = await client.get(
        "/api/v1/posture/issues?category=head_neck",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    for issue in resp.json():
        assert issue["category"] == "head_neck"


@pytest.mark.asyncio
async def test_get_issue_detail(client):
    token = await _login_user(client)
    resp = await client.get(
        "/api/v1/posture/issues/HN-01", headers={"Authorization": f"Bearer {token}"}
    )
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
    resp = await client.get(
        "/api/v1/posture/history", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_get_related(client):
    token = await _login_user(client)
    resp = await client.get(
        "/api/v1/posture/issues/HN-01/related",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) > 0


# --- Photo analysis gate tests ---


@pytest.fixture()
def _force_photo_disabled():
    """Ensure PHOTO_ANALYSIS_ENABLED is False regardless of environment."""
    from app.core.config import settings

    original = settings.PHOTO_ANALYSIS_ENABLED
    settings.PHOTO_ANALYSIS_ENABLED = False
    yield
    settings.PHOTO_ANALYSIS_ENABLED = original


@pytest.mark.asyncio
@pytest.mark.usefixtures("_force_photo_disabled")
async def test_photo_assess_returns_503_when_photo_disabled(client):
    """When PHOTO_ANALYSIS_ENABLED=false, photo assess endpoint returns 503."""
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess/photo",
        json={"issue_id": "HN-01", "photo_keys": ["test/placeholder.jpg"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503
    data = resp.json()
    assert data["detail"] == "照片分析在当前数据模式下未启用"
    assert data["code"] == "photo_analysis_disabled"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_force_photo_disabled")
async def test_photo_assess_does_not_call_ai_when_disabled(client):
    """When photo analysis is disabled, AI model adapter must not be called."""
    token = await _login_user(client)
    with patch(
        "app.posture.ai_service.analyze_posture_photo", new_callable=AsyncMock
    ) as mock_ai:
        await client.post(
            "/api/v1/posture/assess/photo",
            json={"issue_id": "HN-01", "photo_keys": ["test/placeholder.jpg"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        mock_ai.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_force_photo_disabled")
async def test_photo_assess_does_not_create_assessment_when_disabled(client):
    """When photo analysis is disabled, no PostureAssessment record is created."""
    token = await _login_user(client)
    await client.post(
        "/api/v1/posture/assess/photo",
        json={"issue_id": "HN-01", "photo_keys": ["test/placeholder.jpg"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    # Verify no assessment records were created
    resp = await client.get(
        "/api/v1/posture/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("_force_photo_disabled")
async def test_photo_assess_returns_401_when_unauthenticated(client):
    """Unauthenticated request must return 401, not 503 (auth before gate)."""
    resp = await client.post(
        "/api/v1/posture/assess/photo",
        json={"issue_id": "HN-01", "photo_keys": ["test/placeholder.jpg"]},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.usefixtures("_force_photo_disabled")
async def test_photo_assess_invalid_json_returns_503_when_disabled(client):
    """Authenticated + invalid JSON body + disabled -> 503, not 422."""
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess/photo",
        content=b"not valid json {{{",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 503
    data = resp.json()
    assert data["detail"] == "照片分析在当前数据模式下未启用"
    assert data["code"] == "photo_analysis_disabled"
