// app/lib/screens/issues/issue_list_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/constants.dart';
import '../../providers/issue_provider.dart';
import '../../providers/posture_state_provider.dart';
import '../../widgets/issue_card.dart';

class IssueListScreen extends ConsumerStatefulWidget {
  final String category;
  const IssueListScreen({super.key, required this.category});

  @override
  ConsumerState<IssueListScreen> createState() => _IssueListScreenState();
}

class _IssueListScreenState extends ConsumerState<IssueListScreen> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() {
      if (mounted) ref.read(issueProvider.notifier).fetchIssues(widget.category);
    });
  }

  @override
  Widget build(BuildContext context) {
    final issueState = ref.watch(issueProvider);
    final postureStates = ref.watch(postureStateProvider);
    final categoryName =
        AppConstants.categoryNames[widget.category] ?? widget.category;
    final issues = issueState.issuesByCategory[widget.category] ?? [];

    return Scaffold(
      appBar: AppBar(title: Text(categoryName)),
      body: issueState.isLoading && issues.isEmpty
          ? const Center(child: CircularProgressIndicator())
          : issueState.error != null && issues.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(issueState.error!, style: const TextStyle(color: Color(0xFFFF1744))),
                      const SizedBox(height: 16),
                      ElevatedButton(
                        onPressed: () => ref.read(issueProvider.notifier).fetchIssues(widget.category),
                        child: const Text('重试'),
                      ),
                    ],
                  ),
                )
              : issues.isEmpty
                  ? const Center(
                      child: Text('该分类暂无问题', style: TextStyle(color: Color(0xFF8892B0))))
                  : ListView.builder(
                      itemCount: issues.length,
                      itemBuilder: (_, i) {
                        final issue = issues[i];
                        final state = postureStates[issue.id];
                        return IssueCard(
                          key: Key('issue-list-item-${issue.id}'),
                          issue: issue,
                          result: state?.result,
                          onTap: () => context.push('/issue/${issue.id}/detail'),
                        );
                      },
                    ),
    );
  }
}
