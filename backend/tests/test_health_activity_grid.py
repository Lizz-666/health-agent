"""Phase 2 Task 4 tests: activity grid projection over check-in statuses.

All data is synthetic. Covers the Phase 2-only status set
(none/checked_in/active_rest/safety_adjustment), range bounding + cap, default
window, cross-user isolation, and the "no plan-execution statuses" invariant.
"""

import pytest

from app.auth.models import VerificationCode
from sqlalchemy import select
from tests.conftest import TestSession


AUTH = "/api/v1/auth"
GRID = "/api/v1/health/activity-grid"
CHECKIN_TODAY = "/api/v1/health/checkins/today"


async def _login_user(client, phone: str) -> str:
    """Register/login a synthetic user and return its access token."""
    await client.post(f"{AUTH}/send-code", json={"phone": phone})
    async with TestSession() as db:
        result = await db.execute(
            select(VerificationCode)
            .where(VerificationCode.phone == phone)
            .order_by(VerificationCode.created_at.desc())
        )
        code = result.scalar_one().code
    resp = await client.post(
        f"{AUTH}/verify-login", json={"phone": phone, "code": code}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _checkin(local_date: str, daily_status: str) -> dict:
    return {
        "local_date": local_date,
        "sleep_quality": "good",
        "energy": "normal",
        "muscle_soreness": "none",
        "available_time": "30_min",
        "daily_status": daily_status,
        "abnormal_pain": False,
    }


async def _seed_checkins(client, token, items):
    for local_date, status in items:
        resp = await client.put(
            CHECKIN_TODAY,
            json=_checkin(local_date, status),
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_required(client):
    resp = await client.get(GRID)
    assert resp.status_code == 401, resp.text
    assert resp.json()["code"] == "unauthorized"


# ---------------------------------------------------------------------------
# Status projection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_range_is_all_none(client):
    token = await _login_user(client, "13903000001")
    resp = await client.get(
        f"{GRID}?start_date=2026-07-20&end_date=2026-07-23",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["start_date"] == "2026-07-20"
    assert body["end_date"] == "2026-07-23"
    assert [c["status"] for c in body["cells"]] == ["none"] * 4
    assert [c["date"] for c in body["cells"]] == [
        "2026-07-20",
        "2026-07-21",
        "2026-07-22",
        "2026-07-23",
    ]


@pytest.mark.asyncio
async def test_status_projection_from_checkins(client):
    token = await _login_user(client, "13903000002")
    await _seed_checkins(
        client,
        token,
        [
            ("2026-07-21", "checked_in"),
            ("2026-07-22", "active_rest"),
            ("2026-07-23", "safety_adjustment"),
        ],
    )
    resp = await client.get(
        f"{GRID}?start_date=2026-07-20&end_date=2026-07-23",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200, resp.text
    assert [c["status"] for c in resp.json()["cells"]] == [
        "none",
        "checked_in",
        "active_rest",
        "safety_adjustment",
    ]


@pytest.mark.asyncio
async def test_grid_never_emits_plan_execution_statuses(client):
    token = await _login_user(client, "13903000003")
    await _seed_checkins(
        client,
        token,
        [
            ("2026-07-21", "checked_in"),
            ("2026-07-22", "active_rest"),
            ("2026-07-23", "safety_adjustment"),
        ],
    )
    resp = await client.get(
        f"{GRID}?start_date=2026-07-20&end_date=2026-07-23",
        headers=_auth_header(token),
    )
    body = resp.json()
    statuses = {c["status"] for c in body["cells"]}
    assert statuses <= {"none", "checked_in", "active_rest", "safety_adjustment"}
    assert "partial_execution" not in statuses
    assert "main_plan_completed" not in statuses


# ---------------------------------------------------------------------------
# Range bounding + defaults + cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_window_is_28_days(client):
    token = await _login_user(client, "13903000004")
    resp = await client.get(GRID, headers=_auth_header(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["cells"]) == 28
    # Contiguous ascending dates.
    dates = [c["date"] for c in body["cells"]]
    assert dates == sorted(dates)


@pytest.mark.asyncio
async def test_invalid_range_order_is_422(client):
    token = await _login_user(client, "13903000005")
    resp = await client.get(
        f"{GRID}?start_date=2026-07-23&end_date=2026-07-20",
        headers=_auth_header(token),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "invalid_date_range"


@pytest.mark.asyncio
async def test_range_over_cap_is_422(client):
    token = await _login_user(client, "13903000006")
    resp = await client.get(
        f"{GRID}?start_date=2025-01-01&end_date=2026-12-31",
        headers=_auth_header(token),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "invalid_date_range"


@pytest.mark.asyncio
async def test_range_exactly_at_cap_accepted(client):
    token = await _login_user(client, "13903000007")
    # 2026-01-01 .. 2027-01-01 inclusive == 366 days (2026 is non-leap) -> ok.
    resp = await client.get(
        f"{GRID}?start_date=2026-01-01&end_date=2027-01-01",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["cells"]) == 366


@pytest.mark.asyncio
async def test_range_one_over_cap_is_422(client):
    token = await _login_user(client, "13903000008")
    # 367 inclusive days -> over cap.
    resp = await client.get(
        f"{GRID}?start_date=2026-01-01&end_date=2027-01-02",
        headers=_auth_header(token),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "invalid_date_range"


# ---------------------------------------------------------------------------
# Cross-user isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_user_isolation(client):
    token_a = await _login_user(client, "13903000010")
    token_b = await _login_user(client, "13903000011")

    await _seed_checkins(
        client, token_a, [("2026-07-21", "checked_in"), ("2026-07-22", "active_rest")]
    )

    b_grid = await client.get(
        f"{GRID}?start_date=2026-07-20&end_date=2026-07-23",
        headers=_auth_header(token_b),
    )
    assert b_grid.status_code == 200
    # B sees no check-in days -> all none.
    assert {c["status"] for c in b_grid.json()["cells"]} == {"none"}

    a_grid = await client.get(
        f"{GRID}?start_date=2026-07-20&end_date=2026-07-23",
        headers=_auth_header(token_a),
    )
    assert [c["status"] for c in a_grid.json()["cells"]] == [
        "none",
        "checked_in",
        "active_rest",
        "none",
    ]
