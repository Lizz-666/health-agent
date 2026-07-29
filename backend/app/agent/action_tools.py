"""Phase 5 Agent confirmed write adapters (Task 3).

A server-side CLOSED registry for the five allowed write actions. It is
deliberately separate from the provider-exposed read registry: write Tool names
are never offered to the model, and the model is never given confirm/cancel/
consent/delete authority (spec Tool Registry And Permission Matrix; ADR-0003).

Each action binds:
- a strict (``extra="forbid``) typed Arguments model with NO actor/user/time/
  policy/consent/fingerprint fields and NO free text;
- a deterministic typed Diff rendered server-side (never provider prose);
- a ``prepare`` step that re-runs the LATEST deterministic domain validation
  against current structured data and yields a context-fingerprint payload plus
  a deferred transaction-neutral executor (flush only, no commit); and
- the domain idempotency inputs (training only).

``confirm_proposal`` (in ``app.agent.persistence``) calls ``prepare``, compares
the recomputed context fingerprint against the stored proposal, and only then
runs the executor inside one atomic unit of work. No write occurs before
confirmation; exactly one occurs after an idempotent confirmation.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import schemas as S
from app.agent.fingerprints import AgentFingerprint, compute_fingerprint
from app.agent.messages import AgentError, ResultCode
from app.core.exceptions import AppException
from app.health.models import DailyCheckIn
from app.health.schemas import CheckInCreate, WeightRecordCreate
from app.health.service import (
    create_weight_record_core,
    get_profile_result,
    upsert_today_core,
)
from app.training import persistence as P
from app.training import service as training_service

# Domain idempotency operations reused for the two-layer training contract.
_DOMAIN_OP = {
    S.GENERATE_TRAINING_PLAN_DRAFT: P.OP_PLAN_GENERATE,
    S.SUBSTITUTE_TODAY_EXERCISE: P.OP_SESSION_SUBSTITUTE,
    S.RECORD_TRAINING_FEEDBACK: P.OP_SESSION_FEEDBACK,
}

SAFETY_SIGNAL_ROUTE_CODE = "agent_safety_signal_route_required"


@dataclass(frozen=True)
class ExecutionResult:
    """The outcome of running an action's transaction-neutral executor."""

    result_ref: str
    result_code: str = "executed"
    # Domain idempotency result_ref (training two-layer); None for health.
    domain_result_ref: Optional[str] = None


@dataclass(frozen=True)
class PreparedAction:
    """Result of ``prepare``: latest-validated inputs ready to confirm.

    ``context_fingerprint_payload`` is HMAC'd by the caller and compared with
    the proposal's stored fingerprint; a mismatch means the context the user saw
    has changed and the proposal is stale. ``execute`` performs the flush-only
    domain side effect (NO commit) and must be called inside the caller's unit
    of work. ``domain_operation``/``domain_request_hash`` carry the training
    domain idempotency inputs (empty for health, which has no domain layer).
    """

    context_fingerprint_payload: Mapping[str, Any]
    execute: Callable[[], ExecutionResult]
    domain_operation: Optional[str] = None
    domain_request_hash: str = ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def validate_arguments(name: str, raw: Any) -> S.WriteActionArguments:
    """Validate typed write-action arguments; reject unknown names/fields."""
    model = _ARGUMENTS_MODELS.get(name)
    if model is None:
        raise AgentError(ResultCode.TOOL_NOT_ALLOWED)
    try:
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise TypeError("action arguments must be an object")
        return model.model_validate(raw)
    except (TypeError, ValueError) as exc:
        raise AgentError(ResultCode.TOOL_NOT_ALLOWED) from exc


def compute_arguments_fingerprint(arguments: S.WriteActionArguments) -> AgentFingerprint:
    """Keyed HMAC over the typed arguments (no free text; bounded values only)."""
    return compute_fingerprint(arguments.model_dump(mode="json"))


def is_write_action(name: str) -> bool:
    return name in _ARGUMENTS_MODELS


# --------------------------------------------------------------------------- #
# Diff builders (deterministic, server-rendered, no provider free text)       #
# --------------------------------------------------------------------------- #


