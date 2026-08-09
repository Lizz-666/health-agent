// app/test/screens/result_screen_test.dart
//
// Task 8C result screen contracts. The screen keeps the legacy result +
// suggestion display, and additionally fetches /posture/profile/{issue_id}
// to render certainty / sources / risk_tier from the server profile entry.
//
// Safety contracts under test (spec §9.2 / §10.5 / §15):
//  - Legacy result + suggestion + disclaimer still render.
//  - On entry-detail data: SeverityBadge (with nullable combined_severity),
//    CertaintyBadge, RiskTierBadge and per-source rows render.
//  - On entry-detail networkError: "档案状态暂不可用" + retry; MUST NOT show
//    "正常" or empty badges (no silent fallback to normal).
//  - On entry-detail parseError: same message + retry; no normal fallback.
//  - On entry-detail empty (404): "该问题暂无档案记录" (NOT normal).
//  - Retry re-fires the entry fetch.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/app.dart' show parseResultRouteExtra;
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/screens/result/result_screen.dart';

import '../providers/_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

Widget _wrap(ApiClient api, {required Widget child}) => ProviderScope(
  overrides: [apiClientProvider.overrideWithValue(api)],
  child: MaterialApp(home: child),
);

const _issueDetailBody = <String, dynamic>{
  'id': 'HN-01',
  'name_cn': '头部前倾',
  'name_en': 'Forward Head',
  'category': 'head_neck',
  'aliases': <String>[],
  'definition': '定义',
  'severity_levels': <String>['normal', 'mild', 'moderate', 'severe'],
  'causes': <Map<String, dynamic>>[],
  'self_tests': <Map<String, dynamic>>[],
  'corrections': <Map<String, dynamic>>[],
  'consequences': <Map<String, dynamic>>[],
  'red_flags': <String>[],
  'related_issues': <Map<String, dynamic>>[],
};

Widget _home(ResultScreen child) => _homeScreen(child);

// IssueDetailScreen wraps the result screen via route in production, but in
// the test we render ResultScreen directly under MaterialApp and override
// issueProvider with the HN-01 detail so it doesn't fire a separate network
// request.
Widget _homeScreen(ResultScreen child) => child;

final _conflictEntry = <String, dynamic>{
  'issue_id': 'HN-01',
  'issue_name': '头部前倾',
  'category': 'head_neck',
  'combined_severity': null,
  'certainty': 'conflict',
  'has_conflict': true,
  'sources': <Map<String, dynamic>>[
    {
      'source': 'self_test',
      'event_id': 'e1',
      'severity': 'moderate',
      'created_at': '2026-07-11T10:00:00Z',
    },
    {
      'source': 'ai_photo',
      'event_id': 'e2',
      'severity': 'severe',
      'created_at': '2026-07-11T10:01:00Z',
    },
  ],
  'risk_tier': 'normal',
  'risk_version': 'phase1-initial-v1',
  'updated_at': '2026-07-11T10:05:00Z',
};

