// app/lib/screens/profile/health_profile_screen.dart
//
// Phase 2 health profile My-page surface (spec Domain Model, Health Profile).
//
// Safety / state contract (Task 6):
//  - This screen consumes healthProfileProvider only; it is independent from
//    the posture profile screen and never mixes health and posture state.
//  - loading / empty (not configured) / networkError / parseError are visually
//    distinct; neither network nor parse failure is allowed to render as a
//    ready/normal profile or as "no data needed".
//  - A not-configured profile (configured=false, profile=null) shows the
//    deterministic readiness (missing_required_data / restricted) and the
//    concrete missingFields; it never fabricates defaults.
//  - Optional fields are shown as "未填写"/"未配置" when null; missing stays
//    missing.
//  - restricted readiness is shown explicitly and never as ready.
//  - Deletion requires a confirmation dialog before calling provider delete;
//    on success the provider refetches and the screen returns to the
//    not-configured state. The delete control is disabled while loading.
//  - The edit/correct form is full-replacement; existing pain / allergy /
//    diet lists are carried through so they are not wiped on save.
//  - No AI, recommendation, training-plan or diet advice is emitted.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants.dart';
import '../../models/health_profile.dart';
import '../../providers/assessment_provider.dart' show LoadStatus;
import '../../providers/health_profile_provider.dart';
import '../../widgets/disclaimer_banner.dart';

class HealthProfileScreen extends ConsumerStatefulWidget {
  const HealthProfileScreen({super.key});

  @override
  ConsumerState<HealthProfileScreen> createState() =>
      _HealthProfileScreenState();
}

class _HealthProfileScreenState extends ConsumerState<HealthProfileScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      ref.read(healthProfileProvider.notifier).fetchProfile();
    });
  }

  Future<void> _confirmDelete() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除健康档案'),
        content: const Text('确认删除健康档案？该操作不可撤销，将清除你的健康档案数据。'),
        actions: [
          TextButton(
            key: const Key('health-delete-cancel'),
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          ElevatedButton(
            key: const Key('health-delete-confirm'),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(AppConstants.severeColor),
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('确认删除'),
          ),
        ],
      ),
    );
    if (ok == true && mounted) {
      await ref.read(healthProfileProvider.notifier).deleteProfile();
    }
  }

  Future<void> _openEditForm() async {
    final result = ref.read(healthProfileProvider).result;
    final profile = result?.profile;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => _HealthProfileEditSheet(existing: profile),
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(healthProfileProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('健康档案')),
      body: Column(
        children: [
          const DisclaimerBanner(),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: _HealthProfileBody(
                state: state,
                onRetry: () =>
                    ref.read(healthProfileProvider.notifier).fetchProfile(),
                onEdit: _openEditForm,
                onDelete: _confirmDelete,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Body: state switch (loading / empty / networkError / parseError / data)
// ---------------------------------------------------------------------------

class _HealthProfileBody extends StatelessWidget {
  final HealthProfileState state;
  final VoidCallback onRetry;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  const _HealthProfileBody({
    required this.state,
    required this.onRetry,
    required this.onEdit,
    required this.onDelete,
  });

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
              '加载健康档案中…',
              style: TextStyle(color: Color(AppConstants.textMuted)),
            ),
          ],
        ),
      );
    }
    if (status == LoadStatus.networkError) {
      return _box(
        child: _ErrorState(
          message: state.error ?? '健康档案加载失败',
          onRetry: onRetry,
        ),
      );
    }
    if (status == LoadStatus.parseError) {
      return _box(
        child: _ErrorState(message: '数据解析异常', onRetry: onRetry),
      );
    }
    final result = state.result!;
    if (status == LoadStatus.empty || !result.configured) {
      return _box(
        child: _NotConfiguredView(
          readiness: result.readiness,
          onEdit: onEdit,
        ),
      );
    }
    return _ConfiguredView(
      result: result,
      onEdit: onEdit,
      onDelete: onDelete,
    );
  }
}

// ---------------------------------------------------------------------------
// Not-configured view: deterministic readiness + missing fields (no defaults)
// ---------------------------------------------------------------------------

class _NotConfiguredView extends StatelessWidget {
  final HealthReadiness readiness;
  final VoidCallback onEdit;

