# 体态分析 Flutter App 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建体态分析 App 前端（3D 导航、问题浏览、自测流程、AI 拍照分析、结果展示、历史记录）

**Architecture:** Flutter + Riverpod 状态管理 + GoRouter 路由 + Dio HTTP 客户端 + model_viewer_plus 3D 渲染，深色主题

**Tech Stack:** Flutter 3.x, Dart, Riverpod 2, GoRouter, Dio 5, model_viewer_plus, image_picker, flutter_secure_storage, intl

**工作目录:** `C:\Users\Lenovo\Desktop\develop\health\app`

---

## 文件结构总览

```
app/
├── pubspec.yaml
├── android/
│   └── app/src/main/AndroidManifest.xml   # 权限配置
├── ios/
│   └── Runner/Info.plist                   # 权限描述
├── lib/
│   ├── main.dart                           # 入口 + ProviderScope
│   ├── app.dart                            # MaterialApp.router + GoRouter + 主题
│   ├── core/
│   │   ├── constants.dart                  # API URL, 颜色, 分类映射
│   │   ├── theme.dart                      # 深色主题
│   │   ├── storage.dart                    # SecureStorage 封装
│   │   └── api_client.dart                 # Dio 单例 + JWT 拦截器
│   ├── models/
│   │   ├── user.dart                       # 用户模型
│   │   ├── issue.dart                      # 体态问题模型
│   │   ├── assessment.dart                 # 评估结果模型
│   │   └── token.dart                      # JWT Token 模型
│   ├── providers/
│   │   ├── auth_provider.dart              # 登录状态管理
│   │   ├── user_provider.dart              # 用户信息
│   │   ├── issue_provider.dart             # 问题库数据
│   │   └── assessment_provider.dart        # 评估提交/历史
│   ├── screens/
│   │   ├── auth/
│   │   │   ├── login_screen.dart
│   │   │   └── register_screen.dart
│   │   ├── onboarding/
│   │   │   └── onboarding_screen.dart
│   │   ├── home/
│   │   │   └── home_screen.dart            # 3D 模型导航
│   │   ├── issues/
│   │   │   ├── issue_list_screen.dart
│   │   │   └── issue_detail_screen.dart
│   │   ├── test/
│   │   │   ├── self_test_screen.dart
│   │   │   └── photo_test_screen.dart
│   │   ├── result/
│   │   │   └── result_screen.dart
│   │   ├── history/
│   │   │   └── history_screen.dart
│   │   └── profile/
│   │       └── profile_screen.dart
│   └── widgets/
│       ├── loading_overlay.dart
│       ├── issue_card.dart
│       ├── result_badge.dart
│       └── disclaimer_banner.dart
└── assets/
    ├── models/
    │   └── human_body.glb                  # 占位 3D 模型（后续替换 MakeHuman）
    └── images/
        └── tests/
            └── placeholder.png             # 占位示意图（后续替换 AI 生成图）
```

---

### Task 1: 项目初始化 + 依赖安装

**Files:**
- Create: `app/` (Flutter 项目)
- Modify: `app/pubspec.yaml`
- Modify: `app/android/app/src/main/AndroidManifest.xml`
- Modify: `app/ios/Runner/Info.plist`
- Create: `app/assets/models/human_body.glb` (占位)
- Create: `app/assets/images/tests/placeholder.png` (占位)

- [ ] **Step 1:** 运行 `flutter create --org com.health posture_app`，然后重命名为 `app`
- [ ] **Step 2:** 在 `pubspec.yaml` 添加依赖：

```yaml
dependencies:
  flutter:
    sdk: flutter
  flutter_riverpod: ^2.5.0
  go_router: ^14.0.0
  dio: ^5.4.0
  model_viewer_plus: ^1.10.0
  image_picker: ^1.1.0
  flutter_secure_storage: ^9.2.0
  intl: ^0.19.0

flutter:
  assets:
    - assets/models/
    - assets/images/tests/
```

