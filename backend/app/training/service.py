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
from app.training.adaptive import (
    OverlayCandidate,
    build_deferral_overlays,
    build_recovery_overlays,
    build_shortened_overlay,
    occupied_plan_dates,
)
from app.training.adaptive_policy import (
    AdjustmentInput,
    AdjustmentKind,
    AdaptivePolicy,
    decide_adjustment,
    load_adaptive_policy,
)
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
    AdjustmentResponse,
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
ADAPTIVE_POLICY_PATH = _DATA / "training_adaptive_policy.v1.json"

# Versioned knowledge is loaded once at process start (immutable for the run).
SAFETY_POLICY: SafetyPolicy = load_safety_policy(str(SAFETY_POLICY_PATH))
TRAINING_POLICY: TrainingPolicy = load_training_policy(str(TRAINING_POLICY_PATH))
ADAPTIVE_POLICY: AdaptivePolicy = load_adaptive_policy(str(ADAPTIVE_POLICY_PATH))
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
    equipment = data.equipment if data is not None else None
    bw = bool(equipment.bodyweight) if equipment is not None else False
    band = bool(equipment.resistance_band) if equipment is not None else False
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
        origin_weekly_review_id=(
            str(version.origin_weekly_review_id)
            if version.origin_weekly_review_id
            else None
        ),
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
    evaluation = await evaluate_draft_request(
        db,
        user_id,
        fitness_goal=req.fitness_goal,
        weekly_frequency=req.weekly_frequency,
        session_duration_minutes=req.session_duration_minutes,
        equipment_bodyweight=req.equipment_bodyweight,
        equipment_resistance_band=req.equipment_resistance_band,
        iana_timezone=req.iana_timezone,
        now=now,
    )

    persisted = await P.create_draft(
        db, user_id,
        draft=evaluation.draft,
        weekly_frequency=evaluation.weekly_frequency,
        session_duration_minutes=evaluation.session_duration_minutes,
        decision_gate=evaluation.decision_gate,
        decision_fingerprint=evaluation.decision_fingerprint,
        generated_at=now,
        change_reason=rationale.INITIAL_GENERATION,
        idempotency_key=req.idempotency_key,
        request_hash=request_hash,
    )
    version = await P.get_version_owned(db, user_id, persisted.plan_version_id)
    if version is None:
        raise AppException(410, "草案幂等记录指向的计划已被清除", "idempotency_result_gone")
    view = await _version_to_view(db, version)
    return DraftResponse(
        has_draft=True, draft=view, decision_gate=evaluation.decision_gate
    )


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


@dataclass
class AdjustmentEvaluation:
    plan_version_id: uuid.UUID
    source_session_id: uuid.UUID
    source_local_date: date
    target_local_date: Optional[date]
    adjustment_kind: str
    trigger_code: str
    reason_codes: tuple[str, ...]
    source_context_fingerprint: str
    decision_fingerprint: str
    training_policy_version: str
    catalog_version: str
    source_manifest_version: str
    target_minutes: Optional[int]
    items: tuple[P.AdjustmentItemInput, ...]


def _adjustment_response(adjustment, status: str) -> AdjustmentResponse:
    return AdjustmentResponse(
        adjustment_id=str(adjustment.adjustment_id),
        status=status,
        adjustment_kind=adjustment.adjustment_kind,
        original_session_id=str(adjustment.source_session_id),
        source_local_date=adjustment.source_local_date,
        target_local_date=adjustment.target_local_date,
        target_minutes=adjustment.target_minutes,
        reason_codes=list(adjustment.reason_codes),
    )


def _validation_passes(candidate, ctx, decision, candidates) -> bool:
    return validate_plan(
        candidate.draft, ctx, decision, candidates, catalog(),
        TRAINING_POLICY, SAFETY_POLICY,
    ).valid


def _persistent_items(
    candidate: OverlayCandidate, source_prescriptions
) -> tuple[P.AdjustmentItemInput, ...]:
    values = []
    for item in candidate.items:
        prescription = item.prescription
        source_id = (
            source_prescriptions[item.source_index].prescription_id
            if item.source_index is not None else None
        )
        values.append(P.AdjustmentItemInput(
            source_prescription_id=source_id,
            item_action=item.action,
            effective_exercise_id=(
                prescription.exercise_id if prescription is not None else None),
            sets=prescription.sets if prescription is not None else None,
            reps=prescription.reps if prescription is not None else None,
            duration_seconds=(
                prescription.duration_seconds if prescription is not None else None),
            rest_seconds=(
                prescription.rest_seconds if prescription is not None else None),
            display_order=item.display_order,
        ))
    return tuple(values)


