// app/lib/screens/profile/posture_profile_screen.dart
//
// Server-driven posture profile + multi-issue priorities + goal confirmation
// + structured safety-signal reporting (Task 8C, spec §9.2 / §10.5-§10.8 /
// §11.2 / §12).
//
// Safety / state contract:
//  - This screen does NOT use postureStateProvider as a source of truth; the
//    server profile + priorities responses are authoritative. The placeholder
//    implementation that derived counts from local state has been removed.
//  - loading / empty / networkError / parseError are visually distinct and
//    neither network nor parse failure is allowed to render as "正常",
//    "暂无问题" or an empty profile card.
//  - conflict entries surface "来源不一致 / 无合并结论" with per-source
//    severity and timestamp (no merging, no "take more severe").
//  - provisional entries show "建议重新评估".
//  - combined_severity == null shows "无合并结论".
//  - restricted vs red_flag use distinct icon + label (never color alone).
//  - Goal selection is limited to 1..3 of the current normal_candidates with
//    consecutive rank 1..N; duplicate submit is blocked while submitting.
//  - 409 stale_priority clears local selection and surfaces a reconfirm
//    banner without auto-replaying the confirm.
//  - Safety-signal success invalidates the previous selection (provider
//    clears priorities + confirmedGoals; the screen clears the local
//    selection via the needsReconfirm listener).
//  - The "生成改善计划（后续开放）" entry is always disabled and never calls
//    a plan API.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/constants.dart';
import '../../models/posture_profile.dart';
import '../../models/priority_suggestion.dart';
import '../../models/safety_signal.dart';
import '../../providers/assessment_provider.dart' show LoadStatus;
import '../../providers/posture_profile_provider.dart';
import '../../widgets/disclaimer_banner.dart';
import '../../widgets/posture_status_badge.dart';

class PostureProfileScreen extends ConsumerStatefulWidget {
  const PostureProfileScreen({super.key});

  @override
  ConsumerState<PostureProfileScreen> createState() =>
      _PostureProfileScreenState();
}

class _PostureProfileScreenState extends ConsumerState<PostureProfileScreen> {
  /// Issue IDs in selection order; ranks are derived as 1..N at submit time.
  /// A Dart `{}` set literal preserves insertion order (LinkedHashSet).
  final Set<String> _selectedIssueIds = <String>{};

