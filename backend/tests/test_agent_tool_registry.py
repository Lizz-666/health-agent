"""Phase 5 Task 1 (Batch A) - static read Tool Registry + entry allowlists.

The registry is static code that binds each read Tool to its allowed entries,
side-effect class, typed projections, and server adapter. Unknown Tools, unknown
entries, and every write/risk/validator name fail closed (Decision 1: Task 1
registers ONLY read Tools). Synthetic data only.
"""
from __future__ import annotations

import pytest

from app.agent import tool_registry
from app.agent.messages import AgentError, ResultCode
from app.agent.schemas import (
    AuthModel,
    BaseModel,
    DisplayView,
    EntryType,
    GetPostureIssueInput,
    GetTrainingExerciseInput,
    HealthProfileDisplayView,
    ListPostureIssuesInput,
    ProviderView,
    ReadToolResult,
    SideEffectClass,
    WeightTrendProviderView,
)

# The exact read Tools named in the spec Tool Registry And Permission Matrix.
_READ_TOOLS = {
    "get_health_profile_summary",
    "get_today_checkin",
    "get_weight_trend_summary",
    "list_posture_issues",
    "get_posture_issue",
    "guide_posture_self_test",
    "get_posture_profile",
    "get_posture_priorities",
    "get_training_draft",
    "get_active_training_plan",
    "get_today_training",
    "get_training_exercise",
}

# Write Tools appear in the spec matrix but MUST NOT be registered in Task 1.
_WRITE_TOOLS = {
    "upsert_today_checkin",
    "create_weight_record",
    "generate_training_plan_draft",
    "substitute_today_exercise",
    "record_training_feedback",
}

# Mandatory server wrappers / non-Tools that must never be provider-exposed.
_NON_TOOLS = {
    "classify_risk",
    "risk_classification",
    "validate_plan",
    "plan_validator",
    "confirm_posture_goals",
    "analyze_posture_photo",
}


_EXPECTED_ALLOWLIST = {
    EntryType.general: {
        "get_health_profile_summary",
        "get_today_checkin",
        "get_weight_trend_summary",
        "list_posture_issues",
        "get_posture_profile",
        "get_posture_priorities",
        "get_training_draft",
        "get_active_training_plan",
        "get_today_training",
    },
    EntryType.health_profile: {
        "get_health_profile_summary",
        "get_today_checkin",
        "get_weight_trend_summary",
    },
    EntryType.posture_issue: {
        "list_posture_issues",
        "get_posture_issue",
        "guide_posture_self_test",
        "get_posture_profile",
        "get_posture_priorities",
    },
    EntryType.training_plan: {
        "get_training_draft",
        "get_active_training_plan",
        "get_today_training",
    },
    EntryType.training_session: {
        "get_today_training",
        "get_training_exercise",
    },
    EntryType.training_exercise: {
        "get_today_training",
        "get_training_exercise",
    },
}


def test_registry_contains_exactly_the_spec_read_tools():
    assert set(tool_registry.READ_TOOLS) == _READ_TOOLS


def test_every_tool_is_read_class_with_typed_projections_and_adapter():
    for name, spec in tool_registry.READ_TOOLS.items():
        assert spec.name == name
        assert spec.side_effect is SideEffectClass.READ
        assert spec.requires_confirmation is False
        assert issubclass(spec.provider_view_model, ProviderView)
        assert issubclass(spec.display_view_model, DisplayView)
        assert callable(spec.adapter)


@pytest.mark.parametrize("entry", list(EntryType))
def test_allowed_tools_for_matches_the_permission_matrix(entry):
    assert set(tool_registry.allowed_tools_for(entry)) == _EXPECTED_ALLOWLIST[entry]


def test_every_allow_cell_resolves_and_every_deny_cell_fails_closed():
    for entry in EntryType:
        allowed = _EXPECTED_ALLOWLIST[entry]
        for tool in _READ_TOOLS:
            if tool in allowed:
                spec = tool_registry.resolve_tool_for_entry(tool, entry)
                assert spec.name == tool
                assert tool_registry.is_tool_allowed(tool, entry) is True
            else:
                assert tool_registry.is_tool_allowed(tool, entry) is False
                with pytest.raises(AgentError) as exc:
                    tool_registry.resolve_tool_for_entry(tool, entry)
                assert exc.value.code == ResultCode.TOOL_NOT_ALLOWED


def test_unknown_tool_name_fails_closed():
    with pytest.raises(AgentError) as exc:
        tool_registry.get_read_tool("definitely_not_a_tool")
    assert exc.value.code == ResultCode.TOOL_NOT_ALLOWED