def _candidate_retains_substitution(
    candidate: OverlayCandidate, source_prescriptions, original_exercise_id: str
) -> bool:
    source_index = next((
        index
        for index, prescription in enumerate(source_prescriptions)
        if prescription.exercise_id == original_exercise_id
    ), None)
    return source_index is not None and any(
        item.source_index == source_index and item.action == "keep"
        for item in candidate.items
    )


def _snapshot_retains_substitution(
    items, source_prescriptions, original_exercise_id: str
) -> bool:
    source_id = next((
        prescription.prescription_id
        for prescription in source_prescriptions
        if prescription.exercise_id == original_exercise_id
    ), None)
    return source_id is not None and any(
        item.source_prescription_id == source_id and item.item_action == "keep"
        for item in items
    )


async def evaluate_adjustment(
    db: AsyncSession,
    user_id: str,
    *,
    expected_plan_version_id: str,
    expected_session_id: str,
    iana_timezone: str,
    now: Optional[datetime] = None,
) -> AdjustmentEvaluation:
    """Build and fully validate one current-context adjustment without writes."""
    if not validate_iana_timezone(iana_timezone):
        raise AppException(400, "时区标识无效", "invalid_timezone")
    try:
        expected_plan = uuid.UUID(str(expected_plan_version_id))
        expected_session = uuid.UUID(str(expected_session_id))
    except ValueError as exc:
        raise AppException(
            400, "预期计划或场次标识无效", "invalid_expected_version"
        ) from exc

    active = await P.get_active_version(db, user_id)
    if active is None:
        raise AppException(409, "没有生效的训练计划", "no_active_plan")
    if active.plan_version_id != expected_plan:
        raise AppException(409, "计划版本已变化", "stale_plan_version")
    if active.confirmed_at is None:
        raise AppException(409, "生效计划缺少确认时间", "active_plan_invalid")

    now = now or _utc_now()
    local_date = derive_local_date(now, iana_timezone)
    assert local_date is not None
    week_index = _plan_week(active.confirmed_at, local_date, iana_timezone)
    sessions = await P.load_sessions(db, active.plan_version_id)
    target = next((
        session for session in sessions
        if session.week_index == week_index
        and session.day_of_week == local_date.isoweekday()
    ), None)
    incoming = await P.get_incoming_deferral(
        db, user_id, active.plan_version_id, local_date)
    if incoming is not None:
        raise AppException(
            409, "延期场次不能再次叠加调整", "adjustment_chain_not_allowed")
    if target is None:
        raise AppException(409, "今天没有可调整的训练场次", "no_session_today")
    if target.session_id != expected_session:
        raise AppException(409, "训练场次已变化", "stale_session")

    bw, band = await _profile_equipment(db, user_id)
    request = _request_snapshot(
        active.requested_goal, active.weekly_frequency,
        active.session_duration_minutes, bw, band, iana_timezone, now)
    ctx, safety_decision = await _classify(db, user_id, request, now)
    gate = safety_decision.gate_status.value
    if gate in ("clarification_required", "restricted", "red_flag"):
        code = {
            "clarification_required": "clarification_required",
            "restricted": "restricted_no_plan",
            "red_flag": "red_flag_stop",
        }[gate]
        raise AppException(409, _gate_message(code), code)
    checkin = ctx.checkin
    adaptive_values = (
        checkin.energy, checkin.muscle_soreness, checkin.available_time,
        checkin.daily_status, checkin.token,
    )
    if (not checkin.present or checkin.local_date != local_date
            or any(value is None for value in adaptive_values)):
        raise AppException(
            409, "今天的结构化签到不完整", "missing_current_checkin")
    if checkin.abnormal_pain:
        raise AppException(
            409, "疼痛状态不允许普通调整", "pain_blocks_adjustment")
    if await P.get_feedback(db, user_id, target.session_id, local_date):
        raise AppException(
            409, "今天的训练反馈已经记录", "feedback_already_recorded")
    prior_adjustment = await P.get_latest_source_adjustment(
        db, user_id, active.plan_version_id, target.session_id, local_date)
    if (
        prior_adjustment is not None
        and prior_adjustment.source_context_fingerprint
        == safety_decision.fingerprint
    ):
        raise AppException(
            409, "今天的场次已经调整", "adjustment_already_applied")

    source_prescriptions = await P.load_prescriptions(db, target.session_id)
    adaptive_decision = decide_adjustment(AdjustmentInput(
        available_time=checkin.available_time,
        energy=checkin.energy,
        muscle_soreness=checkin.muscle_soreness,
        daily_status=checkin.daily_status,
        abnormal_pain=checkin.abnormal_pain,
        target_minutes=target.target_minutes or active.session_duration_minutes,
        prescription_count=len(source_prescriptions),
    ), ADAPTIVE_POLICY)
    if adaptive_decision.kind is AdjustmentKind.blocked:
        raise AppException(409, "当前状态不允许普通调整", "adjustment_blocked")

    candidates = select_candidates(
        ctx, safety_decision, catalog(), TRAINING_POLICY, SAFETY_POLICY)
    base = await _version_to_draft(
        db, active, context_fingerprint=safety_decision.fingerprint,
        profile_version=ctx.health.profile_version)
    base = await _compose_existing_overlays(
        db,
        user_id,
        active,
        base,
        exclude_source=(target.session_id, local_date),
    )
    if base is None:
        raise AppException(
            409, "现有调整无法安全重建", "adjustment_history_invalid")
    substitution = await P.get_substitution(
        db, user_id, target.session_id, local_date)
    selected: Optional[OverlayCandidate] = None
    final_kind = adaptive_decision.kind
    reasons = adaptive_decision.reason_codes

    if adaptive_decision.kind is AdjustmentKind.shortened:
        if substitution is not None and not _apply_substitution(
                base, target.week_index, target.day_of_week,
                substitution.original_exercise_id,
                substitution.replacement_exercise_id):
            raise AppException(
                409, "替换与缩短无法安全组合", "adjustment_collision")
        proposed = build_shortened_overlay(
            base, week_index=target.week_index,
            day_of_week=target.day_of_week,
            target_minutes=adaptive_decision.target_minutes,
            adaptive_policy=ADAPTIVE_POLICY, catalog=catalog())
        if proposed is not None and _validation_passes(
                proposed, ctx, safety_decision, candidates):
            if substitution is not None and not _candidate_retains_substitution(
                proposed,
                source_prescriptions,
                substitution.original_exercise_id,
            ):
                raise AppException(
                    409,
                    "缩短场次未保留已替换动作",
                    "adjustment_collision",
                )
            selected = proposed
    elif adaptive_decision.kind is AdjustmentKind.recovery:
        if substitution is not None:
            raise AppException(
                409, "恢复场次不能与动作替换组合", "adjustment_collision")
        for proposed in build_recovery_overlays(
                base, week_index=target.week_index,
                day_of_week=target.day_of_week,
                adaptive_policy=ADAPTIVE_POLICY, catalog=catalog(),
                candidates=candidates):
            if _validation_passes(proposed, ctx, safety_decision, candidates):
                selected = proposed
                break
        if selected is None:
            raise AppException(
                409, "没有通过完整校验的恢复场次",
                "no_safe_recovery_overlay")

    if adaptive_decision.kind is AdjustmentKind.deferred or (
            adaptive_decision.kind is AdjustmentKind.shortened
            and selected is None):
        if substitution is not None:
            raise AppException(409, "已有动作替换，不能延期", "adjustment_collision")
        plan_start = local_date - timedelta(
            days=(target.week_index - 1) * 7 + target.day_of_week - 1)
        occupied = occupied_plan_dates(base, plan_start)
        occupied.update(
            item.target_local_date
            for item in await P.list_effective_plan_adjustments(
                db, user_id, active.plan_version_id)
            if item.target_local_date is not None)
        for proposed in build_deferral_overlays(
                base, source_week_index=target.week_index,
                source_day_of_week=target.day_of_week,
                source_local_date=local_date, occupied_dates=occupied):
            if _validation_passes(proposed, ctx, safety_decision, candidates):
                selected = proposed
                final_kind = AdjustmentKind.deferred
                if adaptive_decision.kind is AdjustmentKind.shortened:
                    reasons = (*reasons, "shortening_failed_deferred")
                break
        if selected is None:
            final_kind = AdjustmentKind.active_rest
            reasons = (*reasons, "active_rest_no_legal_deferral")

    effective_identity = {
        "kind": final_kind.value,
        "target_date": selected.target_local_date if selected else None,
        "target_minutes": selected.target_minutes if selected else None,
        "items": [{
            "action": item.action,
            "exercise": item.prescription.exercise_id if item.prescription else None,
            "sets": item.prescription.sets if item.prescription else None,
            "reps": item.prescription.reps if item.prescription else None,
            "duration_seconds": (
                item.prescription.duration_seconds if item.prescription else None
            ),
            "rest_seconds": (
                item.prescription.rest_seconds if item.prescription else None
            ),
            "source_index": item.source_index,
            "order": item.display_order,
        } for item in (selected.items if selected else ())],
    }
    return AdjustmentEvaluation(
        plan_version_id=active.plan_version_id,
        source_session_id=target.session_id,
        source_local_date=local_date,
        target_local_date=selected.target_local_date if selected else None,
        adjustment_kind=final_kind.value,
        trigger_code=reasons[0],
        reason_codes=tuple(reasons),
        source_context_fingerprint=safety_decision.fingerprint,
        decision_fingerprint=P.hash_request(effective_identity),
        training_policy_version=TRAINING_POLICY.policy_version,
        catalog_version=catalog().content_version,
        source_manifest_version=catalog().source_manifest_version,
        target_minutes=selected.target_minutes if selected else None,
        items=_persistent_items(selected, source_prescriptions) if selected else (),
    )


