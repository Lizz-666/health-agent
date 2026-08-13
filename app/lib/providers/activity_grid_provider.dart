// app/lib/providers/activity_grid_provider.dart
//
// State + API surface for GET /api/v1/health/activity-grid (Phase 2 spec;
// backend ActivityGridResponse).
//
// Hard contract (Task 5):
//  - A valid all-none grid is distinguished from network and parse failures
//    via LoadStatus.
//  - A 2xx response that fails to parse clears stale state and surfaces as
//    parseError; an unknown status (e.g. a plan-execution value) can never be
//    silently coerced to `none` (the model throws -> parseError).
//  - No raw health values are logged; parse errors carry only generic text.
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../models/activity_grid.dart';
import 'assessment_provider.dart' show LoadStatus;

class ActivityGridState {
  final LoadStatus status;
  final ActivityGrid? grid;
  final String? error;

  const ActivityGridState({
    this.status = LoadStatus.idle,
    this.grid,
    this.error,
  });

  ActivityGridState copyWith({
    LoadStatus? status,
    ActivityGrid? grid,
    bool clearGrid = false,
    String? error,
    bool clearError = false,
  }) =>
      ActivityGridState(
        status: status ?? this.status,
        grid: clearGrid ? null : (grid ?? this.grid),
        error: clearError ? null : (error ?? this.error),
      );
}

class ActivityGridNotifier extends StateNotifier<ActivityGridState> {
  final ApiClient _api;
  int _generation = 0;

  ActivityGridNotifier(this._api) : super(const ActivityGridState());

  // ---------------- GET /health/activity-grid ----------------
  Future<void> fetchGrid({DateTime? startDate, DateTime? endDate}) async {
    final generation = ++_generation;
    state = state.copyWith(
      status: LoadStatus.loading,
      clearGrid: true,
      clearError: true,
    );
    try {
      final query = <String, dynamic>{
        if (startDate != null) 'start_date': _ymd(startDate),
        if (endDate != null) 'end_date': _ymd(endDate),
      };
      final resp = await _api.dio.get(
        '/health/activity-grid',
        queryParameters: query,
      );
      if (!mounted) return;
      final grid = ActivityGrid.fromJson(resp.data as Map<String, dynamic>);
      if (generation != _generation) return;
      state = state.copyWith(grid: grid, status: LoadStatus.data);
    } on DioException catch (e) {
      if (!mounted) return;
      if (generation != _generation) return;
      state = state.copyWith(
        status: LoadStatus.networkError,
        error: _dioMessage(e) ?? '加载活动网格失败',
      );
    } on FormatException {
      _reportParseError('fetchGrid', generation);
    } catch (_) {
      _reportParseError('fetchGrid', generation);
    }
  }

  void _reportParseError(String where, int generation) {
    if (!mounted) return;
    if (generation != _generation) return;
    state = state.copyWith(
      status: LoadStatus.parseError,
      clearGrid: true,
      error: '数据解析异常',
    );
    assert(() {
      // ignore: avoid_print
      print('activity_grid_provider parse error in $where');
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

final activityGridProvider =
    StateNotifierProvider<ActivityGridNotifier, ActivityGridState>((ref) {
  final api = ref.read(apiClientProvider);
  return ActivityGridNotifier(api);
});
