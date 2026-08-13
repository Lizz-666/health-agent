"""Versioned training policy loader tests (Task 5)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.training.policy import TrainingPolicy, load_training_policy

POLICY_PATH = "app/training/data/training_policy.v1.json"


def test_policy_loads_with_expected_shape():
    p = load_training_policy(POLICY_PATH)
    assert p.policy_version == "v1"
    # The exact spec filter order is preserved.
    assert p.filter_order == [
        "context_valid", "gate", "recommendation_ready", "equipment",
        "goal_and_posture", "contraindication", "conservative", "dedup",
        "conflict", "sort",
    ]
    assert p.role_priority[0] == "corrective"
    assert p.difficulty_priority[0] == "beginner"
    assert p.dedup_by == "movement_purpose_overlap"


def test_role_and_difficulty_indices():
    p = load_training_policy(POLICY_PATH)
    assert p.role_index(["strength"]) == 1
    assert p.role_index(["recovery"]) == 4
    assert p.role_index(["corrective", "recovery"]) == 0  # best wins
    assert p.role_index(["unknown_role"]) == len(p.role_priority)
    assert p.difficulty_index("beginner") == 0
    assert p.difficulty_index("advanced") == 2


def test_volume_caps_are_sensible_and_bounded():
    p = load_training_policy(POLICY_PATH)
    assert 1 <= p.max_exercises_per_session <= 20
    assert p.max_sessions_per_week <= 7
    assert p.min_recovery_hours_between_sessions >= 0


def test_policy_model_rejects_unknown_field():
    with pytest.raises(Exception):
        TrainingPolicy.model_validate({
            "policy_version": "v1", "filter_order": ["gate"],
            "role_priority": ["strength"], "difficulty_priority": ["beginner"],
            "unexpected_field": True,
        })


def test_policy_loader_rejects_missing_safety_section(tmp_path):
    raw = json.loads(Path(POLICY_PATH).read_text(encoding="utf-8"))
    raw.pop("weekly_volume")
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(KeyError):
        load_training_policy(path)


def test_policy_loader_rejects_unknown_nested_control(tmp_path):
    raw = json.loads(Path(POLICY_PATH).read_text(encoding="utf-8"))
    raw["weekly_volume"]["minimum_recovery_typo"] = 0
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported weekly_volume"):
        load_training_policy(path)
