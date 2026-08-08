"""Phase 5 Agent confirmed write adapters (Task 3).

A server-side CLOSED registry for the reviewed write actions. It is
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
from app.nutrition import persistence as nutrition_persistence
from app.nutrition import service as nutrition_service
from app.training import persistence as P
from app.training import review_service
from app.training import service as training_service
from app.training.context import derive_local_date, validate_iana_timezone
from app.training.models import PostureRecheckDismissal, TrainingDayAdjustment

# Domain idempotency operations reused for the two-layer training contract.
_DOMAIN_OP = {
    S.GENERATE_TRAINING_PLAN_DRAFT: P.OP_PLAN_GENERATE,
    S.SUBSTITUTE_TODAY_EXERCISE: P.OP_SESSION_SUBSTITUTE,
    S.RECORD_TRAINING_FEEDBACK: P.OP_SESSION_FEEDBACK,
    S.GENERATE_MEAL_PLAN_DRAFT: nutrition_persistence.OP_DRAFT_GENERATE,
    S.REPLACE_FOOD: nutrition_persistence.OP_REPLACEMENT_CONFIRM,
    S.GENERATE_WEEKLY_REVIEW: P.OP_WEEKLY_REVIEW_GENERATE,
    S.APPLY_TODAY_ADJUSTMENT: P.OP_TODAY_ADJUSTMENT,
    S.CREATE_REVIEW_TRAINING_DRAFT: P.OP_REVIEW_TRAINING_DRAFT,
    S.CREATE_REVIEW_NUTRITION_DRAFT: P.OP_REVIEW_NUTRITION_DRAFT,
    S.DISMISS_POSTURE_RECHECK: P.OP_POSTURE_RECHECK_DISMISS,
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


def domain_operation_for(name: str) -> Optional[str]:
    """Return the existing domain idempotency namespace for a write action."""
    return _DOMAIN_OP.get(name)


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
    if name == S.GENERATE_MEAL_PLAN_DRAFT:
        return S.GenerateMealPlanDraftDiff(
            action=name,
            summary_code="agent_nutrition_draft_diff",
        )
    if name == S.REPLACE_FOOD:
        return S.ReplaceFoodDiff(
            action=name,
            summary_code="agent_nutrition_replacement_diff",
            day_kind=arguments.day_kind,
            meal=arguments.meal,
            item_index=arguments.item_index,
            from_food_id=arguments.from_food_id,
            to_food_id=arguments.to_food_id,
        )
    if name == S.APPLY_TODAY_ADJUSTMENT:
        return S.ApplyTodayAdjustmentDiff(
            action=name, summary_code="agent_today_adjustment_diff"
        )
    if name in {
        S.GENERATE_WEEKLY_REVIEW,
        S.CREATE_REVIEW_TRAINING_DRAFT,
        S.CREATE_REVIEW_NUTRITION_DRAFT,
        S.DISMISS_POSTURE_RECHECK,
    }:
        return S.WeeklyReviewActionDiff(
            action=name,
            summary_code=f"agent_{name}_diff",
            week_index=arguments.week_index,
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
    if args.local_date != derive_local_date(now, iana_timezone):
        raise AppException(
            409,
            "签到日期与当前本地日期不一致",
            "agent_context_stale",
        )
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
    today = await training_service.get_today(
        db, user_id, iana_timezone, now=now
    )
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


def _raise_mapped_nutrition_error(exc: AppException) -> None:
    mapping = {
        "nutrition_runtime_disabled": ResultCode.NUTRITION_DISABLED,
        "nutrition_red_flag": ResultCode.NUTRITION_BLOCKED,
        "nutrition_restricted": ResultCode.NUTRITION_BLOCKED,
        "nutrition_limited_education": ResultCode.NUTRITION_BLOCKED,
        "nutrition_clarification_required": ResultCode.NUTRITION_INCOMPLETE,
        "no_safe_candidate": ResultCode.NUTRITION_NO_SAFE_CANDIDATE,
        "invalid_replacement": ResultCode.NUTRITION_INVALID_REPLACEMENT,
        "invalid_recommendation_state": ResultCode.NUTRITION_INVALID_REPLACEMENT,
        "stale_context": ResultCode.CONTEXT_STALE,
        "recommendation_validation_failed": ResultCode.NUTRITION_BLOCKED,
    }
    code = mapping.get(exc.code, ResultCode.TOOL_FAILED)
    raise AppException(exc.status_code, "营养操作未通过校验", code) from exc


def _raise_mapped_adaptive_error(exc: AppException) -> None:
    if exc.code in {
        "stale_context",
        "adjustment_version_stale",
        ResultCode.CONTEXT_STALE,
    }:
        code = ResultCode.CONTEXT_STALE
    elif exc.code in {
        "red_flag_stop",
        "restricted_no_plan",
        "clarification_required",
        "adjustment_blocked",
        "no_safe_recovery_overlay",
        ResultCode.SAFETY_SIGNAL_ROUTE_REQUIRED,
    }:
        code = ResultCode.SAFETY_SIGNAL_ROUTE_REQUIRED
    elif exc.code in {
        ResultCode.NUTRITION_DISABLED,
        ResultCode.NUTRITION_BLOCKED,
        ResultCode.NUTRITION_INCOMPLETE,
        ResultCode.NUTRITION_NO_SAFE_CANDIDATE,
    }:
        code = exc.code
    else:
        code = ResultCode.ADAPTIVE_UNAVAILABLE
    raise AppException(
        exc.status_code,
        "训练调整或周复盘动作未通过当前校验",
        code,
    ) from exc


async def _prepare_generate_meal_plan_draft(
    db: AsyncSession,
    user_id: str,
    _args: S.GenerateMealPlanDraftArguments,
    iana_timezone: str,
    now: datetime,
) -> PreparedAction:
    try:
        candidate = await nutrition_service.prepare_draft_domain(
            db, user_id, iana_timezone
        )
    except AppException as exc:
        _raise_mapped_nutrition_error(exc)
    payload = {
        "action": S.GENERATE_MEAL_PLAN_DRAFT,
        "source_context_fingerprint": candidate.payload.source_context_fingerprint,
        "profile_version": candidate.pins.profile_version,
        "training_plan_version_id": candidate.pins.training_plan_version_id,
        "checkin_token": candidate.pins.checkin_token,
        "versions": candidate.payload.versions.model_dump(mode="json"),
    }
    request_hash = nutrition_persistence.hash_request(payload)

    async def _execute_async() -> ExecutionResult:
        result = await nutrition_persistence.create_draft_core(
            db,
            user_id,
            payload=candidate.payload,
            pins=candidate.pins,
            now=now,
        )
        ref = str(result.recommendation_id)
        return ExecutionResult(result_ref=ref, domain_result_ref=ref)

    return PreparedAction(
        context_fingerprint_payload=payload,
        execute=_execute_async,  # type: ignore[arg-type]
        domain_operation=_DOMAIN_OP[S.GENERATE_MEAL_PLAN_DRAFT],
        domain_request_hash=request_hash,
    )


async def _prepare_replace_food(
    db: AsyncSession,
    user_id: str,
    args: S.ReplaceFoodArguments,
    iana_timezone: str,
    now: datetime,
) -> PreparedAction:
    try:
        candidate = await nutrition_service.prepare_replacement_domain(
            db,
            user_id,
            iana_timezone,
            day_kind=args.day_kind,
            meal=args.meal,
            item_index=args.item_index,
            from_food_id=args.from_food_id,
            to_food_id=args.to_food_id,
        )
    except AppException as exc:
        _raise_mapped_nutrition_error(exc)
    diff = candidate.payload.replacement_diff
    if diff is None:
        raise AppException(
            409,
            "营养替换缺少差异",
            ResultCode.NUTRITION_INVALID_REPLACEMENT,
        )
    payload = {
        "action": S.REPLACE_FOOD,
        "source_recommendation_id": str(candidate.source.recommendation_id),
        "source_version": candidate.source.version,
        "source_context_fingerprint": candidate.payload.source_context_fingerprint,
        "replacement_diff": diff.model_dump(mode="json"),
        "versions": candidate.payload.versions.model_dump(mode="json"),
    }
    request_hash = nutrition_persistence.hash_request(payload)

    async def _execute_async() -> ExecutionResult:
        try:
            result = await nutrition_persistence.create_replacement_active_core(
                db,
                user_id,
                source_id=candidate.source.recommendation_id,
                expected_version=candidate.source.version,
                expected_fingerprint=candidate.source.source_context_fingerprint,
                payload=candidate.payload,
                pins=candidate.pins,
                now=now,
            )
        except AppException as exc:
            _raise_mapped_nutrition_error(exc)
        ref = str(result.recommendation_id)
        return ExecutionResult(result_ref=ref, domain_result_ref=ref)

    return PreparedAction(
        context_fingerprint_payload=payload,
        execute=_execute_async,  # type: ignore[arg-type]
        domain_operation=_DOMAIN_OP[S.REPLACE_FOOD],
        domain_request_hash=request_hash,
    )


async def _fresh_review(
    db: AsyncSession,
    user_id: str,
    week_index: int,
    iana_timezone: str,
    now: datetime,
):
    plan = await P.get_active_version(db, user_id)
    if plan is None:
        raise AppException(404, "当前没有生效计划", "review_not_generated")
    review = await review_service._latest_review(
        db, user_id, plan.plan_version_id, week_index
    )
    if review is None:
        raise AppException(404, "该周尚未生成回顾", "review_not_generated")
    assembly = await review_service._assemble(
        db, user_id, week_index, iana_timezone, now
    )
    if review.input_fingerprint != assembly.fingerprint:
        raise AppException(409, "回顾上下文已变化", ResultCode.CONTEXT_STALE)
    return review, assembly


async def _prepare_generate_weekly_review(
    db: AsyncSession,
    user_id: str,
    args: S.GenerateWeeklyReviewArguments,
    iana_timezone: str,
    now: datetime,
) -> PreparedAction:
    assembly = await review_service._assemble(
        db, user_id, args.week_index, iana_timezone, now
    )
    payload = {
        "action": S.GENERATE_WEEKLY_REVIEW,
        "week_index": args.week_index,
        "plan_version_id": str(assembly.plan.plan_version_id),
        "input_fingerprint": assembly.fingerprint,
    }
    request_hash = P.hash_request(
        {
            "operation": P.OP_WEEKLY_REVIEW_GENERATE,
            "plan_version_id": str(assembly.plan.plan_version_id),
            "week_index": args.week_index,
            "iana_timezone": iana_timezone,
        }
    )

    async def _execute_async() -> ExecutionResult:
        review = await review_service._persist_review_core(
            db, user_id, args.week_index, assembly, now
        )
        ref = str(review.review_id)
        return ExecutionResult(result_ref=ref, domain_result_ref=ref)

    return PreparedAction(
        context_fingerprint_payload=payload,
        execute=_execute_async,  # type: ignore[arg-type]
        domain_operation=_DOMAIN_OP[S.GENERATE_WEEKLY_REVIEW],
        domain_request_hash=request_hash,
    )


async def _prepare_apply_today_adjustment(
    db: AsyncSession,
    user_id: str,
    _args: S.ApplyTodayAdjustmentArguments,
    iana_timezone: str,
    now: datetime,
) -> PreparedAction:
    active = await P.get_active_version(db, user_id)
    today = await training_service.get_today(
        db, user_id, iana_timezone, now=now
    )
    if active is None or today.original_session_id is None:
        raise AppException(409, "今天没有可调整的训练", "session_not_today")
    evaluation = await training_service.evaluate_adjustment(
        db,
        user_id,
        expected_plan_version_id=str(active.plan_version_id),
        expected_session_id=today.original_session_id,
        iana_timezone=iana_timezone,
        now=now,
    )
    payload = {
        "action": S.APPLY_TODAY_ADJUSTMENT,
        "plan_version_id": str(evaluation.plan_version_id),
        "source_session_id": str(evaluation.source_session_id),
        "source_local_date": evaluation.source_local_date.isoformat(),
        "decision_fingerprint": evaluation.decision_fingerprint,
        "adjustment_kind": evaluation.adjustment_kind,
    }
    request_hash = P.hash_request(
        {
            "op": "today_adjustment",
            "intent": "apply_today_adjustment",
            "expected_plan_version_id": str(evaluation.plan_version_id),
            "expected_session_id": str(evaluation.source_session_id),
            "iana_timezone": iana_timezone,
        }
    )

    async def _execute_async() -> ExecutionResult:
        duplicate = await db.scalar(
            select(TrainingDayAdjustment.adjustment_id).where(
                TrainingDayAdjustment.user_id == uuid.UUID(user_id),
                TrainingDayAdjustment.plan_version_id
                == evaluation.plan_version_id,
                TrainingDayAdjustment.source_session_id
                == evaluation.source_session_id,
                TrainingDayAdjustment.source_local_date
                == evaluation.source_local_date,
                TrainingDayAdjustment.source_context_fingerprint
                == evaluation.source_context_fingerprint,
                TrainingDayAdjustment.adaptive_policy_version
                == training_service.ADAPTIVE_POLICY.policy_version,
                TrainingDayAdjustment.adjustment_kind
                == evaluation.adjustment_kind,
            )
        )
        if duplicate is not None:
            raise AppException(
                409, "当前上下文的调整已经记录", "adjustment_already_applied"
            )
        adjustment_id = await P._persist_adjustment_core(
            db,
            user_id,
            plan_version_id=evaluation.plan_version_id,
            source_session_id=evaluation.source_session_id,
            source_local_date=evaluation.source_local_date,
            target_local_date=evaluation.target_local_date,
            adjustment_kind=evaluation.adjustment_kind,
            trigger_code=evaluation.trigger_code,
            reason_codes=evaluation.reason_codes,
            source_context_fingerprint=evaluation.source_context_fingerprint,
            decision_fingerprint=evaluation.decision_fingerprint,
            adaptive_policy_version=training_service.ADAPTIVE_POLICY.policy_version,
            training_policy_version=evaluation.training_policy_version,
            catalog_version=evaluation.catalog_version,
            source_manifest_version=evaluation.source_manifest_version,
            surface="agent_confirmation",
            target_minutes=evaluation.target_minutes,
            items=evaluation.items,
        )
        ref = str(adjustment_id)
        return ExecutionResult(result_ref=ref, domain_result_ref=ref)

    return PreparedAction(
        context_fingerprint_payload=payload,
        execute=_execute_async,  # type: ignore[arg-type]
        domain_operation=_DOMAIN_OP[S.APPLY_TODAY_ADJUSTMENT],
        domain_request_hash=request_hash,
    )


async def _prepare_create_review_training_draft(
    db: AsyncSession,
    user_id: str,
    args: S.CreateReviewTrainingDraftArguments,
    iana_timezone: str,
    now: datetime,
) -> PreparedAction:
    review, assembly = await _fresh_review(
        db, user_id, args.week_index, iana_timezone, now
    )
    proposal = next(
        (
            item
            for item in review.proposal_codes
            if item["code"] == "offer_training_draft"
        ),
        None,
    )
    if proposal is None:
        raise AppException(409, "该回顾没有训练草案提案", "review_action_unavailable")
    frequency = assembly.plan.weekly_frequency
    duration = assembly.plan.session_duration_minutes
    if proposal["strategy"] == "lower_frequency":
        frequency = max(2, frequency - 1)
    elif proposal["strategy"] == "progression":
        if duration < 60:
            duration = {15: 30, 30: 45, 45: 60}[duration]
        else:
            frequency = min(5, frequency + 1)
    else:
        duration = {60: 45, 45: 30, 30: 15}.get(duration, duration)
    bodyweight, band = await training_service._profile_equipment(db, user_id)
    evaluation = await training_service.evaluate_draft_request(
        db,
        user_id,
        fitness_goal=assembly.plan.requested_goal,
        weekly_frequency=frequency,
        session_duration_minutes=duration,
        equipment_bodyweight=bodyweight,
        equipment_resistance_band=band,
        iana_timezone=iana_timezone,
        now=now,
    )
    payload = {
        "action": S.CREATE_REVIEW_TRAINING_DRAFT,
        "week_index": args.week_index,
        "review_id": str(review.review_id),
        "input_fingerprint": review.input_fingerprint,
        "decision_fingerprint": evaluation.decision_fingerprint,
    }
    request_hash = P.hash_request(
        {
            "operation": P.OP_REVIEW_TRAINING_DRAFT,
            "review_id": str(review.review_id),
            "fingerprint": review.input_fingerprint,
        }
    )

    async def _execute_async() -> ExecutionResult:
        draft_id = await P._persist_draft_core(
            db,
            user_id,
            draft=evaluation.draft,
            weekly_frequency=evaluation.weekly_frequency,
            session_duration_minutes=evaluation.session_duration_minutes,
            decision_gate=evaluation.decision_gate,
            decision_fingerprint=evaluation.decision_fingerprint,
            generated_at=now,
            change_reason="weekly_review_draft",
            origin_weekly_review_id=review.review_id,
        )
        ref = str(draft_id)
        return ExecutionResult(result_ref=ref, domain_result_ref=ref)

    return PreparedAction(
        context_fingerprint_payload=payload,
        execute=_execute_async,  # type: ignore[arg-type]
        domain_operation=_DOMAIN_OP[S.CREATE_REVIEW_TRAINING_DRAFT],
        domain_request_hash=request_hash,
    )


async def _prepare_create_review_nutrition_draft(
    db: AsyncSession,
    user_id: str,
    args: S.CreateReviewNutritionDraftArguments,
    iana_timezone: str,
    now: datetime,
) -> PreparedAction:
    review, _assembly = await _fresh_review(
        db, user_id, args.week_index, iana_timezone, now
    )
    if not any(
        item["code"] == "offer_nutrition_refresh"
        for item in review.proposal_codes
    ):
        raise AppException(409, "该回顾没有营养刷新提案", "review_action_unavailable")
    try:
        candidate = await nutrition_service.prepare_draft_domain(
            db, user_id, iana_timezone
        )
    except AppException as exc:
        _raise_mapped_nutrition_error(exc)
    payload = {
        "action": S.CREATE_REVIEW_NUTRITION_DRAFT,
        "week_index": args.week_index,
        "review_id": str(review.review_id),
        "input_fingerprint": review.input_fingerprint,
        "source_context_fingerprint": candidate.payload.source_context_fingerprint,
    }
    request_hash = P.hash_request(
        {
            "operation": P.OP_REVIEW_NUTRITION_DRAFT,
            "review_id": str(review.review_id),
            "fingerprint": review.input_fingerprint,
        }
    )

    async def _execute_async() -> ExecutionResult:
        created = await nutrition_persistence.create_draft_core(
            db,
            user_id,
            payload=candidate.payload,
            pins=candidate.pins,
            now=now,
            origin_weekly_review_id=review.review_id,
        )
        ref = str(created.recommendation_id)
        return ExecutionResult(result_ref=ref, domain_result_ref=ref)

    return PreparedAction(
        context_fingerprint_payload=payload,
        execute=_execute_async,  # type: ignore[arg-type]
        domain_operation=_DOMAIN_OP[S.CREATE_REVIEW_NUTRITION_DRAFT],
        domain_request_hash=request_hash,
    )


async def _prepare_dismiss_posture_recheck(
    db: AsyncSession,
    user_id: str,
    args: S.DismissPostureRecheckArguments,
    iana_timezone: str,
    now: datetime,
) -> PreparedAction:
    review, _assembly = await _fresh_review(
        db, user_id, args.week_index, iana_timezone, now
    )
    if review.facts["posture"]["status"] != "due":
        raise AppException(409, "当前没有可关闭的体态复查提醒", "review_action_unavailable")
    payload = {
        "action": S.DISMISS_POSTURE_RECHECK,
        "week_index": args.week_index,
        "review_id": str(review.review_id),
        "input_fingerprint": review.input_fingerprint,
    }
    request_hash = P.hash_request(
        {
            "operation": P.OP_POSTURE_RECHECK_DISMISS,
            "review_id": str(review.review_id),
            "fingerprint": review.input_fingerprint,
        }
    )

    async def _execute_async() -> ExecutionResult:
        existing = await db.scalar(
            select(PostureRecheckDismissal.dismissal_id).where(
                PostureRecheckDismissal.user_id == uuid.UUID(user_id),
                PostureRecheckDismissal.plan_version_id == review.plan_version_id,
            )
        )
        if existing is not None:
            raise AppException(409, "该周期提醒已经关闭", "review_action_unavailable")
        row = PostureRecheckDismissal(
            user_id=uuid.UUID(user_id),
            plan_version_id=review.plan_version_id,
            due_reason="cycle_complete",
            dismissed_at=now,
            created_at=now,
        )
        db.add(row)
        await db.flush()
        ref = str(row.dismissal_id)
        return ExecutionResult(result_ref=ref, domain_result_ref=ref)

    return PreparedAction(
        context_fingerprint_payload=payload,
        execute=_execute_async,  # type: ignore[arg-type]
        domain_operation=_DOMAIN_OP[S.DISMISS_POSTURE_RECHECK],
        domain_request_hash=request_hash,
    )


_ARGUMENTS_MODELS: Dict[str, type] = {
    S.UPSERT_TODAY_CHECKIN: S.UpsertTodayCheckinArguments,
    S.CREATE_WEIGHT_RECORD: S.CreateWeightRecordArguments,
    S.GENERATE_TRAINING_PLAN_DRAFT: S.GenerateTrainingPlanDraftArguments,
    S.SUBSTITUTE_TODAY_EXERCISE: S.SubstituteTodayExerciseArguments,
    S.RECORD_TRAINING_FEEDBACK: S.RecordTrainingFeedbackArguments,
    S.GENERATE_MEAL_PLAN_DRAFT: S.GenerateMealPlanDraftArguments,
    S.REPLACE_FOOD: S.ReplaceFoodArguments,
    S.GENERATE_WEEKLY_REVIEW: S.GenerateWeeklyReviewArguments,
    S.APPLY_TODAY_ADJUSTMENT: S.ApplyTodayAdjustmentArguments,
    S.CREATE_REVIEW_TRAINING_DRAFT: S.CreateReviewTrainingDraftArguments,
    S.CREATE_REVIEW_NUTRITION_DRAFT: S.CreateReviewNutritionDraftArguments,
    S.DISMISS_POSTURE_RECHECK: S.DismissPostureRecheckArguments,
}

_PREPARERS: Dict[str, Callable] = {
    S.UPSERT_TODAY_CHECKIN: _prepare_upsert_today_checkin,
    S.CREATE_WEIGHT_RECORD: _prepare_create_weight_record,
    S.GENERATE_TRAINING_PLAN_DRAFT: _prepare_generate_training_plan_draft,
    S.RECORD_TRAINING_FEEDBACK: _prepare_record_training_feedback,
    S.SUBSTITUTE_TODAY_EXERCISE: _prepare_substitute_today_exercise,
    S.GENERATE_MEAL_PLAN_DRAFT: _prepare_generate_meal_plan_draft,
    S.REPLACE_FOOD: _prepare_replace_food,
    S.GENERATE_WEEKLY_REVIEW: _prepare_generate_weekly_review,
    S.APPLY_TODAY_ADJUSTMENT: _prepare_apply_today_adjustment,
    S.CREATE_REVIEW_TRAINING_DRAFT: _prepare_create_review_training_draft,
    S.CREATE_REVIEW_NUTRITION_DRAFT: _prepare_create_review_nutrition_draft,
    S.DISMISS_POSTURE_RECHECK: _prepare_dismiss_posture_recheck,
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
    if not validate_iana_timezone(iana_timezone):
        raise AppException(400, "时区标识无效", ResultCode.INVALID_TIMEZONE)
    try:
        return await preparer(db, user_id, arguments, iana_timezone, now)
    except AppException as exc:
        if name in {
            S.GENERATE_WEEKLY_REVIEW,
            S.APPLY_TODAY_ADJUSTMENT,
            S.CREATE_REVIEW_TRAINING_DRAFT,
            S.CREATE_REVIEW_NUTRITION_DRAFT,
            S.DISMISS_POSTURE_RECHECK,
        }:
            _raise_mapped_adaptive_error(exc)
        raise


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
    "domain_operation_for",
    "build_diff",
    "prepare",
]
