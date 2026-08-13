// app/lib/models/activity_grid.dart
//
// Typed model for GET /api/v1/health/activity-grid (Phase 2 spec Domain
// Model, Activity Grid; backend ActivityGridResponse / ActivityGridCell /
// GridStatus).
//
// Safety contract (Task 5):
//  - `GridStatus` is exactly the Phase 2 set: none, checked_in, active_rest,
//    safety_adjustment. An unknown status MUST NOT be coerced to `none`; it
//    surfaces as FormatException so a plan-execution status can never be
//    silently rendered as a normal day.
//  - active_rest and safety_adjustment are valid, non-failure engagement
//    states (spec Domain Model, Activity Grid).

enum GridStatus {
  none,
  checkedIn,
  activeRest,
  safetyAdjustment;

  static GridStatus? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'none':
        return GridStatus.none;
      case 'checked_in':
        return GridStatus.checkedIn;
      case 'active_rest':
        return GridStatus.activeRest;
      case 'safety_adjustment':
        return GridStatus.safetyAdjustment;
      default:
        return null;
    }
  }

  String get wire {
    switch (this) {
      case GridStatus.none:
        return 'none';
      case GridStatus.checkedIn:
        return 'checked_in';
      case GridStatus.activeRest:
        return 'active_rest';
      case GridStatus.safetyAdjustment:
        return 'safety_adjustment';
    }
  }
}

class ActivityGridCell {
  final DateTime date;
  final GridStatus status;

  const ActivityGridCell({required this.date, required this.status});

  factory ActivityGridCell.fromJson(Map<String, dynamic> json) {
    final status = GridStatus.tryParse(json['status']);
    if (status == null) {
      throw const FormatException(
        'ActivityGridCell: unknown status value',
      );
    }
    return ActivityGridCell(
      date: _readRequiredDate(json, 'date', 'ActivityGridCell'),
      status: status,
    );
  }
}

/// GET /api/v1/health/activity-grid response (backend ActivityGridResponse).
class ActivityGrid {
  final DateTime startDate;
  final DateTime endDate;
  final List<ActivityGridCell> cells;

  const ActivityGrid({
    required this.startDate,
    required this.endDate,
    required this.cells,
  });

  factory ActivityGrid.fromJson(Map<String, dynamic> json) {
    final rawCells = json['cells'];
    if (rawCells is! List) {
      throw const FormatException('ActivityGrid: `cells` must be a list');
    }
    return ActivityGrid(
      startDate: _readRequiredDate(json, 'start_date', 'ActivityGrid'),
      endDate: _readRequiredDate(json, 'end_date', 'ActivityGrid'),
      cells: rawCells
          .map((e) =>
              ActivityGridCell.fromJson(_readJsonObject(e, 'ActivityGrid.cells')))
          .toList(growable: false),
    );
  }
}

// ---------------------------------------------------------------------------
// Parsing helpers (private; mirror app/lib/models/health_profile.dart).
// ---------------------------------------------------------------------------

DateTime _readRequiredDate(Map<String, dynamic> json, String key, String context) {
  final raw = ((json[key] as String?) ?? '').trim();
  if (raw.isEmpty) {
    throw FormatException('$context: missing required `$key` field');
  }
  final parsed = DateTime.tryParse(raw);
  if (parsed == null) {
    throw FormatException('$context: unparseable `$key`');
  }
  return parsed;
}

Map<String, dynamic> _readJsonObject(Object? raw, String context) {
  if (raw is! Map<String, dynamic>) {
    throw FormatException('$context must contain a JSON object');
  }
  return raw;
}
