"""Phase 5 Agent persistence behavior tests (Task 2).

Covers the consent sequence/replay/conflict/gone/cross-user matrix, run
duplicate-turn behavior, the proposal lifecycle (create / lazy expiry / cancel /
terminal scrub), key-rotation invalidation, 30-day retention cleanup, and
Agent-data deletion (four Agent tables + three Agent namespaces removed while
independently owned domain rows and domain idempotency evidence are preserved).

All data is synthetic. No live provider, real health data, or credential is
used. SQLite is used here; PostgreSQL concurrency/lock tests live in
``test_pg_integration.py``.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.agent import action_tools as at
from app.agent import persistence as ap
from app.agent import schemas as S
from app.agent.models import (
    AgentCloudConsent,
    AgentRun,
)
from app.auth.models import User
from app.core.config import settings
from app.core.exceptions import AppException
from app.posture.models import IdempotencyRecord

pytestmark = pytest.mark.asyncio

PROVIDER = "cloud-provider-a"
DISCLOSURE = "disclosure-2026-07"
HMAC_KEY = "test-agent-audit-key-0123456789abcdef"
HMAC_VERSION = "v1"
TZ = "Asia/Shanghai"


@pytest.fixture(autouse=True)
def _hmac_key(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY", HMAC_KEY)
    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY_VERSION", HMAC_VERSION)


async def _make_user(db) -> uuid.UUID:
    user = User(phone="139" + uuid.uuid4().hex[:8])
    db.add(user)
    await db.flush()
    return user.id


async def _seed_run(db, user_id, turn_id="turn-1") -> AgentRun:
    res = await ap.record_run(db, str(user_id), client_turn_id=turn_id, entry_type="general")
    return res.run


async def _grant(db, user_id, key="k1", provider=PROVIDER, disclosure=DISCLOSURE):
    return await ap.grant_consent(
        db,
        str(user_id),
        accepted_provider_id=provider,
        accepted_disclosure_version=disclosure,
        current_provider_id=provider,
        current_disclosure_version=disclosure,
        idempotency_key=key,
    )


async def _ensure_consent(db, user_id):
    if not (await ap.active_consent(db, str(user_id))).active:
        await _grant(db, user_id, "grant-" + uuid.uuid4().hex[:8])


async def _create_weight_proposal(
    db,
    user_id,
    *,
    run=None,
    weight_kg=70.0,
    now=None,
    ttl=None,
):
    await _ensure_consent(db, user_id)
    run = run or await _seed_run(db, user_id, "turn-" + uuid.uuid4().hex[:8])
    args = S.CreateWeightRecordArguments(
        recorded_at=now or datetime.now(timezone.utc), weight_kg=weight_kg
    )
    fp = at.compute_arguments_fingerprint(args)
    return await ap.create_proposal(
        db,
        run_id=run.run_id,
        user_id=str(user_id),
        tool_name=S.CREATE_WEIGHT_RECORD,
        arguments_json=args.model_dump(mode="json"),
        arguments_hash=fp.value,
        fingerprint_key_version=fp.key_version,
        iana_timezone=TZ,
        now=now,
        ttl=ttl,
    )


# --------------------------------------------------------------------------- #
# Consent                                                                      #
# --------------------------------------------------------------------------- #


async def test_grant_appends_monotonic_sequence_and_derives_active():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        g1 = await _grant(db, uid, "k1")
        assert g1.sequence_no == 1 and g1.status == "granted" and not g1.replayed

        active = await ap.active_consent(db, str(uid))
        assert active.active and active.provider_id == PROVIDER

        w = await ap.withdraw_consent(db, str(uid), idempotency_key="k2")
        assert w.sequence_no == 2 and w.status == "withdrawn"
        active = await ap.active_consent(db, str(uid))
        assert not active.active  # highest sequence is a withdrawal
        assert active.provider_id == PROVIDER
        assert active.disclosure_version == DISCLOSURE


async def test_grant_replay_returns_same_consent_no_new_row():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        first = await _grant(db, uid, "key-replay")
        second = await _grant(db, uid, "key-replay")
        assert second.replayed is True
        assert second.consent_id == first.consent_id
        rows = (
            await db.execute(
                select(AgentCloudConsent).where(AgentCloudConsent.user_id == uid)
            )
        ).scalars().all()
        assert len(rows) == 1  # no duplicate grant row on replay


async def test_grant_conflict_on_same_key_different_request():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        await ap.grant_consent(
            db,
            str(uid),
            accepted_provider_id=PROVIDER,
            accepted_disclosure_version=DISCLOSURE,
            current_provider_id=PROVIDER,
            current_disclosure_version=DISCLOSURE,
            idempotency_key="dup-key",
        )
        with pytest.raises(AppException) as exc:
            await ap.grant_consent(
                db,
                str(uid),
                accepted_provider_id=PROVIDER,
                accepted_disclosure_version="disclosure-OTHER",
                current_provider_id=PROVIDER,
                current_disclosure_version="disclosure-OTHER",
                idempotency_key="dup-key",
            )
        assert exc.value.code == "idempotency_key_conflict"


async def test_grant_stale_disclosure_rejected():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        with pytest.raises(AppException) as exc:
            await ap.grant_consent(
                db,
                str(uid),
                accepted_provider_id="stale-provider",
                accepted_disclosure_version=DISCLOSURE,
                current_provider_id=PROVIDER,
                current_disclosure_version=DISCLOSURE,
                idempotency_key="k",
            )
        assert exc.value.code == "agent_disclosure_stale"
        assert not (await ap.active_consent(db, str(uid))).active


async def test_withdraw_scrubs_pending_proposals_atomically():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        await _grant(db, uid, "g1")
        run = await _seed_run(db, uid)
        p = await _create_weight_proposal(db, uid, run=run)
        # Withdraw must invalidate + scrub the pending proposal same-transaction.
        await ap.withdraw_consent(db, str(uid), idempotency_key="w1")
        proposal = await ap.load_owned_proposal(db, str(uid), p.proposal_id)
        assert proposal.status == "invalidated"
        assert proposal.arguments_json is None  # scrubbed


async def test_grant_gone_anchor_returns_410():
    from tests.conftest import TestSession
    from sqlalchemy import delete

    async with TestSession() as db:
        uid = await _make_user(db)
        g = await _grant(db, uid, "gone-key")
        # Simulate the referenced consent being cleared while the idempotency
        # record remains (e.g. partial historical state).
        await db.execute(
            delete(AgentCloudConsent).where(AgentCloudConsent.consent_id == g.consent_id)
        )
        await db.commit()
        with pytest.raises(AppException) as exc:
            await _grant(db, uid, "gone-key")
        assert exc.value.status_code == 410


async def test_consent_cross_user_isolation():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid_a = await _make_user(db)
        uid_b = await _make_user(db)
        await _grant(db, uid_a, "ka")
        # User B has no consent and cannot see/affect user A's consent.
        assert not (await ap.active_consent(db, str(uid_b))).active
        assert (await ap.active_consent(db, str(uid_a))).active


# --------------------------------------------------------------------------- #
# Run + Tool event                                                             #
# --------------------------------------------------------------------------- #


async def test_duplicate_client_turn_returns_existing_no_second_run():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        first = await ap.record_run(
            db, str(uid), client_turn_id="dup", entry_type="general"
        )
        second = await ap.record_run(
            db, str(uid), client_turn_id="dup", entry_type="general"
        )
        assert first.created is True
        assert second.created is False
        assert second.run.run_id == first.run.run_id
        runs = (
            await db.execute(select(AgentRun).where(AgentRun.user_id == uid))
        ).scalars().all()
        assert len(runs) == 1


async def test_tool_event_stores_metadata_only():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        run = await _seed_run(db, uid)
        ev = await ap.record_tool_event(
            db,
            run_id=run.run_id,
            user_id=str(uid),
            tool_name="get_today_checkin",
            side_effect_class="read",
            status="ok",
            request_fingerprint="fp",
            result_code="agent_read_ok",
        )
        assert ev.result_ref is None
        # No raw payload column exists on the row.
        assert not hasattr(ev, "arguments_json") and not hasattr(ev, "result_payload")


async def test_tool_event_rejects_foreign_run_binding():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid_a = await _make_user(db)
        uid_b = await _make_user(db)
        run = await _seed_run(db, uid_a)
        with pytest.raises(AppException) as exc:
            await ap.record_tool_event(
                db,
                run_id=run.run_id,
                user_id=str(uid_b),
                tool_name="get_today_checkin",
                side_effect_class="read",
                status="ok",
            )
        assert exc.value.code == "agent_entity_not_found"


# --------------------------------------------------------------------------- #
# Proposal lifecycle                                                           #
# --------------------------------------------------------------------------- #


async def test_pending_retains_arguments_and_terminal_scrubs():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        p = await _create_weight_proposal(db, uid)
        proposal = await ap.load_owned_proposal(db, str(uid), p.proposal_id)
        assert proposal.status == "pending"
        assert proposal.arguments_json["weight_kg"] == 70.0
        assert set(proposal.arguments_json) == {"recorded_at", "weight_kg"}

        cancelled = await ap.cancel_proposal(db, str(uid), p.proposal_id)
        assert cancelled.status == "cancelled"
        assert cancelled.arguments_json is None


async def test_create_proposal_rejects_foreign_run_binding():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid_a = await _make_user(db)
        uid_b = await _make_user(db)
        run = await _seed_run(db, uid_a)
        await _ensure_consent(db, uid_b)
        args = S.CreateWeightRecordArguments(
            recorded_at=datetime.now(timezone.utc), weight_kg=70.0
        )
        fp = at.compute_arguments_fingerprint(args)
        with pytest.raises(AppException) as exc:
            await ap.create_proposal(
                db,
                run_id=run.run_id,
                user_id=str(uid_b),
                tool_name="create_weight_record",
                arguments_json=args.model_dump(mode="json"),
                arguments_hash=fp.value,
                fingerprint_key_version=fp.key_version,
                iana_timezone=TZ,
            )
        assert exc.value.code == "agent_entity_not_found"


async def test_create_proposal_requires_current_server_consent():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        run = await _seed_run(db, uid)
        args = S.CreateWeightRecordArguments(
            recorded_at=datetime.now(timezone.utc), weight_kg=70.0
        )
        fp = at.compute_arguments_fingerprint(args)
        with pytest.raises(AppException) as exc:
            await ap.create_proposal(
                db,
                run_id=run.run_id,
                user_id=str(uid),
                tool_name=S.CREATE_WEIGHT_RECORD,
                arguments_json=args.model_dump(mode="json"),
                arguments_hash=fp.value,
                fingerprint_key_version=fp.key_version,
                iana_timezone=TZ,
            )
        assert exc.value.code == "agent_consent_required"


async def test_create_proposal_rejects_untyped_or_identity_arguments():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        run = await _seed_run(db, uid)
        await _ensure_consent(db, uid)
        with pytest.raises(AppException) as exc:
            await ap.create_proposal(
                db,
                run_id=run.run_id,
                user_id=str(uid),
                tool_name="create_weight_record",
                arguments_json={
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "weight_kg": 70.0,
                    "user_id": str(uid),
                    "note": "must never be persisted",
                },
                arguments_hash="not-trusted",
                iana_timezone=TZ,
            )
        assert exc.value.code == "agent_tool_not_allowed"


async def test_one_write_proposal_per_run():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        run = await _seed_run(db, uid)
        await _create_weight_proposal(db, uid, run=run, weight_kg=70.0)
        with pytest.raises(AppException) as exc:
            await _create_weight_proposal(db, uid, run=run, weight_kg=71.0)
        assert exc.value.code == "agent_proposal_already_exists"


async def test_cancel_is_idempotent_terminal():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        p = await _create_weight_proposal(db, uid)
        await ap.cancel_proposal(db, str(uid), p.proposal_id)
        # Second cancel is a no-op (already cancelled), not an error.
        again = await ap.cancel_proposal(db, str(uid), p.proposal_id)
        assert again.status == "cancelled"


async def test_load_owned_proposal_non_enumerating_for_foreign():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid_a = await _make_user(db)
        uid_b = await _make_user(db)
        p = await _create_weight_proposal(db, uid_a)
        # Foreign user loading the proposal gets None (same as missing).
        assert await ap.load_owned_proposal(db, str(uid_b), p.proposal_id) is None


async def test_lazy_expire_scrubs_past_ttl():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        p = await _create_weight_proposal(
            db,
            uid,
            now=past - timedelta(minutes=14),  # created well in the past
            ttl=timedelta(seconds=1),
        )
        count = await ap.expire_due_proposals(db, str(uid))
        assert count == 1
        proposal = await ap.load_owned_proposal(db, str(uid), p.proposal_id)
        assert proposal.status == "expired"
        assert proposal.arguments_json is None


async def test_load_pending_expired_inline():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        p = await _create_weight_proposal(
            db,
            uid,
            ttl=timedelta(seconds=1),
        )
        import asyncio

        await asyncio.sleep(1.2)
        proposal, expired = await ap.load_pending_owned_proposal(db, str(uid), p.proposal_id)
        assert expired is True
        assert proposal.status == "expired"
        assert proposal.arguments_json is None


# --------------------------------------------------------------------------- #
# Key rotation                                                                 #
# --------------------------------------------------------------------------- #


async def test_key_rotation_invalidates_old_version_proposals():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        p = await _create_weight_proposal(db, uid)
        count = await ap.scrub_pending_on_key_change(db, str(uid), "v2")
        assert count == 1
        proposal = await ap.load_owned_proposal(db, str(uid), p.proposal_id)
        assert proposal.status == "invalidated"
        assert proposal.arguments_json is None


# --------------------------------------------------------------------------- #
# Retention                                                                    #
# --------------------------------------------------------------------------- #


async def test_cleanup_expired_runs_deletes_dependents_keeps_recent():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        # An expired run (expires_at in the past) with a tool event + proposal.
        old_run = (
            await ap.record_run(
                db,
                str(uid),
                client_turn_id="old",
                entry_type="general",
                expires_at=datetime.now(timezone.utc) - timedelta(days=31),
            )
        ).run
        await ap.record_tool_event(
            db,
            run_id=old_run.run_id,
            user_id=str(uid),
            tool_name="get_today_checkin",
            side_effect_class="read",
            status="ok",
        )
        await _create_weight_proposal(
            db,
            uid,
            run=old_run,
            ttl=timedelta(seconds=1),
        )
        # A recent run that must survive.
        recent = (
            await ap.record_run(
                db, str(uid), client_turn_id="recent", entry_type="general"
            )
        ).run

        result = await ap.cleanup_expired_runs(db)
        assert result.runs_deleted == 1
        assert result.tool_events_deleted >= 1
        assert result.proposals_deleted >= 1

        remaining = (
            await db.execute(select(AgentRun).where(AgentRun.user_id == uid))
        ).scalars().all()
        assert {r.run_id for r in remaining} == {recent.run_id}
        # Consent rows are NOT deleted by retention (last until Agent-data deletion).
        # (no consents seeded here; just confirm no error.)


async def test_cleanup_idempotent():
    from tests.conftest import TestSession

    async with TestSession() as db:
        first = await ap.cleanup_expired_runs(db)
        second = await ap.cleanup_expired_runs(db)
        assert first.runs_deleted == 0 and second.runs_deleted == 0


# --------------------------------------------------------------------------- #
# Agent-data deletion                                                          #
# --------------------------------------------------------------------------- #


async def test_delete_agent_data_removes_agent_rows_and_namespaces_preserves_domain():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        await _grant(db, uid, "g")  # consent + agent_consent_grant namespace
        run = await _seed_run(db, uid)
        await ap.record_tool_event(
            db,
            run_id=run.run_id,
            user_id=str(uid),
            tool_name="get_today_checkin",
            side_effect_class="read",
            status="ok",
        )
        await _create_weight_proposal(db, uid, run=run)
        # Domain idempotency evidence (training + posture) must be preserved.
        now = datetime.now(timezone.utc)
        db.add(
            IdempotencyRecord(
                user_id=uid,
                operation="plan_generate",
                idempotency_key="dom-1",
                request_hash="x",
                status="completed",
                result_ref="plan-1",
                expires_at=now + timedelta(hours=1),
            )
        )
        db.add(
            IdempotencyRecord(
                user_id=uid,
                operation=ap.OP_AGENT_ACTION_CONFIRM,
                idempotency_key="ag-1",
                request_hash="x",
                status="completed",
                result_ref="r",
                expires_at=now + timedelta(hours=1),
            )
        )
        await db.commit()

        result = await ap.delete_agent_data(db, str(uid))
        assert result.consents_deleted == 1
        assert result.runs_deleted == 1
        assert result.tool_events_deleted == 1
        assert result.proposals_deleted == 1
        assert result.idempotency_deleted == 2  # grant + action_confirm

        # Agent tables empty for the user.
        assert (
            await db.execute(
                select(AgentRun).where(AgentRun.user_id == uid)
            )
        ).scalars().all() == []
        # Domain idempotency evidence preserved.
        ops = {
            r.operation
            for r in (
                await db.execute(
                    select(IdempotencyRecord).where(IdempotencyRecord.user_id == uid)
                )
            ).scalars().all()
        }
        assert ops == {"plan_generate"}
