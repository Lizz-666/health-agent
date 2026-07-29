"""Phase 2 Task 4 tests: manual weight CRUD, trend calculation, and bounds.

All data is synthetic. Covers auth, weight bounds, create/list/update/delete,
cross-user isolation, deleted-not-returned, the deterministic insufficient_data
/ sufficient moving-trend behavior with exact SMA values, date-range bounding,
and the "no recommendation text" invariant.
"""

import pytest

import app.agent.models  # noqa: F401  (Phase 5 spy test needs the Agent tables)
from app.auth.models import VerificationCode
from sqlalchemy import select
from tests.conftest import TestSession


AUTH = "/api/v1/auth"
WEIGHT = "/api/v1/health/weight-records"
TREND = "/api/v1/health/trends/weight"


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


def _record(weight: float, at: str = "2026-07-23T08:00:00", note=None, **extra) -> dict:
    payload = {"recorded_at": at, "weight_kg": weight}
    if note is not None:
        payload["note"] = note
    payload.update(extra)
    return payload


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path", [
    ("get", WEIGHT),
    ("post", WEIGHT),
])
@pytest.mark.asyncio
async def test_auth_required(client, method, path):
    if method == "get":
        resp = await client.get(path)
    else:
        resp = await client.post(path, json={})
    assert resp.status_code == 401, resp.text
    assert resp.json()["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_update_delete_auth_required(client):
    rid = "00000000-0000-0000-0000-000000000001"
    assert (await client.put(f"{WEIGHT}/{rid}", json={})).status_code == 401
    assert (await client.delete(f"{WEIGHT}/{rid}")).status_code == 401


# ---------------------------------------------------------------------------
# Create + bounds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_returns_manual_source(client):
    token = await _login_user(client, "13902000001")
    resp = await client.post(
        WEIGHT, json=_record(70.5), headers=_auth_header(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["weight_kg"] == 70.5
    assert body["source"] == "manual"  # server-set
    assert body["id"]
    assert body["recorded_at"].startswith("2026-07-23T08:00:00")


@pytest.mark.parametrize("weight", [19.9, 300.1, 0, -5.0, 9999])
@pytest.mark.asyncio
async def test_create_rejects_out_of_bounds(client, weight):
    token = await _login_user(client, "13902000002")
    resp = await client.post(
        WEIGHT, json=_record(weight), headers=_auth_header(token)
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize("weight", [20.0, 300.0, 75.25])
@pytest.mark.asyncio
async def test_create_accepts_boundary_values(client, weight):
    token = await _login_user(client, "13902000003")
    resp = await client.post(
        WEIGHT, json=_record(weight), headers=_auth_header(token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["weight_kg"] == weight


@pytest.mark.asyncio
async def test_create_rejects_nonnumeric_weight(client):
    token = await _login_user(client, "13902000004")
    resp = await client.post(
        WEIGHT,
        json={"recorded_at": "2026-07-23T08:00:00", "weight_kg": "heavy"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_create_rejects_client_source(client):
    token = await _login_user(client, "13902000005")
    # extra="forbid" rejects a client-supplied source.
    resp = await client.post(
        WEIGHT,
        json={"recorded_at": "2026-07-23T08:00:00", "weight_kg": 70.0, "source": "scale"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# List + ordering + range bounding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_newest_first_and_range_filter(client):
    token = await _login_user(client, "13902000010")
    for at in (
        "2026-07-20T08:00:00",
        "2026-07-21T08:00:00",
        "2026-07-22T08:00:00",
        "2026-07-23T08:00:00",
    ):
        r = await client.post(WEIGHT, json=_record(70.0, at=at), headers=_auth_header(token))
        assert r.status_code == 200

    all_resp = await client.get(WEIGHT, headers=_auth_header(token))
    assert all_resp.status_code == 200
    assert [c["recorded_at"][:10] for c in all_resp.json()] == [
        "2026-07-23",
        "2026-07-22",
        "2026-07-21",
        "2026-07-20",
    ]

    ranged = await client.get(
        f"{WEIGHT}?start_date=2026-07-21&end_date=2026-07-22",
        headers=_auth_header(token),
    )
    assert [c["recorded_at"][:10] for c in ranged.json()] == [
        "2026-07-22",
        "2026-07-21",
    ]


# ---------------------------------------------------------------------------
# Update / Delete + ownership
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_replaces_fields(client):
    token = await _login_user(client, "13902000020")
    created = await client.post(
        WEIGHT, json=_record(70.0), headers=_auth_header(token)
    )
    rid = created.json()["id"]

    updated = await client.put(
        f"{WEIGHT}/{rid}",
        json=_record(71.2, at="2026-07-24T09:00:00", note="updated"),
        headers=_auth_header(token),
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["weight_kg"] == 71.2
    assert body["recorded_at"].startswith("2026-07-24T09:00:00")
    assert body["note"] == "updated"
    assert body["source"] == "manual"


@pytest.mark.asyncio
async def test_delete_then_not_returned(client):
    token = await _login_user(client, "13902000021")
    created = await client.post(
        WEIGHT, json=_record(70.0), headers=_auth_header(token)
    )
    rid = created.json()["id"]

    deleted = await client.delete(f"{WEIGHT}/{rid}", headers=_auth_header(token))
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] is True

    listed = await client.get(WEIGHT, headers=_auth_header(token))
    assert listed.json() == []


@pytest.mark.asyncio
async def test_update_delete_missing_is_404(client):
    token = await _login_user(client, "13902000022")
    rid = "00000000-0000-0000-0000-000000000002"
    upd = await client.put(
        f"{WEIGHT}/{rid}", json=_record(70.0), headers=_auth_header(token)
    )
    assert upd.status_code == 404
    assert upd.json()["code"] == "not_found"
    dele = await client.delete(f"{WEIGHT}/{rid}", headers=_auth_header(token))
    assert dele.status_code == 404
    assert dele.json()["code"] == "not_found"


@pytest.mark.asyncio
async def test_invalid_uuid_is_422(client):
    token = await _login_user(client, "13902000023")
    assert (
        await client.delete(f"{WEIGHT}/not-a-uuid", headers=_auth_header(token))
    ).status_code == 422


@pytest.mark.asyncio
async def test_cross_user_isolation(client):
    token_a = await _login_user(client, "13902000030")
    token_b = await _login_user(client, "13902000031")

    a_created = await client.post(
        WEIGHT, json=_record(70.0), headers=_auth_header(token_a)
    )
    a_id = a_created.json()["id"]

    # B cannot see A's records.
    b_list = await client.get(WEIGHT, headers=_auth_header(token_b))
    assert b_list.json() == []

    # B cannot update or delete A's record -> 404, A still has it.
    assert (
        await client.put(
            f"{WEIGHT}/{a_id}", json=_record(99.0), headers=_auth_header(token_b)
        )
    ).status_code == 404
    assert (
        await client.delete(f"{WEIGHT}/{a_id}", headers=_auth_header(token_b))
    ).status_code == 404

    a_list = await client.get(WEIGHT, headers=_auth_header(token_a))
    assert len(a_list.json()) == 1
    assert a_list.json()[0]["id"] == a_id


# ---------------------------------------------------------------------------
# Trend: insufficient_data + deterministic moving average
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trend_insufficient_when_below_window(client):
    token = await _login_user(client, "13902000040")
    # Default window is 7; provide fewer than 7 records.
    for at in ("2026-07-21T08:00:00", "2026-07-22T08:00:00", "2026-07-23T08:00:00"):
        await client.post(WEIGHT, json=_record(70.0, at=at), headers=_auth_header(token))

    resp = await client.get(TREND, headers=_auth_header(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sufficient"] is False
    assert body["trend"] == []
    assert body["window"] == 7
    # Raw records are still returned.
    assert len(body["records"]) == 3


@pytest.mark.asyncio
async def test_trend_moving_average_is_deterministic(client):
    token = await _login_user(client, "13902000041")
    # 3 records with window=2 -> two trend points:
    #   avg(70.0,71.0)=70.5 ; avg(71.0,72.0)=71.5
    for w, at in (
        (70.0, "2026-07-21T08:00:00"),
        (71.0, "2026-07-22T08:00:00"),
        (72.0, "2026-07-23T08:00:00"),
    ):
        await client.post(WEIGHT, json=_record(w, at=at), headers=_auth_header(token))

    resp = await client.get(f"{TREND}?window=2", headers=_auth_header(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sufficient"] is True
    assert body["window"] == 2
    assert [p["weight_kg"] for p in body["trend"]] == [70.5, 71.5]
    assert [p["recorded_at"][:10] for p in body["trend"]] == [
        "2026-07-22",
        "2026-07-23",
    ]


@pytest.mark.asyncio
async def test_trend_window_default_and_bounds(client):
    token = await _login_user(client, "13902000042")
    # Default window 7.
    resp = await client.get(TREND, headers=_auth_header(token))
    assert resp.json()["window"] == 7

    # Out-of-range window -> 422.
    assert (
        await client.get(f"{TREND}?window=1", headers=_auth_header(token))
    ).status_code == 422
    assert (
        await client.get(f"{TREND}?window=15", headers=_auth_header(token))
    ).status_code == 422


@pytest.mark.asyncio
async def test_trend_range_bounding(client):
    token = await _login_user(client, "13902000043")
    for w, at in (
        (70.0, "2026-07-20T08:00:00"),
        (71.0, "2026-07-21T08:00:00"),
        (72.0, "2026-07-22T08:00:00"),
        (73.0, "2026-07-23T08:00:00"),
    ):
        await client.post(WEIGHT, json=_record(w, at=at), headers=_auth_header(token))

    # Range window=2 over only the middle two days -> one trend point 71.5.
    resp = await client.get(
        f"{TREND}?start_date=2026-07-21&end_date=2026-07-22&window=2",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [r["recorded_at"][:10] for r in body["records"]] == [
        "2026-07-21",
        "2026-07-22",
    ]
    assert [p["weight_kg"] for p in body["trend"]] == [71.5]


@pytest.mark.asyncio
async def test_trend_emits_no_recommendation_text(client):
    token = await _login_user(client, "13902000044")
    for w, at in (
        (70.0, "2026-07-21T08:00:00"),
        (75.0, "2026-07-22T08:00:00"),
        (80.0, "2026-07-23T08:00:00"),
    ):
        await client.post(WEIGHT, json=_record(w, at=at), headers=_auth_header(token))

    resp = await client.get(f"{TREND}?window=2", headers=_auth_header(token))
    body = resp.json()
    serialized = str(body)
    forbidden = ("建议", "adjustment", "warning", "pass", "fail", "diet", "calorie")
    for word in forbidden:
        assert word.lower() not in serialized.lower(), (
            f"trend response leaked judgment/advice text: {word}"
        )
    # Schema is exactly records/trend/window/sufficient.
    assert set(body.keys()) == {"records", "trend", "window", "sufficient"}


# ---------------------------------------------------------------------------
# Phase 5 Task 3: chat and button share the transaction-neutral core.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_weight_button_and_agent_share_transaction_neutral_core(monkeypatch):
    """Both the committing API wrapper and the Agent confirmation executor call
    the same ``create_weight_record_core`` (ADR-0003; spec Write Confirmation)."""
    import uuid as _uuid
    from datetime import datetime, timezone

    import app.health.service as hsvc
    from app.agent import action_tools as at
    from app.agent import persistence as ap
    from app.agent import schemas as S
    from app.auth.models import User
    from app.core.config import settings
    from app.health.schemas import WeightRecordCreate

    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY", "spy-key-0123456789abcdef")
    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY_VERSION", "v1")

    calls = []
    real = hsvc.create_weight_record_core

    async def spy(db, user_id, data):
        calls.append("core")
        return await real(db, user_id, data)

    monkeypatch.setattr(hsvc, "create_weight_record_core", spy)
    # Also patch the symbol the Agent module bound at import time.
    monkeypatch.setattr(at, "create_weight_record_core", spy, raising=False)

    async with TestSession() as db:
        user = User(phone="139" + _uuid.uuid4().hex[:8])
        db.add(user)
        await db.flush()
        uid = str(user.id)
        await ap.grant_consent(
            db, uid, accepted_provider_id="prov", accepted_disclosure_version="d1",
            current_provider_id="prov", current_disclosure_version="d1",
            idempotency_key="ck",
        )
        # Button path: the committing wrapper calls the core.
        await hsvc.create_weight_record(
            db, uid, WeightRecordCreate(recorded_at=datetime.now(timezone.utc), weight_kg=70.0)
        )
        assert calls.count("core") == 1

        # Agent path: build a proposal then confirm; the executor calls the core.
        args = S.CreateWeightRecordArguments(
            recorded_at=datetime.now(timezone.utc), weight_kg=71.0
        )
        afp = at.compute_arguments_fingerprint(args)
        prepared = await at.prepare(db, S.CREATE_WEIGHT_RECORD, args, uid, iana_timezone="Asia/Shanghai")
        cfp = at.compute_context_fingerprint(prepared.context_fingerprint_payload)
        run = (await ap.record_run(db, uid, client_turn_id="t1", entry_type="general")).run
        prop = await ap.create_proposal(
            db, run_id=run.run_id, user_id=uid, tool_name=S.CREATE_WEIGHT_RECORD,
            arguments_json=args.model_dump(mode="json"), arguments_hash=afp.value,
            context_fingerprint=cfp.value, fingerprint_key_version=cfp.key_version,
        )
        await db.commit()
        res = await ap.confirm_proposal(db, uid, prop.proposal_id, idempotency_key="c1", iana_timezone="Asia/Shanghai")
        assert res.status == "executed"
        assert calls.count("core") == 2  # button + agent both used the core
