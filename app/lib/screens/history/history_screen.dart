// app/lib/screens/history/history_screen.dart
//
// Task 8C history screen. Renders assessment records using the canonical
// `source` field from /posture/history (Task 8A). The legacy `method` field
// is not used as the display source; unknown source values surface as
// "其他来源" and NEVER impersonate AI.
//
// Safety contract (Task 8C, spec §9.1 / §15):
//  - A valid empty history (server returned []) and a loading failure are
//    rendered as distinct states. Failure MUST NOT look like "no records".
//  - When a refresh fails while a stale cached list is held by the provider,
//    the screen keeps the list AND surfaces an error banner at the top
//    (does not silently wipe data).
//  - Migrated to the current light theme; flat r=8 containers; no nested
//    cards; no decorative hero.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/constants.dart';
import '../../models/assessment.dart';
import '../../providers/assessment_provider.dart';
import '../../widgets/disclaimer_banner.dart';
import '../../widgets/posture_status_badge.dart';

/// Canonical source label for the history list. Unknown sources surface as
/// "其他来源" — they NEVER display as AI (spec §15: custom unknown sources
/// must not impersonate AI).
String historySourceLabel(String source) {
  switch (source) {
    case 'self_test':
      return '自测';
    case 'ai_photo':
      return 'AI 拍照分析';
    default:
      return '其他来源';
  }
}

class HistoryScreen extends ConsumerStatefulWidget {
  const HistoryScreen({super.key});

  @override
  ConsumerState<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends ConsumerState<HistoryScreen> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() {
      if (!mounted) return;
      ref.read(assessmentProvider.notifier).fetchHistory();
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(assessmentProvider);
    final status = state.status;
    final hasList = state.history.isNotEmpty;
    final showErrorBanner =
        hasList &&
        (status == LoadStatus.networkError || status == LoadStatus.parseError);

    // Group by date preserving chronological order.
    final grouped = <String, List<AssessmentRecord>>{};
    for (final r in state.history) {
      final key = DateFormat('yyyy-MM-dd').format(r.createdAt);
      grouped.putIfAbsent(key, () => []).add(r);
    }

    Widget body;
    if (state.isLoading && !hasList) {
      body = const Center(child: CircularProgressIndicator());
    } else if (!hasList) {
      if (status == LoadStatus.networkError) {
        body = _FullScreenStatus(
          icon: Icons.error_outline,
          color: const Color(AppConstants.severeColor),
          message: state.error ?? '加载失败',
          actionLabel: '重试',
          onAction: () => ref.read(assessmentProvider.notifier).fetchHistory(),
        );
      } else if (status == LoadStatus.parseError) {
        body = _FullScreenStatus(
          icon: Icons.broken_image_outlined,
          color: const Color(AppConstants.severeColor),
          message: '数据解析异常',
          actionLabel: '重试',
          onAction: () => ref.read(assessmentProvider.notifier).fetchHistory(),
        );
      } else {
        // Valid empty.
        body = _FullScreenStatus(
          icon: Icons.history,
          color: const Color(AppConstants.textMuted),
          message: '暂无评估记录',
          hint: '去首页开始你的第一次体态分析吧',
          actionLabel: '去首页',
          onAction: () => context.push('/'),
        );
      }
    } else {
      body = ListView(
        children: [
          if (showErrorBanner)
            _StaleListBanner(
              status: status,
              onRetry: () =>
                  ref.read(assessmentProvider.notifier).fetchHistory(),
            ),
          for (final entry in grouped.entries) ...[
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 6),
              child: Text(
                _formatDate(entry.key),
                style: const TextStyle(
                  fontSize: 13,
                  color: Color(AppConstants.textMuted),
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            for (final r in entry.value)
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 4,
                ),
                child: InkWell(
                  onTap: () => context.push(
                    '/issue/${r.issueId}/result',
                    extra: {
                      'assessmentId': r.id,
                      'result': r.result,
                      'suggestion': '',
                    },
                  ),
                  borderRadius: BorderRadius.circular(8),
                  child: Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(AppConstants.cardColor),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(
                        color: const Color(AppConstants.glassBorder),
                      ),
                    ),
                    child: Row(
                      children: [
                        AssessmentResultBadge(result: r.result, size: 12),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                r.issueName,
                                style: const TextStyle(
                                  fontSize: 14,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              Text(
                                historySourceLabel(r.source),
                                style: const TextStyle(
                                  fontSize: 12,
                                  color: Color(AppConstants.textMuted),
                                ),
                              ),
                            ],
                          ),
                        ),
                        Text(
                          DateFormat('HH:mm').format(r.createdAt),
                          style: const TextStyle(
                            color: Color(AppConstants.textMuted),
                            fontSize: 12,
                          ),
                        ),
                        const SizedBox(width: 4),
                        const Icon(
                          Icons.chevron_right,
                          color: Color(AppConstants.textMuted),
                          size: 18,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
          ],
          const SizedBox(height: 16),
        ],
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('评估历史')),
      body: Column(
        children: [
          Expanded(
            // RefreshIndicator wraps the body so pull-to-refresh works on
            // both the list and the full-screen empty/error states.
            child: RefreshIndicator(
              onRefresh: () async {
                await ref.read(assessmentProvider.notifier).fetchHistory();
              },
              child: body,
            ),
          ),
          const DisclaimerBanner(),
        ],
      ),
    );
  }

  String _formatDate(String dateStr) {
    final now = DateTime.now();
    final date = DateTime.tryParse(dateStr);
    if (date == null) return dateStr;
    if (DateFormat('yyyy-MM-dd').format(now) == dateStr) return '今天';
    if (DateFormat(
          'yyyy-MM-dd',
        ).format(now.subtract(const Duration(days: 1))) ==
        dateStr) {
      return '昨天';
    }
    return DateFormat('M月d日').format(date);
  }
}

class _StaleListBanner extends StatelessWidget {
  final LoadStatus status;
  final VoidCallback onRetry;
  const _StaleListBanner({required this.status, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(AppConstants.severeColor).withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(AppConstants.severeColor)),
      ),
      child: Row(
        children: [
          const Icon(
            Icons.error_outline,
            color: Color(AppConstants.severeColor),
            size: 18,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              status == LoadStatus.parseError
                  ? '部分最新记录解析失败，下方为已加载记录。'
                  : '最新记录加载失败，下方为已加载记录。',
              style: const TextStyle(
                color: Color(AppConstants.textColor),
                fontSize: 12,
              ),
            ),
          ),
          TextButton(onPressed: onRetry, child: const Text('重试')),
        ],
      ),
    );
  }
}

class _FullScreenStatus extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String message;
  final String? hint;
  final String? actionLabel;
  final VoidCallback? onAction;
  const _FullScreenStatus({
    required this.icon,
    required this.color,
    required this.message,
    this.hint,
    this.actionLabel,
    this.onAction,
  });

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        const SizedBox(height: 120),
        Center(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Column(
              children: [
                Icon(icon, size: 56, color: color),
                const SizedBox(height: 12),
                Text(
                  message,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: color,
                  ),
                ),
                if (hint != null) ...[
                  const SizedBox(height: 4),
                  Text(
                    hint!,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      color: Color(AppConstants.textMuted),
                      fontSize: 13,
                    ),
                  ),
                ],
                if (actionLabel != null && onAction != null) ...[
                  const SizedBox(height: 16),
                  OutlinedButton.icon(
                    onPressed: onAction,
                    icon: const Icon(Icons.refresh, size: 18),
                    label: Text(actionLabel!),
                  ),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}
