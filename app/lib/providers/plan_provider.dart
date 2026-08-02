// app/lib/providers/plan_provider.dart
//
// State + API surface for the Phase 4 training plan API
// (/api/v1/training/plans*). Mirrors backend service.py.
//
// Hard contract (Task 5):
//  - Per-flow LoadStatus for draft / active / today, each with its own
//    generation counter so a stale response can never overwrite a newer one.
//  - A 2xx response that fails to parse clears the affected flow's state and
//    surfaces as parseError; a blocked / restricted / red-flag result is never
//    coerced to a usable plan.
//  - The client renders server results and collects explicit confirmations /
//    feedback; no recommendation or safety logic lives here.
//  - No raw health values are logged; errors carry only generic text + the
//    server's structured detail/code.
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../models/plan.dart';
import 'assessment_provider.dart' show LoadStatus;
import 'nutrition_provider.dart';

class PlanState {
  final LoadStatus draftStatus;
  final LoadStatus activeStatus;
  final LoadStatus todayStatus;
  final PlanVersion? draft;
  final PlanVersion? activePlan;
  final TodayResult? today;
  final String? error;

  const PlanState({
    this.draftStatus = LoadStatus.idle,
    this.activeStatus = LoadStatus.idle,
    this.todayStatus = LoadStatus.idle,
    this.draft,
    this.activePlan,
    this.today,
    this.error,
  });

  PlanState copyWith({
    LoadStatus? draftStatus,
    LoadStatus? activeStatus,
    LoadStatus? todayStatus,
    PlanVersion? draft,
    bool clearDraft = false,
    PlanVersion? activePlan,
    bool clearActive = false,
    TodayResult? today,
    bool clearToday = false,
    String? error,
    bool clearError = false,
  }) =>
      PlanState(
        draftStatus: draftStatus ?? this.draftStatus,
        activeStatus: activeStatus ?? this.activeStatus,
        todayStatus: todayStatus ?? this.todayStatus,
        draft: clearDraft ? null : (draft ?? this.draft),
        activePlan: clearActive ? null : (activePlan ?? this.activePlan),
        today: clearToday ? null : (today ?? this.today),
        error: clearError ? null : (error ?? this.error),
      );
}

class PlanNotifier extends StateNotifier<PlanState> {
  final ApiClient _api;
  final void Function() _onPlanChanged;
  int _draftGen = 0;
  int _todayGen = 0;

  PlanNotifier(this._api, {void Function()? onPlanChanged})
      : _onPlanChanged = onPlanChanged ?? _noop,
        super(const PlanState());

  // POST /training/plans:draft
  Future<bool> generateDraft(DraftInput input) async {
    final gen = ++_draftGen;
    state = state.copyWith(
      draftStatus: LoadStatus.loading,
      clearDraft: true,
      clearError: true,
    );
    try {
      final resp = await _api.dio.post('/training/plans:draft', data: input.toJson());
      if (!mounted) return false;
      final result = DraftResult.fromJson(resp.data as Map<String, dynamic>);
      if (gen != _draftGen) return false;
      state = state.copyWith(
        draft: result.draft,
        draftStatus: result.hasDraft ? LoadStatus.data : LoadStatus.empty,
      );
      return result.hasDraft;
    } on DioException catch (e) {
      return _failDraft(e, gen);
    } on FormatException {
      _reportParseError('generateDraft', gen, flow: 'draft');
      return false;
    } catch (_) {
      _reportParseError('generateDraft', gen, flow: 'draft');
      return false;
    }
  }

  // GET /training/plans/draft
  Future<void> fetchDraft() async {
    final gen = ++_draftGen;
    state = state.copyWith(draftStatus: LoadStatus.loading, clearError: true);
    try {
      final resp = await _api.dio.get('/training/plans/draft');
      if (!mounted) return;
      final result = DraftResult.fromJson(resp.data as Map<String, dynamic>);
      if (gen != _draftGen) return;
      state = state.copyWith(
        draft: result.draft,
        draftStatus: result.hasDraft ? LoadStatus.data : LoadStatus.empty,
      );
    } on DioException catch (e) {
      _failDraft(e, gen);
    } on FormatException {
      _reportParseError('fetchDraft', gen, flow: 'draft');
    } catch (_) {
      _reportParseError('fetchDraft', gen, flow: 'draft');
    }
  }

  // POST /training/plans:confirm
  Future<bool> confirm(ConfirmInput input) async {
    state = state.copyWith(activeStatus: LoadStatus.loading, clearError: true);
    try {
      final resp = await _api.dio.post('/training/plans:confirm', data: input.toJson());
      if (!mounted) return false;
      final result = ActivePlanResult.fromJson({'has_active': true, 'plan': resp.data['plan']});
      state = state.copyWith(
        activePlan: result.plan,
        activeStatus: LoadStatus.data,
        clearDraft: true,
        draftStatus: LoadStatus.empty,
      );
      _onPlanChanged();
      return true;
    } on DioException catch (e) {
      if (!mounted) return false;
      state = state.copyWith(
        activeStatus: LoadStatus.networkError,
        error: _dioMessage(e) ?? '确认计划失败',
      );
      return false;
    } on FormatException {
      _reportParseError('confirm', 0, flow: 'active');
      return false;
    } catch (_) {
      _reportParseError('confirm', 0, flow: 'active');
      return false;
    }
  }

