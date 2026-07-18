// app/lib/providers/posture_profile_provider.dart
//
// State + API surface for the posture profile / priorities / goal confirm /
// safety signal flows (Task 8B, spec §9.2 / §10.5-§10.8).
//
// Hard contract:
//  - A valid empty profile/priorities response is distinguished from network
//    and parse failures via LoadStatus (empty != networkError != parseError).
//  - Unknown certainty/risk_tier enum values never fall back to normal/cautious
//    -- they surface as parseError.
//  - 409 stale_priority clears stale suggestion state, refreshes priorities
//    and exposes needsReconfirm=true; the original confirm is NEVER replayed.
//  - Successful safety-signal reporting invalidates the cached priorities and
//    refreshes profile + priorities so the old suggestion cannot be submitted.
//  - Each user action (confirm goals, report signal, analyze photo via the
//    assessment provider) generates exactly one idempotency_key, reused by
//    Dio's 401-refresh retry automatically.
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../core/idempotency_key.dart';
import '../models/posture_profile.dart';
import '../models/priority_suggestion.dart';
import '../models/safety_signal.dart';
import 'assessment_provider.dart' show LoadStatus;

/// Typed confirm-goal failures. Mirrors the backend's 4xx error codes plus
/// the local structural pre-checks (no network call wasted on bad input).
enum PostureConfirmError {
  invalidGoal,
  stalePriority,
  restrictedBlocked,
  redFlagBlocked,
  idempotencyConflict,
  idempotencyResultGone,
  notFound,
  network,
  parse,
}

enum SafetySignalError {
  invalidSignal,
  idempotencyConflict,
  resultGone,
  notFound,
  network,
  parse,
}

class PostureProfileState {
  final LoadStatus profileStatus;
  final PostureProfile? profile;

  final LoadStatus entryStatus;
  final PostureProfileEntry? entryDetail;

  final LoadStatus prioritiesStatus;
  final PrioritySuggestions? priorities;

  final LoadStatus confirmStatus;
  final ConfirmedGoals? confirmedGoals;
  final PostureConfirmError? confirmError;
  final String? confirmErrorMessage;

  /// Set after a 409 stale_priority (or after a successful safety-signal
  /// report) until priorities are freshly fetched and the user has had a
  /// chance to re-confirm. The previous suggestion_id/profile_version MUST
  /// NOT be reused while this is true.
  final bool needsReconfirm;

  final LoadStatus safetyStatus;
  final SafetySignalResult? lastSafetyResult;
  final SafetySignalError? safetyError;
  final String? safetyErrorMessage;

  final String? error;

  const PostureProfileState({
    this.profileStatus = LoadStatus.idle,
    this.profile,
    this.entryStatus = LoadStatus.idle,
    this.entryDetail,
    this.prioritiesStatus = LoadStatus.idle,
    this.priorities,
    this.confirmStatus = LoadStatus.idle,
    this.confirmedGoals,
    this.confirmError,
    this.confirmErrorMessage,
    this.needsReconfirm = false,
    this.safetyStatus = LoadStatus.idle,
    this.lastSafetyResult,
    this.safetyError,
    this.safetyErrorMessage,
    this.error,
  });

