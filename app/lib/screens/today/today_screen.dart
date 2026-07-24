// app/lib/screens/today/today_screen.dart
//
// Phase 2 Today page: daily 20-second check-in (spec Domain Model, Daily
// Check-In; consumes daily_checkin_provider).
//
// Safety / state contract (Task 7):
//  - The page is driven by dailyCheckinProvider only. loading / empty
//    (not checked in) / data (already checked in) / networkError / parseError
//    are visually distinct; neither network nor parse failure may render as a
//    checked-in / normal state.
//  - Not-checked-in shows the quick check-in form. Normal path is one tap
//    (sensible defaults). abnormal_pain=true REQUIRES the pain_followup block
//    before submit; the submit is blocked until pain_area / pain_started /
//    pain_intensity are provided.
//  - red_flag result shows bounded escalation guidance ("停止训练并尽快就医")
//    and is NEVER rendered as normal/success. caution / restricted are
//    distinguishable from normal.
//  - active_rest and safety_adjustment daily_status values are presented as
//    VALID, non-failure engagement states (never as missed/absent).
//  - Plan functionality does not exist: no executable plan, action, progress
//    or active-looking placeholder is rendered; plan absence is communicated
//    explicitly as unavailable.
//  - No AI, no recommendation / plan / diet generation.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants.dart';
import '../../models/daily_checkin.dart';
import '../../providers/assessment_provider.dart' show LoadStatus;
import '../../providers/daily_checkin_provider.dart';
import '../../widgets/disclaimer_banner.dart';

class TodayScreen extends ConsumerStatefulWidget {
  const TodayScreen({super.key});

  @override
  ConsumerState<TodayScreen> createState() => _TodayScreenState();
}

