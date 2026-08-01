import math

import pytest

from app.nutrition.calculator import bmi_category, calculate_bmi, calculate_targets


def test_formula_golden_vector_and_outward_rounding():
    result = calculate_targets(65, 170, 30)
    assert result.reference_center_kcal == pytest.approx(2078.3)
    assert result.energy_low_kcal == 1700
    assert result.energy_high_kcal == 2500
    assert result.uncertainty_code == "product_estimate_band_not_confidence_interval"


def test_formula_spans_both_published_branches_without_gender_input():
    result = calculate_targets(60, 165, 40)
    common = 10 * 60 + 6.25 * 165 - 5 * 40
    assert result.reference_center_kcal == pytest.approx((common + (-161 + 5) / 2) * 1.40)
    assert "gender" not in calculate_targets.__annotations__


@pytest.mark.parametrize("weight,height,age", [
    (0, 170, 30), (-1, 170, 30), (math.nan, 170, 30),
    (65, 0, 30), (65, math.inf, 30), (65, 170, 0), (65, 170, 30.5),
])
def test_formula_rejects_missing_invalid_or_non_finite_inputs(weight, height, age):
    with pytest.raises(ValueError):
        calculate_targets(weight, height, age)


@pytest.mark.parametrize("bmi,expected", [
    (18.49, "below_scope"), (18.5, "supported"), (23.999, "supported"),
    (24, "supported_conservative"), (27.999, "supported_conservative"),
    (28, "above_scope"),
])
def test_bmi_scope_boundaries(bmi, expected):
    assert bmi_category(bmi) == expected


def test_bmi_uses_metric_height():
    assert calculate_bmi(74, 200) == pytest.approx(18.5)
