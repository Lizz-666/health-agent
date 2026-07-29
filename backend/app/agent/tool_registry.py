"""Static typed read Tool Registry + entry allowlists (Task 1).

The registry is static code (never model-selected). Each entry binds a stable
Tool name to its typed ``provider_view`` / ``display_view`` models, allowed
entry types, ``read`` side-effect class, and the server adapter that reuses an
existing domain service. Unknown Tools, unknown entry combinations, and every
write/risk/validator name fail closed (spec Tool Registry And Permission Matrix,
ADR-0003).

Decision 1 (Gate 0 minimal scope): Task 1 registers ONLY read Tools. Write Tool
schemas, confirmation metadata, and execution adapters are deferred to Task 3;
until then a write Tool name is simply unknown and rejected.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, FrozenSet, Tuple

from app.agent import read_tools
from app.agent.messages import AgentError, ResultCode
from app.agent.schemas import (
    ActivePlanDisplayView,
    ActivePlanProviderView,
    EntryType,
    HealthProfileDisplayView,
    HealthProfileProviderView,
    PostureIssueDetailDisplayView,
    PostureIssueDetailProviderView,
    PostureIssueListDisplayView,
    PostureIssueListProviderView,
    PostureProfileDisplayView,
    PostureProfileProviderView,
    PosturePrioritiesDisplayView,
    PosturePrioritiesProviderView,
    SelfTestGuideDisplayView,
    SelfTestGuideProviderView,
    SideEffectClass,
    TodayCheckinDisplayView,
    TodayCheckinProviderView,
    TodayTrainingDisplayView,
    TodayTrainingProviderView,
    TrainingDraftDisplayView,
    TrainingDraftProviderView,
    TrainingExerciseDisplayView,
    TrainingExerciseProviderView,
    WeightTrendDisplayView,
    WeightTrendProviderView,
)


@dataclass(frozen=True)
class ReadToolSpec:
    """Static metadata binding a read Tool to its contracts and adapter."""

    name: str
    allowed_entries: FrozenSet[EntryType]
    side_effect: SideEffectClass
    provider_view_model: type
    display_view_model: type
    adapter: Callable
    requires_confirmation: bool = False


def _spec(
    name: str,
    entries: FrozenSet[EntryType],
    provider_view_model: type,
    display_view_model: type,
    adapter: Callable,
) -> ReadToolSpec:
    return ReadToolSpec(
        name=name,
        allowed_entries=entries,
        side_effect=SideEffectClass.READ,
        provider_view_model=provider_view_model,
        display_view_model=display_view_model,
        adapter=adapter,
        requires_confirmation=False,
    )


_HEALTH_ENTRIES = frozenset({EntryType.general, EntryType.health_profile})
_POSTURE_ENTRIES = frozenset({EntryType.general, EntryType.posture_issue})
_PLAN_ENTRIES = frozenset({EntryType.general, EntryType.training_plan})
_TRAINING_TODAY_ENTRIES = frozenset(
    {
        EntryType.general,
        EntryType.training_plan,
        EntryType.training_session,
        EntryType.training_exercise,
    }
)
_EXERCISE_ENTRIES = frozenset(
    {EntryType.training_session, EntryType.training_exercise}
)


READ_TOOLS: Dict[str, ReadToolSpec] = {
    spec.name: spec
    for spec in (
        _spec(
            "get_health_profile_summary",
            _HEALTH_ENTRIES,
            HealthProfileProviderView,
            HealthProfileDisplayView,
            read_tools.adapt_health_profile_summary,
        ),
        _spec(
            "get_today_checkin",
            _HEALTH_ENTRIES,
            TodayCheckinProviderView,
            TodayCheckinDisplayView,
            read_tools.adapt_today_checkin,
        ),
        _spec(
            "get_weight_trend_summary",
            _HEALTH_ENTRIES,
            WeightTrendProviderView,
            WeightTrendDisplayView,
            read_tools.adapt_weight_trend_summary,
        ),
        _spec(
            "list_posture_issues",
            _POSTURE_ENTRIES,
            PostureIssueListProviderView,
            PostureIssueListDisplayView,
            read_tools.adapt_list_posture_issues,
        ),
        _spec(
            "get_posture_issue",
            frozenset({EntryType.posture_issue}),
            PostureIssueDetailProviderView,
            PostureIssueDetailDisplayView,
            read_tools.adapt_get_posture_issue,
        ),
        _spec(
            "guide_posture_self_test",
            frozenset({EntryType.posture_issue}),
            SelfTestGuideProviderView,
            SelfTestGuideDisplayView,
            read_tools.adapt_guide_posture_self_test,
        ),
        _spec(
            "get_posture_profile",
            _POSTURE_ENTRIES,
            PostureProfileProviderView,
            PostureProfileDisplayView,
            read_tools.adapt_get_posture_profile,
        ),
        _spec(
            "get_posture_priorities",
            _POSTURE_ENTRIES,
            PosturePrioritiesProviderView,
            PosturePrioritiesDisplayView,
            read_tools.adapt_get_posture_priorities,
        ),
        _spec(
            "get_training_draft",
            _PLAN_ENTRIES,
            TrainingDraftProviderView,
            TrainingDraftDisplayView,
            read_tools.adapt_get_training_draft,
        ),
        _spec(
            "get_active_training_plan",
            _PLAN_ENTRIES,
            ActivePlanProviderView,
            ActivePlanDisplayView,
            read_tools.adapt_get_active_training_plan,
        ),
        _spec(
            "get_today_training",
            _TRAINING_TODAY_ENTRIES,
            TodayTrainingProviderView,
            TodayTrainingDisplayView,
            read_tools.adapt_get_today_training,
        ),
        _spec(
            "get_training_exercise",
            _EXERCISE_ENTRIES,
            TrainingExerciseProviderView,
            TrainingExerciseDisplayView,
            read_tools.adapt_get_training_exercise,
        ),
    )
}


def is_read_tool(name: str) -> bool:
    """True iff ``name`` is a registered provider-exposed read Tool."""
    return name in READ_TOOLS


def get_read_tool(name: str) -> ReadToolSpec:
    """Return the read Tool spec or fail closed for any unknown name."""
    try:
        return READ_TOOLS[name]
    except KeyError as exc:
        raise AgentError(
            ResultCode.TOOL_NOT_ALLOWED, f"unknown read tool: {name!r}"
        ) from exc


def is_tool_allowed(name: str, entry_type: EntryType) -> bool:
    """True iff ``name`` is a read Tool allowed at ``entry_type``."""
    spec = READ_TOOLS.get(name)
    return spec is not None and entry_type in spec.allowed_entries


def allowed_tools_for(entry_type: EntryType) -> Tuple[str, ...]:
    """Sorted stable Tool names offered for ``entry_type`` (empty if none)."""
    return tuple(
        sorted(
            name
            for name, spec in READ_TOOLS.items()
            if entry_type in spec.allowed_entries
        )
    )


def resolve_tool_for_entry(name: str, entry_type: EntryType) -> ReadToolSpec:
    """Return the spec only when ``name`` is allowed at ``entry_type``.

    Unknown Tool, or a known Tool at a non-allowed entry, both fail closed with
    ``agent_tool_not_allowed`` (non-enumerating: the caller cannot distinguish
    an unknown Tool from a disallowed-here Tool).
    """
    spec = READ_TOOLS.get(name)
    if spec is None or entry_type not in spec.allowed_entries:
        raise AgentError(
            ResultCode.TOOL_NOT_ALLOWED,
            f"tool {name!r} not allowed for entry {entry_type.value!r}",
        )
    return spec


__all__ = [
    "ReadToolSpec",
    "READ_TOOLS",
    "is_read_tool",
    "get_read_tool",
    "is_tool_allowed",
    "allowed_tools_for",
    "resolve_tool_for_entry",
]
