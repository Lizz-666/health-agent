// Strict client contracts for the Phase 6 nutrition recommendation API.
// Unknown fields and enum values fail closed so malformed server results are
// never rendered as eligible or active recommendations.

enum NutritionGate {
  redFlag('red_flag'),
  restricted('restricted'),
  limitedEducation('limited_education'),
  clarificationRequired('clarification_required'),
  eligibleConservative('eligible_conservative'),
  eligible('eligible');

  final String wire;
  const NutritionGate(this.wire);

  static NutritionGate parse(Object? raw) => values.firstWhere(
    (value) => value.wire == raw,
    orElse: () => throw const FormatException('unknown nutrition gate'),
  );

  bool get allowsRecommendation =>
      this == eligible || this == eligibleConservative;
}

enum NutritionDayKind {
  trainingDay('training_day'),
  restDay('rest_day');

  final String wire;
  const NutritionDayKind(this.wire);
  static NutritionDayKind parse(Object? raw) => values.firstWhere(
    (value) => value.wire == raw,
    orElse: () => throw const FormatException('unknown day kind'),
  );
}

enum NutritionMeal {
  breakfast('breakfast'),
  lunch('lunch'),
  dinner('dinner');

  final String wire;
  const NutritionMeal(this.wire);
  static NutritionMeal parse(Object? raw) => values.firstWhere(
    (value) => value.wire == raw,
    orElse: () => throw const FormatException('unknown meal'),
  );
}

enum RecommendationStatus {
  draft,
  active,
  superseded;

  static RecommendationStatus parse(Object? raw) => values.firstWhere(
    (value) => value.name == raw,
    orElse: () => throw const FormatException('unknown recommendation status'),
  );
}

class NutritionVersions {
  final String policyVersion;
  final String catalogVersion;
  final String sourceManifestVersion;
  final String mediaManifestVersion;

  const NutritionVersions({
    required this.policyVersion,
    required this.catalogVersion,
    required this.sourceManifestVersion,
    required this.mediaManifestVersion,
  });

  factory NutritionVersions.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {
      'policy_version',
      'catalog_version',
      'source_manifest_version',
      'media_manifest_version',
    }, 'NutritionVersions');
    return NutritionVersions(
      policyVersion: _string(json, 'policy_version', 'NutritionVersions'),
      catalogVersion: _string(json, 'catalog_version', 'NutritionVersions'),
      sourceManifestVersion: _string(
        json,
        'source_manifest_version',
        'NutritionVersions',
      ),
      mediaManifestVersion: _string(
        json,
        'media_manifest_version',
        'NutritionVersions',
      ),
    );
  }
}

class NutritionEligibility {
  final NutritionGate gate;
  final List<String> reasonCodes;
  final List<String> missingFieldCodes;
  final String? bmiCategory;
  final NutritionVersions versions;

  const NutritionEligibility({
    required this.gate,
    required this.reasonCodes,
    required this.missingFieldCodes,
    required this.bmiCategory,
    required this.versions,
  });

  factory NutritionEligibility.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {
      'gate',
      'reason_codes',
      'missing_field_codes',
      'bmi_category',
      'versions',
    }, 'NutritionEligibility');
    return NutritionEligibility(
      gate: NutritionGate.parse(json['gate']),
      reasonCodes: _stringList(json['reason_codes'], 'reason_codes'),
      missingFieldCodes: _stringList(
        json['missing_field_codes'],
        'missing_field_codes',
      ),
      bmiCategory: _nullableString(json['bmi_category'], 'bmi_category'),
      versions: NutritionVersions.fromJson(
        _object(json['versions'], 'NutritionEligibility.versions'),
      ),
    );
  }
}

class NutritionTargets {
  final int energyLowKcal;
  final int energyHighKcal;
  final int proteinGMin;
  final int proteinGMax;
  final int proteinEnergyPctMin;
  final int proteinEnergyPctMax;
  final int carbohydrateEnergyPctMin;
  final int carbohydrateEnergyPctMax;
  final int fatEnergyPctMin;
  final int fatEnergyPctMax;
  final int fibreGMin;
  final int fibreGMax;
  final int drinkingWaterMlMin;
  final int drinkingWaterMlMax;
  final int totalWaterMlMin;
  final int totalWaterMlMax;
  final String uncertaintyCode;
  final List<String> limitationCodes;

