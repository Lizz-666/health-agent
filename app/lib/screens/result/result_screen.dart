// app/lib/screens/result/result_screen.dart
//
// Task 8C result screen. Keeps the legacy result + suggestion + corrections
// + related-issues display, and additionally fetches
// GET /posture/profile/{issue_id} to render the server's certainty /
// sources / risk_tier alongside the legacy result string.
//
// Safety contract (Task 8C, spec §9.2 / §10.5 / §15):
//  - The legacy disclaimer ("本内容仅供参考…") is preserved.
//  - When the entry-detail fetch fails (networkError OR parseError), the UI
//    shows "档案状态暂不可用" + retry. It MUST NOT fall back to a "正常"
//    badge or empty state — the absence of a server profile is not a green
//    light.
//  - conflict entries surface "来源不一致" + "无合并结论" with per-source
//    severity and timestamp; no merging.
//  - combined_severity == null surfaces as "无合并结论".
//  - Migrated to the current light theme (GlassCard palette + AppConstants);
//    flat containers with r=8 corners; no nested cards; no decorative hero.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/constants.dart';
import '../../models/posture_profile.dart';
import '../../providers/assessment_provider.dart' show LoadStatus;
import '../../providers/issue_provider.dart';
import '../../providers/posture_profile_provider.dart';
import '../../widgets/disclaimer_banner.dart';
import '../../widgets/posture_status_badge.dart';

class ResultScreen extends ConsumerStatefulWidget {
  final String issueId;
  final String assessmentId;
  final String result;
  final String suggestion;

  const ResultScreen({
    super.key,
    required this.issueId,
    required this.assessmentId,
    required this.result,
    required this.suggestion,
  });

