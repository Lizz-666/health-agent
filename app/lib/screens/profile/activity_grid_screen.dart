// app/lib/screens/profile/activity_grid_screen.dart
//
// Phase 2 activity grid My-page surface (spec Domain Model, Activity Grid).
//
// Safety / state contract (Task 6):
//  - This screen consumes activityGridProvider only.
//  - loading / networkError / parseError / data are visually distinct.
//  - Only the Phase 2 status set is rendered: none, checked_in, active_rest,
//    safety_adjustment. active_rest and safety_adjustment are valid,
//    non-failure engagement states (never styled as a missed/failure day).
//  - No plan-execution statuses are fabricated; the model already rejects
//    unknown values as a parse error.
//  - The grid carries no recommendation, judgment or adjustment text.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants.dart';
import '../../models/activity_grid.dart';
import '../../providers/activity_grid_provider.dart';
import '../../providers/assessment_provider.dart' show LoadStatus;
import '../../widgets/disclaimer_banner.dart';

class ActivityGridScreen extends ConsumerStatefulWidget {
  const ActivityGridScreen({super.key});

  @override
  ConsumerState<ActivityGridScreen> createState() =>
      _ActivityGridScreenState();
}

class _ActivityGridScreenState extends ConsumerState<ActivityGridScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      ref.read(activityGridProvider.notifier).fetchGrid();
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(activityGridProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('活动记录')),
      body: Column(
        children: [
          const DisclaimerBanner(),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: _ActivityGridBody(
                state: state,
                onRetry: () =>
                    ref.read(activityGridProvider.notifier).fetchGrid(),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ActivityGridBody extends StatelessWidget {
  final ActivityGridState state;
  final VoidCallback onRetry;
  const _ActivityGridBody({required this.state, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    final status = state.status;
    if (status == LoadStatus.idle || status == LoadStatus.loading) {
      return _box(
        child: Column(
          children: const [
            CircularProgressIndicator(),
            SizedBox(height: 12),
            Text(
              '加载活动记录中…',
              style: TextStyle(color: Color(AppConstants.textMuted)),
            ),
          ],
        ),
      );
    }
    if (status == LoadStatus.networkError) {
      return _box(
        child: _ErrorState(
          message: state.error ?? '活动记录加载失败',
          onRetry: onRetry,
        ),
      );
    }
    if (status == LoadStatus.parseError) {
      return _box(child: _ErrorState(message: '数据解析异常', onRetry: onRetry));
    }
    final grid = state.grid!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '记录范围：${_formatDate(grid.startDate)} ~ ${_formatDate(grid.endDate)}',
          style: const TextStyle(
            fontSize: 12,
            color: Color(AppConstants.textMuted),
          ),
        ),
        const SizedBox(height: 8),
        _Legend(),
        const SizedBox(height: 16),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final cell in grid.cells) _GridCell(cell: cell),
          ],
        ),
      ],
    );
  }
}

class _Legend extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return _box(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '图例',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: Color(AppConstants.textColor),
            ),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 12,
            runSpacing: 8,
            children: [
              for (final s in GridStatus.values) _LegendChip(status: s),
            ],
          ),
        ],
      ),
    );
  }
}

class _LegendChip extends StatelessWidget {
  final GridStatus status;
  const _LegendChip({required this.status});

  @override
  Widget build(BuildContext context) {
    final style = _styleOf(status);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(style.icon, size: 16, color: style.color),
        const SizedBox(width: 4),
        Text(
          style.label,
          style: TextStyle(fontSize: 12, color: style.color),
        ),
      ],
    );
  }
}

class _GridCell extends StatelessWidget {
  final ActivityGridCell cell;
  const _GridCell({required this.cell});

  @override
  Widget build(BuildContext context) {
    final style = _styleOf(cell.status);
    return Container(
      key: Key('grid-cell-${cell.date.toIso8601String()}'),
      width: 44,
      height: 44,
      decoration: BoxDecoration(
        color: style.color.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: style.color),
      ),
      child: Icon(style.icon, size: 18, color: style.color),
    );
  }
}

class _StatusStyle {
  final IconData icon;
  final Color color;
  final String label;
  const _StatusStyle(this.icon, this.color, this.label);
}

_StatusStyle _styleOf(GridStatus status) {
  switch (status) {
    case GridStatus.checkedIn:
      return const _StatusStyle(
        Icons.check_circle,
        Color(AppConstants.normalColor),
        '已签到',
      );
    case GridStatus.activeRest:
      return const _StatusStyle(
        Icons.self_improvement,
        Color(AppConstants.accentLight),
        '主动休息',
      );
    case GridStatus.safetyAdjustment:
      return const _StatusStyle(
        Icons.shield,
        Color(AppConstants.moderateColor),
        '安全调整',
      );
    case GridStatus.none:
      return const _StatusStyle(
        Icons.remove_circle_outline,
        Color(AppConstants.textMuted),
        '无',
      );
  }
}

class _ErrorState extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _ErrorState({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const Icon(
          Icons.error_outline,
          size: 40,
          color: Color(AppConstants.severeColor),
        ),
        const SizedBox(height: 8),
        Text(
          message,
          textAlign: TextAlign.center,
          style: const TextStyle(
            fontSize: 14,
            color: Color(AppConstants.textColor),
          ),
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          key: const Key('grid-retry'),
          onPressed: onRetry,
          icon: const Icon(Icons.refresh, size: 18),
          label: const Text('重试'),
        ),
      ],
    );
  }
}

Widget _box({required Widget child}) => Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(AppConstants.cardColor),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(AppConstants.glassBorder)),
      ),
      child: child,
    );

String _formatDate(DateTime dt) {
  String two(int v) => v.toString().padLeft(2, '0');
  return '${dt.year}-${two(dt.month)}-${two(dt.day)}';
}
