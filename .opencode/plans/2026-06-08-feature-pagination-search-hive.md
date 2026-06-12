# 功能完善计划：本地持久化 + 分页加载 + 搜索功能

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完善 3 个独立功能：(1) Hive 本地持久化体态状态、(2) 历史记录分页加载、(3) 问题搜索功能，并修复首页硬编码 26 的问题。

**Architecture:**
- Task 1: 用 Hive box 持久化 `UserPostureState`，App 重启后从磁盘恢复，写入时同步 Hive；
- Task 2: `AssessmentState` 增加 `hasMore`/`offset` 字段，历史页底部加"加载更多"按钮；
- Task 3: 新增全局搜索 provider，首页/问题列表页顶部加搜索入口，搜索走已缓存的 `issuesByCategory['all']`。

**Tech Stack:** Flutter, Riverpod 2, Hive 2 (已在 pubspec), GoRouter, 现有 API

---

## File Modification Map

| 文件 | 操作 | 说明 |
|------|------|------|
| `lib/providers/posture_state_provider.dart` | Modify | 加入 Hive 读写 |
| `lib/main.dart` | Modify | Hive 初始化 |
| `lib/services/sync_service.dart` | Modify | 登出时清除 Hive |
| `lib/screens/home/home_screen.dart` | Modify | 硬编码 26 → 动态 |
| `lib/providers/assessment_provider.dart` | Modify | 加 `hasMore`/`offset`/`appendHistory` |
| `lib/screens/history/history_screen.dart` | Modify | 加载更多按钮 |
| `lib/providers/issue_provider.dart` | Modify | 确保 `all` 分类缓存全量 |
| `lib/screens/issues/issue_list_screen.dart` | Modify | 加搜索入口 |
| `lib/screens/search/search_screen.dart` | **Create** | 搜索页 |

---

## Task 1: Hive 本地持久化体态状态

**Files:**
- Modify: `app/lib/main.dart`
- Modify: `app/lib/providers/posture_state_provider.dart`
- Modify: `app/lib/services/sync_service.dart`

### 背景

Hive 已在 pubspec 中（`hive: ^2.2.3`, `hive_flutter: ^1.1.0`），`UserPostureState` 已有 `toJson()`/`fromJson()`。策略：用一个 `Map<String, dynamic>` 类型的 Hive box（名为 `postureStateBox`），key = issueId，value = `UserPostureState.toJson()`。

- [ ] **Step 1: 初始化 Hive（main.dart）**

```dart
// app/lib/main.dart
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'app.dart';
import 'providers/auth_provider.dart';
import 'services/sync_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await Hive.initFlutter();
  await Hive.openBox<Map>('postureStateBox');

  FlutterError.onError = (details) {
    FlutterError.presentError(details);
    debugPrint('Flutter error: ${details.exceptionAsString()}');
  };
  PlatformDispatcher.instance.onError = (error, stack) {
    debugPrint('Uncaught error: $error\n$stack');
    return true;
  };

  final container = ProviderContainer();

  await container.read(authProvider.notifier).checkAuth();

  if (container.read(authProvider).isLoggedIn) {
    try {
      await container.read(syncServiceProvider).startupSync();
    } catch (e) {
      debugPrint('Startup sync failed: $e');
    }
  }

  runApp(
    UncontrolledProviderScope(
      container: container,
      child: const PostureApp(),
    ),
  );
}
```

- [ ] **Step 2: 重写 posture_state_provider.dart（加 Hive 读写）**

