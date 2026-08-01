"""Independent structural, source and exclusion validation helpers."""
from __future__ import annotations

from app.nutrition.portions import project_portion
from app.nutrition.schemas import (
    DailyFoodGroupSummary,
    FoodCatalog,
    GateStatus,
    MediaManifest,
    NutritionDecision,
    NutritionPolicy,
    RecommendationPayload,
    NutritionVersions,
    SourceManifest,
    ValidationIssue,
    ValidationResult,
)

def _apply_group_amount(
    values: dict[str, int], food, amount: int, whole_grain_ids: set[str]
) -> None:
    category = food.category.value
    if category == "grain":
        values["grains"] += amount
        if food.food_id in whole_grain_ids:
            values["whole_grains_mixed_beans"] += amount
    elif category == "tuber":
        values["tubers"] += amount
    elif category == "vegetable":
        values["vegetables"] += amount
    elif category == "fruit":
        values["fruit"] += amount
    elif category in {"animal_protein", "egg"}:
        values["animal_foods"] += amount
    elif category == "dairy":
        values["dairy_ml"] += amount
    elif category in {"soy", "nut"}:
        values["soy_nuts"] += amount


def validate_versions(
    expected: NutritionVersions,
    actual: NutritionVersions,
) -> ValidationResult:
    issues = [
        ValidationIssue(code="stale_version", path=field)
        for field, value in expected.model_dump().items()
        if value != actual.model_dump()[field]
    ]
    return ValidationResult(valid=not issues, issues=issues)


def validate_food_selection(
    food_ids: list[str],
    catalog: FoodCatalog,
    decision: NutritionDecision,
    allergen_codes: set[str],
    excluded_food_ids: set[str],
) -> ValidationResult:
    issues: list[ValidationIssue] = []
    if decision.gate not in {GateStatus.eligible, GateStatus.eligible_conservative}:
        issues.append(ValidationIssue(code="safety_gate_blocked", path="decision.gate"))
    index = {food.food_id: food for food in catalog.foods}
    for position, food_id in enumerate(food_ids):
        path = f"foods.{position}"
        food = index.get(food_id)
        if food is None:
            issues.append(ValidationIssue(code="unknown_food", path=path))
            continue
        if not food.generation_eligible or food.review_status.value != "approved":
            issues.append(ValidationIssue(code="food_not_generation_eligible", path=path))
        if {x.value for x in food.allergen_codes} & allergen_codes:
            issues.append(ValidationIssue(code="allergen_intersection", path=path))
        if food_id in excluded_food_ids:
            issues.append(ValidationIssue(code="explicit_exclusion_intersection", path=path))
    return ValidationResult(valid=not issues, issues=issues)


def validate_manifest_pins(
    catalog: FoodCatalog,
    source_manifest: SourceManifest,
    media_manifest: MediaManifest,
) -> ValidationResult:
    issues: list[ValidationIssue] = []
    if catalog.source_manifest_version != source_manifest.manifest_version:
        issues.append(ValidationIssue(code="source_manifest_version_mismatch", path="catalog"))
    if catalog.media_manifest_version != media_manifest.manifest_version:
        issues.append(ValidationIssue(code="media_manifest_version_mismatch", path="catalog"))
    return ValidationResult(valid=not issues, issues=issues)


def _daily_summary(
    payload_items, index: dict, whole_grain_ids: set[str]
) -> DailyFoodGroupSummary:
    values = {key: 0 for key in DailyFoodGroupSummary.model_fields}
    for item in payload_items:
        food = index.get(item.food_id)
        if food is None:
            continue
        _apply_group_amount(values, food, item.guideline_equivalent_g, whole_grain_ids)
    return DailyFoodGroupSummary(**values)


def _meal_energy(items, index: dict) -> float:
    return sum(
        (item.gram_min + item.gram_max)
        / 2
        * index[item.food_id].nutrients_per_100g.energy_kcal
        / 100
        for item in items
        if item.food_id in index
        and index[item.food_id].nutrients_per_100g.energy_kcal is not None
    )


