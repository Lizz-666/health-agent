// app/lib/screens/profile/weight_trend_screen.dart
//
// Phase 2 weight trend My-page surface (spec Domain Model, Weight Record And
// Trend).
//
// Safety / state contract (Task 6):
//  - This screen consumes weightTrendProvider only.
//  - loading / networkError / parseError / data are visually distinct.
//  - When trend.sufficient == false, only raw records are shown and an honest
//    "数据不足" banner is displayed; no moving-trend points are fabricated and
//    no precision is implied.
//  - The view never emits advice, warnings, pass/fail judgment or plan/diet
//    adjustment text.
//  - Manual weight add uses the Phase 2 backend bounds for weight_kg
//    (20.0-300.0 kg); the record recorded_at
//    defaults to now. Invalid input is surfaced honestly, not coerced.
//  - Per-record delete requires a confirmation dialog before calling provider
//    delete; the trend is refreshed on success.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants.dart';
import '../../models/weight_record.dart';
import '../../providers/assessment_provider.dart' show LoadStatus;
import '../../providers/weight_trend_provider.dart';
import '../../widgets/disclaimer_banner.dart';

class WeightTrendScreen extends ConsumerStatefulWidget {
  const WeightTrendScreen({super.key});

  @override
  ConsumerState<WeightTrendScreen> createState() => _WeightTrendScreenState();
}

