// app/test/providers/daily_checkin_provider_test.dart
//
// Phase 2 Task 5: DailyCheckInNotifier behavior. All data synthetic.
// Covers: fetchToday (data/empty), saveToday, deleteCheckin, parse-error
// clears state (red_flag never downgraded), network error, and stale discard.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/models/daily_checkin.dart';
import 'package:posture_app/providers/assessment_provider.dart' show LoadStatus;
import 'package:posture_app/providers/daily_checkin_provider.dart';

import '_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

ProviderContainer _container(ApiClient api) =>
    ProviderContainer(overrides: [apiClientProvider.overrideWithValue(api)]);

Map<String, dynamic> _checkin({
  String id = 'synthetic-checkin-1',
  String riskSummary = 'normal',
}) =>
    {
      'id': id,
      'local_date': '2026-07-23',
      'sleep_quality': 'good',
      'energy': 'normal',
      'muscle_soreness': 'mild',
      'available_time': '30_min',
      'daily_status': 'checked_in',
      'abnormal_pain': false,
      'pain_followup': null,
      'risk_summary': riskSummary,
      'risk_version': '2026-07-22-v1',
      'created_at': '2026-07-23T08:00:00Z',
      'updated_at': '2026-07-23T08:00:00Z',
    };

void main() {
  test('fetchToday: checked_in -> data', () async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/checkins/today', (_) => {
            'checked_in': true,
            'checkin': _checkin(),
          });
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    await container
        .read(dailyCheckinProvider.notifier)
        .fetchToday(localDate: DateTime(2026, 7, 23));
    final state = container.read(dailyCheckinProvider);
    expect(state.status, LoadStatus.data);
    expect(state.checkin!.id, 'synthetic-checkin-1');
  });

  test('fetchToday: not checked in -> empty', () async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/checkins/today', (_) => {
            'checked_in': false,
            'checkin': null,
          });
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    await container
        .read(dailyCheckinProvider.notifier)
        .fetchToday(localDate: DateTime(2026, 7, 23));
    final state = container.read(dailyCheckinProvider);
    expect(state.status, LoadStatus.empty);
    expect(state.checkin, isNull);
  });

  test('saveToday sends PUT body and stores the check-in', () async {
    RequestOptions? captured;
    final adapter = FakeDioAdapter()
      ..register('PUT', '/health/checkins/today', (options) {
        captured = options;
        return Response(
          requestOptions: options,
          statusCode: 200,
          data: _checkin(riskSummary: 'caution'),
        );
      });
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    final ok = await container.read(dailyCheckinProvider.notifier).saveToday(
          CheckInCreate(
            localDate: DateTime(2026, 7, 23),
            sleepQuality: SleepQuality.good,
            energy: Energy.normal,
            muscleSoreness: MuscleSoreness.mild,
            availableTime: AvailableTime.thirtyMin,
            dailyStatus: DailyStatus.checkedIn,
            abnormalPain: false,
          ),
        );
    expect(ok, isTrue);
    expect(captured!.data['local_date'], '2026-07-23');
    expect(container.read(dailyCheckinProvider).checkin!.riskSummary,
        CheckInRiskSummary.caution);
  });

  test('deleteCheckin clears the in-view check-in', () async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/checkins/today', (_) => {
            'checked_in': true,
            'checkin': _checkin(),
          })
      ..registerJson(
          'DELETE', '/health/checkins/synthetic-checkin-1', (_) => {'deleted': true});
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    await container
        .read(dailyCheckinProvider.notifier)
        .fetchToday(localDate: DateTime(2026, 7, 23));
    expect(container.read(dailyCheckinProvider).checkin, isNotNull);

    final ok = await container
        .read(dailyCheckinProvider.notifier)
        .deleteCheckin('synthetic-checkin-1');
    expect(ok, isTrue);
    expect(container.read(dailyCheckinProvider).checkin, isNull);
    expect(container.read(dailyCheckinProvider).status, LoadStatus.empty);
  });

  test('2xx parse failure clears stale state (red_flag not downgraded)',
      () async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/checkins/today', (_) => {
            'checked_in': true,
            'checkin': _checkin(riskSummary: 'red_flag'),
          });
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    // Seed valid red_flag data.
    await container
        .read(dailyCheckinProvider.notifier)
        .fetchToday(localDate: DateTime(2026, 7, 23));
    expect(container.read(dailyCheckinProvider).checkin!.riskSummary,
        CheckInRiskSummary.redFlag);

    // Serve an unparseable risk_summary.
    adapter.registerJson('GET', '/health/checkins/today', (_) => {
          'checked_in': true,
          'checkin': _checkin(riskSummary: 'all_good'),
        });
    await container
        .read(dailyCheckinProvider.notifier)
        .fetchToday(localDate: DateTime(2026, 7, 23));
    final state = container.read(dailyCheckinProvider);
    expect(state.status, LoadStatus.parseError);
    expect(state.checkin, isNull);
  });

  test('network error -> networkError', () async {
    final adapter = FakeDioAdapter()
      ..registerError('GET', '/health/checkins/today', 500, {'detail': 'boom'});
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    await container
        .read(dailyCheckinProvider.notifier)
        .fetchToday(localDate: DateTime(2026, 7, 23));
    expect(container.read(dailyCheckinProvider).status, LoadStatus.networkError);
  });

  test('stale response is discarded', () async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/checkins/today', (_) => {
            'checked_in': true,
            'checkin': _checkin(id: 'user-a'),
          });
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    final pending = Completer<Response>();
    adapter.register('GET', '/health/checkins/today', (_) => pending.future);
    final first = container
        .read(dailyCheckinProvider.notifier)
        .fetchToday(localDate: DateTime(2026, 7, 23));
    await Future<void>.delayed(Duration.zero);

    adapter.registerJson('GET', '/health/checkins/today', (_) => {
          'checked_in': true,
          'checkin': _checkin(id: 'user-b'),
        });
    await container
        .read(dailyCheckinProvider.notifier)
        .fetchToday(localDate: DateTime(2026, 7, 23));
    expect(container.read(dailyCheckinProvider).checkin!.id, 'user-b');

    pending.complete(Response(
      requestOptions: RequestOptions(path: '/health/checkins/today'),
      statusCode: 200,
      data: {
        'checked_in': true,
        'checkin': _checkin(id: 'user-a'),
      },
    ));
    await first;
    expect(container.read(dailyCheckinProvider).checkin!.id, 'user-b');
  });
}
