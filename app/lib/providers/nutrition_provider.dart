import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../core/idempotency_key.dart';
import '../models/nutrition.dart';
import 'assessment_provider.dart' show LoadStatus;

const nutritionTimezone = 'Asia/Shanghai';

class NutritionState {
  final LoadStatus status;
  final NutritionEligibility? eligibility;
  final NutritionTargetsResponse? targets;
  final List<NutritionFood> foods;
  final NutritionRecommendation? draft;
  final NutritionRecommendation? active;
  final NutritionRecommendation? replacementPreview;
  final ReplacementSelection? replacementSelection;
  final String? error;
  final String? errorCode;

  const NutritionState({
    this.status = LoadStatus.idle,
    this.eligibility,
    this.targets,
    this.foods = const [],
    this.draft,
    this.active,
    this.replacementPreview,
    this.replacementSelection,
    this.error,
    this.errorCode,
  });

  NutritionState copyWith({
    LoadStatus? status,
    NutritionEligibility? eligibility,
    NutritionTargetsResponse? targets,
    List<NutritionFood>? foods,
    NutritionRecommendation? draft,
    NutritionRecommendation? active,
    NutritionRecommendation? replacementPreview,
    ReplacementSelection? replacementSelection,
    String? error,
    String? errorCode,
    bool clearDraft = false,
    bool clearActive = false,
    bool clearPreview = false,
    bool clearError = false,
  }) => NutritionState(
    status: status ?? this.status,
    eligibility: eligibility ?? this.eligibility,
    targets: targets ?? this.targets,
    foods: foods ?? this.foods,
    draft: clearDraft ? null : (draft ?? this.draft),
    active: clearActive ? null : (active ?? this.active),
    replacementPreview: clearPreview
        ? null
        : (replacementPreview ?? this.replacementPreview),
    replacementSelection: clearPreview
        ? null
        : (replacementSelection ?? this.replacementSelection),
    error: clearError ? null : (error ?? this.error),
    errorCode: clearError ? null : (errorCode ?? this.errorCode),
  );
}

class NutritionNotifier extends StateNotifier<NutritionState> {
  final ApiClient _api;
  int _generation = 0;

  NutritionNotifier(this._api) : super(const NutritionState());

  Future<void> load() async {
    final generation = ++_generation;
    state = const NutritionState(status: LoadStatus.loading);
    try {
      final responses = await Future.wait([
        _api.dio.get(
          '/nutrition/eligibility',
          queryParameters: {'iana_timezone': nutritionTimezone},
        ),
        _api.dio.get('/nutrition/foods'),
      ]);
      final eligibility = NutritionEligibility.fromJson(
        _json(responses[0].data, 'eligibility'),
      );
      final foodList = NutritionFoodList.fromJson(
        _json(responses[1].data, 'foods'),
      );
      if (foodList.catalogVersion != eligibility.versions.catalogVersion) {
        throw const FormatException('nutrition catalog version mismatch');
      }
      if (!mounted || generation != _generation) return;

      NutritionTargetsResponse? targets;
      NutritionRecommendation? draft;
      NutritionRecommendation? active;
      if (eligibility.gate.allowsRecommendation) {
        final eligibleResponses = await Future.wait([
          _api.dio.get(
            '/nutrition/targets',
            queryParameters: {'iana_timezone': nutritionTimezone},
          ),
          _api.dio.get(
            '/nutrition/recommendations/draft',
            queryParameters: {'iana_timezone': nutritionTimezone},
          ),
          _api.dio.get(
            '/nutrition/recommendations/active',
            queryParameters: {'iana_timezone': nutritionTimezone},
          ),
        ]);
        targets = NutritionTargetsResponse.fromJson(
          _json(eligibleResponses[0].data, 'targets'),
        );
        if (targets.gate != eligibility.gate) {
          throw const FormatException('nutrition gate changed during load');
        }
        final draftResult = RecommendationResult.fromJson(
          _json(eligibleResponses[1].data, 'draft'),
        );
        final activeResult = RecommendationResult.fromJson(
          _json(eligibleResponses[2].data, 'active'),
        );
        draft = draftResult.recommendation;
        active = activeResult.recommendation;
        if (draft != null && draft.status != RecommendationStatus.draft) {
          throw const FormatException('draft endpoint returned non-draft');
        }
        if (active != null && active.status != RecommendationStatus.active) {
          throw const FormatException('active endpoint returned non-active');
        }
      }
      if (!mounted || generation != _generation) return;
      state = NutritionState(
        status: LoadStatus.data,
        eligibility: eligibility,
        targets: targets,
        foods: foodList.foods,
        draft: draft,
        active: active,
      );
    } on DioException catch (error) {
      _networkFailure(error, generation);
    } on FormatException {
      _parseFailure(generation);
    } catch (_) {
      _parseFailure(generation);
    }
  }

