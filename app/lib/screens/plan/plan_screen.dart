// app/lib/screens/plan/plan_screen.dart
//
// Phase 4 plan + daily execution flow (Task 6): goal/schedule selection ->
// draft review -> explicit confirm -> active plan -> today's session ->
// feedback. Honest blocked / restricted / red-flag / no-active / rest-day /
// stale / parse-error states are surfaced and never faked as success. The
// client only renders server results and collects explicit confirmations and
// feedback; no recommendation or safety logic lives here.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:go_router/go_router.dart';
import '../../core/constants.dart';
import '../../core/idempotency_key.dart';
import '../../models/plan.dart';
import '../../providers/assessment_provider.dart' show LoadStatus;
import '../../providers/health_profile_provider.dart';
import '../../providers/plan_provider.dart';

const String _kDefaultTimezone = 'Asia/Shanghai';

const Map<String, String> _kGoalLabels = {
  'posture_improvement': '体态改善',
  'fat_loss': '减脂',
  'basic_strength': '基础增肌塑形',
};

String _outcomeLabel(OutcomeState s) {
  switch (s) {
    case OutcomeState.completed:
      return '已完成';
    case OutcomeState.partial:
      return '部分完成';
    case OutcomeState.tooBusy:
      return '太忙未练';
    case OutcomeState.intentionalRest:
      return '主动休息';
    case OutcomeState.discomfort:
      return '身体不适';
  }
}

void _openAgent(
  BuildContext context, {
  required String entryType,
  required String entityId,
}) {
  context.go(
    Uri(
      path: '/agent',
      queryParameters: {'entry_type': entryType, 'entity_id': entityId},
    ).toString(),
  );
}

Widget _exerciseIllustration(PlanExercise exercise, {double size = 72}) {
  return Semantics(
    label: exercise.illustrationAltZh,
    image: true,
    child: SvgPicture.asset(
      exercise.illustrationAssetKey,
      width: size,
      height: size,
      fit: BoxFit.contain,
      errorBuilder: (_, _, _) => SizedBox(
        width: size,
        height: size,
        child: const Icon(Icons.image_not_supported_outlined),
      ),
    ),
  );
}

class PlanScreen extends ConsumerStatefulWidget {
  const PlanScreen({super.key});
  @override
  ConsumerState<PlanScreen> createState() => _PlanScreenState();
}

