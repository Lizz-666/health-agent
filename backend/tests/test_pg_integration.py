"""PostgreSQL 16 integration tests.

These tests exercise real PostgreSQL advisory locks, ``FOR UPDATE SKIP LOCKED``
job claiming, JSONB/UUID roundtrips and concurrent scenarios that SQLite cannot
test. They run in the SAME pytest session as the SQLite tests: the conftest.py
SQLite monkey-patch (``pg.UUID`` -> ``_SQLiteUUID``, ``JSONB`` -> ``JSON``) is
PROVEN to roundtrip correctly on real PostgreSQL.

CRITICAL invariants enforced by this module:
  * NEVER imports from ``tests.conftest`` and NEVER uses ``TestSession``.
  * Uses ONLY ``pg_session`` / ``pg_session_factory`` from ``conftest_pg``.
  * EVERY test asserts ``session.bind.dialect.name == "postgresql"`` first.
  * Concurrency tests (#1, #5) use two independent sessions from the same
    engine via ``asyncio.gather`` to exercise real PG advisory locks.
"""

import asyncio
import uuid as _uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from tests.conftest_pg import pg_available, requires_pg, skip_reason


# All tests in this module require PG (skipped as a group only when Docker is
# genuinely unavailable — never because the SQLite patch is active).
pytestmark = [
    requires_pg,
    pytest.mark.asyncio,
]


@pytest.fixture(autouse=True)
def _skip_without_pg():
    if not pg_available:
        pytest.skip(skip_reason)


# ---------------------------------------------------------------------------
# Helpers — create test data directly via ORM (NO imports from tests.conftest)
# ---------------------------------------------------------------------------


async def _make_user(db):
    """Create a minimal user row and return its id (UUID)."""
    from app.auth.models import User

    user = User(phone=f"139{_uuid.uuid4().hex[:8]}", nickname="pg_test_user")
    db.add(user)
    await db.flush()
    return user.id


async def _seed_photo_event(db, user_id, issue_id="HN-01", photo_keys=None):
    """Create an ai_photo assessment event and return it."""
    from app.posture.models import PostureAssessmentEvent

    evt = PostureAssessmentEvent(
        user_id=user_id,
        issue_id=issue_id,
        method="ai_photo",
        result="moderate",
        source="ai_photo",
        severity="moderate",
        lifecycle="active",
        photo_keys=photo_keys or [],
    )
    db.add(evt)
    await db.flush()
    return evt


def _slow_store(purge, delay=0.3):
    """A FakeObjectStore whose delete_object sleeps, widening the concurrency
    window so the loser reliably observes a non-terminal purge_operation."""

    class _Slow(purge.FakeObjectStore):
        async def delete_object(self, key):
            await asyncio.sleep(delay)
            await super().delete_object(key)

    return _Slow()


_TEST_KEY = "0123456789abcdef" * 4  # 32-byte AES-256 key (64 hex chars)


# ---------------------------------------------------------------------------
# Test 1: Concurrent purge on the same user — advisory lock serializes,
#         exactly one wins, the other is rejected with HTTP 409.
# ---------------------------------------------------------------------------


