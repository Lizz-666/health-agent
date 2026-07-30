import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../core/idempotency_key.dart';
import '../models/agent.dart';
import 'daily_checkin_provider.dart';
import 'plan_provider.dart';
import 'weight_trend_provider.dart';

const agentDefaultTimezone = 'Asia/Shanghai';

enum AgentLoadStatus {
  idle,
  loading,
  ready,
  unavailable,
  networkError,
  parseError,
}

enum AgentConversationRole { user, agent, action }

class AgentConversationItem {
  const AgentConversationItem._({
    required this.role,
    required this.text,
    this.turn,
    this.action,
  });

  final AgentConversationRole role;
  final String text;
  final AgentTurnResponse? turn;
  final AgentActionResponse? action;

  factory AgentConversationItem.user(String text) =>
      AgentConversationItem._(role: AgentConversationRole.user, text: text);

  factory AgentConversationItem.agent(AgentTurnResponse turn) =>
      AgentConversationItem._(
        role: AgentConversationRole.agent,
        text: turn.message ?? _fallbackMessage(turn.resultCode),
        turn: turn,
      );

  factory AgentConversationItem.action(AgentActionResponse action) =>
      AgentConversationItem._(
        role: AgentConversationRole.action,
        text: action.message,
        action: action,
      );
}

class _TurnDraft {
  const _TurnDraft({
    required this.clientTurnId,
    required this.context,
    required this.message,
  });

  final String clientTurnId;
  final AgentRouteContext context;
  final String message;

  _TurnDraft retried() => _TurnDraft(
    clientTurnId: newIdempotencyKey(),
    context: context,
    message: message,
  );

  Map<String, dynamic> toJson() => {
    'client_turn_id': clientTurnId,
    'entry_type': context.entryType.wire,
    'entity_id': context.entityId,
    'message': message,
    'iana_timezone': agentDefaultTimezone,
  };
}

class AgentState {
  const AgentState({
    this.capabilitiesStatus = AgentLoadStatus.idle,
    this.capabilities,
    this.context = const AgentRouteContext(),
    this.messages = const [],
    this.pendingProposal,
    this.busy = false,
    this.errorCode,
    this.errorMessage,
    this.canRetry = false,
  });

  final AgentLoadStatus capabilitiesStatus;
  final AgentCapabilities? capabilities;
  final AgentRouteContext context;
  final List<AgentConversationItem> messages;
  final AgentProposal? pendingProposal;
  final bool busy;
  final String? errorCode;
  final String? errorMessage;
  final bool canRetry;

  bool get available =>
      capabilitiesStatus == AgentLoadStatus.ready &&
      capabilities?.available == true;

  AgentState copyWith({
    AgentLoadStatus? capabilitiesStatus,
    Object? capabilities = _unset,
    AgentRouteContext? context,
    List<AgentConversationItem>? messages,
    Object? pendingProposal = _unset,
    bool? busy,
    Object? errorCode = _unset,
    Object? errorMessage = _unset,
    bool? canRetry,
  }) => AgentState(
    capabilitiesStatus: capabilitiesStatus ?? this.capabilitiesStatus,
    capabilities: capabilities == _unset
        ? this.capabilities
        : capabilities as AgentCapabilities?,
    context: context ?? this.context,
    messages: messages ?? this.messages,
    pendingProposal: pendingProposal == _unset
        ? this.pendingProposal
        : pendingProposal as AgentProposal?,
    busy: busy ?? this.busy,
    errorCode: errorCode == _unset ? this.errorCode : errorCode as String?,
    errorMessage: errorMessage == _unset
        ? this.errorMessage
        : errorMessage as String?,
    canRetry: canRetry ?? this.canRetry,
  );
}

class AgentNotifier extends StateNotifier<AgentState> {
  AgentNotifier(this._api, {required this._onDomainWrite})
    : super(const AgentState());

  final ApiClient _api;
  final void Function() _onDomainWrite;
  int _generation = 0;
  int _capabilitiesRequest = 0;
  _TurnDraft? _lastRetryableTurn;

