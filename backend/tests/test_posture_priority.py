"""Phase 1 Task 6: deterministic posture priority + goal confirmation.

Covers (spec §9.2 / §9.3 / §10.0 / §10.6 / §10.7 / §12.2-§12.4, plan Task 6):

GET /api/v1/posture/priorities
  * empty profile -> three empty buckets + stable control values (no error);
  * deterministic suggestion_id / profile_version (same input -> same output);
  * qualification routing: normal excluded; provisional/conflict -> retest;
    restricted/red_flag -> safety_blocked (priority over provisional);
  * ranking: severity base (300/200/100) + strong-association +20 + dual-source
    +2 + stale -1, tie-break by latest_event_at DESC then issue_id ASC, cap 3;
  * new assessment / new safety signal / crossing 30-day boundary invalidates
    suggestion_id;
  * cross-user isolation; read-only (no goal rows created).

POST /api/v1/posture/goals/confirm
  * 1-3 distinct current candidates, ranks unique & consecutive 1..N;
  * extra="forbid" rejects priority_context_snapshot; bad body -> 400 (not 422);
  * stale suggestion_id / profile_version -> 409 stale_priority;
  * restricted -> 409 restricted_blocked; red_flag -> 409 red_flag_blocked;
  * normal/provisional/conflict/unevaluated/non-candidate -> 400 invalid_goal;
  * idempotency: same key+request replays first batch (no dup writes); same
    key+different request -> 400 idempotency_key_conflict; replay after
    supersede returns the first batch; replay after purge -> 410;
  * supersede prior goals; shared confirmed_at per batch; result_ref = anchor.

All data is synthetic. Phase 1 ships no rule that produces ``red_flag``; the
red_flag routing/branch is exercised via a controlled (monkeypatched)
classification, clearly labelled.
"""
import uuid as _uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.auth.models import VerificationCode
from app.posture import priority, service
from app.posture.models import IdempotencyRecord, PostureProfileEntry, PostureUserGoal
from app.posture.risk_rules import RISK_VERSION
from tests.conftest import TestSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _uid(token):
    from app.core.security import decode_token

    return decode_token(token)["sub"]


async def _assess_self(client, token, issue_id, answer="positive", test_index=0):
    return await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": issue_id, "test_index": test_index, "answer": answer},
        headers=_headers(token),
    )


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


async def _photo(user_id, issue_id, level):
    async with TestSession() as db:
        await service.save_photo_assessment(
            db, user_id, issue_id, ["fake.jpg"], _ai_result(level)
        )