  SignalType? _signalType;
  BodyRegion? _signalBodyRegion;
  SeverityHint? _signalSeverityHint;
  final TextEditingController _relatedIssueIdCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      ref.read(postureProfileProvider.notifier).fetchProfile();
      ref.read(postureProfileProvider.notifier).fetchPriorities();
    });
    // Whenever the provider raises needsReconfirm (stale_priority OR a fresh
    // safety signal), the previous selection is no longer valid against the
    // current candidate set. Clear it and let the user re-pick explicitly.
    ref.listenManual(postureProfileProvider.select((s) => s.needsReconfirm), (
      prev,
      next,
    ) {
      if (next && !(prev ?? false)) {
        setState(_selectedIssueIds.clear);
      }
    });
    // Also clear selection once a confirm batch succeeds (the provider clears
    // priorities + confirmedGoals; we just stop showing the user's old picks).
    ref.listenManual(postureProfileProvider.select((s) => s.confirmedGoals), (
      prev,
      next,
    ) {
      if (next != null && next != prev) {
        setState(_selectedIssueIds.clear);
      }
    });
    // A refresh invalidates the candidate set immediately. Do not retain
    // selections that were made against an older suggestion_id.
    ref.listenManual(postureProfileProvider.select((s) => s.prioritiesStatus), (
      prev,
      next,
    ) {
      if (next == LoadStatus.loading &&
          prev != LoadStatus.loading &&
          _selectedIssueIds.isNotEmpty) {
        setState(_selectedIssueIds.clear);
      }
    });
    ref.listenManual(
      postureProfileProvider.select((s) => s.priorities?.suggestionId),
      (prev, next) {
        if (prev != null && next == null && _selectedIssueIds.isNotEmpty) {
          setState(_selectedIssueIds.clear);
        }
      },
    );
  }

  @override
  void dispose() {
    _relatedIssueIdCtrl.dispose();
    super.dispose();
  }

  bool _isCandidateSelected(String issueId) =>
      _selectedIssueIds.contains(issueId);

  void _toggleCandidate(NormalCandidate candidate) {
    final id = candidate.issueId;
    setState(() {
      if (_selectedIssueIds.contains(id)) {
        _selectedIssueIds.remove(id);
      } else {
        if (_selectedIssueIds.length >= 3) return; // UI max 3
        _selectedIssueIds.add(id);
      }
    });
  }

  Future<void> _confirmGoals() async {
    final suggestions = ref.read(postureProfileProvider).priorities;
    if (suggestions == null) return;
    if (_selectedIssueIds.isEmpty) return;
    final goals = <GoalInput>[];
    var rank = 1;
    for (final id in _selectedIssueIds) {
      goals.add(GoalInput(issueId: id, priorityRank: rank++));
    }
    await ref.read(postureProfileProvider.notifier).confirmGoals(goals);
  }

  Future<void> _submitSafetySignal() async {
    final type = _signalType;
    if (type == null) return;
    final input = SafetySignalInput(
      signalType: type,
      bodyRegion: _signalBodyRegion,
      relatedIssueId: _relatedIssueIdCtrl.text.trim().isEmpty
          ? null
          : _relatedIssueIdCtrl.text.trim(),
      severityHint: _signalSeverityHint,
      reportedAt: DateTime.now(),
    );
    final ok = await ref
        .read(postureProfileProvider.notifier)
        .reportSafetySignal(input);
    if (ok && mounted) {
      setState(() {
        _signalType = null;
        _signalBodyRegion = null;
        _signalSeverityHint = null;
        _relatedIssueIdCtrl.clear();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(postureProfileProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('我的体态档案')),
      body: Column(
        children: [
          const DisclaimerBanner(),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _ProfileSection(
                    state: state,
                    onRetry: () => ref
                        .read(postureProfileProvider.notifier)
                        .fetchProfile(),
                  ),
                  const SizedBox(height: 16),
                  _PrioritiesSection(
                    state: state,
                    selectedIssueIds: _selectedIssueIds,
                    isCandidateSelected: _isCandidateSelected,
                    onToggleCandidate: _toggleCandidate,
                    selectionEnabled: state.confirmStatus != LoadStatus.loading,
                    onConfirm: _confirmGoals,
                    onRetry: () => ref
                        .read(postureProfileProvider.notifier)
                        .fetchPriorities(),
                  ),
                  const SizedBox(height: 16),
                  _SafetySignalSection(
                    state: state,
                    signalType: _signalType,
                    signalBodyRegion: _signalBodyRegion,
                    signalSeverityHint: _signalSeverityHint,
                    relatedIssueIdCtrl: _relatedIssueIdCtrl,
                    onSignalTypeChanged: (v) => setState(() => _signalType = v),
                    onBodyRegionChanged: (v) =>
                        setState(() => _signalBodyRegion = v),
                    onSeverityHintChanged: (v) =>
                        setState(() => _signalSeverityHint = v),
                    onSubmit: _submitSafetySignal,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Profile section: loading / empty / networkError / parseError / data
// ---------------------------------------------------------------------------

class _ProfileSection extends StatelessWidget {
  final PostureProfileState state;
  final VoidCallback onRetry;
  const _ProfileSection({required this.state, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    final status = state.profileStatus;
    if (status == LoadStatus.idle || status == LoadStatus.loading) {
      return _Section(
        child: Column(
          children: const [
            CircularProgressIndicator(),
            SizedBox(height: 12),
            Text(
              '加载档案中…',
              style: TextStyle(color: Color(AppConstants.textMuted)),
            ),
          ],
        ),
      );
    }
    if (status == LoadStatus.empty) {
      final categories =
          state.profile?.unevaluatedCategories
              .map((c) => AppConstants.categoryNames[c] ?? c)
              .join('、') ??
          '';
      return _Section(
        child: _InfoState(
          icon: Icons.folder_open,
          text: '评估记录为空',
          hint: categories.isEmpty
              ? '前往问题页完成第一次自测，再返回查看档案。'
              : '尚未评估：$categories。前往问题页完成第一次自测。',
          actionLabel: '去浏览问题',
          onAction: () => context.push('/'),
        ),
      );
    }
    if (status == LoadStatus.networkError) {
      return _Section(
        child: _ErrorState(message: state.error ?? '档案加载失败', onRetry: onRetry),
      );
    }
    if (status == LoadStatus.parseError) {
      return _Section(
        child: _ErrorState(message: '数据解析异常', onRetry: onRetry),
      );
    }
    final profile = state.profile!;
    return _Section(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('档案概览', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Wrap(
            spacing: 12,
            runSpacing: 8,
            children: [
              _SummaryChip(
                label: '已评估',
                value: '${profile.summary.totalEvaluated}',
              ),
              _SummaryChip(
                label: '冲突',
                value: '${profile.summary.totalConflict}',
              ),
              _SummaryChip(
                label: '待重新评估',
                value: '${profile.summary.totalProvisional}',
              ),
            ],
          ),
          if (profile.unevaluatedCategories.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(
              '未评估：${profile.unevaluatedCategories.join('、')}',
              style: const TextStyle(
                color: Color(AppConstants.textMuted),
                fontSize: 13,
              ),
            ),
          ],
          const SizedBox(height: 12),
          for (final entry in profile.evaluatedIssues) ...[
            _EntryCard(entry: entry),
            const SizedBox(height: 8),
          ],
        ],
      ),
    );
  }
}

class _EntryCard extends StatelessWidget {
  final PostureProfileEntry entry;
  const _EntryCard({required this.entry});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _flatBox(context),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  entry.issueName,
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    color: Color(AppConstants.textColor),
                  ),
                ),
              ),
              Text(
                AppConstants.categoryNames[entry.category] ?? entry.category,
                style: const TextStyle(
                  color: Color(AppConstants.textMuted),
                  fontSize: 12,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              SeverityBadge(severity: entry.combinedSeverity),
              CertaintyBadge(certainty: entry.certainty),
              RiskTierBadge(riskTier: entry.riskTier),
            ],
          ),
          if (entry.certainty == Certainty.conflict) ...[
            const SizedBox(height: 8),
            const Text(
              '各来源分别记录（不合并）：',
              style: TextStyle(
                fontSize: 12,
                color: Color(AppConstants.textColor),
              ),
            ),
            for (final s in entry.sources) ...[
              const SizedBox(height: 4),
              _SourceRow(source: s),
            ],
          ],
          if (entry.certainty == Certainty.provisional) ...[
            const SizedBox(height: 6),
            const Text(
              '当前来源不足以形成结论，建议重新自测或咨询专业人士。',
              style: TextStyle(
                fontSize: 12,
                color: Color(AppConstants.moderateColor),
              ),
            ),
          ],
          const SizedBox(height: 6),
          Text(
            '更新于 ${_formatDate(entry.updatedAt)}',
            style: const TextStyle(
              fontSize: 11,
              color: Color(AppConstants.textMuted),
            ),
          ),
        ],
      ),
    );
  }
}

