import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/screens/plan/plan_screen.dart';
import 'package:posture_app/screens/plan/weekly_review_screen.dart';

import '../test/providers/_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

Widget _screen(FakeDioAdapter adapter, Widget child) => ProviderScope(
  overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
  child: MaterialApp(home: child),
);

Map<String, dynamic> _healthProfile() => {
  'configured': true,
  'profile': {
    'id': 'synthetic-phase7-user',
    'fitness_goal': 'basic_strength',
    'training_experience': 'experienced',
    'weekly_frequency': 3,
    'session_duration_minutes': 30,
    'equipment': {'bodyweight': true, 'resistance_band': false},
    'pain_injury_limitations': <String>[],
    'risk_screen': <String, String>{},
    'allergies': <String>[],
    'diet_exclusions': <String>[],
    'version': 1,
    'updated_at': '2026-08-24T01:00:00Z',
    'created_at': '2026-07-27T01:00:00Z',
  },
  'readiness': {
    'readiness': 'ready',
    'risk_version': 'v1',
    'reason': 'synthetic',
    'missing_fields': <String>[],
    'restricted_reason': null,
  },
};

Map<String, dynamic> _session({int minutes = 30}) => {
  'session_id': '00000000-0000-4000-8000-000000000101',
  'week_index': 1,
  'day_of_week': 1,
  'session_order': 1,
  'target_minutes': minutes,
  'prescriptions': [
    {
      'prescription_id': '00000000-0000-4000-8000-000000000201',
      'exercise_id': 'ex-warmup',
      'sets': 1,
      'reps': 8,
      'duration_seconds': null,
      'rest_seconds': 30,
      'relation_reason': null,
      'exercise': {
        'exercise_id': 'ex-warmup',
        'name_en': 'Warmup',
        'name_zh': 'Synthetic warmup',
        'training_roles': ['warmup'],
        'difficulty': 'beginner',
        'illustration_asset_key':
            'assets/training/illustrations/ex_mobility_cat_cow.svg',
        'illustration_alt_zh': 'Synthetic warmup',
        'instruction_steps': ['step'],
        'form_cues': ['controlled'],
        'substitution_ids': <String>[],
      },
    },
  ],
};

Map<String, dynamic> _activePlan() => {
  'plan_version_id': '00000000-0000-4000-8000-000000000001',
  'requested_goal': 'basic_strength',
  'weekly_frequency': 3,
  'session_duration_minutes': 30,
  'status': 'active',
  'change_reason': 'initial_confirmation',
  'decision_gate': 'eligible',
  'generated_at': '2026-07-27T01:00:00Z',
  'confirmed_at': '2026-07-27T01:00:00Z',
  'catalog_version': 'v1',
  'policy_version': 'v1',
  'sessions': [_session()],
};

Map<String, dynamic> _today({bool adjusted = false}) => {
  'state': 'session',
  'local_date': '2026-07-27',
  'decision_gate': 'eligible',
  'session': _session(minutes: adjusted ? 15 : 30),
  'feedback_outcome_state': null,
  'substitution_applied': false,
  'original_session_id': '00000000-0000-4000-8000-000000000101',
  'source_local_date': '2026-07-27',
  'adjustment_id': adjusted ? '00000000-0000-4000-8000-000000000301' : null,
  'adjustment_kind': adjusted ? 'shortened' : null,
  'adjustment_reason_codes': adjusted
      ? ['available_time_shortened']
      : <String>[],
  'safety_status': 'eligible',
};

