// app/lib/models/adaptive_review.dart
//
// Typed models for the Phase 7 weekly review snapshot
// (/api/v1/training/reviews/weeks/{week_index}).
//
// The backend response is strict snake_case. Any response that does not match,
// including a 404 / network failure / unknown enum / missing required field,
// must fail closed as a parse error or an explicit unavailable state, never a
// fabricated review or "all-zero" facts.
//
// Safety contract (mirrors plan.dart):
//  - Unknown enum values surface as FormatException.
//  - Missing required scalars/blocks throw; the provider never renders a
//    half-formed review and never counts missing data as zero.
//  - Weight trend is display / nutrition-refresh context only; it never
//    influences a training proposal and carries no raw body value.
//  - No prose, notes, pain text, photos, meals, chat text, or provider
//    payloads are present in these models.

DateTime _readDate(Map<String, dynamic> json, String key) {
  final v = json[key];
  if (v is String) {
    final parsed = DateTime.tryParse(v);
    if (parsed != null) return parsed;
  }
  throw FormatException('missing or invalid date field: $key');
}

DateTime? _readOptionalDate(Map<String, dynamic> json, String key) {
  final v = json[key];
  if (v == null) return null;
  if (v is String) {
    final parsed = DateTime.tryParse(v);
    if (parsed != null) return parsed;
  }
  throw FormatException('invalid optional date field: $key');
}

String _readString(Map<String, dynamic> json, String key) {
  final v = json[key];
  if (v is String && v.trim().isNotEmpty) return v;
  throw FormatException('missing or invalid field: $key');
}

String _readFingerprint(Map<String, dynamic> json, String key) {
  final value = _readString(json, key);
  if (!RegExp(r'^[0-9a-f]{64}$').hasMatch(value)) {
    throw FormatException('invalid fingerprint field: $key');
  }
  return value;
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
  throw FormatException('missing or invalid int field: $key');
}

int _readCount(Map<String, dynamic> json, String key) {
  final value = _readInt(json, key);
  if (value < 0) throw FormatException('negative count field: $key');
  return value;
}

int? _readOptionalInt(Map<String, dynamic> json, String key) {
  final v = json[key];
  if (v == null) return null;
  if (v is int) return v;
  throw FormatException('invalid optional int field: $key');
}

bool _readBool(Map<String, dynamic> json, String key) {
  final v = json[key];
  if (v is bool) return v;
  throw FormatException('missing or invalid bool field: $key');
}

List<String> _readStringList(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is List && value.every((item) => item is String)) {
    return List<String>.unmodifiable(value.cast<String>());
  }
  throw FormatException('missing or invalid string list field: $key');
}

Map<String, dynamic> _readObject(Map<String, dynamic> json, String key) {
  final v = json[key];
  if (v is Map<String, dynamic>) return v;
  throw FormatException('missing or invalid object field: $key');
}

enum ExecutionTrendDirection {
  improving,
  steady,
  declining;

  static ExecutionTrendDirection tryParse(Object? raw) {
    if (raw is String) {
      switch (raw) {
        case 'improving':
          return ExecutionTrendDirection.improving;
        case 'steady':
          return ExecutionTrendDirection.steady;
        case 'declining':
          return ExecutionTrendDirection.declining;
      }
    }
    throw FormatException('unknown execution trend direction: $raw');
  }
}

enum WeightTrendDirection {
  rising,
  falling,
  stable;

  static WeightTrendDirection tryParse(Object? raw) {
    if (raw is String) {
      switch (raw) {
        case 'rising':
          return WeightTrendDirection.rising;
        case 'falling':
          return WeightTrendDirection.falling;
        case 'stable':
          return WeightTrendDirection.stable;
      }
    }
    throw FormatException('unknown weight trend direction: $raw');
  }
}

enum NutritionRecommendationState {
  none,
  active,
  stale,
  unavailable;

  static NutritionRecommendationState tryParse(Object? raw) {
    if (raw is String) {
      switch (raw) {
        case 'none':
          return NutritionRecommendationState.none;
        case 'active':
          return NutritionRecommendationState.active;
        case 'stale':
          return NutritionRecommendationState.stale;
        case 'unavailable':
          return NutritionRecommendationState.unavailable;
      }
    }
    throw FormatException('unknown nutrition recommendation state: $raw');
  }
}

enum PostureRecheckStatus {
  notDue,
  due,
  comparisonAvailable,
  unavailable;

