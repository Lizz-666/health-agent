"""Deterministic Phase 7 same-day adjustment routing.

The policy consumes only existing structured check-in categories. It does not
classify pain or eligibility; callers must run the authoritative training safety
engine first. Unknown inputs fail Pydantic validation rather than becoming an
ordinary adjustment.
"""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Dict, Literal, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AdjustmentKind(str, Enum):
    blocked = "blocked"
    shortened = "shortened"
    recovery = "recovery"
    deferred = "deferred"
    active_rest = "active_rest"
    unchanged = "unchanged"


class AdaptivePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: str = Field(..., min_length=1, max_length=40)
    review_scope: Literal["personal_development"]
    duration_minutes: Dict[str, int]
    exercise_caps: Dict[int, int]
    required_roles: Tuple[str, ...]
    recovery_roles: Tuple[str, ...]

    @field_validator("duration_minutes")
    @classmethod
    def _duration_keys_are_closed(cls, value):
        if set(value) != {"15_min", "30_min", "45_min_plus"}:
            raise ValueError("duration_minutes has unsupported keys")
        if value != {"15_min": 15, "30_min": 30, "45_min_plus": 45}:
            raise ValueError("duration_minutes must use approved buckets")
        return value

    @field_validator("exercise_caps")
    @classmethod
    def _exercise_caps_are_closed(cls, value):
        if value != {15: 3, 30: 5, 45: 7, 60: 8}:
            raise ValueError("exercise_caps must match reviewed duration buckets")
        return value


class AdjustmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available_time: Literal["none", "15_min", "30_min", "45_min_plus"]
    energy: Literal["low", "normal", "high"]
    muscle_soreness: Literal["none", "mild", "significant"]
    daily_status: Literal["checked_in", "active_rest", "safety_adjustment"]
    abnormal_pain: bool
    target_minutes: Literal[15, 30, 45, 60]
    prescription_count: int = Field(..., ge=1, le=8)


class AdjustmentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: AdjustmentKind
    target_minutes: Optional[int] = None
    reason_codes: Tuple[str, ...]


def load_adaptive_policy(path: Union[str, Path]) -> AdaptivePolicy:
    with Path(path).open("r", encoding="utf-8") as handle:
        return AdaptivePolicy.model_validate(json.load(handle))


def decide_adjustment(
    inputs: AdjustmentInput, policy: AdaptivePolicy
) -> AdjustmentDecision:
    """Choose a bounded adjustment kind; no persistence or health inference."""
    if inputs.abnormal_pain:
        return AdjustmentDecision(
            kind=AdjustmentKind.blocked,
            reason_codes=("abnormal_pain_blocks_adjustment",),
        )

    if inputs.available_time == "none" or inputs.daily_status == "active_rest":
        reason = (
            "active_rest_requested"
            if inputs.daily_status == "active_rest"
            else "no_available_time"
        )
        return AdjustmentDecision(
            kind=AdjustmentKind.deferred, reason_codes=(reason,)
        )

    if inputs.energy == "low":
        return AdjustmentDecision(
            kind=AdjustmentKind.recovery,
            reason_codes=("energy_recovery",),
        )
    if inputs.muscle_soreness == "significant":
        return AdjustmentDecision(
            kind=AdjustmentKind.recovery,
            reason_codes=("muscle_soreness_recovery",),
        )
    if inputs.daily_status == "safety_adjustment":
        return AdjustmentDecision(
            kind=AdjustmentKind.recovery,
            reason_codes=("daily_status_recovery",),
        )

    available_minutes = policy.duration_minutes[inputs.available_time]
    if (
        available_minutes < inputs.target_minutes
    ):
        return AdjustmentDecision(
            kind=AdjustmentKind.shortened,
            target_minutes=available_minutes,
            reason_codes=("available_time_shortened",),
        )
    return AdjustmentDecision(
        kind=AdjustmentKind.unchanged,
        reason_codes=("no_adjustment_needed",),
    )


__all__ = [
    "AdaptivePolicy",
    "AdjustmentDecision",
    "AdjustmentInput",
    "AdjustmentKind",
    "decide_adjustment",
    "load_adaptive_policy",
]
