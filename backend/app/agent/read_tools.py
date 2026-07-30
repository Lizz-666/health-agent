"""Read Tool adapters (Task 1).

Each adapter delegates to an EXISTING domain service/Tool and produces two
separately typed projections (minimal ``provider_view`` + owned
``display_view``). No adapter runs SQL/HTTP, opens a new data-access path, or
duplicates domain business logic; identity comes only from the server-injected
``ActorContext.user_id``. Nothing here writes, and a full Tool result is never
handed back to the provider verbatim (spec Tool Registry And Permission Matrix,
Safety/Failure/Observability).
"""
from __future__ import annotations

from datetime import date
from typing import Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.messages import AgentError, ResultCode
from app.agent.schemas import (
    ActivePlanDisplayView,
    ActivePlanProviderView,
    ExerciseCatalogDisplayView,
    ExerciseCatalogProviderView,
    HealthProfileDisplayView,
    HealthProfileProviderView,
    PostureIssueDetailDisplayView,
    PostureIssueDetailProviderView,
    PostureIssueDisplayItem,
    PostureIssueListDisplayView,
    PostureIssueListProviderView,
    PostureIssueProviderItem,
    PostureProfileDisplayView,
    PostureProfileEntryView,
    PostureProfileProviderView,
    PosturePrioritiesDisplayView,
    PosturePrioritiesProviderView,
    PriorityItemView,
    ReadToolResult,
    SelfTestGuideDisplayView,
    SelfTestGuideProviderView,
    StopConditionView,
    TodayCheckinDisplayView,
    TodayCheckinProviderView,
    TodayTrainingDisplayView,
    TodayTrainingProviderView,
    TrainingDraftDisplayView,
    TrainingDraftProviderView,
    TrainingExerciseDisplayView,
    TrainingExerciseProviderView,
    TrainingPlanSummaryView,
    WeightTrendDisplayView,
    WeightTrendProviderView,
)
from app.core.actor_context import ActorContext
from app.health import service as health_service
from app.posture import tools as posture_tools
from app.training import service as training_service


def _enum_val(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value.value) if hasattr(value, "value") else str(value)


# --------------------------------------------------------------------------- #
# Health                                                                       #
# --------------------------------------------------------------------------- #


async def adapt_health_profile_summary(
    db: AsyncSession, actor: ActorContext
) -> ReadToolResult:
    result = await health_service.get_profile_result(db, actor.user_id)
    profile = result.profile
    readiness = result.readiness
    equip = getattr(profile, "equipment", None)

    if profile is None:
        provider = HealthProfileProviderView(
            configured=False,
            readiness_code=readiness.readiness,
            risk_version=readiness.risk_version,
        )
        display = HealthProfileDisplayView(
            configured=False,
            readiness_code=readiness.readiness,
            risk_version=readiness.risk_version,
        )
        return ReadToolResult("get_health_profile_summary", provider, display)

    pain = profile.pain_injury_limitations or []
    allergies = profile.allergies or []
    diet = profile.diet_exclusions or []
    common = dict(
        configured=True,
        profile_version=profile.version,
        readiness_code=readiness.readiness,
        risk_version=readiness.risk_version,
        fitness_goal=_enum_val(profile.fitness_goal),
        training_experience=_enum_val(profile.training_experience),
        weekly_frequency=profile.weekly_frequency,
        session_duration_minutes=_enum_val(profile.session_duration_minutes),
        equipment_bodyweight=getattr(equip, "bodyweight", None) if equip else None,
        equipment_resistance_band=(
            getattr(equip, "resistance_band", None) if equip else None
        ),
        restricted=readiness.restricted_reason is not None,
    )
    provider = HealthProfileProviderView(
        has_pain_limitations=bool(pain),
        has_allergies=bool(allergies),
        has_diet_exclusions=bool(diet),
        **common,
    )
    display = HealthProfileDisplayView(
        pain_limitation_count=len(pain),
        allergies_count=len(allergies),
        diet_exclusions_count=len(diet),
        **common,
    )
    return ReadToolResult("get_health_profile_summary", provider, display)


