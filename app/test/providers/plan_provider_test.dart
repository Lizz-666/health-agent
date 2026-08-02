// app/test/providers/plan_provider_test.dart
//
// Plan provider behavior: loading/data/empty, stale-response discarded, parse
// error clears state, network error surfaces, and confirm/feedback flows.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/models/plan.dart';
import 'package:posture_app/providers/assessment_provider.dart' show LoadStatus;
import 'package:posture_app/providers/plan_provider.dart';

import '_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

Map<String, dynamic> _planJson() => {
  'plan_version_id': 'pv-1',
  'requested_goal': 'basic_strength',
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
            'illustration_asset_key': 'assets/training/illustrations/ex-1.svg',
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

DraftInput _draftInput() => const DraftInput(
  fitnessGoal: 'basic_strength',
  weeklyFrequency: 3,
  sessionDurationMinutes: 30,
  equipmentBodyweight: true,
  equipmentResistanceBand: false,
  ianaTimezone: 'Asia/Shanghai',
  idempotencyKey: 'k1',
);

void main() {
  test('generateDraft loads a draft', () async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'POST',
        '/training/plans:draft',
        (_) => {
          'has_draft': true,
          'draft': _planJson(),
          'decision_gate': 'eligible',
        },
      );
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(container.dispose);
    final ok = await container
        .read(planProvider.notifier)
        .generateDraft(_draftInput());
    expect(ok, isTrue);
    expect(container.read(planProvider).draftStatus, LoadStatus.data);
    expect(container.read(planProvider).draft?.planVersionId, 'pv-1');
  });

  test('fetchDraft surfaces an explicit empty state', () async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/training/plans/draft',
        (_) => {'has_draft': false},
      );
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(container.dispose);
    await container.read(planProvider.notifier).fetchDraft();
    expect(container.read(planProvider).draftStatus, LoadStatus.empty);
    expect(container.read(planProvider).draft, isNull);
  });

  test(
    'a 2xx that fails to parse clears state and surfaces parseError',
    () async {
      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/training/plans/draft',
          (_) => {'has_draft': 'oops'},
        );
      final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
      );
      addTearDown(container.dispose);
      // Seed a draft first so clearing is observable.
      adapter.registerJson(
        'POST',
        '/training/plans:draft',
        (_) => {
          'has_draft': true,
          'draft': _planJson(),
          'decision_gate': 'eligible',
        },
      );
      await container.read(planProvider.notifier).generateDraft(_draftInput());
      expect(container.read(planProvider).draft, isNotNull);
      // Now fetch returns an unparseable body.
      adapter.registerJson(
        'GET',
        '/training/plans/draft',
        (_) => {'has_draft': 'oops'},
      );
      await container.read(planProvider.notifier).fetchDraft();
      expect(container.read(planProvider).draftStatus, LoadStatus.parseError);
      expect(container.read(planProvider).draft, isNull);
    },
  );

  test(
    'stale response is discarded (older fetch does not overwrite newer)',
    () async {
      final adapter = FakeDioAdapter();
      final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
      );
      addTearDown(container.dispose);
      // Slow first fetch returns draft pv-old; a second fetch returns pv-newer.
      final slow = Completer<Response>();
      adapter.register('GET', '/training/plans/draft', (_) => slow.future);
      final first = container.read(planProvider.notifier).fetchDraft();
      await Future<void>.delayed(Duration.zero);
      // Overwrite route with the newer response and trigger a second fetch.
      adapter.registerJson(
        'GET',
        '/training/plans/draft',
        (_) => {
          'has_draft': true,
          'draft': _planJson(),
          'decision_gate': 'eligible',
        },
      );
      final second = container.read(planProvider.notifier).fetchDraft();
      await second;
      // Complete the stale (older-generation) fetch afterwards.
      slow.complete(
        Response(
          requestOptions: RequestOptions(path: '/training/plans/draft'),
          statusCode: 200,
          data: {
            'has_draft': true,
            'draft': _planJson(),
            'decision_gate': 'eligible',
          },
        ),
      );
      await first;
      // The newer generation won; state is data (not overwritten by the stale one).
      expect(container.read(planProvider).draftStatus, LoadStatus.data);
    },
  );

  test('confirm loads the active plan', () async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'POST',
        '/training/plans:confirm',
        (_) => {'plan': _planJson(), 'superseded_prior': false},
      );
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(container.dispose);
    final ok = await container
        .read(planProvider.notifier)
        .confirm(
          ConfirmInput(
            fitnessGoal: 'basic_strength',
            weeklyFrequency: 3,
            sessionDurationMinutes: 30,
            equipmentBodyweight: true,
            equipmentResistanceBand: false,
            ianaTimezone: 'Asia/Shanghai',
            idempotencyKey: 'c1',
          ),
        );
    expect(ok, isTrue);
    expect(container.read(planProvider).activeStatus, LoadStatus.data);
    expect(container.read(planProvider).activePlan, isNotNull);
  });

  test('confirm invalidates dependent nutrition state', () async {
    var invalidations = 0;
    final adapter = FakeDioAdapter()
      ..registerJson(
        'POST',
        '/training/plans:confirm',
        (_) => {'plan': _planJson(), 'superseded_prior': false},
      );
    final notifier = PlanNotifier(
      _apiWith(adapter),
      onPlanChanged: () => invalidations++,
    );
    addTearDown(notifier.dispose);

    final ok = await notifier.confirm(
      const ConfirmInput(
        fitnessGoal: 'basic_strength',
        weeklyFrequency: 3,
        sessionDurationMinutes: 30,
        equipmentBodyweight: true,
        equipmentResistanceBand: false,
        ianaTimezone: 'Asia/Shanghai',
        idempotencyKey: 'c1',
      ),
    );

    expect(ok, isTrue);
    expect(invalidations, 1);
  });

  test('today blocked state is surfaced honestly', () async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/training/today',
        (_) => {
          'state': 'blocked',
          'local_date': '2026-07-27',
          'decision_gate': 'restricted',
        },
      );
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(container.dispose);
    await container.read(planProvider.notifier).fetchToday('Asia/Shanghai');
    expect(container.read(planProvider).todayStatus, LoadStatus.data);
    expect(container.read(planProvider).today?.state, TodayState.blocked);
    expect(container.read(planProvider).today?.session, isNull);
  });

  test(
    'fetchToday reads /training/today (not the legacy plans/today path)',
    () async {
      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/training/today',
          (_) => {'state': 'no_active_plan'},
        );
      final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
      );
      addTearDown(container.dispose);
      await container.read(planProvider.notifier).fetchToday('Asia/Shanghai');
      expect(adapter.calls.any((x) => x.path == '/training/today'), isTrue);
      expect(adapter.calls.any((x) => x.path.contains('plans/today')), isFalse);
    },
  );

  test(
    'applyTodayAdjustment recorded -> posts correct body then refetches Today',
    () async {
      final adapter = FakeDioAdapter()
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
        )
        ..registerJson('GET', '/training/today', (_) {
          return {
            'state': 'session',
            'local_date': '2026-07-27',
            'session': _planJson()['sessions'][0],
            'adjustment_kind': 'shortened',
            'original_session_id': 's-1',
            'source_local_date': '2026-07-27',
            'adjustment_id': 'adj-1',
          };
        });
      final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
      );
      addTearDown(container.dispose);
      await container
          .read(planProvider.notifier)
          .applyTodayAdjustment(
            const AdjustmentRequestInput(
              expectedPlanVersionId: 'pv-1',
              expectedSessionId: 's-1',
              ianaTimezone: 'Asia/Shanghai',
              idempotencyKey: 'k1',
            ),
          );
      final post = adapter.calls.firstWhere(
        (x) => x.path == '/training/today/adjustments' && x.method == 'POST',
      );
      expect(post.data['intent'], 'apply_today_adjustment');
      expect(post.data['expected_session_id'], 's-1');
      expect((post.data as Map).keys.toSet(), {
        'intent',
        'expected_plan_version_id',
        'expected_session_id',
        'iana_timezone',
        'idempotency_key',
      });
      expect(
        container.read(planProvider).adjustState,
        AdjustApplyState.applied,
      );
      // Success refetches Today as execution authority.
      expect(
        adapter.calls.any(
          (x) => x.path == '/training/today' && x.method == 'GET',
        ),
        isTrue,
      );
      await container.read(planProvider.notifier).fetchToday('Asia/Shanghai');
      expect(container.read(planProvider).adjustState, AdjustApplyState.idle);
    },
  );

  test('POST success is not applied when authority refetch fails', () async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'POST',
        '/training/today/adjustments',
        (_) => {
          'adjustment_id': 'adj-1',
          'status': 'recorded',
          'adjustment_kind': 'shortened',
          'original_session_id': 's-1',
          'source_local_date': '2026-07-27',
          'target_minutes': 15,
          'reason_codes': ['available_time_shortened'],
        },
      );
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(container.dispose);

    await container
        .read(planProvider.notifier)
        .applyTodayAdjustment(
          const AdjustmentRequestInput(
            expectedPlanVersionId: 'pv-1',
            expectedSessionId: 's-1',
            ianaTimezone: 'Asia/Shanghai',
            idempotencyKey: 'k1',
          ),
        );

    expect(
      container.read(planProvider).adjustState,
      AdjustApplyState.unavailable,
    );
  });

  test('applyTodayAdjustment maps stable error codes distinctly', () async {
    Future<void> run(String code, int status, AdjustApplyState expected) async {
      final adapter = FakeDioAdapter()
        ..registerError('POST', '/training/today/adjustments', status, {
          'detail': 'x',
          'code': code,
        });
      final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
      );
      addTearDown(container.dispose);
      await container
          .read(planProvider.notifier)
          .applyTodayAdjustment(
            const AdjustmentRequestInput(
              expectedPlanVersionId: 'pv-1',
              expectedSessionId: 's-1',
              ianaTimezone: 'Asia/Shanghai',
              idempotencyKey: 'k',
            ),
          );
      expect(container.read(planProvider).adjustState, expected);
    }

    await run('stale_context', 409, AdjustApplyState.stale);
    await run('stale_plan_version', 409, AdjustApplyState.stale);
    await run('red_flag_stop', 409, AdjustApplyState.safetyBlocked);
    await run('pain_blocks_adjustment', 409, AdjustApplyState.safetyBlocked);
    await run('clarification_required', 409, AdjustApplyState.missingInput);
    await run('missing_current_checkin', 409, AdjustApplyState.missingInput);
    await run('adjustment_collision', 409, AdjustApplyState.conflict);
    await run('generation_failed', 503, AdjustApplyState.unavailable);
    // Unknown future code fails closed to unavailable (never safe/success).
    await run('some_future_code', 409, AdjustApplyState.unavailable);
  });

  test(
    'applyTodayAdjustment 422 schema error fails closed to unavailable',
    () async {
      final adapter = FakeDioAdapter()
        ..registerError('POST', '/training/today/adjustments', 422, {
          'detail': [
            {'msg': 'bad'},
          ],
        });
      final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
      );
      addTearDown(container.dispose);
      await container
          .read(planProvider.notifier)
          .applyTodayAdjustment(
            const AdjustmentRequestInput(
              expectedPlanVersionId: 'pv-1',
              expectedSessionId: 's-1',
              ianaTimezone: 'Asia/Shanghai',
              idempotencyKey: 'k',
            ),
          );
      expect(
        container.read(planProvider).adjustState,
        AdjustApplyState.unavailable,
      );
    },
  );

  test('replayed status yields replayed state', () async {
    final adapter = FakeDioAdapter()
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
      )
      ..registerJson(
        'GET',
        '/training/today',
        (_) => {
          'state': 'rest_day',
          'adjustment_kind': 'deferred',
          'original_session_id': 's-1',
          'source_local_date': '2026-07-27',
          'target_local_date': '2026-07-29',
          'adjustment_id': 'a',
        },
      );
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(container.dispose);
    await container
        .read(planProvider.notifier)
        .applyTodayAdjustment(
          const AdjustmentRequestInput(
            expectedPlanVersionId: 'pv-1',
            expectedSessionId: 's-1',
            ianaTimezone: 'Asia/Shanghai',
            idempotencyKey: 'k',
          ),
        );
    expect(container.read(planProvider).adjustState, AdjustApplyState.replayed);
  });

  test('concurrent duplicate press is ignored; only one POST', () async {
    final gate = Completer<Response>();
    final adapter = FakeDioAdapter()
      ..register('POST', '/training/today/adjustments', (_) => gate.future)
      ..registerJson(
        'GET',
        '/training/today',
        (_) => {'state': 'no_active_plan'},
      );
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(container.dispose);
    const input = AdjustmentRequestInput(
      expectedPlanVersionId: 'pv-1',
      expectedSessionId: 's-1',
      ianaTimezone: 'Asia/Shanghai',
      idempotencyKey: 'k',
    );
    final f1 = container
        .read(planProvider.notifier)
        .applyTodayAdjustment(input);
    // Second concurrent press must be ignored while the first is in flight.
    final f2 = container
        .read(planProvider.notifier)
        .applyTodayAdjustment(input);
    await Future<void>.delayed(Duration.zero);
    expect(container.read(planProvider).adjustState, AdjustApplyState.applying);
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
    await Future.wait([f1, f2]);
    expect(
      adapter.calls
          .where(
            (x) =>
                x.path == '/training/today/adjustments' && x.method == 'POST',
          )
          .length,
      1,
    );
  });

  test('feedback success returns true', () async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'POST',
        '/training/plans/sessions',
        (_) => {
          'feedback_id': 'f-1',
          'outcome_state': 'completed',
          'status': 'recorded',
        },
      );
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(container.dispose);
    final ok = await container
        .read(planProvider.notifier)
        .recordFeedback(
          's-1',
          FeedbackInput(
            outcomeState: OutcomeState.completed,
            idempotencyKey: 'f1',
          ),
          'Asia/Shanghai',
        );
    expect(ok, isTrue);
    expect(
      adapter.calls.last.queryParameters['iana_timezone'],
      'Asia/Shanghai',
    );
  });
}
