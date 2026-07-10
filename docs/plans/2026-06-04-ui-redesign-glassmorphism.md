> **⚠️ 历史资料** — 本文档记录早期开发过程，不代表当前完成状态或当前架构决策。
> 当前规格和计划见 [docs/README.md](../README.md)。

# UI Redesign — Implementation Plan

> **STATUS: ✅ COMPLETED (2026-06-08)**
>
> 本计划已执行完毕。最终方案从 "Dark Glassmorphism" 修正为 "Light Gray Glassmorphism"（浅灰背景 + 毛玻璃卡片 + Teal accent）。
> 详见最终 spec: `docs/specs/2026-06-04-ui-redesign-spec.md`

**Spec:** `docs/specs/2026-06-04-ui-redesign-spec.md`

**Goal:** Implement the Light Gray Glassmorphism design system — light gray background, frosted glass cards with BackdropFilter, teal accent, dark text.

**Architecture:** Pure visual layer change. No business logic, providers, models, or API changes. Modify theme, constants, and all screen/widget files for the new design language.

**Tech Stack:** Flutter (>= 3.27), existing Riverpod + GoRouter architecture unchanged.

---

## Task Dependencies

```
Task 1 (色板+主题) ──┐
Task 2 (GlassCard)  ──┤── 前置依赖，必须先完成
Task 3 (全局颜色替换) ┘
                      │
         ┌────────────┴──────────────┐
         ▼                           ▼
Task 4-12 (各页面/组件)          可并行执行
         │
         ▼
Task 13 (最终验证)
```

---

## File Modification Map

### Core (全局影响)
- `lib/core/constants.dart` — 更新色板值，新增 textColor/textMuted/glassBorder
- `lib/core/theme.dart` — 重写 ThemeData 匹配新设计

### Widgets (共用组件)
- `lib/widgets/glass_card.dart` — **新建** glassmorphism Card 组件
- `lib/widgets/body_region_button.dart` — 圆形 icon 容器 + label
- `lib/widgets/issue_card.dart` — 应用 GlassCard + 新色彩
- `lib/widgets/result_badge.dart` — pill shape + 新色彩
- `lib/widgets/disclaimer_banner.dart` — 新色调

### Screens
- `lib/screens/auth/login_screen.dart` — GlassCard form + pill buttons
- `lib/screens/onboarding/onboarding_screen.dart` — GlassCard 包裹 picker + teal 色
- `lib/screens/home/home_screen.dart` — 新版首页布局
- `lib/screens/issues/issue_list_screen.dart` — GlassCard 列表项
- `lib/screens/issues/issue_detail_screen.dart` — GlassCard 分区
- `lib/screens/test/self_test_screen.dart` — teal 进度 + GlassCard
- `lib/screens/test/photo_test_screen.dart` — GlassCard + pill buttons
- `lib/screens/result/result_screen.dart` — 大号结果 + GlassCard 建议区
- `lib/screens/history/history_screen.dart` — 数据表格风格
- `lib/screens/profile/profile_screen.dart` — GlassCard sections + 弹窗适配
- `lib/screens/profile/posture_profile_screen.dart` — GlassCard + teal progress bars

### App Shell
- `lib/app.dart` — BottomNav glass 样式 + extendBody

---

## Tasks

### Task 1: 更新色板 + 全局主题

**Files:**
- Modify: `lib/core/constants.dart`
- Modify: `lib/core/theme.dart`

- [ ] **Step 1:** 更新 `constants.dart`，替换色板值，新增字段：

```dart
// 色板
static const int bgColor = 0xFF0D1117;
static const int cardColor = 0xFF161B22;
static const int primaryColor = 0xFF21262D;
static const int accentColor = 0xFF2DD4BF;
static const int glassBorder = 0xFF30363D;
static const int textColor = 0xFFF0F6FC;
static const int textMuted = 0xFF8B949E;

// 结果颜色
static const int normalColor = 0xFF34D399;
static const int moderateColor = 0xFFF59E0B;
static const int severeColor = 0xFFEF4444;
```

- [ ] **Step 2:** 重写 `theme.dart` ThemeData（见 spec 2.3-2.5, 2.10-2.11）:
  - scaffoldBackgroundColor, cardTheme(radius 20, elevation 0, border glassBorder)
  - AppBar: transparent, no elevation, foreground textColor
  - ElevatedButton: pill (radius 24), accentColor fill, white text, height 52
  - OutlinedButton: pill, accentColor border/text
  - InputDecoration: radius 16, filled cardColor, glassBorder border
  - NavigationBarTheme: surfaceTintColor transparent, indicatorColor accentColor
  - DialogTheme: radius 20, backgroundColor cardColor
  - SnackBarTheme: floating, radius 12, backgroundColor cardColor
  - DividerTheme: color glassBorder
  - ProgressIndicatorTheme: color accentColor, trackColor primaryColor
