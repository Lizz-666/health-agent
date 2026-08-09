import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/models/health_profile.dart';
import 'package:posture_app/models/nutrition.dart';

import '../nutrition_fixtures.dart';

void main() {
  test('strict nutrition parser accepts a complete recommendation', () {
    final result = RecommendationResult.fromJson(
      recommendationResultJson(status: 'active'),
    );
    expect(result.hasRecommendation, isTrue);
    expect(result.recommendation!.status, RecommendationStatus.active);
    expect(result.recommendation!.payload.variants, hasLength(2));
    expect(result.recommendation!.originWeeklyReviewId, isNull);
  });

  test('weekly review provenance is accepted only as a nullable string', () {
    final recommendation = recommendationJson(status: 'draft');
    recommendation['origin_weekly_review_id'] =
        '00000000-0000-0000-0000-000000000008';
    expect(
      NutritionRecommendation.fromJson(recommendation).originWeeklyReviewId,
      '00000000-0000-0000-0000-000000000008',
    );

    recommendation['origin_weekly_review_id'] = 8;
    expect(
      () => NutritionRecommendation.fromJson(recommendation),
      throwsFormatException,
    );
  });

  test('unknown result field fails closed', () {
    expect(
      () => RecommendationResult.fromJson({
        ...recommendationResultJson(),
        'surprise': true,
      }),
      throwsFormatException,
    );
  });

  test('unknown gate and recommendation status fail closed', () {
    expect(
      () => NutritionEligibility.fromJson(eligibilityJson(gate: 'fine')),
      throwsFormatException,
    );
    expect(
      () => NutritionRecommendation.fromJson(
        recommendationJson(status: 'published'),
      ),
      throwsFormatException,
    );
  });

  test('unknown catalog allergen code fails closed', () {
    final food = foodJson();
    food['allergen_codes'] = ['invented_allergen'];
    expect(() => NutritionFood.fromJson(food), throwsFormatException);
  });

  test('inconsistent result never creates a false active state', () {
    expect(
      () => RecommendationResult.fromJson({
        ...recommendationResultJson(status: 'active'),
        'has_recommendation': false,
      }),
      throwsFormatException,
    );
  });

  test('health structured nutrition fields distinguish null from empty', () {
    Map<String, dynamic> profile({required Object? allergens}) => {
      'id': 'synthetic',
      'fitness_goal': null,
      'training_experience': null,
      'weekly_frequency': null,
      'session_duration_minutes': null,
      'equipment': null,
      'pain_injury_limitations': null,
      'risk_screen': null,
      'allergies': null,
      'diet_exclusions': null,
      'food_allergen_codes': allergens,
      'excluded_food_codes': <String>[],
      'version': 1,
      'updated_at': null,
      'created_at': '2026-08-01T08:00:00Z',
    };

    expect(
      HealthProfile.fromJson(profile(allergens: null)).foodAllergenCodes,
      isNull,
    );
    expect(
      HealthProfile.fromJson(profile(allergens: <String>[])).foodAllergenCodes,
      isEmpty,
    );
  });

  test('health structured codes reject unknown and duplicate values', () {
    final update = HealthProfileUpdate(
      foodAllergenCodes: const [FoodAllergenCode.milk],
      excludedFoodCodes: const [ExcludedFoodCode.avoidBeef],
    ).toJson();
    expect(update['food_allergen_codes'], ['milk']);
    expect(update['excluded_food_codes'], ['avoid_beef']);
  });
}
