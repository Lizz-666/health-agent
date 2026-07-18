// app/test/screens/history_screen_test.dart
//
// Task 8C history screen contracts. The screen must use the canonical
// `source` field from /posture/history (Task 8A) and distinguish:
//  - self_test  -> "自测"
//  - ai_photo   -> "AI 拍照分析"
//  - any other  -> "其他来源" (NEVER "AI"/"AI分析" — unknown sources must
//                  not impersonate AI, per spec §9.1 / §15)
//
// Loading failure and a valid empty history MUST be visually distinct. When
// a stale (cached) list exists alongside a refresh failure, the screen
// keeps the list AND shows an error banner (does not silently wipe data).
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/providers/assessment_provider.dart' show LoadStatus;
import 'package:posture_app/providers/assessment_provider.dart';
import 'package:posture_app/screens/history/history_screen.dart';

import '../providers/_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

Widget _wrap(ApiClient api) => ProviderScope(
  overrides: [apiClientProvider.overrideWithValue(api)],
  child: const MaterialApp(home: HistoryScreen()),
);

void _registerHistory(FakeDioAdapter a, List<Map<String, dynamic>> items) =>
    a.register(
      'GET',
      '/posture/history',
      (options) =>
          Response(requestOptions: options, statusCode: 200, data: items),
    );

void _registerHistoryErr(FakeDioAdapter a, int code) => a.registerError(
  'GET',
  '/posture/history',
  code,
  {'detail': '加载失败', 'code': 'load_failed'},
);

Map<String, dynamic> _record({
  required String id,
  required String source,
  required String result,
}) => {
  'id': id,
  'issue_id': 'HN-01',
  'issue_name': '头部前倾',
  'source': source,
  'method': source,
  'result': result,
  'created_at': '2026-07-18T10:00:00Z',
};

void main() {
  testWidgets('self_test source renders 自测 and not AI分析', (tester) async {
    final adapter = FakeDioAdapter();
    _registerHistory(adapter, [
      _record(id: 'r1', source: 'self_test', result: 'moderate'),
    ]);
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.text('自测'), findsOneWidget);
    expect(find.text('AI分析'), findsNothing);
    expect(find.text('AI 拍照分析'), findsNothing);
  });

  testWidgets('ai_photo source renders AI 拍照分析', (tester) async {
    final adapter = FakeDioAdapter();
    _registerHistory(adapter, [
      _record(id: 'r1', source: 'ai_photo', result: 'moderate'),
    ]);
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.text('AI 拍照分析'), findsOneWidget);
  });

  testWidgets('mild assessment renders 轻度 rather than 未知', (tester) async {
    final adapter = FakeDioAdapter();
    _registerHistory(adapter, [
      _record(id: 'r1', source: 'self_test', result: 'mild'),
    ]);
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.text('轻度'), findsOneWidget);
    expect(find.text('未知'), findsNothing);
  });

  testWidgets(
    'unknown source renders 其他来源 and does NOT impersonate AI (spec §15)',
    (tester) async {
      final adapter = FakeDioAdapter();
      _registerHistory(adapter, [
        _record(id: 'r1', source: 'manual_review', result: 'moderate'),
      ]);
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      expect(find.text('其他来源'), findsOneWidget);
      expect(find.text('AI'), findsNothing);
      expect(find.text('AI分析'), findsNothing);
      expect(find.text('AI 拍照分析'), findsNothing);
    },
  );

  testWidgets('valid empty history shows 暂无评估记录', (tester) async {
    final adapter = FakeDioAdapter();
    _registerHistory(adapter, const <Map<String, dynamic>>[]);
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('暂无评估记录'), findsOneWidget);
    expect(find.textContaining('加载失败'), findsNothing);
  });

  testWidgets(
    'failure with empty cached list shows error + retry and NOT 暂无评估记录',
    (tester) async {
      final adapter = FakeDioAdapter();
      _registerHistoryErr(adapter, 503);
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      expect(find.textContaining('加载失败'), findsOneWidget);
      expect(find.textContaining('重试'), findsOneWidget);
      expect(find.textContaining('暂无评估记录'), findsNothing);
    },
  );

  testWidgets(
    'failure with stale cached list keeps list AND shows error banner',
    (tester) async {
      final adapter = FakeDioAdapter();
      // First call returns one record; we then re-register the route to fail
      // and trigger a refresh via pull-to-refresh.
      _registerHistory(adapter, [
        _record(id: 'r1', source: 'self_test', result: 'moderate'),
      ]);
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();
      expect(find.text('头部前倾'), findsWidgets);

      // Re-register to fail, then pull to refresh.
      _registerHistoryErr(adapter, 503);
      await tester.fling(find.text('头部前倾').first, const Offset(0, 300), 1000);
      await tester.pumpAndSettle();

      // Both the stale record and the error banner are visible.
      expect(find.text('头部前倾'), findsWidgets);
      expect(find.textContaining('加载失败'), findsOneWidget);
    },
  );

  testWidgets('parse failure surfaces as parse error, not empty', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    // Return a payload that fails the strict AssessmentRecord parser.
    adapter.register(
      'GET',
      '/posture/history',
      (options) => Response(
        requestOptions: options,
        statusCode: 200,
        data: <Map<String, dynamic>>[
          {
            // missing required fields -> FormatException
            'id': 'r1',
          },
        ],
      ),
    );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('数据解析异常'), findsOneWidget);
    expect(find.text('重试'), findsOneWidget);
    expect(find.textContaining('暂无评估记录'), findsNothing);

    _registerHistory(adapter, [
      _record(id: 'r2', source: 'self_test', result: 'mild'),
    ]);
    await tester.tap(find.text('重试'));
    await tester.pumpAndSettle();
    expect(find.text('头部前倾'), findsOneWidget);
  });
}

// ignore_for_file: unused_import
// (LoadStatus import retained for clarity; the screen uses status via state.)
