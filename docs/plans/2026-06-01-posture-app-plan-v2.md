# 体态分析 Flutter App 实现计划 v2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建体态分析 App Flutter 前端（验证码登录、3D 导航、问题浏览、自测流程、AI 拍照、结果展示、体态档案、历史记录）

**Architecture:** Flutter + Riverpod 2 + GoRouter 14 + Dio 5 + Hive（本地缓存）+ model_viewer_plus（3D），对齐已有 FastAPI 后端

**Tech Stack:** Flutter 3.x, Dart, Riverpod 2, GoRouter 14, Dio 5, Hive 2, model_viewer_plus 1.10, image_picker 1.1, flutter_secure_storage 9, intl 0.19, cached_network_image 3

**工作目录:** `C:\Users\Lenovo\Desktop\develop\health\app`

**后端 API 参考：**
- POST `/api/v1/auth/send-code` → `{phone}` → `{message}`
- POST `/api/v1/auth/verify-login` → `{phone, code}` → `{access_token, refresh_token, token_type, is_new_user}`
- POST `/api/v1/auth/refresh` → `{refresh_token}` → `{access_token, refresh_token, token_type}`
- GET `/api/v1/user/profile` → `{id, phone, nickname, height, weight, age, gender, membership_level, created_at}`
- PUT `/api/v1/user/profile` → `{nickname?, height?, weight?, age?, gender?}`
- GET `/api/v1/posture/issues?category=` → `[{id, name_cn, category, aliases, definition}]`
- GET `/api/v1/posture/issues/:id` → 完整问题详情
- GET `/api/v1/posture/issues/:id/related` → `[{id, name_cn, weight, relation}]`
- POST `/api/v1/posture/assess` → `{issue_id, test_index, answer}` → `{id, issue_id, result, suggestion}`
- POST `/api/v1/posture/assess/photo` → `{issue_id, photo_keys}` → 评估结果
- GET `/api/v1/posture/history?limit=&offset=` → `[{id, issue_id, issue_name, method, result, created_at}]`
- POST `/api/v1/upload/sts-token` → `{access_key_id, access_key_secret, security_token, bucket, region, endpoint, path_prefix}`

---

## Task 1: Flutter 项目初始化

**Files:**
- Create: `app/` (整个 Flutter 项目)

- [ ] **Step 1: 创建 Flutter 项目**

```bash
cd C:\Users\Lenovo\Desktop\develop\health && flutter create --org com.health posture_app
```
项目创建后目录名为 `posture_app`，暂不重命名，后续调整。

- [ ] **Step 2: 配置 pubspec.yaml**

`app/pubspec.yaml`，在 dependencies 下添加：

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

flutter:
  assets:
    - assets/models/
    - assets/images/tests/
```

- [ ] **Step 3: 配置 Android 权限**

`app/android/app/src/main/AndroidManifest.xml`，添加：

```xml
<!-- 在 application 标签上添加 -->
<uses-permission android:name="android.permission.INTERNET"/>
<uses-permission android:name="android.permission.CAMERA"/>

<!-- 在 application 标签添加 -->
android:usesCleartextTraffic="true"
```

修改 `app/android/app/build.gradle` 中 `minSdkVersion` 为 24。

- [ ] **Step 4: 配置 iOS 权限**

`app/ios/Runner/Info.plist`，在 `<dict>` 中添加：

```xml
<key>NSCameraUsageDescription</key>
<string>需要相机拍摄体态照片</string>
<key>NSPhotoLibraryUsageDescription</key>
<string>需要相册选择体态照片</string>
<key>io.flutter.embedded_views_preview</key>
<true/>
```

- [ ] **Step 5: 创建资产目录和占位文件**

```bash
mkdir -p app/assets/models app/assets/images/tests
```

创建一个 1x1 的占位 PNG 文件 `app/assets/images/tests/placeholder.png`，和拷贝 model_viewer_plus 的示例 GLB 到 `app/assets/models/astronaut.glb`。

- [ ] **Step 6: 安装依赖并验证**

```bash
cd app && flutter pub get
```

确认控制台无错误输出。

- [ ] **Step 7: 创建 lib 目录结构**

```bash
mkdir -p app/lib/core app/lib/models app/lib/providers app/lib/screens/auth app/lib/screens/onboarding app/lib/screens/home app/lib/screens/issues app/lib/screens/test app/lib/screens/result app/lib/screens/history app/lib/screens/profile app/lib/widgets app/lib/services
```

- [ ] **Step 8: 提交**

```bash
cd C:\Users\Lenovo\Desktop\develop\health
git add app/
git commit -m "feat: init Flutter project with dependencies and platform config"
```

---

## Task 2: 核心层（常量、主题、存储、API 客户端）

**Files:**
- Create: `app/lib/core/constants.dart`
- Create: `app/lib/core/theme.dart`
- Create: `app/lib/core/storage.dart`
- Create: `app/lib/core/api_client.dart`

- [ ] **Step 1: 编写 constants.dart**

```dart
// app/lib/core/constants.dart
class AppConstants {
  static const String apiBaseUrl = 'http://10.0.2.2:8000/api/v1';
  static const String appName = '体态分析';
  static const Duration httpTimeout = Duration(seconds: 30);

  // 色板
  static const int bgColor = 0xFF1A1A2E;
  static const int cardColor = 0xFF16213E;
  static const int primaryColor = 0xFF0F3460;
  static const int accentColor = 0xFFE94560;

  // 结果颜色
  static const int normalColor = 0xFF00C853;
  static const int moderateColor = 0xFFFFB300;
  static const int severeColor = 0xFFFF1744;

  // 分类映射
  static const Map<String, String> categoryNames = {
    'head_neck': '头颈部',
    'shoulder_thorax': '肩胸区',
    'pelvis_spine': '骨盆腰椎',
    'lower_limb': '下肢',
    'compound': '复合综合征',
  };

  // 分类与3D区域的对应关系
  static const Map<String, String> categoryRoutes = {
    'head_neck': '/issues/head_neck',
    'shoulder_thorax': '/issues/shoulder_thorax',
    'pelvis_spine': '/issues/pelvis_spine',
    'lower_limb': '/issues/lower_limb',
    'compound': '/issues/compound',
  };
}
```

- [ ] **Step 2: 编写 theme.dart**

```dart
// app/lib/core/theme.dart
import 'package:flutter/material.dart';
import 'constants.dart';

class AppTheme {
  static ThemeData get darkTheme => ThemeData(
    brightness: Brightness.dark,
    scaffoldBackgroundColor: const Color(AppConstants.bgColor),
    cardColor: const Color(AppConstants.cardColor),
    primaryColor: const Color(AppConstants.primaryColor),
    colorScheme: const ColorScheme.dark(
      primary: Color(AppConstants.primaryColor),
      secondary: Color(AppConstants.accentColor),
      surface: Color(AppConstants.cardColor),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: Color(AppConstants.cardColor),
      foregroundColor: Color(0xFFEAEAEA),
      elevation: 0,
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: const Color(AppConstants.accentColor),
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: const Color(AppConstants.cardColor),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: Color(0xFF0F3460)),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: Color(AppConstants.accentColor)),
      ),
    ),
    cardTheme: CardTheme(
      color: const Color(AppConstants.cardColor),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      elevation: 4,
    ),
  );
}
```

- [ ] **Step 3: 编写 storage.dart**

```dart
// app/lib/core/storage.dart
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AppStorage {
  static const _storage = FlutterSecureStorage();
  static const _accessTokenKey = 'access_token';
  static const _refreshTokenKey = 'refresh_token';

  static Future<void> saveTokens(String access, String refresh) async {
    await _storage.write(key: _accessTokenKey, value: access);
    await _storage.write(key: _refreshTokenKey, value: refresh);
  }

  static Future<String?> getAccessToken() =>
      _storage.read(key: _accessTokenKey);

  static Future<String?> getRefreshToken() =>
      _storage.read(key: _refreshTokenKey);

  static Future<void> clearTokens() async {
    await _storage.delete(key: _accessTokenKey);
    await _storage.delete(key: _refreshTokenKey);
  }

  static Future<bool> hasToken() async {
    final token = await getAccessToken();
    return token != null && token.isNotEmpty;
  }
}
```

- [ ] **Step 4: 编写 api_client.dart**

```dart
// app/lib/core/api_client.dart
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'constants.dart';
import 'storage.dart';

class ApiClient {
  late final Dio dio;

  ApiClient() {
    dio = Dio(BaseOptions(
      baseUrl: AppConstants.apiBaseUrl,
      connectTimeout: AppConstants.httpTimeout,
      receiveTimeout: AppConstants.httpTimeout,
      headers: {'Content-Type': 'application/json'},
    ));

    dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final token = await AppStorage.getAccessToken();
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        handler.next(options);
      },
      onError: (error, handler) async {
        if (error.response?.statusCode == 401) {
          final refreshToken = await AppStorage.getRefreshToken();
          if (refreshToken != null) {
            try {
              final resp = await Dio(BaseOptions(
                baseUrl: AppConstants.apiBaseUrl,
              )).post('/auth/refresh', data: {'refresh_token': refreshToken});
              final data = resp.data;
              await AppStorage.saveTokens(
                data['access_token'], data['refresh_token']);
              error.requestOptions.headers['Authorization'] =
                  'Bearer ${data['access_token']}';
              final retryResp = await Dio().fetch(error.requestOptions);
              return handler.resolve(retryResp);
            } catch (_) {
              await AppStorage.clearTokens();
            }
          }
        }
        handler.next(error);
      },
    ));
  }
}

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());
```

- [ ] **Step 5: 提交**

```bash
cd C:\Users\Lenovo\Desktop\develop\health && git add app/lib/core/ && git commit -m "feat: add core layer (constants, theme, storage, API client)"
```

---

## Task 3: 数据模型

**Files:**
- Create: `app/lib/models/token.dart`
- Create: `app/lib/models/user.dart`
- Create: `app/lib/models/issue.dart`
- Create: `app/lib/models/assessment.dart`
- Create: `app/lib/models/user_posture_state.dart`

- [ ] **Step 1: 编写 token.dart**

```dart
// app/lib/models/token.dart
class TokenResponse {
  final String accessToken;
  final String refreshToken;
  final String tokenType;
  final bool isNewUser;