  PostureProfileState copyWith({
    LoadStatus? profileStatus,
    PostureProfile? profile,
    bool clearProfile = false,
    LoadStatus? entryStatus,
    PostureProfileEntry? entryDetail,
    bool clearEntryDetail = false,
    LoadStatus? prioritiesStatus,
    PrioritySuggestions? priorities,
    bool clearPriorities = false,
    LoadStatus? confirmStatus,
    ConfirmedGoals? confirmedGoals,
    bool clearConfirmedGoals = false,
    PostureConfirmError? confirmError,
    bool clearConfirmError = false,
    String? confirmErrorMessage,
    bool clearConfirmErrorMessage = false,
    bool? needsReconfirm,
    LoadStatus? safetyStatus,
    SafetySignalResult? lastSafetyResult,
    bool clearLastSafetyResult = false,
    SafetySignalError? safetyError,
    bool clearSafetyError = false,
    String? safetyErrorMessage,
    bool clearSafetyErrorMessage = false,
    String? error,
    bool clearError = false,
  }) => PostureProfileState(
    profileStatus: profileStatus ?? this.profileStatus,
    profile: clearProfile ? null : (profile ?? this.profile),
    entryStatus: entryStatus ?? this.entryStatus,
    entryDetail: clearEntryDetail ? null : (entryDetail ?? this.entryDetail),
    prioritiesStatus: prioritiesStatus ?? this.prioritiesStatus,
    priorities: clearPriorities ? null : (priorities ?? this.priorities),
    confirmStatus: confirmStatus ?? this.confirmStatus,
    confirmedGoals: clearConfirmedGoals
        ? null
        : (confirmedGoals ?? this.confirmedGoals),
    confirmError: clearConfirmError
        ? null
        : (confirmError ?? this.confirmError),
    confirmErrorMessage: clearConfirmErrorMessage
        ? null
        : (confirmErrorMessage ?? this.confirmErrorMessage),
    needsReconfirm: needsReconfirm ?? this.needsReconfirm,
    safetyStatus: safetyStatus ?? this.safetyStatus,
    lastSafetyResult: clearLastSafetyResult
        ? null
        : (lastSafetyResult ?? this.lastSafetyResult),
    safetyError: clearSafetyError ? null : (safetyError ?? this.safetyError),
    safetyErrorMessage: clearSafetyErrorMessage
        ? null
        : (safetyErrorMessage ?? this.safetyErrorMessage),
    error: clearError ? null : (error ?? this.error),
  );
}

class PostureProfileNotifier extends StateNotifier<PostureProfileState> {
  final ApiClient _api;
  int _profileGeneration = 0;
  int _entryGeneration = 0;
  int _prioritiesGeneration = 0;
  int _confirmGeneration = 0;

  PostureProfileNotifier(this._api) : super(const PostureProfileState());

  // ---------------- GET /posture/profile ----------------

  Future<void> fetchProfile() async {
    final generation = ++_profileGeneration;
    state = state.copyWith(
      profileStatus: LoadStatus.loading,
      clearProfile: true,
      clearError: true,
    );
    try {
      final resp = await _api.dio.get('/posture/profile');
      final profile = PostureProfile.fromJson(
        resp.data as Map<String, dynamic>,
      );
      if (generation != _profileGeneration) return;
      state = state.copyWith(
        profile: profile,
        profileStatus: profile.evaluatedIssues.isEmpty
            ? LoadStatus.empty
            : LoadStatus.data,
      );
    } on DioException catch (e) {
      if (generation != _profileGeneration) return;
      state = state.copyWith(
        profileStatus: LoadStatus.networkError,
        error: _dioMessage(e) ?? '加载档案失败',
      );
    } on FormatException catch (e) {
      if (generation != _profileGeneration) return;
      _reportParseError('fetchProfile: ${e.message}');
    } catch (_) {
      if (generation != _profileGeneration) return;
      _reportParseError('fetchProfile: unexpected error');
    }
  }

  // ---------------- GET /posture/profile/{issue_id} ----------------

  Future<void> fetchProfileEntry(String issueId) async {
    final generation = ++_entryGeneration;
    state = state.copyWith(
      entryStatus: LoadStatus.loading,
      clearEntryDetail: true,
      clearError: true,
    );
    try {
      final resp = await _api.dio.get('/posture/profile/$issueId');
      final entry = PostureProfileEntry.fromJson(
        resp.data as Map<String, dynamic>,
      );
      if (generation != _entryGeneration) return;
      state = state.copyWith(entryDetail: entry, entryStatus: LoadStatus.data);
    } on DioException catch (e) {
      if (generation != _entryGeneration) return;
      final code = _errorCode(e);
      if (e.response?.statusCode == 404 || code == 'issue_not_found') {
        state = state.copyWith(
          entryStatus: LoadStatus.empty,
          error: _dioMessage(e) ?? '未找到该问题的档案',
        );
      } else {
        state = state.copyWith(
          entryStatus: LoadStatus.networkError,
          error: _dioMessage(e) ?? '加载档案详情失败',
        );
      }
    } on FormatException catch (e) {
      if (generation != _entryGeneration) return;
      state = state.copyWith(
        entryStatus: LoadStatus.parseError,
        error: '数据解析异常',
      );
      assert(() {
        // ignore: avoid_print
        print('fetchProfileEntry parse error: ${e.message}');
        return true;
      }());
    } catch (_) {
      if (generation != _entryGeneration) return;
      state = state.copyWith(
        entryStatus: LoadStatus.parseError,
        error: '数据解析异常',
      );
    }
  }

