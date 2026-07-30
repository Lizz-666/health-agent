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
    INVALID_REQUEST = "agent_request_invalid"
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

    # Phase 5 runtime/privacy/provider states.
    DISABLED = "agent_disabled"
    CONSENT_REQUIRED = "agent_consent_required"
    PRIVACY_GATE_BLOCKED = "agent_privacy_gate_blocked"
    DISCLOSURE_STALE = "agent_disclosure_stale"
    PROVIDER_UNAVAILABLE = "agent_provider_unavailable"
    OUTPUT_INVALID = "agent_output_invalid"
    STEP_LIMIT = "agent_step_limit"
    TOOL_FAILED = "agent_tool_failed"
    CONTEXT_STALE = "agent_context_stale"
    AVAILABLE = "agent_available"

    # Reviewed provider-selectable message/question codes.
    ANSWER_READY = "agent_answer_ready"
    CLARIFY_REQUIRED = "agent_clarify_required"
    UNSUPPORTED_SCOPE = "agent_unsupported_scope"
    UNSUPPORTED_MEDICAL = "agent_unsupported_medical"
    UNSUPPORTED_NUTRITION = "agent_unsupported_nutrition"

    # Proposal/confirmation lifecycle.
    ACTION_CONFIRMATION_REQUIRED = "agent_action_confirmation_required"
    ACTION_EXPIRED = "agent_action_expired"
    ACTION_INVALIDATED = "agent_action_invalidated"
    ACTION_CANCELLED = "agent_action_cancelled"
    ACTION_EXECUTED = "agent_action_executed"


# Reviewed, versioned server-side templates. The provider cannot add, remove, or
# alter these strings; they are the ONLY user-visible text the read boundary can
# emit. ``NO_TEXT_SIGNAL_DETECTED`` is deliberately NOT a "normal"/"safe"
# clearance message - it only states that the deterministic text router found no
# configured signal, and downstream structured gates still run.
TEMPLATES: Dict[str, str] = {
    ResultCode.INVALID_TIMEZONE: "请提供有效的时区后再继续。",
    ResultCode.INVALID_REQUEST: "请求格式无效，未调用 Agent 或执行任何操作。",
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
    ResultCode.DISABLED: "Agent 当前未启用，其他功能仍可正常使用。",
    ResultCode.CONSENT_REQUIRED: "使用云端 Agent 前需要先阅读告知并明确同意。",
    ResultCode.PRIVACY_GATE_BLOCKED: "Agent 的隐私与运行条件尚未满足，当前不会调用云端模型。",
    ResultCode.DISCLOSURE_STALE: "服务信息已更新，请重新阅读并确认当前告知。",
    ResultCode.PROVIDER_UNAVAILABLE: "Agent 服务暂时不可用，未执行任何操作。",
    ResultCode.OUTPUT_INVALID: "Agent 返回了无效结果，未执行任何操作。",
    ResultCode.STEP_LIMIT: "本次 Agent 处理已达到安全步骤上限，未执行任何操作。",
    ResultCode.TOOL_FAILED: "读取当前信息时失败，未执行任何操作。",
    ResultCode.CONTEXT_STALE: "相关信息已变化，请重新发起操作。",
    ResultCode.AVAILABLE: "Agent 已满足当前运行与隐私条件。",
    ResultCode.ANSWER_READY: "已根据当前可访问的信息整理结果。",
    ResultCode.CLARIFY_REQUIRED: "继续前还需要补充结构化信息。",
    ResultCode.UNSUPPORTED_SCOPE: "该请求超出当前健康教练的支持范围。",
    ResultCode.UNSUPPORTED_MEDICAL: "当前产品不提供医学诊断或治疗建议，请使用适当的专业服务。",
    ResultCode.UNSUPPORTED_NUTRITION: "当前阶段尚不提供该饮食建议，请勿将此功能视为营养治疗。",
    ResultCode.ACTION_CONFIRMATION_REQUIRED: "操作尚未执行，请核对变更内容并明确确认或取消。",
    ResultCode.ACTION_EXPIRED: "该操作提案已过期，请重新发起。",
    ResultCode.ACTION_INVALIDATED: "相关信息已变化，该操作未执行。",
    ResultCode.ACTION_CANCELLED: "该操作已取消，未写入数据。",
    ResultCode.ACTION_EXECUTED: "操作已按确认内容执行。",
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


def is_known_code(code: str) -> bool:
    """Return whether a code has a reviewed user-visible template."""
    return code in TEMPLATES


__all__ = ["ResultCode", "TEMPLATES", "AgentError", "render", "is_known_code"]