  // GET /training/plans/active
  Future<void> fetchActive() async {
    state = state.copyWith(activeStatus: LoadStatus.loading, clearError: true);
    try {
      final resp = await _api.dio.get('/training/plans/active');
      if (!mounted) return;
      final result = ActivePlanResult.fromJson(resp.data as Map<String, dynamic>);
      state = state.copyWith(
        activePlan: result.plan,
        activeStatus: result.hasActive ? LoadStatus.data : LoadStatus.empty,
      );
    } on DioException catch (e) {
      if (!mounted) return;
      state = state.copyWith(
        activeStatus: LoadStatus.networkError,
        error: _dioMessage(e) ?? '加载计划失败',
      );
    } on FormatException {
      _reportParseError('fetchActive', 0, flow: 'active');
    } catch (_) {
      _reportParseError('fetchActive', 0, flow: 'active');
    }
  }

  // GET /training/plans/today?iana_timezone=...
  Future<void> fetchToday(String ianaTimezone) async {
    final gen = ++_todayGen;
    state = state.copyWith(todayStatus: LoadStatus.loading, clearToday: true, clearError: true);
    try {
      final resp = await _api.dio.get(
        '/training/plans/today',
        queryParameters: {'iana_timezone': ianaTimezone},
      );
      if (!mounted) return;
      final result = TodayResult.fromJson(resp.data as Map<String, dynamic>);
      if (gen != _todayGen) return;
      state = state.copyWith(today: result, todayStatus: LoadStatus.data);
    } on DioException catch (e) {
      if (!mounted) return;
      if (gen != _todayGen) return;
      state = state.copyWith(
        todayStatus: LoadStatus.networkError,
        error: _dioMessage(e) ?? '加载今日训练失败',
      );
    } on FormatException {
      if (!mounted) return;
      if (gen != _todayGen) return;
      state = state.copyWith(
        todayStatus: LoadStatus.parseError,
        clearToday: true,
        error: '数据解析异常',
      );
    } catch (_) {
      if (!mounted) return;
      if (gen != _todayGen) return;
      state = state.copyWith(
        todayStatus: LoadStatus.parseError,
        clearToday: true,
        error: '数据解析异常',
      );
    }
  }

  // POST /training/plans/sessions/{id}:feedback
  Future<bool> recordFeedback(
      String sessionId, FeedbackInput input, String ianaTimezone) async {
    try {
      final resp = await _api.dio.post(
        '/training/plans/sessions/$sessionId:feedback',
        queryParameters: {'iana_timezone': ianaTimezone},
        data: input.toJson(),
      );
      if (!mounted) return false;
      FeedbackResult.fromJson(resp.data as Map<String, dynamic>);
      return true;
    } on DioException catch (e) {
      if (!mounted) return false;
      state = state.copyWith(error: _dioMessage(e) ?? '记录反馈失败');
      return false;
    } catch (_) {
      if (!mounted) return false;
      state = state.copyWith(error: '记录反馈失败');
      return false;
    }
  }

  // POST /training/plans/sessions/{id}:substitute
  Future<bool> recordSubstitution(
      String sessionId, SubstitutionInput input, String ianaTimezone) async {
    try {
      final resp = await _api.dio.post(
        '/training/plans/sessions/$sessionId:substitute',
        queryParameters: {'iana_timezone': ianaTimezone},
        data: input.toJson(),
      );
      if (!mounted) return false;
      SubstitutionResult.fromJson(resp.data as Map<String, dynamic>);
      // Refresh today so the substituted session is reflected.
      return true;
    } on DioException catch (e) {
      if (!mounted) return false;
      state = state.copyWith(error: _dioMessage(e) ?? '替换动作失败');
      return false;
    } catch (_) {
      if (!mounted) return false;
      state = state.copyWith(error: '替换动作失败');
      return false;
    }
  }

  bool _failDraft(DioException e, int gen) {
    if (!mounted) return false;
    if (gen != _draftGen) return false;
    state = state.copyWith(
      draftStatus: LoadStatus.networkError,
      error: _dioMessage(e) ?? '生成计划失败',
    );
    return false;
  }

  void _reportParseError(String where, int gen, {required String flow}) {
    if (!mounted) return;
    if (flow == 'draft' && gen != _draftGen) return;
    if (flow == 'draft') {
      state = state.copyWith(
        draftStatus: LoadStatus.parseError,
        clearDraft: true,
        error: '数据解析异常',
      );
    } else if (flow == 'active') {
      state = state.copyWith(
        activeStatus: LoadStatus.parseError,
        clearActive: true,
        error: '数据解析异常',
      );
    } else {
      state = state.copyWith(todayStatus: LoadStatus.parseError, error: '数据解析异常');
    }
    assert(() {
      // ignore: avoid_print
      print('plan_provider parse error in $where ($flow)');
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

final planProvider = StateNotifierProvider<PlanNotifier, PlanState>((ref) {
  final api = ref.read(apiClientProvider);
  return PlanNotifier(
    api,
    onPlanChanged: () => ref.invalidate(nutritionProvider),
  );
});

void _noop() {}