async def apply_today_adjustment(
    db: AsyncSession, user_id: str, req
) -> AdjustmentResponse:
    request_hash = P.hash_request({
        "op": "today_adjustment", "intent": req.intent,
        "expected_plan_version_id": str(req.expected_plan_version_id),
        "expected_session_id": str(req.expected_session_id),
        "iana_timezone": req.iana_timezone,
    })
    replayed_ref = await P.peek_idempotency(
        db, user_id, P.OP_TODAY_ADJUSTMENT, req.idempotency_key,
        request_hash, _utc_now())
    if replayed_ref is not None:
        adjustment = await P.get_adjustment_owned(
            db, user_id, uuid.UUID(replayed_ref))
        if adjustment is None:
            raise AppException(
                410, "调整幂等记录指向的数据已清除", "idempotency_result_gone")
        return _adjustment_response(adjustment, "replayed")

    evaluation = await evaluate_adjustment(
        db, user_id,
        expected_plan_version_id=str(req.expected_plan_version_id),
        expected_session_id=str(req.expected_session_id),
        iana_timezone=req.iana_timezone)
    result = await P.record_adjustment(
        db, user_id,
        plan_version_id=evaluation.plan_version_id,
        source_session_id=evaluation.source_session_id,
        source_local_date=evaluation.source_local_date,
        target_local_date=evaluation.target_local_date,
        adjustment_kind=evaluation.adjustment_kind,
        trigger_code=evaluation.trigger_code,
        reason_codes=evaluation.reason_codes,
        source_context_fingerprint=evaluation.source_context_fingerprint,
        decision_fingerprint=evaluation.decision_fingerprint,
        adaptive_policy_version=ADAPTIVE_POLICY.policy_version,
        training_policy_version=evaluation.training_policy_version,
        catalog_version=evaluation.catalog_version,
        source_manifest_version=evaluation.source_manifest_version,
        surface="button", target_minutes=evaluation.target_minutes,
        items=evaluation.items, idempotency_key=req.idempotency_key,
        request_hash=request_hash)
    adjustment = await P.get_adjustment_owned(db, user_id, result.adjustment_id)
    assert adjustment is not None
    return _adjustment_response(adjustment, result.status)


