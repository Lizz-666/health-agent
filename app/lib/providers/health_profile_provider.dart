// app/lib/providers/health_profile_provider.dart
//
// State + API surface for GET/PUT/DELETE /api/v1/health/profile (Phase 2
// spec; backend HealthProfileResultResponse).
//
// Hard contract (Task 5):
//  - A valid not-configured response (configured=false, profile=null) is
//    distinguished from network and parse failures via LoadStatus.
//  - A 2xx response that fails to parse clears stale state and surfaces as
//    parseError; stale data is never retained as current.
//  - Unknown readiness enum values never downgrade to `ready` (the model
//    throws FormatException -> parseError).
//  - No raw health values are logged; parse errors carry only generic text.
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../models/health_profile.dart';
import 'assessment_provider.dart' show LoadStatus;

class HealthProfileState {
  final LoadStatus status;
  final HealthProfileResult? result;
  final String? error;

  const HealthProfileState({
    this.status = LoadStatus.idle,
    this.result,
    this.error,
  });

  HealthProfileState copyWith({
    LoadStatus? status,
    HealthProfileResult? result,
    bool clearResult = false,
    String? error,
    bool clearError = false,
  }) =>
      HealthProfileState(
        status: status ?? this.status,
        result: clearResult ? null : (result ?? this.result),
        error: clearError ? null : (error ?? this.error),
      );
}

class HealthProfileNotifier extends StateNotifier<HealthProfileState> {
  final ApiClient _api;
  int _generation = 0;

  HealthProfileNotifier(this._api) : super(const HealthProfileState());

  // ---------------- GET /health/profile ----------------
  Future<void> fetchProfile() async {
    final generation = ++_generation;
    state = state.copyWith(
      status: LoadStatus.loading,
      clearResult: true,
      clearError: true,
    );
    try {
      final resp = await _api.dio.get('/health/profile');
      if (!mounted) return;
      final result = HealthProfileResult.fromJson(
        resp.data as Map<String, dynamic>,
      );
      if (generation != _generation) return;
      state = state.copyWith(
        result: result,
        status: result.configured ? LoadStatus.data : LoadStatus.empty,
      );
    } on DioException catch (e) {
      if (!mounted) return;
      if (generation != _generation) return;
      state = state.copyWith(
        status: LoadStatus.networkError,
        error: _dioMessage(e) ?? '加载健康档案失败',
      );
    } on FormatException {
      _reportParseError('fetchProfile', generation);
    } catch (_) {
      _reportParseError('fetchProfile', generation);
    }
  }

  // ---------------- PUT /health/profile ----------------
  Future<bool> updateProfile(HealthProfileUpdate input) async {
    final generation = ++_generation;
    state = state.copyWith(
      status: LoadStatus.loading,
      clearResult: true,
      clearError: true,
    );
    try {
      final resp = await _api.dio.put('/health/profile', data: input.toJson());
      if (!mounted) return false;
      final result = HealthProfileResult.fromJson(
        resp.data as Map<String, dynamic>,
      );
      if (generation != _generation) return false;
      state = state.copyWith(
        result: result,
        status: result.configured ? LoadStatus.data : LoadStatus.empty,
      );
      return true;
    } on DioException catch (e) {
      if (!mounted) return false;
      if (generation != _generation) return false;
      state = state.copyWith(
        status: LoadStatus.networkError,
        error: _dioMessage(e) ?? '保存健康档案失败',
      );
      return false;
    } on FormatException {
      _reportParseError('updateProfile', generation);
      return false;
    } catch (_) {
      _reportParseError('updateProfile', generation);
      return false;
    }
  }

  // ---------------- DELETE /health/profile ----------------
  Future<bool> deleteProfile() async {
    try {
      await _api.dio.delete('/health/profile');
      if (!mounted) return false;
      // Refresh so the not-configured state + empty-profile readiness is shown.
      await fetchProfile();
      return true;
    } on DioException catch (e) {
      if (!mounted) return false;
      state = state.copyWith(
        status: LoadStatus.networkError,
        error: _dioMessage(e) ?? '删除健康档案失败',
      );
      return false;
    } catch (_) {
      if (!mounted) return false;
      state = state.copyWith(
        status: LoadStatus.parseError,
        error: '删除失败',
      );
      return false;
    }
  }

  void _reportParseError(String where, int generation) {
    if (!mounted) return;
    if (generation != _generation) return;
    state = state.copyWith(
      status: LoadStatus.parseError,
      clearResult: true,
      error: '数据解析异常',
    );
    assert(() {
      // ignore: avoid_print
      print('health_profile_provider parse error in $where');
      return true;
    }());
  }
}

String? _dioMessage(DioException e) {
  final data = e.response?.data;
  if (data is Map<String, dynamic>) {
    final detail = (data['detail'] as String?)?.trim();
    if (detail != null && detail.isNotEmpty) return detail;
  }
  return null;
}

final healthProfileProvider =
    StateNotifierProvider<HealthProfileNotifier, HealthProfileState>((ref) {
  final api = ref.read(apiClientProvider);
  return HealthProfileNotifier(api);
});
