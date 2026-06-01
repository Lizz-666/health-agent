# 体态分析 Flutter App 前端设计 Spec

> 日期: 2026-06-01
> 状态: Draft → 待审查
> 范围: 体态模块 Flutter 前端 MVP（模块1/3）
> 后端状态: 已完成，13 个测试通过

---

## 1. 项目概述

### 1.1 产品定位

面向健身人群的健康 App 的体态分析模块。用户可通过 3D 人体导航浏览 26 个体态问题，进行自测评估或 AI 拍照分析，发现的问题自动记录为用户体态状态，持续追踪。

### 1.2 MVP 功能清单

| 功能 | 优先级 |
|------|--------|
| 验证码登录（登录即注册） | P0 |
| 用户信息采集（身高/体重/年龄/性别） | P0 |
| 首页 3D 人体模型导航 | P0 |
| 体态问题列表 + 详情 | P0 |
| 自测评估流程 | P0 |
| AI 拍照分析 | P0 |
| 评估结果展示 + 关联推荐 | P0 |
| 我的体态档案（当前状态汇总） | P0 |
| 历史记录 | P1 |
| 个人中心 | P1 |

### 1.3 技术栈

| 类别 | 选型 |
|------|------|
| 框架 | Flutter 3.x |
| 状态管理 | Riverpod 2 (StateNotifier) |
| 路由 | GoRouter 14 |
| HTTP | Dio 5 |
| 本地存储 | Hive（业务数据缓存）+ FlutterSecureStorage（Token） |
| 3D 渲染 | model_viewer_plus（WebView + GLB） |
| 图片 | image_picker + cached_network_image |
| 平台 | Android + iOS 双平台 |

### 1.4 约束

- 开发环境：Windows + Android 模拟器
- 后端已有 API，前端对齐后端接口
- 3D 模型先用占位 GLB，后续替换 MakeHuman 生成模型
- 自测示意图先用占位图，后续替换 AI 生成图

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────┐
│              UI Layer (Screens)          │
├─────────────────────────────────────────┤
│          State Management (Providers)    │
│  auth | user | issue | assessment |     │
│  posture_state                         │
├──────────────┬──────────────────────────┤
│  API Client  │   Local Storage          │
│  (Dio+JWT)   │   (Hive + SecureStorage) │
├──────────────┴──────────────────────────┤
│         Sync Manager                    │
│   本地优先写入 → 联网后同步到云端         │
├─────────────────────────────────────────┤
│              Backend API                │
│     FastAPI (已实现)                     │
└─────────────────────────────────────────┘
```

### 2.2 本地存储策略

**存储分工：**

| 数据 | 存储位置 | 同步方向 | 说明 |
|------|---------|---------|------|
| Token | SecureStorage | 仅云端 | access_token + refresh_token |
| 用户信息 | Hive | 双向 | 先本地缓存，联网刷新 |
| 体态问题库 | Hive | 云端→本地 | 启动时检查更新 |
| 评估结果 | Hive 先存 | 本地→云端 | pending_sync 标记 |
| 用户体态状态 | Hive | 仅本地 | 从评估历史聚合推导 |

**Hive TypeId 分配：**

| typeId | 类型 | 说明 |
|--------|------|------|
| 1 | UserPostureState | 每个问题的最新状态 |
| 2 | AssessmentRecord | 本地评估记录缓存 |
| 3 | IssueCacheEntry | 问题库缓存 |
| 4 | UserProfileCache | 用户信息缓存 |

**同步策略：**
- 启动时：拉取云端最新评估历史 → 本地聚合推导体态状态 → 更新 Hive
- 提交评估时：先写 Hive（pending_sync=true）→ 调 API → 成功标记 synced
- 网络失败：保留 pending_sync，下次启动重试
- 冲突解决：last-write-wins（按 updatedAt 比较，保留更新的记录）

### 2.3 体态状态聚合逻辑

用户体态状态不从后端直接获取，而是客户端从评估历史中推导：

```
App 启动 / 新评估提交后
  → 读取所有评估记录（Hive + 云端合并）
  → 按 issue_id 分组，取每组中 updatedAt 最新的记录
  → 生成 Map<String, UserPostureState>
  → 存入 Hive + 更新 Provider
