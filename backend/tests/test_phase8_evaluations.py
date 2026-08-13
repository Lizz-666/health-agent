"""Versioned synthetic Phase 8 training and Agent evaluation matrices."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict
import xml.etree.ElementTree as ET

import pytest
from pydantic import ValidationError

from app.agent.provider import (
    ProviderFailure,
    ProviderRequest,
    ScriptedProvider,
    parse_provider_decision,
)
from app.agent.safety_precheck import route_turn_text
from app.training.candidates import select_candidates
from app.training.knowledge import load_catalog
from app.training.policy import load_training_policy
from app.training.safety import classify_safety, load_safety_policy
from app.training.schemas import TrainingSafetyContext


DATA_DIR = Path(__file__).with_name("data")
BACKEND_DIR = Path(__file__).parents[1]
TRAINING_PATH = DATA_DIR / "phase8_training_cases.v1.json"
AGENT_PATH = DATA_DIR / "phase8_agent_cases.v1.json"
TRAINING = json.loads(TRAINING_PATH.read_text(encoding="utf-8"))
AGENT = json.loads(AGENT_PATH.read_text(encoding="utf-8"))
CATALOG = load_catalog(BACKEND_DIR / "app/training/data/exercises.v1.json")
SAFETY_POLICY = load_safety_policy(
    BACKEND_DIR / "app/training/data/training_safety_policy.v1.json"
)
TRAINING_POLICY = load_training_policy(
    BACKEND_DIR / "app/training/data/training_policy.v1.json"
)
EVAL_AT = datetime(2026, 8, 9, 1, 0, tzinfo=timezone.utc)
RISK_QUESTIONS = (
    "underage",
    "pregnancy_or_postpartum",
    "recent_surgery_or_major_injury",
    "major_chronic_condition",
    "eating_disorder_concern",
    "professional_instruction_limitations",
)


def _base_training_context() -> Dict[str, Any]:
    return {
        "health": {
            "configured": True,
            "fitness_goal": "basic_strength",
            "training_experience": "experienced",
            "weekly_frequency": 3,
            "session_duration_minutes": 30,
            "equipment_bodyweight": True,
            "equipment_resistance_band": False,
            "pain_limitations": [],
            "risk_screen": {question: "no" for question in RISK_QUESTIONS},
            "profile_version": 1,
            "profile_updated_at": EVAL_AT,
        },
        "checkin": {
            "present": True,
            "local_date": "2026-08-09",
            "recomputed_risk": "normal",
            "token": "synthetic-current-token",
        },
        "retained_pain": [],
        "posture": {
            "active_signals_digest": "synthetic-empty-signals",
            "global_risk_tier": "normal",
            "risk_version": "synthetic-posture-v1",
            "goals": [
                {
                    "issue_id": "lower_limb",
                    "active": True,
                    "blocked": False,
                    "confirmed_at": EVAL_AT,
                    "suggestion_id": "synthetic-suggestion",
                    "profile_version": "synthetic-profile-v1",
                    "rule_version": "synthetic-rule-v1",
                    "risk_version": "synthetic-posture-v1",
                }
            ],
        },
        "request": {
            "fitness_goal": "basic_strength",
            "equipment_bodyweight": True,
            "equipment_resistance_band": False,
            "weekly_frequency": 3,
            "session_duration_minutes": 30,
            "iana_timezone": "Asia/Shanghai",
        },
        "versions": {
            "policy_version": SAFETY_POLICY.policy_version,
            "catalog_version": CATALOG.content_version,
            "source_manifest_version": CATALOG.source_manifest_version,
            "schema_version": "v1",
        },
        "eval": {
            "evaluated_at_utc": EVAL_AT,
            "iana_timezone": "Asia/Shanghai",
            "current_local_date": "2026-08-09",
            "timezone_trusted": True,
        },
    }


def _merge(target: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = value
    return target


def _assert_matrix(document: Dict[str, Any], version: str) -> None:
    assert set(document) == {
        "schema_version",
        "synthetic_only",
        "required_categories",
        "cases",
    }
    assert document["schema_version"] == version
    assert document["synthetic_only"] is True
    cases = document["cases"]
    assert cases and len({case["id"] for case in cases}) == len(cases)
    assert set(document["required_categories"]) == {
        case["category"] for case in cases
    }
    for case in cases:
        assert set(case) >= {"id", "category", "evaluator", "expected"}
        assert case["expected"]
        if case["evaluator"] == "linked_pytest":
            assert set(case["expected"]) == {"pytest_cases"}
            assert case["expected"]["pytest_cases"] >= 1
        encoded = json.dumps(case, sort_keys=True)
        assert "real_" not in encoded.lower()
        assert "access_token" not in encoded.lower()


def test_versioned_matrices_are_closed_complete_and_synthetic():
    _assert_matrix(TRAINING, "phase8-training-eval-v1")
    _assert_matrix(AGENT, "phase8-agent-eval-v1")
    assert set(TRAINING["required_categories"]) == {
        "supported",
        "missing_input",
        "equipment_schedule_conflict",
        "pain",
        "restricted",
        "red_flag",
        "stale",
        "replay",
        "adjustment_safety",
    }
    assert set(AGENT["required_categories"]) == {
        "allowed_read",
        "proposal_confirmation_write",
        "consent_missing_withdrawn",
        "prompt_injection",
        "cross_user",
        "unknown_tool",
        "invalid_schema",
        "provider_timeout_exhaustion",
        "safety_pre_route",
    }


@pytest.mark.parametrize(
    "case",
    [case for case in TRAINING["cases"] if case["evaluator"] == "safety_candidates"],
    ids=lambda case: case["id"],
)
def test_training_safety_candidate_matrix(case):
    raw = _merge(deepcopy(_base_training_context()), case["overrides"])
    context = TrainingSafetyContext.model_validate(raw)
    decision = classify_safety(context, SAFETY_POLICY)
    candidates = select_candidates(
        context, decision, CATALOG, TRAINING_POLICY, SAFETY_POLICY
    )
    expected = case["expected"]

    assert decision.gate_status.value == expected["gate"]
    assert candidates.gate_status.value == expected["candidate_gate"]
    assert len(candidates.candidates) >= expected["min_candidates"]
    if expected["candidate_ids_hidden"]:
        assert candidates.candidates == []
        assert candidates.excluded == []
    if "excluded_reason" in expected:
        assert any(
            expected["excluded_reason"] in excluded.reason_codes
            for excluded in candidates.excluded
        )


@pytest.mark.parametrize(
    "case",
    [
        case
        for case in AGENT["cases"]
        if case["evaluator"] in {"provider_parse_accept", "provider_parse_reject"}
    ],
    ids=lambda case: case["id"],
)
def test_agent_provider_schema_matrix(case):
    if case["evaluator"] == "provider_parse_accept":
        decision = parse_provider_decision(case["input"])
        assert decision.type == case["expected"]["decision_type"]
    else:
        with pytest.raises((ValidationError, TypeError)):
            parse_provider_decision(case["input"])
        assert case["expected"]["result_code"] == "agent_output_invalid"


@pytest.mark.parametrize(
    "case",
    [case for case in AGENT["cases"] if case["evaluator"] == "safety_pre_route"],
    ids=lambda case: case["id"],
)
def test_agent_safety_pre_route_matrix(case):
    result = route_turn_text(case["input"]["message"])
    assert result.routed is case["expected"]["routed"]
    assert result.result_code == case["expected"]["result_code"]
    assert result.signal == case["expected"]["signal"]


@pytest.mark.asyncio
async def test_scripted_provider_exhaustion_matrix():
    case = next(
        case for case in AGENT["cases"] if case["evaluator"] == "scripted_exhaustion"
    )
    provider = ScriptedProvider([])
    request = ProviderRequest(
        prompt_version="phase8-eval-v1",
        system_prompt="Return one reviewed JSON decision.",
        user_message="Synthetic read-only request.",
        context={"entry_type": "general"},
        allowed_tools=[],
        read_results=[],
    )
    with pytest.raises(ProviderFailure) as error:
        await provider.decide(request)
    assert error.value.code == case["expected"]["result_code"]
    assert provider.calls == [request]


def test_linked_state_machine_cases_pass_as_one_closed_evaluation(tmp_path):
    linked = [
        case
        for document in (TRAINING, AGENT)
        for case in document["cases"]
        if case["evaluator"] == "linked_pytest"
    ]
    nodeids = list(dict.fromkeys(case["nodeid"] for case in linked))
    expected_cases = sum(case["expected"]["pytest_cases"] for case in linked)
    junit = tmp_path / "phase8-linked-junit.xml"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *nodeids,
            "-q",
            f"--junitxml={junit}",
        ],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    root = ET.parse(junit).getroot()
    suites = root.findall("testsuite") if root.tag == "testsuites" else [root]
    total = sum(int(suite.get("tests", "0")) for suite in suites)
    failed = sum(
        int(suite.get("failures", "0")) + int(suite.get("errors", "0"))
        for suite in suites
    )
    skipped = sum(int(suite.get("skipped", "0")) for suite in suites)
    assert (total, failed, skipped) == (expected_cases, 0, 0)
    assert len(nodeids) == 14
