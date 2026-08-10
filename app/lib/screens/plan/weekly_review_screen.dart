// app/lib/screens/plan/weekly_review_screen.dart
//
// Phase 7 weekly review screen: a bounded week 1..4 immutable snapshot viewer.
//
// Hard contract (Task 2):
//  - GET (loadReview) may run on screen open / week selection; it never POSTs.
//    Generation POST runs only after an explicit button press, never
//    automatically.
//  - Real 404 / network / unknown-code responses render as an explicit
//    `unavailable` state. We never fabricate a review or count missing data as
//    zero.
//  - Facts render before proposals. Active-rest and safety-adjustment are
//    valid non-failure engagement states. A draft is distinct from a proposal
//    or an active version and must say it still requires the existing separate
//    confirmation flow (no draft is activated here).
//  - Weight trend is display / nutrition-refresh context only and never
//    influences a training proposal. Posture recheck is an ordinary reminder
//    and never hides safety UI.
//  - Unknown enums / malformed bodies fail closed as `parseError`. No response
//    payloads or health values are logged.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants.dart';
import '../../models/adaptive_review.dart';
import '../../providers/adaptive_review_provider.dart';

class WeeklyReviewScreen extends ConsumerStatefulWidget {
  const WeeklyReviewScreen({super.key});

  @override
  ConsumerState<WeeklyReviewScreen> createState() => _WeeklyReviewScreenState();
}

class _WeeklyReviewScreenState extends ConsumerState<WeeklyReviewScreen> {
  int _week = 1;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      // Read-only load on open. Generation is explicit only (see _generate).
      ref.read(adaptiveReviewProvider.notifier).loadReview(_week);
    });
  }

  void _selectWeek(int week) {
    if (week == _week) return;
    setState(() => _week = week);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      ref.read(adaptiveReviewProvider.notifier).loadReview(week);
    });
  }

  Future<void> _generate() async {
    await ref.read(adaptiveReviewProvider.notifier).generateReview(_week);
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(adaptiveReviewProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('周回顾')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [_weekSelector(), const SizedBox(height: 16), _body(state)],
        ),
      ),
    );
  }

  Widget _weekSelector() {
    return SegmentedButton<int>(
      segments: [
        ButtonSegment(
          value: 1,
          label: Text('第1周', key: const Key('review-week-1')),
        ),
        ButtonSegment(
          value: 2,
          label: Text('第2周', key: const Key('review-week-2')),
        ),
        ButtonSegment(
          value: 3,
          label: Text('第3周', key: const Key('review-week-3')),
        ),
        ButtonSegment(
          value: 4,
          label: Text('第4周', key: const Key('review-week-4')),
        ),
      ],
      selected: {_week},
      onSelectionChanged: (s) => _selectWeek(s.first),
      multiSelectionEnabled: false,
    );
  }

  Widget _body(AdaptiveReviewState state) {
    switch (state.phase) {
      case ReviewPhase.idle:
      case ReviewPhase.loading:
        return const _Panel(icon: Icons.hourglass_top, title: '加载周回顾中…');
      case ReviewPhase.notGenerated:
        return _Panel(
          key: const Key('review-not-generated'),
          icon: Icons.inbox_outlined,
          title: '本周尚未生成回顾',
          detail: '本周结束后可生成回顾。生成只会在你显式点击下方按钮后开始。',
          action: _generate,
          actionLabel: '生成本周回顾',
          actionKey: const Key('review-generate-button'),
        );
      case ReviewPhase.notDue:
        return const _Panel(
          key: Key('review-not-due'),
          icon: Icons.event_available,
          title: '本周尚未结束',
          detail: '回顾只能在计划周结束后生成。',
        );
      case ReviewPhase.stale:
        return _Panel(
          key: const Key('review-stale'),
          icon: Icons.sync_problem,
          title: '回顾上下文已变化',
          detail: '输入已更新，请重新生成。',
          action: _generate,
          actionLabel: '重新生成',
          actionKey: const Key('review-regenerate-button'),
        );
      case ReviewPhase.safetyBlocked:
        return const _Panel(
          key: Key('review-safety'),
          icon: Icons.block,
          title: '当前安全状态暂停回顾',
          detail: '存在安全风险信号，不会显示为成功。',
        );
      case ReviewPhase.unavailable:
        return _Panel(
          key: const Key('review-unavailable'),
          icon: Icons.cloud_off,
          title: '回顾暂不可用',
          detail: state.message ?? '服务暂不可用或尚未实现，请稍后重试。',
          action: () =>
              ref.read(adaptiveReviewProvider.notifier).loadReview(_week),
          actionLabel: '重试',
          actionKey: const Key('review-retry'),
        );
      case ReviewPhase.parseError:
        return const _Panel(
          key: Key('review-parse-error'),
          icon: Icons.broken_image_outlined,
          title: '回顾数据解析异常',
          detail: '不会显示为可用的回顾。',
        );
      case ReviewPhase.data:
        final s = state.snapshot!;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _FactsSection(snapshot: s),
            const SizedBox(height: 16),
            _ProposalsSection(
              snapshot: s,
              mutating: state.mutating,
              onCreateDraft: (code) async {
                await ref
                    .read(adaptiveReviewProvider.notifier)
                    .createDraft(code);
              },
            ),
          ],
        );
    }
  }
}

