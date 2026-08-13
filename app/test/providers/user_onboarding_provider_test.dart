import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/core/constants.dart';
import 'package:posture_app/providers/user_provider.dart';

import '_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

Map<String, dynamic> _profile() => {
  'id': 'synthetic-onboarding-user',
  'account_name': 'synthetic-trial-01',
  'height': 170.0,
  'weight': 65.0,
  'age': 25,
  'gender': 'male',
  'membership_level': 'free',
};

void main() {
  test(
    'onboarding grants current consent before writing health fields',
    () async {
      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/privacy/consent',
          (_) => {
            'purpose': 'controlled_trial_sensitive_health',
            'active': false,
            'notice_version': null,
            'sequence_no': 0,
          },
        )
        ..registerJson(
          'POST',
          '/privacy/consent',
          (_) => {
            'purpose': 'controlled_trial_sensitive_health',
            'active': true,
            'notice_version': AppConstants.privacyNoticeVersion,
            'sequence_no': 1,
          },
        )
        ..registerJson('PUT', '/user/profile', (_) => _profile());
      final notifier = UserNotifier(_apiWith(adapter));
      addTearDown(notifier.dispose);

      final result = await notifier.completeOnboarding(
        height: 170,
        weight: 65,
        age: 25,
        gender: 'male',
      );

      expect(result, isTrue);
      expect(
        adapter.calls.map((request) => '${request.method} ${request.path}'),
        ['GET /privacy/consent', 'POST /privacy/consent', 'PUT /user/profile'],
      );
      expect(adapter.calls[1].data, {
        'action': 'grant',
        'notice_version': AppConstants.privacyNoticeVersion,
      });
      expect(adapter.calls[2].data, {
        'height': 170.0,
        'weight': 65.0,
        'age': 25,
        'gender': 'male',
      });
      expect(notifier.state.profile?.hasProfile, isTrue);
      expect(notifier.state.error, isNull);
    },
  );

  test(
    'current consent is reused without creating a duplicate event',
    () async {
      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/privacy/consent',
          (_) => {
            'purpose': 'controlled_trial_sensitive_health',
            'active': true,
            'notice_version': AppConstants.privacyNoticeVersion,
            'sequence_no': 1,
          },
        )
        ..registerJson('PUT', '/user/profile', (_) => _profile());
      final notifier = UserNotifier(_apiWith(adapter));
      addTearDown(notifier.dispose);

      final result = await notifier.completeOnboarding(
        height: 170,
        weight: 65,
        age: 25,
        gender: 'male',
      );

      expect(result, isTrue);
      expect(adapter.calls.map((request) => request.method), ['GET', 'PUT']);
    },
  );

  test(
    'consent failure blocks the health write and exposes the detail',
    () async {
      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/privacy/consent',
          (_) => {
            'purpose': 'controlled_trial_sensitive_health',
            'active': false,
            'notice_version': null,
            'sequence_no': 0,
          },
        )
        ..registerError('POST', '/privacy/consent', 409, {
          'detail': '隐私告知版本已更新，请重新确认',
          'code': 'privacy_notice_stale',
        });
      final notifier = UserNotifier(_apiWith(adapter));
      addTearDown(notifier.dispose);

      final result = await notifier.completeOnboarding(
        height: 170,
        weight: 65,
        age: 25,
        gender: 'male',
      );

      expect(result, isFalse);
      expect(adapter.calls.map((request) => request.method), ['GET', 'POST']);
      expect(notifier.state.error, '隐私告知版本已更新，请重新确认');
    },
  );
}
