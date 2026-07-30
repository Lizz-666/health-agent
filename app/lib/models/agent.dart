// Strict client contracts for the authenticated Phase 5 Agent API.
//
// The server owns authorization, safety decisions, tool selection, and all
// user-visible Agent response text. Unknown or malformed values fail closed;
// they are never coerced into a successful client state.

enum AgentEntryType {
  general('general'),
  healthProfile('health_profile'),
  postureIssue('posture_issue'),
  trainingPlan('training_plan'),
  trainingSession('training_session'),
  trainingExercise('training_exercise');

  const AgentEntryType(this.wire);
  final String wire;

  static AgentEntryType parse(Object? raw) => values.firstWhere(
    (value) => value.wire == raw,
    orElse: () => throw FormatException('unknown Agent entry type: $raw'),
  );
}

class AgentRouteContext {
  const AgentRouteContext({
    this.entryType = AgentEntryType.general,
    this.entityId,
  });

  final AgentEntryType entryType;
  final String? entityId;

  factory AgentRouteContext.fromQuery(Map<String, String> query) {
    const allowed = {'entry_type', 'entity_id'};
    if (query.keys.any((key) => !allowed.contains(key))) {
      throw const FormatException('unknown Agent route parameter');
    }
    final entry = query['entry_type'] == null
        ? AgentEntryType.general
        : AgentEntryType.parse(query['entry_type']);
    final entity = query['entity_id'];
    if (entity != null && (entity.trim().isEmpty || entity.length > 64)) {
      throw const FormatException('invalid Agent entity id');
    }
    return AgentRouteContext(entryType: entry, entityId: entity);
  }

  Map<String, String> toQuery() => {
    'entry_type': entryType.wire,
    'entity_id': ?entityId,
  };

  @override
  bool operator ==(Object other) =>
      other is AgentRouteContext &&
      other.entryType == entryType &&
      other.entityId == entityId;

  @override
  int get hashCode => Object.hash(entryType, entityId);
}

class AgentDisclosure {
  const AgentDisclosure({
    required this.disclosureVersion,
    required this.providerId,
    required this.providerNameZh,
    required this.purposeCode,
    required this.processingBoundaryCode,
    required this.dataScopeCodes,
    required this.applicationRetentionCode,
    required this.withdrawalAvailable,
    required this.agentDataDeletionAvailable,
  });

  final String disclosureVersion;
  final String providerId;
  final String providerNameZh;
  final String purposeCode;
  final String processingBoundaryCode;
  final List<String> dataScopeCodes;
  final String applicationRetentionCode;
  final bool withdrawalAvailable;
  final bool agentDataDeletionAvailable;

  factory AgentDisclosure.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {
      'disclosure_version',
      'provider_id',
      'provider_name_zh',
      'purpose_code',
      'processing_boundary_code',
      'data_scope_codes',
      'application_retention_code',
      'withdrawal_available',
      'agent_data_deletion_available',
    });
    return AgentDisclosure(
      disclosureVersion: _string(json, 'disclosure_version'),
      providerId: _string(json, 'provider_id'),
      providerNameZh: _string(json, 'provider_name_zh'),
      purposeCode: _string(json, 'purpose_code'),
      processingBoundaryCode: _string(json, 'processing_boundary_code'),
      dataScopeCodes: _stringList(json, 'data_scope_codes'),
      applicationRetentionCode: _string(json, 'application_retention_code'),
      withdrawalAvailable: _boolean(json, 'withdrawal_available'),
      agentDataDeletionAvailable: _boolean(
        json,
        'agent_data_deletion_available',
      ),
    );
  }
}

class AgentCapabilities {
  const AgentCapabilities({
    required this.runtimeEnabled,
    required this.providerConfigured,
    required this.providerId,
    required this.modelId,
    required this.disclosureVersion,
    required this.consentActive,
    required this.available,
    required this.resultCode,
    required this.message,
    required this.disclosure,
  });

  final bool runtimeEnabled;
  final bool providerConfigured;
  final String? providerId;
  final String? modelId;
  final String? disclosureVersion;
  final bool consentActive;
  final bool available;
  final String resultCode;
  final String message;
  final AgentDisclosure? disclosure;

  String get boundaryId =>
      '${providerId ?? ''}:${modelId ?? ''}:${disclosureVersion ?? ''}';

