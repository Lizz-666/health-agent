// app/lib/models/safety_signal.dart
//
// Typed models for POST /posture/safety-signals (spec §9.2 / §10.8 / §12.2,
// backend SafetySignalRequest / SafetySignalResponse).
//
// Safety contract (Task 8B):
//  - The input serializes only the five signal fields. The provider adds the
//    sixth field, idempotency_key, at the request boundary. The backend uses
//    extra="forbid", so never add unrelated fields here.
//  - Unknown enum values MUST NOT be silently coerced; building the input
//    from an unknown value throws ArgumentError rather than emitting
//    `pain` / `head_neck` / `mild` by default.
import 'posture_profile.dart';

enum SignalType {
  pain,
  numbness,
  weakness,
  dizziness,
  acuteTrauma,
  other;

  String get wire {
    switch (this) {
      case SignalType.pain:
        return 'pain';
      case SignalType.numbness:
        return 'numbness';
      case SignalType.weakness:
        return 'weakness';
      case SignalType.dizziness:
        return 'dizziness';
      case SignalType.acuteTrauma:
        return 'acute_trauma';
      case SignalType.other:
        return 'other';
    }
  }

  static SignalType? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'pain':
        return SignalType.pain;
      case 'numbness':
        return SignalType.numbness;
      case 'weakness':
        return SignalType.weakness;
      case 'dizziness':
        return SignalType.dizziness;
      case 'acute_trauma':
        return SignalType.acuteTrauma;
      case 'other':
        return SignalType.other;
      default:
        return null;
    }
  }
}

enum BodyRegion {
  headNeck,
  cervical,
  upperBack,
  thoracic,
  lowerBack,
  shoulderThorax,
  pelvisSpine,
  lowerLimb,
  compound;

  String get wire {
    switch (this) {
      case BodyRegion.headNeck:
        return 'head_neck';
      case BodyRegion.cervical:
        return 'cervical';
      case BodyRegion.upperBack:
        return 'upper_back';
      case BodyRegion.thoracic:
        return 'thoracic';
      case BodyRegion.lowerBack:
        return 'lower_back';
      case BodyRegion.shoulderThorax:
        return 'shoulder_thorax';
      case BodyRegion.pelvisSpine:
        return 'pelvis_spine';
      case BodyRegion.lowerLimb:
        return 'lower_limb';
      case BodyRegion.compound:
        return 'compound';
    }
  }

  static BodyRegion? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'head_neck':
        return BodyRegion.headNeck;
      case 'cervical':
        return BodyRegion.cervical;
      case 'upper_back':
        return BodyRegion.upperBack;
      case 'thoracic':
        return BodyRegion.thoracic;
      case 'lower_back':
        return BodyRegion.lowerBack;
      case 'shoulder_thorax':
        return BodyRegion.shoulderThorax;
      case 'pelvis_spine':
        return BodyRegion.pelvisSpine;
      case 'lower_limb':
        return BodyRegion.lowerLimb;
      case 'compound':
        return BodyRegion.compound;
      default:
        return null;
    }
  }
}

enum SeverityHint {
  mild,
  moderate,
  severe;

  String get wire => name;

  static SeverityHint? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'mild':
        return SeverityHint.mild;
      case 'moderate':
        return SeverityHint.moderate;
      case 'severe':
        return SeverityHint.severe;
      default:
        return null;
    }
  }
}

/// Structured safety-signal input. The provider adds the idempotency key at
/// the request boundary so callers cannot accidentally reuse or fabricate it.
class SafetySignalInput {
  final SignalType signalType;
  final BodyRegion? bodyRegion;
  final String? relatedIssueId;
  final SeverityHint? severityHint;
  final DateTime? reportedAt;

  SafetySignalInput({
    required this.signalType,
    required this.bodyRegion,
    required this.relatedIssueId,
    required this.severityHint,
    required this.reportedAt,
  });

  /// Serialize to the exact 6-field request body expected by the backend
  /// signal fields. The provider appends `idempotency_key` once per action.
  Map<String, dynamic> toJson() {
    final body = <String, dynamic>{'signal_type': signalType.wire};
    if (bodyRegion != null) {
      body['body_region'] = bodyRegion!.wire;
    }
    if (relatedIssueId != null && relatedIssueId!.trim().isNotEmpty) {
      body['related_issue_id'] = relatedIssueId!.trim();
    }
    if (severityHint != null) {
      body['severity_hint'] = severityHint!.wire;
    }
    if (reportedAt != null) {
      body['reported_at'] = reportedAt!.toUtc().toIso8601String();
    }
    return body;
  }
}