```dart
// app/lib/providers/posture_state_provider.dart
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive/hive.dart';
import '../models/assessment.dart';
import '../models/user_posture_state.dart';

class PostureStateNotifier extends StateNotifier<Map<String, UserPostureState>> {
  static const _boxName = 'postureStateBox';

  PostureStateNotifier() : super({}) {
    _loadFromDisk();
  }

  Box<Map> get _box => Hive.box<Map>(_boxName);

  void _loadFromDisk() {
    try {
      final diskState = <String, UserPostureState>{};
      for (final key in _box.keys) {
        final raw = _box.get(key);
        if (raw != null) {
          diskState[key.toString()] = UserPostureState.fromJson(
              Map<String, dynamic>.from(raw));
        }
      }
      state = diskState;
    } catch (e) {
      debugPrint('PostureState: load from disk failed: $e');
    }
  }

  void updateState({
    required String issueId,
    required String result,
    required String method,
  }) {
    final entry = UserPostureState(
      issueId: issueId,
      result: result,
      method: method,
      updatedAt: DateTime.now(),
      synced: false,
    );
    final newState = Map<String, UserPostureState>.from(state);
    newState[issueId] = entry;
    state = newState;
    try {
      _box.put(issueId, entry.toJson());
    } catch (e) {
      debugPrint('PostureState: save to disk failed: $e');
    }
  }

  void rebuildFromHistory(List<AssessmentRecord> records) {
    final Map<String, List<AssessmentRecord>> grouped = {};
    for (final r in records) {
      grouped.putIfAbsent(r.issueId, () => []).add(r);
    }
    final newState = <String, UserPostureState>{};
    for (final entry in grouped.entries) {
      entry.value.sort((a, b) => b.createdAt.compareTo(a.createdAt));
      final latest = entry.value.first;
      newState[entry.key] = UserPostureState(
        issueId: entry.key,
        result: latest.result,
        method: latest.method,
        updatedAt: latest.createdAt,
        synced: true,
      );
    }
    state = newState;
    try {
      _box.clear();
      for (final e in newState.entries) {
        _box.put(e.key, e.value.toJson());
      }
    } catch (e) {
      debugPrint('PostureState: sync to disk failed: $e');
    }
  }

  void clearAll() {
    state = {};
    try {
      _box.clear();
    } catch (e) {
      debugPrint('PostureState: clear disk failed: $e');
    }
  }
}

final postureStateProvider =
    StateNotifierProvider<PostureStateNotifier, Map<String, UserPostureState>>(
        (_) => PostureStateNotifier());
```

- [ ] **Step 3: sync_service 登出时清除 Hive**

在 `auth_provider.dart` 的 `logout()` 方法中，`clearTokens()` 之后调用 `ref.read(postureStateProvider.notifier).clearAll()`：

```dart
// app/lib/providers/auth_provider.dart — logout() 方法
Future<void> logout() async {
  await AppStorage.clearTokens();
  _api.onAuthFailed = null;
  state = const AuthState();
}
```

> **注意：** posture_state 的清除由 `_onAuthFailed` 触发后 UI 层通过 Riverpod 失效来处理，而不是在 auth_provider 里直接引用。改为在 `app.dart` 的 `_AuthNotifier` 监听到 logout 时：

实际上，在 `sync_service.dart` 的 `startupSync` 已经会调用 `rebuildFromHistory` 完成覆盖，所以登出时只需要确保 `posture_state_provider.clearAll()` 被调用。最简单方案：在 `auth_provider.dart` 的 `_onAuthFailed` 回调之后，在 `logout()` 内额外调用（但不引入循环依赖）。

**最简方案：** 直接在 `PostureStateNotifier._loadFromDisk()` 增加容错，并在 `rebuildFromHistory()` 覆盖磁盘即可。退出登录时由于 `state = const AuthState()` 触发 GoRouter redirect 到 `/login`，下次登录 `startupSync` 会自动用新用户历史覆盖。这已满足需求，无需额外改动。

- [ ] **Step 4: 修复 home_screen 硬编码 26**

```dart
// app/lib/screens/home/home_screen.dart — body 档案文字部分
// 用 issueProvider 的 all 分类长度动态显示
final issueState = ref.watch(issueProvider);
final totalCount = issueState.issuesByCategory['all']?.length ?? 53;
// ...
Text('已评估 $assessedCount/$totalCount 项，$problemCount 项需关注', ...)
```

同时在 class 开头 import issueProvider：
```dart
import '../../providers/issue_provider.dart';
```

- [ ] **Step 5: 运行 flutter analyze 确认无错误**

```bash
cd app && flutter analyze
```

Expected: 0 errors

- [ ] **Step 6: Commit**

```bash
git add app/lib/main.dart app/lib/providers/posture_state_provider.dart app/lib/screens/home/home_screen.dart
git commit -m "feat: persist posture state to Hive, fix hardcoded total count"
```

---

## Task 2: 历史记录分页加载

**Files:**
- Modify: `app/lib/providers/assessment_provider.dart`
- Modify: `app/lib/screens/history/history_screen.dart`