- [ ] **Step 3:** 配置 Android 权限（AndroidManifest.xml）：
  - `android:usesCleartextTraffic="true"`（开发阶段 localhost）
  - 相机权限 `CAMERA`
  - 网络权限（默认已有）
  - `minSdkVersion` 改为 24

- [ ] **Step 4:** 配置 iOS 权限（Info.plist）：
  - `NSCameraUsageDescription`: "需要相机拍摄体态照片"
  - `NSPhotoLibraryUsageDescription`: "需要相册选择体态照片"
  - `io.flutter.embedded_views_preview`: YES

- [ ] **Step 5:** 放入占位 GLB 文件和占位 PNG 图片
- [ ] **Step 6:** 运行 `flutter pub get` 验证依赖安装成功
- [ ] **Step 7:** 提交

---

### Task 2: 核心层（主题、配置、API 客户端）

**Files:**
- Create: `lib/core/constants.dart`
- Create: `lib/core/theme.dart`
- Create: `lib/core/storage.dart`
- Create: `lib/core/api_client.dart`

- [ ] **Step 1:** 编写 `constants.dart`
  - `apiBaseUrl`（默认 `http://10.0.2.2:8000/api/v1`，Android 模拟器映射）
  - 颜色常量：背景 `#1A1A2E`、卡片 `#16213E`、主色 `#0F3460`、强调色 `#E94560`
  - 分类名映射：`head_neck→头颈部`、`shoulder_thorax→肩胸区` 等

- [ ] **Step 2:** 编写 `theme.dart`
  - 深色 ThemeData：scaffoldBackgroundColor、cardColor、appBarTheme、textTheme
  - 按钮样式（圆角、强调色）
  - 输入框样式（边框色、聚焦色）

- [ ] **Step 3:** 编写 `storage.dart`
  - 封装 FlutterSecureStorage 读写方法
  - `saveTokens(access, refresh)` / `getAccessToken()` / `getRefreshToken()` / `clearTokens()`

- [ ] **Step 4:** 编写 `api_client.dart`
  - Dio 单例，baseUrl 从 constants 读取
  - 请求拦截器：从 storage 读 token → 添加 `Authorization: Bearer xxx`
  - 响应拦截器：遇到 401 → 尝试用 refresh_token 刷新 → 失败则清除 token 并跳登录
  - 统一错误处理：DioException → 友好提示

- [ ] **Step 5:** 提交

---

### Task 3: 数据模型

**Files:**
- Create: `lib/models/user.dart`
- Create: `lib/models/issue.dart`
- Create: `lib/models/assessment.dart`
- Create: `lib/models/token.dart`

- [ ] **Step 1:** 编写 4 个模型类，每个包含：
  - 字段定义（与后端 JSON 一一对应）
  - `factory fromJson(Map<String, dynamic> json)`
  - `Map<String, dynamic> toJson()`

- [ ] **Step 2:** `issue.dart` 模型需包含嵌套结构：
  - `SelfTest`（name, steps, positiveSign, imageKey）
  - `Correction`（type, targetMuscle, method, freq）
  - `RelatedIssue`（id, nameCn, weight, relation）

- [ ] **Step 3:** 提交

---

### Task 4: 路由配置 + 认证守卫

**Files:**
- Create: `lib/app.dart`
- Modify: `lib/main.dart`

- [ ] **Step 1:** 编写 `app.dart`
  - GoRouter 实例，定义路由表：

```
/login
/register
/onboarding
/home
/issues/:category
/issues/:id/detail
/issues/:id/test
/issues/:id/photo
/issues/:id/result
/history
/profile
```

  - `redirect` 逻辑：检查 auth 状态 → 未登录重定向 /login → 已登录未填信息重定向 /onboarding

- [ ] **Step 2:** 编写 `main.dart`
  - `ProviderScope` 包裹 App
  - `runApp(ProviderScope(child: PostureApp()))`

- [ ] **Step 3:** 提交

---

