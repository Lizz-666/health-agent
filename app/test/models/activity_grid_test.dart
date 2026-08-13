// app/test/models/activity_grid_test.dart
//
// Phase 2 Task 5: ActivityGrid model parsing. All data synthetic.
// Covers: status projection (none/checked_in/active_rest/safety_adjustment),
// contiguous cells, and unknown status -> parse error (never coerced to none).
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/models/activity_grid.dart';

Map<String, dynamic> _cell(String date, String status) =>
    {'date': date, 'status': status};

void main() {
  group('ActivityGrid', () {
    test('parses each Phase 2 status', () {
      final g = ActivityGrid.fromJson({
        'start_date': '2026-07-20',
        'end_date': '2026-07-23',
        'cells': [
          _cell('2026-07-20', 'none'),
          _cell('2026-07-21', 'checked_in'),
          _cell('2026-07-22', 'active_rest'),
          _cell('2026-07-23', 'safety_adjustment'),
        ],
      });
      expect(g.startDate, DateTime(2026, 7, 20));
      expect(g.endDate, DateTime(2026, 7, 23));
      expect(
        g.cells.map((c) => c.status).toList(),
        [
          GridStatus.none,
          GridStatus.checkedIn,
          GridStatus.activeRest,
          GridStatus.safetyAdjustment,
        ],
      );
    });

    test('all-none grid parses', () {
      final g = ActivityGrid.fromJson({
        'start_date': '2026-07-20',
        'end_date': '2026-07-21',
        'cells': [_cell('2026-07-20', 'none'), _cell('2026-07-21', 'none')],
      });
      expect(g.cells.every((c) => c.status == GridStatus.none), isTrue);
    });
  });

  group('error handling', () {
    test('unknown status throws (never coerced to none)', () {
      expect(
        () => ActivityGridCell.fromJson(_cell('2026-07-20', 'partial_execution')),
        throwsA(isA<FormatException>()),
      );
      expect(
        () => ActivityGridCell.fromJson(
          _cell('2026-07-20', 'main_plan_completed'),
        ),
        throwsA(isA<FormatException>()),
      );
    });

    test('cells must be a list', () {
      expect(
        () => ActivityGrid.fromJson({
          'start_date': '2026-07-20',
          'end_date': '2026-07-20',
          'cells': 'nope',
        }),
        throwsA(isA<FormatException>()),
      );
    });
  });

  test('GridStatus.wire round-trips the Phase 2 set', () {
    for (final s in GridStatus.values) {
      expect(GridStatus.tryParse(s.wire), s);
    }
  });
}
