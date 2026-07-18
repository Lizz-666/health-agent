// app/lib/models/priority_suggestion.dart
//
// Typed models for GET /posture/priorities and POST /posture/goals/confirm
// (spec §9.2 / §10.6 / §10.7, backend PrioritySuggestionsResponse /
// ConfirmGoalsRequest / ConfirmedGoalsResponse).
//
// Safety contract (Task 8B):
//  - `restricted` vs `red_flag` MUST stay semantically distinct in
//    safety_blocked items; an unknown risk_tier surfaces as a parse error
//    rather than coercing to `normal`.
//  - `suggestion_id`, `profile_version`, `rule_version`, `risk_version` are
//    server-generated and echoed back on confirm for optimistic locking.
//    The client never self-reports a `priority_context_snapshot`.
//  - GoalInput local validation enforces: 1..3 distinct issue_ids, unique
//    consecutive priority_rank 1..N, all drawn from current normal_candidates.
//    These mirror the server-side InvalidGoal (400) structural checks so we
//    fail fast without burning an idempotency key.
import 'posture_profile.dart';

class NormalCandidate {
  final String issueId;
  final String issueName;
  final int suggestedRank;
  final PostureSeverity? severity;
  final List<String> reasons;
  final String? relationType;
  final double? associationWeight;

  NormalCandidate({
    required this.issueId,
    required this.issueName,
    required this.suggestedRank,
    required this.severity,
    required this.reasons,
    required this.relationType,
    required this.associationWeight,
  });

  factory NormalCandidate.fromJson(Map<String, dynamic> json) {
    final issueId = ((json['issue_id'] as String?) ?? '').trim();
    if (issueId.isEmpty) {
      throw const FormatException(
        'NormalCandidate: missing required `issue_id` field',
      );
    }
    final suggestedRank = json['suggested_rank'];
    if (suggestedRank is! int || suggestedRank < 1) {
      throw FormatException(
        'NormalCandidate: invalid `suggested_rank`: ${json['suggested_rank']}',
      );
    }
    final rawReasons = json['reasons'];
    if (rawReasons is! List) {
      throw const FormatException('NormalCandidate: `reasons` must be a list');
    }
    final associationWeight = (json['association_weight'] as num?)?.toDouble();
    return NormalCandidate(
      issueId: issueId,
      issueName: _requiredString(json, 'issue_name', 'NormalCandidate'),
      suggestedRank: suggestedRank,
      severity: parseNullablePostureSeverity(
        json['severity'],
        'NormalCandidate.severity',
      ),
      reasons: _strictStringList(rawReasons, 'NormalCandidate.reasons'),
      relationType: (json['relation_type'] as String?)?.trim().isEmpty ?? true
          ? null
          : (json['relation_type'] as String).trim(),
      associationWeight: associationWeight,
    );
  }
}

class RetestItem {
  final String issueId;
  final String issueName;
  final Certainty certainty;
  final String reason;

  RetestItem({
    required this.issueId,
    required this.issueName,
    required this.certainty,
    required this.reason,
  });

  factory RetestItem.fromJson(Map<String, dynamic> json) {
    final issueId = ((json['issue_id'] as String?) ?? '').trim();
    if (issueId.isEmpty) {
      throw const FormatException(
        'RetestItem: missing required `issue_id` field',
      );
    }
    final certainty = Certainty.tryParse(json['certainty']);
    if (certainty == null) {
      throw FormatException(
        'RetestItem: unknown certainty value: ${json['certainty']}',
      );
    }
    return RetestItem(
      issueId: issueId,
      issueName: _requiredString(json, 'issue_name', 'RetestItem'),
      certainty: certainty,
      reason: _requiredString(json, 'reason', 'RetestItem'),
    );
  }
}

class SafetyBlockedItem {
  final String issueId;
  final String issueName;
  final RiskTier riskTier;
  final String reason;
  final String nextAction;

  SafetyBlockedItem({
    required this.issueId,
    required this.issueName,
    required this.riskTier,
    required this.reason,
    required this.nextAction,
  });