### Task 5: Auth Provider + 登录/注册页面

**Files:**
- Create: `lib/providers/auth_provider.dart`
- Create: `lib/screens/auth/login_screen.dart`
- Create: `lib/screens/auth/register_screen.dart`

- [ ] **Step 1:** 编写 `auth_provider.dart`（Riverpod StateNotifier）
  - 状态：isLoggedIn, isLoading, error
  - 方法：
    - `sendCode(phone)` → POST /auth/send-code
    - `login(phone, code)` → POST /auth/login → saveTokens
    - `register(phone, code, password)` → POST /auth/register → saveTokens
    - `logout()` → clearTokens
    - `checkAuth()` → 从 storage 读 token 判断登录状态

- [ ] **Step 2:** 编写 `login_screen.dart`
  - 手机号输入（11位校验）
  - "发送验证码"按钮 + 60s 倒计时 Timer
  - 验证码输入（4-6位）
  - "登录"按钮
  - 底部："没有账号？去注册" 链接

- [ ] **Step 3:** 编写 `register_screen.dart`
  - 类似 login，多一个密码输入框
  - 注册成功 → 自动登录 → 跳转 onboarding

- [ ] **Step 4:** 提交

---

### Task 6: Onboarding 信息采集

**Files:**
- Create: `lib/screens/onboarding/onboarding_screen.dart`
- Create: `lib/providers/user_provider.dart`

- [ ] **Step 1:** 编写 `user_provider.dart`
  - `fetchProfile()` → GET /user/profile
  - `updateProfile(data)` → PUT /user/profile
  - 缓存用户信息

- [ ] **Step 2:** 编写 `onboarding_screen.dart`
  - PageView 分 4 步卡片：
    - 身高（Slider 100-220cm）
    - 体重（Slider 30-200kg）
    - 年龄（NumberPicker）
    - 性别（男/女选择按钮）
  - 进度指示器（4 dots）
  - 最后一步 "完成" 按钮 → updateProfile → 跳转 /home

- [ ] **Step 3:** 提交

---

### Task 7: 首页 3D 模型导航

**Files:**
- Create: `lib/screens/home/home_screen.dart`

- [ ] **Step 1:** 编写 `home_screen.dart`
  - `ModelViewer` widget 配置：
    - `src: 'assets/models/human_body.glb'`（占位模型）
    - `backgroundColor: Color(0xFF1A1A2E)`
    - `autoRotate: true`
    - `cameraControls: true`
  - 4 个 hotspot annotation（通过 model_viewer_plus 的 HTML slot）：
    - 头颈区 → 点击跳转 `/issues/head_neck`
    - 肩胸区 → 点击跳转 `/issues/shoulder_thorax`
    - 骨盆腰区 → 点击跳转 `/issues/pelvis_spine`
    - 下肢区 → 点击跳转 `/issues/lower_limb`
  - 底部独立按钮："综合评估" → `/issues/compound`

- [ ] **Step 2:** 如果 model_viewer_plus hotspot 交互复杂，备选方案：
  - 模型仅做展示（旋转缩放）
  - 下方放 4 个分类按钮卡片（带图标），点击跳转

- [ ] **Step 3:** 提交

---

### Task 8: Issue Provider + 问题列表

**Files:**
- Create: `lib/providers/issue_provider.dart`
- Create: `lib/screens/issues/issue_list_screen.dart`
- Create: `lib/widgets/issue_card.dart`

- [ ] **Step 1:** 编写 `issue_provider.dart`
  - `fetchIssues(category?)` → GET /posture/issues?category=xxx
  - 本地 Map 缓存（按 category 分 key），避免重复请求
  - `fetchIssueDetail(id)` → GET /posture/issues/:id

- [ ] **Step 2:** 编写 `issue_card.dart` 通用组件
  - 深色卡片，圆角
  - 标题：问题中文名
  - 副标题：俗称标签（Chip 样式）
  - 底部：一句话定义
  - 点击整张卡片可跳转

