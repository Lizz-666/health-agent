// app/test/screens/today_checkin_test.dart
//
// Phase 2 Task 7: TodayScreen contracts. All data synthetic.
// Covers: loading, not-checked-in form, normal check-in path, abnormal pain
// follow-up required (blocked then complete), red_flag display (not normal),
// active_rest valid state, safety_adjustment valid state, already-checked-in
// display, networkError/parseError handling, route mounting, and plan absence.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:posture_app/app.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/screens/today/today_screen.dart';

import '../providers/_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

Widget _wrap(ApiClient api) => ProviderScope(
  overrides: [apiClientProvider.overrideWithValue(api)],
  child: const MaterialApp(home: TodayScreen()),
);

Map<String, dynamic> _checkin({
  String id = 'c1',
  String riskSummary = 'normal',
  String dailyStatus = 'checked_in',
  bool abnormalPain = false,
  Map<String, dynamic>? painFollowup,
}) => {
  'id': id,
  'local_date': '2026-07-24',
  'sleep_quality': 'good',
  'energy': 'normal',
  'muscle_soreness': 'mild',
  'available_time': '30_min',
  'daily_status': dailyStatus,
  'abnormal_pain': abnormalPain,
  'pain_followup': painFollowup,
  'risk_summary': riskSummary,
  'risk_version': '2026-07-22-v1',
  'created_at': '2026-07-24T08:00:00Z',
  'updated_at': '2026-07-24T08:00:00Z',
};

Map<String, dynamic> _todayResult(Map<String, dynamic>? checkin) => {
  'checked_in': checkin != null,
  'checkin': checkin,
};

final _followup = <String, dynamic>{
  'pain_area': '下背',
  'pain_started': 'today',
  'pain_intensity': 'mild',
  'has_neurological_symptom': false,
  'has_dizziness_or_chest_symptom': false,
  'has_acute_trauma': false,
  'pain_note': null,
};