  const NutritionTargets({
    required this.energyLowKcal,
    required this.energyHighKcal,
    required this.proteinGMin,
    required this.proteinGMax,
    required this.proteinEnergyPctMin,
    required this.proteinEnergyPctMax,
    required this.carbohydrateEnergyPctMin,
    required this.carbohydrateEnergyPctMax,
    required this.fatEnergyPctMin,
    required this.fatEnergyPctMax,
    required this.fibreGMin,
    required this.fibreGMax,
    required this.drinkingWaterMlMin,
    required this.drinkingWaterMlMax,
    required this.totalWaterMlMin,
    required this.totalWaterMlMax,
    required this.uncertaintyCode,
    required this.limitationCodes,
  });

  factory NutritionTargets.fromJson(Map<String, dynamic> json) {
    const keys = {
      'energy_low_kcal',
      'energy_high_kcal',
      'protein_g_min',
      'protein_g_max',
      'protein_energy_pct_min',
      'protein_energy_pct_max',
      'carbohydrate_energy_pct_min',
      'carbohydrate_energy_pct_max',
      'fat_energy_pct_min',
      'fat_energy_pct_max',
      'fibre_g_min',
      'fibre_g_max',
      'drinking_water_ml_min',
      'drinking_water_ml_max',
      'total_water_ml_min',
      'total_water_ml_max',
      'uncertainty_code',
      'limitation_codes',
    };
    _expectKeys(json, keys, 'NutritionTargets');
    return NutritionTargets(
      energyLowKcal: _integer(json, 'energy_low_kcal', 'NutritionTargets'),
      energyHighKcal: _integer(json, 'energy_high_kcal', 'NutritionTargets'),
      proteinGMin: _integer(json, 'protein_g_min', 'NutritionTargets'),
      proteinGMax: _integer(json, 'protein_g_max', 'NutritionTargets'),
      proteinEnergyPctMin: _integer(
        json,
        'protein_energy_pct_min',
        'NutritionTargets',
      ),
      proteinEnergyPctMax: _integer(
        json,
        'protein_energy_pct_max',
        'NutritionTargets',
      ),
      carbohydrateEnergyPctMin: _integer(
        json,
        'carbohydrate_energy_pct_min',
        'NutritionTargets',
      ),
      carbohydrateEnergyPctMax: _integer(
        json,
        'carbohydrate_energy_pct_max',
        'NutritionTargets',
      ),
      fatEnergyPctMin: _integer(json, 'fat_energy_pct_min', 'NutritionTargets'),
      fatEnergyPctMax: _integer(json, 'fat_energy_pct_max', 'NutritionTargets'),
      fibreGMin: _integer(json, 'fibre_g_min', 'NutritionTargets'),
      fibreGMax: _integer(json, 'fibre_g_max', 'NutritionTargets'),
      drinkingWaterMlMin: _integer(
        json,
        'drinking_water_ml_min',
        'NutritionTargets',
      ),
      drinkingWaterMlMax: _integer(
        json,
        'drinking_water_ml_max',
        'NutritionTargets',
      ),
      totalWaterMlMin: _integer(json, 'total_water_ml_min', 'NutritionTargets'),
      totalWaterMlMax: _integer(json, 'total_water_ml_max', 'NutritionTargets'),
      uncertaintyCode: _string(json, 'uncertainty_code', 'NutritionTargets'),
      limitationCodes: _stringList(
        json['limitation_codes'],
        'limitation_codes',
      ),
    );
  }
}

class NutritionTargetsResponse {
  final NutritionGate gate;
  final NutritionTargets targets;
  final NutritionVersions versions;

  const NutritionTargetsResponse({
    required this.gate,
    required this.targets,
    required this.versions,
  });

  factory NutritionTargetsResponse.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {'gate', 'targets', 'versions'}, 'TargetsResponse');
    return NutritionTargetsResponse(
      gate: NutritionGate.parse(json['gate']),
      targets: NutritionTargets.fromJson(_object(json['targets'], 'targets')),
      versions: NutritionVersions.fromJson(
        _object(json['versions'], 'versions'),
      ),
    );
  }
}

class NutritionFood {
  final String foodId;
  final String nameZh;
  final String category;
  final String? imageKey;

  const NutritionFood({
    required this.foodId,
    required this.nameZh,
    required this.category,
    required this.imageKey,
  });