  TokenResponse({
    required this.accessToken,
    required this.refreshToken,
    this.tokenType = 'bearer',
    this.isNewUser = false,
  });

  factory TokenResponse.fromJson(Map<String, dynamic> json) => TokenResponse(
    accessToken: json['access_token'] as String,
    refreshToken: json['refresh_token'] as String,
    tokenType: (json['token_type'] as String?) ?? 'bearer',
    isNewUser: (json['is_new_user'] as bool?) ?? false,
  );
}
```

- [ ] **Step 2: 编写 user.dart**

```dart
// app/lib/models/user.dart
class UserProfile {
  final String id;
  final String phone;
  final String? nickname;
  final double? height;
  final double? weight;
  final int? age;
  final String? gender;
  final String membershipLevel;
  final String? createdAt;

  UserProfile({
    required this.id,
    required this.phone,
    this.nickname,
    this.height,
    this.weight,
    this.age,
    this.gender,
    this.membershipLevel = 'free',
    this.createdAt,
  });

  factory UserProfile.fromJson(Map<String, dynamic> json) => UserProfile(
    id: json['id'] as String,
    phone: json['phone'] as String,
    nickname: json['nickname'] as String?,
    height: (json['height'] as num?)?.toDouble(),
    weight: (json['weight'] as num?)?.toDouble(),
    age: json['age'] as int?,
    gender: json['gender'] as String?,
    membershipLevel: (json['membership_level'] as String?) ?? 'free',
    createdAt: json['created_at'] as String?,
  );

  Map<String, dynamic> toJson() => {
    'nickname': nickname,
    'height': height,
    'weight': weight,
    'age': age,
    'gender': gender,
  };

  bool get hasProfile =>
      height != null && weight != null && age != null && gender != null;
}
```

- [ ] **Step 3: 编写 issue.dart**

```dart
// app/lib/models/issue.dart
class IssueSummary {
  final String id;
  final String nameCn;
  final String category;
  final List<String> aliases;
  final String definition;

  IssueSummary({
    required this.id,
    required this.nameCn,
    required this.category,
    required this.aliases,
    required this.definition,
  });

  factory IssueSummary.fromJson(Map<String, dynamic> json) => IssueSummary(
    id: json['id'] as String,
    nameCn: json['name_cn'] as String,
    category: json['category'] as String,
    aliases: List<String>.from(json['aliases'] as List),
    definition: json['definition'] as String,
  );
}

class IssueDetail {
  final String id;
  final String nameCn;
  final String nameEn;
  final String category;
  final List<String> aliases;
  final String definition;
  final List<String> severityLevels;
  final List<Map<String, dynamic>> causes;
  final List<SelfTest> selfTests;
  final List<Map<String, dynamic>> corrections;
  final List<Map<String, dynamic>> consequences;
  final List<String> redFlags;
  final List<RelatedIssueRef> relatedIssues;

  IssueDetail({
    required this.id,
    required this.nameCn,
    required this.nameEn,
    required this.category,
    required this.aliases,
    required this.definition,
    required this.severityLevels,
    required this.causes,
    required this.selfTests,
    required this.corrections,
    required this.consequences,
    required this.redFlags,
    required this.relatedIssues,
  });

