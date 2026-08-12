import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/app.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/providers/auth_provider.dart';

import '../providers/_test_dio.dart';

class _LoggedInAuthNotifier extends AuthNotifier {
  _LoggedInAuthNotifier(super.api) {
    state = const AuthState(isLoggedIn: true);
  }
}

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

ProviderContainer _container(FakeDioAdapter adapter) {
  final api = _apiWith(adapter);
  return ProviderContainer(
    overrides: [
      apiClientProvider.overrideWithValue(api),
      authProvider.overrideWith((_) => _LoggedInAuthNotifier(api)),
    ],
  );
}

void main() {
  testWidgets('legacy root redirects to preserved posture route', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/checkins/today',
        (_) => {'checked_in': false, 'checkin': null},
      );
    final container = _container(adapter);
    addTearDown(container.dispose);
    final router = container.read(routerProvider);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();
    router.go('/');
    await tester.pumpAndSettle();

    expect(router.routeInformationProvider.value.uri.path, '/posture');
    expect(find.byIcon(Icons.search), findsOneWidget);
  });

  testWidgets('main shell uses Today Plan Agent Profile ordering', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/checkins/today',
        (_) => {'checked_in': false, 'checkin': null},
      )
      ..registerJson(
        'GET',
        '/agent/capabilities',
        (_) => {
          'runtime_enabled': false,
          'provider_configured': false,
          'provider_id': null,
          'model_id': null,
          'disclosure_version': null,
          'consent_active': false,
          'available': false,
          'result_code': 'agent_disabled',
          'message': 'Agent 当前未启用，其他功能仍可正常使用。',
          'disclosure': null,
        },
      );
    final container = _container(adapter);
    addTearDown(container.dispose);
    final router = container.read(routerProvider);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();
    router.go('/agent');
    await tester.pumpAndSettle();

    expect(find.text('今日'), findsOneWidget);
    expect(find.text('计划'), findsOneWidget);
    expect(find.text('健康助手'), findsWidgets);
    expect(find.text('我的'), findsOneWidget);
    expect(find.text('首页'), findsNothing);
    expect(find.text('健康助手当前不可用'), findsOneWidget);

    await tester.tap(find.byKey(const Key('agent-privacy-menu')));
    await tester.pumpAndSettle();
    expect(find.text('删除健康助手数据'), findsOneWidget);
  });

  testWidgets('unknown Agent query fails closed before capabilities request', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/checkins/today',
        (_) => {'checked_in': false, 'checkin': null},
      );
    final container = _container(adapter);
    addTearDown(container.dispose);
    final router = container.read(routerProvider);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();
    router.go('/agent?entry_type=general&health_payload=forbidden');
    await tester.pumpAndSettle();

    expect(find.text('健康助手入口无效'), findsOneWidget);
    expect(
      adapter.calls.where((call) => call.path == '/agent/capabilities'),
      isEmpty,
    );
  });
}
