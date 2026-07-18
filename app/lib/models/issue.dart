// app/lib/models/issue.dart
class IssueSummary {
  final String id;
  final String nameCn;
  final String category;
  final List<String> aliases;
  final String definition;

  IssueSummary({
    required this.id,
    required this.nameCn,
    required this.category,
    required this.aliases,
    required this.definition,
  });

  factory IssueSummary.fromJson(Map<String, dynamic> json) => IssueSummary(
    id: (json['id'] as String?) ?? '',
    nameCn: (json['name_cn'] as String?) ?? '',
    category: (json['category'] as String?) ?? '',
    aliases: List<String>.from(json['aliases'] as List? ?? []),
    definition: (json['definition'] as String?) ?? '',
  );
}

class IssueDetail {
  final String id;
  final String nameCn;
  final String nameEn;
  final String category;
  final List<String> aliases;
  final String definition;
  final List<String> severityLevels;
  final List<Map<String, dynamic>> causes;
  final List<SelfTest> selfTests;
  final List<Map<String, dynamic>> corrections;
  final List<Map<String, dynamic>> consequences;
  final List<String> redFlags;
  final List<RelatedIssueRef> relatedIssues;

  IssueDetail({
    required this.id,
    required this.nameCn,
    required this.nameEn,
    required this.category,
    required this.aliases,
    required this.definition,
    required this.severityLevels,
    required this.causes,
    required this.selfTests,
    required this.corrections,
    required this.consequences,
    required this.redFlags,
    required this.relatedIssues,
  });

  factory IssueDetail.fromJson(Map<String, dynamic> json) => IssueDetail(
    id: (json['id'] as String?) ?? '',
    nameCn: (json['name_cn'] as String?) ?? '',
    nameEn: (json['name_en'] as String?) ?? '',
    category: (json['category'] as String?) ?? '',
    aliases: List<String>.from(json['aliases'] as List? ?? []),
    definition: (json['definition'] as String?) ?? '',
    severityLevels: List<String>.from(json['severity_levels'] as List? ?? []),
    causes: List<Map<String, dynamic>>.from(json['causes'] as List? ?? []),
    selfTests: (json['self_tests'] as List? ?? [])
        .map((e) => SelfTest.fromJson(e as Map<String, dynamic>))
        .toList(),
    corrections: List<Map<String, dynamic>>.from(
      json['corrections'] as List? ?? [],
    ),
    consequences: List<Map<String, dynamic>>.from(
      json['consequences'] as List? ?? [],
    ),
    redFlags: List<String>.from(json['red_flags'] as List? ?? []),
    relatedIssues: (json['related_issues'] as List? ?? [])
        .map((e) => RelatedIssueRef.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

class SelfTest {
  final String name;
  final List<String> steps;
  final String positiveSign;
  final String imageKey;
  final String toolsNeeded;

  // Extended self-test fields mirrored from the backend SelfTestSchema
  // (spec §6.6 / §12.1). These are display-only on the client; legacy
  // knowledge entries ship without them and parse with empty defaults.
  final String preparation;
  final String correctPosture;
  final List<String> commonErrors;
  final List<String> stopConditions;
  final List<String> safetyNotes;
  final String? contentVersion;
  final Map<String, dynamic>? source;

  SelfTest({
    required this.name,
    required this.steps,
    required this.positiveSign,
    required this.imageKey,
    required this.toolsNeeded,
    this.preparation = '',
    this.correctPosture = '',
    this.commonErrors = const [],
    this.stopConditions = const [],
    this.safetyNotes = const [],
    this.contentVersion,
    this.source,
  });

  factory SelfTest.fromJson(Map<String, dynamic> json) {
    final contentVersion = (json['content_version'] as String?)?.trim();
    final preparation = (json['preparation'] as String?)?.trim() ?? '';
    final correctPosture = (json['correct_posture'] as String?)?.trim() ?? '';
    final commonErrors = List<String>.from(
      json['common_errors'] as List? ?? [],
    ).map((e) => e.trim()).toList(growable: false);
    final stopConditions = List<String>.from(
      json['stop_conditions'] as List? ?? [],
    ).map((e) => e.trim()).toList(growable: false);
    final safetyNotes = List<String>.from(
      json['safety_notes'] as List? ?? [],
    ).map((e) => e.trim()).toList(growable: false);
    final source = json['source'] == null
        ? null
        : Map<String, dynamic>.from(json['source'] as Map);
    final extended =
        preparation.isNotEmpty ||
        correctPosture.isNotEmpty ||
        commonErrors.isNotEmpty ||
        stopConditions.isNotEmpty ||
        (contentVersion?.isNotEmpty ?? false) ||
        source != null;
    if (extended &&
        (preparation.isEmpty ||
            correctPosture.isEmpty ||
            !commonErrors.any((e) => e.isNotEmpty) ||
            !stopConditions.any((e) => e.isNotEmpty) ||
            contentVersion == null ||
            contentVersion.isEmpty ||
            source == null)) {
      throw const FormatException(
        'SelfTest: extended content is missing required safety fields',
      );
    }
    return SelfTest(
      name: (json['name'] as String?) ?? '',
      steps: List<String>.from(json['steps'] as List? ?? []),
      positiveSign: (json['positive_sign'] as String?) ?? '',
      imageKey: (json['image_key'] as String?) ?? '',
      toolsNeeded: (json['tools_needed'] as String?) ?? '',
      preparation: preparation,
      correctPosture: correctPosture,
      commonErrors: commonErrors,
      stopConditions: stopConditions,
      safetyNotes: safetyNotes,
      contentVersion: (contentVersion == null || contentVersion.isEmpty)
          ? null
          : contentVersion,
      source: source,
    );
  }
}

class RelatedIssueRef {
  final String id;
  final double weight;
  final String relation;

  RelatedIssueRef({
    required this.id,
    required this.weight,
    required this.relation,
  });

  factory RelatedIssueRef.fromJson(Map<String, dynamic> json) =>
      RelatedIssueRef(
        id: (json['id'] as String?) ?? '',
        weight: (json['weight'] as num?)?.toDouble() ?? 0.0,
        relation: (json['relation'] as String?) ?? '',
      );
}
