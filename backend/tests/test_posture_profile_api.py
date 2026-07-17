"""Phase 1 Task 4: posture profile read API (spec §9.2).

Covers ``GET /api/v1/posture/profile`` and ``GET /api/v1/posture/profile/{issue_id}``:

* empty profile -> no evaluated issues + all knowledge categories unevaluated;
* a confirmed self-test entry surfaces correctly;
* a conflict projection -> certainty=conflict, has_conflict=true,
  combined_severity=null (no auto-merge);
* a provisional projection -> combined_severity=null;
* certainty-keyed summary counts;
* unevaluated categories exclude evaluated categories;
* ``sources`` never leak ``photo_keys`` / photo URLs / raw ``ai_response``;
* cross-user isolation: identity is JWT-only (no user_id param), so one user
  can never read another user's profile or single-issue entry;
* single-issue detail: found / issue_not_found / profile_entry_not_found;
* auth required.
"""

import pytest
from sqlalchemy import select

from app.auth.models import VerificationCode
from app.posture import service
from tests.conftest import TestSession


# All knowledge categories, sorted (mirrors service._all_knowledge_categories).
ALL_CATEGORIES = ["compound", "head_neck", "lower_limb", "pelvis_spine", "shoulder_thorax"]

# Exact key sets the response contract must expose (drives Flutter Task 8).
TOP_LEVEL_KEYS = {"user_id", "evaluated_issues", "unevaluated_categories", "summary"}
SUMMARY_KEYS = {"total_evaluated", "total_conflict", "total_provisional"}
ENTRY_KEYS = {
    "issue_id",
    "issue_name",
    "category",
    "combined_severity",
    "certainty",
    "has_conflict",
    "sources",
    "risk_tier",
    "risk_version",
    "updated_at",
}
# The only keys a source object may carry (privacy: no photo_keys / ai_response).
SOURCE_KEYS = {"source", "event_id", "severity", "created_at"}


async def _login_user(client, phone="13800138000"):
    await client.post("/api/v1/auth/send-code", json={"phone": phone})
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


def _ai_result(level, **overrides):
    base = {
        "level": level,
        "confidence": 0.82,
        "evidence": ["evidence"],
        "suggestion": "建议",
        "need_retake": False,
        "retake_reason": "",
    }
    base.update(overrides)
    return base


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


async def _assess_self(client, token, issue_id, answer="positive", test_index=0):
    return await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": issue_id, "test_index": test_index, "answer": answer},
        headers=_headers(token),
    )


# ===========================================================================
# GET /profile
# ===========================================================================


