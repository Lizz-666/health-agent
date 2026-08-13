// app/test/screens/self_test_screen_test.dart
//
// Task 8C self-test screen contracts. The screen must render the Task 3
// extended self-test fields (preparation / correctPosture / commonErrors /
// stopConditions / safetyNotes), with stopConditions rendered ABOVE the
// numbered action steps. The "AI 拍照更准确" wording has been removed; AI
// photo analysis is only described as "another reference method".
//
// Safety contract (spec §6.6 / §12.1): stop_conditions must be visible
// before action steps so the user can decide to abort before forcing a
// position.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/screens/test/self_test_screen.dart';

import '../providers/_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

Widget _wrap(ApiClient api) => ProviderScope(
  overrides: [apiClientProvider.overrideWithValue(api)],
  child: const MaterialApp(home: SelfTestScreen(issueId: 'HN-01')),
);

const _extendedIssueDetail = <String, dynamic>{
  'id': 'HN-01',
  'name_cn': '头部前倾',
  'name_en': 'Forward Head',
  'category': 'head_neck',
  'aliases': <String>[],
  'definition': 'd',
  'severity_levels': <String>['normal', 'mild', 'moderate', 'severe'],
  'causes': <Map<String, dynamic>>[],
  'self_tests': <Map<String, dynamic>>[
    {
      'name': '靠墙站立测试',
      'steps': <String>['脚跟贴墙站立', '后脑勺尝试贴墙'],
      'positive_sign': '后脑勺无法贴墙',
      'image_key': 'self_test_hn01_wall_stand',
      'tools_needed': '一面墙',
      'preparation': '穿平底鞋，自然站立。',
      'correct_posture': '目视前方，下颌微收。',
      'common_errors': <String>['强行仰头代偿', '弓背贴墙'],
      'stop_conditions': <String>['出现头晕', '出现颈部剧烈疼痛'],
      'safety_notes': <String>['动作缓慢，避免突然发力'],
      'content_version': '2026-07-11-v1',
      'source': {
        'identifier': 'DOI:10.1016/j.math.2007.01.013',
        'type': 'L4_RCT',
        'title': 'Yip CHT et al. Man Ther 2008',
        'version': '2008-original',
        'reviewed_at': '2026-07-11',
        'scope': '成人颈部体态筛查',
        'license': 'elsevier-subscription',
      },
    },
  ],
  'corrections': <Map<String, dynamic>>[],
  'consequences': <Map<String, dynamic>>[],
  'red_flags': <String>[],
  'related_issues': <Map<String, dynamic>>[],
};

const _legacyIssueDetail = <String, dynamic>{
  'id': 'HN-01',
  'name_cn': '头部前倾',
  'name_en': 'Forward Head',
  'category': 'head_neck',
  'aliases': <String>[],
  'definition': 'd',
  'severity_levels': <String>['normal', 'mild', 'moderate', 'severe'],
  'causes': <Map<String, dynamic>>[],
  'self_tests': <Map<String, dynamic>>[
    {
      'name': '靠墙站立测试',
      'steps': <String>['脚跟贴墙站立', '后脑勺尝试贴墙'],
      'positive_sign': '后脑勺无法贴墙',
      'image_key': 'self_test_hn01_wall_stand',
      'tools_needed': '一面墙',
    },
  ],
  'corrections': <Map<String, dynamic>>[],
  'consequences': <Map<String, dynamic>>[],
  'red_flags': <String>[],
  'related_issues': <Map<String, dynamic>>[],
};