async def adapt_today_checkin(
    db: AsyncSession, actor: ActorContext, local_date: date
) -> ReadToolResult:
    result = await health_service.get_today(db, actor.user_id, local_date)
    checkin = result.checkin
    if checkin is None:
        provider = TodayCheckinProviderView(checked_in=False)
        display = TodayCheckinDisplayView(checked_in=False)
        return ReadToolResult("get_today_checkin", provider, display)

    provider = TodayCheckinProviderView(
        checked_in=True,
        local_date=checkin.local_date,
        risk_summary_code=checkin.risk_summary,
        risk_version=checkin.risk_version,
        abnormal_pain=checkin.abnormal_pain,
        has_pain_followup=checkin.pain_followup is not None,
    )
    display = TodayCheckinDisplayView(
        checked_in=True,
        local_date=checkin.local_date,
        risk_summary_code=checkin.risk_summary,
        risk_version=checkin.risk_version,
        abnormal_pain=checkin.abnormal_pain,
        sleep_quality=_enum_val(checkin.sleep_quality),
        energy=_enum_val(checkin.energy),
        muscle_soreness=_enum_val(checkin.muscle_soreness),
        available_time=_enum_val(checkin.available_time),
        daily_status=_enum_val(checkin.daily_status),
    )
    return ReadToolResult("get_today_checkin", provider, display)


async def adapt_weight_trend_summary(
    db: AsyncSession, actor: ActorContext
) -> ReadToolResult:
    trend = await health_service.get_weight_trend(db, actor.user_id)
    latest = trend.records[-1].weight_kg if trend.records else None
    provider = WeightTrendProviderView(
        sufficient=trend.sufficient,
        window=trend.window,
        record_count=len(trend.records),
        trend_point_count=len(trend.trend),
    )
    display = WeightTrendDisplayView(
        sufficient=trend.sufficient,
        window=trend.window,
        record_count=len(trend.records),
        trend_point_count=len(trend.trend),
        latest_weight_kg=latest,
    )
    return ReadToolResult("get_weight_trend_summary", provider, display)


# --------------------------------------------------------------------------- #
# Posture                                                                      #
# --------------------------------------------------------------------------- #


def adapt_list_posture_issues(category: Optional[str] = None) -> ReadToolResult:
    issues = posture_tools.list_posture_issues(category)
    provider = PostureIssueListProviderView(
        issues=[
            PostureIssueProviderItem(id=i.id, name_cn=i.name_cn, category=i.category)
            for i in issues
        ]
    )
    display = PostureIssueListDisplayView(
        issues=[
            PostureIssueDisplayItem(
                id=i.id,
                name_cn=i.name_cn,
                category=i.category,
                aliases=list(i.aliases),
                definition=i.definition,
            )
            for i in issues
        ]
    )
    return ReadToolResult("list_posture_issues", provider, display)


def adapt_get_posture_issue(issue_id: str) -> ReadToolResult:
    detail = posture_tools.get_posture_issue(issue_id)
    provider = PostureIssueDetailProviderView(
        id=detail.id,
        name_cn=detail.name_cn,
        category=detail.category,
        severity_levels=list(detail.severity_levels),
        self_test_count=len(detail.self_tests),
        has_red_flags=bool(detail.red_flags),
    )
    display = PostureIssueDetailDisplayView(
        id=detail.id,
        name_cn=detail.name_cn,
        name_en=detail.name_en,
        category=detail.category,
        definition=detail.definition,
        severity_levels=list(detail.severity_levels),
        red_flags=list(detail.red_flags),
        self_test_count=len(detail.self_tests),
    )
    return ReadToolResult("get_posture_issue", provider, display)


async def adapt_guide_posture_self_test(
    db: AsyncSession, actor: ActorContext, issue_id: str
) -> ReadToolResult:
    guide = await posture_tools.guide_posture_self_test(db, actor, issue_id)
    common = dict(
        issue_id=guide.issue_id,
        issue_name=guide.issue_name,
        category=guide.category,
        self_test_count=len(guide.self_tests),
        has_existing_result=guide.has_existing_result,
    )
    provider = SelfTestGuideProviderView(**common)
    display = SelfTestGuideDisplayView(**common)
    return ReadToolResult("guide_posture_self_test", provider, display)


async def adapt_get_posture_profile(
    db: AsyncSession, actor: ActorContext
) -> ReadToolResult:
    profile = await posture_tools.get_posture_profile(db, actor)
    evaluated = getattr(profile, "evaluated_issues", []) or []
    summary = getattr(profile, "summary", None)
    entries = [
        PostureProfileEntryView(
            issue_id=e.issue_id,
            issue_name=e.issue_name,
            category=e.category,
            combined_severity=e.combined_severity,
            certainty=e.certainty,
            has_conflict=e.has_conflict,
            risk_tier=e.risk_tier,
            risk_version=getattr(e, "risk_version", None),
            source_codes=[source.source for source in (e.sources or [])],
        )
        for e in evaluated
    ]
    totals = dict(
        total_evaluated=getattr(summary, "total_evaluated", 0) if summary else 0,
        total_conflict=getattr(summary, "total_conflict", 0) if summary else 0,
        total_provisional=getattr(summary, "total_provisional", 0) if summary else 0,
    )
    provider = PostureProfileProviderView(
        present=bool(evaluated), entries=entries, **totals
    )
    display = PostureProfileDisplayView(
        present=bool(evaluated),
        entries=entries,
        unevaluated_categories=list(
            getattr(profile, "unevaluated_categories", []) or []
        ),
        **totals,
    )
    return ReadToolResult("get_posture_profile", provider, display)