async def _seed_entry(
    user_id,
    issue_id,
    *,
    severity="moderate",
    certainty="confirmed",
    risk_tier="normal",
    risk_version="phase1-initial-v1",
    sources=None,
    has_conflict=False,
):
    """Seed a profile entry directly with full control (synthetic data)."""
    if sources is None:
        sources = [
            {
                "source": "self_test",
                "event_id": str(_uuid.uuid4()),
                "severity": severity,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
    entry = PostureProfileEntry(
        id=_uuid.uuid4(),
        user_id=_uuid.UUID(user_id),
        issue_id=issue_id,
        certainty=certainty,
        combined_severity=severity,
        sources=sources,
        has_conflict=has_conflict,
        risk_tier=risk_tier,
        risk_version=risk_version,
    )
    async with TestSession() as db:
        db.add(entry)
        await db.commit()
    return entry


async def _priorities(client, token):
    return await client.get("/api/v1/posture/priorities", headers=_headers(token))


async def _confirm(
    client, token, suggestion_id, profile_version, goals, idempotency_key
):
    return await client.post(
        "/api/v1/posture/goals/confirm",
        json={
            "suggestion_id": suggestion_id,
            "profile_version": profile_version,
            "goals": goals,
            "idempotency_key": idempotency_key,
        },
        headers=_headers(token),
    )


def _candidate_id_set(body):
    return {c["issue_id"] for c in body["normal_candidates"]}


# ===========================================================================
# Pure-function unit tests (deterministic, no HTTP)
# ===========================================================================


def test_route_matrix_matches_spec_12_4():
    # safety_blocked wins over provisional/conflict/confirmed
    assert priority._route("provisional", None, "restricted") == "safety_blocked"
    assert priority._route("conflict", None, "restricted") == "safety_blocked"
    assert priority._route("confirmed", "moderate", "red_flag") == "safety_blocked"
    # confirmed non-normal + normal/cautious tier -> candidate
    assert priority._route("confirmed", "moderate", "normal") == "normal_candidates"
    assert priority._route("confirmed", "severe", "cautious") == "normal_candidates"
    # confirmed normal -> excluded
    assert priority._route("confirmed", "normal", "normal") == "excluded"
    # provisional/conflict + non-blocking tier -> retest
    assert priority._route("provisional", None, "normal") == "retest_required"
    assert priority._route("conflict", None, "cautious") == "retest_required"


def test_route_restricted_does_not_fall_through_to_retest():
    """Contract: restricted must NOT land in retest via provisional."""
    for certainty in ("confirmed", "provisional", "conflict"):
        assert priority._route(certainty, "moderate", "restricted") == "safety_blocked"


def test_candidate_score_combinations():
    assert priority._candidate_score("severe", 1, False, False) == 300
    assert priority._candidate_score("moderate", 1, False, False) == 200
    assert priority._candidate_score("mild", 1, False, False) == 100
    # severity band cannot be crossed by sub-bonuses: moderate(200)+all bonuses
    # = 223 < severe(300); mild(100)+all = 121 < moderate(200).
    assert priority._candidate_score("moderate", 2, True, True) == 200 + 20 + 2 - 1
    assert priority._candidate_score("severe", 1, False, False) > priority._candidate_score(
        "moderate", 2, True, True
    )
    assert priority._candidate_score("moderate", 1, False, False) > priority._candidate_score(
        "mild", 2, True, True
    )


def test_safety_blocked_wording_keeps_restricted_distinct_from_red_flag():
    restricted_reason = priority._safety_blocked_reason("restricted")
    red_flag_reason = priority._safety_blocked_reason("red_flag")
    # restricted must NOT use clinical red-flag wording
    assert "红旗" not in restricted_reason
    assert "红旗" in red_flag_reason
    assert priority._safety_blocked_next_action("red_flag") != priority._safety_blocked_next_action(
        "restricted"
    )


def test_suggestion_id_is_deterministic_and_context_sensitive():
    pv = "p" * 64
    cd = "c" * 64
    a = priority._suggestion_id("u1", pv, cd)
    b = priority._suggestion_id("u1", pv, cd)
    assert a == b and a != ""
    # different user / digest / profile_version -> different id
    assert priority._suggestion_id("u2", pv, cd) != a
    assert priority._suggestion_id("u1", pv + "x", cd) != a
    assert priority._suggestion_id("u1", pv, cd + "x") != a


def test_latest_event_tie_break_preserves_microseconds():
    base = datetime(2026, 7, 17, 12, 0, 0, tzinfo=timezone.utc)
    newer = base + timedelta(microseconds=1)
    ordered = sorted([base, newer], key=priority._sort_dt_desc)
    assert ordered == [newer, base]


# ===========================================================================
# GET /priorities -- HTTP contract
# ===========================================================================


@pytest.mark.asyncio
async def test_get_priorities_requires_auth(client):
    resp = await client.get("/api/v1/posture/priorities")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_empty_profile_returns_three_empty_buckets_and_control_values(client):
    token = await _login_user(client)
    resp = await _priorities(client, token)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {
        "suggestion_id", "profile_version", "rule_version", "risk_version",
        "generated_at", "normal_candidates", "retest_required",
        "safety_blocked", "disclaimer",
    }
    assert body["normal_candidates"] == []
    assert body["retest_required"] == []
    assert body["safety_blocked"] == []
    assert body["rule_version"] == "2026-07-17-v1"
    assert body["risk_version"] == RISK_VERSION
    assert body["suggestion_id"]
    assert body["profile_version"]
    assert body["disclaimer"]


@pytest.mark.asyncio
async def test_priorities_deterministic_same_input_same_suggestion_id(client):
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="positive")
    r1 = (await _priorities(client, token)).json()
    r2 = (await _priorities(client, token)).json()
    assert r1["suggestion_id"] == r2["suggestion_id"]
    assert r1["profile_version"] == r2["profile_version"]


@pytest.mark.asyncio
async def test_confirmed_non_normal_is_normal_candidate(client):
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="positive")  # -> moderate
    body = (await _priorities(client, token)).json()
    assert {c["issue_id"] for c in body["normal_candidates"]} == {"HN-01"}
    cand = body["normal_candidates"][0]
    assert set(cand.keys()) == {
        "issue_id", "issue_name", "suggested_rank", "severity", "reasons",
        "relation_type", "association_weight",
    }
    assert cand["severity"] == "moderate"
    assert cand["suggested_rank"] == 1
    assert cand["reasons"]


