"""Deterministic Phase 7 weekly reviews and review-origin draft commands."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.health.models import DailyCheckIn
from app.health.service import get_weight_trend
from app.nutrition import persistence as nutrition_persistence
from app.nutrition import service as nutrition_service
from app.nutrition.models import NutritionRecommendation
from app.posture.models import PostureAssessmentEvent
from app.posture.user_lock import acquire_user_transaction_lock
from app.training import persistence as P
from app.training import service as training_service
from app.training.models import (
    PostureRecheckDismissal,
    TrainingPlanVersion,
    TrainingSession,
    TrainingSessionFeedback,
    TrainingWeeklyReview,
)
from app.training.schemas_api import (
    AdjustmentFactsView,
    ExecutionTrendView,
    ExecutionFactsView,
    NutritionReviewView,
    PostureDismissalResponse,
    PostureReviewView,
    ReviewDraftResponse,
    ReviewGenerateRequest,
    ReviewMutationRequest,
    ReviewProposalView,
    ReviewSafetyView,
    WeightTrendView,
    WeeklyReviewResponse,
)


@dataclass(frozen=True)
class ReviewAssembly:
    plan: TrainingPlanVersion
    period_start: date
    period_end: date
    facts: dict
    proposals: list[dict]
    fingerprint: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _canonical_hash(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _plan_start(plan: TrainingPlanVersion, iana_timezone: str) -> date:
    if plan.confirmed_at is None:
        raise AppException(409, "计划尚未生效", "review_not_due")
    confirmed = training_service.derive_local_date(plan.confirmed_at, iana_timezone)
    return confirmed - timedelta(days=confirmed.isoweekday() - 1)


def _period(plan: TrainingPlanVersion, week: int, iana_timezone: str) -> tuple[date, date]:
    if week < 1 or week > 4:
        raise AppException(400, "周序号无效", "invalid_week_index")
    start = _plan_start(plan, iana_timezone) + timedelta(days=(week - 1) * 7)
    return start, start + timedelta(days=6)


async def _active_plan(db: AsyncSession, user_id: str) -> TrainingPlanVersion:
    plan = await P.get_active_version(db, user_id)
    if plan is None:
        raise AppException(404, "当前没有生效计划", "review_not_generated")
    return plan


async def _execution_facts(
    db: AsyncSession,
    user_id: str,
    plan: TrainingPlanVersion,
    week: int,
    period_start: date,
    period_end: date,
) -> tuple[dict, dict, dict]:
    owner = uuid.UUID(user_id)
    sessions = list(
        (
            await db.execute(
                select(TrainingSession).where(
                    TrainingSession.plan_version_id == plan.plan_version_id,
                )
            )
        ).scalars().all()
    )
    source_sessions = [item for item in sessions if item.week_index == week]
    adjustments = await P.list_effective_plan_adjustments(
        db, user_id, plan.plan_version_id
    )
    adjustment_by_source = {
        (item.source_session_id, item.source_local_date): item
        for item in adjustments
    }
    feedback = list(
        (
            await db.execute(
                select(TrainingSessionFeedback).where(
                    TrainingSessionFeedback.user_id == owner,
                    TrainingSessionFeedback.plan_version_id == plan.plan_version_id,
                )
            )
        ).scalars().all()
    )
    feedback_by_session_date = {
        (item.session_id, item.local_date): item for item in feedback
    }
    execution = {
        "scheduled": len(source_sessions),
        "effective": 0,
        "completed": 0,
        "partial": 0,
        "too_busy": 0,
        "intentional_rest": 0,
        "discomfort": 0,
        "active_rest": 0,
        "safety_adjustment": 0,
        "unavailable": 0,
    }
    adjustment_counts = {
        "shortened": 0,
        "recovery": 0,
        "deferred": 0,
        "active_rest": 0,
        "unchanged": 0,
        "missing": 0,
        "unavailable": 0,
    }
    pressure_sessions: set[uuid.UUID] = set()
    execution_dates: set[date] = set()
    plan_start = period_start - timedelta(days=(week - 1) * 7)
    for session in sessions:
        source_date = plan_start + timedelta(
            days=(session.week_index - 1) * 7 + session.day_of_week - 1
        )
        source_in_period = period_start <= source_date <= period_end
        adjustment = adjustment_by_source.get((session.session_id, source_date))
        if adjustment is not None and source_in_period:
            adjustment_counts[adjustment.adjustment_kind] += 1
            execution_dates.add(source_date)
            if adjustment.adjustment_kind == "active_rest":
                execution["active_rest"] += 1
                pressure_sessions.add(session.session_id)
                continue
        elif adjustment is not None and adjustment.adjustment_kind == "active_rest":
            continue
        execution_date = (
            adjustment.target_local_date
            if adjustment is not None
            and adjustment.adjustment_kind == "deferred"
            and adjustment.target_local_date is not None
            else source_date
        )
        if (
            adjustment is not None
            and adjustment.adjustment_kind == "deferred"
            and source_in_period
        ):
            pressure_sessions.add(session.session_id)
        if not period_start <= execution_date <= period_end:
            continue
        execution["effective"] += 1
        execution_dates.add(execution_date)
        if adjustment is not None and adjustment.adjustment_kind == "recovery":
            execution["safety_adjustment"] += 1
        item = feedback_by_session_date.get((session.session_id, execution_date))
        if item is None:
            execution["unavailable"] += 1
        elif item.outcome_state in {
            "completed",
            "partial",
            "too_busy",
            "intentional_rest",
            "discomfort",
        }:
            execution[item.outcome_state] += 1
            if item.outcome_state in {"too_busy", "intentional_rest"}:
                pressure_sessions.add(session.session_id)
        else:
            execution["unavailable"] += 1
    return execution, adjustment_counts, {
        "schedule_pressure": len(pressure_sessions),
        "execution_dates": sorted(execution_dates),
    }


def _trend(current: dict, previous: Optional[dict]) -> dict:
    if (
        previous is None
        or current["effective"] - current["unavailable"] == 0
        or previous["effective"] - previous["unavailable"] == 0
    ):
        return {"available": False, "direction": None}
    current_observed = current["effective"] - current["unavailable"]
    previous_observed = previous["effective"] - previous["unavailable"]
    left = current["completed"] * previous_observed
    right = previous["completed"] * current_observed
    direction = "improving" if left > right else "declining" if left < right else "steady"
    return {"available": True, "direction": direction}


async def _weight_facts(
    db: AsyncSession, user_id: str, period_end: date
) -> dict:
    trend = await get_weight_trend(db, user_id, end_date=period_end)
    if not trend.sufficient or len(trend.trend) < 2:
        return {"available": False, "direction": None}
    first = trend.trend[0].weight_kg
    last = trend.trend[-1].weight_kg
    direction = "rising" if last > first else "falling" if last < first else "stable"
    return {"available": True, "direction": direction}


async def _nutrition_facts(
    db: AsyncSession,
    user_id: str,
    iana_timezone: str,
    now: datetime,
) -> dict:
    active = await nutrition_persistence.get_active(db, user_id)
    age_days = None
    recommendation_id = None
    recommendation_version = None
    if active is not None:
        recommendation_id = str(active.recommendation_id)
        recommendation_version = active.version
        local_today = training_service.derive_local_date(now, iana_timezone)
        local_generated = training_service.derive_local_date(
            _as_utc(active.generated_at), iana_timezone
        )
        age_days = max(0, (local_today - local_generated).days)
    try:
        candidate = await nutrition_service.prepare_draft_domain(
            db, user_id, iana_timezone
        )
    except AppException as exc:
        return {
            "state": "unavailable",
            "age_days": age_days,
            "refresh_available": False,
            "unavailable_reason": exc.code,
            "recommendation_id": recommendation_id,
            "version": recommendation_version,
        }
    if active is None:
        return {
            "state": "none",
            "age_days": None,
            "refresh_available": True,
            "unavailable_reason": None,
            "recommendation_id": None,
            "version": None,
        }
    stale = any(
        (
            active.profile_version != candidate.pins.profile_version,
            active.training_plan_version_id
            != candidate.pins.training_plan_version_id,
            active.checkin_token != candidate.pins.checkin_token,
            active.source_context_fingerprint
            != candidate.payload.source_context_fingerprint,
        )
    )
    return {
        "state": "stale" if stale else "active",
        "age_days": age_days,
        "refresh_available": stale,
        "unavailable_reason": None,
        "recommendation_id": recommendation_id,
        "version": recommendation_version,
    }


async def _current_training_safety(
    db: AsyncSession,
    user_id: str,
    plan: TrainingPlanVersion,
    iana_timezone: str,
    now: datetime,
) -> dict:
    """Re-run the authoritative gate without exposing health payloads."""
    bodyweight, band = await training_service._profile_equipment(db, user_id)
    request = training_service._request_snapshot(
        plan.requested_goal,
        plan.weekly_frequency,
        plan.session_duration_minutes,
        bodyweight,
        band,
        iana_timezone,
        now,
    )
    _context, decision = await training_service._classify(
        db, user_id, request, now
    )
    gate = decision.gate_status.value
    return {
        "gate": gate,
        "blocked": gate not in {"eligible", "eligible_conservative"},
        "reason_codes": list(decision.reason_codes),
        "missing_fields": list(decision.missing_fields),
    }


async def _period_safety(
    db: AsyncSession,
    user_id: str,
    execution_dates: list[date],
) -> dict:
    dates = set(execution_dates)
    if not dates:
        return {
            "blocked": False,
            "progression_blocked": False,
            "reason_codes": [],
            "missing_fields": [],
        }
    rows = list(
        (
            await db.execute(
                select(DailyCheckIn).where(
                    DailyCheckIn.user_id == uuid.UUID(user_id),
                    DailyCheckIn.local_date.in_(dates),
                )
            )
        ).scalars().all()
    )
    by_date = {item.local_date: item for item in rows}
    missing = sorted(day.isoformat() for day in dates - set(by_date))
    reason_codes: set[str] = set()
    progression_codes: set[str] = set()
    for item in rows:
        if item.abnormal_pain:
            reason_codes.add("review_abnormal_pain")
        if item.risk_summary in {"restricted", "red_flag"}:
            reason_codes.add(f"review_{item.risk_summary}")
        if item.energy == "low":
            progression_codes.add("review_low_energy")
        if item.muscle_soreness == "significant":
            progression_codes.add("review_significant_soreness")
    if missing:
        reason_codes.add("review_safety_input_missing")
    return {
        "blocked": bool(reason_codes),
        "progression_blocked": bool(reason_codes or progression_codes),
        "reason_codes": sorted(reason_codes | progression_codes),
        "missing_fields": ["checkin:" + day for day in missing],
    }


async def _cycle_progression_eligible(
    db: AsyncSession,
    user_id: str,
    plan: TrainingPlanVersion,
    iana_timezone: str,
) -> bool:
    """Conservative four-week progression gate over execution and check-ins."""
    cycle_start, _unused = _period(plan, 1, iana_timezone)
    _unused, cycle_end = _period(plan, 4, iana_timezone)
    expected_checkin_dates: set[date] = set()
    for cycle_week in range(1, 5):
        period_start, period_end = _period(
            plan, cycle_week, iana_timezone
        )
        execution, adjustments, metrics = await _execution_facts(
            db, user_id, plan, cycle_week, period_start, period_end
        )
        expected_checkin_dates.update(metrics["execution_dates"])
        if (
            execution["scheduled"] == 0
            or execution["effective"] != execution["scheduled"]
            or execution["completed"] != execution["effective"]
            or any(
                execution[key]
                for key in (
                    "partial",
                    "too_busy",
                    "intentional_rest",
                    "discomfort",
                    "active_rest",
                    "safety_adjustment",
                    "unavailable",
                )
            )
            or any(
                adjustments[key]
                for key in (
                    "shortened",
                    "recovery",
                    "deferred",
                    "active_rest",
                    "missing",
                    "unavailable",
                )
            )
        ):
            return False
    checkins = list(
        (
            await db.execute(
                select(DailyCheckIn).where(
                    DailyCheckIn.user_id == uuid.UUID(user_id),
                    DailyCheckIn.local_date >= cycle_start,
                    DailyCheckIn.local_date <= cycle_end,
                )
            )
        ).scalars().all()
    )
    if not expected_checkin_dates.issubset(
        {item.local_date for item in checkins}
    ):
        return False
    return not any(
        item.energy == "low"
        or item.muscle_soreness == "significant"
        or item.abnormal_pain
        or item.risk_summary in {"restricted", "red_flag"}
        for item in checkins
    )


def _assessment_signal(
    baseline: dict[str, tuple[tuple[str, Optional[str]], ...]],
    comparison: dict[str, tuple[tuple[str, Optional[str]], ...]],
) -> str:
    detected_before = {
        key: value
        for key, value in baseline.items()
        if any(severity not in (None, "normal") for _source, severity in value)
    }
    detected_after = {
        key: value
        for key, value in comparison.items()
        if any(severity not in (None, "normal") for _source, severity in value)
    }
    if detected_before == detected_after:
        return "unchanged"
    if set(detected_after) - set(detected_before):
        return "added"
    if set(detected_before) - set(detected_after):
        return "not_detected"
    return "changed"


async def _structured_posture_snapshot(
    db: AsyncSession,
    owner: uuid.UUID,
    *,
    cutoff_exclusive: datetime,
) -> tuple[
    dict[str, tuple[tuple[str, Optional[str]], ...]],
    Optional[datetime],
    list[str],
    list[dict],
]:
    rows = list(
        (
            await db.execute(
                select(PostureAssessmentEvent)
                .where(
                    PostureAssessmentEvent.user_id == owner,
                    PostureAssessmentEvent.source.in_({"self_test", "ai_photo"}),
                    PostureAssessmentEvent.lifecycle.in_({"active", "superseded"}),
                    PostureAssessmentEvent.created_at < cutoff_exclusive,
                )
                .order_by(
                    PostureAssessmentEvent.created_at.asc(),
                    PostureAssessmentEvent.id.asc(),
                )
            )
        ).scalars().all()
    )
    latest: dict[tuple[str, str], PostureAssessmentEvent] = {}
    for row in rows:
        latest[(row.issue_id, row.source)] = row
    if not latest:
        return {}, None, [], []
    by_issue: dict[str, list[tuple[str, Optional[str]]]] = {}
    for (issue_id, source), row in latest.items():
        by_issue.setdefault(issue_id, []).append((source, row.severity))
    signal = {
        issue_id: tuple(sorted(values)) for issue_id, values in by_issue.items()
    }
    anchor = max(_as_utc(row.created_at) for row in latest.values())
    identity = sorted(
        (
            {
                "event_id": str(row.id),
                "content_version": row.content_version,
            }
            for row in latest.values()
        ),
        key=lambda item: item["event_id"],
    )
    return (
        signal,
        anchor,
        sorted({source for _issue, source in latest}),
        identity,
    )


async def _posture_facts(
    db: AsyncSession,
    user_id: str,
    plan: TrainingPlanVersion,
    week: int,
    period_end: date,
    iana_timezone: str,
    now: datetime,
) -> dict:
    owner = uuid.UUID(user_id)
    _current, _current_at, _current_sources, current_identity = (
        await _structured_posture_snapshot(
            db,
            owner,
            cutoff_exclusive=_as_utc(now) + timedelta(microseconds=1),
        )
    )
    if week < 4:
        return {
            "status": "not_due",
            "_assessment_identity": {"current": current_identity},
        }
    dismissed = await db.scalar(
        select(PostureRecheckDismissal.dismissal_id).where(
            PostureRecheckDismissal.user_id == owner,
            PostureRecheckDismissal.plan_version_id == plan.plan_version_id,
        )
    )
    baseline_cutoff = plan.confirmed_at
    if baseline_cutoff is None:
        return {
            "status": "unavailable",
            "reason": "baseline_missing",
            "_assessment_identity": {"current": current_identity},
        }
    if baseline_cutoff.tzinfo is None:
        baseline_cutoff = baseline_cutoff.replace(tzinfo=timezone.utc)
    baseline, baseline_at, baseline_sources, baseline_identity = (
        await _structured_posture_snapshot(
            db,
            owner,
            cutoff_exclusive=baseline_cutoff + timedelta(microseconds=1),
        )
    )
    if baseline_at is None:
        return {
            "status": "unavailable",
            "reason": "baseline_missing",
            "_assessment_identity": {"current": current_identity},
        }
    zone = ZoneInfo(iana_timezone)
    cycle_end = datetime.combine(
        period_end + timedelta(days=1), time.min, tzinfo=zone
    ).astimezone(timezone.utc)
    comparison_at = await db.scalar(
        select(func.min(PostureAssessmentEvent.created_at)).where(
            PostureAssessmentEvent.user_id == owner,
            PostureAssessmentEvent.source.in_({"self_test", "ai_photo"}),
            PostureAssessmentEvent.lifecycle.in_({"active", "superseded"}),
            PostureAssessmentEvent.created_at >= cycle_end,
        )
    )
    if comparison_at is None:
        if dismissed is not None:
            return {
                "status": "not_due",
                "reason": "dismissed_for_cycle",
                "_assessment_identity": {
                    "baseline": baseline_identity,
                    "current": current_identity,
                },
            }
        return {
            "status": "due",
            "baseline_at": baseline_at.isoformat(),
            "baseline_sources": baseline_sources,
            "reason": "cycle_complete",
            "_assessment_identity": {
                "baseline": baseline_identity,
                "comparison": [],
                "current": current_identity,
            },
        }
    comparison_at = _as_utc(comparison_at)
    comparison_local_date = comparison_at.astimezone(zone).date()
    comparison_cutoff = datetime.combine(
        comparison_local_date + timedelta(days=1), time.min, tzinfo=zone
    ).astimezone(timezone.utc)
    comparison, comparison_anchor, comparison_sources, comparison_identity = (
        await _structured_posture_snapshot(
            db,
            owner,
            cutoff_exclusive=comparison_cutoff,
        )
    )
    return {
        "status": "comparison_available",
        "comparison_signal": _assessment_signal(baseline, comparison),
        "baseline_at": baseline_at.isoformat(),
        "comparison_at": comparison_anchor.isoformat(),
        "baseline_sources": baseline_sources,
        "comparison_sources": comparison_sources,
        "_assessment_identity": {
            "baseline": baseline_identity,
            "comparison": comparison_identity,
            "current": current_identity,
        },
    }


def training_proposal(
    execution: dict,
    adjustments: dict,
    *,
    weekly_frequency: int,
    session_duration_minutes: int,
    safety_blocked: bool = False,
    cycle_progression_eligible: bool = False,
    schedule_pressure_count: Optional[int] = None,
) -> Optional[str]:
    """Pure mapping deliberately excludes weight, nutrition, posture and Agent text."""
    if safety_blocked or execution["discomfort"] or execution["unavailable"]:
        return None
    schedule_pressure = (
        schedule_pressure_count
        if schedule_pressure_count is not None
        else execution["too_busy"]
        + execution["intentional_rest"]
        + execution["active_rest"]
        + adjustments["deferred"]
    )
    if schedule_pressure >= 2:
        if session_duration_minutes > 15:
            return "conservative_duration"
        if weekly_frequency > 2:
            return "lower_frequency"
    if adjustments["recovery"] >= 2 and session_duration_minutes > 15:
        return "regression"
    if cycle_progression_eligible and (
        session_duration_minutes < 60 or weekly_frequency < 5
    ):
        return "progression"
    return None


async def _assemble(
    db: AsyncSession,
    user_id: str,
    week: int,
    iana_timezone: str,
    now: datetime,
) -> ReviewAssembly:
    if not training_service.validate_iana_timezone(iana_timezone):
        raise AppException(400, "时区标识无效", "invalid_timezone")
    plan = await _active_plan(db, user_id)
    period_start, period_end = _period(plan, week, iana_timezone)
    local_date = training_service.derive_local_date(now, iana_timezone)
    if local_date <= period_end:
        raise AppException(409, "该计划周尚未结束", "review_not_due")
    execution, adjustments, execution_metrics = await _execution_facts(
        db, user_id, plan, week, period_start, period_end
    )
    previous = None
    if week > 1:
        previous_start, previous_end = _period(
            plan, week - 1, iana_timezone
        )
        previous, _unused, _previous_metrics = await _execution_facts(
            db, user_id, plan, week - 1, previous_start, previous_end
        )
    weight = await _weight_facts(db, user_id, period_end)
    nutrition = await _nutrition_facts(
        db, user_id, iana_timezone, now
    )
    posture = await _posture_facts(
        db, user_id, plan, week, period_end, iana_timezone, now
    )
    safety = await _current_training_safety(
        db, user_id, plan, iana_timezone, now
    )
    period_safety = await _period_safety(
        db, user_id, execution_metrics["execution_dates"]
    )
    safety = {
        **safety,
        "blocked": safety["blocked"] or period_safety["blocked"],
        "reason_codes": sorted(
            set(safety["reason_codes"]) | set(period_safety["reason_codes"])
        ),
        "missing_fields": sorted(
            set(safety["missing_fields"]) | set(period_safety["missing_fields"])
        ),
    }
    cycle_progression_eligible = (
        week == 4
        and not safety["blocked"]
        and not period_safety["progression_blocked"]
        and await _cycle_progression_eligible(
            db, user_id, plan, iana_timezone
        )
    )
    facts = {
        "execution": execution,
        "execution_trend": _trend(execution, previous),
        "adjustments": adjustments,
        "weight_trend": weight,
        "nutrition": nutrition,
        "posture": posture,
        "safety": safety,
    }
    strategy = training_proposal(
        execution,
        adjustments,
        weekly_frequency=plan.weekly_frequency,
        session_duration_minutes=plan.session_duration_minutes,
        safety_blocked=safety["blocked"],
        cycle_progression_eligible=cycle_progression_eligible,
        schedule_pressure_count=execution_metrics["schedule_pressure"],
    )
    proposals: list[dict] = []
    if strategy is not None:
        proposals.append({"code": "offer_training_draft", "strategy": strategy})
    elif (
        not safety["blocked"]
        and execution["effective"] > 0
        and execution["unavailable"] == 0
    ):
        proposals.append({"code": "keep_current_plan"})
    if nutrition["refresh_available"]:
        proposals.append({"code": "offer_nutrition_refresh"})
    if posture["status"] == "due":
        proposals.append({"code": "posture_recheck_due"})
    elif posture["status"] == "comparison_available":
        proposals.append({"code": "posture_comparison_available"})
    if week == 4:
        proposals.append({"code": "revisit_goal"})
    fingerprint = _canonical_hash(
        {
            "plan_version_id": str(plan.plan_version_id),
            "week_index": week,
            "period_start": period_start,
            "period_end": period_end,
            "facts": facts,
            "proposals": proposals,
            "adaptive_policy_version": training_service.ADAPTIVE_POLICY.policy_version,
            "training_policy_version": training_service.TRAINING_POLICY.policy_version,
            "catalog_version": training_service.catalog().content_version,
            "source_manifest_version": training_service.catalog().source_manifest_version,
        }
    )
    return ReviewAssembly(
        plan=plan,
        period_start=period_start,
        period_end=period_end,
        facts=facts,
        proposals=proposals,
        fingerprint=fingerprint,
    )


async def _latest_review(
    db: AsyncSession, user_id: str, plan_id: uuid.UUID, week: int
) -> Optional[TrainingWeeklyReview]:
    return (
        await db.execute(
            select(TrainingWeeklyReview)
            .where(
                TrainingWeeklyReview.user_id == uuid.UUID(user_id),
                TrainingWeeklyReview.plan_version_id == plan_id,
                TrainingWeeklyReview.week_index == week,
            )
            .order_by(
                TrainingWeeklyReview.review_version.desc(),
                TrainingWeeklyReview.created_at.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def _review_by_id(
    db: AsyncSession, user_id: str, review_id: uuid.UUID
) -> Optional[TrainingWeeklyReview]:
    return (
        await db.execute(
            select(TrainingWeeklyReview).where(
                TrainingWeeklyReview.user_id == uuid.UUID(user_id),
                TrainingWeeklyReview.review_id == review_id,
            )
        )
    ).scalar_one_or_none()


async def _proposal_views(
    db: AsyncSession,
    review: TrainingWeeklyReview,
    *,
    posture_due_dismissed: bool = False,
) -> list[ReviewProposalView]:
    training_origin = (
        await db.execute(
            select(TrainingPlanVersion)
            .where(
                TrainingPlanVersion.user_id == review.user_id,
                TrainingPlanVersion.origin_weekly_review_id == review.review_id,
            )
            .order_by(
                TrainingPlanVersion.created_at.desc(),
                TrainingPlanVersion.plan_version_id.desc(),
            )
        )
    ).scalars().first()
    nutrition_origin = (
        await db.execute(
            select(NutritionRecommendation)
            .where(
                NutritionRecommendation.user_id == review.user_id,
                NutritionRecommendation.origin_weekly_review_id == review.review_id,
            )
            .order_by(NutritionRecommendation.version.desc())
        )
    ).scalars().first()
    result = []
    for proposal in review.proposal_codes:
        if posture_due_dismissed and proposal["code"] == "posture_recheck_due":
            continue
        origin = None
        state = "proposal"
        if proposal["code"] == "offer_training_draft" and training_origin is not None:
            origin = str(review.review_id)
            state = (
                training_origin.status
                if training_origin.status in {"active", "draft"}
                else "unavailable"
            )
        if proposal["code"] == "offer_nutrition_refresh" and nutrition_origin is not None:
            origin = str(review.review_id)
            state = (
                nutrition_origin.status
                if nutrition_origin.status in {"active", "draft"}
                else "unavailable"
            )
        result.append(
            ReviewProposalView(
                code=proposal["code"],
                state=state,
                strategy=proposal.get("strategy"),
                origin_weekly_review_id=origin,
            )
        )
    return result


async def _to_response(
    db: AsyncSession, review: TrainingWeeklyReview
) -> WeeklyReviewResponse:
    facts = review.facts
    posture_facts = facts["posture"]
    posture_due_dismissed = False
    if posture_facts["status"] == "due":
        posture_due_dismissed = (
            await db.scalar(
                select(PostureRecheckDismissal.dismissal_id).where(
                    PostureRecheckDismissal.user_id == review.user_id,
                    PostureRecheckDismissal.plan_version_id
                    == review.plan_version_id,
                )
            )
            is not None
        )
        if posture_due_dismissed:
            posture_facts = {
                "status": "not_due",
                "reason": "dismissed_for_cycle",
            }
    return WeeklyReviewResponse(
        review_id=str(review.review_id),
        plan_version_id=str(review.plan_version_id),
        week_index=review.week_index,
        review_version=review.review_version,
        input_fingerprint=review.input_fingerprint,
        period_start=review.period_start,
        period_end=review.period_end,
        execution=ExecutionFactsView(**facts["execution"]),
        execution_trend=ExecutionTrendView(**facts["execution_trend"]),
        adjustments=AdjustmentFactsView(**facts["adjustments"]),
        weight_trend=WeightTrendView(**facts["weight_trend"]),
        nutrition=NutritionReviewView(**facts["nutrition"]),
        posture=PostureReviewView(
            **{
                key: value
                for key, value in posture_facts.items()
                if not key.startswith("_")
            }
        ),
        safety=ReviewSafetyView(**facts["safety"]),
        proposals=await _proposal_views(
            db,
            review,
            posture_due_dismissed=posture_due_dismissed,
        ),
    )


async def get_review(
    db: AsyncSession, user_id: str, week: int
) -> WeeklyReviewResponse:
    review = (
        await db.execute(
            select(TrainingWeeklyReview)
            .where(
                TrainingWeeklyReview.user_id == uuid.UUID(user_id),
                TrainingWeeklyReview.week_index == week,
            )
            .order_by(
                TrainingWeeklyReview.period_end.desc(),
                TrainingWeeklyReview.created_at.desc(),
                TrainingWeeklyReview.review_version.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if review is None:
        raise AppException(404, "该周尚未生成回顾", "review_not_generated")
    return await _to_response(db, review)


async def _persist_review_core(
    db: AsyncSession,
    user_id: str,
    week: int,
    assembly: ReviewAssembly,
    created_at: datetime,
) -> TrainingWeeklyReview:
    """Insert or reuse one immutable snapshot without locking or committing."""
    existing = (
        await db.execute(
            select(TrainingWeeklyReview).where(
                TrainingWeeklyReview.user_id == uuid.UUID(user_id),
                TrainingWeeklyReview.plan_version_id
                == assembly.plan.plan_version_id,
                TrainingWeeklyReview.week_index == week,
                TrainingWeeklyReview.input_fingerprint == assembly.fingerprint,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    latest = await _latest_review(
        db, user_id, assembly.plan.plan_version_id, week
    )
    review = TrainingWeeklyReview(
        user_id=uuid.UUID(user_id),
        plan_version_id=assembly.plan.plan_version_id,
        week_index=week,
        review_version=(latest.review_version + 1 if latest else 1),
        input_fingerprint=assembly.fingerprint,
        period_start=assembly.period_start,
        period_end=assembly.period_end,
        facts=assembly.facts,
        proposal_codes=assembly.proposals,
        adaptive_policy_version=training_service.ADAPTIVE_POLICY.policy_version,
        training_policy_version=training_service.TRAINING_POLICY.policy_version,
        catalog_version=training_service.catalog().content_version,
        source_manifest_version=training_service.catalog().source_manifest_version,
        created_at=created_at,
    )
    db.add(review)
    await db.flush()
    return review


async def generate_review(
    db: AsyncSession,
    user_id: str,
    week: int,
    request: ReviewGenerateRequest,
    *,
    now: Optional[datetime] = None,
) -> WeeklyReviewResponse:
    current = now or _now()
    await acquire_user_transaction_lock(db, user_id)
    assembly = await _assemble(
        db, user_id, week, request.iana_timezone, current
    )
    request_hash = P.hash_request(
        {
            "operation": P.OP_WEEKLY_REVIEW_GENERATE,
            "plan_version_id": str(assembly.plan.plan_version_id),
            "week_index": week,
            "iana_timezone": request.iana_timezone,
        }
    )
    action, record = await P._check_idempotency(
        db,
        user_id,
        P.OP_WEEKLY_REVIEW_GENERATE,
        request.idempotency_key,
        request_hash,
        current,
    )
    if action == "conflict":
        raise AppException(400, "幂等键已用于其他请求", "idempotency_key_conflict")
    if action == "replay":
        review_id = uuid.UUID(record.result_ref or "")
        await db.rollback()
        review = await _review_by_id(db, user_id, review_id)
        if review is None:
            raise AppException(409, "幂等状态不完整", "idempotency_state_inconsistent")
        return await _to_response(db, review)
    existing = await _persist_review_core(
        db, user_id, week, assembly, current
    )
    await P._record_idempotency(
        db,
        user_id,
        P.OP_WEEKLY_REVIEW_GENERATE,
        request.idempotency_key,
        request_hash,
        str(existing.review_id),
        current,
    )
    await db.commit()
    return await _to_response(db, existing)


async def _require_fresh_review(
    db: AsyncSession,
    user_id: str,
    week: int,
    request: ReviewMutationRequest,
    now: datetime,
) -> tuple[TrainingWeeklyReview, ReviewAssembly]:
    review = await _review_by_id(db, user_id, request.expected_review_id)
    if review is None or review.week_index != week:
        raise AppException(404, "回顾不存在", "not_owner_or_missing_review")
    assembly = await _assemble(db, user_id, week, request.iana_timezone, now)
    if (
        review.input_fingerprint != request.expected_input_fingerprint
        or review.input_fingerprint != assembly.fingerprint
        or review.plan_version_id != assembly.plan.plan_version_id
    ):
        raise AppException(409, "回顾上下文已变化", "stale_context")
    return review, assembly


def training_draft_preferences(
    plan: TrainingPlanVersion, strategy: str
) -> tuple[int, int]:
    """Map one persisted review strategy to one bounded adjacent preference."""
    frequency = plan.weekly_frequency
    duration = plan.session_duration_minutes
    if strategy == "lower_frequency" and frequency > 2:
        frequency -= 1
    elif strategy == "progression":
        if duration < 60:
            duration = {15: 30, 30: 45, 45: 60}[duration]
        elif frequency < 5:
            frequency += 1
        else:
            raise AppException(409, "回顾提案已变化", "stale_context")
    elif strategy in {"conservative_duration", "regression"} and duration > 15:
        duration = {60: 45, 45: 30, 30: 15}[duration]
    else:
        raise AppException(409, "回顾提案已变化", "stale_context")
    return frequency, duration


async def validate_training_draft_confirmation(
    db: AsyncSession,
    user_id: str,
    draft: TrainingPlanVersion,
    *,
    iana_timezone: str,
    now: datetime,
) -> TrainingPlanVersion:
    """Rebind a review-origin draft to the latest immutable review inputs."""
    if draft.origin_weekly_review_id is None:
        raise AppException(409, "回顾来源缺失", "stale_context")
    review = await _review_by_id(db, user_id, draft.origin_weekly_review_id)
    if review is None:
        raise AppException(409, "回顾来源已变化", "stale_context")
    assembly = await _assemble(db, user_id, review.week_index, iana_timezone, now)
    if (
        review.plan_version_id != assembly.plan.plan_version_id
        or review.input_fingerprint != assembly.fingerprint
    ):
        raise AppException(409, "回顾输入已变化", "stale_context")
    proposal = next(
        (
            item
            for item in assembly.proposals
            if item["code"] == "offer_training_draft"
        ),
        None,
    )
    if proposal is None:
        raise AppException(409, "回顾提案已变化", "stale_context")
    frequency, duration = training_draft_preferences(
        assembly.plan, proposal["strategy"]
    )
    if (
        draft.requested_goal != assembly.plan.requested_goal
        or draft.weekly_frequency != frequency
        or draft.session_duration_minutes != duration
    ):
        raise AppException(409, "回顾草案已变化", "stale_context")
    return assembly.plan


async def _prepare_mutation(
    db: AsyncSession,
    user_id: str,
    week: int,
    request: ReviewMutationRequest,
    operation: str,
    now: datetime,
):
    review = await _review_by_id(db, user_id, request.expected_review_id)
    if review is None or review.week_index != week:
        raise AppException(404, "回顾不存在", "not_owner_or_missing_review")
    request_hash = P.hash_request(
        {
            "operation": operation,
            "review_id": str(review.review_id),
            "fingerprint": request.expected_input_fingerprint,
        }
    )
    action, record = await P._check_idempotency(
        db,
        user_id,
        operation,
        request.idempotency_key,
        request_hash,
        now,
    )
    if action == "conflict":
        raise AppException(400, "幂等键已用于其他请求", "idempotency_key_conflict")
    return review, request_hash, action, record


async def create_training_draft(
    db: AsyncSession,
    user_id: str,
    week: int,
    request: ReviewMutationRequest,
    *,
    now: Optional[datetime] = None,
) -> ReviewDraftResponse:
    current = now or _now()
    await acquire_user_transaction_lock(db, user_id)
    review, request_hash, action, idem = await _prepare_mutation(
        db, user_id, week, request, P.OP_REVIEW_TRAINING_DRAFT, current
    )
    if action == "replay":
        draft_id = uuid.UUID(idem.result_ref or "")
        await db.rollback()
        row = await P.get_version_owned(db, user_id, draft_id)
        if (
            row is None
            or row.origin_weekly_review_id != request.expected_review_id
        ):
            raise AppException(409, "幂等状态不完整", "idempotency_state_inconsistent")
        return ReviewDraftResponse(
            review_id=str(request.expected_review_id), draft_id=str(row.plan_version_id),
            status="replayed", origin_weekly_review_id=str(request.expected_review_id),
        )
    review, assembly = await _require_fresh_review(db, user_id, week, request, current)
    proposal = next(
        (item for item in review.proposal_codes if item["code"] == "offer_training_draft"),
        None,
    )
    if proposal is None:
        raise AppException(409, "该回顾没有训练草案提案", "review_action_unavailable")
    strategy = proposal["strategy"]
    frequency, duration = training_draft_preferences(assembly.plan, strategy)
    bodyweight, band = await training_service._profile_equipment(db, user_id)
    evaluation = await training_service.evaluate_review_draft_request(
        db,
        user_id,
        base_fitness_goal=assembly.plan.requested_goal,
        base_weekly_frequency=assembly.plan.weekly_frequency,
        base_session_duration_minutes=assembly.plan.session_duration_minutes,
        fitness_goal=assembly.plan.requested_goal,
        weekly_frequency=frequency,
        session_duration_minutes=duration,
        equipment_bodyweight=bodyweight,
        equipment_resistance_band=band,
        iana_timezone=request.iana_timezone,
        now=current,
    )
    draft_id = await P._persist_draft_core(
        db,
        user_id,
        draft=evaluation.draft,
        weekly_frequency=evaluation.weekly_frequency,
        session_duration_minutes=evaluation.session_duration_minutes,
        decision_gate=evaluation.decision_gate,
        decision_fingerprint=evaluation.decision_fingerprint,
        generated_at=current,
        change_reason="weekly_review_draft",
        origin_weekly_review_id=review.review_id,
    )
    await P._record_idempotency(
        db, user_id, P.OP_REVIEW_TRAINING_DRAFT,
        request.idempotency_key, request_hash, str(draft_id), current,
    )
    await db.commit()
    return ReviewDraftResponse(
        review_id=str(review.review_id), draft_id=str(draft_id), status="created",
        origin_weekly_review_id=str(review.review_id),
    )


async def create_nutrition_draft(
    db: AsyncSession,
    user_id: str,
    week: int,
    request: ReviewMutationRequest,
    *,
    now: Optional[datetime] = None,
) -> ReviewDraftResponse:
    current = now or _now()
    await acquire_user_transaction_lock(db, user_id)
    review, request_hash, action, idem = await _prepare_mutation(
        db, user_id, week, request, P.OP_REVIEW_NUTRITION_DRAFT, current
    )
    if action == "replay":
        draft_id = uuid.UUID(idem.result_ref or "")
        await db.rollback()
        row = await nutrition_persistence.get_owned(db, user_id, draft_id)
        if (
            row is None
            or row.origin_weekly_review_id != request.expected_review_id
        ):
            raise AppException(409, "幂等状态不完整", "idempotency_state_inconsistent")
        return ReviewDraftResponse(
            review_id=str(request.expected_review_id),
            draft_id=str(row.recommendation_id), status="replayed",
            origin_weekly_review_id=str(request.expected_review_id),
        )
    review, _assembly = await _require_fresh_review(db, user_id, week, request, current)
    if not any(
        item["code"] == "offer_nutrition_refresh" for item in review.proposal_codes
    ):
        raise AppException(409, "该回顾没有营养刷新提案", "review_action_unavailable")
    prepared = await nutrition_service.prepare_draft_domain(
        db, user_id, request.iana_timezone
    )
    created = await nutrition_persistence.create_draft_core(
        db,
        user_id,
        payload=prepared.payload,
        pins=prepared.pins,
        now=current,
        origin_weekly_review_id=review.review_id,
    )
    await P._record_idempotency(
        db, user_id, P.OP_REVIEW_NUTRITION_DRAFT,
        request.idempotency_key, request_hash,
        str(created.recommendation_id), current,
    )
    await db.commit()
    return ReviewDraftResponse(
        review_id=str(review.review_id), draft_id=str(created.recommendation_id),
        status="created", origin_weekly_review_id=str(review.review_id),
    )


async def dismiss_posture_recheck(
    db: AsyncSession,
    user_id: str,
    week: int,
    request: ReviewMutationRequest,
    *,
    now: Optional[datetime] = None,
) -> PostureDismissalResponse:
    current = now or _now()
    await acquire_user_transaction_lock(db, user_id)
    review, request_hash, action, idem = await _prepare_mutation(
        db, user_id, week, request, P.OP_POSTURE_RECHECK_DISMISS, current
    )
    if action == "replay":
        dismissal_id = uuid.UUID(idem.result_ref or "")
        await db.rollback()
        row = await db.get(PostureRecheckDismissal, dismissal_id)
        if row is None or row.user_id != uuid.UUID(user_id):
            raise AppException(409, "幂等状态不完整", "idempotency_state_inconsistent")
        return PostureDismissalResponse(
            review_id=str(request.expected_review_id), dismissal_id=str(row.dismissal_id),
            status="replayed",
        )
    review, _assembly = await _require_fresh_review(db, user_id, week, request, current)
    if review.facts["posture"]["status"] != "due":
        raise AppException(409, "当前没有可关闭的体态复查提醒", "review_action_unavailable")
    row = PostureRecheckDismissal(
        user_id=uuid.UUID(user_id),
        plan_version_id=review.plan_version_id,
        due_reason="cycle_complete",
        dismissed_at=current,
        created_at=current,
    )
    db.add(row)
    await db.flush()
    await P._record_idempotency(
        db, user_id, P.OP_POSTURE_RECHECK_DISMISS,
        request.idempotency_key, request_hash, str(row.dismissal_id), current,
    )
    await db.commit()
    return PostureDismissalResponse(
        review_id=str(review.review_id), dismissal_id=str(row.dismissal_id),
        status="recorded",
    )


__all__ = [
    "training_proposal",
    "get_review",
    "generate_review",
    "create_training_draft",
    "create_nutrition_draft",
    "dismiss_posture_recheck",
]