  // ---------------- GET /posture/priorities ----------------

  /// Fetch priorities. [clearNeedsReconfirm] defaults to true for
  /// user-initiated refreshes (pull-to-refresh, screen entry): fresh
  /// suggestions mean the user can pick again. Internal callers
  /// (after stale_priority auto-refresh, after a safety-signal success)
  /// pass false so the "please re-confirm" hint survives the refresh.
  Future<void> fetchPriorities({bool clearNeedsReconfirm = true}) async {
    final generation = ++_prioritiesGeneration;
    state = state.copyWith(
      prioritiesStatus: LoadStatus.loading,
      clearPriorities: true,
      clearError: true,
    );
    try {
      final resp = await _api.dio.get('/posture/priorities');
      final suggestions = PrioritySuggestions.fromJson(
        resp.data as Map<String, dynamic>,
      );
      if (generation != _prioritiesGeneration) return;
      // Fresh priorities are now in hand. Only clear needsReconfirm when
      // the caller asked us to (user-initiated refresh); internal callers
      // preserve it so the UI can still explain why a re-pick is needed.
      state = state.copyWith(
        priorities: suggestions,
        prioritiesStatus:
            suggestions.normalCandidates.isEmpty &&
                suggestions.retestRequired.isEmpty &&
                suggestions.safetyBlocked.isEmpty
            ? LoadStatus.empty
            : LoadStatus.data,
        needsReconfirm: clearNeedsReconfirm ? false : state.needsReconfirm,
      );
    } on DioException catch (e) {
      if (generation != _prioritiesGeneration) return;
      state = state.copyWith(
        prioritiesStatus: LoadStatus.networkError,
        error: _dioMessage(e) ?? '加载优先级失败',
      );
    } on FormatException catch (e) {
      if (generation != _prioritiesGeneration) return;
      state = state.copyWith(
        prioritiesStatus: LoadStatus.parseError,
        error: '数据解析异常',
      );
      assert(() {
        // ignore: avoid_print
        print('fetchPriorities parse error: ${e.message}');
        return true;
      }());
    } catch (_) {
      if (generation != _prioritiesGeneration) return;
      state = state.copyWith(
        prioritiesStatus: LoadStatus.parseError,
        error: '数据解析异常',
      );
    }
  }

  // ---------------- POST /posture/goals/confirm ----------------

