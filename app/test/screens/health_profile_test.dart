// app/test/screens/health_profile_test.dart
//
// Phase 2 Task 6: HealthProfileScreen contracts. All data synthetic.
// Covers: loading, not-configured/missing, configured data + restricted
// readiness, edit/correct flow (lists preserved), delete confirmation
// (cancel + confirm), networkError, parseError, narrow-screen fit, and
// logout/clearing (provider reset drops stale health UI).
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/providers/health_profile_provider.dart';
import 'package:posture_app/screens/profile/health_profile_screen.dart';

import '../providers/_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

Widget _wrap(ApiClient api) => ProviderScope(
  overrides: [apiClientProvider.overrideWithValue(api)],
  child: const MaterialApp(home: HealthProfileScreen()),
);

Map<String, dynamic> _readiness(
  String tier, {
  List<String> missing = const [],
  String? restricted,
}) => {
  'readiness': tier,
  'risk_version': '2026-07-22-v1',
  'reason': 'synthetic',
  'missing_fields': missing,
  'restricted_reason': restricted,
};

Map<String, dynamic> _result(
  bool configured,
  Map<String, dynamic>? profile,
  Map<String, dynamic> readiness,
) => {'configured': configured, 'profile': profile, 'readiness': readiness};

final _profile = <String, dynamic>{
  'id': 'synthetic-user-a',
  'fitness_goal': 'basic_strength',
  'training_experience': 'some_experience',
  'weekly_frequency': 3,
  'session_duration_minutes': 30,
  'equipment': {'bodyweight': true, 'resistance_band': false},
  'pain_injury_limitations': <Map<String, dynamic>>[
    {'body_area': '下背', 'status': 'ongoing'},
  ],
  'risk_screen': <String, dynamic>{},
  'allergies': <Map<String, dynamic>>[
    {'label': '花生'},
  ],
  'diet_exclusions': <Map<String, dynamic>>[
    {'item': '乳制品'},
  ],
  'version': 1,
  'updated_at': '2026-07-23T08:00:00Z',
  'created_at': '2026-07-23T08:00:00Z',
};

