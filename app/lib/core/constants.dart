// app/lib/core/constants.dart
class AppConstants {
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000/api/v1',
  );
  static const bool photoAnalysisEnabled = bool.fromEnvironment(
    'PHOTO_ANALYSIS_ENABLED',
  );
  static const String authMode = String.fromEnvironment(
    'AUTH_MODE',
    defaultValue: 'legacy',
  );
  static const String authCredentialProvider = String.fromEnvironment(
    'AUTH_CREDENTIAL_PROVIDER',
    defaultValue: 'offline_password',
  );
  static const bool controlledTrialAuth = authMode == 'controlled_trial';
  static const String clientPlatform = 'android';
  static const int clientVersionCode = int.fromEnvironment(
    'CLIENT_VERSION_CODE',
    defaultValue: 1,
  );
  static const String appName = '体态分析';
  static const Duration httpTimeout = Duration(seconds: 30);
  static const String devAdminPhone = String.fromEnvironment('DEV_ADMIN_PHONE');
  static const String devAdminPassword = String.fromEnvironment(
    'DEV_ADMIN_PASSWORD',
  );
  static bool get controlledTrialConfigurationValid =>
      !controlledTrialAuth ||
      (apiBaseUrl.startsWith('https://') &&
          !photoAnalysisEnabled &&
          devAdminPhone.isEmpty &&
          devAdminPassword.isEmpty &&
          authCredentialProvider.isNotEmpty);

  // 色板 — Light Gray Glassmorphism (F1 branding)
  static const int bgColor = 0xFFD6D8D9; // 浅灰背景
  static const int cardColor = 0x40FFFFFF; // 白色 25% opacity (glass)
  static const int primaryColor = 0xFF20272A; // 深炭灰
  static const int accentColor = 0xFF005443; // 高对比 teal 主操作
  static const int accentLight = 0xFF72E3C8; // 亮 teal 装饰
  static const int glassBorder = 0x50FFFFFF; // 白色 30% 卡片边框
  static const int textColor = 0xFF20272A; // 深色主文字
  static const int textMuted = 0xFF435055; // 高对比次要文字
  static const int surfaceDark = 0xFF20272A; // 深色表面
  static const int navigationMuted = 0xFFB8C0C4; // 深色导航上的未选中项
  static const int dividerColor = 0xFFC8CACC; // 分割线

  // 语义色
  static const int normalColor = 0xFF005443;
  static const int moderateColor = 0xFF574400;
  static const int severeColor = 0xFF881423;

  static const Map<String, String> categoryNames = {
    'head_neck': '头颈部',
    'shoulder_thorax': '肩胸区',
    'pelvis_spine': '骨盆腰椎',
    'lower_limb': '下肢',
    'compound': '复合综合征',
  };

  static const Map<String, String> categoryRoutes = {
    'head_neck': '/issues/head_neck',
    'shoulder_thorax': '/issues/shoulder_thorax',
    'pelvis_spine': '/issues/pelvis_spine',
    'lower_limb': '/issues/lower_limb',
    'compound': '/issues/compound',
  };
}
