"""Versioned training policy loader (Task 5).

Loads ``training_policy.v1.json`` into a typed ``TrainingPolicy``. The policy
defines the exact candidate filter order, role/difficulty priorities, the
de-duplication rule, conflict resolution and the session/weekly volume caps
used by the candidate engine (Task 5) and the validator (Task 6).

Policy values are versioned product-policy constraints within the healthy-adult
source envelope, NOT medical prescriptions.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Union

from pydantic import BaseModel, ConfigDict, Field


class TrainingPolicy(BaseModel):
    """Typed view of ``training_policy.v1.json``."""

    model_config = ConfigDict(extra="forbid")

    policy_version: str = Field(..., min_length=1)
    filter_order: List[str]
    role_priority: List[str]
    difficulty_priority: List[str]
    conservative_requires_conservative_eligible: bool = True
    dedup_by: str = Field(default="movement_purposes_set")
    dedup_reason_code: str = Field(default="duplicate_movement_purpose")
    conflict_pick: str = Field(default="lowest_sort_key")
    max_exercises_per_session: int = Field(default=8, ge=1, le=20)
    max_sets_per_session: int = Field(default=24, ge=1, le=60)
    max_sessions_per_week: int = Field(default=5, ge=1, le=7)
    min_recovery_hours_between_sessions: int = Field(default=24, ge=0, le=168)

    def role_index(self, roles) -> int:
        """Return the best (lowest) priority index for an exercise's roles."""
        for idx, role in enumerate(self.role_priority):
            if role in [r.value if hasattr(r, "value") else r for r in roles]:
                return idx
        return len(self.role_priority)

    def difficulty_index(self, difficulty) -> int:
        d = difficulty.value if hasattr(difficulty, "value") else difficulty
        if d in self.difficulty_priority:
            return self.difficulty_priority.index(d)
        return len(self.difficulty_priority)


def load_training_policy(path: Union[str, Path]) -> TrainingPolicy:
    with Path(path).open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return TrainingPolicy(
        policy_version=data["policy_version"],
        filter_order=data["filter_order"],
        role_priority=data["role_priority"],
        difficulty_priority=data["difficulty_priority"],
        conservative_requires_conservative_eligible=(
            data.get("conservative_requires_conservative_eligible", True)),
        dedup_by=data.get("dedup", {}).get("by", "movement_purposes_set"),
        dedup_reason_code=data.get("dedup", {}).get(
            "reason_code", "duplicate_movement_purpose"),
        conflict_pick=data.get("conflict_resolution", {}).get(
            "pick", "lowest_sort_key"),
        max_exercises_per_session=data.get("session_volume", {}).get(
            "max_exercises_per_session", 8),
        max_sets_per_session=data.get("session_volume", {}).get(
            "max_sets_per_session", 24),
        max_sessions_per_week=data.get("weekly_volume", {}).get(
            "max_sessions_per_week", 5),
        min_recovery_hours_between_sessions=data.get(
            "weekly_volume", {}).get(
            "min_recovery_hours_between_sessions", 24),
    )
