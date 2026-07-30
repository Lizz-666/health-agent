"""Bounded provider decision loop over the static Agent Tool boundary.

This module performs no persistence and no domain write. Read results remain in
memory; a write decision is only prepared and returned as a typed proposal
candidate. ``service.py`` persists audit/proposal metadata only after a valid
terminal result, so provider/Tool failures cannot leave partial Agent state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import action_tools, tool_registry
from app.agent.fingerprints import AgentFingerprint, compute_fingerprint
from app.agent.messages import AgentError, ResultCode, is_known_code
from app.agent.provider import (
    AGENT_OUTPUT_INVALID,
    ActionProposalDecision,
    AgentProvider,
    AnswerDecision,
    ClarifyDecision,
    ProviderFailure,
    ProviderReadResult,
    ProviderRequest,
    ProviderToolDefinition,
    ReadToolCallDecision,
    UnsupportedDecision,
)
from app.agent.schemas import (
    CREATE_WEIGHT_RECORD,
    GENERATE_TRAINING_PLAN_DRAFT,
    RECORD_TRAINING_FEEDBACK,
    SUBSTITUTE_TODAY_EXERCISE,
    UPSERT_TODAY_CHECKIN,
    CreateWeightRecordArguments,
    EntryType,
    GenerateTrainingPlanDraftArguments,
    ReadToolResult,
    RecordTrainingFeedbackArguments,
    ResolvedContext,
    SubstituteTodayExerciseArguments,
    TurnInput,
    UpsertTodayCheckinArguments,
    WriteActionArguments,
    WriteActionDiff,
)
from app.core.actor_context import ActorContext
from app.core.exceptions import AppException


PROMPT_VERSION = "agent-v1"
POLICY_VERSION = "agent-policy-v1"
MAX_PROVIDER_DECISIONS = 4
MAX_READ_CALLS = 4
MAX_PROPOSALS = 1

_PROMPT_PATH = Path(__file__).with_name("prompts") / "agent_v1.txt"

_ANSWER_CODES = frozenset({ResultCode.ANSWER_READY})
_QUESTION_CODES = frozenset({ResultCode.CLARIFY_REQUIRED})
_UNSUPPORTED_CODES = frozenset(
    {
        ResultCode.UNSUPPORTED_SCOPE,
        ResultCode.UNSUPPORTED_MEDICAL,
        ResultCode.UNSUPPORTED_NUTRITION,
    }
)
_MISSING_FIELD_CODES = frozenset(
    {
        "fitness_goal",
        "weekly_frequency",
        "session_duration_minutes",
        "equipment",
        "today_checkin",
        "weight_value",
        "training_outcome",
        "replacement_exercise",
    }
)

_WRITE_MODELS: Dict[str, type] = {
    UPSERT_TODAY_CHECKIN: UpsertTodayCheckinArguments,
    CREATE_WEIGHT_RECORD: CreateWeightRecordArguments,
    GENERATE_TRAINING_PLAN_DRAFT: GenerateTrainingPlanDraftArguments,
    SUBSTITUTE_TODAY_EXERCISE: SubstituteTodayExerciseArguments,
    RECORD_TRAINING_FEEDBACK: RecordTrainingFeedbackArguments,
}
_ENTRY_WRITES = {
    EntryType.general: frozenset(_WRITE_MODELS),
    EntryType.health_profile: frozenset(
        {UPSERT_TODAY_CHECKIN, CREATE_WEIGHT_RECORD}
    ),
    EntryType.posture_issue: frozenset(),
    EntryType.training_plan: frozenset({GENERATE_TRAINING_PLAN_DRAFT}),
    EntryType.training_session: frozenset(
        {SUBSTITUTE_TODAY_EXERCISE, RECORD_TRAINING_FEEDBACK}
    ),
    EntryType.training_exercise: frozenset(
        {SUBSTITUTE_TODAY_EXERCISE, RECORD_TRAINING_FEEDBACK}
    ),
}


class OrchestrationFailure(Exception):
    """Redacted deterministic failure; no provider/body detail is retained."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ReadTrace:
    result: ReadToolResult
    request_fingerprint: AgentFingerprint

    @property
    def display_view(self):
        return self.result.display_view


@dataclass(frozen=True)
class ProposalCandidate:
    tool_name: str
    arguments: WriteActionArguments
    arguments_fingerprint: AgentFingerprint
    context_fingerprint: AgentFingerprint
    diff: WriteActionDiff


@dataclass(frozen=True)
class OrchestrationResult:
    status: str
    result_code: str
    provider_decisions: int
    read_calls: int
    display_results: Tuple[ReadTrace, ...]
    proposal: Optional[ProposalCandidate] = None
    model_version: Optional[str] = None


