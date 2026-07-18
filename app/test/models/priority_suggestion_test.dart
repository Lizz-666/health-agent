// app/test/models/priority_suggestion_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/models/posture_profile.dart';
import 'package:posture_app/models/priority_suggestion.dart';

final _suggestions = <String, dynamic>{
  'suggestion_id': 'sugg-1',
  'profile_version': 'pv-1',
  'rule_version': '2026-07-17-v1',
  'risk_version': '2026-07-16-v4',
  'generated_at': '2026-07-17T12:00:00Z',
  'normal_candidates': [
    {
      'issue_id': 'HN-01',
      'issue_name': '头部前倾',
      'suggested_rank': 1,
      'severity': 'moderate',
      'reasons': ['严重度为 moderate', '与已确认的圆肩强关联'],
      'relation_type': '共存(UCS)',
      'association_weight': 0.9,
    },
    {
      'issue_id': 'SS-01',
      'issue_name': '圆肩',
      'suggested_rank': 2,
      'reasons': ['严重度为 mild'],
    },
  ],
  'retest_required': [
    {
      'issue_id': 'ST-04',
      'issue_name': '上交叉',
      'certainty': 'conflict',
      'reason': '来源不一致，需重新评估',
    },
  ],
  'safety_blocked': [
    {
      'issue_id': 'SC-10',
      'issue_name': '颈椎问题',
      'risk_tier': 'restricted',
      'reason': '存在受限安全信号',
      'next_action': '建议寻求专业评估',
    },
  ],
  'disclaimer': '优先级属于建议，关联图谱仅用于排查参考。',
};

