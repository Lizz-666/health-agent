// app/lib/providers/weight_trend_provider.dart
//
// State + API surface for GET /api/v1/health/trends/weight and weight-record
// CRUD (POST/GET/PUT/DELETE /api/v1/health/weight-records) (Phase 2 spec;
// backend WeightTrendResponse / WeightRecordResponse).
//
// Hard contract (Task 5):
//  - The trend view distinguishes valid empty/insufficient data from network
//    and parse failures via LoadStatus.
//  - A 2xx response that fails to parse clears stale state and surfaces as
//    parseError; stale data is never retained as current.
//  - Weight CRUD succeeds -> the trend is refreshed so the view stays
//    consistent; CRUD failures do not corrupt the cached trend.
//  - The trend never carries plan/diet adjustments or pass/fail judgment.
//  - No raw weight values are logged; parse errors carry only generic text.
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../models/weight_record.dart';
import 'assessment_provider.dart' show LoadStatus;

class WeightTrendState {
  final LoadStatus status;
  final WeightTrend? trend;
  final LoadStatus actionStatus;
  final String? error;
  final String? actionError;

  const WeightTrendState({
    this.status = LoadStatus.idle,
    this.trend,
    this.actionStatus = LoadStatus.idle,
    this.error,
    this.actionError,
  });

  WeightTrendState copyWith({
    LoadStatus? status,
    WeightTrend? trend,
    bool clearTrend = false,
    LoadStatus? actionStatus,
    String? error,
    bool clearError = false,
    String? actionError,
    bool clearActionError = false,
  }) =>
      WeightTrendState(
        status: status ?? this.status,
        trend: clearTrend ? null : (trend ?? this.trend),
        actionStatus: actionStatus ?? this.actionStatus,
        error: clearError ? null : (error ?? this.error),
        actionError: clearActionError ? null : (actionError ?? this.actionError),
      );
}

class WeightTrendNotifier extends StateNotifier<WeightTrendState> {
  final ApiClient _api;
  int _generation = 0;

  WeightTrendNotifier(this._api) : super(const WeightTrendState());

  // ---------------- GET /health/trends/weight ----------------
  Future<void> fetchTrend({
    DateTime? startDate,
    DateTime? endDate,
    int? window,
  }) async {
    final generation = ++_generation;
    state = state.copyWith(
      status: LoadStatus.loading,
      clearTrend: true,
      clearError: true,
    );
    try {
      final query = <String, dynamic>{
        if (startDate != null) 'start_date': _ymd(startDate),
        if (endDate != null) 'end_date': _ymd(endDate),
      };
      if (window != null) {
        query['window'] = window;
      }
      final resp = await _api.dio.get(
        '/health/trends/weight',
        queryParameters: query,
      );
      if (!mounted) return;
      final trend = WeightTrend.fromJson(resp.data as Map<String, dynamic>);
      if (generation != _generation) return;
      state = state.copyWith(trend: trend, status: LoadStatus.data);
    } on DioException catch (e) {
      if (!mounted) return;
      if (generation != _generation) return;
      state = state.copyWith(
        status: LoadStatus.networkError,
        error: _dioMessage(e) ?? '加载体重趋势失败',
      );
    } on FormatException {
      _reportParseError('fetchTrend', generation);
    } catch (_) {
      _reportParseError('fetchTrend', generation);
    }
  }

  // ---------------- POST /health/weight-records ----------------
  Future<bool> addWeight(WeightRecordInput input) async {
    state = state.copyWith(
      actionStatus: LoadStatus.loading,
      clearActionError: true,
    );
    try {
      await _api.dio.post('/health/weight-records', data: input.toJson());
      if (!mounted) return false;
      state = state.copyWith(actionStatus: LoadStatus.data);
      await fetchTrend();
      return true;
    } on DioException catch (e) {
      if (!mounted) return false;
      state = state.copyWith(
        actionStatus: LoadStatus.networkError,
        actionError: _dioMessage(e) ?? '添加体重记录失败',
      );
      return false;
    } catch (_) {
      if (!mounted) return false;
      state = state.copyWith(
        actionStatus: LoadStatus.parseError,
        actionError: '添加失败',
      );
      return false;
    }
  }

  // ---------------- PUT /health/weight-records/{id} ----------------
  Future<bool> updateWeight(String id, WeightRecordInput input) async {
    state = state.copyWith(
      actionStatus: LoadStatus.loading,
      clearActionError: true,
    );
    try {
      await _api.dio.put('/health/weight-records/$id', data: input.toJson());
      if (!mounted) return false;
      state = state.copyWith(actionStatus: LoadStatus.data);
      await fetchTrend();
      return true;
    } on DioException catch (e) {
      if (!mounted) return false;
      state = state.copyWith(
        actionStatus: LoadStatus.networkError,
        actionError: _dioMessage(e) ?? '更新体重记录失败',
      );
      return false;
    } catch (_) {
      if (!mounted) return false;
      state = state.copyWith(
        actionStatus: LoadStatus.parseError,
        actionError: '更新失败',
      );
      return false;
    }
  }

  // ---------------- DELETE /health/weight-records/{id} ----------------
  Future<bool> deleteWeight(String id) async {
    state = state.copyWith(
      actionStatus: LoadStatus.loading,
      clearActionError: true,
    );
    try {
      await _api.dio.delete('/health/weight-records/$id');
      if (!mounted) return false;
      state = state.copyWith(actionStatus: LoadStatus.data);
      await fetchTrend();
      return true;
    } on DioException catch (e) {
      if (!mounted) return false;
      state = state.copyWith(
        actionStatus: LoadStatus.networkError,
        actionError: _dioMessage(e) ?? '删除体重记录失败',
      );
      return false;
    } catch (_) {
      if (!mounted) return false;
      state = state.copyWith(
        actionStatus: LoadStatus.parseError,
        actionError: '删除失败',
      );
      return false;
    }
  }

  void _reportParseError(String where, int generation) {
    if (!mounted) return;
    if (generation != _generation) return;
    state = state.copyWith(
      status: LoadStatus.parseError,
      clearTrend: true,
      error: '数据解析异常',
    );
    assert(() {
      // ignore: avoid_print
      print('weight_trend_provider parse error in $where');
      return true;
    }());
  }
}

String _ymd(DateTime dt) {
  String two(int v) => v.toString().padLeft(2, '0');
  return '${dt.year}-${two(dt.month)}-${two(dt.day)}';
}

String? _dioMessage(DioException e) {
  final data = e.response?.data;
  if (data is Map<String, dynamic>) {
    final detail = (data['detail'] as String?)?.trim();
    if (detail != null && detail.isNotEmpty) return detail;
  }
  return null;
}

final weightTrendProvider =
    StateNotifierProvider<WeightTrendNotifier, WeightTrendState>((ref) {
  final api = ref.read(apiClientProvider);
  return WeightTrendNotifier(api);
});
