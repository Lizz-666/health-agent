// app/lib/models/daily_checkin.dart
//
// Typed models for GET/PUT /api/v1/health/checkins/today and
// DELETE /api/v1/health/checkins/{id} (Phase 2 spec Domain Model, Daily
// Check-In; backend CheckInTodayResultResponse / CheckInResponse /
// CheckInCreate / PainFollowup).
//
// Safety contract (Task 5):
//  - `risk_summary` is a deterministic safety tier. An unknown value MUST NOT
//    be coerced to `normal`; it surfaces as FormatException (parse error).
//  - `pain_followup` is nullable: present only when abnormal_pain is true.
//    `pain_note` is untrusted free text and is never a safety-rule source.
//  - Unknown enum values for any structured field surface as FormatException.
//  - Missing required scalars (id, risk_summary, risk_version, timestamps)
//    throw; the provider never silently renders a half-formed check-in.
//  - No raw health values are logged by this module.

enum SleepQuality {
  poor,
  ok,
  good;

  static SleepQuality? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'poor':
        return SleepQuality.poor;
      case 'ok':
        return SleepQuality.ok;
      case 'good':
        return SleepQuality.good;
      default:
        return null;
    }
  }

  String get wire => name == 'ok' ? 'ok' : name;
}

enum Energy {
  low,
  normal,
  high;

  static Energy? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'low':
        return Energy.low;
      case 'normal':
        return Energy.normal;
      case 'high':
        return Energy.high;
      default:
        return null;
    }
  }

  String get wire => name;
}

enum MuscleSoreness {
  none,
  mild,
  significant;

  static MuscleSoreness? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'none':
        return MuscleSoreness.none;
      case 'mild':
        return MuscleSoreness.mild;
      case 'significant':
        return MuscleSoreness.significant;
      default:
        return null;
    }
  }

  String get wire => name;
}

enum AvailableTime {
  none,
  fifteenMin,
  thirtyMin,
  fortyFiveMinPlus;

  static AvailableTime? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'none':
        return AvailableTime.none;
      case '15_min':
        return AvailableTime.fifteenMin;
      case '30_min':
        return AvailableTime.thirtyMin;
      case '45_min_plus':
        return AvailableTime.fortyFiveMinPlus;
      default:
        return null;
    }
  }

  String get wire {
    switch (this) {
      case AvailableTime.none:
        return 'none';
      case AvailableTime.fifteenMin:
        return '15_min';
      case AvailableTime.thirtyMin:
        return '30_min';
      case AvailableTime.fortyFiveMinPlus:
        return '45_min_plus';
    }
  }
}

enum DailyStatus {
  checkedIn,
  activeRest,
  safetyAdjustment;

  static DailyStatus? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'checked_in':
        return DailyStatus.checkedIn;
      case 'active_rest':
        return DailyStatus.activeRest;
      case 'safety_adjustment':
        return DailyStatus.safetyAdjustment;
      default:
        return null;
    }
  }

  String get wire {
    switch (this) {
      case DailyStatus.checkedIn:
        return 'checked_in';
      case DailyStatus.activeRest:
        return 'active_rest';
      case DailyStatus.safetyAdjustment:
        return 'safety_adjustment';
    }
  }
}

enum PainStarted {
  today,
  recentDays,
  ongoing,
  afterAcuteEvent;

  static PainStarted? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'today':
        return PainStarted.today;
      case 'recent_days':
        return PainStarted.recentDays;
      case 'ongoing':
        return PainStarted.ongoing;
      case 'after_acute_event':
        return PainStarted.afterAcuteEvent;
      default:
        return null;
    }
  }

  String get wire {
    switch (this) {
      case PainStarted.today:
        return 'today';
      case PainStarted.recentDays:
        return 'recent_days';
      case PainStarted.ongoing:
        return 'ongoing';
      case PainStarted.afterAcuteEvent:
        return 'after_acute_event';
    }
  }
}

enum PainIntensity {
  mild,
  moderate,
  severe;

  static PainIntensity? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'mild':
        return PainIntensity.mild;
      case 'moderate':
        return PainIntensity.moderate;
      case 'severe':
        return PainIntensity.severe;
      default:
        return null;
    }
  }

  String get wire => name;
}

/// Deterministic check-in risk_summary tier. An unknown value MUST NOT be
/// downgraded to `normal`; it surfaces as a parse error so a red_flag /
/// restricted / caution state can never be mistaken for an ordinary one.
enum CheckInRiskSummary {
  normal,
  caution,
  restricted,
  redFlag;