- [ ] **Step 3:** 运行 `flutter analyze` 确认无错误
- [ ] **Step 4:** Commit

### Task 2: 新建 GlassCard 通用组件

**Files:**
- Create: `lib/widgets/glass_card.dart`

- [ ] **Step 1:** 创建 `GlassCard` StatelessWidget:

```dart
class GlassCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry? padding;
  final EdgeInsetsGeometry? margin;
  final double borderRadius;

  const GlassCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(20),
    this.margin,
    this.borderRadius = 20,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: margin,
      padding: padding,
      decoration: BoxDecoration(
        color: const Color(AppConstants.cardColor).withValues(alpha: 0.85),
        borderRadius: BorderRadius.circular(borderRadius),
        border: Border.all(
          color: const Color(AppConstants.glassBorder),
          width: 1,
        ),
      ),
      child: child,
    );
  }
}
```

- [ ] **Step 2:** 运行 `flutter analyze` 确认无错误
- [ ] **Step 3:** Commit

### Task 3: 全局 hardcoded 颜色替换

**Files:**
- All screen/widget .dart files

- [ ] **Step 1:** 搜索全项目 `0xFFE94560`（旧 accentColor）替换为 `AppConstants.accentColor`
- [ ] **Step 2:** 搜索全项目 `0xFF8892B0`（旧 textSecondary）替换为 `AppConstants.textMuted`
- [ ] **Step 3:** 搜索全项目 `0xFF0F3460`（旧 primaryColor）替换为 `AppConstants.primaryColor`
- [ ] **Step 4:** 搜索全项目 `0xFF16213E`（旧 cardColor）替换为 `AppConstants.cardColor`
- [ ] **Step 5:** 搜索全项目 `0xFFEAEAEA`（旧 textPrimary）替换为 `AppConstants.textColor`
- [ ] **Step 6:** 搜索 `withOpacity(` 替换为 `withValues(alpha: `
- [ ] **Step 7:** 运行 `flutter analyze` 确认无错误
- [ ] **Step 8:** Commit

### Task 4: 重写 body_region_button + result_badge

**Files:**
- Modify: `lib/widgets/body_region_button.dart`
- Modify: `lib/widgets/result_badge.dart`

- [ ] **Step 1:** `BodyRegionButton` — Column 布局: 圆形 Container(48x48, accentColor 15% bg) 内嵌 icon(accentColor) + SizedBox(8) + label(13px, textMuted)
- [ ] **Step 2:** `ResultBadge` — pill Container(padding h12v6), 背景 `color.withValues(alpha: 0.15)`, 无 border, Row(icon + text)
- [ ] **Step 3:** 运行 `flutter analyze` 确认无错误
- [ ] **Step 4:** Commit

### Task 5: 重写 issue_card + disclaimer_banner

**Files:**
- Modify: `lib/widgets/issue_card.dart`
- Modify: `lib/widgets/disclaimer_banner.dart`

- [ ] **Step 1:** `IssueCard` — 外层用 GlassCard(margin: h16v6), 移除 Material Card/InkWell, 用 GestureDetector 包裹
- [ ] **Step 2:** `DisclaimerBanner` — 背景改 moderateColor 15%, icon/text 改 moderateColor
- [ ] **Step 3:** 运行 `flutter analyze` 确认无错误
- [ ] **Step 4:** Commit

### Task 6: 重写首页 (home_screen)

**Files:**
- Modify: `lib/screens/home/home_screen.dart`

- [ ] **Step 1:** AppBar: transparent bg, title "体态分析" 左对齐 24px bold
- [ ] **Step 2:** 3D 模型: ClipRRect(borderRadius 20) 包裹 ModelViewer
- [ ] **Step 3:** 分类导航: Row + MainAxisAlignment.spaceEvenly, 4 个 BodyRegionButton
- [ ] **Step 4:** "综合评估" 改为 OutlinedButton (pill style, theme 已全局设置)
- [ ] **Step 5:** 体态档案入口: GlassCard, Row(icon container + text + Spacer + teal LinearProgressIndicator)
- [ ] **Step 6:** 移除 `_buildFallback` 死代码
- [ ] **Step 7:** body 底部添加 `SizedBox(height: 80)` 为 nav 预留空间
- [ ] **Step 8:** 运行 `flutter analyze` 确认无错误
- [ ] **Step 9:** Commit