class _Panel extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? detail;
  final VoidCallback? action;
  final String? actionLabel;
  final Key? actionKey;

  const _Panel({
    super.key,
    required this.icon,
    required this.title,
    this.detail,
    this.action,
    this.actionLabel,
    this.actionKey,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: const Color(AppConstants.cardColor),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(AppConstants.glassBorder)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 40, color: const Color(AppConstants.textMuted)),
          const SizedBox(height: 12),
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          if (detail != null) ...[
            const SizedBox(height: 8),
            Text(
              detail!,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 13),
            ),
          ],
          if (action != null && actionLabel != null) ...[
            const SizedBox(height: 16),
            FilledButton(
              key: actionKey,
              onPressed: action,
              child: Text(actionLabel!),
            ),
          ],
        ],
      ),
    );
  }
}

class _FactsSection extends StatelessWidget {
  final WeeklyReviewSnapshot snapshot;
  const _FactsSection({required this.snapshot});

  @override
  Widget build(BuildContext context) {
    final e = snapshot.execution;
    return Container(
      key: const Key('review-facts'),
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(AppConstants.cardColor),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(AppConstants.glassBorder)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('本周执行事实', style: Theme.of(context).textTheme.titleMedium),
          if (snapshot.safety.blocked) ...[
            const SizedBox(height: 8),
            Container(
              key: const Key('review-snapshot-safety'),
              width: double.infinity,
              padding: const EdgeInsets.all(10),
              color: Colors.orange.withValues(alpha: 0.12),
              child: Text(
                '安全校验已阻止普通训练建议：${snapshot.safety.reasonCodes.join("、")}',
                style: const TextStyle(fontSize: 12),
              ),
            ),
          ],
          const SizedBox(height: 8),
          _row('计划场次', '${e.scheduled}'),
          _row('有效场次', '${e.effective}'),
          _row('完成', '${e.completed}'),
          _row('部分完成', '${e.partial}'),
          _row('太忙未练', '${e.tooBusy}'),
          _row('主动休息', '${e.activeRest}（有效状态）'),
          _row('安全调整', '${e.safetyAdjustment}（有效状态）'),
          _row('身体不适', '${e.discomfort}'),
          _row('记录不可用', '${e.unavailable}（不计为未完成）'),
          const Divider(),
          _row(
            '本周调整次数',
            '缩短 ${snapshot.adjustments.shortened} · 恢复 ${snapshot.adjustments.recovery} · '
                '延期 ${snapshot.adjustments.deferred} · 主动休息 ${snapshot.adjustments.activeRest} · '
                '未调整 ${snapshot.adjustments.unchanged} · 缺失 ${snapshot.adjustments.missing} · '
                '不可用 ${snapshot.adjustments.unavailable}',
          ),
          _row(
            '执行趋势',
            snapshot.executionTrend.available
                ? _executionTrendLabel(snapshot.executionTrend.direction)
                : '数据不足',
          ),
          Padding(
            key: const Key('review-weight-trend'),
            padding: const EdgeInsets.only(top: 6),
            child: _row(
              '体重趋势',
              snapshot.weightTrend.available
                  ? _weightTrendLabel(snapshot.weightTrend.direction)
                  : '数据不足',
            ),
          ),
          const Padding(
            padding: EdgeInsets.only(top: 2),
            child: Text(
              '体重趋势仅供参考，不影响训练建议。',
              style: TextStyle(
                fontSize: 11,
                color: Color(AppConstants.textMuted),
              ),
            ),
          ),
          _row('营养建议', _nutritionLabel(snapshot.nutrition)),
          _row('体态复检', _postureLabel(snapshot.posture)),
        ],
      ),
    );
  }

  Widget _row(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontSize: 12,
              color: Color(AppConstants.textMuted),
            ),
          ),
          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.right,
              style: const TextStyle(
                fontSize: 13,
                color: Color(AppConstants.textColor),
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _nutritionLabel(NutritionReviewState n) {
    final age = n.ageDays == null ? '' : '（已 ${n.ageDays} 天）';
    final refresh = n.refreshAvailable ? '；可请求刷新草案' : '';
    final unavailable = n.unavailableReason == null
        ? ''
        : '（${_unavailableReasonLabel(n.unavailableReason!)}）';
    return '${_nutritionStateLabel(n.state)}$age$refresh$unavailable';
  }

  String _postureLabel(PostureRecheckInfo p) {
    switch (p.status) {
      case PostureRecheckStatus.due:
        return '本周期待复检（普通提醒，不会隐藏安全信息）';
      case PostureRecheckStatus.notDue:
        return '暂未到期';
      case PostureRecheckStatus.comparisonAvailable:
        return '可比较（${_postureComparisonLabel(p.comparisonSignal)}）';
      case PostureRecheckStatus.unavailable:
        return '不可用${p.reason == null ? "" : "（${p.reason}）"}';
    }
  }
}