def _replacement_preserves_meal_shares(
    variant,
    meal,
    item,
    candidate,
    index: dict,
    policy: NutritionPolicy,
) -> bool:
    energies = {entry.meal.value: _meal_energy(entry.items, index) for entry in variant.meals}
    selected = index[item.food_id]
    selected_energy = (
        (item.gram_min + item.gram_max)
        / 2
        * selected.nutrients_per_100g.energy_kcal
        / 100
    )
    candidate_energy = (
        (candidate.edible_portion_min_g + candidate.edible_portion_max_g)
        / 2
        * candidate.nutrients_per_100g.energy_kcal
        / 100
    )
    energies[meal.meal.value] += candidate_energy - selected_energy
    total = sum(energies.values())
    meal_shares_valid = total > 0 and all(
        bounds[0] <= energies[name] * 100 / total <= bounds[1]
        for name, bounds in policy.meal_share_pct.items()
    )
    items = [entry for template in variant.meals for entry in template.items]
    whole_grain_ids = set(policy.whole_grain_food_ids)
    groups = _daily_summary(items, index, whole_grain_ids).model_dump()
    _apply_group_amount(
        groups, selected, -item.guideline_equivalent_g, whole_grain_ids
    )
    if not (
        candidate.guideline_equivalent_min_g
        <= item.guideline_equivalent_g
        <= candidate.guideline_equivalent_max_g
    ):
        return False
    _apply_group_amount(
        groups, candidate, item.guideline_equivalent_g, whole_grain_ids
    )
    group_ranges_valid = all(
        bounds[0] <= groups[name] <= bounds[1]
        for name, bounds in policy.food_group_daily_ranges.items()
    )
    return meal_shares_valid and group_ranges_valid


