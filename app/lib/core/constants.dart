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