  static PostureRecheckStatus tryParse(Object? raw) {
    if (raw is String) {
      switch (raw) {
        case 'not_due':
          return PostureRecheckStatus.notDue;
        case 'due':
          return PostureRecheckStatus.due;
        case 'comparison_available':
          return PostureRecheckStatus.comparisonAvailable;
        case 'unavailable':
          return PostureRecheckStatus.unavailable;
      }
    }
    throw FormatException('unknown posture recheck status: $raw');
  }
}

enum PostureComparisonSignal {
  added,
  notDetected,
  unchanged,
  changed;

  static PostureComparisonSignal tryParse(Object? raw) {
    if (raw is String) {
      switch (raw) {
        case 'added':
          return PostureComparisonSignal.added;
        case 'not_detected':
          return PostureComparisonSignal.notDetected;
        case 'unchanged':
          return PostureComparisonSignal.unchanged;
        case 'changed':
          return PostureComparisonSignal.changed;
      }
    }
    throw FormatException('unknown posture comparison signal: $raw');
  }
}

enum ReviewProposalCode {
  keepCurrentPlan,
  offerTrainingDraft,
  offerNutritionRefresh,
  postureRecheckDue,
  postureComparisonAvailable,
  revisitGoal;

  String get wire => switch (this) {
    ReviewProposalCode.keepCurrentPlan => 'keep_current_plan',
    ReviewProposalCode.offerTrainingDraft => 'offer_training_draft',
    ReviewProposalCode.offerNutritionRefresh => 'offer_nutrition_refresh',
    ReviewProposalCode.postureRecheckDue => 'posture_recheck_due',
    ReviewProposalCode.postureComparisonAvailable =>
      'posture_comparison_available',
    ReviewProposalCode.revisitGoal => 'revisit_goal',
  };

  static ReviewProposalCode tryParse(Object? raw) {
    if (raw is String) {
      switch (raw) {
        case 'keep_current_plan':
          return ReviewProposalCode.keepCurrentPlan;
        case 'offer_training_draft':
          return ReviewProposalCode.offerTrainingDraft;
        case 'offer_nutrition_refresh':
          return ReviewProposalCode.offerNutritionRefresh;
        case 'posture_recheck_due':
          return ReviewProposalCode.postureRecheckDue;
        case 'posture_comparison_available':
          return ReviewProposalCode.postureComparisonAvailable;
        case 'revisit_goal':
          return ReviewProposalCode.revisitGoal;
      }
    }
    throw FormatException('unknown review proposal code: $raw');
  }
}

enum ReviewDraftStrategy {
  conservativeDuration,
  lowerFrequency,
  progression,
  regression;

  static ReviewDraftStrategy tryParse(Object? raw) {
    if (raw is String) {
      switch (raw) {
        case 'conservative_duration':
          return ReviewDraftStrategy.conservativeDuration;
        case 'lower_frequency':
          return ReviewDraftStrategy.lowerFrequency;
        case 'progression':
          return ReviewDraftStrategy.progression;
        case 'regression':
          return ReviewDraftStrategy.regression;
      }
    }
    throw FormatException('unknown review draft strategy: $raw');
  }
}

enum ReviewProposalState {
  proposal,
  draft,
  active,
  unavailable;

  static ReviewProposalState tryParse(Object? raw) {
    if (raw is String) {
      switch (raw) {
        case 'proposal':
          return ReviewProposalState.proposal;
        case 'draft':
          return ReviewProposalState.draft;
        case 'active':
          return ReviewProposalState.active;
        case 'unavailable':
          return ReviewProposalState.unavailable;
      }
    }
    throw FormatException('unknown review proposal state: $raw');
  }
}

/// Execution engagement counts. Active-rest and safety-adjustment are valid
/// non-failure engagement states; missing data is never counted as zero here
/// (a missing `execution` block fails closed at the snapshot level).
class WeeklyExecutionFacts {
  final int scheduled;
  final int effective;
  final int completed;
  final int partial;
  final int tooBusy;
  final int intentionalRest;
  final int discomfort;
  final int activeRest;
  final int safetyAdjustment;
  final int unavailable;

  const WeeklyExecutionFacts({
    required this.scheduled,
    required this.effective,
    required this.completed,
    required this.partial,
    required this.tooBusy,
    required this.intentionalRest,
    required this.discomfort,
    required this.activeRest,
    required this.safetyAdjustment,
    required this.unavailable,
  });

