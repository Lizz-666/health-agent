from pathlib import Path

import pytest
from pydantic import ValidationError

from app.training.adaptive_policy import (
    AdjustmentInput,
    AdjustmentKind,
    decide_adjustment,
    load_adaptive_policy,
)


POLICY_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "training"
    / "data"
    / "training_adaptive_policy.v1.json"
)


def _input(**overrides):
    data = {
        "available_time": "45_min_plus",
        "energy": "normal",
        "muscle_soreness": "mild",
        "daily_status": "checked_in",
        "abnormal_pain": False,
        "target_minutes": 30,
        "prescription_count": 5,
    }
    data.update(overrides)
    return AdjustmentInput(**data)


def test_policy_loads_reviewed_version_and_bounded_duration_caps():
    policy = load_adaptive_policy(POLICY_PATH)
    assert policy.policy_version == "adaptive-v1"
    assert policy.review_scope == "personal_development"
    assert policy.duration_minutes == {
        "15_min": 15,
        "30_min": 30,
        "45_min_plus": 45,
    }
    assert policy.exercise_caps == {15: 3, 30: 5, 45: 7, 60: 8}


@pytest.mark.parametrize("field,value", [
    ("available_time", "unknown"),
    ("energy", "exhausted"),
    ("muscle_soreness", "severe"),
    ("daily_status", "missed"),
])
def test_unknown_structured_input_fails_schema(field, value):
    with pytest.raises(ValidationError):
        _input(**{field: value})


def test_abnormal_pain_blocks_instead_of_recovery_or_deferral():
    result = decide_adjustment(
        _input(
            abnormal_pain=True,
            energy="low",
            available_time="none",
        ),
        load_adaptive_policy(POLICY_PATH),
    )
    assert result.kind is AdjustmentKind.blocked
    assert result.reason_codes == ("abnormal_pain_blocks_adjustment",)


@pytest.mark.parametrize("status", ["active_rest", "safety_adjustment"])
def test_no_time_or_explicit_rest_defers_before_recovery(status):
    result = decide_adjustment(
        _input(
            daily_status=status,
            available_time="none",
            energy="low",
            muscle_soreness="significant",
        ),
        load_adaptive_policy(POLICY_PATH),
    )
    assert result.kind is AdjustmentKind.deferred
    assert result.target_minutes is None


@pytest.mark.parametrize("field", ["energy", "muscle_soreness"])
def test_low_energy_or_significant_soreness_selects_recovery(field):
    value = "low" if field == "energy" else "significant"
    result = decide_adjustment(
        _input(**{field: value}), load_adaptive_policy(POLICY_PATH)
    )
    assert result.kind is AdjustmentKind.recovery
    assert result.reason_codes == (f"{field}_recovery",)


@pytest.mark.parametrize(
    "available,target,count,kind,minutes",
    [
        ("15_min", 60, 8, AdjustmentKind.shortened, 15),
        ("15_min", 30, 3, AdjustmentKind.shortened, 15),
        ("30_min", 45, 7, AdjustmentKind.shortened, 30),
        ("45_min_plus", 60, 8, AdjustmentKind.shortened, 45),
        ("45_min_plus", 45, 7, AdjustmentKind.unchanged, None),
        ("30_min", 30, 3, AdjustmentKind.unchanged, None),
    ],
)
def test_available_time_shortens_only_when_it_changes_effective_session(
    available, target, count, kind, minutes
):
    result = decide_adjustment(
        _input(
            available_time=available,
            target_minutes=target,
            prescription_count=count,
        ),
        load_adaptive_policy(POLICY_PATH),
    )
    assert result.kind is kind
    assert result.target_minutes == minutes