void main() {
  testWidgets('loading shows spinner and not the form/summary', (tester) async {
    final adapter = FakeDioAdapter();
    final completer = Completer<Response>();
    adapter.register('GET', '/health/checkins/today', (o) => completer.future);
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 10));

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.textContaining('加载今日签到中'), findsOneWidget);
    expect(find.textContaining('今日尚未签到'), findsNothing);
    expect(find.textContaining('今日记录'), findsNothing);

    completer.complete(
      Response(
        requestOptions: RequestOptions(path: '/health/checkins/today'),
        statusCode: 200,
        data: _todayResult(null),
      ),
    );
    await tester.pumpAndSettle();
  });

  testWidgets('not checked in shows the quick check-in form', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/checkins/today', (_) => _todayResult(null))
      ..registerJson(
        'GET',
        '/training/today',
        (_) => {'state': 'no_active_plan'},
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('今日尚未签到'), findsOneWidget);
    expect(find.byKey(const Key('today-checkin-submit')), findsOneWidget);
    // Compact read-only training card replaces the old "unavailable" placeholder.
    expect(find.byKey(const Key('today-training-card')), findsOneWidget);
    expect(find.textContaining('暂无生效的训练计划'), findsOneWidget);
    // No adjustment button lives on Today (only an explicit Plan-screen button).
    expect(find.byKey(const Key('today-adjust-button')), findsNothing);
  });

  testWidgets('normal check-in path submits and shows summary', (tester) async {
    dynamic putBody;
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/checkins/today', (_) => _todayResult(null))
      ..register('PUT', '/health/checkins/today', (options) {
        putBody = options.data;
        return Response(
          requestOptions: options,
          statusCode: 200,
          data: _checkin(),
        );
      });
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.byKey(const Key('today-checkin-submit')));
    await tester.tap(find.byKey(const Key('today-checkin-submit')));
    await tester.pumpAndSettle();

    // PUT issued with the normal-path payload (abnormal_pain false, no followup).
    expect(putBody, isNotNull);
    expect((putBody as Map<String, dynamic>)['abnormal_pain'], false);
    expect(putBody['pain_followup'], isNull);
    // Summary shown with normal state.
    expect(find.text('状态正常'), findsOneWidget);
    expect(find.textContaining('今日记录'), findsOneWidget);
  });

  testWidgets(
    'abnormal pain without follow-up is blocked, then complete submits it',
    (tester) async {
      dynamic putBody;
      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/health/checkins/today',
          (_) => _todayResult(null),
        )
        ..register('PUT', '/health/checkins/today', (options) {
          putBody = options.data;
          return Response(
            requestOptions: options,
            statusCode: 200,
            data: _checkin(
              abnormalPain: true,
              painFollowup: _followup,
              riskSummary: 'caution',
            ),
          );
        });
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      // Turn abnormal pain ON.
      await tester.ensureVisible(find.byKey(const Key('today-abnormal-pain')));
      await tester.tap(find.byKey(const Key('today-abnormal-pain')));
      await tester.pumpAndSettle();
      // Submit without filling follow-up -> blocked.
      await tester.ensureVisible(find.byKey(const Key('today-checkin-submit')));
      await tester.tap(find.byKey(const Key('today-checkin-submit')));
      await tester.pumpAndSettle();
      expect(find.textContaining('请补充疼痛追问信息'), findsOneWidget);
      expect(adapter.calls.where((c) => c.method == 'PUT').toList(), isEmpty);

      // Fill the required follow-up fields.
      await tester.ensureVisible(find.byKey(const Key('today-pain-area')));
      await tester.enterText(find.byKey(const Key('today-pain-area')), '下背');
      await tester.ensureVisible(find.byKey(const Key('today-pain-started')));
      await tester.tap(find.byKey(const Key('today-pain-started')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('今天').last);
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.byKey(const Key('today-pain-intensity')));
      await tester.tap(find.byKey(const Key('today-pain-intensity')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('轻度').last);
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.byKey(const Key('today-checkin-submit')));
      await tester.tap(find.byKey(const Key('today-checkin-submit')));
      await tester.pumpAndSettle();

      expect(putBody, isNotNull);
      final body = putBody as Map<String, dynamic>;
      expect(body['abnormal_pain'], true);
      expect(body['pain_followup'], isA<Map>());
      expect((body['pain_followup'] as Map)['pain_area'], '下背');
    },
  );

  testWidgets('red_flag result shows escalation and never normal/success', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/checkins/today',
        (_) => _todayResult(_checkin(riskSummary: 'red_flag')),
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.text('红旗信号'), findsOneWidget);
    expect(find.textContaining('停止训练'), findsOneWidget);
    // Must NOT look like a normal/success state.
    expect(find.text('状态正常'), findsNothing);
  });

  testWidgets('caution risk summary is distinct from normal/restricted', (
    tester,
  ) async {
    final cautionAdapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/checkins/today',
        (_) => _todayResult(_checkin(riskSummary: 'caution')),
      );
    await tester.pumpWidget(_wrap(_apiWith(cautionAdapter)));
    await tester.pumpAndSettle();

    expect(find.text('需注意'), findsOneWidget);
    expect(find.text('受限'), findsNothing);
    expect(find.text('状态正常'), findsNothing);
  });

  testWidgets('restricted risk summary is distinct from normal/caution', (
    tester,
  ) async {
    final restrictedAdapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/checkins/today',
        (_) => _todayResult(_checkin(riskSummary: 'restricted')),
      );
    await tester.pumpWidget(_wrap(_apiWith(restrictedAdapter)));
    await tester.pumpAndSettle();

    expect(find.text('受限'), findsOneWidget);
    expect(find.text('需注意'), findsNothing);
    expect(find.text('状态正常'), findsNothing);
  });

  testWidgets('active_rest is shown as a valid, non-failure state', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/checkins/today',
        (_) => _todayResult(_checkin(dailyStatus: 'active_rest')),
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.text('今日：主动休息'), findsOneWidget);
    // Framed as a valid recovery state (the hint explicitly says it is not
    // counted as absence/failure).
    expect(find.textContaining('有效的恢复'), findsOneWidget);
  });

  testWidgets('safety_adjustment is shown as a valid, non-failure state', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/checkins/today',
        (_) => _todayResult(_checkin(dailyStatus: 'safety_adjustment')),
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.text('今日：安全调整'), findsOneWidget);
    // Framed as a valid choice (the hint explicitly says it is not
    // counted as absence/failure).
    expect(find.textContaining('有效选择'), findsOneWidget);
  });

  testWidgets('already checked-in (normal) shows summary, no form', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/checkins/today',
        (_) => _todayResult(_checkin(riskSummary: 'normal')),
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('状态正常'), findsOneWidget);
    expect(find.textContaining('今日已签到'), findsOneWidget);
    // No check-in form when already checked in.
    expect(find.byKey(const Key('today-checkin-submit')), findsNothing);
  });

  testWidgets('network error shows retry and not checked-in/summary', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerError('GET', '/health/checkins/today', 503, {
        'detail': '今日签到加载失败',
        'code': 'service_unavailable',
      });
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('今日签到加载失败'), findsOneWidget);
    expect(find.byKey(const Key('today-retry')), findsOneWidget);
    expect(find.textContaining('今日尚未签到'), findsNothing);
    expect(find.textContaining('状态正常'), findsNothing);
  });

  testWidgets('parse error shows 解析异常 and retry, never normal', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/checkins/today',
        (_) => <String, dynamic>{'oops': 1},
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('数据解析异常'), findsOneWidget);
    expect(find.byKey(const Key('today-retry')), findsOneWidget);
    expect(find.textContaining('状态正常'), findsNothing);
  });

  testWidgets(
    'route: TodayScreen mounts under /today and shows compact training card',
    (tester) async {
      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/health/checkins/today',
          (_) => _todayResult(null),
        )
        ..registerJson(
          'GET',
          '/training/today',
          (_) => {'state': 'no_active_plan'},
        );
      final router = GoRouter(
        initialLocation: '/today',
        routes: [
          GoRoute(path: '/today', builder: (_, _) => const TodayScreen()),
        ],
      );
      await tester.pumpWidget(
        ProviderScope(
          overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
          child: MaterialApp.router(routerConfig: router),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('今日尚未签到'), findsOneWidget);
      // Compact read-only training card is present.
      expect(find.byKey(const Key('today-training-card')), findsOneWidget);
      expect(find.textContaining('开始训练'), findsNothing);
      // No adjustment mutation surface on Today.
      expect(find.byKey(const Key('today-adjust-button')), findsNothing);
    },
  );

  testWidgets('bottom nav exposes Today, Plan, Agent and Profile', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/checkins/today',
        (_) => _todayResult(null),
      );
    final router = GoRouter(
      initialLocation: '/today',
      routes: [
        StatefulShellRoute.indexedStack(
          builder: (_, _, navigationShell) =>
              AppShell(navigationShell: navigationShell),
          branches: [
            StatefulShellBranch(
              routes: [
                GoRoute(path: '/today', builder: (_, _) => const TodayScreen()),
              ],
            ),
            StatefulShellBranch(
              routes: [
                GoRoute(
                  path: '/plan',
                  builder: (_, _) => const Scaffold(body: Text('PLAN_PAGE')),
                ),
              ],
            ),
            StatefulShellBranch(
              routes: [
                GoRoute(
                  path: '/agent',
                  builder: (_, _) => const Scaffold(body: Text('AGENT_PAGE')),
                ),
              ],
            ),
            StatefulShellBranch(
              routes: [
                GoRoute(
                  path: '/profile',
                  builder: (_, _) => const Scaffold(body: Text('PROFILE_PAGE')),
                ),
              ],
            ),
          ],
        ),
      ],
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('今日'), findsWidgets);
    expect(find.text('计划'), findsOneWidget);
    expect(find.text('Agent'), findsOneWidget);
    expect(find.text('我的'), findsOneWidget);
    expect(find.text('首页'), findsNothing);
    expect(find.textContaining('今日尚未签到'), findsOneWidget);

    await tester.tap(find.text('Agent'));
    await tester.pumpAndSettle();

    expect(find.text('AGENT_PAGE'), findsOneWidget);
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
        '/health/checkins/today',
        (_) => _todayResult(_checkin(riskSummary: 'red_flag')),
      )
      ..registerJson(
        'GET',
        '/training/today',
        (_) => {'state': 'no_active_plan'},
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });

  // -------------------------------------------------------------------------
  // Phase 7: compact read-only training-today card. The Today screen never
  // hosts the adjustment mutation (only the Plan screen does); it never POSTs
  // to /training/today/adjustments on load or on check-in save.
  // -------------------------------------------------------------------------

  Map<String, dynamic> trainingSessionJson() => {
    'session_id': 's-1',
    'week_index': 1,
    'day_of_week': 1,
    'session_order': 1,
    'target_minutes': null,
    'prescriptions': [
      {
        'prescription_id': 'p-1',
        'exercise_id': 'ex-1',
        'sets': 3,
        'reps': 10,
        'duration_seconds': null,
        'rest_seconds': 60,
        'relation_reason': null,
        'exercise': {
          'exercise_id': 'ex-1',
          'name_en': 'Squat',
          'name_zh': '深蹲',
          'training_roles': ['strength'],
          'difficulty': 'beginner',
          'illustration_asset_key': 'assets/training/illustrations/ex-1.svg',
          'illustration_alt_zh': '深蹲',
          'instruction_steps': ['stand'],
          'form_cues': ['straight'],
          'substitution_ids': [],
        },
      },
    ],
  };

  testWidgets('training card shows session + adjustment chip when adjusted', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/checkins/today', (_) => _todayResult(null))
      ..registerJson(
        'GET',
        '/training/today',
        (_) => {
          'state': 'session',
          'session': trainingSessionJson(),
          'adjustment_kind': 'shortened',
          'original_session_id': 's-1',
          'source_local_date': '2026-07-27',
          'adjustment_id': 'adj-1',
        },
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('today-training-card')), findsOneWidget);
    expect(find.textContaining('今日有训练安排'), findsOneWidget);
    // Adjustment kind surfaced as a non-failure chip.
    expect(find.textContaining('已调整：缩短'), findsOneWidget);
    expect(find.byKey(const Key('today-adjust-button')), findsNothing);
  });

  testWidgets('training card shows blocked as a safety state, never success', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/checkins/today', (_) => _todayResult(null))
      ..registerJson(
        'GET',
        '/training/today',
        (_) => {
          'state': 'blocked',
          'decision_gate': 'restricted',
          'safety_status': 'restricted',
        },
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('today-training-card')), findsOneWidget);
    expect(find.textContaining('暂停训练'), findsOneWidget);
    expect(find.textContaining('今日有训练安排'), findsNothing);
  });

  testWidgets(
    'training card shows active-rest deferral as a valid non-failure state',
    (tester) async {
      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/health/checkins/today',
          (_) => _todayResult(null),
        )
        ..registerJson(
          'GET',
          '/training/today',
          (_) => {
            'state': 'rest_day',
            'adjustment_kind': 'active_rest',
            'original_session_id': 's-1',
            'source_local_date': '2026-07-27',
            'adjustment_id': 'adj-1',
          },
        );
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('today-training-card')), findsOneWidget);
      expect(find.textContaining('今日主动休息'), findsOneWidget);
      expect(find.textContaining('缺勤'), findsNothing);
    },
  );

  testWidgets('Today never POSTs an adjustment on load or on check-in save', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/checkins/today', (_) => _todayResult(null))
      ..registerJson(
        'GET',
        '/training/today',
        (_) => {
          'state': 'session',
          'local_date': '2026-07-27',
          'session': trainingSessionJson(),
          'original_session_id': 's-1',
          'source_local_date': '2026-07-27',
        },
      )
      ..register('PUT', '/health/checkins/today', (options) {
        return Response(
          requestOptions: options,
          statusCode: 200,
          data: _checkin(),
        );
      });
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.byKey(const Key('today-checkin-submit')));
    await tester.tap(find.byKey(const Key('today-checkin-submit')));
    await tester.pumpAndSettle();

    expect(
      adapter.calls
          .where(
            (c) =>
                c.method == 'POST' && c.path == '/training/today/adjustments',
          )
          .toList(),
      isEmpty,
    );
    expect(
      adapter.calls
          .where((c) => c.method == 'GET' && c.path == '/training/today')
          .length,
      greaterThanOrEqualTo(2),
    );
  });
}
