"""Provider-neutral Agent decision boundary and one reviewed live adapter.

The provider returns codes and typed Tool intent only. It cannot return display
text, actor identity, authorization, confirmation, or arbitrary side effects.
Production uses the Alibaba Cloud Model Studio OpenAI-compatible Chat API; the
core does not depend on an SDK and tests use ``ScriptedProvider`` only through
dependency injection.

Official contract verified 2026-07-30:
https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-chat-completions
The API supports ``POST .../chat/completions`` and
``response_format={"type":"json_object"}``. JSON Schema enforcement is not
assumed; every response is independently validated below.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Annotated, Dict, List, Literal, Optional, Protocol, Union

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError


AGENT_PROVIDER_UNAVAILABLE = "agent_provider_unavailable"
AGENT_OUTPUT_INVALID = "agent_output_invalid"

_MAX_DECISION_JSON_BYTES = 16 * 1024
_MAX_CONNECT_TIMEOUT_SECONDS = 10.0
_MAX_READ_TIMEOUT_SECONDS = 60.0
_MAX_HTTP_RESPONSE_BYTES = 1024 * 1024


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AnswerDecision(_StrictModel):
    type: Literal["answer"]
    message_code: str = Field(..., min_length=1, max_length=60)
    references: List[str] = Field(default_factory=list, max_length=8)


class ClarifyDecision(_StrictModel):
    type: Literal["clarify"]
    question_code: str = Field(..., min_length=1, max_length=60)
    missing_fields: List[str] = Field(..., min_length=1, max_length=8)


class ReadToolCallDecision(_StrictModel):
    type: Literal["read_tool_call"]
    tool_name: str = Field(..., min_length=1, max_length=60)
    arguments: Dict[str, Any]


class ActionProposalDecision(_StrictModel):
    type: Literal["action_proposal"]
    tool_name: str = Field(..., min_length=1, max_length=60)
    arguments: Dict[str, Any]


class UnsupportedDecision(_StrictModel):
    type: Literal["unsupported"]
    message_code: str = Field(..., min_length=1, max_length=60)


ProviderDecision = Annotated[
    Union[
        AnswerDecision,
        ClarifyDecision,
        ReadToolCallDecision,
        ActionProposalDecision,
        UnsupportedDecision,
    ],
    Field(discriminator="type"),
]
_DECISION_ADAPTER = TypeAdapter(ProviderDecision)


class ProviderToolDefinition(_StrictModel):
    name: str = Field(..., min_length=1, max_length=60)
    side_effect: Literal["read", "proposal"]
    parameters: Dict[str, Any]


class ProviderReadResult(_StrictModel):
    tool_name: str = Field(..., min_length=1, max_length=60)
    provider_view: Dict[str, Any]


class ProviderRequest(_StrictModel):
    """One ephemeral provider request; never persisted or logged."""

    prompt_version: str = Field(..., min_length=1, max_length=40)
    system_prompt: str = Field(..., min_length=1, max_length=20_000)
    user_message: str = Field(..., min_length=1, max_length=2_000)
    context: Dict[str, Any]
    allowed_tools: List[ProviderToolDefinition] = Field(max_length=32)
    read_results: List[ProviderReadResult] = Field(max_length=4)


class ProviderFailure(Exception):
    """Redacted provider failure carrying only a stable result code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class AgentProvider(Protocol):
    provider_id: str
    model_id: str
    last_model_version: Optional[str]

    async def decide(self, request: ProviderRequest) -> ProviderDecision:
        ...


def parse_provider_decision(raw: Any) -> ProviderDecision:
    """Validate one strict discriminated decision without coercing a list."""
    if not isinstance(raw, dict):
        raise TypeError("provider decision must be an object")
    return _DECISION_ADAPTER.validate_python(raw)


class ScriptedProvider:
    """Deterministic test fake; never selected through runtime configuration."""

    provider_id = "scripted-test-provider"
    model_id = "scripted-test-model"
    last_model_version: Optional[str] = "scripted-test-model"

    def __init__(self, script: List[Any]) -> None:
        self._script = list(script)
        self.calls: List[ProviderRequest] = []

    async def decide(self, request: ProviderRequest) -> ProviderDecision:
        self.calls.append(request)
        if not self._script:
            raise ProviderFailure(AGENT_PROVIDER_UNAVAILABLE)
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        try:
            return parse_provider_decision(item)
        except (TypeError, ValidationError) as exc:
            raise ProviderFailure(AGENT_OUTPUT_INVALID) from exc


@dataclass(frozen=True)
class _Timeouts:
    connect: float = 5.0
    read: float = 20.0