  factory IssueDetail.fromJson(Map<String, dynamic> json) => IssueDetail(
    id: json['id'] as String,
    nameCn: json['name_cn'] as String,
    nameEn: (json['name_en'] as String?) ?? '',
    category: json['category'] as String,
    aliases: List<String>.from(json['aliases'] as List),
    definition: json['definition'] as String,
    severityLevels: List<String>.from(json['severity_levels'] as List),
    causes: List<Map<String, dynamic>>.from(json['causes'] as List),
    selfTests: (json['self_tests'] as List)
        .map((e) => SelfTest.fromJson(e as Map<String, dynamic>))
        .toList(),
    corrections: List<Map<String, dynamic>>.from(json['corrections'] as List),
    consequences:
        List<Map<String, dynamic>>.from(json['consequences'] as List),
    redFlags: List<String>.from(json['red_flags'] as List),
    relatedIssues: (json['related_issues'] as List)
        .map((e) => RelatedIssueRef.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

class SelfTest {
  final String name;
  final List<String> steps;
  final String positiveSign;
  final String imageKey;
  final String toolsNeeded;

  SelfTest({
    required this.name,
    required this.steps,
    required this.positiveSign,
    required this.imageKey,
    required this.toolsNeeded,
  });

  factory SelfTest.fromJson(Map<String, dynamic> json) => SelfTest(
    name: json['name'] as String,
    steps: List<String>.from(json['steps'] as List),
    positiveSign: json['positive_sign'] as String,
    imageKey: (json['image_key'] as String?) ?? '',
    toolsNeeded: (json['tools_needed'] as String?) ?? '',
  );
}

class RelatedIssueRef {
  final String id;
  final double weight;
  final String relation;

  RelatedIssueRef({
    required this.id,
    required this.weight,
    required this.relation,
  });

  factory RelatedIssueRef.fromJson(Map<String, dynamic> json) =>
      RelatedIssueRef(
        id: json['id'] as String,
        weight: (json['weight'] as num).toDouble(),
        relation: json['relation'] as String,
      );
}
```

- [ ] **Step 4: 编写 assessment.dart**

```dart
// app/lib/models/assessment.dart
class AssessmentRecord {
  final String id;
  final String issueId;
  final String issueName;
  final String method;
  final String result;
  final DateTime createdAt;

  AssessmentRecord({
    required this.id,
    required this.issueId,
    required this.issueName,
    required this.method,
    required this.result,
    required this.createdAt,
  });

  factory AssessmentRecord.fromJson(Map<String, dynamic> json) =>
      AssessmentRecord(
        id: json['id'] as String,
        issueId: json['issue_id'] as String,
        issueName: json['issue_name'] as String,
        method: json['method'] as String,
        result: json['result'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
      );
}

class SelfAssessResult {
  final String id;
  final String issueId;
  final String result;
  final String suggestion;

  SelfAssessResult({
    required this.id,
    required this.issueId,
    required this.result,
    required this.suggestion,
  });

  factory SelfAssessResult.fromJson(Map<String, dynamic> json) =>
      SelfAssessResult(
        id: json['id'] as String,
        issueId: json['issue_id'] as String,
        result: json['result'] as String,
        suggestion: json['suggestion'] as String,
      );
}
```

- [ ] **Step 5: 编写 user_posture_state.dart**

```dart
// app/lib/models/user_posture_state.dart
class UserPostureState {
  final String issueId;
  final String result;
  final String method;
  final DateTime updatedAt;
  bool synced;

  UserPostureState({
    required this.issueId,
    required this.result,
    required this.method,
    required this.updatedAt,
    this.synced = false,
  });

  Map<String, dynamic> toJson() => {
    'issueId': issueId,
    'result': result,
    'method': method,
    'updatedAt': updatedAt.toIso8601String(),
    'synced': synced,
  };

  factory UserPostureState.fromJson(Map<String, dynamic> json) =>
      UserPostureState(
        issueId: json['issueId'] as String,
        result: json['result'] as String,
        method: json['method'] as String,
        updatedAt: DateTime.parse(json['updatedAt'] as String),
        synced: (json['synced'] as bool?) ?? false,
      );
}
```

- [ ] **Step 6: 提交**

```bash
cd C:\Users\Lenovo\Desktop\develop\health && git add app/lib/models/ && git commit -m "feat: add data models (token, user, issue, assessment, posture_state)"
```

---

## Task 4: Auth Provider + 登录页面

**Files:**
- Create: `app/lib/providers/auth_provider.dart`
- Create: `app/lib/screens/auth/login_screen.dart`

- [ ] **Step 1: 编写 auth_provider.dart**

```dart
// app/lib/providers/auth_provider.dart
import 'dart:async';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../core/storage.dart';
import '../models/token.dart';

class AuthState {
  final bool isLoggedIn;
  final bool isLoading;
  final String? error;
  final bool isNewUser;
  final int countdown;

  const AuthState({
    this.isLoggedIn = false,
    this.isLoading = false,
    this.error,
    this.isNewUser = false,
    this.countdown = 0,
  });

  AuthState copyWith({
    bool? isLoggedIn,
    bool? isLoading,
    String? error,
    bool? isNewUser,
    int? countdown,
    bool clearError = false,
  }) =>
      AuthState(
        isLoggedIn: isLoggedIn ?? this.isLoggedIn,
        isLoading: isLoading ?? this.isLoading,
        error: clearError ? null : (error ?? this.error),
        isNewUser: isNewUser ?? this.isNewUser,
        countdown: countdown ?? this.countdown,
      );
}

class AuthNotifier extends StateNotifier<AuthState> {
  final ApiClient _api;
  Timer? _timer;

  AuthNotifier(this._api) : super(const AuthState());

  Future<void> checkAuth() async {
    final hasToken = await AppStorage.hasToken();
    state = state.copyWith(isLoggedIn: hasToken);
  }

  Future<bool> sendCode(String phone) async {
    try {
      state = state.copyWith(isLoading: true, clearError: true);
      await _api.dio.post('/auth/send-code', data: {'phone': phone});
      _startCountdown();
      state = state.copyWith(isLoading: false);
      return true;
    } on DioException catch (e) {
      final msg = e.response?.data?['detail'] ?? '发送验证码失败';
      state = state.copyWith(isLoading: false, error: msg);
      return false;
    }
  }

  Future<bool> login(String phone, String code) async {
    try {
      state = state.copyWith(isLoading: true, clearError: true);
      final resp = await _api.dio.post('/auth/verify-login', data: {
        'phone': phone,
        'code': code,
      });
      final token = TokenResponse.fromJson(resp.data as Map<String, dynamic>);
      await AppStorage.saveTokens(token.accessToken, token.refreshToken);
      state = state.copyWith(
        isLoading: false,
        isLoggedIn: true,
        isNewUser: token.isNewUser,
      );
      return true;
    } on DioException catch (e) {
      final msg = e.response?.data?['detail'] ?? '登录失败';
      state = state.copyWith(isLoading: false, error: msg);
      return false;
    }
  }

  Future<void> logout() async {
    await AppStorage.clearTokens();
    state = const AuthState();
  }

  void _startCountdown() {
    state = state.copyWith(countdown: 60);
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (state.countdown <= 1) {
        _timer?.cancel();
        state = state.copyWith(countdown: 0);
      } else {
        state = state.copyWith(countdown: state.countdown - 1);
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  final api = ref.read(apiClientProvider);
  return AuthNotifier(api);
});
```

- [ ] **Step 2: 编写 login_screen.dart**

```dart
// app/lib/screens/auth/login_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../providers/auth_provider.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _phoneController = TextEditingController();
  final _codeController = TextEditingController();

  @override
  void dispose() {
    _phoneController.dispose();
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _sendCode() async {
    final phone = _phoneController.text.trim();
    if (phone.length != 11 || !RegExp(r'^1[3-9]\d{9}$').hasMatch(phone)) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('请输入正确的手机号')));
      return;
    }
    await ref.read(authProvider.notifier).sendCode(phone);
  }

  Future<void> _login() async {
    final phone = _phoneController.text.trim();
    final code = _codeController.text.trim();
    if (code.length < 4) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('请输入验证码')));
      return;
    }
    final ok = await ref.read(authProvider.notifier).login(phone, code);
    if (ok && mounted) {
      final state = ref.read(authProvider);
      if (state.isNewUser) {
        context.go('/onboarding');
      } else {
        context.go('/');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(authProvider);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.accessibility_new,
                    size: 80, color: Color(0xFFE94560)),
                const SizedBox(height: 16),
                const Text('体态分析',
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                const Text('了解你的身体，科学改善体态',
                    style: TextStyle(color: Color(0xFF8892B0))),
                const SizedBox(height: 48),
                TextField(
                  controller: _phoneController,
                  keyboardType: TextInputType.phone,
                  maxLength: 11,
                  decoration:
                      const InputDecoration(labelText: '手机号', counterText: ''),
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _codeController,
                        keyboardType: TextInputType.number,
                        maxLength: 6,
                        decoration: const InputDecoration(
                            labelText: '验证码', counterText: ''),
                      ),
                    ),
                    const SizedBox(width: 12),
                    SizedBox(
                      width: 120,
                      height: 48,
                      child: ElevatedButton(
                        onPressed:
                            state.countdown > 0 || state.isLoading ? null : _sendCode,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF0F3460),
                        ),
                        child: Text(
                          state.countdown > 0
                              ? '${state.countdown}s'
                              : '发送验证码',
                          style: const TextStyle(fontSize: 13),
                        ),
                      ),
                    ),
                  ],
                ),
                if (state.error != null) ...[
                  const SizedBox(height: 12),
                  Text(state.error!,
                      style: const TextStyle(color: Color(0xFFFF1744))),
                ],
                const SizedBox(height: 24),
                SizedBox(
                  width: double.infinity,
                  height: 52,
                  child: ElevatedButton(
                    onPressed: state.isLoading ? null : _login,
                    child: state.isLoading
                        ? const SizedBox(
                            width: 24,
                            height: 24,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : const Text('登录', style: TextStyle(fontSize: 18)),
                  ),
                ),
                const SizedBox(height: 24),
                const Text('首次验证将自动注册账号',
                    style: TextStyle(color: Color(0xFF8892B0), fontSize: 13)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
```

- [ ] **Step 3: 提交**

```bash
cd C:\Users\Lenovo\Desktop\develop\health && git add app/lib/providers/ app/lib/screens/ && git commit -m "feat: add auth provider and login screen"
```

---

## Task 5: User Provider + 信息采集页

**Files:**
- Create: `app/lib/providers/user_provider.dart`
- Create: `app/lib/screens/onboarding/onboarding_screen.dart`

- [ ] **Step 1: 编写 user_provider.dart**

```dart
// app/lib/providers/user_provider.dart
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../models/user.dart';

class UserState {
  final UserProfile? profile;
  final bool isLoading;
  final String? error;

  const UserState({this.profile, this.isLoading = false, this.error});

  UserState copyWith({UserProfile? profile, bool? isLoading, String? error, bool clearError = false}) =>
      UserState(profile: profile ?? this.profile, isLoading: isLoading ?? this.isLoading, error: clearError ? null : (error ?? this.error));
}

class UserNotifier extends StateNotifier<UserState> {
  final ApiClient _api;

  UserNotifier(this._api) : super(const UserState());

  Future<void> fetchProfile() async {
    try {
      state = state.copyWith(isLoading: true);
      final resp = await _api.dio.get('/user/profile');
      final profile = UserProfile.fromJson(resp.data as Map<String, dynamic>);
      state = state.copyWith(profile: profile, isLoading: false);
    } on DioException catch (e) {
      final msg = e.response?.data?['detail'] ?? '获取用户信息失败';
      state = state.copyWith(isLoading: false, error: msg);
    }
  }

  Future<bool> updateProfile({
    String? nickname,
    double? height,
    double? weight,
    int? age,
    String? gender,
  }) async {
    try {
      state = state.copyWith(isLoading: true);
      final data = <String, dynamic>{};
      if (nickname != null) data['nickname'] = nickname;
      if (height != null) data['height'] = height;
      if (weight != null) data['weight'] = weight;
      if (age != null) data['age'] = age;
      if (gender != null) data['gender'] = gender;
      final resp = await _api.dio.put('/user/profile', data: data);
      final profile = UserProfile.fromJson(resp.data as Map<String, dynamic>);
      state = state.copyWith(profile: profile, isLoading: false);
      return true;
    } on DioException catch (e) {
      final msg = e.response?.data?['detail'] ?? '更新失败';
      state = state.copyWith(isLoading: false, error: msg);
      return false;
    }
  }
}

final userProvider = StateNotifierProvider<UserNotifier, UserState>((ref) {
  final api = ref.read(apiClientProvider);
  return UserNotifier(api);
});
```

- [ ] **Step 2: 编写 onboarding_screen.dart**

```dart
// app/lib/screens/onboarding/onboarding_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../providers/user_provider.dart';

class OnboardingScreen extends ConsumerStatefulWidget {
  const OnboardingScreen({super.key});
  @override
  ConsumerState<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends ConsumerState<OnboardingScreen> {
  final _pageController = PageController();
  int _currentPage = 0;
  double _height = 170;
  double _weight = 65;
  int _age = 25;
  String? _gender;
  String? _nickname;

  void _next() {
    if (_currentPage < 3) {
      _pageController.nextPage(duration: const Duration(milliseconds: 300), curve: Curves.easeInOut);
    }
  }

  Future<void> _finish() async {
    final ok = await ref.read(userProvider.notifier).updateProfile(
      height: _height, weight: _weight, age: _age, gender: _gender, nickname: _nickname);
    if (ok && mounted) context.go('/');
  }

  Future<void> _skip() async {
    if (mounted) context.go('/');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            LinearProgressIndicator(value: (_currentPage + 1) / 5),
            Expanded(
              child: PageView(
                controller: _pageController,
                onPageChanged: (i) => setState(() => _currentPage = i),
                children: [
                  _buildSliderPage('你的身高？', 'cm', _height, 100, 220,
                      (v) => _height = v, Icons.height),
                  _buildSliderPage('你的体重？', 'kg', _weight, 30, 200,
                      (v) => _weight = v, Icons.monitor_weight_outlined),
                  _buildNumberPage('你的年龄？', _age, 13, 120,
                      (v) => _age = v),
                  _buildGenderPage(),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(24),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  TextButton(onPressed: _skip, child: const Text('稍后完善')),
                  Row(
                    children: List.generate(5, (i) => Container(
                      margin: const EdgeInsets.symmetric(horizontal: 4),
                      width: 8, height: 8,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: i == _currentPage ? const Color(0xFFE94560) : const Color(0xFF0F3460),
                      ),
                    )),
                  ),
                  _currentPage < 3
                      ? ElevatedButton(onPressed: _next, child: const Text('下一步'))
                      : ElevatedButton(onPressed: _finish, child: const Text('完成')),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSliderPage(String title, String unit, double value, double min,
      double max, ValueChanged<double> onChanged, IconData icon) {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 64, color: const Color(0xFFE94560)),
          const SizedBox(height: 24),
          Text(title, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          Text('${value.toInt()} $unit',
              style: const TextStyle(fontSize: 32, color: Color(0xFFE94560))),
          Slider(value: value, min: min, max: max, onChanged: onChanged),
          Text(
            unit == 'cm' ? '范围: ${min.toInt()}-${max.toInt()}cm' : '范围: ${min.toInt()}-${max.toInt()}kg',
            style: const TextStyle(color: Color(0xFF8892B0)),
          ),
        ],
      ),
    );
  }

  Widget _buildNumberPage(String title, int value, int min, int max, ValueChanged<int> onChanged) {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.calendar_today, size: 64, color: Color(0xFFE94560)),
          const SizedBox(height: 24),
          Text(title, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          Text('$value 岁', style: const TextStyle(fontSize: 32, color: Color(0xFFE94560))),
          Slider(value: value.toDouble(), min: min.toDouble(), max: max.toDouble(),
              onChanged: (v) => onChanged(v.toInt())),
        ],
      ),
    );
  }

  Widget _buildGenderPage() {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.person, size: 64, color: Color(0xFFE94560)),
          const SizedBox(height: 24),
          const Text('你的性别？', style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
          const SizedBox(height: 32),
          Row(
            children: [
              Expanded(
                child: _genderCard('男', 'male', Icons.male),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: _genderCard('女', 'female', Icons.female),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _genderCard(String label, String value, IconData icon) {
    final selected = _gender == value;
    return GestureDetector(
      onTap: () => setState(() => _gender = value),
      child: Container(
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: selected ? const Color(0xFFE94560) : const Color(0xFF16213E),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: selected ? const Color(0xFFE94560) : const Color(0xFF0F3460), width: 2),
        ),
        child: Column(
          children: [
            Icon(icon, size: 48, color: Colors.white),
            const SizedBox(height: 8),
            Text(label, style: const TextStyle(fontSize: 20)),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }
}
```

- [ ] **Step 3: 提交**

```bash
cd C:\Users\Lenovo\Desktop\develop\health && git add app/lib/providers/user_provider.dart app/lib/screens/onboarding/ && git commit -m "feat: add user provider and onboarding screen"
```

---

## Task 6: 路由 + 底部导航 + 入口

**Files:**
- Create: `app/lib/app.dart`
- Modify: `app/lib/main.dart`

- [ ] **Step 1: 编写 main.dart**

```dart
// app/lib/main.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'app.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Hive 初始化将在 Task 15 的 sync 服务中添加
  runApp(const ProviderScope(child: PostureApp()));
}
```

- [ ] **Step 2: 编写 app.dart**

```dart
// app/lib/app.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'core/theme.dart';
import 'providers/auth_provider.dart';
import 'providers/user_provider.dart';
import 'screens/auth/login_screen.dart';
import 'screens/onboarding/onboarding_screen.dart';
import 'screens/home/home_screen.dart';
import 'screens/issues/issue_list_screen.dart';
import 'screens/issues/issue_detail_screen.dart';
import 'screens/test/self_test_screen.dart';
import 'screens/test/photo_test_screen.dart';
import 'screens/result/result_screen.dart';
import 'screens/history/history_screen.dart';
import 'screens/profile/profile_screen.dart';
import 'screens/profile/posture_profile_screen.dart';

final _rootNavigatorKey = GlobalKey<NavigatorState>();
final _shellNavigatorKey = GlobalKey<NavigatorState>();

class PostureApp extends ConsumerWidget {
  const PostureApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authProvider);
    final userState = ref.watch(userProvider);

    final router = GoRouter(
      navigatorKey: _rootNavigatorKey,
      initialLocation: '/login',
      redirect: (context, state) {
        final onLogin = state.matchedLocation == '/login';
        final onOnboarding = state.matchedLocation == '/onboarding';
        if (!authState.isLoggedIn && !onLogin) return '/login';
        if (authState.isLoggedIn && onLogin) return '/';
        if (authState.isLoggedIn && !userState.profile?.hasProfile == true && !onOnboarding) {
          return '/onboarding';
        }
        return null;
      },
      routes: [
        GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),
        GoRoute(path: '/onboarding', builder: (_, __) => const OnboardingScreen()),
        StatefulShellRoute.indexedStack(
          builder: (_, __, navigationShell) =>
              AppShell(navigationShell: navigationShell),
          branches: [
            StatefulShellBranch(routes: [
              GoRoute(path: '/', builder: (_, __) => const HomeScreen()),
            ]),
            StatefulShellBranch(routes: [
              GoRoute(path: '/history', builder: (_, __) => const HistoryScreen()),
            ]),
            StatefulShellBranch(routes: [
              GoRoute(
                path: '/profile',
                builder: (_, __) => const ProfileScreen(),
                routes: [
                  GoRoute(
                    path: 'posture',
                    builder: (_, __) => const PostureProfileScreen(),
                  ),
                ],
              ),
            ]),
          ],
        ),
        GoRoute(
          path: '/issues/:category',
          builder: (_, state) =>
              IssueListScreen(category: state.pathParameters['category']!),
        ),
        GoRoute(
          path: '/issues/:id/detail',
          builder: (_, state) =>
              IssueDetailScreen(issueId: state.pathParameters['id']!),
        ),
        GoRoute(
          path: '/issues/:id/test',
          builder: (_, state) =>
              SelfTestScreen(issueId: state.pathParameters['id']!),
        ),
        GoRoute(
          path: '/issues/:id/photo',
          builder: (_, state) =>
              PhotoTestScreen(issueId: state.pathParameters['id']!),
        ),
        GoRoute(
          path: '/issues/:id/result',
          builder: (_, state) {
            final extra = state.extra as Map<String, dynamic>;
            return ResultScreen(
              issueId: state.pathParameters['id']!,
              assessmentId: extra['assessmentId'] as String,
              result: extra['result'] as String,
              suggestion: extra['suggestion'] as String,
            );
          },
        ),
      ],
    );

    return MaterialApp.router(
      title: '体态分析',
      theme: AppTheme.darkTheme,
      routerConfig: router,
      debugShowCheckedModeBanner: false,
    );
  }
}

class AppShell extends StatelessWidget {
  final StatefulNavigationShell navigationShell;
  const AppShell({super.key, required this.navigationShell});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: NavigationBar(
        selectedIndex: navigationShell.currentIndex,
        onDestinationSelected: (index) {
          navigationShell.goBranch(index, initialLocation: index == navigationShell.currentIndex);
        },
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: '首页'),
          NavigationDestination(icon: Icon(Icons.history_outlined), selectedIcon: Icon(Icons.history), label: '历史'),
          NavigationDestination(icon: Icon(Icons.person_outlined), selectedIcon: Icon(Icons.person), label: '我的'),
        ],
      ),
    );
  }
}
```

- [ ] **Step 3: 提交**

```bash
cd C:\Users\Lenovo\Desktop\develop\health && git add app/lib/main.dart app/lib/app.dart && git commit -m "feat: add router, bottom nav, and app shell"
```

---

## Task 7: 首页（3D 模型 + 降级方案 + 体态档案入口）

**Files:**
- Create: `app/lib/widgets/body_region_button.dart`
- Create: `app/lib/screens/home/home_screen.dart`

- [ ] **Step 1: 编写 body_region_button.dart**

```dart
// app/lib/widgets/body_region_button.dart
import 'package:flutter/material.dart';
import '../core/constants.dart';

class BodyRegionButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final VoidCallback onTap;

  const BodyRegionButton({
    super.key,
    required this.label,
    required this.icon,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: const Color(AppConstants.cardColor),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: const Color(0xFF0F3460), width: 1),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 36, color: const Color(AppConstants.accentColor)),
            const SizedBox(height: 8),
            Text(label, style: const TextStyle(fontSize: 14, color: Color(0xFFEAEAEA))),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 2: 编写 home_screen.dart**

```dart
// app/lib/screens/home/home_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:model_viewer_plus/model_viewer_plus.dart';
import '../../core/constants.dart';
import '../../providers/posture_state_provider.dart';
import '../../widgets/body_region_button.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final postureStates = ref.watch(postureStateProvider);
    final assessedCount = postureStates.values.length;
    final problemCount = postureStates.values
        .where((s) => s.result == 'moderate' || s.result == 'severe')
        .length;

    return Scaffold(
      appBar: AppBar(title: const Text(AppConstants.appName), centerTitle: true),
      body: Column(
        children: [
          // 3D 模型区域
          Expanded(
            flex: 3,
            child: _buildModelViewer(),
          ),
          // 分类导航（2D降级/热点备选）
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                BodyRegionButton(label: '头颈部', icon: Icons.face, onTap: () => context.push('/issues/head_neck')),
                BodyRegionButton(label: '肩胸部', icon: Icons.accessibility_new, onTap: () => context.push('/issues/shoulder_thorax')),
                BodyRegionButton(label: '骨盆腰', icon: Icons.charging_station, onTap: () => context.push('/issues/pelvis_spine')),
                BodyRegionButton(label: '下肢', icon: Icons.directions_walk, onTap: () => context.push('/issues/lower_limb')),
              ],
            ),
          ),
          // 综合评估按钮
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () => context.push('/issues/compound'),
                icon: const Icon(Icons.auto_awesome),
                label: const Text('综合评估'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: const Color(AppConstants.accentColor),
                  side: const BorderSide(color: Color(AppConstants.accentColor)),
                  padding: const EdgeInsets.symmetric(vertical: 12),
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
          // 体态档案入口
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: GestureDetector(
              onTap: () => context.push('/profile/posture'),
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    children: [
                      const Icon(Icons.assignment, color: Color(AppConstants.accentColor)),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('我的体态档案', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                            Text('已评估 $assessedCount/26 项，$problemCount 项需关注',
                                style: const TextStyle(color: Color(0xFF8892B0), fontSize: 13)),
                          ],
                        ),
                      ),
                      const Icon(Icons.chevron_right, color: Color(0xFF8892B0)),
                    ],
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }

  Widget _buildModelViewer() {
    try {
      return ModelViewer(
        src: 'assets/models/astronaut.glb',
        alt: '3D人体模型',
        autoRotate: true,
        cameraControls: true,
        backgroundColor: const Color(AppConstants.bgColor),
      );
    } catch (_) {
      return _buildFallback();
    }
  }

  Widget _buildFallback() {
    return const Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.accessibility_new, size: 80, color: Color(0xFF0F3460)),
          SizedBox(height: 12),
          Text('3D 模型加载中...', style: TextStyle(color: Color(0xFF8892B0))),
          Text('请使用上方的分类按钮导航', style: TextStyle(color: Color(0xFF8892B0), fontSize: 13)),
        ],
      ),
    );
  }
}
```