class _PlanScreenState extends ConsumerState<PlanScreen> {
  String _goal = 'posture_improvement';
  int _frequency = 3;
  int _duration = 30;
  bool _bodyweight = true;
  bool _resistanceBand = false;
  bool _profileReady = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadInitialState();
    });
  }

  Future<void> _loadInitialState() async {
    await Future.wait([
      ref.read(healthProfileProvider.notifier).fetchProfile(),
      ref.read(planProvider.notifier).fetchActive(),
      ref.read(planProvider.notifier).fetchDraft(),
    ]);
    if (!mounted) return;
    final profile = ref.read(healthProfileProvider).result?.profile;
    final supportedGoal = profile?.fitnessGoal?.wire;
    if (profile != null &&
        supportedGoal != null &&
        _kGoalLabels.containsKey(supportedGoal) &&
        profile.weeklyFrequency != null &&
        profile.sessionDurationMinutes != null &&
        profile.equipment?.bodyweight != null &&
        profile.equipment?.resistanceBand != null) {
      setState(() {
        _goal = supportedGoal;
        _frequency = profile.weeklyFrequency!;
        _duration = profile.sessionDurationMinutes!.value;
        _bodyweight = profile.equipment!.bodyweight!;
        _resistanceBand = profile.equipment!.resistanceBand!;
        _profileReady = _bodyweight || _resistanceBand;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final plan = ref.watch(planProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('训练计划'),
        actions: [
          TextButton.icon(
            key: const Key('plan-weekly-review-entry'),
            onPressed: () => context.go('/plan/weekly-review'),
            icon: const Icon(Icons.assignment_turned_in_outlined),
            label: const Text('周回顾'),
          ),
          TextButton.icon(
            key: const Key('plan-nutrition-entry'),
            onPressed: () => context.go('/plan/nutrition'),
            icon: const Icon(Icons.restaurant_menu),
            label: const Text('饮食建议'),
          ),
        ],
      ),
      body: SafeArea(child: _body(context, plan)),
    );
  }

  Widget _body(BuildContext context, PlanState plan) {
    if (plan.draftStatus == LoadStatus.data &&
        plan.draft != null &&
        plan.activeStatus == LoadStatus.data &&
        plan.activePlan != null) {
      return _ActiveAndDraftView(
        draft: plan.draft!,
        draftReady: _profileReady,
        goal: _goal,
        frequency: _frequency,
        duration: _duration,
        bodyweight: _bodyweight,
        onConfirm: _confirm,
        onRegenerate: _generate,
      );
    }
    if (plan.draftStatus == LoadStatus.data && plan.draft != null) {
      if (!_profileReady) return _profileRequired();
      return _DraftReview(
        draft: plan.draft!,
        goal: _goal,
        frequency: _frequency,
        duration: _duration,
        bodyweight: _bodyweight,
        onConfirm: _confirm,
        onRegenerate: _generate,
      );
    }
    if (plan.activeStatus == LoadStatus.data && plan.activePlan != null) {
      return const _ActiveView();
    }
    if (plan.draftStatus == LoadStatus.loading ||
        plan.activeStatus == LoadStatus.loading ||
        ref.watch(healthProfileProvider).status == LoadStatus.loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (!_profileReady) return _profileRequired();
    if (plan.draftStatus == LoadStatus.networkError &&
        plan.draftFailure != DraftFailureState.none &&
        plan.draftFailure != DraftFailureState.unavailable) {
      return switch (plan.draftFailure) {
        DraftFailureState.safetyBlocked => const _StatusCard(
          key: Key('plan-status-safety'),
          icon: Icons.block,
          title: '当前安全状态不允许生成训练计划',
          detail: '受限或红旗状态不会被显示为普通失败，也不会创建可确认草案。',
        ),
        DraftFailureState.missingInput => const _StatusCard(
          key: Key('plan-status-missing'),
          icon: Icons.assignment_late_outlined,
          title: '缺少生成计划所需信息',
          detail: '请先补全当前健康档案和安全筛查，再重新生成。',
        ),
        DraftFailureState.stale => const _StatusCard(
          key: Key('plan-status-stale'),
          icon: Icons.sync_problem,
          title: '计划上下文已变化',
          detail: '请刷新当前档案和目标后重新发起，旧请求不会继续执行。',
        ),
        DraftFailureState.conflict => const _StatusCard(
          key: Key('plan-status-conflict'),
          icon: Icons.warning_amber_outlined,
          title: '计划请求发生冲突',
          detail: '请求未被显示为成功，请刷新后重新发起。',
        ),
        DraftFailureState.none || DraftFailureState.unavailable =>
          throw StateError('handled outside typed draft failure branch'),
      };
    }
    if (plan.draftStatus == LoadStatus.networkError ||
        plan.activeStatus == LoadStatus.networkError) {
      return _StatusCard(
        icon: Icons.cloud_off,
        title: '加载失败',
        detail: plan.error ?? '请稍后重试',
        action: () {
          ref.read(planProvider.notifier).fetchActive();
          ref.read(planProvider.notifier).fetchDraft();
        },
        actionLabel: '重试',
      );
    }
    if (plan.draftStatus == LoadStatus.parseError ||
        plan.activeStatus == LoadStatus.parseError) {
      return const _StatusCard(
        icon: Icons.broken_image_outlined,
        title: '数据解析异常',
        detail: '无法解析服务端返回的训练计划，不会显示为成功。',
      );
    }
    return _GenerationForm(
      goal: _goal,
      frequency: _frequency,
      duration: _duration,
      bodyweight: _bodyweight,
      resistanceBand: _resistanceBand,
      onGenerate: _generate,
    );
  }

  Widget _profileRequired() => const _StatusCard(
    icon: Icons.assignment_ind_outlined,
    title: '请先完善健康档案',
    detail: '训练目标、频率、时长和器材必须来自当前健康档案，不能使用页面默认值代替。',
  );

  Future<void> _generate() async {
    await ref
        .read(planProvider.notifier)
        .generateDraft(
          DraftInput(
            fitnessGoal: _goal,
            weeklyFrequency: _frequency,
            sessionDurationMinutes: _duration,
            equipmentBodyweight: _bodyweight,
            equipmentResistanceBand: _resistanceBand,
            ianaTimezone: _kDefaultTimezone,
            idempotencyKey: newIdempotencyKey(),
          ),
        );
  }

  Future<void> _confirm() async {
    final draft = ref.read(planProvider).draft;
    if (draft == null) return;
    final ok = await ref
        .read(planProvider.notifier)
        .confirm(
          ConfirmInput(
            expectedPlanVersionId: draft.planVersionId,
            fitnessGoal: draft.requestedGoal,
            weeklyFrequency: draft.weeklyFrequency,
            sessionDurationMinutes: draft.sessionDurationMinutes,
            equipmentBodyweight: _bodyweight,
            equipmentResistanceBand: _resistanceBand,
            ianaTimezone: _kDefaultTimezone,
            idempotencyKey: newIdempotencyKey(),
          ),
        );
    if (ok && mounted) {
      ref.read(planProvider.notifier).fetchToday(_kDefaultTimezone);
    }
  }
}

class _ActiveAndDraftView extends StatelessWidget {
  final PlanVersion draft;
  final bool draftReady;
  final String goal;
  final int frequency;
  final int duration;
  final bool bodyweight;
  final VoidCallback onConfirm;
  final VoidCallback onRegenerate;

  const _ActiveAndDraftView({
    required this.draft,
    required this.draftReady,
    required this.goal,
    required this.frequency,
    required this.duration,
    required this.bodyweight,
    required this.onConfirm,
    required this.onRegenerate,
  });

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Column(
        children: [
          const TabBar(
            tabs: [
              Tab(key: Key('plan-active-tab'), text: '当前生效'),
              Tab(key: Key('plan-draft-tab'), text: '待确认草案'),
            ],
          ),
          Expanded(
            child: TabBarView(
              children: [
                const _ActiveView(),
                if (draftReady)
                  _DraftReview(
                    draft: draft,
                    goal: goal,
                    frequency: frequency,
                    duration: duration,
                    bodyweight: bodyweight,
                    onConfirm: onConfirm,
                    onRegenerate: onRegenerate,
                  )
                else
                  const _StatusCard(
                    key: Key('plan-draft-profile-required'),
                    icon: Icons.assignment_late_outlined,
                    title: '草稿暂不可确认',
                    detail: '当前健康档案不可用；已生效计划仍可查看，草稿确认保持关闭。',
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _GenerationForm extends StatelessWidget {
  final String goal;
  final int frequency;
  final int duration;
  final bool bodyweight;
  final bool resistanceBand;
  final VoidCallback onGenerate;

  const _GenerationForm({
    required this.goal,
    required this.frequency,
    required this.duration,
    required this.bodyweight,
    required this.resistanceBand,
    required this.onGenerate,
  });

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('生成四周训练计划', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          initialValue: goal,
          decoration: const InputDecoration(labelText: '健身目标'),
          items: _kGoalLabels.entries
              .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
              .toList(),
          onChanged: null,
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<int>(
          initialValue: frequency,
          decoration: const InputDecoration(labelText: '每周训练次数'),
          items: [2, 3, 4, 5]
              .map((e) => DropdownMenuItem(value: e, child: Text('$e 次/周')))
              .toList(),
          onChanged: null,
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<int>(
          initialValue: duration,
          decoration: const InputDecoration(labelText: '单次时长'),
          items: [15, 30, 45, 60]
              .map((e) => DropdownMenuItem(value: e, child: Text('$e 分钟')))
              .toList(),
          onChanged: null,
        ),
        const SizedBox(height: 8),
        SwitchListTile(
          title: const Text('徒手训练'),
          value: bodyweight,
          onChanged: null,
        ),
        SwitchListTile(
          title: const Text('弹力带'),
          value: resistanceBand,
          onChanged: null,
        ),
        const SizedBox(height: 16),
        FilledButton(
          key: const Key('plan-generate-button'),
          onPressed: onGenerate,
          child: const Text('生成计划草案'),
        ),
        const SizedBox(height: 8),
        const Text(
          '以上选项来自当前健康档案。如需修改，请先更新健康档案；受限或风险状态不会生成计划。',
          style: TextStyle(fontSize: 12),
        ),
      ],
    );
  }
}

class _DraftReview extends StatelessWidget {
  final PlanVersion draft;
  final String goal;
  final int frequency;
  final int duration;
  final bool bodyweight;
  final VoidCallback onConfirm;
  final VoidCallback onRegenerate;

  const _DraftReview({
    required this.draft,
    required this.goal,
    required this.frequency,
    required this.duration,
    required this.bodyweight,
    required this.onConfirm,
    required this.onRegenerate,
  });

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          '计划草案 · ${_kGoalLabels[draft.requestedGoal] ?? draft.requestedGoal} · '
          '${draft.weeklyFrequency}次/周 · ${draft.sessionDurationMinutes}分钟',
        ),
        const SizedBox(height: 8),
        for (final session in draft.sessions)
          Card(
            child: ListTile(
              title: Text(
                '第${session.weekIndex}周 · 周${session.dayOfWeek} · 场次${session.sessionOrder}',
              ),
              subtitle: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final p in session.prescriptions)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Row(
                        children: [
                          if (p.exercise != null) ...[
                            _exerciseIllustration(p.exercise!, size: 52),
                            const SizedBox(width: 8),
                          ],
                          Expanded(
                            child: Text(
                              '${p.exercise?.nameZh ?? p.exerciseId} · '
                              '${p.sets}组'
                              '${p.reps != null ? " × ${p.reps}次" : ""}'
                              '${p.durationSeconds != null ? " · ${p.durationSeconds}秒" : ""}'
                              ' · 休息${p.restSeconds}秒',
                            ),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            ),
          ),
        const SizedBox(height: 16),
        FilledButton(
          key: const Key('plan-confirm-button'),
          onPressed: onConfirm,
          child: const Text('确认并生效'),
        ),
        const SizedBox(height: 8),
        OutlinedButton(
          key: const Key('plan-regenerate-button'),
          onPressed: onRegenerate,
          child: const Text('重新生成'),
        ),
      ],
    );
  }
}

class _ActiveView extends ConsumerStatefulWidget {
  const _ActiveView();
  @override
  ConsumerState<_ActiveView> createState() => _ActiveViewState();
}

class _ActiveViewState extends ConsumerState<_ActiveView> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(planProvider.notifier).fetchToday(_kDefaultTimezone);
    });
  }

  @override
  Widget build(BuildContext context) {
    final plan = ref.watch(planProvider);
    final active = plan.activePlan!;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                '生效计划 · ${_kGoalLabels[active.requestedGoal] ?? active.requestedGoal}',
              ),
            ),
            TextButton.icon(
              key: const Key('agent-plan-entry'),
              onPressed: () => _openAgent(
                context,
                entryType: 'training_plan',
                entityId: active.planVersionId,
              ),
              icon: const Icon(Icons.auto_awesome_outlined),
              label: const Text('问 Agent'),
            ),
          ],
        ),
        Text(
          '计划状态：已生效 · 安全校验：${_decisionGateLabel(active.decisionGate)}',
          style: const TextStyle(fontSize: 12),
        ),
        const Divider(),
        _todaySection(plan, active),
      ],
    );
  }

  Widget _todaySection(PlanState plan, PlanVersion active) {
    if (plan.todayStatus == LoadStatus.loading) {
      return const Padding(
        padding: EdgeInsets.all(16),
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (plan.todayStatus == LoadStatus.networkError) {
      return _StatusCard(
        key: const Key('today-status-unavailable'),
        icon: Icons.cloud_off,
        title: '今日加载失败',
        detail: '暂时无法加载今日训练。请检查连接后重试。',
        action: () =>
            ref.read(planProvider.notifier).fetchToday(_kDefaultTimezone),
        actionLabel: '重试',
      );
    }
    if (plan.todayStatus == LoadStatus.parseError || plan.today == null) {
      return _StatusCard(
        key: const Key('today-status-parse-error'),
        icon: Icons.broken_image_outlined,
        title: '今日数据解析异常',
        detail: '不会显示为可执行的训练。',
        action: () =>
            ref.read(planProvider.notifier).fetchToday(_kDefaultTimezone),
        actionLabel: '重试',
      );
    }
    final today = plan.today!;
    if (today.state == TodayState.blocked) {
      if (_isStaleToday(today)) {
        return const _StatusCard(
          key: Key('today-status-stale'),
          icon: Icons.sync_problem,
          title: '今日调整已过期',
          detail: '签到或策略上下文已变化，旧调整不可执行。请刷新后重新操作。',
        );
      }
      if (today.decisionGate == 'clarification_required') {
        return const _StatusCard(
          key: Key('today-status-missing'),
          icon: Icons.help_outline,
          title: '缺少今日必要信息',
          detail: '请先完成必要信息，再重新加载今日训练。',
        );
      }
      if (today.decisionGate == 'restricted' ||
          today.decisionGate == 'red_flag' ||
          today.changeReason == 'safety_revalidation_failed') {
        return _StatusCard(
          key: const Key('today-status-safety'),
          icon: Icons.block,
          title: '当前安全状态暂停训练',
          detail: '当前状态为${_decisionGateLabel(today.decisionGate)}，不会显示为可执行训练。',
        );
      }
      return const _StatusCard(
        key: Key('today-status-unavailable'),
        icon: Icons.error_outline,
        title: '今日训练暂不可执行',
        detail: '当前执行状态存在冲突或缺少可验证来源，不会按安全状态或成功状态展示。',
      );
    }
    final originalSession = _findSession(active, today.originalSessionId);
    if (today.originalSessionId != null && originalSession == null) {
      return const _StatusCard(
        key: Key('today-status-unavailable'),
        icon: Icons.error_outline,
        title: '原始训练场次不可用',
        detail: '无法核对原始与有效训练，不会提供调整按钮。',
      );
    }
    final controls = _AdjustmentControls(
      today: today,
      originalSession: originalSession,
      originalPlanMinutes: active.sessionDurationMinutes,
      planVersionId: active.planVersionId,
      state: plan.adjustState,
      message: plan.adjustMessage,
      timezone: _kDefaultTimezone,
      ref: ref,
    );
    switch (today.state) {
      case TodayState.noActivePlan:
        return const _StatusCard(icon: Icons.event_busy, title: '没有生效的训练计划');
      case TodayState.blocked:
        throw StateError('blocked Today handled before adjustment controls');
      case TodayState.restDay:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _StatusCard(
              icon: Icons.self_improvement,
              title: today.adjustmentKind == AdjustmentKind.activeRest
                  ? '今日主动休息（有效状态）'
                  : '今天是休息日',
              detail: today.adjustmentKind == AdjustmentKind.activeRest
                  ? '主动休息是有效的恢复状态，不计为缺勤或失败。'
                  : '按计划今日无训练任务。',
            ),
            if (originalSession != null) ...[
              const SizedBox(height: 12),
              controls,
            ],
          ],
        );
      case TodayState.planComplete:
        return const _StatusCard(
          icon: Icons.flag_outlined,
          title: '四周计划已完成',
          detail: '本周期已结束，不会重复显示第一周课程。',
        );
      case TodayState.session:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            controls,
            const SizedBox(height: 12),
            _SessionSection(
              session: today.session!,
              feedback: today.feedbackOutcomeState,
              substitutionApplied: today.substitutionApplied,
              onFeedback: (OutcomeState outcome) async {
                await ref
                    .read(planProvider.notifier)
                    .recordFeedback(
                      today.session!.sessionId,
                      FeedbackInput(
                        outcomeState: outcome,
                        idempotencyKey: newIdempotencyKey(),
                      ),
                      _kDefaultTimezone,
                    );
                if (mounted) {
                  ref.read(planProvider.notifier).fetchToday(_kDefaultTimezone);
                }
              },
              onSubstitute: (original, replacement) async {
                await ref
                    .read(planProvider.notifier)
                    .recordSubstitution(
                      today.session!.sessionId,
                      SubstitutionInput(
                        originalExerciseId: original,
                        replacementExerciseId: replacement,
                        idempotencyKey: newIdempotencyKey(),
                      ),
                      _kDefaultTimezone,
                    );
                if (mounted) {
                  ref.read(planProvider.notifier).fetchToday(_kDefaultTimezone);
                }
              },
            ),
          ],
        );
    }
  }
}

