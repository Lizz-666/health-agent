"""Explicit synthetic backend for the Phase 5 Android business smoke.

Launch only from ``backend`` with::

    python -m uvicorn tests.agent_device_server:app --host 0.0.0.0 --port 8000

Production code never imports this module and has no selector for it. It uses a
disposable SQLite file, fixed synthetic credentials, and ScriptedProvider.
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select


_DEVICE_DB_PATH = Path(__file__).resolve().parents[1] / "phase5_device_smoke.db"
_DEVICE_DB_URL = f"sqlite+aiosqlite:///{_DEVICE_DB_PATH.as_posix()}"
_configured_test_db = os.environ.get("TEST_DB_URL")
if _configured_test_db not in (None, _DEVICE_DB_URL):
    raise RuntimeError(
        "agent_device_server refuses to use an externally configured TEST_DB_URL"
    )
os.environ["TEST_DB_URL"] = _DEVICE_DB_URL

from tests.conftest import TestSession, test_engine  # noqa: E402
from app.agent.models import AgentActionProposal  # noqa: E402
from app.agent.provider import ScriptedProvider  # noqa: E402
from app.auth.models import User  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.health.models import WeightRecord  # noqa: E402
from tests.agent_app_factory import create_agent_test_app  # noqa: E402


SYNTHETIC_PHONE = "13900000000"
SYNTHETIC_PASSWORD = "synthetic-phase5-smoke"

settings.DEV_MODE = True
settings.DEV_ADMIN_PHONE = SYNTHETIC_PHONE
settings.DEV_ADMIN_PASSWORD = SYNTHETIC_PASSWORD
settings.AGENT_RUNTIME_ENABLED = True
settings.AGENT_PROVIDER_ID = "dashscope"
settings.AGENT_MODEL_ID = "qwen-synthetic-device"
settings.AGENT_DISCLOSURE_VERSION = "agent-cloud-v1"
settings.DASHSCOPE_API_KEY = "synthetic-test-key"
settings.AGENT_AUDIT_HMAC_KEY = "d" * 32
settings.AGENT_AUDIT_HMAC_KEY_VERSION = "device-v1"

_provider = ScriptedProvider(
    [
        {
            "type": "read_tool_call",
            "tool_name": "get_health_profile_summary",
            "arguments": {},
        },
        {
            "type": "answer",
            "message_code": "agent_answer_ready",
            "references": ["get_health_profile_summary"],
        },
        {
            "type": "action_proposal",
            "tool_name": "create_weight_record",
            "arguments": {
                "recorded_at": datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                "weight_kg": 70.5,
            },
        },
    ]
)


async def _override_db():
    async with TestSession() as db:
        yield db


app = create_agent_test_app(
    provider=_provider,
    get_db_override=_override_db,
)


@asynccontextmanager
async def _device_lifespan(_app):
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with TestSession() as db:
        db.add(User(id=uuid.uuid4(), phone=SYNTHETIC_PHONE))
        await db.commit()
    yield


app.router.lifespan_context = _device_lifespan


@app.get("/smoke/evidence")
async def smoke_evidence():
    async with TestSession() as db:
        weight_count = await db.scalar(
            select(func.count()).select_from(WeightRecord)
        )
        executed_count = await db.scalar(
            select(func.count())
            .select_from(AgentActionProposal)
            .where(AgentActionProposal.status == "executed")
        )
    return {
        "synthetic_only": True,
        "provider_calls": len(_provider.calls),
        "weight_records": weight_count or 0,
        "executed_proposals": executed_count or 0,
    }