class _WeightTrendScreenState extends ConsumerState<WeightTrendScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      ref.read(weightTrendProvider.notifier).fetchTrend();
    });
  }

  Future<void> _openAddForm() async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => const _AddWeightSheet(),
    );
  }

  Future<void> _confirmDelete(WeightRecord record) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除体重记录'),
        content: Text(
          '确认删除 ${_formatDate(record.recordedAt)} 的体重记录？该操作不可撤销。',
        ),
        actions: [
          TextButton(
            key: const Key('weight-delete-cancel'),
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          ElevatedButton(
            key: const Key('weight-delete-confirm'),
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
      await ref.read(weightTrendProvider.notifier).deleteWeight(record.id);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(weightTrendProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('体重趋势')),
      floatingActionButton: FloatingActionButton(
        key: const Key('weight-add-fab'),
        onPressed: _openAddForm,
        child: const Icon(Icons.add),
      ),
      body: Column(
        children: [
          const DisclaimerBanner(),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: _WeightTrendBody(
                state: state,
                onRetry: () =>
                    ref.read(weightTrendProvider.notifier).fetchTrend(),
                onDelete: _confirmDelete,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _WeightTrendBody extends StatelessWidget {
  final WeightTrendState state;
  final VoidCallback onRetry;
  final void Function(WeightRecord) onDelete;

  const _WeightTrendBody({
    required this.state,
    required this.onRetry,
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
              '加载体重趋势中…',
              style: TextStyle(color: Color(AppConstants.textMuted)),
            ),
          ],
        ),
      );
    }
    if (status == LoadStatus.networkError) {
      return _box(
        child: _ErrorState(
          message: state.error ?? '体重趋势加载失败',
          onRetry: onRetry,
        ),
      );
    }
    if (status == LoadStatus.parseError) {
      return _box(child: _ErrorState(message: '数据解析异常', onRetry: onRetry));
    }
    final trend = state.trend!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (!trend.sufficient) _InsufficientBanner(window: trend.window),
        if (trend.sufficient) ...[
          _box(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('移动趋势', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 4),
                Text(
                  '基于最近 ${trend.window} 个记录的简单移动平均，仅为描述性展示，不代表评价或建议。',
                  style: const TextStyle(
                    fontSize: 11,
                    color: Color(AppConstants.textMuted),
                  ),
                ),
                const SizedBox(height: 8),
                for (final p in trend.trend) ...[
                  _TrendRow(point: p),
                  const SizedBox(height: 4),
                ],
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],
        Text('原始记录（${trend.records.length}）',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (trend.records.isEmpty)
          const Text(
            '暂无体重记录。',
            style: TextStyle(
              color: Color(AppConstants.textMuted),
              fontSize: 12,
            ),
          )
        else
          for (final r in trend.records) ...[
            _RecordCard(record: r, onDelete: () => onDelete(r)),
            const SizedBox(height: 8),
          ],
      ],
    );
  }
}

class _InsufficientBanner extends StatelessWidget {
  final int window;
  const _InsufficientBanner({required this.window});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(AppConstants.moderateColor).withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(AppConstants.moderateColor)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: const [
              Icon(
                Icons.info,
                size: 18,
                color: Color(AppConstants.moderateColor),
              ),
              SizedBox(width: 8),
              Text(
                '数据不足',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: Color(AppConstants.moderateColor),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            '当前记录数不足 $window 条，暂不计算移动趋势。仅展示已记录的数据，不进行任何推算或判断。',
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

class _TrendRow extends StatelessWidget {
  final WeightTrendPoint point;
  const _TrendRow({required this.point});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          _formatDate(point.recordedAt),
          style: const TextStyle(
            fontSize: 12,
            color: Color(AppConstants.textMuted),
          ),
        ),
        Text(
          '${point.weightKg.toStringAsFixed(1)} kg',
          style: const TextStyle(
            fontSize: 13,
            color: Color(AppConstants.textColor),
          ),
        ),
      ],
    );
  }
}

class _RecordCard extends StatelessWidget {
  final WeightRecord record;
  final VoidCallback onDelete;
  const _RecordCard({required this.record, required this.onDelete});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(AppConstants.cardColor),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(AppConstants.glassBorder)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _formatDate(record.recordedAt),
                  style: const TextStyle(
                    fontSize: 12,
                    color: Color(AppConstants.textMuted),
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  '${record.weightKg.toStringAsFixed(1)} kg',
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: Color(AppConstants.textColor),
                  ),
                ),
                if (record.note != null && record.note!.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(
                    record.note!,
                    style: const TextStyle(
                      fontSize: 12,
                      color: Color(AppConstants.textMuted),
                    ),
                  ),
                ],
              ],
            ),
          ),
          IconButton(
            key: Key('weight-delete-${record.id}'),
            icon: const Icon(
              Icons.delete_outline,
              color: Color(AppConstants.severeColor),
              size: 20,
            ),
            onPressed: onDelete,
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Add weight sheet
// ---------------------------------------------------------------------------

class _AddWeightSheet extends ConsumerStatefulWidget {
  const _AddWeightSheet();

  @override
  ConsumerState<_AddWeightSheet> createState() => _AddWeightSheetState();
}

class _AddWeightSheetState extends ConsumerState<_AddWeightSheet> {
  final _weightCtrl = TextEditingController();
  final _noteCtrl = TextEditingController();
  DateTime _recordedAt = DateTime.now();
  String? _weightError;
  bool _saving = false;

  @override
  void dispose() {
    _weightCtrl.dispose();
    _noteCtrl.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _recordedAt,
      firstDate: DateTime(2000),
      lastDate: DateTime.now(),
    );
    if (picked != null) {
      setState(() {
        _recordedAt = DateTime(
          picked.year,
          picked.month,
          picked.day,
          _recordedAt.hour,
          _recordedAt.minute,
        );
      });
    }
  }

  bool _validate() {
    final raw = _weightCtrl.text.trim();
    final value = double.tryParse(raw);
    if (value == null || value < 20 || value > 300) {
      setState(() => _weightError = '请输入有效的体重（20–300 kg）');
      return false;
    }
    setState(() => _weightError = null);
    return true;
  }

  Future<void> _save() async {
    if (!_validate()) return;
    setState(() => _saving = true);
    final value = double.parse(_weightCtrl.text.trim());
    final note = _noteCtrl.text.trim();
    final ok = await ref.read(weightTrendProvider.notifier).addWeight(
          WeightRecordInput(
            recordedAt: _recordedAt,
            weightKg: value,
            note: note.isEmpty ? null : note,
          ),
        );
    if (!mounted) return;
    setState(() => _saving = false);
    if (ok) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final actionError = ref.watch(
      weightTrendProvider.select((s) => s.actionError),
    );
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
              Text('添加体重记录', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 12),
              TextField(
                key: const Key('weight-input'),
                controller: _weightCtrl,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                decoration: InputDecoration(
                  labelText: '体重 (kg)',
                  errorText: _weightError,
                ),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '记录日期：${_formatDate(_recordedAt)}',
                      style: const TextStyle(
                        fontSize: 13,
                        color: Color(AppConstants.textMuted),
                      ),
                    ),
                  ),
                  TextButton(
                    key: const Key('weight-date-pick'),
                    onPressed: _saving ? null : _pickDate,
                    child: const Text('选择日期'),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextField(
                key: const Key('weight-note-input'),
                controller: _noteCtrl,
                decoration: const InputDecoration(labelText: '备注（可选）'),
                maxLength: 200,
              ),
              if (actionError != null) ...[
                const SizedBox(height: 8),
                Text(
                  actionError,
                  style: const TextStyle(
                    color: Color(AppConstants.severeColor),
                    fontSize: 12,
                  ),
                ),
              ],
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
                      key: const Key('weight-save-button'),
                      onPressed: _saving ? null : _save,
                      child: _saving
                          ? Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: const [
                                SizedBox(
                                  width: 14,
                                  height: 14,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
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
}

// ---------------------------------------------------------------------------
// Shared widgets
// ---------------------------------------------------------------------------

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
          key: const Key('weight-retry'),
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