class _SourceRow extends StatelessWidget {
  final ProfileSource source;
  const _SourceRow({required this.source});

  @override
  Widget build(BuildContext context) {
    final label = source.source == 'self_test'
        ? '自测'
        : source.source == 'ai_photo'
        ? 'AI 拍照分析'
        : source.source;
    return Row(
      children: [
        Text(
          '$label · ',
          style: const TextStyle(
            fontSize: 12,
            color: Color(AppConstants.textColor),
          ),
        ),
        SeverityBadge(severity: source.severity, size: 12),
        const SizedBox(width: 8),
        Text(
          _formatDate(source.createdAt),
          style: const TextStyle(
            fontSize: 11,
            color: Color(AppConstants.textMuted),
          ),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Priorities section: three buckets + selection + confirm + plan-disabled
// ---------------------------------------------------------------------------

class _PrioritiesSection extends StatelessWidget {
  final PostureProfileState state;
  final Set<String> selectedIssueIds;
  final bool Function(String) isCandidateSelected;
  final void Function(NormalCandidate) onToggleCandidate;
  final bool selectionEnabled;
  final Future<void> Function() onConfirm;
  final VoidCallback onRetry;

  const _PrioritiesSection({
    required this.state,
    required this.selectedIssueIds,
    required this.isCandidateSelected,
    required this.onToggleCandidate,
    required this.selectionEnabled,
    required this.onConfirm,
    required this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    final status = state.prioritiesStatus;
    return _Section(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.low_priority,
                color: Color(AppConstants.accentColor),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  '多问题优先级（仅供参考）',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            state.priorities?.disclaimer ?? '优先级属于建议，不作为病因认定。',
            style: const TextStyle(
              fontSize: 12,
              color: Color(AppConstants.textMuted),
            ),
          ),
          const SizedBox(height: 12),
          if (status == LoadStatus.loading || status == LoadStatus.idle)
            const Center(child: CircularProgressIndicator())
          else if (status == LoadStatus.networkError)
            _ErrorState(message: state.error ?? '加载优先级失败', onRetry: onRetry)
          else if (status == LoadStatus.parseError)
            _ErrorState(message: '数据解析异常', onRetry: onRetry)
          else ...[
            if (state.needsReconfirm)
              Container(
                margin: const EdgeInsets.only(bottom: 12),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(
                    AppConstants.moderateColor,
                  ).withValues(alpha: 0.16),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: const Color(AppConstants.moderateColor),
                  ),
                ),
                child: Row(
                  children: const [
                    Icon(
                      Icons.refresh,
                      color: Color(AppConstants.moderateColor),
                      size: 18,
                    ),
                    SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '优先级已更新，请重新确认目标。',
                        style: TextStyle(
                          color: Color(AppConstants.textColor),
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            if (state.confirmedGoals != null)
              _ConfirmedGoalsCard(goals: state.confirmedGoals!),
            _CandidatesBucket(
              candidates: state.priorities?.normalCandidates ?? const [],
              selectedIssueIds: selectedIssueIds,
              isCandidateSelected: isCandidateSelected,
              onToggle: onToggleCandidate,
              selectionEnabled: selectionEnabled,
            ),
            const SizedBox(height: 12),
            _RetestBucket(items: state.priorities?.retestRequired ?? const []),
            const SizedBox(height: 12),
            _SafetyBlockedBucket(
              items: state.priorities?.safetyBlocked ?? const [],
            ),
            const SizedBox(height: 12),
            Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _ConfirmButton(
                  key: const Key('confirm-goals-button'),
                  selectedCount: selectedIssueIds.length,
                  isSubmitting: state.confirmStatus == LoadStatus.loading,
                  onConfirm: onConfirm,
                ),
                const SizedBox(height: 8),
                OutlinedButton(
                  // Enabled only when the server gate can_generate_plan is true
                  // (confirmed posture goals present). Navigates to the Phase 4
                  // plan tab; the plan/safety logic lives entirely server-side.
                  onPressed:
                      (state.confirmedGoals?.canGeneratePlan ?? false)
                          ? () => context.go('/plan')
                          : null,
                  child: const Text('生成改善计划'),
                ),
              ],
            ),
            if (state.confirmError != null &&
                state.confirmStatus == LoadStatus.parseError &&
                state.confirmErrorMessage != null) ...[
              const SizedBox(height: 8),
              Text(
                state.confirmErrorMessage!,
                style: const TextStyle(
                  color: Color(AppConstants.severeColor),
                  fontSize: 12,
                ),
              ),
            ],
          ],
        ],
      ),
    );
  }
}

class _CandidatesBucket extends StatelessWidget {
  final List<NormalCandidate> candidates;
  final Set<String> selectedIssueIds;
  final bool Function(String) isCandidateSelected;
  final void Function(NormalCandidate) onToggle;
  final bool selectionEnabled;
  const _CandidatesBucket({
    required this.candidates,
    required this.selectedIssueIds,
    required this.isCandidateSelected,
    required this.onToggle,
    required this.selectionEnabled,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          '普通候选（可选择 1–3 个目标）',
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: Color(AppConstants.textColor),
          ),
        ),
        const SizedBox(height: 6),
        if (candidates.isEmpty)
          const Text(
            '暂无普通候选。',
            style: TextStyle(
              color: Color(AppConstants.textMuted),
              fontSize: 12,
            ),
          )
        else
          for (final c in candidates) ...[
            _CandidateCard(
              candidate: c,
              selected: isCandidateSelected(c.issueId),
              onTap: selectionEnabled ? () => onToggle(c) : null,
            ),
            const SizedBox(height: 6),
          ],
      ],
    );
  }
}