- [ ] **Step 3: 提交**

```bash
cd C:\Users\Lenovo\Desktop\develop\health && git add app/lib/screens/home/ app/lib/widgets/ && git commit -m "feat: add home screen with 3D model and 2D fallback"
```

---

## Task 8: Issue Provider + 问题列表

**Files:**
- Create: `app/lib/providers/issue_provider.dart`
- Create: `app/lib/screens/issues/issue_list_screen.dart`
- Create: `app/lib/widgets/issue_card.dart`

- [ ] **Step 1: 编写 issue_provider.dart**

```dart
// app/lib/providers/issue_provider.dart
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../models/issue.dart';

class IssueState {
  final Map<String, List<IssueSummary>> issuesByCategory;
  final IssueDetail? currentDetail;
  final bool isLoading;
  final String? error;

  const IssueState({
    this.issuesByCategory = const {},
    this.currentDetail,
    this.isLoading = false,
    this.error,
  });

  IssueState copyWith({
    Map<String, List<IssueSummary>>? issuesByCategory,
    IssueDetail? currentDetail,
    bool? isLoading,
    String? error,
    bool clearError = false,
  }) =>
      IssueState(
        issuesByCategory: issuesByCategory ?? this.issuesByCategory,
        currentDetail: currentDetail ?? this.currentDetail,
        isLoading: isLoading ?? this.isLoading,
        error: clearError ? null : (error ?? this.error),
      );
}

class IssueNotifier extends StateNotifier<IssueState> {
  final ApiClient _api;

  IssueNotifier(this._api) : super(const IssueState());

  // 获取分类问题列表，缓存到 Map
  Future<void> fetchIssues(String? category) async {
    try {
      state = state.copyWith(isLoading: true, clearError: true);
      final queryParams = <String, dynamic>{};
      if (category != null) queryParams['category'] = category;
      final resp = await _api.dio.get('/posture/issues', queryParameters: queryParams.isEmpty ? null : queryParams);
      final list = (resp.data as List)
          .map((e) => IssueSummary.fromJson(e as Map<String, dynamic>))
          .toList();
      final key = category ?? 'all';
      final newMap = Map<String, List<IssueSummary>>.from(state.issuesByCategory);
      newMap[key] = list;
      state = state.copyWith(issuesByCategory: newMap, isLoading: false);
    } on DioException catch (e) {
      state = state.copyWith(
          isLoading: false,
          error: e.response?.data?['detail'] ?? '加载失败');
    }
  }

  Future<void> fetchDetail(String issueId) async {
    try {
      state = state.copyWith(isLoading: true, clearError: true);
      final resp = await _api.dio.get('/posture/issues/$issueId');
      final detail = IssueDetail.fromJson(resp.data as Map<String, dynamic>);
      state = state.copyWith(currentDetail: detail, isLoading: false);
    } on DioException catch (e) {
      state = state.copyWith(
          isLoading: false,
          error: e.response?.data?['detail'] ?? '加载失败');
    }
  }
}

final issueProvider = StateNotifierProvider<IssueNotifier, IssueState>((ref) {
  final api = ref.read(apiClientProvider);
  return IssueNotifier(api);
});
```

- [ ] **Step 2: 编写 issue_card.dart**

```dart
// app/lib/widgets/issue_card.dart
import 'package:flutter/material.dart';
import '../core/constants.dart';
import '../models/issue.dart';

class IssueCard extends StatelessWidget {
  final IssueSummary issue;
  final String? result;
  final VoidCallback onTap;

  const IssueCard({
    super.key,
    required this.issue,
    this.result,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(issue.nameCn,
                            style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
                        const SizedBox(width: 8),
                        if (result != null) _resultBadge(result!),
                      ],
                    ),
                    if (issue.aliases.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Wrap(
                        spacing: 6,
                        children: issue.aliases
                            .map((a) => Chip(
                                  label: Text(a, style: const TextStyle(fontSize: 11)),
                                  padding: EdgeInsets.zero,
                                  materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                  visualDensity: VisualDensity.compact,
                                ))
                            .toList(),
                      ),
                    ],
                    const SizedBox(height: 8),
                    Text(issue.definition,
                        style: const TextStyle(color: Color(0xFF8892B0), fontSize: 13),
                        maxLines: 2, overflow: TextOverflow.ellipsis),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: Color(0xFF8892B0)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _resultBadge(String r) {
    final colors = {
      'normal': AppConstants.normalColor,
      'moderate': AppConstants.moderateColor,
      'severe': AppConstants.severeColor,
    };
    final labels = {'normal': '正常', 'moderate': '需关注', 'severe': '严重'};
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: Color(colors[r] ?? AppConstants.primaryColor).withOpacity(0.2),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(labels[r] ?? r,
          style: TextStyle(color: Color(colors[r] ?? AppConstants.primaryColor), fontSize: 11)),
    );
  }
}
```

- [ ] **Step 3: 编写 issue_list_screen.dart**

```dart
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
    Future.microtask(() =>
        ref.read(issueProvider.notifier).fetchIssues(widget.category));
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
      body: issueState.isLoading
          ? const Center(child: CircularProgressIndicator())
          : issues.isEmpty
              ? const Center(
                  child: Text('该分类暂无问题', style: TextStyle(color: Color(0xFF8892B0))))
              : ListView.builder(
                  itemCount: issues.length,
                  itemBuilder: (_, i) {
                    final issue = issues[i];
                    final state = postureStates[issue.id];
                    return IssueCard(
                      issue: issue,
                      result: state?.result,
                      onTap: () => context.push('/issues/${issue.id}/detail'),
                    );
                  },
                ),
    );
  }
}
```

- [ ] **Step 4: 提交**

```bash
cd C:\Users\Lenovo\Desktop\develop\health && git add app/lib/providers/issue_provider.dart app/lib/screens/issues/issue_list_screen.dart app/lib/widgets/issue_card.dart && git commit -m "feat: add issue provider, list screen, and issue card widget"
```

---

## Task 9: 问题详情页

**Files:**
- Create: `app/lib/screens/issues/issue_detail_screen.dart`

- [ ] **Step 1: 编写 issue_detail_screen.dart**

```dart
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
    Future.microtask(() =>
        ref.read(issueProvider.notifier).fetchDetail(widget.issueId));
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(issueProvider);
    final detail = state.currentDetail;

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
          // 定义区
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
          // 成因
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
                            child: Text(c['type'] as String,
                                style: const TextStyle(fontSize: 11, color: Colors.white)),
                          ),
                          Expanded(child: Text(c['desc'] as String, style: const TextStyle(height: 1.4))),
                        ],
                      ),
                    )),
                  ],
                ),
              ),
            ),
          ),
          // 纠正方法
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
                          Icon(c['type'] == '拉伸' ? Icons.fitness_center : c['type'] == '强化' ? Icons.trending_up : Icons.lightbulb_outline,
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
          // 后果
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
                          Text('${c['timeframe']}：',
                              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                          Expanded(child: Text(c['desc'] as String, style: const TextStyle(fontSize: 14))),
                        ],
                      ),
                    )),
                  ],
                ),
              ),
            ),
          ),
          // 红旗征
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
              onPressed: () => context.push('/issues/${detail.id}/test'),
              child: const Text('开始自测', style: TextStyle(fontSize: 18)),
            ),
          ),
        ),
      ),
    );
  }
}
```

- [ ] **Step 2: 提交**

```bash
cd C:\Users\Lenovo\Desktop\develop\health && git add app/lib/screens/issues/issue_detail_screen.dart && git commit -m "feat: add issue detail screen"
```

