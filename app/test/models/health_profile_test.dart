// app/test/models/health_profile_test.dart
//
// Phase 2 Task 5: HealthProfile model parsing. All data synthetic.
// Covers: not-configured state, complete profile, missing/null optional
// fields stay missing, required-field throw, and unknown enum -> parse error
// (readiness tier never downgraded to `ready`).
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/models/health_profile.dart';

Map<String, dynamic> _readiness(String tier) => {
      'readiness': tier,
      'risk_version': '2026-07-22-v1',
      'reason': 'synthetic',
      'missing_fields': <String>[],
      'restricted_reason': null,
    };

Map<String, dynamic> _completeProfile() => {
      'id': 'synthetic-id-1',
      'fitness_goal': 'basic_strength',
      'training_experience': 'some_experience',
      'weekly_frequency': 3,
      'session_duration_minutes': 30,
      'equipment': {'bodyweight': true, 'resistance_band': false},
      'pain_injury_limitations': <Map<String, dynamic>>[],
      'risk_screen': {
        'underage': 'no',
        'pregnancy_or_postpartum': 'unknown',
      },
      'allergies': [
        {'label': 'synthetic-allergy', 'note': null},
      ],
      'diet_exclusions': <Map<String, dynamic>>[],
      'version': 1,
      'updated_at': '2026-07-23T08:00:00Z',
      'created_at': '2026-07-23T08:00:00Z',
    };

void main() {
  group('HealthProfileResult', () {
    test('not-configured: configured=false, profile=null, readiness present',
        () {
      final result = HealthProfileResult.fromJson({
        'configured': false,
        'profile': null,
        'readiness': _readiness('missing_required_data'),
      });
      expect(result.configured, isFalse);
      expect(result.profile, isNull);
      expect(result.readiness.readiness, ReadinessTier.missingRequiredData);
    });

    test('complete profile parses all fields', () {
      final result = HealthProfileResult.fromJson({
        'configured': true,
        'profile': _completeProfile(),
        'readiness': _readiness('ready'),
      });
      final p = result.profile!;
      expect(p.id, 'synthetic-id-1');
      expect(p.fitnessGoal, FitnessGoal.basicStrength);
      expect(p.trainingExperience, TrainingExperience.someExperience);
      expect(p.weeklyFrequency, 3);
      expect(p.sessionDurationMinutes, SessionDurationMinutes.thirty);
      expect(p.equipment!.bodyweight, isTrue);
      expect(p.riskScreen!.underage, YesNoUnknown.no);
      expect(p.riskScreen!.pregnancyOrPostpartum, YesNoUnknown.unknown);
      expect(p.allergies!.length, 1);
      expect(p.version, 1);
    });

    test('missing optional fields stay null, never fabricated', () {
      final result = HealthProfileResult.fromJson({
        'configured': true,
        'profile': {
          'id': 'synthetic-id-2',
          'fitness_goal': null,
          'training_experience': null,
          'weekly_frequency': null,
          'session_duration_minutes': null,
          'equipment': null,
          'pain_injury_limitations': null,
          'risk_screen': null,
          'allergies': null,
          'diet_exclusions': null,
          'version': 2,
          'updated_at': null,
          'created_at': '2026-07-23T08:00:00Z',
        },
        'readiness': _readiness('missing_required_data'),
      });
      final p = result.profile!;
      expect(p.fitnessGoal, isNull);
      expect(p.trainingExperience, isNull);
      expect(p.weeklyFrequency, isNull);
      expect(p.sessionDurationMinutes, isNull);
      expect(p.equipment, isNull);
      expect(p.painInjuryLimitations, isNull);
      expect(p.riskScreen, isNull);
      expect(p.allergies, isNull);
      expect(p.dietExclusions, isNull);
      expect(p.updatedAt, isNull);
    });
  });

  group('unknown enum handling', () {
    test('unknown readiness tier throws (never downgraded to ready)', () {
      expect(
        () => HealthReadiness.fromJson(_readiness('totally_fine')),
        throwsA(isA<FormatException>()),
      );
    });

    test('unknown fitness_goal throws', () {
      expect(
        () => HealthProfile.fromJson({
          ..._completeProfile(),
          'fitness_goal': 'get_huge',
        }),
        throwsA(isA<FormatException>()),
      );
    });

    test('unknown session_duration_minutes throws', () {
      expect(
        () => HealthProfile.fromJson({
          ..._completeProfile(),
          'session_duration_minutes': 20,
        }),
        throwsA(isA<FormatException>()),
      );
    });

    test('unknown risk_screen yes/no/unknown value throws', () {
      expect(
        () => RiskScreen.fromJson({'underage': 'maybe'}),
        throwsA(isA<FormatException>()),
      );
    });
  });

  group('required fields', () {
    test('missing id throws', () {
      expect(
        () => HealthProfile.fromJson({
          ..._completeProfile(),
          'id': null,
        }),
        throwsA(isA<FormatException>()),
      );
    });

    test('missing readiness object throws', () {
      expect(
        () => HealthProfileResult.fromJson({
          'configured': false,
          'profile': null,
          'readiness': null,
        }),
        throwsA(isA<FormatException>()),
      );
    });
  });

  group('HealthProfileUpdate.toJson', () {
    test('emits editable fields, omits server-managed ones', () {
      final json = HealthProfileUpdate(
        fitnessGoal: FitnessGoal.mobility,
        weeklyFrequency: 4,
        sessionDurationMinutes: SessionDurationMinutes.fortyFive,
        equipment: Equipment(bodyweight: true),
      ).toJson();
      expect(json['fitness_goal'], 'mobility');
      expect(json['weekly_frequency'], 4);
      expect(json['session_duration_minutes'], 45);
      expect((json['equipment'] as Map)['bodyweight'], isTrue);
      // Server-managed fields never sent.
      expect(json.containsKey('id'), isFalse);
      expect(json.containsKey('version'), isFalse);
      // Cleared optional fields are null, not omitted-as-missing on the wire.
      expect(json['training_experience'], isNull);
    });
  });
}