@pytest.mark.parametrize("name", sorted(_WRITE_TOOLS | _NON_TOOLS))
def test_write_and_wrapper_names_are_not_provider_exposed_reads(name):
    assert name not in tool_registry.READ_TOOLS
    assert tool_registry.is_read_tool(name) is False
    with pytest.raises(AgentError) as exc:
        tool_registry.get_read_tool(name)
    assert exc.value.code == ResultCode.TOOL_NOT_ALLOWED
    # And it is disallowed at every entry.
    for entry in EntryType:
        assert tool_registry.is_tool_allowed(name, entry) is False


def test_resolve_rejects_unknown_entry_membership_for_known_tool():
    # A known read Tool at a non-allowed entry still fails closed.
    with pytest.raises(AgentError) as exc:
        tool_registry.resolve_tool_for_entry(
            "get_training_exercise", EntryType.health_profile
        )
    assert exc.value.code == ResultCode.TOOL_NOT_ALLOWED


# ===========================================================================
# Fix #2: strict Tool input models + auth/context binding + validators
# ===========================================================================


def test_every_tool_binds_strict_input_output_and_auth_metadata():
    for name, spec in tool_registry.READ_TOOLS.items():
        assert spec.side_effect is SideEffectClass.READ
        assert spec.requires_confirmation is False
        # input model is strict (extra forbidden).
        assert issubclass(spec.input_model, BaseModel)
        assert spec.input_model.model_config.get("extra") == "forbid"
        # output models are the typed projections.
        assert issubclass(spec.provider_view_model, ProviderView)
        assert issubclass(spec.display_view_model, DisplayView)
        assert isinstance(spec.auth_model, AuthModel)
        assert callable(spec.adapter)


def test_tools_with_provider_typeable_args_have_typed_input_models():
    assert (
        tool_registry.READ_TOOLS["list_posture_issues"].input_model
        is ListPostureIssuesInput
    )
    assert (
        tool_registry.READ_TOOLS["get_posture_issue"].input_model
        is GetPostureIssueInput
    )
    assert (
        tool_registry.READ_TOOLS["get_training_exercise"].input_model
        is GetTrainingExerciseInput
    )


def test_identity_bearing_tools_carry_no_identity_in_their_input_model():
    # No input model may accept a server-injected identity/authority value.
    forbidden = {
        "user_id",
        "actor",
        "db",
        "consent",
        "consent_record",
        "risk_tier",
        "policy_version",
        "iana_timezone",
        "server_time",
        "now",
        "allowed_tools",
    }
    for spec in tool_registry.READ_TOOLS.values():
        assert not (forbidden & set(spec.input_model.model_fields)), spec.name


@pytest.mark.parametrize(
    "name, raw",
    [
        ("get_health_profile_summary", {"user_id": "attacker"}),
        ("get_today_checkin", {"now": "2026-01-01"}),
        ("list_posture_issues", {"category": "x", "extra": 1}),
        ("get_posture_issue", {"issue_id": "x", "actor": object()}),
        ("get_training_exercise", {"exercise_id": "ex1", "user_id": "u"}),
    ],
)
def test_unknown_or_identity_input_field_fails_closed(name, raw):
    with pytest.raises(AgentError) as exc:
        tool_registry.validate_tool_input(name, raw)
    assert exc.value.code == ResultCode.TOOL_NOT_ALLOWED


def test_invalid_argument_value_fails_closed():
    # A missing required field is an invalid tool input, not a server error.
    with pytest.raises(AgentError) as exc:
        tool_registry.validate_tool_input("get_training_exercise", {})
    assert exc.value.code == ResultCode.TOOL_NOT_ALLOWED


def test_post_validator_rejects_wrong_output_type():
    spec = tool_registry.get_read_tool("get_health_profile_summary")
    # A non-ReadToolResult object fails closed.
    with pytest.raises(AgentError) as exc:
        spec.validate_output(object())
    assert exc.value.code == ResultCode.TOOL_NOT_ALLOWED


def test_post_validator_rejects_wrong_provider_view_type():
    spec = tool_registry.get_read_tool("get_health_profile_summary")
    # Correct display view but a provider_view of the wrong bound type.
    bogus = ReadToolResult(
        tool_name="get_health_profile_summary",
        provider_view=WeightTrendProviderView(
            sufficient=False, window=7, record_count=0, trend_point_count=0
        ),
        display_view=HealthProfileDisplayView(configured=False),
    )
    with pytest.raises(AgentError) as exc:
        spec.validate_output(bogus)
    assert exc.value.code == ResultCode.TOOL_NOT_ALLOWED


def test_valid_input_round_trips_through_pre_validator():
    parsed = tool_registry.validate_tool_input(
        "get_training_exercise", {"exercise_id": "ex1"}
    )
    assert isinstance(parsed, GetTrainingExerciseInput)
    assert parsed.exercise_id == "ex1"
