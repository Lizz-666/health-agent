// app/lib/models/health_profile.dart
//
// Typed models for GET/PUT/DELETE /api/v1/health/profile (Phase 2 spec Domain
// Model; backend HealthProfileResultResponse / HealthProfileResponse /
// HealthReadinessResponse / HealthProfileUpdate).
//
// Safety contract (Task 5):
//  - Every optional training / diet / pain field is nullable. A missing value
//    stays missing (null); it is NEVER replaced by a default that could look
//    user-provided (spec Domain Model, Recommendation And AI Behavior).
//  - Unknown enum values (fitness_goal, training_experience,
//    session_duration_minutes, yes/no/unknown, readiness tier) MUST NOT be
//    coerced to a safe default. They surface as FormatException so the provider
//    can mark the response as a parse error.
//  - In particular, an unknown `readiness` tier is never downgraded to `ready`.
//  - Missing required scalars (id, version, readiness fields) throw.
//  - No raw health values are logged by this module (fromJson throws only
//    generic messages; it never embeds payload values in exceptions).

enum FitnessGoal {
  postureImprovement,
  fatLoss,
  basicStrength,
  mobility,
  generalWellness;

  static FitnessGoal? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'posture_improvement':
        return FitnessGoal.postureImprovement;
      case 'fat_loss':
        return FitnessGoal.fatLoss;
      case 'basic_strength':
        return FitnessGoal.basicStrength;
      case 'mobility':
        return FitnessGoal.mobility;
      case 'general_wellness':
        return FitnessGoal.generalWellness;
      default:
        return null;
    }
  }

  String get wire {
    switch (this) {
      case FitnessGoal.postureImprovement:
        return 'posture_improvement';
      case FitnessGoal.fatLoss:
        return 'fat_loss';
      case FitnessGoal.basicStrength:
        return 'basic_strength';
      case FitnessGoal.mobility:
        return 'mobility';
      case FitnessGoal.generalWellness:
        return 'general_wellness';
    }
  }
}

enum TrainingExperience {
  beginner,
  someExperience,
  experienced;

  static TrainingExperience? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'beginner':
        return TrainingExperience.beginner;
      case 'some_experience':
        return TrainingExperience.someExperience;
      case 'experienced':
        return TrainingExperience.experienced;
      default:
        return null;
    }
  }

  String get wire {
    switch (this) {
      case TrainingExperience.beginner:
        return 'beginner';
      case TrainingExperience.someExperience:
        return 'some_experience';
      case TrainingExperience.experienced:
        return 'experienced';
    }
  }
}

/// Allowed single-session durations in minutes. The JSON value is an int.
enum SessionDurationMinutes {
  fifteen(15),
  thirty(30),
  fortyFive(45),
  sixty(60);

  final int value;
  const SessionDurationMinutes(this.value);

  static SessionDurationMinutes? fromInt(Object? raw) {
    if (raw is! int) return null;
    switch (raw) {
      case 15:
        return SessionDurationMinutes.fifteen;
      case 30:
        return SessionDurationMinutes.thirty;
      case 45:
        return SessionDurationMinutes.fortyFive;
      case 60:
        return SessionDurationMinutes.sixty;
      default:
        return null;
    }
  }
}

enum YesNoUnknown {
  yes,
  no,
  unknown;

  static YesNoUnknown? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'yes':
        return YesNoUnknown.yes;
      case 'no':
        return YesNoUnknown.no;
      case 'unknown':
        return YesNoUnknown.unknown;
      default:
        return null;
    }
  }

  String get wire {
    switch (this) {
      case YesNoUnknown.yes:
        return 'yes';
      case YesNoUnknown.no:
        return 'no';
      case YesNoUnknown.unknown:
        return 'unknown';
    }
  }
}

enum FoodAllergenCode {
  glutenCereal('gluten_cereal'),
  crustacean('crustacean'),
  fish('fish'),
  egg('egg'),
  peanut('peanut'),
  soy('soy'),
  milk('milk'),
  treeNut('tree_nut');

  final String wire;
  const FoodAllergenCode(this.wire);

  static FoodAllergenCode? tryParse(Object? raw) {
    if (raw is! String) return null;
    for (final value in values) {
      if (value.wire == raw) return value;
    }
    return null;
  }
}

enum ExcludedFoodCode {
  avoidPork('avoid_pork'),
  avoidBeef('avoid_beef');

