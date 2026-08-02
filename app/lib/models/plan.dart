// app/lib/models/plan.dart
//
// Typed models for the Phase 4 training plan API
// (/api/v1/training/plans*). Mirrors backend schemas_api.py.
//
// Safety contract (Task 5):
//  - Unknown enum values (status / today state / outcome state) MUST surface as
//    FormatException; a blocked / restricted / red-flag result is never coerced
//    to a normal-looking plan.
//  - Missing required scalars throw; the provider never renders a half-formed
//    plan.
//  - No raw health values are present in these models or logged by this module.
//  - `decision_gate` / `change_reason` are server-owned strings; the client only
//    displays them and never sends them as authorization.

enum PlanStatus {
  draft,
  active,
  superseded,
  cancelled;

  static PlanStatus tryParse(Object? raw) {
    if (raw is String) {
      switch (raw) {
        case 'draft':
          return PlanStatus.draft;
        case 'active':
          return PlanStatus.active;
        case 'superseded':
          return PlanStatus.superseded;
        case 'cancelled':
          return PlanStatus.cancelled;
      }
    }
    throw FormatException('unknown plan status: $raw');
  }
}

enum TodayState {
  noActivePlan,
  blocked,
  restDay,
  planComplete,
  session;

  static TodayState tryParse(Object? raw) {
    if (raw is String) {
      switch (raw) {
        case 'no_active_plan':
          return TodayState.noActivePlan;
        case 'blocked':
          return TodayState.blocked;
        case 'rest_day':
          return TodayState.restDay;
        case 'plan_complete':
          return TodayState.planComplete;
        case 'session':
          return TodayState.session;
      }
    }
    throw FormatException('unknown today state: $raw');
  }
}

enum OutcomeState {
  completed,
  partial,
  tooBusy,
  intentionalRest,
  discomfort;

  static OutcomeState tryParse(Object? raw) {
    if (raw is String) {
      switch (raw) {
        case 'completed':
          return OutcomeState.completed;
        case 'partial':
          return OutcomeState.partial;
        case 'too_busy':
          return OutcomeState.tooBusy;
        case 'intentional_rest':
          return OutcomeState.intentionalRest;
        case 'discomfort':
          return OutcomeState.discomfort;
      }
    }
    throw FormatException('unknown outcome state: $raw');
  }

  String get wire {
    switch (this) {
      case OutcomeState.tooBusy:
        return 'too_busy';
      case OutcomeState.intentionalRest:
        return 'intentional_rest';
      default:
        return name;
    }
  }
}

// Phase 7 same-day execution overlay kinds. Mirrors the backend
// `AdjustmentKind` wire values (the internal `blocked` outcome is never
// serialized and is therefore intentionally absent here).
enum AdjustmentKind {
  shortened,
  recovery,
  deferred,
  activeRest,
  unchanged;

  static AdjustmentKind tryParse(Object? raw) {
    if (raw is String) {
      switch (raw) {
        case 'shortened':
          return AdjustmentKind.shortened;
        case 'recovery':
          return AdjustmentKind.recovery;
        case 'deferred':
          return AdjustmentKind.deferred;
        case 'active_rest':
          return AdjustmentKind.activeRest;
        case 'unchanged':
          return AdjustmentKind.unchanged;
      }
    }
    throw FormatException('unknown adjustment kind: $raw');
  }
}

// Status of a foreground adjustment command response.
enum AdjustmentApplyStatus {
  recorded,
  replayed;

  static AdjustmentApplyStatus tryParse(Object? raw) {
    if (raw is String) {
      switch (raw) {
        case 'recorded':
          return AdjustmentApplyStatus.recorded;
        case 'replayed':
          return AdjustmentApplyStatus.replayed;
      }
    }
    throw FormatException('unknown adjustment status: $raw');
  }
}

String _readString(Map<String, dynamic> json, String key) {
  final v = json[key];
  if (v is String && v.trim().isNotEmpty) return v;
  throw FormatException('missing or invalid field: $key');
}

String? _readOptionalString(Map<String, dynamic> json, String key) {
  final v = json[key];
  if (v == null) return null;
  if (v is String) return v;
  throw FormatException('invalid optional field: $key');
}

int _readInt(Map<String, dynamic> json, String key) {
  final v = json[key];
  if (v is int) return v;
  if (v is num) return v.toInt();
  throw FormatException('missing or invalid int field: $key');
}

