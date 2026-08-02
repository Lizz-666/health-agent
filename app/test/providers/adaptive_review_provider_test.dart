// app/test/providers/adaptive_review_provider_test.dart
//
// Behavior tests for the weekly review provider. The review endpoints are not
// implemented on the backend (Codex Task 3); these tests use the fake Dio
// adapter against the specified paths and assert that real 404 / network /
// unknown-code responses fail closed as `unavailable`, never as a fabricated
// review. GET never POSTs; generation is explicit only.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/providers/adaptive_review_provider.dart';

import '_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

Map<String, dynamic> _snapshotJson() => {
  'review_id': 'rv-1',
  'plan_version_id': 'pv-1',
  'week_index': 1,
  'review_version': 1,
  'period_start': '2026-07-20',
  'period_end': '2026-07-26',
  'execution': {
    'scheduled': 3,
    'completed': 3,
    'partial': 0,
    'too_busy': 0,
    'intentional_rest': 0,
    'discomfort': 0,
    'active_rest': 0,
    'safety_adjustment': 0,
    'unavailable': 0,
    'effective': 3,
  },
  'execution_trend': {'available': true, 'direction': 'improving'},
  'adjustments': {
    'shortened': 0,
    'recovery': 0,
    'deferred': 0,
    'active_rest': 0,
    'unchanged': 0,
    'missing': 0,
    'unavailable': 0,
  },
  'weight_trend': {'available': false},
  'nutrition': {'state': 'active', 'age_days': 12, 'refresh_available': false},
  'posture': {'status': 'not_due'},
  'proposals': [
    {'code': 'keep_current_plan', 'state': 'proposal'},
  ],
};

