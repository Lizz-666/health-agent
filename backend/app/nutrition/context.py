"""Assemble current owned nutrition context through existing domain services."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import get_user_by_id
from app.health import service as health_service
from app.health.risk import classify_checkin, restricted_reason
from app.nutrition.schemas import (
    DayKind,
    NutritionContext,
    NutritionVersions,
    WeightSource,
)
from app.training import service as training_service
from app.training.context import (
    checkin_token as training_checkin_token,
    derive_local_date,
    validate_iana_timezone,
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def resolve_nutrition_context(
    db: AsyncSession,
    user_id: str,
    iana_timezone: str,
    versions: NutritionVersions,
    *,
    now: datetime | None = None,
) -> NutritionContext:
    if not validate_iana_timezone(iana_timezone):
        raise ValueError("invalid IANA timezone")
    evaluated_at = _utc(now or datetime.now(timezone.utc))
    local_date = derive_local_date(evaluated_at, iana_timezone)
    if local_date is None:
        raise ValueError("could not derive current local date")

    user = await get_user_by_id(db, user_id)
    profile_result = await health_service.get_profile_result(db, user_id)
    profile = profile_result.profile
    manual_weight = await health_service.get_latest_manual_weight_at(
        db, user_id, evaluated_at
    )
    weight_source = None
    if manual_weight is not None:
        weight_source = WeightSource(
            kind="manual_record",
            record_id=str(manual_weight.id),
            recorded_at=manual_weight.recorded_at,
            timestamp=manual_weight.updated_at,
            weight_kg=manual_weight.weight_kg,
        )
    elif user is not None and user.weight is not None:
        weight_source = WeightSource(
            kind="account",
            timestamp=user.updated_at,
            weight_kg=user.weight,
        )

    checkins = await health_service.list_checkins(
        db, user_id, start_date=local_date, end_date=local_date
    )
    checkin = checkins[0] if checkins else None
    checkin_token = None
    checkin_risk = None
    if checkin is not None:
        qualifier = restricted_reason(profile) if profile is not None else None
        recomputed = classify_checkin(checkin, restricted_qualifier=qualifier)
        checkin_risk = recomputed.risk_summary
        checkin_token = training_checkin_token(checkin, checkin_risk)

    active = await training_service.get_active(db, user_id)
    today = await training_service.get_today(
        db, user_id, iana_timezone, now=evaluated_at
    )
    active_goal = active.plan.requested_goal if active.plan is not None else None
    active_id = active.plan.plan_version_id if active.plan is not None else None
    day_kind = None
    if today.state == "session":
        day_kind = DayKind.training_day
    elif today.state == "rest_day":
        day_kind = DayKind.rest_day

    risk_screen = None
    allergens = None
    exclusions = None
    legacy_allergies = False
    legacy_exclusions = False
    if profile is not None:
        risk_screen = (
            profile.risk_screen.model_dump(mode="json")
            if profile.risk_screen is not None else None
        )
        allergens = profile.food_allergen_codes
        exclusions = [x.value for x in profile.excluded_food_codes] \
            if profile.excluded_food_codes is not None else None
        legacy_allergies = bool(profile.allergies)
        legacy_exclusions = bool(profile.diet_exclusions)

    blocked_risk = today.decision_gate if today.state == "blocked" else None
    return NutritionContext(
        age=user.age if user is not None else None,
        height_cm=user.height if user is not None else None,
        account_updated_at=user.updated_at if user is not None else None,
        weight_source=weight_source,
        profile_version=profile.version if profile is not None else None,
        profile_updated_at=profile.updated_at if profile is not None else None,
        risk_screen=risk_screen,
        food_allergen_codes=allergens,
        excluded_food_codes=exclusions,
        has_legacy_allergies=legacy_allergies,
        has_legacy_diet_exclusions=legacy_exclusions,
        checkin_present=checkin is not None,
        checkin_risk=checkin_risk,
        checkin_token=checkin_token,
        posture_risk=blocked_risk,
        active_plan_present=active.has_active and today.state not in {
            "no_active_plan", "plan_complete", "blocked"
        },
        active_plan_goal=active_goal,
        active_plan_version_id=active_id,
        training_decision_gate=today.decision_gate,
        day_kind=day_kind,
        current_local_date=local_date,
        iana_timezone=iana_timezone,
        versions=versions,
    )
