"""Phase 1 Task 5: conflict-state audit coverage (spec §6.3 / §6.4 / §11.1).

The conflict projection itself lives in ``service.project_profile`` (Task 2)
and is already complete and correct; ``/profile`` exposes it (Task 4). This
file is the authoritative §11.1 conflict-rule test matrix plus the rebuild /
no-auto-merge evidence called for by plan Task 5 -- it fills the test gap
without re-implementing production logic.

Coverage:

* the full §11.1 two-source table -- every equal / disagreeing (incl. 1-level)
  / null-involving combination -> (certainty, combined_severity);
* single-source (self_test AND ai_photo) at every severity -> confirmed;
* the §11.1 "关键规则": there is NO "差1级取更严重" merge -- a conflict's
  ``combined_severity`` is always ``None`` (never ``max`` of the inputs);
* DB-level conflict resolution: conflict -> reassess one source to match ->
  rebuilds to confirmed, proving rebuild-from-latest-per-source, no stale
  conflict and no auto-merge code path.
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import select

from app.auth.models import VerificationCode
from app.posture import service
from app.posture.models import PostureProfileEntry
from app.posture.service import project_profile
from tests.conftest import TestSession


_TS = datetime(2026, 7, 11, 10, 0, 0, tzinfo=timezone.utc)
LEVELS = ["normal", "mild", "moderate", "severe"]


def _ev(source, severity, idx):
    """A latest-per-source event dict for the pure projection tests."""
    return {"source": source, "severity": severity, "id": f"id-{idx}", "created_at": _TS}


# (self_test severity, ai_photo severity, expected certainty, expected combined)
# Mirrors the spec §11.1 table verbatim.
_TWO_SOURCE_MATRIX = [
    # --- all non-null and equal -> confirmed, combined = common value ---
    ("normal", "normal", "confirmed", "normal"),
    ("mild", "mild", "confirmed", "mild"),
    ("moderate", "moderate", "confirmed", "moderate"),
    ("severe", "severe", "confirmed", "severe"),
    # --- non-null disagreement -> conflict, combined = null (incl. 1-level) ---
    ("normal", "mild", "conflict", None),
    ("mild", "moderate", "conflict", None),  # 1-level apart is still conflict
    ("moderate", "severe", "conflict", None),  # 1-level apart is still conflict
    ("normal", "moderate", "conflict", None),
    ("normal", "severe", "conflict", None),
    ("mild", "severe", "conflict", None),
    # --- any null source -> provisional, combined = null ---
    (None, "moderate", "provisional", None),
    ("moderate", None, "provisional", None),
    (None, None, "provisional", None),
]


_TWO_SOURCE_IDS = [
    f"{s or 'null'}__{p or 'null'}->{c}" for s, p, c, _ in _TWO_SOURCE_MATRIX
]


@pytest.mark.parametrize(
    "self_sev,photo_sev,expected_certainty,expected_combined",
    _TWO_SOURCE_MATRIX,
    ids=_TWO_SOURCE_IDS,
)
def test_two_source_combination_matches_spec_table(
    self_sev, photo_sev, expected_certainty, expected_combined
):
    """Every §11.1 two-source row projects to the spec-mandated
    (certainty, combined_severity)."""
    events = [_ev("self_test", self_sev, 1), _ev("ai_photo", photo_sev, 2)]
    out = project_profile(events)
    assert out["certainty"] == expected_certainty
    assert out["combined_severity"] == expected_combined
    assert out["has_conflict"] == (expected_certainty == "conflict")


_SINGLE_SOURCE_IDS = [f"{src}-{sev}" for src in ("self_test", "ai_photo") for sev in LEVELS]


@pytest.mark.parametrize(
    "source,severity",
    [(src, sev) for src in ("self_test", "ai_photo") for sev in LEVELS],
    ids=_SINGLE_SOURCE_IDS,
)
def test_single_source_is_confirmed(source, severity):
    """§11.1: a single source (self_test OR ai_photo) at any severity is
    confirmed with combined_severity equal to that severity."""
    out = project_profile([_ev(source, severity, 1)])
    assert out["certainty"] == "confirmed"
    assert out["combined_severity"] == severity
    assert out["has_conflict"] is False


@pytest.mark.parametrize(
    "self_sev,photo_sev",
    [
        ("normal", "mild"),
        ("mild", "moderate"),  # 1-level apart
        ("moderate", "severe"),  # 1-level apart
        ("normal", "severe"),
    ],
    ids=["normal-mild", "mild-moderate", "moderate-severe", "normal-severe"],
)
def test_conflict_never_takes_more_severe(self_sev, photo_sev):
    """§11.1 关键规则: there is NO '差1级取更严重并 confirmed' rule. A
    disagreement always yields conflict with combined_severity == None --
    never ``max(self, photo)`` and never one of the input severities."""
    out = project_profile(
        [_ev("self_test", self_sev, 1), _ev("ai_photo", photo_sev, 2)]
    )
    assert out["certainty"] == "conflict"
    assert out["has_conflict"] is True
    assert out["combined_severity"] is None
    assert out["combined_severity"] not in (self_sev, photo_sev)


def test_equal_non_null_pair_keeps_common_severity_not_conflict():
    """Two agreeing non-null sources must NOT be flagged as a conflict."""
    out = project_profile(
        [_ev("self_test", "moderate", 1), _ev("ai_photo", "moderate", 2)]
    )
    assert out["certainty"] == "confirmed"
    assert out["combined_severity"] == "moderate"
    assert out["has_conflict"] is False


# ===========================================================================
# DB-level: conflict resolution / rebuild (spec §11.1, plan Task 5)
# ===========================================================================


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


def _ai_result(level):
    return {
        "level": level,
        "confidence": 0.8,
        "evidence": ["evidence"],
        "suggestion": "建议",
        "need_retake": False,
        "retake_reason": "",
    }


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


async def _profile_for(issue_id):
    async with TestSession() as db:
        result = await db.execute(
            select(PostureProfileEntry).where(PostureProfileEntry.issue_id == issue_id)
        )
        return result.scalar_one_or_none()


async def _profile_count():
    async with TestSession() as db:
        result = await db.execute(select(PostureProfileEntry))
        return len(result.scalars().all())


@pytest.mark.asyncio
async def test_conflict_resolves_to_confirmed_when_photo_reassessed_to_match(client):
    """self moderate + photo severe -> conflict; reassessing the photo to
    moderate rebuilds to confirmed/moderate.

    Proves: rebuild from latest-per-source active events, no stale conflict
    left behind, and no auto-merge path (the conflict was never silently
    resolved to 'severe')."""
    from app.core.security import decode_token

    token = await _login_user(client)
    user_id = decode_token(token)["sub"]

    # self-test positive -> moderate
    await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers=_headers(token),
    )
    # photo severe disagrees -> conflict
    async with TestSession() as db:
        await service.save_photo_assessment(
            db, user_id, "HN-01", ["fake.jpg"], _ai_result("severe")
        )
    profile = await _profile_for("HN-01")
    assert profile is not None
    assert profile.certainty == "conflict"
    assert profile.has_conflict is True
    assert profile.combined_severity is None

    # reassess photo to moderate -> matches self moderate -> confirmed
    async with TestSession() as db:
        await service.save_photo_assessment(
            db, user_id, "HN-01", ["fake.jpg"], _ai_result("moderate")
        )
    profile = await _profile_for("HN-01")
    assert profile.certainty == "confirmed"
    assert profile.has_conflict is False
    assert profile.combined_severity == "moderate"
    # upserted in place -- still exactly one profile row for this issue
    assert await _profile_count() == 1


@pytest.mark.asyncio
async def test_conflict_persists_when_reassessment_still_disagrees(client):
    """Reassessing a source to a different (still non-matching) severity keeps
    the entry in conflict -- the projection always reflects the LATEST
    per-source severities, never a historical merge."""
    from app.core.security import decode_token

    token = await _login_user(client)
    user_id = decode_token(token)["sub"]

    await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers=_headers(token),
    )
    # self moderate + photo severe -> conflict
    async with TestSession() as db:
        await service.save_photo_assessment(
            db, user_id, "HN-01", ["fake.jpg"], _ai_result("severe")
        )
    # reassess photo to normal -> still disagrees with self moderate -> conflict
    async with TestSession() as db:
        await service.save_photo_assessment(
            db, user_id, "HN-01", ["fake.jpg"], _ai_result("normal")
        )
    profile = await _profile_for("HN-01")
    assert profile.certainty == "conflict"
    assert profile.has_conflict is True
    assert profile.combined_severity is None  # never auto-picked normal or moderate