def build_diff(name: str, arguments: S.WriteActionArguments, *, session_id: Optional[str] = None) -> S.WriteActionDiff:
    """Render the deterministic typed diff for an action from its arguments."""
    if name == S.UPSERT_TODAY_CHECKIN:
        return S.UpsertTodayCheckinDiff(
            action=name, summary_code="agent_checkin_diff", local_date=arguments.local_date
        )
    if name == S.CREATE_WEIGHT_RECORD:
        return S.CreateWeightRecordDiff(
            action=name, summary_code="agent_weight_diff",
            recorded_at=arguments.recorded_at, weight_kg=arguments.weight_kg,
        )
    if name == S.GENERATE_TRAINING_PLAN_DRAFT:
        return S.GenerateTrainingPlanDraftDiff(
            action=name, summary_code="agent_draft_diff",
            fitness_goal=arguments.fitness_goal,
            weekly_frequency=arguments.weekly_frequency,
            session_duration_minutes=arguments.session_duration_minutes,
        )
    if name == S.SUBSTITUTE_TODAY_EXERCISE:
        return S.SubstituteTodayExerciseDiff(
            action=name, summary_code="agent_substitution_diff",
            session_id=session_id,
            original_exercise_id=arguments.original_exercise_id,
            replacement_exercise_id=arguments.replacement_exercise_id,
        )
    if name == S.RECORD_TRAINING_FEEDBACK:
        return S.RecordTrainingFeedbackDiff(
            action=name, summary_code="agent_feedback_diff",
            session_id=session_id, outcome_state=arguments.outcome_state,
        )
    raise AgentError(ResultCode.TOOL_NOT_ALLOWED)


# --------------------------------------------------------------------------- #
# Prepare (latest validation + fingerprint payload + deferred executor)       #
# --------------------------------------------------------------------------- #


async def _today_profile_payload(db: AsyncSession, user_id: str) -> Dict[str, Any]:
    profile = await get_profile_result(db, user_id)
    data = profile.profile
    readiness = profile.readiness
    return {
        "profile_configured": profile.configured,
        "profile_version": data.version if data else 0,
        "readiness": readiness.readiness,
        "restricted": bool(readiness.restricted_reason),
    }


async def _prepare_upsert_today_checkin(
    db: AsyncSession, user_id: str, args: S.UpsertTodayCheckinArguments,
    iana_timezone: str, now: datetime,
) -> PreparedAction:
    """Latest-data gate: an existing same-day ``abnormal_pain=true`` check-in is
    a safety signal that must NOT be overwritten or downgraded (spec Tool
    Registry). The ordinary Agent check-in is ``abnormal_pain=false`` with no
    pain fields."""
    user_uuid = uuid.UUID(user_id)
    existing = (
        await db.execute(
            select(DailyCheckIn).where(
                DailyCheckIn.user_id == user_uuid,
                DailyCheckIn.local_date == args.local_date,
            )
        )
    ).scalar_one_or_none()
    existing_abnormal = bool(existing is not None and existing.abnormal_pain)
    existing_risk = existing.risk_summary if existing is not None else None

    profile_payload = await _today_profile_payload(db, user_id)
    payload = {
        "action": S.UPSERT_TODAY_CHECKIN,
        "local_date": args.local_date.isoformat(),
        "existing_abnormal_pain": existing_abnormal,
        "existing_risk_summary": existing_risk,
        **profile_payload,
    }

    data = CheckInCreate(
        local_date=args.local_date,
        sleep_quality=args.sleep_quality,
        energy=args.energy,
        muscle_soreness=args.muscle_soreness,
        available_time=args.available_time,
        daily_status=args.daily_status,
        abnormal_pain=False,
        pain_followup=None,
    )

    async def _execute_async() -> ExecutionResult:
        # Latest-data gate at execution time: an existing same-day
        # abnormal_pain=true check-in is a safety signal that must NOT be
        # overwritten or downgraded; route to the dedicated safety flow.
        current = (
            await db.execute(
                select(DailyCheckIn).where(
                    DailyCheckIn.user_id == user_uuid,
                    DailyCheckIn.local_date == args.local_date,
                )
            )
        ).scalar_one_or_none()
        if current is not None and current.abnormal_pain:
            raise AppException(
                409, "当日已存在异常疼痛记录，请通过安全流程处理", SAFETY_SIGNAL_ROUTE_CODE
            )
        # upsert_today_core flushes + refreshes (no commit). It cannot set
        # abnormal_pain=true (forced false) and carries no pain fields.
        response = await upsert_today_core(db, user_id, data)
        return ExecutionResult(result_ref=str(response.id))

    return PreparedAction(
        context_fingerprint_payload=payload,
        execute=_execute_async,  # type: ignore[arg-type]
        domain_operation=None,
        domain_request_hash="",
    )


