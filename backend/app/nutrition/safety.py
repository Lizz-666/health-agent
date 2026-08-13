"""Fail-closed deterministic nutrition eligibility classification."""
from __future__ import annotations

import hashlib
import json

from app.nutrition.calculator import bmi_category, calculate_bmi, calculate_targets
from app.nutrition.schemas import GateStatus, NutritionContext, NutritionDecision

RISK_FIELDS = (
    "underage",
    "pregnancy_or_postpartum",
    "recent_surgery_or_major_injury",
    "major_chronic_condition",
    "eating_disorder_concern",
    "professional_instruction_limitations",
)
SUPPORTED_GOALS = {"posture_improvement", "fat_loss", "basic_strength"}


def compose_context_fingerprint(context: NutritionContext) -> str:
    """Hash only stable versions, state codes and owned references.

    Raw body values, allergy labels, notes and the user identifier are excluded.
    """
    payload = {
        "account_updated_at": context.account_updated_at.isoformat()
        if context.account_updated_at else None,
        "weight_source_kind": context.weight_source.kind if context.weight_source else None,
        "weight_record_id": context.weight_source.record_id if context.weight_source else None,
        "weight_timestamp": context.weight_source.timestamp.isoformat()
        if context.weight_source else None,
        "weight_recorded_at": context.weight_source.recorded_at.isoformat()
        if context.weight_source and context.weight_source.recorded_at else None,
        "profile_version": context.profile_version,
        "profile_updated_at": context.profile_updated_at.isoformat()
        if context.profile_updated_at else None,
        "risk_answers": context.risk_screen,
        "allergen_codes": sorted(x.value for x in (context.food_allergen_codes or [])),
        "exclusion_codes": sorted(context.excluded_food_codes or []),
        "legacy_allergy_present": context.has_legacy_allergies,
        "legacy_exclusion_present": context.has_legacy_diet_exclusions,
        "checkin_token": context.checkin_token,
        "checkin_risk": context.checkin_risk,
        "posture_risk": context.posture_risk,
        "active_plan_present": context.active_plan_present,
        "active_plan_goal": context.active_plan_goal,
        "active_plan_version_id": context.active_plan_version_id,
        "training_decision_gate": context.training_decision_gate,
        "day_kind": context.day_kind.value if context.day_kind else None,
        "current_local_date": context.current_local_date.isoformat(),
        "iana_timezone": context.iana_timezone,
        "versions": context.versions.model_dump(mode="json"),
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def classify_nutrition(context: NutritionContext, allowed_exclusions: set[str]) -> NutritionDecision:
    reasons: list[str] = []
    missing: list[str] = []

    red = context.checkin_risk == "red_flag" or context.posture_risk == "red_flag"
    if red:
        reasons.append("current_safety_red_flag")

    risk = context.risk_screen
    restricted = bool(context.age is not None and context.age < 18)
    if restricted:
        reasons.append("age_under_18")
    if risk is not None:
        for field in RISK_FIELDS:
            if risk.get(field) == "yes":
                restricted = True
                reasons.append("risk_screen_yes:" + field)

    if context.age is None:
        missing.append("age")
    if context.height_cm is None:
        missing.append("height_cm")
    if context.weight_source is None:
        missing.append("weight")
    if context.profile_version is None or context.profile_updated_at is None:
        missing.append("health_profile_version")
    if risk is None:
        missing.append("risk_screen")
    else:
        for field in RISK_FIELDS:
            if risk.get(field) not in {"yes", "no"}:
                missing.append("risk_screen." + field)
    if context.food_allergen_codes is None:
        missing.append("food_allergen_codes")
    if context.excluded_food_codes is None:
        missing.append("excluded_food_codes")
    elif any(code not in allowed_exclusions for code in context.excluded_food_codes):
        missing.append("excluded_food_codes")
    if context.has_legacy_allergies:
        missing.append("legacy_allergies")
    if context.has_legacy_diet_exclusions:
        missing.append("legacy_diet_exclusions")
    if not context.checkin_present or not context.checkin_token:
        missing.append("current_day_checkin")
    elif context.checkin_risk not in {"normal", "caution", "restricted", "red_flag"}:
        missing.append("current_day_checkin")
    if not context.active_plan_present:
        missing.append("active_training_plan")
    if context.training_decision_gate not in {"eligible", "eligible_conservative"}:
        missing.append("training_decision_gate")
    if context.active_plan_goal not in SUPPORTED_GOALS:
        missing.append("active_plan_goal")
    if context.day_kind is None:
        missing.append("effective_training_day_state")
    for field, value in context.versions.model_dump().items():
        if not value:
            missing.append(field)

    age_limited = context.age == 18 or (
        context.age is not None and context.age > 64
    )
    limited = age_limited
    conservative = context.checkin_risk == "caution"
    category = None
    if not any(x in missing for x in ("age", "height_cm", "weight")):
        assert context.age is not None and context.height_cm is not None
        assert context.weight_source is not None
        try:
            bmi = calculate_bmi(context.weight_source.weight_kg, context.height_cm)
        except ValueError:
            missing.append("body_measurements_out_of_range")
        else:
            category = bmi_category(bmi)
            conservative = conservative or category == "supported_conservative"
            bmi_limited = category in {"below_scope", "above_scope"}
            limited = limited or bmi_limited
            if not restricted and not age_limited and not bmi_limited:
                try:
                    targets = calculate_targets(
                        context.weight_source.weight_kg,
                        context.height_cm,
                        context.age,
                    )
                except ValueError:
                    missing.append("body_measurements_out_of_range")
                else:
                    limited = limited or not (
                        1600 <= targets.reference_center_kcal <= 2400
                    )

    fingerprint = compose_context_fingerprint(context)
    if red:
        gate = GateStatus.red_flag
    elif restricted or context.checkin_risk == "restricted" or context.posture_risk == "restricted":
        gate = GateStatus.restricted
    elif limited:
        gate = GateStatus.limited_education
        reasons.append("outside_personalized_scope")
    elif missing:
        gate = GateStatus.clarification_required
        reasons.append("required_context_incomplete")
    elif conservative:
        gate = GateStatus.eligible_conservative
        reasons.append("conservative_template_required")
    else:
        gate = GateStatus.eligible
        reasons.append("supported_scope")
    return NutritionDecision(
        gate=gate,
        reason_codes=sorted(set(reasons)),
        missing_field_codes=sorted(set(missing)),
        bmi_category=category,
        context_fingerprint=fingerprint,
    )
