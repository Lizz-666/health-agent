// app/test/models/adaptive_review_test.dart
//
// Strict parsing tests for the Phase 7 weekly review snapshot models.
//
// The weekly review endpoints are owned by Codex Task 3 and are not yet
// implemented on the backend. These tests pin the typed client contract
// (proposed, spec-aligned snake_case) used by mock-backed provider/widget
// tests; any real response that does not match fails closed rather than
// fabricating a review. No raw health values are asserted here.
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/models/adaptive_review.dart';

Map<String, dynamic> _snapshotJson() => {
  'review_id': 'rv-1',
  'plan_version_id': 'pv-1',
  'week_index': 1,
  'review_version': 1,
  'period_start': '2026-07-20',
  'period_end': '2026-07-26',
  'execution': {
    'scheduled': 3,
    'completed': 2,
    'partial': 0,
    'too_busy': 1,
    'intentional_rest': 0,
    'discomfort': 0,
    'active_rest': 0,
    'safety_adjustment': 0,
    'unavailable': 0,
    'effective': 3,
  },
  'execution_trend': {'available': true, 'direction': 'steady'},
  'adjustments': {
    'shortened': 1,
    'recovery': 0,
    'deferred': 0,
    'active_rest': 0,
    'unchanged': 0,
    'missing': 0,
    'unavailable': 0,
  },
  'weight_trend': {'available': true, 'direction': 'rising'},
  'nutrition': {'state': 'active', 'age_days': 12, 'refresh_available': true},
  'posture': {'status': 'due'},
  'proposals': [
    {'code': 'keep_current_plan', 'state': 'proposal'},
    {
      'code': 'offer_training_draft',
      'strategy': 'conservative_duration',
      'state': 'proposal',
    },
  ],
};