```

### 2.4 文件结构

```
app/lib/
├── main.dart                           # Hive 初始化 + ProviderScope
├── app.dart                            # MaterialApp.router + GoRouter + 主题
├── core/
│   ├── constants.dart                  # API URL, 颜色, 分类映射
│   ├── theme.dart                      # 深色主题定义
│   ├── storage.dart                    # Hive 封装（CRUD + 盒子管理）
│   ├── api_client.dart                 # Dio 单例 + JWT 拦截器 + 401 自动刷新
│   └── sync_manager.dart              # 本地→云端同步管理
├── models/
│   ├── user.dart                       # 用户模型
│   ├── issue.dart                      # 体态问题模型（含嵌套结构）
│   ├── assessment.dart                 # 评估结果模型
│   ├── token.dart                      # JWT Token 模型
│   └── user_posture_state.dart         # 用户当前体态状态（Hive TypeId=1）
├── providers/
│   ├── auth_provider.dart              # 登录状态管理
│   ├── user_provider.dart              # 用户信息
│   ├── issue_provider.dart             # 问题库数据（含 Hive 缓存）
│   ├── assessment_provider.dart        # 评估提交/历史
│   └── posture_state_provider.dart     # 体态档案状态管理（聚合推导）
├── screens/
│   ├── auth/
│   │   └── login_screen.dart           # 验证码登录（登录即注册）
│   ├── onboarding/
│   │   └── onboarding_screen.dart      # 信息采集（4步，每步可跳过）
│   ├── home/
│   │   └── home_screen.dart            # 3D 导航 + 档案入口 + 档案统计
│   ├── issues/
│   │   ├── issue_list_screen.dart      # 分类问题列表
│   │   └── issue_detail_screen.dart    # 问题详情（定义/成因/纠正/后果/红旗征）
│   ├── test/
│   │   ├── self_test_screen.dart       # 自测流程（PageView + 三选一）
│   │   └── photo_test_screen.dart      # AI 拍照分析
│   ├── result/
│   │   └── result_screen.dart          # 结果展示 + 纠正建议 + 关联推荐
│   ├── history/
│   │   └── history_screen.dart         # 按日期分组的评估历史
│   ├── profile/
│   │   ├── profile_screen.dart         # 个人中心
│   │   └── posture_profile_screen.dart # 体态档案（当前状态汇总）
│   └── widgets/
│       ├── loading_overlay.dart
│       ├── issue_card.dart
│       ├── result_badge.dart
│       ├── disclaimer_banner.dart
│       └── body_region_button.dart     # 2D 降级时的分类按钮
└── services/
    └── sync_service.dart               # 同步服务（启动同步 + 重试队列）