async def _prepare_create_weight_record(
    db: AsyncSession, user_id: str, args: S.CreateWeightRecordArguments,
    iana_timezone: str, now: datetime,
) -> PreparedAction:
    profile_payload = await _today_profile_payload(db, user_id)
    payload = {
        "action": S.CREATE_WEIGHT_RECORD,
        **profile_payload,
    }
    # note is forced null and is NOT a field on the arguments.
    data = WeightRecordCreate(recorded_at=args.recorded_at, weight_kg=args.weight_kg, note=None)

    async def _execute_async() -> ExecutionResult:
        response = await create_weight_record_core(db, user_id, data)
        return ExecutionResult(result_ref=str(response.id))

    return PreparedAction(
        context_fingerprint_payload=payload,
        execute=_execute_async,  # type: ignore[arg-type]
        domain_operation=None,
        domain_request_hash="",
    )


async def _prepare_generate_training_plan_draft(
    db: AsyncSession, user_id: str, args: S.GenerateTrainingPlanDraftArguments,
    iana_timezone: str, now: datetime,
) -> PreparedAction:
    ev = await training_service.evaluate_draft_request(
        db, user_id,
        fitness_goal=args.fitness_goal,
        weekly_frequency=args.weekly_frequency,
        session_duration_minutes=args.session_duration_minutes,
        equipment_bodyweight=args.equipment_bodyweight,
        equipment_resistance_band=args.equipment_resistance_band,
        iana_timezone=iana_timezone,
        now=now,
    )
    payload = {
        "action": S.GENERATE_TRAINING_PLAN_DRAFT,
        "decision_fingerprint": ev.decision_fingerprint,
        "fitness_goal": args.fitness_goal,
        "weekly_frequency": args.weekly_frequency,
        "session_duration_minutes": args.session_duration_minutes,
    }

    async def _execute_async() -> ExecutionResult:
        plan_version_id = await P._persist_draft_core(
            db, user_id,
            draft=ev.draft,
            weekly_frequency=ev.weekly_frequency,
            session_duration_minutes=ev.session_duration_minutes,
            decision_gate=ev.decision_gate,
            decision_fingerprint=ev.decision_fingerprint,
            generated_at=now,
            change_reason="agent_generated_draft",
        )
        ref = str(plan_version_id)
        return ExecutionResult(result_ref=ref, domain_result_ref=ref)

    return PreparedAction(
        context_fingerprint_payload=payload,
        execute=_execute_async,  # type: ignore[arg-type]
        domain_operation=_DOMAIN_OP[S.GENERATE_TRAINING_PLAN_DRAFT],
        domain_request_hash=ev.request_hash,
    )


async def _resolve_current_session_id(
    db: AsyncSession, user_id: str, iana_timezone: str, now: datetime
) -> str:
    """Resolve the current local-day owned session id via the latest today view.

    ``get_today`` re-runs the current safety gate; a blocked/rest/no-plan state
    means there is no confirmable session today (the proposal becomes stale).
    """
    today = await training_service.get_today(db, user_id, iana_timezone)
    if today.state != "session" or today.session is None:
        raise AppException(409, "今天没有可记录的训练场次", "session_not_today")
    return today.session.session_id


async def _prepare_record_training_feedback(
    db: AsyncSession, user_id: str, args: S.RecordTrainingFeedbackArguments,
    iana_timezone: str, now: datetime,
) -> PreparedAction:
    # The Agent feedback action excludes the pain/discomfort outcome (a pain
    # report uses the dedicated safety flow); args validation enforces that.
    session_id = await _resolve_current_session_id(db, user_id, iana_timezone, now)
    ev = await training_service.evaluate_feedback(
        db, user_id,
        session_id=session_id,
        outcome_state=args.outcome_state,
        iana_timezone=iana_timezone,
        now=now,
    )
    payload = {
        "action": S.RECORD_TRAINING_FEEDBACK,
        "decision_fingerprint": ev.decision_fingerprint,
        "session_id": str(ev.session_id),
        "outcome_state": args.outcome_state,
    }

    async def _execute_async() -> ExecutionResult:
        feedback_id = await P._persist_feedback_core(
            db, user_id,
            plan_version_id=ev.plan_version_id,
            session_id=ev.session_id,
            local_date=ev.local_date,
            outcome_state=ev.outcome_state,
        )
        ref = str(feedback_id)
        return ExecutionResult(result_ref=ref, domain_result_ref=ref)

    return PreparedAction(
        context_fingerprint_payload=payload,
        execute=_execute_async,  # type: ignore[arg-type]
        domain_operation=_DOMAIN_OP[S.RECORD_TRAINING_FEEDBACK],
        domain_request_hash=ev.request_hash,
    )