  factory NutritionFood.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {
      'food_id',
      'name_zh',
      'source_description_en',
      'category',
      'preparation_state',
      'exchange_group',
      'source_id',
      'source_record_id',
      'source_data_type',
      'source_publication_date',
      'nutrients_per_100g',
      'edible_portion_min_g',
      'edible_portion_max_g',
      'guideline_equivalent_min_g',
      'guideline_equivalent_max_g',
      'household_unit_code',
      'preparation_note_code',
      'allergen_codes',
      'ingredient_tags',
      'exclusion_codes',
      'dark_vegetable',
      'image_key',
      'generation_eligible',
      'review_status',
      'reviewer_role',
      'reviewed_at',
      'quality_limit_codes',
    }, 'NutritionFood');
    const categories = {
      'grain',
      'tuber',
      'vegetable',
      'fruit',
      'animal_protein',
      'egg',
      'dairy',
      'soy',
      'nut',
    };
    final category = _string(json, 'category', 'NutritionFood');
    if (!categories.contains(category)) {
      throw const FormatException('NutritionFood has unknown category');
    }
    for (final key in const {
      'source_description_en',
      'preparation_state',
      'exchange_group',
      'source_id',
      'source_record_id',
      'source_data_type',
      'household_unit_code',
      'preparation_note_code',
      'reviewer_role',
    }) {
      _string(json, key, 'NutritionFood');
    }
    for (final key in const {
      'edible_portion_min_g',
      'edible_portion_max_g',
      'guideline_equivalent_min_g',
      'guideline_equivalent_max_g',
    }) {
      _integer(json, key, 'NutritionFood');
    }
    for (final key in const {'source_publication_date', 'reviewed_at'}) {
      _date(json, key, 'NutritionFood');
    }
    for (final key in const {
      'allergen_codes',
      'ingredient_tags',
      'exclusion_codes',
      'quality_limit_codes',
    }) {
      _stringList(json[key], 'NutritionFood.$key');
    }
    _validateAllergenCodes(json['allergen_codes'], 'NutritionFood.allergen_codes');
    _validateExclusionCodes(json['exclusion_codes'], 'NutritionFood.exclusion_codes');
    for (final key in const {'dark_vegetable', 'generation_eligible'}) {
      _boolean(json, key, 'NutritionFood');
    }
    final reviewStatus = _string(json, 'review_status', 'NutritionFood');
    if (!const {'approved', 'pending'}.contains(reviewStatus)) {
      throw const FormatException('NutritionFood has unknown review status');
    }
    final nutrients = _object(json['nutrients_per_100g'], 'nutrients_per_100g');
    _expectKeys(nutrients, const {
      'energy_kcal',
      'protein_g',
      'carbohydrate_g',
      'fat_g',
      'fibre_g',
    }, 'NutrientsPer100g');
    for (final key in nutrients.keys) {
      final value = nutrients[key];
      if (value != null && value is! num) {
        throw const FormatException('nutrient value must be numeric');
      }
    }
    return NutritionFood(
      foodId: _string(json, 'food_id', 'NutritionFood'),
      nameZh: _string(json, 'name_zh', 'NutritionFood'),
      category: category,
      imageKey: _nullableString(json['image_key'], 'NutritionFood.image_key'),
    );
  }
}

class NutritionFoodList {
  final String catalogVersion;
  final List<NutritionFood> foods;
  const NutritionFoodList({required this.catalogVersion, required this.foods});

  factory NutritionFoodList.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {'catalog_version', 'foods'}, 'NutritionFoodList');
    return NutritionFoodList(
      catalogVersion: _string(json, 'catalog_version', 'NutritionFoodList'),
      foods: _list(json['foods'], 'foods')
          .map((value) => NutritionFood.fromJson(_object(value, 'food')))
          .toList(growable: false),
    );
  }
}

class HouseholdPortion {
  final String unitCode;
  final int amountMin;
  final int amountMax;
  final String unitLabel;
  final bool approximate;
  final String limitationCode;

  const HouseholdPortion({
    required this.unitCode,
    required this.amountMin,
    required this.amountMax,
    required this.unitLabel,
    required this.approximate,
    required this.limitationCode,
  });

