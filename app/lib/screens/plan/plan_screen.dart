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
import '../../core/idempotency_key.dart';
import '../../models/plan.dart';
import '../../providers/assessment_provider.dart' show LoadStatus;
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

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(planProvider.notifier).fetchActive();
      ref.read(planProvider.notifier).fetchDraft();
    });
  }

  @override
  Widget build(BuildContext context) {
    final plan = ref.watch(planProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('训练计划')),
      body: SafeArea(child: _body(context, plan)),
    );
  }

  Widget _body(BuildContext context, PlanState plan) {
    if (plan.activeStatus == LoadStatus.data && plan.activePlan != null) {
      return _ActiveView(plan: plan);
    }
    if (plan.draftStatus == LoadStatus.data && plan.draft != null) {
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
        plan.activeStatus == LoadStatus.loading) {
      return const Center(child: CircularProgressIndicator());
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
      onChangedGoal: (v) => setState(() => _goal = v),
      onChangedFrequency: (v) => setState(() => _frequency = v),
      onChangedDuration: (v) => setState(() => _duration = v),
      onChangedBodyweight: (v) => setState(() => _bodyweight = v),
      onGenerate: _generate,
    );
  }

  Future<void> _generate() async {
    await ref.read(planProvider.notifier).generateDraft(DraftInput(
          fitnessGoal: _goal,
          weeklyFrequency: _frequency,
          sessionDurationMinutes: _duration,
          equipmentBodyweight: _bodyweight,
          equipmentResistanceBand: false,
          ianaTimezone: _kDefaultTimezone,
          idempotencyKey: newIdempotencyKey(),
        ));
  }

  Future<void> _confirm() async {
    final ok = await ref.read(planProvider.notifier).confirm(ConfirmInput(
          fitnessGoal: _goal,
          weeklyFrequency: _frequency,
          sessionDurationMinutes: _duration,
          equipmentBodyweight: _bodyweight,
          equipmentResistanceBand: false,
          ianaTimezone: _kDefaultTimezone,
          idempotencyKey: newIdempotencyKey(),
        ));
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
  final ValueChanged<String> onChangedGoal;
  final ValueChanged<int> onChangedFrequency;
  final ValueChanged<int> onChangedDuration;
  final ValueChanged<bool> onChangedBodyweight;
  final VoidCallback onGenerate;

  const _GenerationForm({
    required this.goal,
    required this.frequency,
    required this.duration,
    required this.bodyweight,
    required this.onChangedGoal,
    required this.onChangedFrequency,
    required this.onChangedDuration,
    required this.onChangedBodyweight,
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
          onChanged: (v) {
            if (v != null) onChangedGoal(v);
          },
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<int>(
          initialValue: frequency,
          decoration: const InputDecoration(labelText: '每周训练次数'),
          items: [2, 3, 4, 5]
              .map((e) => DropdownMenuItem(value: e, child: Text('$e 次/周')))
              .toList(),
          onChanged: (v) {
            if (v != null) onChangedFrequency(v);
          },
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<int>(
          initialValue: duration,
          decoration: const InputDecoration(labelText: '单次时长'),
          items: [15, 30, 45, 60]
              .map((e) => DropdownMenuItem(value: e, child: Text('$e 分钟')))
              .toList(),
          onChanged: (v) {
            if (v != null) onChangedDuration(v);
          },
        ),
        const SizedBox(height: 8),
        SwitchListTile(
          title: const Text('徒手训练'),
          value: bodyweight,
          onChanged: onChangedBodyweight,
        ),
        const SizedBox(height: 16),
        FilledButton(
          key: const Key('plan-generate-button'),
          onPressed: onGenerate,
          child: const Text('生成计划草案'),
        ),
        const SizedBox(height: 8),
        const Text(
          '计划基于当前健康档案与体态评估，由确定性引擎生成；受限或风险状态不会生成计划。',
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
        Text('计划草案 · ${_kGoalLabels[draft.requestedGoal] ?? draft.requestedGoal} · '
            '${draft.weeklyFrequency}次/周 · ${draft.sessionDurationMinutes}分钟'),
        const SizedBox(height: 8),
        for (final session in draft.sessions)
          Card(
            child: ListTile(
              title: Text(
                  '第${session.weekIndex}周 · 周${session.dayOfWeek} · 场次${session.sessionOrder}'),
              subtitle: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final p in session.prescriptions)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
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
        Text('生效计划 · ${_kGoalLabels[active.requestedGoal] ?? active.requestedGoal}'),
        Text('版本 ${active.changeReason} · 决策 ${active.decisionGate}',
            style: const TextStyle(fontSize: 12)),
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
        return const _StatusCard(
            icon: Icons.event_busy, title: '没有生效的训练计划');
      case TodayState.blocked:
        return _StatusCard(
          icon: Icons.block,
          title: '当前状态暂停训练',
          detail: '检测到安全风险信号（${today.decisionGate ?? "blocked"}），已停止训练；不会显示为成功。',
        );
      case TodayState.restDay:
        return _StatusCard(
          icon: Icons.self_improvement,
          title: '今天是休息日',
          detail: '按计划今日无训练任务。',
        );
      case TodayState.session:
        return _SessionSection(
          session: today.session!,
          onFeedback: (OutcomeState outcome) async {
            await ref.read(planProvider.notifier).recordFeedback(
                  today.session!.sessionId,
                  FeedbackInput(
                      outcomeState: outcome, idempotencyKey: newIdempotencyKey()),
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
  final Future<void> Function(OutcomeState outcome) onFeedback;
  const _SessionSection({required this.session, required this.onFeedback});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('今日训练 · 第${session.weekIndex}周 周${session.dayOfWeek}'),
        for (final p in session.prescriptions)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(p.exercise?.nameZh ?? p.exerciseId,
                      style: const TextStyle(fontWeight: FontWeight.bold)),
                  Text('${p.sets}组'
                      '${p.reps != null ? " × ${p.reps}次" : ""}'
                      '${p.durationSeconds != null ? " · ${p.durationSeconds}秒" : ""}'
                      ' · 休息${p.restSeconds}秒'),
                  if (p.exercise != null) ...[
                    const SizedBox(height: 4),
                    for (final step in p.exercise!.instructionSteps.take(4))
                      Text('· $step', style: const TextStyle(fontSize: 12)),
                  ],
                ],
              ),
            ),
          ),
        const SizedBox(height: 12),
        const Text('今日完成情况'),
        Wrap(
          spacing: 8,
          children: [
            for (final o in OutcomeState.values)
              ActionChip(
                key: Key('feedback-${o.name}'),
                label: Text(_outcomeLabel(o)),
                onPressed: () => onFeedback(o),
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
              Text(detail!,
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 13)),
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