class _CandidateCard extends StatelessWidget {
  final NormalCandidate candidate;
  final bool selected;
  final VoidCallback? onTap;
  const _CandidateCard({
    required this.candidate,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        key: Key('candidate-${candidate.issueId}'),
        width: double.infinity,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: selected
              ? const Color(AppConstants.accentColor).withValues(alpha: 0.16)
              : const Color(AppConstants.cardColor),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: selected
                ? const Color(AppConstants.accentColor)
                : const Color(AppConstants.glassBorder),
          ),
        ),
        child: Row(
          children: [
            Icon(
              selected ? Icons.check_box : Icons.check_box_outline_blank,
              color: selected
                  ? const Color(AppConstants.accentColor)
                  : const Color(AppConstants.textMuted),
              size: 20,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    candidate.issueName,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      color: Color(AppConstants.textColor),
                    ),
                  ),
                  const SizedBox(height: 2),
                  if (candidate.severity != null)
                    SeverityBadge(severity: candidate.severity, size: 12),
                  const SizedBox(height: 4),
                  Text(
                    '建议排序：${candidate.suggestedRank}',
                    style: const TextStyle(
                      fontSize: 11,
                      color: Color(AppConstants.textMuted),
                    ),
                  ),
                  for (final r in candidate.reasons)
                    Text(
                      '· $r',
                      style: const TextStyle(
                        fontSize: 11,
                        color: Color(AppConstants.textMuted),
                      ),
                    ),
                  if (candidate.relationType != null)
                    Text(
                      '可能关联：${candidate.relationType}（不作为病因认定）',
                      style: const TextStyle(
                        fontSize: 11,
                        color: Color(AppConstants.textMuted),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _RetestBucket extends StatelessWidget {
  final List<RetestItem> items;
  const _RetestBucket({required this.items});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          '需重新评估',
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: Color(AppConstants.textColor),
          ),
        ),
        const SizedBox(height: 6),
        if (items.isEmpty)
          const Text(
            '暂无需重新评估的条目。',
            style: TextStyle(
              color: Color(AppConstants.textMuted),
              fontSize: 12,
            ),
          )
        else
          for (final i in items) ...[
            _FlatInfoCard(
              icon: Icons.refresh,
              color: const Color(AppConstants.moderateColor),
              title: i.issueName,
              subtitle: i.reason,
            ),
            const SizedBox(height: 6),
          ],
      ],
    );
  }
}