void main() {
  test(
    'result route rejects missing or unknown result instead of defaulting normal',
    () {
      expect(parseResultRouteExtra(null), isNull);
      expect(
        parseResultRouteExtra({'assessmentId': 'a-1', 'suggestion': '建议'}),
        isNull,
      );
      expect(
        parseResultRouteExtra({
          'assessmentId': 'a-1',
          'result': 'unexpected',
          'suggestion': '建议',
        }),
        isNull,
      );
      expect(
        parseResultRouteExtra({
          'assessmentId': 'a-1',
          'result': 'mild',
          'suggestion': '建议',
        })?.result,
        'mild',
      );
    },
  );

  testWidgets('legacy result + suggestion + disclaimer still render', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    adapter.registerJson(
      'GET',
      '/posture/issues/HN-01',
      (_) => _issueDetailBody,
    );
    adapter.registerJson(
      'GET',
      '/posture/profile/HN-01',
      (_) => _conflictEntry,
    );
    await tester.pumpWidget(
      _wrap(
        _apiWith(adapter),
        child: _home(
          const ResultScreen(
            issueId: 'HN-01',
            assessmentId: 'a-1',
            result: 'moderate',
            suggestion: '建议纠正头部姿势',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Phase 8 automation anchor: the result surface is stably keyed.
    expect(find.byKey(const Key('result-screen')), findsOneWidget);
    expect(find.textContaining('建议纠正头部姿势'), findsOneWidget);
    expect(find.textContaining('不能替代专业医疗诊断'), findsOneWidget);
  });

  testWidgets('entry-detail data renders certainty / sources / risk badges', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    adapter.registerJson(
      'GET',
      '/posture/issues/HN-01',
      (_) => _issueDetailBody,
    );
    adapter.registerJson(
      'GET',
      '/posture/profile/HN-01',
      (_) => _conflictEntry,
    );
    await tester.pumpWidget(
      _wrap(
        _apiWith(adapter),
        child: _home(
          const ResultScreen(
            issueId: 'HN-01',
            assessmentId: 'a-1',
            result: 'moderate',
            suggestion: '建议',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('来源不一致'), findsOneWidget);
    expect(find.textContaining('无合并结论'), findsWidgets);
    // Both source severities rendered.
    expect(find.text('中度'), findsWidgets);
    expect(find.text('严重'), findsOneWidget);
  });

  testWidgets('legacy result surface renders mild as 轻度, not 未知', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    adapter.registerJson(
      'GET',
      '/posture/issues/HN-01',
      (_) => _issueDetailBody,
    );
    adapter.registerJson(
      'GET',
      '/posture/profile/HN-01',
      (_) => _conflictEntry,
    );
    await tester.pumpWidget(
      _wrap(
        _apiWith(adapter),
        child: _home(
          const ResultScreen(
            issueId: 'HN-01',
            assessmentId: 'a-1',
            result: 'mild',
            suggestion: '建议',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('轻度'), findsOneWidget);
    expect(find.text('未知'), findsNothing);
  });

  testWidgets('confirmed entry still renders its source and timestamp', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    adapter.registerJson(
      'GET',
      '/posture/issues/HN-01',
      (_) => _issueDetailBody,
    );
    adapter.registerJson(
      'GET',
      '/posture/profile/HN-01',
      (_) => <String, dynamic>{
        ..._conflictEntry,
        'combined_severity': 'moderate',
        'certainty': 'confirmed',
        'has_conflict': false,
        'sources': <Map<String, dynamic>>[
          (_conflictEntry['sources'] as List).first as Map<String, dynamic>,
        ],
      },
    );
    await tester.pumpWidget(
      _wrap(
        _apiWith(adapter),
        child: _home(
          const ResultScreen(
            issueId: 'HN-01',
            assessmentId: 'a-1',
            result: 'moderate',
            suggestion: '建议',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('评估来源：'), findsOneWidget);
    expect(find.textContaining('自测'), findsOneWidget);
    expect(find.textContaining('2026-07-11'), findsWidgets);
  });

  testWidgets('mismatched profile entry is never rendered for another issue', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    adapter.registerJson(
      'GET',
      '/posture/issues/HN-01',
      (_) => _issueDetailBody,
    );
    adapter.registerJson(
      'GET',
      '/posture/profile/HN-01',
      (_) => <String, dynamic>{..._conflictEntry, 'issue_id': 'HN-99'},
    );
    await tester.pumpWidget(
      _wrap(
        _apiWith(adapter),
        child: _home(
          const ResultScreen(
            issueId: 'HN-01',
            assessmentId: 'a-1',
            result: 'moderate',
            suggestion: '建议',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('当前详情与所选问题不一致'), findsOneWidget);
    expect(find.textContaining('来源不一致'), findsNothing);
    expect(find.text('重试'), findsOneWidget);
  });

  testWidgets(
    'entry-detail networkError shows 档案状态暂不可用 + retry and does NOT show 正常',
    (tester) async {
      final adapter = FakeDioAdapter();
      adapter.registerJson(
        'GET',
        '/posture/issues/HN-01',
        (_) => _issueDetailBody,
      );
      adapter.registerError('GET', '/posture/profile/HN-01', 503, {
        'detail': '档案不可用',
        'code': 'service_unavailable',
      });
      await tester.pumpWidget(
        _wrap(
          _apiWith(adapter),
          child: _home(
            const ResultScreen(
              issueId: 'HN-01',
              assessmentId: 'a-1',
              result: 'moderate',
              suggestion: '建议',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('档案状态暂不可用'), findsOneWidget);
      expect(find.textContaining('重试'), findsOneWidget);
      // Phase 8 automation anchor: the retry control is stably keyed.
      expect(find.byKey(const Key('result-entry-retry')), findsOneWidget);
      // MUST NOT fall back to a normal badge or "正常" text from the entry.
      expect(find.text('正常'), findsNothing);
    },
  );

  testWidgets(
    'entry-detail parseError shows 档案状态暂不可用 + retry and does NOT show 正常',
    (tester) async {
      final adapter = FakeDioAdapter();
      adapter.registerJson(
        'GET',
        '/posture/issues/HN-01',
        (_) => _issueDetailBody,
      );
      adapter.registerJson(
        'GET',
        '/posture/profile/HN-01',
        (_) => <String, dynamic>{'unexpected': 'payload'},
      );
      await tester.pumpWidget(
        _wrap(
          _apiWith(adapter),
          child: _home(
            const ResultScreen(
              issueId: 'HN-01',
              assessmentId: 'a-1',
              result: 'moderate',
              suggestion: '建议',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('档案状态暂不可用'), findsOneWidget);
      expect(find.textContaining('重试'), findsOneWidget);
      expect(find.text('正常'), findsNothing);
    },
  );

  testWidgets('entry-detail empty (404) shows 该问题暂无档案记录 and not 正常', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    adapter.registerJson(
      'GET',
      '/posture/issues/HN-01',
      (_) => _issueDetailBody,
    );
    adapter.registerError('GET', '/posture/profile/HN-01', 404, {
      'detail': '该问题暂无档案',
      'code': 'issue_not_found',
    });
    await tester.pumpWidget(
      _wrap(
        _apiWith(adapter),
        child: _home(
          const ResultScreen(
            issueId: 'HN-01',
            assessmentId: 'a-1',
            result: 'moderate',
            suggestion: '建议',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('该问题暂无档案记录'), findsOneWidget);
    expect(find.text('正常'), findsNothing);
  });

  testWidgets('retry re-fires the entry fetch', (tester) async {
    final adapter = FakeDioAdapter();
    adapter.registerJson(
      'GET',
      '/posture/issues/HN-01',
      (_) => _issueDetailBody,
    );
    // First call fails; second succeeds (the FakeDioAdapter only keeps the
    // most recent registration for a key, so re-register before tapping).
    adapter.registerError('GET', '/posture/profile/HN-01', 503, {
      'detail': '档案不可用',
    });
    await tester.pumpWidget(
      _wrap(
        _apiWith(adapter),
        child: _home(
          const ResultScreen(
            issueId: 'HN-01',
            assessmentId: 'a-1',
            result: 'moderate',
            suggestion: '建议',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final firstCount = adapter.calls
        .where((c) => c.path == '/posture/profile/HN-01')
        .length;
    expect(firstCount, 1);

    // Re-register to make the next call succeed, then tap retry.
    adapter.registerJson(
      'GET',
      '/posture/profile/HN-01',
      (_) => _conflictEntry,
    );
    await tester.tap(find.textContaining('重试'));
    await tester.pumpAndSettle();

    final secondCount = adapter.calls
        .where((c) => c.path == '/posture/profile/HN-01')
        .length;
    expect(secondCount, 2);
    // Conflict UI now visible after successful retry.
    expect(find.textContaining('来源不一致'), findsOneWidget);
  });
}