```

---

## 3. 路由设计

### 3.1 路由表

| 路径 | 页面 | 需要登录 |
|------|------|---------|
| `/login` | 登录页 | 否 |
| `/onboarding` | 信息采集 | 是 |
| `/` | 首页（3D 导航） | 是 |
| `/issues/:category` | 问题列表 | 是 |
| `/issues/:id` | 问题详情 | 是 |
| `/issues/:id/test` | 自测 | 是 |
| `/issues/:id/photo` | AI 拍照 | 是 |
| `/issues/:id/result` | 结果页 | 是 |
| `/history` | 历史记录 | 是 |
| `/profile` | 个人中心 | 是 |
| `/profile/posture` | 体态档案 | 是 |

### 3.2 路由守卫

```dart
redirect: (context, state) {
  final isLoggedIn = /* 读 auth_provider */;
  final hasProfile = /* 读 user_provider, 判断身高/体重等是否有值 */;
  final isOnLogin = state.matchedLocation == '/login';
  final isOnOnboarding = state.matchedLocation == '/onboarding';

  if (!isLoggedIn && !isOnLogin) return '/login';
  if (isLoggedIn && isOnLogin) return '/';
  if (isLoggedIn && !hasProfile && !isOnOnboarding) return '/onboarding';
  return null;
}
```

### 3.3 底部导航

使用 `StatefulShellRoute.indexedStack`，3 个 tab：

```
Tab 0: 首页 (/)
Tab 1: 历史 (/history)
Tab 2: 个人中心 (/profile)
```

每个 tab 维护独立的导航栈，切换 tab 时不丢失子页面状态。

---

## 4. 页面详细设计

### 4.1 登录页

- 顶部：App Logo + 标语"了解你的身体，科学改善体态"
- 手机号输入框（11 位校验 `^1[3-9]\d{9}$`）
- 验证码输入框（6 位）+ "发送验证码"按钮（60s 倒计时）
- "登录"大按钮（主色调）
- 底部文字："首次验证将自动注册账号"
- 无密码输入，无单独注册页

**API 对接：**
- 发送验证码：`POST /api/v1/auth/send-code`
- 登录：`POST /api/v1/auth/verify-login`
- 返回 `{access_token, refresh_token, is_new_user}`
- `is_new_user=true` → 跳转信息采集，否则跳首页

### 4.2 信息采集页

PageView 4 步卡片：
1. 身高（Slider 100-220cm）
2. 体重（Slider 30-200kg）
3. 年龄（NumberPicker）
4. 性别（男/女选择按钮）+ "完成"按钮

**每一步都允许跳过**（选填），最后一步可以点"稍后完善"直接进首页。
路由守卫不强求填完，仅检查是否已登录。

**API 对接：**
- 提交信息：`PUT /api/v1/user/profile`

### 4.3 首页

```
┌──────────────────────────────┐
│  AppBar: "体态分析"           │
├──────────────────────────────┤
│                              │
│  3D 人体模型区域              │
│  model_viewer_plus WebView   │
│  （可旋转/缩放）              │
│  热点标注方式：               │
│  - 首选：Flutter Stack +     │
│    Positioned overlay 按钮   │
│  - 备选：2D 分类按钮列表     │
│                              │
├──────────────────────────────┤
│  [综合评估] 按钮             │
├──────────────────────────────┤
│  "我的体态档案" 卡片         │
│  已评估 X/26 项，X 项需关注  │
│  点击 → /profile/posture     │
├──────────────────────────────┤
│  底部导航：首页 | 历史 | 个人 │
└──────────────────────────────┘
```

**3D 导航交互：**
- 点击身体区域 → 跳转 `/issues/:category`
- 分类映射：头颈→head_neck, 肩胸→shoulder_thorax, 骨盆→pelvis_spine, 下肢→lower_limb
- 底部独立按钮："综合评估" → `/issues/compound`

**3D 降级策略：**
- WebView 加载失败（onError）→ 隐藏 3D 区域
- 显示 4 个 BodyRegionButton（带图标和名称），功能等价
- 开发阶段提供"开发者选项"切换 2D/3D 模式

### 4.4 问题列表页

- AppBar：分类中文名（如"头颈部"）
- ListView.builder 渲染 IssueCard：
  - 深色卡片，圆角
  - 标题：问题中文名
  - 副标题：俗称标签（Chip 样式）
  - 右侧：已评估时显示 ResultBadge（绿/黄/红），未评估不显示
  - 底部：一句话定义
  - 点击 → 跳转问题详情
- 空状态："该分类暂无问题"

**API 对接：**
- `GET /api/v1/posture/issues?category=xxx`

### 4.5 问题详情页

CustomScrollView，各区段 Card 包裹：
- **定义区**：名称 + 英文名 + 俗称 Chip + 定义文本
- **成因区**：按 type 分组列表（行为习惯/肌肉失衡/…）
- **纠正方法区**：按 拉伸/强化/习惯/灵活性 分组展示
- **后果区**：短期/长期分栏
- **红旗征区**（若有）：红色高亮 Card + 醒目警告图标
- 底部固定 SafeArea 按钮："开始自测" → `/issues/:id/test`

**API 对接：**
- `GET /api/v1/posture/issues/:id`

### 4.6 自测流程页

PageView 逐步展示每个自测方法：
- 顶部 60%：示意图（占位图 placeholder.png）
- 中部：步骤列表（编号 + 文字）
- 底部高亮文字："阳性征：{positive_sign}"

最后一页为结果选择：
- "我有这个问题"（positive）→ 橙色按钮
- "我没有这个问题"（negative）→ 绿色按钮
- "不确定"（uncertain）→ 灰色按钮

**选择后的流程：**
1. 调用 assessment_provider.submitSelfAssess()
2. 先写 Hive（pending_sync=true）
3. 调 API `POST /api/v1/posture/assess`
4. 成功 → 标记 synced，更新 posture_state_provider
5. 失败 → 保持 pending_sync，加入重试队列
6. 更新 UserPostureState（该问题的最新状态）
7. 如果选"不确定" → 弹窗："要试试 AI 拍照分析吗？" → 是则跳 photo 页
8. 跳转结果页

### 4.7 AI 拍照分析页

**引导阶段：**
- 提示文字："请保持自然站姿，全身入镜"
- 示意图（正确站姿占位图）
- 两个按钮："拍照" / "从相册选择"

**上传流程：**
1. image_picker 获取图片（maxWidth: 1024, maxHeight: 1024, compress）
2. `POST /api/v1/upload/sts-token` 获取 OSS 临时凭证
3. Dio 直传图片到 OSS
4. `POST /api/v1/posture/assess/photo` 提交分析

**等待态：**
- 全屏加载动画 + "AI 正在分析中..."
- 超时 30s 提示"分析超时，请重试"

**Mock 模式：**
- 后端 DEV_MODE=true 且 DASHSCOPE_API_KEY 未配置时
- 后端 ai_service.py 应 catch 异常返回 mock 结果 + 提示
- 前端展示时标注"模拟结果，仅供参考"

### 4.8 结果页

**接收参数：** assessmentId, issueId, result, suggestion

**顶部大卡片：**
- ResultBadge（normal=绿+勾, moderate=黄+警告, severe=红+叉）
- 结果等级文字 + suggestion 文本
- severe → 自动弹就医提示 AlertDialog（不可跳过）

**中部（仅 moderate 时显示）：**
- "纠正建议" 标题
- 从 issue_provider 缓存中读取该问题的 corrections
- 按 拉伸/强化/习惯/灵活性 分组展示

**底部：**
- "相关问题推荐" 标题
- 横向滚动 ListView
- `GET /api/v1/posture/issues/:id/related`
- 每张卡片：问题名 + 关联强度 + 关系描述
- 点击 → 跳转对应问题详情

**固定底部：**
- DisclaimerBanner："本内容仅供参考，不能替代专业医疗诊断。如有不适请及时就医。"

### 4.9 历史记录页

- `GET /api/v1/posture/history`
- 按日期分组（今天/昨天/更早）
- 每条记录卡片：
  - 左侧：ResultBadge（颜色标识）
  - 中间：问题名称 + 方法标签（"自测" / "AI分析"）
  - 右侧：日期
- 点击 → 跳转结果页（复用 result_screen）
- 空状态："暂无评估记录，去首页开始你的第一次体态分析吧"

### 4.10 个人中心

- 顶部：头像占位圆形 + 手机号（脱敏 138****8000）
- 信息卡片：身高/体重/年龄/性别（点击弹编辑框 + "保存"→PUT /user/profile）
- 菜单项：
  - "我的体态档案" → /profile/posture
  - "评估历史" → /history
  - "关于" → 版本号 + 免责声明
  - "退出登录" → auth_provider.logout() → 清除 token + Hive → 跳 /login

### 4.11 体态档案页

- 标题："我的体态档案"
- 顶部统计卡片："已评估 X/26 项，X 项需关注"
- 按身体区域分组（头颈/肩胸/骨盆腰椎/下肢/复合综合征）：
  - 每个问题一行：名称 + ResultBadge + 最后评估时间
  - 未评估：灰色文字"未评估"
- 点击某个问题 → 跳转问题详情（可重新评估）
- 底部按钮："重新评估全部"（清除所有状态，重新开始）

**数据来源：** posture_state_provider（从评估历史聚合推导）

---

## 5. 状态管理

### 5.1 Provider 清单

#### auth_provider (StateNotifier<AuthState>)
```
状态：isLoggedIn, isLoading, error
方法：
  sendCode(phone) → POST /auth/send-code
  login(phone, code) → POST /auth/verify-login → saveTokens
  logout() → clearTokens + clearHive
  checkAuth() → 从 SecureStorage 读 token 判断状态
