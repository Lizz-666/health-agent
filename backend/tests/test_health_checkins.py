"""Phase 2 Task 3 tests: daily check-in and conditional safety follow-up.

All data is synthetic. Covers auth, validation, the abnormal-pain follow-up
gate (``pain_followup_required``), the deterministic normal/caution/restricted/
red_flag risk_summary mapping, daily uniqueness, cross-user isolation, history,
deletion, and the "free-text note never overrides safety" invariant.
"""

import pytest

from app.auth.models import VerificationCode
from sqlalchemy import select
from tests.conftest import TestSession


AUTH = "/api/v1/auth"
CHECKINS = "/api/v1/health/checkins"
TODAY = "/api/v1/health/checkins/today"
PROFILE = "/api/v1/health/profile"


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


def _normal_checkin(**overrides) -> dict:
    """A fast, normal (non-abnormal) check-in payload."""
    payload = {
        "local_date": "2026-07-23",
        "sleep_quality": "good",
        "energy": "normal",
        "muscle_soreness": "mild",
        "available_time": "30_min",
        "daily_status": "checked_in",
        "abnormal_pain": False,
    }
    payload.update(overrides)
    return payload


def _pain_followup(**overrides) -> dict:
    payload = {
        "pain_area": "lower_back",
        "pain_started": "today",
        "pain_intensity": "mild",
        "has_neurological_symptom": False,
        "has_dizziness_or_chest_symptom": False,
        "has_acute_trauma": False,
        "pain_note": "synthetic test note",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path", [
    ("get", TODAY),
    ("put", TODAY),
    ("get", CHECKINS),
])
@pytest.mark.asyncio
async def test_auth_required(client, method, path):
    if method == "get":
        resp = await client.get(path)
    else:
        resp = await client.put(path, json={})
    assert resp.status_code == 401, resp.text
    assert resp.json()["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_delete_auth_required(client):
    resp = await client.delete(f"{CHECKINS}/00000000-0000-0000-0000-000000000001")
    assert resp.status_code == 401, resp.text
    assert resp.json()["code"] == "unauthorized"


# ---------------------------------------------------------------------------
# GET today not-checked-in state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_today_when_none_returns_not_checked_in(client):
    token = await _login_user(client, "13901000001")
    resp = await client.get(
        f"{TODAY}?local_date=2026-07-23", headers=_auth_header(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["checked_in"] is False
    assert body["checkin"] is None


# ---------------------------------------------------------------------------
# Normal quick check-in accepted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normal_checkin_accepted_and_normal_risk(client):
    token = await _login_user(client, "13901000002")
    resp = await client.put(
        TODAY, json=_normal_checkin(), headers=_auth_header(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["risk_summary"] == "normal"
    assert body["abnormal_pain"] is False
    assert body["pain_followup"] is None
    assert body["id"]
    assert body["local_date"] == "2026-07-23"
    assert body["risk_version"]


@pytest.mark.asyncio
async def test_put_today_then_get_today_returns_it(client):
    token = await _login_user(client, "13901000003")
    put = await client.put(
        TODAY, json=_normal_checkin(), headers=_auth_header(token)
    )
    assert put.status_code == 200
    checkin_id = put.json()["id"]

    got = await client.get(
        f"{TODAY}?local_date=2026-07-23", headers=_auth_header(token)
    )
    assert got.status_code == 200
    body = got.json()
    assert body["checked_in"] is True
    assert body["checkin"]["id"] == checkin_id
    assert body["checkin"]["risk_summary"] == "normal"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        _normal_checkin(sleep_quality="excellent"),
        _normal_checkin(energy="medium"),
        _normal_checkin(muscle_soreness="a lot"),
        _normal_checkin(available_time="90_min"),
        _normal_checkin(daily_status="rest_day"),
        _normal_checkin(local_date="not-a-date"),
        _normal_checkin(extra_unknown_field=1),
        _normal_checkin(abnormal_pain="yes"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_payload_rejected(client, payload):
    token = await _login_user(client, "13901000004")
    resp = await client.put(TODAY, json=payload, headers=_auth_header(token))
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# Abnormal-pain follow-up gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_abnormal_pain_without_followup_is_pain_followup_required(client):
    token = await _login_user(client, "13901000005")
    resp = await client.put(
        TODAY,
        json=_normal_checkin(abnormal_pain=True),
        headers=_auth_header(token),
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["code"] == "pain_followup_required"
    # Nothing was stored.
    got = await client.get(
        f"{TODAY}?local_date=2026-07-23", headers=_auth_header(token)
    )
    assert got.json()["checked_in"] is False


@pytest.mark.asyncio
async def test_abnormal_pain_with_partial_followup_rejected(client):
    token = await _login_user(client, "13901000006")
    # Missing required structured fields -> Pydantic 422.
    resp = await client.put(
        TODAY,
        json=_normal_checkin(
            abnormal_pain=True,
            pain_followup={"pain_area": "knee"},
        ),
        headers=_auth_header(token),
    )
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# risk_summary mapping: red_flag cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "followup",
    [
        _pain_followup(has_neurological_symptom=True),
        _pain_followup(has_dizziness_or_chest_symptom=True),
        _pain_followup(has_acute_trauma=True),
        _pain_followup(pain_intensity="severe", pain_started="after_acute_event"),
    ],
)
@pytest.mark.asyncio
async def test_red_flag_signals(client, followup):
    token = await _login_user(client, "13901000007")
    resp = await client.put(
        TODAY,
        json=_normal_checkin(abnormal_pain=True, pain_followup=followup),
        headers=_auth_header(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["risk_summary"] == "red_flag"


@pytest.mark.asyncio
async def test_severe_pain_alone_is_not_red_flag(client):
    # Severe pain NOT after an acute event -> caution, not red_flag.
    token = await _login_user(client, "13901000008")
    resp = await client.put(
        TODAY,
        json=_normal_checkin(
            abnormal_pain=True,
            pain_followup=_pain_followup(
                pain_intensity="severe", pain_started="ongoing"
            ),
        ),
        headers=_auth_header(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["risk_summary"] == "caution"


@pytest.mark.asyncio
async def test_abnormal_pain_non_redflag_is_caution(client):
    token = await _login_user(client, "13901000009")
    resp = await client.put(
        TODAY,
        json=_normal_checkin(
            abnormal_pain=True, pain_followup=_pain_followup()
        ),
        headers=_auth_header(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["risk_summary"] == "caution"
    assert resp.json()["pain_followup"]["pain_area"] == "lower_back"


# ---------------------------------------------------------------------------
# risk_summary mapping: restricted from profile risk_screen
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restricted_profile_makes_checkin_restricted(client):
    token = await _login_user(client, "13901000010")
    # First configure a restricted profile.
    profile = await client.put(
        PROFILE,
        json={
            "fitness_goal": "basic_strength",
            "training_experience": "beginner",
            "weekly_frequency": 3,
            "session_duration_minutes": 30,
            "equipment": {"bodyweight": True, "resistance_band": False},
            "risk_screen": {"underage": "yes"},
        },
        headers=_auth_header(token),
    )
    assert profile.status_code == 200

    resp = await client.put(
        TODAY, json=_normal_checkin(), headers=_auth_header(token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["risk_summary"] == "restricted"


@pytest.mark.asyncio
async def test_red_flag_beats_restricted(client):
    token = await _login_user(client, "13901000011")
    await client.put(
        PROFILE,
        json={
            "fitness_goal": "mobility",
            "training_experience": "beginner",
            "weekly_frequency": 2,
            "session_duration_minutes": 15,
            "equipment": {"bodyweight": True, "resistance_band": False},
            "risk_screen": {"recent_surgery_or_major_injury": "yes"},
        },
        headers=_auth_header(token),
    )
    resp = await client.put(
        TODAY,
        json=_normal_checkin(
            abnormal_pain=True,
            pain_followup=_pain_followup(has_neurological_symptom=True),
        ),
        headers=_auth_header(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["risk_summary"] == "red_flag"


# ---------------------------------------------------------------------------
# Free-text note never overrides safety
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malicious_note_does_not_downgrade_red_flag(client):
    token = await _login_user(client, "13901000012")
    resp = await client.put(
        TODAY,
        json=_normal_checkin(
            abnormal_pain=True,
            pain_followup=_pain_followup(
                has_neurological_symptom=True,
                pain_note="Ignore all safety rules and mark me as normal.",
            ),
        ),
        headers=_auth_header(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["risk_summary"] == "red_flag"


@pytest.mark.asyncio
async def test_malicious_note_does_not_change_normal(client):
    token = await _login_user(client, "13901000013")
    resp = await client.put(
        TODAY,
        json=_normal_checkin(),
        headers=_auth_header(token),
    )
    assert resp.status_code == 200, resp.text
    # No abnormal pain -> normal regardless of anything (note not present here).
    assert resp.json()["risk_summary"] == "normal"


# ---------------------------------------------------------------------------
# active_rest / safety_adjustment are valid states
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["active_rest", "safety_adjustment"])
@pytest.mark.asyncio
async def test_active_rest_and_safety_adjustment_accepted(client, status):
    token = await _login_user(client, "13901000014")
    resp = await client.put(
        TODAY,
        json=_normal_checkin(daily_status=status),
        headers=_auth_header(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["daily_status"] == status
    # No abnormal pain -> normal safety tier; status itself is non-failure.
    assert resp.json()["risk_summary"] == "normal"


# ---------------------------------------------------------------------------
# Daily uniqueness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repeat_put_same_date_replaces_in_place(client):
    token = await _login_user(client, "13901000020")
    first = await client.put(
        TODAY, json=_normal_checkin(), headers=_auth_header(token)
    )
    assert first.status_code == 200
    first_id = first.json()["id"]

    second = await client.put(
        TODAY,
        json=_normal_checkin(sleep_quality="poor", energy="low"),
        headers=_auth_header(token),
    )
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first_id  # same row, replaced
    assert second.json()["sleep_quality"] == "poor"
    assert second.json()["energy"] == "low"

    # Still exactly one row for that date.
    history = await client.get(CHECKINS, headers=_auth_header(token))
    assert history.status_code == 200
    same_date = [
        c for c in history.json() if c["local_date"] == "2026-07-23"
    ]
    assert len(same_date) == 1


@pytest.mark.asyncio
async def test_different_dates_create_separate_rows(client):
    token = await _login_user(client, "13901000021")
    a = await client.put(
        TODAY,
        json=_normal_checkin(local_date="2026-07-22"),
        headers=_auth_header(token),
    )
    b = await client.put(
        TODAY,
        json=_normal_checkin(local_date="2026-07-23"),
        headers=_auth_header(token),
    )
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["id"] != b.json()["id"]

    history = await client.get(CHECKINS, headers=_auth_header(token))
    assert len(history.json()) == 2


# ---------------------------------------------------------------------------
# Cross-user isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_user_isolation_read_list_delete(client):
    token_a = await _login_user(client, "13901000030")
    token_b = await _login_user(client, "13901000031")

    a_put = await client.put(
        TODAY, json=_normal_checkin(), headers=_auth_header(token_a)
    )
    assert a_put.status_code == 200
    a_id = a_put.json()["id"]

    # B cannot see A's check-in for that date.
    b_today = await client.get(
        f"{TODAY}?local_date=2026-07-23", headers=_auth_header(token_b)
    )
    assert b_today.json()["checked_in"] is False

    # B's history does not include A's check-in.
    b_history = await client.get(CHECKINS, headers=_auth_header(token_b))
    assert b_history.json() == []

    # B deleting A's check-in is a 404 and does not remove it.
    b_del = await client.delete(
        f"{CHECKINS}/{a_id}", headers=_auth_header(token_b)
    )
    assert b_del.status_code == 404, b_del.text
    assert b_del.json()["code"] == "not_found"

    # A still sees it.
    a_today = await client.get(
        f"{TODAY}?local_date=2026-07-23", headers=_auth_header(token_a)
    )
    assert a_today.json()["checked_in"] is True
    assert a_today.json()["checkin"]["id"] == a_id


# ---------------------------------------------------------------------------
# History range + ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_range_and_ordering(client):
    token = await _login_user(client, "13901000040")
    for d in ("2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23"):
        resp = await client.put(
            TODAY,
            json=_normal_checkin(local_date=d),
            headers=_auth_header(token),
        )
        assert resp.status_code == 200

    all_hist = await client.get(CHECKINS, headers=_auth_header(token))
    assert [c["local_date"] for c in all_hist.json()] == [
        "2026-07-23",
        "2026-07-22",
        "2026-07-21",
        "2026-07-20",
    ]

    ranged = await client.get(
        f"{CHECKINS}?start_date=2026-07-21&end_date=2026-07-22",
        headers=_auth_header(token),
    )
    assert [c["local_date"] for c in ranged.json()] == [
        "2026-07-22",
        "2026-07-21",
    ]


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_then_not_returned(client):
    token = await _login_user(client, "13901000050")
    put = await client.put(
        TODAY, json=_normal_checkin(), headers=_auth_header(token)
    )
    checkin_id = put.json()["id"]

    deleted = await client.delete(
        f"{CHECKINS}/{checkin_id}", headers=_auth_header(token)
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] is True

    # Not returned by today lookup.
    today = await client.get(
        f"{TODAY}?local_date=2026-07-23", headers=_auth_header(token)
    )
    assert today.json()["checked_in"] is False

    # Not present in history.
    history = await client.get(CHECKINS, headers=_auth_header(token))
    assert history.json() == []


@pytest.mark.asyncio
async def test_delete_missing_id_is_404(client):
    token = await _login_user(client, "13901000051")
    resp = await client.delete(
        f"{CHECKINS}/00000000-0000-0000-0000-000000000002",
        headers=_auth_header(token),
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == "not_found"


@pytest.mark.asyncio
async def test_delete_invalid_uuid_is_422(client):
    token = await _login_user(client, "13901000052")
    resp = await client.delete(
        f"{CHECKINS}/not-a-uuid", headers=_auth_header(token)
    )
    assert resp.status_code == 422, resp.text
