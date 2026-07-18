// app/test/screens/posture_profile_test.dart
//
// Task 8C posture profile screen contracts. The screen is the only Task 8C
// screen with side effects, so the assertions lean heavily on the fake Dio
// adapter to drive provider state transitions.
//
// Safety contracts under test (spec §9.2 / §10.5-§10.8 / §11.2 / §12):
//  - loading / empty / networkError / parseError are visually distinct and
//    neither error nor parse failure falls back to "正常" / "暂无问题".
//  - conflict entries surface "来源不一致" + "无合并结论" with per-source
//    severity (no merging).
//  - restricted vs red_flag in safety_blocked use distinct text + icon.
//  - Goal selection limited to current normal_candidates, max 3, consecutive
//    rank 1..N; duplicate submit blocked while submitting.
//  - 409 stale_priority clears local selection and shows a reconfirm banner
//    without auto-replaying the confirm.
//  - Safety-signal success invalidates the previous selection.
//  - can_generate_plan button present and always disabled (no plan API call).
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/models/posture_profile.dart';
import 'package:posture_app/screens/profile/posture_profile_screen.dart';

import '../providers/_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

Widget _wrap(ApiClient api) => ProviderScope(
  overrides: [apiClientProvider.overrideWithValue(api)],
  child: const MaterialApp(home: PostureProfileScreen()),
);

final _emptyProfile = <String, dynamic>{
  'user_id': 'user-1',
  'evaluated_issues': <Map<String, dynamic>>[],
  'unevaluated_categories': <String>['head_neck', 'lower_limb', 'compound'],
  'summary': {
    'total_evaluated': 0,
    'total_conflict': 0,
    'total_provisional': 0,
  },
};

Map<String, dynamic> _entry({
  required String issueId,
  required String name,
  required Certainty certainty,
  PostureSeverity? combined,
  RiskTier riskTier = RiskTier.normal,
  List<Map<String, dynamic>> sources = const [],
}) {
  // sources must be non-empty per the model contract.
  final srcs = sources.isEmpty
      ? <Map<String, dynamic>>[
          {
            'source': 'self_test',
            'event_id': 'evt-$issueId',
            'severity': 'moderate',
            'created_at': '2026-07-11T10:00:00Z',
          },
        ]
      : sources;
  return {
    'issue_id': issueId,
    'issue_name': name,
    'category': 'head_neck',
    'combined_severity': combined?.name,
    'certainty': certainty.name,
    'has_conflict': certainty == Certainty.conflict,
    'sources': srcs,
    'risk_tier': riskTier == RiskTier.redFlag ? 'red_flag' : riskTier.name,
    'risk_version': 'phase1-initial-v1',
    'updated_at': '2026-07-11T10:05:00Z',
  };
}

Map<String, dynamic> _profile(List<Map<String, dynamic>> entries) {
  final conflict = entries.where((e) => e['certainty'] == 'conflict').length;
  final provisional = entries
      .where((e) => e['certainty'] == 'provisional')
      .length;
  return {
    'user_id': 'user-1',
    'evaluated_issues': entries,
    'unevaluated_categories': <String>['lower_limb'],
    'summary': {
      'total_evaluated': entries.length,
      'total_conflict': conflict,
      'total_provisional': provisional,
    },
  };
}

Map<String, dynamic> _priorities({
  List<Map<String, dynamic>> candidates = const [],
  List<Map<String, dynamic>> retest = const [],
  List<Map<String, dynamic>> blocked = const [],
}) {
  return {
    'suggestion_id': 'sugg-1',
    'profile_version': 'pv-1',
    'rule_version': '2026-07-17-v1',
    'risk_version': '2026-07-16-v4',
    'generated_at': '2026-07-17T12:00:00Z',
    'normal_candidates': candidates,
    'retest_required': retest,
    'safety_blocked': blocked,
    'disclaimer': '优先级属于建议，不作为病因认定。',
  };
}

void _registerProfileOk(FakeDioAdapter a, Map<String, dynamic> body) =>
    a.registerJson('GET', '/posture/profile', (_) => body);

void _registerPrioritiesOk(FakeDioAdapter a, Map<String, dynamic> body) =>
    a.registerJson('GET', '/posture/priorities', (_) => body);