  factory WeeklyExecutionFacts.fromJson(Map<String, dynamic> json) {
    return WeeklyExecutionFacts(
      scheduled: _readCount(json, 'scheduled'),
      effective: _readCount(json, 'effective'),
      completed: _readCount(json, 'completed'),
      partial: _readCount(json, 'partial'),
      tooBusy: _readCount(json, 'too_busy'),
      intentionalRest: _readCount(json, 'intentional_rest'),
      discomfort: _readCount(json, 'discomfort'),
      activeRest: _readCount(json, 'active_rest'),
      safetyAdjustment: _readCount(json, 'safety_adjustment'),
      unavailable: _readCount(json, 'unavailable'),
    );
  }
}

class ExecutionTrend {
  final bool available;
  final ExecutionTrendDirection? direction;

  const ExecutionTrend({required this.available, this.direction});

  factory ExecutionTrend.fromJson(Map<String, dynamic> json) {
    final available = _readBool(json, 'available');
    final rawDirection = json['direction'];
    if (available != (rawDirection != null)) {
      throw const FormatException(
        'execution trend availability and direction disagree',
      );
    }
    return ExecutionTrend(
      available: available,
      direction: available
          ? ExecutionTrendDirection.tryParse(rawDirection)
          : null,
    );
  }
}

class AdjustmentFacts {
  final int shortened;
  final int recovery;
  final int deferred;
  final int activeRest;
  final int unchanged;
  final int missing;
  final int unavailable;

  const AdjustmentFacts({
    required this.shortened,
    required this.recovery,
    required this.deferred,
    required this.activeRest,
    required this.unchanged,
    required this.missing,
    required this.unavailable,
  });

  factory AdjustmentFacts.fromJson(Map<String, dynamic> json) {
    return AdjustmentFacts(
      shortened: _readCount(json, 'shortened'),
      recovery: _readCount(json, 'recovery'),
      deferred: _readCount(json, 'deferred'),
      activeRest: _readCount(json, 'active_rest'),
      unchanged: _readCount(json, 'unchanged'),
      missing: _readCount(json, 'missing'),
      unavailable: _readCount(json, 'unavailable'),
    );
  }
}

/// Descriptive weight trend from the existing health service. Display and
/// nutrition-refresh context only; never influences a training proposal and
/// carries no raw body value.
class WeightTrend {
  final bool available;
  final WeightTrendDirection? direction;

  const WeightTrend({required this.available, this.direction});

  factory WeightTrend.fromJson(Map<String, dynamic> json) {
    final available = _readBool(json, 'available');
    final rawDirection = json['direction'];
    if (available != (rawDirection != null)) {
      throw const FormatException(
        'weight trend availability and direction disagree',
      );
    }
    return WeightTrend(
      available: available,
      direction: available ? WeightTrendDirection.tryParse(rawDirection) : null,
    );
  }
}

class NutritionReviewState {
  final NutritionRecommendationState state;
  final int? ageDays;
  final bool refreshAvailable;
  final String? unavailableReason;
  final String? recommendationId;
  final int? version;

  const NutritionReviewState({
    required this.state,
    required this.ageDays,
    required this.refreshAvailable,
    required this.unavailableReason,
    required this.recommendationId,
    required this.version,
  });

  factory NutritionReviewState.fromJson(Map<String, dynamic> json) {
    final ageDays = _readOptionalInt(json, 'age_days');
    if (ageDays != null && ageDays < 0) {
      throw const FormatException('nutrition age_days cannot be negative');
    }
    final state = NutritionRecommendationState.tryParse(json['state']);
    final refreshAvailable = _readBool(json, 'refresh_available');
    final unavailableReason = _readOptionalString(json, 'unavailable_reason');
    final recommendationId = _readOptionalString(json, 'recommendation_id');
    final version = _readOptionalInt(json, 'version');
    final hasIdentity = recommendationId != null && version != null;
    if ((recommendationId == null) != (version == null) ||
        (version != null && version < 1)) {
      throw const FormatException('nutrition identity must be complete');
    }
    if (state == NutritionRecommendationState.unavailable &&
        (refreshAvailable ||
            unavailableReason == null ||
            unavailableReason.trim().isEmpty)) {
      throw const FormatException(
        'unavailable nutrition state requires a reason and no refresh',
      );
    }
    if (state != NutritionRecommendationState.unavailable &&
        unavailableReason != null) {
      throw const FormatException(
        'only unavailable nutrition state has a reason',
      );
    }
    if (state == NutritionRecommendationState.none &&
        (hasIdentity || ageDays != null || !refreshAvailable)) {
      throw const FormatException(
        'none nutrition state must offer an initial draft',
      );
    }
    if (state == NutritionRecommendationState.active &&
        (!hasIdentity || refreshAvailable)) {
      throw const FormatException(
        'active nutrition state cannot offer refresh',
      );
    }
    if (state == NutritionRecommendationState.stale &&
        (!hasIdentity || !refreshAvailable)) {
      throw const FormatException('stale nutrition state must offer refresh');
    }
    return NutritionReviewState(
      state: state,
      ageDays: ageDays,
      refreshAvailable: refreshAvailable,
      unavailableReason: unavailableReason,
      recommendationId: recommendationId,
      version: version,
    );
  }
}

