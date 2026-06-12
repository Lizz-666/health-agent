// app/lib/services/sync_service.dart
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/assessment_provider.dart';
import '../providers/issue_provider.dart';
import '../providers/posture_state_provider.dart';
import '../providers/user_provider.dart';

class SyncService {
  final Ref _ref;

  SyncService(this._ref);

  Future<void> startupSync() async {
    try {
      await _ref.read(userProvider.notifier).fetchProfile();
    } catch (e) {
      debugPrint('Sync: fetchProfile failed: $e');
    }
    try {
      await _ref.read(issueProvider.notifier).fetchIssues(null);
    } catch (e) {
      debugPrint('Sync: fetchIssues failed: $e');
    }
    try {
      await _ref.read(assessmentProvider.notifier).fetchHistory();
    } catch (e) {
      debugPrint('Sync: fetchHistory failed: $e');
    }
    final history = _ref.read(assessmentProvider).history;
    _ref.read(postureStateProvider.notifier).rebuildFromHistory(history);
  }
}

final syncServiceProvider = Provider<SyncService>((ref) => SyncService(ref));
