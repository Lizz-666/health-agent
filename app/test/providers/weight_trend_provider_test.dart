// app/test/providers/weight_trend_provider_test.dart
//
// Phase 2 Task 5: WeightTrendNotifier behavior. All data synthetic.
// Covers: fetchTrend (sufficient/insufficient), addWeight CRUD + refresh,
// deleteWeight, parse-error clears state, network error, and stale discard.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/models/weight_record.dart';
import 'package:posture_app/providers/assessment_provider.dart' show LoadStatus;
import 'package:posture_app/providers/weight_trend_provider.dart';

import '_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

ProviderContainer _container(ApiClient api) =>
    ProviderContainer(overrides: [apiClientProvider.overrideWithValue(api)]);

Map<String, dynamic> _record(double kg) => {
      'id': 'w-$kg',
      'recorded_at': '2026-07-23T08:00:00Z',
      'weight_kg': kg,
      'source': 'manual',
      'note': null,
      'created_at': '2026-07-23T08:00:00Z',
      'updated_at': '2026-07-23T08:00:00Z',
    };

Map<String, dynamic> _trend(List<double> kgs, {required bool sufficient}) => {
      'records': [for (final kg in kgs) _record(kg)],
      'trend': sufficient
          ? [
              {'recorded_at': '2026-07-23T08:00:00Z', 'weight_kg': 70.5},
            ]
          : <Map<String, dynamic>>[],
      'window': 7,
      'sufficient': sufficient,
    };

void main() {
  test('fetchTrend: sufficient -> data', () async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/trends/weight',
          (_) => _trend([70.0, 71.0], sufficient: true));
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    await container.read(weightTrendProvider.notifier).fetchTrend();
    final state = container.read(weightTrendProvider);
    expect(state.status, LoadStatus.data);
    expect(state.trend!.sufficient, isTrue);
    expect(state.trend!.records.length, 2);
  });

  test('fetchTrend: insufficient -> data with sufficient=false', () async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/trends/weight',
          (_) => _trend([70.0], sufficient: false));
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    await container.read(weightTrendProvider.notifier).fetchTrend();
    final state = container.read(weightTrendProvider);
    expect(state.status, LoadStatus.data);
    expect(state.trend!.sufficient, isFalse);
    expect(state.trend!.trend, isEmpty);
  });

  test('addWeight POSTs and refreshes the trend', () async {
    final adapter = FakeDioAdapter()
      ..registerJson('POST', '/health/weight-records', (_) => _record(72.0))
      ..registerJson('GET', '/health/trends/weight',
          (_) => _trend([70.0, 72.0], sufficient: true));
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    final ok = await container.read(weightTrendProvider.notifier).addWeight(
          WeightRecordInput(
              recordedAt: DateTime.utc(2026, 7, 23, 8), weightKg: 72.0),
        );
    expect(ok, isTrue);
  });

  test('deleteWeight DELETEs and refreshes the trend', () async {
    final adapter = FakeDioAdapter()
      ..registerJson('DELETE', '/health/weight-records/w-70.0',
          (_) => {'deleted': true})
      ..registerJson('GET', '/health/trends/weight',
          (_) => _trend([], sufficient: false));
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    final ok = await container
        .read(weightTrendProvider.notifier)
        .deleteWeight('w-70.0');
    expect(ok, isTrue);
    expect(container.read(weightTrendProvider).actionStatus, LoadStatus.data);
  });

  test('2xx parse failure clears stale state -> parseError', () async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/trends/weight',
          (_) => _trend([70.0], sufficient: false));
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    await container.read(weightTrendProvider.notifier).fetchTrend();
    expect(container.read(weightTrendProvider).status, LoadStatus.data);

    // Serve a non-list records field -> parse error.
    adapter.registerJson('GET', '/health/trends/weight', (_) => {
          'records': 'nope',
          'trend': <Map<String, dynamic>>[],
          'window': 7,
          'sufficient': false,
        });
    await container.read(weightTrendProvider.notifier).fetchTrend();
    final state = container.read(weightTrendProvider);
    expect(state.status, LoadStatus.parseError);
    expect(state.trend, isNull);
  });

  test('network error -> networkError', () async {
    final adapter = FakeDioAdapter()
      ..registerError('GET', '/health/trends/weight', 500, {'detail': 'boom'});
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    await container.read(weightTrendProvider.notifier).fetchTrend();
    expect(container.read(weightTrendProvider).status, LoadStatus.networkError);
  });

  test('stale response is discarded', () async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/trends/weight',
          (_) => _trend([70.0], sufficient: false));
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    final pending = Completer<Response>();
    adapter.register('GET', '/health/trends/weight', (_) => pending.future);
    final first = container.read(weightTrendProvider.notifier).fetchTrend();
    await Future<void>.delayed(Duration.zero);

    adapter.registerJson('GET', '/health/trends/weight',
        (_) => _trend([71.0, 72.0], sufficient: true));
    await container.read(weightTrendProvider.notifier).fetchTrend();
    expect(container.read(weightTrendProvider).trend!.records.length, 2);

    pending.complete(Response(
      requestOptions: RequestOptions(path: '/health/trends/weight'),
      statusCode: 200,
      data: _trend([70.0], sufficient: false),
    ));
    await first;
    // Late insufficient response must not overwrite the 2-record winner.
    expect(container.read(weightTrendProvider).trend!.records.length, 2);
  });
}