void main() {
  group('WeeklyReviewSnapshot parsing', () {
    test('parses a complete snapshot', () {
      final s = WeeklyReviewSnapshot.fromJson(_snapshotJson());
      expect(s.reviewId, 'rv-1');
      expect(s.weekIndex, 1);
      expect(s.reviewVersion, 1);
      expect(s.periodStart, DateTime.parse('2026-07-20'));
      expect(s.periodEnd, DateTime.parse('2026-07-26'));
      expect(s.execution.completed, 2);
      expect(s.execution.activeRest, 0);
      expect(s.adjustments.shortened, 1);
      expect(s.executionTrend.available, isTrue);
      expect(s.executionTrend.direction, ExecutionTrendDirection.steady);
      expect(s.weightTrend.available, isTrue);
      expect(s.weightTrend.direction, WeightTrendDirection.rising);
      expect(s.nutrition.state, NutritionRecommendationState.active);
      expect(s.nutrition.ageDays, 12);
      expect(s.nutrition.refreshAvailable, isTrue);
      expect(s.posture.status, PostureRecheckStatus.due);
      expect(s.proposals.length, 2);
      expect(s.proposals[0].code, ReviewProposalCode.keepCurrentPlan);
      expect(s.proposals[1].code, ReviewProposalCode.offerTrainingDraft);
      expect(s.proposals[1].strategy, ReviewDraftStrategy.conservativeDuration);
    });

    test('missing required field fails closed', () {
      final json = _snapshotJson()..remove('review_id');
      expect(() => WeeklyReviewSnapshot.fromJson(json), throwsFormatException);
    });

    test('missing execution block fails closed (no missing-as-zero)', () {
      final json = _snapshotJson()..remove('execution');
      expect(() => WeeklyReviewSnapshot.fromJson(json), throwsFormatException);
    });

    test('week_index out of bounds fails closed', () {
      final json = _snapshotJson()..['week_index'] = 5;
      expect(() => WeeklyReviewSnapshot.fromJson(json), throwsFormatException);
      final json0 = _snapshotJson()..['week_index'] = 0;
      expect(() => WeeklyReviewSnapshot.fromJson(json0), throwsFormatException);
    });

    test('unknown proposal code fails closed', () {
      final json = _snapshotJson()
        ..['proposals'] = [
          {'code': 'auto_upgrade_plan', 'state': 'proposal'},
        ];
      expect(() => WeeklyReviewSnapshot.fromJson(json), throwsFormatException);
    });

    test('unknown proposal state fails closed', () {
      final json = _snapshotJson()
        ..['proposals'] = [
          {'code': 'keep_current_plan', 'state': 'confirmed'},
        ];
      expect(() => WeeklyReviewSnapshot.fromJson(json), throwsFormatException);
    });

    test('unknown weight trend direction fails closed', () {
      final json = _snapshotJson()
        ..['weight_trend'] = {'available': true, 'direction': 'surging'};
      expect(() => WeeklyReviewSnapshot.fromJson(json), throwsFormatException);
    });

    test('unknown posture status fails closed', () {
      final json = _snapshotJson()..['posture'] = {'status': 'overdue'};
      expect(() => WeeklyReviewSnapshot.fromJson(json), throwsFormatException);
    });

    test('unknown nutrition state fails closed', () {
      final json = _snapshotJson()
        ..['nutrition'] = {'state': 'expired', 'age_days': 1};
      expect(() => WeeklyReviewSnapshot.fromJson(json), throwsFormatException);
    });

    test('unavailable trends have null direction', () {
      final json = _snapshotJson()
        ..['execution_trend'] = {'available': false}
        ..['weight_trend'] = {'available': false};
      final s = WeeklyReviewSnapshot.fromJson(json);
      expect(s.executionTrend.available, isFalse);
      expect(s.executionTrend.direction, isNull);
      expect(s.weightTrend.available, isFalse);
      expect(s.weightTrend.direction, isNull);
    });

    test('available trend without direction fails closed', () {
      final json = _snapshotJson()..['execution_trend'] = {'available': true};
      expect(() => WeeklyReviewSnapshot.fromJson(json), throwsFormatException);
    });

    test('negative or fractional counts fail closed', () {
      final negative = _snapshotJson();
      (negative['execution'] as Map<String, dynamic>)['completed'] = -1;
      expect(
        () => WeeklyReviewSnapshot.fromJson(negative),
        throwsFormatException,
      );
      final fractional = _snapshotJson();
      fractional['adjustments'] = Map<String, dynamic>.from(
        fractional['adjustments'] as Map,
      )..['shortened'] = 1.5;
      expect(
        () => WeeklyReviewSnapshot.fromJson(fractional),
        throwsFormatException,
      );
    });

    test('posture unavailable with reason parses', () {
      final json = _snapshotJson()
        ..['posture'] = {'status': 'unavailable', 'reason': 'no_baseline'};
      final s = WeeklyReviewSnapshot.fromJson(json);
      expect(s.posture.status, PostureRecheckStatus.unavailable);
      expect(s.posture.reason, 'no_baseline');
    });

    test('posture comparison signal parses', () {
      final json = _snapshotJson()
        ..['posture'] = {
          'status': 'comparison_available',
          'comparison_signal': 'changed',
          'baseline_at': '2026-06-01',
          'comparison_at': '2026-08-01',
        };
      final s = WeeklyReviewSnapshot.fromJson(json);
      expect(s.posture.status, PostureRecheckStatus.comparisonAvailable);
      expect(s.posture.comparisonSignal, PostureComparisonSignal.changed);
    });

    test('malformed counts fail closed (not silently coerced to zero)', () {
      final json = _snapshotJson()..['execution'] = {'scheduled': 'three'};
      expect(() => WeeklyReviewSnapshot.fromJson(json), throwsFormatException);
    });

    test('unknown draft strategy fails closed', () {
      final json = _snapshotJson()
        ..['proposals'] = [
          {
            'code': 'offer_training_draft',
            'strategy': 'aggressive_bulk',
            'state': 'proposal',
          },
        ];
      expect(() => WeeklyReviewSnapshot.fromJson(json), throwsFormatException);
    });

    test('training draft proposal requires a bounded strategy', () {
      final json = _snapshotJson()
        ..['proposals'] = [
          {'code': 'offer_training_draft', 'state': 'proposal'},
        ];
      expect(() => WeeklyReviewSnapshot.fromJson(json), throwsFormatException);
    });

    test('draft proposal state parses distinctly from active', () {
      final json = _snapshotJson()
        ..['proposals'] = [
          {
            'code': 'offer_training_draft',
            'state': 'draft',
            'strategy': 'conservative_duration',
            'origin_weekly_review_id': 'rv-0',
          },
        ];
      final s = WeeklyReviewSnapshot.fromJson(json);
      expect(s.proposals.single.state, ReviewProposalState.draft);
      expect(s.proposals.single.originWeeklyReviewId, 'rv-0');
    });
  });
}
