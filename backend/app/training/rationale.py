"""Stable change-reason / rationale codes for Phase 4 plans (Task 3).

Codes are stable strings stored on ``training_plan_versions.change_reason`` and
used for UI text. Display text is bounded and wellness-scoped, never clinical.
"""
from __future__ import annotations

INITIAL_GENERATION = "initial_generation"
INITIAL_CONFIRMATION = "initial_confirmation"
SUPERSEDED_BY_NEW_DRAFT = "superseded_by_new_draft"
CANCELLED_BY_USER = "cancelled_by_user"
SUBSTITUTION_APPLIED = "substitution_applied"
FEEDBACK_RECORDED = "feedback_recorded"

ALL_CODES = frozenset(
    {
        INITIAL_GENERATION,
        INITIAL_CONFIRMATION,
        SUPERSEDED_BY_NEW_DRAFT,
        CANCELLED_BY_USER,
        SUBSTITUTION_APPLIED,
        FEEDBACK_RECORDED,
    }
)

_ZH = {
    INITIAL_GENERATION: "已生成新的四周计划草案",
    INITIAL_CONFIRMATION: "已确认并生效",
    SUPERSEDED_BY_NEW_DRAFT: "已被新计划替换",
    CANCELLED_BY_USER: "已取消",
    SUBSTITUTION_APPLIED: "已替换当日动作",
    FEEDBACK_RECORDED: "已记录当日执行情况",
}


def display_text_zh(code: str) -> str:
    """Bounded Chinese display text for a rationale code."""
    return _ZH.get(code, code)


__all__ = [
    "INITIAL_GENERATION",
    "INITIAL_CONFIRMATION",
    "SUPERSEDED_BY_NEW_DRAFT",
    "CANCELLED_BY_USER",
    "SUBSTITUTION_APPLIED",
    "FEEDBACK_RECORDED",
    "ALL_CODES",
    "display_text_zh",
]
