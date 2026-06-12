import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lpinyin/lpinyin.dart';
import '../../core/constants.dart';
import '../../models/issue.dart';
import '../../models/user_posture_state.dart';
import '../../providers/issue_provider.dart';
import '../../providers/posture_state_provider.dart';
import '../../widgets/issue_card.dart';

const _hotIssues = [
  ('PS-13', '骨盆前倾'),
  ('ST-04', '圆肩'),
  ('HN-01', '头前倾'),
  ('ST-08', '驼背'),
  ('ST-10', '肋骨外翻'),
  ('LL-18', 'X型腿'),
  ('PS-11', '脊柱侧弯'),
  ('LL-21', '扁平足'),
  ('LL-20', '膝超伸'),
];

const _categoryTabs = [
  ('all', '全部'),
  ('head_neck', '头颈'),
  ('shoulder_thorax', '肩胸'),
  ('pelvis_spine', '骨盆'),
  ('lower_limb', '下肢'),
  ('compound', '综合'),
];

class SearchScreen extends ConsumerStatefulWidget {
  const SearchScreen({super.key});

  @override
  ConsumerState<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends ConsumerState<SearchScreen> {
  final _controller = TextEditingController();
  String _query = '';
  String _selectedCategory = 'all';

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  final _pinyinCache = <String, String>{};
  final _pinyinShortCache = <String, String>{};

  String _toPinyin(String text, {bool short = false}) {
    if (text.isEmpty) return '';
    final cache = short ? _pinyinShortCache : _pinyinCache;
    return cache.putIfAbsent(text, () {
      final raw = short
          ? PinyinHelper.getShortPinyin(text)
          : PinyinHelper.getPinyin(text, separator: '');
      return raw.replaceAll(' ', '').toLowerCase();
    });
  }

  List<IssueSummary> _filter(List<IssueSummary> all, String query) {
    if (query.trim().isEmpty) {
      if (_selectedCategory == 'all') return all;
      return all.where((i) => i.category == _selectedCategory).toList();
    }
    final q = query.trim().toLowerCase();

    return all.where((issue) {
      if (issue.nameCn.toLowerCase().contains(q)) return true;
      if (issue.aliases.any((a) => a.toLowerCase().contains(q))) return true;
      if (issue.definition.toLowerCase().contains(q)) return true;

      final searchText = '${issue.nameCn} ${issue.aliases.join(' ')}';
      if (_toPinyin(searchText).contains(q)) return true;
      if (_toPinyin(searchText, short: true).contains(q)) return true;

      final nameShort = _toPinyin(issue.nameCn, short: true);
      if (nameShort.length >= 2 && q.contains(nameShort)) return true;

      return false;
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final issueState = ref.watch(issueProvider);
    final postureStates = ref.watch(postureStateProvider);
    final allIssues = issueState.issuesByCategory['all'] ?? [];

    // 自动加载（如果数据未拉取）
    if (!issueState.isLoading &&
        issueState.issuesByCategory['all'] == null &&
        issueState.error == null) {
      Future.microtask(
          () => ref.read(issueProvider.notifier).fetchIssues(null));
    }
    final results = _filter(allIssues, _query);
    final showHotContent = _query.trim().isEmpty;

    return Scaffold(
      appBar: AppBar(
        titleSpacing: 0,
        title: TextField(
          controller: _controller,
          autofocus: true,
          style: TextStyle(color: Color(AppConstants.textColor), fontSize: 16),
          decoration: InputDecoration(
            hintText: '搜索体态问题…',
            hintStyle: TextStyle(color: Color(AppConstants.textMuted)),
            border: InputBorder.none,
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 8, vertical: 0),
            filled: false,
          ),
          onChanged: (v) => setState(() => _query = v),
        ),
        actions: [
          if (_query.isNotEmpty)
            IconButton(
              icon: const Icon(Icons.clear),
              onPressed: () {
                _controller.clear();
                setState(() => _query = '');
              },
            ),
        ],
      ),
      body: showHotContent
          ? (issueState.isLoading && allIssues.isEmpty
              ? const Center(child: CircularProgressIndicator())
              : _buildHotContent(allIssues, postureStates))
          : issueState.isLoading
              ? const Center(child: CircularProgressIndicator())
              : results.isEmpty
                  ? Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.search_off,
                              size: 64, color: Color(AppConstants.primaryColor)),
                          const SizedBox(height: 16),
                          Text('未找到"$_query"相关问题',
                              style: TextStyle(
                                  color: Color(AppConstants.textMuted))),
                        ],
                      ),
                    )
                  : ListView.builder(
                      itemCount: results.length,
                      padding: const EdgeInsets.only(top: 8),
                      itemBuilder: (_, i) {
                        final issue = results[i];
                        return IssueCard(
                          issue: issue,
                          result: postureStates[issue.id]?.result,
                          onTap: () =>
                              context.push('/issue/${issue.id}/detail'),
                        );
                      },
                    ),
    );
  }

  Widget _buildHotContent(List<IssueSummary> allIssues, Map<String, UserPostureState> postureStates) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('热门问题',
              style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  color: Color(AppConstants.textColor))),
          const SizedBox(height: 12),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: _hotIssues.map((issue) {
              return ActionChip(
                label: Text(issue.$2,
                    style: TextStyle(
                        color: Color(AppConstants.textColor), fontSize: 14)),
                backgroundColor: Color(AppConstants.cardColor),
                side: BorderSide(
                    color: Color(AppConstants.glassBorder), width: 0.5),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(20)),
                padding:
                    const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
                onPressed: () =>
                    context.push('/issue/${issue.$1}/detail'),
              );
            }).toList(),
          ),
          const SizedBox(height: 24),
          const Text('按部位浏览',
              style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  color: Color(AppConstants.textMuted))),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _categoryTabs.map((tab) {
              final selected = _selectedCategory == tab.$1;
              return ChoiceChip(
                label: Text(tab.$2,
                    style: TextStyle(
                        fontSize: 13,
                        color: selected
                            ? Color(AppConstants.accentColor)
                            : Color(AppConstants.textMuted))),
                selected: selected,
                selectedColor:
                    Color(AppConstants.accentColor).withAlpha(38),
                backgroundColor: Color(AppConstants.cardColor),
                side: BorderSide(
                    color: selected
                        ? Color(AppConstants.accentColor).withAlpha(128)
                        : Color(AppConstants.glassBorder),
                    width: 0.5),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16)),
                visualDensity: VisualDensity.compact,
                onSelected: (_) => setState(() => _selectedCategory = tab.$1),
              );
            }).toList(),
          ),
          const SizedBox(height: 16),
          // 按分类展示过滤结果
          if (_selectedCategory != 'all') ...[
            ..._filter(allIssues, '').map((issue) => Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: IssueCard(
                    issue: issue,
                    result: postureStates[issue.id]?.result,
                    onTap: () =>
                        context.push('/issue/${issue.id}/detail'),
                  ),
                )),
          ],
        ],
      ),
    );
  }
}
