// app/lib/screens/home/home_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/constants.dart';
import '../../providers/issue_provider.dart';
import '../../providers/posture_state_provider.dart';
import '../../models/issue.dart';
import '../../models/user_posture_state.dart';
import '../../widgets/disclaimer_banner.dart';
import '../../widgets/glass_card.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final postureStates = ref.watch(postureStateProvider);
    final assessedCount = postureStates.length;
    final needAttentionCount = postureStates.values
        .where((s) => s.result == 'moderate' || s.result == 'severe')
        .length;

    final issueState = ref.watch(issueProvider);
    final allIssues = issueState.issuesByCategory['all'] ?? [];

    return Scaffold(
      appBar: AppBar(
        title: const Text(AppConstants.appName),
        titleTextStyle: TextStyle(
          color: Color(AppConstants.textColor),
          fontSize: 20,
          fontWeight: FontWeight.bold,
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.search),
            tooltip: '搜索',
            onPressed: () => context.push('/search'),
          ),
          IconButton(
            icon: const Icon(Icons.assignment),
            tooltip: '体态档案',
            onPressed: () => context.push('/profile/posture'),
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildStatsRow(context, assessedCount, needAttentionCount),
                  const SizedBox(height: 16),
                  _buildBodyContent(issueState, allIssues, postureStates, context),
                ],
              ),
            ),
          ),
          const DisclaimerBanner(),
        ],
      ),
    );
  }

  Widget _buildBodyContent(IssueState issueState, List<IssueSummary> allIssues,
      Map<String, UserPostureState> postureStates, BuildContext context) {
    if (issueState.isLoading && allIssues.isEmpty) {
      return const Padding(
        padding: EdgeInsets.only(top: 48),
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (issueState.error != null && allIssues.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.only(top: 48),
          child: Column(
            children: [
              const Icon(Icons.error_outline, size: 48,
                  color: Color(AppConstants.severeColor)),
              const SizedBox(height: 12),
              Text(issueState.error!,
                  style: const TextStyle(
                      color: Color(AppConstants.textMuted))),
            ],
          ),
        ),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: _kCategories.map((cat) => _buildCategoryCard(
            context, cat, postureStates, allIssues,
          )).toList(),
    );
  }

  Widget _buildStatsRow(
      BuildContext context, int assessed, int needAttention) {
    return Row(
      children: [
        Expanded(
          child: GestureDetector(
            onTap: () => context.push('/profile/posture'),
            child: GlassCard(
              padding: const EdgeInsets.all(20),
              child: Column(
                children: [
                  Text('$assessed',
                      style: TextStyle(
                          fontSize: 36,
                          fontWeight: FontWeight.bold,
                          color: Color(AppConstants.accentColor))),
                  const SizedBox(height: 4),
                  const Text('已评估',
                      style: TextStyle(
                          fontSize: 14, color: Color(AppConstants.textMuted))),
                  Text('/ 26 项',
                      style: TextStyle(
                          fontSize: 12,
                          color: Color(AppConstants.textMuted).withAlpha(178))),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: GestureDetector(
            onTap: () => context.push('/profile/posture'),
            child: GlassCard(
              padding: const EdgeInsets.all(20),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      if (needAttention > 0)
                        Text('⚠ ', style: TextStyle(fontSize: 20)),
                      Text('$needAttention',
                          style: TextStyle(
                              fontSize: 36,
                              fontWeight: FontWeight.bold,
                              color: needAttention > 0
                                  ? Color(AppConstants.moderateColor)
                                  : Color(AppConstants.normalColor))),
                    ],
                  ),
                  const SizedBox(height: 4),
                  const Text('需关注',
                      style: TextStyle(
                          fontSize: 14, color: Color(AppConstants.textMuted))),
                  Text('个问题',
                      style: TextStyle(
                          fontSize: 12,
                          color: Color(AppConstants.textMuted).withAlpha(178))),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildCategoryCard(
      BuildContext context,
      _CategoryInfo cat,
      Map<String, UserPostureState> postureStates,
      List<IssueSummary> allIssues) {
    final catIssues =
        allIssues.where((i) => i.category == cat.key).toList();
    final assessedInCat =
        catIssues.where((i) => postureStates.containsKey(i.id)).length;
    final totalInCat = catIssues.length;
    final allDone = assessedInCat == totalInCat && totalInCat > 0;

    final preview = catIssues.take(3).map((i) => i.nameCn).join('、');

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: GestureDetector(
        onTap: () => context.push(cat.route),
        child: GlassCard(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: [
              Icon(cat.icon,
                  color: Color(AppConstants.accentColor), size: 28),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(cat.name,
                        style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                            color: Color(AppConstants.textColor))),
                    const SizedBox(height: 3),
                    Text(preview.isNotEmpty ? preview : '暂无',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                            fontSize: 13,
                            color: Color(AppConstants.textMuted))),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: allDone
                      ? Color(AppConstants.normalColor).withAlpha(38)
                      : Color(AppConstants.accentColor).withAlpha(25),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  allDone ? '✓ $assessedInCat/$totalInCat' : '$assessedInCat/$totalInCat',
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: allDone
                        ? Color(AppConstants.normalColor)
                        : Color(AppConstants.accentColor),
                  ),
                ),
              ),
              const SizedBox(width: 4),
              Icon(Icons.chevron_right,
                  color: Color(AppConstants.textMuted), size: 20),
            ],
          ),
        ),
      ),
    );
  }
}

class _CategoryInfo {
  final String key;
  final IconData icon;
  final String name;
  final String route;
  const _CategoryInfo({
    required this.key,
    required this.icon,
    required this.name,
    required this.route,
  });
}

const _kCategories = [
  _CategoryInfo(key: 'head_neck', icon: Icons.face, name: '头颈部', route: '/issues/head_neck'),
  _CategoryInfo(key: 'shoulder_thorax', icon: Icons.accessibility_new, name: '肩胸区', route: '/issues/shoulder_thorax'),
  _CategoryInfo(key: 'pelvis_spine', icon: Icons.charging_station, name: '骨盆腰椎', route: '/issues/pelvis_spine'),
  _CategoryInfo(key: 'lower_limb', icon: Icons.directions_walk, name: '下肢区', route: '/issues/lower_limb'),
  _CategoryInfo(key: 'compound', icon: Icons.auto_awesome, name: '综合评估', route: '/issues/compound'),
];