  factory SafetyBlockedItem.fromJson(Map<String, dynamic> json) {
    final issueId = ((json['issue_id'] as String?) ?? '').trim();
    if (issueId.isEmpty) {
      throw const FormatException(
        'SafetyBlockedItem: missing required `issue_id` field',
      );
    }
    final riskTier = RiskTier.tryParse(json['risk_tier']);
    if (riskTier == null) {
      throw FormatException(
        'SafetyBlockedItem: unknown risk_tier value: ${json['risk_tier']}',
      );
    }
    return SafetyBlockedItem(
      issueId: issueId,
      issueName: _requiredString(json, 'issue_name', 'SafetyBlockedItem'),
      riskTier: riskTier,
      reason: _requiredString(json, 'reason', 'SafetyBlockedItem'),
      nextAction: _requiredString(json, 'next_action', 'SafetyBlockedItem'),
    );
  }
}

class PrioritySuggestions {
  final String suggestionId;
  final String profileVersion;
  final String ruleVersion;
  final String riskVersion;
  final DateTime generatedAt;
  final List<NormalCandidate> normalCandidates;
  final List<RetestItem> retestRequired;
  final List<SafetyBlockedItem> safetyBlocked;
  final String disclaimer;

  PrioritySuggestions({
    required this.suggestionId,
    required this.profileVersion,
    required this.ruleVersion,
    required this.riskVersion,
    required this.generatedAt,
    required this.normalCandidates,
    required this.retestRequired,
    required this.safetyBlocked,
    required this.disclaimer,
  });

  factory PrioritySuggestions.fromJson(Map<String, dynamic> json) {
    final suggestionId = ((json['suggestion_id'] as String?) ?? '').trim();
    if (suggestionId.isEmpty) {
      throw const FormatException(
        'PrioritySuggestions: missing required `suggestion_id` field',
      );
    }
    final profileVersion = ((json['profile_version'] as String?) ?? '').trim();
    if (profileVersion.isEmpty) {
      throw const FormatException(
        'PrioritySuggestions: missing required `profile_version` field',
      );
    }
    final ruleVersion = ((json['rule_version'] as String?) ?? '').trim();
    if (ruleVersion.isEmpty) {
      throw const FormatException(
        'PrioritySuggestions: missing required `rule_version` field',
      );
    }
    final riskVersion = ((json['risk_version'] as String?) ?? '').trim();
    if (riskVersion.isEmpty) {
      throw const FormatException(
        'PrioritySuggestions: missing required `risk_version` field',
      );
    }
    final generatedAtRaw = ((json['generated_at'] as String?) ?? '').trim();
    final generatedAt = generatedAtRaw.isEmpty
        ? null
        : DateTime.tryParse(generatedAtRaw);
    if (generatedAt == null) {
      throw FormatException(
        'PrioritySuggestions: missing/invalid `generated_at`: $generatedAtRaw',
      );
    }
    return PrioritySuggestions(
      suggestionId: suggestionId,
      profileVersion: profileVersion,
      ruleVersion: ruleVersion,
      riskVersion: riskVersion,
      generatedAt: generatedAt,
      normalCandidates: _parseList<NormalCandidate>(
        json['normal_candidates'],
        'normal_candidates',
        NormalCandidate.fromJson,
      ),
      retestRequired: _parseList<RetestItem>(
        json['retest_required'],
        'retest_required',
        RetestItem.fromJson,
      ),
      safetyBlocked: _parseList<SafetyBlockedItem>(
        json['safety_blocked'],
        'safety_blocked',
        SafetyBlockedItem.fromJson,
      ),
      disclaimer: _requiredString(json, 'disclaimer', 'PrioritySuggestions'),
    );
  }
}

/// One goal in a confirm request. Local pre-validation mirrors the server
/// InvalidGoal (400) structural checks (spec §10.7).
class GoalInput {
  final String issueId;
  final int priorityRank;

  GoalInput({required this.issueId, required this.priorityRank});

  Map<String, dynamic> toJson() => {
    'issue_id': issueId,
    'priority_rank': priorityRank,
  };
}

/// Result of a goal-input structural pre-check. The provider refuses to POST
/// (and burn an idempotency key) when the local checks already fail.
enum GoalValidationError {
  tooFew,
  tooMany,
  duplicateIssue,
  duplicateRank,
  rankNotConsecutive,
  issueNotInCandidates,
}

