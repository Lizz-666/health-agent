// app/lib/screens/issues/issue_detail_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../providers/issue_provider.dart';

class IssueDetailScreen extends ConsumerStatefulWidget {
  final String issueId;
  const IssueDetailScreen({super.key, required this.issueId});

  @override
  ConsumerState<IssueDetailScreen> createState() => _IssueDetailScreenState();
}

class _IssueDetailScreenState extends ConsumerState<IssueDetailScreen> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() {
      if (mounted) ref.read(issueProvider.notifier).fetchDetail(widget.issueId);
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(issueProvider);
    final detail = state.currentDetail;

    if (state.error != null && detail == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('加载失败')),
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(state.error!, style: const TextStyle(color: Color(0xFFFF1744))),
              const SizedBox(height: 16),
              ElevatedButton(
                onPressed: () => ref.read(issueProvider.notifier).fetchDetail(widget.issueId),
                child: const Text('重试'),
              ),
            ],
          ),
        ),
      );
    }

    if (state.isLoading || detail == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('加载中...')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(title: Text(detail.nameCn)),
      body: CustomScrollView(
        slivers: [
          SliverToBoxAdapter(
            child: Card(
              margin: const EdgeInsets.all(16),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(detail.nameCn,
                              style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
                        ),
                        if (detail.nameEn.isNotEmpty)
                          Text(detail.nameEn,
                              style: const TextStyle(color: Color(0xFF8892B0), fontSize: 13)),
                      ],
                    ),
                    if (detail.aliases.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 6,
                        children: detail.aliases
                            .map((a) => Chip(label: Text(a), padding: EdgeInsets.zero,
                                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap))
                            .toList(),
                      ),
                    ],
                    const SizedBox(height: 12),
                    Text(detail.definition,
                        style: const TextStyle(fontSize: 15, height: 1.5)),
                  ],
                ),
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: Card(
              margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('成因', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 8),
                    ...detail.causes.map((c) => Padding(
                      padding: const EdgeInsets.only(bottom: 6),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            margin: const EdgeInsets.only(top: 4, right: 8),
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                            decoration: BoxDecoration(
                              color: const Color(0xFF0F3460),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text((c['type'] as String?) ?? '',
                                style: const TextStyle(fontSize: 11, color: Colors.white)),
                          ),
                          Expanded(child: Text((c['desc'] as String?) ?? '', style: const TextStyle(height: 1.4))),
                        ],
                      ),
                    )),
                  ],
                ),
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: Card(
              margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('纠正方法', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 8),
                    ...detail.corrections.map((c) => Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon((c['type'] as String?) == '拉伸' ? Icons.fitness_center : (c['type'] as String?) == '强化' ? Icons.trending_up : Icons.lightbulb_outline,
                              size: 18, color: const Color(0xFFE94560)),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                if (c['method'] != null)
                                  Text(c['method'] as String, style: const TextStyle(fontWeight: FontWeight.w600)),
                                if (c['freq'] != null)
                                  Text(c['freq'] as String, style: const TextStyle(color: Color(0xFF8892B0), fontSize: 12)),
                                if (c['desc'] != null)
                                  Text(c['desc'] as String, style: const TextStyle(height: 1.4)),
                              ],
                            ),
                          ),
                        ],
                      ),
                    )),
                  ],
                ),
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: Card(
              margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('不纠正的后果', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 8),
                    ...detail.consequences.map((c) => Padding(
                      padding: const EdgeInsets.only(bottom: 6),
                      child: Row(
                        children: [
                          Text('${c['timeframe'] ?? ''}：',
                              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                          Expanded(child: Text((c['desc'] as String?) ?? '', style: const TextStyle(fontSize: 14))),
                        ],
                      ),
                    )),
                  ],
                ),
              ),
            ),
          ),
          if (detail.redFlags.isNotEmpty)
            SliverToBoxAdapter(
              child: Card(
                margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                color: const Color(0x33FF1744),
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Row(
                        children: [
                          Icon(Icons.warning, color: Color(0xFFFF1744)),
                          SizedBox(width: 8),
                          Text('红旗征', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Color(0xFFFF1744))),
                        ],
                      ),
                      const SizedBox(height: 8),
                      ...detail.redFlags.map((f) => Padding(
                        padding: const EdgeInsets.only(bottom: 4),
                        child: Text('• $f', style: const TextStyle(fontSize: 14)),
                      )),
                    ],
                  ),
                ),
              ),
            ),
          const SliverToBoxAdapter(child: SizedBox(height: 80)),
        ],
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: SizedBox(
            width: double.infinity,
            height: 52,
            child: ElevatedButton(
              onPressed: () => context.push('/issue/${detail.id}/test'),
              child: const Text('开始自测', style: TextStyle(fontSize: 18)),
            ),
          ),
        ),
      ),
    );
  }
}
