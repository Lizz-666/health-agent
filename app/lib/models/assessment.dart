// app/lib/models/assessment.dart
class AssessmentRecord {
  final String id;
  final String issueId;
  final String issueName;
  final String method;
  final String result;
  final DateTime createdAt;

  AssessmentRecord({
    required this.id,
    required this.issueId,
    required this.issueName,
    required this.method,
    required this.result,
    required this.createdAt,
  });

  factory AssessmentRecord.fromJson(Map<String, dynamic> json) =>
      AssessmentRecord(
        id: (json['id'] as String?) ?? '',
        issueId: (json['issue_id'] as String?) ?? '',
        issueName: (json['issue_name'] as String?) ?? '',
        method: (json['method'] as String?) ?? '',
        result: (json['result'] as String?) ?? '',
        createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
      );
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

  factory SelfAssessResult.fromJson(Map<String, dynamic> json) =>
      SelfAssessResult(
        id: (json['id'] as String?) ?? '',
        issueId: (json['issue_id'] as String?) ?? '',
        result: (json['result'] as String?) ?? '',
        suggestion: (json['suggestion'] as String?) ?? '',
      );
}
