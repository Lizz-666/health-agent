// app/test/models/weight_record_test.dart
//
// Phase 2 Task 5: WeightRecord / WeightTrend model parsing. All data synthetic.
// Covers: record parsing, nullable note, numeric weight_kg (int + double),
// trend sufficient/insufficient, required-field throw, and non-numeric
// weight -> parse error.
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/models/weight_record.dart';

Map<String, dynamic> _record({
  Object? weightKg = 70.5,
  Object? note,
}) =>
    {
      'id': 'synthetic-weight-1',
      'recorded_at': '2026-07-23T08:00:00Z',
      'weight_kg': weightKg,
      'source': 'manual',
      'note': note,
      'created_at': '2026-07-23T08:00:00Z',
      'updated_at': '2026-07-23T08:00:00Z',
    };

void main() {
  group('WeightRecord', () {
    test('parses fields and nullable note', () {
      final r = WeightRecord.fromJson(_record(note: 'synthetic note'));
      expect(r.id, 'synthetic-weight-1');
      expect(r.weightKg, 70.5);
      expect(r.source, 'manual');
      expect(r.note, 'synthetic note');
    });

    test('note stays null when missing', () {
      final r = WeightRecord.fromJson(_record(note: null));
      expect(r.note, isNull);
    });

    test('weight_kg accepts integer JSON as double', () {
      final r = WeightRecord.fromJson(_record(weightKg: 70));
      expect(r.weightKg, 70.0);
    });
  });

  group('WeightTrend', () {
    test('sufficient trend parses records + trend points', () {
      final t = WeightTrend.fromJson({
        'records': [_record(weightKg: 70.0), _record(weightKg: 71.0)],
        'trend': [
          {'recorded_at': '2026-07-23T08:00:00Z', 'weight_kg': 70.5},
        ],
        'window': 2,
        'sufficient': true,
      });
      expect(t.records.length, 2);
      expect(t.trend.length, 1);
      expect(t.trend.first.weightKg, 70.5);
      expect(t.window, 2);
      expect(t.sufficient, isTrue);
    });

    test('insufficient trend: sufficient=false, empty trend, records present',
        () {
      final t = WeightTrend.fromJson({
        'records': [_record()],
        'trend': <Map<String, dynamic>>[],
        'window': 7,
        'sufficient': false,
      });
      expect(t.sufficient, isFalse);
      expect(t.trend, isEmpty);
      expect(t.records.length, 1);
    });
  });

  group('error handling', () {
    test('non-numeric weight_kg throws', () {
      expect(
        () => WeightRecord.fromJson(_record(weightKg: 'heavy')),
        throwsA(isA<FormatException>()),
      );
    });

    test('missing recorded_at throws', () {
      final json = _record()..remove('recorded_at');
      expect(
        () => WeightRecord.fromJson(json),
        throwsA(isA<FormatException>()),
      );
    });

    test('records must be a list', () {
      expect(
        () => WeightTrend.fromJson({
          'records': 'nope',
          'trend': <Map<String, dynamic>>[],
          'window': 7,
          'sufficient': false,
        }),
        throwsA(isA<FormatException>()),
      );
    });
  });

  test('WeightRecordInput.toJson omits id/source and ISO-encodes recorded_at', () {
    final json = WeightRecordInput(
      recordedAt: DateTime.utc(2026, 7, 23, 8, 0, 0),
      weightKg: 72.3,
    ).toJson();
    expect(json['recorded_at'], '2026-07-23T08:00:00.000Z');
    expect(json['weight_kg'], 72.3);
    expect(json.containsKey('id'), isFalse);
    expect(json.containsKey('source'), isFalse);
    expect(json.containsKey('note'), isFalse);
  });
}
