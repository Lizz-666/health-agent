from pathlib import Path

import pytest

from app.nutrition.calculator import calculate_targets
from app.nutrition.generator import (
    NutritionGenerationError,
    generate_recommendation,
    preview_replacement,
)
from app.nutrition.knowledge import (
    load_catalog,
    load_media_manifest,
    load_policy,
)
from app.nutrition.schemas import (
    DayKind,
    GateStatus,
    MealName,
    NutritionDecision,
    NutritionVersions,
)
from app.nutrition.validator import validate_recommendation

DATA = Path(__file__).resolve().parents[1] / "app/nutrition/data"
VERSIONS = NutritionVersions(
    policy_version="v1",
    catalog_version="v1",
    source_manifest_version="v1",
    media_manifest_version="v1",
)


def _decision(gate: GateStatus = GateStatus.eligible) -> NutritionDecision:
    return NutritionDecision(
        gate=gate,
        reason_codes=["supported_scope"],
        context_fingerprint="a" * 64,
    )


def _generate(*, goal="posture_improvement", allergens=frozenset(), excluded=frozenset()):
    catalog = load_catalog(DATA / "foods.v1.json")
    policy = load_policy(DATA / "nutrition_policy.v1.json")
    media = load_media_manifest(DATA / "media_manifest.v1.json")
    payload = generate_recommendation(
        catalog=catalog,
        policy=policy,
        media_manifest=media,
        decision=_decision(),
        targets=calculate_targets(65, 170, 30),
        versions=VERSIONS,
        requested_goal=goal,
        allergen_codes=set(allergens),
        excluded_food_ids=set(excluded),
    )
    return payload, catalog, policy, media


def test_generator_is_deterministic_complete_and_independently_validated():
    first, catalog, policy, media = _generate()
    second, *_ = _generate()
    assert first == second
    assert {variant.day_kind.value for variant in first.variants} == {
        "training_day", "rest_day"
    }
    assert all(
        [meal.meal.value for meal in variant.meals]
        == ["breakfast", "lunch", "dinner"]
        for variant in first.variants
    )
    result = validate_recommendation(
        first, catalog, policy, media, _decision(), VERSIONS, set(), set()
    )
    assert result.valid, result.issues


def test_goal_and_day_kind_have_explicit_deterministic_differences():
    posture, *_ = _generate(goal="posture_improvement")
    strength, *_ = _generate(goal="basic_strength")
    assert posture != strength
    assert posture.variants[0] != posture.variants[1]
    assert "goal_posture_improvement" in posture.variants[0].rationale_codes
    assert "goal_basic_strength" in strength.variants[0].rationale_codes


def test_selected_foods_have_two_safe_alternatives_where_catalog_permits():
    payload, *_ = _generate(excluded={"beef_tenderloin"})
    alternative_counts = []
    for variant in payload.variants:
        for meal in variant.meals:
            for item in meal.items:
                alternative_counts.append(len(item.alternatives))
                assert all(alt.food_id != item.food_id for alt in item.alternatives)
                assert all(alt.food_id != "beef_tenderloin" for alt in item.alternatives)
    assert max(alternative_counts) >= 2


@pytest.mark.parametrize(
    "allergens",
    [{"gluten_cereal"}, {"egg"}, {"milk"}, {"soy"}],
)
def test_generator_fails_closed_when_required_safe_group_is_incomplete(allergens):
    with pytest.raises(NutritionGenerationError) as exc:
        _generate(allergens=allergens)
    assert exc.value.code == "no_safe_candidate"


def test_validator_rejects_allergen_leak_version_staleness_and_tampering():
    payload, catalog, policy, media = _generate()
    leaked = payload.model_copy(deep=True)
    leaked.variants[0].meals[0].items[0].food_id = "egg_chicken"
    result = validate_recommendation(
        leaked, catalog, policy, media, _decision(), VERSIONS, {"egg"}, set()
    )
    assert not result.valid
    assert "allergen_intersection" in {issue.code for issue in result.issues}

    stale = VERSIONS.model_copy(update={"catalog_version": "v2"})
    result = validate_recommendation(
        payload, catalog, policy, media, _decision(), stale, set(), set()
    )
    assert not result.valid
    assert "stale_version" in {issue.code for issue in result.issues}

    tampered = payload.model_copy(deep=True)
    tampered.variants[0].meals[0].items[0].household_portion.amount_min += 1
    result = validate_recommendation(
        tampered, catalog, policy, media, _decision(), VERSIONS, set(), set()
    )
    assert not result.valid
    assert "catalog_projection_mismatch" in {issue.code for issue in result.issues}


def test_recommendation_schema_contains_no_intake_or_completion_state():
    payload, *_ = _generate()
    serialized = str(payload.model_dump(mode="json")).lower()
    for forbidden in ("eaten", "consumed", "completed", "meal_event", "intake_quantity"):
        assert forbidden not in serialized
    assert "reference_center_kcal" not in serialized

    invalid = payload.model_dump(mode="json")
    invalid["guideline_source_codes"] = ["free text is not a stable code"]
    with pytest.raises(ValueError, match="stable codes"):
        type(payload).model_validate(invalid)


def test_replacement_preview_is_typed_equivalent_and_revalidated():
    payload, catalog, policy, media = _generate()
    item = payload.variants[0].meals[1].items[1]
    target = item.alternatives[0].food_id
    preview = preview_replacement(
        payload,
        catalog=catalog,
        policy=policy,
        day_kind=DayKind.training_day,
        meal=MealName.lunch,
        item_index=1,
        from_food_id=item.food_id,
        to_food_id=target,
        allergen_codes=set(),
        excluded_food_ids=set(),
    )
    assert payload.variants[0].meals[1].items[1].food_id == item.food_id
    assert preview.variants[0].meals[1].items[1].food_id == target
    assert preview.replacement_diff.from_food_id == item.food_id
    result = validate_recommendation(
        preview, catalog, policy, media, _decision(), VERSIONS, set(), set()
    )
    assert result.valid, result.issues


def test_replacement_preview_rejects_non_allowlisted_candidate():
    payload, catalog, policy, *_ = _generate()
    item = payload.variants[0].meals[0].items[0]
    with pytest.raises(NutritionGenerationError) as exc:
        preview_replacement(
            payload,
            catalog=catalog,
            policy=policy,
            day_kind=DayKind.training_day,
            meal=MealName.breakfast,
            item_index=0,
            from_food_id=item.food_id,
            to_food_id="egg_chicken",
            allergen_codes=set(),
            excluded_food_ids=set(),
        )
    assert exc.value.code == "invalid_replacement"
