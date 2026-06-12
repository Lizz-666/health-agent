// app/lib/screens/result/result_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../providers/issue_provider.dart';
import '../../widgets/result_badge.dart';
import '../../widgets/disclaimer_banner.dart';

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
      ref.read(issueProvider.notifier).fetchDetail(widget.issueId);
      if (widget.result == 'severe' && !_dialogShown) {
        _dialogShown = true;
        _showSevereDialog(context);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final detail = ref.watch(issueProvider).currentDetail;

    return Scaffold(
      appBar: AppBar(title: const Text('评估结果')),
      body: Column(
        children: [
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // 顶部结果卡片
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Column(
                        children: [
                          ResultBadge(result: widget.result, size: 22),
                          const SizedBox(height: 16),
                          Text(
                            widget.suggestion,
                            textAlign: TextAlign.center,
                            style: const TextStyle(fontSize: 16, height: 1.5),
                          ),
                        ],
                      ),
                    ),
                  ),
                  // 纠正建议（仅 moderate 时显示）
                  if (widget.result == 'moderate' && detail != null) ...[
                    const SizedBox(height: 16),
                    const Text(
                      '纠正建议',
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    ...detail.corrections.map(
                      (c) => Card(
                        margin: const EdgeInsets.only(bottom: 8),
                        child: Padding(
                          padding: const EdgeInsets.all(12),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Icon(
                                c['type'] == '拉伸'
                                    ? Icons.fitness_center
                                    : c['type'] == '强化'
                                    ? Icons.trending_up
                                    : Icons.lightbulb,
                                color: const Color(0xFFE94560),
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
                                          color: Color(0xFF8892B0),
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
                    ),
                  ],
                  // 相关推荐
                  if (detail != null && detail.relatedIssues.isNotEmpty) ...[
                    const SizedBox(height: 16),
                    const Text(
                      '你可能还需要关注',
                      style: TextStyle(
                        fontSize: 20,
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
                              decoration: BoxDecoration(
                                color: const Color(0xFF16213E),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    rel.id,
                                    style: const TextStyle(
                                      fontSize: 12,
                                      color: Color(0xFF8892B0),
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
                                      color: Color(0xFF8892B0),
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
        icon: const Icon(Icons.warning, color: Color(0xFFFF1744), size: 48),
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
