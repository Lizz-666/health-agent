// app/lib/screens/test/self_test_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../providers/issue_provider.dart';
import '../../providers/assessment_provider.dart';
import '../../providers/posture_state_provider.dart';

class SelfTestScreen extends ConsumerStatefulWidget {
  final String issueId;
  const SelfTestScreen({super.key, required this.issueId});

  @override
  ConsumerState<SelfTestScreen> createState() => _SelfTestScreenState();
}

class _SelfTestScreenState extends ConsumerState<SelfTestScreen> {
  final _pageController = PageController();
  int _currentTest = 0;

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  Future<void> _submitAnswer(String answer) async {
    final result = await ref
        .read(assessmentProvider.notifier)
        .submitSelfAssess(widget.issueId, _currentTest, answer);

    if (result != null) {
      ref.read(postureStateProvider.notifier).updateState(
        issueId: widget.issueId,
        result: result.result,
        method: 'self_test',
      );

      if (answer == 'uncertain') {
        _showPhotoDialog();
      } else {
        _goToResult(result.id, result.result, result.suggestion);
      }
    }
  }

  void _showPhotoDialog() {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('不确定？'),
        content: const Text('要试试 AI 拍照分析吗？更准确判断你的体态状况。'),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.pop(ctx);
              final result = ref.read(assessmentProvider).currentResult;
              if (result != null) {
                _goToResult(result.id, result.result, result.suggestion);
              }
            },
            child: const Text('以后再说'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(ctx);
              context.push('/issues/${widget.issueId}/photo');
            },
            child: const Text('拍照分析'),
          ),
        ],
      ),
    );
  }

  void _goToResult(String assessmentId, String result, String suggestion) {
    context.push('/issues/${widget.issueId}/result', extra: {
      'assessmentId': assessmentId,
      'result': result,
      'suggestion': suggestion,
    });
  }

  @override
  Widget build(BuildContext context) {
    final issueState = ref.watch(issueProvider);
    final detail = issueState.currentDetail;
    if (detail == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('自测')),
        body: const Center(child: Text('请先查看详情')),
      );
    }

    final tests = detail.selfTests;
    if (tests.isEmpty) {
      return Scaffold(
        appBar: AppBar(title: const Text('自测')),
        body: const Center(child: Text('暂无自测项目')),
      );
    }

    return Scaffold(
      appBar: AppBar(title: Text('${detail.nameCn} 自测')),
      body: Column(
        children: [
          // 进度指示
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: List.generate(tests.length + 1, (i) {
                return Expanded(
                  child: Container(
                    height: 4,
                    margin: const EdgeInsets.symmetric(horizontal: 2),
                    decoration: BoxDecoration(
                      color: i <= _currentTest ? const Color(0xFFE94560) : const Color(0xFF0F3460),
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                );
              }),
            ),
          ),
          Expanded(
            child: PageView.builder(
              controller: _pageController,
              itemCount: tests.length + 1,
              onPageChanged: (i) => setState(() => _currentTest = i),
              itemBuilder: (_, index) {
                if (index < tests.length) {
                  return _buildTestPage(tests[index], index + 1, tests.length);
                }
                return _buildAnswerPage();
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTestPage(dynamic test, int current, int total) {
    // test is SelfTest
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('自测方法 $current/$total', style: const TextStyle(color: Color(0xFF8892B0))),
          const SizedBox(height: 16),
          // 示意图区域
          Container(
            height: 220,
            width: double.infinity,
            decoration: BoxDecoration(
              color: const Color(0xFF16213E),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Center(
              child: test.imageKey.isNotEmpty
                  ? Image.asset('assets/images/tests/placeholder.png', fit: BoxFit.contain)
                  : const Icon(Icons.image, size: 64, color: Color(0xFF8892B0)),
            ),
          ),
          const SizedBox(height: 24),
          Text(test.name, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
          const SizedBox(height: 12),
          ...test.steps.asMap().entries.map((entry) => Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 24, height: 24,
                  margin: const EdgeInsets.only(right: 12),
                  decoration: const BoxDecoration(
                    color: Color(0xFFE94560), shape: BoxShape.circle),
                  child: Center(child: Text('${entry.key + 1}',
                      style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold))),
                ),
                Expanded(child: Text(entry.value, style: const TextStyle(fontSize: 15, height: 1.4))),
              ],
            ),
          )),
          const SizedBox(height: 24),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0x33FFB300),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                const Icon(Icons.info_outline, color: Color(0xFFFFB300)),
                const SizedBox(width: 12),
                Expanded(
                  child: Text('阳性征：${test.positiveSign}',
                      style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                ),
              ],
            ),
          ),
          if (test.toolsNeeded.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text('所需工具：${test.toolsNeeded}',
                style: const TextStyle(color: Color(0xFF8892B0), fontSize: 13)),
          ],
        ],
      ),
    );
  }

  Widget _buildAnswerPage() {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.quiz, size: 64, color: Color(0xFFE94560)),
          const SizedBox(height: 24),
          const Text('你的自测结果？', style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
          const SizedBox(height: 32),
          SizedBox(
            width: double.infinity, height: 52,
            child: ElevatedButton(
              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF00C853)),
              onPressed: () => _submitAnswer('negative'),
              child: const Text('我没有这个问题', style: TextStyle(fontSize: 16)),
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity, height: 52,
            child: ElevatedButton(
              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFFFFB300)),
              onPressed: () => _submitAnswer('positive'),
              child: const Text('我有这个问题', style: TextStyle(fontSize: 16)),
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity, height: 52,
            child: ElevatedButton(
              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF0F3460)),
              onPressed: () => _submitAnswer('uncertain'),
              child: const Text('不确定', style: TextStyle(fontSize: 16)),
            ),
          ),
        ],
      ),
    );
  }
}