  final String wire;
  const ExcludedFoodCode(this.wire);

  static ExcludedFoodCode? tryParse(Object? raw) {
    if (raw is! String) return null;
    for (final value in values) {
      if (value.wire == raw) return value;
    }
    return null;
  }
}

class Equipment {
  final bool? bodyweight;
  final bool? resistanceBand;

  const Equipment({this.bodyweight, this.resistanceBand});

  factory Equipment.fromJson(Map<String, dynamic> json) {
    return Equipment(
      bodyweight: _readNullableBool(json['bodyweight'], 'Equipment.bodyweight'),
      resistanceBand:
          _readNullableBool(json['resistance_band'], 'Equipment.resistance_band'),
    );
  }

  Map<String, dynamic> toJson() => {
        'bodyweight': bodyweight,
        'resistance_band': resistanceBand,
      };
}

class PainInjuryLimitation {
  final String bodyArea;
  final String status;
  final String? note;
  final DateTime? updatedAt;

  const PainInjuryLimitation({
    required this.bodyArea,
    required this.status,
    this.note,
    this.updatedAt,
  });

  factory PainInjuryLimitation.fromJson(Map<String, dynamic> json) {
    return PainInjuryLimitation(
      bodyArea:
          _readRequiredString(json, 'body_area', 'PainInjuryLimitation'),
      status: _readRequiredString(json, 'status', 'PainInjuryLimitation'),
      note: _readNullableString(json['note']),
      updatedAt: _readNullableDate(json['updated_at'], 'PainInjuryLimitation.updated_at'),
    );
  }

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{
      'body_area': bodyArea,
      'status': status,
      if (note != null) 'note': note,
      if (updatedAt != null)
        'updated_at': _formatDate(updatedAt!),
    };
    return json;
  }
}

class RiskScreen {
  final YesNoUnknown? underage;
  final YesNoUnknown? pregnancyOrPostpartum;
  final YesNoUnknown? recentSurgeryOrMajorInjury;
  final YesNoUnknown? majorChronicCondition;
  final YesNoUnknown? eatingDisorderConcern;
  final YesNoUnknown? professionalInstructionLimitations;

  const RiskScreen({
    this.underage,
    this.pregnancyOrPostpartum,
    this.recentSurgeryOrMajorInjury,
    this.majorChronicCondition,
    this.eatingDisorderConcern,
    this.professionalInstructionLimitations,
  });

  factory RiskScreen.fromJson(Map<String, dynamic> json) {
    return RiskScreen(
      underage: _parseYesNoUnknown(json['underage'], 'RiskScreen.underage'),
      pregnancyOrPostpartum: _parseYesNoUnknown(
          json['pregnancy_or_postpartum'], 'RiskScreen.pregnancy_or_postpartum'),
      recentSurgeryOrMajorInjury: _parseYesNoUnknown(
          json['recent_surgery_or_major_injury'],
          'RiskScreen.recent_surgery_or_major_injury'),
      majorChronicCondition: _parseYesNoUnknown(
          json['major_chronic_condition'], 'RiskScreen.major_chronic_condition'),
      eatingDisorderConcern: _parseYesNoUnknown(
          json['eating_disorder_concern'], 'RiskScreen.eating_disorder_concern'),
      professionalInstructionLimitations: _parseYesNoUnknown(
          json['professional_instruction_limitations'],
          'RiskScreen.professional_instruction_limitations'),
    );
  }

  Map<String, dynamic> toJson() => {
        'underage': underage?.wire,
        'pregnancy_or_postpartum': pregnancyOrPostpartum?.wire,
        'recent_surgery_or_major_injury': recentSurgeryOrMajorInjury?.wire,
        'major_chronic_condition': majorChronicCondition?.wire,
        'eating_disorder_concern': eatingDisorderConcern?.wire,
        'professional_instruction_limitations':
            professionalInstructionLimitations?.wire,
      };
}

class Allergy {
  final String label;
  final String? note;

  const Allergy({required this.label, this.note});

  factory Allergy.fromJson(Map<String, dynamic> json) {
    return Allergy(
      label: _readRequiredString(json, 'label', 'Allergy'),
      note: _readNullableString(json['note']),
    );
  }

  Map<String, dynamic> toJson() => {
        'label': label,
        if (note != null) 'note': note,
      };
}