  factory AgentCapabilities.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {
      'runtime_enabled',
      'provider_configured',
      'provider_id',
      'model_id',
      'disclosure_version',
      'consent_active',
      'available',
      'result_code',
      'message',
      'disclosure',
    });
    final resultCode = _knownResultCode(json, 'result_code');
    final disclosureJson = _optionalMap(json, 'disclosure');
    final runtimeEnabled = _boolean(json, 'runtime_enabled');
    final providerConfigured = _boolean(json, 'provider_configured');
    final providerId = _optionalString(json, 'provider_id');
    final modelId = _optionalString(json, 'model_id');
    final disclosureVersion = _optionalString(json, 'disclosure_version');
    final consentActive = _boolean(json, 'consent_active');
    final available = _boolean(json, 'available');
    final disclosure = disclosureJson == null
        ? null
        : AgentDisclosure.fromJson(disclosureJson);

    if (disclosure != null &&
        (disclosure.providerId != providerId ||
            disclosure.disclosureVersion != disclosureVersion)) {
      throw const FormatException('Agent disclosure boundary mismatch');
    }
    if ((available || resultCode == 'agent_available') &&
        !(available &&
            resultCode == 'agent_available' &&
            runtimeEnabled &&
            providerConfigured &&
            consentActive &&
            providerId != null &&
            modelId != null &&
            disclosureVersion != null &&
            disclosure != null &&
            disclosure.withdrawalAvailable &&
            disclosure.agentDataDeletionAvailable)) {
      throw const FormatException('inconsistent Agent availability state');
    }
    if (resultCode == 'agent_consent_required' &&
        (available || consentActive || disclosure == null)) {
      throw const FormatException('inconsistent Agent consent state');
    }
    return AgentCapabilities(
      runtimeEnabled: runtimeEnabled,
      providerConfigured: providerConfigured,
      providerId: providerId,
      modelId: modelId,
      disclosureVersion: disclosureVersion,
      consentActive: consentActive,
      available: available,
      resultCode: resultCode,
      message: _string(json, 'message'),
      disclosure: disclosure,
    );
  }
}

class AgentConsentResult {
  const AgentConsentResult({
    required this.consentId,
    required this.sequenceNo,
    required this.status,
    required this.replayed,
  });

  final String consentId;
  final int sequenceNo;
  final String status;
  final bool replayed;

  factory AgentConsentResult.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {
      'consent_id',
      'sequence_no',
      'status',
      'replayed',
    });
    final status = _string(json, 'status');
    if (!const {'granted', 'withdrawn'}.contains(status)) {
      throw FormatException('unknown Agent consent status: $status');
    }
    return AgentConsentResult(
      consentId: _string(json, 'consent_id'),
      sequenceNo: _integer(json, 'sequence_no'),
      status: status,
      replayed: _boolean(json, 'replayed'),
    );
  }
}

class AgentDataDeletionResult {
  const AgentDataDeletionResult({
    required this.consentsDeleted,
    required this.runsDeleted,
    required this.toolEventsDeleted,
    required this.proposalsDeleted,
    required this.idempotencyDeleted,
  });

  final int consentsDeleted;
  final int runsDeleted;
  final int toolEventsDeleted;
  final int proposalsDeleted;
  final int idempotencyDeleted;

  factory AgentDataDeletionResult.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {
      'deleted',
      'consents_deleted',
      'runs_deleted',
      'tool_events_deleted',
      'proposals_deleted',
      'idempotency_deleted',
    });
    if (!_boolean(json, 'deleted')) {
      throw const FormatException('Agent data deletion was not acknowledged');
    }
    return AgentDataDeletionResult(
      consentsDeleted: _nonNegativeInteger(json, 'consents_deleted'),
      runsDeleted: _nonNegativeInteger(json, 'runs_deleted'),
      toolEventsDeleted: _nonNegativeInteger(json, 'tool_events_deleted'),
      proposalsDeleted: _nonNegativeInteger(json, 'proposals_deleted'),
      idempotencyDeleted: _nonNegativeInteger(json, 'idempotency_deleted'),
    );
  }
}

enum AgentTurnStatus {
  answer('answer'),
  clarify('clarify'),
  unsupported('unsupported'),
  proposalPending('proposal_pending'),
  safetyRouted('safety_routed'),
  failed('failed'),
  replayed('replayed');