def _load_prompt() -> str:
    text = _PROMPT_PATH.read_text(encoding="utf-8").strip()
    if not text:
        raise OrchestrationFailure(AGENT_OUTPUT_INVALID)
    return text


def _schema(model: type) -> dict:
    value = model.model_json_schema()
    value["additionalProperties"] = False
    return value


def provider_tools_for(context: ResolvedContext) -> List[ProviderToolDefinition]:
    """Return the closed server-owned Tool schema set for this entry."""
    definitions: List[ProviderToolDefinition] = []
    for name in context.allowed_tools:
        spec = tool_registry.resolve_tool_for_entry(name, context.entry_type)
        definitions.append(
            ProviderToolDefinition(
                name=name,
                side_effect="read",
                parameters=_schema(spec.input_model),
            )
        )
    for name in sorted(_ENTRY_WRITES[context.entry_type]):
        definitions.append(
            ProviderToolDefinition(
                name=name,
                side_effect="proposal",
                parameters=_schema(_WRITE_MODELS[name]),
            )
        )
    return definitions


async def orchestrate(
    db: AsyncSession,
    actor: ActorContext,
    turn: TurnInput,
    context: ResolvedContext,
    provider: AgentProvider,
    *,
    now: Optional[datetime] = None,
) -> OrchestrationResult:
    """Run at most four sequential provider decisions and four read Tools."""
    now = now or datetime.now(timezone.utc)
    read_traces: List[ReadTrace] = []
    provider_results: List[ProviderReadResult] = []
    tool_definitions = provider_tools_for(context)

    for decision_number in range(1, MAX_PROVIDER_DECISIONS + 1):
        request = ProviderRequest(
            prompt_version=PROMPT_VERSION,
            system_prompt=_load_prompt(),
            user_message=turn.message,
            context=context.provider_context.model_dump(
                mode="json", exclude_none=True
            ),
            allowed_tools=tool_definitions,
            read_results=provider_results,
        )
        try:
            decision = await provider.decide(request)
        except ProviderFailure as exc:
            raise OrchestrationFailure(exc.code) from exc
        except Exception as exc:
            raise OrchestrationFailure(ResultCode.PROVIDER_UNAVAILABLE) from exc

        if isinstance(decision, ReadToolCallDecision):
            if len(read_traces) >= MAX_READ_CALLS:
                raise OrchestrationFailure(ResultCode.STEP_LIMIT)
            try:
                result, fingerprint = await _execute_read_tool(
                    db, actor, context, decision
                )
            except AgentError as exc:
                raise OrchestrationFailure(exc.code) from exc
            except AppException as exc:
                code = exc.code if is_known_code(exc.code) else ResultCode.TOOL_FAILED
                raise OrchestrationFailure(code) from exc
            except Exception as exc:
                raise OrchestrationFailure(ResultCode.TOOL_FAILED) from exc
            trace = ReadTrace(result=result, request_fingerprint=fingerprint)
            read_traces.append(trace)
            provider_results.append(
                ProviderReadResult(
                    tool_name=result.tool_name,
                    provider_view=result.provider_view.model_dump(
                        mode="json", exclude_none=True
                    ),
                )
            )
            if decision_number == MAX_PROVIDER_DECISIONS:
                raise OrchestrationFailure(ResultCode.STEP_LIMIT)
            continue

        if isinstance(decision, ActionProposalDecision):
            proposal = await _prepare_proposal(
                db, actor, context, decision, now=now
            )
            return OrchestrationResult(
                status="proposal",
                result_code=ResultCode.ACTION_CONFIRMATION_REQUIRED,
                provider_decisions=decision_number,
                read_calls=len(read_traces),
                display_results=tuple(read_traces),
                proposal=proposal,
                model_version=provider.last_model_version,
            )

        if isinstance(decision, AnswerDecision):
            _validate_answer(decision, read_traces)
            return _terminal_result(
                "answer", decision.message_code, decision_number,
                read_traces, provider.last_model_version,
            )
        if isinstance(decision, ClarifyDecision):
            _validate_clarify(decision)
            return _terminal_result(
                "clarify", decision.question_code, decision_number,
                read_traces, provider.last_model_version,
            )
        if isinstance(decision, UnsupportedDecision):
            if decision.message_code not in _UNSUPPORTED_CODES:
                raise OrchestrationFailure(AGENT_OUTPUT_INVALID)
            return _terminal_result(
                "unsupported", decision.message_code, decision_number,
                read_traces, provider.last_model_version,
            )
        raise OrchestrationFailure(AGENT_OUTPUT_INVALID)

    raise OrchestrationFailure(ResultCode.STEP_LIMIT)