@pytest.mark.asyncio
async def test_confirmed_normal_is_excluded(client):
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="negative")  # -> normal
    body = (await _priorities(client, token)).json()
    assert body["normal_candidates"] == []
    assert body["retest_required"] == []
    assert body["safety_blocked"] == []


@pytest.mark.asyncio
async def test_provisional_goes_to_retest(client):
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="uncertain")  # -> provisional
    body = (await _priorities(client, token)).json()
    assert body["normal_candidates"] == []
    assert body["safety_blocked"] == []
    assert [r["issue_id"] for r in body["retest_required"]] == ["HN-01"]
    assert body["retest_required"][0]["certainty"] == "provisional"


@pytest.mark.asyncio
async def test_conflict_goes_to_retest(client):
    token = await _login_user(client)
    uid = _uid(token)
    await _assess_self(client, token, "ST-04", answer="positive")  # moderate
    await _photo(uid, "ST-04", "severe")  # disagreement -> conflict
    body = (await _priorities(client, token)).json()
    assert body["normal_candidates"] == []
    assert [r["issue_id"] for r in body["retest_required"]] == ["ST-04"]
    assert body["retest_required"][0]["certainty"] == "conflict"


@pytest.mark.asyncio
async def test_restricted_safety_signal_routes_to_safety_blocked_not_retest(client):
    """Contract #2: restricted must NOT fall into retest via provisional."""
    token = await _login_user(client)
    # confirmed moderate on HN-01 first
    await _assess_self(client, token, "HN-01", answer="positive")
    before = (await _priorities(client, token)).json()
    assert "HN-01" in _candidate_id_set(before)

    # report acute_trauma (product-policy restricted) scoped to HN-01
    sig = await client.post(
        "/api/v1/posture/safety-signals",
        json={
            "signal_type": "acute_trauma",
            "related_issue_id": "HN-01",
            "idempotency_key": "k-at-1",
        },
        headers=_headers(token),
    )
    assert sig.status_code == 200

    after = (await _priorities(client, token)).json()
    sb = {x["issue_id"]: x for x in after["safety_blocked"]}
    assert "HN-01" in sb
    assert sb["HN-01"]["risk_tier"] == "restricted"
    # restricted wording must not pose as a clinical red flag
    assert "红旗" not in sb["HN-01"]["reason"]
    # must NOT appear in retest or candidates
    assert "HN-01" not in _candidate_id_set(after)
    assert "HN-01" not in {r["issue_id"] for r in after["retest_required"]}
    # new safety signal invalidated the old suggestion id
    assert after["suggestion_id"] != before["suggestion_id"]


@pytest.mark.asyncio
async def test_red_flag_routes_to_safety_blocked_via_controlled_classification(
    client, monkeypatch
):
    """Phase 1 ships no red_flag rule; exercise the branch with a synthetic
    classification (clearly labelled). Verifies GET routing + wording."""
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="positive")

    from app.posture.risk_rules import RiskClassification
    from app.posture import safety as safety_mod

    async def fake_classify(db, user_id, issue_id=None):
        return RiskClassification(
            risk_tier="red_flag",
            risk_version=RISK_VERSION,
            rule_id="fake-red-flag",
            reason="synthetic",
            sources=[],
        )

    monkeypatch.setattr(safety_mod, "compute_profile_risk", fake_classify)
    body = (await _priorities(client, token)).json()
    sb = {x["issue_id"]: x for x in body["safety_blocked"]}
    assert "HN-01" in sb
    assert sb["HN-01"]["risk_tier"] == "red_flag"
    assert "红旗" in sb["HN-01"]["reason"]
    assert "HN-01" not in _candidate_id_set(body)


@pytest.mark.asyncio
async def test_association_bonus_and_display(client):
    """HN-01 <-> ST-04 share a weight=0.9 edge; both confirmed non-normal
    candidates earn the +20 association bonus and surface the edge."""
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="positive")  # moderate
    await _assess_self(client, token, "ST-04", answer="positive")  # moderate
    body = (await _priorities(client, token)).json()
    ids = _candidate_id_set(body)
    assert {"HN-01", "ST-04"} <= ids
    by_id = {c["issue_id"]: c for c in body["normal_candidates"]}
    for cid in ("HN-01", "ST-04"):
        assert by_id[cid]["association_weight"] == 0.9
        assert by_id[cid]["relation_type"]
        assert any("强关联" in r for r in by_id[cid]["reasons"])


