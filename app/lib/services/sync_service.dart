// app/lib/services/sync_service.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/assessment_provider.dart';
import '../providers/issue_provider.dart';
import '../providers/posture_state_provider.dart';
import '../providers/user_provider.dart';

class SyncService {
  final Ref _ref;

  SyncService(this._ref);

  /// App 启动时调用：加载数据并同步
  Future<void> startupSync() async {
    // 1. 加载用户信息
    await _ref.read(userProvider.notifier).fetchProfile();
    // 2. 加载所有问题列表
    await _ref.read(issueProvider.notifier).fetchIssues(null);
    // 3. 加载评估历史
    await _ref.read(assessmentProvider.notifier).fetchHistory();
    // 4. 从历史聚合推导体态状态
    final history = _ref.read(assessmentProvider).history;
    _ref.read(postureStateProvider.notifier).rebuildFromHistory(history);
  }
}

final syncServiceProvider = Provider<SyncService>((ref) => SyncService(ref));
