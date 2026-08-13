"""Deterministic, catalog-only nutrition recommendation composition."""
from __future__ import annotations

from app.nutrition.portions import project_portion
from app.nutrition.schemas import (
    DayKind,
    DayMealRecommendation,
    DailyFoodGroupSummary,
    FoodAlternative,
    FoodCatalog,
    FoodRecord,
    GateStatus,
    MealFoodItem,
    MealName,
    MealTemplate,
    MediaManifest,
    NutritionDecision,
    NutritionPolicy,
    NutritionTargetRanges,
    NutritionTargets,
    NutritionVersions,
    RecommendationPayload,
    ReplacementDiff,
)


class NutritionGenerationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


_GOAL_PROTEINS = {
    "posture_improvement": ("chicken_breast", "beef_tenderloin", "pork_tenderloin"),
    "fat_loss": ("pork_tenderloin", "chicken_breast", "beef_tenderloin"),
    "basic_strength": ("beef_tenderloin", "chicken_breast", "pork_tenderloin"),
}
_GUIDELINE_EQUIVALENTS = {
    "staple_grain": 70,
    "tuber": 75,
    "vegetable": 125,
    "fruit": 175,
    "animal_protein": 100,
    "egg": 50,
    "dairy": 300,
    "soy_nut": 25,
}
def _apply_group_amount(
    values: dict[str, int],
    food: FoodRecord,
    amount: int,
    whole_grain_ids: set[str],
) -> None:
    if food.category.value == "grain":
        values["grains"] += amount
        if food.food_id in whole_grain_ids:
            values["whole_grains_mixed_beans"] += amount
    elif food.category.value == "tuber":
        values["tubers"] += amount
    elif food.category.value == "vegetable":
        values["vegetables"] += amount
    elif food.category.value == "fruit":
        values["fruit"] += amount
    elif food.category.value in {"animal_protein", "egg"}:
        values["animal_foods"] += amount
    elif food.category.value == "dairy":
        values["dairy_ml"] += amount
    elif food.category.value in {"soy", "nut"}:
        values["soy_nuts"] += amount


def _safe_groups(
    catalog: FoodCatalog,
    allergen_codes: set[str],
    excluded_food_ids: set[str],
) -> dict[str, list[FoodRecord]]:
    groups: dict[str, list[FoodRecord]] = {}
    for food in catalog.foods:
        if not food.generation_eligible or food.review_status.value != "approved":
            continue
        if food.food_id in excluded_food_ids:
            continue
        if {code.value for code in food.allergen_codes} & allergen_codes:
            continue
        groups.setdefault(food.exchange_group, []).append(food)
    for values in groups.values():
        values.sort(key=lambda food: food.food_id)
    return groups


def _preferred(candidates: list[FoodRecord], food_ids: tuple[str, ...]) -> FoodRecord:
    by_id = {food.food_id: food for food in candidates}
    for food_id in food_ids:
        if food_id in by_id:
            return by_id[food_id]
    if candidates:
        return candidates[0]
    raise NutritionGenerationError("no_safe_candidate")


def _overlapping(left: FoodRecord, right: FoodRecord) -> bool:
    return max(left.edible_portion_min_g, right.edible_portion_min_g) <= min(
        left.edible_portion_max_g, right.edible_portion_max_g
    )


def _alternative(food: FoodRecord) -> FoodAlternative:
    return FoodAlternative(
        food_id=food.food_id,
        gram_min=food.edible_portion_min_g,
        gram_max=food.edible_portion_max_g,
        household_portion=project_portion(food.household_unit_code),
        allergen_codes=food.allergen_codes,
        image_key=food.image_key,
    )