void _registerProfileNet(FakeDioAdapter a) => a.registerError(
  'GET',
  '/posture/profile',
  503,
  {'detail': '档案加载失败', 'code': 'service_unavailable'},
);

void _registerProfileParse(FakeDioAdapter a) => a.registerJson(
  'GET',
  '/posture/profile',
  (_) => <String, dynamic>{'oops': 1},
);

void main() {
  testWidgets('loading state shows spinner and does not show data widgets', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    final completer = Completer<Response>();
    adapter.register('GET', '/posture/profile', (options) => completer.future);
    adapter.registerJson('GET', '/posture/priorities', (_) => _priorities());
    final api = _apiWith(adapter);

    await tester.pumpWidget(_wrap(api));
    await tester.pump(); // run microtask -> fetchProfile -> loading
    await tester.pump(const Duration(milliseconds: 10));

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.textContaining('加载档案中'), findsOneWidget);
    // MUST NOT show empty-card text while loading.
    expect(find.textContaining('评估记录为空'), findsNothing);
    expect(find.textContaining('暂无问题'), findsNothing);

    completer.complete(
      Response(
        requestOptions: RequestOptions(path: '/posture/profile'),
        statusCode: 200,
        data: _emptyProfile,
      ),
    );
    await tester.pumpAndSettle();
  });

  testWidgets('valid empty profile shows empty card and not an error', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    _registerProfileOk(adapter, _emptyProfile);
    _registerPrioritiesOk(adapter, _priorities());
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('评估记录为空'), findsOneWidget);
    expect(find.textContaining('头颈部'), findsOneWidget);
    expect(find.textContaining('下肢'), findsOneWidget);
    // Empty MUST NOT look like an error.
    expect(find.textContaining('档案加载失败'), findsNothing);
    expect(find.textContaining('数据解析异常'), findsNothing);
    // Network/parse error MUST NOT be displayed as "正常" or "暂无问题".
    expect(find.text('正常'), findsNothing);
    expect(find.textContaining('暂无问题'), findsNothing);
  });

  testWidgets('network error shows retry and does NOT look like empty/normal', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    _registerProfileNet(adapter);
    _registerPrioritiesOk(adapter, _priorities());
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('档案加载失败'), findsOneWidget);
    expect(find.textContaining('重试'), findsOneWidget);
    // MUST NOT show empty-card text on network error.
    expect(find.textContaining('评估记录为空'), findsNothing);
    expect(find.text('正常'), findsNothing);
    expect(find.textContaining('暂无问题'), findsNothing);
  });

  testWidgets('parse error shows 解析异常 and retry, never normal/empty', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    _registerProfileParse(adapter);
    _registerPrioritiesOk(adapter, _priorities());
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('数据解析异常'), findsOneWidget);
    expect(find.textContaining('重试'), findsOneWidget);
    expect(find.textContaining('评估记录为空'), findsNothing);
    expect(find.text('正常'), findsNothing);
  });

  testWidgets('confirmed moderate entry renders 中度 severity label', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    _registerProfileOk(
      adapter,
      _profile([
        _entry(
          issueId: 'HN-01',
          name: '头部前倾',
          certainty: Certainty.confirmed,
          combined: PostureSeverity.moderate,
        ),
      ]),
    );
    _registerPrioritiesOk(adapter, _priorities());
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.text('中度'), findsOneWidget);
    expect(find.textContaining('头部前倾'), findsOneWidget);
  });

  testWidgets(
    'mild entry renders 轻度 (legacy ResultBadge did not handle mild)',
    (tester) async {
      final adapter = FakeDioAdapter();
      _registerProfileOk(
        adapter,
        _profile([
          _entry(
            issueId: 'HN-01',
            name: '头部前倾',
            certainty: Certainty.confirmed,
            combined: PostureSeverity.mild,
          ),
        ]),
      );
      _registerPrioritiesOk(adapter, _priorities());
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      expect(find.text('轻度'), findsOneWidget);
    },
  );

  testWidgets('conflict entry shows 来源不一致 + 无合并结论 and both source severities', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    _registerProfileOk(
      adapter,
      _profile([
        _entry(
          issueId: 'ST-04',
          name: '圆肩',
          certainty: Certainty.conflict,
          combined: null,
          sources: [
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
        ),
      ]),
    );
    _registerPrioritiesOk(adapter, _priorities());
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('来源不一致'), findsOneWidget);
    expect(find.textContaining('无合并结论'), findsWidgets);
    // Both source severities rendered individually (not merged).
    expect(find.text('中度'), findsOneWidget);
    expect(find.text('严重'), findsOneWidget);
  });

  testWidgets('provisional entry shows 建议重新评估', (tester) async {
    final adapter = FakeDioAdapter();
    _registerProfileOk(
      adapter,
      _profile([
        _entry(
          issueId: 'HN-02',
          name: '颈前移',
          certainty: Certainty.provisional,
          combined: null,
        ),
      ]),
    );
    _registerPrioritiesOk(adapter, _priorities());
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('建议重新评估'), findsOneWidget);
  });

  testWidgets(
    'priorities safety_blocked renders restricted and red_flag distinctly',
    (tester) async {
      final adapter = FakeDioAdapter();
      _registerProfileOk(adapter, _emptyProfile);
      _registerPrioritiesOk(
        adapter,
        _priorities(
          blocked: [
            {
              'issue_id': 'SC-10',
              'issue_name': '综合受限示例',
              'risk_tier': 'restricted',
              'reason': '存在受限安全信号',
              'next_action': '仅提供健康教育，并建议按需寻求专业评估',
            },
            {
              'issue_id': 'SC-99',
              'issue_name': '综合红旗示例',
              'risk_tier': 'red_flag',
              'reason': '存在风险信号',
              'next_action': '停止规划并寻求就医升级',
            },
          ],
        ),
      );
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      expect(find.textContaining('专业评估'), findsWidgets);
      expect(find.textContaining('停止规划'), findsWidgets);
    },
  );

  testWidgets('three priority sections are rendered separately', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    _registerProfileOk(adapter, _emptyProfile);
    _registerPrioritiesOk(
      adapter,
      _priorities(
        candidates: [
          {
            'issue_id': 'HN-01',
            'issue_name': '头部前倾',
            'suggested_rank': 1,
            'reasons': ['严重度 moderate'],
          },
        ],
        retest: [
          {
            'issue_id': 'SS-02',
            'issue_name': '圆肩',
            'certainty': 'conflict',
            'reason': '来源不一致，需重新评估',
          },
        ],
        blocked: [
          {
            'issue_id': 'SC-10',
            'issue_name': '综合受限',
            'risk_tier': 'restricted',
            'reason': '存在受限安全信号',
            'next_action': '仅提供教育',
          },
        ],
      ),
    );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    // Section headers (defining text) for the three buckets.
    expect(find.textContaining('普通候选'), findsWidgets);
    expect(find.textContaining('需重新评估'), findsWidgets);
    expect(find.textContaining('安全阻断'), findsWidgets);
  });

  testWidgets(
    'selecting 2 candidates then confirm POSTs goals with rank 1 and 2',
    (tester) async {
      final adapter = FakeDioAdapter();
      _registerProfileOk(
        adapter,
        _profile([
          _entry(
            issueId: 'HN-01',
            name: '头部前倾',
            certainty: Certainty.confirmed,
            combined: PostureSeverity.moderate,
          ),
          _entry(
            issueId: 'SS-01',
            name: '圆肩',
            certainty: Certainty.confirmed,
            combined: PostureSeverity.mild,
          ),
        ]),
      );
      _registerPrioritiesOk(
        adapter,
        _priorities(
          candidates: [
            {
              'issue_id': 'HN-01',
              'issue_name': '头部前倾',
              'suggested_rank': 1,
              'reasons': ['严重度 moderate'],
            },
            {
              'issue_id': 'SS-01',
              'issue_name': '圆肩',
              'suggested_rank': 2,
              'reasons': ['严重度 mild'],
            },
          ],
        ),
      );
      // Confirm returns a successful ConfirmedGoals payload.
      adapter.registerJson('POST', '/posture/goals/confirm', (options) {
        return <String, dynamic>{
          'confirmed_goals': [
            {
              'issue_id': 'HN-01',
              'priority_rank': 1,
              'confirmed_at': '2026-07-18T10:00:00Z',
            },
            {
              'issue_id': 'SS-01',
              'priority_rank': 2,
              'confirmed_at': '2026-07-18T10:00:00Z',
            },
          ],
          'can_generate_plan': true,
          'risk_version': '2026-07-16-v4',
        };
      });
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      // Tap HN-01 then SS-01 candidate cards by their stable card key.
      await tester.ensureVisible(find.byKey(const Key('candidate-HN-01')));
      await tester.tap(find.byKey(const Key('candidate-HN-01')));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.byKey(const Key('candidate-SS-01')));
      await tester.tap(find.byKey(const Key('candidate-SS-01')));
      await tester.pumpAndSettle();

      // Confirm button now enabled.
      await tester.ensureVisible(
        find.widgetWithText(ElevatedButton, '确认 2 个目标'),
      );
      final confirmBtn = find.widgetWithText(ElevatedButton, '确认 2 个目标');
      expect(confirmBtn, findsOneWidget);
      await tester.tap(confirmBtn);
      await tester.pumpAndSettle();

      // Find the confirm POST in the recorded calls.
      final confirmCalls = adapter.calls
          .where((c) => c.path == '/posture/goals/confirm')
          .toList();
      expect(confirmCalls.length, 1);
      final goals = (confirmCalls.first.data as Map<String, dynamic>)['goals'];
      expect(goals, isA<List>());
      expect((goals as List).map((g) => g['priority_rank']).toList(), [1, 2]);
      expect(goals.map((g) => g['issue_id']).toList(), ['HN-01', 'SS-01']);
      expect(
        (confirmCalls.first.data as Map<String, dynamic>)['suggestion_id'],
        'sugg-1',
      );

      // Success card surfaces confirmedGoals.
      expect(find.textContaining('已确认'), findsWidgets);
    },
  );

  testWidgets('tapping a 4th candidate is rejected (UI limit of 3)', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    _registerProfileOk(adapter, _emptyProfile);
    final candidates = <Map<String, dynamic>>[
      for (var i = 1; i <= 4; i++)
        {
          'issue_id': 'I-0$i',
          'issue_name': '问题 0$i',
          'suggested_rank': i,
          'reasons': ['r'],
        },
    ];
    _registerPrioritiesOk(adapter, _priorities(candidates: candidates));
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    for (var i = 1; i <= 3; i++) {
      await tester.ensureVisible(find.byKey(Key('candidate-I-0$i')));
      await tester.tap(find.byKey(Key('candidate-I-0$i')));
      await tester.pump();
    }
    // 4th tap should be rejected — find the checkbox still unchecked and the
    // confirm button labelled "3".
    await tester.ensureVisible(find.byKey(const Key('candidate-I-04')));
    await tester.tap(find.byKey(const Key('candidate-I-04')));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.widgetWithText(ElevatedButton, '确认 3 个目标'));
    expect(find.widgetWithText(ElevatedButton, '确认 3 个目标'), findsOneWidget);
  });

  testWidgets('duplicate submit is blocked while submitting', (tester) async {
    final adapter = FakeDioAdapter();
    _registerProfileOk(adapter, _emptyProfile);
    _registerPrioritiesOk(
      adapter,
      _priorities(
        candidates: [
          {
            'issue_id': 'HN-01',
            'issue_name': '头部前倾',
            'suggested_rank': 1,
            'reasons': ['r'],
          },
        ],
      ),
    );
    final completer = Completer<Response>();
    adapter.register(
      'POST',
      '/posture/goals/confirm',
      (options) => completer.future,
    );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.byKey(const Key('candidate-HN-01')));
    await tester.tap(find.byKey(const Key('candidate-HN-01')));
    await tester.pumpAndSettle();
    final confirmBtn = find.byKey(const Key('confirm-goals-button'));
    await tester.ensureVisible(confirmBtn);
    await tester.tap(confirmBtn);
    // Pump a few frames so the confirm POST is dispatched and the provider
    // flips to confirmStatus=loading (which disables the button).
    for (var i = 0; i < 5; i++) {
      await tester.pump(const Duration(milliseconds: 10));
    }

    // While submitting: exactly one confirm POST recorded and the button is
    // now disabled (onPressed == null), so a second tap cannot enqueue another.
    final confirmCallsDuringSubmit = adapter.calls
        .where((c) => c.path == '/posture/goals/confirm')
        .length;
    expect(confirmCallsDuringSubmit, 1);
    final btn = tester.widget<ElevatedButton>(
      find.descendant(of: confirmBtn, matching: find.byType(ElevatedButton)),
    );
    expect(btn.onPressed, isNull);

    completer.complete(
      Response(
        requestOptions: RequestOptions(path: '/posture/goals/confirm'),
        statusCode: 200,
        data: <String, dynamic>{
          'confirmed_goals': <Map<String, dynamic>>[
            {
              'issue_id': 'HN-01',
              'priority_rank': 1,
              'confirmed_at': '2026-07-18T10:00:00Z',
            },
          ],
          'can_generate_plan': true,
          'risk_version': '2026-07-16-v4',
        },
      ),
    );
    await tester.pumpAndSettle();
    final confirmCallsAfter = adapter.calls
        .where((c) => c.path == '/posture/goals/confirm')
        .length;
    expect(confirmCallsAfter, 1);
  });

  testWidgets(
    'stale_priority clears selection, shows reconfirm banner, and does NOT auto-resubmit',
    (tester) async {
      final adapter = FakeDioAdapter();
      _registerProfileOk(adapter, _emptyProfile);
      // First /priorities returns suggestion_id sugg-1; subsequent refreshes
      // after stale also return sugg-2 (so we can detect a refetch happened).
      var prioritiesCallCount = 0;
      adapter.register('GET', '/posture/priorities', (options) {
        prioritiesCallCount++;
        return Response(
          requestOptions: options,
          statusCode: 200,
          data: <String, dynamic>{
            'suggestion_id': prioritiesCallCount == 1 ? 'sugg-1' : 'sugg-2',
            'profile_version': prioritiesCallCount == 1 ? 'pv-1' : 'pv-2',
            'rule_version': '2026-07-17-v1',
            'risk_version': '2026-07-16-v4',
            'generated_at': '2026-07-17T12:00:00Z',
            'normal_candidates': <Map<String, dynamic>>[
              {
                'issue_id': 'HN-01',
                'issue_name': '头部前倾',
                'suggested_rank': 1,
                'reasons': <String>['r'],
              },
            ],
            'retest_required': <Map<String, dynamic>>[],
            'safety_blocked': <Map<String, dynamic>>[],
            'disclaimer': 'd',
          },
        );
      });
      adapter.registerError('POST', '/posture/goals/confirm', 409, {
        'detail': '优先级已更新',
        'code': 'stale_priority',
      });
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.byKey(const Key('candidate-HN-01')));
      await tester.tap(find.byKey(const Key('candidate-HN-01')));
      await tester.pumpAndSettle();
      await tester.ensureVisible(
        find.widgetWithText(ElevatedButton, '确认 1 个目标'),
      );
      expect(find.widgetWithText(ElevatedButton, '确认 1 个目标'), findsOneWidget);

      await tester.tap(find.widgetWithText(ElevatedButton, '确认 1 个目标'));
      await tester.pumpAndSettle();

      // Selection cleared: confirm button text no longer "1 个目标".
      expect(find.widgetWithText(ElevatedButton, '确认 1 个目标'), findsNothing);
      // Reconfirm banner shown.
      expect(find.textContaining('请重新确认'), findsOneWidget);
      // Only one confirm POST happened (no auto-replay).
      final confirmCalls = adapter.calls
          .where((c) => c.path == '/posture/goals/confirm')
          .length;
      expect(confirmCalls, 1);
    },
  );

  testWidgets(
    'safety signal success clears selection and surfaces a recorded banner',
    (tester) async {
      final adapter = FakeDioAdapter();
      _registerProfileOk(adapter, _emptyProfile);
      _registerPrioritiesOk(
        adapter,
        _priorities(
          candidates: [
            {
              'issue_id': 'HN-01',
              'issue_name': '头部前倾',
              'suggested_rank': 1,
              'reasons': ['r'],
            },
          ],
        ),
      );
      adapter.registerJson('POST', '/posture/safety-signals', (options) {
        return <String, dynamic>{
          'signal_id': 'sig-1',
          'status': 'recorded',
          'lifecycle': 'active',
          'risk_tier': 'restricted',
          'risk_version': '2026-07-16-v4',
          'invalidates_until': '2026-08-18T00:00:00Z',
          'classification': {
            'risk_tier': 'restricted',
            'risk_version': '2026-07-16-v4',
            'rule_id': 'RST-acute-trauma',
            'reason': '急性创伤',
            'sources': <Map<String, dynamic>>[],
          },
        };
      });
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.byKey(const Key('candidate-HN-01')));
      await tester.tap(find.byKey(const Key('candidate-HN-01')));
      await tester.pumpAndSettle();
      await tester.ensureVisible(
        find.widgetWithText(ElevatedButton, '确认 1 个目标'),
      );
      expect(find.widgetWithText(ElevatedButton, '确认 1 个目标'), findsOneWidget);

      // Open the SignalType dropdown and pick 疼痛 (pain).
      await tester.ensureVisible(find.byKey(const Key('safety-signal-type')));
      await tester.tap(find.byKey(const Key('safety-signal-type')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('疼痛').last);
      await tester.pumpAndSettle();

      await tester.tap(find.widgetWithText(ElevatedButton, '提交安全信号'));
      await tester.pumpAndSettle();

      // Selection cleared after safety signal success.
      expect(find.widgetWithText(ElevatedButton, '确认 1 个目标'), findsNothing);
      // Recorded banner with the new risk tier.
      expect(find.textContaining('安全信号已记录'), findsOneWidget);
    },
  );

  testWidgets(
    '2xx safety response parse failure still clears stale goal selection',
    (tester) async {
      final adapter = FakeDioAdapter();
      _registerProfileOk(adapter, _emptyProfile);
      _registerPrioritiesOk(
        adapter,
        _priorities(
          candidates: [
            {
              'issue_id': 'HN-01',
              'issue_name': '头部前倾',
              'suggested_rank': 1,
              'reasons': ['r'],
            },
          ],
        ),
      );
      adapter.registerJson(
        'POST',
        '/posture/safety-signals',
        (_) => <String, dynamic>{},
      );
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.byKey(const Key('candidate-HN-01')));
      await tester.tap(find.byKey(const Key('candidate-HN-01')));
      await tester.pumpAndSettle();
      expect(find.widgetWithText(ElevatedButton, '确认 1 个目标'), findsOneWidget);

      await tester.ensureVisible(find.byKey(const Key('safety-signal-type')));
      await tester.tap(find.byKey(const Key('safety-signal-type')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('疼痛').last);
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(ElevatedButton, '提交安全信号'));
      await tester.pumpAndSettle();

      expect(find.widgetWithText(ElevatedButton, '确认 1 个目标'), findsNothing);
      expect(find.textContaining('数据解析异常'), findsWidgets);
    },
  );

  testWidgets('can_generate_plan button is present and always disabled', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    _registerProfileOk(adapter, _emptyProfile);
    _registerPrioritiesOk(
      adapter,
      _priorities(
        candidates: [
          {
            'issue_id': 'HN-01',
            'issue_name': '头部前倾',
            'suggested_rank': 1,
            'reasons': ['r'],
          },
        ],
      ),
    );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    final planBtn = find.textContaining('生成改善计划');
    expect(planBtn, findsOneWidget);
    // Disabled: tapping it never hits any plan endpoint.
    await tester.tap(planBtn, warnIfMissed: false);
    await tester.pumpAndSettle();
    expect(
      adapter.calls.where((c) => c.path.contains('plan')).toList(),
      isEmpty,
    );
  });

  testWidgets('profile controls and risk labels do not overflow at 320px', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(320, 720);
    tester.platformDispatcher.textScaleFactorTestValue = 1.5;
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

    final adapter = FakeDioAdapter();
    _registerProfileOk(adapter, _emptyProfile);
    _registerPrioritiesOk(
      adapter,
      _priorities(
        blocked: [
          {
            'issue_id': 'SC-10',
            'issue_name': '需要专业评估的综合受限示例',
            'risk_tier': 'restricted',
            'reason': '存在受限安全信号，需要在继续前完成评估',
            'next_action': '仅提供健康教育，并建议按需寻求专业评估',
          },
        ],
      ),
    );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });
}