class _ProposalsSection extends StatelessWidget {
  final WeeklyReviewSnapshot snapshot;
  final bool mutating;
  final Future<void> Function(ReviewProposalCode code) onCreateDraft;
  const _ProposalsSection({
    required this.snapshot,
    required this.mutating,
    required this.onCreateDraft,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const Key('review-proposals'),
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(AppConstants.cardColor),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(AppConstants.glassBorder)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('建议', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          for (final p in snapshot.proposals) _proposalTile(p),
        ],
      ),
    );
  }

  Widget _proposalTile(ReviewProposal p) {
    final codeLabel = switch (p.code) {
      ReviewProposalCode.keepCurrentPlan => '保持当前计划',
      ReviewProposalCode.offerTrainingDraft => '可生成更保守的训练草案',
      ReviewProposalCode.offerNutritionRefresh => '可刷新饮食建议草案',
      ReviewProposalCode.postureRecheckDue => '体态复检已到期',
      ReviewProposalCode.postureComparisonAvailable => '体态对比可用',
      ReviewProposalCode.revisitGoal => '可重新考虑训练目标',
    };
    final (stateLabel, needsConfirm) = switch (p.state) {
      ReviewProposalState.proposal => ('建议', false),
      ReviewProposalState.draft => ('草案（尚未生效）', true),
      ReviewProposalState.active => ('已生效', false),
      ReviewProposalState.unavailable => ('不可用', false),
    };
    return Padding(
      key: Key('review-proposal-${p.code.wire}'),
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '· $codeLabel（$stateLabel）',
            style: const TextStyle(
              fontSize: 13,
              color: Color(AppConstants.textColor),
            ),
          ),
          if (p.strategy != null)
            Text(
              '  调整方向：${_reviewStrategyLabel(p.strategy!)}',
              style: const TextStyle(
                fontSize: 11,
                color: Color(AppConstants.textMuted),
              ),
            ),
          if (needsConfirm)
            const Text(
              '  创建/激活草案仍需通过现有的单独确认流程，回顾生成不会自动激活。',
              style: TextStyle(
                fontSize: 11,
                color: Color(AppConstants.textMuted),
              ),
            ),
          if (p.state == ReviewProposalState.proposal &&
              (p.code == ReviewProposalCode.offerTrainingDraft ||
                  p.code == ReviewProposalCode.offerNutritionRefresh)) ...[
            const SizedBox(height: 6),
            OutlinedButton(
              key: Key(
                p.code == ReviewProposalCode.offerTrainingDraft
                    ? 'review-create-training-draft'
                    : 'review-create-nutrition-draft',
              ),
              onPressed: mutating ? null : () => onCreateDraft(p.code),
              child: Text(
                p.code == ReviewProposalCode.offerTrainingDraft
                    ? '创建训练草案'
                    : '创建饮食草案',
              ),
            ),
          ],
        ],
      ),
    );
  }
}

String _executionTrendLabel(ExecutionTrendDirection? direction) =>
    switch (direction) {
      ExecutionTrendDirection.improving => '执行改善',
      ExecutionTrendDirection.steady => '执行稳定',
      ExecutionTrendDirection.declining => '执行下降',
      null => '未知',
    };

String _weightTrendLabel(WeightTrendDirection? direction) =>
    switch (direction) {
      WeightTrendDirection.rising => '上升',
      WeightTrendDirection.falling => '下降',
      WeightTrendDirection.stable => '稳定',
      null => '未知',
    };

String _nutritionStateLabel(NutritionRecommendationState state) =>
    switch (state) {
      NutritionRecommendationState.none => '暂无营养建议',
      NutritionRecommendationState.active => '营养建议已生效',
      NutritionRecommendationState.stale => '营养建议待更新',
      NutritionRecommendationState.unavailable => '营养建议不可用',
    };

String _unavailableReasonLabel(String reason) => switch (reason) {
  'nutrition_clarification_required' => '需要补充营养信息',
  'nutrition_restricted' => '当前安全状态受限',
  'nutrition_red_flag' => '已触发安全阻断',
  _ => '原因暂不可用',
};

String _postureComparisonLabel(PostureComparisonSignal? signal) =>
    switch (signal) {
      PostureComparisonSignal.added => '新增信号',
      PostureComparisonSignal.notDetected => '本次未检出',
      PostureComparisonSignal.unchanged => '无明显变化',
      PostureComparisonSignal.changed => '已有变化',
      null => '未知',
    };

String _reviewStrategyLabel(ReviewDraftStrategy strategy) => switch (strategy) {
  ReviewDraftStrategy.conservativeDuration => '保守缩短单次时长',
  ReviewDraftStrategy.lowerFrequency => '降低每周频次',
  ReviewDraftStrategy.progression => '逐步进阶',
  ReviewDraftStrategy.regression => '降低难度',
};
