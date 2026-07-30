"""Phase 5 synthetic end-to-end acceptance through the isolated app factory.

No live provider, production credential, real health value, or raw transcript is
used. The flow exercises the same authenticated router and disposable database
dependencies as production while requiring explicit provider injection.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.agent.models import (
    AgentActionProposal,
    AgentCloudConsent,
    AgentRun,
    AgentToolEvent,
)
from app.agent.persistence import (
    OP_AGENT_ACTION_CONFIRM,
    OP_AGENT_CONSENT_GRANT,
    OP_AGENT_CONSENT_WITHDRAW,
)
from app.agent.provider import DashScopeProvider, ScriptedProvider
from app.auth.models import User
from app.core.config import settings
from app.core.security import create_access_token
from app.health.models import WeightRecord
from app.posture.models import IdempotencyRecord
from tests.agent_app_factory import create_agent_test_app
from tests.conftest import TestSession


pytestmark = pytest.mark.asyncio

PROVIDER_ID = "dashscope"
DISCLOSURE_VERSION = "agent-cloud-v1"


@pytest.fixture(autouse=True)
def _configured_synthetic_runtime(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_RUNTIME_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_PROVIDER_ID", PROVIDER_ID)
    monkeypatch.setattr(settings, "AGENT_MODEL_ID", "qwen-synthetic-e2e")
    monkeypatch.setattr(
        settings, "AGENT_DISCLOSURE_VERSION", DISCLOSURE_VERSION
    )
    monkeypatch.setattr(settings, "DASHSCOPE_API_KEY", "synthetic-test-key")
    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY", "e" * 32)
    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY_VERSION", "e2e-v1")


async def _seed_user() -> tuple[str, dict[str, str]]:
    user_id = uuid.uuid4()
    async with TestSession() as db:
        db.add(User(id=user_id, phone="136" + uuid.uuid4().hex[:8]))
        await db.commit()
    token = create_access_token(str(user_id))
    return str(user_id), {"Authorization": f"Bearer {token}"}


async def _override_db():
    async with TestSession() as db:
        yield db


async def _counts(user_id: str) -> dict[str, int]:
    uid = uuid.UUID(user_id)
    async with TestSession() as db:
        values = {}
        for name, model in (
            ("consents", AgentCloudConsent),
            ("runs", AgentRun),
            ("tool_events", AgentToolEvent),
            ("proposals", AgentActionProposal),
            ("weight_records", WeightRecord),
        ):
            value = await db.scalar(
                select(func.count()).select_from(model).where(model.user_id == uid)
            )
            values[name] = value or 0
        agent_idempotency = await db.scalar(
            select(func.count())
            .select_from(IdempotencyRecord)
            .where(
                IdempotencyRecord.user_id == uid,
                IdempotencyRecord.operation.in_(
                    (
                        OP_AGENT_ACTION_CONFIRM,
                        OP_AGENT_CONSENT_GRANT,
                        OP_AGENT_CONSENT_WITHDRAW,
                    )
                ),
            )
        )
        values["agent_idempotency"] = agent_idempotency or 0
        return values


async def test_consent_contextual_read_proposal_confirm_delete_flow(
    monkeypatch,
):
    user_id, headers = await _seed_user()
    recorded_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    fake = ScriptedProvider(
        [
            {
                "type": "read_tool_call",
                "tool_name": "get_health_profile_summary",
                "arguments": {},
            },
            {
                "type": "action_proposal",
                "tool_name": "create_weight_record",
                "arguments": {
                    "recorded_at": recorded_at,
                    "weight_kg": 70.5,
                },
            },
        ]
    )
    live_calls = 0

    async def forbidden_live_call(self, request):
        nonlocal live_calls
        live_calls += 1
        raise AssertionError("isolated Phase 5 E2E must not call a live provider")

    monkeypatch.setattr(DashScopeProvider, "decide", forbidden_live_call)
    test_app = create_agent_test_app(
        provider=fake,
        get_db_override=_override_db,
    )
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://synthetic-agent-e2e",
    ) as client:
        health = await client.get("/health")
        assert health.json() == {
            "status": "ok",
            "mode": "synthetic-agent-test",
        }

        before = await client.get(
            "/api/v1/agent/capabilities", headers=headers
        )
        assert before.status_code == 200
        assert before.json()["available"] is False
        assert before.json()["result_code"] == "agent_consent_required"

        blocked = await client.post(
            "/api/v1/agent/turns",
            headers=headers,
            json={
                "client_turn_id": "phase5-before-consent",
                "entry_type": "health_profile",
                "message": "Read the synthetic current profile summary.",
                "iana_timezone": "Asia/Shanghai",
            },
        )
        assert blocked.status_code == 200
        assert blocked.json()["status"] == "failed"
        assert blocked.json()["result_code"] == "agent_consent_required"
        assert fake.calls == []
        assert await _counts(user_id) == {
            "consents": 0,
            "runs": 0,
            "tool_events": 0,
            "proposals": 0,
            "weight_records": 0,
            "agent_idempotency": 0,
        }

        granted = await client.post(
            "/api/v1/agent/consents:grant",
            headers=headers,
            json={
                "accepted_provider_id": PROVIDER_ID,
                "accepted_disclosure_version": DISCLOSURE_VERSION,
                "idempotency_key": "phase5-e2e-consent",
            },
        )
        assert granted.status_code == 200
        assert granted.json()["status"] == "granted"

        available = await client.get(
            "/api/v1/agent/capabilities", headers=headers
        )
        assert available.json()["available"] is True
        assert available.json()["result_code"] == "agent_available"

        turn = await client.post(
            "/api/v1/agent/turns",
            headers=headers,
            json={
                "client_turn_id": "phase5-context-read-and-proposal",
                "entry_type": "health_profile",
                "message": "Use the synthetic profile and prepare a weight record.",
                "iana_timezone": "Asia/Shanghai",
            },
        )
        assert turn.status_code == 200, turn.text
        body = turn.json()
        assert body["status"] == "proposal_pending"
        assert body["result_code"] == "agent_action_confirmation_required"
        assert body["message"].startswith("操作尚未执行")
        assert [item["tool_name"] for item in body["display_data"]] == [
            "get_health_profile_summary"
        ]
        assert body["proposal"]["action"] == "create_weight_record"
        assert body["proposal"]["diff"]["weight_kg"] == 70.5
        proposal_id = body["proposal"]["proposal_id"]
        assert len(fake.calls) == 2
        before_confirm = await _counts(user_id)
        assert before_confirm["consents"] == 1
        assert before_confirm["weight_records"] == 0
        assert before_confirm["agent_idempotency"] == 1

        confirmed = await client.post(
            f"/api/v1/agent/actions/{proposal_id}:confirm",
            headers=headers,
            json={"idempotency_key": "phase5-e2e-confirm"},
        )
        replayed = await client.post(
            f"/api/v1/agent/actions/{proposal_id}:confirm",
            headers=headers,
            json={"idempotency_key": "phase5-e2e-confirm"},
        )
        assert confirmed.status_code == replayed.status_code == 200
        assert confirmed.json()["status"] == "executed"
        assert replayed.json()["status"] == "replayed"
        assert confirmed.json()["result_code"] == "agent_action_executed"
        assert replayed.json()["result_code"] == "agent_action_executed"
        assert (await _counts(user_id))["weight_records"] == 1

        deleted = await client.delete("/api/v1/agent/data", headers=headers)
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True
        assert deleted.json()["consents_deleted"] == 1
        assert deleted.json()["idempotency_deleted"] == 2
        assert await _counts(user_id) == {
            "consents": 0,
            "runs": 0,
            "tool_events": 0,
            "proposals": 0,
            "weight_records": 1,
            "agent_idempotency": 0,
        }

    assert live_calls == 0


async def test_global_disable_blocks_factory_provider_and_persistence(monkeypatch):
    user_id, headers = await _seed_user()
    fake = ScriptedProvider(
        [{"type": "answer", "message_code": "agent_answer_ready"}]
    )
    monkeypatch.setattr(settings, "AGENT_RUNTIME_ENABLED", False)
    test_app = create_agent_test_app(
        provider=fake,
        get_db_override=_override_db,
    )
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://synthetic-agent-disabled",
    ) as client:
        response = await client.post(
            "/api/v1/agent/turns",
            headers=headers,
            json={
                "client_turn_id": "phase5-disabled",
                "entry_type": "general",
                "message": "Synthetic benign request.",
                "iana_timezone": "Asia/Shanghai",
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["result_code"] == "agent_disabled"
    assert fake.calls == []
    assert await _counts(user_id) == {
        "consents": 0,
        "runs": 0,
        "tool_events": 0,
        "proposals": 0,
        "weight_records": 0,
        "agent_idempotency": 0,
    }


async def test_device_server_refuses_external_test_database():
    backend_dir = Path(__file__).resolve().parents[1]
    device_db = backend_dir / "phase5_device_smoke.db"
    assert not device_db.exists()
    environment = os.environ.copy()
    environment["TEST_DB_URL"] = (
        "postgresql+asyncpg://forbidden:forbidden@127.0.0.1/forbidden"
    )

    result = subprocess.run(
        [sys.executable, "-c", "import tests.agent_device_server"],
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode != 0
    assert "refuses to use an externally configured TEST_DB_URL" in (
        result.stdout + result.stderr
    )
    assert not device_db.exists()


async def test_production_source_has_no_device_server_selector():
    app_dir = Path(__file__).resolve().parents[1] / "app"
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in app_dir.rglob("*.py")
    )
    assert "agent_device_server" not in source
    assert "agent_app_factory" not in source