```

#### user_provider (StateNotifier<UserState>)
```
状态：userProfile, isLoading
方法：
  fetchProfile() → GET /user/profile（先 Hive，再 API）
  updateProfile(data) → PUT /user/profile
```

#### issue_provider (StateNotifier<IssueState>)
```
状态：issuesByCategory (Map<String, List<Issue>>), currentDetail
方法：
  fetchIssues(category?) → GET /posture/issues（先 Hive 缓存，再 API 刷新）
  fetchDetail(id) → GET /posture/issues/:id
```

#### assessment_provider (StateNotifier<AssessmentState>)
```
状态：currentResult, history, pendingSync (List<AssessmentRecord>)
方法：
  submitSelfAssess(issueId, testIndex, answer) → 先 Hive → POST /posture/assess
  submitPhotoAssess(issueId, photoKeys) → 先 Hive → POST /posture/assess/photo
  fetchHistory() → GET /posture/history → 更新 Hive + 聚合状态
```

#### posture_state_provider (StateNotifier<PostureState>)
```
状态：postureStates (Map<String, UserPostureState>)
方法：
  loadFromLocal() → 从 Hive 读取
  rebuildFromHistory(List<AssessmentRecord>) → 按 issueId 分组取最新
  updateState(issueId, result, method) → 单条更新
  clearAll() → 清除所有状态
