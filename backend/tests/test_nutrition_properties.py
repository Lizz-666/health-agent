from pathlib import Path

import pytest

from app.nutrition.calculator import calculate_targets
from app.nutrition.generator import (
    NutritionGenerationError,
    generate_recommendation,
    preview_replacement,
)
from app.nutrition.knowledge import load_catalog, load_media_manifest, load_policy
from app.nutrition.schemas import GateStatus, NutritionDecision, NutritionVersions
from app.nutrition.validator import validate_recommendation

DATA = Path(__file__).resolve().parents[1] / "app/nutrition/data"
CATALOG = load_catalog(DATA / "foods.v1.json")
POLICY = load_policy(DATA / "nutrition_policy.v1.json")
MEDIA = load_media_manifest(DATA / "media_manifest.v1.json")
VERSIONS = NutritionVersions(
    policy_version="v1",
    catalog_version="v1",
    source_manifest_version="v1",
    media_manifest_version="v1",
)
DECISION = NutritionDecision(
    gate=GateStatus.eligible,
    reason_codes=["supported_scope"],
    context_fingerprint="a" * 64,
)


def _generate(allergens: set[str], excluded: set[str]):
    return generate_recommendation(
        catalog=CATALOG,
        policy=POLICY,
        media_manifest=MEDIA,
        decision=DECISION,
        targets=calculate_targets(65, 170, 30),
        versions=VERSIONS,
        requested_goal="posture_improvement",
        allergen_codes=allergens,
        excluded_food_ids=excluded,
    )


@pytest.mark.parametrize("allergen", [code.value for code in POLICY.allergen_codes])
def test_complete_allergen_matrix_never_leaks_blocked_food(allergen):
    try:
        payload = _generate({allergen}, set())
    except NutritionGenerationError as exc:
        assert exc.code == "no_safe_candidate"
        return
    result = validate_recommendation(
        payload, CATALOG, POLICY, MEDIA, DECISION, VERSIONS, {allergen}, set()
    )
    assert result.valid, result.issues
    selected = {
        item.food_id
        for variant in payload.variants
        for meal in variant.meals
        for item in meal.items
    }
    blocked = {
        food.food_id
        for food in CATALOG.foods
        if allergen in {code.value for code in food.allergen_codes}
    }
    assert selected.isdisjoint(blocked)


@pytest.mark.parametrize("exclusion", [code.value for code in POLICY.exclusion_food_ids])
def test_supported_exclusions_are_expanded_by_policy_not_substring(exclusion):
    blocked = {
        food_id
        for code, food_ids in POLICY.exclusion_food_ids.items()
        if code.value == exclusion
        for food_id in food_ids
    }
    payload = _generate(set(), blocked)
    selected = {
        item.food_id
        for variant in payload.variants
        for meal in variant.meals
        for item in meal.items
    }
    assert selected.isdisjoint(blocked)


def test_every_exposed_replacement_preserves_the_full_validator():
    payload = _generate(set(), set())
    checked = 0
    for variant in payload.variants:
        for meal in variant.meals:
            for item_index, item in enumerate(meal.items):
                for alternative in item.alternatives:
                    preview = preview_replacement(
                        payload,
                        catalog=CATALOG,
                        policy=POLICY,
                        day_kind=variant.day_kind,
                        meal=meal.meal,
                        item_index=item_index,
                        from_food_id=item.food_id,
                        to_food_id=alternative.food_id,
                        allergen_codes=set(),
                        excluded_food_ids=set(),
                    )
                    result = validate_recommendation(
                        preview,
                        CATALOG,
                        POLICY,
                        MEDIA,
                        DECISION,
                        VERSIONS,
                        set(),
                        set(),
                    )
                    assert result.valid, result.issues
                    checked += 1
    assert checked >= 12