/// Per-cycle posture recheck state. Comparison uses structured owned
/// summaries only; never raw photos or diagnostic language. An ordinary
/// dismissal reminder never hides safety UI.
class PostureRecheckInfo {
  final PostureRecheckStatus status;
  final PostureComparisonSignal? comparisonSignal;
  final DateTime? baselineAt;
  final DateTime? comparisonAt;
  final List<PostureAssessmentSource> baselineSources;
  final List<PostureAssessmentSource> comparisonSources;
  final String? reason;

  const PostureRecheckInfo({
    required this.status,
    required this.comparisonSignal,
    required this.baselineAt,
    required this.comparisonAt,
    required this.baselineSources,
    required this.comparisonSources,
    required this.reason,
  });

  factory PostureRecheckInfo.fromJson(Map<String, dynamic> json) {
    final status = PostureRecheckStatus.tryParse(json['status']);
    final comparisonSignal = json['comparison_signal'] == null
        ? null
        : PostureComparisonSignal.tryParse(json['comparison_signal']);
    final baselineAt = _readOptionalDate(json, 'baseline_at');
    final comparisonAt = _readOptionalDate(json, 'comparison_at');
    final reason = _readOptionalString(json, 'reason');
    final baselineSources = _readStringList(
      json,
      'baseline_sources',
    ).map(PostureAssessmentSource.tryParse).toList(growable: false);
    final comparisonSources = _readStringList(
      json,
      'comparison_sources',
    ).map(PostureAssessmentSource.tryParse).toList(growable: false);
    if (status == PostureRecheckStatus.comparisonAvailable &&
        (comparisonSignal == null ||
            baselineAt == null ||
            comparisonAt == null)) {
      throw const FormatException(
        'posture comparison requires signal and both anchors',
      );
    }
    if (status != PostureRecheckStatus.comparisonAvailable &&
        (comparisonSignal != null || comparisonAt != null)) {
      throw const FormatException(
        'posture comparison fields require comparison status',
      );
    }
    if (status == PostureRecheckStatus.due && baselineAt == null) {
      throw const FormatException('posture due state requires baseline anchor');
    }
    if (status == PostureRecheckStatus.unavailable &&
        (reason == null || reason.trim().isEmpty)) {
      throw const FormatException(
        'posture unavailable state requires a reason',
      );
    }
    return PostureRecheckInfo(
      status: status,
      comparisonSignal: comparisonSignal,
      baselineAt: baselineAt,
      comparisonAt: comparisonAt,
      baselineSources: baselineSources,
      comparisonSources: comparisonSources,
      reason: reason,
    );
  }
}

enum PostureAssessmentSource {
  selfTest,
  aiPhoto;

  static PostureAssessmentSource tryParse(Object? raw) {
    if (raw is String) {
      switch (raw) {
        case 'self_test':
          return PostureAssessmentSource.selfTest;
        case 'ai_photo':
          return PostureAssessmentSource.aiPhoto;
      }
    }
    throw FormatException('unknown posture assessment source: $raw');
  }
}

class ReviewSafetyState {
  final String gate;
  final bool blocked;
  final List<String> reasonCodes;
  final List<String> missingFields;

  const ReviewSafetyState({
    required this.gate,
    required this.blocked,
    required this.reasonCodes,
    required this.missingFields,
  });