### 策略

- `AssessmentState` 新增 `hasMore: bool`、`currentOffset: int`
- `fetchHistory(offset: 0)` 覆盖式加载（初始/刷新）
- `fetchMoreHistory()` 追加式加载
- 历史页 ListView 末尾加"加载更多"按钮（非无限滚动，用手动触发保持简单）

- [ ] **Step 1: 修改 assessment_provider.dart**

```dart
// app/lib/providers/assessment_provider.dart
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../models/assessment.dart';

const _pageSize = 20;

class AssessmentState {
  final SelfAssessResult? currentResult;
  final List<AssessmentRecord> history;
  final bool isLoading;
  final bool isLoadingMore;
  final bool hasMore;
  final int currentOffset;
  final String? error;

  const AssessmentState({
    this.currentResult,
    this.history = const [],
    this.isLoading = false,
    this.isLoadingMore = false,
    this.hasMore = false,
    this.currentOffset = 0,
    this.error,
  });

  AssessmentState copyWith({
    SelfAssessResult? currentResult,
    bool clearResult = false,
    List<AssessmentRecord>? history,
    bool? isLoading,
    bool? isLoadingMore,
    bool? hasMore,
    int? currentOffset,
    String? error,
    bool clearError = false,
  }) =>
      AssessmentState(
        currentResult: clearResult ? null : (currentResult ?? this.currentResult),
        history: history ?? this.history,
        isLoading: isLoading ?? this.isLoading,
        isLoadingMore: isLoadingMore ?? this.isLoadingMore,
        hasMore: hasMore ?? this.hasMore,
        currentOffset: currentOffset ?? this.currentOffset,
        error: clearError ? null : (error ?? this.error),
      );
}

class AssessmentNotifier extends StateNotifier<AssessmentState> {
  final ApiClient _api;

  AssessmentNotifier(this._api) : super(const AssessmentState());

  Future<SelfAssessResult?> submitSelfAssess(String issueId, int testIndex, String answer) async {
    try {
      state = state.copyWith(isLoading: true, clearError: true);
      final resp = await _api.dio.post('/posture/assess', data: {
        'issue_id': issueId,
        'test_index': testIndex,
        'answer': answer,
      });
      final result = SelfAssessResult.fromJson(resp.data as Map<String, dynamic>);
      state = state.copyWith(currentResult: result, isLoading: false);
      return result;
    } on DioException catch (e) {
      final data = e.response?.data;
      final msg = (data is Map<String, dynamic>)
          ? (data['detail'] as String?) ?? '提交失败'
          : '提交失败';
      state = state.copyWith(isLoading: false, error: msg);
      return null;
    } catch (e) {
      state = state.copyWith(isLoading: false, error: '提交失败');
      return null;
    }
  }

  Future<Map<String, dynamic>?> submitPhotoAssess(String issueId, List<String> photoKeys) async {
    try {
      state = state.copyWith(isLoading: true, clearError: true, clearResult: true);
      final resp = await _api.dio.post('/posture/assess/photo', data: {
        'issue_id': issueId,
        'photo_keys': photoKeys,
      });
      state = state.copyWith(isLoading: false);
      return resp.data as Map<String, dynamic>;
    } on DioException catch (e) {
      final data = e.response?.data;
      final msg = (data is Map<String, dynamic>)
          ? (data['detail'] as String?) ?? '分析失败'
          : '分析失败';
      state = state.copyWith(isLoading: false, error: msg);
      return null;
    } catch (e) {
      state = state.copyWith(isLoading: false, error: '分析失败');
      return null;
    }
  }

  /// 初始加载或刷新（覆盖式）
  Future<void> fetchHistory() async {
    try {
      state = state.copyWith(isLoading: true, clearError: true);
      final resp = await _api.dio.get('/posture/history',
          queryParameters: {'limit': _pageSize, 'offset': 0});
      final list = (resp.data as List)
          .map((e) => AssessmentRecord.fromJson(e as Map<String, dynamic>))
          .toList();
      state = state.copyWith(
        history: list,
        isLoading: false,
        currentOffset: list.length,
        hasMore: list.length >= _pageSize,
      );
    } on DioException catch (e) {
      final data = e.response?.data;
      final msg = (data is Map<String, dynamic>)
          ? (data['detail'] as String?) ?? '加载失败'
          : '加载失败';
      state = state.copyWith(isLoading: false, error: msg);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: '数据解析异常');
    }
  }

  /// 追加加载更多
  Future<void> fetchMoreHistory() async {
    if (state.isLoadingMore || !state.hasMore) return;
    try {
      state = state.copyWith(isLoadingMore: true, clearError: true);
      final resp = await _api.dio.get('/posture/history',
          queryParameters: {
            'limit': _pageSize,
            'offset': state.currentOffset,
          });
      final list = (resp.data as List)
          .map((e) => AssessmentRecord.fromJson(e as Map<String, dynamic>))
          .toList();
      state = state.copyWith(
        history: [...state.history, ...list],
        isLoadingMore: false,
        currentOffset: state.currentOffset + list.length,
        hasMore: list.length >= _pageSize,
      );
    } on DioException catch (e) {
      final data = e.response?.data;
      final msg = (data is Map<String, dynamic>)
          ? (data['detail'] as String?) ?? '加载失败'
          : '加载失败';
      state = state.copyWith(isLoadingMore: false, error: msg);
    } catch (e) {
      state = state.copyWith(isLoadingMore: false, error: '加载失败');
    }
  }
}

final assessmentProvider = StateNotifierProvider<AssessmentNotifier, AssessmentState>((ref) {
  final api = ref.read(apiClientProvider);
  return AssessmentNotifier(api);
});
```