@pytest.mark.asyncio
async def test_dual_source_bonus(client):
    """self_test + ai_photo at the same severity -> confirmed with 2 sources
    -> +2 and '多来源评估一致' reason."""
    token = await _login_user(client)
    uid = _uid(token)
    await _assess_self(client, token, "HN-01", answer="positive")  # moderate
    await _photo(uid, "HN-01", "moderate")  # agrees -> confirmed, 2 sources
    body = (await _priorities(client, token)).json()
    cand = body["normal_candidates"][0]
    assert cand["issue_id"] == "HN-01"
    assert any("多来源评估一致" in r for r in cand["reasons"])


@pytest.mark.asyncio
async def test_source_count_change_invalidates_suggestion_with_same_latest_event(
    client,
):
    """Removing an older source changes the +2 ranking input even when the
    latest source event and every profile_version field remain unchanged."""
    token = await _login_user(client)
    uid = _uid(token)
    older = datetime(2026, 1, 1, tzinfo=timezone.utc)
    latest = datetime(2026, 1, 2, tzinfo=timezone.utc)
    latest_source = {
        "source": "self_test",
        "event_id": str(_uuid.uuid4()),
        "severity": "moderate",
        "created_at": latest.isoformat(),
    }
    await _seed_entry(
        uid,
        "HN-01",
        sources=[
            {
                "source": "ai_photo",
                "event_id": str(_uuid.uuid4()),
                "severity": "moderate",
                "created_at": older.isoformat(),
            },
            latest_source,
        ],
    )

    async with TestSession() as db:
        before = await priority.build_priority_suggestions(db, uid, now=latest)
        entry = await db.scalar(
            select(PostureProfileEntry).where(
                PostureProfileEntry.user_id == _uuid.UUID(uid),
                PostureProfileEntry.issue_id == "HN-01",
            )
        )
        entry.sources = [latest_source]
        await db.commit()
        after = await priority.build_priority_suggestions(db, uid, now=latest)

    assert before["profile_version"] == after["profile_version"]
    assert before["suggestion_id"] != after["suggestion_id"]
    assert any("多来源评估一致" in r for r in before["normal_candidates"][0]["reasons"])
    assert all(
        "多来源评估一致" not in r for r in after["normal_candidates"][0]["reasons"]
    )


@pytest.mark.asyncio
async def test_ranking_order_severity_band_dominates(client):
    """severe > moderate > mild regardless of sub-bonuses. Drives the real
    engine via seeded entries at each severity."""
    token = await _login_user(client)
    uid = _uid(token)
    # Pick issues without mutual 0.9 edges so the severity base dominates
    # cleanly: HN-01 (severe), PS-13 (moderate), LL-22 (mild).
    await _seed_entry(uid, "HN-01", severity="severe")
    await _seed_entry(uid, "PS-13", severity="moderate")
    await _seed_entry(uid, "LL-22", severity="mild")
    async with TestSession() as db:
        body = await priority.build_priority_suggestions(db, uid)
    sev_order = [c["severity"] for c in body["normal_candidates"]]
    id_order = [c["issue_id"] for c in body["normal_candidates"]]
    assert sev_order == ["severe", "moderate", "mild"]
    assert id_order == ["HN-01", "PS-13", "LL-22"]


@pytest.mark.asyncio
async def test_max_three_candidates(client):
    token = await _login_user(client)
    uid = _uid(token)
    # seed 4 distinct confirmed non-normal entries at moderate severity
    for iid in ("HN-01", "ST-04", "PS-13", "LL-21"):
        await _seed_entry(uid, iid, severity="moderate")
    body = (await _priorities(client, token)).json()
    assert len(body["normal_candidates"]) == 3
    ranks = [c["suggested_rank"] for c in body["normal_candidates"]]
    assert ranks == [1, 2, 3]


@pytest.mark.asyncio
async def test_new_assessment_invalidates_suggestion_id(client):
    token = await _login_user(client)
    before = (await _priorities(client, token)).json()
    await _assess_self(client, token, "HN-01", answer="positive")
    after = (await _priorities(client, token)).json()
    assert before["suggestion_id"] != after["suggestion_id"]
    assert before["profile_version"] != after["profile_version"]


