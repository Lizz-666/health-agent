// app/test/models/safety_signal_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/models/posture_profile.dart';
import 'package:posture_app/models/safety_signal.dart';

void main() {
  group('SafetySignalInput.toJson', () {
    test('emits exactly signal_type when all optionals null', () {
      final json = SafetySignalInput(
        signalType: SignalType.pain,
        bodyRegion: null,
        relatedIssueId: null,
        severityHint: null,
        reportedAt: null,
      ).toJson();
      expect(json.keys.toSet(), {'signal_type'});
      expect(json['signal_type'], 'pain');
    });

    test('emits all 5 signal fields when fully populated', () {
      final json = SafetySignalInput(
        signalType: SignalType.acuteTrauma,
        bodyRegion: BodyRegion.cervical,
        relatedIssueId: 'HN-01',
        severityHint: SeverityHint.severe,
        reportedAt: DateTime.utc(2026, 7, 11, 10, 0, 0),
      ).toJson();
      expect(json['signal_type'], 'acute_trauma');
      expect(json['body_region'], 'cervical');
      expect(json['related_issue_id'], 'HN-01');
      expect(json['severity_hint'], 'severe');
      expect(json['reported_at'], '2026-07-11T10:00:00.000Z');
    });

    test('omits related_issue_id when blank (server max_length=20)', () {
      final json = SafetySignalInput(
        signalType: SignalType.other,
        bodyRegion: null,
        relatedIssueId: '   ',
        severityHint: null,
        reportedAt: null,
      ).toJson();
      expect(json.containsKey('related_issue_id'), isFalse);
    });

    test('uses snake_case wire format for all enums', () {
      expect(SignalType.acuteTrauma.wire, 'acute_trauma');
      expect(BodyRegion.headNeck.wire, 'head_neck');
      expect(BodyRegion.shoulderThorax.wire, 'shoulder_thorax');
      expect(BodyRegion.pelvisSpine.wire, 'pelvis_spine');
      expect(BodyRegion.lowerLimb.wire, 'lower_limb');
      expect(SeverityHint.mild.wire, 'mild');
    });

    test('never leaks priority_context_snapshot or extra keys', () {
      final json = SafetySignalInput(
        signalType: SignalType.pain,
        bodyRegion: null,
        relatedIssueId: null,
        severityHint: null,
        reportedAt: null,
      ).toJson();
      expect(json.containsKey('idempotency_key'), isFalse);
      expect(json.containsKey('priority_context_snapshot'), isFalse);
      expect(json.containsKey('actor'), isFalse);
      expect(json.containsKey('user_id'), isFalse);
    });
  });

  group('enum tryParse (never coerces unknown to first value)', () {
    test('SignalType.tryParse rejects unknown', () {
      expect(SignalType.tryParse('burning'), isNull);
      expect(SignalType.tryParse('pain'), SignalType.pain);
      expect(SignalType.tryParse(null), isNull);
    });

    test('BodyRegion.tryParse rejects unknown', () {
      expect(BodyRegion.tryParse('throat'), isNull);
      expect(BodyRegion.tryParse('compound'), BodyRegion.compound);
    });

    test('SeverityHint.tryParse rejects unknown', () {
      expect(SeverityHint.tryParse('agonizing'), isNull);
      expect(SeverityHint.tryParse('moderate'), SeverityHint.moderate);
    });
  });

  group('SafetySignalResult.fromJson', () {
    final response = <String, dynamic>{
      'signal_id': 'sig-1',
      'status': 'recorded',
      'lifecycle': 'active',
      'risk_tier': 'cautious',
      'risk_version': '2026-07-16-v4',
      'invalidates_until': '2026-08-11T00:00:00Z',
      'classification': {
        'risk_tier': 'cautious',
        'risk_version': '2026-07-16-v4',
        'rule_id': 'RST-acute-trauma',
        'reason': '受限分类',
        'sources': [],
      },
    };

    test('parses a recorded active signal with cautious risk', () {
      final r = SafetySignalResult.fromJson(Map.from(response));
      expect(r.signalId, 'sig-1');
      expect(r.status, SafetySignalStatus.recorded);
      expect(r.lifecycle, SafetySignalLifecycle.active);
      expect(r.riskTier, RiskTier.cautious);
      expect(r.riskVersion, '2026-07-16-v4');
      expect(r.classification.ruleId, 'RST-acute-trauma');
    });

    test('parses restricted risk_tier (distinct from cautious)', () {
      final restricted = Map<String, dynamic>.from(response)
        ..['risk_tier'] = 'restricted'
        ..['classification'] = {
          ...response['classification'] as Map<String, dynamic>,
          'risk_tier': 'restricted',
        };
      final r = SafetySignalResult.fromJson(restricted);
      expect(r.riskTier, RiskTier.restricted);
    });

    test('parses red_flag risk_tier', () {
      final redFlag = Map<String, dynamic>.from(response)
        ..['risk_tier'] = 'red_flag'
        ..['classification'] = {
          ...response['classification'] as Map<String, dynamic>,
          'risk_tier': 'red_flag',
        };
      final r = SafetySignalResult.fromJson(redFlag);
      expect(r.riskTier, RiskTier.redFlag);
    });

    test('throws on unknown risk_tier', () {
      expect(
        () => SafetySignalResult.fromJson(
          Map.from(response)..['risk_tier'] = 'critical',
        ),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws on missing signal_id', () {
      final bad = Map<String, dynamic>.from(response)..remove('signal_id');
      expect(
        () => SafetySignalResult.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws on missing invalidates_until', () {
      final bad = Map<String, dynamic>.from(response)
        ..remove('invalidates_until');
      expect(
        () => SafetySignalResult.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws on missing classification object', () {
      final bad = Map<String, dynamic>.from(response)..remove('classification');
      expect(
        () => SafetySignalResult.fromJson(bad),
        throwsA(isA<FormatException>()),
      );
    });
  });
}
