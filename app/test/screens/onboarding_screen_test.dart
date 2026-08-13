import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/core/constants.dart';
import 'package:posture_app/providers/auth_provider.dart';
import 'package:posture_app/screens/onboarding/onboarding_screen.dart';

import '../providers/_test_dio.dart';

class _NewUserAuthNotifier extends AuthNotifier {
  _NewUserAuthNotifier(super.api) {
    state = const AuthState(isLoggedIn: true, isNewUser: true);
  }
}

class _AuthRefresh extends ChangeNotifier {
  _AuthRefresh(ProviderContainer container) {
    _subscription = container.listen<AuthState>(authProvider, (_, _) {
      notifyListeners();
    });
  }

  late final ProviderSubscription<AuthState> _subscription;

  @override
  void dispose() {
    _subscription.close();
    super.dispose();
  }
}

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

Future<ProviderContainer> _pump(
  WidgetTester tester,
  FakeDioAdapter adapter,
) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1080, 1920);
  addTearDown(tester.view.resetDevicePixelRatio);
  addTearDown(tester.view.resetPhysicalSize);
  final api = _apiWith(adapter);
  final container = ProviderContainer(
    overrides: [
      apiClientProvider.overrideWithValue(api),
      authProvider.overrideWith((_) => _NewUserAuthNotifier(api)),
    ],
  );
  addTearDown(container.dispose);
  final refresh = _AuthRefresh(container);
  addTearDown(refresh.dispose);
  final router = GoRouter(
    initialLocation: '/onboarding',
    refreshListenable: refresh,
    redirect: (_, state) {
      final auth = container.read(authProvider);
      if (auth.isLoggedIn &&
          !auth.isNewUser &&
          state.matchedLocation == '/onboarding') {
        return '/today';
      }
      return null;
    },
    routes: [
      GoRoute(path: '/onboarding', builder: (_, _) => const OnboardingScreen()),
      GoRoute(
        path: '/today',
        builder: (_, _) => const Scaffold(body: Text('今日页面')),
      ),
    ],
  );
  addTearDown(router.dispose);
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: MaterialApp.router(routerConfig: router),
    ),
  );
  await tester.pumpAndSettle();
  for (var page = 0; page < 3; page += 1) {
    await tester.tap(find.text('下一步'));
    await tester.pumpAndSettle();
  }
  await tester.tap(find.text('男'));
  await tester.pump();
  return container;
}

void main() {
  testWidgets('completion requires explicit sensitive-health consent', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    await _pump(tester, adapter);

    await tester.tap(find.byKey(const Key('onboarding-finish')));
    await tester.pump();

    expect(find.text('请先确认敏感健康数据告知'), findsOneWidget);
    expect(adapter.calls, isEmpty);
  });

  testWidgets('successful completion clears new-user state and navigates', (
    tester,
  ) async {
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
    final container = await _pump(tester, adapter);

    await tester.tap(find.byKey(const Key('onboarding-health-consent')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('onboarding-finish')));
    await tester.pumpAndSettle();

    expect(find.text('今日页面'), findsOneWidget);
    expect(container.read(authProvider).isNewUser, isFalse);
  });

  testWidgets('consent failure remains visible and does not navigate', (
    tester,
  ) async {
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
    await _pump(tester, adapter);

    await tester.tap(find.byKey(const Key('onboarding-health-consent')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('onboarding-finish')));
    await tester.pumpAndSettle();

    expect(find.text('隐私告知版本已更新，请重新确认'), findsOneWidget);
    expect(find.byKey(const Key('onboarding-save-error')), findsOneWidget);
    expect(find.text('今日页面'), findsNothing);
    expect(adapter.calls.map((request) => request.method), ['GET', 'POST']);
  });
}