async def test_pg_concurrent_purge_rejected(pg_session_factory):
    s1 = pg_session_factory()
    s2 = pg_session_factory()
    assert s1.bind.dialect.name == "postgresql"
    assert s2.bind.dialect.name == "postgresql"

    from app.core.exceptions import AppException
    from app.posture import purge

    user_id = await _make_user(s1)
    await _seed_photo_event(s1, user_id, photo_keys=["concurrent.jpg"])
    await s1.commit()

    store = _slow_store(purge, delay=0.3)
    store.add_existing("concurrent.jpg")

    async def _do(db):
        return await purge.run_purge(
            db, user_id, store, trigger="user_delete", encryption_key=_TEST_KEY
        )

    outcomes = await asyncio.gather(_do(s1), _do(s2), return_exceptions=True)

    completed = [
        o for o in outcomes
        if not isinstance(o, BaseException) and getattr(o, "status", None) == "completed"
    ]
    rejected = [
        o for o in outcomes
        if isinstance(o, AppException) and o.status_code == 409
    ]

    assert len(completed) == 1, f"expected exactly 1 completed purge, got: {outcomes!r}"
    assert len(rejected) == 1, (
        f"expected exactly 1 purge rejected with 409 (purge_already_in_flight), "
        f"got: {outcomes!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: A non-terminal (freezing) purge_operation blocks BOTH assessment
#         writes and safety-signal writes with HTTP 409.
# ---------------------------------------------------------------------------


async def test_pg_freeze_blocks_assessment_and_signal(pg_session):
    assert pg_session.bind.dialect.name == "postgresql"

    from app.core.exceptions import AppException
    from app.posture import safety, service
    from app.posture.models import PurgeOperation

    user_id = await _make_user(pg_session)
    pg_session.add(
        PurgeOperation(
            user_id=user_id,
            trigger="user_delete",
            status="freezing",
            attempt_count=0,
            max_attempts=10,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
    )
    await pg_session.commit()

    uid_str = str(user_id)

    with pytest.raises(AppException) as exc_assessment:
        await service.save_self_assessment(pg_session, uid_str, "HN-01", "positive", 0)
    assert exc_assessment.value.status_code == 409

    with pytest.raises(AppException) as exc_signal:
        await safety.record_safety_signal(
            pg_session,
            uid_str,
            {
                "signal_type": "pain",
                "body_region": "head_neck",
                "related_issue_id": "HN-01",
                "severity_hint": "mild",
            },
            idempotency_key="frozen-signal-1",
        )
    assert exc_signal.value.status_code == 409


# ---------------------------------------------------------------------------
# Test 3: Scoped (consent_withdrawn) purge deletes the ai_photo event, unlinks
#         the profile FK, rebuilds from the surviving self_test event, and is
#         safety-aware (provisional while an active signal covers the issue).
# ---------------------------------------------------------------------------


async def test_pg_scoped_purge_fk_and_projection(pg_session):
    assert pg_session.bind.dialect.name == "postgresql"

    from app.posture import purge
    from app.posture.models import (
        PostureAssessmentEvent,
        PostureProfileEntry,
        PostureSafetySignal,
    )

    user_id = await _make_user(pg_session)

    self_evt = PostureAssessmentEvent(
        user_id=user_id, issue_id="HN-01", method="self_test",
        result="moderate", source="self_test", severity="moderate",
        lifecycle="active",
    )
    photo_evt = PostureAssessmentEvent(
        user_id=user_id, issue_id="HN-01", method="ai_photo",
        result="moderate", source="ai_photo", severity="moderate",
        lifecycle="active", photo_keys=["scoped-photo.jpg"],
    )
    pg_session.add_all([self_evt, photo_evt])
    await pg_session.flush()

    pg_session.add(
        PostureProfileEntry(
            user_id=user_id, issue_id="HN-01",
            combined_severity="moderate", certainty="confirmed",
            sources={}, has_conflict=False,
            risk_tier="normal", risk_version="2026-07-16-v3",
            latest_photo_event_id=photo_evt.id,
            latest_self_test_event_id=self_evt.id,
        )
    )
    pg_session.add(
        PostureSafetySignal(
            user_id=user_id, signal_type="pain", body_region="head_neck",
            related_issue_id="HN-01", severity_hint="mild",
            reported_at=datetime.now(timezone.utc), lifecycle="active",
            invalidates_until=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    await pg_session.commit()

    store = purge.FakeObjectStore()
    store.add_existing("scoped-photo.jpg")

    result = await purge.run_purge(
        pg_session, user_id, store,
        trigger="consent_withdrawn", encryption_key=_TEST_KEY,
    )
    assert result.status == "completed"

    # Photo event is gone; self_test event survives.
    remaining_events = (
        await pg_session.execute(
            select(PostureAssessmentEvent).where(
                PostureAssessmentEvent.user_id == user_id
            )
        )
    ).scalars().all()
    assert len(remaining_events) == 1
    assert remaining_events[0].source == "self_test"

    # Profile rebuilt from self_test only + safety-aware override.
    profile = (
        await pg_session.execute(
            select(PostureProfileEntry).where(
                PostureProfileEntry.user_id == user_id,
                PostureProfileEntry.issue_id == "HN-01",
            )
        )
    ).scalar_one()
    assert profile.latest_photo_event_id is None
    assert profile.latest_self_test_event_id == self_evt.id
    # Active signal for HN-01 forces provisional / null severity.
    assert profile.certainty == "provisional"
    assert profile.combined_severity is None


# ---------------------------------------------------------------------------
# Test 4: A safety signal on issue A does NOT escalate issue B (issue-scoped
#         classification), unless the signal is global.
# ---------------------------------------------------------------------------


async def test_pg_different_issue_risk_isolation(pg_session):
    assert pg_session.bind.dialect.name == "postgresql"

    from app.posture import safety
    from app.posture.models import PostureProfileEntry

    user_id = await _make_user(pg_session)
    uid_str = str(user_id)

    pg_session.add_all(
        [
            PostureProfileEntry(
                user_id=user_id, issue_id="HN-01",
                combined_severity="moderate", certainty="confirmed",
                sources={}, has_conflict=False,
                risk_tier="normal", risk_version="2026-07-16-v3",
            ),
            PostureProfileEntry(
                user_id=user_id, issue_id="ST-04",
                combined_severity="moderate", certainty="confirmed",
                sources={}, has_conflict=False,
                risk_tier="normal", risk_version="2026-07-16-v3",
            ),
        ]
    )
    await pg_session.commit()

    result = await safety.record_safety_signal(
        pg_session,
        uid_str,
        {
            "signal_type": "pain",
            "body_region": "head_neck",
            "related_issue_id": "HN-01",
            "severity_hint": "mild",
        },
        idempotency_key="isolation-1",
    )
    assert result["risk_tier"] == "cautious"

    hn = (
        await pg_session.execute(
            select(PostureProfileEntry).where(
                PostureProfileEntry.user_id == user_id,
                PostureProfileEntry.issue_id == "HN-01",
            )
        )
    ).scalar_one()
    st = (
        await pg_session.execute(
            select(PostureProfileEntry).where(
                PostureProfileEntry.user_id == user_id,
                PostureProfileEntry.issue_id == "ST-04",
            )
        )
    ).scalar_one()

    # HN-01 downgraded by its own signal; ST-04 untouched (issue-scoped).
    assert hn.risk_tier == "cautious"
    assert st.risk_tier == "normal"
    assert st.certainty == "confirmed"


# ---------------------------------------------------------------------------
# Test 5: Retry worker uses FOR UPDATE SKIP LOCKED — two concurrent workers
#         each claim a DIFFERENT job; no double processing.
# ---------------------------------------------------------------------------


async def test_pg_retry_no_double_claim(pg_session_factory):
    from app.posture import purge
    from app.posture.models import PostureAssessmentEvent, PosturePurgeTombstone, PurgeOperation

    seed = pg_session_factory()
    assert seed.bind.dialect.name == "postgresql"

    seeded = []
    for tag in ("job-a", "job-b"):
        uid = await _make_user(seed)
        evt = await _seed_photo_event(seed, uid, photo_keys=[f"{tag}.jpg"])
        await seed.flush()
        op_id = _uuid.uuid4()
        encrypted = purge.encrypt_object_keys(
            [f"{tag}.jpg"], _TEST_KEY,
            operation_id=str(op_id), user_id=str(uid),
            trigger="user_delete", key_version=purge.KEY_VERSION,
        )
        seed.add(
            PurgeOperation(
                id=op_id, user_id=uid, trigger="user_delete",
                status="failed_oss_retry",
                encrypted_object_keys=encrypted,
                target_event_ids=[str(evt.id)],
                attempt_count=1, max_attempts=5,
                next_retry_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        seeded.append((op_id, uid))
    await seed.commit()

    store = _slow_store(purge, delay=0.15)
    store.add_existing("job-a.jpg")
    store.add_existing("job-b.jpg")

    w1 = pg_session_factory()
    w2 = pg_session_factory()

    r1, r2 = await asyncio.gather(
        purge.run_due_purge_jobs(w1, store, _TEST_KEY),
        purge.run_due_purge_jobs(w2, store, _TEST_KEY),
    )

    all_results = list(r1) + list(r2)
    completed = [r for r in all_results if r.status == "completed"]
    assert len(completed) == 2, (
        f"expected both jobs completed once (no double claim), got: {all_results!r}"
    )

    # Verify on a fresh session to avoid stale identity-map reads.
    verify = pg_session_factory()
    for op_id, _uid in seeded:
        op = (
            await verify.execute(
                select(PurgeOperation).where(PurgeOperation.id == op_id)
            )
        ).scalar_one()
        assert op.status == "completed", f"op {op_id} not completed: {op.status}"
        assert op.user_id is None  # scrubbed on completion (方案 B)

    tombstones = (
        await verify.execute(select(PosturePurgeTombstone))
    ).scalars().all()
    assert len(tombstones) == 2  # exactly one tombstone per job, no duplicates


# ---------------------------------------------------------------------------
# Test 6: A user with ONLY a goal (no events / profiles / signals) is still
#         fully purged by an account_deletion trigger.
# ---------------------------------------------------------------------------


async def test_pg_goal_only_account_purge(pg_session):
    assert pg_session.bind.dialect.name == "postgresql"

    from app.posture import purge
    from app.posture.models import PostureUserGoal

    user_id = await _make_user(pg_session)
    pg_session.add(
        PostureUserGoal(
            user_id=user_id, issue_id="HN-01", priority_rank=1,
            suggestion_id="s1", profile_version="v1",
            rule_version="r1", risk_version="rv1",
        )
    )
    await pg_session.commit()

    store = purge.FakeObjectStore()
    result = await purge.run_purge(
        pg_session, user_id, store,
        trigger="account_deletion", encryption_key=_TEST_KEY,
    )
    assert result.status == "completed"

    goals = (
        await pg_session.execute(
            select(PostureUserGoal).where(PostureUserGoal.user_id == user_id)
        )
    ).scalars().all()
    assert goals == []


# ---------------------------------------------------------------------------
# Test 7: DB-retry tombstone consistency — when OSS already succeeded (stored
#         oss_outcome) but the DB delete failed, the retry writes a tombstone
#         carrying the STORED oss_outcome (not recomputed), and completes.
# ---------------------------------------------------------------------------


async def test_pg_db_retry_tombstone_consistent(pg_session):
    assert pg_session.bind.dialect.name == "postgresql"

    from app.posture import purge
    from app.posture.models import PosturePurgeTombstone, PurgeOperation

    user_id = await _make_user(pg_session)
    evt = await _seed_photo_event(pg_session, user_id, photo_keys=["oss-ok.jpg"])
    await pg_session.commit()

    op_id = _uuid.uuid4()
    # OSS already completed (keys cleared); DB delete failed -> failed_db_retry.
    # The stored oss_outcome is preserved in target_signal_ids (review fix #10).
    pg_session.add(
        PurgeOperation(
            id=op_id, user_id=user_id, trigger="user_delete",
            status="failed_db_retry",
            encrypted_object_keys=None,  # cleared after OSS success
            target_event_ids=[str(evt.id)],
            target_signal_ids={
                "oss_outcome": "oss_deleted",
                "per_key": {"oss-ok.jpg": "deleted"},
            },
            attempt_count=1, max_attempts=5,
            next_retry_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
    )
    await pg_session.commit()

    store = purge.FakeObjectStore()  # no live OSS calls happen on db-retry
    results = await purge.run_due_purge_jobs(pg_session, store, _TEST_KEY)

    assert len(results) == 1
    assert results[0].status == "completed"
    assert results[0].tombstone_receipt_id is not None

    tomb = (
        await pg_session.execute(select(PosturePurgeTombstone))
    ).scalar_one()
    # Tombstone carries the STORED oss_outcome verbatim (not recomputed).
    assert tomb.object_delete_status == "oss_deleted"

    op = (
        await pg_session.execute(
            select(PurgeOperation).where(PurgeOperation.id == op_id)
        )
    ).scalar_one()
    assert op.status == "completed"


async def test_pg_purge_waits_for_uncommitted_writer(pg_session_factory):
    """The no-data decision is made only after taking the shared user lock."""
    from app.posture import purge
    from app.posture.models import PostureAssessmentEvent
    from app.posture.user_lock import acquire_user_transaction_lock

    seed = pg_session_factory()
    user_id = await _make_user(seed)
    await seed.commit()

    writer = pg_session_factory()
    deleter = pg_session_factory()
    await acquire_user_transaction_lock(writer, str(user_id))
    writer.add(
        PostureAssessmentEvent(
            user_id=user_id,
            issue_id="HN-01",
            method="self_test",
            result="moderate",
            source="self_test",
            severity="moderate",
            lifecycle="active",
        )
    )
    await writer.flush()

    purge_task = asyncio.create_task(
        purge.run_purge(
            deleter,
            user_id,
            purge.FakeObjectStore(),
            trigger="account_deletion",
            encryption_key=_TEST_KEY,
        )
    )
    await asyncio.sleep(0.2)
    assert not purge_task.done(), "purge returned before the locked writer committed"

    await writer.commit()
    result = await asyncio.wait_for(purge_task, timeout=5)
    assert result.status == "completed"

    verify = pg_session_factory()
    remaining = (
        await verify.execute(
            select(PostureAssessmentEvent).where(
                PostureAssessmentEvent.user_id == user_id
            )
        )
    ).scalars().all()
    assert remaining == []


async def test_pg_expired_lease_does_not_duplicate_active_worker(
    pg_session_factory, monkeypatch
):
    """A stale-looking lease may be reclaimed, but the shared user lock and
    post-lock refresh must prevent two live workers from executing one job."""
    from app.posture import purge
    from app.posture.models import PosturePurgeTombstone, PurgeOperation

    monkeypatch.setattr(purge, "LEASE_DURATION", timedelta(milliseconds=100))

    seed = pg_session_factory()
    user_id = await _make_user(seed)
    event = await _seed_photo_event(seed, user_id, photo_keys=["slow-lease.jpg"])
    await seed.flush()
    operation_id = _uuid.uuid4()
    encrypted = purge._encrypt_with_resolved_key(
        ["slow-lease.jpg"],
        _TEST_KEY,
        purge.KEY_VERSION,
        operation_id=str(operation_id),
        user_id=str(user_id),
        trigger="account_deletion",
    )
    seed.add(
        PurgeOperation(
            id=operation_id,
            user_id=user_id,
            trigger="account_deletion",
            status="failed_oss_retry",
            encrypted_object_keys=encrypted,
            target_event_ids=[str(event.id)],
            attempt_count=0,
            max_attempts=5,
            next_retry_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
    )
    await seed.commit()

    class CountingSlowStore(purge.FakeObjectStore):
        def __init__(self):
            super().__init__()
            self.calls = 0

        async def delete_object(self, key):
            self.calls += 1
            await asyncio.sleep(0.4)
            await super().delete_object(key)

    store = CountingSlowStore()
    store.add_existing("slow-lease.jpg")
    worker_one = pg_session_factory()
    worker_two = pg_session_factory()

    async def run_first():
        return await purge.run_due_purge_jobs(worker_one, store, _TEST_KEY)

    async def run_second():
        await asyncio.sleep(0.2)
        return await purge.run_due_purge_jobs(worker_two, store, _TEST_KEY)

    first, second = await asyncio.gather(run_first(), run_second())
    assert [result.status for result in first] == ["completed"]
    assert [result.status for result in second] == ["idempotent_noop"]
    assert store.calls == 1

    verify = pg_session_factory()
    tombstones = (
        await verify.execute(select(PosturePurgeTombstone))
    ).scalars().all()
    assert len(tombstones) == 1
    operation = await verify.get(PurgeOperation, operation_id)
    assert operation.status == "completed"


async def test_pg_initial_purge_lease_does_not_duplicate_oss_delete(
    pg_session_factory, monkeypatch
):
    """The synchronous initial path holds the same user lock while OSS runs."""
    from app.posture import purge
    from app.posture.models import PosturePurgeTombstone

    monkeypatch.setattr(purge, "LEASE_DURATION", timedelta(milliseconds=100))

    seed = pg_session_factory()
    user_id = await _make_user(seed)
    await _seed_photo_event(seed, user_id, photo_keys=["initial-slow.jpg"])
    await seed.commit()

    class CountingSlowStore(purge.FakeObjectStore):
        def __init__(self):
            super().__init__()
            self.calls = 0

        async def delete_object(self, key):
            self.calls += 1
            await asyncio.sleep(0.4)
            await super().delete_object(key)

    store = CountingSlowStore()
    store.add_existing("initial-slow.jpg")
    initial_session = pg_session_factory()
    retry_session = pg_session_factory()

    async def run_initial():
        return await purge.run_purge(
            initial_session,
            user_id,
            store,
            trigger="account_deletion",
            encryption_key=_TEST_KEY,
        )

    async def run_retry_worker():
        await asyncio.sleep(0.2)
        return await purge.run_due_purge_jobs(retry_session, store, _TEST_KEY)

    initial, retry = await asyncio.gather(run_initial(), run_retry_worker())
    statuses = [initial.status] + [result.status for result in retry]
    assert sorted(statuses) == ["completed", "idempotent_noop"]
    assert store.calls == 1

    verify = pg_session_factory()
    tombstones = (
        await verify.execute(select(PosturePurgeTombstone))
    ).scalars().all()
    assert len(tombstones) == 1
