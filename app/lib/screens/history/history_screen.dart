// app/lib/screens/history/history_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import '../../providers/assessment_provider.dart';
import '../../widgets/result_badge.dart';

class HistoryScreen extends ConsumerStatefulWidget {
  const HistoryScreen({super.key});

  @override
  ConsumerState<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends ConsumerState<HistoryScreen> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() =>
        ref.read(assessmentProvider.notifier).fetchHistory());
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(assessmentProvider);

    // 按日期分组
    final grouped = <String, List<dynamic>>{};
    for (final r in state.history) {
      final key = DateFormat('yyyy-MM-dd').format(r.createdAt);
      grouped.putIfAbsent(key, () => []).add(r);
    }

    return Scaffold(
      appBar: AppBar(title: const Text('评估历史')),
      body: state.isLoading
          ? const Center(child: CircularProgressIndicator())
          : state.history.isEmpty
              ? const Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.history, size: 64, color: Color(0xFF0F3460)),
                      SizedBox(height: 16),
                      Text('暂无评估记录',
                          style: TextStyle(fontSize: 18, color: Color(0xFF8892B0))),
                      Text('去首页开始你的第一次体态分析吧',
                          style: TextStyle(color: Color(0xFF8892B0))),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: () async {
                    await ref.read(assessmentProvider.notifier).fetchHistory();
                  },
                  child: ListView.builder(
                    itemCount: grouped.keys.length,
                    itemBuilder: (_, i) {
                      final date = grouped.keys.elementAt(i);
                      final records = grouped[date]!;
                      return Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Padding(
                            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                            child: Text(_formatDate(date),
                                style: const TextStyle(fontSize: 14, color: Color(0xFF8892B0), fontWeight: FontWeight.w600)),
                          ),
                          ...records.map((r) => Card(
                            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                            child: ListTile(
                              leading: ResultBadge(result: r.result, size: 13),
                              title: Text(r.issueName),
                              subtitle: Text(r.method == 'self_test' ? '自测' : 'AI分析',
                                  style: const TextStyle(fontSize: 12)),
                              trailing: Text(DateFormat('HH:mm').format(r.createdAt),
                                  style: const TextStyle(color: Color(0xFF8892B0), fontSize: 13)),
                              onTap: () => context.push('/issues/${r.issueId}/result', extra: {
                                'assessmentId': r.id,
                                'result': r.result,
                                'suggestion': '',
                              }),
                            ),
                          )),
                        ],
                      );
                    },
                  ),
                ),
    );
  }

  String _formatDate(String dateStr) {
    final now = DateTime.now();
    final date = DateTime.tryParse(dateStr);
    if (date == null) return dateStr;
    if (DateFormat('yyyy-MM-dd').format(now) == dateStr) return '今天';
    if (DateFormat('yyyy-MM-dd').format(now.subtract(const Duration(days: 1))) == dateStr) return '昨天';
    return DateFormat('M月d日').format(date);
  }
}
