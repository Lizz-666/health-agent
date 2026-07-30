"""Synthetic prompt-injection, authority, bounds, and redaction evaluation."""
from __future__ import annotations

import inspect
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.requests import Request
from sqlalchemy import func, select

from app.agent.models import AgentActionProposal, AgentRun, AgentToolEvent
from app.agent.provider import DashScopeProvider, ScriptedProvider
from app.agent.router import get_agent_provider
from app.auth.models import User
from app.core.config import settings
from app.core.security import create_access_token
from app.main import app
from tests.conftest import TestSession


pytestmark = pytest.mark.asyncio

_FIXTURE_PATH = (
    Path(__file__).with_name("fixtures") / "agent" / "agent_eval_v1.json"
)
_EVAL = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
_CASES = _EVAL["cases"]


@pytest.fixture(autouse=True)
def _runtime(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_RUNTIME_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_PROVIDER_ID", "dashscope")
    monkeypatch.setattr(settings, "AGENT_MODEL_ID", "qwen-test-model")
    monkeypatch.setattr(settings, "AGENT_DISCLOSURE_VERSION", "agent-cloud-v1")
    monkeypatch.setattr(settings, "DASHSCOPE_API_KEY", "synthetic-test-key")
    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY", "b" * 32)
    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY_VERSION", "eval-v1")


async def _seed_and_grant(client):
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        db.add(User(id=uuid.UUID(user_id), phone="138" + uuid.uuid4().hex[:8]))
        await db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}
    response = await client.post(
        "/api/v1/agent/consents:grant",
        headers=headers,
        json={
            "accepted_provider_id": "dashscope",
            "accepted_disclosure_version": "agent-cloud-v1",
            "idempotency_key": "eval-grant",
        },
    )
    assert response.status_code == 200
    return user_id, headers


async def _counts(user_id):
    uid = uuid.UUID(user_id)
    async with TestSession() as db:
        counts = []
        for model in (AgentRun, AgentToolEvent, AgentActionProposal):
            value = await db.scalar(
                select(func.count()).select_from(model).where(model.user_id == uid)
            )
            counts.append(value or 0)
        return tuple(counts)


@pytest.mark.parametrize("case", _CASES, ids=[case["id"] for case in _CASES])
async def test_versioned_synthetic_adversarial_matrix(client, case):
    assert _EVAL["schema_version"] == "agent-eval-v1"
    assert _EVAL["synthetic_only"] is True
    user_id, headers = await _seed_and_grant(client)
    fake = ScriptedProvider(case["script"])
    app.dependency_overrides[get_agent_provider] = lambda: fake
    try:
        response = await client.post(
            "/api/v1/agent/turns",
            headers=headers,
            json={
                "client_turn_id": "eval-" + case["id"],
                "entry_type": "general",
                "message": case["message"],
                "iana_timezone": "Asia/Shanghai",
            },
        )
    finally:
        app.dependency_overrides.pop(get_agent_provider, None)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == case["expected_status"]
    assert body["result_code"] == case["expected_code"]
    assert len(fake.calls) == case["expected_provider_calls"]
    runs, events, proposals = await _counts(user_id)
    assert runs == case["expected_runs"]
    assert events == 0
    assert proposals == 0


async def test_live_provider_gate_blocks_network_before_consent(
    client, monkeypatch
):
    user_id = str(uuid.uuid4())
    async with TestSession() as db:
        db.add(User(id=uuid.UUID(user_id), phone="137" + uuid.uuid4().hex[:8]))
        await db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}
    calls = 0

    async def forbidden_decide(self, request):
        nonlocal calls
        calls += 1
        raise AssertionError("live provider must remain behind consent")

    monkeypatch.setattr(DashScopeProvider, "decide", forbidden_decide)
    response = await client.post(
        "/api/v1/agent/turns",
        headers=headers,
        json={
            "client_turn_id": "no-consent-no-network",
            "entry_type": "general",
            "message": "benign synthetic request",
            "iana_timezone": "Asia/Shanghai",
        },
    )

    assert response.json()["result_code"] == "agent_consent_required"
    assert calls == 0
    assert await _counts(user_id) == (0, 0, 0)


async def test_provider_failure_logs_do_not_include_ephemeral_message(
    client, caplog
):
    user_id, headers = await _seed_and_grant(client)
    sentinel = "SYNTHETIC-PRIVATE-MESSAGE-DO-NOT-LOG"
    fake = ScriptedProvider([RuntimeError("synthetic provider failure")])
    app.dependency_overrides[get_agent_provider] = lambda: fake
    try:
        response = await client.post(
            "/api/v1/agent/turns",
            headers=headers,
            json={
                "client_turn_id": "redaction-case",
                "entry_type": "general",
                "message": sentinel,
                "iana_timezone": "Asia/Shanghai",
            },
        )
    finally:
        app.dependency_overrides.pop(get_agent_provider, None)

    assert response.json()["result_code"] == "agent_provider_unavailable"
    assert sentinel not in caplog.text
    assert "synthetic provider failure" not in caplog.text
    assert await _counts(user_id) == (0, 0, 0)


async def test_production_router_has_no_scripted_provider_selection_path():
    from app.agent import router

    source = inspect.getsource(router)
    assert "ScriptedProvider" not in source
    assert "scripted-test-provider" not in source


async def test_unhandled_error_log_uses_route_template_not_proposal_identifier(
    caplog,
):
    import app.main as main_module

    proposal_id = str(uuid.uuid4())
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": f"/api/v1/agent/actions/{proposal_id}:confirm",
            "raw_path": b"/api/v1/agent/actions/redacted:confirm",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1),
            "server": ("test", 80),
            "route": SimpleNamespace(
                path="/api/v1/agent/actions/{proposal_id}:confirm"
            ),
        }
    )

    await main_module.unhandled_exception_handler(
        request, RuntimeError("synthetic failure")
    )

    assert proposal_id not in caplog.text
    assert "/api/v1/agent/actions/{proposal_id}:confirm" in caplog.text
    assert "synthetic failure" not in caplog.text
