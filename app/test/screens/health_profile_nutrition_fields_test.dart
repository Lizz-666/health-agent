import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/screens/profile/health_profile_screen.dart';

import '../providers/_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

Map<String, dynamic> _profileJson({Object? allergens, Object? exclusions}) => {
  'configured': true,
  'profile': {
    'id': 'synthetic-profile',
    'fitness_goal': 'posture_improvement',
    'training_experience': 'beginner',
    'weekly_frequency': 3,
    'session_duration_minutes': 30,
    'equipment': {'bodyweight': true, 'resistance_band': false},
    'pain_injury_limitations': <Map<String, dynamic>>[],
    'risk_screen': {
      'underage': 'no',
      'pregnancy_or_postpartum': 'no',
      'recent_surgery_or_major_injury': 'no',
      'major_chronic_condition': 'no',
      'eating_disorder_concern': 'no',
      'professional_instruction_limitations': 'no',
    },
    'allergies': <Map<String, dynamic>>[],
    'diet_exclusions': <Map<String, dynamic>>[],
    'food_allergen_codes': allergens,
    'excluded_food_codes': exclusions,
    'version': 1,
    'updated_at': '2026-08-01T08:00:00Z',
    'created_at': '2026-08-01T08:00:00Z',
  },
  'readiness': {
    'readiness': 'ready',
    'risk_version': 'v1',
    'reason': 'synthetic',
    'missing_fields': <String>[],
    'restricted_reason': null,
  },
};

void main() {
  testWidgets(
    'structured allergy selection preserves answered-empty semantics',
    (tester) async {
      Map<String, dynamic>? saved;
      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/health/profile',
          (_) => _profileJson(allergens: null, exclusions: null),
        )
        ..registerJson('PUT', '/health/profile', (options) {
          saved = Map<String, dynamic>.from(options.data as Map);
          return _profileJson(
            allergens: saved!['food_allergen_codes'],
            exclusions: saved!['excluded_food_codes'],
          );
        });
      await tester.pumpWidget(
        ProviderScope(
          overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
          child: const MaterialApp(home: HealthProfileScreen()),
        ),
      );
      await tester.pumpAndSettle();
      final edit = find.byKey(const Key('health-edit-button'));
      await tester.ensureVisible(edit);
      await tester.tap(edit);
      await tester.pumpAndSettle();

      final answered = find.byKey(const Key('health-allergens-answered'));
      await tester.ensureVisible(answered);
      await tester.tap(answered);
      await tester.pump();
      final milk = find.byKey(const Key('health-allergen-milk'));
      await tester.ensureVisible(milk);
      await tester.tap(milk);

      final exclusions = find.byKey(const Key('health-exclusions-answered'));
      await tester.ensureVisible(exclusions);
      await tester.tap(exclusions);
      final save = find.byKey(const Key('health-save-button'));
      await tester.ensureVisible(save);
      await tester.tap(save);
      await tester.pumpAndSettle();

      expect(saved!['food_allergen_codes'], ['milk']);
      expect(saved!['excluded_food_codes'], isEmpty);
    },
  );
}
