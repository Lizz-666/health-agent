// app/test/models/posture_profile_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/models/posture_profile.dart';

final _confirmedEntry = <String, dynamic>{
  'issue_id': 'HN-01',
  'issue_name': '头部前倾',
  'category': 'head_neck',
  'combined_severity': 'moderate',
  'certainty': 'confirmed',
  'has_conflict': false,
  'sources': [
    {
      'source': 'self_test',
      'event_id': 'evt-1',
      'severity': 'moderate',
      'created_at': '2026-07-11T10:00:00Z',
    },
  ],
  'risk_tier': 'normal',
  'risk_version': 'phase1-initial-v1',
  'updated_at': '2026-07-11T10:05:00Z',
};

final _conflictEntry = <String, dynamic>{
  'issue_id': 'ST-04',
  'issue_name': '圆肩',
  'category': 'shoulder_thorax',
  'combined_severity': null,
  'certainty': 'conflict',
  'has_conflict': true,
  'sources': [
    {
      'source': 'self_test',
      'event_id': 'evt-2',
      'severity': 'moderate',
      'created_at': '2026-07-11T10:00:00Z',
    },
    {
      'source': 'ai_photo',
      'event_id': 'evt-3',
      'severity': 'severe',
      'created_at': '2026-07-11T10:01:00Z',
    },
  ],
  'risk_tier': 'normal',
  'risk_version': 'phase1-initial-v1',
  'updated_at': '2026-07-11T10:05:00Z',
};

final _provisionalEntry = <String, dynamic>{
  'issue_id': 'PS-13',
  'issue_name': '骨盆前倾',
  'category': 'pelvis_spine',
  'combined_severity': null,
  'certainty': 'provisional',
  'has_conflict': false,
  'sources': [
    {
      'source': 'self_test',
      'event_id': 'evt-4',
      'severity': null,
      'created_at': '2026-07-11T10:00:00Z',
    },
  ],
  'risk_tier': 'normal',
  'risk_version': 'phase1-initial-v1',
  'updated_at': '2026-07-11T10:05:00Z',
};

Map<String, dynamic> _profile(List<Map<String, dynamic>> entries) => {
  'user_id': 'user-1',
  'evaluated_issues': entries,
  'unevaluated_categories': const ['compound', 'lower_limb'],
  'summary': {
    'total_evaluated': entries.length,
    'total_conflict': entries.where((e) => e['certainty'] == 'conflict').length,
    'total_provisional': entries
        .where((e) => e['certainty'] == 'provisional')
        .length,
  },
};