class _SafetyBlockedBucket extends StatelessWidget {
  final List<SafetyBlockedItem> items;
  const _SafetyBlockedBucket({required this.items});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          '安全阻断',
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: Color(AppConstants.textColor),
          ),
        ),
        const SizedBox(height: 6),
        if (items.isEmpty)
          const Text(
            '暂无安全阻断条目。',
            style: TextStyle(
              color: Color(AppConstants.textMuted),
              fontSize: 12,
            ),
          )
        else
          for (final i in items) ...[
            _SafetyBlockedCard(item: i),
            const SizedBox(height: 6),
          ],
      ],
    );
  }
}

class _SafetyBlockedCard extends StatelessWidget {
  final SafetyBlockedItem item;
  const _SafetyBlockedCard({required this.item});

  @override
  Widget build(BuildContext context) {
    // restricted vs red_flag distinct icon + label via RiskTierBadge.
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: riskTierColor(item.riskTier).withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: riskTierColor(item.riskTier)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                riskTierIcon(item.riskTier),
                color: riskTierColor(item.riskTier),
                size: 18,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  item.issueName,
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: Color(AppConstants.textColor),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Align(
            alignment: Alignment.centerLeft,
            child: RiskTierBadge(riskTier: item.riskTier, size: 12),
          ),
          const SizedBox(height: 6),
          Text(
            item.reason,
            style: const TextStyle(
              fontSize: 12,
              color: Color(AppConstants.textColor),
            ),
          ),
          const SizedBox(height: 4),
          Text(
            '下一步：${item.nextAction}',
            style: const TextStyle(
              fontSize: 12,
              color: Color(AppConstants.textMuted),
            ),
          ),
        ],
      ),
    );
  }
}