bool _isStaleToday(TodayResult today) => const {
  'adjustment_stale',
  'adjustment_version_stale',
}.contains(today.changeReason);

PlanSession? _findSession(PlanVersion plan, String? sessionId) {
  if (sessionId == null) return null;
  for (final session in plan.sessions) {
    if (session.sessionId == sessionId) return session;
  }
  return null;
}

String _kindLabel(AdjustmentKind? k) => switch (k) {
  AdjustmentKind.shortened => '缩短',
  AdjustmentKind.recovery => '恢复',
  AdjustmentKind.deferred => '延期',
  AdjustmentKind.activeRest => '主动休息',
  AdjustmentKind.unchanged => '未调整',
  null => '未调整',
};

String _formatDate(DateTime dt) {
  String two(int v) => v.toString().padLeft(2, '0');
  return '${dt.year}-${two(dt.month)}-${two(dt.day)}';
}

/// Foreground same-day adjustment controls. The button is the ONLY surface
/// that calls POST /training/today/adjustments; it never fires on load,
/// check-in save, feedback, substitution, or retry. It uses the original
/// source session identity returned by Today and the active plan version id.
/// Distinct loading/replay/stale/safety/missing/conflict/unavailable/parse
/// states are rendered separately and never as success.
class _AdjustmentControls extends ConsumerWidget {
  final TodayResult today;
  final PlanSession? originalSession;
  final int originalPlanMinutes;
  final String planVersionId;
  final AdjustApplyState state;
  final String? message;
  final String timezone;
  final WidgetRef ref;