  factory HouseholdPortion.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {
      'unit_code',
      'amount_min',
      'amount_max',
      'unit_label',
      'approximate',
      'limitation_code',
    }, 'HouseholdPortion');
    final approximate = json['approximate'];
    if (approximate is! bool) {
      throw const FormatException('HouseholdPortion.approximate must be bool');
    }
    return HouseholdPortion(
      unitCode: _string(json, 'unit_code', 'HouseholdPortion'),
      amountMin: _integer(json, 'amount_min', 'HouseholdPortion'),
      amountMax: _integer(json, 'amount_max', 'HouseholdPortion'),
      unitLabel: _string(json, 'unit_label', 'HouseholdPortion'),
      approximate: approximate,
      limitationCode: _string(json, 'limitation_code', 'HouseholdPortion'),
    );
  }
}

class FoodAlternative {
  final String foodId;
  final int gramMin;
  final int gramMax;
  final HouseholdPortion householdPortion;
  final List<String> allergenCodes;
  final String? imageKey;

  const FoodAlternative({
    required this.foodId,
    required this.gramMin,
    required this.gramMax,
    required this.householdPortion,
    required this.allergenCodes,
    required this.imageKey,
  });

  factory FoodAlternative.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {
      'food_id',
      'gram_min',
      'gram_max',
      'household_portion',
      'allergen_codes',
      'image_key',
    }, 'FoodAlternative');
    return FoodAlternative(
      foodId: _string(json, 'food_id', 'FoodAlternative'),
      gramMin: _integer(json, 'gram_min', 'FoodAlternative'),
      gramMax: _integer(json, 'gram_max', 'FoodAlternative'),
      householdPortion: HouseholdPortion.fromJson(
        _object(json['household_portion'], 'household_portion'),
      ),
      allergenCodes:
          _validateAllergenCodes(json['allergen_codes'], 'allergen_codes'),
      imageKey: _nullableString(json['image_key'], 'image_key'),
    );
  }
}

class MealFoodItem {
  final String foodId;
  final int gramMin;
  final int gramMax;
  final int guidelineEquivalentG;
  final HouseholdPortion householdPortion;
  final String preparationCode;
  final List<String> allergenCodes;
  final String? imageKey;
  final List<FoodAlternative> alternatives;

  const MealFoodItem({
    required this.foodId,
    required this.gramMin,
    required this.gramMax,
    required this.guidelineEquivalentG,
    required this.householdPortion,
    required this.preparationCode,
    required this.allergenCodes,
    required this.imageKey,
    required this.alternatives,
  });

  factory MealFoodItem.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {
      'food_id',
      'gram_min',
      'gram_max',
      'guideline_equivalent_g',
      'household_portion',
      'preparation_code',
      'allergen_codes',
      'image_key',
      'alternatives',
    }, 'MealFoodItem');
    return MealFoodItem(
      foodId: _string(json, 'food_id', 'MealFoodItem'),
      gramMin: _integer(json, 'gram_min', 'MealFoodItem'),
      gramMax: _integer(json, 'gram_max', 'MealFoodItem'),
      guidelineEquivalentG: _integer(
        json,
        'guideline_equivalent_g',
        'MealFoodItem',
      ),
      householdPortion: HouseholdPortion.fromJson(
        _object(json['household_portion'], 'household_portion'),
      ),
      preparationCode: _string(json, 'preparation_code', 'MealFoodItem'),
      allergenCodes:
          _validateAllergenCodes(json['allergen_codes'], 'allergen_codes'),
      imageKey: _nullableString(json['image_key'], 'image_key'),
      alternatives: _list(json['alternatives'], 'alternatives')
          .map(
            (value) => FoodAlternative.fromJson(_object(value, 'alternative')),
          )
          .toList(growable: false),
    );
  }
}

class MealTemplate {
  final NutritionMeal meal;
  final List<String> rationaleCodes;
  final List<MealFoodItem> items;
  const MealTemplate({
    required this.meal,
    required this.rationaleCodes,
    required this.items,
  });

  factory MealTemplate.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {
      'meal',
      'rationale_codes',
      'items',
    }, 'MealTemplate');
    return MealTemplate(
      meal: NutritionMeal.parse(json['meal']),
      rationaleCodes: _stringList(json['rationale_codes'], 'rationale_codes'),
      items: _list(json['items'], 'items')
          .map((value) => MealFoodItem.fromJson(_object(value, 'meal item')))
          .toList(growable: false),
    );
  }
}

class DayRecommendation {
  final NutritionDayKind dayKind;
  final List<String> rationaleCodes;
  final List<MealTemplate> meals;
  const DayRecommendation({
    required this.dayKind,
    required this.rationaleCodes,
    required this.meals,
  });