  const AgentTurnStatus(this.wire);
  final String wire;

  static AgentTurnStatus parse(Object? raw) => values.firstWhere(
    (value) => value.wire == raw,
    orElse: () => throw FormatException('unknown Agent turn status: $raw'),
  );
}

enum AgentActionType {
  upsertTodayCheckin('upsert_today_checkin'),
  createWeightRecord('create_weight_record'),
  generateTrainingPlanDraft('generate_training_plan_draft'),
  substituteTodayExercise('substitute_today_exercise'),
  recordTrainingFeedback('record_training_feedback');

  const AgentActionType(this.wire);
  final String wire;

  static AgentActionType parse(Object? raw) => values.firstWhere(
    (value) => value.wire == raw,
    orElse: () => throw FormatException('unknown Agent action: $raw'),
  );
}

abstract class AgentActionDiff {
  const AgentActionDiff(this.action, this.summaryCode);

  final AgentActionType action;
  final String summaryCode;
  List<MapEntry<String, String>> get displayRows;

  static AgentActionDiff fromJson(
    AgentActionType expectedAction,
    Map<String, dynamic> json,
  ) {
    if (AgentActionType.parse(json['action']) != expectedAction) {
      throw const FormatException('proposal action and diff disagree');
    }
    final summary = _string(json, 'summary_code');
    switch (expectedAction) {
      case AgentActionType.upsertTodayCheckin:
        _expectKeys(json, const {
          'action',
          'summary_code',
          'local_date',
          'abnormal_pain',
        });
        return CheckinActionDiff(
          summary,
          _date(json, 'local_date'),
          _boolean(json, 'abnormal_pain'),
        );
      case AgentActionType.createWeightRecord:
        _expectKeys(json, const {
          'action',
          'summary_code',
          'recorded_at',
          'weight_kg',
        });
        return WeightActionDiff(
          summary,
          _dateTime(json, 'recorded_at'),
          _number(json, 'weight_kg'),
        );
      case AgentActionType.generateTrainingPlanDraft:
        _expectKeys(json, const {
          'action',
          'summary_code',
          'fitness_goal',
          'weekly_frequency',
          'session_duration_minutes',
          'requires_plan_review',
        });
        return PlanDraftActionDiff(
          summary,
          _string(json, 'fitness_goal'),
          _integer(json, 'weekly_frequency'),
          _integer(json, 'session_duration_minutes'),
          _boolean(json, 'requires_plan_review'),
        );
      case AgentActionType.substituteTodayExercise:
        _expectKeysWithOptional(
          json,
          const {
            'action',
            'summary_code',
            'original_exercise_id',
            'replacement_exercise_id',
          },
          const {'session_id'},
        );
        return SubstitutionActionDiff(
          summary,
          _optionalString(json, 'session_id'),
          _string(json, 'original_exercise_id'),
          _string(json, 'replacement_exercise_id'),
        );
      case AgentActionType.recordTrainingFeedback:
        _expectKeysWithOptional(
          json,
          const {'action', 'summary_code', 'outcome_state'},
          const {'session_id'},
        );
        final outcome = _string(json, 'outcome_state');
        if (!const {
          'completed',
          'partial',
          'too_busy',
          'intentional_rest',
        }.contains(outcome)) {
          throw FormatException('unknown feedback outcome: $outcome');
        }
        return FeedbackActionDiff(
          summary,
          _optionalString(json, 'session_id'),
          outcome,
        );
    }
  }
}

class CheckinActionDiff extends AgentActionDiff {
  const CheckinActionDiff(String summaryCode, this.localDate, this.abnormalPain)
    : super(AgentActionType.upsertTodayCheckin, summaryCode);

  final DateTime localDate;
  final bool abnormalPain;

  @override
  List<MapEntry<String, String>> get displayRows => [
    MapEntry('日期', _dateOnly(localDate)),
    MapEntry('异常疼痛', abnormalPain ? '是' : '否'),
  ];
}

class WeightActionDiff extends AgentActionDiff {
  const WeightActionDiff(String summaryCode, this.recordedAt, this.weightKg)
    : super(AgentActionType.createWeightRecord, summaryCode);

  final DateTime recordedAt;
  final num weightKg;

