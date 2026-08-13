// app/test/models/daily_checkin_test.dart
//
// Phase 2 Task 5: DailyCheckIn model parsing. All data synthetic.
// Covers: not-checked-in state, normal + abnormal-pain check-ins, missing
// pain_followup when abnormal_pain=false, required-field throw, and unknown
// risk_summary -> parse error (never downgraded to normal).
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/models/daily_checkin.dart';

Map<String, dynamic> _checkin({
  String riskSummary = 'normal',
  bool abnormalPain = false,
  Object? painFollowup,
  String dailyStatus = 'checked_in',
}) {
  return {
    'id': 'synthetic-checkin-1',
    'local_date': '2026-07-23',
    'sleep_quality': 'good',
    'energy': 'normal',
    'muscle_soreness': 'mild',
    'available_time': '30_min',
    'daily_status': dailyStatus,
    'abnormal_pain': abnormalPain,
    'pain_followup': painFollowup,
    'risk_summary': riskSummary,
    'risk_version': '2026-07-22-v1',
    'created_at': '2026-07-23T08:00:00Z',
    'updated_at': '2026-07-23T08:00:00Z',
  };
}

Map<String, dynamic> _followup() => {
      'pain_area': 'lower_back',
      'pain_started': 'today',
      'pain_intensity': 'severe',
      'has_neurological_symptom': true,
      'has_dizziness_or_chest_symptom': false,
      'has_acute_trauma': false,
      'pain_note': 'synthetic note',
    };

void main() {
  group('DailyCheckInTodayResult', () {
    test('not-checked-in: checked_in=false, checkin=null', () {
      final r = DailyCheckInTodayResult.fromJson({
        'checked_in': false,
        'checkin': null,
      });
      expect(r.checkedIn, isFalse);
      expect(r.checkin, isNull);
    });

    test('checked-in parses the checkin', () {
      final r = DailyCheckInTodayResult.fromJson({
        'checked_in': true,
        'checkin': _checkin(),
      });
      expect(r.checkedIn, isTrue);
      expect(r.checkin!.id, 'synthetic-checkin-1');
    });
  });

  group('DailyCheckIn parsing', () {
    test('normal check-in parses all enums', () {
      final c = DailyCheckIn.fromJson(_checkin());
      expect(c.sleepQuality, SleepQuality.good);
      expect(c.energy, Energy.normal);
      expect(c.muscleSoreness, MuscleSoreness.mild);
      expect(c.availableTime, AvailableTime.thirtyMin);
      expect(c.dailyStatus, DailyStatus.checkedIn);
      expect(c.abnormalPain, isFalse);
      expect(c.painFollowup, isNull);
      expect(c.riskSummary, CheckInRiskSummary.normal);
      expect(c.localDate, DateTime(2026, 7, 23));
    });

    test('abnormal pain with followup parses pain_followup', () {
      final c = DailyCheckIn.fromJson(
        _checkin(abnormalPain: true, painFollowup: _followup(), riskSummary: 'red_flag'),
      );
      expect(c.abnormalPain, isTrue);
      expect(c.painFollowup, isNotNull);
      expect(c.painFollowup!.painArea, 'lower_back');
      expect(c.painFollowup!.hasNeurologicalSymptom, isTrue);
      expect(c.painFollowup!.painIntensity, PainIntensity.severe);
      expect(c.riskSummary, CheckInRiskSummary.redFlag);
    });

    test('active_rest and safety_adjustment parse as valid statuses', () {
      expect(
        DailyCheckIn.fromJson(_checkin(dailyStatus: 'active_rest')).dailyStatus,
        DailyStatus.activeRest,
      );
      expect(
        DailyCheckIn.fromJson(_checkin(dailyStatus: 'safety_adjustment'))
            .dailyStatus,
        DailyStatus.safetyAdjustment,
      );
    });
  });

  group('unknown enum handling', () {
    test('unknown risk_summary throws (never downgraded to normal)', () {
      expect(
        () => DailyCheckIn.fromJson(_checkin(riskSummary: 'all_good')),
        throwsA(isA<FormatException>()),
      );
    });

    test('unknown daily_status throws', () {
      expect(
        () => DailyCheckIn.fromJson(_checkin(dailyStatus: 'rest_day')),
        throwsA(isA<FormatException>()),
      );
    });

    test('unknown pain_started in followup throws', () {
      expect(
        () => PainFollowup.fromJson({..._followup(), 'pain_started': 'long_ago'}),
        throwsA(isA<FormatException>()),
      );
    });
  });

  group('CheckInCreate.toJson', () {
    test('emits local_date as yyyy-MM-dd + fields; omits null followup', () {
      final json = CheckInCreate(
        localDate: DateTime(2026, 7, 23),
        sleepQuality: SleepQuality.good,
        energy: Energy.normal,
        muscleSoreness: MuscleSoreness.mild,
        availableTime: AvailableTime.thirtyMin,
        dailyStatus: DailyStatus.checkedIn,
        abnormalPain: false,
      ).toJson();
      expect(json['local_date'], '2026-07-23');
      expect(json['sleep_quality'], 'good');
      expect(json['available_time'], '30_min');
      expect(json['daily_status'], 'checked_in');
      expect(json['abnormal_pain'], isFalse);
      expect(json.containsKey('pain_note'), isFalse);
    });
  });
}
