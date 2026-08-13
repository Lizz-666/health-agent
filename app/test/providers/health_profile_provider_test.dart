// app/test/providers/health_profile_provider_test.dart
//
// Phase 2 Task 5: HealthProfileNotifier behavior. All data synthetic.
// Covers: fetch (configured/empty), update, delete, parse-error clears state,
// network error, and stale-response discard.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/models/health_profile.dart';
import 'package:posture_app/providers/assessment_provider.dart' show LoadStatus;
import 'package:posture_app/providers/health_profile_provider.dart';

import '_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

ProviderContainer _container(ApiClient api) =>
    ProviderContainer(overrides: [apiClientProvider.overrideWithValue(api)]);

Map<String, dynamic> _readiness(String tier) => {
      'readiness': tier,
      'risk_version': '2026-07-22-v1',
      'reason': 'synthetic',
      'missing_fields': <String>[],
      'restricted_reason': null,
    };

Map<String, dynamic> _result(bool configured, Map<String, dynamic>? profile) =>
    {
      'configured': configured,
      'profile': profile,
      'readiness':
          _readiness(configured ? 'ready' : 'missing_required_data'),
    };

final _profile = <String, dynamic>{
  'id': 'synthetic-user-a',
  'fitness_goal': 'basic_strength',
  'training_experience': 'some_experience',
  'weekly_frequency': 3,
  'session_duration_minutes': 30,
  'equipment': {'bodyweight': true, 'resistance_band': false},
  'pain_injury_limitations': <Map<String, dynamic>>[],
  'risk_screen': <String, dynamic>{},
  'allergies': <Map<String, dynamic>>[],
  'diet_exclusions': <Map<String, dynamic>>[],
  'version': 1,
  'updated_at': '2026-07-23T08:00:00Z',
  'created_at': '2026-07-23T08:00:00Z',
};

void main() {
  test('fetch: configured profile -> data', () async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/profile', (_) => _result(true, _profile));
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    await container.read(healthProfileProvider.notifier).fetchProfile();
    final state = container.read(healthProfileProvider);
    expect(state.status, LoadStatus.data);
    expect(state.result!.configured, isTrue);
    expect(state.result!.profile!.id, 'synthetic-user-a');
  });

  test('fetch: not-configured -> empty, profile null', () async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/profile', (_) => _result(false, null));
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    await container.read(healthProfileProvider.notifier).fetchProfile();
    final state = container.read(healthProfileProvider);
    expect(state.status, LoadStatus.empty);
    expect(state.result!.configured, isFalse);
    expect(state.result!.profile, isNull);
  });

  test('update sends PUT body and reflects data', () async {
    RequestOptions? captured;
    final adapter = FakeDioAdapter()
      ..register('PUT', '/health/profile', (options) {
        captured = options;
        return Response(
          requestOptions: options,
          statusCode: 200,
          data: _result(true, _profile),
        );
      });
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    final ok = await container.read(healthProfileProvider.notifier).updateProfile(
          const HealthProfileUpdate(weeklyFrequency: 5),
        );
    expect(ok, isTrue);
    expect(captured!.data, isA<Map>());
    expect((captured!.data as Map)['weekly_frequency'], 5);
    expect(container.read(healthProfileProvider).status, LoadStatus.data);
  });

  test('delete calls DELETE then refreshes', () async {
    final adapter = FakeDioAdapter()
      ..registerJson('DELETE', '/health/profile', (_) => {'deleted': true})
      ..registerJson('GET', '/health/profile', (_) => _result(false, null));
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    final ok = await container.read(healthProfileProvider.notifier).deleteProfile();
    expect(ok, isTrue);
    expect(container.read(healthProfileProvider).status, LoadStatus.empty);
  });

  test('2xx parse failure clears stale state -> parseError', () async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/profile', (_) => _result(true, _profile));
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    // Seed valid data first.
    await container.read(healthProfileProvider.notifier).fetchProfile();
    expect(container.read(healthProfileProvider).status, LoadStatus.data);

    // Now serve an unparseable readiness tier.
    adapter.registerJson('GET', '/health/profile', (_) => _result(true, {..._profile, 'id': null}));
    await container.read(healthProfileProvider.notifier).fetchProfile();
    final state = container.read(healthProfileProvider);
    expect(state.status, LoadStatus.parseError);
    expect(state.result, isNull); // stale not retained
  });

  test('network error -> networkError', () async {
    final adapter = FakeDioAdapter()
      ..registerError('GET', '/health/profile', 500, {'detail': 'boom'});
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    await container.read(healthProfileProvider.notifier).fetchProfile();
    expect(container.read(healthProfileProvider).status, LoadStatus.networkError);
  });

  test('stale response is discarded', () async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/profile', (_) => _result(true, {..._profile, 'id': 'user-a'}));
    final container = _container(_apiWith(adapter));
    addTearDown(container.dispose);

    // Slow first fetch (user A), then a fast second fetch (user B) wins.
    final pending = Completer<Response>();
    adapter.register('GET', '/health/profile', (_) => pending.future);
    final first = container.read(healthProfileProvider.notifier).fetchProfile();
    await Future<void>.delayed(Duration.zero);

    adapter.registerJson(
        'GET', '/health/profile', (_) => _result(true, {..._profile, 'id': 'user-b'}));
    await container.read(healthProfileProvider.notifier).fetchProfile();
    expect(container.read(healthProfileProvider).result!.profile!.id, 'user-b');

    // Late user-A response must not overwrite the winner.
    pending.complete(Response(
      requestOptions: RequestOptions(path: '/health/profile'),
      statusCode: 200,
      data: _result(true, {..._profile, 'id': 'user-a'}),
    ));
    await first;
    expect(container.read(healthProfileProvider).result!.profile!.id, 'user-b');
  });
}