# --- today ------------------------------------------------------------------


def _apply_adjustment_snapshot(
    draft: TrainingPlanDraft,
    source_session,
    items,
    target_minutes: Optional[int],
    substitution: Optional[tuple[str, str]],
) -> Optional[PlanSession]:
    target = next((
        session for session in draft.sessions
        if session.week_index == source_session.week_index
        and session.day_of_week == source_session.day_of_week
    ), None)
    if target is None:
        return None
    prescriptions = []
    for item in items:
        if item.item_action == "drop":
            continue
        if (
            item.effective_exercise_id is None
            or item.sets is None
            or item.rest_seconds is None
        ):
            return None
        exercise_id = item.effective_exercise_id
        sets = item.sets
        reps = item.reps
        duration_seconds = item.duration_seconds
        rest_seconds = item.rest_seconds
        relation_reason = None
        relation_source = None
        if substitution is not None:
            original_id, replacement_id = substitution
            if (
                item.source_prescription_id is not None
                and exercise_id == original_id
            ):
                replacement = _index().get(replacement_id)
                if replacement is None:
                    return None
                bounds = replacement.prescription
                exercise_id = replacement_id
                sets = bounds.sets_min
                reps = bounds.reps_min if bounds.mode.value == "reps" else None
                duration_seconds = (
                    bounds.duration_seconds_min
                    if bounds.mode.value == "duration"
                    else None
                )
                rest_seconds = bounds.rest_seconds_min
            if (
                item.source_prescription_id is not None
                and exercise_id == replacement_id
            ):
                relation_reason = "substitution"
                relation_source = original_id
        prescriptions.append(PlanPrescription(
            exercise_id=exercise_id,
            sets=sets,
            reps=reps,
            duration_seconds=duration_seconds,
            rest_seconds=rest_seconds,
            relation_reason=relation_reason,
            relation_source_exercise_id=relation_source,
        ))
    if not prescriptions:
        return None
    target.prescriptions = prescriptions
    target.target_minutes = target_minutes or target.target_minutes
    return target


