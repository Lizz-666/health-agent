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
    bool clearDetail = false,
    bool? isLoading,
    String? error,
    bool clearError = false,
  }) =>
      IssueState(
        issuesByCategory: issuesByCategory ?? this.issuesByCategory,
        currentDetail: clearDetail ? null : (currentDetail ?? this.currentDetail),
        isLoading: isLoading ?? this.isLoading,
        error: clearError ? null : (error ?? this.error),
      );
}

class IssueNotifier extends StateNotifier<IssueState> {
  final ApiClient _api;

  IssueNotifier(this._api) : super(const IssueState());

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
      final data = e.response?.data;
      final msg = (data is Map<String, dynamic>)
          ? (data['detail'] as String?) ?? '加载失败'
          : '加载失败';
      state = state.copyWith(isLoading: false, error: msg);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: '数据解析异常');
    }
  }

  Future<void> fetchDetail(String issueId) async {
    try {
      state = state.copyWith(isLoading: true, clearError: true, clearDetail: true);
      final resp = await _api.dio.get('/posture/issues/$issueId');
      final detail = IssueDetail.fromJson(resp.data as Map<String, dynamic>);
      state = state.copyWith(currentDetail: detail, isLoading: false);
    } on DioException catch (e) {
      final data = e.response?.data;
      final msg = (data is Map<String, dynamic>)
          ? (data['detail'] as String?) ?? '加载失败'
          : '加载失败';
      state = state.copyWith(isLoading: false, error: msg);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: '数据解析异常');
    }
  }
}

final issueProvider = StateNotifierProvider<IssueNotifier, IssueState>((ref) {
  final api = ref.read(apiClientProvider);
  return IssueNotifier(api);
});