def _priority_items(items: List[Any]) -> List[PriorityItemView]:
    return [
        PriorityItemView(
            issue_id=i.issue_id,
            issue_name=i.issue_name,
            suggested_rank=getattr(i, "suggested_rank", None),
            severity=getattr(i, "severity", None),
            certainty=getattr(i, "certainty", None),
            risk_tier=getattr(i, "risk_tier", None),
        )
        for i in items
    ]


async def adapt_get_posture_priorities(
    db: AsyncSession, actor: ActorContext
) -> ReadToolResult:
    result = await posture_tools.suggest_posture_priorities(db, actor)
    provider = PosturePrioritiesProviderView(
        suggestion_id=result.suggestion_id,
        profile_version=result.profile_version,
        rule_version=result.rule_version,
        risk_version=result.risk_version,
        normal_candidate_count=len(result.normal_candidates),
        retest_count=len(result.retest_required),
        safety_blocked_count=len(result.safety_blocked),
    )
    display = PosturePrioritiesDisplayView(
        suggestion_id=result.suggestion_id,
        profile_version=result.profile_version,
        rule_version=result.rule_version,
        risk_version=result.risk_version,
        normal_candidates=_priority_items(result.normal_candidates),
        retest_required=_priority_items(result.retest_required),
        safety_blocked=_priority_items(result.safety_blocked),
    )
    return ReadToolResult("get_posture_priorities", provider, display)


# --------------------------------------------------------------------------- #
# Training                                                                     #
# --------------------------------------------------------------------------- #


def _plan_summary(plan: Any) -> Optional[TrainingPlanSummaryView]:
    if plan is None:
        return None
    return TrainingPlanSummaryView(
        plan_version_id=plan.plan_version_id,
        status=plan.status,
        requested_goal=plan.requested_goal,
        weekly_frequency=plan.weekly_frequency,
        session_duration_minutes=plan.session_duration_minutes,
        decision_gate=plan.decision_gate,
        session_count=len(plan.sessions),
        change_reason=getattr(plan, "change_reason", None),
        catalog_version=getattr(plan, "catalog_version", None),
        policy_version=getattr(plan, "policy_version", None),
    )


async def adapt_get_training_draft(
    db: AsyncSession, actor: ActorContext
) -> ReadToolResult:
    result = await training_service.get_draft(db, actor.user_id)
    summary = _plan_summary(result.draft)
    provider = TrainingDraftProviderView(
        has_draft=result.has_draft, decision_gate=result.decision_gate, plan=summary
    )
    display = TrainingDraftDisplayView(
        has_draft=result.has_draft, decision_gate=result.decision_gate, plan=summary
    )
    return ReadToolResult("get_training_draft", provider, display)


async def adapt_get_active_training_plan(
    db: AsyncSession, actor: ActorContext
) -> ReadToolResult:
    result = await training_service.get_active(db, actor.user_id)
    summary = _plan_summary(result.plan)
    provider = ActivePlanProviderView(has_active=result.has_active, plan=summary)
    display = ActivePlanDisplayView(has_active=result.has_active, plan=summary)
    return ReadToolResult("get_active_training_plan", provider, display)


async def adapt_get_today_training(
    db: AsyncSession, actor: ActorContext, iana_timezone: str
) -> ReadToolResult:
    today = await training_service.get_today(db, actor.user_id, iana_timezone)
    return _project_today_training(today)


def _project_today_training(today: Any) -> ReadToolResult:
    """Project one already-resolved current-day snapshot without re-reading it."""
    session = today.session
    prescriptions = session.prescriptions if session else []
    prescription_ids = [p.prescription_id for p in prescriptions if p.prescription_id]
    exercise_ids = [p.exercise_id for p in prescriptions]
    provider = TodayTrainingProviderView(
        state=today.state,
        local_date=today.local_date,
        decision_gate=today.decision_gate,
        has_session=session is not None,
        session_id=session.session_id if session else None,
        prescription_count=len(prescriptions),
        prescription_ids=prescription_ids,
        exercise_ids=exercise_ids,
        substitution_applied=today.substitution_applied,
        feedback_outcome_state=today.feedback_outcome_state,
    )
    display = TodayTrainingDisplayView(
        state=today.state,
        local_date=today.local_date,
        decision_gate=today.decision_gate,
        change_reason=today.change_reason,
        session_id=session.session_id if session else None,
        prescription_count=len(prescriptions),
        exercise_ids=exercise_ids,
        substitution_applied=today.substitution_applied,
        feedback_outcome_state=today.feedback_outcome_state,
    )
    return ReadToolResult("get_today_training", provider, display)