async def _compose_existing_overlays(
    db: AsyncSession,
    user_id: str,
    active: TrainingPlanVersion,
    draft: TrainingPlanDraft,
    *,
    exclude_source: Optional[tuple[uuid.UUID, date]] = None,
) -> Optional[TrainingPlanDraft]:
    """Rebuild the latest effective append-only overlay state for a plan."""
    sessions = {
        session.session_id: session
        for session in await P.load_sessions(db, active.plan_version_id)
    }
    adjustments = await P.list_effective_plan_adjustments(
        db, user_id, active.plan_version_id)
    for adjustment in adjustments:
        source_key = (
            adjustment.source_session_id, adjustment.source_local_date)
        if exclude_source == source_key:
            continue
        source = sessions.get(adjustment.source_session_id)
        if source is None:
            return None
        target = next((
            item for item in draft.sessions
            if item.week_index == source.week_index
            and item.day_of_week == source.day_of_week
        ), None)
        if target is None:
            return None
        if adjustment.adjustment_kind == "active_rest":
            draft.sessions.remove(target)
            continue
        if adjustment.adjustment_kind == "deferred":
            if adjustment.target_local_date is None:
                return None
            plan_start = adjustment.source_local_date - timedelta(
                days=(source.week_index - 1) * 7 + source.day_of_week - 1)
            offset = (adjustment.target_local_date - plan_start).days
            if offset < 0 or offset > 27:
                return None
            target_week = offset // 7 + 1
            target_day = offset % 7 + 1
            if any(
                item is not target
                and item.week_index == target_week
                and item.day_of_week == target_day
                for item in draft.sessions
            ):
                return None
            target.week_index = target_week
            target.day_of_week = target_day
            continue
        if adjustment.adjustment_kind == "unchanged":
            substitution = await P.get_substitution(
                db,
                user_id,
                source.session_id,
                adjustment.source_local_date,
            )
            if substitution is not None and not _apply_substitution(
                draft,
                source.week_index,
                source.day_of_week,
                substitution.original_exercise_id,
                substitution.replacement_exercise_id,
            ):
                return None
            continue
        items = await P.load_adjustment_items(db, adjustment.adjustment_id)
        substitution = await P.get_substitution(
            db,
            user_id,
            source.session_id,
            adjustment.source_local_date,
        )
        source_prescriptions = await P.load_prescriptions(db, source.session_id)
        if substitution is not None and not _snapshot_retains_substitution(
            items,
            source_prescriptions,
            substitution.original_exercise_id,
        ):
            return None
        if _apply_adjustment_snapshot(
            draft,
            source,
            items,
            adjustment.target_minutes,
            (
                (
                    substitution.original_exercise_id,
                    substitution.replacement_exercise_id,
                )
                if substitution is not None
                else None
            ),
        ) is None:
            return None
    for week_index in range(1, 5):
        week = sorted(
            (item for item in draft.sessions if item.week_index == week_index),
            key=lambda item: item.day_of_week,
        )
        for order, session in enumerate(week, start=1):
            session.session_order = order
    return draft