```

### 5.2 核心数据流

**自测评估：**
```
用户选择答案
  → assessment_provider.submitSelfAssess()
    → 写 Hive (pending_sync=true)
    → POST /api/v1/posture/assess
    → 成功: synced=true
    → 失败: 保持 pending_sync
  → posture_state_provider.updateState(issueId, result, method)
    → 更新 Hive + Provider
  → 问题列表页的 ResultBadge 自动刷新
  → 首页的档案统计自动更新
  → 跳转结果页
```

**App 启动：**
```
main() → Hive.init() → runApp(ProviderScope)
  → auth_provider.checkAuth()
  → if logged in:
    → user_provider.fetchProfile() (Hive → API)
    → issue_provider.fetchIssues() (Hive → API)
    → sync_service.syncPending()
      → 遍历 pending_sync 记录，逐条重试
    → assessment_provider.fetchHistory()
      → API → Hive 缓存
      → posture_state_provider.rebuildFromHistory()
        → 聚合推导最新状态
```

**API 401 处理（Dio 拦截器）：**
```
响应 401
  → 读 refresh_token
  → POST /api/v1/auth/refresh
  → 成功: 更新 SecureStorage, 重试原请求
  → 失败: 清除 token, 跳转 /login
```

---

## 6. 依赖清单

```yaml
dependencies:
  flutter:
    sdk: flutter
  flutter_riverpod: ^2.5.0
  go_router: ^14.0.0
  dio: ^5.4.0
  hive: ^2.2.3
  hive_flutter: ^1.1.0
  model_viewer_plus: ^1.10.0
  image_picker: ^1.1.0
  flutter_secure_storage: ^9.2.0
  intl: ^0.19.0
  cached_network_image: ^3.3.0

dev_dependencies:
  hive_generator: ^2.0.0
  build_runner: ^2.4.0
  flutter_test:
    sdk: flutter
  flutter_lints: ^3.0.0
```

---

## 7. 深色主题

```dart
// 色板
backgroundColor: #1A1A2E    // 页面背景
cardColor: #16213E          // 卡片背景
primaryColor: #0F3460       // 主色调（按钮、AppBar）
accentColor: #E94560        // 强调色（CTA、警告）
textColor: #EAEAEA          // 正文文字
textSecondary: #8892B0      // 次要文字
successColor: #00C853       // 正常/绿色
warningColor: #FFB300       // 中度/黄色
errorColor: #FF1744         // 严重/红色

