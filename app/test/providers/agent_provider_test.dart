import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/models/agent.dart';
import 'package:posture_app/providers/agent_provider.dart';

import '_test_dio.dart';

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
  bool available = true,
  bool consent = true,
  String version = 'agent-disclosure-v1',
}) => {
  'runtime_enabled': true,
  'provider_configured': true,
  'provider_id': 'dashscope',
  'model_id': 'qwen-plus',
  'disclosure_version': version,
  'consent_active': consent,
  'available': available,
  'result_code': available ? 'agent_available' : 'agent_consent_required',
  'message': available ? 'Agent 已满足当前运行与隐私条件。' : '使用云端 Agent 前需要先阅读告知并明确同意。',
  'disclosure': _disclosure(version: version),
};

Map<String, dynamic> _answer({String code = 'agent_answer_ready'}) => {
  'run_id': '20000000-0000-4000-8000-000000000001',
  'status': code == 'agent_provider_unavailable' ? 'failed' : 'answer',
  'message': code == 'agent_provider_unavailable'
      ? 'Agent 服务暂时不可用，未执行任何操作。'
      : '已根据当前可访问的信息整理结果。',
  'result_code': code,
  'display_data': <Map<String, dynamic>>[],
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
    'action': 'create_weight_record',
    'diff': {
      'action': 'create_weight_record',
      'summary_code': 'weight_record_change',
      'recorded_at': '2026-07-30T08:00:00Z',
      'weight_kg': 70.5,
    },
    'expires_at': '2099-07-30T08:15:00Z',
  },
  'replayed': false,
};

void _registerCapabilities(
  FakeDioAdapter adapter,
  Map<String, dynamic> Function() value,
) {
  adapter.registerJson('GET', '/agent/capabilities', (_) => value());
}

