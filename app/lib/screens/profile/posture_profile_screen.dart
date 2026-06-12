// app/lib/screens/profile/posture_profile_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/constants.dart';
import '../../providers/posture_state_provider.dart';
import '../../providers/issue_provider.dart';
import '../../widgets/result_badge.dart';

class PostureProfileScreen extends ConsumerWidget {
  const PostureProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final postureStates = ref.watch(postureStateProvider);
    final issuesByCategory = ref.watch(issueProvider).issuesByCategory;
    final allIssues = issuesByCategory['all'] ?? [];

    final assessedCount = postureStates.values.length;
    final problemCount = postureStates.values
        .where((s) => s.result == 'moderate' || s.result == 'severe')
        .length;
    final normalCount = postureStates.values
        .where((s) => s.result == 'normal')
        .length;

    // 按分类组织
    final categoryOrder = ['head_neck', 'shoulder_thorax', 'pelvis_spine', 'lower_limb', 'compound'];

    return Scaffold(
      appBar: AppBar(title: const Text('我的体态档案')),
      body: Column(
        children: [
          // 统计卡片
          Container(
            margin: const EdgeInsets.all(16),
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(AppConstants.cardColor),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _statItem('$assessedCount', '已评估'),
                _statItem('$normalCount', '正常'),
                _statItem('$problemCount', '需关注'),
              ],
            ),
          ),
          Expanded(
            child: allIssues.isEmpty
                ? Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.folder_open, size: 64, color: Color(0xFF0F3460)),
                        const SizedBox(height: 16),
                        const Text('暂无数据', style: TextStyle(color: Color(0xFF8892B0))),
                        const SizedBox(height: 12),
                        ElevatedButton(
                          onPressed: () => context.go('/'),
                          child: const Text('去首页浏览问题'),
                        ),
                      ],
                    ),
                  )
                : ListView.builder(
                    itemCount: categoryOrder.length,
                    itemBuilder: (_, i) {
                      final cat = categoryOrder[i];
                      final catIssues = allIssues.where((iss) => iss.category == cat).toList();
                      if (catIssues.isEmpty) return const SizedBox.shrink();
                      return _buildCategorySection(context, cat, catIssues, postureStates, ref);
                    },
                  ),
          ),
        ],
      ),
    );
  }

  Widget _statItem(String value, String label) {
    return Column(
      children: [
        Text(value,
            style: const TextStyle(fontSize: 28, fontWeight: FontWeight.bold, color: Color(AppConstants.accentColor))),
        const SizedBox(height: 4),
        Text(label, style: const TextStyle(color: Color(0xFF8892B0), fontSize: 13)),
      ],
    );
  }

  Widget _buildCategorySection(BuildContext context, String cat, List<dynamic> issues, Map postureStates, WidgetRef ref) {
    final catName = AppConstants.categoryNames[cat] ?? cat;
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(catName, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Color(AppConstants.accentColor))),
            const SizedBox(height: 8),
            ...issues.map((issue) {
              final state = postureStates[issue.id];
              return ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: state != null
                    ? ResultBadge(result: state.result, size: 12)
                    : const Icon(Icons.radio_button_unchecked, size: 18, color: Color(0xFF8892B0)),
                title: Text(issue.nameCn ?? '', style: const TextStyle(fontSize: 14)),
                subtitle: state != null
                    ? Text('${state.method == 'self_test' ? '自测' : 'AI'} · ${_formatDate(state.updatedAt)}',
                        style: const TextStyle(fontSize: 11, color: Color(0xFF8892B0)))
                    : null,
                trailing: const Icon(Icons.chevron_right, size: 18, color: Color(0xFF8892B0)),
                onTap: () => context.push('/issue/${issue.id}/detail'),
              );
            }),
          ],
        ),
      ),
    );
  }

  String _formatDate(DateTime d) {
    final now = DateTime.now();
    final diff = now.difference(d);
    if (diff.inDays == 0) return '今天';
    if (diff.inDays == 1) return '昨天';
    return '${diff.inDays}天前';
  }
}