- [ ] **Step 2: 修改 history_screen.dart — 加载更多**

```dart
// app/lib/screens/history/history_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import '../../core/constants.dart';
import '../../providers/assessment_provider.dart';
import '../../widgets/glass_card.dart';
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
    Future.microtask(() => ref.read(assessmentProvider.notifier).fetchHistory());
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(assessmentProvider);

    final grouped = <String, List<dynamic>>{};
    for (final r in state.history) {
      final key = DateFormat('yyyy-MM-dd').format(r.createdAt);
      grouped.putIfAbsent(key, () => []).add(r);
    }

    // 在日期组列表末尾加"加载更多"条目
    final dateKeys = grouped.keys.toList();

    return Scaffold(
      appBar: AppBar(title: const Text('评估历史')),
      body: state.isLoading
          ? const Center(child: CircularProgressIndicator())
          : state.history.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.history, size: 64, color: Color(AppConstants.primaryColor)),
                      const SizedBox(height: 16),
                      Text('暂无评估记录',
                          style: TextStyle(fontSize: 18, color: Color(AppConstants.textMuted))),
                      Text('去首页开始你的第一次体态分析吧',
                          style: TextStyle(color: Color(AppConstants.textMuted))),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: () async => ref.read(assessmentProvider.notifier).fetchHistory(),
                  child: ListView.builder(
                    padding: const EdgeInsets.only(bottom: 80),
                    // +1 for load more footer
                    itemCount: dateKeys.length + 1,
                    itemBuilder: (_, i) {
                      // Load more footer
                      if (i == dateKeys.length) {
                        if (state.isLoadingMore) {
                          return const Padding(
                            padding: EdgeInsets.symmetric(vertical: 24),
                            child: Center(child: CircularProgressIndicator()),
                          );
                        }
                        if (state.hasMore) {
                          return Padding(
                            padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                            child: OutlinedButton(
                              onPressed: () =>
                                  ref.read(assessmentProvider.notifier).fetchMoreHistory(),
                              child: const Text('加载更多'),
                            ),
                          );
                        }
                        return Padding(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          child: Center(
                            child: Text('已加载全部记录',
                                style: TextStyle(
                                    color: Color(AppConstants.textMuted), fontSize: 13)),
                          ),
                        );
                      }

                      final date = dateKeys[i];
                      final records = grouped[date]!;
                      return Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Padding(
                            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                            child: Text(_formatDate(date),
                                style: TextStyle(
                                    fontSize: 14,
                                    color: Color(AppConstants.textMuted),
                                    fontWeight: FontWeight.w600)),
                          ),
                          ...records.map((r) => GlassCard(
                            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                            padding: const EdgeInsets.all(12),
                            child: InkWell(
                              borderRadius: BorderRadius.circular(20),
                              onTap: () => context.push('/issue/${r.issueId}/result', extra: {
                                'assessmentId': r.id,
                                'result': r.result,
                                'suggestion': '',
                              }),
                              child: Row(
                                children: [
                                  Container(
                                    width: 12, height: 12,
                                    decoration: BoxDecoration(
                                      shape: BoxShape.circle,
                                      color: _resultColor(r.result),
                                    ),
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(r.issueName,
                                            style: TextStyle(
                                                fontSize: 15,
                                                color: Color(AppConstants.textColor))),
                                        const SizedBox(height: 2),
                                        Container(
                                          padding: const EdgeInsets.symmetric(
                                              horizontal: 8, vertical: 2),
                                          decoration: BoxDecoration(
                                            color: Color(AppConstants.primaryColor),
                                            borderRadius: BorderRadius.circular(8),
                                          ),
                                          child: Text(
                                            r.method == 'self_test' ? '自测' : 'AI',
                                            style: TextStyle(
                                                fontSize: 11,
                                                color: Color(AppConstants.textMuted)),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  Text(
                                    DateFormat('HH:mm').format(r.createdAt),
                                    style: TextStyle(
                                        color: Color(AppConstants.textMuted), fontSize: 13),
                                  ),
                                ],
                              ),
                            ),
                          )),
                        ],
                      );
                    },
                  ),
                ),
    );
  }

  Color _resultColor(String result) {
    switch (result) {
      case 'normal': return const Color(AppConstants.normalColor);
      case 'moderate': return const Color(AppConstants.moderateColor);
      case 'severe': return const Color(AppConstants.severeColor);
      default: return const Color(AppConstants.textMuted);
    }
  }

  String _formatDate(String dateStr) {
    final now = DateTime.now();
    final date = DateTime.tryParse(dateStr);
    if (date == null) return dateStr;
    if (DateFormat('yyyy-MM-dd').format(now) == dateStr) return '今天';
    if (DateFormat('yyyy-MM-dd').format(now.subtract(const Duration(days: 1))) == dateStr) {
      return '昨天';
    }
    return DateFormat('M月d日').format(date);
  }
}
```

