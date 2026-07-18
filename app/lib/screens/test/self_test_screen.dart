// app/lib/screens/test/self_test_screen.dart
//
// Task 8C self-test screen. Renders the Task 3 extended fields
// (preparation / correctPosture / commonErrors / stopConditions / safetyNotes)
// with stop_conditions rendered ABOVE the numbered action steps so the user
// can decide to abort before forcing a position (spec §6.6 / §12.1).
//
// Safety contract (Task 8C, spec §15):
//  - The legacy "AI 拍照更准确" wording has been removed. AI photo analysis is
//    described as another reference method, not as more accurate. The
//    wording is exposed via [photoDialogDescription] so it can be tested
//    without flipping the PHOTO_ANALYSIS_ENABLED flag.
//  - Migrated to the current light theme; flat r=8 containers, no nested
//    cards, no decorative hero.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/constants.dart';
import '../../models/assessment.dart';
import '../../models/issue.dart';
import '../../providers/assessment_provider.dart';
import '../../providers/issue_provider.dart';
import '../../providers/posture_state_provider.dart';

class SelfTestScreen extends ConsumerStatefulWidget {
  final String issueId;
  const SelfTestScreen({super.key, required this.issueId});

  /// Neutral wording for the AI photo prompt. Exposed for testability so the
  /// contract ("AI 拍照更准确" removed; only "another reference method") can
  /// be verified without enabling PHOTO_ANALYSIS_ENABLED.
  static const String photoDialogDescription = 'AI 拍照分析是另一种参考方式，需要时可尝试。';

  @override
  ConsumerState<SelfTestScreen> createState() => _SelfTestScreenState();
}

class _SelfTestScreenState extends ConsumerState<SelfTestScreen> {
  final _pageController = PageController();
  int _currentTest = 0;
  int _activeTestForAnswer = 0;