class RiskClassification {
  final RiskTier riskTier;
  final String riskVersion;
  final String ruleId;
  final String reason;
  final List<Map<String, dynamic>> sources;

  RiskClassification({
    required this.riskTier,
    required this.riskVersion,
    required this.ruleId,
    required this.reason,
    required this.sources,
  });

  factory RiskClassification.fromJson(Map<String, dynamic> json) {
    final riskTier = RiskTier.tryParse(json['risk_tier']);
    if (riskTier == null) {
      throw FormatException(
        'RiskClassification: unknown risk_tier value: ${json['risk_tier']}',
      );
    }
    return RiskClassification(
      riskTier: riskTier,
      riskVersion: _requiredString(json, 'risk_version', 'RiskClassification'),
      ruleId: _requiredString(json, 'rule_id', 'RiskClassification'),
      reason: _requiredString(json, 'reason', 'RiskClassification'),
      sources: (json['sources'] as List? ?? [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList(growable: false),
    );
  }
}

enum SafetySignalStatus { recorded, deduplicated }

enum SafetySignalLifecycle { active, resolved }

class SafetySignalResult {
  final String signalId;
  final SafetySignalStatus status;
  final SafetySignalLifecycle lifecycle;
  final RiskTier riskTier;
  final String riskVersion;
  final DateTime invalidatesUntil;
  final RiskClassification classification;

  SafetySignalResult({
    required this.signalId,
    required this.status,
    required this.lifecycle,
    required this.riskTier,
    required this.riskVersion,
    required this.invalidatesUntil,
    required this.classification,
  });

  factory SafetySignalResult.fromJson(Map<String, dynamic> json) {
    final signalId = ((json['signal_id'] as String?) ?? '').trim();
    if (signalId.isEmpty) {
      throw const FormatException(
        'SafetySignalResult: missing required `signal_id` field',
      );
    }
    final riskTier = RiskTier.tryParse(json['risk_tier']);
    if (riskTier == null) {
      throw FormatException(
        'SafetySignalResult: unknown risk_tier value: ${json['risk_tier']}',
      );
    }
    final invalidatesRaw = ((json['invalidates_until'] as String?) ?? '')
        .trim();
    final invalidatesUntil = invalidatesRaw.isEmpty
        ? null
        : DateTime.tryParse(invalidatesRaw);
    if (invalidatesUntil == null) {
      throw FormatException(
        'SafetySignalResult: missing/invalid `invalidates_until`: $invalidatesRaw',
      );
    }
    final rawClassification = json['classification'];
    if (rawClassification is! Map<String, dynamic>) {
      throw const FormatException(
        'SafetySignalResult: missing required `classification` object',
      );
    }
    final status = switch (json['status']) {
      'recorded' => SafetySignalStatus.recorded,
      'deduplicated' => SafetySignalStatus.deduplicated,
      _ => throw FormatException(
        'SafetySignalResult: unknown status value: ${json['status']}',
      ),
    };
    final lifecycle = switch (json['lifecycle']) {
      'active' => SafetySignalLifecycle.active,
      'resolved' => SafetySignalLifecycle.resolved,
      _ => throw FormatException(
        'SafetySignalResult: unknown lifecycle value: ${json['lifecycle']}',
      ),
    };
    final riskVersion = _requiredString(
      json,
      'risk_version',
      'SafetySignalResult',
    );
    final classification = RiskClassification.fromJson(rawClassification);
    if (classification.riskTier != riskTier ||
        classification.riskVersion != riskVersion) {
      throw const FormatException(
        'SafetySignalResult: classification does not match top-level risk',
      );
    }
    return SafetySignalResult(
      signalId: signalId,
      status: status,
      lifecycle: lifecycle,
      riskTier: riskTier,
      riskVersion: riskVersion,
      invalidatesUntil: invalidatesUntil,
      classification: classification,
    );
  }
}

String _requiredString(Map<String, dynamic> json, String key, String context) {
  final value = (json[key] as String?)?.trim();
  if (value == null || value.isEmpty) {
    throw FormatException('$context: missing required `$key` field');
  }
  return value;
}
