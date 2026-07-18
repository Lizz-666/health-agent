// app/lib/models/assessment.dart
//
// Strict parsing for posture assessment history and self-assess results.
//
// Safety contract (Task 8B, spec §7 / §9.1):
//  - Required fields (id, issue_id, issue_name, result, created_at) must be
//    present and well-formed. Missing or blank values surface as a
//    FormatException so the provider can mark the request as a parse error
//    rather than silently fabricating "now" / empty strings / normal values.
//  - `source` is the canonical provenance field added by Task 8A
//    (GET /posture/history). `method` is kept as a back-compat alias:
//    legacy consumers (history_screen, posture_state_provider) read `.method`
//    and keep working unchanged. When only one of `source`/`method` is
//    present the other mirrors it; they are always consistent.
class AssessmentRecord {
  final String id;
  final String issueId;
  final String issueName;
  final String source;
  final String method;
  final String result;
  final DateTime createdAt;

  AssessmentRecord({
    required this.id,
    required this.issueId,
    required this.issueName,
    required this.source,
    required this.method,
    required this.result,
    required this.createdAt,
  });

  factory AssessmentRecord.fromJson(Map<String, dynamic> json) {
    final id = _readNonEmpty(json, 'id');
    final issueId = _readNonEmpty(json, 'issue_id');
    final issueName = _readNonEmpty(json, 'issue_name');
    final result = _readPostureResult(json, 'result');

    // Prefer the canonical `source` field (Task 8A), fall back to legacy
    // `method` for older payloads. Both must always resolve to the same
    // value when only one is provided.
    final sourceRaw = (json['source'] as String?)?.trim() ?? '';
    final methodRaw = (json['method'] as String?)?.trim() ?? '';
    final source = sourceRaw.isNotEmpty ? sourceRaw : methodRaw;
    if (source.isEmpty) {
      throw const FormatException(
        'AssessmentRecord: missing required `source`/`method` field',
      );
    }
    if (sourceRaw.isNotEmpty &&
        methodRaw.isNotEmpty &&
        sourceRaw != methodRaw) {
      throw const FormatException(
        'AssessmentRecord: `source` and `method` aliases disagree',
      );
    }

    final createdAtRaw = (json['created_at'] as String?)?.trim() ?? '';
    if (createdAtRaw.isEmpty) {
      throw const FormatException(
        'AssessmentRecord: missing required `created_at` field',
      );
    }
    final createdAt = DateTime.tryParse(createdAtRaw);
    if (createdAt == null) {
      throw FormatException(
        'AssessmentRecord: unparseable `created_at` value: $createdAtRaw',
      );
    }

    return AssessmentRecord(
      id: id,
      issueId: issueId,
      issueName: issueName,
      source: source,
      method: source,
      result: result,
      createdAt: createdAt,
    );
  }
}

class SelfAssessResult {
  final String id;
  final String issueId;
  final String result;
  final String suggestion;

  SelfAssessResult({
    required this.id,
    required this.issueId,
    required this.result,
    required this.suggestion,
  });

  factory SelfAssessResult.fromJson(Map<String, dynamic> json) {
    return SelfAssessResult(
      id: _readNonEmpty(json, 'id'),
      issueId: _readNonEmpty(json, 'issue_id'),
      result: _readPostureResult(json, 'result'),
      // Backend always returns suggestion (may be empty string for some
      // severities, which is a valid value, not a missing field).
      suggestion: ((json['suggestion'] as String?) ?? '').trim(),
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'issue_id': issueId,
    'result': result,
    'suggestion': suggestion,
  };
}

String _readNonEmpty(Map<String, dynamic> json, String key) {
  final value = (json[key] as String?)?.trim();
  if (value == null || value.isEmpty) {
    throw FormatException('AssessmentRecord: missing required `$key` field');
  }
  return value;
}

String _readPostureResult(Map<String, dynamic> json, String key) {
  final result = _readNonEmpty(json, key);
  if (!const {'normal', 'mild', 'moderate', 'severe'}.contains(result)) {
    throw FormatException('AssessmentRecord: unknown `$key` value: $result');
  }
  return result;
}