  factory DayRecommendation.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {
      'day_kind',
      'rationale_codes',
      'meals',
      'food_group_summary',
    }, 'DayRecommendation');
    final meals = _list(json['meals'], 'meals')
        .map((value) => MealTemplate.fromJson(_object(value, 'meal')))
        .toList(growable: false);
    if (meals.length != 3 || meals.map((e) => e.meal).toSet().length != 3) {
      throw const FormatException('recommendation requires three named meals');
    }
    final summary = _object(json['food_group_summary'], 'food_group_summary');
    _expectKeys(summary, const {
      'grains',
      'whole_grains_mixed_beans',
      'tubers',
      'vegetables',
      'fruit',
      'animal_foods',
      'dairy_ml',
      'soy_nuts',
    }, 'DailyFoodGroupSummary');
    for (final key in summary.keys) {
      _integer(summary, key, 'DailyFoodGroupSummary');
    }
    return DayRecommendation(
      dayKind: NutritionDayKind.parse(json['day_kind']),
      rationaleCodes: _stringList(json['rationale_codes'], 'rationale_codes'),
      meals: meals,
    );
  }
}

class ReplacementDiff {
  final NutritionDayKind dayKind;
  final NutritionMeal meal;
  final int itemIndex;
  final String fromFoodId;
  final String toFoodId;
  final int fromGramMin;
  final int fromGramMax;
  final int toGramMin;
  final int toGramMax;
  final List<String> validationCodes;

  const ReplacementDiff({
    required this.dayKind,
    required this.meal,
    required this.itemIndex,
    required this.fromFoodId,
    required this.toFoodId,
    required this.fromGramMin,
    required this.fromGramMax,
    required this.toGramMin,
    required this.toGramMax,
    required this.validationCodes,
  });

  factory ReplacementDiff.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {
      'day_kind',
      'meal',
      'item_index',
      'from_food_id',
      'to_food_id',
      'from_gram_min',
      'from_gram_max',
      'to_gram_min',
      'to_gram_max',
      'validation_codes',
    }, 'ReplacementDiff');
    return ReplacementDiff(
      dayKind: NutritionDayKind.parse(json['day_kind']),
      meal: NutritionMeal.parse(json['meal']),
      itemIndex: _integer(json, 'item_index', 'ReplacementDiff'),
      fromFoodId: _string(json, 'from_food_id', 'ReplacementDiff'),
      toFoodId: _string(json, 'to_food_id', 'ReplacementDiff'),
      fromGramMin: _integer(json, 'from_gram_min', 'ReplacementDiff'),
      fromGramMax: _integer(json, 'from_gram_max', 'ReplacementDiff'),
      toGramMin: _integer(json, 'to_gram_min', 'ReplacementDiff'),
      toGramMax: _integer(json, 'to_gram_max', 'ReplacementDiff'),
      validationCodes: _stringList(
        json['validation_codes'],
        'validation_codes',
      ),
    );
  }
}

class RecommendationPayload {
  final NutritionGate decisionGate;
  final String sourceContextFingerprint;
  final NutritionVersions versions;
  final NutritionTargets targets;
  final List<DayRecommendation> variants;
  final List<String> guidelineSourceCodes;
  final List<String> uncertaintyCodes;
  final String crossContactWarningCode;
  final ReplacementDiff? replacementDiff;

  const RecommendationPayload({
    required this.decisionGate,
    required this.sourceContextFingerprint,
    required this.versions,
    required this.targets,
    required this.variants,
    required this.guidelineSourceCodes,
    required this.uncertaintyCodes,
    required this.crossContactWarningCode,
    required this.replacementDiff,
  });