class DietExclusion {
  final String item;
  final String? note;

  const DietExclusion({required this.item, this.note});

  factory DietExclusion.fromJson(Map<String, dynamic> json) {
    return DietExclusion(
      item: _readRequiredString(json, 'item', 'DietExclusion'),
      note: _readNullableString(json['note']),
    );
  }

  Map<String, dynamic> toJson() => {
        'item': item,
        if (note != null) 'note': note,
      };
}

/// Deterministic profile readiness tier. An unknown value MUST NOT be coerced
/// to `ready`; it surfaces as a parse error.
enum ReadinessTier {
  ready,
  missingRequiredData,
  restricted;

  static ReadinessTier? tryParse(Object? raw) {
    if (raw is! String) return null;
    switch (raw) {
      case 'ready':
        return ReadinessTier.ready;
      case 'missing_required_data':
        return ReadinessTier.missingRequiredData;
      case 'restricted':
        return ReadinessTier.restricted;
      default:
        return null;
    }
  }
}

class HealthReadiness {
  final ReadinessTier readiness;
  final String riskVersion;
  final String reason;
  final List<String> missingFields;
  final String? restrictedReason;

  const HealthReadiness({
    required this.readiness,
    required this.riskVersion,
    required this.reason,
    required this.missingFields,
    required this.restrictedReason,
  });

  factory HealthReadiness.fromJson(Map<String, dynamic> json) {
    final tier = ReadinessTier.tryParse(json['readiness']);
    if (tier == null) {
      throw const FormatException(
        'HealthReadiness: unknown readiness tier value',
      );
    }
    final rawMissing = json['missing_fields'];
    if (rawMissing is! List) {
      throw const FormatException(
        'HealthReadiness: `missing_fields` must be a list',
      );
    }
    final missingFields = rawMissing.map((e) {
      if (e is! String) {
        throw const FormatException(
          'HealthReadiness: missing_fields entries must be strings',
        );
      }
      return e;
    }).toList(growable: false);
    return HealthReadiness(
      readiness: tier,
      riskVersion:
          _readRequiredString(json, 'risk_version', 'HealthReadiness'),
      reason: _readRequiredString(json, 'reason', 'HealthReadiness'),
      missingFields: missingFields,
      restrictedReason: _readNullableString(json['restricted_reason']),
    );
  }
}

/// The stored health profile (backend HealthProfileResponse). Optional fields
/// are nullable: missing stays missing.
class HealthProfile {
  final String id;
  final FitnessGoal? fitnessGoal;
  final TrainingExperience? trainingExperience;
  final int? weeklyFrequency;
  final SessionDurationMinutes? sessionDurationMinutes;
  final Equipment? equipment;
  final List<PainInjuryLimitation>? painInjuryLimitations;
  final RiskScreen? riskScreen;
  final List<Allergy>? allergies;
  final List<DietExclusion>? dietExclusions;
  final List<FoodAllergenCode>? foodAllergenCodes;
  final List<ExcludedFoodCode>? excludedFoodCodes;
  final int version;
  final DateTime? updatedAt;
  final DateTime createdAt;

  const HealthProfile({
    required this.id,
    required this.fitnessGoal,
    required this.trainingExperience,
    required this.weeklyFrequency,
    required this.sessionDurationMinutes,
    required this.equipment,
    required this.painInjuryLimitations,
    required this.riskScreen,
    required this.allergies,
    required this.dietExclusions,
    required this.foodAllergenCodes,
    required this.excludedFoodCodes,
    required this.version,
    required this.updatedAt,
    required this.createdAt,
  });

