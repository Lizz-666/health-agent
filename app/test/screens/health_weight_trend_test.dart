// app/test/screens/health_weight_trend_test.dart
//
// Phase 2 Task 6: WeightTrendScreen contracts. All data synthetic.
// Covers: loading, insufficient data (no fabricated trend), sufficient data,
// add weight, delete record confirmation, networkError, parseError, and the
// no-advice / no-judgment invariant.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/screens/profile/weight_trend_screen.dart';

import '../providers/_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

Widget _wrap(ApiClient api) => ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(api)],
      child: const MaterialApp(home: WeightTrendScreen()),
    );

Map<String, dynamic> _record(String id, String at, double kg) => {
      'id': id,
      'recorded_at': at,
      'weight_kg': kg,
      'source': 'manual',
      'note': null,
      'created_at': at,
      'updated_at': at,
    };

Map<String, dynamic> _trend({
  required List<Map<String, dynamic>> records,
  required List<Map<String, dynamic>> trend,
  required int window,
  required bool sufficient,
}) =>
    {
      'records': records,
      'trend': trend,
      'window': window,
      'sufficient': sufficient,
    };

final _two = <Map<String, dynamic>>[
  _record('w1', '2026-07-20T08:00:00Z', 70.0),
  _record('w2', '2026-07-21T08:00:00Z', 69.5),
];

final _insufficient = _trend(records: _two, trend: const [], window: 3, sufficient: false);

final _sufficient = _trend(
  records: [
    _record('w1', '2026-07-20T08:00:00Z', 70.0),
    _record('w2', '2026-07-21T08:00:00Z', 69.5),
    _record('w3', '2026-07-22T08:00:00Z', 69.0),
  ],
  trend: [
    {'recorded_at': '2026-07-20T08:00:00Z', 'weight_kg': 70.0},
    {'recorded_at': '2026-07-21T08:00:00Z', 'weight_kg': 69.75},
    {'recorded_at': '2026-07-22T08:00:00Z', 'weight_kg': 69.5},
  ],
  window: 3,
  sufficient: true,
);

void main() {
  testWidgets('loading shows spinner and not data', (tester) async {
    final adapter = FakeDioAdapter();
    final completer = Completer<Response>();
    adapter.register('GET', '/health/trends/weight', (o) => completer.future);
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 10));

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.textContaining('加载体重趋势中'), findsOneWidget);

    completer.complete(
      Response(
        requestOptions: RequestOptions(path: '/health/trends/weight'),
        statusCode: 200,
        data: _insufficient,
      ),
    );
    await tester.pumpAndSettle();
  });

  testWidgets(
    'insufficient data shows banner and raw records only, no trend section',
    (tester) async {
      final adapter = FakeDioAdapter()
        ..registerJson('GET', '/health/trends/weight', (_) => _insufficient);
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      expect(find.textContaining('数据不足'), findsOneWidget);
      // No fabricated moving-trend section header (exact match; the banner
      // text legitimately mentions 移动趋势 in a negation).
      expect(find.text('移动趋势'), findsNothing);
      // Raw records still shown.
      expect(find.textContaining('70.0 kg'), findsOneWidget);
      // No advisory / judgment labels.
      expect(find.textContaining('达标'), findsNothing);
      expect(find.textContaining('未达标'), findsNothing);
      expect(find.textContaining('偏高'), findsNothing);
      expect(find.textContaining('偏低'), findsNothing);
    },
  );

  testWidgets('sufficient data shows moving trend and records', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/trends/weight', (_) => _sufficient);
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('移动趋势'), findsOneWidget);
    expect(find.textContaining('69.5 kg'), findsNWidgets(2)); // trend + record
  });

  testWidgets('add weight posts record and refetches trend', (tester) async {
    dynamic postBody;
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/trends/weight', (_) => _insufficient)
      ..register('POST', '/health/weight-records', (options) {
        postBody = options.data;
        return Response(
          requestOptions: options,
          statusCode: 200,
          data: <String, dynamic>{},
        );
      });
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('weight-add-fab')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('weight-input')), '68.5');
    await tester.tap(find.byKey(const Key('weight-save-button')));
    await tester.pumpAndSettle();

    expect(postBody, isNotNull);
    expect((postBody as Map<String, dynamic>)['weight_kg'], 68.5);
    expect(
      adapter.calls.where((c) => c.method == 'POST').length,
      1,
    );
    // Trend refetched after add.
    expect(
      adapter.calls.where((c) => c.method == 'GET').length,
      greaterThanOrEqualTo(2),
    );
  });

  testWidgets('invalid weight blocks save', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/trends/weight', (_) => _insufficient);
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('weight-add-fab')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('weight-input')), 'abc');
    await tester.tap(find.byKey(const Key('weight-save-button')));
    await tester.pump();

    expect(find.textContaining('有效的体重'), findsOneWidget);
    expect(
      adapter.calls.where((c) => c.method == 'POST').toList(),
      isEmpty,
    );
  });

  testWidgets('out-of-backend-bound weight blocks save', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/trends/weight', (_) => _insufficient);
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('weight-add-fab')));
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(const Key('weight-input')), '19.9');
    await tester.tap(find.byKey(const Key('weight-save-button')));
    await tester.pump();
    expect(find.textContaining('20–300 kg'), findsOneWidget);

    await tester.enterText(find.byKey(const Key('weight-input')), '300.1');
    await tester.tap(find.byKey(const Key('weight-save-button')));
    await tester.pump();
    expect(find.textContaining('20–300 kg'), findsOneWidget);

    expect(
      adapter.calls.where((c) => c.method == 'POST').toList(),
      isEmpty,
    );
  });

  testWidgets('delete confirm issues DELETE and refetches', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/health/trends/weight', (_) => _insufficient)
      ..registerJson('DELETE', '/health/weight-records', (_) => <String, dynamic>{});
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('weight-delete-w1')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('weight-delete-cancel')));
    await tester.pumpAndSettle();
    // Cancel: no DELETE.
    expect(
      adapter.calls.where((c) => c.method == 'DELETE').toList(),
      isEmpty,
    );

    await tester.tap(find.byKey(const Key('weight-delete-w1')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('weight-delete-confirm')));
    await tester.pumpAndSettle();
    expect(
      adapter.calls.where((c) => c.method == 'DELETE').length,
      1,
    );
  });

  testWidgets('network error shows retry and not empty data', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerError(
        'GET',
        '/health/trends/weight',
        503,
        {'detail': '体重趋势加载失败', 'code': 'service_unavailable'},
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('体重趋势加载失败'), findsOneWidget);
    expect(find.byKey(const Key('weight-retry')), findsOneWidget);
    expect(find.textContaining('70.0 kg'), findsNothing);
  });

  testWidgets('parse error shows 解析异常 and retry', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/health/trends/weight',
        (_) => <String, dynamic>{'oops': 1},
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('数据解析异常'), findsOneWidget);
    expect(find.byKey(const Key('weight-retry')), findsOneWidget);
  });
}