  @override
  List<MapEntry<String, String>> get displayRows => [
    MapEntry('记录时间', recordedAt.toLocal().toString()),
    MapEntry('体重', '$weightKg kg'),
  ];
}

class PlanDraftActionDiff extends AgentActionDiff {
  const PlanDraftActionDiff(
    String summaryCode,
    this.fitnessGoal,
    this.weeklyFrequency,
    this.sessionDurationMinutes,
    this.requiresPlanReview,
  ) : super(AgentActionType.generateTrainingPlanDraft, summaryCode);

  final String fitnessGoal;
  final int weeklyFrequency;
  final int sessionDurationMinutes;
  final bool requiresPlanReview;

  @override
  List<MapEntry<String, String>> get displayRows => [
    MapEntry('目标', fitnessGoal),
    MapEntry('每周频次', '$weeklyFrequency 次'),
    MapEntry('单次时长', '$sessionDurationMinutes 分钟'),
    MapEntry('仍需计划页确认', requiresPlanReview ? '是' : '否'),
  ];
}

class SubstitutionActionDiff extends AgentActionDiff {
  const SubstitutionActionDiff(
    String summaryCode,
    this.sessionId,
    this.originalExerciseId,
    this.replacementExerciseId,
  ) : super(AgentActionType.substituteTodayExercise, summaryCode);

  final String? sessionId;
  final String originalExerciseId;
  final String replacementExerciseId;

  @override
  List<MapEntry<String, String>> get displayRows => [
    MapEntry('原动作', originalExerciseId),
    MapEntry('替代动作', replacementExerciseId),
  ];
}

class FeedbackActionDiff extends AgentActionDiff {
  const FeedbackActionDiff(
    String summaryCode,
    this.sessionId,
    this.outcomeState,
  ) : super(AgentActionType.recordTrainingFeedback, summaryCode);

  final String? sessionId;
  final String outcomeState;

  @override
  List<MapEntry<String, String>> get displayRows => [
    MapEntry('完成情况', outcomeState),
  ];
}

class AgentProposal {
  const AgentProposal({
    required this.proposalId,
    required this.action,
    required this.diff,
    required this.expiresAt,
  });

  final String proposalId;
  final AgentActionType action;
  final AgentActionDiff diff;
  final DateTime expiresAt;

  bool get isLocallyExpired => !expiresAt.isAfter(DateTime.now().toUtc());

  factory AgentProposal.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {'proposal_id', 'action', 'diff', 'expires_at'});
    final action = AgentActionType.parse(json['action']);
    return AgentProposal(
      proposalId: _string(json, 'proposal_id'),
      action: action,
      diff: AgentActionDiff.fromJson(action, _map(json, 'diff')),
      expiresAt: _dateTime(json, 'expires_at').toUtc(),
    );
  }
}

class AgentToolDisplay {
  const AgentToolDisplay({required this.toolName, required this.data});

  final String toolName;
  final Map<String, dynamic> data;

  factory AgentToolDisplay.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {'tool_name', 'data'});
    final tool = _string(json, 'tool_name');
    if (!_knownReadTools.contains(tool)) {
      throw FormatException('unknown Agent read tool: $tool');
    }
    final data = _map(json, 'data');
    _validateJsonValue(data);
    return AgentToolDisplay(toolName: tool, data: data);
  }
}

class AgentTurnResponse {
  const AgentTurnResponse({
    required this.runId,
    required this.status,
    required this.message,
    required this.resultCode,
    required this.displayData,
    required this.proposal,
    required this.replayed,
  });

  final String? runId;
  final AgentTurnStatus status;
  final String? message;
  final String resultCode;
  final List<AgentToolDisplay> displayData;
  final AgentProposal? proposal;
  final bool replayed;

  bool get isRetryableFailure =>
      status == AgentTurnStatus.failed &&
      const {
        'agent_provider_unavailable',
        'agent_output_invalid',
        'agent_step_limit',
        'agent_tool_failed',
      }.contains(resultCode);