  factory HealthProfile.fromJson(Map<String, dynamic> json) {
    return HealthProfile(
      id: _readRequiredString(json, 'id', 'HealthProfile'),
      fitnessGoal:
          _parseNullableEnum<FitnessGoal>(json['fitness_goal'], FitnessGoal.tryParse, 'HealthProfile.fitness_goal'),
      trainingExperience: _parseNullableEnum<TrainingExperience>(
          json['training_experience'], TrainingExperience.tryParse, 'HealthProfile.training_experience'),
      weeklyFrequency: _readNullableInt(json['weekly_frequency'], 'HealthProfile.weekly_frequency'),
      sessionDurationMinutes: _parseNullableSessionDuration(
          json['session_duration_minutes'], 'HealthProfile.session_duration_minutes'),
      equipment: _parseNullableEquipment(json['equipment']),
      painInjuryLimitations:
          _parseNullableList(json['pain_injury_limitations'], 'HealthProfile.pain_injury_limitations',
              (e) => PainInjuryLimitation.fromJson(_readJsonObject(e, 'HealthProfile.pain_injury_limitations'))),
      riskScreen: _parseNullableRiskScreen(json['risk_screen']),
      allergies: _parseNullableList(json['allergies'], 'HealthProfile.allergies',
          (e) => Allergy.fromJson(_readJsonObject(e, 'HealthProfile.allergies'))),
      dietExclusions: _parseNullableList(json['diet_exclusions'], 'HealthProfile.diet_exclusions',
          (e) => DietExclusion.fromJson(_readJsonObject(e, 'HealthProfile.diet_exclusions'))),
      foodAllergenCodes: _parseNullableEnumList(
        json['food_allergen_codes'],
        'HealthProfile.food_allergen_codes',
        FoodAllergenCode.tryParse,
      ),
      excludedFoodCodes: _parseNullableEnumList(
        json['excluded_food_codes'],
        'HealthProfile.excluded_food_codes',
        ExcludedFoodCode.tryParse,
      ),
      version: _readRequiredNonNegativeInt(json, 'version', 'HealthProfile'),
      updatedAt: _readNullableDateTime(json['updated_at'], 'HealthProfile.updated_at'),
      createdAt: _readRequiredDateTime(json, 'created_at', 'HealthProfile'),
    );
  }
}

/// GET / PUT /api/v1/health/profile envelope (backend HealthProfileResultResponse).
/// `configured` is false and `profile` is null when no profile exists yet (an
/// explicit not-configured state; no defaults are fabricated).
class HealthProfileResult {
  final bool configured;
  final HealthProfile? profile;
  final HealthReadiness readiness;

  const HealthProfileResult({
    required this.configured,
    required this.profile,
    required this.readiness,
  });

  factory HealthProfileResult.fromJson(Map<String, dynamic> json) {
    final configuredRaw = json['configured'];
    if (configuredRaw is! bool) {
      throw const FormatException(
        'HealthProfileResult: `configured` must be a bool',
      );
    }
    final rawReadiness = json['readiness'];
    if (rawReadiness is! Map<String, dynamic>) {
      throw const FormatException(
        'HealthProfileResult: missing required `readiness` object',
      );
    }
    HealthProfile? profile;
    final rawProfile = json['profile'];
    if (rawProfile != null) {
      if (rawProfile is! Map<String, dynamic>) {
        throw const FormatException(
          'HealthProfileResult: `profile` must be an object when present',
        );
      }
      profile = HealthProfile.fromJson(rawProfile);
    }
    return HealthProfileResult(
      configured: configuredRaw,
      profile: profile,
      readiness: HealthReadiness.fromJson(rawReadiness),
    );
  }
}

/// PUT /api/v1/health/profile request body (backend HealthProfileUpdate).
/// Full-replacement payload: every editable field is carried; null means the
/// field is cleared to missing. Server-managed fields (id, version, timestamps)
/// are never sent.
class HealthProfileUpdate {
  final FitnessGoal? fitnessGoal;
  final TrainingExperience? trainingExperience;
  final int? weeklyFrequency;
  final SessionDurationMinutes? sessionDurationMinutes;
  final Equipment? equipment;
  final List<PainInjuryLimitation>? painInjuryLimitations;
  final RiskScreen? riskScreen;
  final List<Allergy>? allergies;
  final List<DietExclusion>? dietExclusions;
  final List<FoodAllergenCode>? foodAllergenCodes;
  final List<ExcludedFoodCode>? excludedFoodCodes;

  const HealthProfileUpdate({
    this.fitnessGoal,
    this.trainingExperience,
    this.weeklyFrequency,
    this.sessionDurationMinutes,
    this.equipment,
    this.painInjuryLimitations,
    this.riskScreen,
    this.allergies,
    this.dietExclusions,
    this.foodAllergenCodes,
    this.excludedFoodCodes,
  });

