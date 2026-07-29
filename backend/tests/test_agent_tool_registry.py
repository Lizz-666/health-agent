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
from app.agent.schemas import DisplayView, EntryType, ProviderView, SideEffectClass

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
