"""Shared user-level transaction lock (hardening fix #1).

A single advisory-lock domain serializes ALL user-scoped write paths:
  * service.py  save_self_assessment / save_photo_assessment
  * safety.py   record_safety_signal
  * purge.py    run_purge (start / completion / cancel / retry resume)

PostgreSQL: ``pg_advisory_xact_lock(hashtext(user_id))`` — held until COMMIT.
SQLite (test DB): single-writer, no advisory locks → no-op.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def acquire_user_transaction_lock(db: AsyncSession, user_id: str) -> None:
    """Acquire a per-user advisory transaction lock.

    The lock is released automatically at COMMIT/ROLLBACK (xact-scoped).
    On SQLite this is a no-op (single-writer semantics).
    """
    if db.bind.dialect.name == "sqlite":
        return
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
        {"k": user_id},
    )