def _terminal_result(
    status: str,
    code: str,
    decision_count: int,
    traces: List[ReadTrace],
    model_version: Optional[str],
) -> OrchestrationResult:
    return OrchestrationResult(
        status=status,
        result_code=code,
        provider_decisions=decision_count,
        read_calls=len(traces),
        display_results=tuple(traces),
        model_version=model_version,
    )


def _validate_answer(
    decision: AnswerDecision, traces: List[ReadTrace]
) -> None:
    if decision.message_code not in _ANSWER_CODES:
        raise OrchestrationFailure(AGENT_OUTPUT_INVALID)
    allowed_refs = {"context"} | {trace.result.tool_name for trace in traces}
    if any(ref not in allowed_refs for ref in decision.references):
        raise OrchestrationFailure(AGENT_OUTPUT_INVALID)


def _validate_clarify(decision: ClarifyDecision) -> None:
    if decision.question_code not in _QUESTION_CODES:
        raise OrchestrationFailure(AGENT_OUTPUT_INVALID)
    if any(field not in _MISSING_FIELD_CODES for field in decision.missing_fields):
        raise OrchestrationFailure(AGENT_OUTPUT_INVALID)


async def _prepare_proposal(
    db: AsyncSession,
    actor: ActorContext,
    context: ResolvedContext,
    decision: ActionProposalDecision,
    *,
    now: datetime,
) -> ProposalCandidate:
    if decision.tool_name not in _ENTRY_WRITES[context.entry_type]:
        raise OrchestrationFailure(ResultCode.TOOL_NOT_ALLOWED)
    try:
        arguments = action_tools.validate_arguments(
            decision.tool_name, decision.arguments
        )
        prepared = await action_tools.prepare(
            db,
            decision.tool_name,
            arguments,
            actor.user_id,
            iana_timezone=context.iana_timezone,
            now=now,
        )
        arguments_fp = action_tools.compute_arguments_fingerprint(arguments)
        context_fp = action_tools.compute_context_fingerprint(
            prepared.context_fingerprint_payload
        )
        diff = action_tools.build_diff(
            decision.tool_name,
            arguments,
            session_id=context.provider_context.session_id,
        )
    except AgentError as exc:
        raise OrchestrationFailure(exc.code) from exc
    except AppException as exc:
        code = exc.code if is_known_code(exc.code) else ResultCode.CONTEXT_STALE
        raise OrchestrationFailure(code) from exc
    except Exception as exc:
        raise OrchestrationFailure(ResultCode.TOOL_FAILED) from exc
    return ProposalCandidate(
        tool_name=decision.tool_name,
        arguments=arguments,
        arguments_fingerprint=arguments_fp,
        context_fingerprint=context_fp,
        diff=diff,
    )


async def _execute_read_tool(
    db: AsyncSession,
    actor: ActorContext,
    context: ResolvedContext,
    decision: ReadToolCallDecision,
) -> Tuple[ReadToolResult, AgentFingerprint]:
    spec = tool_registry.resolve_tool_for_entry(
        decision.tool_name, context.entry_type
    )
    arguments: BaseModel = spec.validate_input(decision.arguments)
    name = decision.tool_name

    if name in {
        "get_health_profile_summary",
        "get_weight_trend_summary",
        "get_posture_profile",
        "get_posture_priorities",
        "get_training_draft",
        "get_active_training_plan",
    }:
        result = await spec.adapter(db, actor)
    elif name == "get_today_checkin":
        result = await spec.adapter(db, actor, context.current_local_date)
    elif name == "list_posture_issues":
        result = spec.adapter(arguments.category)
    elif name == "get_posture_issue":
        if context.entity_id is not None and arguments.issue_id != context.entity_id:
            raise AgentError(ResultCode.ENTITY_NOT_FOUND)
        result = spec.adapter(arguments.issue_id)
    elif name == "guide_posture_self_test":
        if context.entity_id is None:
            raise AgentError(ResultCode.ENTITY_NOT_FOUND)
        result = await spec.adapter(db, actor, context.entity_id)
    elif name == "get_today_training":
        result = await spec.adapter(db, actor, context.iana_timezone)
    elif name == "get_training_exercise":
        result = await spec.adapter(
            db, actor, context.iana_timezone, arguments.exercise_id
        )
    else:
        raise AgentError(ResultCode.TOOL_NOT_ALLOWED)

    validated = spec.validate_output(result)
    fingerprint = compute_fingerprint(
        {
            "tool_name": name,
            "arguments": arguments.model_dump(mode="json"),
        }
    )
    return validated, fingerprint


__all__ = [
    "PROMPT_VERSION",
    "POLICY_VERSION",
    "MAX_PROVIDER_DECISIONS",
    "MAX_READ_CALLS",
    "MAX_PROPOSALS",
    "OrchestrationFailure",
    "ReadTrace",
    "ProposalCandidate",
    "OrchestrationResult",
    "provider_tools_for",
    "orchestrate",
]