---

## Task 10: Assessment Provider + 自测页

**Files:**
- Create: `app/lib/providers/assessment_provider.dart`
- Create: `app/lib/providers/posture_state_provider.dart`
- Create: `app/lib/screens/test/self_test_screen.dart`

- [ ] **Step 1: 编写 assessment_provider.dart**

```dart
// app/lib/providers/assessment_provider.dart
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../models/assessment.dart';

class AssessmentState {
  final SelfAssessResult? currentResult;
  final List<AssessmentRecord> history;
  final bool isLoading;
  final String? error;

  const AssessmentState({
    this.currentResult,
    this.history = const [],
    this.isLoading = false,
    this.error,
  });

  AssessmentState copyWith({
    SelfAssessResult? currentResult,
    List<AssessmentRecord>? history,
    bool? isLoading,
    String? error,
  }) =>
      AssessmentState(
        currentResult: currentResult ?? this.currentResult,
        history: history ?? this.history,
        isLoading: isLoading ?? this.isLoading,
        error: error ?? this.error,
      );
}

class AssessmentNotifier extends StateNotifier<AssessmentState> {
  final ApiClient _api;

  AssessmentNotifier(this._api) : super(const AssessmentState());

  Future<SelfAssessResult?> submitSelfAssess(String issueId, int testIndex, String answer) async {
    try {
      state = state.copyWith(isLoading: true);
      final resp = await _api.dio.post('/posture/assess', data: {
        'issue_id': issueId,
        'test_index': testIndex,
        'answer': answer,
      });
      final result = SelfAssessResult.fromJson(resp.data as Map<String, dynamic>);
      state = state.copyWith(currentResult: result, isLoading: false);
      return result;
    } on DioException catch (e) {
      state = state.copyWith(isLoading: false, error: e.response?.data?['detail'] ?? '提交失败');
      return null;
    }
  }

  Future<Map<String, dynamic>?> submitPhotoAssess(String issueId, List<String> photoKeys) async {
    try {
      state = state.copyWith(isLoading: true);
      final resp = await _api.dio.post('/posture/assess/photo', data: {
        'issue_id': issueId,
        'photo_keys': photoKeys,
      });
      state = state.copyWith(currentResult: null, isLoading: false);
      return resp.data as Map<String, dynamic>;
    } on DioException catch (e) {
      state = state.copyWith(isLoading: false, error: e.response?.data?['detail'] ?? '分析失败');
      return null;
    }
  }

  Future<void> fetchHistory({int limit = 20, int offset = 0}) async {
    try {
      state = state.copyWith(isLoading: true);
      final resp = await _api.dio.get('/posture/history', queryParameters: {'limit': limit, 'offset': offset});
      final list = (resp.data as List)
          .map((e) => AssessmentRecord.fromJson(e as Map<String, dynamic>))
          .toList();
      state = state.copyWith(history: list, isLoading: false);
    } on DioException catch (e) {
      state = state.copyWith(isLoading: false, error: e.response?.data?['detail'] ?? '加载失败');
    }
  }
}

final assessmentProvider = StateNotifierProvider<AssessmentNotifier, AssessmentState>((ref) {
  final api = ref.read(apiClientProvider);
  return AssessmentNotifier(api);
});
```

- [ ] **Step 2: 编写 posture_state_provider.dart**

```dart
// app/lib/providers/posture_state_provider.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/assessment.dart';
import '../models/user_posture_state.dart';

class PostureStateNotifier extends StateNotifier<Map<String, UserPostureState>> {
  PostureStateNotifier() : super({});

  void updateState({
    required String issueId,
    required String result,
    required String method,
  }) {
    final newState = Map<String, UserPostureState>.from(state);
    newState[issueId] = UserPostureState(
      issueId: issueId,
      result: result,
      method: method,
      updatedAt: DateTime.now(),
      synced: false,
    );
    state = newState;
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
  }

  void clearAll() => state = {};
}

final postureStateProvider =
    StateNotifierProvider<PostureStateNotifier, Map<String, UserPostureState>>(
        (_) => PostureStateNotifier());
```

- [ ] **Step 3: 编写 self_test_screen.dart**

```dart
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
```

- [ ] **Step 4: 提交**

```bash
cd C:\Users\Lenovo\Desktop\develop\health && git add app/lib/providers/assessment_provider.dart app/lib/providers/posture_state_provider.dart app/lib/screens/test/self_test_screen.dart && git commit -m "feat: add assessment provider, posture state provider, and self-test screen"
```

---

## Task 11: AI 拍照分析页

**Files:**
- Create: `app/lib/screens/test/photo_test_screen.dart`

- [ ] **Step 1: 编写 photo_test_screen.dart**

```dart
// app/lib/screens/test/photo_test_screen.dart
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:dio/dio.dart';
import '../../core/api_client.dart';
import '../../providers/assessment_provider.dart';
import '../../providers/posture_state_provider.dart';

class PhotoTestScreen extends ConsumerStatefulWidget {
  final String issueId;
  const PhotoTestScreen({super.key, required this.issueId});

  @override
  ConsumerState<PhotoTestScreen> createState() => _PhotoTestScreenState();
}

class _PhotoTestScreenState extends ConsumerState<PhotoTestScreen> {
  final _picker = ImagePicker();
  File? _photo;
  bool _analyzing = false;
  String? _result;
  String? _suggestion;

  Future<void> _pickPhoto(ImageSource source) async {
    final xFile = await _picker.pickImage(source: source, maxWidth: 1024, maxHeight: 1024);
    if (xFile == null) return;
    setState(() => _photo = File(xFile.path));
    await _uploadAndAnalyze();
  }

  Future<void> _uploadAndAnalyze() async {
    if (_photo == null) return;
    setState(() => _analyzing = true);

    try {
      final api = ref.read(apiClientProvider);
      // 1. 获取 OSS 凭证
      final stsResp = await api.dio.post('/upload/sts-token');
      final sts = stsResp.data as Map<String, dynamic>;

      // 2. 上传到 OSS
      final fileName = '${DateTime.now().millisecondsSinceEpoch}.jpg';
      final objectKey = '${sts['path_prefix']}$fileName';
      final formData = FormData.fromMap({
        'file': await MultipartFile.fromFile(_photo!.path, filename: fileName),
        'key': objectKey,
      });
      // 开发模式：使用直传URL，生产需 OSS SDK
      await api.dio.post(
        'https://${sts['bucket']}.${sts['endpoint']}',
        data: formData,
        options: Options(headers: {
          'Content-Type': 'multipart/form-data',
        }),
      );

      // 3. 提交 AI 分析
      final result = await ref
          .read(assessmentProvider.notifier)
          .submitPhotoAssess(widget.issueId, [objectKey]);

      if (result != null && mounted) {
        final aiLevel = result['result'] ?? 'normal';
        final aiSuggestion = result['suggestion'] ?? '';
        ref.read(postureStateProvider.notifier).updateState(
          issueId: widget.issueId,
          result: aiLevel,
          method: 'ai_photo',
        );
        context.push('/issues/${widget.issueId}/result', extra: {
          'assessmentId': result['id'] ?? '',
          'result': aiLevel,
          'suggestion': aiSuggestion,
        });
      }
    } on DioException catch (e) {
      final msg = e.response?.data?['detail'] ?? '上传或分析失败，请重试';
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      }
    } finally {
      if (mounted) setState(() => _analyzing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('AI 拍照分析')),
      body: _analyzing
          ? const Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CircularProgressIndicator(),
                  SizedBox(height: 16),
                  Text('AI 正在分析中...', style: TextStyle(fontSize: 18)),
                  SizedBox(height: 8),
                  Text('请耐心等待，最多约30秒', style: TextStyle(color: Color(0xFF8892B0))),
                ],
              ),
            )
          : _photo != null
              ? Column(
                  children: [
                    Expanded(child: Image.file(_photo!, fit: BoxFit.contain)),
                    Padding(
                      padding: const EdgeInsets.all(16),
                      child: Row(
                        children: [
                          Expanded(
                            child: OutlinedButton(
                              onPressed: () => setState(() => _photo = null),
                              child: const Text('重新选择'),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: ElevatedButton(
                              onPressed: _uploadAndAnalyze,
                              child: const Text('开始分析'),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                )
              : Padding(
                  padding: const EdgeInsets.all(32),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.camera_alt, size: 80, color: Color(0xFFE94560)),
                      const SizedBox(height: 24),
                      const Text('AI 体态分析',
                          style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
                      const SizedBox(height: 8),
                      const Text('请保持自然站姿，全身入镜\n光线充足，背景简洁',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: Color(0xFF8892B0))),
                      const SizedBox(height: 32),
                      Container(
                        height: 200,
                        decoration: BoxDecoration(
                          color: const Color(0xFF16213E),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Center(
                          child: Icon(Icons.accessibility_new, size: 80, color: Color(0xFF0F3460)),
                        ),
                      ),
                      const SizedBox(height: 32),
                      SizedBox(
                        width: double.infinity, height: 52,
                        child: ElevatedButton.icon(
                          onPressed: () => _pickPhoto(ImageSource.camera),
                          icon: const Icon(Icons.camera),
                          label: const Text('拍照'),
                        ),
                      ),
                      const SizedBox(height: 12),
                      SizedBox(
                        width: double.infinity, height: 52,
                        child: ElevatedButton.icon(
                          onPressed: () => _pickPhoto(ImageSource.gallery),
                          icon: const Icon(Icons.photo_library),
                          label: const Text('从相册选择'),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF0F3460),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
    );
  }
}
```