### Task 7: 重写登录页 (login_screen)

**Files:**
- Modify: `lib/screens/auth/login_screen.dart`

- [ ] **Step 1:** 顶部: Icon(teal) + "体态分析"(28px bold) + subtitle(textMuted)
- [ ] **Step 2:** 表单: GlassCard 包裹 (手机号 TextField + 验证码 Row + 错误文字)
- [ ] **Step 3:** "登录" 按钮: ElevatedButton (theme 已定义 pill)
- [ ] **Step 4:** 开发区: Divider(glassBorder) + GlassCard 包裹 OutlinedButton
- [ ] **Step 5:** 运行 `flutter analyze` 确认无错误
- [ ] **Step 6:** Commit

### Task 8: 重写引导页 (onboarding_screen)

**Files:**
- Modify: `lib/screens/onboarding/onboarding_screen.dart`

- [ ] **Step 1:** LinearProgressIndicator: valueColor accentColor, backgroundColor primaryColor
- [ ] **Step 2:** Picker 页: GlassCard 包裹 CupertinoPicker; selectionOverlay border 改 accentColor
- [ ] **Step 3:** 体重页: GlassCard 包裹 TextField; underline border 改 accentColor
- [ ] **Step 4:** 性别卡片: GlassCard, selected border 改 accentColor, selected bg 改 accentColor 15%
- [ ] **Step 5:** 底部: dot indicator active 色改 accentColor; 按钮用 theme pill style
- [ ] **Step 6:** 运行 `flutter analyze` 确认无错误
- [ ] **Step 7:** Commit

### Task 9: 重写问题列表页 (issue_list_screen)

**Files:**
- Modify: `lib/screens/issues/issue_list_screen.dart`

- [ ] **Step 1:** AppBar title 保持当前(分类名); 错误态/空态文字颜色改 textMuted
- [ ] **Step 2:** 重试按钮用 ElevatedButton (pill, teal)
- [ ] **Step 3:** 运行 `flutter analyze` 确认无错误
- [ ] **Step 4:** Commit

### Task 10: 重写问题详情页 (issue_detail_screen)

**Files:**
- Modify: `lib/screens/issues/issue_detail_screen.dart`

- [ ] **Step 1:** 所有 Card 替换为 GlassCard(margin: h16v6)
- [ ] **Step 2:** 成因/纠正方法的 type icon 用圆形 container(32x32, accentColor 15% bg)
- [ ] **Step 3:** "开始自测" bottomNav 按钮用 ElevatedButton (teal pill)
- [ ] **Step 4:** 红旗征 GlassCard: 背景改为 Container decoration 用 severeColor 15%
- [ ] **Step 5:** Chip 样式: backgroundColor primaryColor, textColor textMuted
- [ ] **Step 6:** 运行 `flutter analyze` 确认无错误
- [ ] **Step 7:** Commit

### Task 11: 重写自测页 (self_test_screen)

**Files:**
- Modify: `lib/screens/test/self_test_screen.dart`

- [ ] **Step 1:** 进度条段: color 改 accentColor active / primaryColor inactive
- [ ] **Step 2:** 测试图片区域: GlassCard + ClipRRect(12)
- [ ] **Step 3:** 步骤序号: 圆圈 bg 改 accentColor
- [ ] **Step 4:** "阳性征" 提示: GlassCard, amber(moderateColor) 15% 背景 + icon 改 moderateColor
- [ ] **Step 5:** 答案按钮: pill shape, 保持绿/amber/primaryColor 配色
- [ ] **Step 6:** 运行 `flutter analyze` 确认无错误
- [ ] **Step 7:** Commit

### Task 12: 重写拍照页 (photo_test_screen)

**Files:**
- Modify: `lib/screens/test/photo_test_screen.dart`

- [ ] **Step 1:** 引导态: icon 改 accentColor; 示意区域 GlassCard; 按钮 pill style
- [ ] **Step 2:** 预览态: Image 包裹 ClipRRect(16); 按钮 pill
- [ ] **Step 3:** 分析中: CircularProgressIndicator color accentColor
- [ ] **Step 4:** 运行 `flutter analyze` 确认无错误
- [ ] **Step 5:** Commit

### Task 13: 重写结果页 (result_screen)

**Files:**
- Modify: `lib/screens/result/result_screen.dart`

- [ ] **Step 1:** 顶部 GlassCard: ResultBadge(size: 28) 居中 + suggestion 文字
- [ ] **Step 2:** 纠正建议每项: GlassCard(margin bottom 8), icon 用圆形 container
- [ ] **Step 3:** 相关推荐: 水平 ListView, 每项 GlassCard(width 160)
- [ ] **Step 4:** 运行 `flutter analyze` 确认无错误
- [ ] **Step 5:** Commit

