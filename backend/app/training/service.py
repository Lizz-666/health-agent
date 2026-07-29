"""Phase 4 training plan application services (Task 4).

Compose the Phase 3 safety engine, the deterministic generator, and the Phase 4
persistence layer behind a narrow, ownership-scoped service API. Identity is the
JWT-derived ``user_id`` (never client-supplied). Every generation, confirmation,
substitution, and feedback re-runs the current safety classification from
current structured data; blocked gates never yield a usable plan or success.

Privacy: responses and logs carry decision fingerprints, gate/risk results,
reason codes, versions, and counts only - never raw health fields, pain notes,
or another user's identifiers.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.health.service import get_profile_result
from app.training import persistence as P
from app.training import rationale
from app.training.context import build_context, derive_local_date, validate_iana_timezone
from app.training.candidates import select_candidates
from app.training.generator import generate_plan_draft
from app.training.knowledge import build_index
from app.training.models import TrainingPlanVersion
from app.training.policy import TrainingPolicy, load_training_policy
from app.training.safety import SafetyPolicy, classify_safety, load_safety_policy
from app.training.schemas import (
    PlanPrescription,
    PlanSession,
    RequestSnapshot,
    TrainingPlanDraft,
)
from app.training.schemas_api import (
    ActivePlanResponse,
    ConfirmResponse,
    DraftResponse,
    ExerciseView,
    FeedbackRequest,
    FeedbackResponse,
    PlanVersionView,
    PrescriptionView,
    SessionView,
    SubstitutionResponse,
    TodayResponse,
)
from app.training.validator import validate_plan

_DATA = Path(__file__).resolve().parent / "data"
CATALOG_PATH = _DATA / "exercises.v1.json"
SAFETY_POLICY_PATH = _DATA / "training_safety_policy.v1.json"
TRAINING_POLICY_PATH = _DATA / "training_policy.v1.json"

# Versioned knowledge is loaded once at process start (immutable for the run).
SAFETY_POLICY: SafetyPolicy = load_safety_policy(str(SAFETY_POLICY_PATH))
TRAINING_POLICY: TrainingPolicy = load_training_policy(str(TRAINING_POLICY_PATH))
# Catalog is loaded lazily (load_catalog performs source/asset verification and
# is heavier); keep a module-level singleton.
_catalog_singleton = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def catalog():
    """Lazily load and cache the verified exercise catalog."""
    global _catalog_singleton
    if _catalog_singleton is None:
        from app.training.knowledge import load_catalog
        _catalog_singleton = load_catalog(str(CATALOG_PATH))
    return _catalog_singleton


def _index():
    return build_index(catalog())


def _confirm_request_hash(req) -> str:
    return P.hash_request({
        "op": "confirm",
        "fitness_goal": req.fitness_goal,
        "weekly_frequency": req.weekly_frequency,
        "session_duration_minutes": req.session_duration_minutes,
        "equipment_bodyweight": req.equipment_bodyweight,
        "equipment_resistance_band": req.equipment_resistance_band,
        "iana_timezone": req.iana_timezone,
    })


_BLOCKING_GATE_CODES = {
    "clarification_required": (409, "clarification_required"),
    "restricted_no_plan": (409, "restricted_no_plan"),
    "red_flag_stop": (409, "red_flag_stop"),
}


def _raise_from_reason(reason_code: str) -> None:
    if reason_code in _BLOCKING_GATE_CODES:
        status, code = _BLOCKING_GATE_CODES[reason_code]
        raise AppException(status, _gate_message(code), code)
    if reason_code == "goal_not_supported_yet":
        raise AppException(400, "该健身目标暂不支持生成训练计划", "goal_not_supported_yet")
    if reason_code == "invalid_weekly_frequency":
        raise AppException(400, "每周频率无效", "invalid_weekly_frequency")
    if reason_code == "stale_safety_decision":
        raise AppException(409, "安全决策已过期，请重新生成", "stale_context")
    if reason_code in ("no_eligible_candidates", "insufficient_candidates_for_frequency"):
        raise AppException(
            409, "当前条件下无可用的候选动作，请调整频率或目标后重试", reason_code)
    raise AppException(503, "计划生成失败", "generation_failed")


def _gate_message(code: str) -> str:
    return {
        "clarification_required": "缺少必要信息，无法生成训练计划",
        "restricted_no_plan": "当前健康状态不适用自动训练计划",
        "red_flag_stop": "检测到安全风险信号，已停止训练计划",
    }.get(code, code)


def _request_snapshot(goal: str, freq: int, duration: int, bw: bool, band: bool,
                      tz: str, now: datetime) -> RequestSnapshot:
    if not validate_iana_timezone(tz):
        raise AppException(400, "时区标识无效", "invalid_timezone")
    local_date = derive_local_date(now, tz)
    return RequestSnapshot(
        fitness_goal=goal,
        equipment_bodyweight=bw,
        equipment_resistance_band=band,
        weekly_frequency=freq,
        session_duration_minutes=duration,
        iana_timezone=tz,
        client_local_date=local_date,
    )


async def _profile_equipment(db: AsyncSession, user_id: str) -> Tuple[bool, bool]:
    profile = await get_profile_result(db, user_id)
    data = profile.profile
    bw = bool(getattr(data, "equipment_bodyweight", False)) if data else False
    band = bool(getattr(data, "equipment_resistance_band", False)) if data else False
    return bw, band


async def _classify(db: AsyncSession, user_id: str, request: RequestSnapshot,
                    now: Optional[datetime] = None):
    """Build the current ownership-scoped context and classify safety."""
    cat = catalog()
    now = now or _utc_now()
    ctx = await build_context(
        db, user_id, request=request, policy=SAFETY_POLICY,
        catalog_version=cat.content_version,
        source_manifest_version=cat.source_manifest_version,
        evaluated_at_utc=now,
    )
    decision = classify_safety(ctx, SAFETY_POLICY)
    return ctx, decision


def _exercise_view(
    exercise_id: str, allowed_substitutions: Optional[set] = None,
) -> Optional[ExerciseView]:
    ex = _index().get(exercise_id)
    if ex is None:
        return None
    return ExerciseView(
        exercise_id=ex.exercise_id,
        name_en=ex.names.name_en,
        name_zh=ex.names.name_zh,
        training_roles=[r.value for r in ex.training_roles],
        difficulty=ex.difficulty.value,
        illustration_asset_key=ex.illustration.asset_key,
        illustration_alt_zh=ex.illustration.alt_text_zh,
        instruction_steps=list(ex.instruction_steps),
        form_cues=list(ex.form_cues),
        substitution_ids=[
            item for item in ex.substitution_ids
            if allowed_substitutions is None or item in allowed_substitutions
        ],
    )


async def _version_to_view(db: AsyncSession, version: TrainingPlanVersion) -> PlanVersionView:
    sessions = await P.load_sessions(db, version.plan_version_id)
    session_views = []
    for ses in sessions:
        prescs = await P.load_prescriptions(db, ses.session_id)
        session_views.append(SessionView(
            session_id=str(ses.session_id),
            week_index=ses.week_index,
            day_of_week=ses.day_of_week,
            session_order=ses.session_order,
            target_minutes=ses.target_minutes,
            prescriptions=[
                PrescriptionView(
                    prescription_id=str(p.prescription_id),
                    exercise_id=p.exercise_id,
                    sets=p.sets,
                    reps=p.reps,
                    duration_seconds=p.duration_seconds,
                    rest_seconds=p.rest_seconds,
                    relation_reason=p.relation_reason,
                    exercise=_exercise_view(p.exercise_id),
                )
                for p in prescs
            ],
        ))
    return PlanVersionView(
        plan_version_id=str(version.plan_version_id),
        requested_goal=version.requested_goal,
        weekly_frequency=version.weekly_frequency,
        session_duration_minutes=version.session_duration_minutes,
        status=version.status,
        change_reason=version.change_reason,
        decision_gate=version.decision_gate,
        generated_at=version.generated_at,
        confirmed_at=version.confirmed_at,
        catalog_version=version.catalog_version,
        policy_version=version.policy_version,
        sessions=session_views,
    )


async def _version_to_draft(
    db: AsyncSession,
    version: TrainingPlanVersion,
    *,
    context_fingerprint: Optional[str] = None,
    profile_version: Optional[int] = None,
) -> TrainingPlanDraft:
    sessions = []
    for ses in await P.load_sessions(db, version.plan_version_id):
        prescriptions = await P.load_prescriptions(db, ses.session_id)
        sessions.append(PlanSession(
            week_index=ses.week_index,
            day_of_week=ses.day_of_week,
            session_order=ses.session_order,
            target_minutes=ses.target_minutes,
            prescriptions=[PlanPrescription(
                exercise_id=p.exercise_id,
                sets=p.sets,
                reps=p.reps,
                duration_seconds=p.duration_seconds,
                rest_seconds=p.rest_seconds,
                relation_reason=p.relation_reason,
                relation_source_exercise_id=p.relation_source_exercise_id,
            ) for p in prescriptions],
        ))
    return TrainingPlanDraft(
        draft_id=str(version.plan_version_id),
        requested_goal=version.requested_goal,
        source_context_fingerprint=(
            context_fingerprint or version.source_context_fingerprint),
        profile_version=profile_version or version.profile_version,
        catalog_version=version.catalog_version,
        policy_version=version.policy_version,
        source_manifest_version=version.source_manifest_version,
        sessions=sessions,
    )


def _plan_week(confirmed_at: datetime, local_date: date, tz: str) -> int:
    confirmed_local = derive_local_date(confirmed_at, tz)
    start = confirmed_local - timedelta(days=confirmed_local.isoweekday() - 1)
    return ((local_date - start).days // 7) + 1


def _apply_substitution(
    draft: TrainingPlanDraft,
    week_index: int,
    day_of_week: int,
    original_exercise_id: str,
    replacement_exercise_id: str,
) -> bool:
    index = _index()
    source = index.get(original_exercise_id)
    replacement = index.get(replacement_exercise_id)
    if source is None or replacement is None:
        return False
    session = next((
        item for item in draft.sessions
        if item.week_index == week_index and item.day_of_week == day_of_week
    ), None)
    if session is None:
        return False
    position = next((
        i for i, item in enumerate(session.prescriptions)
        if item.exercise_id == original_exercise_id
    ), None)
    if position is None:
        return False
    rx = replacement.prescription
    session.prescriptions[position] = PlanPrescription(
        exercise_id=replacement.exercise_id,
        sets=rx.sets_min,
        reps=rx.reps_min if rx.mode.value == "reps" else None,
        duration_seconds=(rx.duration_seconds_min
                          if rx.mode.value == "duration" else None),
        rest_seconds=rx.rest_seconds_min,
        relation_reason="substitution",
        relation_source_exercise_id=source.exercise_id,
    )
    return True


# --- generate / draft -------------------------------------------------------


def _draft_request_hash(req) -> str:
    return P.hash_request({
        "op": "draft",
        "fitness_goal": req.fitness_goal,
        "weekly_frequency": req.weekly_frequency,
        "session_duration_minutes": req.session_duration_minutes,
        "equipment_bodyweight": req.equipment_bodyweight,
        "equipment_resistance_band": req.equipment_resistance_band,
        "iana_timezone": req.iana_timezone,
    })


async def generate_draft(db: AsyncSession, user_id: str, req) -> DraftResponse:
    now = _utc_now()
    request_hash = _draft_request_hash(req)
    replayed_ref = await P.peek_idempotency(
        db, user_id, P.OP_PLAN_GENERATE, req.idempotency_key,
        request_hash, now,
    )
    if replayed_ref is not None:
        version = await P.get_version_owned(
            db, user_id, uuid.UUID(replayed_ref))
        if version is None:
            raise AppException(
                410, "草案幂等记录指向的计划已被清除",
                "idempotency_result_gone")
        return DraftResponse(
            has_draft=True,
            draft=await _version_to_view(db, version),
            decision_gate=version.decision_gate,
        )
    request = _request_snapshot(
        req.fitness_goal, req.weekly_frequency, req.session_duration_minutes,
        req.equipment_bodyweight, req.equipment_resistance_band, req.iana_timezone, now,
    )
    ctx, decision = await _classify(db, user_id, request, now)
    cat = catalog()
    candidates = select_candidates(ctx, decision, cat, TRAINING_POLICY, SAFETY_POLICY)
    result = generate_plan_draft(ctx, decision, candidates, cat, TRAINING_POLICY, SAFETY_POLICY)
    if not result.ok:
        _raise_from_reason(result.reason_codes[0])
        raise AssertionError  # _raise_from_reason always raises

    persisted = await P.create_draft(
        db, user_id,
        draft=result.draft,
        weekly_frequency=req.weekly_frequency,
        session_duration_minutes=req.session_duration_minutes,
        decision_gate=decision.gate_status.value,
        decision_fingerprint=decision.fingerprint,
        generated_at=now,
        change_reason=rationale.INITIAL_GENERATION,
        idempotency_key=req.idempotency_key,
        request_hash=request_hash,
    )
    version = await P.get_version_owned(db, user_id, persisted.plan_version_id)
    if version is None:
        raise AppException(410, "草案幂等记录指向的计划已被清除", "idempotency_result_gone")
    view = await _version_to_view(db, version)
    return DraftResponse(has_draft=True, draft=view, decision_gate=decision.gate_status.value)


async def get_draft(db: AsyncSession, user_id: str) -> DraftResponse:
    version = await P.get_pending_draft(db, user_id)
    if version is None:
        return DraftResponse(has_draft=False)
    view = await _version_to_view(db, version)
    return DraftResponse(has_draft=True, draft=view, decision_gate=version.decision_gate)


# --- confirm / active -------------------------------------------------------


async def confirm(db: AsyncSession, user_id: str, req) -> ConfirmResponse:
    now = _utc_now()
    confirm_hash = _confirm_request_hash(req)
    # Replay takes precedence over the pending-draft precondition: a replay of an
    # already-completed confirm returns the active plan even though no pending
    # draft remains.
    replayed_ref = await P.peek_idempotency(
        db, user_id, P.OP_PLAN_CONFIRM, req.idempotency_key, confirm_hash, now
    )
    if replayed_ref is not None:
        version = await P.get_version_owned(db, user_id, uuid.UUID(replayed_ref))
        if version is None:
            raise AppException(410, "幂等记录指向的计划已被清除", "idempotency_result_gone")
        view = await _version_to_view(db, version)
        return ConfirmResponse(plan=view, superseded_prior=False)

    pending = await P.get_pending_draft(db, user_id)
    if pending is None:
        raise AppException(409, "没有待确认的计划草案", "no_pending_draft")

    request = _request_snapshot(
        req.fitness_goal, req.weekly_frequency, req.session_duration_minutes,
        req.equipment_bodyweight, req.equipment_resistance_band, req.iana_timezone, now,
    )
    ctx, decision = await _classify(db, user_id, request, now)
    gate = decision.gate_status.value
    if gate in ("clarification_required", "restricted", "red_flag"):
        code = {"clarification_required": "clarification_required",
                "restricted": "restricted_no_plan", "red_flag": "red_flag_stop"}[gate]
        raise AppException(409, _gate_message(code), code)

    cat = catalog()
    # Freshness: the stored draft must bind to the current decision fingerprint
    # and the current catalog/policy/manifest/profile versions.
    if pending.source_context_fingerprint != decision.fingerprint:
        raise AppException(409, "上下文已变化，请重新生成计划", "stale_context")
    if pending.catalog_version != cat.content_version:
        raise AppException(409, "动作目录版本已变化，请重新生成", "stale_context")
    if pending.policy_version != TRAINING_POLICY.policy_version:
        raise AppException(409, "训练策略版本已变化，请重新生成", "stale_context")
    if pending.source_manifest_version != cat.source_manifest_version:
        raise AppException(409, "来源清单版本已变化，请重新生成", "stale_context")
    if pending.profile_version != (ctx.health.profile_version or 0):
        raise AppException(409, "健康档案已变化，请重新生成", "stale_context")

    candidates = select_candidates(
        ctx, decision, cat, TRAINING_POLICY, SAFETY_POLICY)
    stored_draft = await _version_to_draft(db, pending)
    validation = validate_plan(
        stored_draft, ctx, decision, candidates, cat,
        TRAINING_POLICY, SAFETY_POLICY,
    )
    if not validation.valid:
        raise AppException(
            409,
            "待确认计划未通过当前安全校验，请重新生成",
            "stored_draft_invalid",
        )

    prior_active = await P.get_active_version(db, user_id)
    confirm_result = await P.confirm_and_activate(
        db, user_id, plan_version_id=pending.plan_version_id,
        confirmed_at=now, change_reason=rationale.INITIAL_CONFIRMATION,
        idempotency_key=req.idempotency_key,
        request_hash=confirm_hash,
    )
    version = await P.get_version_owned(db, user_id, confirm_result.plan_version_id)
    view = await _version_to_view(db, version)
    return ConfirmResponse(
        plan=view,
        superseded_prior=(prior_active is not None),
    )


async def get_active(db: AsyncSession, user_id: str) -> ActivePlanResponse:
    version = await P.get_active_version(db, user_id)
    if version is None:
        return ActivePlanResponse(has_active=False)
    view = await _version_to_view(db, version)
    return ActivePlanResponse(has_active=True, plan=view)


# --- today ------------------------------------------------------------------


async def get_today(db: AsyncSession, user_id: str, iana_timezone: str) -> TodayResponse:
    if not validate_iana_timezone(iana_timezone):
        raise AppException(400, "时区标识无效", "invalid_timezone")
    active = await P.get_active_version(db, user_id)
    if active is None:
        return TodayResponse(state="no_active_plan")

    now = _utc_now()
    local_date = derive_local_date(now, iana_timezone)
    # Re-check current safety; a blocked gate surfaces as an honest state.
    bw, band = await _profile_equipment(db, user_id)
    request = _request_snapshot(
        active.requested_goal, active.weekly_frequency, active.session_duration_minutes,
        bw, band, iana_timezone, now,
    )
    ctx, decision = await _classify(db, user_id, request, now)
    gate = decision.gate_status.value
    if gate in ("clarification_required", "restricted", "red_flag"):
        return TodayResponse(
            state="blocked", local_date=local_date,
            change_reason=active.change_reason, decision_gate=gate,
        )

    candidates = select_candidates(
        ctx, decision, catalog(), TRAINING_POLICY, SAFETY_POLICY)
    safe_candidate_ids = {
        candidate.exercise_id for candidate in candidates.candidates}

    if active.confirmed_at is None:
        raise AppException(409, "生效计划缺少确认时间", "active_plan_invalid")
    week_index = _plan_week(active.confirmed_at, local_date, iana_timezone)
    if week_index > 4:
        return TodayResponse(
            state="plan_complete", local_date=local_date,
            change_reason=active.change_reason, decision_gate=gate,
        )
    if week_index < 1:
        return TodayResponse(
            state="rest_day", local_date=local_date,
            change_reason=active.change_reason, decision_gate=gate,
        )

    weekday = local_date.isoweekday()  # Mon=1 .. Sun=7
    sessions = await P.load_sessions(db, active.plan_version_id)
    todays = [
        s for s in sessions
        if s.week_index == week_index and s.day_of_week == weekday
    ]
    if not todays:
        return TodayResponse(
            state="rest_day", local_date=local_date,
            change_reason=active.change_reason, decision_gate=gate,
        )
    ses = todays[0]
    prescs = await P.load_prescriptions(db, ses.session_id)
    substitution = await P.get_substitution(
        db, user_id, ses.session_id, local_date)
    feedback = await P.get_feedback(db, user_id, ses.session_id, local_date)
    effective = await _version_to_draft(
        db, active,
        context_fingerprint=decision.fingerprint,
        profile_version=ctx.health.profile_version,
    )
    if substitution is not None and not _apply_substitution(
            effective, ses.week_index, ses.day_of_week,
            substitution.original_exercise_id,
            substitution.replacement_exercise_id):
        return TodayResponse(
            state="blocked", local_date=local_date,
            change_reason="safety_revalidation_failed", decision_gate=gate,
        )
    validation = validate_plan(
        effective, ctx, decision, candidates, catalog(),
        TRAINING_POLICY, SAFETY_POLICY,
    )
    if not validation.valid:
        return TodayResponse(
            state="blocked", local_date=local_date,
            change_reason="safety_revalidation_failed", decision_gate=gate,
        )
    replacement = (
        _index()[substitution.replacement_exercise_id]
        if substitution is not None else None)
    prescription_views = []
    for p in prescs:
        if (replacement is not None
                and p.exercise_id == substitution.original_exercise_id):
            rx = replacement.prescription
            prescription_views.append(PrescriptionView(
                prescription_id=str(p.prescription_id),
                exercise_id=replacement.exercise_id,
                sets=rx.sets_min,
                reps=rx.reps_min if rx.mode.value == "reps" else None,
                duration_seconds=(rx.duration_seconds_min
                                  if rx.mode.value == "duration" else None),
                rest_seconds=rx.rest_seconds_min,
                relation_reason="substitution",
                exercise=_exercise_view(
                    replacement.exercise_id, safe_candidate_ids),
            ))
        else:
            prescription_views.append(PrescriptionView(
                prescription_id=str(p.prescription_id),
                exercise_id=p.exercise_id, sets=p.sets, reps=p.reps,
                duration_seconds=p.duration_seconds,
                rest_seconds=p.rest_seconds,
                relation_reason=p.relation_reason,
                exercise=_exercise_view(p.exercise_id, safe_candidate_ids),
            ))
    session_view = SessionView(
        session_id=str(ses.session_id),
        week_index=ses.week_index, day_of_week=ses.day_of_week,
        session_order=ses.session_order, target_minutes=ses.target_minutes,
        prescriptions=prescription_views,
    )
    return TodayResponse(
        state="session", local_date=local_date,
        change_reason=active.change_reason, decision_gate=gate,
        session=session_view,
        feedback_outcome_state=(feedback.outcome_state if feedback else None),
        substitution_applied=substitution is not None,
    )


# --- execution records ------------------------------------------------------


async def _execution_context(
    db: AsyncSession, user_id: str, session_id: str, iana_timezone: str,
):
    if not validate_iana_timezone(iana_timezone):
        raise AppException(400, "时区标识无效", "invalid_timezone")
    active = await P.get_active_version(db, user_id)
    if active is None:
        raise AppException(409, "没有生效的训练计划", "no_active_plan")
    sessions = await P.load_sessions(db, active.plan_version_id)
    target = next((s for s in sessions if str(s.session_id) == session_id), None)
    if target is None:
        raise AppException(404, "训练场次不存在", "not_owner_or_missing_session")

    now = _utc_now()
    local_date = derive_local_date(now, iana_timezone)
    if active.confirmed_at is None:
        raise AppException(409, "生效计划缺少确认时间", "active_plan_invalid")
    week_index = _plan_week(active.confirmed_at, local_date, iana_timezone)
    if (week_index not in range(1, 5)
            or target.week_index != week_index
            or target.day_of_week != local_date.isoweekday()):
        raise AppException(409, "只能记录今天的训练场次", "session_not_today")

    bw, band = await _profile_equipment(db, user_id)
    request = _request_snapshot(
        active.requested_goal, active.weekly_frequency,
        active.session_duration_minutes, bw, band, iana_timezone, now,
    )
    ctx, decision = await _classify(db, user_id, request, now)
    gate = decision.gate_status.value
    if gate in ("clarification_required", "restricted", "red_flag"):
        code = {"clarification_required": "clarification_required",
                "restricted": "restricted_no_plan",
                "red_flag": "red_flag_stop"}[gate]
        raise AppException(409, _gate_message(code), code)
    candidates = select_candidates(
        ctx, decision, catalog(), TRAINING_POLICY, SAFETY_POLICY)
    return active, target, local_date, ctx, decision, candidates


async def record_feedback(db: AsyncSession, user_id: str, session_id: str,
                          req, iana_timezone: str) -> FeedbackResponse:
    if req.outcome_state not in req.allowed_outcomes():
        raise AppException(400, "执行状态无效", "invalid_outcome_state")
    request_hash = P.hash_request({
        "op": "feedback", "session_id": session_id,
        "outcome": req.outcome_state, "iana_timezone": iana_timezone,
    })
    replayed_ref = await P.peek_idempotency(
        db, user_id, P.OP_SESSION_FEEDBACK, req.idempotency_key,
        request_hash, _utc_now(),
    )
    if replayed_ref is not None:
        feedback = await P.get_feedback_owned(
            db, user_id, uuid.UUID(replayed_ref))
        if feedback is None:
            raise AppException(
                410, "反馈幂等记录指向的数据已被清除",
                "idempotency_result_gone")
        return FeedbackResponse(
            feedback_id=str(feedback.feedback_id),
            outcome_state=feedback.outcome_state,
            status="replayed",
        )
    active, _target, local_date, _ctx, _decision, _candidates = (
        await _execution_context(db, user_id, session_id, iana_timezone))
    result = await P.record_feedback(
        db, user_id, plan_version_id=active.plan_version_id,
        session_id=uuid.UUID(session_id), local_date=local_date,
        outcome_state=req.outcome_state,
        idempotency_key=req.idempotency_key,
        request_hash=request_hash,
    )
    return FeedbackResponse(
        feedback_id=str(result.feedback_id), outcome_state=req.outcome_state,
        status=result.status,
    )


async def record_substitution(db: AsyncSession, user_id: str, session_id: str,
                               req, iana_timezone: str) -> SubstitutionResponse:
    request_hash = P.hash_request({
        "op": "substitute", "session_id": session_id,
        "orig": req.original_exercise_id,
        "repl": req.replacement_exercise_id,
        "iana_timezone": iana_timezone,
    })
    replayed_ref = await P.peek_idempotency(
        db, user_id, P.OP_SESSION_SUBSTITUTE, req.idempotency_key,
        request_hash, _utc_now(),
    )
    if replayed_ref is not None:
        substitution = await P.get_substitution_owned(
            db, user_id, uuid.UUID(replayed_ref))
        if substitution is None:
            raise AppException(
                410, "替换幂等记录指向的数据已被清除",
                "idempotency_result_gone")
        return SubstitutionResponse(
            substitution_id=str(substitution.substitution_id),
            status="replayed",
        )
    index = _index()
    if req.original_exercise_id not in index or req.replacement_exercise_id not in index:
        raise AppException(400, "动作不存在", "exercise_not_found")
    if req.original_exercise_id == req.replacement_exercise_id:
        raise AppException(400, "替换动作不能与原动作相同", "invalid_substitution")
    active, target, local_date, ctx, decision, candidates = (
        await _execution_context(db, user_id, session_id, iana_timezone))
    existing_feedback = await P.get_feedback(
        db, user_id, target.session_id, local_date)
    if existing_feedback is not None:
        raise AppException(409, "今天的训练反馈已经记录", "feedback_already_recorded")

    prescriptions = await P.load_prescriptions(db, target.session_id)
    original = next(
        (p for p in prescriptions if p.exercise_id == req.original_exercise_id),
        None,
    )
    if original is None:
        raise AppException(400, "原动作不在今天的处方中", "original_not_prescribed")
    source = index[req.original_exercise_id]
    if req.replacement_exercise_id not in source.substitution_ids:
        raise AppException(400, "该动作不是原动作的允许替代项", "substitution_not_allowed")
    if req.replacement_exercise_id not in {
            candidate.exercise_id for candidate in candidates.candidates}:
        raise AppException(409, "替代动作不符合当前安全条件", "substitution_not_safe")

    effective = await _version_to_draft(
        db, active,
        context_fingerprint=decision.fingerprint,
        profile_version=ctx.health.profile_version,
    )
    if not _apply_substitution(
            effective, target.week_index, target.day_of_week,
            req.original_exercise_id, req.replacement_exercise_id):
        raise AppException(
            409, "替换后的计划无法重建", "substitution_not_safe")
    validation = validate_plan(
        effective, ctx, decision, candidates, catalog(),
        TRAINING_POLICY, SAFETY_POLICY,
    )
    if not validation.valid:
        raise AppException(409, "替换后的计划未通过安全校验", "substitution_not_safe")

    result = await P.record_substitution(
        db, user_id, plan_version_id=active.plan_version_id,
        session_id=target.session_id, local_date=local_date,
        original_exercise_id=req.original_exercise_id,
        replacement_exercise_id=req.replacement_exercise_id,
        relation_reason="substitution", decision_gate=decision.gate_status.value,
        idempotency_key=req.idempotency_key,
        request_hash=request_hash,
    )
    return SubstitutionResponse(substitution_id=str(result.substitution_id), status=result.status)


# --- transaction-neutral evaluation helpers (shared by button + Agent) --------
#
# Each ``evaluate_*`` function re-runs the LATEST deterministic safety/validation
# against current structured data and returns the resolved inputs needed to
# persist, WITHOUT persisting or committing. The committing button flow and the
# Agent confirmation path both call these so chat and button share one validation
# path (ADR-0003; spec Write Confirmation Semantics). ``request_hash`` is the
# domain idempotency request hash for the operation.


@dataclass
class DraftEvaluation:
    draft: TrainingPlanDraft
    weekly_frequency: int
    session_duration_minutes: int
    decision_gate: str
    decision_fingerprint: str
    request_hash: str


async def evaluate_draft_request(
    db: AsyncSession,
    user_id: str,
    *,
    fitness_goal: str,
    weekly_frequency: int,
    session_duration_minutes: int,
    equipment_bodyweight: bool,
    equipment_resistance_band: bool,
    iana_timezone: str,
    now: Optional[datetime] = None,
) -> DraftEvaluation:
    """Re-validate a draft-generation request against the latest context and
    deterministically generate the draft without persisting. Raises on any
    blocking gate. Reused by the button flow and the Agent confirmation path."""
    now = now or _utc_now()
    request_hash = P.hash_request(
        {
            "op": "draft",
            "fitness_goal": fitness_goal,
            "weekly_frequency": weekly_frequency,
            "session_duration_minutes": session_duration_minutes,
            "equipment_bodyweight": equipment_bodyweight,
            "equipment_resistance_band": equipment_resistance_band,
            "iana_timezone": iana_timezone,
        }
    )
    request = _request_snapshot(
        fitness_goal, weekly_frequency, session_duration_minutes,
        equipment_bodyweight, equipment_resistance_band, iana_timezone, now,
    )
    ctx, decision = await _classify(db, user_id, request, now)
    cat = catalog()
    candidates = select_candidates(ctx, decision, cat, TRAINING_POLICY, SAFETY_POLICY)
    result = generate_plan_draft(ctx, decision, candidates, cat, TRAINING_POLICY, SAFETY_POLICY)
    if not result.ok:
        _raise_from_reason(result.reason_codes[0])
        raise AssertionError  # _raise_from_reason always raises
    return DraftEvaluation(
        draft=result.draft,
        weekly_frequency=weekly_frequency,
        session_duration_minutes=session_duration_minutes,
        decision_gate=decision.gate_status.value,
        decision_fingerprint=decision.fingerprint,
        request_hash=request_hash,
    )


@dataclass
class FeedbackEvaluation:
    plan_version_id: uuid.UUID
    session_id: uuid.UUID
    local_date: date
    outcome_state: str
    decision_fingerprint: str
    request_hash: str


async def evaluate_feedback(
    db: AsyncSession,
    user_id: str,
    *,
    session_id: str,
    outcome_state: str,
    iana_timezone: str,
    now: Optional[datetime] = None,
) -> FeedbackEvaluation:
    """Re-validate a session-feedback request against the latest context (active
    plan, today, current safety gate) without persisting."""
    if outcome_state not in FeedbackRequest.allowed_outcomes():
        raise AppException(400, "执行状态无效", "invalid_outcome_state")
    request_hash = P.hash_request(
        {
            "op": "feedback",
            "session_id": session_id,
            "outcome": outcome_state,
            "iana_timezone": iana_timezone,
        }
    )
    active, _target, local_date, _ctx, decision, _candidates = (
        await _execution_context(db, user_id, session_id, iana_timezone)
    )
    return FeedbackEvaluation(
        plan_version_id=active.plan_version_id,
        session_id=uuid.UUID(session_id),
        local_date=local_date,
        outcome_state=outcome_state,
        decision_fingerprint=decision.fingerprint,
        request_hash=request_hash,
    )


@dataclass
class SubstitutionEvaluation:
    plan_version_id: uuid.UUID
    session_id: uuid.UUID
    local_date: date
    original_exercise_id: str
    replacement_exercise_id: str
    relation_reason: str
    decision_gate: str
    decision_fingerprint: str
    request_hash: str


async def evaluate_substitution(
    db: AsyncSession,
    user_id: str,
    *,
    session_id: str,
    original_exercise_id: str,
    replacement_exercise_id: str,
    iana_timezone: str,
    now: Optional[datetime] = None,
) -> SubstitutionEvaluation:
    """Re-validate a same-day substitution against the latest context, catalog,
    candidate set, and plan validator without persisting. Raises on any safety,
    ownership, or validation failure."""
    request_hash = P.hash_request(
        {
            "op": "substitute",
            "session_id": session_id,
            "orig": original_exercise_id,
            "repl": replacement_exercise_id,
            "iana_timezone": iana_timezone,
        }
    )
    index = _index()
    if original_exercise_id not in index or replacement_exercise_id not in index:
        raise AppException(400, "动作不存在", "exercise_not_found")
    if original_exercise_id == replacement_exercise_id:
        raise AppException(400, "替换动作不能与原动作相同", "invalid_substitution")
    active, target, local_date, ctx, decision, candidates = (
        await _execution_context(db, user_id, session_id, iana_timezone)
    )
    existing_feedback = await P.get_feedback(
        db, user_id, target.session_id, local_date
    )
    if existing_feedback is not None:
        raise AppException(409, "今天的训练反馈已经记录", "feedback_already_recorded")

    prescriptions = await P.load_prescriptions(db, target.session_id)
    original = next(
        (p for p in prescriptions if p.exercise_id == original_exercise_id),
        None,
    )
    if original is None:
        raise AppException(400, "原动作不在今天的处方中", "original_not_prescribed")
    source = index[original_exercise_id]
    if replacement_exercise_id not in source.substitution_ids:
        raise AppException(400, "该动作不是原动作的允许替代项", "substitution_not_allowed")
    if replacement_exercise_id not in {
        candidate.exercise_id for candidate in candidates.candidates
    }:
        raise AppException(409, "替代动作不符合当前安全条件", "substitution_not_safe")

    effective = await _version_to_draft(
        db, active,
        context_fingerprint=decision.fingerprint,
        profile_version=ctx.health.profile_version,
    )
    if not _apply_substitution(
        effective, target.week_index, target.day_of_week,
        original_exercise_id, replacement_exercise_id,
    ):
        raise AppException(409, "替换后的计划无法重建", "substitution_not_safe")
    validation = validate_plan(
        effective, ctx, decision, candidates, catalog(),
        TRAINING_POLICY, SAFETY_POLICY,
    )
    if not validation.valid:
        raise AppException(409, "替换后的计划未通过安全校验", "substitution_not_safe")
    return SubstitutionEvaluation(
        plan_version_id=active.plan_version_id,
        session_id=target.session_id,
        local_date=local_date,
        original_exercise_id=original_exercise_id,
        replacement_exercise_id=replacement_exercise_id,
        relation_reason="substitution",
        decision_gate=decision.gate_status.value,
        decision_fingerprint=decision.fingerprint,
        request_hash=request_hash,
    )


__all__ = [
    "generate_draft",
    "get_draft",
    "confirm",
    "get_active",
    "get_today",
    "record_feedback",
    "record_substitution",
    "catalog",
    "SAFETY_POLICY",
    "TRAINING_POLICY",
    "evaluate_draft_request",
    "evaluate_feedback",
    "evaluate_substitution",
    "DraftEvaluation",
    "FeedbackEvaluation",
    "SubstitutionEvaluation",
]