class _ConfirmedGoalsCard extends StatelessWidget {
  final ConfirmedGoals goals;
  const _ConfirmedGoalsCard({required this.goals});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(AppConstants.normalColor).withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(AppConstants.normalColor)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: const [
              Icon(
                Icons.check_circle,
                color: Color(AppConstants.normalColor),
                size: 18,
              ),
              SizedBox(width: 8),
              Text(
                '已确认目标',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: Color(AppConstants.textColor),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          for (final g in goals.confirmedGoals)
            Text(
              '· ${g.priorityRank}. ${g.issueId}（${_formatDate(g.confirmedAt)}）',
              style: const TextStyle(
                fontSize: 12,
                color: Color(AppConstants.textColor),
              ),
            ),
        ],
      ),
    );
  }
}

class _ConfirmButton extends StatelessWidget {
  final int selectedCount;
  final bool isSubmitting;
  final Future<void> Function() onConfirm;
  const _ConfirmButton({
    super.key,
    required this.selectedCount,
    required this.isSubmitting,
    required this.onConfirm,
  });

  @override
  Widget build(BuildContext context) {
    final disabled = selectedCount == 0 || isSubmitting;
    return ElevatedButton(
      onPressed: disabled ? null : () => onConfirm(),
      child: isSubmitting
          ? Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: const [
                SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                SizedBox(width: 8),
                Text('提交中…'),
              ],
            )
          : Text('确认 $selectedCount 个目标'),
    );
  }
}

// ---------------------------------------------------------------------------
// Safety signal section (structured enum controls, no free text for
// signal_type / body_region / severity_hint)
// ---------------------------------------------------------------------------

class _SafetySignalSection extends StatelessWidget {
  final PostureProfileState state;
  final SignalType? signalType;
  final BodyRegion? signalBodyRegion;
  final SeverityHint? signalSeverityHint;
  final TextEditingController relatedIssueIdCtrl;
  final void Function(SignalType?) onSignalTypeChanged;
  final void Function(BodyRegion?) onBodyRegionChanged;
  final void Function(SeverityHint?) onSeverityHintChanged;
  final Future<void> Function() onSubmit;

  const _SafetySignalSection({
    required this.state,
    required this.signalType,
    required this.signalBodyRegion,
    required this.signalSeverityHint,
    required this.relatedIssueIdCtrl,
    required this.onSignalTypeChanged,
    required this.onBodyRegionChanged,
    required this.onSeverityHintChanged,
    required this.onSubmit,
  });