  const _NotConfiguredView({required this.readiness, required this.onEdit});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Icon(
          Icons.favorite_outline,
          size: 48,
          color: Color(AppConstants.textMuted),
        ),
        const SizedBox(height: 12),
        const Text(
          '尚未配置健康档案',
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            color: Color(AppConstants.textColor),
          ),
        ),
        const SizedBox(height: 4),
        const Text(
          '完善基本信息后即可生成健康档案。信息缺失会如实显示，不会自动补全。',
          style: TextStyle(
            fontSize: 12,
            color: Color(AppConstants.textMuted),
          ),
        ),
        const SizedBox(height: 12),
        _ReadinessCard(readiness: readiness),
        const SizedBox(height: 16),
        SizedBox(
          width: double.infinity,
          child: ElevatedButton.icon(
            key: const Key('health-edit-button'),
            onPressed: onEdit,
            icon: const Icon(Icons.edit),
            label: const Text('完善健康档案'),
          ),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Configured view: fields + actions
// ---------------------------------------------------------------------------

class _ConfiguredView extends StatelessWidget {
  final HealthProfileResult result;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  const _ConfiguredView({
    required this.result,
    required this.onEdit,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    final profile = result.profile!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _ReadinessCard(readiness: result.readiness),
        const SizedBox(height: 16),
        _box(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('档案信息', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              _Field(
                label: '健身目标',
                value: _fitnessGoalLabel(profile.fitnessGoal),
              ),
              _Field(
                label: '训练经验',
                value: _experienceLabel(profile.trainingExperience),
              ),
              _Field(
                label: '每周频率',
                value: profile.weeklyFrequency == null
                    ? null
                    : '${profile.weeklyFrequency} 次/周',
              ),
              _Field(
                label: '单次时长',
                value: _durationLabel(profile.sessionDurationMinutes),
              ),
              _Field(
                label: '器械',
                value: _equipmentLabel(profile.equipment),
              ),
              _Field(
                label: '疼痛/损伤限制',
                value: _listCountLabel(
                  profile.painInjuryLimitations?.length,
                  singular: '项',
                ),
              ),
              _Field(
                label: '过敏',
                value: _listCountLabel(
                  profile.allergies?.length,
                  singular: '项',
                ),
              ),
              _Field(
                label: '饮食排除',
                value: _listCountLabel(
                  profile.dietExclusions?.length,
                  singular: '项',
                ),
              ),
              const SizedBox(height: 8),
              Text(
                '更新于 ${_formatDateTime(profile.updatedAt ?? profile.createdAt)}',
                style: const TextStyle(
                  fontSize: 11,
                  color: Color(AppConstants.textMuted),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        Text(
          '疼痛/过敏/饮食等详细条目目前为只读展示，保存档案时会被原样保留。',
          style: const TextStyle(
            fontSize: 11,
            color: Color(AppConstants.textMuted),
          ),
        ),
        const SizedBox(height: 16),
        SizedBox(
          width: double.infinity,
          child: ElevatedButton.icon(
            key: const Key('health-edit-button'),
            onPressed: onEdit,
            icon: const Icon(Icons.edit),
            label: const Text('更正 / 编辑'),
          ),
        ),
        const SizedBox(height: 8),
        SizedBox(
          width: double.infinity,
          child: OutlinedButton.icon(
            key: const Key('health-delete-button'),
            onPressed: onDelete,
            style: OutlinedButton.styleFrom(
              foregroundColor: const Color(AppConstants.severeColor),
              side: const BorderSide(color: Color(AppConstants.severeColor)),
            ),
            icon: const Icon(Icons.delete_outline),
            label: const Text('删除健康档案'),
          ),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Readiness card: ready / missing_required_data / restricted (never ready+stale)
// ---------------------------------------------------------------------------

class _ReadinessCard extends StatelessWidget {
  final HealthReadiness readiness;
  const _ReadinessCard({required this.readiness});

  @override
  Widget build(BuildContext context) {
    final (color, icon, label) = switch (readiness.readiness) {
      ReadinessTier.ready => (
        const Color(AppConstants.normalColor),
        Icons.check_circle,
        '档案就绪',
      ),
      ReadinessTier.missingRequiredData => (
        const Color(AppConstants.moderateColor),
        Icons.info,
        '信息不完整',
      ),
      ReadinessTier.restricted => (
        const Color(AppConstants.severeColor),
        Icons.warning_amber,
        '受限',
      ),
    };
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: color, size: 18),
              const SizedBox(width: 8),
              Text(
                label,
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: color,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            readiness.reason,
            style: const TextStyle(
              fontSize: 12,
              color: Color(AppConstants.textColor),
            ),
          ),
          if (readiness.missingFields.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              '缺失字段：${readiness.missingFields.join('、')}',
              style: const TextStyle(
                fontSize: 11,
                color: Color(AppConstants.textMuted),
              ),
            ),
          ],
          if (readiness.restrictedReason != null) ...[
            const SizedBox(height: 6),
            Text(
              '受限原因：${readiness.restrictedReason}',
              style: const TextStyle(
                fontSize: 11,
                color: Color(AppConstants.severeColor),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Edit form (bottom sheet): scalars + enums only; lists carried through
// ---------------------------------------------------------------------------

class _HealthProfileEditSheet extends ConsumerStatefulWidget {
  final HealthProfile? existing;
  const _HealthProfileEditSheet({required this.existing});

  @override
  ConsumerState<_HealthProfileEditSheet> createState() =>
      _HealthProfileEditSheetState();
}

class _HealthProfileEditSheetState
    extends ConsumerState<_HealthProfileEditSheet> {
  late FitnessGoal? _goal;
  late TrainingExperience? _experience;
  late int? _weeklyFrequency;
  late SessionDurationMinutes? _duration;
  late bool? _bodyweight;
  late bool? _resistanceBand;
  late YesNoUnknown? _underage;
  late YesNoUnknown? _pregnancyOrPostpartum;
  late YesNoUnknown? _recentSurgeryOrMajorInjury;
  late YesNoUnknown? _majorChronicCondition;
  late YesNoUnknown? _eatingDisorderConcern;
  late YesNoUnknown? _professionalInstructionLimitations;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final p = widget.existing;
    _goal = p?.fitnessGoal;
    _experience = p?.trainingExperience;
    _weeklyFrequency = p?.weeklyFrequency;
    _duration = p?.sessionDurationMinutes;
    _bodyweight = p?.equipment?.bodyweight;
    _resistanceBand = p?.equipment?.resistanceBand;
    final r = p?.riskScreen;
    _underage = r?.underage;
    _pregnancyOrPostpartum = r?.pregnancyOrPostpartum;
    _recentSurgeryOrMajorInjury = r?.recentSurgeryOrMajorInjury;
    _majorChronicCondition = r?.majorChronicCondition;
    _eatingDisorderConcern = r?.eatingDisorderConcern;
    _professionalInstructionLimitations = r?.professionalInstructionLimitations;
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          16,
          16,
          16,
          16 + MediaQuery.of(context).viewInsets.bottom,
        ),
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                widget.existing == null ? '完善健康档案' : '更正健康档案',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 4),
              const Text(
                '未填写项将保存为缺失，不会被自动补全。疼痛/过敏/饮食等条目保留原值。',
                style: TextStyle(
                  fontSize: 11,
                  color: Color(AppConstants.textMuted),
                ),
              ),
              const SizedBox(height: 12),
              _DropdownField<FitnessGoal?>(
                label: '健身目标',
                value: _goal,
                items: const [
                  DropdownMenuItem(value: null, child: Text('未填写')),
                  DropdownMenuItem(
                    value: FitnessGoal.postureImprovement,
                    child: Text('改善体态'),
                  ),
                  DropdownMenuItem(
                    value: FitnessGoal.fatLoss,
                    child: Text('减脂'),
                  ),
                  DropdownMenuItem(
                    value: FitnessGoal.basicStrength,
                    child: Text('基础力量'),
                  ),
                  DropdownMenuItem(
                    value: FitnessGoal.mobility,
                    child: Text('活动度'),
                  ),
                  DropdownMenuItem(
                    value: FitnessGoal.generalWellness,
                    child: Text('综合健康'),
                  ),
                ],
                onChanged: _saving ? null : (v) => setState(() => _goal = v),
              ),
              _DropdownField<TrainingExperience?>(
                label: '训练经验',
                value: _experience,
                items: const [
                  DropdownMenuItem(value: null, child: Text('未填写')),
                  DropdownMenuItem(
                    value: TrainingExperience.beginner,
                    child: Text('初级'),
                  ),
                  DropdownMenuItem(
                    value: TrainingExperience.someExperience,
                    child: Text('有一些经验'),
                  ),
                  DropdownMenuItem(
                    value: TrainingExperience.experienced,
                    child: Text('经验丰富'),
                  ),
                ],
                onChanged: _saving ? null : (v) => setState(() => _experience = v),
              ),
              _DropdownField<int?>(
                label: '每周频率',
                value: _weeklyFrequency,
                items: [
                  const DropdownMenuItem(value: null, child: Text('未填写')),
                  for (final f in const [2, 3, 4, 5])
                    DropdownMenuItem(value: f, child: Text('$f 次/周')),
                ],
                onChanged: _saving ? null : (v) => setState(() => _weeklyFrequency = v),
              ),
              _DropdownField<SessionDurationMinutes?>(
                label: '单次时长',
                value: _duration,
                items: const [
                  DropdownMenuItem(value: null, child: Text('未填写')),
                  DropdownMenuItem(
                    value: SessionDurationMinutes.fifteen,
                    child: Text('15 分钟'),
                  ),
                  DropdownMenuItem(
                    value: SessionDurationMinutes.thirty,
                    child: Text('30 分钟'),
                  ),
                  DropdownMenuItem(
                    value: SessionDurationMinutes.fortyFive,
                    child: Text('45 分钟'),
                  ),
                  DropdownMenuItem(
                    value: SessionDurationMinutes.sixty,
                    child: Text('60 分钟'),
                  ),
                ],
                onChanged: _saving ? null : (v) => setState(() => _duration = v),
              ),
              const SizedBox(height: 8),
              const Text(
                '器械',
                style: TextStyle(
                  fontSize: 12,
                  color: Color(AppConstants.textMuted),
                ),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('自重训练'),
                value: _bodyweight ?? false,
                onChanged: _saving
                    ? null
                    : (v) => setState(() => _bodyweight = v),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('弹力带'),
                value: _resistanceBand ?? false,
                onChanged: _saving
                    ? null
                    : (v) => setState(() => _resistanceBand = v),
              ),
              const SizedBox(height: 8),
              const Text(
                '安全筛查（不指定 = 未填写）',
                style: TextStyle(
                  fontSize: 12,
                  color: Color(AppConstants.textMuted),
                ),
              ),
              _DropdownField<YesNoUnknown?>(
                label: '未成年',
                value: _underage,
                items: _yesNoUnknownItems(),
                onChanged: _saving ? null : (v) => setState(() => _underage = v),
              ),
              _DropdownField<YesNoUnknown?>(
                label: '孕期或产后',
                value: _pregnancyOrPostpartum,
                items: _yesNoUnknownItems(),
                onChanged: _saving
                    ? null
                    : (v) => setState(() => _pregnancyOrPostpartum = v),
              ),
              _DropdownField<YesNoUnknown?>(
                label: '近期手术或重大损伤',
                value: _recentSurgeryOrMajorInjury,
                items: _yesNoUnknownItems(),
                onChanged: _saving
                    ? null
                    : (v) =>
                        setState(() => _recentSurgeryOrMajorInjury = v),
              ),
              _DropdownField<YesNoUnknown?>(
                label: '重大慢性病',
                value: _majorChronicCondition,
                items: _yesNoUnknownItems(),
                onChanged: _saving
                    ? null
                    : (v) => setState(() => _majorChronicCondition = v),
              ),
              _DropdownField<YesNoUnknown?>(
                label: '饮食失调倾向',
                value: _eatingDisorderConcern,
                items: _yesNoUnknownItems(),
                onChanged: _saving
                    ? null
                    : (v) => setState(() => _eatingDisorderConcern = v),
              ),
              _DropdownField<YesNoUnknown?>(
                label: '专业指导受限',
                value: _professionalInstructionLimitations,
                items: _yesNoUnknownItems(),
                onChanged: _saving
                    ? null
                    : (v) =>
                        setState(() => _professionalInstructionLimitations = v),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: _saving ? null : () => Navigator.pop(context),
                      child: const Text('取消'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: ElevatedButton(
                      key: const Key('health-save-button'),
                      onPressed: _saving ? null : _save,
                      child: _saving
                          ? Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: const [
                                SizedBox(
                                  width: 14,
                                  height: 14,
                                  child:
                                      CircularProgressIndicator(strokeWidth: 2),
                                ),
                                SizedBox(width: 8),
                                Text('保存中…'),
                              ],
                            )
                          : const Text('保存'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  List<DropdownMenuItem<YesNoUnknown?>> _yesNoUnknownItems() => const [
        DropdownMenuItem(value: null, child: Text('未填写')),
        DropdownMenuItem(value: YesNoUnknown.yes, child: Text('是')),
        DropdownMenuItem(value: YesNoUnknown.no, child: Text('否')),
        DropdownMenuItem(value: YesNoUnknown.unknown, child: Text('不确定')),
      ];

  Future<void> _save() async {
    setState(() => _saving = true);
    final notifier = ref.read(healthProfileProvider.notifier);
    final existing = ref.read(healthProfileProvider).result?.profile;
    final update = HealthProfileUpdate(
      fitnessGoal: _goal,
      trainingExperience: _experience,
      weeklyFrequency: _weeklyFrequency,
      sessionDurationMinutes: _duration,
      equipment: Equipment(
        bodyweight: _bodyweight,
        resistanceBand: _resistanceBand,
      ),
      // Preserve existing list entries verbatim; they are read-only here.
      painInjuryLimitations: existing?.painInjuryLimitations,
      riskScreen: RiskScreen(
        underage: _underage,
        pregnancyOrPostpartum: _pregnancyOrPostpartum,
        recentSurgeryOrMajorInjury: _recentSurgeryOrMajorInjury,
        majorChronicCondition: _majorChronicCondition,
        eatingDisorderConcern: _eatingDisorderConcern,
        professionalInstructionLimitations: _professionalInstructionLimitations,
      ),
      allergies: existing?.allergies,
      dietExclusions: existing?.dietExclusions,
    );
    final ok = await notifier.updateProfile(update);
    if (!mounted) return;
    setState(() => _saving = false);
    if (ok) {
      Navigator.pop(context);
    }
  }
}

// ---------------------------------------------------------------------------
// Small shared widgets
// ---------------------------------------------------------------------------

class _Field extends StatelessWidget {
  final String label;
  final String? value;
  const _Field({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: const TextStyle(color: Color(AppConstants.textMuted)),
          ),
          Flexible(
            child: Text(
              value ?? '未填写',
              style: const TextStyle(
                fontSize: 15,
                color: Color(AppConstants.textColor),
              ),
            ),
          ),
        ],
      ),
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
          key: const Key('health-retry'),
          onPressed: onRetry,
          icon: const Icon(Icons.refresh, size: 18),
          label: const Text('重试'),
        ),
      ],
    );
  }
}

class _DropdownField<T extends Object?> extends StatelessWidget {
  final String label;
  final T? value;
  final List<DropdownMenuItem<T>> items;
  final void Function(T?)? onChanged;
  const _DropdownField({
    required this.label,
    required this.value,
    required this.items,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
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
      ),
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

String? _fitnessGoalLabel(FitnessGoal? v) => switch (v) {
      FitnessGoal.postureImprovement => '改善体态',
      FitnessGoal.fatLoss => '减脂',
      FitnessGoal.basicStrength => '基础力量',
      FitnessGoal.mobility => '活动度',
      FitnessGoal.generalWellness => '综合健康',
      null => null,
    };

String? _experienceLabel(TrainingExperience? v) => switch (v) {
      TrainingExperience.beginner => '初级',
      TrainingExperience.someExperience => '有一些经验',
      TrainingExperience.experienced => '经验丰富',
      null => null,
    };

String? _durationLabel(SessionDurationMinutes? v) => switch (v) {
      SessionDurationMinutes.fifteen => '15 分钟',
      SessionDurationMinutes.thirty => '30 分钟',
      SessionDurationMinutes.fortyFive => '45 分钟',
      SessionDurationMinutes.sixty => '60 分钟',
      null => null,
    };

String? _equipmentLabel(Equipment? e) {
  if (e == null) return null;
  if (e.bodyweight == null && e.resistanceBand == null) return null;
  final parts = <String>[];
  if (e.bodyweight == true) parts.add('自重');
  if (e.resistanceBand == true) parts.add('弹力带');
  if (parts.isEmpty) return '无';
  return parts.join('、');
}

String _listCountLabel(int? count, {required String singular}) {
  if (count == null) return '未填写';
  return '$count $singular';
}

String _formatDateTime(DateTime dt) {
  String two(int v) => v.toString().padLeft(2, '0');
  return '${dt.year}-${two(dt.month)}-${two(dt.day)} '
      '${two(dt.hour)}:${two(dt.minute)}';
}