class DashScopeProvider:
    """Bounded OpenAI-compatible DashScope adapter.

    It uses one non-streaming candidate and JSON-object mode. The adapter does
    not retry automatically: retrying a decision could create divergent Tool
    intent. HTTP bodies and exception details are never included in errors.
    """

    provider_id = "dashscope"

    def __init__(
        self,
        *,
        api_key: str,
        model_id: str,
        base_url: str,
        connect_timeout: float = 5.0,
        read_timeout: float = 20.0,
        max_response_bytes: int = 64 * 1024,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.api_key = api_key
        self.model_id = model_id
        self.base_url = base_url.rstrip("/")
        self.timeouts = _Timeouts(connect_timeout, read_timeout)
        self.max_response_bytes = max_response_bytes
        self.transport = transport
        self.last_model_version: Optional[str] = None

    async def decide(self, request: ProviderRequest) -> ProviderDecision:
        if (
            not self.api_key
            or not self.model_id
            or not self.base_url.startswith("https://")
            or not math.isfinite(self.timeouts.connect)
            or not math.isfinite(self.timeouts.read)
            or not 0 < self.timeouts.connect <= _MAX_CONNECT_TIMEOUT_SECONDS
            or not 0 < self.timeouts.read <= _MAX_READ_TIMEOUT_SECONDS
            or not 1024 <= self.max_response_bytes <= _MAX_HTTP_RESPONSE_BYTES
        ):
            raise ProviderFailure(AGENT_PROVIDER_UNAVAILABLE)

        provider_input = {
            "message": request.user_message,
            "context": request.context,
            "allowed_tools": [
                item.model_dump(mode="json") for item in request.allowed_tools
            ],
            "read_results": [
                item.model_dump(mode="json") for item in request.read_results
            ],
        }
        body = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        provider_input,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        allow_nan=False,
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
            "max_completion_tokens": 1200,
            "temperature": 0,
            "n": 1,
            "stream": False,
        }
        timeout = httpx.Timeout(
            connect=self.timeouts.connect,
            read=self.timeouts.read,
            write=self.timeouts.connect,
            pool=self.timeouts.connect,
        )
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                async with client.stream(
                    "POST",
                    self.base_url + "/chat/completions",
                    headers={
                        "Authorization": "Bearer " + self.api_key,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=body,
                ) as response:
                    if response.status_code < 200 or response.status_code >= 300:
                        raise ProviderFailure(AGENT_PROVIDER_UNAVAILABLE)
                    chunks: List[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > self.max_response_bytes:
                            raise ProviderFailure(AGENT_OUTPUT_INVALID)
                        chunks.append(chunk)
            payload = _strict_json_loads(b"".join(chunks))
            if not isinstance(payload, dict):
                raise ProviderFailure(AGENT_OUTPUT_INVALID)
            choices = payload.get("choices")
            if not isinstance(choices, list) or len(choices) != 1:
                raise ProviderFailure(AGENT_OUTPUT_INVALID)
            choice = choices[0]
            if not isinstance(choice, dict) or choice.get("finish_reason") != "stop":
                raise ProviderFailure(AGENT_OUTPUT_INVALID)
            message = choice.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str):
                raise ProviderFailure(AGENT_OUTPUT_INVALID)
            encoded = content.encode("utf-8")
            if len(encoded) > _MAX_DECISION_JSON_BYTES:
                raise ProviderFailure(AGENT_OUTPUT_INVALID)
            decision_raw = _strict_json_loads(encoded)
            self.last_model_version = _bounded_model_version(payload.get("model"))
            return parse_provider_decision(decision_raw)
        except ProviderFailure:
            raise
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise ProviderFailure(AGENT_PROVIDER_UNAVAILABLE) from exc
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            RecursionError,
            TypeError,
            ValueError,
            ValidationError,
        ) as exc:
            raise ProviderFailure(AGENT_OUTPUT_INVALID) from exc


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-finite JSON value")


def _strict_json_loads(raw: bytes) -> Any:
    return json.loads(
        raw.decode("utf-8"),
        parse_constant=_reject_json_constant,
        object_pairs_hook=_reject_duplicate_keys,
    )


def _reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _bounded_model_version(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value or len(value) > 60:
        return None
    return value


__all__ = [
    "AGENT_PROVIDER_UNAVAILABLE",
    "AGENT_OUTPUT_INVALID",
    "AnswerDecision",
    "ClarifyDecision",
    "ReadToolCallDecision",
    "ActionProposalDecision",
    "UnsupportedDecision",
    "ProviderDecision",
    "ProviderToolDefinition",
    "ProviderReadResult",
    "ProviderRequest",
    "ProviderFailure",
    "AgentProvider",
    "parse_provider_decision",
    "ScriptedProvider",
    "DashScopeProvider",
]
