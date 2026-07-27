// app/test/screens/plan_screen_test.dart
//
// Phase 4 plan flow widget test (Task 6): generation form -> draft review ->
// confirm. Honest states are covered by the model/provider tests; this test
// covers the user-facing wiring (entry button, draft rendering, confirm action).
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/screens/plan/plan_screen.dart';

import '../providers/_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

Map<String, dynamic> _draftPlanJson() => {
      'plan_version_id': 'pv-1',
      'requested_goal': 'posture_improvement',
      'weekly_frequency': 3,
      'session_duration_minutes': 30,
      'status': 'draft',
      'change_reason': 'initial_generation',
      'decision_gate': 'eligible',
      'generated_at': '2026-07-27T08:00:00Z',
      'confirmed_at': null,
      'catalog_version': 'v1',
      'policy_version': 'v1',
      'sessions': [
        {
          'session_id': 's-1',
          'week_index': 1,
          'day_of_week': 1,
          'session_order': 1,
          'target_minutes': null,
          'prescriptions': [
            {
              'prescription_id': 'p-1',
              'exercise_id': 'ex-1',
              'sets': 3,
              'reps': 10,
              'duration_seconds': null,
              'rest_seconds': 60,
              'relation_reason': null,
              'exercise': {
                'exercise_id': 'ex-1',
                'name_en': 'Squat',
                'name_zh': '深蹲',
                'training_roles': ['strength'],
                'difficulty': 'beginner',
                'illustration_asset_key':
                    'assets/training/illustrations/ex-1.svg',
                'illustration_alt_zh': '深蹲',
                'instruction_steps': ['stand'],
                'form_cues': ['straight'],
                'substitution_ids': [],
              },
            },
          ],
        },
      ],
    };

Widget _wrap(ApiClient api) {
  return ProviderScope(
    overrides: [apiClientProvider.overrideWithValue(api)],
    child: const MaterialApp(home: PlanScreen()),
  );
}

void main() {
  testWidgets('generation form -> draft review on generate', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/training/plans/active', (_) => {'has_active': false})
      ..registerJson('GET', '/training/plans/draft', (_) => {'has_draft': false})
      ..registerJson('POST', '/training/plans:draft',
          (_) => {'has_draft': true, 'draft': _draftPlanJson(), 'decision_gate': 'eligible'});

    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    // Generation form is shown with the generate button.
    expect(find.byKey(const Key('plan-generate-button')), findsOneWidget);
    await tester.tap(find.byKey(const Key('plan-generate-button')));
    await tester.pumpAndSettle();

    // Draft review renders the session and the confirm button.
    expect(find.textContaining('深蹲'), findsWidgets);
    expect(find.byKey(const Key('plan-confirm-button')), findsOneWidget);
    expect(find.byKey(const Key('plan-regenerate-button')), findsOneWidget);
  });

  testWidgets('draft review confirm posts to plans:confirm', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/training/plans/active', (_) => {'has_active': false})
      ..registerJson('GET', '/training/plans/draft', (_) => {'has_draft': false})
      ..registerJson('POST', '/training/plans:draft',
          (_) => {'has_draft': true, 'draft': _draftPlanJson(), 'decision_gate': 'eligible'})
      ..registerJson('POST', '/training/plans:confirm',
          (_) => {'plan': _draftPlanJson(), 'superseded_prior': false})
      ..registerJson('GET', '/training/plans/today',
          (_) => {'state': 'rest_day', 'local_date': '2026-07-27'});
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('plan-generate-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('plan-confirm-button')));
    await tester.pumpAndSettle();
    // Confirm hit the endpoint.
    expect(
      adapter.calls.where((c) => c.path.contains('plans:confirm')).toList(),
      isNotEmpty,
    );
    // Active view shows a rest day honestly (no fake session).
    expect(find.text('今天是休息日'), findsOneWidget);
  });
}