  @override
  void initState() {
    super.initState();
    Future.microtask(() {
      if (mounted) ref.read(issueProvider.notifier).fetchDetail(widget.issueId);
    });
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  Future<void> _submitAnswer(String answer) async {
    if (ref.read(assessmentProvider).isLoading) return;
    final result = await ref
        .read(assessmentProvider.notifier)
        .submitSelfAssess(widget.issueId, _activeTestForAnswer, answer);

    if (!mounted) return;

    if (result != null) {
      ref
          .read(postureStateProvider.notifier)
          .updateState(
            issueId: widget.issueId,
            result: result.result,
            method: 'self_test',
          );

      if (answer == 'uncertain' && AppConstants.photoAnalysisEnabled) {
        _showPhotoDialog(result);
      } else {
        _goToResult(result.id, result.result, result.suggestion);
      }
    }
  }

  void _showPhotoDialog(SelfAssessResult selfResult) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('不确定？'),
        content: const Text(SelfTestScreen.photoDialogDescription),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.pop(ctx);
              _goToResult(
                selfResult.id,
                selfResult.result,
                selfResult.suggestion,
              );
            },
            child: const Text('以后再说'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(ctx);
              if (mounted) context.push('/issue/${widget.issueId}/photo');
            },
            child: const Text('拍照分析'),
          ),
        ],
      ),
    );
  }

  void _goToResult(String assessmentId, String result, String suggestion) {
    if (!mounted) return;
    context.push(
      '/issue/${widget.issueId}/result',
      extra: {
        'assessmentId': assessmentId,
        'result': result,
        'suggestion': suggestion,
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final issueState = ref.watch(issueProvider);
    final assessmentState = ref.watch(assessmentProvider);
    final currentDetail = issueState.currentDetail;
    final detail = currentDetail?.id == widget.issueId ? currentDetail : null;
    if (detail == null) {
      final detailError =
          issueState.error ??
          (currentDetail != null ? '问题详情与当前自测不一致，请重新加载。' : null);
      return Scaffold(
        appBar: AppBar(title: const Text('自测')),
        body: detailError == null
            ? const Center(child: CircularProgressIndicator())
            : Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(
                        Icons.error_outline,
                        color: Color(AppConstants.severeColor),
                        size: 40,
                      ),
                      const SizedBox(height: 12),
                      Text(
                        detailError,
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                          color: Color(AppConstants.textColor),
                        ),
                      ),
                      const SizedBox(height: 12),
                      OutlinedButton.icon(
                        onPressed: () => ref
                            .read(issueProvider.notifier)
                            .fetchDetail(widget.issueId),
                        icon: const Icon(Icons.refresh),
                        label: const Text('重试'),
                      ),
                    ],
                  ),
                ),
              ),
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
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: List.generate(tests.length + 1, (i) {
                return Expanded(
                  child: Container(
                    height: 4,
                    margin: const EdgeInsets.symmetric(horizontal: 2),
                    decoration: BoxDecoration(
                      color: i <= _currentTest
                          ? const Color(AppConstants.accentColor)
                          : const Color(AppConstants.dividerColor),
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
              onPageChanged: (i) {
                setState(() {
                  _currentTest = i;
                  if (i < tests.length) {
                    _activeTestForAnswer = i;
                  }
                });
              },
              itemBuilder: (_, index) {
                if (index < tests.length) {
                  return _buildTestPage(tests[index], index + 1, tests.length);
                }
                return _buildAnswerPage(assessmentState.isLoading);
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTestPage(SelfTest test, int current, int total) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '自测方法 $current/$total',
            style: const TextStyle(
              color: Color(AppConstants.textMuted),
              fontSize: 13,
            ),
          ),
          const SizedBox(height: 12),
          Container(
            height: 180,
            width: double.infinity,
            decoration: BoxDecoration(
              color: const Color(AppConstants.cardColor),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(AppConstants.glassBorder)),
            ),
            child: Center(
              child: test.imageKey.isNotEmpty
                  ? const Icon(
                      Icons.image,
                      size: 56,
                      color: Color(AppConstants.textMuted),
                    )
                  : const Icon(
                      Icons.image,
                      size: 56,
                      color: Color(AppConstants.textMuted),
                    ),
            ),
          ),
          const SizedBox(height: 16),
          Text(
            test.name,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 12),

          // --- stop_conditions rendered BEFORE action steps (spec §12.1) ---
          if (test.stopConditions.isNotEmpty)
            _WarningBlock(
              icon: Icons.pan_tool_outlined,
              title: '停止条件：出现以下情况请立即停止',
              items: test.stopConditions,
            ),

          // --- correct posture ---
          if (test.correctPosture.isNotEmpty) ...[
            const SizedBox(height: 8),
            _InfoBlock(
              icon: Icons.accessibility_new,
              title: '正确姿势',
              body: test.correctPosture,
            ),
          ],

          // --- numbered action steps (legacy) ---
          const SizedBox(height: 16),
          ...test.steps.asMap().entries.map(
            (entry) => Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 24,
                    height: 24,
                    margin: const EdgeInsets.only(right: 12),
                    decoration: const BoxDecoration(
                      color: Color(AppConstants.accentColor),
                      shape: BoxShape.circle,
                    ),
                    child: Center(
                      child: Text(
                        '${entry.key + 1}',
                        style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                    ),
                  ),
                  Expanded(
                    child: Text(
                      entry.value,
                      style: const TextStyle(fontSize: 15, height: 1.4),
                    ),
                  ),
                ],
              ),
            ),
          ),

          // --- positive sign (legacy) ---
          const SizedBox(height: 16),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(
                AppConstants.moderateColor,
              ).withValues(alpha: 0.14),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: const Color(AppConstants.moderateColor),
              ),
            ),
            child: Row(
              children: [
                const Icon(
                  Icons.info_outline,
                  color: Color(AppConstants.moderateColor),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '阳性征：${test.positiveSign}',
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          ),

          // --- common errors ---
          if (test.commonErrors.isNotEmpty) ...[
            const SizedBox(height: 12),
            _InfoBlock(
              icon: Icons.report_problem_outlined,
              title: '常见错误',
              items: test.commonErrors,
            ),
          ],

          // --- preparation ---
          if (test.preparation.isNotEmpty) ...[
            const SizedBox(height: 8),
            _InfoBlock(
              icon: Icons.checklist,
              title: '准备工作',
              body: test.preparation,
            ),
          ],

          // --- safety notes ---
          if (test.safetyNotes.isNotEmpty) ...[
            const SizedBox(height: 8),
            _WarningBlock(
              icon: Icons.shield_outlined,
              title: '安全提示',
              items: test.safetyNotes,
            ),
          ],

          // --- tools needed (legacy) ---
          if (test.toolsNeeded.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              '所需工具：${test.toolsNeeded}',
              style: const TextStyle(
                color: Color(AppConstants.textMuted),
                fontSize: 13,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildAnswerPage(bool isSubmitting) {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(
            Icons.quiz,
            size: 64,
            color: Color(AppConstants.accentColor),
          ),
          const SizedBox(height: 24),
          const Text(
            '你的自测结果？',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 32),
          SizedBox(
            width: double.infinity,
            height: 52,
            child: ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(AppConstants.normalColor),
              ),
              onPressed: isSubmitting ? null : () => _submitAnswer('negative'),
              child: const Text('我没有这个问题', style: TextStyle(fontSize: 16)),
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            height: 52,
            child: ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(AppConstants.moderateColor),
              ),
              onPressed: isSubmitting ? null : () => _submitAnswer('positive'),
              child: const Text('我有这个问题', style: TextStyle(fontSize: 16)),
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            height: 52,
            child: ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(AppConstants.surfaceDark),
              ),
              onPressed: isSubmitting ? null : () => _submitAnswer('uncertain'),
              child: const Text('不确定', style: TextStyle(fontSize: 16)),
            ),
          ),
          if (isSubmitting) ...[
            const SizedBox(height: 16),
            const CircularProgressIndicator(),
          ],
        ],
      ),
    );
  }
}

class _WarningBlock extends StatelessWidget {
  final IconData icon;
  final String title;
  final List<String> items;
  const _WarningBlock({
    required this.icon,
    required this.title,
    required this.items,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(AppConstants.severeColor).withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(AppConstants.severeColor)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                icon,
                color: const Color(AppConstants.severeColor),
                size: 18,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: Color(AppConstants.severeColor),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          for (final s in items)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                '· $s',
                style: const TextStyle(
                  fontSize: 13,
                  color: Color(AppConstants.textColor),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _InfoBlock extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? body;
  final List<String>? items;
  const _InfoBlock({
    required this.icon,
    required this.title,
    this.body,
    this.items,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(AppConstants.accentColor).withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(AppConstants.accentColor)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                icon,
                color: const Color(AppConstants.accentColor),
                size: 18,
              ),
              const SizedBox(width: 8),
              Text(
                title,
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: Color(AppConstants.accentColor),
                ),
              ),
            ],
          ),
          if (body != null && body!.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              body!,
              style: const TextStyle(
                fontSize: 13,
                color: Color(AppConstants.textColor),
              ),
            ),
          ],
          if (items != null) ...[
            const SizedBox(height: 6),
            for (final s in items!)
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Text(
                  '· $s',
                  style: const TextStyle(
                    fontSize: 13,
                    color: Color(AppConstants.textColor),
                  ),
                ),
              ),
          ],
        ],
      ),
    );
  }
}