void main() {
  testWidgets('loading state shows spinner and not data/empty text', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    final completer = Completer<Response>();
    adapter.register('GET', '/health/profile', (options) => completer.future);
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 10));

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.textContaining('加载健康档案中'), findsOneWidget);
    expect(find.textContaining('尚未配置'), findsNothing);
    expect(find.textContaining('档案信息'), findsNothing);

    completer.complete(
      Response(
        requestOptions: RequestOptions(path: '/health/profile'),
        statusCode: 200,
        data: _result(false, null, _readiness('missing_required_data')),
      ),
    );
    await tester.pumpAndSettle();
  });

  testWidgets(
    'not-configured shows missing state, readiness and missing fields',
    (tester) async {
      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/health/profile',
          (_) => _result(
            false,
            null,
            _readiness(
              'missing_required_data',
              missing: ['fitness_goal', 'training_experience'],
            ),
          ),
        );
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      expect(find.textContaining('尚未配置健康档案'), findsOneWidget);
      expect(find.textContaining('信息不完整'), findsOneWidget);
      expect(find.textContaining('训练目标'), findsOneWidget);
      expect(find.textContaining('训练经验'), findsOneWidget);
      expect(find.textContaining('fitness_goal'), findsNothing);
      expect(find.textContaining('training_experience'), findsNothing);
      expect(find.widgetWithText(ElevatedButton, '完善健康档案'), findsOneWidget);
      // Must NOT look like an error.
      expect(find.textContaining('重试'), findsNothing);
      expect(find.textContaining('数据解析异常'), findsNothing);
    },
  );

  testWidgets('configured data shows fields and edit/delete actions', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/profile',
        (_) => _result(true, _profile, _readiness('ready')),
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('档案就绪'), findsOneWidget);
    expect(find.textContaining('基础力量'), findsOneWidget);
    expect(find.widgetWithText(ElevatedButton, '更正 / 编辑'), findsOneWidget);
    expect(find.widgetWithText(OutlinedButton, '删除健康档案'), findsOneWidget);
  });

  testWidgets('restricted readiness shown explicitly, never as ready', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/profile',
        (_) => _result(
          true,
          _profile,
          _readiness('restricted', restricted: 'underage'),
        ),
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('受限原因'), findsOneWidget);
    expect(find.textContaining('年龄范围不适用'), findsOneWidget);
    expect(find.textContaining('underage'), findsNothing);
    expect(find.textContaining('档案就绪'), findsNothing);
  });

  testWidgets('unknown readiness details never expose raw service values', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/profile',
        (_) => _result(
          true,
          _profile,
          _readiness(
            'restricted',
            missing: ['future_internal_field'],
            restricted: 'future_restricted_reason',
          ),
        ),
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('安全筛查结果需要进一步确认'), findsOneWidget);
    expect(find.textContaining('future_internal_field'), findsNothing);
    expect(find.textContaining('future_restricted_reason'), findsNothing);
    expect(find.textContaining('synthetic'), findsNothing);
  });

  testWidgets('edit flow opens form and saves with lists preserved', (
    tester,
  ) async {
    dynamic putBody;
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/profile',
        (_) => _result(true, _profile, _readiness('ready')),
      )
      ..register('PUT', '/health/profile', (options) {
        putBody = options.data;
        return Response(
          requestOptions: options,
          statusCode: 200,
          data: _result(true, _profile, _readiness('ready')),
        );
      });
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.byKey(const Key('health-edit-button')));
    await tester.tap(find.widgetWithText(ElevatedButton, '更正 / 编辑'));
    await tester.pumpAndSettle();

    // Save without changing anything; prefilled values + preserved lists.
    await tester.ensureVisible(find.byKey(const Key('health-save-button')));
    await tester.tap(find.byKey(const Key('health-save-button')));
    await tester.pumpAndSettle();

    expect(putBody, isNotNull);
    final body = putBody as Map<String, dynamic>;
    // Lists carried through verbatim (not wiped to null).
    expect(body['pain_injury_limitations'], isA<List>());
    expect((body['pain_injury_limitations'] as List).first['body_area'], '下背');
    expect((body['allergies'] as List).first['label'], '花生');
    expect((body['diet_exclusions'] as List).first['item'], '乳制品');
    expect(body['fitness_goal'], 'basic_strength');
  });

  testWidgets('delete cancel does not call DELETE', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/profile',
        (_) => _result(true, _profile, _readiness('ready')),
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.byKey(const Key('health-delete-button')));
    await tester.tap(find.widgetWithText(OutlinedButton, '删除健康档案'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('health-delete-cancel')));
    await tester.pumpAndSettle();

    expect(adapter.calls.where((c) => c.method == 'DELETE').toList(), isEmpty);
  });

  testWidgets('delete confirm issues DELETE and returns to not-configured', (
    tester,
  ) async {
    var getCall = 0;
    final adapter = FakeDioAdapter()
      ..register('GET', '/health/profile', (options) {
        getCall++;
        return Response(
          requestOptions: options,
          statusCode: 200,
          data: getCall == 1
              ? _result(true, _profile, _readiness('ready'))
              : _result(false, null, _readiness('missing_required_data')),
        );
      })
      ..registerJson('DELETE', '/health/profile', (_) => <String, dynamic>{});
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.byKey(const Key('health-delete-button')));
    await tester.tap(find.widgetWithText(OutlinedButton, '删除健康档案'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('health-delete-confirm')));
    await tester.pumpAndSettle();

    expect(adapter.calls.where((c) => c.method == 'DELETE').length, 1);
    // After delete the screen shows the not-configured state again.
    expect(find.textContaining('尚未配置健康档案'), findsOneWidget);
  });

  testWidgets('network error shows retry and not empty/ready', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerError('GET', '/health/profile', 503, {
        'detail': '健康档案加载失败',
        'code': 'service_unavailable',
      });
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('健康档案加载失败'), findsOneWidget);
    expect(find.byKey(const Key('health-retry')), findsOneWidget);
    expect(find.textContaining('尚未配置'), findsNothing);
    expect(find.textContaining('档案就绪'), findsNothing);
  });

  testWidgets('parse error shows 解析异常 and retry, never ready/empty', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/profile',
        (_) => <String, dynamic>{'oops': 1},
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('数据解析异常'), findsOneWidget);
    expect(find.byKey(const Key('health-retry')), findsOneWidget);
    expect(find.textContaining('尚未配置'), findsNothing);
    expect(find.textContaining('档案就绪'), findsNothing);
  });

  testWidgets('logout/clearing: provider reset drops stale health UI values', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/profile',
        (_) => _result(true, _profile, _readiness('ready')),
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();
    expect(find.textContaining('基础力量'), findsOneWidget);

    // Simulate logout/account-switch: auth_provider invalidates providers,
    // which resets healthProfileProvider to a fresh idle state.
    final container = ProviderScope.containerOf(
      tester.element(find.byType(HealthProfileScreen)),
    );
    container.invalidate(healthProfileProvider);
    // Pump fixed frames (not pumpAndSettle): idle renders an indeterminate
    // spinner that never settles, which is exactly the "no stale data"
    // state we want to assert.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    // No previous-user health data is retained as current.
    expect(find.textContaining('基础力量'), findsNothing);
    expect(find.textContaining('档案就绪'), findsNothing);
  });

  testWidgets('narrow screen + large text does not overflow', (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(320, 720);
    tester.platformDispatcher.textScaleFactorTestValue = 1.5;
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/profile',
        (_) => _result(
          true,
          _profile,
          _readiness('restricted', restricted: '安全筛查受限，需要在继续前完成评估'),
        ),
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });

  testWidgets(
    '320x720 textScaler 2.0 no overflow, edit/delete buttons still findable',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(320, 720);
      tester.platformDispatcher.textScaleFactorTestValue = 2.0;
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/health/profile',
          (_) => _result(true, _profile, _readiness('ready')),
        );
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.byKey(const Key('health-edit-button')), findsOneWidget);
      expect(find.byKey(const Key('health-delete-button')), findsOneWidget);
    },
  );

  testWidgets('error state uses liveRegion semantics and retry is findable', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerError('GET', '/health/profile', 503, {
        'detail': '健康档案加载失败',
        'code': 'service_unavailable',
      });
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('健康档案加载失败'), findsOneWidget);
    expect(find.byKey(const Key('health-retry')), findsOneWidget);
    expect(
      tester.getSemantics(find.byKey(const Key('health-error-live'))),
      isSemantics(label: '健康档案加载失败，请检查网络后重试。', isLiveRegion: true),
    );
    // Should not be presenting as a success/ready state.
    expect(find.textContaining('档案就绪'), findsNothing);
  });
}
