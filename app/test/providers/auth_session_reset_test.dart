import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/providers/assessment_provider.dart';
import 'package:posture_app/providers/auth_provider.dart';
import 'package:posture_app/providers/posture_profile_provider.dart';
import 'package:posture_app/providers/posture_state_provider.dart';
import 'package:posture_app/providers/user_provider.dart';

import '_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

void main() {
  test('auth failure synchronously invalidates cached health state', () async {
    final adapter = FakeDioAdapter();
    adapter.register(
      'GET',
      '/posture/history',
      (options) => Response(
        requestOptions: options,
        statusCode: 200,
        data: [
          {
            'id': 'record-user-a',
            'issue_id': 'HN-01',
            'issue_name': '用户 A 的记录',
            'source': 'self_test',
            'method': 'self_test',
            'result': 'moderate',
            'created_at': '2026-07-18T10:00:00Z',
          },
        ],
      ),
    );
    adapter.registerJson(
      'GET',
      '/posture/profile',
      (_) => {
        'user_id': 'user-a',
        'evaluated_issues': <Map<String, dynamic>>[],
        'unevaluated_categories': <String>['head_neck'],
        'summary': {
          'total_evaluated': 0,
          'total_conflict': 0,
          'total_provisional': 0,
        },
      },
    );
    adapter.registerJson(
      'GET',
      '/user/profile',
      (_) => {
        'id': 'user-a',
        'phone': 'synthetic-user-a',
        'membership_level': 'free',
      },
    );
    final api = _apiWith(adapter);
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    // Register the authentication-failure callback, then seed synthetic
    // user-A data in each user-scoped health provider.
    container.read(authProvider);
    await container.read(assessmentProvider.notifier).fetchHistory();
    await container.read(postureProfileProvider.notifier).fetchProfile();
    await container.read(userProvider.notifier).fetchProfile();
    container
        .read(postureStateProvider.notifier)
        .updateState(issueId: 'HN-01', result: 'moderate', method: 'self_test');

    expect(container.read(assessmentProvider).history, isNotEmpty);
    expect(container.read(postureProfileProvider).profile?.userId, 'user-a');
    expect(container.read(postureStateProvider), isNotEmpty);
    expect(container.read(userProvider).profile?.id, 'user-a');

    final pendingResponse = Completer<Response>();
    adapter.register('GET', '/posture/history', (_) => pendingResponse.future);
    final oldSessionRefresh = container
        .read(assessmentProvider.notifier)
        .fetchHistory();
    await Future<void>.delayed(Duration.zero);

    api.onAuthFailed?.call();

    expect(container.read(assessmentProvider).history, isEmpty);
    expect(container.read(postureProfileProvider).profile, isNull);
    expect(container.read(postureStateProvider), isEmpty);
    expect(container.read(userProvider).profile, isNull);

    pendingResponse.complete(
      Response(
        requestOptions: RequestOptions(path: '/posture/history'),
        statusCode: 200,
        data: [
          {
            'id': 'late-record-user-a',
            'issue_id': 'HN-01',
            'issue_name': '用户 A 的延迟记录',
            'source': 'self_test',
            'method': 'self_test',
            'result': 'severe',
            'created_at': '2026-07-18T11:00:00Z',
          },
        ],
      ),
    );
    await oldSessionRefresh;
    expect(container.read(assessmentProvider).history, isEmpty);
  });
}