  static CheckInRiskSummary? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'normal':
        return CheckInRiskSummary.normal;
      case 'caution':
        return CheckInRiskSummary.caution;
      case 'restricted':
        return CheckInRiskSummary.restricted;
      case 'red_flag':
        return CheckInRiskSummary.redFlag;
      default:
        return null;
    }
  }

  String get wire {
    switch (this) {
      case CheckInRiskSummary.normal:
        return 'normal';
      case CheckInRiskSummary.caution:
        return 'caution';
      case CheckInRiskSummary.restricted:
        return 'restricted';
      case CheckInRiskSummary.redFlag:
        return 'red_flag';
    }
  }
}

class PainFollowup {
  final String painArea;
  final PainStarted painStarted;
  final PainIntensity painIntensity;
  final bool hasNeurologicalSymptom;
  final bool hasDizzinessOrChestSymptom;
  final bool hasAcuteTrauma;
  final String? painNote;

  const PainFollowup({
    required this.painArea,
    required this.painStarted,
    required this.painIntensity,
    required this.hasNeurologicalSymptom,
    required this.hasDizzinessOrChestSymptom,
    required this.hasAcuteTrauma,
    this.painNote,
  });

  factory PainFollowup.fromJson(Map<String, dynamic> json) {
    final started = PainStarted.tryParse(json['pain_started']);
    if (started == null) {
      throw const FormatException(
        'PainFollowup: unknown pain_started value',
      );
    }
    final intensity = PainIntensity.tryParse(json['pain_intensity']);
    if (intensity == null) {
      throw const FormatException(
        'PainFollowup: unknown pain_intensity value',
      );
    }
    return PainFollowup(
      painArea: _readRequiredString(json, 'pain_area', 'PainFollowup'),
      painStarted: started,
      painIntensity: intensity,
      hasNeurologicalSymptom:
          _readRequiredBool(json, 'has_neurological_symptom', 'PainFollowup'),
      hasDizzinessOrChestSymptom: _readRequiredBool(
          json, 'has_dizziness_or_chest_symptom', 'PainFollowup'),
      hasAcuteTrauma: _readRequiredBool(json, 'has_acute_trauma', 'PainFollowup'),
      painNote: _readNullableString(json['pain_note']),
    );
  }

  Map<String, dynamic> toJson() => {
        'pain_area': painArea,
        'pain_started': painStarted.wire,
        'pain_intensity': painIntensity.wire,
        'has_neurological_symptom': hasNeurologicalSymptom,
        'has_dizziness_or_chest_symptom': hasDizzinessOrChestSymptom,
        'has_acute_trauma': hasAcuteTrauma,
        if (painNote != null) 'pain_note': painNote,
      };
}

/// Stored daily check-in (backend CheckInResponse).
class DailyCheckIn {
  final String id;
  final DateTime localDate;
  final SleepQuality sleepQuality;
  final Energy energy;
  final MuscleSoreness muscleSoreness;
  final AvailableTime availableTime;
  final DailyStatus dailyStatus;
  final bool abnormalPain;
  final PainFollowup? painFollowup;
  final CheckInRiskSummary riskSummary;
  final String riskVersion;
  final DateTime createdAt;
  final DateTime updatedAt;

  const DailyCheckIn({
    required this.id,
    required this.localDate,
    required this.sleepQuality,
    required this.energy,
    required this.muscleSoreness,
    required this.availableTime,
    required this.dailyStatus,
    required this.abnormalPain,
    required this.painFollowup,
    required this.riskSummary,
    required this.riskVersion,
    required this.createdAt,
    required this.updatedAt,
  });

