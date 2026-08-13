// Phase 9 controlled-trial Android reliability gate over real HTTP.
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:integration_test/integration_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/core/constants.dart';
import 'package:posture_app/core/storage.dart';
import 'package:posture_app/providers/auth_provider.dart';
import 'package:posture_app/screens/auth/login_screen.dart';
import 'package:posture_app/screens/auth/trial_auth_form.dart';

const String _controlHeader = 'X-Phase9-Control-Token';
const String _controlToken = 'phase9-local-control-only';
const String _account = 'synthetic-trial-01';
const String _credential = 'Synthetic-trial-passphrase-01';
const String _invitation = 'synthetic_trial_invitation_0000000000000001';

String _origin() {
  const suffix = '/api/v1';
  if (!AppConstants.apiBaseUrl.endsWith(suffix)) {
    throw StateError('API_BASE_URL must end with /api/v1');
  }
  return AppConstants.apiBaseUrl.substring(
    0,
    AppConstants.apiBaseUrl.length - suffix.length,
  );
}

Dio _controlClient() => Dio(
  BaseOptions(
    baseUrl: '${_origin()}/__phase9',
    connectTimeout: const Duration(seconds: 20),
    receiveTimeout: const Duration(seconds: 20),
    headers: {_controlHeader: _controlToken},
  ),
);

Future<void> _reset() async {
  final control = _controlClient();
  try {
    final response = await control.post<dynamic>('/reset');
    final data = response.data;
    if (response.statusCode != 200 ||
        data is! Map<String, dynamic> ||
        data['synthetic_only'] != true) {
      throw const FormatException('Invalid Phase 9 reset evidence');
    }
  } finally {
    control.close(force: true);
  }
}

Future<void> _control(String path, Map<String, dynamic> data) async {
  final control = _controlClient();
  try {
    final response = await control.post<dynamic>(path, data: data);
    if (response.statusCode != 200) {
      throw StateError('Phase 9 control failed: $path');
    }
  } finally {
    control.close(force: true);
  }
}

class _Harness extends ConsumerWidget {
  const _Harness();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    if (auth.clientIncompatible) return const LoginScreen();
    if (!auth.isLoggedIn) return const TrialAuthScreen();
    return const Scaffold(
      body: SafeArea(
        child: Center(child: Text('内测会话已就绪', key: Key('trial-session-ready'))),
      ),
    );
  }
}

class _AuthRefresh extends ChangeNotifier {
  _AuthRefresh(ProviderContainer container) {
    _subscription = container.listen<AuthState>(
      authProvider,
      (_, _) => notifyListeners(),
    );
  }

  late final ProviderSubscription<AuthState> _subscription;

  @override
  void dispose() {
    _subscription.close();
    super.dispose();
  }
}

class _BootResult {
  const _BootResult(this.container, this.router);

  final ProviderContainer container;
  final GoRouter router;
}

Widget _readyScreen() => const Scaffold(
  body: SafeArea(
    child: Center(child: Text('内测会话已就绪', key: Key('trial-session-ready'))),
  ),
);

Future<_BootResult> _boot(WidgetTester tester) async {
  final container = ProviderContainer();
  final refresh = _AuthRefresh(container);
  final router = GoRouter(
    initialLocation: '/',
    refreshListenable: refresh,
    redirect: (_, state) {
      final auth = container.read(authProvider);
      if ((!auth.isLoggedIn || auth.clientIncompatible) &&
          state.matchedLocation != '/') {
        return '/';
      }
      return null;
    },
    routes: [
      GoRoute(path: '/', builder: (_, _) => const _Harness()),
      GoRoute(path: '/onboarding', builder: (_, _) => _readyScreen()),
      GoRoute(path: '/today', builder: (_, _) => _readyScreen()),
    ],
  );
  addTearDown(container.dispose);
  addTearDown(refresh.dispose);
  addTearDown(router.dispose);
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: MaterialApp.router(routerConfig: router),
    ),
  );
  await tester.pump();
  return _BootResult(container, router);
}

