// app/lib/providers/daily_checkin_provider.dart
//
// State + API surface for GET/PUT /api/v1/health/checkins/today and
// DELETE /api/v1/health/checkins/{id} (Phase 2 spec; backend
// CheckInTodayResultResponse / CheckInResponse).
//
// Hard contract (Task 5):
//  - A valid not-checked-in response (checked_in=false, checkin=null) is
//    distinguished from network and parse failures via LoadStatus.
//  - A 2xx response that fails to parse clears stale state and surfaces as
//    parseError; a red_flag / restricted / caution state can never be silently
//    downgraded to normal (the model throws on unknown risk_summary).
//  - fetchToday() defaults to the device's local date when none is passed.
//  - No raw health values are logged; parse errors carry only generic text.
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../models/daily_checkin.dart';
import 'assessment_provider.dart' show LoadStatus;

class DailyCheckInState {
  final LoadStatus status;
  final DailyCheckIn? checkin;
  final DateTime? viewedDate;
  final String? error;

  const DailyCheckInState({
    this.status = LoadStatus.idle,
    this.checkin,
    this.viewedDate,
    this.error,
  });

  DailyCheckInState copyWith({
    LoadStatus? status,
    DailyCheckIn? checkin,
    bool clearCheckin = false,
    DateTime? viewedDate,
    String? error,
    bool clearError = false,
  }) =>
      DailyCheckInState(
        status: status ?? this.status,
        checkin: clearCheckin ? null : (checkin ?? this.checkin),
        viewedDate: viewedDate ?? this.viewedDate,
        error: clearError ? null : (error ?? this.error),
      );
}

class DailyCheckInNotifier extends StateNotifier<DailyCheckInState> {
  final ApiClient _api;
  int _generation = 0;

  DailyCheckInNotifier(this._api) : super(const DailyCheckInState());

  // ---------------- GET /health/checkins/today ----------------
  Future<void> fetchToday({DateTime? localDate}) async {
    final generation = ++_generation;
    final date = localDate ?? DateTime.now();
    state = state.copyWith(
      status: LoadStatus.loading,
      clearCheckin: true,
      viewedDate: date,
      clearError: true,
    );
    try {
      final resp = await _api.dio.get(
        '/health/checkins/today',
        queryParameters: {'local_date': _ymd(date)},
      );
      if (!mounted) return;
      final result = DailyCheckInTodayResult.fromJson(
        resp.data as Map<String, dynamic>,
      );
      if (generation != _generation) return;
      state = state.copyWith(
        checkin: result.checkin,
        status: result.checkedIn ? LoadStatus.data : LoadStatus.empty,
      );
    } on DioException catch (e) {
      if (!mounted) return;
      if (generation != _generation) return;
      state = state.copyWith(
        status: LoadStatus.networkError,
        error: _dioMessage(e) ?? '加载今日签到失败',
      );
    } on FormatException {
      _reportParseError('fetchToday', generation);
    } catch (_) {
      _reportParseError('fetchToday', generation);
    }
  }

  // ---------------- PUT /health/checkins/today ----------------
  Future<bool> saveToday(CheckInCreate input) async {
    final generation = ++_generation;
    state = state.copyWith(
      status: LoadStatus.loading,
      clearCheckin: true,
      viewedDate: input.localDate,
      clearError: true,
    );
    try {
      final resp =
          await _api.dio.put('/health/checkins/today', data: input.toJson());
      if (!mounted) return false;
      final checkin = DailyCheckIn.fromJson(resp.data as Map<String, dynamic>);
      if (generation != _generation) return false;
      state = state.copyWith(
        checkin: checkin,
        status: LoadStatus.data,
      );
      return true;
    } on DioException catch (e) {
      if (!mounted) return false;
      if (generation != _generation) return false;
      state = state.copyWith(
        status: LoadStatus.networkError,
        error: _dioMessage(e) ?? '保存签到失败',
      );
      return false;
    } on FormatException {
      _reportParseError('saveToday', generation);
      return false;
    } catch (_) {
      _reportParseError('saveToday', generation);
      return false;
    }
  }

  // ---------------- DELETE /health/checkins/{id} ----------------
  Future<bool> deleteCheckin(String id) async {
    try {
      await _api.dio.delete('/health/checkins/$id');
      if (!mounted) return false;
      // If the deleted check-in was the one currently in view, clear it.
      if (state.checkin?.id == id) {
        state = state.copyWith(clearCheckin: true, status: LoadStatus.empty);
      }
      return true;
    } on DioException catch (e) {
      if (!mounted) return false;
      state = state.copyWith(
        status: LoadStatus.networkError,
        error: _dioMessage(e) ?? '删除签到失败',
      );
      return false;
    } catch (_) {
      if (!mounted) return false;
      state = state.copyWith(status: LoadStatus.parseError, error: '删除失败');
      return false;
    }
  }

  void _reportParseError(String where, int generation) {
    if (!mounted) return;
    if (generation != _generation) return;
    state = state.copyWith(
      status: LoadStatus.parseError,
      clearCheckin: true,
      error: '数据解析异常',
    );
    assert(() {
      // ignore: avoid_print
      print('daily_checkin_provider parse error in $where');
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

final dailyCheckinProvider =
    StateNotifierProvider<DailyCheckInNotifier, DailyCheckInState>((ref) {
  final api = ref.read(apiClientProvider);
  return DailyCheckInNotifier(api);
});
