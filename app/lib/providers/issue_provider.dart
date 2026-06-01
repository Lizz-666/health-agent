// app/lib/providers/issue_provider.dart
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../models/issue.dart';

class IssueState {
  final Map<String, List<IssueSummary>> issuesByCategory;
  final IssueDetail? currentDetail;
  final bool isLoading;
  final String? error;

  const IssueState({
    this.issuesByCategory = const {},
    this.currentDetail,
    this.isLoading = false,
    this.error,
  });

  IssueState copyWith({
    Map<String, List<IssueSummary>>? issuesByCategory,
    IssueDetail? currentDetail,
    bool? isLoading,
    String? error,
    bool clearError = false,
  }) =>
      IssueState(
        issuesByCategory: issuesByCategory ?? this.issuesByCategory,
        currentDetail: currentDetail ?? this.currentDetail,
        isLoading: isLoading ?? this.isLoading,
        error: clearError ? null : (error ?? this.error),
      );
}

class IssueNotifier extends StateNotifier<IssueState> {
  final ApiClient _api;

  IssueNotifier(this._api) : super(const IssueState());

  // 获取分类问题列表，缓存到 Map
  Future<void> fetchIssues(String? category) async {
    try {
      state = state.copyWith(isLoading: true, clearError: true);
      final queryParams = <String, dynamic>{};
      if (category != null) queryParams['category'] = category;
      final resp = await _api.dio.get('/posture/issues', queryParameters: queryParams.isEmpty ? null : queryParams);
      final list = (resp.data as List)
          .map((e) => IssueSummary.fromJson(e as Map<String, dynamic>))
          .toList();
      final key = category ?? 'all';
      final newMap = Map<String, List<IssueSummary>>.from(state.issuesByCategory);
      newMap[key] = list;
      state = state.copyWith(issuesByCategory: newMap, isLoading: false);
    } on DioException catch (e) {
      state = state.copyWith(
          isLoading: false,
          error: e.response?.data?['detail'] ?? '加载失败');
    }
  }

  Future<void> fetchDetail(String issueId) async {
    try {
      state = state.copyWith(isLoading: true, clearError: true);
      final resp = await _api.dio.get('/posture/issues/$issueId');
      final detail = IssueDetail.fromJson(resp.data as Map<String, dynamic>);
      state = state.copyWith(currentDetail: detail, isLoading: false);
    } on DioException catch (e) {
      state = state.copyWith(
          isLoading: false,
          error: e.response?.data?['detail'] ?? '加载失败');
    }
  }
}

final issueProvider = StateNotifierProvider<IssueNotifier, IssueState>((ref) {
  final api = ref.read(apiClientProvider);
  return IssueNotifier(api);
});
