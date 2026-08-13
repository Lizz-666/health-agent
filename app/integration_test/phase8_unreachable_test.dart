// Phase 8 Gate 4 Android hard-gate for a genuinely unreachable app endpoint.
//
// A bounded setup client resets the disposable backend and obtains its
// synthetic JWT over real HTTP. The production Today screen and providers then
// call a different emulator-host port with no listener. No FakeDio, API
// provider override, domain fixture, real credential, or live service is used.
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

const String _expectedUnreachableBase = 'http://10.0.2.2:65534/api/v1';
const String _expectedSeedBase = 'http://10.0.2.2:8000/api/v1';
const String _seedBase = String.fromEnvironment('PHASE8_SEED_API_BASE_URL');
const String _controlHeaderName = 'X-Phase8-Control-Token';
const String _controlHeaderValue = 'phase8-local-control-only';

Future<void> _seedSyntheticSession() async {
  if (_seedBase != _expectedSeedBase ||
      AppConstants.devAdminPhone.isEmpty ||
      AppConstants.devAdminPassword.isEmpty) {
    throw StateError('Synthetic seed endpoint or credentials are not pinned');
  }

  final options = BaseOptions(
    connectTimeout: const Duration(seconds: 20),
    receiveTimeout: const Duration(seconds: 20),
    contentType: Headers.jsonContentType,
  );
  final control = Dio(
    options.copyWith(baseUrl: 'http://10.0.2.2:8000/__phase8'),
  );
  final setup = Dio(options.copyWith(baseUrl: _seedBase));
  try {
    final reset = await control.post<dynamic>(
      '/reset',
      data: {'checkpoint': 'blank_supported'},
      options: Options(headers: {_controlHeaderName: _controlHeaderValue}),
    );
    final evidence = reset.data;
    if (reset.statusCode != 200 ||
        evidence is! Map<String, dynamic> ||
        evidence['synthetic_only'] != true ||
        evidence['checkpoint'] != 'blank_supported') {
      throw const FormatException('Invalid synthetic reset evidence');
    }

    final response = await setup.post<dynamic>(
      '/auth/dev-login',
      data: {
        'phone': AppConstants.devAdminPhone,
        'password': AppConstants.devAdminPassword,
      },
    );
    if (response.statusCode != 200 || response.data is! Map<String, dynamic>) {
      throw const FormatException('Invalid synthetic login response');
    }
    final token = TokenResponse.fromJson(response.data as Map<String, dynamic>);
    if (token.accessToken.isEmpty || token.refreshToken.isEmpty) {
      throw const FormatException('Synthetic login returned empty tokens');
    }
    await AppStorage.saveTokens(token.accessToken, token.refreshToken);
  } finally {
    control.close(force: true);
    setup.close(force: true);
  }
}

Future<void> _pumpUntil(
  WidgetTester tester,
  bool Function() condition, {
  Duration timeout = const Duration(seconds: 40),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    if (condition()) return;
  }
  throw TestFailure('Timed out waiting for the unreachable state');
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    'unreachable emulator host fails closed and keeps retry visible',
    (tester) async {
      expect(
        AppConstants.apiBaseUrl,
        _expectedUnreachableBase,
        reason: 'This hard-gate must target the reserved unreachable port.',
      );
      await AppStorage.clearTokens();
      await _seedSyntheticSession();
      expect(
        await AppStorage.hasToken(),
        isTrue,
        reason: 'The bounded real-HTTP setup must persist its synthetic JWT.',
      );

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
            container.read(planProvider).todayStatus ==
                LoadStatus.networkError &&
            container.read(dailyCheckinProvider).status ==
                LoadStatus.networkError &&
            find.byKey(const Key('today-retry')).evaluate().isNotEmpty,
      );

      final failed = container.read(planProvider);
      expect(failed.todayStatus, LoadStatus.networkError);
      expect(failed.today, isNull);
      expect(failed.adjustState, AdjustApplyState.idle);
      expect(find.byKey(const Key('today-retry')), findsOneWidget);
      expect(find.byKey(const Key('today-adjust-button')), findsNothing);
      expect(find.byKey(const Key('today-checkin-submit')), findsNothing);
      expect(find.textContaining('训练安排就绪'), findsNothing);
      expect(find.textContaining('今日有训练安排'), findsNothing);
      expect(find.textContaining('今日已签到'), findsNothing);

      await tester.tap(find.byKey(const Key('today-retry')));
      expect(container.read(dailyCheckinProvider).status, LoadStatus.loading);
      await _pumpUntil(
        tester,
        () =>
            container.read(dailyCheckinProvider).status ==
                LoadStatus.networkError &&
            find.byKey(const Key('today-retry')).evaluate().isNotEmpty,
      );

      final retried = container.read(planProvider);
      expect(retried.todayStatus, LoadStatus.networkError);
      expect(retried.today, isNull);
      expect(retried.adjustState, AdjustApplyState.idle);
    },
  );
}
