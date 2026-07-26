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

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TrainingPolicy(BaseModel):
    """Typed view of ``training_policy.v1.json``."""

    model_config = ConfigDict(extra="forbid")

    policy_version: str = Field(..., min_length=1)
    filter_order: List[str]
    role_priority: List[str]
    difficulty_priority: List[str]
    conservative_requires_conservative_eligible: bool
    dedup_by: str
    dedup_reason_code: str
    conflict_pick: str
    max_exercises_per_session: int = Field(..., ge=1, le=20)
    max_sets_per_session: int = Field(..., ge=1, le=60)
    max_sessions_per_week: int = Field(..., ge=1, le=7)
    min_recovery_hours_between_sessions: int = Field(..., ge=0, le=168)

    @model_validator(mode="after")
    def _validate_engine_contract(self):
        if self.filter_order != [
            "context_valid", "gate", "recommendation_ready", "equipment",
            "goal_and_posture", "contraindication", "conservative", "dedup",
            "conflict", "sort",
        ]:
            raise ValueError("filter_order does not match the implemented contract")
        if set(self.role_priority) != {
            "warmup", "strength", "corrective", "mobility", "recovery"}:
            raise ValueError("role_priority must contain every supported role once")
        if len(self.role_priority) != len(set(self.role_priority)):
            raise ValueError("role_priority contains duplicates")
        if self.difficulty_priority != ["beginner", "intermediate", "advanced"]:
            raise ValueError("difficulty_priority does not match the supported order")
        if self.dedup_by != "movement_purpose_overlap":
            raise ValueError("unsupported dedup policy")
        if self.conflict_pick != "lowest_sort_key":
            raise ValueError("unsupported conflict policy")
        return self

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
    allowed_top_level = {
        "policy_version", "review_scope", "source", "filter_order",
        "role_priority", "difficulty_priority",
        "conservative_requires_conservative_eligible", "dedup",
        "conflict_resolution", "session_volume", "weekly_volume",
        "sort_key_composition",
    }
    unknown_top_level = set(data) - allowed_top_level
    if unknown_top_level:
        raise ValueError(
            f"unsupported policy fields: {sorted(unknown_top_level)}")
    dedup = data["dedup"]
    conflict = data["conflict_resolution"]
    session_volume = data["session_volume"]
    weekly_volume = data["weekly_volume"]
    expected_nested = {
        "dedup": {"by", "reason_code"},
        "conflict_resolution": {"pick", "note"},
        "session_volume": {"max_exercises_per_session", "max_sets_per_session"},
        "weekly_volume": {
            "max_sessions_per_week", "min_recovery_hours_between_sessions"},
    }
    for section, expected in expected_nested.items():
        unknown = set(data[section]) - expected
        if unknown:
            raise ValueError(
                f"unsupported {section} control fields: {sorted(unknown)}")
    return TrainingPolicy(
        policy_version=data["policy_version"],
        filter_order=data["filter_order"],
        role_priority=data["role_priority"],
        difficulty_priority=data["difficulty_priority"],
        conservative_requires_conservative_eligible=
            data["conservative_requires_conservative_eligible"],
        dedup_by=dedup["by"],
        dedup_reason_code=dedup["reason_code"],
        conflict_pick=conflict["pick"],
        max_exercises_per_session=
            session_volume["max_exercises_per_session"],
        max_sets_per_session=session_volume["max_sets_per_session"],
        max_sessions_per_week=weekly_volume["max_sessions_per_week"],
        min_recovery_hours_between_sessions=
            weekly_volume["min_recovery_hours_between_sessions"],
    )
