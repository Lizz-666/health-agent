"""Application service for the authenticated Phase 5 Agent API.

The service owns the live-runtime gate and persistence boundary. Provider and
read-Tool work remains ephemeral until the orchestrator reaches a valid
terminal decision; only then are minimized run/event metadata and an optional
pending proposal committed together. Failure paths rollback and return only a
reviewed result code/template.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import action_tools, persistence
from app.agent.context_resolver import resolve_context
from app.agent.fingerprints import compute_fingerprint
from app.agent.messages import AgentError, ResultCode, is_known_code, render
from app.agent.models import (
    PROPOSAL_CANCELLED,
    PROPOSAL_EXECUTED,
    PROPOSAL_EXPIRED,
    PROPOSAL_PENDING,
)
from app.agent.orchestrator import (
    POLICY_VERSION,
    PROMPT_VERSION,
    OrchestrationFailure,
    OrchestrationResult,
    orchestrate,
)
from app.agent.privacy_gate import PrivacyGateInput, evaluate_privacy_gate
from app.agent.provider import AgentProvider
from app.agent.safety_precheck import route_turn_text
from app.agent.schemas import (
    AgentActionResponse,
    AgentCapabilitiesResponse,
    AgentConsentGrantRequest,
    AgentConsentResponse,
    AgentDataDeletionResponse,
    AgentDisclosureView,
    AgentProposalView,
    AgentToolDisplay,
    AgentTurnResponse,
    TurnInput,
)
from app.core.actor_context import ActorContext
from app.core.config import settings
from app.core.exceptions import AppException
from app.training.context import validate_iana_timezone


CONTEXT_VERSION = "agent-context-v1"
_DISCLOSURE_PATH = Path(__file__).with_name("data") / "agent_disclosure_v1.json"


class _DisclosureDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    disclosure_version: str
    provider_id: str
    provider_name_zh: str
    purpose_code: str
    processing_boundary_code: str
    data_scope_codes: List[str]
    application_retention_code: str
    withdrawal_available: bool
    agent_data_deletion_available: bool
    reviewed_at: date
    official_api_reference: str

    def public_view(self) -> AgentDisclosureView:
        return AgentDisclosureView(
            disclosure_version=self.disclosure_version,
            provider_id=self.provider_id,
            provider_name_zh=self.provider_name_zh,
            purpose_code=self.purpose_code,
            processing_boundary_code=self.processing_boundary_code,
            data_scope_codes=self.data_scope_codes,
            application_retention_code=self.application_retention_code,
            withdrawal_available=self.withdrawal_available,
            agent_data_deletion_available=self.agent_data_deletion_available,
        )


@lru_cache(maxsize=1)
def _load_disclosure() -> Optional[_DisclosureDocument]:
    try:
        raw = json.loads(_DISCLOSURE_PATH.read_text(encoding="utf-8"))
        return _DisclosureDocument.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError):
        return None


@dataclass(frozen=True)
class RuntimeState:
    runtime_enabled: bool
    provider_configured: bool
    audit_key_configured: bool
    provider_id: str
    model_id: str
    disclosure_version: str
    disclosure: Optional[_DisclosureDocument]


def _is_reviewed_dashscope_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname == "dashscope.aliyuncs.com"
        and port in (None, 443)
        and not parsed.username
        and not parsed.password
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
        and parsed.path.rstrip("/") == "/compatible-mode/v1"
    )


def runtime_state() -> RuntimeState:
    disclosure = _load_disclosure()
    provider_id = settings.AGENT_PROVIDER_ID.strip()
    model_id = settings.AGENT_MODEL_ID.strip()
    disclosure_version = settings.AGENT_DISCLOSURE_VERSION.strip()
    base_url = settings.AGENT_PROVIDER_BASE_URL.strip()

    reviewed_configuration = bool(
        disclosure is not None
        and provider_id == "dashscope"
        and provider_id == disclosure.provider_id
        and disclosure_version == disclosure.disclosure_version
        and len(provider_id) <= 60
        and len(model_id) <= 60
        and len(disclosure_version) <= 40
        and disclosure.purpose_code == "agent_cloud_processing"
        and disclosure.withdrawal_available
        and disclosure.agent_data_deletion_available
    )
    provider_configured = bool(
        reviewed_configuration
        and model_id
        and settings.DASHSCOPE_API_KEY.strip()
        and _is_reviewed_dashscope_url(base_url)
        and 0 < settings.AGENT_PROVIDER_CONNECT_TIMEOUT_SECONDS <= 10
        and 0 < settings.AGENT_PROVIDER_READ_TIMEOUT_SECONDS <= 60
        and 1024 <= settings.AGENT_PROVIDER_MAX_RESPONSE_BYTES <= 1024 * 1024
    )
    audit_key = settings.AGENT_AUDIT_HMAC_KEY.strip()
    audit_version = settings.AGENT_AUDIT_HMAC_KEY_VERSION.strip()
    audit_key_configured = bool(
        audit_key
        and audit_version
        and len(audit_key.encode("utf-8")) >= 32
        and len(audit_version) <= 40
        and audit_key != settings.SECRET_KEY.strip()
        and audit_key != "CHANGE-ME-IN-PRODUCTION"
    )
    return RuntimeState(
        runtime_enabled=bool(settings.AGENT_RUNTIME_ENABLED),
        provider_configured=provider_configured,
        audit_key_configured=audit_key_configured,
        provider_id=provider_id,
        model_id=model_id,
        disclosure_version=disclosure_version,
        disclosure=disclosure,
    )


def _privacy_input(state: RuntimeState, consent, *, supported_context: bool):
    return PrivacyGateInput(
        runtime_enabled=state.runtime_enabled,
        provider_id=state.provider_id if state.provider_configured else "",
        model_id=state.model_id if state.provider_configured else "",
        disclosure_version=(
            state.disclosure_version if state.provider_configured else ""
        ),
        consent=consent,
        no_transcript_persistence=True,
        log_redaction_verified=True,
        withdrawal_path_available=True,
        agent_data_deletion_path_available=True,
        non_agent_flows_available_on_failure=True,
        supported_context=supported_context,
        dedicated_audit_hmac_key_configured=state.audit_key_configured,
    )


def _failed_turn(code: str) -> AgentTurnResponse:
    safe_code = code if is_known_code(code) else ResultCode.TOOL_FAILED
    return AgentTurnResponse(
        status="failed",
        result_code=safe_code,
        message=render(safe_code),
    )


async def get_capabilities(
    db: AsyncSession, user_id: str
) -> AgentCapabilitiesResponse:
    state = runtime_state()
    consent = await persistence.active_consent(db, user_id)

    if not state.runtime_enabled:
        code = ResultCode.DISABLED
        available = False
    elif not state.provider_configured or not state.audit_key_configured:
        code = ResultCode.PRIVACY_GATE_BLOCKED
        available = False
    else:
        decision = evaluate_privacy_gate(
            _privacy_input(state, consent, supported_context=True)
        )
        code = decision.blocking_code or ResultCode.AVAILABLE
        available = decision.passed

    disclosure_view = None
    if (
        state.disclosure is not None
        and state.provider_id == state.disclosure.provider_id
        and state.disclosure_version == state.disclosure.disclosure_version
    ):
        disclosure_view = state.disclosure.public_view()

    return AgentCapabilitiesResponse(
        runtime_enabled=state.runtime_enabled,
        provider_configured=state.provider_configured,
        provider_id=state.provider_id or None,
        model_id=state.model_id or None,
        disclosure_version=state.disclosure_version or None,
        consent_active=consent.active,
        available=available,
        result_code=code,
        message=render(code),
        disclosure=disclosure_view,
    )


async def grant_cloud_consent(
    db: AsyncSession, user_id: str, request: AgentConsentGrantRequest
) -> AgentConsentResponse:
    state = runtime_state()
    if not state.provider_configured or state.disclosure is None:
        raise AppException(
            409,
            render(ResultCode.PRIVACY_GATE_BLOCKED),
            ResultCode.PRIVACY_GATE_BLOCKED,
        )
    result = await persistence.grant_consent(
        db,
        user_id,
        accepted_provider_id=request.accepted_provider_id,
        accepted_disclosure_version=request.accepted_disclosure_version,
        current_provider_id=state.provider_id,
        current_disclosure_version=state.disclosure_version,
        idempotency_key=request.idempotency_key,
    )
    return AgentConsentResponse(
        consent_id=result.consent_id,
        sequence_no=result.sequence_no,
        status=result.status,
        replayed=result.replayed,
    )


async def withdraw_cloud_consent(
    db: AsyncSession, user_id: str, idempotency_key: str
) -> AgentConsentResponse:
    result = await persistence.withdraw_consent(
        db, user_id, idempotency_key=idempotency_key
    )
    return AgentConsentResponse(
        consent_id=result.consent_id,
        sequence_no=result.sequence_no,
        status=result.status,
        replayed=result.replayed,
    )


async def delete_current_agent_data(
    db: AsyncSession, user_id: str
) -> AgentDataDeletionResponse:
    result = await persistence.delete_agent_data(db, user_id)
    return AgentDataDeletionResponse(
        consents_deleted=result.consents_deleted,
        runs_deleted=result.runs_deleted,
        tool_events_deleted=result.tool_events_deleted,
        proposals_deleted=result.proposals_deleted,
        idempotency_deleted=result.idempotency_deleted,
    )


async def process_turn(
    db: AsyncSession,
    actor: ActorContext,
    turn: TurnInput,
    provider: AgentProvider,
    *,
    now: Optional[datetime] = None,
) -> AgentTurnResponse:
    now = now or datetime.now(timezone.utc)

    # This check deliberately precedes even idempotency and ownership reads.
    if not validate_iana_timezone(turn.iana_timezone):
        return _failed_turn(ResultCode.INVALID_TIMEZONE)

    prior = await persistence.load_run_for_client_turn(
        db, actor.user_id, turn.client_turn_id
    )
    if prior is not None:
        response = await _replay_turn(db, actor.user_id, prior)
        await db.rollback()
        return response

    safety = route_turn_text(turn.message)
    if safety.routed:
        await db.rollback()
        return AgentTurnResponse(
            status="safety_routed",
            result_code=safety.result_code,
            message=render(safety.result_code),
        )

    state = runtime_state()
    if not state.runtime_enabled:
        await db.rollback()
        return _failed_turn(ResultCode.DISABLED)
    if not state.provider_configured or not state.audit_key_configured:
        await db.rollback()
        return _failed_turn(ResultCode.PRIVACY_GATE_BLOCKED)

    consent = await persistence.active_consent(db, actor.user_id)
    gate = evaluate_privacy_gate(
        _privacy_input(state, consent, supported_context=True)
    )
    if not gate.passed:
        await db.rollback()
        return _failed_turn(gate.blocking_code or ResultCode.PRIVACY_GATE_BLOCKED)

    try:
        context = await resolve_context(
            db,
            actor,
            entry_type=turn.entry_type,
            entity_id=turn.entity_id,
            iana_timezone=turn.iana_timezone,
            now=now,
        )
        context_fingerprint = compute_fingerprint(context.fingerprint_payload)
        result = await orchestrate(db, actor, turn, context, provider, now=now)
    except AgentError as exc:
        await db.rollback()
        return _failed_turn(exc.code)
    except OrchestrationFailure as exc:
        await db.rollback()
        return _failed_turn(exc.code)
    except AppException as exc:
        await db.rollback()
        return _failed_turn(exc.code)
    except Exception:
        await db.rollback()
        return _failed_turn(ResultCode.TOOL_FAILED)

    try:
        # Cleanup and key-rotation scrubbing are request-bound only after a
        # successful provider terminal. Provider failures therefore leave no
        # persistence mutation of any kind.
        await persistence.cleanup_expired_runs(db, now=now)
        await persistence.scrub_pending_on_key_change(
            db, actor.user_id, context_fingerprint.key_version, now=now
        )
        return await _persist_terminal(
            db,
            actor.user_id,
            turn,
            result,
            context_fingerprint.value,
            context_fingerprint.key_version,
            state,
            now,
        )
    except IntegrityError:
        await db.rollback()
        prior = await persistence.load_run_for_client_turn(
            db, actor.user_id, turn.client_turn_id
        )
        if prior is None:
            await db.rollback()
            return _failed_turn(ResultCode.TOOL_FAILED)
        response = await _replay_turn(db, actor.user_id, prior)
        await db.rollback()
        return response
    except AgentError as exc:
        await db.rollback()
        return _failed_turn(exc.code)
    except AppException as exc:
        await db.rollback()
        return _failed_turn(exc.code)
    except Exception:
        await db.rollback()
        return _failed_turn(ResultCode.TOOL_FAILED)


async def _persist_terminal(
    db: AsyncSession,
    user_id: str,
    turn: TurnInput,
    result: OrchestrationResult,
    context_fingerprint: str,
    fingerprint_key_version: str,
    state: RuntimeState,
    now: datetime,
) -> AgentTurnResponse:
    status = "proposal_pending" if result.status == "proposal" else result.status
    tool_count = result.read_calls + (1 if result.proposal is not None else 0)
    recorded = await persistence.record_run(
        db,
        user_id,
        client_turn_id=turn.client_turn_id,
        entry_type=turn.entry_type.value,
        intent_code=result.result_code,
        context_fingerprint=context_fingerprint,
        fingerprint_key_version=fingerprint_key_version,
        prompt_version=PROMPT_VERSION,
        provider_id=state.provider_id,
        model_version=result.model_version or state.model_id,
        policy_version=POLICY_VERSION,
        status=status,
        result_code=result.result_code,
        tool_call_count=tool_count,
        started_at=now,
        now=now,
        commit=False,
    )
    if not recorded.created:
        return await _replay_turn(db, user_id, recorded.run)

    recorded.run.completed_at = now
    display_data: List[AgentToolDisplay] = []
    for trace in result.display_results:
        await persistence.record_tool_event(
            db,
            run_id=recorded.run.run_id,
            user_id=user_id,
            tool_name=trace.result.tool_name,
            side_effect_class="read",
            status="completed",
            request_fingerprint=trace.request_fingerprint.value,
            fingerprint_key_version=trace.request_fingerprint.key_version,
            policy_version=POLICY_VERSION,
            context_version=CONTEXT_VERSION,
            result_code=ResultCode.READ_OK,
        )
        display_data.append(
            AgentToolDisplay(
                tool_name=trace.result.tool_name,
                data=trace.display_view.model_dump(mode="json", exclude_none=True),
            )
        )

    proposal_view = None
    if result.proposal is not None:
        candidate = result.proposal
        await persistence.record_tool_event(
            db,
            run_id=recorded.run.run_id,
            user_id=user_id,
            tool_name=candidate.tool_name,
            side_effect_class="proposal",
            status=PROPOSAL_PENDING,
            request_fingerprint=candidate.arguments_fingerprint.value,
            fingerprint_key_version=candidate.arguments_fingerprint.key_version,
            policy_version=POLICY_VERSION,
            context_version=CONTEXT_VERSION,
            result_code=ResultCode.ACTION_CONFIRMATION_REQUIRED,
        )
        proposal = await persistence.create_proposal(
            db,
            run_id=recorded.run.run_id,
            user_id=user_id,
            tool_name=candidate.tool_name,
            arguments_json=candidate.arguments.model_dump(mode="json"),
            arguments_hash=candidate.arguments_fingerprint.value,
            iana_timezone=turn.iana_timezone,
            context_fingerprint=candidate.context_fingerprint.value,
            fingerprint_key_version=candidate.arguments_fingerprint.key_version,
            context_version=CONTEXT_VERSION,
            policy_version=POLICY_VERSION,
            now=now,
            commit=False,
        )
        proposal_view = AgentProposalView(
            proposal_id=proposal.proposal_id,
            action=candidate.tool_name,
            diff=candidate.diff.model_dump(mode="json", exclude_none=True),
            expires_at=proposal.expires_at,
        )

    response = AgentTurnResponse(
        run_id=recorded.run.run_id,
        status=status,
        result_code=result.result_code,
        message=render(result.result_code),
        display_data=display_data,
        proposal=proposal_view,
    )
    await db.commit()
    return response


async def _replay_turn(db: AsyncSession, user_id: str, run) -> AgentTurnResponse:
    proposal = await persistence.load_proposal_for_run(db, user_id, run.run_id)
    proposal_view = None
    code = run.result_code or ResultCode.OUTPUT_INVALID
    if proposal is not None and proposal.status == PROPOSAL_PENDING:
        proposal, expired_now = await persistence.load_pending_owned_proposal(
            db, user_id, proposal.proposal_id
        )
        if expired_now:
            await db.commit()
            code = ResultCode.ACTION_EXPIRED
    if proposal is not None and proposal.status == PROPOSAL_PENDING:
        try:
            arguments = action_tools.validate_arguments(
                proposal.tool_name, proposal.arguments_json
            )
            diff = action_tools.build_diff(proposal.tool_name, arguments)
            proposal_view = AgentProposalView(
                proposal_id=proposal.proposal_id,
                action=proposal.tool_name,
                diff=diff.model_dump(mode="json", exclude_none=True),
                expires_at=proposal.expires_at,
            )
        except AgentError:
            proposal_view = None
            code = ResultCode.OUTPUT_INVALID
    elif proposal is not None:
        code = _action_result_code(proposal.status, proposal.result_code)
    if not is_known_code(code):
        code = ResultCode.OUTPUT_INVALID
    return AgentTurnResponse(
        run_id=run.run_id,
        status="replayed",
        message=None,
        result_code=code,
        proposal=proposal_view,
        replayed=True,
    )


def _action_result_code(status: str, stored_code: Optional[str]) -> str:
    if status == PROPOSAL_EXECUTED or (
        status == "replayed" and stored_code and not is_known_code(stored_code)
    ):
        return ResultCode.ACTION_EXECUTED
    if status == PROPOSAL_EXPIRED:
        return ResultCode.ACTION_EXPIRED
    if status == PROPOSAL_CANCELLED:
        return ResultCode.ACTION_CANCELLED
    if stored_code and is_known_code(stored_code):
        return stored_code
    return ResultCode.ACTION_INVALIDATED


async def confirm_action(
    db: AsyncSession,
    user_id: str,
    proposal_id,
    *,
    idempotency_key: str,
) -> AgentActionResponse:
    state = runtime_state()
    if not state.runtime_enabled:
        return AgentActionResponse(
            proposal_id=proposal_id,
            status="blocked",
            result_code=ResultCode.DISABLED,
            message=render(ResultCode.DISABLED),
        )
    if not state.provider_configured or not state.audit_key_configured:
        return AgentActionResponse(
            proposal_id=proposal_id,
            status="blocked",
            result_code=ResultCode.PRIVACY_GATE_BLOCKED,
            message=render(ResultCode.PRIVACY_GATE_BLOCKED),
        )
    consent = await persistence.active_consent(db, user_id)
    gate = evaluate_privacy_gate(
        _privacy_input(state, consent, supported_context=True)
    )
    if not gate.passed:
        code = gate.blocking_code or ResultCode.PRIVACY_GATE_BLOCKED
        await db.rollback()
        return AgentActionResponse(
            proposal_id=proposal_id,
            status="blocked",
            result_code=code,
            message=render(code),
        )

    result = await persistence.confirm_proposal(
        db,
        user_id,
        proposal_id,
        idempotency_key=idempotency_key,
    )
    code = _action_result_code(result.status, result.result_code)
    return AgentActionResponse(
        proposal_id=result.proposal_id,
        status=result.status,
        result_code=code,
        result_ref=result.result_ref,
        message=render(code),
    )


async def cancel_action(
    db: AsyncSession, user_id: str, proposal_id
) -> AgentActionResponse:
    proposal = await persistence.cancel_proposal(db, user_id, proposal_id)
    return AgentActionResponse(
        proposal_id=proposal.proposal_id,
        status=proposal.status,
        result_code=ResultCode.ACTION_CANCELLED,
        message=render(ResultCode.ACTION_CANCELLED),
    )


__all__ = [
    "CONTEXT_VERSION",
    "RuntimeState",
    "runtime_state",
    "get_capabilities",
    "grant_cloud_consent",
    "withdraw_cloud_consent",
    "delete_current_agent_data",
    "process_turn",
    "confirm_action",
    "cancel_action",
]
