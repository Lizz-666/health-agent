"""Phase 5 Task 4 provider boundary tests (synthetic data only)."""
from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from app.agent.provider import (
    DashScopeProvider,
    ProviderFailure,
    ProviderRequest,
    ScriptedProvider,
    parse_provider_decision,
)


def _request() -> ProviderRequest:
    return ProviderRequest(
        prompt_version="agent-v1",
        system_prompt="Return one JSON decision.",
        user_message="请解释今天的训练",
        context={"entry_type": "general", "today_state": "session"},
        allowed_tools=[
            {
                "name": "get_today_training",
                "side_effect": "read",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            }
        ],
        read_results=[],
    )


@pytest.mark.parametrize(
    "raw,kind",
    [
        ({"type": "answer", "message_code": "agent_answer_ready", "references": []}, "answer"),
        ({"type": "clarify", "question_code": "agent_clarify_required", "missing_fields": ["fitness_goal"]}, "clarify"),
        ({"type": "read_tool_call", "tool_name": "get_today_training", "arguments": {}}, "read_tool_call"),
        ({"type": "action_proposal", "tool_name": "create_weight_record", "arguments": {"recorded_at": "2026-07-30T00:00:00Z", "weight_kg": 70.0}}, "action_proposal"),
        ({"type": "unsupported", "message_code": "agent_unsupported_scope"}, "unsupported"),
    ],
)
def test_provider_decision_union_accepts_only_closed_shapes(raw, kind):
    assert parse_provider_decision(raw).type == kind


@pytest.mark.parametrize(
    "raw",
    [
        {"type": "answer", "message_code": "agent_answer_ready", "text": "free text"},
        {"type": "read_tool_call", "tool_name": "x", "arguments": {}, "user_id": "other"},
        {"type": "unknown", "message_code": "agent_answer_ready"},
        ["not-an-object"],
    ],
)
def test_provider_decision_rejects_free_text_unknown_fields_and_unknown_kind(raw):
    with pytest.raises((ValidationError, TypeError)):
        parse_provider_decision(raw)


async def test_scripted_provider_is_deterministic_and_exhaustion_fails_closed():
    provider = ScriptedProvider([
        {"type": "answer", "message_code": "agent_answer_ready", "references": []}
    ])
    assert (await provider.decide(_request())).type == "answer"
    with pytest.raises(ProviderFailure) as exc:
        await provider.decide(_request())
    assert exc.value.code == "agent_provider_unavailable"


async def test_dashscope_adapter_uses_reviewed_json_object_contract():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "qwen-plus-2026-07-01",
                "choices": [{
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": json.dumps({
                            "type": "answer",
                            "message_code": "agent_answer_ready",
                            "references": [],
                        }),
                    },
                }],
            },
        )

    provider = DashScopeProvider(
        api_key="synthetic-key",
        model_id="qwen-plus",
        base_url="https://example.invalid/compatible-mode/v1",
        transport=httpx.MockTransport(handler),
    )
    decision = await provider.decide(_request())
    assert decision.type == "answer"
    assert provider.last_model_version == "qwen-plus-2026-07-01"
    assert captured["authorization"] == "Bearer synthetic-key"
    body = captured["body"]
    assert body["response_format"] == {"type": "json_object"}
    assert body["stream"] is False
    assert body["n"] == 1
    assert body["max_completion_tokens"] <= 1200


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(429, json={"error": "rate limited"}),
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}),
        httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "not-json"}}]}),
    ],
)
async def test_dashscope_provider_failures_never_become_decisions(response):
    async def handler(_request: httpx.Request) -> httpx.Response:
        return response

    provider = DashScopeProvider(
        api_key="synthetic-key",
        model_id="qwen-plus",
        base_url="https://example.invalid/compatible-mode/v1",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderFailure):
        await provider.decide(_request())


async def test_dashscope_oversized_response_fails_closed():
    payload = b"x" * 2049

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    provider = DashScopeProvider(
        api_key="synthetic-key",
        model_id="qwen-plus",
        base_url="https://example.invalid/compatible-mode/v1",
        max_response_bytes=2048,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderFailure) as exc:
        await provider.decide(_request())
    assert exc.value.code == "agent_output_invalid"


async def test_dashscope_duplicate_json_keys_fail_closed():
    content = (
        '{"type":"answer","type":"unsupported",'
        '"message_code":"agent_unsupported_scope"}'
    )

    async def handler(_request: httpx.Request) -> httpx.Response:
        envelope = {
            "model": "qwen-plus",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": content},
                }
            ],
        }
        return httpx.Response(200, json=envelope)

    provider = DashScopeProvider(
        api_key="synthetic-key",
        model_id="qwen-plus",
        base_url="https://example.invalid/compatible-mode/v1",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderFailure) as exc:
        await provider.decide(_request())
    assert exc.value.code == "agent_output_invalid"


async def test_dashscope_timeout_is_typed_and_redacted():
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("contains-sensitive-request-details")

    provider = DashScopeProvider(
        api_key="synthetic-key",
        model_id="qwen-plus",
        base_url="https://example.invalid/compatible-mode/v1",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderFailure) as exc:
        await provider.decide(_request())
    assert exc.value.code == "agent_provider_unavailable"
    assert "sensitive" not in str(exc.value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"connect_timeout": 0},
        {"connect_timeout": 10.1},
        {"read_timeout": float("nan")},
        {"read_timeout": 60.1},
        {"max_response_bytes": 1023},
        {"max_response_bytes": 1024 * 1024 + 1},
    ],
)
async def test_dashscope_runtime_bounds_fail_before_network(overrides):
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("invalid bounds must block before network")

    provider = DashScopeProvider(
        api_key="synthetic-key",
        model_id="qwen-plus",
        base_url="https://example.invalid/compatible-mode/v1",
        transport=httpx.MockTransport(handler),
        **overrides,
    )
    with pytest.raises(ProviderFailure) as exc:
        await provider.decide(_request())
    assert exc.value.code == "agent_provider_unavailable"
    assert calls == 0