void main() {
  testWidgets(
    'extended fields render: stop conditions / correct posture / common errors / preparation / safety notes',
    (tester) async {
      final adapter = FakeDioAdapter();
      adapter.registerJson(
        'GET',
        '/posture/issues/HN-01',
        (_) => _extendedIssueDetail,
      );
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      expect(find.textContaining('出现头晕'), findsOneWidget);
      expect(find.textContaining('出现颈部剧烈疼痛'), findsOneWidget);
      expect(find.textContaining('目视前方'), findsOneWidget);
      expect(find.textContaining('强行仰头代偿'), findsOneWidget);
      expect(find.textContaining('穿平底鞋'), findsOneWidget);
      expect(find.textContaining('动作缓慢'), findsOneWidget);
    },
  );

  testWidgets(
    'stop conditions render ABOVE the first numbered action step (spec §12.1)',
    (tester) async {
      final adapter = FakeDioAdapter();
      adapter.registerJson(
        'GET',
        '/posture/issues/HN-01',
        (_) => _extendedIssueDetail,
      );
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      final stopY = tester.getCenter(find.textContaining('出现头晕')).dy;
      final firstStepY = tester.getCenter(find.text('脚跟贴墙站立')).dy;
      expect(stopY, lessThan(firstStepY));
    },
  );

  testWidgets('legacy test without extended fields still renders name/steps', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    adapter.registerJson(
      'GET',
      '/posture/issues/HN-01',
      (_) => _legacyIssueDetail,
    );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('靠墙站立测试'), findsOneWidget);
    expect(find.text('脚跟贴墙站立'), findsOneWidget);
    expect(find.textContaining('停止条件'), findsNothing);
    expect(find.textContaining('正确姿势'), findsNothing);
  });

  testWidgets(
    'mismatched issue detail is not rendered as the current self-test',
    (tester) async {
      final adapter = FakeDioAdapter();
      adapter.registerJson(
        'GET',
        '/posture/issues/HN-01',
        (_) => <String, dynamic>{..._legacyIssueDetail, 'id': 'HN-99'},
      );
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      expect(find.textContaining('问题详情与当前自测不一致'), findsOneWidget);
      expect(find.textContaining('靠墙站立测试'), findsNothing);
      expect(find.text('重试'), findsOneWidget);
    },
  );

  testWidgets('answer buttons block duplicate assessment submission', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    adapter.registerJson(
      'GET',
      '/posture/issues/HN-01',
      (_) => _legacyIssueDetail,
    );
    final completer = Completer<Response>();
    adapter.register('POST', '/posture/assess', (options) => completer.future);
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    await tester.drag(find.byType(PageView), const Offset(-600, 0));
    await tester.pumpAndSettle();
    final submit = find.widgetWithText(ElevatedButton, '我有这个问题');
    expect(submit, findsOneWidget);
    await tester.tap(submit);
    await tester.pump();

    final button = tester.widget<ElevatedButton>(submit);
    expect(button.onPressed, isNull);
    await tester.tap(submit, warnIfMissed: false);
    for (var i = 0; i < 5; i++) {
      await tester.pump(const Duration(milliseconds: 10));
    }
    expect(adapter.calls.where((c) => c.path == '/posture/assess').length, 1);

    completer.complete(
      Response(
        requestOptions: RequestOptions(path: '/posture/assess'),
        statusCode: 200,
        // Deliberately invalid so the provider settles without navigating;
        // this test only exercises duplicate-submit suppression.
        data: <String, dynamic>{},
      ),
    );
    await tester.pumpAndSettle();
  });

  testWidgets('photo dialog wording does NOT contain 更准确 (spec §15)', (
    tester,
  ) async {
    expect(SelfTestScreen.photoDialogDescription, isNot(contains('更准确')));
    expect(SelfTestScreen.photoDialogDescription, contains('参考'));
  });

  testWidgets(
    'Phase 8 anchors: self-test pages and the three answer actions carry stable keys',
    (tester) async {
      final adapter = FakeDioAdapter();
      adapter.registerJson(
        'GET',
        '/posture/issues/HN-01',
        (_) => _legacyIssueDetail,
      );
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      // The paged self-test surface is anchored.
      expect(find.byKey(const Key('self-test-pages')), findsOneWidget);

      // Advance to the answer page and assert all three answer anchors.
      await tester.drag(
        find.byKey(const Key('self-test-pages')),
        const Offset(-600, 0),
      );
      await tester.pumpAndSettle();

      expect(
        find.byKey(const Key('self-test-answer-negative')),
        findsOneWidget,
      );
      expect(
        find.byKey(const Key('self-test-answer-positive')),
        findsOneWidget,
      );
      expect(
        find.byKey(const Key('self-test-answer-uncertain')),
        findsOneWidget,
      );
    },
  );
}