- [ ] **Step 3:** 编写 `issue_list_screen.dart`
  - AppBar 标题：分类中文名（从 constants 映射）
  - ListView.builder 渲染 IssueCard
  - 空状态提示

- [ ] **Step 4:** 提交

---

### Task 9: 问题详情页

**Files:**
- Create: `lib/screens/issues/issue_detail_screen.dart`

- [ ] **Step 1:** 编写 `issue_detail_screen.dart`
  - 从 issue_provider 获取详情数据
  - CustomScrollView 布局，各区段用 Card 包裹：
    - **定义区**：名称 + 英文名 + 俗称 Chip + 定义文本
    - **成因区**：按 type 分组的列表项
    - **纠正方法区**：按 拉伸/强化/习惯 三列 Tab 或折叠面板展示
    - **后果区**：短期/长期分栏
    - **红旗征区**（若有）：红色高亮 Card，醒目图标
  - 底部固定 SafeArea 按钮："开始自测" → 跳转 `/issues/:id/test`

- [ ] **Step 2:** 提交

---

### Task 10: 自测流程

**Files:**
- Create: `lib/screens/test/self_test_screen.dart`
- Create: `lib/providers/assessment_provider.dart`

- [ ] **Step 1:** 编写 `assessment_provider.dart`
  - `submitSelfAssess(issueId, testIndex, answer)` → POST /posture/assess
  - `submitPhotoAssess(issueId, photoKeys)` → POST /posture/assess/photo
  - `fetchHistory()` → GET /posture/history

- [ ] **Step 2:** 编写 `self_test_screen.dart`
  - 从问题详情中读取 self_tests 数组
  - PageView 逐步展示每个自测：
    - 顶部 60%：示意图（Image.asset，占位图 placeholder.png）
    - 中部：步骤列表（编号 + 文字）
    - 底部高亮文字："阳性征：{positive_sign}"
  - 最后一页：三选一按钮
    - "我有这个问题"（positive）→ 橙色
    - "我没有这个问题"（negative）→ 绿色
    - "不确定"（uncertain）→ 灰色
  - 选择后调用 assessment_provider.submitSelfAssess
  - 若选"不确定"→ 弹出 AlertDialog："要试试 AI 拍照分析吗？"
    - 是 → 跳转 `/issues/:id/photo`
    - 否 → 保存为 uncertain，跳转结果页

- [ ] **Step 3:** 提交

---

### Task 11: AI 拍照分析

**Files:**
- Create: `lib/screens/test/photo_test_screen.dart`

- [ ] **Step 1:** 编写 `photo_test_screen.dart`
  - **引导页**：
    - 提示文字（"请保持自然站姿，全身入镜"）
    - 示意图（正确站姿示例，占位图）
    - 两个按钮："拍照" / "从相册选择"
  - **上传流程**：
    1. image_picker 获取图片
    2. 调 POST /upload/sts-token 获取 OSS 临时凭证
    3. 用 Dio 直传图片到 OSS（multipart upload）
    4. 收集 object keys
    5. 调 assessment_provider.submitPhotoAssess
  - **等待状态**：
    - 全屏加载动画 + "AI 正在分析中..."
    - 超时 30s 提示"分析超时，请重试"
  - **完成**：跳转结果页

- [ ] **Step 2:** 提交

---

### Task 12: 结果页

**Files:**
- Create: `lib/screens/result/result_screen.dart`
- Create: `lib/widgets/result_badge.dart`
- Create: `lib/widgets/disclaimer_banner.dart`

- [ ] **Step 1:** 编写 `result_badge.dart`
  - 三种状态的圆形/圆角矩形标签：
    - normal → 绿色 + 勾号图标
    - moderate → 黄色 + 警告图标
    - severe → 红色 + 叉号图标

- [ ] **Step 2:** 编写 `disclaimer_banner.dart`
  - 半透明深色背景条
  - 文字："本内容仅供参考，不能替代专业医疗诊断。如有不适请及时就医。"