  factory RecommendationPayload.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {
      'schema_version',
      'requested_goal',
      'decision_gate',
      'source_context_fingerprint',
      'versions',
      'targets',
      'variants',
      'guideline_source_codes',
      'uncertainty_codes',
      'cross_contact_warning_code',
      'replacement_diff',
    }, 'RecommendationPayload');
    if (json['schema_version'] != 'v1') {
      throw const FormatException('unsupported recommendation schema');
    }
    if (!const {
      'posture_improvement',
      'fat_loss',
      'basic_strength',
    }.contains(json['requested_goal'])) {
      throw const FormatException('unsupported recommendation goal');
    }
    final variants = _list(json['variants'], 'variants')
        .map((value) => DayRecommendation.fromJson(_object(value, 'variant')))
        .toList(growable: false);
    if (variants.length != 2 ||
        variants.map((e) => e.dayKind).toSet().length != 2) {
      throw const FormatException('recommendation requires two day variants');
    }
    final fingerprint = _string(
      json,
      'source_context_fingerprint',
      'RecommendationPayload',
    );
    if (!RegExp(r'^[0-9a-f]{64}$').hasMatch(fingerprint)) {
      throw const FormatException('invalid recommendation fingerprint');
    }
    final rawDiff = json['replacement_diff'];
    return RecommendationPayload(
      decisionGate: NutritionGate.parse(json['decision_gate']),
      sourceContextFingerprint: fingerprint,
      versions: NutritionVersions.fromJson(
        _object(json['versions'], 'versions'),
      ),
      targets: NutritionTargets.fromJson(_object(json['targets'], 'targets')),
      variants: variants,
      guidelineSourceCodes: _stringList(
        json['guideline_source_codes'],
        'guideline_source_codes',
      ),
      uncertaintyCodes: _stringList(
        json['uncertainty_codes'],
        'uncertainty_codes',
      ),
      crossContactWarningCode: _string(
        json,
        'cross_contact_warning_code',
        'RecommendationPayload',
      ),
      replacementDiff: rawDiff == null
          ? null
          : ReplacementDiff.fromJson(_object(rawDiff, 'replacement_diff')),
    );
  }
}

class NutritionRecommendation {
  final String recommendationId;
  final int version;
  final RecommendationStatus status;
  final String changeReason;
  final RecommendationPayload payload;
  final List<String> validationCodes;
  final DateTime generatedAt;

  const NutritionRecommendation({
    required this.recommendationId,
    required this.version,
    required this.status,
    required this.changeReason,
    required this.payload,
    required this.validationCodes,
    required this.generatedAt,
  });

  factory NutritionRecommendation.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {
      'recommendation_id',
      'version',
      'status',
      'change_reason',
      'source_recommendation_id',
      'superseded_by_id',
      'payload',
      'validation_codes',
      'generated_at',
      'confirmed_at',
      'superseded_at',
    }, 'NutritionRecommendation');
    final status = RecommendationStatus.parse(json['status']);
    final payload = RecommendationPayload.fromJson(
      _object(json['payload'], 'payload'),
    );
    if (!payload.decisionGate.allowsRecommendation) {
      throw const FormatException('blocked recommendation cannot be rendered');
    }
    _nullableString(
      json['source_recommendation_id'],
      'source_recommendation_id',
    );
    _nullableString(json['superseded_by_id'], 'superseded_by_id');
    _nullableDateTime(json['confirmed_at'], 'confirmed_at');
    _nullableDateTime(json['superseded_at'], 'superseded_at');
    if (status == RecommendationStatus.active && json['confirmed_at'] == null) {
      throw const FormatException('active recommendation lacks confirmation');
    }
    return NutritionRecommendation(
      recommendationId: _string(
        json,
        'recommendation_id',
        'NutritionRecommendation',
      ),
      version: _integer(json, 'version', 'NutritionRecommendation'),
      status: status,
      changeReason: _string(json, 'change_reason', 'NutritionRecommendation'),
      payload: payload,
      validationCodes: _stringList(
        json['validation_codes'],
        'validation_codes',
      ),
      generatedAt: _dateTime(json, 'generated_at', 'NutritionRecommendation'),
    );
  }
}

class RecommendationResult {
  final bool hasRecommendation;
  final NutritionRecommendation? recommendation;
  final String? operationStatus;
  final String? supersededRecommendationId;
  final int? previewResultingVersion;

  const RecommendationResult({
    required this.hasRecommendation,
    required this.recommendation,
    required this.operationStatus,
    required this.supersededRecommendationId,
    required this.previewResultingVersion,
  });

  factory RecommendationResult.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {
      'has_recommendation',
      'recommendation',
      'operation_status',
      'superseded_recommendation_id',
      'preview_resulting_version',
    }, 'RecommendationResult');
    final has = json['has_recommendation'];
    if (has is! bool) {
      throw const FormatException('has_recommendation must be bool');
    }
    final raw = json['recommendation'];
    final recommendation = raw == null
        ? null
        : NutritionRecommendation.fromJson(_object(raw, 'recommendation'));
    if (has != (recommendation != null)) {
      throw const FormatException('inconsistent recommendation result');
    }
    return RecommendationResult(
      hasRecommendation: has,
      recommendation: recommendation,
      operationStatus: _nullableString(
        json['operation_status'],
        'operation_status',
      ),
      supersededRecommendationId: _nullableString(
        json['superseded_recommendation_id'],
        'superseded_recommendation_id',
      ),
      previewResultingVersion: _nullableInt(
        json['preview_resulting_version'],
        'preview_resulting_version',
      ),
    );
  }
}