  Future<void> loadCapabilities() async {
    final request = ++_capabilitiesRequest;
    state = state.copyWith(
      capabilitiesStatus: AgentLoadStatus.loading,
      errorCode: null,
      errorMessage: null,
    );
    try {
      final response = await _api.dio.get('/agent/capabilities');
      final capabilities = AgentCapabilities.fromJson(
        _responseMap(response.data),
      );
      if (request != _capabilitiesRequest) return;

      final previous = state.capabilities;
      final boundaryChanged =
          previous != null &&
          (previous.boundaryId != capabilities.boundaryId ||
              previous.consentActive != capabilities.consentActive);
      final mustClear =
          boundaryChanged ||
          (!capabilities.available &&
              capabilities.resultCode != 'agent_consent_required');
      if (mustClear) _lastRetryableTurn = null;
      state = state.copyWith(
        capabilitiesStatus: capabilities.available
            ? AgentLoadStatus.ready
            : AgentLoadStatus.unavailable,
        capabilities: capabilities,
        messages: mustClear ? const [] : state.messages,
        pendingProposal: mustClear ? null : state.pendingProposal,
        busy: false,
        errorCode: null,
        errorMessage: null,
        canRetry: mustClear ? false : state.canRetry,
      );
    } on FormatException {
      if (request != _capabilitiesRequest) return;
      _lastRetryableTurn = null;
      state = state.copyWith(
        capabilitiesStatus: AgentLoadStatus.parseError,
        capabilities: null,
        messages: const [],
        pendingProposal: null,
        busy: false,
        errorCode: 'agent_response_invalid',
        errorMessage: 'Agent 服务返回格式异常，未执行任何操作。',
        canRetry: false,
      );
    } on DioException {
      if (request != _capabilitiesRequest) return;
      state = state.copyWith(
        capabilitiesStatus: AgentLoadStatus.networkError,
        busy: false,
        errorCode: 'agent_network_error',
        errorMessage: '无法连接 Agent 服务，其他功能仍可正常使用。',
        canRetry: false,
      );
    }
  }

  void setContext(AgentRouteContext context) {
    if (state.context.entryType == context.entryType &&
        state.context.entityId == context.entityId) {
      return;
    }
    _generation += 1;
    _lastRetryableTurn = null;
    state = state.copyWith(
      context: context,
      messages: const [],
      pendingProposal: null,
      busy: false,
      errorCode: null,
      errorMessage: null,
      canRetry: false,
    );
  }

  void clearConversation() {
    _generation += 1;
    _lastRetryableTurn = null;
    state = state.copyWith(
      messages: const [],
      pendingProposal: null,
      busy: false,
      errorCode: null,
      errorMessage: null,
      canRetry: false,
    );
  }

  Future<bool> grantConsent() async {
    final disclosure = state.capabilities?.disclosure;
    if (disclosure == null || state.busy) return false;
    final generation = _generation;
    state = state.copyWith(busy: true, errorCode: null, errorMessage: null);
    try {
      final response = await _api.dio.post(
        '/agent/consents:grant',
        data: {
          'accepted_provider_id': disclosure.providerId,
          'accepted_disclosure_version': disclosure.disclosureVersion,
          'idempotency_key': newIdempotencyKey(),
        },
      );
      final consent = AgentConsentResult.fromJson(_responseMap(response.data));
      if (consent.status != 'granted') {
        throw const FormatException('grant returned non-granted status');
      }
      if (generation != _generation) return false;
      clearConversation();
      await loadCapabilities();
      return state.available;
    } on FormatException {
      if (generation == _generation) {
        state = state.copyWith(
          capabilitiesStatus: AgentLoadStatus.parseError,
          busy: false,
          errorCode: 'agent_response_invalid',
          errorMessage: '同意结果格式异常，Agent 未启用。',
        );
      }
      return false;
    } on DioException catch (error) {
      if (generation == _generation) {
        final code = _apiErrorCode(error);
        final staleDisclosure = code == 'agent_disclosure_stale';
        state = state.copyWith(
          capabilitiesStatus: staleDisclosure
              ? state.capabilitiesStatus
              : AgentLoadStatus.networkError,
          busy: false,
          errorCode: code,
          errorMessage: staleDisclosure
              ? '服务信息已更新，请重新阅读当前告知。'
              : '无法保存同意，请稍后重试。',
        );
        if (staleDisclosure) await loadCapabilities();
      }
      return false;
    }
  }

