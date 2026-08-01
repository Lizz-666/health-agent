from pathlib import Path

from app.nutrition.knowledge import load_catalog
from app.nutrition.schemas import (
    GateStatus, NutritionDecision, NutritionVersions,
)
from app.nutrition.validator import validate_food_selection, validate_versions

DATA = Path(__file__).resolve().parents[1] / "app/nutrition/data"


def _decision(gate=GateStatus.eligible):
    return NutritionDecision(gate=gate, reason_codes=[], context_fingerprint="a" * 64)


def test_validator_rejects_unknown_blocked_allergen_and_explicit_exclusion():
    catalog = load_catalog(DATA / "foods.v1.json")
    result = validate_food_selection(
        ["missing", "egg_chicken", "pork_tenderloin"], catalog,
        _decision(GateStatus.clarification_required), {"egg"}, {"pork_tenderloin"},
    )
    assert result.valid is False
    assert {issue.code for issue in result.issues} == {
        "safety_gate_blocked", "unknown_food", "allergen_intersection",
        "explicit_exclusion_intersection",
    }


def test_validator_accepts_safe_reviewed_selection():
    catalog = load_catalog(DATA / "foods.v1.json")
    assert validate_food_selection(
        ["rice_white", "broccoli", "apple_raw"], catalog, _decision(), set(), set()
    ).valid


def test_every_version_pin_is_checked_independently():
    expected = NutritionVersions(
        policy_version="v1", catalog_version="v1",
        source_manifest_version="v1", media_manifest_version="v1")
    for field in expected.model_fields:
        changed = expected.model_copy(update={field: "v2"})
        result = validate_versions(expected, changed)
        assert not result.valid
        assert [issue.path for issue in result.issues] == [field]
