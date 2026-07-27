"""Alembic 迁移环境。

设计要点：
- 从应用配置 (settings.DATABASE_URL) 读取数据库 URL，不在 alembic.ini 中存放凭据。
- 显式 import 所有 ORM 模型，确保 Base.metadata 完整注册。
- 同时支持 offline（--sql，仅方言渲染，无需驱动/数据库）和 online（异步引擎）模式。
- 不打印数据库密码或完整连接串。
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# --- 应用配置与模型元数据 ---
from app.core.config import settings
from app.db.base import Base

# 显式导入所有模型模块，使其表定义注册进 Base.metadata。
# 不要删除这些 import，否则 autogenerate / 元数据比对会漏表。
import app.auth.models  # noqa: F401
import app.health.models  # noqa: F401
import app.posture.models  # noqa: F401
import app.training.models  # noqa: F401  Phase 4 plan persistence (migration 0007)

# Alembic Config 对象，提供对 alembic.ini 的访问。
config = context.config

# 从应用配置注入数据库 URL（覆盖 alembic.ini 中的空值）。
# ConfigParser 会把 "%" 当作插值语法，合法的百分号编码密码（如 p%25%40ss）
# 会触发 "invalid interpolation syntax"。这里转义为 "%%"，ConfigParser 读取时
# 会还原为单个 "%"，因此 online 引擎拿到的仍是原始有效 URL。
# 不修改全局 settings，不记录 URL。
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

# 日志配置。
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 目标元数据：用于 autogenerate 和一致性校验。
target_metadata = Base.metadata


def _offline_url() -> str:
    """离线渲染用的 URL。

    离线模式只需要方言信息（postgresql），不需要驱动或真实连接。
    去掉 ``+asyncpg`` 等驱动后缀，避免离线渲染时尝试加载异步驱动。
    """
    url = settings.DATABASE_URL
    if url.startswith("postgresql+"):
        # postgresql+asyncpg://... -> postgresql://...
        return "postgresql://" + url.split("://", 1)[1]
    return url


def run_migrations_offline() -> None:
    """离线模式：仅生成 SQL，不连接数据库。"""
    context.configure(
        url=_offline_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """在线模式：使用异步引擎执行迁移。"""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