Map<String, dynamic> _review() => {
  'review_id': '00000000-0000-4000-8000-000000000401',
  'plan_version_id': '00000000-0000-4000-8000-000000000001',
  'week_index': 4,
  'review_version': 1,
  'input_fingerprint': 'a' * 64,
  'period_start': '2026-08-17',
  'period_end': '2026-08-23',
  'execution': {
    'scheduled': 3,
    'effective': 3,
    'completed': 1,
    'partial': 0,
    'too_busy': 1,
    'intentional_rest': 1,
    'discomfort': 0,
    'active_rest': 0,
    'safety_adjustment': 0,
    'unavailable': 0,
  },
  'execution_trend': {'available': true, 'direction': 'declining'},
  'adjustments': {
    'shortened': 1,
    'recovery': 0,
    'deferred': 0,
    'active_rest': 0,
    'unchanged': 0,
    'missing': 0,
    'unavailable': 0,
  },
  'weight_trend': {'available': true, 'direction': 'rising'},
  'nutrition': {
    'state': 'none',
    'age_days': null,
    'refresh_available': true,
    'unavailable_reason': null,
    'recommendation_id': null,
    'version': null,
  },
  'posture': {
    'status': 'due',
    'baseline_at': '2026-07-26T01:00:00Z',
    'baseline_sources': ['self_test'],
    'comparison_sources': <String>[],
    'reason': 'cycle_complete',
  },
  'safety': {
    'gate': 'eligible',
    'blocked': false,
    'reason_codes': <String>[],
    'missing_fields': <String>[],
  },
  'proposals': [
    {
      'code': 'offer_training_draft',
      'strategy': 'conservative_duration',
      'state': 'draft',
      'origin_weekly_review_id': '00000000-0000-4000-8000-000000000401',
    },
    {'code': 'offer_nutrition_refresh', 'state': 'proposal'},
    {'code': 'posture_recheck_due', 'state': 'proposal'},
    {'code': 'revisit_goal', 'state': 'proposal'},
  ],
};

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('Android enabled flow applies adjustment and renders review', (
    tester,
  ) async {
    var adjusted = false;
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/profile', (_) => _healthProfile())
      ..registerJson(
        'GET',
        '/training/plans/active',
        (_) => {'has_active': true, 'plan': _activePlan()},
      )
      ..registerJson(
        'GET',
        '/training/plans/draft',
        (_) => {'has_draft': false},
      )
      ..registerJson(
        'GET',
        '/training/today',
        (_) => _today(adjusted: adjusted),
      )
      ..registerJson('POST', '/training/today/adjustments', (_) {
        adjusted = true;
        return {
          'adjustment_id': '00000000-0000-4000-8000-000000000301',
          'status': 'recorded',
          'adjustment_kind': 'shortened',
          'original_session_id': '00000000-0000-4000-8000-000000000101',
          'source_local_date': '2026-07-27',
          'target_local_date': null,
          'target_minutes': 15,
          'reason_codes': ['available_time_shortened'],
        };
      })
      ..registerJson('GET', '/training/reviews/weeks/1', (_) => _review())
      ..registerJson('GET', '/training/reviews/weeks/4', (_) => _review());

    await tester.pumpWidget(_screen(adapter, const PlanScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('today-adjust-button')), findsOneWidget);
    await tester.tap(find.byKey(const Key('today-adjust-button')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('adjust-status-applied')), findsOneWidget);
    expect(find.byKey(const Key('today-original-summary')), findsOneWidget);
    expect(find.byKey(const Key('today-effective-summary')), findsOneWidget);
    expect(
      adapter.calls
          .where((call) => call.path == '/training/today/adjustments')
          .length,
      1,
    );

    await tester.pumpWidget(_screen(adapter, const WeeklyReviewScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('review-week-4')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('review-facts')), findsOneWidget);
    expect(find.byKey(const Key('review-proposals')), findsOneWidget);
    expect(
      find.byKey(const Key('review-proposal-offer_training_draft')),
      findsOneWidget,
    );
    expect(find.byKey(const Key('review-weight-trend')), findsOneWidget);
    final facts = tester.getCenter(find.byKey(const Key('review-facts')));
    final proposals = tester.getCenter(
      find.byKey(const Key('review-proposals')),
    );
    expect(facts.dy, lessThan(proposals.dy));
  });

  testWidgets('Android unavailable flow fails closed without mutation', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/profile', (_) => _healthProfile())
      ..registerJson(
        'GET',
        '/training/plans/active',
        (_) => {'has_active': true, 'plan': _activePlan()},
      )
      ..registerJson(
        'GET',
        '/training/plans/draft',
        (_) => {'has_draft': false},
      )
      ..registerError('GET', '/training/today', 503, {
        'detail': 'Synthetic service unavailable',
        'code': 'service_unavailable',
      })
      ..registerError('GET', '/training/reviews/weeks/1', 503, {
        'detail': 'Synthetic review unavailable',
        'code': 'service_unavailable',
      });

    await tester.pumpWidget(_screen(adapter, const PlanScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('today-status-unavailable')), findsOneWidget);
    expect(find.byKey(const Key('today-adjust-button')), findsNothing);

    await tester.pumpWidget(_screen(adapter, const WeeklyReviewScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('review-unavailable')), findsOneWidget);
    expect(find.byKey(const Key('review-facts')), findsNothing);
    expect(adapter.calls.where((call) => call.method == 'POST'), isEmpty);
  });
}