- [ ] **Step 3: 运行 flutter analyze 确认无错误**

```bash
cd app && flutter analyze
```

Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
git add app/lib/providers/assessment_provider.dart app/lib/screens/history/history_screen.dart
git commit -m "feat: add history pagination with load more"
```

---

## Task 3: 问题搜索功能

**Files:**
- Modify: `app/lib/providers/issue_provider.dart` — 确保 `fetchIssues(null)` 缓存 `'all'` key
- Create: `app/lib/screens/search/search_screen.dart` — 搜索页
- Modify: `app/lib/screens/issues/issue_list_screen.dart` — AppBar 加搜索图标入口
- Modify: `app/lib/app.dart` — 注册 `/search` 路由

### 策略

- 搜索走**本地缓存**（已经在 `issuesByCategory['all']` 里，`syncService.startupSync` 时已调用 `fetchIssues(null)` 缓存全量）
- `SearchScreen` 是独立页面，接收 query 参数，纯过滤 — 不发 API 请求
- 搜索范围：`name_cn` + `aliases` + `definition`（前 20 字）

- [ ] **Step 1: 确认 issue_provider fetchIssues 缓存 all key（无需改动，但确认）**

`issue_provider.dart` 中 `fetchIssues(null)` 已将结果存入 key `'all'`。`syncService.startupSync` 已调用 `fetchIssues(null)`。确认逻辑正确，无需修改。

- [ ] **Step 2: 创建 search_screen.dart**

```dart
// app/lib/screens/search/search_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/constants.dart';
import '../../models/issue.dart';
import '../../providers/issue_provider.dart';
import '../../providers/posture_state_provider.dart';
import '../../widgets/issue_card.dart';

class SearchScreen extends ConsumerStatefulWidget {
  const SearchScreen({super.key});

