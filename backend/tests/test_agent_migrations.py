"""Phase 5 Agent MVP migration runtime tests (Task 2).

Complements ``test_migrations.py`` (offline SQL + metadata parity) with
SQLite-runtime behavior: CHECK constraints are declared on the ORM models so
``create_all`` materializes them on SQLite just as the migration materializes
them on PostgreSQL (parity). The closed status lifecycles reject illegal values,
the named UNIQUE constraints reject duplicates, and no raw-text/context/prompt/
provider payload column exists on any Agent table.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.agent.models import (
    AgentActionProposal,
    AgentCloudConsent,
    AgentRun,
    AgentToolEvent,
)
from app.auth.models import User

pytestmark = pytest.mark.asyncio


async def _make_user(db) -> uuid.UUID:
    user = User(phone="139" + uuid.uuid4().hex[:8])
    db.add(user)
    await db.flush()
    return user.id


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def test_agent_tables_have_no_raw_payload_columns():
    """No Agent table carries a raw user message / context / prompt / provider
    payload column (spec Acceptance #16)."""
    forbidden_fragments = (
        "raw_context",
        "provider_request",
        "provider_response",
        "result_payload",
        "arguments_raw",
        "assistant_prose",
    )
    for table in (
        AgentCloudConsent,
        AgentRun,
        AgentToolEvent,
        AgentActionProposal,
    ):
        names = {c.name for c in inspect(table).columns}
        for fragment in forbidden_fragments:
            for name in names:
                assert fragment not in name, (
                    f"{table.__tablename__}.{name} looks like a raw payload column"
                )
        # Explicit allow-list check: a prompt/provider *version* code is fine; a
        # raw prompt/payload column is not.
        assert "prompt_text" not in names
        assert "user_message" not in names


async def test_consent_check_constraint_rejects_illegal_status():
    """SQLite enforces the consent status CHECK (parity with PostgreSQL)."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        db.add(
            AgentCloudConsent(
                user_id=uid,
                purpose="agent_cloud_processing",
                provider_id="p",
                disclosure_version="v1",
                status="bogus",
                sequence_no=1,
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_proposal_check_constraint_rejects_illegal_status():
    """SQLite enforces the proposal status CHECK (closed lifecycle)."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        run = AgentRun(
            user_id=uid,
            client_turn_id="t1",
            entry_type="general",
            status="started",
            started_at=_now(),
            expires_at=_now() + timedelta(days=30),
        )
        db.add(run)
        await db.flush()
        db.add(
            AgentActionProposal(
                run_id=run.run_id,
                user_id=uid,
                tool_name="upsert_today_checkin",
                arguments_json={},
                arguments_hash="h",
                status="bogus",
                iana_timezone="Asia/Shanghai",
                expires_at=_now(),
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_consent_unique_sequence_constraint():
    """UniqueConstraint(user_id, purpose, sequence_no) rejects duplicate seq."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        for _ in range(2):
            db.add(
                AgentCloudConsent(
                    user_id=uid,
                    purpose="agent_cloud_processing",
                    provider_id="p",
                    disclosure_version="v1",
                    status="granted",
                    sequence_no=1,
                )
            )
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_run_unique_user_turn_constraint():
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        ts = _now()
        for _ in range(2):
            db.add(
                AgentRun(
                    user_id=uid,
                    client_turn_id="dup-turn",
                    entry_type="general",
                    status="started",
                    started_at=ts,
                    expires_at=ts + timedelta(days=30),
                )
            )
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_proposal_unique_run_constraint():
    """The database enforces the one-write-proposal-per-turn limit."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        now = _now()
        run = AgentRun(
            user_id=uid,
            client_turn_id="one-proposal",
            entry_type="general",
            status="completed",
            started_at=now,
            expires_at=now + timedelta(days=30),
        )
        db.add(run)
        await db.flush()
        for index in range(2):
            db.add(
                AgentActionProposal(
                    run_id=run.run_id,
                    user_id=uid,
                    tool_name="create_weight_record",
                    arguments_json={"weight_kg": 70.0 + index},
                    arguments_hash=f"h{index}",
                    iana_timezone="Asia/Shanghai",
                    status="pending",
                    expires_at=now + timedelta(minutes=15),
                )
            )
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_valid_agent_rows_persist():
    """All four tables accept valid rows on the SQLite test schema."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        uid = await _make_user(db)
        now = _now()
        consent = AgentCloudConsent(
            user_id=uid,
            purpose="agent_cloud_processing",
            provider_id="prov",
            disclosure_version="d1",
            status="granted",
            sequence_no=1,
        )
        db.add(consent)
        await db.flush()
        run = AgentRun(
            user_id=uid,
            client_turn_id="t1",
            entry_type="general",
            status="completed",
            started_at=now,
            expires_at=now + timedelta(days=30),
        )
        db.add(run)
        await db.flush()
        event = AgentToolEvent(
            run_id=run.run_id,
            user_id=uid,
            tool_name="get_today_checkin",
            side_effect_class="read",
            status="ok",
        )
        db.add(event)
        proposal = AgentActionProposal(
            run_id=run.run_id,
            user_id=uid,
            tool_name="upsert_today_checkin",
            arguments_json={"local_date": "2026-07-29"},
            arguments_hash="abc",
            iana_timezone="Asia/Shanghai",
            status="pending",
            expires_at=now + timedelta(minutes=15),
        )
        db.add(proposal)
        await db.commit()
        assert consent.sequence_no == 1
        assert proposal.arguments_json == {"local_date": "2026-07-29"}