- [ ] **Step 2: 提交**

```bash
cd C:\Users\Lenovo\Desktop\develop\health && git add app/lib/screens/test/photo_test_screen.dart && git commit -m "feat: add AI photo test screen"
```

---

## Task 12: 结果页 + 通用 Widgets

**Files:**
- Create: `app/lib/widgets/result_badge.dart`
- Create: `app/lib/widgets/disclaimer_banner.dart`
- Create: `app/lib/screens/result/result_screen.dart`

- [ ] **Step 1: 编写 result_badge.dart**

```dart
// app/lib/widgets/result_badge.dart
import 'package:flutter/material.dart';
import '../core/constants.dart';

class ResultBadge extends StatelessWidget {
  final String result;
  final double size;

  const ResultBadge({super.key, required this.result, this.size = 16});

  Color get color {
    switch (result) {
      case 'normal': return const Color(AppConstants.normalColor);
      case 'moderate': return const Color(AppConstants.moderateColor);
      case 'severe': return const Color(AppConstants.severeColor);
      default: return const Color(0xFF8892B0);
    }
  }

  IconData get icon {
    switch (result) {
      case 'normal': return Icons.check_circle;
      case 'moderate': return Icons.warning_amber;
      case 'severe': return Icons.cancel;
      default: return Icons.help_outline;
    }
  }

  String get label {
    switch (result) {
      case 'normal': return '正常';
      case 'moderate': return '需关注';
      case 'severe': return '严重';
      default: return '未知';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color.withOpacity(0.2),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color, width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color, size: size),
          const SizedBox(width: 6),
          Text(label, style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: size)),
        ],
      ),
    );
  }
}
```

- [ ] **Step 2: 编写 disclaimer_banner.dart**

```dart
// app/lib/widgets/disclaimer_banner.dart
import 'package:flutter/material.dart';

class DisclaimerBanner extends StatelessWidget {
  const DisclaimerBanner({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      color: const Color(0xFF16213E),
      child: const Text(
        '本内容仅供参考，不能替代专业医疗诊断。如有不适请及时就医。',
        textAlign: TextAlign.center,
        style: TextStyle(color: Color(0xFF8892B0), fontSize: 12),
      ),
    );
  }
}
```

- [ ] **Step 3: 编写 result_screen.dart**

```dart
// app/lib/screens/result/result_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../providers/issue_provider.dart';
import '../../widgets/result_badge.dart';
import '../../widgets/disclaimer_banner.dart';

class ResultScreen extends ConsumerWidget {
  final String issueId;
  final String assessmentId;
  final String result;
  final String suggestion;

  const ResultScreen({
    super.key,
    required this.issueId,
    required this.assessmentId,
    required this.result,
    required this.suggestion,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(issueProvider).currentDetail;

    // severe 时自动弹就医提示
    if (result == 'severe') {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _showSevereDialog(context);
      });
    }

    return Scaffold(
      appBar: AppBar(title: const Text('评估结果')),
      body: Column(
        children: [
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // 顶部结果卡片
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Column(
                        children: [
                          ResultBadge(result: result, size: 22),
                          const SizedBox(height: 16),
                          Text(suggestion,
                              textAlign: TextAlign.center,
                              style: const TextStyle(fontSize: 16, height: 1.5)),
                        ],
                      ),
                    ),
                  ),
                  // 纠正建议（仅 moderate 时显示）
                  if (result == 'moderate' && detail != null) ...[
                    const SizedBox(height: 16),
                    const Text('纠正建议', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 8),
                    ...detail.corrections.map((c) => Card(
                      margin: const EdgeInsets.only(bottom: 8),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(
                              c['type'] == '拉伸' ? Icons.fitness_center : c['type'] == '强化' ? Icons.trending_up : Icons.lightbulb,
                              color: const Color(0xFFE94560), size: 20),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  if (c['target_muscle'] != null)
                                    Text(c['target_muscle'] as String, style: const TextStyle(fontWeight: FontWeight.w600)),
                                  if (c['method'] != null)
                                    Text(c['method'] as String, style: const TextStyle(height: 1.4)),
                                  if (c['freq'] != null)
                                    Text(c['freq'] as String, style: const TextStyle(color: Color(0xFF8892B0), fontSize: 12)),
                                  if (c['desc'] != null)
                                    Text(c['desc'] as String, style: const TextStyle(height: 1.4)),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    )),
                  ],
                  // 相关推荐
                  if (detail != null && detail.relatedIssues.isNotEmpty) ...[
                    const SizedBox(height: 16),
                    const Text('你可能还需要关注', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 8),
                    SizedBox(
                      height: 120,
                      child: ListView.separated(
                        scrollDirection: Axis.horizontal,
                        itemCount: detail.relatedIssues.length,
                        separatorBuilder: (_, __) => const SizedBox(width: 8),
                        itemBuilder: (_, i) {
                          final rel = detail.relatedIssues[i];
                          return GestureDetector(
                            onTap: () => context.push('/issues/${rel.id}/detail'),
                            child: Container(
                              width: 160,
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: const Color(0xFF16213E),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(rel.id,
                                      style: const TextStyle(fontSize: 12, color: Color(0xFF8892B0))),
                                  const SizedBox(height: 4),
                                  Text(rel.relation,
                                      style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold)),
                                  Text('关联度: ${rel.weight}',
                                      style: const TextStyle(fontSize: 12, color: Color(0xFF8892B0))),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
          const DisclaimerBanner(),
        ],
      ),
    );
  }

  void _showSevereDialog(BuildContext context) {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        icon: const Icon(Icons.warning, color: Color(0xFFFF1744), size: 48),
        title: const Text('建议及时就医'),
        content: const Text('你的评估结果为"严重"。本 App 的评估仅供参考，不能替代专业医疗诊断。建议你尽快咨询专业医师进行详细检查。'),
        actions: [
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('我知道了'),
          ),
        ],
      ),
    );
  }
}
```

- [ ] **Step 4: 提交**

```bash
cd C:\Users\Lenovo\Desktop\develop\health && git add app/lib/widgets/result_badge.dart app/lib/widgets/disclaimer_banner.dart app/lib/screens/result/ && git commit -m "feat: add result screen, result badge, and disclaimer widgets"
```

---

## Task 13: 历史记录页

**Files:**
- Create: `app/lib/screens/history/history_screen.dart`

- [ ] **Step 1: 编写 history_screen.dart**

```dart
// app/lib/screens/history/history_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import '../../providers/assessment_provider.dart';
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
    Future.microtask(() =>
        ref.read(assessmentProvider.notifier).fetchHistory());
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(assessmentProvider);

    // 按日期分组
    final grouped = <String, List<dynamic>>{};
    for (final r in state.history) {
      final key = DateFormat('yyyy-MM-dd').format(r.createdAt);
      grouped.putIfAbsent(key, () => []).add(r);
    }

    return Scaffold(
      appBar: AppBar(title: const Text('评估历史')),
      body: state.isLoading
          ? const Center(child: CircularProgressIndicator())
          : state.history.isEmpty
              ? const Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.history, size: 64, color: Color(0xFF0F3460)),
                      SizedBox(height: 16),
                      Text('暂无评估记录',
                          style: TextStyle(fontSize: 18, color: Color(0xFF8892B0))),
                      Text('去首页开始你的第一次体态分析吧',
                          style: TextStyle(color: Color(0xFF8892B0))),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: () async {
                    await ref.read(assessmentProvider.notifier).fetchHistory();
                  },
                  child: ListView.builder(
                    itemCount: grouped.keys.length,
                    itemBuilder: (_, i) {
                      final date = grouped.keys.elementAt(i);
                      final records = grouped[date]!;
                      return Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Padding(
                            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                            child: Text(_formatDate(date),
                                style: const TextStyle(fontSize: 14, color: Color(0xFF8892B0), fontWeight: FontWeight.w600)),
                          ),
                          ...records.map((r) => Card(
                            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                            child: ListTile(
                              leading: ResultBadge(result: r.result, size: 13),
                              title: Text(r.issueName),
                              subtitle: Text(r.method == 'self_test' ? '自测' : 'AI分析',
                                  style: const TextStyle(fontSize: 12)),
                              trailing: Text(DateFormat('HH:mm').format(r.createdAt),
                                  style: const TextStyle(color: Color(0xFF8892B0), fontSize: 13)),
                              onTap: () => context.push('/issues/${r.issueId}/result', extra: {
                                'assessmentId': r.id,
                                'result': r.result,
                                'suggestion': '',
                              }),
                            ),
                          )),
                        ],
                      );
                    },
                  ),
                ),
    );
  }

  String _formatDate(String dateStr) {
    final now = DateTime.now();
    final date = DateTime.tryParse(dateStr);
    if (date == null) return dateStr;
    if (DateFormat('yyyy-MM-dd').format(now) == dateStr) return '今天';
    if (DateFormat('yyyy-MM-dd').format(now.subtract(const Duration(days: 1))) == dateStr) return '昨天';
    return DateFormat('M月d日').format(date);
  }
}
```

- [ ] **Step 2: 提交**

```bash
cd C:\Users\Lenovo\Desktop\develop\health && git add app/lib/screens/history/ && git commit -m "feat: add history screen"
```