async def _prepare_substitute_today_exercise(
    db: AsyncSession, user_id: str, args: S.SubstituteTodayExerciseArguments,
    iana_timezone: str, now: datetime,
) -> PreparedAction:
    session_id = await _resolve_current_session_id(db, user_id, iana_timezone, now)
    ev = await training_service.evaluate_substitution(
        db, user_id,
        session_id=session_id,
        original_exercise_id=args.original_exercise_id,
        replacement_exercise_id=args.replacement_exercise_id,
        iana_timezone=iana_timezone,
        now=now,
    )
    payload = {
        "action": S.SUBSTITUTE_TODAY_EXERCISE,
        "decision_fingerprint": ev.decision_fingerprint,
        "session_id": str(ev.session_id),
        "original_exercise_id": args.original_exercise_id,
        "replacement_exercise_id": args.replacement_exercise_id,
    }

    async def _execute_async() -> ExecutionResult:
        substitution_id = await P._persist_substitution_core(
            db, user_id,
            plan_version_id=ev.plan_version_id,
            session_id=ev.session_id,
            local_date=ev.local_date,
            original_exercise_id=ev.original_exercise_id,
            replacement_exercise_id=ev.replacement_exercise_id,
            relation_reason=ev.relation_reason,
            decision_gate=ev.decision_gate,
        )
        ref = str(substitution_id)
        return ExecutionResult(result_ref=ref, domain_result_ref=ref)

    return PreparedAction(
        context_fingerprint_payload=payload,
        execute=_execute_async,  # type: ignore[arg-type]
        domain_operation=_DOMAIN_OP[S.SUBSTITUTE_TODAY_EXERCISE],
        domain_request_hash=ev.request_hash,
    )


_ARGUMENTS_MODELS: Dict[str, type] = {
    S.UPSERT_TODAY_CHECKIN: S.UpsertTodayCheckinArguments,
    S.CREATE_WEIGHT_RECORD: S.CreateWeightRecordArguments,
    S.GENERATE_TRAINING_PLAN_DRAFT: S.GenerateTrainingPlanDraftArguments,
    S.SUBSTITUTE_TODAY_EXERCISE: S.SubstituteTodayExerciseArguments,
    S.RECORD_TRAINING_FEEDBACK: S.RecordTrainingFeedbackArguments,
}

_PREPARERS: Dict[str, Callable] = {
    S.UPSERT_TODAY_CHECKIN: _prepare_upsert_today_checkin,
    S.CREATE_WEIGHT_RECORD: _prepare_create_weight_record,
    S.GENERATE_TRAINING_PLAN_DRAFT: _prepare_generate_training_plan_draft,
    S.RECORD_TRAINING_FEEDBACK: _prepare_record_training_feedback,
    S.SUBSTITUTE_TODAY_EXERCISE: _prepare_substitute_today_exercise,
}


async def prepare(
    db: AsyncSession, name: str, arguments: S.WriteActionArguments, user_id: str,
    *, iana_timezone: str, now: Optional[datetime] = None,
) -> PreparedAction:
    """Re-run the latest domain validation for ``name`` and return the
    fingerprint payload + deferred transaction-neutral executor."""
    preparer = _PREPARERS.get(name)
    if preparer is None:
        raise AgentError(ResultCode.TOOL_NOT_ALLOWED)
    now = now or _now()
    return await preparer(db, user_id, arguments, iana_timezone, now)


def compute_context_fingerprint(payload: Mapping[str, Any]) -> AgentFingerprint:
    """Keyed HMAC over a prepared context-fingerprint payload."""
    return compute_fingerprint(payload)


__all__ = [
    "SAFETY_SIGNAL_ROUTE_CODE",
    "ExecutionResult",
    "PreparedAction",
    "validate_arguments",
    "compute_arguments_fingerprint",
    "compute_context_fingerprint",
    "is_write_action",
    "build_diff",
    "prepare",
]