void main() {
  group('PrioritySuggestions.fromJson', () {
    final s = PrioritySuggestions.fromJson(Map.from(_suggestions));

    test('parses server control values', () {
      expect(s.suggestionId, 'sugg-1');
      expect(s.profileVersion, 'pv-1');
      expect(s.ruleVersion, '2026-07-17-v1');
      expect(s.riskVersion, '2026-07-16-v4');
      expect(s.generatedAt, DateTime.parse('2026-07-17T12:00:00Z'));
    });

    test('parses normal_candidates', () {
      expect(s.normalCandidates.length, 2);
      final first = s.normalCandidates.first;
      expect(first.issueId, 'HN-01');
      expect(first.suggestedRank, 1);
      expect(first.severity, PostureSeverity.moderate);
      expect(first.reasons.length, 2);
      expect(first.relationType, '共存(UCS)');
      expect(first.associationWeight, 0.9);
    });

    test('parses retest_required with strict certainty', () {
      expect(s.retestRequired.length, 1);
      expect(s.retestRequired.first.certainty, Certainty.conflict);
    });

    test('parses safety_blocked with restricted distinct from red_flag', () {
      expect(s.safetyBlocked.length, 1);
      expect(s.safetyBlocked.first.riskTier, RiskTier.restricted);
    });

    test('a valid empty three-bucket response parses (not an error)', () {
      final empty = Map<String, dynamic>.from(_suggestions)
        ..['normal_candidates'] = <Map<String, dynamic>>[]
        ..['retest_required'] = <Map<String, dynamic>>[]
        ..['safety_blocked'] = <Map<String, dynamic>>[];
      final parsed = PrioritySuggestions.fromJson(empty);
      expect(parsed.normalCandidates, isEmpty);
      expect(parsed.retestRequired, isEmpty);
      expect(parsed.safetyBlocked, isEmpty);
    });

    test('throws when suggestion_id missing', () {
      final bad = Map<String, dynamic>.from(_suggestions)
        ..remove('suggestion_id');
      expect(
        () => PrioritySuggestions.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws when profile_version missing', () {
      final bad = Map<String, dynamic>.from(_suggestions)
        ..remove('profile_version');
      expect(
        () => PrioritySuggestions.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws when generated_at missing', () {
      final bad = Map<String, dynamic>.from(_suggestions)
        ..remove('generated_at');
      expect(
        () => PrioritySuggestions.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('SafetyBlockedItem throws on unknown risk_tier', () {
      final bad = Map<String, dynamic>.from(_suggestions)
        ..['safety_blocked'] = [
          {
            'issue_id': 'SC-10',
            'issue_name': 'x',
            'risk_tier': 'critical', // unknown
            'reason': 'r',
            'next_action': 'a',
          },
        ];
      expect(
        () => PrioritySuggestions.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('SafetyBlockedItem keeps red_flag distinct from restricted', () {
      final withRed = Map<String, dynamic>.from(_suggestions)
        ..['safety_blocked'] = [
          {
            'issue_id': 'SC-99',
            'issue_name': 'x',
            'risk_tier': 'red_flag',
            'reason': 'r',
            'next_action': 'a',
          },
        ];
      final parsed = PrioritySuggestions.fromJson(withRed);
      expect(parsed.safetyBlocked.first.riskTier, RiskTier.redFlag);
    });

    test('RetestItem throws on unknown certainty', () {
      final bad = Map<String, dynamic>.from(_suggestions)
        ..['retest_required'] = [
          {
            'issue_id': 'ST-04',
            'issue_name': 'x',
            'certainty': 'resolved',
            'reason': 'r',
          },
        ];
      expect(
        () => PrioritySuggestions.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('NormalCandidate throws on rank < 1', () {
      final bad = Map<String, dynamic>.from(_suggestions)
        ..['normal_candidates'] = [
          {
            'issue_id': 'HN-01',
            'issue_name': 'x',
            'suggested_rank': 0,
            'reasons': ['r'],
          },
        ];
      expect(
        () => PrioritySuggestions.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('NormalCandidate rejects a fractional rank', () {
      final bad = Map<String, dynamic>.from(_suggestions)
        ..['normal_candidates'] = [
          {
            'issue_id': 'HN-01',
            'issue_name': 'x',
            'suggested_rank': 1.5,
            'reasons': ['r'],
          },
        ];
      expect(
        () => PrioritySuggestions.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('NormalCandidate rejects non-string reasons', () {
      final bad = Map<String, dynamic>.from(_suggestions)
        ..['normal_candidates'] = [
          {
            'issue_id': 'HN-01',
            'issue_name': 'x',
            'suggested_rank': 1,
            'reasons': [42],
          },
        ];
      expect(
        () => PrioritySuggestions.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('NormalCandidate throws on unknown non-null severity', () {
      final bad = Map<String, dynamic>.from(_suggestions)
        ..['normal_candidates'] = [
          {
            'issue_id': 'HN-01',
            'issue_name': 'x',
            'suggested_rank': 1,
            'severity': 'critical',
            'reasons': ['r'],
          },
        ];
      expect(
        () => PrioritySuggestions.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });
  });

  group('ConfirmedGoals.fromJson', () {
    test('parses a successful confirm response', () {
      final c = ConfirmedGoals.fromJson({
        'confirmed_goals': [
          {
            'issue_id': 'HN-01',
            'priority_rank': 1,
            'confirmed_at': '2026-07-17T12:30:00Z',
          },
        ],
        'can_generate_plan': true,
        'risk_version': '2026-07-16-v4',
      });
      expect(c.confirmedGoals.length, 1);
      expect(c.confirmedGoals.first.issueId, 'HN-01');
      expect(c.confirmedGoals.first.priorityRank, 1);
      expect(c.canGeneratePlan, isTrue);
      expect(c.riskVersion, '2026-07-16-v4');
    });

    test('throws on confirmed_goal missing issue_id', () {
      expect(
        () => ConfirmedGoals.fromJson({
          'confirmed_goals': [
            {'priority_rank': 1, 'confirmed_at': '2026-07-17T12:30:00Z'},
          ],
          'can_generate_plan': true,
          'risk_version': '2026-07-16-v4',
        }),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws on confirmed_goal with rank < 1', () {
      expect(
        () => ConfirmedGoals.fromJson({
          'confirmed_goals': [
            {
              'issue_id': 'HN-01',
              'priority_rank': 0,
              'confirmed_at': '2026-07-17T12:30:00Z',
            },
          ],
          'can_generate_plan': false,
          'risk_version': '2026-07-16-v4',
        }),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws when can_generate_plan is missing', () {
      expect(
        () => ConfirmedGoals.fromJson({
          'confirmed_goals': <Map<String, dynamic>>[],
          'risk_version': '2026-07-16-v4',
        }),
        throwsA(isA<FormatException>()),
      );
    });
  });

  group('validateGoals (local pre-check)', () {
    final candidates = <String>{'HN-01', 'SS-01', 'PS-13'};

    test('accepts 1 valid goal', () {
      expect(
        validateGoals([
          GoalInput(issueId: 'HN-01', priorityRank: 1),
        ], candidates),
        isNull,
      );
    });

    test('accepts 3 distinct issues with consecutive ranks 1..3', () {
      expect(
        validateGoals([
          GoalInput(issueId: 'HN-01', priorityRank: 1),
          GoalInput(issueId: 'SS-01', priorityRank: 2),
          GoalInput(issueId: 'PS-13', priorityRank: 3),
        ], candidates),
        isNull,
      );
    });

    test('rejects empty list', () {
      expect(validateGoals([], candidates), GoalValidationError.tooFew);
    });

    test('rejects >3 goals', () {
      expect(
        validateGoals([
          GoalInput(issueId: 'HN-01', priorityRank: 1),
          GoalInput(issueId: 'SS-01', priorityRank: 2),
          GoalInput(issueId: 'PS-13', priorityRank: 3),
          GoalInput(issueId: 'HN-01', priorityRank: 4),
        ], candidates),
        GoalValidationError.tooMany,
      );
    });

    test('rejects duplicate issue_id', () {
      expect(
        validateGoals([
          GoalInput(issueId: 'HN-01', priorityRank: 1),
          GoalInput(issueId: 'HN-01', priorityRank: 2),
        ], candidates),
        GoalValidationError.duplicateIssue,
      );
    });

    test('rejects duplicate rank', () {
      expect(
        validateGoals([
          GoalInput(issueId: 'HN-01', priorityRank: 1),
          GoalInput(issueId: 'SS-01', priorityRank: 1),
        ], candidates),
        GoalValidationError.duplicateRank,
      );
    });

    test('rejects non-consecutive ranks (1,3)', () {
      expect(
        validateGoals([
          GoalInput(issueId: 'HN-01', priorityRank: 1),
          GoalInput(issueId: 'SS-01', priorityRank: 3),
        ], candidates),
        GoalValidationError.rankNotConsecutive,
      );
    });

    test('rejects issue not in current candidates', () {
      expect(
        validateGoals([
          GoalInput(issueId: 'OUTSIDER', priorityRank: 1),
        ], candidates),
        GoalValidationError.issueNotInCandidates,
      );
    });

    test('GoalInput.toJson serializes the 2 expected fields only', () {
      final json = GoalInput(issueId: 'HN-01', priorityRank: 1).toJson();
      expect(json.keys.toSet(), {'issue_id', 'priority_rank'});
      expect(json['issue_id'], 'HN-01');
      expect(json['priority_rank'], 1);
    });
  });
}
