import uuid as _uuid
import sqlite3
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import String, event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# SQLite 不原生支持 UUID，注册适配器让 sqlite3 能处理 uuid.UUID 对象
sqlite3.register_adapter(_uuid.UUID, lambda u: str(u))

# 先修补 PostgreSQL UUID/JSONB 让它们在 SQLite 下可用
import sqlalchemy.dialects.postgresql as pg

class _SQLiteUUID(String):
    """SQLite 不支持 PostgreSQL UUID，用 CHAR(36) 替代"""
    cache_ok = True

    def __init__(self, as_uuid=False, **kw):
        super().__init__(36)
        self.as_uuid = as_uuid

    def bind_processor(self, dialect):
        def process(value):
            if value is not None:
                if isinstance(value, _uuid.UUID):
                    return str(value)  # 保留连字符
                return str(value)
            return value
        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is not None and self.as_uuid:
                if isinstance(value, str):
                    return _uuid.UUID(value)
            return value
        return process

    def literal_processor(self, dialect):
        def process(value):
            if value is not None:
                return f"'{str(value)}'"
            return "NULL"
        return process

    def coerce_compared_value(self, op, value):
        """确保比较操作时参数也被正确处理"""
        return self

pg.UUID = _SQLiteUUID

# JSONB -> JSON
from sqlalchemy import JSON
pg.JSONB = JSON

# 修改 TypeDecorator 来处理 UUID 类型实例在 SQLite 下的参数转换
# 核心问题：ORM 模型中的 UUID(as_uuid=True) 在 import 时创建实例，
# 但该实例的 bind_processor 对 SQLite 不生效（因为它是 PG 类型）
# 解决方案：通过 engine 的 "before_cursor_execute" 事件转换参数

from app.db.base import Base
from app.db.database import get_db
from app.main import app

TEST_DB_URL = "sqlite+aiosqlite:///./test.db"

test_engine = create_async_engine(TEST_DB_URL, echo=False)


def _convert_uuid_params(params):
    """递归把参数中的 UUID 对象转为 string"""
    if params is None:
        return params
    if isinstance(params, dict):
        return {k: str(v) if isinstance(v, _uuid.UUID) else v for k, v in params.items()}
    if isinstance(params, (list, tuple)):
        return type(params)(str(v) if isinstance(v, _uuid.UUID) else v for v in params)
    return params


# 方案：在 engine 的 do_execute 层面拦截并转换 UUID 参数
# 但 SQLAlchemy 不允许直接修改 before_cursor_execute 的参数
# 最简单的方案：monkey-patch aiosqlite cursor 的 execute 方法
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
