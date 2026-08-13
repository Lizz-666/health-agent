// Phase 9 Android gate for a genuinely unreachable candidate endpoint.
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:posture_app/core/constants.dart';
import 'package:posture_app/core/storage.dart';
import 'package:posture_app/models/token.dart';
import 'package:posture_app/providers/assessment_provider.dart' show LoadStatus;
import 'package:posture_app/providers/daily_checkin_provider.dart';
import 'package:posture_app/providers/plan_provider.dart';
import 'package:posture_app/screens/today/today_screen.dart';

const String _expectedUnreachable = 'http://10.0.2.2:65533/api/v1';
const String _seedBase = String.fromEnvironment('PHASE9_SEED_API_BASE_URL');
const String _expectedSeed = 'http://10.0.2.2:8000/api/v1';
const String _controlHeader = 'X-Phase9-Control-Token';
const String _controlToken = 'phase9-local-control-only';

Future<void> _seedSession() async {
  if (AppConstants.apiBaseUrl != _expectedUnreachable ||
      _seedBase != _expectedSeed) {
    throw StateError('Phase 9 unreachable endpoints are not pinned');
  }
  final headers = {
    'X-Client-Platform': AppConstants.clientPlatform,
    'X-Client-Version-Code': AppConstants.clientVersionCode.toString(),
  };
  final control = Dio(
    BaseOptions(
      baseUrl: 'http://10.0.2.2:8000/__phase9',
      connectTimeout: const Duration(seconds: 20),
      receiveTimeout: const Duration(seconds: 20),
      headers: {_controlHeader: _controlToken},
    ),
  );
  final setup = Dio(
    BaseOptions(
      baseUrl: _seedBase,
      connectTimeout: const Duration(seconds: 20),
      receiveTimeout: const Duration(seconds: 20),
      headers: headers,
    ),
  );
  try {
    final reset = await control.post<dynamic>('/reset');
    if (reset.statusCode != 200 ||
        reset.data is! Map<String, dynamic> ||
        (reset.data as Map<String, dynamic>)['synthetic_only'] != true) {
      throw const FormatException('Invalid Phase 9 reset evidence');
    }
    final response = await setup.post<dynamic>(
      '/auth/trial/activate',
      data: {
        'account_name': 'synthetic-trial-01',
        'credential': 'Synthetic-trial-passphrase-01',
        'invitation_code': 'synthetic_trial_invitation_0000000000000001',
        'provider_id': 'offline_password',
        'device_key': 'synthetic-device-key-0000000000000001',
      },
    );
    final token = TokenResponse.fromJson(response.data as Map<String, dynamic>);
    await AppStorage.saveTokens(token.accessToken, token.refreshToken);
  } finally {
    control.close(force: true);
    setup.close(force: true);
  }
}

Future<void> _pumpUntil(WidgetTester tester, bool Function() condition) async {
  final deadline = DateTime.now().add(const Duration(seconds: 40));
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    if (condition()) return;
  }
  throw TestFailure('Timed out waiting for unreachable state');
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('unreachable candidate fails closed and explicit retry remains', (
    tester,
  ) async {
    await AppStorage.clearTokens();
    await _seedSession();

    final container = ProviderContainer();
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: TodayScreen()),
      ),
    );
    await _pumpUntil(
      tester,
      () =>
          container.read(planProvider).todayStatus == LoadStatus.networkError &&
          container.read(dailyCheckinProvider).status ==
              LoadStatus.networkError &&
          find.byKey(const Key('today-retry')).evaluate().isNotEmpty,
    );

    expect(find.byKey(const Key('today-adjust-button')), findsNothing);
    expect(find.byKey(const Key('today-checkin-submit')), findsNothing);
    await tester.tap(find.byKey(const Key('today-retry')));
    await _pumpUntil(
      tester,
      () =>
          container.read(dailyCheckinProvider).status ==
              LoadStatus.networkError &&
          find.byKey(const Key('today-retry')).evaluate().isNotEmpty,
    );
    expect(container.read(planProvider).today, isNull);
    expect(container.read(planProvider).adjustState, AdjustApplyState.idle);
  });
}