  Map<String, dynamic> toJson() => {
        'fitness_goal': fitnessGoal?.wire,
        'training_experience': trainingExperience?.wire,
        'weekly_frequency': weeklyFrequency,
        'session_duration_minutes': sessionDurationMinutes?.value,
        'equipment': equipment?.toJson(),
        'pain_injury_limitations':
            painInjuryLimitations?.map((e) => e.toJson()).toList(),
        'risk_screen': riskScreen?.toJson(),
        'allergies': allergies?.map((e) => e.toJson()).toList(),
        'diet_exclusions': dietExclusions?.map((e) => e.toJson()).toList(),
        'food_allergen_codes': foodAllergenCodes?.map((e) => e.wire).toList(),
        'excluded_food_codes': excludedFoodCodes?.map((e) => e.wire).toList(),
      };
}

// ---------------------------------------------------------------------------
// Parsing helpers (private; mirror app/lib/models/posture_profile.dart).
// Exceptions carry only field names / context, never raw payload values.
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

int _readRequiredNonNegativeInt(Map<String, dynamic> json, String key, String context) {
  final raw = json[key];
  if (raw is! int || raw < 0) {
    throw FormatException('$context: `$key` must be a non-negative integer');
  }
  return raw;
}

int? _readNullableInt(Object? raw, String context) {
  if (raw == null) return null;
  if (raw is int) return raw;
  throw FormatException('$context must be an integer when present');
}

bool? _readNullableBool(Object? raw, String context) {
  if (raw == null) return null;
  if (raw is bool) return raw;
  throw FormatException('$context must be a bool when present');
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

DateTime? _readNullableDateTime(Object? raw, String context) {
  if (raw == null) return null;
  if (raw is! String) {
    throw FormatException('$context must be a string when present');
  }
  final parsed = DateTime.tryParse(raw);
  if (parsed == null) {
    throw FormatException('$context: unparseable value');
  }
  return parsed;
}

DateTime? _readNullableDate(Object? raw, String context) {
  // Date-only fields ("YYYY-MM-DD"); DateTime.tryParse handles them.
  return _readNullableDateTime(raw, context);
}

Map<String, dynamic> _readJsonObject(Object? raw, String context) {
  if (raw is! Map<String, dynamic>) {
    throw FormatException('$context must contain a JSON object');
  }
  return raw;
}

T? _parseNullableEnum<T>(
    Object? raw, T? Function(Object?) tryParse, String context) {
  if (raw == null) return null;
  final value = tryParse(raw);
  if (value == null) {
    throw FormatException('$context: unknown enum value');
  }
  return value;
}

YesNoUnknown? _parseYesNoUnknown(Object? raw, String context) {
  if (raw == null) return null;
  final value = YesNoUnknown.tryParse(raw);
  if (value == null) {
    throw FormatException('$context: unknown yes/no/unknown value');
  }
  return value;
}

SessionDurationMinutes? _parseNullableSessionDuration(Object? raw, String context) {
  if (raw == null) return null;
  final value = SessionDurationMinutes.fromInt(raw);
  if (value == null) {
    throw FormatException('$context: unknown session_duration_minutes value');
  }
  return value;
}

Equipment? _parseNullableEquipment(Object? raw) {
  if (raw == null) return null;
  return Equipment.fromJson(_readJsonObject(raw, 'HealthProfile.equipment'));
}

RiskScreen? _parseNullableRiskScreen(Object? raw) {
  if (raw == null) return null;
  return RiskScreen.fromJson(_readJsonObject(raw, 'HealthProfile.risk_screen'));
}

List<T>? _parseNullableList<T>(
    Object? raw, String context, T Function(Object) mapper) {
  if (raw == null) return null;
  if (raw is! List) {
    throw FormatException('$context must be a list when present');
  }
  return raw.cast<Object>().map(mapper).toList(growable: false);
}

List<T>? _parseNullableEnumList<T>(
    Object? raw, String context, T? Function(Object?) tryParse) {
  if (raw == null) return null;
  if (raw is! List) {
    throw FormatException('$context must be a list when present');
  }
  final result = <T>[];
  for (final item in raw) {
    final parsed = tryParse(item);
    if (parsed == null) throw FormatException('$context: unknown enum value');
    if (result.contains(parsed)) {
      throw FormatException('$context must not contain duplicates');
    }
    result.add(parsed);
  }
  return List.unmodifiable(result);
}

String _formatDate(DateTime dt) {
  // yyyy-MM-dd (date-only fields like pain limitation updated_at).
  String two(int v) => v.toString().padLeft(2, '0');
  return '${dt.year}-${two(dt.month)}-${two(dt.day)}';
}