Future<void> _pumpUntil(
  WidgetTester tester,
  Finder finder, {
  Duration timeout = const Duration(seconds: 30),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    if (finder.evaluate().isNotEmpty) return;
  }
  throw TestFailure('Timed out waiting for the expected widget');
}

Future<void> _activate(WidgetTester tester) async {
  await tester.enterText(
    find.byKey(const Key('trial-account-input')),
    _account,
  );
  await tester.enterText(
    find.byKey(const Key('trial-invitation-input')),
    _invitation,
  );
  await tester.enterText(
    find.byKey(const Key('trial-credential-input')),
    _credential,
  );
  await tester.tap(find.byKey(const Key('trial-auth-submit')));
  await _pumpUntil(tester, find.byKey(const Key('trial-session-ready')));
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    expect(AppConstants.clientPlatform, 'android');
    expect(AppConstants.clientVersionCode, 1);
    await AppStorage.clearTokens();
    await _reset();
  });

  testWidgets('activation, background resume, and slow request remain usable', (
    tester,
  ) async {
    final boot = await _boot(tester);
    await _activate(tester);
    expect(await AppStorage.hasToken(), isTrue);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await tester.pump(const Duration(milliseconds: 200));
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump(const Duration(milliseconds: 200));
    expect(find.byKey(const Key('trial-session-ready')), findsOneWidget);

    await _control('/faults', {
      'route': '/api/v1/user/profile',
      'kind': 'slow_response',
      'delay_ms': 600,
    });
    final watch = Stopwatch()..start();
    final response = await boot.container
        .read(apiClientProvider)
        .dio
        .get<dynamic>('/user/profile');
    watch.stop();
    expect(response.statusCode, 200);
    expect(watch.elapsedMilliseconds, greaterThanOrEqualTo(500));
    expect(find.byKey(const Key('trial-session-ready')), findsOneWidget);
  });

  testWidgets('expired session clears credentials and returns to auth', (
    tester,
  ) async {
    final boot = await _boot(tester);
    await _activate(tester);
    await _control('/sessions/expire', {'account': 'primary'});

    await expectLater(
      boot.container.read(apiClientProvider).dio.get<dynamic>('/user/profile'),
      throwsA(isA<DioException>()),
    );
    await _pumpUntil(tester, find.byKey(const Key('trial-auth-submit')));

    expect(await AppStorage.getAccessToken(), isNull);
    expect(await AppStorage.getRefreshToken(), isNull);
    expect(find.byKey(const Key('trial-session-ready')), findsNothing);
  });

  testWidgets('revoked session clears credentials and returns to auth', (
    tester,
  ) async {
    final boot = await _boot(tester);
    await _activate(tester);
    await _control('/sessions/revoke', {'account': 'primary'});

    await expectLater(
      boot.container.read(apiClientProvider).dio.get<dynamic>('/user/profile'),
      throwsA(isA<DioException>()),
    );
    await _pumpUntil(tester, find.byKey(const Key('trial-auth-submit')));

    expect(await AppStorage.getAccessToken(), isNull);
    expect(await AppStorage.getRefreshToken(), isNull);
    expect(find.byKey(const Key('trial-session-ready')), findsNothing);
  });

  testWidgets('incompatible client blocks the app before a domain write', (
    tester,
  ) async {
    final boot = await _boot(tester);
    await _activate(tester);
    await _control('/compatibility', {'minimum': 2, 'maximum': 2});

    await expectLater(
      boot.container
          .read(apiClientProvider)
          .dio
          .post<dynamic>(
            '/privacy/consent',
            data: {
              'action': 'grant',
              'notice_version': 'controlled-trial-sensitive-health-v1',
            },
          ),
      throwsA(isA<DioException>()),
    );
    await _pumpUntil(
      tester,
      find.byKey(const Key('client-incompatible-block')),
    );

    expect(find.text('当前应用版本不兼容，请更新后重试'), findsOneWidget);
    expect(await AppStorage.getAccessToken(), isNull);
    expect(await AppStorage.getRefreshToken(), isNull);
  });
}
