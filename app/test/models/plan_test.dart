// app/test/models/plan_test.dart
//
// Strict parsing tests for the Phase 4 plan models. Unknown enums throw
// (never coerced to a normal-looking plan); missing required scalars throw.
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/models/plan.dart';

Map<String, dynamic> _exerciseJson() => {
      'exercise_id': 'ex-1',
      'name_en': 'Squat',
      'name_zh': '深蹲',
      'training_roles': ['strength'],
      'difficulty': 'beginner',
      'illustration_asset_key': 'assets/training/illustrations/ex-1.svg',
      'illustration_alt_zh': '深蹲示意',
      'instruction_steps': ['stand', 'lower'],
      'form_cues': ['keep back straight'],
      'substitution_ids': ['ex-2'],
    };

Map<String, dynamic> _prescriptionJson() => {
      'prescription_id': 'p-1',
      'exercise_id': 'ex-1',
      'sets': 3,
      'reps': 10,
      'duration_seconds': null,
      'rest_seconds': 60,
      'relation_reason': null,
      'exercise': _exerciseJson(),
    };

Map<String, dynamic> _sessionJson() => {
      'session_id': 's-1',
      'week_index': 1,
      'day_of_week': 1,
      'session_order': 1,
      'target_minutes': null,
      'prescriptions': [_prescriptionJson()],
    };

Map<String, dynamic> _planJson({String status = 'draft'}) => {
      'plan_version_id': 'pv-1',
      'requested_goal': 'basic_strength',
      'weekly_frequency': 3,
      'session_duration_minutes': 30,
      'status': status,
      'change_reason': 'initial_generation',
      'decision_gate': 'eligible',
      'generated_at': '2026-07-27T08:00:00Z',
      'confirmed_at': null,
      'catalog_version': 'v1',
      'policy_version': 'v1',
      'sessions': [
        _sessionJson(),
        _sessionJson(),
      ],
    };

void main() {
  group('PlanVersion parsing', () {
    test('parses a valid plan', () {
      final p = PlanVersion.fromJson(_planJson());
      expect(p.status, PlanStatus.draft);
      expect(p.weeklyFrequency, 3);
      expect(p.sessions.length, 2);
      expect(p.sessions[0].prescriptions.first.exercise?.nameZh, '深蹲');
      expect(p.sessions[0].prescriptions.first.reps, 10);
    });

    test('unknown status throws (never coerced to active/normal)', () {
      expect(() => PlanVersion.fromJson(_planJson(status: 'finalized')),
          throwsFormatException);
    });

    test('missing required field throws', () {
      final json = _planJson()..remove('requested_goal');
      expect(() => PlanVersion.fromJson(json), throwsFormatException);
    });
  });

  group('TodayResult parsing', () {
    test('parses session state', () {
      final r = TodayResult.fromJson({
        'state': 'session',
        'local_date': '2026-07-27',
        'change_reason': 'initial_confirmation',
        'decision_gate': 'eligible',
        'session': _sessionJson(),
      });
      expect(r.state, TodayState.session);
      expect(r.session, isNotNull);
    });

    test('parses blocked state honestly', () {
      final r = TodayResult.fromJson({
        'state': 'blocked',
        'local_date': '2026-07-27',
        'decision_gate': 'red_flag',
      });
      expect(r.state, TodayState.blocked);
      expect(r.session, isNull);
    });

    test('unknown today state throws', () {
      expect(() => TodayResult.fromJson({'state': 'almost_ready'}),
          throwsFormatException);
    });

    test('parses the four-week completion state', () {
      final r = TodayResult.fromJson({
        'state': 'plan_complete',
        'local_date': '2026-08-24',
        'substitution_applied': false,
      });
      expect(r.state, TodayState.planComplete);
      expect(r.session, isNull);
    });
  });

  group('FeedbackResult parsing', () {
    test('parses outcome state with snake_case wire mapping', () {
      final r = FeedbackResult.fromJson({
        'feedback_id': 'f-1',
        'outcome_state': 'too_busy',
        'status': 'recorded',
      });
      expect(r.outcomeState, OutcomeState.tooBusy);
      expect(OutcomeState.intentionalRest.wire, 'intentional_rest');
      expect(OutcomeState.completed.wire, 'completed');
    });

    test('unknown outcome throws', () {
      expect(() => FeedbackResult.fromJson({
            'feedback_id': 'f',
            'outcome_state': 'skipped',
            'status': 'recorded',
          }), throwsFormatException);
    });
  });

  group('DraftResult / ActivePlanResult', () {
    test('no-draft / no-active are explicit empty states', () {
      expect(DraftResult.fromJson({'has_draft': false}).hasDraft, isFalse);
      expect(ActivePlanResult.fromJson({'has_active': false}).hasActive, isFalse);
    });
  });
}