  const _AdjustmentControls({
    required this.today,
    required this.originalSession,
    required this.originalPlanMinutes,
    required this.planVersionId,
    required this.state,
    required this.message,
    required this.timezone,
    required this.ref,
  });

  @override
  Widget build(BuildContext context, WidgetRef _) {
    final applying = state == AdjustApplyState.applying;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (today.adjustmentKind != null ||
            today.adjustmentReasonCodes.isNotEmpty)
          _effectiveOriginalBlock(),
        if (today.adjustmentKind != null ||
            today.adjustmentReasonCodes.isNotEmpty)
          const SizedBox(height: 12),
        FilledButton.icon(
          key: const Key('today-adjust-button'),
          onPressed: applying ? null : _apply,
          icon: applying
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.tune),
          label: Text(applying ? '调整中…' : '根据今日状态调整'),
        ),
        if (state != AdjustApplyState.idle &&
            state != AdjustApplyState.applying)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: _statusBanner(),
          ),
      ],
    );
  }

  Widget _effectiveOriginalBlock() {
    return Container(
      key: const Key('today-effective-original'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(AppConstants.cardColor),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(AppConstants.glassBorder)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (today.adjustmentKind != null)
            Text(
              '本次调整：${_kindLabel(today.adjustmentKind)}',
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: Color(AppConstants.accentColor),
              ),
            ),
          if (originalSession != null)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                key: const Key('today-original-summary'),
                '原始场次：${_sessionSummary(originalSession!, originalPlanMinutes)}',
                style: const TextStyle(
                  fontSize: 11,
                  color: Color(AppConstants.textMuted),
                ),
              ),
            ),
          if (today.session != null)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                key: const Key('today-effective-summary'),
                '有效场次：${_sessionSummary(today.session!, originalPlanMinutes)}',
                style: const TextStyle(
                  fontSize: 11,
                  color: Color(AppConstants.textColor),
                ),
              ),
            ),
          if (today.adjustmentReasonCodes.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                '原因：${today.adjustmentReasonCodes.join("、")}',
                style: const TextStyle(
                  fontSize: 11,
                  color: Color(AppConstants.textMuted),
                ),
              ),
            ),
          if (today.adjustmentKind == AdjustmentKind.deferred &&
              today.sourceLocalDate != null &&
              today.targetLocalDate != null)
            Padding(
              key: const Key('today-deferral'),
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                '延期：${_formatDate(today.sourceLocalDate!)} → '
                '${_formatDate(today.targetLocalDate!)}（有效状态，已移至合法日期）',
                style: const TextStyle(
                  fontSize: 12,
                  color: Color(AppConstants.textColor),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _statusBanner() {
    final (key, color, text) = switch (state) {
      AdjustApplyState.applied => (
        const Key('adjust-status-applied'),
        Color(AppConstants.normalColor),
        '已根据今日状态调整，已刷新今日执行。',
      ),
      AdjustApplyState.replayed => (
        const Key('adjust-status-replayed'),
        Color(AppConstants.normalColor),
        '该调整此前已记录，本次为幂等重放。',
      ),
      AdjustApplyState.stale => (
        const Key('adjust-status-stale'),
        Color(AppConstants.moderateColor),
        '今日上下文已变化（stale），请刷新后重试。',
      ),
      AdjustApplyState.safetyBlocked => (
        const Key('adjust-status-safety'),
        Color(AppConstants.severeColor),
        '当前安全状态不允许调整；不会显示为成功。',
      ),
      AdjustApplyState.missingInput => (
        const Key('adjust-status-missing'),
        Color(AppConstants.moderateColor),
        '缺少当日签到等必要信息，无法安全调整。',
      ),
      AdjustApplyState.conflict => (
        const Key('adjust-status-conflict'),
        Color(AppConstants.moderateColor),
        message ?? '当前冲突，暂不可调整。',
      ),
      AdjustApplyState.unavailable => (
        const Key('adjust-status-unavailable'),
        Color(AppConstants.textMuted),
        '调整服务暂不可用，请稍后重试。',
      ),
      AdjustApplyState.parseError => (
        const Key('adjust-status-parse'),
        Color(AppConstants.severeColor),
        '调整结果解析异常，不会显示为成功。',
      ),
      AdjustApplyState.idle || AdjustApplyState.applying => (
        const Key('adjust-status-idle'),
        Color(AppConstants.textMuted),
        '',
      ),
    };
    return Container(
      key: key,
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color),
      ),
      child: Text(text, style: TextStyle(fontSize: 12, color: color)),
    );
  }

  void _apply() {
    // Only an explicit foreground button press reaches the mutation. The
    // Expected identity is always the original source session from Today. A
    // missing source fails closed before this control is rendered.
    ref
        .read(planProvider.notifier)
        .applyTodayAdjustment(
          AdjustmentRequestInput(
            expectedPlanVersionId: planVersionId,
            expectedSessionId: today.originalSessionId!,
            ianaTimezone: timezone,
            idempotencyKey: newIdempotencyKey(),
          ),
        );
  }
}

