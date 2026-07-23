// app/lib/models/weight_record.dart
//
// Typed models for /api/v1/health/weight-records CRUD and
// GET /api/v1/health/trends/weight (Phase 2 spec Domain Model, Weight Record
// And Trend; backend WeightRecordResponse / WeightTrendResponse /
// WeightTrendPoint / WeightRecordCreate / WeightRecordUpdate).
//
// Safety contract (Task 5):
//  - `weight_kg` is a numeric value; non-numeric / missing values surface as
//    FormatException (parse error), never a fabricated default.
//  - `source` is always `manual` in Phase 2; it is server-set and never sent
//    by the client (create/update payloads omit it).
//  - The trend carries no recommendation / adjustment / pass-fail signal; it
//    is descriptive only (raw points + moving average + sufficient flag).
//  - No raw weight values are logged by this module.

/// Stored weight record (backend WeightRecordResponse).
class WeightRecord {
  final String id;
  final DateTime recordedAt;
  final double weightKg;
  final String source;
  final String? note;
  final DateTime createdAt;
  final DateTime updatedAt;

  const WeightRecord({
    required this.id,
    required this.recordedAt,
    required this.weightKg,
    required this.source,
    required this.note,
    required this.createdAt,
    required this.updatedAt,
  });

  factory WeightRecord.fromJson(Map<String, dynamic> json) {
    return WeightRecord(
      id: _readRequiredString(json, 'id', 'WeightRecord'),
      recordedAt: _readRequiredDateTime(json, 'recorded_at', 'WeightRecord'),
      weightKg: _readRequiredDouble(json, 'weight_kg', 'WeightRecord'),
      source: _readRequiredString(json, 'source', 'WeightRecord'),
      note: _readNullableString(json['note']),
      createdAt: _readRequiredDateTime(json, 'created_at', 'WeightRecord'),
      updatedAt: _readRequiredDateTime(json, 'updated_at', 'WeightRecord'),
    );
  }
}

/// POST /api/v1/health/weight-records and PUT .../{record_id} request body
/// (backend WeightRecordCreate / WeightRecordUpdate). `source` / `id` are
/// server-managed and never sent.
class WeightRecordInput {
  final DateTime recordedAt;
  final double weightKg;
  final String? note;

  const WeightRecordInput({
    required this.recordedAt,
    required this.weightKg,
    this.note,
  });

  Map<String, dynamic> toJson() => {
        // ISO-8601 timestamp; the backend canonicalizes to UTC.
        'recorded_at': recordedAt.toUtc().toIso8601String(),
        'weight_kg': weightKg,
        if (note != null) 'note': note,
      };
}

/// One point of the moving trend series (backend WeightTrendPoint).
/// `weightKg` is the simple moving average up to and including `recordedAt`;
/// it is NOT a recommendation or pass/fail signal.
class WeightTrendPoint {
  final DateTime recordedAt;
  final double weightKg;

  const WeightTrendPoint({required this.recordedAt, required this.weightKg});

  factory WeightTrendPoint.fromJson(Map<String, dynamic> json) {
    return WeightTrendPoint(
      recordedAt:
          _readRequiredDateTime(json, 'recorded_at', 'WeightTrendPoint'),
      weightKg: _readRequiredDouble(json, 'weight_kg', 'WeightTrendPoint'),
    );
  }
}

/// GET /api/v1/health/trends/weight response (backend WeightTrendResponse).
/// When `sufficient` is false, `trend` is empty (insufficient data); raw
/// records are still returned. No adjustment / warning text is carried.
class WeightTrend {
  final List<WeightRecord> records;
  final List<WeightTrendPoint> trend;
  final int window;
  final bool sufficient;

  const WeightTrend({
    required this.records,
    required this.trend,
    required this.window,
    required this.sufficient,
  });

  factory WeightTrend.fromJson(Map<String, dynamic> json) {
    final rawRecords = json['records'];
    if (rawRecords is! List) {
      throw const FormatException('WeightTrend: `records` must be a list');
    }
    final rawTrend = json['trend'];
    if (rawTrend is! List) {
      throw const FormatException('WeightTrend: `trend` must be a list');
    }
    final windowRaw = json['window'];
    if (windowRaw is! int || windowRaw < 0) {
      throw const FormatException(
        'WeightTrend: `window` must be a non-negative integer',
      );
    }
    final sufficientRaw = json['sufficient'];
    if (sufficientRaw is! bool) {
      throw const FormatException('WeightTrend: `sufficient` must be a bool');
    }
    return WeightTrend(
      records: rawRecords
          .map((e) =>
              WeightRecord.fromJson(_readJsonObject(e, 'WeightTrend.records')))
          .toList(growable: false),
      trend: rawTrend
          .map((e) =>
              WeightTrendPoint.fromJson(_readJsonObject(e, 'WeightTrend.trend')))
          .toList(growable: false),
      window: windowRaw,
      sufficient: sufficientRaw,
    );
  }
}

// ---------------------------------------------------------------------------
// Parsing helpers (private; mirror app/lib/models/health_profile.dart).
// ---------------------------------------------------------------------------

String _readRequiredString(Map<String, dynamic> json, String key, String context) {
  final value = (json[key] as String?)?.trim();
  if (value == null || value.isEmpty) {
    throw FormatException('$context: missing required `$key` field');
  }
  return value;
}

String? _readNullableString(Object? raw) {
  if (raw == null) return null;
  if (raw is String) return raw.trim().isEmpty ? null : raw.trim();
  throw const FormatException('expected a string value');
}

double _readRequiredDouble(Map<String, dynamic> json, String key, String context) {
  final raw = json[key];
  if (raw is num) return raw.toDouble();
  throw FormatException('$context: `$key` must be a number');
}

DateTime _readRequiredDateTime(Map<String, dynamic> json, String key, String context) {
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
