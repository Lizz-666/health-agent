// app/lib/providers/posture_state_provider.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/assessment.dart';
import '../models/user_posture_state.dart';

class PostureStateNotifier extends StateNotifier<Map<String, UserPostureState>> {
  PostureStateNotifier() : super({});

  void updateState({
    required String issueId,
    required String result,
    required String method,
  }) {
    final newState = Map<String, UserPostureState>.from(state);
    newState[issueId] = UserPostureState(
      issueId: issueId,
      result: result,
      method: method,
      updatedAt: DateTime.now(),
      synced: false,
    );
    state = newState;
  }

  void rebuildFromHistory(List<AssessmentRecord> records) {
    final Map<String, List<AssessmentRecord>> grouped = {};
    for (final r in records) {
      grouped.putIfAbsent(r.issueId, () => []).add(r);
    }
    final newState = <String, UserPostureState>{};
    for (final entry in grouped.entries) {
      entry.value.sort((a, b) => b.createdAt.compareTo(a.createdAt));
      final latest = entry.value.first;
      newState[entry.key] = UserPostureState(
        issueId: entry.key,
        result: latest.result,
        method: latest.method,
        updatedAt: latest.createdAt,
        synced: true,
      );
    }
    state = newState;
  }

  void clearAll() => state = {};
}

final postureStateProvider =
    StateNotifierProvider<PostureStateNotifier, Map<String, UserPostureState>>(
        (_) => PostureStateNotifier());
