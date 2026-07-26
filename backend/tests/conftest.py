import os
import uuid as _uuid
import sqlite3
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import String
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Determine the test DB URL (default: SQLite for fast local testing).
TEST_DB_URL = os.environ.get("TEST_DB_URL", "sqlite+aiosqlite:///./test.db")

# --- CONDITIONAL PATCH (Hardening fix #1) ---
# Only monkey-patch pg.UUID/pg.JSONB when running against SQLite.
# When TEST_DB_URL is a PG DSN, these patches are SKIPPED so PG tests
# exercise the real PostgreSQL types and dialect.
if "sqlite" in TEST_DB_URL:
    # SQLite 不原生支持 UUID，注册适配器让 sqlite3 能处理 uuid.UUID 对象
    sqlite3.register_adapter(_uuid.UUID, lambda u: str(u))

    # 先修补 PostgreSQL UUID/JSONB 让它们在 SQLite 下可用
    import sqlalchemy.dialects.postgresql as pg
    from sqlalchemy import JSON
    from sqlalchemy.types import TypeDecorator

    # Capture the REAL postgresql types before patching, so the dual types can
    # delegate to them on a real PostgreSQL connection. This makes the SAME ORM
    # models work on BOTH SQLite (CHAR(36)/JSON) and PostgreSQL (native
    # uuid/jsonb) within a single pytest session: PG integration tests run
    # alongside the SQLite tests instead of being skipped.
    _REAL_PG_UUID = pg.UUID
    _REAL_PG_JSONB = pg.JSONB

    class _DualUUID(TypeDecorator):
        """UUID stored as CHAR(36) string on SQLite, native uuid on PostgreSQL.

        On PostgreSQL it delegates to the real ``postgresql.UUID`` so the
        asyncpg driver uses its native uuid codec — avoiding the
        ``column ... is of type uuid but expression is of type character
        varying`` error that a plain VARCHAR type would trigger.
        """
        impl = String(36)
        cache_ok = True

        def __init__(self, as_uuid=False, **kw):
            super().__init__()
            self.as_uuid = as_uuid

        def load_dialect_impl(self, dialect):
            if dialect.name == "postgresql":
                return dialect.type_descriptor(_REAL_PG_UUID(as_uuid=self.as_uuid))
            return dialect.type_descriptor(String(36))

        def process_bind_param(self, value, dialect):
            if value is None:
                return None
            if dialect.name == "postgresql":
                # Let asyncpg's native uuid codec bind the UUID object.
                if isinstance(value, _uuid.UUID):
                    return value
                return _uuid.UUID(str(value))
            # SQLite: store as hyphenated string (preserves dashes).
            if isinstance(value, _uuid.UUID):
                return str(value)
            return str(value)

        def process_result_value(self, value, dialect):
            if value is None:
                return None
            if isinstance(value, _uuid.UUID):
                return value if self.as_uuid else str(value)
            if self.as_uuid:
                return _uuid.UUID(str(value))
            return value

        def coerce_compared_value(self, op, value):
            return self

    pg.UUID = _DualUUID

    class _DualJSONB(TypeDecorator):
        """JSONB native on PostgreSQL, JSON on SQLite."""
        impl = JSON
        cache_ok = True

        def load_dialect_impl(self, dialect):
            if dialect.name == "postgresql":
                return dialect.type_descriptor(_REAL_PG_JSONB())
            return dialect.type_descriptor(JSON())

    pg.JSONB = _DualJSONB

    # Monkey-patch aiosqlite to convert UUID params to strings
    import aiosqlite.core

    _original_aiosqlite_execute = aiosqlite.core.Connection._execute

    async def _patched_execute(self, fn, *args, **kwargs):
        # 把 UUID 参数转为 string
        new_args = []
        for arg in args:
            if isinstance(arg, _uuid.UUID):
                new_args.append(str(arg))
            elif isinstance(arg, (list, tuple)):
                new_args.append(type(arg)(str(a) if isinstance(a, _uuid.UUID) else a for a in arg))
            else:
                new_args.append(arg)
        return await _original_aiosqlite_execute(self, fn, *new_args, **kwargs)

    aiosqlite.core.Connection._execute = _patched_execute


from app.db.base import Base  # noqa: E402
from app.db.database import get_db  # noqa: E402
from app.main import app  # noqa: E402

test_engine = create_async_engine(TEST_DB_URL, echo=False)


TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# Register PG fixtures from conftest_pg (pytest only auto-discovers conftest.py)
from tests.conftest_pg import pg_dsn, pg_session, pg_session_factory  # noqa: F401, E402