int? _readOptionalInt(Map<String, dynamic> json, String key) {
  final v = json[key];
  if (v == null) return null;
  if (v is int) return v;
  if (v is num) return v.toInt();
  throw FormatException('invalid optional int field: $key');
}

bool _readBool(Map<String, dynamic> json, String key) {
  final v = json[key];
  if (v is bool) return v;
  throw FormatException('missing or invalid bool field: $key');
}

DateTime _readDateTime(Map<String, dynamic> json, String key) {
  final v = json[key];
  if (v is String) {
    final parsed = DateTime.tryParse(v);
    if (parsed != null) return parsed;
  }
  throw FormatException('missing or invalid datetime field: $key');
}

DateTime? _readOptionalDateTime(Map<String, dynamic> json, String key) {
  final v = json[key];
  if (v == null) return null;
  if (v is String) {
    final parsed = DateTime.tryParse(v);
    if (parsed != null) return parsed;
  }
  throw FormatException('invalid optional datetime field: $key');
}

List<String> _readStringList(Map<String, dynamic> json, String key) {
  final v = json[key];
  if (v is List) {
    return v.map((e) {
      if (e is String && e.trim().isNotEmpty) return e;
      throw FormatException('invalid entry in list: $key');
    }).toList();
  }
  throw FormatException('missing or invalid list field: $key');
}

class PlanExercise {
  final String exerciseId;
  final String nameEn;
  final String nameZh;
  final List<String> trainingRoles;
  final String difficulty;
  final String illustrationAssetKey;
  final String illustrationAltZh;
  final List<String> instructionSteps;
  final List<String> formCues;
  final List<String> substitutionIds;

  const PlanExercise({
    required this.exerciseId,
    required this.nameEn,
    required this.nameZh,
    required this.trainingRoles,
    required this.difficulty,
    required this.illustrationAssetKey,
    required this.illustrationAltZh,
    required this.instructionSteps,
    required this.formCues,
    required this.substitutionIds,
  });

  factory PlanExercise.fromJson(Map<String, dynamic> json) {
    return PlanExercise(
      exerciseId: _readString(json, 'exercise_id'),
      nameEn: _readString(json, 'name_en'),
      nameZh: _readString(json, 'name_zh'),
      trainingRoles: _readStringList(json, 'training_roles'),
      difficulty: _readString(json, 'difficulty'),
      illustrationAssetKey: _readString(json, 'illustration_asset_key'),
      illustrationAltZh: _readString(json, 'illustration_alt_zh'),
      instructionSteps: _readStringList(json, 'instruction_steps'),
      formCues: _readStringList(json, 'form_cues'),
      substitutionIds: _readStringList(json, 'substitution_ids'),
    );
  }
}

class PlanPrescription {
  final String? prescriptionId;
  final String exerciseId;
  final int sets;
  final int? reps;
  final int? durationSeconds;
  final int restSeconds;
  final String? relationReason;
  final PlanExercise? exercise;

  const PlanPrescription({
    required this.prescriptionId,
    required this.exerciseId,
    required this.sets,
    required this.reps,
    required this.durationSeconds,
    required this.restSeconds,
    required this.relationReason,
    required this.exercise,
  });

  factory PlanPrescription.fromJson(Map<String, dynamic> json) {
    final ex = json['exercise'];
    return PlanPrescription(
      prescriptionId: _readOptionalString(json, 'prescription_id'),
      exerciseId: _readString(json, 'exercise_id'),
      sets: _readInt(json, 'sets'),
      reps: _readOptionalInt(json, 'reps'),
      durationSeconds: _readOptionalInt(json, 'duration_seconds'),
      restSeconds: _readInt(json, 'rest_seconds'),
      relationReason: _readOptionalString(json, 'relation_reason'),
      exercise: ex is Map<String, dynamic>
          ? PlanExercise.fromJson(ex)
          : (ex == null ? null : throw FormatException('invalid exercise')),
    );
  }
}

class PlanSession {
  final String sessionId;
  final int weekIndex;
  final int dayOfWeek;
  final int sessionOrder;
  final int? targetMinutes;
  final List<PlanPrescription> prescriptions;

  const PlanSession({
    required this.sessionId,
    required this.weekIndex,
    required this.dayOfWeek,
    required this.sessionOrder,
    required this.targetMinutes,
    required this.prescriptions,
  });