  Future<bool> createDraft() async {
    final generation = ++_generation;
    state = state.copyWith(status: LoadStatus.loading, clearError: true);
    try {
      final response = await _api.dio.post(
        '/nutrition/recommendations/drafts',
        data: {
          'idempotency_key': newIdempotencyKey(),
          'iana_timezone': nutritionTimezone,
        },
      );
      final result = RecommendationResult.fromJson(
        _json(response.data, 'draft'),
      );
      final draft = result.recommendation;
      if (draft == null || draft.status != RecommendationStatus.draft) {
        throw const FormatException('draft operation returned invalid result');
      }
      if (!mounted || generation != _generation) return false;
      state = state.copyWith(
        status: LoadStatus.data,
        draft: draft,
        clearPreview: true,
        clearError: true,
      );
      return true;
    } on DioException catch (error) {
      return _operationFailure(error, generation);
    } on FormatException {
      _parseFailure(generation);
      return false;
    } catch (_) {
      _parseFailure(generation);
      return false;
    }
  }

  Future<bool> confirmDraft() async {
    final draft = state.draft;
    if (draft == null || draft.status != RecommendationStatus.draft) {
      return false;
    }
    final generation = ++_generation;
    state = state.copyWith(status: LoadStatus.loading, clearError: true);
    try {
      final response = await _api.dio.post(
        '/nutrition/recommendations/${draft.recommendationId}:confirm',
        data: {
          'idempotency_key': newIdempotencyKey(),
          'iana_timezone': nutritionTimezone,
          'expected_version': draft.version,
          'expected_fingerprint': draft.payload.sourceContextFingerprint,
        },
      );
      final result = RecommendationResult.fromJson(
        _json(response.data, 'confirm'),
      );
      final active = result.recommendation;
      if (active == null || active.status != RecommendationStatus.active) {
        throw const FormatException('confirm operation returned non-active');
      }
      if (!mounted || generation != _generation) return false;
      state = state.copyWith(
        status: LoadStatus.data,
        active: active,
        clearDraft: true,
        clearPreview: true,
        clearError: true,
      );
      return true;
    } on DioException catch (error) {
      return _operationFailure(error, generation);
    } on FormatException {
      _parseFailure(generation);
      return false;
    } catch (_) {
      _parseFailure(generation);
      return false;
    }
  }

  Future<bool> previewReplacement(ReplacementSelection selection) async {
    final active = state.active;
    if (active == null || active.status != RecommendationStatus.active) {
      return false;
    }
    final generation = ++_generation;
    state = state.copyWith(
      status: LoadStatus.loading,
      clearPreview: true,
      clearError: true,
    );
    try {
      final response = await _api.dio.post(
        '/nutrition/recommendations/${active.recommendationId}/replacements:preview',
        data: selection.toJson(active: active, timezone: nutritionTimezone),
      );
      final result = RecommendationResult.fromJson(
        _json(response.data, 'preview'),
      );
      final preview = result.recommendation;
      if (result.operationStatus != 'preview' ||
          preview == null ||
          preview.payload.replacementDiff == null) {
        throw const FormatException('replacement preview lacks diff');
      }
      if (!mounted || generation != _generation) return false;
      state = state.copyWith(
        status: LoadStatus.data,
        replacementPreview: preview,
        replacementSelection: selection,
        clearError: true,
      );
      return true;
    } on DioException catch (error) {
      return _operationFailure(error, generation);
    } on FormatException {
      _parseFailure(generation);
      return false;
    } catch (_) {
      _parseFailure(generation);
      return false;
    }
  }