class ReplacementSelection {
  final NutritionDayKind dayKind;
  final NutritionMeal meal;
  final int itemIndex;
  final String fromFoodId;
  final String toFoodId;

  const ReplacementSelection({
    required this.dayKind,
    required this.meal,
    required this.itemIndex,
    required this.fromFoodId,
    required this.toFoodId,
  });

  Map<String, dynamic> toJson({
    required NutritionRecommendation active,
    required String timezone,
    String? idempotencyKey,
  }) => {
    'iana_timezone': timezone,
    'expected_version': active.version,
    'expected_fingerprint': active.payload.sourceContextFingerprint,
    'day_kind': dayKind.wire,
    'meal': meal.wire,
    'item_index': itemIndex,
    'from_food_id': fromFoodId,
    'to_food_id': toFoodId,
    'idempotency_key': ?idempotencyKey,
  };
}

void _expectKeys(
  Map<String, dynamic> json,
  Set<String> allowed,
  String context,
) {
  final unknown = json.keys.where((key) => !allowed.contains(key));
  if (unknown.isNotEmpty) throw FormatException('$context has unknown fields');
}

Map<String, dynamic> _object(Object? raw, String context) {
  if (raw is! Map<String, dynamic>) {
    throw FormatException('$context must be an object');
  }
  return raw;
}

List<dynamic> _list(Object? raw, String context) {
  if (raw is! List) throw FormatException('$context must be a list');
  return raw;
}

String _string(Map<String, dynamic> json, String key, String context) {
  final value = json[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$context.$key must be a non-empty string');
  }
  return value;
}

String? _nullableString(Object? raw, String context) {
  if (raw == null) return null;
  if (raw is! String) throw FormatException('$context must be a string');
  return raw;
}

int _integer(Map<String, dynamic> json, String key, String context) {
  final value = json[key];
  if (value is! int) throw FormatException('$context.$key must be an integer');
  return value;
}

bool _boolean(Map<String, dynamic> json, String key, String context) {
  final value = json[key];
  if (value is! bool) throw FormatException('$context.$key must be a bool');
  return value;
}

int? _nullableInt(Object? raw, String context) {
  if (raw == null) return null;
  if (raw is! int) throw FormatException('$context must be an integer');
  return raw;
}

List<String> _stringList(Object? raw, String context) {
  if (raw is! List || raw.any((value) => value is! String)) {
    throw FormatException('$context must be a string list');
  }
  return List<String>.unmodifiable(raw.cast<String>());
}

List<String> _validateAllergenCodes(Object? raw, String context) {
  const allowed = {
    'gluten_cereal',
    'crustacean',
    'fish',
    'egg',
    'peanut',
    'soy',
    'milk',
    'tree_nut',
  };
  final values = _stringList(raw, context);
  if (values.toSet().length != values.length ||
      values.any((value) => !allowed.contains(value))) {
    throw FormatException('$context contains an invalid code');
  }
  return values;
}

List<String> _validateExclusionCodes(Object? raw, String context) {
  const allowed = {'avoid_pork', 'avoid_beef'};
  final values = _stringList(raw, context);
  if (values.toSet().length != values.length ||
      values.any((value) => !allowed.contains(value))) {
    throw FormatException('$context contains an invalid code');
  }
  return values;
}

DateTime _dateTime(Map<String, dynamic> json, String key, String context) {
  final raw = json[key];
  if (raw is! String) throw FormatException('$context.$key must be a datetime');
  final parsed = DateTime.tryParse(raw);
  if (parsed == null) throw FormatException('$context.$key is invalid');
  return parsed;
}

DateTime? _nullableDateTime(Object? raw, String context) {
  if (raw == null) return null;
  if (raw is! String || DateTime.tryParse(raw) == null) {
    throw FormatException('$context must be a datetime');
  }
  return DateTime.parse(raw);
}

DateTime _date(Map<String, dynamic> json, String key, String context) {
  final value = _dateTime(json, key, context);
  final raw = json[key] as String;
  if (!RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(raw)) {
    throw FormatException('$context.$key must be a date');
  }
  return value;
}