  factory PlanSession.fromJson(Map<String, dynamic> json) {
    final list = json['prescriptions'];
    if (list is! List || list.isEmpty) {
      throw FormatException('session missing prescriptions');
    }
    return PlanSession(
      sessionId: _readString(json, 'session_id'),
      weekIndex: _readInt(json, 'week_index'),
      dayOfWeek: _readInt(json, 'day_of_week'),
      sessionOrder: _readInt(json, 'session_order'),
      targetMinutes: _readOptionalInt(json, 'target_minutes'),
      prescriptions: list
          .map((e) => PlanPrescription.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class PlanVersion {
  final String planVersionId;
  final String requestedGoal;
  final int weeklyFrequency;
  final int sessionDurationMinutes;
  final PlanStatus status;
  final String changeReason;
  final String decisionGate;
  final DateTime generatedAt;
  final DateTime? confirmedAt;
  final String catalogVersion;
  final String policyVersion;
  final List<PlanSession> sessions;

  const PlanVersion({
    required this.planVersionId,
    required this.requestedGoal,
    required this.weeklyFrequency,
    required this.sessionDurationMinutes,
    required this.status,
    required this.changeReason,
    required this.decisionGate,
    required this.generatedAt,
    required this.confirmedAt,
    required this.catalogVersion,
    required this.policyVersion,
    required this.sessions,
  });

  factory PlanVersion.fromJson(Map<String, dynamic> json) {
    final list = json['sessions'];
    if (list is! List || list.isEmpty) {
      throw FormatException('plan missing sessions');
    }
    return PlanVersion(
      planVersionId: _readString(json, 'plan_version_id'),
      requestedGoal: _readString(json, 'requested_goal'),
      weeklyFrequency: _readInt(json, 'weekly_frequency'),
      sessionDurationMinutes: _readInt(json, 'session_duration_minutes'),
      status: PlanStatus.tryParse(json['status']),
      changeReason: _readString(json, 'change_reason'),
      decisionGate: _readString(json, 'decision_gate'),
      generatedAt: _readDateTime(json, 'generated_at'),
      confirmedAt: _readOptionalDateTime(json, 'confirmed_at'),
      catalogVersion: _readString(json, 'catalog_version'),
      policyVersion: _readString(json, 'policy_version'),
      sessions: list
          .map((e) => PlanSession.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class DraftResult {
  final bool hasDraft;
  final PlanVersion? draft;
  final String? decisionGate;

  const DraftResult({required this.hasDraft, this.draft, this.decisionGate});

  factory DraftResult.fromJson(Map<String, dynamic> json) {
    final d = json['draft'];
    return DraftResult(
      hasDraft: _readBool(json, 'has_draft'),
      draft: d is Map<String, dynamic>
          ? PlanVersion.fromJson(d)
          : (d == null ? null : throw FormatException('invalid draft')),
      decisionGate: _readOptionalString(json, 'decision_gate'),
    );
  }
}

class ActivePlanResult {
  final bool hasActive;
  final PlanVersion? plan;

  const ActivePlanResult({required this.hasActive, this.plan});

  factory ActivePlanResult.fromJson(Map<String, dynamic> json) {
    final p = json['plan'];
    return ActivePlanResult(
      hasActive: _readBool(json, 'has_active'),
      plan: p is Map<String, dynamic>
          ? PlanVersion.fromJson(p)
          : (p == null ? null : throw FormatException('invalid plan')),
    );
  }
}

class TodayResult {
  final TodayState state;
  final DateTime? localDate;
  final String? changeReason;
  final String? decisionGate;
  final PlanSession? session;
  final OutcomeState? feedbackOutcomeState;
  final bool substitutionApplied;
  // Phase 7 effective-execution overlay fields. Cross-field invariants are
  // checked by fromJson so executable sessions always retain source identity.
  final String? originalSessionId;
  final DateTime? sourceLocalDate;
  final DateTime? targetLocalDate;
  final String? adjustmentId;
  final AdjustmentKind? adjustmentKind;
  final List<String> adjustmentReasonCodes;
  final String? safetyStatus;

  const TodayResult({
    required this.state,
    required this.localDate,
    required this.changeReason,
    required this.decisionGate,
    required this.session,
    required this.feedbackOutcomeState,
    required this.substitutionApplied,
    this.originalSessionId,
    this.sourceLocalDate,
    this.targetLocalDate,
    this.adjustmentId,
    this.adjustmentKind,
    this.adjustmentReasonCodes = const [],
    this.safetyStatus,
  });

  factory TodayResult.fromJson(Map<String, dynamic> json) {
    final s = json['session'];
    final ld = json['local_date'];
    final state = TodayState.tryParse(json['state']);
    final session = s is Map<String, dynamic>
        ? PlanSession.fromJson(s)
        : (s == null ? null : throw FormatException('invalid session'));
    final originalSessionId = _readOptionalString(json, 'original_session_id');
    final sourceLocalDate = _readOptionalDateTime(json, 'source_local_date');
    final targetLocalDate = _readOptionalDateTime(json, 'target_local_date');
    final adjustmentId = _readOptionalString(json, 'adjustment_id');
    final adjustmentKind = json['adjustment_kind'] == null
        ? null
        : AdjustmentKind.tryParse(json['adjustment_kind']);

    if (state == TodayState.session &&
        (session == null ||
            originalSessionId == null ||
            sourceLocalDate == null)) {
      throw const FormatException(
        'session Today requires effective and original identity',
      );
    }
    if (state != TodayState.session && session != null) {
      throw const FormatException('non-session Today cannot include a session');
    }
    if (state != TodayState.blocked && adjustmentKind != null) {
      if (originalSessionId == null ||
          sourceLocalDate == null ||
          adjustmentId == null) {
        throw const FormatException(
          'effective adjustment requires persisted source identity',
        );
      }
      if (adjustmentKind == AdjustmentKind.deferred &&
          targetLocalDate == null) {
        throw const FormatException('deferred adjustment requires target date');
      }
    }

    return TodayResult(
      state: state,
      localDate: ld is String ? DateTime.tryParse(ld) : null,
      changeReason: _readOptionalString(json, 'change_reason'),
      decisionGate: _readOptionalString(json, 'decision_gate'),
      session: session,
      feedbackOutcomeState: json['feedback_outcome_state'] == null
          ? null
          : OutcomeState.tryParse(json['feedback_outcome_state']),
      substitutionApplied: json['substitution_applied'] == null
          ? false
          : _readBool(json, 'substitution_applied'),
      originalSessionId: originalSessionId,
      sourceLocalDate: sourceLocalDate,
      targetLocalDate: targetLocalDate,
      adjustmentId: adjustmentId,
      adjustmentKind: adjustmentKind,
      adjustmentReasonCodes: json['adjustment_reason_codes'] == null
          ? const []
          : _readStringList(json, 'adjustment_reason_codes'),
      safetyStatus: _readOptionalString(json, 'safety_status'),
    );
  }
}

class FeedbackResult {
  final String feedbackId;
  final OutcomeState outcomeState;
  final String status; // "recorded" | "replayed"

  const FeedbackResult({
    required this.feedbackId,
    required this.outcomeState,
    required this.status,
  });

  factory FeedbackResult.fromJson(Map<String, dynamic> json) {
    return FeedbackResult(
      feedbackId: _readString(json, 'feedback_id'),
      outcomeState: OutcomeState.tryParse(json['outcome_state']),
      status: _readString(json, 'status'),
    );
  }
}

class SubstitutionResult {
  final String substitutionId;
  final String status; // "recorded" | "replayed"

  const SubstitutionResult({
    required this.substitutionId,
    required this.status,
  });

  factory SubstitutionResult.fromJson(Map<String, dynamic> json) {
    return SubstitutionResult(
      substitutionId: _readString(json, 'substitution_id'),
      status: _readString(json, 'status'),
    );
  }
}

// Result of an explicit foreground adjustment command
// (POST /training/today/adjustments). Mirrors backend AdjustmentResponse.
class AdjustmentResult {
  final String adjustmentId;
  final AdjustmentApplyStatus status;
  final AdjustmentKind adjustmentKind;
  final String originalSessionId;
  final DateTime sourceLocalDate;
  final DateTime? targetLocalDate;
  final int? targetMinutes;
  final List<String> reasonCodes;

  const AdjustmentResult({
    required this.adjustmentId,
    required this.status,
    required this.adjustmentKind,
    required this.originalSessionId,
    required this.sourceLocalDate,
    required this.targetLocalDate,
    required this.targetMinutes,
    required this.reasonCodes,
  });

  factory AdjustmentResult.fromJson(Map<String, dynamic> json) {
    final adjustmentKind = AdjustmentKind.tryParse(json['adjustment_kind']);
    final targetLocalDate = _readOptionalDateTime(json, 'target_local_date');
    if (adjustmentKind == AdjustmentKind.deferred && targetLocalDate == null) {
      throw const FormatException('deferred adjustment requires target date');
    }
    return AdjustmentResult(
      adjustmentId: _readString(json, 'adjustment_id'),
      status: AdjustmentApplyStatus.tryParse(json['status']),
      adjustmentKind: adjustmentKind,
      originalSessionId: _readString(json, 'original_session_id'),
      sourceLocalDate: _readDateTime(json, 'source_local_date'),
      targetLocalDate: targetLocalDate,
      targetMinutes: _readOptionalInt(json, 'target_minutes'),
      reasonCodes: json['reason_codes'] == null
          ? const []
          : _readStringList(json, 'reason_codes'),
    );
  }
}

// --- request bodies --------------------------------------------------------

class DraftInput {
  final String fitnessGoal;
  final int weeklyFrequency;
  final int sessionDurationMinutes;
  final bool equipmentBodyweight;
  final bool equipmentResistanceBand;
  final String ianaTimezone;
  final String idempotencyKey;

  const DraftInput({
    required this.fitnessGoal,
    required this.weeklyFrequency,
    required this.sessionDurationMinutes,
    required this.equipmentBodyweight,
    required this.equipmentResistanceBand,
    required this.ianaTimezone,
    required this.idempotencyKey,
  });

  Map<String, dynamic> toJson() => {
    'fitness_goal': fitnessGoal,
    'weekly_frequency': weeklyFrequency,
    'session_duration_minutes': sessionDurationMinutes,
    'equipment_bodyweight': equipmentBodyweight,
    'equipment_resistance_band': equipmentResistanceBand,
    'iana_timezone': ianaTimezone,
    'idempotency_key': idempotencyKey,
  };
}

class ConfirmInput {
  final String fitnessGoal;
  final int weeklyFrequency;
  final int sessionDurationMinutes;
  final bool equipmentBodyweight;
  final bool equipmentResistanceBand;
  final String ianaTimezone;
  final String idempotencyKey;

  const ConfirmInput({
    required this.fitnessGoal,
    required this.weeklyFrequency,
    required this.sessionDurationMinutes,
    required this.equipmentBodyweight,
    required this.equipmentResistanceBand,
    required this.ianaTimezone,
    required this.idempotencyKey,
  });

  Map<String, dynamic> toJson() => {
    'fitness_goal': fitnessGoal,
    'weekly_frequency': weeklyFrequency,
    'session_duration_minutes': sessionDurationMinutes,
    'equipment_bodyweight': equipmentBodyweight,
    'equipment_resistance_band': equipmentResistanceBand,
    'iana_timezone': ianaTimezone,
    'idempotency_key': idempotencyKey,
  };
}

class FeedbackInput {
  final OutcomeState outcomeState;
  final String idempotencyKey;

  const FeedbackInput({
    required this.outcomeState,
    required this.idempotencyKey,
  });

  Map<String, dynamic> toJson() => {
    'outcome_state': outcomeState.wire,
    'idempotency_key': idempotencyKey,
  };
}

class SubstitutionInput {
  final String originalExerciseId;
  final String replacementExerciseId;
  final String idempotencyKey;

  const SubstitutionInput({
    required this.originalExerciseId,
    required this.replacementExerciseId,
    required this.idempotencyKey,
  });

  Map<String, dynamic> toJson() => {
    'original_exercise_id': originalExerciseId,
    'replacement_exercise_id': replacementExerciseId,
    'idempotency_key': idempotencyKey,
  };
}

// Foreground same-day adjustment request. The client sends only the intent,
// expected plan/session identity, timezone, and idempotency key. It never sends
// the adjustment kind, target date, replacement exercise, risk tier, target
// minutes, or any safety result; the server derives those deterministically.
class AdjustmentRequestInput {
  final String expectedPlanVersionId;
  final String expectedSessionId;
  final String ianaTimezone;
  final String idempotencyKey;

  const AdjustmentRequestInput({
    required this.expectedPlanVersionId,
    required this.expectedSessionId,
    required this.ianaTimezone,
    required this.idempotencyKey,
  });

  Map<String, dynamic> toJson() => {
    'intent': 'apply_today_adjustment',
    'expected_plan_version_id': expectedPlanVersionId,
    'expected_session_id': expectedSessionId,
    'iana_timezone': ianaTimezone,
    'idempotency_key': idempotencyKey,
  };
}