  @override
  Widget build(BuildContext context) {
    final submitting = state.safetyStatus == LoadStatus.loading;
    return _Section(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.report, color: Color(AppConstants.severeColor)),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  '上报安全信号',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          const Text(
            '请仅上报真实症状信号。该信息会触发风险重算，使当前优先级失效并要求重新确认。',
            style: TextStyle(
              fontSize: 12,
              color: Color(AppConstants.textMuted),
            ),
          ),
          const SizedBox(height: 12),
          _DropdownField<SignalType>(
            key: const Key('safety-signal-type'),
            label: '安全信号：类型',
            value: signalType,
            items: const [
              DropdownMenuItem(value: SignalType.pain, child: Text('疼痛')),
              DropdownMenuItem(value: SignalType.numbness, child: Text('麻木')),
              DropdownMenuItem(value: SignalType.weakness, child: Text('无力')),
              DropdownMenuItem(value: SignalType.dizziness, child: Text('眩晕')),
              DropdownMenuItem(
                value: SignalType.acuteTrauma,
                child: Text('急性创伤'),
              ),
              DropdownMenuItem(value: SignalType.other, child: Text('其他')),
            ],
            onChanged: submitting ? null : onSignalTypeChanged,
          ),
          const SizedBox(height: 8),
          _DropdownField<BodyRegion?>(
            label: '身体区域（可不指定）',
            value: signalBodyRegion,
            items: const [
              DropdownMenuItem(value: null, child: Text('不指定')),
              DropdownMenuItem(value: BodyRegion.headNeck, child: Text('头颈部')),
              DropdownMenuItem(value: BodyRegion.cervical, child: Text('颈椎')),
              DropdownMenuItem(value: BodyRegion.upperBack, child: Text('上背')),
              DropdownMenuItem(value: BodyRegion.thoracic, child: Text('胸椎')),
              DropdownMenuItem(value: BodyRegion.lowerBack, child: Text('下背')),
              DropdownMenuItem(
                value: BodyRegion.shoulderThorax,
                child: Text('肩胸区'),
              ),
              DropdownMenuItem(
                value: BodyRegion.pelvisSpine,
                child: Text('骨盆腰椎'),
              ),
              DropdownMenuItem(value: BodyRegion.lowerLimb, child: Text('下肢')),
              DropdownMenuItem(
                value: BodyRegion.compound,
                child: Text('复合综合征'),
              ),
            ],
            onChanged: submitting ? null : onBodyRegionChanged,
          ),
          const SizedBox(height: 8),
          _DropdownField<SeverityHint?>(
            label: '严重度提示（可不指定，仅作分类参考）',
            value: signalSeverityHint,
            items: const [
              DropdownMenuItem(value: null, child: Text('不指定')),
              DropdownMenuItem(value: SeverityHint.mild, child: Text('轻度')),
              DropdownMenuItem(value: SeverityHint.moderate, child: Text('中度')),
              DropdownMenuItem(value: SeverityHint.severe, child: Text('重度')),
            ],
            onChanged: submitting ? null : onSeverityHintChanged,
          ),
          const SizedBox(height: 8),
          TextField(
            controller: relatedIssueIdCtrl,
            enabled: !submitting,
            decoration: const InputDecoration(
              labelText: '相关问题 ID（可选）',
              hintText: '如 HN-01',
              isDense: true,
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: (submitting || signalType == null)
                  ? null
                  : () => onSubmit(),
              child: submitting
                  ? Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: const [
                        SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                        SizedBox(width: 8),
                        Text('提交中…'),
                      ],
                    )
                  : const Text('提交安全信号'),
            ),
          ),
          if (state.lastSafetyResult != null) ...[
            const SizedBox(height: 8),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: riskTierColor(
                  state.lastSafetyResult!.riskTier,
                ).withValues(alpha: 0.14),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: riskTierColor(state.lastSafetyResult!.riskTier),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '安全信号已记录（风险等级：${riskTierLabel(state.lastSafetyResult!.riskTier)}）',
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: Color(AppConstants.textColor),
                    ),
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    '已使旧优先级失效，请重新查看并确认目标。',
                    style: TextStyle(
                      fontSize: 11,
                      color: Color(AppConstants.textMuted),
                    ),
                  ),
                ],
              ),
            ),
          ],
          if (state.safetyError != null) ...[
            const SizedBox(height: 8),
            Text(
              state.safetyErrorMessage ?? '上报失败，请稍后再试。',
              style: const TextStyle(
                color: Color(AppConstants.severeColor),
                fontSize: 12,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Small shared building blocks (flat, no nested cards, r=8 corners)
// ---------------------------------------------------------------------------

class _Section extends StatelessWidget {
  final Widget child;
  const _Section({required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(AppConstants.cardColor),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(AppConstants.glassBorder)),
      ),
      child: child,
    );
  }
}

class _SummaryChip extends StatelessWidget {
  final String label;
  final String value;
  const _SummaryChip({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(AppConstants.accentColor).withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        children: [
          Text(
            value,
            style: const TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.bold,
              color: Color(AppConstants.accentColor),
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: const TextStyle(
              fontSize: 12,
              color: Color(AppConstants.textMuted),
            ),
          ),
        ],
      ),
    );
  }
}