async def get_today(
    db: AsyncSession,
    user_id: str,
    iana_timezone: str,
    *,
    now: Optional[datetime] = None,
) -> TodayResponse:
    if not validate_iana_timezone(iana_timezone):
        raise AppException(400, "时区标识无效", "invalid_timezone")
    active = await P.get_active_version(db, user_id)
    if active is None:
        return TodayResponse(state="no_active_plan")

    now = now or _utc_now()
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
            safety_status=gate,
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
            safety_status=gate,
        )
    if week_index < 1:
        return TodayResponse(
            state="rest_day", local_date=local_date,
            change_reason=active.change_reason, decision_gate=gate,
            safety_status=gate,
        )

    weekday = local_date.isoweekday()  # Mon=1 .. Sun=7
    sessions = await P.load_sessions(db, active.plan_version_id)
    todays = [
        s for s in sessions
        if s.week_index == week_index and s.day_of_week == weekday
    ]
    incoming = await P.get_incoming_deferral(
        db, user_id, active.plan_version_id, local_date)
    if todays and incoming is not None:
        return TodayResponse(
            state="blocked", local_date=local_date,
            change_reason="adjustment_collision", decision_gate=gate,
            safety_status=gate,
        )
    if not todays and incoming is None:
        return TodayResponse(
            state="rest_day", local_date=local_date,
            change_reason=active.change_reason, decision_gate=gate,
            safety_status=gate,
        )
    ses = todays[0] if todays else next((
        session for session in sessions
        if session.session_id == incoming.source_session_id
    ), None)
    if ses is None:
        return TodayResponse(
            state="blocked", local_date=local_date,
            change_reason="adjustment_source_missing", decision_gate=gate,
            safety_status=gate,
        )
    adjustment = incoming
    if adjustment is None:
        adjustment = await P.get_latest_source_adjustment(
            db, user_id, active.plan_version_id, ses.session_id, local_date)
    if adjustment is not None and (
        adjustment.adaptive_policy_version != ADAPTIVE_POLICY.policy_version
        or adjustment.training_policy_version != TRAINING_POLICY.policy_version
        or adjustment.catalog_version != catalog().content_version
        or adjustment.source_manifest_version
        != catalog().source_manifest_version
    ):
        return TodayResponse(
            state="blocked", local_date=local_date,
            change_reason="adjustment_version_stale", decision_gate=gate,
            original_session_id=str(ses.session_id),
            adjustment_id=str(adjustment.adjustment_id),
            adjustment_kind=adjustment.adjustment_kind,
            safety_status=gate,
        )
    if (
        adjustment is not None
        and incoming is None
        and adjustment.source_context_fingerprint != decision.fingerprint
    ):
        return TodayResponse(
            state="blocked", local_date=local_date,
            change_reason="adjustment_stale", decision_gate=gate,
            original_session_id=str(ses.session_id),
            source_local_date=adjustment.source_local_date,
            target_local_date=adjustment.target_local_date,
            adjustment_id=str(adjustment.adjustment_id),
            adjustment_kind=adjustment.adjustment_kind,
            adjustment_reason_codes=list(adjustment.reason_codes),
            safety_status=gate,
        )
    if (
        adjustment is not None
        and incoming is None
        and adjustment.adjustment_kind in ("deferred", "active_rest")
    ):
        return TodayResponse(
            state="rest_day", local_date=local_date,
            change_reason=adjustment.adjustment_kind,
            decision_gate=gate,
            original_session_id=str(ses.session_id),
            source_local_date=adjustment.source_local_date,
            target_local_date=adjustment.target_local_date,
            adjustment_id=str(adjustment.adjustment_id),
            adjustment_kind=adjustment.adjustment_kind,
            adjustment_reason_codes=list(adjustment.reason_codes),
            safety_status=gate,
        )
    prescs = await P.load_prescriptions(db, ses.session_id)
    substitution = await P.get_substitution(
        db, user_id, ses.session_id,
        adjustment.source_local_date if incoming is not None else local_date)
    feedback = await P.get_feedback(db, user_id, ses.session_id, local_date)
    effective = await _version_to_draft(
        db, active,
        context_fingerprint=decision.fingerprint,
        profile_version=ctx.health.profile_version,
    )
    effective = await _compose_existing_overlays(
        db,
        user_id,
        active,
        effective,
        exclude_source=(
            (ses.session_id, adjustment.source_local_date)
            if adjustment is not None else None
        ),
    )
    if effective is None:
        return TodayResponse(
            state="blocked", local_date=local_date,
            change_reason="adjustment_history_invalid", decision_gate=gate,
            safety_status=gate,
        )
    effective_session = None
    adjustment_items = []
    if incoming is not None:
        plan_start = adjustment.source_local_date - timedelta(
            days=(ses.week_index - 1) * 7 + ses.day_of_week - 1)
        occupied = occupied_plan_dates(effective, plan_start)
        moved = next((
            candidate for candidate in build_deferral_overlays(
                effective,
                source_week_index=ses.week_index,
                source_day_of_week=ses.day_of_week,
                source_local_date=adjustment.source_local_date,
                occupied_dates=occupied,
            )
            if candidate.target_local_date == adjustment.target_local_date
        ), None)
        if moved is not None:
            effective = moved.draft
            effective_session = next((
                session for session in effective.sessions
                if session.week_index == week_index
                and session.day_of_week == weekday
            ), None)
    elif adjustment is not None and adjustment.adjustment_kind == "unchanged":
        if substitution is not None and not _apply_substitution(
                effective, ses.week_index, ses.day_of_week,
                substitution.original_exercise_id,
                substitution.replacement_exercise_id):
            return TodayResponse(
                state="blocked", local_date=local_date,
                change_reason="safety_revalidation_failed", decision_gate=gate,
                safety_status=gate,
            )
        effective_session = next((
            session for session in effective.sessions
            if session.week_index == ses.week_index
            and session.day_of_week == ses.day_of_week
        ), None)
    elif adjustment is not None:
        adjustment_items = await P.load_adjustment_items(
            db, adjustment.adjustment_id)
        if substitution is not None and not _snapshot_retains_substitution(
            adjustment_items,
            prescs,
            substitution.original_exercise_id,
        ):
            return TodayResponse(
                state="blocked", local_date=local_date,
                change_reason="adjustment_collision", decision_gate=gate,
                original_session_id=str(ses.session_id),
                adjustment_id=str(adjustment.adjustment_id),
                adjustment_kind=adjustment.adjustment_kind,
                safety_status=gate,
            )
        effective_session = _apply_adjustment_snapshot(
            effective, ses, adjustment_items, adjustment.target_minutes,
            (
                (
                    substitution.original_exercise_id,
                    substitution.replacement_exercise_id,
                )
                if substitution is not None
                else None
            ))
    elif substitution is not None and not _apply_substitution(
            effective, ses.week_index, ses.day_of_week,
            substitution.original_exercise_id,
            substitution.replacement_exercise_id):
        return TodayResponse(
            state="blocked", local_date=local_date,
            change_reason="safety_revalidation_failed", decision_gate=gate,
            safety_status=gate,
        )
    if adjustment is not None and effective_session is None:
        return TodayResponse(
            state="blocked", local_date=local_date,
            change_reason="adjustment_snapshot_invalid", decision_gate=gate,
            original_session_id=str(ses.session_id),
            adjustment_id=str(adjustment.adjustment_id),
            adjustment_kind=adjustment.adjustment_kind,
            safety_status=gate,
        )
    validation = validate_plan(
        effective, ctx, decision, candidates, catalog(),
        TRAINING_POLICY, SAFETY_POLICY,
    )
    if not validation.valid:
        return TodayResponse(
            state="blocked", local_date=local_date,
            change_reason="safety_revalidation_failed", decision_gate=gate,
            safety_status=gate,
        )
    if effective_session is not None:
        item_ids = (
            [str(item.prescription_id) for item in prescs]
            if adjustment.adjustment_kind == "unchanged"
            else [
                str(item.source_prescription_id)
                if item.source_prescription_id is not None else None
                for item in adjustment_items if item.item_action != "drop"
            ]
        )
        prescription_views = [PrescriptionView(
            prescription_id=(item_ids[idx] if idx < len(item_ids) else None),
            exercise_id=p.exercise_id,
            sets=p.sets,
            reps=p.reps,
            duration_seconds=p.duration_seconds,
            rest_seconds=p.rest_seconds,
            relation_reason=p.relation_reason,
            exercise=_exercise_view(p.exercise_id, safe_candidate_ids),
        ) for idx, p in enumerate(effective_session.prescriptions)]
        session_view = SessionView(
            session_id=str(ses.session_id),
            week_index=effective_session.week_index,
            day_of_week=effective_session.day_of_week,
            session_order=effective_session.session_order,
            target_minutes=effective_session.target_minutes,
            prescriptions=prescription_views,
        )
        return TodayResponse(
            state="session", local_date=local_date,
            change_reason=adjustment.adjustment_kind,
            decision_gate=gate, session=session_view,
            feedback_outcome_state=(feedback.outcome_state if feedback else None),
            substitution_applied=substitution is not None,
            original_session_id=str(ses.session_id),
            source_local_date=adjustment.source_local_date,
            target_local_date=adjustment.target_local_date,
            adjustment_id=str(adjustment.adjustment_id),
            adjustment_kind=adjustment.adjustment_kind,
            adjustment_reason_codes=list(adjustment.reason_codes),
            safety_status=gate,
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
        original_session_id=str(ses.session_id),
        source_local_date=local_date,
        safety_status=gate,
    )