  Future<bool> confirmReplacement() async {
    final active = state.active;
    final selection = state.replacementSelection;
    final preview = state.replacementPreview;
    if (active == null || selection == null || preview == null) return false;
    final generation = ++_generation;
    state = state.copyWith(status: LoadStatus.loading, clearError: true);
    try {
      final response = await _api.dio.post(
        '/nutrition/recommendations/${active.recommendationId}/replacements:confirm',
        data: selection.toJson(
          active: active,
          timezone: nutritionTimezone,
          idempotencyKey: newIdempotencyKey(),
        ),
      );
      final result = RecommendationResult.fromJson(
        _json(response.data, 'replacement'),
      );
      final replacement = result.recommendation;
      if (replacement == null ||
          replacement.status != RecommendationStatus.active) {
        throw const FormatException('replacement confirmation is not active');
      }
      if (!mounted || generation != _generation) return false;
      state = state.copyWith(
        status: LoadStatus.data,
        active: replacement,
        clearPreview: true,
        clearError: true,
      );
      return true;
    } on DioException catch (error) {
      return _operationFailure(error, generation);
    } on FormatException {
      _parseFailure(generation);
      return false;
    } catch (_) {
      _parseFailure(generation);
      return false;
    }
  }

  Future<bool> deleteNutritionData() async {
    final generation = ++_generation;
    try {
      final response = await _api.dio.delete('/nutrition/data');
      final json = _json(response.data, 'delete');
      if (json['status'] != 'deleted') {
        throw const FormatException('nutrition delete was not confirmed');
      }
      if (!mounted || generation != _generation) return false;
      state = const NutritionState(status: LoadStatus.idle);
      return true;
    } on DioException catch (error) {
      _networkFailure(error, generation);
      return false;
    } on FormatException {
      _parseFailure(generation);
      return false;
    }
  }

  void invalidateForProfileChange() {
    _generation++;
    state = const NutritionState();
  }

  bool _operationFailure(DioException error, int generation) {
    _networkFailure(error, generation);
    return false;
  }

  void _networkFailure(DioException error, int generation) {
    if (!mounted || generation != _generation) return;
    final detail = _errorDetail(error);
    const invalidatingCodes = {
      'nutrition_runtime_disabled',
      'nutrition_red_flag',
      'nutrition_restricted',
      'nutrition_limited_education',
      'nutrition_clarification_required',
      'stale_context',
      'invalid_recommendation_state',
    };
    if (invalidatingCodes.contains(detail.code)) {
      state = NutritionState(
        status: LoadStatus.networkError,
        error: detail.message,
        errorCode: detail.code,
      );
      return;
    }
    state = state.copyWith(
      status: LoadStatus.networkError,
      error: detail.message,
      errorCode: detail.code,
      clearPreview: true,
    );
  }

  void _parseFailure(int generation) {
    if (!mounted || generation != _generation) return;
    state = const NutritionState(
      status: LoadStatus.parseError,
      error: '营养建议数据异常，未显示为可用建议。',
    );
  }
}

Map<String, dynamic> _json(Object? raw, String context) {
  if (raw is! Map<String, dynamic>) {
    throw FormatException('$context response must be an object');
  }
  return raw;
}

({String message, String? code}) _errorDetail(DioException error) {
  final data = error.response?.data;
  if (data is Map<String, dynamic>) {
    final detail = data['detail'];
    final code = data['code'];
    return (
      message: detail is String && detail.trim().isNotEmpty
          ? detail
          : '营养建议加载失败，请稍后重试。',
      code: code is String ? code : null,
    );
  }
  return (message: '网络不可用，请检查连接后重试。', code: null);
}

final nutritionProvider =
    StateNotifierProvider<NutritionNotifier, NutritionState>((ref) {
      return NutritionNotifier(ref.read(apiClientProvider));
    });