class _InfoState extends StatelessWidget {
  final IconData icon;
  final String text;
  final String hint;
  final String actionLabel;
  final VoidCallback onAction;
  const _InfoState({
    required this.icon,
    required this.text,
    required this.hint,
    required this.actionLabel,
    required this.onAction,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Icon(icon, size: 48, color: const Color(AppConstants.textMuted)),
        const SizedBox(height: 12),
        Text(
          text,
          style: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            color: Color(AppConstants.textColor),
          ),
        ),
        const SizedBox(height: 4),
        Text(
          hint,
          textAlign: TextAlign.center,
          style: const TextStyle(
            fontSize: 12,
            color: Color(AppConstants.textMuted),
          ),
        ),
        const SizedBox(height: 12),
        OutlinedButton(onPressed: onAction, child: Text(actionLabel)),
      ],
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
          onPressed: onRetry,
          icon: const Icon(Icons.refresh, size: 18),
          label: const Text('重试'),
        ),
      ],
    );
  }
}

class _FlatInfoCard extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String title;
  final String subtitle;
  const _FlatInfoCard({
    required this.icon,
    required this.color,
    required this.title,
    required this.subtitle,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color),
      ),
      child: Row(
        children: [
          Icon(icon, color: color, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: Color(AppConstants.textColor),
                  ),
                ),
                Text(
                  subtitle,
                  style: const TextStyle(
                    fontSize: 12,
                    color: Color(AppConstants.textMuted),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _DropdownField<T extends Object?> extends StatelessWidget {
  final String label;
  final T? value;
  final List<DropdownMenuItem<T>> items;
  final void Function(T?)? onChanged;
  const _DropdownField({
    super.key,
    required this.label,
    required this.value,
    required this.items,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        SizedBox(
          width: 120,
          child: Text(
            label,
            style: const TextStyle(
              fontSize: 12,
              color: Color(AppConstants.textMuted),
            ),
          ),
        ),
        Expanded(
          child: DropdownButton<T>(
            value: value,
            items: items,
            onChanged: onChanged,
            isExpanded: true,
            underline: const SizedBox(),
          ),
        ),
      ],
    );
  }
}

BoxDecoration _flatBox(BuildContext context) => BoxDecoration(
  color: const Color(AppConstants.cardColor),
  borderRadius: BorderRadius.circular(8),
  border: Border.all(color: const Color(AppConstants.glassBorder)),
);

String _formatDate(DateTime d) {
  return '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
}