  factory AgentTurnResponse.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {
      'run_id',
      'status',
      'message',
      'result_code',
      'display_data',
      'proposal',
      'replayed',
    });
    final status = AgentTurnStatus.parse(json['status']);
    final resultCode = _knownResultCode(json, 'result_code');
    final replayed = _boolean(json, 'replayed');
    final proposalJson = _optionalMap(json, 'proposal');
    final proposal = proposalJson == null
        ? null
        : AgentProposal.fromJson(proposalJson);
    if (status == AgentTurnStatus.proposalPending && proposal == null) {
      throw const FormatException('pending Agent turn lacks proposal');
    }
    if (status != AgentTurnStatus.proposalPending &&
        status != AgentTurnStatus.replayed &&
        proposal != null) {
      throw const FormatException('unexpected proposal for Agent turn status');
    }
    if ((status == AgentTurnStatus.replayed) != replayed) {
      throw const FormatException('Agent replay status mismatch');
    }
    _validateTurnStatusCode(status, resultCode);
    return AgentTurnResponse(
      runId: _optionalString(json, 'run_id'),
      status: status,
      message: _optionalString(json, 'message'),
      resultCode: resultCode,
      displayData: _mapList(
        json,
        'display_data',
      ).map(AgentToolDisplay.fromJson).toList(growable: false),
      proposal: proposal,
      replayed: replayed,
    );
  }
}

class AgentActionResponse {
  const AgentActionResponse({
    required this.proposalId,
    required this.status,
    required this.resultCode,
    required this.resultRef,
    required this.message,
  });

  final String proposalId;
  final String status;
  final String resultCode;
  final String? resultRef;
  final String message;

  bool get executed =>
      resultCode == 'agent_action_executed' &&
      const {'executed', 'replayed'}.contains(status);

  factory AgentActionResponse.fromJson(Map<String, dynamic> json) {
    _expectKeys(json, const {
      'proposal_id',
      'status',
      'result_code',
      'result_ref',
      'message',
    });
    final status = _string(json, 'status');
    if (!const {
      'executed',
      'replayed',
      'expired',
      'invalidated',
      'cancelled',
      'blocked',
    }.contains(status)) {
      throw FormatException('unknown Agent action status: $status');
    }
    final code = _knownResultCode(json, 'result_code');
    final hasExecutedCode = code == 'agent_action_executed';
    if ((status == 'executed' && !hasExecutedCode) ||
        (hasExecutedCode && !const {'executed', 'replayed'}.contains(status))) {
      throw const FormatException('Agent action status/result mismatch');
    }
    if ((status == 'expired' && code != 'agent_action_expired') ||
        (status == 'cancelled' && code != 'agent_action_cancelled')) {
      throw const FormatException('Agent terminal status/result mismatch');
    }
    return AgentActionResponse(
      proposalId: _string(json, 'proposal_id'),
      status: status,
      resultCode: code,
      resultRef: _optionalString(json, 'result_ref'),
      message: _string(json, 'message'),
    );
  }
}

const _knownReadTools = {
  'get_health_profile_summary',
  'get_today_checkin',
  'get_weight_trend_summary',
  'list_posture_issues',
  'get_posture_issue',
  'guide_posture_self_test',
  'get_posture_profile',
  'get_posture_priorities',
  'get_training_draft',
  'get_active_training_plan',
  'get_today_training',
  'get_training_exercise',
};

const _knownResultCodes = {
  'invalid_timezone',
  'agent_request_invalid',
  'agent_entity_not_found',
  'agent_entity_not_allowed',
  'agent_entity_required',
  'agent_tool_not_allowed',
  'agent_safety_signal_route_required',
  'no_text_signal_detected',
  'agent_fingerprint_key_missing',
  'agent_fingerprint_invalid_value',
  'agent_read_ok',
  'agent_disabled',
  'agent_consent_required',
  'agent_privacy_gate_blocked',
  'agent_disclosure_stale',
  'agent_provider_unavailable',
  'agent_output_invalid',
  'agent_step_limit',
  'agent_tool_failed',
  'agent_context_stale',
  'agent_available',
  'agent_answer_ready',
  'agent_clarify_required',
  'agent_unsupported_scope',
  'agent_unsupported_medical',
  'agent_unsupported_nutrition',
  'agent_action_confirmation_required',
  'agent_action_expired',
  'agent_action_invalidated',
  'agent_action_cancelled',
  'agent_action_executed',
};

void _expectKeys(Map<String, dynamic> json, Set<String> expected) {
  if (json.length != expected.length ||
      json.keys.any((key) => !expected.contains(key))) {
    throw const FormatException('unexpected JSON object shape');
  }
}

