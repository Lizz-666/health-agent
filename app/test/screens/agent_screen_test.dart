import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/models/agent.dart';
import 'package:posture_app/screens/agent/agent_screen.dart';

import '../providers/_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

Map<String, dynamic> _disclosure({String version = 'agent-disclosure-v1'}) => {
  'disclosure_version': version,
  'provider_id': 'dashscope',
  'provider_name_zh': '通义千问（DashScope）',
  'purpose_code': 'wellness_agent_assistance',
  'processing_boundary_code': 'cloud_model_processing',
  'data_scope_codes': ['structured_health_context', 'ephemeral_user_message'],
  'application_retention_code': 'no_chat_transcript_persistence',
  'withdrawal_available': true,
  'agent_data_deletion_available': true,
};

Map<String, dynamic> _capabilities({
  required bool available,
  String version = 'agent-disclosure-v1',
}) => {
  'runtime_enabled': true,
  'provider_configured': true,
  'provider_id': 'dashscope',
  'model_id': 'qwen-plus',
  'disclosure_version': version,
  'consent_active': available,
  'available': available,
  'result_code': available ? 'agent_available' : 'agent_consent_required',
  'message': available ? 'Agent 已满足当前运行与隐私条件。' : '使用云端 Agent 前需要先阅读告知并明确同意。',
  'disclosure': _disclosure(version: version),
};

Map<String, dynamic> _answer() => {
  'run_id': '20000000-0000-4000-8000-000000000001',
  'status': 'answer',
  'message': '已根据当前可访问的信息整理结果。',
  'result_code': 'agent_answer_ready',
  'display_data': [
    {
      'tool_name': 'get_today_training',
      'data': {
        'state': 'session',
        'exercise_ids': ['exercise-1'],
      },
    },
  ],
  'proposal': null,
  'replayed': false,
};

Map<String, dynamic> _proposalTurn() => {
  'run_id': '20000000-0000-4000-8000-000000000002',
  'status': 'proposal_pending',
  'message': '操作尚未执行，请核对变更内容并明确确认或取消。',
  'result_code': 'agent_action_confirmation_required',
  'display_data': <Map<String, dynamic>>[],
  'proposal': {
    'proposal_id': '10000000-0000-4000-8000-000000000001',
    'action': 'generate_training_plan_draft',
    'diff': {
      'action': 'generate_training_plan_draft',
      'summary_code': 'plan_draft_change',
      'fitness_goal': 'basic_strength',
      'weekly_frequency': 3,
      'session_duration_minutes': 30,
      'requires_plan_review': true,
    },
    'expires_at': '2099-07-30T08:15:00Z',
  },
  'replayed': false,
};

Widget _wrap(
  FakeDioAdapter adapter, {
  AgentRouteContext? routeContext = const AgentRouteContext(),
}) {
  return ProviderScope(
    overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
    child: MaterialApp(home: AgentScreen(routeContext: routeContext)),
  );
}