async def adapt_get_training_exercise(
    db: AsyncSession, actor: ActorContext, iana_timezone: str, exercise_id: str
) -> ReadToolResult:
    """Explain a prescribed exercise in the current local-date session.

    Ordering and safety (spec Tool Registry And Permission Matrix, Acceptance
    #1/#2): a ``get_today`` call resolves the current owned session; the
    exercise must be prescribed there (including a safety-validated same-day
    substitution). Otherwise ``agent_entity_not_found`` is raised BEFORE the
    catalog is touched. The catalog is read ONLY for stop-conditions after
    ownership is confirmed; ``substitution_ids`` come from
    ``prescription.exercise`` (already safety-filtered by ``get_today``) and are
    never re-expanded to the full catalog list.
    """
    today = await training_service.get_today(db, actor.user_id, iana_timezone)
    return _project_training_exercise(today, exercise_id)


def _project_training_exercise(today: Any, exercise_id: str) -> ReadToolResult:
    """Project an exercise from the same owned current-day snapshot."""
    session = today.session
    prescription = None
    if session is not None:
        prescription = next(
            (p for p in session.prescriptions if p.exercise_id == exercise_id), None
        )
    if prescription is None:
        # Non-prescribed / no session / foreign id share one non-enumerating
        # result; the catalog is NOT queried before this point.
        raise AgentError(ResultCode.ENTITY_NOT_FOUND)

    exercise_view = prescription.exercise  # already safety-filtered by get_today
    if exercise_view is None or exercise_view.exercise_id != exercise_id:
        raise AgentError(ResultCode.ENTITY_NOT_FOUND)

    provider_catalog = (
        ExerciseCatalogProviderView(
            exercise_id=exercise_view.exercise_id,
            name_en=exercise_view.name_en,
            name_zh=exercise_view.name_zh,
            difficulty=exercise_view.difficulty,
            training_roles=list(exercise_view.training_roles),
            has_substitutions=bool(exercise_view.substitution_ids),
        )
        if exercise_view is not None
        else None
    )
    display_catalog = (
        ExerciseCatalogDisplayView(
            exercise_id=exercise_view.exercise_id,
            name_en=exercise_view.name_en,
            name_zh=exercise_view.name_zh,
            difficulty=exercise_view.difficulty,
            training_roles=list(exercise_view.training_roles),
            instruction_steps=list(exercise_view.instruction_steps),
            form_cues=list(exercise_view.form_cues),
            substitution_ids=list(exercise_view.substitution_ids),
            illustration_asset_key=exercise_view.illustration_asset_key,
            illustration_alt_zh=exercise_view.illustration_alt_zh,
        )
        if exercise_view is not None
        else None
    )

    # Stop-conditions: read the catalog Exercise ONLY after ownership is
    # confirmed. These are bounded reviewed wellness-scope wording.
    stop_codes: List[str] = []
    stop_views: List[StopConditionView] = []
    catalog_exercise = training_service._index().get(exercise_id)
    if catalog_exercise is None or not catalog_exercise.stop_conditions:
        raise AgentError(ResultCode.ENTITY_NOT_FOUND)
    for sc in catalog_exercise.stop_conditions:
        stop_codes.append(sc.code)
        stop_views.append(
            StopConditionView(code=sc.code, display_text_zh=sc.display_text_zh)
        )

    provider = TrainingExerciseProviderView(
        exercise_id=exercise_id,
        prescribed=True,
        sets=prescription.sets,
        reps=prescription.reps,
        duration_seconds=prescription.duration_seconds,
        rest_seconds=prescription.rest_seconds,
        catalog=provider_catalog,
        stop_condition_codes=stop_codes,
    )
    display = TrainingExerciseDisplayView(
        exercise_id=exercise_id,
        prescribed=True,
        sets=prescription.sets,
        reps=prescription.reps,
        duration_seconds=prescription.duration_seconds,
        rest_seconds=prescription.rest_seconds,
        relation_reason=prescription.relation_reason,
        catalog=display_catalog,
        stop_conditions=stop_views,
    )
    return ReadToolResult("get_training_exercise", provider, display)


__all__ = [
    "adapt_health_profile_summary",
    "adapt_today_checkin",
    "adapt_weight_trend_summary",
    "adapt_list_posture_issues",
    "adapt_get_posture_issue",
    "adapt_guide_posture_self_test",
    "adapt_get_posture_profile",
    "adapt_get_posture_priorities",
    "adapt_get_training_draft",
    "adapt_get_active_training_plan",
    "adapt_get_today_training",
    "adapt_get_training_exercise",
]