void main() {
  group('enum parsers', () {
    test('PostureSeverity.tryParse never coerces unknown to normal', () {
      expect(PostureSeverity.tryParse('moderate'), PostureSeverity.moderate);
      expect(PostureSeverity.tryParse('normal'), PostureSeverity.normal);
      expect(PostureSeverity.tryParse('unknown'), isNull);
      expect(PostureSeverity.tryParse(null), isNull);
      expect(PostureSeverity.tryParse(''), isNull);
    });

    test('Certainty.tryParse never coerces unknown to confirmed', () {
      expect(Certainty.tryParse('conflict'), Certainty.conflict);
      expect(Certainty.tryParse('provisional'), Certainty.provisional);
      expect(Certainty.tryParse('resolved'), isNull);
    });

    test('RiskTier.tryParse never coerces unknown to normal', () {
      expect(RiskTier.tryParse('restricted'), RiskTier.restricted);
      expect(RiskTier.tryParse('red_flag'), RiskTier.redFlag);
      expect(RiskTier.tryParse('cautious'), RiskTier.cautious);
      expect(RiskTier.tryParse('critical'), isNull);
    });
  });

  group('PostureProfileEntry.fromJson', () {
    test('parses a confirmed entry with non-null combined_severity', () {
      final e = PostureProfileEntry.fromJson(Map.from(_confirmedEntry));
      expect(e.issueId, 'HN-01');
      expect(e.combinedSeverity, PostureSeverity.moderate);
      expect(e.certainty, Certainty.confirmed);
      expect(e.hasConflict, isFalse);
      expect(e.riskTier, RiskTier.normal);
      expect(e.sources.length, 1);
      expect(e.sources.first.source, 'self_test');
      expect(e.sources.first.severity, PostureSeverity.moderate);
    });

    test('keeps combined_severity null for conflict (no auto-merge)', () {
      final e = PostureProfileEntry.fromJson(Map.from(_conflictEntry));
      expect(e.certainty, Certainty.conflict);
      expect(e.hasConflict, isTrue);
      expect(e.combinedSeverity, isNull);
      expect(e.sources.length, 2);
    });

    test('keeps combined_severity null for provisional', () {
      final e = PostureProfileEntry.fromJson(Map.from(_provisionalEntry));
      expect(e.certainty, Certainty.provisional);
      expect(e.combinedSeverity, isNull);
      expect(e.sources.first.severity, isNull);
    });

    test('throws on unknown certainty (no normal downgrade)', () {
      final bad = Map<String, dynamic>.from(_confirmedEntry)
        ..['certainty'] = 'resolved';
      expect(
        () => PostureProfileEntry.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws on unknown risk_tier (no normal downgrade)', () {
      final bad = Map<String, dynamic>.from(_confirmedEntry)
        ..['risk_tier'] = 'critical';
      expect(
        () => PostureProfileEntry.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws on unknown non-null combined_severity', () {
      final bad = Map<String, dynamic>.from(_confirmedEntry)
        ..['combined_severity'] = 'critical';
      expect(
        () => PostureProfileEntry.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws when confirmed entry has no combined severity', () {
      final bad = Map<String, dynamic>.from(_confirmedEntry)
        ..['combined_severity'] = null;
      expect(
        () => PostureProfileEntry.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws when conflict flag disagrees with certainty', () {
      final bad = Map<String, dynamic>.from(_conflictEntry)
        ..['has_conflict'] = false;
      expect(
        () => PostureProfileEntry.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws on missing issue_id', () {
      final bad = Map<String, dynamic>.from(_confirmedEntry)
        ..remove('issue_id');
      expect(
        () => PostureProfileEntry.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws on missing updated_at', () {
      final bad = Map<String, dynamic>.from(_confirmedEntry)
        ..remove('updated_at');
      expect(
        () => PostureProfileEntry.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws on missing sources list', () {
      final bad = Map<String, dynamic>.from(_confirmedEntry)..remove('sources');
      expect(
        () => PostureProfileEntry.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws on ProfileSource with empty source string', () {
      final bad = Map<String, dynamic>.from(_confirmedEntry)
        ..['sources'] = [
          {
            'source': '',
            'event_id': 'evt-1',
            'severity': 'moderate',
            'created_at': '2026-07-11T10:00:00Z',
          },
        ];
      expect(
        () => PostureProfileEntry.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('keeps severity null when source severity is null', () {
      final e = PostureProfileEntry.fromJson(Map.from(_provisionalEntry));
      expect(e.sources.first.severity, isNull);
    });
  });

  group('PostureProfile.fromJson', () {
    test('parses a multi-entry profile', () {
      final p = PostureProfile.fromJson(
        _profile([_confirmedEntry, _conflictEntry, _provisionalEntry]),
      );
      expect(p.userId, 'user-1');
      expect(p.evaluatedIssues.length, 3);
      expect(p.unevaluatedCategories, ['compound', 'lower_limb']);
      expect(p.summary.totalEvaluated, 3);
      expect(p.summary.totalConflict, 1);
      expect(p.summary.totalProvisional, 1);
    });

    test('a valid empty profile is not an error (empty != parseError)', () {
      final p = PostureProfile.fromJson(_profile([]));
      expect(p.evaluatedIssues, isEmpty);
      expect(p.summary.totalEvaluated, 0);
      expect(p.summary.totalConflict, 0);
      expect(p.summary.totalProvisional, 0);
    });

    test('throws on missing user_id', () {
      final bad = _profile([])..remove('user_id');
      expect(
        () => PostureProfile.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws when evaluated_issues is not a list', () {
      final bad = _profile([])..['evaluated_issues'] = <String, dynamic>{};
      expect(
        () => PostureProfile.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws when summary is missing', () {
      final bad = _profile([])..remove('summary');
      expect(
        () => PostureProfile.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws when summary counts disagree with entries', () {
      final bad = _profile([_confirmedEntry]);
      (bad['summary'] as Map<String, dynamic>)['total_evaluated'] = 0;
      expect(
        () => PostureProfile.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });
  });
}
