// app/lib/models/posture_profile.dart
//
// Typed models for GET /posture/profile and GET /posture/profile/{issue_id}
// (spec §9.2 / §10.5, backend PostureProfileResponse /
// PostureProfileEntryResponse).
//
// Safety contract (Task 8B):
//  - Unknown `certainty` or `risk_tier` enum values MUST NOT be coerced to a
//    safe default like `normal`. They surface as FormatException so the
//    provider can mark the response as a parse error.
//  - `combined_severity` is always nullable. `conflict` and `provisional`
//    entries keep it null; consumers must never substitute a default.
//  - Missing required scalars throw; the provider never silently renders a
//    half-formed entry.

enum PostureSeverity {
  normal,
  mild,
  moderate,
  severe;

  static PostureSeverity? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'normal':
        return PostureSeverity.normal;
      case 'mild':
        return PostureSeverity.mild;
      case 'moderate':
        return PostureSeverity.moderate;
      case 'severe':
        return PostureSeverity.severe;
      default:
        return null;
    }
  }
}

PostureSeverity? parseNullablePostureSeverity(Object? raw, String fieldName) {
  if (raw == null) return null;
  final severity = PostureSeverity.tryParse(raw);
  if (severity == null) {
    throw FormatException('Unknown `$fieldName` value: $raw');
  }
  return severity;
}

enum Certainty {
  confirmed,
  provisional,
  conflict;

  static Certainty? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'confirmed':
        return Certainty.confirmed;
      case 'provisional':
        return Certainty.provisional;
      case 'conflict':
        return Certainty.conflict;
      default:
        return null;
    }
  }
}

enum RiskTier {
  normal,
  cautious,
  restricted,
  redFlag;

  static RiskTier? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'normal':
        return RiskTier.normal;
      case 'cautious':
        return RiskTier.cautious;
      case 'restricted':
        return RiskTier.restricted;
      case 'red_flag':
        return RiskTier.redFlag;
      default:
        return null;
    }
  }
}

/// One contributing assessment source for a profile entry (backend
/// `ProfileSource`). Privacy: only carries `source` / `event_id` / `severity`
/// / `created_at`; never photo_keys, photo URLs or raw ai_response.
class ProfileSource {
  final String source;
  final String eventId;
  final PostureSeverity? severity;
  final DateTime createdAt;

  ProfileSource({
    required this.source,
    required this.eventId,
    required this.severity,
    required this.createdAt,
  });

  factory ProfileSource.fromJson(Map<String, dynamic> json) {
    final source = ((json['source'] as String?) ?? '').trim();
    if (source.isEmpty) {
      throw const FormatException(
        'ProfileSource: missing required `source` field',
      );
    }
    final eventId = ((json['event_id'] as String?) ?? '').trim();
    if (eventId.isEmpty) {
      throw const FormatException(
        'ProfileSource: missing required `event_id` field',
      );
    }
    final createdAtRaw = ((json['created_at'] as String?) ?? '').trim();
    if (createdAtRaw.isEmpty) {
      throw const FormatException(
        'ProfileSource: missing required `created_at` field',
      );
    }
    final createdAt = DateTime.tryParse(createdAtRaw);
    if (createdAt == null) {
      throw FormatException(
        'ProfileSource: unparseable `created_at`: $createdAtRaw',
      );
    }
    return ProfileSource(
      source: source,
      eventId: eventId,
      severity: parseNullablePostureSeverity(
        json['severity'],
        'ProfileSource.severity',
      ),
      createdAt: createdAt,
    );
  }
}

/// A single evaluated issue in the profile. Returned by both GET /profile
/// (list item) and GET /profile/{issue_id} (single entry detail, same shape).
class PostureProfileEntry {
  final String issueId;
  final String issueName;
  final String category;
  final PostureSeverity? combinedSeverity;
  final Certainty certainty;
  final bool hasConflict;
  final List<ProfileSource> sources;
  final RiskTier riskTier;
  final String riskVersion;
  final DateTime updatedAt;

  PostureProfileEntry({
    required this.issueId,
    required this.issueName,
    required this.category,
    required this.combinedSeverity,
    required this.certainty,
    required this.hasConflict,
    required this.sources,
    required this.riskTier,
    required this.riskVersion,
    required this.updatedAt,
  });