- [ ] **Step 3:** 编写 `result_screen.dart`
  - 接收参数：assessmentId, issueId, result, suggestion
  - **顶部大卡片**：
    - ResultBadge + 结果等级文字 + suggestion 文本
    - severe 时：自动弹出就医提示 AlertDialog（不可跳过）
  - **中部（仅 moderate 时显示）**：
    - "纠正建议" 标题
    - 从问题详情中读取 corrections 列表
    - 按 拉伸/强化/习惯 分组展示
  - **底部**：
    - "相关问题推荐" 标题
    - 横向滚动 ListView（调 GET /issues/:id/related）
    - 每张卡片：问题名 + 关联强度标签 + 关系描述
    - 点击跳转对应问题详情
  - DisclaimerBanner 固定在底部

- [ ] **Step 4:** 提交

---

### Task 13: 历史记录

**Files:**
- Create: `lib/screens/history/history_screen.dart`

- [ ] **Step 1:** 编写 `history_screen.dart`
  - 调用 assessment_provider.fetchHistory()
  - ListView 按日期分组展示
  - 每条记录卡片：
    - 左侧：ResultBadge（颜色标识）
    - 中间：问题名称 + 方法标签（"自测" / "AI分析"）
    - 右侧：日期
  - 空状态："暂无评估记录，去首页开始你的第一次体态分析吧"
  - 点击记录 → 跳转对应问题的结果页（复用 result_screen）

- [ ] **Step 2:** 提交

---

### Task 14: 个人中心

**Files:**
- Create: `lib/screens/profile/profile_screen.dart`

- [ ] **Step 1:** 编写 `profile_screen.dart`
  - 调用 user_provider.fetchProfile()
  - **顶部**：头像占位圆形 + 手机号（脱敏：138****8000）
  - **信息卡片**：
    - 身高 / 体重 / 年龄 / 性别
    - 每项可点击编辑（弹出输入框）
    - "保存" 按钮 → PUT /user/profile
  - **操作区**：
    - "评估历史" → 跳转 /history
    - "关于" → 版本号 + 免责声明
    - "退出登录" → auth_provider.logout() → 跳转 /login

- [ ] **Step 2:** 提交

---

## 执行顺序

```
阶段一：可登录骨架（T1 → T2 → T3 → T4 → T5 → T6）
  完成后：App 可以注册、登录、填写信息、进入首页空壳

阶段二：核心分析流程（T7 → T8 → T9 → T10 → T11 → T12）
  完成后：App 可以 3D 导航→选问题→自测→拍照→看结果

阶段三：收尾（T13 → T14）
  完成后：历史记录 + 个人中心，MVP 完整
```

---

## 占位资源说明

| 资源 | 占位方式 | 后续替换 |
|------|---------|---------|
| 3D 人体模型 (`human_body.glb`) | 使用 model_viewer_plus 自带的 Astronaut.glb 或任意免费 GLB | MakeHuman 生成的人体模型 |
| 自测示意图 (50张) | 统一使用 `placeholder.png` | AI 生成的统一风格示意图 |

---

## 与后端 API 对应关系

| Flutter 操作 | 后端 API |
|-------------|---------|
| 发送验证码 | POST /api/v1/auth/send-code |
| 注册 | POST /api/v1/auth/register |
| 登录 | POST /api/v1/auth/login |
| 刷新 Token | POST /api/v1/auth/refresh |
| 获取/更新个人信息 | GET/PUT /api/v1/user/profile |
| 问题列表 | GET /api/v1/posture/issues?category= |
| 问题详情 | GET /api/v1/posture/issues/:id |
| 提交自测 | POST /api/v1/posture/assess |
| 提交照片分析 | POST /api/v1/posture/assess/photo |
| 获取关联问题 | GET /api/v1/posture/issues/:id/related |
| 获取历史记录 | GET /api/v1/posture/history |
| 获取 OSS 上传凭证 | POST /api/v1/upload/sts-token |
