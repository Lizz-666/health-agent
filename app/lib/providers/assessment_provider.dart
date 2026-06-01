// app/lib/providers/assessment_provider.dart
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../models/assessment.dart';

class AssessmentState {
  final SelfAssessResult? currentResult;
  final List<AssessmentRecord> history;
  final bool isLoading;
  final String? error;

  const AssessmentState({
    this.currentResult,
    this.history = const [],
    this.isLoading = false,
    this.error,
  });

  AssessmentState copyWith({
    SelfAssessResult? currentResult,
    List<AssessmentRecord>? history,
    bool? isLoading,
    String? error,
  }) =>
      AssessmentState(
        currentResult: currentResult ?? this.currentResult,
        history: history ?? this.history,
        isLoading: isLoading ?? this.isLoading,
        error: error ?? this.error,
      );
}

class AssessmentNotifier extends StateNotifier<AssessmentState> {
  final ApiClient _api;

  AssessmentNotifier(this._api) : super(const AssessmentState());

  Future<SelfAssessResult?> submitSelfAssess(String issueId, int testIndex, String answer) async {
    try {
      state = state.copyWith(isLoading: true);
      final resp = await _api.dio.post('/posture/assess', data: {
        'issue_id': issueId,
        'test_index': testIndex,
        'answer': answer,
      });
      final result = SelfAssessResult.fromJson(resp.data as Map<String, dynamic>);
      state = state.copyWith(currentResult: result, isLoading: false);
      return result;
    } on DioException catch (e) {
      state = state.copyWith(isLoading: false, error: e.response?.data?['detail'] ?? '提交失败');
      return null;
    }
  }

  Future<Map<String, dynamic>?> submitPhotoAssess(String issueId, List<String> photoKeys) async {
    try {
      state = state.copyWith(isLoading: true);
      final resp = await _api.dio.post('/posture/assess/photo', data: {
        'issue_id': issueId,
        'photo_keys': photoKeys,
      });
      state = state.copyWith(currentResult: null, isLoading: false);
      return resp.data as Map<String, dynamic>;
    } on DioException catch (e) {
      state = state.copyWith(isLoading: false, error: e.response?.data?['detail'] ?? '分析失败');
      return null;
    }
  }

  Future<void> fetchHistory({int limit = 20, int offset = 0}) async {
    try {
      state = state.copyWith(isLoading: true);
      final resp = await _api.dio.get('/posture/history', queryParameters: {'limit': limit, 'offset': offset});
      final list = (resp.data as List)
          .map((e) => AssessmentRecord.fromJson(e as Map<String, dynamic>))
          .toList();
      state = state.copyWith(history: list, isLoading: false);
    } on DioException catch (e) {
      state = state.copyWith(isLoading: false, error: e.response?.data?['detail'] ?? '加载失败');
    }
  }
}

final assessmentProvider = StateNotifierProvider<AssessmentNotifier, AssessmentState>((ref) {
  final api = ref.read(apiClientProvider);
  return AssessmentNotifier(api);
});
