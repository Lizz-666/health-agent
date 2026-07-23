// app/test/providers/activity_grid_provider_test.dart
//
// Phase 2 Task 5: ActivityGridNotifier behavior. All data synthetic.
// Covers: fetchGrid (data), parse-error clears state (unknown status not
// coerced to none), network error, and stale discard.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/models/activity_grid.dart';
import 'package:posture_app/providers/activity_grid_provider.dart';
import 'package:posture_app/providers/assessment_provider.dart' show LoadStatus;

import '_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

ProviderContainer _container(ApiClient api) =>
    ProviderContainer(overrides: [apiClientProvider.overrideWithValue(api)]);

Map<String, dynamic> _grid(List<String> statuses) => {
      'start_date': '2026-07-20',
      'end_date': '2026-07-${19 + statuses.length}',
      'cells': [
        for (var i = 0; i < statuses.length; i++)
          {'date': '2026-07-${20 + i}', 'status': statuses[i]},
      ],
    };

void main() {
  test('fetchGrid -> data with projected statuses', () async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/activity-grid',
          (_) => _grid(['none', 'checked_in', 'active_rest', 'safety_adjustment']));
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    await container.read(activityGridProvider.notifier).fetchGrid();
    final state = container.read(activityGridProvider);
    expect(state.status, LoadStatus.data);
    expect(
      state.grid!.cells.map((c) => c.status).toList(),
      [
        GridStatus.none,
        GridStatus.checkedIn,
        GridStatus.activeRest,
        GridStatus.safetyAdjustment,
      ],
    );
  });

  test('2xx parse failure clears stale state -> parseError', () async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/activity-grid',
          (_) => _grid(['none', 'checked_in']));
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    await container.read(activityGridProvider.notifier).fetchGrid();
    expect(container.read(activityGridProvider).status, LoadStatus.data);

    // Serve a plan-execution status the model must reject.
    adapter.registerJson(
        'GET', '/health/activity-grid', (_) => _grid(['partial_execution']));
    await container.read(activityGridProvider.notifier).fetchGrid();
    final state = container.read(activityGridProvider);
    expect(state.status, LoadStatus.parseError);
    expect(state.grid, isNull);
  });

  test('network error -> networkError', () async {
    final adapter = FakeDioAdapter()
      ..registerError('GET', '/health/activity-grid', 500, {'detail': 'boom'});
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    await container.read(activityGridProvider.notifier).fetchGrid();
    expect(container.read(activityGridProvider).status, LoadStatus.networkError);
  });

  test('stale response is discarded', () async {
    final adapter = FakeDioAdapter()
      ..registerJson(
          'GET', '/health/activity-grid', (_) => _grid(['none']));
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    final pending = Completer<Response>();
    adapter.register('GET', '/health/activity-grid', (_) => pending.future);
    final first = container.read(activityGridProvider.notifier).fetchGrid();
    await Future<void>.delayed(Duration.zero);

    adapter.registerJson('GET', '/health/activity-grid',
        (_) => _grid(['checked_in', 'active_rest']));
    await container.read(activityGridProvider.notifier).fetchGrid();
    expect(container.read(activityGridProvider).grid!.cells.length, 2);

    pending.complete(Response(
      requestOptions: RequestOptions(path: '/health/activity-grid'),
      statusCode: 200,
      data: _grid(['none']),
    ));
    await first;
    // Late single-cell response must not overwrite the 2-cell winner.
    expect(container.read(activityGridProvider).grid!.cells.length, 2);
  });
}