def _item(food: FoodRecord, group: list[FoodRecord]) -> MealFoodItem:
    amount = _GUIDELINE_EQUIVALENTS[food.exchange_group]
    if not food.guideline_equivalent_min_g <= amount <= food.guideline_equivalent_max_g:
        raise NutritionGenerationError("no_safe_candidate")
    alternatives = [
        _alternative(candidate)
        for candidate in group
        if candidate.food_id != food.food_id and _overlapping(food, candidate)
    ]
    return MealFoodItem(
        food_id=food.food_id,
        gram_min=food.edible_portion_min_g,
        gram_max=food.edible_portion_max_g,
        guideline_equivalent_g=amount,
        household_portion=project_portion(food.household_unit_code),
        preparation_code=food.preparation_note_code,
        allergen_codes=food.allergen_codes,
        image_key=food.image_key,
        alternatives=alternatives,
    )


def _summary(
    items: list[MealFoodItem],
    index: dict[str, FoodRecord],
    whole_grain_ids: set[str],
) -> DailyFoodGroupSummary:
    values = {key: 0 for key in DailyFoodGroupSummary.model_fields}
    for item in items:
        food = index[item.food_id]
        _apply_group_amount(values, food, item.guideline_equivalent_g, whole_grain_ids)
    return DailyFoodGroupSummary(**values)


def _meal_energy(items: list[MealFoodItem], index: dict[str, FoodRecord]) -> float:
    return sum(
        (item.gram_min + item.gram_max)
        / 2
        * index[item.food_id].nutrients_per_100g.energy_kcal
        / 100
        for item in items
    )


def _filter_alternatives(
    meals: list[MealTemplate],
    index: dict[str, FoodRecord],
    policy: NutritionPolicy,
    groups: dict[str, list[FoodRecord]],
) -> None:
    base_energy = {meal.meal.value: _meal_energy(meal.items, index) for meal in meals}
    all_items = [item for meal in meals for item in meal.items]
    whole_grain_ids = set(policy.whole_grain_food_ids)
    base_summary = _summary(all_items, index, whole_grain_ids).model_dump()
    for meal in meals:
        for item in meal.items:
            selected = index[item.food_id]
            item.alternatives = [
                _alternative(candidate)
                for candidate in groups[selected.exchange_group]
                if candidate.food_id != selected.food_id
                and _overlapping(selected, candidate)
            ]
            selected_energy = (
                (item.gram_min + item.gram_max)
                / 2
                * selected.nutrients_per_100g.energy_kcal
                / 100
            )
            allowed: list[FoodAlternative] = []
            for alternative in item.alternatives:
                candidate = index[alternative.food_id]
                candidate_energy = (
                    (alternative.gram_min + alternative.gram_max)
                    / 2
                    * candidate.nutrients_per_100g.energy_kcal
                    / 100
                )
                projected = dict(base_energy)
                projected[meal.meal.value] += candidate_energy - selected_energy
                total = sum(projected.values())
                meal_shares_valid = all(
                    bounds[0] <= projected[name] * 100 / total <= bounds[1]
                    for name, bounds in policy.meal_share_pct.items()
                )
                projected_groups = dict(base_summary)
                _apply_group_amount(
                    projected_groups,
                    selected,
                    -item.guideline_equivalent_g,
                    whole_grain_ids,
                )
                candidate_amount = _GUIDELINE_EQUIVALENTS[candidate.exchange_group]
                _apply_group_amount(
                    projected_groups, candidate, candidate_amount, whole_grain_ids
                )
                group_ranges_valid = all(
                    bounds[0] <= projected_groups[name] <= bounds[1]
                    for name, bounds in policy.food_group_daily_ranges.items()
                )
                if meal_shares_valid and group_ranges_valid:
                    allowed.append(alternative)
            item.alternatives = allowed


