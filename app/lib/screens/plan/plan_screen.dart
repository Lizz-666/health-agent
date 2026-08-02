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
    if (plan.activeStatus == LoadStatus.data && plan.activePlan != null) {
      return _ActiveView(plan: plan);
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
    if (plan.draftStatus == LoadStatus.loading ||
        plan.activeStatus == LoadStatus.loading ||
        ref.watch(healthProfileProvider).status == LoadStatus.loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (!_profileReady) return _profileRequired();
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
    final ok = await ref
        .read(planProvider.notifier)
        .confirm(
          ConfirmInput(
            fitnessGoal: _goal,
            weeklyFrequency: _frequency,
            sessionDurationMinutes: _duration,
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
  final PlanState plan;
  const _ActiveView({required this.plan});
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
          '版本 ${active.changeReason} · 决策 ${active.decisionGate}',
          style: const TextStyle(fontSize: 12),
        ),
        const Divider(),
        _todaySection(plan),
      ],
    );
  }

  Widget _todaySection(PlanState plan) {
    if (plan.todayStatus == LoadStatus.loading) {
      return const Padding(
        padding: EdgeInsets.all(16),
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (plan.todayStatus == LoadStatus.networkError) {
      return _StatusCard(
        icon: Icons.cloud_off,
        title: '今日加载失败',
        detail: plan.error ?? '请稍后重试',
        action: () =>
            ref.read(planProvider.notifier).fetchToday(_kDefaultTimezone),
        actionLabel: '重试',
      );
    }
    if (plan.todayStatus == LoadStatus.parseError || plan.today == null) {
      return const _StatusCard(
        icon: Icons.broken_image_outlined,
        title: '今日数据解析异常',
        detail: '不会显示为可执行的训练。',
      );
    }
    final today = plan.today!;
    switch (today.state) {
      case TodayState.noActivePlan:
        return const _StatusCard(icon: Icons.event_busy, title: '没有生效的训练计划');
      case TodayState.blocked:
        return _StatusCard(
          icon: Icons.block,
          title: '当前状态暂停训练',
          detail:
              '检测到安全风险信号（${today.decisionGate ?? "blocked"}），已停止训练；不会显示为成功。',
        );
      case TodayState.restDay:
        return _StatusCard(
          icon: Icons.self_improvement,
          title: '今天是休息日',
          detail: '按计划今日无训练任务。',
        );
      case TodayState.planComplete:
        return const _StatusCard(
          icon: Icons.flag_outlined,
          title: '四周计划已完成',
          detail: '本周期已结束，不会重复显示第一周课程。',
        );
      case TodayState.session:
        return _SessionSection(
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
        );
    }
  }
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
                    for (final step in p.exercise!.instructionSteps.take(4))
                      Text('· $step', style: const TextStyle(fontSize: 12)),
                    if (p.exercise!.substitutionIds.isNotEmpty &&
                        !substitutionApplied &&
                        feedback == null) ...[
                      const SizedBox(height: 8),
                      const Text('可选替代动作', style: TextStyle(fontSize: 12)),
                      for (final replacement in p.exercise!.substitutionIds)
                        TextButton(
                          key: Key('substitute-${p.exerciseId}-$replacement'),
                          onPressed: () =>
                              onSubstitute(p.exerciseId, replacement),
                          child: Text('替换为 $replacement'),
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

class _StatusCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? detail;
  final VoidCallback? action;
  final String? actionLabel;
  const _StatusCard({
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