void main() {
  testWidgets('invalid contextual route fails closed without an API call', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    await tester.pumpWidget(_wrap(adapter, routeContext: null));
    await tester.pumpAndSettle();

    expect(find.text('Agent 入口无效'), findsOneWidget);
    expect(find.textContaining('未请求或发送任何健康数据'), findsOneWidget);
    expect(adapter.calls, isEmpty);
  });

  testWidgets('consent screen binds explicit acknowledgement to disclosure', (
    tester,
  ) async {
    var available = false;
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/agent/capabilities',
        (_) => _capabilities(available: available),
      )
      ..registerJson('POST', '/agent/consents:grant', (options) {
        final body = options.data as Map<String, dynamic>;
        expect(body['accepted_provider_id'], 'dashscope');
        expect(body['accepted_disclosure_version'], 'agent-disclosure-v1');
        available = true;
        return {
          'consent_id': '30000000-0000-4000-8000-000000000001',
          'sequence_no': 1,
          'status': 'granted',
          'replayed': false,
        };
      });
    await tester.pumpWidget(_wrap(adapter));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('agent-consent-view')), findsOneWidget);
    expect(find.text('通义千问（DashScope）'), findsOneWidget);
    expect(find.textContaining('聊天文本仅保存在当前应用内存中'), findsOneWidget);
    final grant = tester.widget<FilledButton>(
      find.byKey(const Key('agent-consent-grant')),
    );
    expect(grant.onPressed, isNull);

    await tester.tap(find.byKey(const Key('agent-consent-checkbox')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('agent-consent-grant')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('agent-message-input')), findsOneWidget);
    expect(find.textContaining('AI 辅助解释'), findsOneWidget);
  });

  testWidgets('a changed disclosure requires a new acknowledgement', (
    tester,
  ) async {
    var version = 'agent-disclosure-v1';
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/agent/capabilities',
        (_) => _capabilities(available: false, version: version),
      )
      ..register('POST', '/agent/consents:grant', (options) {
        final body = options.data as Map<String, dynamic>;
        expect(body['accepted_disclosure_version'], 'agent-disclosure-v1');
        version = 'agent-disclosure-v2';
        throw DioException(
          requestOptions: options,
          response: Response(
            requestOptions: options,
            statusCode: 409,
            data: {
              'detail': 'stale disclosure',
              'code': 'agent_disclosure_stale',
            },
          ),
          type: DioExceptionType.badResponse,
        );
      });
    await tester.pumpWidget(_wrap(adapter));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('agent-consent-checkbox')));
    await tester.pump();
    expect(
      tester
          .widget<CheckboxListTile>(
            find.byKey(const Key('agent-consent-checkbox')),
          )
          .value,
      isTrue,
    );
    await tester.tap(find.byKey(const Key('agent-consent-grant')));
    await tester.pumpAndSettle();

    expect(
      tester
          .widget<CheckboxListTile>(
            find.byKey(const Key('agent-consent-checkbox')),
          )
          .value,
      isFalse,
    );
    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('agent-consent-grant')))
          .onPressed,
      isNull,
    );
    expect(
      adapter.calls.where((call) => call.path == '/agent/capabilities'),
      hasLength(2),
    );
  });

  testWidgets('Agent-data deletion remains reachable on capability failure', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    await tester.pumpWidget(_wrap(adapter));
    await tester.pumpAndSettle();

    expect(find.text('Agent 服务不可用'), findsOneWidget);
    await tester.tap(find.byKey(const Key('agent-privacy-menu')));
    await tester.pumpAndSettle();
    expect(find.text('删除 Agent 数据'), findsOneWidget);
  });

  testWidgets('available Agent renders structured read result', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/agent/capabilities',
        (_) => _capabilities(available: true),
      )
      ..registerJson('POST', '/agent/turns', (options) {
        final body = options.data as Map<String, dynamic>;
        expect(body['message'], '今天练什么');
        return _answer();
      });
    await tester.pumpWidget(_wrap(adapter));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const Key('agent-message-input')),
      '今天练什么',
    );
    await tester.tap(find.byKey(const Key('agent-send')));
    await tester.pumpAndSettle();

    expect(find.text('今天练什么'), findsOneWidget);
    expect(find.text('已根据当前可访问的信息整理结果。'), findsOneWidget);
    expect(find.text('今日训练'), findsOneWidget);
    expect(find.textContaining('动作标识'), findsOneWidget);
    expect(find.text('agent_answer_ready'), findsNothing);
    expect(find.textContaining('exercise_ids'), findsNothing);
  });

  testWidgets(
    'proposal is not shown as complete before separate confirmation',
    (tester) async {
      var confirmCalls = 0;
      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/agent/capabilities',
          (_) => _capabilities(available: true),
        )
        ..registerJson('POST', '/agent/turns', (_) => _proposalTurn())
        ..registerJson(
          'POST',
          '/agent/actions/10000000-0000-4000-8000-000000000001:confirm',
          (_) {
            confirmCalls += 1;
            return {
              'proposal_id': '10000000-0000-4000-8000-000000000001',
              'status': 'executed',
              'result_code': 'agent_action_executed',
              'result_ref': 'plan-draft-1',
              'message': '操作已按确认内容执行。',
            };
          },
        );
      await tester.pumpWidget(_wrap(adapter));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byKey(const Key('agent-message-input')),
        '准备计划草案',
      );
      await tester.tap(find.byKey(const Key('agent-send')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('agent-proposal-card')), findsOneWidget);
      expect(find.textContaining('尚未执行'), findsWidgets);
      expect(find.text('操作已按确认内容执行。'), findsNothing);
      expect(confirmCalls, 0);
      expect(
        tester
            .widget<TextField>(find.byKey(const Key('agent-message-input')))
            .enabled,
        isFalse,
      );

      await tester.tap(find.byKey(const Key('agent-proposal-confirm')));
      await tester.pumpAndSettle();

      expect(confirmCalls, 1);
      expect(find.byKey(const Key('agent-proposal-card')), findsNothing);
      expect(find.text('操作已按确认内容执行。'), findsOneWidget);
    },
  );

  testWidgets('proposal cancellation is independent and never executes', (
    tester,
  ) async {
    var cancelCalls = 0;
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/agent/capabilities',
        (_) => _capabilities(available: true),
      )
      ..registerJson('POST', '/agent/turns', (_) => _proposalTurn())
      ..registerJson(
        'POST',
        '/agent/actions/10000000-0000-4000-8000-000000000001:cancel',
        (_) {
          cancelCalls += 1;
          return {
            'proposal_id': '10000000-0000-4000-8000-000000000001',
            'status': 'cancelled',
            'result_code': 'agent_action_cancelled',
            'result_ref': null,
            'message': '该操作已取消，未写入数据。',
          };
        },
      );
    await tester.pumpWidget(_wrap(adapter));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('agent-message-input')),
      '准备计划草案',
    );
    await tester.tap(find.byKey(const Key('agent-send')));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('agent-proposal-cancel')));
    await tester.pumpAndSettle();

    expect(cancelCalls, 1);
    expect(find.byKey(const Key('agent-proposal-card')), findsNothing);
    expect(find.text('该操作已取消，未写入数据。'), findsOneWidget);
    expect(find.text('操作已按确认内容执行。'), findsNothing);
  });

  testWidgets('context card contains only entry and owned identifier', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/agent/capabilities',
        (_) => _capabilities(available: true),
      );
    await tester.pumpWidget(
      _wrap(
        adapter,
        routeContext: const AgentRouteContext(
          entryType: AgentEntryType.trainingExercise,
          entityId: 'exercise-owned-1',
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('agent-context-card')), findsOneWidget);
    expect(find.text('当前处方动作'), findsOneWidget);
    expect(find.text('标识：exercise-owned-1'), findsOneWidget);
  });

  testWidgets('provider unavailable remains a failure with explicit retry', (
    tester,
  ) async {
    var calls = 0;
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/agent/capabilities',
        (_) => _capabilities(available: true),
      )
      ..register('POST', '/agent/turns', (options) {
        calls += 1;
        throw DioException(
          requestOptions: options,
          type: DioExceptionType.connectionError,
        );
      });
    await tester.pumpWidget(_wrap(adapter));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('agent-message-input')),
      '今天练什么',
    );
    await tester.tap(find.byKey(const Key('agent-send')));
    await tester.pumpAndSettle();

    expect(find.textContaining('未执行任何操作'), findsOneWidget);
    expect(find.byKey(const Key('agent-retry-turn')), findsOneWidget);
    expect(calls, 1);

    await tester.tap(find.byKey(const Key('agent-retry-turn')));
    await tester.pumpAndSettle();
    expect(calls, 2);
  });
}