// 结果徽章颜色映射
normal  → successColor (#00C853)
moderate → warningColor (#FFB300)
severe  → errorColor (#FF1744)
```

---

## 8. 非功能性要求

### 8.1 错误处理

| 场景 | 处理 |
|------|------|
| 网络断开 | Toast: "网络连接失败，数据已保存到本地" |
| API 401 | 自动 refresh token，失败跳登录 |
| API 其他错误 | Toast 显示后端 detail |
| 3D 加载失败 | 降级为 2D 按钮列表 |
| AI 分析超时 | 30s 超时提示重试 |
| AI 服务未配置 | 后端返回 mock，前端标注"模拟结果" |

### 8.2 性能

- 问题库数据 Hive 缓存，避免每次请求
- 图片压缩后上传（maxWidth/Height: 1024）
- 3D 模型只加载一次
- 列表页用 ListView.builder 懒加载

### 8.3 免责声明

- 结果页底部固定显示
- severe 结果弹窗强制确认
- 个人中心"关于"页展示完整免责声明

---

## 9. 与后端 API 对应关系

| Flutter 操作 | 后端 API | 备注 |
|-------------|---------|------|
| 发送验证码 | POST /api/v1/auth/send-code | |
| 验证码登录 | POST /api/v1/auth/verify-login | 登录即注册 |
| 刷新 Token | POST /api/v1/auth/refresh | |
| 获取用户信息 | GET /api/v1/user/profile | |
| 更新用户信息 | PUT /api/v1/user/profile | |
| 问题列表 | GET /api/v1/posture/issues?category= | |
| 问题详情 | GET /api/v1/posture/issues/:id | |
| 提交自测 | POST /api/v1/posture/assess | |
| 提交照片分析 | POST /api/v1/posture/assess/photo | |
| 关联问题 | GET /api/v1/posture/issues/:id/related | |
| 历史记录 | GET /api/v1/posture/history | 支持 limit/offset |
| OSS 凭证 | POST /api/v1/upload/sts-token | |

---

## 10. 3D 模型策略

| 阶段 | 模型 | 来源 |
|------|------|------|
| MVP 开发 | Astronaut.glb 或任意免费 GLB | model_viewer_plus 示例 |
| MVP 发布 | MakeHuman 生成人体模型 | 自制 |
| 后续优化 | 按需求替换高质量模型 | 3D 素材站/定制 |

**热点标注实现：**
1. 首选方案：Flutter `Stack` + `Positioned` overlay 按钮，通过 JS channel 获取模型旋转角度动态调整位置
2. 如果实现复杂度过高：直接使用 2D 按钮列表（BodyRegionButton 组件）
3. 开发阶段可通过开发者选项切换 2D/3D 模式

---

## 11. 占位资源

| 资源 | 占位方式 | 后续替换 |
|------|---------|---------|
| 3D 人体模型 | Astronaut.glb | MakeHuman 人体模型 |
| 自测示意图 | 统一 placeholder.png | AI 生成统一风格示意图 |
| 站姿示例图 | placeholder.png | AI 生成正确站姿示意图 |

---

## 12. Review 问题修正记录

| # | 问题 | 修正方案 |
|---|------|---------|
| 1 | 后端缺少体态状态同步接口 | 客户端从评估历史聚合推导，不同步到后端 |
| 2 | 同步冲突策略未定义 | last-write-wins（按 updatedAt） |
| 3 | 3D 模型在模拟器性能差 | 开发者选项 2D/3D 切换 |
| 4 | Hive TypeId 未规划 | 统一分配 1-4 |
| 5 | AI 拍照无 API Key 时崩溃 | 后端 catch 返回 mock + 前端标注 |
| 6 | 结果页纠正建议数据来源不明 | 从 issue_provider 缓存读取 |
| 7 | 底部导航实现不明 | StatefulShellRoute.indexedStack |
| 8 | 信息采集无跳过选项 | 每步可跳过 + "稍后完善" |
| 9 | 3D 热点交互实现不明 | Flutter overlay + JS channel，复杂则降级 |
