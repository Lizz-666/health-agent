"""Static typed read Tool Registry + entry allowlists (Task 1).

The registry is static code (never model-selected). Each entry binds a stable
Tool name to a strict typed ``input_model``, its typed ``provider_view`` /
``display_view`` output models, allowed entry types, ``read`` side-effect class,
a ``requires_confirmation`` flag, a server-only ``auth_model`` describing how
identity is bound, an ``ownership_from_context`` flag, the server adapter that
reuses an existing domain service, and deterministic pre/post validators.

Unknown Tools, unknown entry combinations, unknown input fields, and every
write/risk/validator name fail closed (spec Tool Registry And Permission Matrix,
ADR-0003). Identity (``db`` / ``ActorContext`` / timezone / server clock) is
server-injected only and is NEVER a field on a Tool input model.

Decision 1 (Gate 0 minimal scope): Task 1 registers ONLY read Tools. Write Tool
schemas, confirmation metadata, and execution adapters are deferred to Task 3;
until then a write Tool name is simply unknown and rejected.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, Tuple

from app.agent import read_tools
from app.agent.messages import AgentError, ResultCode
from app.agent.schemas import (
    ActivePlanDisplayView,
    ActivePlanProviderView,
    AuthModel,
    EmptyToolInput,
    EntryType,
    GetPostureIssueInput,
    GetTrainingExerciseInput,
    HealthProfileDisplayView,
    HealthProfileProviderView,
    ListPostureIssuesInput,
    NutritionPortionsDisplayView,
    NutritionPortionsProviderView,
    NutritionTargetsDisplayView,
    NutritionTargetsProviderView,
    NutritionValidationDisplayView,
    NutritionValidationProviderView,
    PostureIssueDetailDisplayView,
    PostureIssueDetailProviderView,
    PostureIssueListDisplayView,
    PostureIssueListProviderView,
    PostureProfileDisplayView,
    PostureProfileProviderView,
    PosturePrioritiesDisplayView,
    PosturePrioritiesProviderView,
    ReadToolResult,
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
from pydantic import BaseModel, ValidationError


@dataclass(frozen=True)
class ReadToolSpec:
    """Static metadata binding a read Tool to its contracts and adapter."""

    name: str
    allowed_entries: FrozenSet[EntryType]
    side_effect: SideEffectClass
    input_model: type
    provider_view_model: type
    display_view_model: type
    adapter: Callable
    auth_model: AuthModel
    ownership_from_context: bool
    requires_confirmation: bool = False

    def validate_input(self, raw: Any) -> BaseModel:
        """Pre-validator: reject unknown fields and invalid arguments.

        Raises ``AgentError(agent_tool_not_allowed)`` for any malformed input so
        the orchestrator cannot forward attacker-controlled fields to an adapter.
        """
        try:
            if raw is None:
                raw = {}
            if not isinstance(raw, dict):
                raise TypeError("tool input must be an object")
            return self.input_model.model_validate(raw)
        except (TypeError, ValidationError) as exc:
            raise AgentError(ResultCode.TOOL_NOT_ALLOWED) from exc

    def validate_output(self, result: Any) -> ReadToolResult:
        """Post-validator: the adapter must return a spec-bound ``ReadToolResult``.

        Fails closed if the adapter returns the wrong shape or a projection that
        is not an instance of the bound typed output models.
        """
        if not isinstance(result, ReadToolResult):
            raise AgentError(ResultCode.TOOL_NOT_ALLOWED)
        if result.tool_name != self.name:
            raise AgentError(ResultCode.TOOL_NOT_ALLOWED)
        if not isinstance(result.provider_view, self.provider_view_model):
            raise AgentError(ResultCode.TOOL_NOT_ALLOWED)
        if not isinstance(result.display_view, self.display_view_model):
            raise AgentError(ResultCode.TOOL_NOT_ALLOWED)
        return result


def _spec(
    name: str,
    entries: FrozenSet[EntryType],
    input_model: type,
    provider_view_model: type,
    display_view_model: type,
    adapter: Callable,
    *,
    auth_model: AuthModel = AuthModel.OWNER,
    ownership_from_context: bool = True,
) -> ReadToolSpec:
    return ReadToolSpec(
        name=name,
        allowed_entries=entries,
        side_effect=SideEffectClass.READ,
        input_model=input_model,
        provider_view_model=provider_view_model,
        display_view_model=display_view_model,
        adapter=adapter,
        auth_model=auth_model,
        ownership_from_context=ownership_from_context,
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
_NUTRITION_ENTRIES = frozenset({EntryType.general, EntryType.nutrition_plan})


READ_TOOLS: Dict[str, ReadToolSpec] = {
    spec.name: spec
    for spec in (
        _spec(
            "get_health_profile_summary",
            _HEALTH_ENTRIES,
            EmptyToolInput,
            HealthProfileProviderView,
            HealthProfileDisplayView,
            read_tools.adapt_health_profile_summary,
        ),
        _spec(
            "get_today_checkin",
            _HEALTH_ENTRIES,
            EmptyToolInput,
            TodayCheckinProviderView,
            TodayCheckinDisplayView,
            read_tools.adapt_today_checkin,
        ),
        _spec(
            "get_weight_trend_summary",
            _HEALTH_ENTRIES,
            EmptyToolInput,
            WeightTrendProviderView,
            WeightTrendDisplayView,
            read_tools.adapt_weight_trend_summary,
        ),
        _spec(
            "list_posture_issues",
            _POSTURE_ENTRIES,
            ListPostureIssuesInput,
            PostureIssueListProviderView,
            PostureIssueListDisplayView,
            read_tools.adapt_list_posture_issues,
            auth_model=AuthModel.PUBLIC,
            ownership_from_context=False,
        ),
        _spec(
            "get_posture_issue",
            frozenset({EntryType.posture_issue}),
            GetPostureIssueInput,
            PostureIssueDetailProviderView,
            PostureIssueDetailDisplayView,
            read_tools.adapt_get_posture_issue,
            auth_model=AuthModel.PUBLIC,
            ownership_from_context=False,
        ),
        _spec(
            "guide_posture_self_test",
            frozenset({EntryType.posture_issue}),
            EmptyToolInput,
            SelfTestGuideProviderView,
            SelfTestGuideDisplayView,
            read_tools.adapt_guide_posture_self_test,
        ),
        _spec(
            "get_posture_profile",
            _POSTURE_ENTRIES,
            EmptyToolInput,
            PostureProfileProviderView,
            PostureProfileDisplayView,
            read_tools.adapt_get_posture_profile,
        ),
        _spec(
            "get_posture_priorities",
            _POSTURE_ENTRIES,
            EmptyToolInput,
            PosturePrioritiesProviderView,
            PosturePrioritiesDisplayView,
            read_tools.adapt_get_posture_priorities,
        ),
        _spec(
            "get_training_draft",
            _PLAN_ENTRIES,
            EmptyToolInput,
            TrainingDraftProviderView,
            TrainingDraftDisplayView,
            read_tools.adapt_get_training_draft,
        ),
        _spec(
            "get_active_training_plan",
            _PLAN_ENTRIES,
            EmptyToolInput,
            ActivePlanProviderView,
            ActivePlanDisplayView,
            read_tools.adapt_get_active_training_plan,
        ),
        _spec(
            "get_today_training",
            _TRAINING_TODAY_ENTRIES,
            EmptyToolInput,
            TodayTrainingProviderView,
            TodayTrainingDisplayView,
            read_tools.adapt_get_today_training,
        ),
        _spec(
            "get_training_exercise",
            _EXERCISE_ENTRIES,
            GetTrainingExerciseInput,
            TrainingExerciseProviderView,
            TrainingExerciseDisplayView,
            read_tools.adapt_get_training_exercise,
            auth_model=AuthModel.CURRENT_SESSION,
        ),
        _spec(
            "calculate_nutrition_targets",
            _NUTRITION_ENTRIES,
            EmptyToolInput,
            NutritionTargetsProviderView,
            NutritionTargetsDisplayView,
            read_tools.adapt_calculate_nutrition_targets,
        ),
        _spec(
            "convert_targets_to_portions",
            _NUTRITION_ENTRIES,
            EmptyToolInput,
            NutritionPortionsProviderView,
            NutritionPortionsDisplayView,
            read_tools.adapt_convert_targets_to_portions,
        ),
        _spec(
            "validate_nutrition_plan",
            _NUTRITION_ENTRIES,
            EmptyToolInput,
            NutritionValidationProviderView,
            NutritionValidationDisplayView,
            read_tools.adapt_validate_nutrition_plan,
            auth_model=AuthModel.ENTRY_OWNER,
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
        raise AgentError(ResultCode.TOOL_NOT_ALLOWED) from exc


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
        raise AgentError(ResultCode.TOOL_NOT_ALLOWED)
    return spec


def validate_tool_input(name: str, raw: Any) -> BaseModel:
    """Resolve a Tool by name and run its deterministic pre-validator."""
    return get_read_tool(name).validate_input(raw)


__all__ = [
    "ReadToolSpec",
    "READ_TOOLS",
    "is_read_tool",
    "get_read_tool",
    "is_tool_allowed",
    "allowed_tools_for",
    "resolve_tool_for_entry",
    "validate_tool_input",
]
