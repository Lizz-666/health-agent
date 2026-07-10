import pytest
from unittest.mock import patch, AsyncMock
from app.core.config import settings
from app.core.exceptions import ServiceUnavailable
from app.posture.models import PostureAssessment
from sqlalchemy import select


@pytest.fixture
def photo_analysis_enabled(monkeypatch):
    monkeypatch.setattr(settings, "PHOTO_ANALYSIS_ENABLED", True)


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
def _force_photo_disabled(monkeypatch):
    """Ensure PHOTO_ANALYSIS_ENABLED is False regardless of environment."""
    monkeypatch.setattr(settings, "PHOTO_ANALYSIS_ENABLED", False)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_force_photo_disabled")
async def test_photo_assess_returns_503_when_photo_disabled(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess/photo",
        json={"issue_id": "HN-01", "photo_keys": ["test/placeholder.jpg"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503
    assert resp.json() == {
        "detail": "照片分析在当前数据模式下未启用",
        "code": "photo_analysis_disabled",
    }


@pytest.mark.asyncio
@pytest.mark.usefixtures("_force_photo_disabled")
async def test_photo_assess_does_not_call_ai_when_disabled(client):
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
    token = await _login_user(client)
    await client.post(
        "/api/v1/posture/assess/photo",
        json={"issue_id": "HN-01", "photo_keys": ["test/placeholder.jpg"]},
        headers={"Authorization": f"Bearer {token}"},
    )
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


@pytest.mark.asyncio
async def test_photo_assess_ai_failure_returns_503(client, photo_analysis_enabled):
    """When AI service fails, photo assessment returns 503 and saves no record."""
    token = await _login_user(client)
    with patch(
        "app.posture.ai_service.analyze_posture_photo",
        new_callable=AsyncMock,
        side_effect=ServiceUnavailable("AI service failed"),
    ):
        resp = await client.post(
            "/api/v1/posture/assess/photo",
            json={"issue_id": "HN-01", "photo_keys": ["fake-key.jpg"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 503

    # Verify no assessment was persisted
    resp = await client.get(
        "/api/v1/posture/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_photo_assess_need_retake_returns_503_without_saving(
    client, photo_analysis_enabled
):
    token = await _login_user(client)
    with patch(
        "app.posture.ai_service.analyze_posture_photo",
        new_callable=AsyncMock,
        side_effect=ServiceUnavailable("照片质量不足，请重新拍照"),
    ):
        resp = await client.post(
            "/api/v1/posture/assess/photo",
            json={"issue_id": "HN-01", "photo_keys": ["fake-key.jpg"]},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 503

    from tests.conftest import TestSession

    async with TestSession() as db:
        result = await db.execute(select(PostureAssessment))
        assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_photo_assess_mild_mapped_to_moderate(
    client, photo_analysis_enabled
):
    """AI mild must be mapped to moderate for Flutter, not stored as mild or normal."""
    token = await _login_user(client)
    mock_ai_result = {
        "level": "mild",
        "confidence": 0.7,
        "evidence": ["slight forward head position"],
        "suggestion": "轻度前倾，建议关注",
        "need_retake": False,
        "retake_reason": "",
    }
    with patch(
        "app.posture.ai_service.analyze_posture_photo",
        new_callable=AsyncMock,
        return_value=mock_ai_result,
    ):
        resp = await client.post(
            "/api/v1/posture/assess/photo",
            json={"issue_id": "HN-01", "photo_keys": ["fake-key.jpg"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        # Flutter sees "moderate", not "mild" or "normal"
        assert resp.json()["result"] == "moderate"

    from tests.conftest import TestSession

    async with TestSession() as db:
        result = await db.execute(select(PostureAssessment))
        assessment = result.scalar_one()
        assert assessment.result == "moderate"
        assert assessment.ai_response["level"] == "mild"
