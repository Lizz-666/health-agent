"""Stable Agent message/result codes and the server-rendered template boundary.

Task 1 scope only. This module fixes the small set of deterministic result
codes the read boundary can produce and the reviewed server-side text rendered
for them. It is intentionally NOT a provider free-text channel and NOT a chat
transcript store: the provider never supplies user-visible prose, and unknown
codes fail closed rather than rendering attacker-influenced text.

Later batches extend these codes (write proposals, provider failures, consent),
but Task 1 must not invent proposal/persistence or provider states here.
"""
from __future__ import annotations

from typing import Dict


class ResultCode:
    """Deterministic, stable result codes used by the Task 1 read boundary.

    These are string constants (not an enum) so downstream batches can extend
    the set without renumbering. Every code that can reach a user has a
    reviewed template in ``TEMPLATES``.
    """

    # Request-level deterministic rejections (before any side effect).
    INVALID_TIMEZONE = "invalid_timezone"
    ENTITY_NOT_FOUND = "agent_entity_not_found"  # non-enumerating: missing == foreign
    ENTITY_NOT_ALLOWED = "agent_entity_not_allowed"  # entity supplied where forbidden
    ENTITY_REQUIRED = "agent_entity_required"  # entity omitted where required
    TOOL_NOT_ALLOWED = "agent_tool_not_allowed"

    # Deterministic pre-provider safety text routing.
    SAFETY_SIGNAL_ROUTE_REQUIRED = "agent_safety_signal_route_required"
    NO_TEXT_SIGNAL_DETECTED = "no_text_signal_detected"

    # Fail-closed audit/fingerprint capability.
    FINGERPRINT_KEY_MISSING = "agent_fingerprint_key_missing"
    FINGERPRINT_INVALID_VALUE = "agent_fingerprint_invalid_value"

    # Successful read boundary.
    READ_OK = "agent_read_ok"


# Reviewed, versioned server-side templates. The provider cannot add, remove, or
# alter these strings; they are the ONLY user-visible text the read boundary can
# emit. ``NO_TEXT_SIGNAL_DETECTED`` is deliberately NOT a "normal"/"safe"
# clearance message - it only states that the deterministic text router found no
# configured signal, and downstream structured gates still run.
TEMPLATES: Dict[str, str] = {
    ResultCode.INVALID_TIMEZONE: "请提供有效的时区后再继续。",
    ResultCode.ENTITY_NOT_FOUND: "未找到可访问的对应内容。",
    ResultCode.ENTITY_NOT_ALLOWED: "该入口不接受实体标识。",
    ResultCode.ENTITY_REQUIRED: "该入口需要提供实体标识。",
    ResultCode.TOOL_NOT_ALLOWED: "当前入口不支持该操作。",
    ResultCode.SAFETY_SIGNAL_ROUTE_REQUIRED: (
        "你的描述可能涉及疼痛、伤病或其他安全信号，"
        "请通过结构化健康记录与安全流程处理。"
    ),
    ResultCode.NO_TEXT_SIGNAL_DETECTED: "未在文本中检测到已配置的安全信号。",
    ResultCode.FINGERPRINT_KEY_MISSING: "服务端审计密钥未配置，相关能力已停用。",
    ResultCode.FINGERPRINT_INVALID_VALUE: "审计数据无效，相关能力已停用。",
    ResultCode.READ_OK: "已读取当前拥有的信息。",
}


class AgentError(Exception):
    """Deterministic Agent boundary error carrying a stable ``code``.

    The message is rendered from the reviewed template registry so no
    attacker-influenced or model-authored prose can leak through an exception.
    """

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail or code)


def render(code: str) -> str:
    """Return the reviewed user-visible text for ``code``.

    Fail closed: an unknown/unreviewed code raises rather than echoing a raw or
    model-supplied string (spec Acceptance #6).
    """
    try:
        return TEMPLATES[code]
    except KeyError as exc:  # unknown message code -> fail closed
        raise AgentError(ResultCode.TOOL_NOT_ALLOWED) from exc


__all__ = ["ResultCode", "TEMPLATES", "AgentError", "render"]