@pytest.mark.asyncio
async def test_cross_user_isolation(client):
    token_a = await _login_user(client, phone="13800138000")
    await _assess_self(client, token_a, "HN-01", answer="positive")
    token_b = await _login_user(client, phone="13900139000")
    body = (await _priorities(client, token_b)).json()
    assert body["normal_candidates"] == []
    assert body["safety_blocked"] == []


@pytest.mark.asyncio
async def test_get_priorities_does_not_write_goals(client):
    """GET is read-only: no PostureUserGoal rows appear after a GET call."""
    token = await _login_user(client)
    uid = _uid(token)
    await _assess_self(client, token, "HN-01", answer="positive")
    await _priorities(client, token)
    async with TestSession() as db:
        rows = (
            await db.execute(
                select(PostureUserGoal).where(
                    PostureUserGoal.user_id == _uuid.UUID(uid)
                )
            )
        ).scalars().all()
    assert rows == []


# ===========================================================================
# GET /priorities -- staleness boundary invalidates suggestion_id (direct)
# ===========================================================================


@pytest.mark.asyncio
async def test_thirty_day_boundary_invalidates_suggestion_id(client):
    """Crossing the strict >30-day boundary flips older_than_30_days, which
    enters priority_context_digest -> suggestion_id changes with NO DB write."""
    token = await _login_user(client)
    uid = _uid(token)
    base = datetime(2026, 7, 11, 10, 0, 0, tzinfo=timezone.utc)
    # latest source event exactly 29 days before the first 'now'
    t_now_29_after = base + timedelta(days=29)
    await _seed_entry(
        uid,
        "HN-01",
        severity="moderate",
        sources=[
            {
                "source": "self_test",
                "event_id": str(_uuid.uuid4()),
                "severity": "moderate",
                "created_at": base.isoformat(),
            }
        ],
    )

    async with TestSession() as db:
        r1 = await priority.build_priority_suggestions(db, uid, now=t_now_29_after)
        # 2 days later -> event is 31 days old -> stale bit flips
        r2 = await priority.build_priority_suggestions(
            db, uid, now=t_now_29_after + timedelta(days=2)
        )
    assert r1["suggestion_id"] != r2["suggestion_id"]
    # the candidate's staleness reason only appears past the boundary
    reasons_1 = r1["normal_candidates"][0]["reasons"]
    reasons_2 = r2["normal_candidates"][0]["reasons"]
    assert not any("超过 30 天" in r for r in reasons_1)
    assert any("超过 30 天" in r for r in reasons_2)


# ===========================================================================
# POST /goals/confirm -- HTTP contract
# ===========================================================================