  Future<bool> withdrawConsent() async {
    if (state.busy) return false;
    _generation += 1;
    _capabilitiesRequest += 1;
    final generation = _generation;
    _lastRetryableTurn = null;
    state = state.copyWith(
      messages: const [],
      pendingProposal: null,
      busy: true,
      errorCode: null,
      errorMessage: null,
      canRetry: false,
    );
    try {
      final response = await _api.dio.post(
        '/agent/consents:withdraw',
        data: {'idempotency_key': newIdempotencyKey()},
      );
      final consent = AgentConsentResult.fromJson(_responseMap(response.data));
      if (consent.status != 'withdrawn') {
        throw const FormatException('withdraw returned non-withdrawn status');
      }
      if (generation != _generation) return false;
      await loadCapabilities();
      return true;
    } on FormatException {
      if (generation == _generation) {
        state = state.copyWith(
          capabilitiesStatus: AgentLoadStatus.parseError,
          busy: false,
          errorCode: 'agent_response_invalid',
          errorMessage: '撤回结果格式异常，请刷新后核对状态。',
        );
      }
      return false;
    } on DioException {
      if (generation == _generation) {
        state = state.copyWith(
          capabilitiesStatus: AgentLoadStatus.networkError,
          busy: false,
          errorCode: 'agent_network_error',
          errorMessage: '撤回请求失败；本地对话已清除，请刷新后核对同意状态。',
        );
      }
      return false;
    }
  }

  Future<bool> deleteAgentData() async {
    if (state.busy) return false;
    _generation += 1;
    _capabilitiesRequest += 1;
    final generation = _generation;
    _lastRetryableTurn = null;
    state = state.copyWith(
      messages: const [],
      pendingProposal: null,
      busy: true,
      errorCode: null,
      errorMessage: null,
      canRetry: false,
    );
    try {
      final response = await _api.dio.delete('/agent/data');
      AgentDataDeletionResult.fromJson(_responseMap(response.data));
      if (generation != _generation) return false;
      await loadCapabilities();
      return true;
    } on FormatException {
      if (generation == _generation) {
        state = state.copyWith(
          capabilitiesStatus: AgentLoadStatus.parseError,
          busy: false,
          errorCode: 'agent_response_invalid',
          errorMessage: '删除结果格式异常，请刷新后核对状态。',
        );
      }
      return false;
    } on DioException {
      if (generation == _generation) {
        state = state.copyWith(
          capabilitiesStatus: AgentLoadStatus.networkError,
          busy: false,
          errorCode: 'agent_network_error',
          errorMessage: 'Agent 数据删除请求失败；本地对话已清除。',
        );
      }
      return false;
    }
  }

  Future<bool> sendMessage(String rawMessage) async {
    final message = rawMessage.trim();
    if (!state.available || state.busy || state.pendingProposal != null) {
      return false;
    }
    if (message.isEmpty || message.length > 2000) {
      state = state.copyWith(
        errorCode: 'agent_request_invalid',
        errorMessage: '请输入 1 至 2000 个字符。',
        canRetry: false,
      );
      return false;
    }
    final draft = _TurnDraft(
      clientTurnId: newIdempotencyKey(),
      context: state.context,
      message: message,
    );
    return _executeTurn(draft, appendUser: true);
  }

  Future<bool> retryLastTurn() async {
    final previous = _lastRetryableTurn;
    if (previous == null || !state.available || state.busy) return false;
    return _executeTurn(previous.retried(), appendUser: false);
  }

  Future<bool> _executeTurn(
    _TurnDraft draft, {
    required bool appendUser,
  }) async {
    final generation = _generation;
    final messages = [
      ...state.messages,
      if (appendUser) AgentConversationItem.user(draft.message),
    ];
    state = state.copyWith(
      messages: messages,
      busy: true,
      errorCode: null,
      errorMessage: null,
      canRetry: false,
    );
    try {
      final response = await _api.dio.post(
        '/agent/turns',
        data: draft.toJson(),
      );
      final turn = AgentTurnResponse.fromJson(_responseMap(response.data));
      if (generation != _generation) return false;
      _recordTurn(turn, draft);
      return true;
    } on DioException catch (error) {
      if (generation != _generation) return false;
      final body = error.response?.data;
      if (body is Map<String, dynamic>) {
        try {
          final turn = AgentTurnResponse.fromJson(body);
          _recordTurn(turn, draft);
          return true;
        } on FormatException {
          // Fall through to a redacted transport error. Never display raw data.
        }
      }
      _lastRetryableTurn = draft;
      state = state.copyWith(
        busy: false,
        errorCode: 'agent_network_error',
        errorMessage: 'Agent 请求失败，未执行任何操作。',
        canRetry: true,
      );
      return false;
    } on FormatException {
      if (generation != _generation) return false;
      _lastRetryableTurn = null;
      state = state.copyWith(
        busy: false,
        pendingProposal: null,
        errorCode: 'agent_response_invalid',
        errorMessage: 'Agent 返回格式异常，未执行任何操作。',
        canRetry: false,
      );
      return false;
    }
  }

