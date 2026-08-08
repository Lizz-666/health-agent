// app/lib/providers/adaptive_review_provider.dart
//
// State + API surface for the Phase 7 weekly review snapshot
// (/api/v1/training/reviews/weeks/{week_index}).
//
// Hard contract (Task 2):
//  - GET (loadReview) is read-only and may load an existing snapshot; it never
//    POSTs. POST generation (generateReview) runs only after an explicit user
//    action and never automatically.
//  - Any real 404 / network failure / unknown stable code is treated as
//    `unavailable`. We never invent a local success payload, cached fallback,
//    fake review, or backend compatibility behavior.
//  - A 2xx that fails to parse, an unknown enum, or a missing required field
//    fails closed as `parseError`. Missing data is never counted as zero and
//    active rest is never labeled a failure.
//  - Weight trend is display / nutrition-refresh context only; it never
//    influences a training proposal here.
//  - No response payloads or health values are logged; errors carry only the
//    stable machine `code` and generic text.
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../core/idempotency_key.dart';
import '../models/adaptive_review.dart';

const adaptiveReviewTimezone = 'Asia/Shanghai';

enum ReviewPhase {
  idle,
  loading,
  data,
  notGenerated,
  notDue,
  stale,
  safetyBlocked,
  unavailable,
  parseError,
}

class AdaptiveReviewState {
  final ReviewPhase phase;
  final int weekIndex;
  final WeeklyReviewSnapshot? snapshot;
  final String? message;

  const AdaptiveReviewState({
    this.phase = ReviewPhase.idle,
    this.weekIndex = 1,
    this.snapshot,
    this.message,
  });

  AdaptiveReviewState copyWith({
    ReviewPhase? phase,
    int? weekIndex,
    WeeklyReviewSnapshot? snapshot,
    bool clearSnapshot = false,
    String? message,
    bool clearMessage = false,
  }) => AdaptiveReviewState(
    phase: phase ?? this.phase,
    weekIndex: weekIndex ?? this.weekIndex,
    snapshot: clearSnapshot ? null : (snapshot ?? this.snapshot),
    message: clearMessage ? null : (message ?? this.message),
  );
}

const Set<String> _staleCodes = {
  'stale_context',
  'stale_plan_version',
  'stale_session',
  'adjustment_version_stale',
};

const Set<String> _safetyCodes = {'restricted_no_plan', 'red_flag_stop'};

class AdaptiveReviewNotifier extends StateNotifier<AdaptiveReviewState> {
  final ApiClient _api;
  int _gen = 0;
  bool _generating = false;

  AdaptiveReviewNotifier(this._api) : super(const AdaptiveReviewState());

  // GET /training/reviews/weeks/{week} (read-only; never POSTs).
  Future<void> loadReview(int week) async {
    await _run(week, () => _api.dio.get('/training/reviews/weeks/$week'));
  }

  // POST /training/reviews/weeks/{week} (explicit user action only; never
  // runs automatically). Concurrent generation requests are ignored.
  Future<void> generateReview(int week) async {
    if (_generating) return;
    _generating = true;
    try {
      await _run(
        week,
        () => _api.dio.post(
          '/training/reviews/weeks/$week',
          data: {
            'iana_timezone': adaptiveReviewTimezone,
            'idempotency_key': newIdempotencyKey(),
          },
        ),
        isGenerate: true,
      );
    } finally {
      _generating = false;
    }
  }

  Future<void> _run(
    int week,
    Future<Response> Function() request, {
    bool isGenerate = false,
  }) async {
    if (week < 1 || week > 4) {
      state = AdaptiveReviewState(
        phase: ReviewPhase.parseError,
        weekIndex: state.weekIndex,
        message: '周序号无效',
      );
      return;
    }
    final gen = ++_gen;
    state = AdaptiveReviewState(
      phase: ReviewPhase.loading,
      weekIndex: week,
      snapshot: state.snapshot,
    );
    try {
      final resp = await request();
      if (!mounted || gen != _gen) return;
      final snapshot = WeeklyReviewSnapshot.fromJson(
        resp.data as Map<String, dynamic>,
      );
      if (snapshot.weekIndex != week) {
        throw const FormatException('review week does not match request');
      }
      if (gen != _gen) return;
      state = AdaptiveReviewState(
        phase: ReviewPhase.data,
        weekIndex: week,
        snapshot: snapshot,
      );
    } on DioException catch (e) {
      if (!mounted || gen != _gen) return;
      state = AdaptiveReviewState(
        phase: _mapPhase(e, isGenerate: isGenerate),
        weekIndex: week,
        message: _dioMessage(e),
      );
    } on FormatException {
      if (!mounted || gen != _gen) return;
      state = AdaptiveReviewState(
        phase: ReviewPhase.parseError,
        weekIndex: week,
        message: '数据解析异常',
      );
    } catch (_) {
      if (!mounted || gen != _gen) return;
      state = AdaptiveReviewState(
        phase: ReviewPhase.parseError,
        weekIndex: week,
        message: '数据解析异常',
      );
    }
  }

  // Map stable server codes to distinct fail-closed phases. Real 404 / network
  // / unknown code -> unavailable. Only the machine `code` is used; `detail` is
  // display text only.
  ReviewPhase _mapPhase(DioException e, {required bool isGenerate}) {
    final data = e.response?.data;
    final code = data is Map<String, dynamic> ? data['code'] as String? : null;
    if (code == 'review_not_generated' && !isGenerate) {
      return ReviewPhase.notGenerated;
    }
    if (code == 'review_not_due') return ReviewPhase.notDue;
    if (_staleCodes.contains(code)) return ReviewPhase.stale;
    if (_safetyCodes.contains(code)) return ReviewPhase.safetyBlocked;
    // Unrecognized code, real 404 without code, 5xx, network/timeout ->
    // unavailable. Never fabricated as data or safety.
    return ReviewPhase.unavailable;
  }
}

String? _dioMessage(DioException e) {
  final data = e.response?.data;
  if (data is Map<String, dynamic>) {
    final detail = data['detail'];
    if (detail is String && detail.trim().isNotEmpty) return detail.trim();
  }
  return null;
}

final adaptiveReviewProvider =
    StateNotifierProvider<AdaptiveReviewNotifier, AdaptiveReviewState>(
      (ref) => AdaptiveReviewNotifier(ref.read(apiClientProvider)),
    );