def validate_recommendation(
    payload: RecommendationPayload,
    catalog: FoodCatalog,
    policy: NutritionPolicy,
    media_manifest: MediaManifest,
    decision: NutritionDecision,
    expected_versions: NutritionVersions,
    allergen_codes: set[str],
    excluded_food_ids: set[str],
) -> ValidationResult:
    """Independently re-check a generated or persisted recommendation."""
    issues: list[ValidationIssue] = []
    issues.extend(validate_versions(expected_versions, payload.versions).issues)
    if payload.decision_gate not in {GateStatus.eligible, GateStatus.eligible_conservative}:
        issues.append(ValidationIssue(code="safety_gate_blocked", path="decision_gate"))
    if payload.decision_gate != decision.gate:
        issues.append(ValidationIssue(code="decision_gate_mismatch", path="decision_gate"))
    if payload.source_context_fingerprint != decision.context_fingerprint:
        issues.append(ValidationIssue(code="stale_context", path="source_context_fingerprint"))
    current_versions = NutritionVersions(
        policy_version=policy.policy_version,
        catalog_version=catalog.catalog_version,
        source_manifest_version=catalog.source_manifest_version,
        media_manifest_version=media_manifest.manifest_version,
    )
    issues.extend(validate_versions(current_versions, payload.versions).issues)

    index = {food.food_id: food for food in catalog.foods}
    media_assets = {item.asset_key for item in media_manifest.media}
    for variant_index, variant in enumerate(payload.variants):
        items = [item for meal in variant.meals for item in meal.items]
        selected = validate_food_selection(
            [item.food_id for item in items],
            catalog,
            decision,
            allergen_codes,
            excluded_food_ids,
        )
        issues.extend(selected.issues)
        for meal_index, meal in enumerate(variant.meals):
            for item_index, item in enumerate(meal.items):
                path = f"variants.{variant_index}.meals.{meal_index}.items.{item_index}"
                food = index.get(item.food_id)
                if food is None:
                    continue
                if not (
                    food.edible_portion_min_g <= item.gram_min <= item.gram_max
                    <= food.edible_portion_max_g
                ):
                    issues.append(ValidationIssue(code="portion_out_of_bounds", path=path))
                if not (
                    food.guideline_equivalent_min_g
                    <= item.guideline_equivalent_g
                    <= food.guideline_equivalent_max_g
                ):
                    issues.append(ValidationIssue(code="guideline_equivalent_out_of_bounds", path=path))
                if (
                    item.household_portion != project_portion(food.household_unit_code)
                    or item.preparation_code != food.preparation_note_code
                    or set(item.allergen_codes) != set(food.allergen_codes)
                    or item.image_key != food.image_key
                ):
                    issues.append(ValidationIssue(code="catalog_projection_mismatch", path=path))
                if item.image_key and item.image_key not in media_assets:
                    issues.append(ValidationIssue(code="media_reference_missing", path=path))
                safe_equivalents = []
                for candidate in catalog.foods:
                    if candidate.food_id == food.food_id or candidate.exchange_group != food.exchange_group:
                        continue
                    if not candidate.generation_eligible or candidate.food_id in excluded_food_ids:
                        continue
                    if {code.value for code in candidate.allergen_codes} & allergen_codes:
                        continue
                    if max(food.edible_portion_min_g, candidate.edible_portion_min_g) > min(
                        food.edible_portion_max_g, candidate.edible_portion_max_g
                    ):
                        continue
                    if not _replacement_preserves_meal_shares(
                        variant, meal, item, candidate, index, policy
                    ):
                        continue
                    safe_equivalents.append(candidate)
                expected_alternatives = {candidate.food_id for candidate in safe_equivalents}
                actual_alternatives = {candidate.food_id for candidate in item.alternatives}
                if actual_alternatives != expected_alternatives:
                    issues.append(ValidationIssue(code="replacement_set_mismatch", path=path))
                for alternative in item.alternatives:
                    candidate = index.get(alternative.food_id)
                    if candidate is None:
                        issues.append(ValidationIssue(code="unknown_alternative", path=path))
                        continue
                    if (
                        alternative.gram_min != candidate.edible_portion_min_g
                        or alternative.gram_max != candidate.edible_portion_max_g
                        or alternative.household_portion
                        != project_portion(candidate.household_unit_code)
                        or set(alternative.allergen_codes) != set(candidate.allergen_codes)
                        or alternative.image_key != candidate.image_key
                    ):
                        issues.append(ValidationIssue(code="alternative_projection_mismatch", path=path))

        recomputed = _daily_summary(items, index, set(policy.whole_grain_food_ids))
        if recomputed != variant.food_group_summary:
            issues.append(ValidationIssue(code="food_group_summary_mismatch", path=f"variants.{variant_index}"))
        for group, bounds in policy.food_group_daily_ranges.items():
            value = getattr(recomputed, group)
            if not bounds[0] <= value <= bounds[1]:
                issues.append(ValidationIssue(code="food_group_range_violation", path=f"variants.{variant_index}.{group}"))

        meal_energy: dict[str, float] = {}
        for meal in variant.meals:
            total = 0.0
            for item in meal.items:
                food = index.get(item.food_id)
                if food is None or food.nutrients_per_100g.energy_kcal is None:
                    continue
                total += (
                    (item.gram_min + item.gram_max) / 2
                    * food.nutrients_per_100g.energy_kcal
                    / 100
                )
            meal_energy[meal.meal.value] = total
        daily_energy = sum(meal_energy.values())
        if daily_energy <= 0:
            issues.append(ValidationIssue(code="invalid_template_energy", path=f"variants.{variant_index}"))
        else:
            for meal, bounds in policy.meal_share_pct.items():
                share = meal_energy[meal] * 100 / daily_energy
                if not bounds[0] <= share <= bounds[1]:
                    issues.append(ValidationIssue(code="meal_share_violation", path=f"variants.{variant_index}.{meal}"))
    return ValidationResult(valid=not issues, issues=issues)
