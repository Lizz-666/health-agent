// app/test/screens/health_activity_grid_test.dart
//
// Phase 2 Task 6: ActivityGridScreen contracts. All data synthetic.
// Covers: loading, the four Phase 2 statuses rendered distinctly (none,
// checked_in, active_rest, safety_adjustment), active_rest/safety_adjustment
// shown as valid non-failure states, networkError, parseError.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/screens/profile/activity_grid_screen.dart';

import '../providers/_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

Widget _wrap(ApiClient api) => ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(api)],
      child: const MaterialApp(home: ActivityGridScreen()),
    );

Map<String, dynamic> _cell(String date, String status) =>
    {'date': date, 'status': status};

Map<String, dynamic> _grid(List<Map<String, dynamic>> cells) => {
      'start_date': '2026-07-20',
      'end_date': '2026-07-23',
      'cells': cells,
    };

final _fourStatuses = _grid([
  _cell('2026-07-20', 'none'),
  _cell('2026-07-21', 'checked_in'),
  _cell('2026-07-22', 'active_rest'),
  _cell('2026-07-23', 'safety_adjustment'),
]);

void main() {
  testWidgets('loading shows spinner and not data', (tester) async {
    final adapter = FakeDioAdapter();
    final completer = Completer<Response>();
    adapter.register('GET', '/health/activity-grid', (o) => completer.future);
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 10));

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.textContaining('加载活动记录中'), findsOneWidget);

    completer.complete(
      Response(
        requestOptions: RequestOptions(path: '/health/activity-grid'),
        statusCode: 200,
        data: _fourStatuses,
      ),
    );
    await tester.pumpAndSettle();
  });

  testWidgets('all four statuses rendered distinctly in legend', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/activity-grid', (_) => _fourStatuses);
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('已签到'), findsWidgets);
    expect(find.textContaining('主动休息'), findsWidgets);
    expect(find.textContaining('安全调整'), findsWidgets);
    expect(find.textContaining('无'), findsWidgets);
    // Four distinct cells.
    expect(find.byKey(const Key('grid-cell-2026-07-20T00:00:00.000')), findsOneWidget);
    expect(find.byKey(const Key('grid-cell-2026-07-21T00:00:00.000')), findsOneWidget);
    expect(find.byKey(const Key('grid-cell-2026-07-22T00:00:00.000')), findsOneWidget);
    expect(find.byKey(const Key('grid-cell-2026-07-23T00:00:00.000')), findsOneWidget);
  });

  testWidgets(
    'active_rest and safety_adjustment are not failure states',
    (tester) async {
      final adapter = FakeDioAdapter()
        ..registerJson('GET', '/health/activity-grid', (_) => _fourStatuses);
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      // No failure / missed wording anywhere.
      expect(find.textContaining('失败'), findsNothing);
      expect(find.textContaining('未完成'), findsNothing);
      expect(find.textContaining('缺席'), findsNothing);
    },
  );

  testWidgets('network error shows retry and not data', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerError(
        'GET',
        '/health/activity-grid',
        503,
        {'detail': '活动记录加载失败', 'code': 'service_unavailable'},
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('活动记录加载失败'), findsOneWidget);
    expect(find.byKey(const Key('grid-retry')), findsOneWidget);
    expect(find.textContaining('图例'), findsNothing);
  });

  testWidgets('parse error shows 解析异常 and retry', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/activity-grid',
        (_) => <String, dynamic>{'oops': 1},
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('数据解析异常'), findsOneWidget);
    expect(find.byKey(const Key('grid-retry')), findsOneWidget);
  });
}
