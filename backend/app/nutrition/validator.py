"""Independent structural, source and exclusion validation helpers."""
from __future__ import annotations

from app.nutrition.schemas import (
    FoodCatalog,
    GateStatus,
    MediaManifest,
    NutritionDecision,
    NutritionVersions,
    SourceManifest,
    ValidationIssue,
    ValidationResult,
)


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
