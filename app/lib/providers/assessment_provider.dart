// app/lib/providers/assessment_provider.dart
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../core/idempotency_key.dart';
import '../models/assessment.dart';

/// Distinguishes a valid empty result from a network failure and a parse
/// failure. Required by Task 8B: a missing or malformed field must NOT be
/// silently downgraded to "no data" / "no problem".
enum LoadStatus { idle, loading, data, empty, networkError, parseError }

class AssessmentState {
  final SelfAssessResult? currentResult;
  final List<AssessmentRecord> history;
  final bool isLoading;
  final String? error;
  final LoadStatus status;

  const AssessmentState({
    this.currentResult,
    this.history = const [],
    this.isLoading = false,
    this.error,
    this.status = LoadStatus.idle,
  });

  AssessmentState copyWith({
    SelfAssessResult? currentResult,
    bool clearResult = false,
    List<AssessmentRecord>? history,
    bool? isLoading,
    String? error,
    bool clearError = false,
    LoadStatus? status,
  }) => AssessmentState(
    currentResult: clearResult ? null : (currentResult ?? this.currentResult),
    history: history ?? this.history,
    isLoading: isLoading ?? this.isLoading,
    error: clearError ? null : (error ?? this.error),
    status: status ?? this.status,
  );
}

class AssessmentNotifier extends StateNotifier<AssessmentState> {
  final ApiClient _api;

  AssessmentNotifier(this._api) : super(const AssessmentState());

  Future<SelfAssessResult?> submitSelfAssess(
    String issueId,
    int testIndex,
    String answer,
  ) async {
    try {
      state = state.copyWith(
        isLoading: true,
        clearError: true,
        status: LoadStatus.loading,
      );
      final resp = await _api.dio.post(
        '/posture/assess',
        data: {'issue_id': issueId, 'test_index': testIndex, 'answer': answer},
      );
      if (!mounted) return null;
      final result = SelfAssessResult.fromJson(
        resp.data as Map<String, dynamic>,
      );
      state = state.copyWith(
        currentResult: result,
        isLoading: false,
        status: LoadStatus.data,
      );
      return result;
    } on DioException catch (e) {
      if (!mounted) return null;
      final msg = _dioMessage(e) ?? '提交失败';
      state = state.copyWith(
        isLoading: false,
        error: msg,
        status: LoadStatus.networkError,
      );
      return null;
    } on FormatException catch (e) {
      if (!mounted) return null;
      state = state.copyWith(
        isLoading: false,
        error: '数据解析异常',
        status: LoadStatus.parseError,
      );
      // Surface the parsing detail only in debug; never show raw payload to
      // the user (privacy: response may carry health data).
      assert(() {
        // ignore: avoid_print
        print('submitSelfAssess parse error: ${e.message}');
        return true;
      }());
      return null;
    } catch (e) {
      if (!mounted) return null;
      state = state.copyWith(
        isLoading: false,
        error: '提交失败',
        status: LoadStatus.parseError,
      );
      return null;
    }
  }

  /// Submit a photo assessment. A fresh UUID v4 is generated once for this
  /// action. Dio's 401-token-refresh retry replays the original request body,
  /// so the same key survives a transport retry.
  Future<Map<String, dynamic>?> submitPhotoAssess(
    String issueId,
    List<String> photoKeys,
  ) async {
    if (state.isLoading) return null;
    final key = newIdempotencyKey();
    try {
      state = state.copyWith(
        isLoading: true,
        clearError: true,
        clearResult: true,
        status: LoadStatus.loading,
      );
      final resp = await _api.dio.post(
        '/posture/assess/photo',
        data: {
          'issue_id': issueId,
          'photo_keys': photoKeys,
          'idempotency_key': key,
        },
      );
      if (!mounted) return null;
      final parsed = SelfAssessResult.fromJson(
        resp.data as Map<String, dynamic>,
      );
      state = state.copyWith(isLoading: false, status: LoadStatus.data);
      return parsed.toJson();
    } on DioException catch (e) {
      if (!mounted) return null;
      final msg = _dioMessage(e) ?? '分析失败';
      state = state.copyWith(
        isLoading: false,
        error: msg,
        status: LoadStatus.networkError,
      );
      return null;
    } on FormatException catch (e) {
      if (!mounted) return null;
      state = state.copyWith(
        isLoading: false,
        error: '数据解析异常',
        status: LoadStatus.parseError,
      );
      assert(() {
        // ignore: avoid_print
        print('submitPhotoAssess parse error: ${e.message}');
        return true;
      }());
      return null;
    } catch (_) {
      if (!mounted) return null;
      state = state.copyWith(
        isLoading: false,
        error: '分析失败',
        status: LoadStatus.parseError,
      );
      return null;
    }
  }

  Future<void> fetchHistory({int limit = 20, int offset = 0}) async {
    try {
      state = state.copyWith(
        isLoading: true,
        clearError: true,
        status: LoadStatus.loading,
      );
      final resp = await _api.dio.get(
        '/posture/history',
        queryParameters: {'limit': limit, 'offset': offset},
      );
      if (!mounted) return;
      final raw = resp.data;
      if (raw is! List) {
        state = state.copyWith(
          isLoading: false,
          error: '数据解析异常',
          status: LoadStatus.parseError,
        );
        return;
      }
      // Parse strictly: a single malformed record surfaces as parseError,
      // never as a silently truncated list with fabricated timestamps.
      final List<AssessmentRecord> list;
      try {
        list = raw
            .map((e) => AssessmentRecord.fromJson(e as Map<String, dynamic>))
            .toList(growable: false);
      } on FormatException catch (e) {
        state = state.copyWith(
          isLoading: false,
          error: '数据解析异常',
          status: LoadStatus.parseError,
        );
        assert(() {
          // ignore: avoid_print
          print('fetchHistory parse error: ${e.message}');
          return true;
        }());
        return;
      }
      state = state.copyWith(
        history: list,
        isLoading: false,
        status: list.isEmpty ? LoadStatus.empty : LoadStatus.data,
      );
    } on DioException catch (e) {
      if (!mounted) return;
      final msg = _dioMessage(e) ?? '加载失败';
      state = state.copyWith(
        isLoading: false,
        error: msg,
        status: LoadStatus.networkError,
      );
    } catch (e) {
      if (!mounted) return;
      state = state.copyWith(
        isLoading: false,
        error: '数据解析异常',
        status: LoadStatus.parseError,
      );
    }
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

final assessmentProvider =
    StateNotifierProvider<AssessmentNotifier, AssessmentState>((ref) {
      final api = ref.read(apiClientProvider);
      return AssessmentNotifier(api);
    });