/// Locally validate a goal set against the current normal-candidate list
/// before issuing POST /posture/goals/confirm.
///
/// Rules (spec §9.2 / §10.7):
///  - 1..3 distinct issue_ids
///  - all issue_ids must be present in [candidateIssueIds]
///  - priority_rank values unique and exactly 1..N consecutive
GoalValidationError? validateGoals(
  List<GoalInput> goals,
  Set<String> candidateIssueIds,
) {
  if (goals.isEmpty) return GoalValidationError.tooFew;
  if (goals.length > 3) return GoalValidationError.tooMany;

  final issueIds = <String>{};
  for (final g in goals) {
    if (g.issueId.trim().isEmpty || !candidateIssueIds.contains(g.issueId)) {
      return GoalValidationError.issueNotInCandidates;
    }
    if (!issueIds.add(g.issueId)) {
      return GoalValidationError.duplicateIssue;
    }
  }

  final ranks = goals.map((g) => g.priorityRank).toList()..sort();
  if (ranks.toSet().length != ranks.length) {
    return GoalValidationError.duplicateRank;
  }
  for (var i = 0; i < ranks.length; i++) {
    if (ranks[i] != i + 1) {
      return GoalValidationError.rankNotConsecutive;
    }
  }
  return null;
}

class ConfirmedGoal {
  final String issueId;
  final int priorityRank;
  final DateTime confirmedAt;

  ConfirmedGoal({
    required this.issueId,
    required this.priorityRank,
    required this.confirmedAt,
  });

  factory ConfirmedGoal.fromJson(Map<String, dynamic> json) {
    final issueId = ((json['issue_id'] as String?) ?? '').trim();
    if (issueId.isEmpty) {
      throw const FormatException(
        'ConfirmedGoal: missing required `issue_id` field',
      );
    }
    final priorityRank = json['priority_rank'];
    if (priorityRank is! int || priorityRank < 1) {
      throw FormatException(
        'ConfirmedGoal: invalid `priority_rank`: ${json['priority_rank']}',
      );
    }
    final confirmedAtRaw = ((json['confirmed_at'] as String?) ?? '').trim();
    final confirmedAt = confirmedAtRaw.isEmpty
        ? null
        : DateTime.tryParse(confirmedAtRaw);
    if (confirmedAt == null) {
      throw FormatException(
        'ConfirmedGoal: missing/invalid `confirmed_at`: $confirmedAtRaw',
      );
    }
    return ConfirmedGoal(
      issueId: issueId,
      priorityRank: priorityRank,
      confirmedAt: confirmedAt,
    );
  }
}

class ConfirmedGoals {
  final List<ConfirmedGoal> confirmedGoals;
  final bool canGeneratePlan;
  final String riskVersion;

  ConfirmedGoals({
    required this.confirmedGoals,
    required this.canGeneratePlan,
    required this.riskVersion,
  });

  factory ConfirmedGoals.fromJson(Map<String, dynamic> json) {
    final canGeneratePlan = json['can_generate_plan'];
    if (canGeneratePlan is! bool) {
      throw const FormatException(
        'ConfirmedGoals: `can_generate_plan` must be a bool',
      );
    }
    return ConfirmedGoals(
      confirmedGoals: _parseList<ConfirmedGoal>(
        json['confirmed_goals'],
        'confirmed_goals',
        ConfirmedGoal.fromJson,
      ),
      canGeneratePlan: canGeneratePlan,
      riskVersion: _requiredString(json, 'risk_version', 'ConfirmedGoals'),
    );
  }
}

List<T> _parseList<T>(
  Object? raw,
  String fieldName,
  T Function(Map<String, dynamic>) fromJson,
) {
  if (raw is! List) {
    throw FormatException('PrioritySuggestion: `$fieldName` must be a list');
  }
  return raw
      .map((e) {
        if (e is! Map<String, dynamic>) {
          throw FormatException(
            'PrioritySuggestion: `$fieldName` entries must be objects',
          );
        }
        return fromJson(e);
      })
      .toList(growable: false);
}

String _requiredString(Map<String, dynamic> json, String key, String context) {
  final value = (json[key] as String?)?.trim();
  if (value == null || value.isEmpty) {
    throw FormatException('$context: missing required `$key` field');
  }
  return value;
}

List<String> _strictStringList(List<dynamic> raw, String context) {
  return raw
      .map((e) {
        if (e is! String || e.trim().isEmpty) {
          throw FormatException('$context must contain non-empty strings');
        }
        return e.trim();
      })
      .toList(growable: false);
}