@pytest.mark.asyncio
async def test_confirm_requires_auth(client):
    resp = await client.post(
        "/api/v1/posture/goals/confirm",
        json={
            "suggestion_id": "x",
            "profile_version": "y",
            "goals": [{"issue_id": "HN-01", "priority_rank": 1}],
            "idempotency_key": "k",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_confirm_bad_json_returns_400(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/goals/confirm",
        content=b"{not json",
        headers={**_headers(token), "Content-Type": "application/json"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_confirm_rejects_priority_context_snapshot(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/goals/confirm",
        json={
            "suggestion_id": "x",
            "profile_version": "y",
            "goals": [{"issue_id": "HN-01", "priority_rank": 1}],
            "idempotency_key": "k",
            "priority_context_snapshot": {"should": "be rejected"},
        },
        headers=_headers(token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_confirm_success_writes_goals_with_shared_confirmed_at(client):
    token = await _login_user(client)
    uid = _uid(token)
    await _assess_self(client, token, "HN-01", answer="positive")
    await _assess_self(client, token, "ST-04", answer="positive")
    body = (await _priorities(client, token)).json()

    resp = await _confirm(
        client,
        token,
        body["suggestion_id"],
        body["profile_version"],
        [
            {"issue_id": "HN-01", "priority_rank": 1},
            {"issue_id": "ST-04", "priority_rank": 2},
        ],
        "k-confirm-1",
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert set(out.keys()) == {"confirmed_goals", "can_generate_plan", "risk_version"}
    assert out["can_generate_plan"] is True
    assert out["risk_version"] == RISK_VERSION
    assert len(out["confirmed_goals"]) == 2

    async with TestSession() as db:
        goals = (
            await db.execute(
                select(PostureUserGoal)
                .where(PostureUserGoal.user_id == _uuid.UUID(uid))
                .order_by(PostureUserGoal.priority_rank.asc())
            )
        ).scalars().all()
    assert len(goals) == 2
    # shared confirmed_at, server control values persisted
    assert goals[0].confirmed_at == goals[1].confirmed_at
    assert goals[0].suggestion_id == body["suggestion_id"]
    assert goals[0].profile_version == body["profile_version"]
    assert goals[0].rule_version == "2026-07-17-v1"
    assert goals[0].risk_version == RISK_VERSION
    assert all(g.superseded_at is None for g in goals)


@pytest.mark.asyncio
async def test_confirm_normal_issue_returns_400_invalid_goal(client):
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="negative")  # normal
    body = (await _priorities(client, token)).json()
    # no candidates; send a confirm with the current control values + normal goal
    resp = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"],
        [{"issue_id": "HN-01", "priority_rank": 1}], "k-normal",
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_goal"


@pytest.mark.asyncio
async def test_confirm_provisional_returns_400_invalid_goal(client):
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="uncertain")
    body = (await _priorities(client, token)).json()
    resp = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"],
        [{"issue_id": "HN-01", "priority_rank": 1}], "k-prov",
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_goal"


@pytest.mark.asyncio
async def test_confirm_structural_errors_return_400(client):
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="positive")
    body = (await _priorities(client, token)).json()
    sid, pv = body["suggestion_id"], body["profile_version"]
    cand = body["normal_candidates"][0]["issue_id"]

    # empty goals
    r = await _confirm(client, token, sid, pv, [], "k-empty")
    assert r.status_code == 400 and r.json()["code"] == "invalid_goal"
    # 4 goals (over max) -- add synthetic candidate issues so ranks could be valid
    # but count must still fail first
    r = await _confirm(
        client, token, sid, pv,
        [{"issue_id": cand, "priority_rank": i} for i in range(1, 5)],
        "k-too-many",
    )
    assert r.status_code == 400 and r.json()["code"] == "invalid_goal"
    # duplicate issue
    r = await _confirm(
        client, token, sid, pv,
        [{"issue_id": cand, "priority_rank": 1}, {"issue_id": cand, "priority_rank": 2}],
        "k-dup-issue",
    )
    assert r.status_code == 400 and r.json()["code"] == "invalid_goal"
    # non-consecutive ranks
    r = await _confirm(
        client, token, sid, pv,
        [{"issue_id": cand, "priority_rank": 2}],
        "k-bad-rank",
    )
    assert r.status_code == 400 and r.json()["code"] == "invalid_goal"


@pytest.mark.asyncio
async def test_confirm_restricted_returns_409_restricted_blocked(client):
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="positive")
    # escalate to restricted via acute_trauma
    sig = await client.post(
        "/api/v1/posture/safety-signals",
        json={
            "signal_type": "acute_trauma",
            "related_issue_id": "HN-01",
            "idempotency_key": "k-at-confirm",
        },
        headers=_headers(token),
    )
    assert sig.status_code == 200
    body = (await _priorities(client, token)).json()
    resp = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"],
        [{"issue_id": "HN-01", "priority_rank": 1}], "k-restricted",
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "restricted_blocked"


@pytest.mark.asyncio
async def test_confirm_red_flag_returns_409_red_flag_blocked(client, monkeypatch):
    """Controlled classification to exercise the red_flag confirm branch."""
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="positive")

    from app.posture.risk_rules import RiskClassification
    from app.posture import safety as safety_mod

    async def fake_classify(db, user_id, issue_id=None):
        return RiskClassification(
            risk_tier="red_flag", risk_version=RISK_VERSION,
            rule_id="fake", reason="synthetic", sources=[],
        )

    monkeypatch.setattr(safety_mod, "compute_profile_risk", fake_classify)
    body = (await _priorities(client, token)).json()
    resp = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"],
        [{"issue_id": "HN-01", "priority_rank": 1}], "k-redflag",
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "red_flag_blocked"


@pytest.mark.asyncio
async def test_confirm_stale_suggestion_id_returns_409(client):
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="positive")
    body = (await _priorities(client, token)).json()
    resp = await _confirm(
        client, token,
        body["suggestion_id"] + "tampered",  # wrong suggestion_id
        body["profile_version"],
        [{"issue_id": "HN-01", "priority_rank": 1}], "k-stale-sid",
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "stale_priority"


@pytest.mark.asyncio
async def test_confirm_stale_after_new_assessment_returns_409(client):
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="positive")
    stale = (await _priorities(client, token)).json()
    # new assessment changes the profile -> old control values become stale
    await _assess_self(client, token, "ST-04", answer="positive")
    resp = await _confirm(
        client, token, stale["suggestion_id"], stale["profile_version"],
        [{"issue_id": "HN-01", "priority_rank": 1}], "k-stale-after",
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "stale_priority"


@pytest.mark.asyncio
async def test_confirm_stale_after_new_safety_signal_returns_409_before_block(client):
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="positive")
    stale = (await _priorities(client, token)).json()

    signal = await client.post(
        "/api/v1/posture/safety-signals",
        json={
            "signal_type": "acute_trauma",
            "related_issue_id": "HN-01",
            "idempotency_key": "k-stale-safety-signal",
        },
        headers=_headers(token),
    )
    assert signal.status_code == 200

    resp = await _confirm(
        client,
        token,
        stale["suggestion_id"],
        stale["profile_version"],
        [{"issue_id": "HN-01", "priority_rank": 1}],
        "k-confirm-stale-safety",
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "stale_priority"


@pytest.mark.asyncio
async def test_confirm_unknown_issue_returns_404(client):
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="positive")
    body = (await _priorities(client, token)).json()
    resp = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"],
        [{"issue_id": "NOPE-99", "priority_rank": 1}], "k-unknown",
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "issue_not_found"


# ===========================================================================
# POST /goals/confirm -- idempotency, supersede, replay, purge 410
# ===========================================================================


@pytest.mark.asyncio
async def test_confirm_supersedes_prior_goals(client):
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="positive")
    await _assess_self(client, token, "ST-04", answer="positive")
    body = (await _priorities(client, token)).json()
    uid = _uid(token)

    first = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"],
        [{"issue_id": "HN-01", "priority_rank": 1}], "k-first",
    )
    assert first.status_code == 200
    second = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"],
        [{"issue_id": "ST-04", "priority_rank": 1}], "k-second",
    )
    assert second.status_code == 200

    async with TestSession() as db:
        goals = (
            await db.execute(
                select(PostureUserGoal)
                .where(PostureUserGoal.user_id == _uuid.UUID(uid))
                .order_by(PostureUserGoal.confirmed_at.asc())
            )
        ).scalars().all()
    # first batch superseded, second batch active
    by_issue = {g.issue_id: g for g in goals}
    assert by_issue["HN-01"].superseded_at is not None
    assert by_issue["ST-04"].superseded_at is None