  /// Confirm 1..3 of the current normal-candidate goals. Generates one
  /// idempotency_key per call (Dio 401 retry reuses it automatically). On
  /// 409 stale_priority it clears stale suggestion state, refreshes
  /// priorities and exposes needsReconfirm=true without auto-replaying.
  Future<bool> confirmGoals(List<GoalInput> goals) async {
    if (state.confirmStatus == LoadStatus.loading) {
      return false;
    }
    final suggestions = state.priorities;
    if (suggestions == null) {
      state = state.copyWith(
        confirmStatus: LoadStatus.parseError,
        confirmError: PostureConfirmError.invalidGoal,
        confirmErrorMessage: '尚无可用的优先级建议，请先刷新',
      );
      return false;
    }

    final candidateIds = suggestions.normalCandidates
        .map((c) => c.issueId)
        .toSet();
    final localError = validateGoals(goals, candidateIds);
    if (localError != null) {
      state = state.copyWith(
        confirmStatus: LoadStatus.parseError,
        confirmError: PostureConfirmError.invalidGoal,
        confirmErrorMessage: _goalValidationMessage(localError),
      );
      return false;
    }

    // One fresh key per user action. Reused across Dio 401 retry.
    final idempotencyKey = newIdempotencyKey();
    final generation = ++_confirmGeneration;
    state = state.copyWith(
      confirmStatus: LoadStatus.loading,
      clearConfirmedGoals: true,
      clearConfirmError: true,
      clearConfirmErrorMessage: true,
      clearError: true,
    );

    try {
      final resp = await _api.dio.post(
        '/posture/goals/confirm',
        data: {
          'suggestion_id': suggestions.suggestionId,
          'profile_version': suggestions.profileVersion,
          'goals': goals.map((g) => g.toJson()).toList(),
          'idempotency_key': idempotencyKey,
        },
      );
      if (generation != _confirmGeneration) return false;
      _prioritiesGeneration++;
      state = state.copyWith(clearPriorities: true);
      final confirmed = ConfirmedGoals.fromJson(
        resp.data as Map<String, dynamic>,
      );
      state = state.copyWith(
        confirmedGoals: confirmed,
        confirmStatus: LoadStatus.data,
        needsReconfirm: false,
        clearPriorities: true,
      );
      return true;
    } on DioException catch (e) {
      if (generation != _confirmGeneration) return false;
      final code = _errorCode(e);
      final message = _dioMessage(e) ?? '确认失败';
      final typed = _mapConfirmError(e.response?.statusCode, code);
      if (typed == PostureConfirmError.stalePriority) {
        // Do NOT auto-replay the confirm. Clear stale suggestion state,
        // mark needsReconfirm and refresh priorities so the user can
        // re-pick from the current candidate set.
        _prioritiesGeneration++;
        state = state.copyWith(
          confirmStatus: LoadStatus.parseError,
          confirmError: typed,
          confirmErrorMessage: message,
          needsReconfirm: true,
          clearPriorities: true,
        );
        await fetchPriorities(clearNeedsReconfirm: false);
      } else {
        state = state.copyWith(
          confirmStatus: typed == PostureConfirmError.network
              ? LoadStatus.networkError
              : LoadStatus.parseError,
          confirmError: typed,
          confirmErrorMessage: message,
        );
      }
      return false;
    } on FormatException catch (e) {
      if (generation != _confirmGeneration) return false;
      state = state.copyWith(
        confirmStatus: LoadStatus.parseError,
        confirmError: PostureConfirmError.parse,
        confirmErrorMessage: '数据解析异常',
      );
      assert(() {
        // ignore: avoid_print
        print('confirmGoals parse error: ${e.message}');
        return true;
      }());
      return false;
    } catch (_) {
      if (generation != _confirmGeneration) return false;
      state = state.copyWith(
        confirmStatus: LoadStatus.parseError,
        confirmError: PostureConfirmError.parse,
        confirmErrorMessage: '确认失败',
      );
      return false;
    }
  }

  // ---------------- POST /posture/safety-signals ----------------

  /// Report a structured safety signal. Generates one idempotency_key per
  /// call. On success, invalidates the cached priorities and refreshes
  /// profile + priorities so the previous suggestion can no longer be
  /// submitted (a new safety signal may reclassify the user's risk).
  Future<bool> reportSafetySignal(SafetySignalInput signal) async {
    if (state.safetyStatus == LoadStatus.loading) {
      return false;
    }
    final idempotencyKey = newIdempotencyKey();
    state = state.copyWith(
      safetyStatus: LoadStatus.loading,
      clearLastSafetyResult: true,
      clearSafetyError: true,
      clearSafetyErrorMessage: true,
      clearError: true,
    );
    try {
      final requestBody = signal.toJson()..['idempotency_key'] = idempotencyKey;
      final resp = await _api.dio.post(
        '/posture/safety-signals',
        data: requestBody,
      );
      _invalidateProfileReads();
      state = state.copyWith(
        profileStatus: LoadStatus.idle,
        clearProfile: true,
        entryStatus: LoadStatus.idle,
        clearEntryDetail: true,
        prioritiesStatus: LoadStatus.idle,
        clearPriorities: true,
        confirmStatus: LoadStatus.idle,
        clearConfirmError: true,
        clearConfirmErrorMessage: true,
        clearConfirmedGoals: true,
        needsReconfirm: true,
      );
      final result = SafetySignalResult.fromJson(
        resp.data as Map<String, dynamic>,
      );
      // New safety signal invalidates the previous suggestion_id and may
      // change risk classification. Clear cached priorities, mark
      // needsReconfirm, and refresh profile + priorities in parallel-safe
      // sequence (profile first so priorities recomputes against fresh
      // risk classification).
      state = state.copyWith(
        lastSafetyResult: result,
        safetyStatus: LoadStatus.data,
        needsReconfirm: true,
        clearPriorities: true,
        clearConfirmedGoals: true,
      );
      await fetchProfile();
      // Preserve needsReconfirm: a fresh safety signal invalidates any
      // prior suggestion_id; the user must explicitly re-confirm against
      // the new candidate set.
      await fetchPriorities(clearNeedsReconfirm: false);
      return true;
    } on DioException catch (e) {
      final code = _errorCode(e);
      final statusCode = e.response?.statusCode;
      SafetySignalError typed;
      if (statusCode == 400 && code == 'idempotency_key_conflict') {
        typed = SafetySignalError.idempotencyConflict;
      } else if (statusCode == 400) {
        typed = SafetySignalError.invalidSignal;
      } else if (statusCode == 410) {
        typed = SafetySignalError.resultGone;
      } else if (statusCode == 404) {
        typed = SafetySignalError.notFound;
      } else {
        typed = SafetySignalError.network;
      }
      state = state.copyWith(
        safetyStatus: typed == SafetySignalError.network
            ? LoadStatus.networkError
            : LoadStatus.parseError,
        safetyError: typed,
        safetyErrorMessage: _dioMessage(e) ?? '上报失败',
        error: _dioMessage(e) ?? '上报失败',
      );
      return false;
    } on FormatException catch (e) {
      state = state.copyWith(
        safetyStatus: LoadStatus.parseError,
        safetyError: SafetySignalError.parse,
        safetyErrorMessage: '数据解析异常',
      );
      assert(() {
        // ignore: avoid_print
        print('reportSafetySignal parse error: ${e.message}');
        return true;
      }());
      return false;
    } catch (_) {
      state = state.copyWith(
        safetyStatus: LoadStatus.parseError,
        safetyError: SafetySignalError.parse,
        safetyErrorMessage: '上报失败',
      );
      return false;
    }
  }

