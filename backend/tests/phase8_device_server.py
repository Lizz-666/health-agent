"""Explicit synthetic backend for Phase 8 real-device acceptance.

Launch only from ``backend`` with::

    python -m uvicorn tests.phase8_device_server:app --host 0.0.0.0 --port 8000

Production code never imports this module and has no selector for it.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path


PHASE8_DB_PATH = Path(__file__).resolve().parents[1] / "phase8_acceptance.db"
PHASE8_DB_URL = f"sqlite+aiosqlite:///{PHASE8_DB_PATH.as_posix()}"
configured_test_db = os.environ.get("TEST_DB_URL")
if configured_test_db not in (None, PHASE8_DB_URL):
    raise RuntimeError(
        "phase8_device_server refuses externally configured TEST_DB_URL"
    )
os.environ["TEST_DB_URL"] = PHASE8_DB_URL

from app.core.config import settings  # noqa: E402
from tests.conftest import TestSession, test_engine  # noqa: E402
from tests.phase8_app_factory import create_phase8_test_app  # noqa: E402
from tests.phase8_fixtures import (  # noqa: E402
    Checkpoint,
    Phase8Control,
    ProviderController,
    SYNTHETIC_PASSWORD,
    SYNTHETIC_PHONE,
)


settings.DEV_MODE = True
settings.DEV_ADMIN_PHONE = SYNTHETIC_PHONE
settings.DEV_ADMIN_PASSWORD = SYNTHETIC_PASSWORD
settings.PHOTO_ANALYSIS_ENABLED = False
settings.NUTRITION_RUNTIME_ENABLED = True
settings.AGENT_RUNTIME_ENABLED = True
settings.AGENT_PROVIDER_ID = "scripted-phase8"
settings.AGENT_MODEL_ID = "synthetic-phase8"
settings.AGENT_DISCLOSURE_VERSION = "synthetic-phase8-v1"
settings.AGENT_AUDIT_HMAC_KEY = "phase8-synthetic-audit-key-only"
settings.AGENT_AUDIT_HMAC_KEY_VERSION = "phase8-v1"
settings.DASHSCOPE_API_KEY = ""
settings.PURGE_ENCRYPTION_KEY = "8" * 64

provider_controller = ProviderController()
control = Phase8Control(
    engine=test_engine,
    session_factory=TestSession,
    expected_db_path=PHASE8_DB_PATH,
    provider_controller=provider_controller,
)


async def _override_db():
    async with TestSession() as db:
        yield db


@asynccontextmanager
async def _device_lifespan(_app):
    await control.reset(Checkpoint.blank_supported)
    yield


app = create_phase8_test_app(
    get_db_override=_override_db,
    get_provider_override=provider_controller.get,
    control=control,
    lifespan=_device_lifespan,
)


__all__ = ["PHASE8_DB_PATH", "PHASE8_DB_URL", "app", "control"]