  void _recordTurn(AgentTurnResponse turn, _TurnDraft draft) {
    _lastRetryableTurn = turn.isRetryableFailure ? draft : null;
    state = state.copyWith(
      messages: [...state.messages, AgentConversationItem.agent(turn)],
      pendingProposal: turn.proposal,
      busy: false,
      errorCode: null,
      errorMessage: null,
      canRetry: turn.isRetryableFailure,
    );
  }

  Future<bool> confirmProposal() async {
    final proposal = state.pendingProposal;
    if (proposal == null || state.busy) return false;
    final generation = _generation;
    state = state.copyWith(busy: true, errorCode: null, errorMessage: null);
    try {
      final response = await _api.dio.post(
        '/agent/actions/${proposal.proposalId}:confirm',
        data: {'idempotency_key': newIdempotencyKey()},
      );
      final action = AgentActionResponse.fromJson(_responseMap(response.data));
      if (generation != _generation) return false;
      if (action.proposalId != proposal.proposalId) {
        throw const FormatException('confirmation returned another proposal');
      }
      if (action.executed) _onDomainWrite();
      _lastRetryableTurn = null;
      state = state.copyWith(
        messages: [...state.messages, AgentConversationItem.action(action)],
        pendingProposal: null,
        busy: false,
        errorCode: null,
        errorMessage: null,
        canRetry: false,
      );
      return action.executed;
    } on FormatException {
      if (generation == _generation) {
        state = state.copyWith(
          busy: false,
          errorCode: 'agent_response_invalid',
          errorMessage: '确认结果格式异常，不会显示为已完成。',
        );
      }
      return false;
    } on DioException {
      if (generation == _generation) {
        state = state.copyWith(
          busy: false,
          errorCode: 'agent_network_error',
          errorMessage: '确认请求失败，无法确认操作是否执行；请刷新后核对。',
        );
      }
      return false;
    }
  }

  Future<bool> cancelProposal() async {
    final proposal = state.pendingProposal;
    if (proposal == null || state.busy) return false;
    final generation = _generation;
    state = state.copyWith(busy: true, errorCode: null, errorMessage: null);
    try {
      final response = await _api.dio.post(
        '/agent/actions/${proposal.proposalId}:cancel',
      );
      final action = AgentActionResponse.fromJson(_responseMap(response.data));
      if (generation != _generation) return false;
      if (action.proposalId != proposal.proposalId ||
          action.status != 'cancelled') {
        throw const FormatException('cancel returned inconsistent status');
      }
      _lastRetryableTurn = null;
      state = state.copyWith(
        messages: [...state.messages, AgentConversationItem.action(action)],
        pendingProposal: null,
        busy: false,
        errorCode: null,
        errorMessage: null,
        canRetry: false,
      );
      return true;
    } on FormatException {
      if (generation == _generation) {
        state = state.copyWith(
          busy: false,
          errorCode: 'agent_response_invalid',
          errorMessage: '取消结果格式异常，请刷新后核对。',
        );
      }
      return false;
    } on DioException {
      if (generation == _generation) {
        state = state.copyWith(
          busy: false,
          errorCode: 'agent_network_error',
          errorMessage: '取消请求失败，请稍后重试。',
        );
      }
      return false;
    }
  }

  @override
  void dispose() {
    _generation += 1;
    _capabilitiesRequest += 1;
    super.dispose();
  }
}

final agentProvider = StateNotifierProvider<AgentNotifier, AgentState>((ref) {
  final api = ref.read(apiClientProvider);
  return AgentNotifier(
    api,
    onDomainWrite: () {
      ref.invalidate(dailyCheckinProvider);
      ref.invalidate(weightTrendProvider);
      ref.invalidate(planProvider);
    },
  );
});

const _unset = Object();

Map<String, dynamic> _responseMap(Object? data) {
  if (data is Map<String, dynamic>) return data;
  throw const FormatException('Agent response is not an object');
}

String? _apiErrorCode(DioException error) {
  final data = error.response?.data;
  if (data is Map<String, dynamic>) {
    final code = data['code'];
    if (code is String && _knownApiErrors.contains(code)) return code;
  }
  return null;
}

const _knownApiErrors = {
  'agent_disclosure_stale',
  'idempotency_key_conflict',
  'agent_consent_required',
  'agent_disabled',
  'agent_privacy_gate_blocked',
};

String _fallbackMessage(String resultCode) {
  switch (resultCode) {
    case 'agent_action_confirmation_required':
      return '操作尚未执行，请核对后明确确认或取消。';
    case 'agent_action_expired':
      return '该操作提案已过期，请重新发起。';
    case 'agent_action_invalidated':
      return '相关信息已变化，该操作未执行。';
    default:
      return '已返回先前请求的结构化状态。';
  }
}
