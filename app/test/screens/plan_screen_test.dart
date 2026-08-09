// app/test/screens/plan_screen_test.dart
//
// Phase 4 plan flow widget test (Task 6): generation form -> draft review ->
// confirm. Honest states are covered by the model/provider tests; this test
// covers the user-facing wiring (entry button, draft rendering, confirm action).
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
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
                'assets/training/illustrations/ex_strength_bodyweight_squat.svg',
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

Map<String, dynamic> _healthProfileJson() => {
  'configured': true,
  'profile': {
    'id': 'synthetic-user',
    'fitness_goal': 'posture_improvement',
    'training_experience': 'experienced',
    'weekly_frequency': 3,
    'session_duration_minutes': 30,
    'equipment': {'bodyweight': true, 'resistance_band': false},
    'pain_injury_limitations': [],
    'risk_screen': {},
    'allergies': [],
    'diet_exclusions': [],
    'version': 1,
    'updated_at': '2026-07-27T08:00:00Z',
    'created_at': '2026-07-27T08:00:00Z',
  },
  'readiness': {
    'readiness': 'ready',
    'risk_version': 'v1',
    'reason': 'synthetic',
    'missing_fields': [],
    'restricted_reason': null,
  },
};

Widget _wrap(ApiClient api) {
  return ProviderScope(
    overrides: [apiClientProvider.overrideWithValue(api)],
    child: const MaterialApp(home: PlanScreen()),
  );
}

Widget _wrapWithRouter(ApiClient api, GoRouter router) {
  return ProviderScope(
    overrides: [apiClientProvider.overrideWithValue(api)],
    child: MaterialApp.router(routerConfig: router),
  );
}