  factory DailyCheckIn.fromJson(Map<String, dynamic> json) {
    final sleep = SleepQuality.tryParse(json['sleep_quality']);
    if (sleep == null) {
      throw const FormatException('DailyCheckIn: unknown sleep_quality value');
    }
    final energy = Energy.tryParse(json['energy']);
    if (energy == null) {
      throw const FormatException('DailyCheckIn: unknown energy value');
    }
    final soreness = MuscleSoreness.tryParse(json['muscle_soreness']);
    if (soreness == null) {
      throw const FormatException('DailyCheckIn: unknown muscle_soreness value');
    }
    final available = AvailableTime.tryParse(json['available_time']);
    if (available == null) {
      throw const FormatException('DailyCheckIn: unknown available_time value');
    }
    final status = DailyStatus.tryParse(json['daily_status']);
    if (status == null) {
      throw const FormatException('DailyCheckIn: unknown daily_status value');
    }
    final risk = CheckInRiskSummary.tryParse(json['risk_summary']);
    if (risk == null) {
      throw const FormatException('DailyCheckIn: unknown risk_summary value');
    }
    final abnormalRaw = json['abnormal_pain'];
    if (abnormalRaw is! bool) {
      throw const FormatException(
        'DailyCheckIn: `abnormal_pain` must be a bool',
      );
    }
    PainFollowup? followup;
    final rawFollowup = json['pain_followup'];
    if (rawFollowup != null) {
      if (rawFollowup is! Map<String, dynamic>) {
        throw const FormatException(
          'DailyCheckIn: `pain_followup` must be an object when present',
        );
      }
      followup = PainFollowup.fromJson(rawFollowup);
    }
    return DailyCheckIn(
      id: _readRequiredString(json, 'id', 'DailyCheckIn'),
      localDate: _readRequiredDate(json, 'local_date', 'DailyCheckIn'),
      sleepQuality: sleep,
      energy: energy,
      muscleSoreness: soreness,
      availableTime: available,
      dailyStatus: status,
      abnormalPain: abnormalRaw,
      painFollowup: followup,
      riskSummary: risk,
      riskVersion: _readRequiredString(json, 'risk_version', 'DailyCheckIn'),
      createdAt: _readRequiredDateTime(json, 'created_at', 'DailyCheckIn'),
      updatedAt: _readRequiredDateTime(json, 'updated_at', 'DailyCheckIn'),
    );
  }
}

/// PUT /api/v1/health/checkins/today request body (backend CheckInCreate).
/// `localDate` is the user-local date and per-user daily uniqueness key.
class CheckInCreate {
  final DateTime localDate;
  final SleepQuality sleepQuality;
  final Energy energy;
  final MuscleSoreness muscleSoreness;
  final AvailableTime availableTime;
  final DailyStatus dailyStatus;
  final bool abnormalPain;
  final PainFollowup? painFollowup;

  const CheckInCreate({
    required this.localDate,
    required this.sleepQuality,
    required this.energy,
    required this.muscleSoreness,
    required this.availableTime,
    required this.dailyStatus,
    required this.abnormalPain,
    this.painFollowup,
  });

  Map<String, dynamic> toJson() => {
        'local_date': _formatDate(localDate),
        'sleep_quality': sleepQuality.wire,
        'energy': energy.wire,
        'muscle_soreness': muscleSoreness.wire,
        'available_time': availableTime.wire,
        'daily_status': dailyStatus.wire,
        'abnormal_pain': abnormalPain,
        'pain_followup': painFollowup?.toJson(),
      };
}

/// GET /api/v1/health/checkins/today envelope (backend
/// CheckInTodayResultResponse). `checked_in` is false and `checkin` is null
/// when no check-in exists for the date (an explicit not-checked-in state).
class DailyCheckInTodayResult {
  final bool checkedIn;
  final DailyCheckIn? checkin;

  const DailyCheckInTodayResult({required this.checkedIn, required this.checkin});

  factory DailyCheckInTodayResult.fromJson(Map<String, dynamic> json) {
    final checkedRaw = json['checked_in'];
    if (checkedRaw is! bool) {
      throw const FormatException(
        'DailyCheckInTodayResult: `checked_in` must be a bool',
      );
    }
    DailyCheckIn? checkin;
    final rawCheckin = json['checkin'];
    if (rawCheckin != null) {
      if (rawCheckin is! Map<String, dynamic>) {
        throw const FormatException(
          'DailyCheckInTodayResult: `checkin` must be an object when present',
        );
      }
      checkin = DailyCheckIn.fromJson(rawCheckin);
    }
    return DailyCheckInTodayResult(checkedIn: checkedRaw, checkin: checkin);
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

bool _readRequiredBool(Map<String, dynamic> json, String key, String context) {
  final raw = json[key];
  if (raw is! bool) {
    throw FormatException('$context: `$key` must be a bool');
  }
  return raw;
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

DateTime _readRequiredDate(Map<String, dynamic> json, String key, String context) {
  // Date-only field ("YYYY-MM-DD"); DateTime.tryParse handles it.
  return _readRequiredDateTime(json, key, context);
}

String _formatDate(DateTime dt) {
  String two(int v) => v.toString().padLeft(2, '0');
  return '${dt.year}-${two(dt.month)}-${two(dt.day)}';
}