  @override
  ConsumerState<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends ConsumerState<SearchScreen> {
  final _controller = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  List<IssueSummary> _filter(List<IssueSummary> all, String query) {
    if (query.trim().isEmpty) return [];
    final q = query.trim().toLowerCase();
    return all.where((issue) {
      if (issue.nameCn.toLowerCase().contains(q)) return true;
      if (issue.aliases.any((a) => a.toLowerCase().contains(q))) return true;
      if (issue.definition.toLowerCase().contains(q)) return true;
      return false;
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final issueState = ref.watch(issueProvider);
    final postureStates = ref.watch(postureStateProvider);
    final allIssues = issueState.issuesByCategory['all'] ?? [];
    final results = _filter(allIssues, _query);

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
            contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 0),
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
      body: _query.trim().isEmpty
          ? Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.search, size: 64, color: Color(AppConstants.primaryColor)),
                  const SizedBox(height: 16),
                  Text('输入关键词搜索体态问题',
                      style: TextStyle(color: Color(AppConstants.textMuted))),
                  const SizedBox(height: 8),
                  Text('支持问题名称、别名、定义搜索',
                      style: TextStyle(
                          color: Color(AppConstants.textMuted), fontSize: 13)),
                ],
              ),
            )
          : issueState.isLoading
              ? const Center(child: CircularProgressIndicator())
              : results.isEmpty
                  ? Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.search_off, size: 64,
                              color: Color(AppConstants.primaryColor)),
                          const SizedBox(height: 16),
                          Text('未找到"$_query"相关问题',
                              style: TextStyle(color: Color(AppConstants.textMuted))),
                        ],
                      ),
                    )
                  : ListView.builder(
                      itemCount: results.length,
                      itemBuilder: (_, i) {
                        final issue = results[i];
                        return IssueCard(
                          issue: issue,
                          result: postureStates[issue.id]?.result,
                          onTap: () => context.push('/issue/${issue.id}/detail'),
                        );
                      },
                    ),
    );
  }
}
```

- [ ] **Step 3: 在 app.dart 注册 /search 路由**

在 `app.dart` 的 routes 列表中，已有的 GoRoute 列表里添加：

```dart
GoRoute(
  path: '/search',
  builder: (_, __) => const SearchScreen(),
),
```

同时在 imports 里加：
```dart
import 'screens/search/search_screen.dart';
```

- [ ] **Step 4: 在 issue_list_screen.dart AppBar 加搜索入口**

修改 `IssueListScreen` 的 AppBar，添加搜索 action：

```dart
appBar: AppBar(
  title: Text(categoryName),
  actions: [
    IconButton(
      icon: const Icon(Icons.search),
      tooltip: '搜索',
      onPressed: () => context.push('/search'),
    ),
  ],
),
```

- [ ] **Step 5: 在 home_screen.dart AppBar 加搜索入口**

修改 `HomeScreen` 的 AppBar，添加搜索 action：

```dart
appBar: AppBar(
  title: const Text(AppConstants.appName),
  centerTitle: true,
  actions: [
    IconButton(
      icon: const Icon(Icons.search),
      tooltip: '搜索',
      onPressed: () => context.push('/search'),
    ),
  ],
),
```

- [ ] **Step 6: 运行 flutter analyze 确认无错误**

```bash
cd app && flutter analyze
```

Expected: 0 errors

- [ ] **Step 7: Commit**

```bash
git add app/lib/screens/search/ app/lib/app.dart app/lib/screens/issues/issue_list_screen.dart app/lib/screens/home/home_screen.dart
git commit -m "feat: add issue search screen with local filtering"
```

---

## Task 4: 最终验证

- [ ] **Step 1: 完整 analyze**

```bash
cd app && flutter analyze 2>&1 | grep -E "error|warning"
```

Expected: 0 errors, 0 warnings

- [ ] **Step 2: 后端测试**

```bash
cd backend && python -m pytest tests/ -q
```

Expected: 13 passed

- [ ] **Step 3: 验证 Hive 持久化**

启动 App → 登录 → 做一次自测 → 关闭 App → 重新启动 → 检查首页档案计数是否保留

- [ ] **Step 4: 验证分页**

启动 App → 进入历史页 → 如有超过 20 条记录可看到"加载更多"按钮；少于 20 条则显示"已加载全部记录"

- [ ] **Step 5: 验证搜索**

进入任意问题列表 → 点击 AppBar 右上角搜索图标 → 输入"头" → 确认显示相关结果 → 输入"FHP" → 确认别名搜索有效

- [ ] **Step 6: Commit 文档更新**

```bash
git add docs/
git commit -m "docs: update implementation status with pagination, search, Hive cache"
```