@pytest.mark.asyncio
async def test_profile_requires_auth(client):
    resp = await client.get("/api/v1/posture/profile")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_empty_profile_returns_no_entries_and_all_categories(client):
    token = await _login_user(client)
    resp = await client.get("/api/v1/posture/profile", headers=_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == TOP_LEVEL_KEYS
    assert body["evaluated_issues"] == []
    assert body["unevaluated_categories"] == ALL_CATEGORIES
    assert body["summary"] == {
        "total_evaluated": 0,
        "total_conflict": 0,
        "total_provisional": 0,
    }


@pytest.mark.asyncio
async def test_confirmed_self_test_entry_appears(client):
    token = await _login_user(client)
    resp = await _assess_self(client, token, "HN-01", answer="positive")
    assert resp.status_code == 200

    resp = await client.get("/api/v1/posture/profile", headers=_headers(token))
    assert resp.status_code == 200
    body = resp.json()

    assert len(body["evaluated_issues"]) == 1
    entry = body["evaluated_issues"][0]
    assert set(entry.keys()) == ENTRY_KEYS
    assert entry["issue_id"] == "HN-01"
    assert entry["issue_name"] == "头部前倾"
    assert entry["category"] == "head_neck"
    assert entry["combined_severity"] == "moderate"
    assert entry["certainty"] == "confirmed"
    assert entry["has_conflict"] is False
    assert entry["risk_tier"] == "normal"
    assert entry["risk_version"] == "phase1-initial-v1"

    assert len(entry["sources"]) == 1
    src = entry["sources"][0]
    assert set(src.keys()) == SOURCE_KEYS
    assert src["source"] == "self_test"
    assert src["severity"] == "moderate"

    # head_neck is now evaluated -> dropped from unevaluated.
    assert "head_neck" not in body["unevaluated_categories"]
    assert body["summary"] == {
        "total_evaluated": 1,
        "total_conflict": 0,
        "total_provisional": 0,
    }


@pytest.mark.asyncio
async def test_conflict_entry_has_null_combined_and_flag(client):
    """self_test moderate + photo severe -> conflict, combined_severity=null."""
    from app.core.security import decode_token

    token = await _login_user(client)
    user_id = decode_token(token)["sub"]
    await _assess_self(client, token, "ST-04", answer="positive")
    async with TestSession() as db:
        await service.save_photo_assessment(
            db, user_id, "ST-04", ["fake.jpg"], _ai_result("severe")
        )

    resp = await client.get("/api/v1/posture/profile", headers=_headers(token))
    assert resp.status_code == 200
    entries = resp.json()["evaluated_issues"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["issue_id"] == "ST-04"
    assert entry["certainty"] == "conflict"
    assert entry["has_conflict"] is True
    assert entry["combined_severity"] is None

    # Two contributing sources, newest-first.
    assert len(entry["sources"]) == 2
    for src in entry["sources"]:
        assert set(src.keys()) == SOURCE_KEYS
    assert {s["source"] for s in entry["sources"]} == {"self_test", "ai_photo"}


@pytest.mark.asyncio
async def test_provisional_entry_has_null_combined(client):
    """A single uncertain self-test -> severity null -> provisional."""
    token = await _login_user(client)
    await _assess_self(client, token, "PS-13", answer="uncertain")

    resp = await client.get("/api/v1/posture/profile", headers=_headers(token))
    assert resp.status_code == 200
    entries = resp.json()["evaluated_issues"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["issue_id"] == "PS-13"
    assert entry["certainty"] == "provisional"
    assert entry["combined_severity"] is None
    assert entry["has_conflict"] is False


@pytest.mark.asyncio
async def test_summary_counts_and_unevaluated_categories(client):
    """3 evaluated issues across 3 categories:
    HN-01 confirmed, ST-04 conflict, PS-13 provisional."""
    from app.core.security import decode_token

    token = await _login_user(client)
    user_id = decode_token(token)["sub"]

    # HN-01 (head_neck): confirmed
    await _assess_self(client, token, "HN-01", answer="positive")
    # ST-04 (shoulder_thorax): conflict
    await _assess_self(client, token, "ST-04", answer="positive")
    async with TestSession() as db:
        await service.save_photo_assessment(
            db, user_id, "ST-04", ["fake.jpg"], _ai_result("severe")
        )
    # PS-13 (pelvis_spine): provisional
    await _assess_self(client, token, "PS-13", answer="uncertain")

    resp = await client.get("/api/v1/posture/profile", headers=_headers(token))
    assert resp.status_code == 200
    body = resp.json()

    assert body["summary"] == {
        "total_evaluated": 3,
        "total_conflict": 1,
        "total_provisional": 1,
    }
    # evaluated: head_neck, shoulder_thorax, pelvis_spine
    # unevaluated: compound, lower_limb
    assert body["unevaluated_categories"] == ["compound", "lower_limb"]


@pytest.mark.asyncio
async def test_sources_never_leak_photo_keys_or_raw_ai(client):
    """Every source object must carry only the 4 safe keys -- never
    photo_keys, photo URLs, confidence or the raw ai_response."""
    from app.core.security import decode_token

    token = await _login_user(client)
    user_id = decode_token(token)["sub"]
    await _assess_self(client, token, "HN-01", answer="positive")
    async with TestSession() as db:
        await service.save_photo_assessment(
            db, user_id, "HN-01", ["secret-photo-key.jpg"], _ai_result("moderate")
        )

    resp = await client.get("/api/v1/posture/profile", headers=_headers(token))
    assert resp.status_code == 200
    serialized = resp.text
    # raw health payloads / photo object keys must not appear in the response.
    assert "secret-photo-key.jpg" not in serialized
    assert "ai_response" not in serialized
    assert "photo_keys" not in serialized
    assert "photo_url" not in serialized

    for entry in resp.json()["evaluated_issues"]:
        for src in entry["sources"]:
            assert set(src.keys()) == SOURCE_KEYS
            assert "confidence" not in src


@pytest.mark.asyncio
async def test_cross_user_isolation_on_profile(client):
    """User B must never see user A's evaluated issues."""
    token_a = await _login_user(client, phone="13800138000")
    await _assess_self(client, token_a, "HN-01", answer="positive")

    token_b = await _login_user(client, phone="13900139000")
    resp = await client.get("/api/v1/posture/profile", headers=_headers(token_b))
    assert resp.status_code == 200
    body = resp.json()
    assert body["evaluated_issues"] == []
    assert body["summary"]["total_evaluated"] == 0
    # user_id in the response is user B's, never user A's.
    assert body["user_id"] != ""


# ===========================================================================
# GET /profile/{issue_id}
# ===========================================================================


@pytest.mark.asyncio
async def test_entry_detail_requires_auth(client):
    resp = await client.get("/api/v1/posture/profile/HN-01")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_entry_detail_found(client):
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="positive")

    resp = await client.get("/api/v1/posture/profile/HN-01", headers=_headers(token))
    assert resp.status_code == 200
    entry = resp.json()
    assert set(entry.keys()) == ENTRY_KEYS
    assert entry["issue_id"] == "HN-01"
    assert entry["issue_name"] == "头部前倾"
    assert entry["category"] == "head_neck"
    assert entry["certainty"] == "confirmed"
    assert entry["combined_severity"] == "moderate"
    assert "related_priority" not in entry  # out of scope (Task 6)


@pytest.mark.asyncio
async def test_entry_detail_issue_not_found(client):
    token = await _login_user(client)
    resp = await client.get(
        "/api/v1/posture/profile/NOPE-99", headers=_headers(token)
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "issue_not_found"
    assert "detail" in body


@pytest.mark.asyncio
async def test_entry_detail_not_evaluated_returns_404(client):
    """A known-but-unassessed issue -> profile_entry_not_found (must not leak
    whether any other user has data)."""
    token = await _login_user(client)
    resp = await client.get("/api/v1/posture/profile/LL-21", headers=_headers(token))
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "profile_entry_not_found"


@pytest.mark.asyncio
async def test_entry_detail_cross_user_isolation(client):
    """User A has HN-01; user B requesting it gets profile_entry_not_found,
    not A's data."""
    token_a = await _login_user(client, phone="13800138000")
    await _assess_self(client, token_a, "HN-01", answer="positive")

    token_b = await _login_user(client, phone="13900139000")
    resp = await client.get("/api/v1/posture/profile/HN-01", headers=_headers(token_b))
    assert resp.status_code == 404
    assert resp.json()["code"] == "profile_entry_not_found"
