import pytest

from app.nutrition.portions import project_portion, supported_portion_codes


def test_all_reviewed_household_units_are_bounded_and_approximate():
    assert len(supported_portion_codes()) == 6
    for code in supported_portion_codes():
        result = project_portion(code)
        assert result.amount_min < result.amount_max
        assert result.approximate is True
        assert result.limitation_code


def test_exact_reviewed_ranges():
    assert project_portion("small_bowl_cooked_staple").model_dump() == {
        "unit_code": "small_bowl_cooked_staple", "amount_min": 150,
        "amount_max": 200, "unit_label": "g", "approximate": True,
        "limitation_code": "bowl_size_and_absorption_vary",
    }
    assert project_portion("cup_dairy").amount_min == 250
    assert project_portion("thumb_nuts").amount_max == 12


def test_unknown_household_unit_fails_closed():
    with pytest.raises(ValueError, match="unsupported"):
        project_portion("one_exact_plate")