---

## Task 14: 个人中心 + 体态档案页

**Files:**
- Create: `app/lib/screens/profile/profile_screen.dart`
- Create: `app/lib/screens/profile/posture_profile_screen.dart`

- [ ] **Step 1: 编写 profile_screen.dart**

```dart
// app/lib/screens/profile/profile_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../providers/auth_provider.dart';
import '../../providers/user_provider.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(userProvider).profile;

    return Scaffold(
      appBar: AppBar(title: const Text('个人中心')),
      body: ListView(
        children: [
          // 头像区
          Container(
            padding: const EdgeInsets.all(24),
            child: Row(
              children: [
                const CircleAvatar(
                  radius: 30,
                  backgroundColor: Color(0xFF0F3460),
                  child: Icon(Icons.person, size: 36, color: Color(0xFF8892B0)),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(profile?.phone ?? '未登录',
                          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                      const Text('普通用户', style: TextStyle(color: Color(0xFF8892B0))),
                    ],
                  ),
                ),
              ],
            ),
          ),
          // 基本信息
          Card(
            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('基本信息', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 12),
                  _infoRow('身高', '${profile?.height ?? "未填写"} cm', () => _editField(context, ref, '身高', 'cm', (profile?.height ?? 170).toInt(), 100, 220, (v) => _updateProfile(ref, height: v.toDouble()))),
                  _infoRow('体重', '${profile?.weight ?? "未填写"} kg', () => _editField(context, ref, '体重', 'kg', (profile?.weight ?? 65).toInt(), 30, 200, (v) => _updateProfile(ref, weight: v.toDouble()))),
                  _infoRow('年龄', '${profile?.age ?? "未填写"} 岁', () => _editField(context, ref, '年龄', '岁', profile?.age ?? 25, 12, 120, (v) => _updateProfile(ref, age: v))),
                  _infoRow('性别', profile?.gender == 'male' ? '男' : profile?.gender == 'female' ? '女' : '未填写',
                      () => _editGender(context, ref)),
                ],
              ),
            ),
          ),
          // 菜单
          Card(
            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Column(
              children: [
                _menuItem('我的体态档案', Icons.assignment, () => context.push('/profile/posture')),
                const Divider(height: 1),
                _menuItem('评估历史', Icons.history, () => context.push('/history')),
                const Divider(height: 1),
                _menuItem('关于', Icons.info_outline, _showAbout),
              ],
            ),
          ),
          const SizedBox(height: 24),
          // 退出登录
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: SizedBox(
              width: double.infinity,
              child: OutlinedButton(
                onPressed: () async {
                  await ref.read(authProvider.notifier).logout();
                  if (context.mounted) context.go('/login');
                },
                style: OutlinedButton.styleFrom(foregroundColor: const Color(0xFFFF1744)),
                child: const Text('退出登录'),
              ),
            ),
          ),
          const SizedBox(height: 32),
        ],
      ),
    );
  }

  Widget _infoRow(String label, String value, VoidCallback onTap) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: const TextStyle(color: Color(0xFF8892B0))),
            Row(
              children: [
                Text(value, style: const TextStyle(fontSize: 15)),
                const SizedBox(width: 4),
                const Icon(Icons.edit, size: 16, color: Color(0xFF8892B0)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _menuItem(String title, IconData icon, VoidCallback onTap) {
    return ListTile(
      leading: Icon(icon, color: const Color(0xFFE94560)),
      title: Text(title),
      trailing: const Icon(Icons.chevron_right, color: Color(0xFF8892B0)),
      onTap: onTap,
    );
  }

  void _updateProfile(WidgetRef ref, {double? height, double? weight, int? age, String? gender}) {
    ref.read(userProvider.notifier).updateProfile(
      height: height, weight: weight, age: age, gender: gender);
  }

  void _editField(BuildContext context, WidgetRef ref, String label, String unit, int value, int min, int max, ValueChanged<int> onSave) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('$label'),
        content: StatefulBuilder(
          builder: (_, setDialogState) {
            int temp = value;
            return Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('$temp $unit', style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
                Slider(
                  value: temp.toDouble(), min: min.toDouble(), max: max.toDouble(),
                  onChanged: (v) => setDialogState(() => temp = v.toInt()),
                ),
              ],
            );
          },
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
          ElevatedButton(onPressed: () { onSave(value); Navigator.pop(ctx); }, child: const Text('保存')),
        ],
      ),
    );
  }

  void _editGender(BuildContext context, WidgetRef ref) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('性别'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(title: const Text('男'), onTap: () { _updateProfile(ref, gender: 'male'); Navigator.pop(ctx); }),
            ListTile(title: const Text('女'), onTap: () { _updateProfile(ref, gender: 'female'); Navigator.pop(ctx); }),
          ],
        ),
      ),
    );
  }

  void _showAbout() {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('关于体态分析'),
        content: const Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('版本: 1.0.0 MVP', style: TextStyle(fontSize: 16)),
            SizedBox(height: 12),
            Text('本 App 内容基于公开医学文献，仅供健康科普与自我管理参考，不能替代专业医疗诊断与治疗。如有持续疼痛、麻木、畸形或其他异常，请及时就医。',
                style: TextStyle(height: 1.5)),
          ],
        ),
        actions: [
          ElevatedButton(onPressed: () => Navigator.pop(ctx), child: const Text('知道了')),
        ],
      ),
    );
  }
}
```

- [ ] **Step 2: 编写 posture_profile_screen.dart**

```dart
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
                onTap: () => context.push('/issues/${issue.id}/detail'),
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
```

- [ ] **Step 3: 提交**

```bash
cd C:\Users\Lenovo\Desktop\develop\health && git add app/lib/screens/profile/ && git commit -m "feat: add profile screen and posture profile screen"
```

---

## Task 15: 启动同步 + 收尾

**Files:**
- Create: `app/lib/services/sync_service.dart`
- Modify: `app/lib/main.dart`

- [ ] **Step 1: 编写 sync_service.dart**

```dart
// app/lib/services/sync_service.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/assessment.dart';
import '../providers/assessment_provider.dart';
import '../providers/issue_provider.dart';
import '../providers/posture_state_provider.dart';
import '../providers/user_provider.dart';

class SyncService {
  final Ref _ref;

  SyncService(this._ref);

  /// App 启动时调用：加载数据并同步
  Future<void> startupSync() async {
    // 1. 加载用户信息
    await _ref.read(userProvider.notifier).fetchProfile();
    // 2. 加载所有问题列表
    await _ref.read(issueProvider.notifier).fetchIssues(null);
    // 3. 加载评估历史
    await _ref.read(assessmentProvider.notifier).fetchHistory();
    // 4. 从历史聚合推导体态状态
    final history = _ref.read(assessmentProvider).history;
    _ref.read(postureStateProvider.notifier).rebuildFromHistory(history);
  }
}

final syncServiceProvider = Provider<SyncService>((ref) => SyncService(ref));
```

- [ ] **Step 2: 修改 main.dart**

在 `app/lib/main.dart` 中，ProviderScope 启动时触发同步。修改为：

```dart
// app/lib/main.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'app.dart';
import 'providers/auth_provider.dart';
import 'services/sync_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ProviderScope(child: PostureApp()));
}

// 启动后初始化
class _StartupInitializer extends ConsumerStatefulWidget {
  final Widget child;
  const _StartupInitializer({required this.child});

  @override
  ConsumerState<_StartupInitializer> createState() => _StartupInitializerState();
}

class _StartupInitializerState extends ConsumerState<_StartupInitializer> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() async {
      final authState = ref.read(authProvider);
      if (authState.isLoggedIn) {
        await ref.read(syncServiceProvider).startupSync();
      }
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
```

实际上简化：直接修改 `app.dart` 中的 HomeScreen 或添加一个启动时的 provider listener。最简单的做法是使用 `posture_state_provider` 在 `assessment_provider` history 变化时自动重建。

更简洁的方案是在 `app.dart` 的 redirect 中添加初始化逻辑：

```dart
// 在 app.dart 顶部添加
// 不再需要独立的 sync_service 调用，各 provider 在 initState 中自行 fetch 数据
```

简化为：修改 `main.dart` 添加 checkAuth 调用：

```dart
// app/lib/main.dart (final version)
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'app.dart';
import 'providers/auth_provider.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final container = ProviderContainer();
  // 启动时检查 auth 状态
  await container.read(authProvider.notifier).checkAuth();
  runApp(
    UncontrolledProviderScope(
      container: container,
      child: const PostureApp(),
    ),
  );
}
```

- [ ] **Step 3: 提交**

```bash
cd C:\Users\Lenovo\Desktop\develop\health && git add app/lib/main.dart app/lib/services/ && git commit -m "feat: add startup sync and finalize main.dart"
```

---

## 执行顺序

```
阶段一：可登录骨架（T1 → T2 → T3 → T4 → T5 → T6）
  验证：App 可验证码登录、填写信息、进入首页空壳 + 底部导航

阶段二：核心分析流程（T7 → T8 → T9 → T10 → T11 → T12）
  验证：3D导航→分类→问题详情→自测→拍照→结果展示 全流程

阶段三：收尾（T13 → T14 → T15）
  验证：历史记录 + 个人中心 + 体态档案 + 启动同步

原则：每完成一个 Task 后运行 `flutter analyze` 确保无编译错误，再继续下一个 Task
```