void main() {
  testWidgets('generation form -> draft review on generate', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/profile', (_) => _healthProfileJson())
      ..registerJson(
        'GET',
        '/training/plans/active',
        (_) => {'has_active': false},
      )
      ..registerJson(
        'GET',
        '/training/plans/draft',
        (_) => {'has_draft': false},
      )
      ..registerJson(
        'POST',
        '/training/plans:draft',
        (_) => {
          'has_draft': true,
          'draft': _draftPlanJson(),
          'decision_gate': 'eligible',
        },
      );

    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    // Generation form is shown with the generate button.
    expect(find.byKey(const Key('plan-generate-button')), findsOneWidget);
    await tester.tap(find.byKey(const Key('plan-generate-button')));
    await tester.pumpAndSettle();

    // Draft review renders the session and the confirm button.
    expect(find.textContaining('深蹲'), findsWidgets);
    expect(find.byType(SvgPicture), findsWidgets);
    expect(find.byKey(const Key('plan-confirm-button')), findsOneWidget);
    expect(find.byKey(const Key('plan-regenerate-button')), findsOneWidget);
  });

  testWidgets('draft review confirm posts to plans:confirm', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/profile', (_) => _healthProfileJson())
      ..registerJson(
        'GET',
        '/training/plans/active',
        (_) => {'has_active': false},
      )
      ..registerJson(
        'GET',
        '/training/plans/draft',
        (_) => {'has_draft': false},
      )
      ..registerJson(
        'POST',
        '/training/plans:draft',
        (_) => {
          'has_draft': true,
          'draft': _draftPlanJson(),
          'decision_gate': 'eligible',
        },
      )
      ..registerJson(
        'POST',
        '/training/plans:confirm',
        (_) => {'plan': _draftPlanJson(), 'superseded_prior': false},
      )
      ..registerJson(
        'GET',
        '/training/today',
        (_) => {'state': 'rest_day', 'local_date': '2026-07-27'},
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('plan-generate-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('plan-confirm-button')));
    await tester.pumpAndSettle();
    // Confirm hit the endpoint.
    final confirm = adapter.calls.singleWhere(
      (call) => call.path.contains('plans:confirm'),
    );
    expect(confirm.data['expected_plan_version_id'], 'pv-1');
    // Active view shows a rest day honestly (no fake session).
    expect(find.text('今天是休息日'), findsOneWidget);
  });

  testWidgets(
    'pending draft is reviewable while an older plan remains active',
    (tester) async {
      final active = _draftPlanJson()
        ..['plan_version_id'] = 'pv-active'
        ..['status'] = 'active'
        ..['confirmed_at'] = '2026-07-27T09:00:00Z';
      final adapter = FakeDioAdapter()
        ..registerJson('GET', '/health/profile', (_) => _healthProfileJson())
        ..registerJson(
          'GET',
          '/training/plans/active',
          (_) => {'has_active': true, 'plan': active},
        )
        ..registerJson(
          'GET',
          '/training/plans/draft',
          (_) => {
            'has_draft': true,
            'draft': _draftPlanJson(),
            'decision_gate': 'eligible',
          },
        );

      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('plan-confirm-button')), findsOneWidget);
      expect(find.textContaining('计划草案'), findsOneWidget);
      expect(find.textContaining('生效计划'), findsNothing);
    },
  );

  testWidgets('missing health profile blocks generation defaults', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/profile',
        (_) => {
          'configured': false,
          'profile': null,
          'readiness': {
            'readiness': 'missing_required_data',
            'risk_version': 'v1',
            'reason': 'synthetic',
            'missing_fields': ['fitness_goal'],
            'restricted_reason': null,
          },
        },
      )
      ..registerJson(
        'GET',
        '/training/plans/active',
        (_) => {'has_active': false},
      )
      ..registerJson(
        'GET',
        '/training/plans/draft',
        (_) => {'has_draft': false},
      );

    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.text('请先完善健康档案'), findsOneWidget);
    expect(find.byKey(const Key('plan-generate-button')), findsNothing);
  });

  testWidgets('active session renders local SVG and substitution action', (
    tester,
  ) async {
    final active = _draftPlanJson()
      ..['status'] = 'active'
      ..['confirmed_at'] = '2026-07-27T08:00:00Z';
    final session = (active['sessions'] as List).first as Map<String, dynamic>;
    final prescription =
        (session['prescriptions'] as List).first as Map<String, dynamic>;
    (prescription['exercise'] as Map<String, dynamic>)['substitution_ids'] = [
      'ex-alt',
    ];
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/profile', (_) => _healthProfileJson())
      ..registerJson(
        'GET',
        '/training/plans/active',
        (_) => {'has_active': true, 'plan': active},
      )
      ..registerJson(
        'GET',
        '/training/plans/draft',
        (_) => {'has_draft': false},
      )
      ..registerJson(
        'GET',
        '/training/today',
        (_) => {
          'state': 'session',
          'local_date': '2026-07-27',
          'decision_gate': 'eligible',
          'session': session,
          'feedback_outcome_state': null,
          'substitution_applied': false,
          'original_session_id': 's-1',
          'source_local_date': '2026-07-27',
        },
      );

    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.byType(SvgPicture), findsWidgets);
    expect(find.byKey(const Key('substitute-ex-1-ex-alt')), findsOneWidget);
    expect(find.byKey(const Key('feedback-completed')), findsOneWidget);
    expect(find.byKey(const Key('agent-plan-entry')), findsOneWidget);
    expect(find.byKey(const Key('agent-session-entry')), findsOneWidget);
    expect(find.byKey(const Key('agent-exercise-ex-1')), findsOneWidget);
  });

  testWidgets('exercise entry routes only entry type and owned id', (
    tester,
  ) async {
    final active = _draftPlanJson()
      ..['status'] = 'active'
      ..['confirmed_at'] = '2026-07-27T08:00:00Z';
    final session = (active['sessions'] as List).first as Map<String, dynamic>;
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/profile', (_) => _healthProfileJson())
      ..registerJson(
        'GET',
        '/training/plans/active',
        (_) => {'has_active': true, 'plan': active},
      )
      ..registerJson(
        'GET',
        '/training/plans/draft',
        (_) => {'has_draft': false},
      )
      ..registerJson(
        'GET',
        '/training/today',
        (_) => {
          'state': 'session',
          'local_date': '2026-07-27',
          'decision_gate': 'eligible',
          'session': session,
          'feedback_outcome_state': null,
          'substitution_applied': false,
          'original_session_id': 's-1',
          'source_local_date': '2026-07-27',
        },
      );
    late Uri captured;
    final router = GoRouter(
      initialLocation: '/plan',
      routes: [
        GoRoute(path: '/plan', builder: (_, _) => const PlanScreen()),
        GoRoute(
          path: '/agent',
          builder: (_, state) {
            captured = state.uri;
            return const Scaffold(body: Text('AGENT_CONTEXT_PAGE'));
          },
        ),
      ],
    );
    addTearDown(router.dispose);

    await tester.pumpWidget(_wrapWithRouter(_apiWith(adapter), router));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('agent-exercise-ex-1')));
    await tester.pumpAndSettle();

    expect(find.text('AGENT_CONTEXT_PAGE'), findsOneWidget);
    expect(captured.queryParameters, {
      'entry_type': 'training_exercise',
      'entity_id': 'ex-1',
    });
    expect(captured.queryParameters.containsKey('health_profile'), isFalse);
  });

  // -------------------------------------------------------------------------
  // Phase 7: foreground same-day adjustment + weekly-review entry.
  // -------------------------------------------------------------------------

  Map<String, dynamic> activePlanJson() => _draftPlanJson()
    ..['status'] = 'active'
    ..['confirmed_at'] = '2026-07-27T08:00:00Z';

  Map<String, dynamic> todaySessionJson({
    String? originalSessionId = 's-1',
    String? adjustmentKind,
    List<String> reasonCodes = const [],
  }) => {
    'state': 'session',
    'local_date': '2026-07-27',
    'decision_gate': 'eligible',
    'session': (activePlanJson()['sessions'] as List).first,
    'feedback_outcome_state': null,
    'substitution_applied': false,
    'original_session_id': originalSessionId,
    'source_local_date': '2026-07-27',
    'adjustment_kind': adjustmentKind,
    'adjustment_reason_codes': reasonCodes,
    'safety_status': 'eligible',
  };

  testWidgets(
    'adjustment button posts correct body using original session id, then refetches',
    (tester) async {
      final active = activePlanJson();
      final adapter = FakeDioAdapter()
        ..registerJson('GET', '/health/profile', (_) => _healthProfileJson())
        ..registerJson(
          'GET',
          '/training/plans/active',
          (_) => {'has_active': true, 'plan': active},
        )
        ..registerJson(
          'GET',
          '/training/plans/draft',
          (_) => {'has_draft': false},
        )
        ..registerJson('GET', '/training/today', (_) => todaySessionJson())
        ..registerJson(
          'POST',
          '/training/today/adjustments',
          (_) => {
            'adjustment_id': 'adj-1',
            'status': 'recorded',
            'adjustment_kind': 'shortened',
            'original_session_id': 's-1',
            'source_local_date': '2026-07-27',
            'target_minutes': 30,
            'reason_codes': ['available_time_shortened'],
          },
        );
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('today-adjust-button')), findsOneWidget);
      await tester.tap(find.byKey(const Key('today-adjust-button')));
      await tester.pumpAndSettle();

      final post = adapter.calls.firstWhere(
        (c) => c.path == '/training/today/adjustments' && c.method == 'POST',
      );
      expect(post.data['intent'], 'apply_today_adjustment');
      // Uses the ORIGINAL source session identity returned by Today.
      expect(post.data['expected_session_id'], 's-1');
      expect(post.data['expected_plan_version_id'], 'pv-1');
      expect(post.data['iana_timezone'], 'Asia/Shanghai');
      expect(post.data['idempotency_key'], isA<String>());
      // Success status banner.
      expect(find.byKey(const Key('adjust-status-applied')), findsOneWidget);
      // Today refetched after success.
      expect(
        adapter.calls
            .where((c) => c.path == '/training/today' && c.method == 'GET')
            .length,
        greaterThanOrEqualTo(2),
      );
    },
  );

  testWidgets('adjustment button disabled while applying (no duplicate post)', (
    tester,
  ) async {
    final active = activePlanJson();
    final gate = Completer<Response>();
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/profile', (_) => _healthProfileJson())
      ..registerJson(
        'GET',
        '/training/plans/active',
        (_) => {'has_active': true, 'plan': active},
      )
      ..registerJson(
        'GET',
        '/training/plans/draft',
        (_) => {'has_draft': false},
      )
      ..registerJson('GET', '/training/today', (_) => todaySessionJson())
      ..register('POST', '/training/today/adjustments', (_) => gate.future);
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('today-adjust-button')));
    await tester.pump();
    // Button disabled while in flight.
    final button = tester.widget<FilledButton>(
      find.byKey(const Key('today-adjust-button')),
    );
    expect(button.enabled, isFalse);

    gate.complete(
      Response(
        requestOptions: RequestOptions(path: '/training/today/adjustments'),
        statusCode: 200,
        data: {
          'adjustment_id': 'a',
          'status': 'recorded',
          'adjustment_kind': 'unchanged',
          'original_session_id': 's-1',
          'source_local_date': '2026-07-27',
          'reason_codes': [],
        },
      ),
    );
    await tester.pumpAndSettle();
    expect(
      adapter.calls
          .where(
            (c) =>
                c.path == '/training/today/adjustments' && c.method == 'POST',
          )
          .length,
      1,
    );
  });

  Future<void> pumpAndAssertBanner(
    WidgetTester tester,
    String code,
    int status,
    Key expectedKey,
  ) async {
    final active = activePlanJson();
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/profile', (_) => _healthProfileJson())
      ..registerJson(
        'GET',
        '/training/plans/active',
        (_) => {'has_active': true, 'plan': active},
      )
      ..registerJson(
        'GET',
        '/training/plans/draft',
        (_) => {'has_draft': false},
      )
      ..registerJson('GET', '/training/today', (_) => todaySessionJson())
      ..registerError('POST', '/training/today/adjustments', status, {
        'detail': 'x',
        'code': code,
      });
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('today-adjust-button')));
    await tester.pumpAndSettle();
    expect(find.byKey(expectedKey), findsOneWidget);
  }

  testWidgets('adjustment banner: stale_context', (tester) async {
    await pumpAndAssertBanner(
      tester,
      'stale_context',
      409,
      const Key('adjust-status-stale'),
    );
  });

  testWidgets('adjustment banner: red_flag_stop -> safety', (tester) async {
    await pumpAndAssertBanner(
      tester,
      'red_flag_stop',
      409,
      const Key('adjust-status-safety'),
    );
  });

  testWidgets('adjustment banner: missing_current_checkin', (tester) async {
    await pumpAndAssertBanner(
      tester,
      'missing_current_checkin',
      409,
      const Key('adjust-status-missing'),
    );
  });

  testWidgets('adjustment banner: adjustment_collision -> conflict', (
    tester,
  ) async {
    await pumpAndAssertBanner(
      tester,
      'adjustment_collision',
      409,
      const Key('adjust-status-conflict'),
    );
  });

  testWidgets('adjustment banner: generation_failed -> unavailable', (
    tester,
  ) async {
    await pumpAndAssertBanner(
      tester,
      'generation_failed',
      503,
      const Key('adjust-status-unavailable'),
    );
  });

  testWidgets('replayed adjustment shows replayed banner', (tester) async {
    final active = activePlanJson();
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/profile', (_) => _healthProfileJson())
      ..registerJson(
        'GET',
        '/training/plans/active',
        (_) => {'has_active': true, 'plan': active},
      )
      ..registerJson(
        'GET',
        '/training/plans/draft',
        (_) => {'has_draft': false},
      )
      ..registerJson('GET', '/training/today', (_) => todaySessionJson())
      ..registerJson(
        'POST',
        '/training/today/adjustments',
        (_) => {
          'adjustment_id': 'a',
          'status': 'replayed',
          'adjustment_kind': 'deferred',
          'original_session_id': 's-1',
          'source_local_date': '2026-07-27',
          'target_local_date': '2026-07-29',
          'reason_codes': ['no_available_time'],
        },
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('today-adjust-button')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('adjust-status-replayed')), findsOneWidget);
  });

  testWidgets('deferral renders source/target date as a non-failure state', (
    tester,
  ) async {
    final active = activePlanJson();
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/profile', (_) => _healthProfileJson())
      ..registerJson(
        'GET',
        '/training/plans/active',
        (_) => {'has_active': true, 'plan': active},
      )
      ..registerJson(
        'GET',
        '/training/plans/draft',
        (_) => {'has_draft': false},
      )
      ..registerJson(
        'GET',
        '/training/today',
        (_) => {
          'state': 'rest_day',
          'local_date': '2026-07-27',
          'adjustment_kind': 'deferred',
          'original_session_id': 's-1',
          'source_local_date': '2026-07-27',
          'target_local_date': '2026-07-29',
          'adjustment_id': 'adj-1',
          'adjustment_reason_codes': ['no_available_time'],
        },
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('today-deferral')), findsOneWidget);
    expect(find.textContaining('2026-07-29'), findsOneWidget);
    expect(find.textContaining('缺勤'), findsNothing);
  });

  testWidgets('ordinary rest day has no adjustment mutation button', (
    tester,
  ) async {
    final active = activePlanJson();
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/profile', (_) => _healthProfileJson())
      ..registerJson(
        'GET',
        '/training/plans/active',
        (_) => {'has_active': true, 'plan': active},
      )
      ..registerJson(
        'GET',
        '/training/plans/draft',
        (_) => {'has_draft': false},
      )
      ..registerJson(
        'GET',
        '/training/today',
        (_) => {
          'state': 'rest_day',
          'local_date': '2026-07-27',
          'decision_gate': 'eligible',
        },
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.text('今天是休息日'), findsOneWidget);
    expect(find.byKey(const Key('today-adjust-button')), findsNothing);
  });

  testWidgets('stale effective Today is not mislabeled as a safety signal', (
    tester,
  ) async {
    final active = activePlanJson();
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/profile', (_) => _healthProfileJson())
      ..registerJson(
        'GET',
        '/training/plans/active',
        (_) => {'has_active': true, 'plan': active},
      )
      ..registerJson(
        'GET',
        '/training/plans/draft',
        (_) => {'has_draft': false},
      )
      ..registerJson(
        'GET',
        '/training/today',
        (_) => {
          'state': 'blocked',
          'local_date': '2026-07-27',
          'change_reason': 'adjustment_stale',
          'decision_gate': 'eligible',
          'original_session_id': 's-1',
        },
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('today-status-stale')), findsOneWidget);
    expect(find.textContaining('安全风险信号'), findsNothing);
  });

  testWidgets('adjusted session renders original and effective summaries', (
    tester,
  ) async {
    final active = activePlanJson();
    final effective = Map<String, dynamic>.from(
      (activePlanJson()['sessions'] as List).first as Map<String, dynamic>,
    )..['target_minutes'] = 15;
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/profile', (_) => _healthProfileJson())
      ..registerJson(
        'GET',
        '/training/plans/active',
        (_) => {'has_active': true, 'plan': active},
      )
      ..registerJson(
        'GET',
        '/training/plans/draft',
        (_) => {'has_draft': false},
      )
      ..registerJson(
        'GET',
        '/training/today',
        (_) => {
          ...todaySessionJson(
            adjustmentKind: 'shortened',
            reasonCodes: const ['available_time_shortened'],
          ),
          'session': effective,
          'adjustment_id': 'adj-1',
        },
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('today-original-summary')), findsOneWidget);
    expect(find.byKey(const Key('today-effective-summary')), findsOneWidget);
    expect(find.textContaining('30 分钟'), findsOneWidget);
    expect(find.textContaining('15 分钟'), findsWidgets);
  });

  testWidgets('weekly-review entry navigates to /plan/weekly-review', (
    tester,
  ) async {
    final active = activePlanJson();
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/profile', (_) => _healthProfileJson())
      ..registerJson(
        'GET',
        '/training/plans/active',
        (_) => {'has_active': true, 'plan': active},
      )
      ..registerJson(
        'GET',
        '/training/plans/draft',
        (_) => {'has_draft': false},
      )
      ..registerJson('GET', '/training/today', (_) => todaySessionJson());
    late Uri captured;
    final router = GoRouter(
      initialLocation: '/plan',
      routes: [
        GoRoute(path: '/plan', builder: (_, _) => const PlanScreen()),
        GoRoute(
          path: '/plan/weekly-review',
          builder: (_, state) {
            captured = state.uri;
            return const Scaffold(body: Text('WEEKLY_REVIEW_PAGE'));
          },
        ),
      ],
    );
    addTearDown(router.dispose);

    await tester.pumpWidget(_wrapWithRouter(_apiWith(adapter), router));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('plan-weekly-review-entry')));
    await tester.pumpAndSettle();

    expect(find.text('WEEKLY_REVIEW_PAGE'), findsOneWidget);
    expect(captured.path, '/plan/weekly-review');
  });
}