@pytest.mark.asyncio
async def test_idempotency_same_key_same_request_replays_first_batch(client):
    token = await _login_user(client)
    uid = _uid(token)
    await _assess_self(client, token, "HN-01", answer="positive")
    await _assess_self(client, token, "ST-04", answer="positive")
    body = (await _priorities(client, token)).json()
    goals = [
        {"issue_id": "HN-01", "priority_rank": 1},
        {"issue_id": "ST-04", "priority_rank": 2},
    ]

    first = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"], goals, "k-idem"
    )
    assert first.status_code == 200
    first_confirmed = first.json()["confirmed_goals"]

    # count goals before replay
    async with TestSession() as db:
        n_before = len(
            (
                await db.execute(
                    select(PostureUserGoal).where(
                        PostureUserGoal.user_id == _uuid.UUID(uid)
                    )
                )
            ).scalars().all()
        )
    assert n_before == 2

    replay = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"], goals, "k-idem"
    )
    assert replay.status_code == 200
    # same first batch returned
    assert replay.json()["confirmed_goals"] == first_confirmed

    # no duplicate writes
    async with TestSession() as db:
        n_after = len(
            (
                await db.execute(
                    select(PostureUserGoal).where(
                        PostureUserGoal.user_id == _uuid.UUID(uid)
                    )
                )
            ).scalars().all()
        )
    assert n_after == 2


@pytest.mark.asyncio
async def test_idempotency_same_key_different_request_returns_400(client):
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="positive")
    await _assess_self(client, token, "ST-04", answer="positive")
    body = (await _priorities(client, token)).json()

    first = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"],
        [{"issue_id": "HN-01", "priority_rank": 1}], "k-conflict",
    )
    assert first.status_code == 200

    # same key, different goals -> conflict (checked before stale/qualification)
    second = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"],
        [{"issue_id": "ST-04", "priority_rank": 1}], "k-conflict",
    )
    assert second.status_code == 400
    assert second.json()["code"] == "idempotency_key_conflict"