def _variant(
    day_kind: DayKind,
    requested_goal: str,
    groups: dict[str, list[FoodRecord]],
    index: dict[str, FoodRecord],
    policy: NutritionPolicy,
) -> DayMealRecommendation:
    required_counts = {
        "staple_grain": 3,
        "tuber": 1,
        "vegetable": 3,
        "fruit": 2,
        "animal_protein": 1,
        "egg": 1,
        "dairy": 1,
        "soy_nut": 1,
    }
    if any(len(groups.get(group, [])) < count for group, count in required_counts.items()):
        raise NutritionGenerationError("no_safe_candidate")

    staples = [index[food_id] for food_id in ("oats_cooked", "rice_white", "rice_brown")]
    if any(food not in groups["staple_grain"] for food in staples):
        raise NutritionGenerationError("no_safe_candidate")
    vegetables = [index[food_id] for food_id in ("broccoli", "spinach_cooked", "bok_choy_cooked")]
    if any(food not in groups["vegetable"] for food in vegetables):
        raise NutritionGenerationError("no_safe_candidate")
    fruits = [index[food_id] for food_id in ("orange_raw", "apple_raw")]
    if any(food not in groups["fruit"] for food in fruits):
        raise NutritionGenerationError("no_safe_candidate")

    tuber_order = (
        ("sweet_potato_boiled", "potato_boiled", "yam_cooked")
        if day_kind == DayKind.training_day
        else ("potato_boiled", "sweet_potato_boiled", "yam_cooked")
    )
    tuber = _preferred(groups["tuber"], tuber_order)
    protein = _preferred(groups["animal_protein"], _GOAL_PROTEINS[requested_goal])
    egg = _preferred(groups["egg"], ("egg_chicken", "egg_quail", "egg_duck"))
    dairy = _preferred(groups["dairy"], ("milk_lowfat", "milk_whole", "yogurt_plain"))
    soy = _preferred(groups["soy_nut"], ("tofu_firm", "tofu_soft", "almonds_raw"))

    breakfast_items = [
        _item(staples[0], groups["staple_grain"]),
        _item(dairy, groups["dairy"]),
        _item(fruits[0], groups["fruit"]),
        _item(egg, groups["egg"]),
    ]
    lunch_items = [
        _item(staples[1], groups["staple_grain"]),
        _item(tuber, groups["tuber"]),
        _item(vegetables[0], groups["vegetable"]),
        _item(protein, groups["animal_protein"]),
    ]
    dinner_items = [
        _item(staples[2], groups["staple_grain"]),
        _item(vegetables[1], groups["vegetable"]),
        _item(vegetables[2], groups["vegetable"]),
        _item(fruits[1], groups["fruit"]),
        _item(soy, groups["soy_nut"]),
    ]
    meals = [
        MealTemplate(meal=MealName.breakfast, rationale_codes=["morning_balanced_range"], items=breakfast_items),
        MealTemplate(meal=MealName.lunch, rationale_codes=["midday_balanced_range"], items=lunch_items),
        MealTemplate(meal=MealName.dinner, rationale_codes=["evening_balanced_range"], items=dinner_items),
    ]
    _filter_alternatives(meals, index, policy, groups)
    all_items = breakfast_items + lunch_items + dinner_items
    return DayMealRecommendation(
        day_kind=day_kind,
        rationale_codes=[f"goal_{requested_goal}", day_kind.value, "three_meal_template"],
        meals=meals,
        food_group_summary=_summary(
            all_items, index, set(policy.whole_grain_food_ids)
        ),
    )