  factory ReviewSafetyState.fromJson(Map<String, dynamic> json) {
    return ReviewSafetyState(
      gate: _readString(json, 'gate'),
      blocked: _readBool(json, 'blocked'),
      reasonCodes: _readStringList(json, 'reason_codes'),
      missingFields: _readStringList(json, 'missing_fields'),
    );
  }
}

class ReviewProposal {
  final ReviewProposalCode code;
  final ReviewProposalState state;
  final ReviewDraftStrategy? strategy;
  final String? originWeeklyReviewId;

  const ReviewProposal({
    required this.code,
    required this.state,
    required this.strategy,
    required this.originWeeklyReviewId,
  });

  factory ReviewProposal.fromJson(Map<String, dynamic> json) {
    final code = ReviewProposalCode.tryParse(json['code']);
    final state = ReviewProposalState.tryParse(json['state']);
    final strategy = json['strategy'] == null
        ? null
        : ReviewDraftStrategy.tryParse(json['strategy']);
    if ((code == ReviewProposalCode.offerTrainingDraft) != (strategy != null)) {
      throw const FormatException(
        'only training draft proposals require a strategy',
      );
    }
    return ReviewProposal(
      code: code,
      state: state,
      strategy: strategy,
      originWeeklyReviewId: _readOptionalString(
        json,
        'origin_weekly_review_id',
      ),
    );
  }
}

/// Immutable input-fingerprinted weekly review snapshot. Facts come before
/// proposals. A proposal/draft/active distinction is preserved; a draft still
/// requires the existing separate confirmation flow and is never activated by
/// review generation.
class WeeklyReviewSnapshot {
  final String reviewId;
  final String planVersionId;
  final int weekIndex;
  final int reviewVersion;
  final String inputFingerprint;
  final DateTime periodStart;
  final DateTime periodEnd;
  final WeeklyExecutionFacts execution;
  final ExecutionTrend executionTrend;
  final AdjustmentFacts adjustments;
  final WeightTrend weightTrend;
  final NutritionReviewState nutrition;
  final PostureRecheckInfo posture;
  final ReviewSafetyState safety;
  final List<ReviewProposal> proposals;

  const WeeklyReviewSnapshot({
    required this.reviewId,
    required this.planVersionId,
    required this.weekIndex,
    required this.reviewVersion,
    required this.inputFingerprint,
    required this.periodStart,
    required this.periodEnd,
    required this.execution,
    required this.executionTrend,
    required this.adjustments,
    required this.weightTrend,
    required this.nutrition,
    required this.posture,
    required this.safety,
    required this.proposals,
  });

  factory WeeklyReviewSnapshot.fromJson(Map<String, dynamic> json) {
    final weekIndex = _readInt(json, 'week_index');
    if (weekIndex < 1 || weekIndex > 4) {
      throw FormatException('week_index out of bounds: $weekIndex');
    }
    final proposalsRaw = json['proposals'];
    if (proposalsRaw is! List) {
      throw FormatException('missing or invalid proposals list');
    }
    final reviewVersion = _readInt(json, 'review_version');
    if (reviewVersion < 1) {
      throw const FormatException('review_version must be positive');
    }
    final periodStart = _readDate(json, 'period_start');
    final periodEnd = _readDate(json, 'period_end');
    if (periodEnd.isBefore(periodStart)) {
      throw const FormatException('review period is reversed');
    }
    return WeeklyReviewSnapshot(
      reviewId: _readString(json, 'review_id'),
      planVersionId: _readString(json, 'plan_version_id'),
      weekIndex: weekIndex,
      reviewVersion: reviewVersion,
      inputFingerprint: _readFingerprint(json, 'input_fingerprint'),
      periodStart: periodStart,
      periodEnd: periodEnd,
      execution: WeeklyExecutionFacts.fromJson(_readObject(json, 'execution')),
      executionTrend: ExecutionTrend.fromJson(
        _readObject(json, 'execution_trend'),
      ),
      adjustments: AdjustmentFacts.fromJson(_readObject(json, 'adjustments')),
      weightTrend: WeightTrend.fromJson(_readObject(json, 'weight_trend')),
      nutrition: NutritionReviewState.fromJson(_readObject(json, 'nutrition')),
      posture: PostureRecheckInfo.fromJson(_readObject(json, 'posture')),
      safety: ReviewSafetyState.fromJson(_readObject(json, 'safety')),
      proposals: proposalsRaw
          .map((e) => ReviewProposal.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}
