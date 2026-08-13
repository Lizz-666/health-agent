"""Pure builders for immutable Phase 7 execution overlays."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Optional

from app.training.adaptive_policy import AdaptivePolicy
from app.training.knowledge import build_index
from app.training.schemas import (
    CandidateResult,
    Exercise,
    ExerciseCatalog,
    PlanPrescription,
    PlanSession,
    TrainingPlanDraft,
)


@dataclass(frozen=True)
class OverlayItem:
    source_index: Optional[int]
    action: str
    prescription: Optional[PlanPrescription]
    display_order: int


@dataclass(frozen=True)
class OverlayCandidate:
    draft: TrainingPlanDraft
    items: tuple[OverlayItem, ...]
    target_local_date: Optional[date] = None
    target_minutes: Optional[int] = None


def _session(
    draft: TrainingPlanDraft, week_index: int, day_of_week: int
) -> Optional[PlanSession]:
    return next((
        item for item in draft.sessions
        if item.week_index == week_index and item.day_of_week == day_of_week
    ), None)


def _roles(exercise: Exercise) -> set[str]:
    return {role.value for role in exercise.training_roles}


def _minimum_prescription(exercise: Exercise) -> PlanPrescription:
    bounds = exercise.prescription
    return PlanPrescription(
        exercise_id=exercise.exercise_id,
        sets=bounds.sets_min,
        reps=bounds.reps_min if bounds.mode.value == "reps" else None,
        duration_seconds=(
            bounds.duration_seconds_min
            if bounds.mode.value == "duration"
            else None
        ),
        rest_seconds=bounds.rest_seconds_min,
    )


def build_shortened_overlay(
    draft: TrainingPlanDraft,
    *,
    week_index: int,
    day_of_week: int,
    target_minutes: int,
    adaptive_policy: AdaptivePolicy,
    catalog: ExerciseCatalog,
) -> Optional[OverlayCandidate]:
    """Drop only lower-ranked items while preserving warm-up and one priority."""
    cap = adaptive_policy.exercise_caps.get(target_minutes)
    source = _session(draft, week_index, day_of_week)
    if source is None or cap is None:
        return None
    index = build_index(catalog)
    required = [
        idx for idx, prescription in enumerate(source.prescriptions)
        if prescription.exercise_id in index
        and _roles(index[prescription.exercise_id]) & set(adaptive_policy.required_roles)
    ]
    priority = [
        idx for idx, prescription in enumerate(source.prescriptions)
        if prescription.exercise_id in index and idx not in required
    ]
    if not required or not priority:
        return None
    keep = (
        set(range(len(source.prescriptions)))
        if len(source.prescriptions) <= cap
        else set(required[:1] + priority[:1])
    )
    for idx in range(len(source.prescriptions)):
        if len(keep) >= cap:
            break
        keep.add(idx)
    if len(keep) > cap:
        return None

    effective = draft.model_copy(deep=True)
    target = _session(effective, week_index, day_of_week)
    assert target is not None
    kept_prescriptions = [
        prescription.model_copy(deep=True)
        for idx, prescription in enumerate(source.prescriptions)
        if idx in keep
    ]
    target.prescriptions = kept_prescriptions
    target.target_minutes = target_minutes
    items = []
    display_order = 0
    for idx, prescription in enumerate(source.prescriptions):
        if idx in keep:
            items.append(OverlayItem(
                source_index=idx,
                action="keep",
                prescription=prescription.model_copy(deep=True),
                display_order=display_order,
            ))
            display_order += 1
        else:
            items.append(OverlayItem(
                source_index=idx,
                action="drop",
                prescription=None,
                display_order=display_order,
            ))
            display_order += 1
    return OverlayCandidate(
        draft=effective,
        items=tuple(items),
        target_minutes=target_minutes,
    )


def build_recovery_overlays(
    draft: TrainingPlanDraft,
    *,
    week_index: int,
    day_of_week: int,
    adaptive_policy: AdaptivePolicy,
    catalog: ExerciseCatalog,
    candidates: CandidateResult,
) -> list[OverlayCandidate]:
    """Return deterministic complete recovery snapshots for later validation."""
    source = _session(draft, week_index, day_of_week)
    if source is None:
        return []
    index = build_index(catalog)
    allowed_ids = [candidate.exercise_id for candidate in candidates.candidates]
    allowed = [index[item] for item in allowed_ids if item in index]
    warmups = [
        item for item in allowed
        if "warmup" in _roles(item) and _roles(item) & set(adaptive_policy.recovery_roles)
    ]
    recovery = [
        item for item in allowed
        if _roles(item) & {"mobility", "recovery"}
    ]
    results: list[OverlayCandidate] = []
    for warmup in warmups:
        for secondary in recovery:
            if secondary.exercise_id == warmup.exercise_id:
                continue
            related = set(
                warmup.progression_ids
                + warmup.regression_ids
                + warmup.substitution_ids
            )
            if secondary.exercise_id in related:
                continue
            prescriptions = [
                _minimum_prescription(warmup),
                _minimum_prescription(secondary),
            ]
            effective = draft.model_copy(deep=True)
            target = _session(effective, week_index, day_of_week)
            assert target is not None
            target.prescriptions = prescriptions
            results.append(OverlayCandidate(
                draft=effective,
                items=tuple(
                    OverlayItem(None, "replace", prescription, idx)
                    for idx, prescription in enumerate(prescriptions)
                ),
                target_minutes=target.target_minutes,
            ))
    return results


def _reorder_week(draft: TrainingPlanDraft, week_index: int) -> None:
    week = sorted(
        (session for session in draft.sessions if session.week_index == week_index),
        key=lambda session: session.day_of_week,
    )
    for order, session in enumerate(week, start=1):
        session.session_order = order


def build_deferral_overlays(
    draft: TrainingPlanDraft,
    *,
    source_week_index: int,
    source_day_of_week: int,
    source_local_date: date,
    occupied_dates: Iterable[date],
) -> list[OverlayCandidate]:
    """Move one source session to each future free date, earliest first."""
    source = _session(draft, source_week_index, source_day_of_week)
    if source is None:
        return []
    plan_start = source_local_date - timedelta(
        days=(source_week_index - 1) * 7 + source_day_of_week - 1
    )
    plan_end = plan_start + timedelta(days=27)
    occupied = set(occupied_dates)
    results = []
    candidate_date = source_local_date + timedelta(days=1)
    while candidate_date <= plan_end:
        if candidate_date not in occupied:
            offset = (candidate_date - plan_start).days
            effective = draft.model_copy(deep=True)
            target = _session(effective, source_week_index, source_day_of_week)
            assert target is not None
            old_week = target.week_index
            target.week_index = offset // 7 + 1
            target.day_of_week = offset % 7 + 1
            _reorder_week(effective, old_week)
            if target.week_index != old_week:
                _reorder_week(effective, target.week_index)
            results.append(OverlayCandidate(
                draft=effective,
                items=(),
                target_local_date=candidate_date,
                target_minutes=target.target_minutes,
            ))
        candidate_date += timedelta(days=1)
    return results


def occupied_plan_dates(draft: TrainingPlanDraft, plan_start: date) -> set[date]:
    return {
        plan_start + timedelta(
            days=(session.week_index - 1) * 7 + session.day_of_week - 1
        )
        for session in draft.sessions
    }


__all__ = [
    "OverlayCandidate",
    "OverlayItem",
    "build_deferral_overlays",
    "build_recovery_overlays",
    "build_shortened_overlay",
    "occupied_plan_dates",
]