def generate_recommendation(
    *,
    catalog: FoodCatalog,
    policy: NutritionPolicy,
    media_manifest: MediaManifest,
    decision: NutritionDecision,
    targets: NutritionTargets,
    versions: NutritionVersions,
    requested_goal: str,
    allergen_codes: set[str],
    excluded_food_ids: set[str],
) -> RecommendationPayload:
    if decision.gate not in {GateStatus.eligible, GateStatus.eligible_conservative}:
        raise NutritionGenerationError("safety_gate_blocked")
    if requested_goal not in _GOAL_PROTEINS:
        raise NutritionGenerationError("unsupported_goal")
    if catalog.catalog_version != policy.supported_catalog_version:
        raise NutritionGenerationError("catalog_policy_version_mismatch")
    if versions != NutritionVersions(
        policy_version=policy.policy_version,
        catalog_version=catalog.catalog_version,
        source_manifest_version=catalog.source_manifest_version,
        media_manifest_version=media_manifest.manifest_version,
    ):
        raise NutritionGenerationError("stale_version")
    media_assets = {item.asset_key for item in media_manifest.media}
    if any(food.image_key and food.image_key not in media_assets for food in catalog.foods):
        raise NutritionGenerationError("media_reference_missing")

    groups = _safe_groups(catalog, allergen_codes, excluded_food_ids)
    index = {food.food_id: food for food in catalog.foods}
    display_targets = NutritionTargetRanges.model_validate(
        targets.model_dump(exclude={"reference_center_kcal"})
    )
    return RecommendationPayload(
        requested_goal=requested_goal,
        decision_gate=decision.gate,
        source_context_fingerprint=decision.context_fingerprint,
        versions=versions,
        targets=display_targets,
        variants=[
            _variant(DayKind.training_day, requested_goal, groups, index, policy),
            _variant(DayKind.rest_day, requested_goal, groups, index, policy),
        ],
        guideline_source_codes=[
            "china_dietary_guidelines_2022",
            "chinese_adult_dri_2023",
        ],
        uncertainty_codes=[
            targets.uncertainty_code,
            "template_not_measured_intake",
            "generic_food_values_vary",
        ],
        cross_contact_warning_code="verify_label_and_cross_contact_for_allergies",
    )


def preview_replacement(
    payload: RecommendationPayload,
    *,
    catalog: FoodCatalog,
    policy: NutritionPolicy,
    day_kind: DayKind,
    meal: MealName,
    item_index: int,
    from_food_id: str,
    to_food_id: str,
    allergen_codes: set[str],
    excluded_food_ids: set[str],
) -> RecommendationPayload:
    """Build an immutable replacement candidate; persistence happens later."""
    replacement = payload.model_copy(deep=True)
    variant = next((item for item in replacement.variants if item.day_kind == day_kind), None)
    meal_template = (
        next((item for item in variant.meals if item.meal == meal), None)
        if variant is not None
        else None
    )
    if meal_template is None or not 0 <= item_index < len(meal_template.items):
        raise NutritionGenerationError("invalid_replacement")
    current = meal_template.items[item_index]
    if current.food_id != from_food_id:
        raise NutritionGenerationError("invalid_replacement")
    if to_food_id not in {item.food_id for item in current.alternatives}:
        raise NutritionGenerationError("invalid_replacement")
    groups = _safe_groups(catalog, allergen_codes, excluded_food_ids)
    index = {food.food_id: food for food in catalog.foods}
    target = index.get(to_food_id)
    if target is None or target not in groups.get(target.exchange_group, []):
        raise NutritionGenerationError("invalid_replacement")
    replacement_item = _item(target, groups[target.exchange_group])
    meal_template.items[item_index] = replacement_item
    _filter_alternatives(variant.meals, index, policy, groups)
    all_items = [item for entry in variant.meals for item in entry.items]
    variant.food_group_summary = _summary(
        all_items, index, set(policy.whole_grain_food_ids)
    )
    replacement.replacement_diff = ReplacementDiff(
        day_kind=day_kind,
        meal=meal,
        item_index=item_index,
        from_food_id=from_food_id,
        to_food_id=to_food_id,
        from_gram_min=current.gram_min,
        from_gram_max=current.gram_max,
        to_gram_min=replacement_item.gram_min,
        to_gram_max=replacement_item.gram_max,
        validation_codes=["same_exchange_group", "overlapping_portion_range"],
    )
    return RecommendationPayload.model_validate(replacement.model_dump(mode="json"))


__all__ = [
    "NutritionGenerationError",
    "generate_recommendation",
    "preview_replacement",
]
