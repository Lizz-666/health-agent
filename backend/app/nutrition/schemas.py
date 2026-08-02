"""Strict schemas for the curated nutrition catalog and pure engines."""
from __future__ import annotations

import math
from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.health.schemas import ExcludedFoodCode, FoodAllergenCode as AllergenCode


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FoodCategory(str, Enum):
    grain = "grain"
    tuber = "tuber"
    vegetable = "vegetable"
    fruit = "fruit"
    animal_protein = "animal_protein"
    egg = "egg"
    dairy = "dairy"
    soy = "soy"
    nut = "nut"


class ReviewStatus(str, Enum):
    approved = "approved"
    pending = "pending"


class GateStatus(str, Enum):
    red_flag = "red_flag"
    restricted = "restricted"
    limited_education = "limited_education"
    clarification_required = "clarification_required"
    eligible_conservative = "eligible_conservative"
    eligible = "eligible"


class DayKind(str, Enum):
    training_day = "training_day"
    rest_day = "rest_day"


class NutrientsPer100g(StrictModel):
    energy_kcal: Optional[float] = Field(None, ge=0, le=900)
    protein_g: Optional[float] = Field(None, ge=0, le=100)
    carbohydrate_g: Optional[float] = Field(None, ge=0, le=100)
    fat_g: Optional[float] = Field(None, ge=0, le=100)
    fibre_g: Optional[float] = Field(None, ge=0, le=100)

    @field_validator("energy_kcal", "protein_g", "carbohydrate_g", "fat_g", "fibre_g")
    @classmethod
    def finite(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and not math.isfinite(value):
            raise ValueError("nutrient values must be finite")
        return value


class FoodRecord(StrictModel):
    food_id: str = Field(..., pattern=r"^[a-z0-9_]{3,60}$")
    name_zh: str = Field(..., min_length=1, max_length=40)
    source_description_en: str = Field(..., min_length=1, max_length=160)
    category: FoodCategory
    preparation_state: str = Field(..., min_length=1, max_length=40)
    exchange_group: str = Field(..., pattern=r"^[a-z0-9_]{3,40}$")
    source_id: str = Field(..., min_length=1, max_length=80)
    source_record_id: str = Field(..., min_length=1, max_length=80)
    source_data_type: str = Field(..., min_length=1, max_length=40)
    source_publication_date: date
    nutrients_per_100g: NutrientsPer100g
    edible_portion_min_g: int = Field(..., ge=1, le=1000)
    edible_portion_max_g: int = Field(..., ge=1, le=1000)
    guideline_equivalent_min_g: int = Field(..., ge=1, le=1000)
    guideline_equivalent_max_g: int = Field(..., ge=1, le=1000)
    household_unit_code: str = Field(..., min_length=1, max_length=50)
    preparation_note_code: str = Field(..., min_length=1, max_length=50)
    allergen_codes: List[AllergenCode] = Field(default_factory=list)
    ingredient_tags: List[str] = Field(default_factory=list, max_length=12)
    exclusion_codes: List[ExcludedFoodCode] = Field(default_factory=list, max_length=12)
    dark_vegetable: bool = False
    image_key: Optional[str] = Field(None, max_length=160)
    generation_eligible: bool
    review_status: ReviewStatus
    reviewer_role: str = Field(..., min_length=1, max_length=60)
    reviewed_at: date
    quality_limit_codes: List[str] = Field(default_factory=list, max_length=10)

    @field_validator("name_zh")
    @classmethod
    def chinese_name_is_not_corrupted(cls, value: str) -> str:
        if not any("\u4e00" <= character <= "\u9fff" for character in value):
            raise ValueError("Chinese food name must contain a CJK character")
        return value

    @field_validator("allergen_codes", "exclusion_codes")
    @classmethod
    def safety_codes_are_unique(cls, value: list) -> list:
        if len(value) != len(set(value)):
            raise ValueError("food safety codes must be unique")
        return value

    @model_validator(mode="after")
    def invariants(self):
        if self.edible_portion_min_g > self.edible_portion_max_g:
            raise ValueError("edible portion minimum exceeds maximum")
        if self.guideline_equivalent_min_g > self.guideline_equivalent_max_g:
            raise ValueError("guideline equivalent minimum exceeds maximum")
        core = self.nutrients_per_100g
        complete = all(
            value is not None
            for value in (core.energy_kcal, core.protein_g, core.carbohydrate_g, core.fat_g)
        )
        if self.generation_eligible and not complete:
            raise ValueError("generation-eligible food has incomplete core nutrients")
        if self.generation_eligible and self.review_status != ReviewStatus.approved:
            raise ValueError("generation-eligible food must be approved")
        return self


class FoodCatalog(StrictModel):
    schema_version: str
    catalog_version: str
    source_manifest_version: str
    media_manifest_version: str
    published_at: date
    foods: List[FoodRecord] = Field(..., min_length=1)


class SourceEntry(StrictModel):
    source_id: str = Field(..., min_length=1, max_length=80)
    source_type: str = Field(..., min_length=1, max_length=40)
    name: str = Field(..., min_length=1, max_length=160)
    pinned_version: str = Field(..., min_length=1, max_length=120)
    url: str = Field(..., pattern=r"^https://")
    license: str = Field(..., min_length=1, max_length=80)
    retrieved_at: datetime
    raw_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    local_subset_file: str = Field(..., pattern=r"^fdc_[a-z0-9_.-]+\.json$")
    selected_fields: List[str] = Field(..., min_length=1)
    normalization_version: str = Field(..., min_length=1, max_length=40)
    reviewer_role: str = Field(..., min_length=1, max_length=60)
    review_status: ReviewStatus
    update_procedure: str = Field(..., min_length=1, max_length=300)
    removal_procedure: str = Field(..., min_length=1, max_length=300)


class SourceManifest(StrictModel):
    manifest_version: str
    sources: List[SourceEntry] = Field(..., min_length=1)


class MediaEntry(StrictModel):
    media_id: str = Field(..., pattern=r"^[a-z0-9_]{3,80}$")
    kind: str = Field(..., pattern=r"^(ingredient|prepared_meal)$")
    asset_key: str = Field(..., pattern=r"^assets/images/nutrition/[a-z0-9_./-]+$")
    source_file_url: str = Field(..., pattern=r"^https://")
    source_page_url: str = Field(..., pattern=r"^https://")
    license: str = Field(..., min_length=1, max_length=60)
    author: str = Field(..., min_length=1, max_length=120)
    retrieved_at: datetime
    sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    width: int = Field(..., ge=64, le=4096)
    height: int = Field(..., ge=64, le=4096)
    transformation: str = Field(..., min_length=1, max_length=160)
    review_status: ReviewStatus


class MediaManifest(StrictModel):
    manifest_version: str
    media: List[MediaEntry] = Field(..., min_length=1)


class NutritionPolicy(StrictModel):
    policy_version: str
    supported_catalog_version: str
    allergen_codes: List[AllergenCode]
    exclusion_food_ids: Dict[ExcludedFoodCode, List[str]]
    whole_grain_food_ids: List[str] = Field(..., min_length=1)
    meal_share_pct: Dict[str, List[int]]
    food_group_daily_ranges: Dict[str, List[int]]
    education_only_groups: List[str]

    @model_validator(mode="after")
    def policy_contract(self):
        if set(self.allergen_codes) != set(AllergenCode):
            raise ValueError("policy must contain the complete allergen vocabulary")
        if set(self.exclusion_food_ids) != set(ExcludedFoodCode):
            raise ValueError("policy must contain the complete exclusion vocabulary")
        if any(len(ids) != len(set(ids)) for ids in self.exclusion_food_ids.values()):
            raise ValueError("exclusion food ids must be unique")
        if len(self.whole_grain_food_ids) != len(set(self.whole_grain_food_ids)):
            raise ValueError("whole grain food ids must be unique")
        if set(self.meal_share_pct) != {"breakfast", "lunch", "dinner"}:
            raise ValueError("policy must define exactly three meal shares")
        for bounds in self.meal_share_pct.values():
            if len(bounds) != 2 or bounds[0] > bounds[1]:
                raise ValueError("invalid meal share range")
        return self


class PortionProjection(StrictModel):
    unit_code: str
    amount_min: int = Field(..., ge=1)
    amount_max: int = Field(..., ge=1)
    unit_label: str
    approximate: bool = True
    limitation_code: str


class NutritionVersions(StrictModel):
    policy_version: str
    catalog_version: str
    source_manifest_version: str
    media_manifest_version: str


class WeightSource(StrictModel):
    kind: str = Field(..., pattern=r"^(manual_record|account)$")
    record_id: Optional[str] = None
    recorded_at: Optional[datetime] = None
    timestamp: datetime
    weight_kg: float = Field(..., gt=0, le=500)

    @field_validator("weight_kg")
    @classmethod
    def finite_weight(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("weight must be finite")
        return value


class NutritionContext(StrictModel):
    age: Optional[int] = None
    height_cm: Optional[float] = None
    account_updated_at: Optional[datetime] = None
    weight_source: Optional[WeightSource] = None
    profile_version: Optional[int] = None
    profile_updated_at: Optional[datetime] = None
    risk_screen: Optional[Dict[str, str]] = None
    food_allergen_codes: Optional[List[AllergenCode]] = None
    excluded_food_codes: Optional[List[str]] = None
    has_legacy_allergies: bool = False
    has_legacy_diet_exclusions: bool = False
    checkin_present: bool = False
    checkin_risk: Optional[str] = None
    checkin_token: Optional[str] = None
    posture_risk: Optional[str] = None
    active_plan_present: bool = False
    active_plan_goal: Optional[str] = None
    active_plan_version_id: Optional[str] = None
    training_decision_gate: Optional[str] = None
    day_kind: Optional[DayKind] = None
    current_local_date: date
    iana_timezone: str
    versions: NutritionVersions


class NutritionDecision(StrictModel):
    gate: GateStatus
    reason_codes: List[str]
    missing_field_codes: List[str] = Field(default_factory=list)
    bmi_category: Optional[str] = None
    context_fingerprint: str = Field(..., pattern=r"^[0-9a-f]{64}$")


class NutritionTargets(StrictModel):
    energy_low_kcal: int = Field(..., multiple_of=100)
    energy_high_kcal: int = Field(..., multiple_of=100)
    reference_center_kcal: float
    protein_g_min: int = 55
    protein_g_max: int = 65
    protein_energy_pct_min: int = 10
    protein_energy_pct_max: int = 20
    carbohydrate_energy_pct_min: int = 50
    carbohydrate_energy_pct_max: int = 65
    fat_energy_pct_min: int = 20
    fat_energy_pct_max: int = 30
    fibre_g_min: int = 25
    fibre_g_max: int = 30
    drinking_water_ml_min: int = 1500
    drinking_water_ml_max: int = 1700
    total_water_ml_min: int = 2700
    total_water_ml_max: int = 3000
    uncertainty_code: str = "product_estimate_band_not_confidence_interval"
    limitation_codes: List[str]


class ValidationIssue(StrictModel):
    code: str
    path: str


class ValidationResult(StrictModel):
    valid: bool
    issues: List[ValidationIssue]


class RecommendationStatus(str, Enum):
    draft = "draft"
    active = "active"
    superseded = "superseded"


class MealName(str, Enum):
    breakfast = "breakfast"
    lunch = "lunch"
    dinner = "dinner"


class NutritionTargetRanges(StrictModel):
    """Rounded display ranges only; no unsupported exact energy estimate."""

    energy_low_kcal: int = Field(..., multiple_of=100)
    energy_high_kcal: int = Field(..., multiple_of=100)
    protein_g_min: int
    protein_g_max: int
    protein_energy_pct_min: int
    protein_energy_pct_max: int
    carbohydrate_energy_pct_min: int
    carbohydrate_energy_pct_max: int
    fat_energy_pct_min: int
    fat_energy_pct_max: int
    fibre_g_min: int
    fibre_g_max: int
    drinking_water_ml_min: int
    drinking_water_ml_max: int
    total_water_ml_min: int
    total_water_ml_max: int
    uncertainty_code: str
    limitation_codes: List[str]


class FoodAlternative(StrictModel):
    food_id: str = Field(..., pattern=r"^[a-z0-9_]{3,60}$")
    gram_min: int = Field(..., ge=1, le=1000)
    gram_max: int = Field(..., ge=1, le=1000)
    household_portion: PortionProjection
    allergen_codes: List[AllergenCode]
    image_key: Optional[str] = None

    @model_validator(mode="after")
    def valid_range(self):
        if self.gram_min > self.gram_max:
            raise ValueError("alternative gram minimum exceeds maximum")
        return self


class MealFoodItem(StrictModel):
    food_id: str = Field(..., pattern=r"^[a-z0-9_]{3,60}$")
    gram_min: int = Field(..., ge=1, le=1000)
    gram_max: int = Field(..., ge=1, le=1000)
    guideline_equivalent_g: int = Field(..., ge=1, le=1000)
    household_portion: PortionProjection
    preparation_code: str = Field(..., min_length=1, max_length=50)
    allergen_codes: List[AllergenCode]
    image_key: Optional[str] = None
    alternatives: List[FoodAlternative] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_item(self):
        if self.gram_min > self.gram_max:
            raise ValueError("food gram minimum exceeds maximum")
        alternative_ids = [item.food_id for item in self.alternatives]
        if self.food_id in alternative_ids or len(alternative_ids) != len(set(alternative_ids)):
            raise ValueError("alternatives must be unique and exclude the selected food")
        return self


class MealTemplate(StrictModel):
    meal: MealName
    rationale_codes: List[str] = Field(..., min_length=1)
    items: List[MealFoodItem] = Field(..., min_length=1)

    @field_validator("rationale_codes")
    @classmethod
    def rationale_is_stable_codes(cls, value: List[str]) -> List[str]:
        if len(value) != len(set(value)) or any(
            not code or len(code) > 60 or not code.replace("_", "").isalnum()
            for code in value
        ):
            raise ValueError("rationale must contain unique stable codes")
        return value


class DailyFoodGroupSummary(StrictModel):
    grains: int = Field(..., ge=0)
    whole_grains_mixed_beans: int = Field(..., ge=0)
    tubers: int = Field(..., ge=0)
    vegetables: int = Field(..., ge=0)
    fruit: int = Field(..., ge=0)
    animal_foods: int = Field(..., ge=0)
    dairy_ml: int = Field(..., ge=0)
    soy_nuts: int = Field(..., ge=0)


class DayMealRecommendation(StrictModel):
    day_kind: DayKind
    rationale_codes: List[str] = Field(..., min_length=1)
    meals: List[MealTemplate] = Field(..., min_length=3, max_length=3)
    food_group_summary: DailyFoodGroupSummary

    @field_validator("rationale_codes")
    @classmethod
    def rationale_is_stable_codes(cls, value: List[str]) -> List[str]:
        return MealTemplate.rationale_is_stable_codes(value)

    @model_validator(mode="after")
    def exactly_three_named_meals(self):
        if {meal.meal for meal in self.meals} != set(MealName):
            raise ValueError("day variant must contain breakfast, lunch and dinner")
        return self


class ReplacementDiff(StrictModel):
    day_kind: DayKind
    meal: MealName
    item_index: int = Field(..., ge=0)
    from_food_id: str = Field(..., pattern=r"^[a-z0-9_]{3,60}$")
    to_food_id: str = Field(..., pattern=r"^[a-z0-9_]{3,60}$")
    from_gram_min: int = Field(..., ge=1)
    from_gram_max: int = Field(..., ge=1)
    to_gram_min: int = Field(..., ge=1)
    to_gram_max: int = Field(..., ge=1)
    validation_codes: List[str] = Field(..., min_length=1)

    @field_validator("validation_codes")
    @classmethod
    def validation_is_stable_codes(cls, value: List[str]) -> List[str]:
        return MealTemplate.rationale_is_stable_codes(value)


class RecommendationPayload(StrictModel):
    schema_version: str = "v1"
    requested_goal: str = Field(..., pattern=r"^(posture_improvement|fat_loss|basic_strength)$")
    decision_gate: GateStatus
    source_context_fingerprint: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    versions: NutritionVersions
    targets: NutritionTargetRanges
    variants: List[DayMealRecommendation] = Field(..., min_length=2, max_length=2)
    guideline_source_codes: List[str] = Field(..., min_length=1)
    uncertainty_codes: List[str] = Field(..., min_length=1)
    cross_contact_warning_code: str = Field(..., pattern=r"^[a-z0-9_]{3,80}$")
    replacement_diff: Optional[ReplacementDiff] = None

    @field_validator("guideline_source_codes", "uncertainty_codes")
    @classmethod
    def metadata_is_stable_codes(cls, value: List[str]) -> List[str]:
        return MealTemplate.rationale_is_stable_codes(value)

    @model_validator(mode="after")
    def complete_variants(self):
        if {variant.day_kind for variant in self.variants} != set(DayKind):
            raise ValueError("recommendation must contain training and rest variants")
        return self


class RecommendationContextPins(StrictModel):
    profile_version: int = Field(..., ge=1)
    training_plan_version_id: str = Field(..., min_length=1, max_length=64)
    checkin_token: str = Field(..., pattern=r"^[0-9a-f]{64}$")