void _expectKeysWithOptional(
  Map<String, dynamic> json,
  Set<String> required,
  Set<String> optional,
) {
  if (required.any((key) => !json.containsKey(key)) ||
      json.keys.any(
        (key) => !required.contains(key) && !optional.contains(key),
      )) {
    throw const FormatException('unexpected JSON object shape');
  }
}

void _validateTurnStatusCode(AgentTurnStatus status, String code) {
  final valid = switch (status) {
    AgentTurnStatus.answer => code == 'agent_answer_ready',
    AgentTurnStatus.clarify => code == 'agent_clarify_required',
    AgentTurnStatus.unsupported => const {
      'agent_unsupported_scope',
      'agent_unsupported_medical',
      'agent_unsupported_nutrition',
    }.contains(code),
    AgentTurnStatus.proposalPending =>
      code == 'agent_action_confirmation_required',
    AgentTurnStatus.safetyRouted =>
      code == 'agent_safety_signal_route_required',
    AgentTurnStatus.failed => !const {
      'agent_available',
      'agent_answer_ready',
      'agent_read_ok',
      'agent_action_confirmation_required',
      'agent_action_executed',
    }.contains(code),
    AgentTurnStatus.replayed => true,
  };
  if (!valid) throw const FormatException('Agent turn status/result mismatch');
}

String _string(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is String && value.trim().isNotEmpty) return value;
  throw FormatException('missing or invalid string: $key');
}

String? _optionalString(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value == null) return null;
  if (value is String && value.trim().isNotEmpty) return value;
  throw FormatException('invalid optional string: $key');
}

bool _boolean(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is bool) return value;
  throw FormatException('missing or invalid bool: $key');
}

int _integer(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is int) return value;
  throw FormatException('missing or invalid int: $key');
}

int _nonNegativeInteger(Map<String, dynamic> json, String key) {
  final value = _integer(json, key);
  if (value < 0) throw FormatException('negative count: $key');
  return value;
}

num _number(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is num && value.isFinite) return value;
  throw FormatException('missing or invalid number: $key');
}

Map<String, dynamic> _map(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is Map<String, dynamic>) return value;
  throw FormatException('missing or invalid object: $key');
}

Map<String, dynamic>? _optionalMap(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value == null) return null;
  if (value is Map<String, dynamic>) return value;
  throw FormatException('invalid optional object: $key');
}

List<Map<String, dynamic>> _mapList(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! List) throw FormatException('missing or invalid list: $key');
  return value
      .map((item) {
        if (item is Map<String, dynamic>) return item;
        throw FormatException('invalid object in list: $key');
      })
      .toList(growable: false);
}

List<String> _stringList(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! List) throw FormatException('missing or invalid list: $key');
  return value
      .map((item) {
        if (item is String && item.trim().isNotEmpty) return item;
        throw FormatException('invalid string in list: $key');
      })
      .toList(growable: false);
}

DateTime _date(Map<String, dynamic> json, String key) {
  final raw = _string(json, key);
  final parsed = DateTime.tryParse(raw);
  if (parsed == null || raw.length != 10) {
    throw FormatException('invalid date: $key');
  }
  return parsed;
}

DateTime _dateTime(Map<String, dynamic> json, String key) {
  final raw = _string(json, key);
  final parsed = DateTime.tryParse(raw);
  if (parsed == null) throw FormatException('invalid datetime: $key');
  return parsed;
}

String _knownResultCode(Map<String, dynamic> json, String key) {
  final code = _string(json, key);
  if (!_knownResultCodes.contains(code)) {
    throw FormatException('unknown Agent result code: $code');
  }
  return code;
}

void _validateJsonValue(Object? value) {
  if (value == null || value is String || value is bool) return;
  if (value is num && value.isFinite) return;
  if (value is List) {
    for (final item in value) {
      _validateJsonValue(item);
    }
    return;
  }
  if (value is Map<String, dynamic>) {
    for (final entry in value.entries) {
      if (entry.key.trim().isEmpty) {
        throw const FormatException('empty JSON key');
      }
      _validateJsonValue(entry.value);
    }
    return;
  }
  throw const FormatException('non-JSON Agent display value');
}

String _dateOnly(DateTime value) =>
    '${value.year.toString().padLeft(4, '0')}-'
    '${value.month.toString().padLeft(2, '0')}-'
    '${value.day.toString().padLeft(2, '0')}';