void main() {
  test('consent binds to the disclosure that was actually displayed', () async {
    var granted = false;
    final adapter = FakeDioAdapter();
    _registerCapabilities(
      adapter,
      () => _capabilities(available: granted, consent: granted),
    );
    adapter.registerJson('POST', '/agent/consents:grant', (options) {
      final data = options.data as Map<String, dynamic>;
      expect(data.keys, {
        'accepted_provider_id',
        'accepted_disclosure_version',
        'idempotency_key',
      });
      expect(data['accepted_provider_id'], 'dashscope');
      expect(data['accepted_disclosure_version'], 'agent-disclosure-v1');
      expect(data['idempotency_key'], isA<String>());
      granted = true;
      return {
        'consent_id': '30000000-0000-4000-8000-000000000001',
        'sequence_no': 1,
        'status': 'granted',
        'replayed': false,
      };
    });
    final notifier = AgentNotifier(_apiWith(adapter), onDomainWrite: () {});
    addTearDown(notifier.dispose);

    await notifier.loadCapabilities();
    expect(notifier.state.available, isFalse);

    expect(await notifier.grantConsent(), isTrue);
    expect(notifier.state.available, isTrue);
    expect(notifier.state.messages, isEmpty);
  });

  test('proposal creates no domain write before independent confirm', () async {
    var domainWrites = 0;
    final adapter = FakeDioAdapter();
    _registerCapabilities(adapter, _capabilities);
    adapter.registerJson('POST', '/agent/turns', (_) => _proposalTurn());
    adapter.registerJson(
      'POST',
      '/agent/actions/10000000-0000-4000-8000-000000000001:confirm',
      (options) {
        final data = options.data as Map<String, dynamic>;
        expect(data.keys, {'idempotency_key'});
        return {
          'proposal_id': '10000000-0000-4000-8000-000000000001',
          'status': 'executed',
          'result_code': 'agent_action_executed',
          'result_ref': 'weight-record-1',
          'message': '操作已按确认内容执行。',
        };
      },
    );
    final notifier = AgentNotifier(
      _apiWith(adapter),
      onDomainWrite: () => domainWrites += 1,
    );
    addTearDown(notifier.dispose);
    await notifier.loadCapabilities();

    expect(await notifier.sendMessage('记录体重 70.5 kg'), isTrue);
    expect(domainWrites, 0);
    expect(notifier.state.pendingProposal, isNotNull);
    expect(notifier.state.messages.last.text, contains('尚未执行'));

    expect(await notifier.confirmProposal(), isTrue);
    expect(domainWrites, 1);
    expect(notifier.state.pendingProposal, isNull);
    expect(notifier.state.messages.last.action?.executed, isTrue);
  });

  test(
    'context request contains identifiers but no client health payload',
    () async {
      final adapter = FakeDioAdapter();
      _registerCapabilities(adapter, _capabilities);
      adapter.registerJson('POST', '/agent/turns', (options) {
        final data = options.data as Map<String, dynamic>;
        expect(data.keys, {
          'client_turn_id',
          'entry_type',
          'entity_id',
          'message',
          'iana_timezone',
        });
        expect(data['entry_type'], 'training_exercise');
        expect(data['entity_id'], 'exercise-owned-1');
        expect(data['iana_timezone'], 'Asia/Shanghai');
        expect(data.containsKey('user_id'), isFalse);
        expect(data.containsKey('health_profile'), isFalse);
        expect(data.containsKey('risk_tier'), isFalse);
        return _answer();
      });
      final notifier = AgentNotifier(_apiWith(adapter), onDomainWrite: () {});
      addTearDown(notifier.dispose);
      await notifier.loadCapabilities();
      notifier.setContext(
        const AgentRouteContext(
          entryType: AgentEntryType.trainingExercise,
          entityId: 'exercise-owned-1',
        ),
      );

      expect(await notifier.sendMessage('解释这个动作'), isTrue);
      expect(notifier.state.messages, hasLength(2));
    },
  );

  test('transport retry is explicit and uses a new client turn id', () async {
    var calls = 0;
    final turnIds = <String>[];
    final adapter = FakeDioAdapter();
    _registerCapabilities(adapter, _capabilities);
    adapter.register('POST', '/agent/turns', (options) {
      final data = options.data as Map<String, dynamic>;
      turnIds.add(data['client_turn_id'] as String);
      calls += 1;
      if (calls == 1) {
        throw DioException(
          requestOptions: options,
          type: DioExceptionType.connectionError,
        );
      }
      return Response(
        requestOptions: options,
        statusCode: 200,
        data: _answer(),
      );
    });
    final notifier = AgentNotifier(_apiWith(adapter), onDomainWrite: () {});
    addTearDown(notifier.dispose);
    await notifier.loadCapabilities();

    expect(await notifier.sendMessage('今天练什么'), isFalse);
    expect(notifier.state.canRetry, isTrue);
    expect(calls, 1);

    expect(await notifier.retryLastTurn(), isTrue);
    expect(calls, 2);
    expect(turnIds[0], isNot(turnIds[1]));
    expect(notifier.state.canRetry, isFalse);
    expect(
      notifier.state.messages.where(
        (item) => item.role == AgentConversationRole.user,
      ),
      hasLength(1),
    );
  });

  test('malformed response fails closed and creates no proposal', () async {
    final adapter = FakeDioAdapter();
    _registerCapabilities(adapter, _capabilities);
    adapter.registerJson(
      'POST',
      '/agent/turns',
      (_) => {..._answer(), 'status': 'success'},
    );
    final notifier = AgentNotifier(_apiWith(adapter), onDomainWrite: () {});
    addTearDown(notifier.dispose);
    await notifier.loadCapabilities();

    expect(await notifier.sendMessage('hello'), isFalse);
    expect(notifier.state.errorCode, 'agent_response_invalid');
    expect(notifier.state.pendingProposal, isNull);
    expect(notifier.state.messages.single.role, AgentConversationRole.user);
  });

  test('clearing a conversation ignores a late old-session response', () async {
    final pending = Completer<Response>();
    final adapter = FakeDioAdapter();
    _registerCapabilities(adapter, _capabilities);
    adapter.register('POST', '/agent/turns', (_) => pending.future);
    final notifier = AgentNotifier(_apiWith(adapter), onDomainWrite: () {});
    addTearDown(notifier.dispose);
    await notifier.loadCapabilities();

    final request = notifier.sendMessage('old account message');
    await Future<void>.delayed(Duration.zero);
    notifier.clearConversation();
    pending.complete(
      Response(
        requestOptions: RequestOptions(path: '/agent/turns'),
        statusCode: 200,
        data: _answer(),
      ),
    );
    await request;

    expect(notifier.state.messages, isEmpty);
    expect(notifier.state.pendingProposal, isNull);
  });

  test(
    'withdrawal clears memory before the server response completes',
    () async {
      final pending = Completer<Response>();
      final adapter = FakeDioAdapter();
      _registerCapabilities(adapter, _capabilities);
      adapter.registerJson('POST', '/agent/turns', (_) => _answer());
      adapter.register(
        'POST',
        '/agent/consents:withdraw',
        (_) => pending.future,
      );
      final notifier = AgentNotifier(_apiWith(adapter), onDomainWrite: () {});
      addTearDown(notifier.dispose);
      await notifier.loadCapabilities();
      await notifier.sendMessage('ephemeral');
      expect(notifier.state.messages, isNotEmpty);

      final withdrawal = notifier.withdrawConsent();
      await Future<void>.delayed(Duration.zero);
      expect(notifier.state.messages, isEmpty);
      expect(notifier.state.pendingProposal, isNull);

      pending.complete(
        Response(
          requestOptions: RequestOptions(path: '/agent/consents:withdraw'),
          statusCode: 200,
          data: {
            'consent_id': '30000000-0000-4000-8000-000000000001',
            'sequence_no': 2,
            'status': 'withdrawn',
            'replayed': false,
          },
        ),
      );
      await withdrawal;
    },
  );

  test(
    'withdrawal transport ambiguity blocks turns until status is refreshed',
    () async {
      final adapter = FakeDioAdapter();
      _registerCapabilities(adapter, _capabilities);
      adapter.register('POST', '/agent/consents:withdraw', (options) {
        throw DioException(
          requestOptions: options,
          type: DioExceptionType.connectionError,
        );
      });
      final notifier = AgentNotifier(_apiWith(adapter), onDomainWrite: () {});
      addTearDown(notifier.dispose);
      await notifier.loadCapabilities();

      expect(notifier.state.available, isTrue);
      expect(await notifier.withdrawConsent(), isFalse);
      expect(notifier.state.capabilitiesStatus, AgentLoadStatus.networkError);
      expect(notifier.state.available, isFalse);
      expect(await notifier.sendMessage('must remain local'), isFalse);
      expect(
        adapter.calls.where((call) => call.path == '/agent/turns'),
        isEmpty,
      );
    },
  );

  for (final terminal in [
    (
      status: 'expired',
      code: 'agent_action_expired',
      message: '该操作提案已过期，请重新发起。',
    ),
    (
      status: 'invalidated',
      code: 'agent_context_stale',
      message: '相关信息已变化，请重新发起操作。',
    ),
  ]) {
    test(
      '${terminal.status} proposal never becomes a completed write',
      () async {
        var domainWrites = 0;
        final adapter = FakeDioAdapter();
        _registerCapabilities(adapter, _capabilities);
        adapter.registerJson('POST', '/agent/turns', (_) => _proposalTurn());
        adapter.registerJson(
          'POST',
          '/agent/actions/10000000-0000-4000-8000-000000000001:confirm',
          (_) => {
            'proposal_id': '10000000-0000-4000-8000-000000000001',
            'status': terminal.status,
            'result_code': terminal.code,
            'result_ref': null,
            'message': terminal.message,
          },
        );
        final notifier = AgentNotifier(
          _apiWith(adapter),
          onDomainWrite: () => domainWrites += 1,
        );
        addTearDown(notifier.dispose);
        await notifier.loadCapabilities();
        await notifier.sendMessage('prepare a synthetic proposal');

        expect(await notifier.confirmProposal(), isFalse);
        expect(domainWrites, 0);
        expect(notifier.state.pendingProposal, isNull);
        expect(notifier.state.messages.last.action?.executed, isFalse);
        expect(notifier.state.messages.last.action?.status, terminal.status);
      },
    );
  }

  test('provider or disclosure reset destroys the in-memory session', () async {
    var version = 'agent-disclosure-v1';
    final adapter = FakeDioAdapter();
    _registerCapabilities(adapter, () => _capabilities(version: version));
    adapter.registerJson('POST', '/agent/turns', (_) => _answer());
    final notifier = AgentNotifier(_apiWith(adapter), onDomainWrite: () {});
    addTearDown(notifier.dispose);
    await notifier.loadCapabilities();
    await notifier.sendMessage('ephemeral before provider reset');
    expect(notifier.state.messages, isNotEmpty);

    version = 'agent-disclosure-v2';
    await notifier.loadCapabilities();

    expect(notifier.state.available, isTrue);
    expect(notifier.state.messages, isEmpty);
    expect(notifier.state.pendingProposal, isNull);
  });
}
