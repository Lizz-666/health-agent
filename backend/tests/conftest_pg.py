"""PostgreSQL 16 Docker integration test fixtures.

Spins up a real ``postgres:16`` Docker container on a RANDOM port in the
55600-55699 range with database name ``posture_pg_test``, runs the alembic
migrations, prints the PostgreSQL version (``SELECT version()``), and yields
real asyncpg ``AsyncSession`` fixtures.

CRITICAL: PG tests run in the SAME pytest session as the SQLite tests. The
``tests/conftest.py`` SQLite monkey-patch (``pg.UUID`` -> ``_SQLiteUUID``,
``JSONB`` -> ``JSON``) is PROVEN to roundtrip correctly on real PostgreSQL
(UUID and JSONB), so PG tests are NEVER skipped merely because that patch is
active. The ONLY skip condition is Docker being unavailable.

EXTERNAL DSN SAFETY: when ``PG_TEST_DSN`` is set (instead of the self-built
Docker container), the per-test ``TRUNCATE ... CASCADE`` could wipe a
development database. The external path therefore enforces mandatory safety
guards (see ``_validate_external_dsn`` / ``_verify_connected_db_is_test``):
the database name MUST match a test pattern, ``PG_TEST_ALLOW_DESTRUCTIVE=1``
MUST be set, forbidden production names are rejected, and the DSN password is
never logged. Any guard failure raises ``PGSafetyError`` (hard fail, never a
skip) BEFORE any connection, TRUNCATE or alembic operation.
"""

import asyncio
import os
import random
import socket
import subprocess
import time
from pathlib import Path
from typing import Callable, List, Optional
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool


# ---------------------------------------------------------------------------
# Docker availability — the single gate for PG tests
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    """Return True iff the Docker daemon answers ``docker version``."""
    try:
        result = subprocess.run(
            ["docker", "version"], capture_output=True, timeout=15
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


_DOCKER_OK = _docker_available()
_PG_TEST_DSN_ENV = os.environ.get("PG_TEST_DSN", "")
_SKIP_PG = os.environ.get("VERIFY_SKIP_PG", "").strip() == "1"

# PG tests run whenever Docker is reachable OR an explicit PG_TEST_DSN is set.
# The SQLite monkey-patch in conftest.py does NOT disable PG tests.
pg_available = not _SKIP_PG and (_DOCKER_OK or bool(_PG_TEST_DSN_ENV))

skip_reason = (
    "Docker not available (docker version failed and PG_TEST_DSN not set)"
    if not pg_available
    else "PostgreSQL available"
)

requires_pg = pytest.mark.skipif(not pg_available, reason=skip_reason)


@pytest.fixture(autouse=True)
def record_pg_test_execution(request):
    """Record every marked PG test that reaches fixture setup."""
    if request.node.get_closest_marker("requires_pg") is None:
        return
    evidence_file = os.environ.get("PG_TEST_EVIDENCE_FILE", "").strip()
    if evidence_file and pg_available:
        with Path(evidence_file).open("a", encoding="utf-8") as fh:
            fh.write(f"TEST:{request.node.nodeid}\n")


# ---------------------------------------------------------------------------
# External PG_TEST_DSN safety guards
# ---------------------------------------------------------------------------
# The Docker self-built container path (``_start_container``) is inherently
# safe: it creates its OWN isolated ``posture_pg_test`` database on a random
# port. The external ``PG_TEST_DSN`` path, however, is dangerous: if a
# developer points it at a development/production database, the per-test
# ``TRUNCATE TABLE ... RESTART IDENTITY CASCADE`` (see ``_truncate_all``) would
# WIPE that database. These guards make that impossible: a misconfigured DSN
# fails loudly (raises — never skips) BEFORE any connection, TRUNCATE or alembic
# operation runs.
#
# All guards below are PURE functions so they can be unit-tested without a
# database (see ``tests/test_pg_safety_guard.py``).

# The canonical self-built test database name. External DSNs MUST target a
# database whose name is recognisably a throwaway test database.
_TEST_DB_NAME = "posture_pg_test"

# Database names that are NEVER allowed for an external destructive DSN, even
# if they happened to match a test suffix. These are common production /
# development / system catalog names.
_FORBIDDEN_DB_NAMES = frozenset({
    "postgres", "posture_app", "posture", "health", "production",
    "app", "main", "default", "template1", "template0",
})

class PGSafetyError(RuntimeError):
    """Raised when an external ``PG_TEST_DSN`` fails a safety guard.

    A safety failure is a HARD error (never a ``pytest.skip``): a DSN that
    could destroy a development database must abort the session rather than
    silently skip the PG tests and leave the bad DSN active.
    """


def _mask_dsn(dsn: str) -> str:
    """Return ``dsn`` with the password segment replaced by ``***``.

    Safe to run on arbitrary strings (e.g. alembic subprocess stdout/stderr):
    only the ``://user:password@`` pattern is touched, so output without a
    password is returned unchanged. Used for ALL DSN-bearing logs/output.
    """
    marker = "://"
    start = dsn.find(marker)
    if start < 0:
        return dsn
    authority_start = start + len(marker)
    authority_end = len(dsn)
    for separator in ("/", " ", "\n", "\r", "\t"):
        pos = dsn.find(separator, authority_start)
        if pos >= 0:
            authority_end = min(authority_end, pos)
    authority = dsn[authority_start:authority_end]
    at = authority.rfind("@")
    colon = authority.find(":")
    if colon < 0 or at <= colon:
        return dsn
    masked_authority = authority[: colon + 1] + "***" + authority[at:]
    return dsn[:authority_start] + masked_authority + dsn[authority_end:]


def _parse_db_name_from_dsn(dsn: str) -> Optional[str]:
    """Extract the database name from a SQLAlchemy asyncpg DSN.

    Handles query strings (``?sslmode=require``). Returns None if no database
    path is present.
    """
    try:
        path = urlparse(dsn).path  # e.g. "/posture_pg_test"
    except (ValueError, TypeError):
        return None
    if not path or not path.startswith("/"):
        return None
    name = path[1:].split("?", 1)[0].strip()
    return name or None


def _is_test_db_name(name: Optional[str]) -> bool:
    """Return True iff ``name`` looks like a throwaway test database.

    Accepts only the canonical ``posture_pg_test`` or a name beginning with
    ``posture_pg_test_``. ``_FORBIDDEN_DB_NAMES`` are rejected separately by
    the caller (they take precedence over a matching prefix).
    """
    if not name:
        return False
    n = name.strip().lower()
    if n == _TEST_DB_NAME:
        return True
    if n.startswith("posture_pg_test_"):  # posture_pg_test_20260711, etc.
        return True
    return False


def _validate_external_dsn(dsn: str) -> str:
    """Run the cheap, connection-free safety guards on an external DSN.

    Enforces, in order:
      1. ``PG_TEST_ALLOW_DESTRUCTIVE=1`` is set (explicit opt-in).
      2. The DSN parses to a database name.
      3. The database name is NOT a forbidden production/development name.
      4. The database name matches the test pattern.

    Raises ``PGSafetyError`` on the first failure. Returns the PASSWORD-MASKED
    DSN (safe to print). MUST be called before any connection or alembic op.
    """
    if os.environ.get("PG_TEST_ALLOW_DESTRUCTIVE", "").strip() != "1":
        raise PGSafetyError(
            "PG_TEST_ALLOW_DESTRUCTIVE=1 required for external PG_TEST_DSN "
            "(refusing to connect to / TRUNCATE an unvetted database). Set it "
            "explicitly to acknowledge the external DSN will be wiped."
        )
    db_name = _parse_db_name_from_dsn(dsn)
    if not db_name:
        raise PGSafetyError(
            f"could not parse a database name from PG_TEST_DSN "
            f"({_mask_dsn(dsn)}); refusing to proceed"
        )
    if db_name.lower() in _FORBIDDEN_DB_NAMES:
        raise PGSafetyError(
            f"PG_TEST_DSN targets {db_name!r}, a forbidden "
            f"production/development database name; refusing to TRUNCATE"
        )
    if not _is_test_db_name(db_name):
        raise PGSafetyError(
            f"PG_TEST_DSN database name {db_name!r} does not match the test "
            f"pattern ({_TEST_DB_NAME} / posture_pg_test_*); "
            f"refusing to TRUNCATE"
        )
    return _mask_dsn(dsn)


async def _verify_connected_db_is_test(dsn: str) -> str:
    """Defence-in-depth: assert the PHYSICAL database matches the test pattern.

    Connects via the real asyncpg DSN and reads ``SELECT current_database()``.
    This catches proxies / pgBouncer / connection poolers that route the
    session to a different physical database than the DSN path implies. Raises
    ``PGSafetyError`` if the connected database is forbidden or not a test DB.
    Returns the actual database name. MUST run before any TRUNCATE/alembic.
    """
    engine = create_async_engine(dsn, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            actual = (await conn.execute(text("SELECT current_database()"))).scalar()
    finally:
        await engine.dispose()
    actual = str(actual or "").strip()
    if actual.lower() in _FORBIDDEN_DB_NAMES:
        raise PGSafetyError(
            f"SELECT current_database() returned {actual!r}, a forbidden "
            f"production/development name; refusing to TRUNCATE"
        )
    if not _is_test_db_name(actual):
        raise PGSafetyError(
            f"SELECT current_database() returned {actual!r}, which does not "
            f"match the test pattern ({_TEST_DB_NAME} / posture_pg_test_*); "
            f"refusing to TRUNCATE"
        )
    return actual


# ---------------------------------------------------------------------------
# Container lifecycle (module-level state, shared across the whole session)
# ---------------------------------------------------------------------------

_PG_PASSWORD = "testpass"
_PG_DB = "posture_pg_test"
_PORT_LOW = 55600
_PORT_HIGH = 55699

_container_name: str = ""
_pg_port: int = 0
_pg_dsn: str = ""
_pg_version: str = ""


def _find_free_port() -> int:
    """Pick a free port in 55600-55699; fall back to an OS-chosen port."""
    for _ in range(80):
        port = random.randint(_PORT_LOW, _PORT_HIGH)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_container() -> str:
    """Start ``postgres:16`` on a random port. Return the asyncpg DSN."""
    global _container_name, _pg_port, _pg_dsn
    _pg_port = _find_free_port()
    _container_name = f"posture_pg_test_{random.randint(100000, 999999)}"
    cmd = [
        "docker", "run", "-d",
        "--name", _container_name,
        "-e", f"POSTGRES_PASSWORD={_PG_PASSWORD}",
        "-e", f"POSTGRES_DB={_PG_DB}",
        "-p", f"{_pg_port}:5432",
        "postgres:16",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"docker run failed (exit {result.returncode}):\n{result.stderr}"
        )
    _pg_dsn = (
        f"postgresql+asyncpg://postgres:{_PG_PASSWORD}"
        f"@localhost:{_pg_port}/{_PG_DB}"
    )
    return _pg_dsn


async def _probe(dsn: str, timeout: float = 60.0) -> str:
    """Wait until PG accepts connections via the real asyncpg DSN.

    Returns the ``SELECT version()`` string (proves the DSN roundtrips).
    """
    engine = create_async_engine(dsn, poolclass=NullPool)
    deadline = time.time() + timeout
    last_error: Optional[Exception] = None
    try:
        while time.time() < deadline:
            try:
                async with engine.connect() as conn:
                    version = (
                        await conn.execute(text("SELECT version()"))
                    ).scalar()
                    return str(version)
            except Exception as exc:  # noqa: BLE001 - retry until ready
                last_error = exc
                await asyncio.sleep(0.5)
        raise RuntimeError(
            f"PostgreSQL not ready after {timeout}s (last error: {last_error})"
        )
    finally:
        await engine.dispose()


def _run_alembic(dsn: str) -> None:
    """Run ``alembic upgrade head`` as a subprocess.

    alembic's env.py reads ``settings.DATABASE_URL`` which pydantic loads from
    the ``DATABASE_URL`` environment variable, so we export it for the child.
    The child process is NOT monkey-patched (it never imports tests/conftest),
    so migrations create native PostgreSQL UUID/JSONB columns.
    """
    env = os.environ.copy()
    env["DATABASE_URL"] = dsn
    result = subprocess.run(
        ["python", "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head failed (exit {result.returncode}):\n"
            f"--- stdout ---\n{_mask_dsn(result.stdout)}\n"
            f"--- stderr ---\n{_mask_dsn(result.stderr)}"
        )
    print(
        f"[conftest_pg] alembic upgrade head OK:\n"
        f"{_mask_dsn(result.stdout.strip())}"
    )


def _stop_container() -> None:
    global _container_name
    if _container_name:
        subprocess.run(
            ["docker", "rm", "-f", _container_name],
            capture_output=True,
            timeout=30,
        )
        _container_name = ""


# Tear the container down even if the process is interrupted.
import atexit  # noqa: E402

atexit.register(_stop_container)


# ---------------------------------------------------------------------------
# Session-scoped engine + sessionmaker (lazily created, shared by all PG tests)
# ---------------------------------------------------------------------------

_engine = None
_SessionLocal: Optional[async_sessionmaker] = None


def _get_engine_and_sessionmaker(dsn: str):
    """Return the shared async engine + sessionmaker, creating them once."""
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_async_engine(dsn, poolclass=NullPool, echo=False)
        _SessionLocal = async_sessionmaker(
            _engine, class_=AsyncSession, expire_on_commit=False
        )
    return _engine, _SessionLocal


async def _truncate_all(engine) -> None:
    """Wipe every existing data table without assuming the schema is at head."""
    from app.db.base import Base

    async with engine.connect() as conn:
        existing = set(
            await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        )
        names = ", ".join(
            '"{}"'.format(table)
            for table in sorted(existing.intersection(Base.metadata.tables.keys()))
        )
        if not names:
            return
        await conn.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))
        await conn.commit()


# ---------------------------------------------------------------------------
# Idempotent one-shot setup (called by every PG fixture; not a fixture itself,
# so there is no fixture-on-fixture dependency to resolve).
# ---------------------------------------------------------------------------

_setup_done = False
_setup_dsn = ""


def _ensure_pg_ready() -> str:
    """Start the container + run migrations exactly once. Returns the DSN.

    Skips (raises ``Skipped``) if Docker is unavailable. Safe to call from
    multiple fixtures; only the first call performs the work.

    External ``PG_TEST_DSN`` path enforces ALL safety guards
    (``_validate_external_dsn`` + ``_verify_connected_db_is_test``) and FAILS
    LOUDLY (never skips) on a guard violation, so a misconfigured DSN can never
    point at a development/production database.
    """
    global _setup_done, _setup_dsn, _pg_version
    if _setup_done:
        return _setup_dsn

    _masked_dsn: str = ""
    if _PG_TEST_DSN_ENV:
        # External DSN: enforce every safety guard BEFORE connecting. A
        # violation is a hard PGSafetyError (not a skip) so the bad DSN never
        # reaches a TRUNCATE or alembic operation.
        _masked_dsn = _validate_external_dsn(_PG_TEST_DSN_ENV)
        _setup_dsn = _PG_TEST_DSN_ENV
    else:
        if not _DOCKER_OK:
            pytest.skip("Docker not available")
        _setup_dsn = _start_container()
        _masked_dsn = _mask_dsn(_setup_dsn)

    # Readiness + version via a real asyncpg connection. This sync function
    # runs outside any pytest-asyncio event loop, so asyncio.run() is safe.
    _pg_version = asyncio.run(_probe(_setup_dsn))

    # Defence-in-depth (external DSN only): verify the PHYSICAL database we
    # connected to matches the test pattern, catching proxies/pgBouncer that
    # route elsewhere. Runs BEFORE alembic/TRUNCATE.
    if _PG_TEST_DSN_ENV:
        connected_db = asyncio.run(_verify_connected_db_is_test(_setup_dsn))
        print(
            f"[conftest_pg] connected database verified as test DB: "
            f"{connected_db}"
        )

    print(f"[conftest_pg] PostgreSQL version: {_pg_version}")
    # NEVER print the DSN password — only the masked form.
    print(f"[conftest_pg] DSN (password masked): {_masked_dsn}")
    print(
        f"[conftest_pg] container: {_container_name or '(external)'} "
        f"port: {_pg_port or 'n/a'}"
    )

    _run_alembic(_setup_dsn)
    evidence_file = os.environ.get("PG_TEST_EVIDENCE_FILE", "").strip()
    if evidence_file:
        Path(evidence_file).write_text(
            f"VERSION:{_pg_version}\n", encoding="utf-8")
    _setup_done = True
    return _setup_dsn


# ---------------------------------------------------------------------------
# Fixtures (registered into pytest via conftest.py)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pg_dsn() -> str:
    """Return the live PostgreSQL DSN string for direct use.

    Triggers the one-shot container/migration setup. This is a SYNC
    session-scoped fixture, so ``asyncio.run()`` inside ``_ensure_pg_ready``
    runs with no competing event loop. Container teardown is handled by the
    ``atexit`` handler (robust against interruptions).
    """
    return _ensure_pg_ready()


@pytest_asyncio.fixture
async def pg_session(pg_dsn) -> AsyncSession:
    """Function-scoped real PostgreSQL AsyncSession.

    ``pg_dsn`` (sync, session-scoped) is resolved BEFORE this async body runs,
    so all container/migration setup happens outside the event loop. Asserts
    ``dialect.name == 'postgresql'``. Each test gets its own session; all data
    tables are truncated after the test for isolation.
    """
    engine, SessionLocal = _get_engine_and_sessionmaker(pg_dsn)
    assert engine.dialect.name == "postgresql", (
        f"pg_session MUST be backed by PostgreSQL, got {engine.dialect.name}"
    )
    session = SessionLocal()
    assert session.bind.dialect.name == "postgresql"
    try:
        yield session
    finally:
        try:
            await session.rollback()
        except Exception:
            pass
        await session.close()
        await _truncate_all(engine)


@pytest_asyncio.fixture
async def pg_session_factory(pg_dsn) -> Callable[[], AsyncSession]:
    """Return a callable that creates fresh independent sessions (same engine).

    Used by concurrency tests needing multiple simultaneous sessions backed by
    real PostgreSQL advisory locks. All created sessions are closed and all
    tables are truncated after the test.
    """
    engine, SessionLocal = _get_engine_and_sessionmaker(pg_dsn)
    assert engine.dialect.name == "postgresql", (
        f"pg_session_factory MUST be backed by PostgreSQL, got {engine.dialect.name}"
    )
    created: List[AsyncSession] = []

    def _make() -> AsyncSession:
        s = SessionLocal()
        assert s.bind.dialect.name == "postgresql"
        created.append(s)
        return s

    try:
        yield _make
    finally:
        for s in created:
            try:
                await s.rollback()
            except Exception:
                pass
            try:
                await s.close()
            except Exception:
                pass
        await _truncate_all(engine)