  factory PostureProfileEntry.fromJson(Map<String, dynamic> json) {
    final issueId = ((json['issue_id'] as String?) ?? '').trim();
    if (issueId.isEmpty) {
      throw const FormatException(
        'PostureProfileEntry: missing required `issue_id` field',
      );
    }
    final certainty = Certainty.tryParse(json['certainty']);
    if (certainty == null) {
      throw FormatException(
        'PostureProfileEntry: unknown certainty value: ${json['certainty']}',
      );
    }
    final riskTier = RiskTier.tryParse(json['risk_tier']);
    if (riskTier == null) {
      throw FormatException(
        'PostureProfileEntry: unknown risk_tier value: ${json['risk_tier']}',
      );
    }
    final updatedAtRaw = ((json['updated_at'] as String?) ?? '').trim();
    if (updatedAtRaw.isEmpty) {
      throw const FormatException(
        'PostureProfileEntry: missing required `updated_at` field',
      );
    }
    final updatedAt = DateTime.tryParse(updatedAtRaw);
    if (updatedAt == null) {
      throw FormatException(
        'PostureProfileEntry: unparseable `updated_at`: $updatedAtRaw',
      );
    }
    final rawSources = json['sources'];
    if (rawSources is! List) {
      throw const FormatException(
        'PostureProfileEntry: `sources` must be a list',
      );
    }
    final sources = rawSources
        .map(
          (e) => ProfileSource.fromJson(
            _readJsonObject(e, 'PostureProfileEntry.sources'),
          ),
        )
        .toList(growable: false);
    if (sources.isEmpty) {
      throw const FormatException(
        'PostureProfileEntry: `sources` must not be empty',
      );
    }

    final issueName = _readRequiredString(
      json,
      'issue_name',
      'PostureProfileEntry',
    );
    final category = _readRequiredString(
      json,
      'category',
      'PostureProfileEntry',
    );
    final riskVersion = _readRequiredString(
      json,
      'risk_version',
      'PostureProfileEntry',
    );
    final hasConflictRaw = json['has_conflict'];
    if (hasConflictRaw is! bool) {
      throw const FormatException(
        'PostureProfileEntry: `has_conflict` must be a bool',
      );
    }
    final combinedSeverity = parseNullablePostureSeverity(
      json['combined_severity'],
      'PostureProfileEntry.combined_severity',
    );
    if ((certainty == Certainty.conflict) != hasConflictRaw) {
      throw const FormatException(
        'PostureProfileEntry: certainty/has_conflict mismatch',
      );
    }
    if (certainty != Certainty.confirmed && combinedSeverity != null) {
      throw const FormatException(
        'PostureProfileEntry: non-confirmed entry cannot have combined severity',
      );
    }
    if (certainty == Certainty.confirmed && combinedSeverity == null) {
      throw const FormatException(
        'PostureProfileEntry: confirmed entry requires combined severity',
      );
    }

    return PostureProfileEntry(
      issueId: issueId,
      issueName: issueName,
      category: category,
      // combined_severity is always nullable; conflict/provisional keep null.
      combinedSeverity: combinedSeverity,
      certainty: certainty,
      hasConflict: hasConflictRaw,
      sources: sources,
      riskTier: riskTier,
      riskVersion: riskVersion,
      updatedAt: updatedAt,
    );
  }
}

class PostureProfileSummary {
  final int totalEvaluated;
  final int totalConflict;
  final int totalProvisional;

  PostureProfileSummary({
    required this.totalEvaluated,
    required this.totalConflict,
    required this.totalProvisional,
  });

  factory PostureProfileSummary.fromJson(Map<String, dynamic> json) {
    return PostureProfileSummary(
      totalEvaluated: _readNonNegativeInt(
        json,
        'total_evaluated',
        'PostureProfileSummary',
      ),
      totalConflict: _readNonNegativeInt(
        json,
        'total_conflict',
        'PostureProfileSummary',
      ),
      totalProvisional: _readNonNegativeInt(
        json,
        'total_provisional',
        'PostureProfileSummary',
      ),
    );
  }
}

class PostureProfile {
  final String userId;
  final List<PostureProfileEntry> evaluatedIssues;
  final List<String> unevaluatedCategories;
  final PostureProfileSummary summary;

  PostureProfile({
    required this.userId,
    required this.evaluatedIssues,
    required this.unevaluatedCategories,
    required this.summary,
  });

  factory PostureProfile.fromJson(Map<String, dynamic> json) {
    final userId = ((json['user_id'] as String?) ?? '').trim();
    if (userId.isEmpty) {
      throw const FormatException(
        'PostureProfile: missing required `user_id` field',
      );
    }
    final rawEntries = json['evaluated_issues'];
    if (rawEntries is! List) {
      throw const FormatException(
        'PostureProfile: `evaluated_issues` must be a list',
      );
    }
    final evaluatedIssues = rawEntries
        .map(
          (e) => PostureProfileEntry.fromJson(
            _readJsonObject(e, 'PostureProfile.evaluated_issues'),
          ),
        )
        .toList(growable: false);
    final rawUnevaluated = json['unevaluated_categories'];
    if (rawUnevaluated is! List) {
      throw const FormatException(
        'PostureProfile: `unevaluated_categories` must be a list',
      );
    }
    final unevaluatedCategories = rawUnevaluated
        .map((e) {
          if (e is! String || e.trim().isEmpty) {
            throw const FormatException(
              'PostureProfile: unevaluated category must be a non-empty string',
            );
          }
          return e.trim();
        })
        .toList(growable: false);
    final rawSummary = json['summary'];
    if (rawSummary is! Map<String, dynamic>) {
      throw const FormatException(
        'PostureProfile: missing required `summary` object',
      );
    }
    final summary = PostureProfileSummary.fromJson(rawSummary);
    if (summary.totalEvaluated != evaluatedIssues.length ||
        summary.totalConflict !=
            evaluatedIssues
                .where((e) => e.certainty == Certainty.conflict)
                .length ||
        summary.totalProvisional !=
            evaluatedIssues
                .where((e) => e.certainty == Certainty.provisional)
                .length) {
      throw const FormatException(
        'PostureProfile: summary does not match evaluated entries',
      );
    }
    return PostureProfile(
      userId: userId,
      evaluatedIssues: evaluatedIssues,
      unevaluatedCategories: unevaluatedCategories,
      summary: summary,
    );
  }
}

String _readRequiredString(
  Map<String, dynamic> json,
  String key,
  String context,
) {
  final value = (json[key] as String?)?.trim();
  if (value == null || value.isEmpty) {
    throw FormatException('$context: missing required `$key` field');
  }
  return value;
}

int _readNonNegativeInt(Map<String, dynamic> json, String key, String context) {
  final raw = json[key];
  if (raw is! int || raw < 0) {
    throw FormatException('$context: `$key` must be a non-negative integer');
  }
  return raw;
}

Map<String, dynamic> _readJsonObject(Object? raw, String context) {
  if (raw is! Map<String, dynamic>) {
    throw FormatException('$context must contain JSON objects');
  }
  return raw;
}
