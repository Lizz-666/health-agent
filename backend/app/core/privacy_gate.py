"""Photo privacy gate — the final, evidence-backed authorization boundary for
photo analysis and upload STS credential paths (spec §13.3/§13.4).

This is deliberately NOT the coarse ``PHOTO_ANALYSIS_ENABLED`` feature flag
(see ``app.core.photo_gate``). The feature flag is a system-level switch; the
privacy gate is a finer boundary applied *after* it that requires **verifiable
implementation evidence** for each of 8 enablement conditions.

Phase 1 guarantee: every condition is unsatisfied, so the gate HARD-REJECTS
photo analysis / upload STS paths. This is not a "8 config booleans true ->
allow" fake gate — flipping config flags never satisfies a condition, because
each condition is checked by an evidence function that looks for a real code
path / test, not a setting.
"""

from dataclasses import dataclass, field
from typing import Callable, List

from fastapi import Depends

from app.core.dependencies import get_current_user
from app.core.exceptions import AppException
from app.core.photo_gate import require_photo_analysis


@dataclass(frozen=True)
class ConditionEvidence:
    """Outcome of checking a single privacy-gate enablement condition."""

    condition_id: str
    description: str
    satisfied: bool
    evidence: str


# Each condition is evaluated by a function returning ``ConditionEvidence``.
# In Phase 1 every check returns "not implemented / no evidence". To enable
# photo analysis a future task must flip each check to return ``satisfied=True``
# with concrete evidence (code path + test coverage), reviewed by a human.


def _check_purpose_disclosure() -> ConditionEvidence:
    # §13.3.1: processing-purpose disclosure implemented & verified
    # (photo usage, AI analysis scope, no other用途).
    return ConditionEvidence(
        condition_id="purpose_disclosure",
        description="处理目的告知（照片用途、AI分析范围、不用于其他目的）",
        satisfied=False,
        evidence="未实现：尚无处理目的告知的代码路径或测试覆盖。",
    )


def _check_provider_boundary() -> ConditionEvidence:
    # §13.3.2: cloud model provider boundary documented & verified
    # (model name, provider, processing location).
    return ConditionEvidence(
        condition_id="provider_boundary",
        description="云端模型提供者边界告知（模型名称、提供方、处理位置）",
        satisfied=False,
        evidence="未实现：云端模型提供者边界尚未文档化或验证。",
    )


def _check_consent_flow() -> ConditionEvidence:
    # §13.3.3: pre-upload standalone consent flow implemented & verified.
    return ConditionEvidence(
        condition_id="consent_flow",
        description="上传前单独同意流程（显式同意上传照片用于体态分析）",
        satisfied=False,
        evidence="未实现：上传前同意采集流程尚未实现。",
    )


def _check_retention_configured() -> ConditionEvidence:
    # §13.3.4: retention period defined & verified (default 90 days, actual
    # deletion of original data on expiry). The config knob existing is not
    # sufficient — the expiry-triggered real deletion path must be verified.
    return ConditionEvidence(
        condition_id="retention_configured",
        description="保存期限定义与到期实际删除（默认90天）",
        satisfied=False,
        evidence="未实现：到期实际删除流程尚未验证（配置项存在不等同于条件满足）。",
    )


def _check_deletion_path() -> ConditionEvidence:
    # §13.3.5: deletion path implemented & verified (user can delete events,
    # actually deletes original health data + photo objects, keeps tombstone).
    return ConditionEvidence(
        condition_id="deletion_path",
        description="删除路径（实际删除原始健康数据+照片对象，保留tombstone）",
        satisfied=False,
        evidence="未实现：面向用户的删除入口与端到端验证尚未完成。",
    )


def _check_consent_withdrawal() -> ConditionEvidence:
    # §13.3.6: consent-withdrawal behavior implemented & verified (stop new
    # uploads, trigger purge of existing data).
    return ConditionEvidence(
        condition_id="consent_withdrawal",
        description="撤回同意行为（停止新上传并触发已有数据purge）",
        satisfied=False,
        evidence="未实现：撤回同意触发purge的流程尚未实现。",
    )


def _check_log_redaction() -> ConditionEvidence:
    # §13.3.7: log redaction rules implemented & verified (no photo URL,
    # no raw model response logged).
    return ConditionEvidence(
        condition_id="log_redaction",
        description="日志脱敏规则（不记录照片URL、原始模型响应）",
        satisfied=False,
        evidence="未实现：日志脱敏规则尚未形成可验证的统一实现与覆盖。",
    )


def _check_self_test_preserved() -> ConditionEvidence:
    # §13.3.8: self-test path preserved when not consented & verified.
    # The self-test endpoint is intentionally never gated by the photo gate.
    return ConditionEvidence(
        condition_id="self_test_preserved",
        description="未同意时保留图示自测路径",
        satisfied=False,
        evidence="未验证：尚未建立未同意状态下自测路径完整可用的回归覆盖。",
    )


_CONDITION_CHECKS: List[Callable[[], ConditionEvidence]] = [
    _check_purpose_disclosure,
    _check_provider_boundary,
    _check_consent_flow,
    _check_retention_configured,
    _check_deletion_path,
    _check_consent_withdrawal,
    _check_log_redaction,
    _check_self_test_preserved,
]


@dataclass(frozen=True)
class GateResult:
    satisfied: bool
    satisfied_conditions: List[ConditionEvidence] = field(default_factory=list)
    unsatisfied_conditions: List[ConditionEvidence] = field(default_factory=list)


def evaluate_photo_privacy_gate() -> GateResult:
    """Evaluate all 8 conditions and return the full picture."""
    evidences = [check() for check in _CONDITION_CHECKS]
    satisfied = [e for e in evidences if e.satisfied]
    unsatisfied = [e for e in evidences if not e.satisfied]
    return GateResult(
        satisfied=len(unsatisfied) == 0,
        satisfied_conditions=satisfied,
        unsatisfied_conditions=unsatisfied,
    )


def unsatisfied_conditions() -> List[ConditionEvidence]:
    """Return the list of currently unsatisfied conditions (for reporting)."""
    return evaluate_photo_privacy_gate().unsatisfied_conditions


async def require_photo_privacy(user_id: str = Depends(get_current_user)) -> None:
    """FastAPI dependency: the final photo authorization boundary.

    Ordering is preserved: ``get_current_user`` runs first (so an
    unauthenticated request gets 401 before any gate), then the coarse
    ``require_photo_analysis`` feature flag (503 ``photo_analysis_disabled``
    when the system switch is off), and finally this evidence-backed privacy
    gate. Even when ``PHOTO_ANALYSIS_ENABLED=true`` the request is rejected
    unless all 8 conditions carry evidence.
    """
    await require_photo_analysis(user_id)
    gate = evaluate_photo_privacy_gate()
    if not gate.satisfied:
        raise AppException(
            503,
            "照片分析隐私门启用条件未满足，照片分析暂不可用",
            "photo_analysis_disabled",
        )
