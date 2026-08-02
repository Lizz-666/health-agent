"""Pure, sex-independent Phase 6 nutrition target calculations."""
from __future__ import annotations

import math

from app.nutrition.schemas import NutritionTargets

PAL = 1.40


def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    if not all(math.isfinite(v) and v > 0 for v in (weight_kg, height_cm)):
        raise ValueError("body inputs must be positive finite numbers")
    # Normalize binary floating-point noise before policy threshold checks so
    # mathematically exact boundaries (18.5/24/28) are stable across runtimes.
    return round(weight_kg / ((height_cm / 100.0) ** 2), 6)


def bmi_category(bmi: float) -> str:
    if not math.isfinite(bmi):
        raise ValueError("BMI must be finite")
    if bmi < 18.5:
        return "below_scope"
    if bmi < 24:
        return "supported"
    if bmi < 28:
        return "supported_conservative"
    return "above_scope"


def calculate_targets(weight_kg: float, height_cm: float, age: int) -> NutritionTargets:
    if not isinstance(age, int) or isinstance(age, bool) or age <= 0:
        raise ValueError("age must be a positive integer")
    if not all(math.isfinite(v) and v > 0 for v in (weight_kg, height_cm)):
        raise ValueError("body inputs must be positive finite numbers")
    common = 10 * weight_kg + 6.25 * height_cm - 5 * age
    lower_reference = (common - 161) * PAL
    upper_reference = (common + 5) * PAL
    center = common * PAL + ((-161 + 5) / 2) * PAL
    if min(lower_reference, upper_reference, center) <= 0:
        raise ValueError("formula result is outside the supported domain")
    display_low = math.floor((lower_reference * 0.90) / 100) * 100
    display_high = math.ceil((upper_reference * 1.10) / 100) * 100
    return NutritionTargets(
        energy_low_kcal=display_low,
        energy_high_kcal=display_high,
        reference_center_kcal=center,
        limitation_codes=[
            "estimate_not_measured_expenditure",
            "heat_exercise_illness_medication_change_needs",
            "not_micronutrient_adequacy",
        ],
    )