# --- execution records ------------------------------------------------------


async def _execution_context(
    db: AsyncSession,
    user_id: str,
    session_id: str,
    iana_timezone: str,
    *,
    now: Optional[datetime] = None,
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

    now = now or _utc_now()
    local_date = derive_local_date(now, iana_timezone)
    if active.confirmed_at is None:
        raise AppException(409, "生效计划缺少确认时间", "active_plan_invalid")
    week_index = _plan_week(active.confirmed_at, local_date, iana_timezone)
    original_today = (
        week_index in range(1, 5)
        and target.week_index == week_index
        and target.day_of_week == local_date.isoweekday()
    )
    incoming = await P.get_incoming_deferral(
        db, user_id, active.plan_version_id, local_date)
    deferred_today = (
        incoming is not None and incoming.source_session_id == target.session_id
    )
    if not original_today and not deferred_today:
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
    evaluation = await evaluate_feedback(
        db,
        user_id,
        session_id=session_id,
        outcome_state=req.outcome_state,
        iana_timezone=iana_timezone,
    )
    result = await P.record_feedback(
        db, user_id, plan_version_id=evaluation.plan_version_id,
        session_id=evaluation.session_id, local_date=evaluation.local_date,
        outcome_state=evaluation.outcome_state,
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
    evaluation = await evaluate_substitution(
        db,
        user_id,
        session_id=session_id,
        original_exercise_id=req.original_exercise_id,
        replacement_exercise_id=req.replacement_exercise_id,
        iana_timezone=iana_timezone,
    )

    result = await P.record_substitution(
        db, user_id, plan_version_id=evaluation.plan_version_id,
        session_id=evaluation.session_id, local_date=evaluation.local_date,
        original_exercise_id=evaluation.original_exercise_id,
        replacement_exercise_id=evaluation.replacement_exercise_id,
        relation_reason=evaluation.relation_reason,
        decision_gate=evaluation.decision_gate,
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
        await _execution_context(
            db, user_id, session_id, iana_timezone, now=now
        )
    )
    existing_feedback = await P.get_feedback(
        db, user_id, uuid.UUID(session_id), local_date
    )
    if existing_feedback is not None:
        raise AppException(409, "该训练日已记录反馈", "feedback_already_recorded")
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
        await _execution_context(
            db, user_id, session_id, iana_timezone, now=now
        )
    )
    existing_feedback = await P.get_feedback(
        db, user_id, target.session_id, local_date
    )
    if existing_feedback is not None:
        raise AppException(409, "今天的训练反馈已经记录", "feedback_already_recorded")
    if await P.get_incoming_deferral(
            db, user_id, active.plan_version_id, local_date):
        raise AppException(
            409, "延期场次不能叠加动作替换", "adjustment_collision")
    existing_substitution = await P.get_substitution(
        db, user_id, target.session_id, local_date
    )
    if existing_substitution is not None:
        raise AppException(409, "该训练日已替换过动作", "substitution_limit_reached")

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
    adjustment = await P.get_latest_source_adjustment(
        db, user_id, active.plan_version_id, target.session_id, local_date
    )
    if adjustment is not None:
        if adjustment.source_context_fingerprint != decision.fingerprint:
            raise AppException(409, "已有调整上下文已过期", "stale_context")
        if (
            adjustment.adaptive_policy_version != ADAPTIVE_POLICY.policy_version
            or adjustment.training_policy_version != TRAINING_POLICY.policy_version
            or adjustment.catalog_version != catalog().content_version
            or adjustment.source_manifest_version
            != catalog().source_manifest_version
        ):
            raise AppException(
                409, "已有调整版本已过期", "adjustment_version_stale"
            )
        if adjustment.adjustment_kind not in ("shortened", "unchanged"):
            raise AppException(
                409, "当前调整不能与动作替换组合", "adjustment_collision"
            )
    effective = await _compose_existing_overlays(
        db,
        user_id,
        active,
        effective,
        exclude_source=(
            (target.session_id, local_date) if adjustment is not None else None
        ),
    )
    if effective is None:
        raise AppException(
            409, "现有调整无法安全重建", "adjustment_history_invalid"
        )
    if adjustment is not None and adjustment.adjustment_kind == "shortened":
        items = await P.load_adjustment_items(db, adjustment.adjustment_id)
        if not _snapshot_retains_substitution(
            items, prescriptions, original_exercise_id
        ):
            raise AppException(
                409, "替换动作未被缩短场次保留", "adjustment_collision"
            )
        if _apply_adjustment_snapshot(
            effective,
            target,
            items,
            adjustment.target_minutes,
            (original_exercise_id, replacement_exercise_id),
        ) is None:
            raise AppException(
                409, "替换动作未被缩短场次保留", "adjustment_collision"
            )
    elif not _apply_substitution(
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
    "apply_today_adjustment",
    "record_feedback",
    "record_substitution",
    "catalog",
    "SAFETY_POLICY",
    "TRAINING_POLICY",
    "ADAPTIVE_POLICY",
    "evaluate_draft_request",
    "evaluate_feedback",
    "evaluate_substitution",
    "evaluate_adjustment",
    "DraftEvaluation",
    "FeedbackEvaluation",
    "SubstitutionEvaluation",
    "AdjustmentEvaluation",
]
