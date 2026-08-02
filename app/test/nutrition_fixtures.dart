Map<String, dynamic> nutritionVersionsJson() => {
  'policy_version': 'v1',
  'catalog_version': 'v1',
  'source_manifest_version': 'v1',
  'media_manifest_version': 'v1',
};

Map<String, dynamic> nutritionTargetsJson() => {
  'energy_low_kcal': 1800,
  'energy_high_kcal': 2000,
  'protein_g_min': 55,
  'protein_g_max': 65,
  'protein_energy_pct_min': 10,
  'protein_energy_pct_max': 20,
  'carbohydrate_energy_pct_min': 50,
  'carbohydrate_energy_pct_max': 65,
  'fat_energy_pct_min': 20,
  'fat_energy_pct_max': 30,
  'fibre_g_min': 25,
  'fibre_g_max': 30,
  'drinking_water_ml_min': 1500,
  'drinking_water_ml_max': 1700,
  'total_water_ml_min': 2700,
  'total_water_ml_max': 3000,
  'uncertainty_code': 'product_estimate_band_not_confidence_interval',
  'limitation_codes': ['general_health_only'],
};

Map<String, dynamic> eligibilityJson({String gate = 'eligible'}) => {
  'gate': gate,
  'reason_codes': ['eligible_profile'],
  'missing_field_codes': <String>[],
  'bmi_category': 'normal',
  'versions': nutritionVersionsJson(),
};

Map<String, dynamic> targetsResponseJson() => {
  'gate': 'eligible',
  'targets': nutritionTargetsJson(),
  'versions': nutritionVersionsJson(),
};

Map<String, dynamic> foodJson({
  String id = 'rice_white',
  String name = '白米饭',
  String? imageKey = 'assets/images/nutrition/ingredients/rice_white.jpg',
}) => {
  'food_id': id,
  'name_zh': name,
  'source_description_en': 'Synthetic food',
  'category': 'grain',
  'preparation_state': 'cooked',
  'exchange_group': 'grain_cooked',
  'source_id': 'fdc',
  'source_record_id': 'synthetic-1',
  'source_data_type': 'Foundation',
  'source_publication_date': '2026-01-01',
  'nutrients_per_100g': {
    'energy_kcal': 130,
    'protein_g': 2.5,
    'carbohydrate_g': 28,
    'fat_g': 0.3,
    'fibre_g': 0.4,
  },
  'edible_portion_min_g': 50,
  'edible_portion_max_g': 200,
  'guideline_equivalent_min_g': 50,
  'guideline_equivalent_max_g': 200,
  'household_unit_code': 'bowl',
  'preparation_note_code': 'cooked_plain',
  'allergen_codes': <String>[],
  'ingredient_tags': <String>[],
  'exclusion_codes': <String>[],
  'dark_vegetable': false,
  'image_key': imageKey,
  'generation_eligible': true,
  'review_status': 'approved',
  'reviewer_role': 'synthetic-reviewer',
  'reviewed_at': '2026-01-01',
  'quality_limit_codes': <String>[],
};

Map<String, dynamic> foodListJson() => {
  'catalog_version': 'v1',
  'foods': [
    foodJson(),
    foodJson(
      id: 'oats_cooked',
      name: '燕麦粥',
      imageKey: 'assets/images/nutrition/ingredients/oats_cooked.jpg',
    ),
  ],
};

Map<String, dynamic> _portionJson() => {
  'unit_code': 'bowl',
  'amount_min': 1,
  'amount_max': 2,
  'unit_label': '碗',
  'approximate': true,
  'limitation_code': 'household_portion_approximate',
};

Map<String, dynamic> _alternativeJson() => {
  'food_id': 'oats_cooked',
  'gram_min': 80,
  'gram_max': 120,
  'household_portion': _portionJson(),
  'allergen_codes': <String>[],
  'image_key': 'assets/images/nutrition/ingredients/oats_cooked.jpg',
};

Map<String, dynamic> _itemJson({String id = 'rice_white'}) => {
  'food_id': id,
  'gram_min': 100,
  'gram_max': 150,
  'guideline_equivalent_g': 125,
  'household_portion': _portionJson(),
  'preparation_code': 'cooked_plain',
  'allergen_codes': <String>[],
  'image_key': 'assets/images/nutrition/ingredients/rice_white.jpg',
  'alternatives': [_alternativeJson()],
};

Map<String, dynamic> _mealJson(String meal) => {
  'meal': meal,
  'rationale_codes': ['balanced_meal'],
  'items': [_itemJson()],
};

Map<String, dynamic> _variantJson(String kind) => {
  'day_kind': kind,
  'rationale_codes': ['day_balance'],
  'meals': [_mealJson('breakfast'), _mealJson('lunch'), _mealJson('dinner')],
  'food_group_summary': {
    'grains': 3,
    'whole_grains_mixed_beans': 1,
    'tubers': 1,
    'vegetables': 3,
    'fruit': 2,
    'animal_foods': 2,
    'dairy_ml': 300,
    'soy_nuts': 1,
  },
};

Map<String, dynamic> recommendationJson({
  String status = 'draft',
  bool withDiff = false,
  int version = 1,
}) => {
  'recommendation_id': '00000000-0000-0000-0000-000000000001',
  'version': version,
  'status': status,
  'change_reason': withDiff ? 'food_replacement' : 'initial_generation',
  'source_recommendation_id': null,
  'superseded_by_id': null,
  'payload': {
    'schema_version': 'v1',
    'requested_goal': 'posture_improvement',
    'decision_gate': 'eligible',
    'source_context_fingerprint':
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'versions': nutritionVersionsJson(),
    'targets': nutritionTargetsJson(),
    'variants': [_variantJson('training_day'), _variantJson('rest_day')],
    'guideline_source_codes': ['cns_2023'],
    'uncertainty_codes': ['product_estimate_band_not_confidence_interval'],
    'cross_contact_warning_code': 'verify_cross_contact',
    'replacement_diff': withDiff
        ? {
            'day_kind': 'training_day',
            'meal': 'breakfast',
            'item_index': 0,
            'from_food_id': 'rice_white',
            'to_food_id': 'oats_cooked',
            'from_gram_min': 100,
            'from_gram_max': 150,
            'to_gram_min': 80,
            'to_gram_max': 120,
            'validation_codes': ['replacement_valid'],
          }
        : null,
  },
  'validation_codes': ['recommendation_valid'],
  'generated_at': '2026-08-01T08:00:00Z',
  'confirmed_at': status == 'active' ? '2026-08-01T08:01:00Z' : null,
  'superseded_at': null,
};

Map<String, dynamic> recommendationResultJson({
  String? status,
  bool withDiff = false,
}) => {
  'has_recommendation': status != null,
  'recommendation': status == null
      ? null
      : recommendationJson(status: status, withDiff: withDiff),
      'operation_status': withDiff ? 'preview' : null,
  'superseded_recommendation_id': null,
  'preview_resulting_version': withDiff ? 2 : null,
};