void main() {
  test('loadReview 200 -> data', () async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/training/reviews/weeks/1',
        (_) => _snapshotJson(),
      );
    final c = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(c.dispose);
    await c.read(adaptiveReviewProvider.notifier).loadReview(1);
    final s = c.read(adaptiveReviewProvider);
    expect(s.phase, ReviewPhase.data);
    expect(s.snapshot, isNotNull);
    expect(s.snapshot!.weekIndex, 1);
  });

  test('response for a different week fails closed', () async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/training/reviews/weeks/1',
        (_) => _snapshotJson()..['week_index'] = 2,
      );
    final c = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(c.dispose);
    await c.read(adaptiveReviewProvider.notifier).loadReview(1);
    expect(c.read(adaptiveReviewProvider).phase, ReviewPhase.parseError);
    expect(c.read(adaptiveReviewProvider).snapshot, isNull);
  });

  test('loadReview issues no POST (read-only)', () async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/training/reviews/weeks/1',
        (_) => _snapshotJson(),
      );
    final c = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(c.dispose);
    await c.read(adaptiveReviewProvider.notifier).loadReview(1);
    expect(adapter.calls.every((x) => x.method != 'POST'), isTrue);
  });

  test('loadReview 404 review_not_generated -> notGenerated', () async {
    final adapter = FakeDioAdapter()
      ..registerError('GET', '/training/reviews/weeks/1', 404, {
        'detail': 'x',
        'code': 'review_not_generated',
      });
    final c = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(c.dispose);
    await c.read(adaptiveReviewProvider.notifier).loadReview(1);
    expect(c.read(adaptiveReviewProvider).phase, ReviewPhase.notGenerated);
  });

  test('loadReview real 404 without code -> unavailable', () async {
    final adapter = FakeDioAdapter()
      ..registerError('GET', '/training/reviews/weeks/1', 404, {
        'detail': 'Not Found',
      });
    final c = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(c.dispose);
    await c.read(adaptiveReviewProvider.notifier).loadReview(1);
    expect(c.read(adaptiveReviewProvider).phase, ReviewPhase.unavailable);
  });

  test('loadReview connectionError (no route) -> unavailable', () async {
    final adapter = FakeDioAdapter();
    final c = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(c.dispose);
    await c.read(adaptiveReviewProvider.notifier).loadReview(1);
    expect(c.read(adaptiveReviewProvider).phase, ReviewPhase.unavailable);
  });

  test('loadReview 2xx unparseable body -> parseError', () async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/training/reviews/weeks/1', (_) => {'oops': true});
    final c = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(c.dispose);
    await c.read(adaptiveReviewProvider.notifier).loadReview(1);
    expect(c.read(adaptiveReviewProvider).phase, ReviewPhase.parseError);
  });

  test('generateReview 200 -> data (explicit POST)', () async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'POST',
        '/training/reviews/weeks/2',
        (_) => _snapshotJson()..['week_index'] = 2,
      )
      ..registerJson(
        'GET',
        '/training/reviews/weeks/2',
        (_) => _snapshotJson()..['week_index'] = 2,
      );
    final c = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(c.dispose);
    await c.read(adaptiveReviewProvider.notifier).generateReview(2);
    expect(c.read(adaptiveReviewProvider).phase, ReviewPhase.data);
    final post = adapter.calls.singleWhere((x) => x.method == 'POST');
    expect(post.data, isA<Map<String, dynamic>>());
    expect((post.data as Map<String, dynamic>).keys.toSet(), {
      'iana_timezone',
      'idempotency_key',
    });
    expect(post.data['iana_timezone'], 'Asia/Shanghai');
    expect(post.data['idempotency_key'], isNotEmpty);
  });

  test('out-of-range week fails closed without a request', () async {
    final adapter = FakeDioAdapter();
    final c = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(c.dispose);

    await c.read(adaptiveReviewProvider.notifier).loadReview(0);
    expect(c.read(adaptiveReviewProvider).phase, ReviewPhase.parseError);
    await c.read(adaptiveReviewProvider.notifier).generateReview(5);
    expect(c.read(adaptiveReviewProvider).phase, ReviewPhase.parseError);
    expect(adapter.calls, isEmpty);
  });

  test('generateReview review_not_due -> notDue', () async {
    final adapter = FakeDioAdapter()
      ..registerError('POST', '/training/reviews/weeks/1', 409, {
        'detail': 'x',
        'code': 'review_not_due',
      });
    final c = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(c.dispose);
    await c.read(adaptiveReviewProvider.notifier).generateReview(1);
    expect(c.read(adaptiveReviewProvider).phase, ReviewPhase.notDue);
  });

  test('generateReview stale_context -> stale', () async {
    final adapter = FakeDioAdapter()
      ..registerError('POST', '/training/reviews/weeks/1', 409, {
        'detail': 'x',
        'code': 'stale_context',
      });
    final c = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(c.dispose);
    await c.read(adaptiveReviewProvider.notifier).generateReview(1);
    expect(c.read(adaptiveReviewProvider).phase, ReviewPhase.stale);
  });

  test('generateReview red_flag_stop -> safetyBlocked', () async {
    final adapter = FakeDioAdapter()
      ..registerError('POST', '/training/reviews/weeks/1', 409, {
        'detail': 'x',
        'code': 'red_flag_stop',
      });
    final c = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(c.dispose);
    await c.read(adaptiveReviewProvider.notifier).generateReview(1);
    expect(c.read(adaptiveReviewProvider).phase, ReviewPhase.safetyBlocked);
  });

  test('generateReview unknown code -> unavailable (fail closed)', () async {
    final adapter = FakeDioAdapter()
      ..registerError('POST', '/training/reviews/weeks/1', 500, {
        'detail': 'x',
        'code': 'explosion',
      });
    final c = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(c.dispose);
    await c.read(adaptiveReviewProvider.notifier).generateReview(1);
    expect(c.read(adaptiveReviewProvider).phase, ReviewPhase.unavailable);
  });

  test('concurrent generateReview -> single POST', () async {
    final gate = Completer<Response>();
    final adapter = FakeDioAdapter()
      ..register('POST', '/training/reviews/weeks/1', (_) => gate.future);
    final c = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    );
    addTearDown(c.dispose);
    final f1 = c.read(adaptiveReviewProvider.notifier).generateReview(1);
    final f2 = c.read(adaptiveReviewProvider.notifier).generateReview(1);
    await Future<void>.delayed(Duration.zero);
    expect(c.read(adaptiveReviewProvider).phase, ReviewPhase.loading);
    gate.complete(
      Response(
        requestOptions: RequestOptions(path: '/training/reviews/weeks/1'),
        statusCode: 200,
        data: _snapshotJson(),
      ),
    );
    await Future.wait<void>([f1, f2]);
    expect(
      adapter.calls
          .where(
            (x) => x.path == '/training/reviews/weeks/1' && x.method == 'POST',
          )
          .length,
      1,
    );
  });
}
