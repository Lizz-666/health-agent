"""Loopback-only synthetic Phase 9 controlled-trial server."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path


PHASE9_DB_PATH = Path(__file__).resolve().parents[1] / "phase9_acceptance.db"
PHASE9_DB_URL = f"sqlite+aiosqlite:///{PHASE9_DB_PATH.as_posix()}"
configured_test_db = os.environ.get("TEST_DB_URL")
if configured_test_db not in (None, PHASE9_DB_URL):
    raise RuntimeError("phase9_device_server refuses externally configured TEST_DB_URL")
os.environ["TEST_DB_URL"] = PHASE9_DB_URL

from app.core.config import settings  # noqa: E402

settings.DEPLOYMENT_PROFILE = "controlled_trial_candidate"
settings.AUTH_MODE = "controlled_trial"
settings.AUTH_CREDENTIAL_PROVIDER = "offline_password"
settings.SECRET_KEY = "phase9-synthetic-jwt-key-never-live"
settings.AUTH_AUDIT_HMAC_KEY = "phase9-synthetic-auth-audit-key"
settings.PRIVACY_AUDIT_HMAC_KEY = "phase9-synthetic-privacy-audit-key"
settings.PRIVACY_NOTICE_VERSION = "controlled-trial-sensitive-health-v1"
settings.JWT_ISSUER = "phase9-synthetic-issuer"
settings.JWT_AUDIENCE = "phase9-synthetic-audience"
settings.DEV_MODE = False
settings.DEV_ADMIN_PHONE = ""
settings.DEV_ADMIN_PASSWORD = ""
settings.PHOTO_ANALYSIS_ENABLED = False
settings.AGENT_RUNTIME_ENABLED = False
settings.NUTRITION_RUNTIME_ENABLED = False
settings.MIN_ANDROID_CLIENT_VERSION_CODE = 1
settings.MAX_ANDROID_CLIENT_VERSION_CODE = 1

from app.privacy.router import router as privacy_router  # noqa: E402
from tests.conftest import TestSession, test_engine  # noqa: E402
from tests.phase8_app_factory import create_phase8_test_app  # noqa: E402
from tests.phase8_fixtures import ProviderController  # noqa: E402
from tests.phase8_loopback import install_loopback_guard  # noqa: E402
from tests.phase9_fixtures import Phase9Control  # noqa: E402


provider_controller = ProviderController()
control = Phase9Control(
    engine=test_engine,
    session_factory=TestSession,
    expected_db_path=PHASE9_DB_PATH,
)


async def _override_db():
    async with TestSession() as db:
        yield db


@asynccontextmanager
async def _device_lifespan(_app):
    await control.reset()
    yield


app = create_phase8_test_app(
    get_db_override=_override_db,
    get_provider_override=provider_controller.get,
    control=control,
    lifespan=_device_lifespan,
    extra_routers=(privacy_router,),
    health_mode="synthetic-phase9-test",
    enforce_client_compatibility=True,
)
install_loopback_guard(app)


__all__ = ["PHASE9_DB_PATH", "PHASE9_DB_URL", "app", "control"]