### Task 14: 重写历史记录页 (history_screen)

**Files:**
- Modify: `lib/screens/history/history_screen.dart`

- [ ] **Step 1:** 日期分组标题: 16px semibold, textMuted
- [ ] **Step 2:** 每条记录 GlassCard(margin h16v4, padding 12):
  - Row: colored dot(12px circle, 结果色) + SizedBox(12) + Column(name 15px + method chip) + Spacer + time(caption)
  - method chip: pill(12px radius, primaryColor bg, textMuted text, 小号)
- [ ] **Step 3:** 空态 icon 改 primaryColor, 文字 textMuted
- [ ] **Step 4:** 运行 `flutter analyze` 确认无错误
- [ ] **Step 5:** Commit

### Task 15: 重写个人中心 (profile_screen)

**Files:**
- Modify: `lib/screens/profile/profile_screen.dart`

- [ ] **Step 1:** 头像区: GlassCard(margin h16v8), CircleAvatar(radius 30, bg primaryColor), 手机号 18px bold, "普通用户" textMuted
- [ ] **Step 2:** 基本信息: GlassCard, 行间 Divider(glassBorder), edit icon 色 textMuted
- [ ] **Step 3:** 编辑弹窗内 CupertinoPicker: selectionOverlay border 改 accentColor
- [ ] **Step 4:** 菜单: GlassCard, ListTile leading 用圆形 icon container(accentColor 15% bg)
- [ ] **Step 5:** 退出登录: OutlinedButton, foregroundColor severeColor, side severeColor
- [ ] **Step 6:** 运行 `flutter analyze` 确认无错误
- [ ] **Step 7:** Commit

### Task 16: 重写体态档案页 (posture_profile_screen)

**Files:**
- Modify: `lib/screens/profile/posture_profile_screen.dart`

- [ ] **Step 1:** 每个分类: GlassCard, 标题行(分类名 + "x/n" caption)
- [ ] **Step 2:** 进度条: LinearProgressIndicator(value, color accentColor, bgColor primaryColor), height 6, borderRadius 3
- [ ] **Step 3:** 每个问题行: Row(问题名 + Spacer + colored dot 8px circle)
- [ ] **Step 4:** 运行 `flutter analyze` 确认无错误
- [ ] **Step 5:** Commit

### Task 17: BottomNav 导航栏样式

**Files:**
- Modify: `lib/app.dart`

- [ ] **Step 1:** AppShell Scaffold: `extendBody: true`
- [ ] **Step 2:** NavigationBar: backgroundColor cardColor 85% opacity, elevation 0, indicatorColor accentColor 20%, selectedIconTheme color accentColor, unselectedIconTheme color textMuted, selectedLabelStyle color accentColor, unselectedLabelStyle color textMuted
- [ ] **Step 3:** 运行 `flutter analyze` 确认无错误
- [ ] **Step 4:** Commit

### Task 18: 最终验证

- [ ] **Step 1:** `flutter analyze` 全项目零错误
- [ ] **Step 2:** `flutter run` 验证主流程:
  - 登录页 → 管理员快捷登录 → 首页渲染
  - 首页 → 分类 → 列表 → 详情 → 自测 → 结果
  - 历史记录页 / 个人中心 / 体态档案
- [ ] **Step 3:** 确认无 hardcoded 旧色值残留 (`grep -r "0xFFE94560\|0xFF8892B0\|0xFF0F3460\|0xFF16213E"`)
- [ ] **Step 4:** 更新 `docs/specs/2026-06-01-backend-implementation-status.md` 记录 UI 重设计完成
- [ ] **Step 5:** Commit

---

## 非改动项

- 业务逻辑、Provider、Model、API 层不动
- 后端不动
- 路由结构不动
- 3D 模型资源不动（仍为 astronaut.glb 占位）
- pubspec.yaml 不引入新包

## 风险点

| 风险 | 缓解方案 |
|------|----------|
| `extendBody: true` 导致内容被 nav 遮挡 | 各页面 body 底部统一加 `SizedBox(height: 80)` |
| `withValues(alpha:)` 需 Flutter >= 3.27 | 执行前确认 `flutter --version` |
| GlassCard 半透明背景 + 无 blur 可能视觉单调 | 加 1px glassBorder 增加层次感 |
| 旧颜色 hardcode 遗漏 | Task 3 做全局搜索替换 + Task 18 最终验证 |