  @override
  ConsumerState<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends ConsumerState<ResultScreen> {
  bool _dialogShown = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      ref.read(issueProvider.notifier).fetchDetail(widget.issueId);
      ref
          .read(postureProfileProvider.notifier)
          .fetchProfileEntry(widget.issueId);
      if (widget.result == 'severe' && !_dialogShown) {
        _dialogShown = true;
        _showSevereDialog(context);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final currentDetail = ref.watch(issueProvider).currentDetail;
    final detail = currentDetail?.id == widget.issueId ? currentDetail : null;
    final profileState = ref.watch(postureProfileProvider);

    return Scaffold(
      key: const Key('result-screen'),
      appBar: AppBar(title: const Text('评估结果')),
      body: Column(
        children: [
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Top legacy result card.
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(24),
                    decoration: _flatBox(),
                    child: Column(
                      children: [
                        AssessmentResultBadge(result: widget.result, size: 22),
                        const SizedBox(height: 16),
                        Text(
                          widget.suggestion,
                          textAlign: TextAlign.center,
                          style: const TextStyle(fontSize: 16, height: 1.5),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  _EntryDetailSection(
                    state: profileState,
                    issueId: widget.issueId,
                    onRetry: () => ref
                        .read(postureProfileProvider.notifier)
                        .fetchProfileEntry(widget.issueId),
                  ),
                  // Corrections (legacy, only when moderate).
                  if (widget.result == 'moderate' && detail != null) ...[
                    const SizedBox(height: 16),
                    const Text(
                      '纠正建议',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    ...detail.corrections.map(
                      (c) => Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.all(12),
                        decoration: _flatBox(),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(
                              c['type'] == '拉伸'
                                  ? Icons.fitness_center
                                  : c['type'] == '强化'
                                  ? Icons.trending_up
                                  : Icons.lightbulb,
                              color: const Color(AppConstants.accentColor),
                              size: 20,
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  if (c['target_muscle'] != null)
                                    Text(
                                      c['target_muscle'] as String,
                                      style: const TextStyle(
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                  if (c['method'] != null)
                                    Text(
                                      c['method'] as String,
                                      style: const TextStyle(height: 1.4),
                                    ),
                                  if (c['freq'] != null)
                                    Text(
                                      c['freq'] as String,
                                      style: const TextStyle(
                                        color: Color(AppConstants.textMuted),
                                        fontSize: 12,
                                      ),
                                    ),
                                  if (c['desc'] != null)
                                    Text(
                                      c['desc'] as String,
                                      style: const TextStyle(height: 1.4),
                                    ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                  // Related issues (legacy).
                  if (detail != null && detail.relatedIssues.isNotEmpty) ...[
                    const SizedBox(height: 16),
                    const Text(
                      '你可能还需要关注',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    SizedBox(
                      height: 120,
                      child: ListView.separated(
                        scrollDirection: Axis.horizontal,
                        itemCount: detail.relatedIssues.length,
                        separatorBuilder: (_, _) => const SizedBox(width: 8),
                        itemBuilder: (_, i) {
                          final rel = detail.relatedIssues[i];
                          return GestureDetector(
                            onTap: () =>
                                context.push('/issue/${rel.id}/detail'),
                            child: Container(
                              width: 160,
                              padding: const EdgeInsets.all(12),
                              decoration: _flatBox(),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    rel.id,
                                    style: const TextStyle(
                                      fontSize: 12,
                                      color: Color(AppConstants.textMuted),
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    rel.relation,
                                    style: const TextStyle(
                                      fontSize: 13,
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                                  Text(
                                    '关联度: ${rel.weight}',
                                    style: const TextStyle(
                                      fontSize: 12,
                                      color: Color(AppConstants.textMuted),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
          const DisclaimerBanner(),
        ],
      ),
    );
  }

  void _showSevereDialog(BuildContext context) {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        icon: const Icon(
          Icons.warning,
          color: Color(AppConstants.severeColor),
          size: 48,
        ),
        title: const Text('建议及时就医'),
        content: const Text(
          '你的评估结果为"严重"。本 App 的评估仅供参考，不能替代专业医疗诊断。建议你尽快咨询专业医师进行详细检查。',
        ),
        actions: [
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('我知道了'),
          ),
        ],
      ),
    );
  }
}

class _EntryDetailSection extends StatelessWidget {
  final PostureProfileState state;
  final String issueId;
  final VoidCallback onRetry;
  const _EntryDetailSection({
    required this.state,
    required this.issueId,
    required this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    final status = state.entryStatus;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: _flatBox(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.folder_shared,
                color: Color(AppConstants.accentColor),
                size: 18,
              ),
              const SizedBox(width: 8),
              Text('档案详情', style: Theme.of(context).textTheme.titleMedium),
            ],
          ),
          const SizedBox(height: 8),
          if (status == LoadStatus.idle || status == LoadStatus.loading)
            Row(
              children: const [
                SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                SizedBox(width: 10),
                Text(
                  '加载档案详情…',
                  style: TextStyle(
                    color: Color(AppConstants.textMuted),
                    fontSize: 13,
                  ),
                ),
              ],
            )
          else if (status == LoadStatus.empty)
            const Text(
              '该问题暂无档案记录。',
              style: TextStyle(
                color: Color(AppConstants.textMuted),
                fontSize: 13,
              ),
            )
          else if (status == LoadStatus.networkError)
            _Unavailable(
              message: '档案状态暂不可用',
              hint: state.error ?? '',
              onRetry: onRetry,
            )
          else if (status == LoadStatus.parseError)
            _Unavailable(
              message: '档案状态暂不可用（数据异常）',
              hint: state.error ?? '数据解析异常',
              onRetry: onRetry,
            )
          else if (state.entryDetail?.issueId != issueId)
            _Unavailable(
              message: '档案状态暂不可用',
              hint: '当前详情与所选问题不一致，请重新加载。',
              onRetry: onRetry,
            )
          else ...[
            _EntryDetailBody(entry: state.entryDetail!),
          ],
        ],
      ),
    );
  }
}

class _EntryDetailBody extends StatelessWidget {
  final PostureProfileEntry entry;
  const _EntryDetailBody({required this.entry});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            SeverityBadge(severity: entry.combinedSeverity),
            CertaintyBadge(certainty: entry.certainty),
            RiskTierBadge(riskTier: entry.riskTier),
          ],
        ),
        if (entry.sources.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text(
            entry.certainty == Certainty.conflict ? '各来源分别记录（不合并）：' : '评估来源：',
            style: const TextStyle(
              fontSize: 12,
              color: Color(AppConstants.textColor),
            ),
          ),
          for (final s in entry.sources) ...[
            const SizedBox(height: 4),
            Row(
              children: [
                Text(
                  '${s.source == 'self_test'
                      ? '自测'
                      : s.source == 'ai_photo'
                      ? 'AI 拍照分析'
                      : s.source} · ',
                  style: const TextStyle(
                    fontSize: 12,
                    color: Color(AppConstants.textColor),
                  ),
                ),
                SeverityBadge(severity: s.severity, size: 12),
                const SizedBox(width: 8),
                Text(
                  _formatDate(s.createdAt),
                  style: const TextStyle(
                    fontSize: 11,
                    color: Color(AppConstants.textMuted),
                  ),
                ),
              ],
            ),
          ],
        ],
        const SizedBox(height: 6),
        Text(
          '风险版本：${entry.riskVersion} · 更新于 ${_formatDate(entry.updatedAt)}',
          style: const TextStyle(
            fontSize: 11,
            color: Color(AppConstants.textMuted),
          ),
        ),
      ],
    );
  }
}

class _Unavailable extends StatelessWidget {
  final String message;
  final String hint;
  final VoidCallback? onRetry;
  const _Unavailable({required this.message, this.hint = '', this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Icon(
              Icons.error_outline,
              color: Color(AppConstants.severeColor),
              size: 18,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                message,
                style: const TextStyle(
                  fontSize: 13,
                  color: Color(AppConstants.textColor),
                ),
              ),
            ),
          ],
        ),
        if (hint.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(
              hint,
              style: const TextStyle(
                fontSize: 12,
                color: Color(AppConstants.textMuted),
              ),
            ),
          ),
        if (onRetry != null) ...[
          const SizedBox(height: 8),
          OutlinedButton.icon(
            key: const Key('result-entry-retry'),
            onPressed: onRetry,
            icon: const Icon(Icons.refresh, size: 18),
            label: const Text('重试'),
          ),
        ],
      ],
    );
  }
}

BoxDecoration _flatBox() => BoxDecoration(
  color: const Color(AppConstants.cardColor),
  borderRadius: BorderRadius.circular(8),
  border: Border.all(color: const Color(AppConstants.glassBorder)),
);

String _formatDate(DateTime d) {
  return '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
}