  void _reportParseError(String debugDetail) {
    state = state.copyWith(
      profileStatus: LoadStatus.parseError,
      error: '数据解析异常',
    );
    assert(() {
      // ignore: avoid_print
      print('posture_profile_provider $debugDetail');
      return true;
    }());
  }

  void _invalidateProfileReads() {
    _profileGeneration++;
    _entryGeneration++;
    _prioritiesGeneration++;
    _confirmGeneration++;
  }

  String _goalValidationMessage(GoalValidationError err) {
    switch (err) {
      case GoalValidationError.tooFew:
        return '请至少选择 1 个目标';
      case GoalValidationError.tooMany:
        return '最多只能选择 3 个目标';
      case GoalValidationError.duplicateIssue:
        return '目标问题不能重复';
      case GoalValidationError.duplicateRank:
        return '优先级排名不能重复';
      case GoalValidationError.rankNotConsecutive:
        return '优先级排名必须从 1 开始连续编号';
      case GoalValidationError.issueNotInCandidates:
        return '只能确认当前候选列表中的问题';
    }
  }

  PostureConfirmError _mapConfirmError(int? statusCode, String? code) {
    if (statusCode == 409) {
      switch (code) {
        case 'stale_priority':
          return PostureConfirmError.stalePriority;
        case 'restricted_blocked':
          return PostureConfirmError.restrictedBlocked;
        case 'red_flag_blocked':
          return PostureConfirmError.redFlagBlocked;
      }
    }
    if (statusCode == 400) {
      if (code == 'idempotency_key_conflict') {
        return PostureConfirmError.idempotencyConflict;
      }
      return PostureConfirmError.invalidGoal;
    }
    if (statusCode == 410) {
      return PostureConfirmError.idempotencyResultGone;
    }
    if (statusCode == 404) return PostureConfirmError.notFound;
    return PostureConfirmError.network;
  }
}

String? _errorCode(DioException e) {
  final data = e.response?.data;
  if (data is Map<String, dynamic>) {
    final code = (data['code'] as String?)?.trim();
    if (code != null && code.isNotEmpty) return code;
  }
  return null;
}

String? _dioMessage(DioException e) {
  final data = e.response?.data;
  if (data is Map<String, dynamic>) {
    final detail = (data['detail'] as String?)?.trim();
    if (detail != null && detail.isNotEmpty) return detail;
  }
  return null;
}

final postureProfileProvider =
    StateNotifierProvider<PostureProfileNotifier, PostureProfileState>((ref) {
      final api = ref.read(apiClientProvider);
      return PostureProfileNotifier(api);
    });