@pytest.mark.asyncio
async def test_idempotency_replay_after_supersede_returns_first_batch(client):
    token = await _login_user(client)
    await _assess_self(client, token, "HN-01", answer="positive")
    await _assess_self(client, token, "ST-04", answer="positive")
    body = (await _priorities(client, token)).json()

    first = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"],
        [{"issue_id": "HN-01", "priority_rank": 1}], "k-A",
    )
    assert first.status_code == 200
    first_batch = first.json()["confirmed_goals"]

    # a later confirm (different key) supersedes the first batch
    await _confirm(
        client, token, body["suggestion_id"], body["profile_version"],
        [{"issue_id": "ST-04", "priority_rank": 1}], "k-B",
    )

    # replay k-A -> must still return the FIRST batch (HN-01), not ST-04
    replay = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"],
        [{"issue_id": "HN-01", "priority_rank": 1}], "k-A",
    )
    assert replay.status_code == 200
    assert replay.json()["confirmed_goals"] == first_batch


@pytest.mark.asyncio
async def test_idempotency_replay_isolated_when_batch_clocks_collide(
    client, monkeypatch
):
    """Two batches at the same wall-clock instant must remain distinguishable."""
    token = await _login_user(client)
    uid = _uid(token)
    await _assess_self(client, token, "HN-01", answer="positive")
    await _assess_self(client, token, "ST-04", answer="positive")
    body = (await _priorities(client, token)).json()
    frozen = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen if tz is not None else frozen.replace(tzinfo=None)

    monkeypatch.setattr(service, "datetime", FrozenDateTime)

    first = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"],
        [{"issue_id": "HN-01", "priority_rank": 1}], "k-collision-a",
    )
    second = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"],
        [{"issue_id": "ST-04", "priority_rank": 1}], "k-collision-b",
    )
    assert first.status_code == 200
    assert second.status_code == 200

    replay = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"],
        [{"issue_id": "HN-01", "priority_rank": 1}], "k-collision-a",
    )
    assert replay.status_code == 200
    assert [g["issue_id"] for g in replay.json()["confirmed_goals"]] == ["HN-01"]

    async with TestSession() as db:
        times = (
            await db.execute(
                select(PostureUserGoal.confirmed_at)
                .where(PostureUserGoal.user_id == _uuid.UUID(uid))
                .order_by(PostureUserGoal.confirmed_at.asc())
            )
        ).scalars().all()
    assert len(set(times)) == 2


@pytest.mark.asyncio
async def test_idempotency_replay_after_purge_returns_410(client):
    token = await _login_user(client)
    uid = _uid(token)
    await _assess_self(client, token, "HN-01", answer="positive")
    body = (await _priorities(client, token)).json()

    first = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"],
        [{"issue_id": "HN-01", "priority_rank": 1}], "k-purge",
    )
    assert first.status_code == 200

    # simulate purge deleting the goal rows while the idempotency record stays
    async with TestSession() as db:
        goals = (
            await db.execute(
                select(PostureUserGoal).where(
                    PostureUserGoal.user_id == _uuid.UUID(uid)
                )
            )
        ).scalars().all()
        for g in goals:
            await db.delete(g)
        await db.commit()

    replay = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"],
        [{"issue_id": "HN-01", "priority_rank": 1}], "k-purge",
    )
    assert replay.status_code == 410
    assert replay.json()["code"] == "idempotency_result_gone"


@pytest.mark.asyncio
async def test_confirm_idempotency_record_uses_confirm_goals_operation_and_anchor(
    client,
):
    token = await _login_user(client)
    uid = _uid(token)
    await _assess_self(client, token, "HN-01", answer="positive")
    await _assess_self(client, token, "ST-04", answer="positive")
    body = (await _priorities(client, token)).json()

    resp = await _confirm(
        client, token, body["suggestion_id"], body["profile_version"],
        [
            {"issue_id": "HN-01", "priority_rank": 1},
            {"issue_id": "ST-04", "priority_rank": 2},
        ],
        "k-anchor-check",
    )
    assert resp.status_code == 200

    async with TestSession() as db:
        rec = (
            await db.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.user_id == _uuid.UUID(uid),
                    IdempotencyRecord.operation == "confirm_goals",
                    IdempotencyRecord.idempotency_key == "k-anchor-check",
                )
            )
        ).scalar_one()
        anchor = await db.get(PostureUserGoal, _uuid.UUID(rec.result_ref))
    assert rec.operation == "confirm_goals"
    assert rec.status == "completed"
    # anchor is the rank-1 goal of the batch
    assert anchor.issue_id == "HN-01"
    assert anchor.priority_rank == 1
