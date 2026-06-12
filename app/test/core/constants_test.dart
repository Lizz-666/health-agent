import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/constants.dart';

void main() {
  group('AppConstants.apiBaseUrl', () {
    test('is not empty', () {
      expect(AppConstants.apiBaseUrl, isNotEmpty);
    });

    test('starts with http', () {
      expect(AppConstants.apiBaseUrl, startsWith('http'));
    });

    test('uses compile-time API_BASE_URL or Android emulator default', () {
      const envValue = String.fromEnvironment('API_BASE_URL');
      if (envValue.isEmpty) {
        // No --dart-define provided: should use Android emulator default
        expect(AppConstants.apiBaseUrl, 'http://10.0.2.2:8000/api/v1');
      } else {
        // --dart-define=API_BASE_URL=... provided: should use override
        expect(AppConstants.apiBaseUrl, envValue);
      }
    });

    test('does not contain secrets or tokens in URL', () {
      final lower = AppConstants.apiBaseUrl.toLowerCase();
      expect(lower, isNot(contains('token=')));
      expect(lower, isNot(contains('password=')));
      expect(lower, isNot(contains('secret=')));
      expect(lower, isNot(contains('api_key=')));
    });
  });
}