String _sessionSummary(PlanSession session, int fallbackMinutes) {
  final minutes = session.targetMinutes ?? fallbackMinutes;
  final exercises = session.prescriptions
      .map((item) => item.exercise?.nameZh ?? item.exerciseId)
      .join('、');
  return '$minutes 分钟 · $exercises';
}

class _SessionSection extends StatelessWidget {
  final PlanSession session;
  final OutcomeState? feedback;
  final bool substitutionApplied;
  final Future<void> Function(OutcomeState outcome) onFeedback;
  final Future<void> Function(String original, String replacement) onSubstitute;
  const _SessionSection({
    required this.session,
    required this.feedback,
    required this.substitutionApplied,
    required this.onFeedback,
    required this.onSubstitute,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                '今日训练 · 第${session.weekIndex}周 周${session.dayOfWeek}',
              ),
            ),
            TextButton.icon(
              key: const Key('agent-session-entry'),
              onPressed: () => _openAgent(
                context,
                entryType: 'training_session',
                entityId: session.sessionId,
              ),
              icon: const Icon(Icons.auto_awesome_outlined),
              label: const Text('问 Agent'),
            ),
          ],
        ),
        for (final p in session.prescriptions)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    p.exercise?.nameZh ?? p.exerciseId,
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                  if (p.exercise != null) ...[
                    const SizedBox(height: 8),
                    Center(
                      child: _exerciseIllustration(p.exercise!, size: 140),
                    ),
                  ],
                  Text(
                    '${p.sets}组'
                    '${p.reps != null ? " × ${p.reps}次" : ""}'
                    '${p.durationSeconds != null ? " · ${p.durationSeconds}秒" : ""}'
                    ' · 休息${p.restSeconds}秒',
                  ),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: TextButton.icon(
                      key: Key('agent-exercise-${p.exerciseId}'),
                      onPressed: () => _openAgent(
                        context,
                        entryType: 'training_exercise',
                        entityId: p.exerciseId,
                      ),
                      icon: const Icon(Icons.auto_awesome_outlined),
                      label: const Text('让 Agent 解释'),
                    ),
                  ),
                  if (p.exercise != null) ...[
                    const SizedBox(height: 4),
                    const Text('动作步骤（知识库原文）', style: TextStyle(fontSize: 12)),
                    for (final step in p.exercise!.instructionSteps.take(4))
                      Text('· $step', style: const TextStyle(fontSize: 12)),
                    if (p.exercise!.substitutionIds.isNotEmpty &&
                        !substitutionApplied &&
                        feedback == null) ...[
                      const SizedBox(height: 8),
                      const Text('可选替代动作', style: TextStyle(fontSize: 12)),
                      for (final (index, replacement)
                          in p.exercise!.substitutionIds.indexed)
                        TextButton(
                          key: Key('substitute-${p.exerciseId}-$replacement'),
                          onPressed: () =>
                              onSubstitute(p.exerciseId, replacement),
                          child: Text('替代动作 ${index + 1}'),
                        ),
                    ],
                  ],
                ],
              ),
            ),
          ),
        const SizedBox(height: 12),
        Text(feedback == null ? '今日完成情况' : '已记录：${_outcomeLabel(feedback!)}'),
        Wrap(
          spacing: 8,
          children: [
            for (final o in OutcomeState.values)
              ActionChip(
                key: Key('feedback-${o.name}'),
                label: Text(_outcomeLabel(o)),
                onPressed: feedback == null ? () => onFeedback(o) : null,
              ),
          ],
        ),
      ],
    );
  }
}

String _decisionGateLabel(String? gate) => switch (gate) {
  'eligible' => '已通过',
  'eligible_conservative' => '保守条件通过',
  'clarification_required' => '需要补充信息',
  'restricted' => '受限',
  'red_flag' => '已触发安全阻断',
  _ => '未通过',
};

class _StatusCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? detail;
  final VoidCallback? action;
  final String? actionLabel;
  const _StatusCard({
    super.key,
    required this.icon,
    required this.title,
    this.detail,
    this.action,
    this.actionLabel,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 48),
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
              OutlinedButton(onPressed: action, child: Text(actionLabel!)),
            ],
          ],
        ),
      ),
    );
  }
}