class _TodayScreenState extends ConsumerState<TodayScreen> {
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      ref.read(dailyCheckinProvider.notifier).fetchToday();
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(dailyCheckinProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('今日')),
      body: Column(
        children: [
          const DisclaimerBanner(),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: _TodayBody(
                state: state,
                saving: _saving,
                onRetry: () =>
                    ref.read(dailyCheckinProvider.notifier).fetchToday(),
                onSubmit: (input) async {
                  setState(() => _saving = true);
                  await ref
                      .read(dailyCheckinProvider.notifier)
                      .saveToday(input);
                  if (mounted) setState(() => _saving = false);
                },
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Body: state switch
// ---------------------------------------------------------------------------

class _TodayBody extends StatelessWidget {
  final DailyCheckInState state;
  final bool saving;
  final VoidCallback onRetry;
  final Future<void> Function(CheckInCreate input) onSubmit;

  const _TodayBody({
    required this.state,
    required this.saving,
    required this.onRetry,
    required this.onSubmit,
  });

  @override
  Widget build(BuildContext context) {
    if (saving) {
      return _box(
        child: Column(
          children: const [
            CircularProgressIndicator(),
            SizedBox(height: 12),
            Text(
              '提交中…',
              style: TextStyle(color: Color(AppConstants.textMuted)),
            ),
          ],
        ),
      );
    }
    final status = state.status;
    if (status == LoadStatus.idle || status == LoadStatus.loading) {
      return _box(
        child: Column(
          children: const [
            CircularProgressIndicator(),
            SizedBox(height: 12),
            Text(
              '加载今日签到中…',
              style: TextStyle(color: Color(AppConstants.textMuted)),
            ),
          ],
        ),
      );
    }
    if (status == LoadStatus.networkError) {
      return _box(
        child: _ErrorState(
          message: state.error ?? '今日签到加载失败',
          onRetry: onRetry,
        ),
      );
    }
    if (status == LoadStatus.parseError) {
      return _box(child: _ErrorState(message: '数据解析异常', onRetry: onRetry));
    }
    if (status == LoadStatus.empty) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _NotCheckedInHeader(),
          const SizedBox(height: 16),
          _CheckInForm(onSubmit: onSubmit),
          const SizedBox(height: 16),
          const _PlanUnavailableCard(),
        ],
      );
    }
    // data: already checked in.
    final checkin = state.checkin!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _CheckInSummary(checkin: checkin),
        const SizedBox(height: 16),
        const _PlanUnavailableCard(),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Not-checked-in header
// ---------------------------------------------------------------------------

class _NotCheckedInHeader extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return _box(
      child: Row(
        children: [
          const Icon(
            Icons.radio_button_unchecked,
            color: Color(AppConstants.accentColor),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: const [
                Text(
                  '今日尚未签到',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: Color(AppConstants.textColor),
                  ),
                ),
                SizedBox(height: 2),
                Text(
                  '快速记录今日状态（约 20 秒）。异常疼痛需补充追问信息。',
                  style: TextStyle(
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

// ---------------------------------------------------------------------------
// Check-in form
// ---------------------------------------------------------------------------

class _CheckInForm extends StatefulWidget {
  final Future<void> Function(CheckInCreate input) onSubmit;
  const _CheckInForm({required this.onSubmit});

  @override
  State<_CheckInForm> createState() => _CheckInFormState();
}

class _CheckInFormState extends State<_CheckInForm> {
  SleepQuality _sleep = SleepQuality.good;
  Energy _energy = Energy.normal;
  MuscleSoreness _soreness = MuscleSoreness.none;
  AvailableTime _availableTime = AvailableTime.thirtyMin;
  DailyStatus _dailyStatus = DailyStatus.checkedIn;
  bool _abnormalPain = false;

  final _painAreaCtrl = TextEditingController();
  PainStarted? _painStarted;
  PainIntensity? _painIntensity;
  bool _hasNeuro = false;
  bool _hasDizziness = false;
  bool _hasAcuteTrauma = false;
  final _painNoteCtrl = TextEditingController();
  String? _followupError;

  @override
  void dispose() {
    _painAreaCtrl.dispose();
    _painNoteCtrl.dispose();
    super.dispose();
  }

  bool _followupValid() {
    if (!_abnormalPain) return true;
    if (_painAreaCtrl.text.trim().isEmpty) return false;
    if (_painStarted == null) return false;
    if (_painIntensity == null) return false;
    return true;
  }

  Future<void> _submit() async {
    if (_abnormalPain && !_followupValid()) {
      setState(() => _followupError = '请补充疼痛追问信息（部位、起始、强度）。');
      return;
    }
    setState(() => _followupError = null);
    PainFollowup? followup;
    if (_abnormalPain) {
      followup = PainFollowup(
        painArea: _painAreaCtrl.text.trim(),
        painStarted: _painStarted!,
        painIntensity: _painIntensity!,
        hasNeurologicalSymptom: _hasNeuro,
        hasDizzinessOrChestSymptom: _hasDizziness,
        hasAcuteTrauma: _hasAcuteTrauma,
        painNote: _painNoteCtrl.text.trim().isEmpty
            ? null
            : _painNoteCtrl.text.trim(),
      );
    }
    final input = CheckInCreate(
      localDate: DateTime.now(),
      sleepQuality: _sleep,
      energy: _energy,
      muscleSoreness: _soreness,
      availableTime: _availableTime,
      dailyStatus: _dailyStatus,
      abnormalPain: _abnormalPain,
      painFollowup: followup,
    );
    await widget.onSubmit(input);
  }

  @override
  Widget build(BuildContext context) {
    return _box(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('今日状态', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          _DropdownField<SleepQuality>(
            label: '睡眠',
            value: _sleep,
            items: const [
              DropdownMenuItem(value: SleepQuality.poor, child: Text('差')),
              DropdownMenuItem(value: SleepQuality.ok, child: Text('一般')),
              DropdownMenuItem(value: SleepQuality.good, child: Text('好')),
            ],
            onChanged: (v) => setState(() => _sleep = v ?? _sleep),
          ),
          _DropdownField<Energy>(
            label: '精力',
            value: _energy,
            items: const [
              DropdownMenuItem(value: Energy.low, child: Text('低')),
              DropdownMenuItem(value: Energy.normal, child: Text('正常')),
              DropdownMenuItem(value: Energy.high, child: Text('充沛')),
            ],
            onChanged: (v) => setState(() => _energy = v ?? _energy),
          ),
          _DropdownField<MuscleSoreness>(
            label: '肌肉酸痛',
            value: _soreness,
            items: const [
              DropdownMenuItem(value: MuscleSoreness.none, child: Text('无')),
              DropdownMenuItem(value: MuscleSoreness.mild, child: Text('轻微')),
              DropdownMenuItem(
                value: MuscleSoreness.significant,
                child: Text('明显'),
              ),
            ],
            onChanged: (v) => setState(() => _soreness = v ?? _soreness),
          ),
          _DropdownField<AvailableTime>(
            label: '可用时间',
            value: _availableTime,
            items: const [
              DropdownMenuItem(value: AvailableTime.none, child: Text('无')),
              DropdownMenuItem(
                value: AvailableTime.fifteenMin,
                child: Text('15 分钟'),
              ),
              DropdownMenuItem(
                value: AvailableTime.thirtyMin,
                child: Text('30 分钟'),
              ),
              DropdownMenuItem(
                value: AvailableTime.fortyFiveMinPlus,
                child: Text('45 分钟以上'),
              ),
            ],
            onChanged: (v) => setState(() => _availableTime = v ?? _availableTime),
          ),
          _DropdownField<DailyStatus>(
            label: '今日状态',
            value: _dailyStatus,
            items: const [
              DropdownMenuItem(
                value: DailyStatus.checkedIn,
                child: Text('正常签到'),
              ),
              DropdownMenuItem(
                value: DailyStatus.activeRest,
                child: Text('主动休息'),
              ),
              DropdownMenuItem(
                value: DailyStatus.safetyAdjustment,
                child: Text('安全调整'),
              ),
            ],
            onChanged: (v) => setState(() => _dailyStatus = v ?? _dailyStatus),
          ),
          const SizedBox(height: 4),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              children: [
                const Expanded(child: Text('今日有异常疼痛')),
                Switch(
                  key: const Key('today-abnormal-pain'),
                  value: _abnormalPain,
                  onChanged: (v) => setState(() {
                    _abnormalPain = v;
                    _followupError = null;
                  }),
                ),
              ],
            ),
          ),
          if (_abnormalPain) ..._painFollowupFields(),
          if (_followupError != null) ...[
            const SizedBox(height: 4),
            Text(
              _followupError!,
              style: const TextStyle(
                color: Color(AppConstants.severeColor),
                fontSize: 12,
              ),
            ),
          ],
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              key: const Key('today-checkin-submit'),
              onPressed: _submit,
              child: const Text('完成签到'),
            ),
          ),
        ],
      ),
    );
  }

  List<Widget> _painFollowupFields() {
    return [
      const Divider(),
      const Text(
        '异常疼痛追问（必填）',
        style: TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w600,
          color: Color(AppConstants.textColor),
        ),
      ),
      const SizedBox(height: 8),
      TextField(
        key: const Key('today-pain-area'),
        controller: _painAreaCtrl,
        decoration: const InputDecoration(
          labelText: '疼痛部位',
          isDense: true,
        ),
      ),
      const SizedBox(height: 8),
      _DropdownField<PainStarted?>(
        key: const Key('today-pain-started'),
        label: '起始时间',
        value: _painStarted,
        items: const [
          DropdownMenuItem(value: null, child: Text('请选择')),
          DropdownMenuItem(value: PainStarted.today, child: Text('今天')),
          DropdownMenuItem(
            value: PainStarted.recentDays,
            child: Text('最近几天'),
          ),
          DropdownMenuItem(value: PainStarted.ongoing, child: Text('持续')),
          DropdownMenuItem(
            value: PainStarted.afterAcuteEvent,
            child: Text('急性事件后'),
          ),
        ],
        onChanged: (v) => setState(() => _painStarted = v),
      ),
      _DropdownField<PainIntensity?>(
        key: const Key('today-pain-intensity'),
        label: '疼痛强度',
        value: _painIntensity,
        items: const [
          DropdownMenuItem(value: null, child: Text('请选择')),
          DropdownMenuItem(value: PainIntensity.mild, child: Text('轻度')),
          DropdownMenuItem(value: PainIntensity.moderate, child: Text('中度')),
          DropdownMenuItem(value: PainIntensity.severe, child: Text('重度')),
        ],
        onChanged: (v) => setState(() => _painIntensity = v),
      ),
      _BoolRow(
        key: const Key('today-has-neuro'),
        label: '神经症状（麻木/无力等）',
        value: _hasNeuro,
        onChanged: (v) => setState(() => _hasNeuro = v),
      ),
      _BoolRow(
        key: const Key('today-has-dizziness'),
        label: '眩晕/胸部不适',
        value: _hasDizziness,
        onChanged: (v) => setState(() => _hasDizziness = v),
      ),
      _BoolRow(
        key: const Key('today-has-trauma'),
        label: '急性创伤',
        value: _hasAcuteTrauma,
        onChanged: (v) => setState(() => _hasAcuteTrauma = v),
      ),
      TextField(
        key: const Key('today-pain-note'),
        controller: _painNoteCtrl,
        maxLines: 2,
        decoration: const InputDecoration(
          labelText: '备注（可选）',
          isDense: true,
        ),
      ),
    ];
  }
}

// ---------------------------------------------------------------------------
// Already-checked-in summary
// ---------------------------------------------------------------------------

class _CheckInSummary extends StatelessWidget {
  final DailyCheckIn checkin;
  const _CheckInSummary({required this.checkin});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _RiskSummaryCard(risk: checkin.riskSummary),
        const SizedBox(height: 12),
        _DailyStatusCard(status: checkin.dailyStatus),
        const SizedBox(height: 12),
        _box(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('今日记录', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              _Field(label: '睡眠', value: _sleepLabel(checkin.sleepQuality)),
              _Field(label: '精力', value: _energyLabel(checkin.energy)),
              _Field(
                label: '肌肉酸痛',
                value: _sorenessLabel(checkin.muscleSoreness),
              ),
              _Field(
                label: '可用时间',
                value: _availableLabel(checkin.availableTime),
              ),
              _Field(
                label: '异常疼痛',
                value: checkin.abnormalPain ? '是' : '否',
              ),
              const SizedBox(height: 8),
              Text(
                '日期：${_formatDate(checkin.localDate)}',
                style: const TextStyle(
                  fontSize: 11,
                  color: Color(AppConstants.textMuted),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// Risk-summary card: normal/caution/restricted distinct; red_flag bounded
/// escalation, never rendered as normal/success.
class _RiskSummaryCard extends StatelessWidget {
  final CheckInRiskSummary risk;
  const _RiskSummaryCard({required this.risk});

  @override
  Widget build(BuildContext context) {
    final (color, icon, label, guidance) = switch (risk) {
      CheckInRiskSummary.normal => (
        const Color(AppConstants.normalColor),
        Icons.check_circle,
        '状态正常',
        null,
      ),
      CheckInRiskSummary.caution => (
        const Color(AppConstants.moderateColor),
        Icons.info,
        '需注意',
        '建议降低强度或观察；如不适加重请暂停并咨询专业人士。',
      ),
      CheckInRiskSummary.restricted => (
        const Color(AppConstants.moderateColor),
        Icons.warning_amber,
        '受限',
        '当前受限，仅建议低强度活动；如有疑虑请咨询专业人士。',
      ),
      CheckInRiskSummary.redFlag => (
        const Color(AppConstants.severeColor),
        Icons.dangerous,
        '红旗信号',
        '检测到红旗信号，请停止训练并尽快就医或联系专业人士。',
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
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  color: color,
                ),
              ),
            ],
          ),
          if (guidance != null) ...[
            const SizedBox(height: 6),
            Text(
              guidance,
              style: const TextStyle(
                fontSize: 12,
                color: Color(AppConstants.textColor),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Daily-status card: active_rest / safety_adjustment are VALID non-failure.
class _DailyStatusCard extends StatelessWidget {
  final DailyStatus status;
  const _DailyStatusCard({required this.status});

  @override
  Widget build(BuildContext context) {
    final (icon, color, label, hint) = switch (status) {
      DailyStatus.checkedIn => (
        Icons.check_circle,
        const Color(AppConstants.normalColor),
        '今日已签到',
        null,
      ),
      DailyStatus.activeRest => (
        Icons.self_improvement,
        const Color(AppConstants.accentLight),
        '今日：主动休息',
        '主动休息是有效的恢复状态，不计为缺勤或失败。',
      ),
      DailyStatus.safetyAdjustment => (
        Icons.shield,
        const Color(AppConstants.moderateColor),
        '今日：安全调整',
        '安全调整是根据状态做出的有效选择，不计为缺勤或失败。',
      ),
    };
    return _box(
      child: Row(
        children: [
          Icon(icon, color: color, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: color,
                  ),
                ),
                if (hint != null)
                  Text(
                    hint,
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
    );
  }
}

// ---------------------------------------------------------------------------
// Plan absence — explicitly unavailable, never an active-looking placeholder
// ---------------------------------------------------------------------------

class _PlanUnavailableCard extends StatelessWidget {
  const _PlanUnavailableCard();

  @override
  Widget build(BuildContext context) {
    return _box(
      child: Row(
        children: const [
          Icon(
            Icons.lock_outline,
            color: Color(AppConstants.textMuted),
            size: 20,
          ),
          SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '训练计划（尚未开放）',
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: Color(AppConstants.textColor),
                  ),
                ),
                SizedBox(height: 2),
                Text(
                  '个性化训练计划功能仍在开发中，暂不可用。当前仅记录今日状态。',
                  style: TextStyle(
                    fontSize: 11,
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

// ---------------------------------------------------------------------------
// Small shared widgets
// ---------------------------------------------------------------------------

class _BoolRow extends StatelessWidget {
  final String label;
  final bool value;
  final ValueChanged<bool> onChanged;
  const _BoolRow({
    super.key,
    required this.label,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () => onChanged(!value),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(
          children: [
            Checkbox(value: value, onChanged: (v) => onChanged(v ?? false)),
            Expanded(child: Text(label)),
          ],
        ),
      ),
    );
  }
}

class _Field extends StatelessWidget {
  final String label;
  final String value;
  const _Field({required this.label, required this.value});
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: const TextStyle(color: Color(AppConstants.textMuted)),
          ),
          Text(
            value,
            style: const TextStyle(
              fontSize: 15,
              color: Color(AppConstants.textColor),
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
          key: const Key('today-retry'),
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
    super.key,
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
            width: 90,
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

String _formatDate(DateTime dt) {
  String two(int v) => v.toString().padLeft(2, '0');
  return '${dt.year}-${two(dt.month)}-${two(dt.day)}';
}

String _sleepLabel(SleepQuality v) => switch (v) {
      SleepQuality.poor => '差',
      SleepQuality.ok => '一般',
      SleepQuality.good => '好',
    };

String _energyLabel(Energy v) => switch (v) {
      Energy.low => '低',
      Energy.normal => '正常',
      Energy.high => '充沛',
    };

String _sorenessLabel(MuscleSoreness v) => switch (v) {
      MuscleSoreness.none => '无',
      MuscleSoreness.mild => '轻微',
      MuscleSoreness.significant => '明显',
    };

String _availableLabel(AvailableTime v) => switch (v) {
      AvailableTime.none => '无',
      AvailableTime.fifteenMin => '15 分钟',
      AvailableTime.thirtyMin => '30 分钟',
      AvailableTime.fortyFiveMinPlus => '45 分钟以上',
    };
