> **⚠️ 历史资料** — 本文档记录早期开发过程，不代表当前完成状态或当前架构决策。
> 当前规格和计划见 [docs/README.md](../README.md)。

# UI Redesign Spec — Light Gray Glassmorphism

## 1. 概述

将体态分析 App 的视觉风格改为 **浅灰色底 + 毛玻璃卡片 + Teal 强调色** 的 Glassmorphism 风格。参考来源为 F1 赛事 App 的设计语言。

**关键特征：这是一个浅色主题（Light Mode），背景为浅灰，文字为深色。**

本次改动为**纯视觉层重构**，不涉及业务逻辑、数据模型、API、路由结构的任何变更。

---

## 2. 设计语言定义

### 2.1 色板（来源于 Branding 色板图）

```
Background:         #D6D8D9   浅灰色，全局底色
Text Primary:       #353D40   深炭灰，主文字
Text Secondary:     #83898C   中灰色，次要文字/说明
Accent Light:       #21E2C2   亮 teal，高亮/装饰
Accent Dark:        #00AA88   深 teal，按钮/主操作
```

### 2.2 派生色

```
Card Glass Light:   #FFFFFF40  白色 25% opacity，浅色毛玻璃卡片
Card Glass Dark:    #353D4080  深色 50% opacity，深色毛玻璃卡片（hero 区域）
Card Border:        #FFFFFF50  白色 30% opacity，卡片微光边框
Surface Dark:       #2A3038   深色表面（底部导航/深色区域）
Divider:            #C8CACC   浅灰分割线
```

### 2.3 语义色

```
Normal (正常):      #00AA88   深 teal（与 accent 同系）
Moderate (需关注):  #E5A100   Amber/Gold
Severe (严重):      #DC3545   Red
```

### 2.4 Glassmorphism 卡片规则

**浅色玻璃卡片（默认）：**

| 属性 | 值 |
|------|------|
| 背景色 | 白色 25% opacity (`#FFFFFF40`) |
| 模糊 | `BackdropFilter(sigmaX: 12, sigmaY: 12)` |
| 边框 | 1px solid 白色 30% (`#FFFFFF50`) |
| 圆角 | 20px |
| 阴影 | 无 |
| 内边距 | 20px 默认 |

**深色玻璃卡片（hero/强调区域）：**

| 属性 | 值 |
|------|------|
| 背景色 | `#353D40` at 50% opacity |
| 模糊 | `BackdropFilter(sigmaX: 12, sigmaY: 12)` |
| 边框 | 1px solid 白色 10% (`#FFFFFF1A`) |
| 圆角 | 20px |
| 阴影 | 无 |

### 2.5 排版层级

| 级别 | 字号 | 字重 | 颜色 | 用途 |
|------|------|------|------|------|
| Display | 36-48px | Bold | textPrimary | 大数字展示 |
| H1 | 28px | Bold | textPrimary | 页面主标题 |
| H2 | 20px | SemiBold | textPrimary | 区域标题 |
| Body | 15-16px | Regular | textPrimary | 正文内容 |
| Caption | 12-13px | Regular | textSecondary | 辅助说明 |
| Unit | 14-16px | Regular | textSecondary | 数字单位 |

### 2.6 按钮规范

| 类型 | 填充 | 文字 | 圆角 | 高度 |
|------|------|------|------|------|
| Primary | `accentDark` (#00AA88) solid | White 16px bold | 24px | 52px |
| Secondary | transparent, border accentDark | accentDark 15px | 24px | 48px |
| Ghost | transparent | textSecondary 14px | 24px | 44px |
| Danger | transparent, border red | severeColor | 24px | 48px |

### 2.7 Icon 容器

- 圆形，大小 48x48 / 40x40 / 32x32
- 背景：accentDark at 12% opacity
- Icon 颜色：accentDark

### 2.8 进度条

- Track：#C8CACC（浅灰）
- Active：accentDark (#00AA88) 或 accentLight (#21E2C2)
- 高度：4-6px，圆角 3px

### 2.9 Chip/Tag

- Active：accentDark fill, white text
- Inactive：白色玻璃背景(#FFFFFF40), textSecondary text
- 圆角 12px，高度 28-32px

### 2.10 Dialog

- 背景：白色 85% opacity + blur
- 圆角：20px
- 文字：textPrimary

### 2.11 SnackBar

- 背景：surfaceDark (#2A3038)
- 文字：white
- 圆角：12px, floating

### 2.12 底部导航栏

- 背景：surfaceDark (#2A3038) at 95% opacity + blur
- 选中：accentLight (#21E2C2)
- 未选中：#83898C
- 文字同色

---

## 3. 各页面设计说明

### 3.1 登录页

- 浅灰背景
- 顶部：App icon（teal）+ 标题(H1, textPrimary) + 副标题(textSecondary)
- 中间：浅色 GlassCard 包裹表单
- 按钮：Primary teal pill
- 开发区：浅色 GlassCard muted

### 3.2 引导页

- 浅灰背景
- 进度条：teal accent
- Picker 区域：浅色 GlassCard 包裹
- 性别卡片：浅色 GlassCard，选中态 border 改 teal + teal 填充 8%

### 3.3 首页

- 浅灰背景
- 3D 模型区域：深色 GlassCard（类似 F1 左屏 hero 效果）
- 分类导航：横排 icon 按钮
- 体态档案入口：浅色 GlassCard

### 3.4-3.11 其他页面

- 统一浅灰背景
- 所有信息区域使用浅色 GlassCard
- 红旗征/严重区域使用 severeColor 淡背景
- 列表行间用浅色 GlassCard 或白玻璃行

### 3.12 底部导航栏

- 深色毛玻璃底(surfaceDark 95%)
- teal 选中态

---

## 4. 全局颜色使用规则

**绝对规则：整个 App 只允许出现以下颜色家族**

| 用途 | 允许的颜色 | 禁止 |
|------|----------|------|
| 背景 | `bgColor` (#D6D8D9) | 纯黑、深蓝 |
| 卡片/容器 | 白色半透明(glass)、深色半透明(dark glass) | 不透明深色、实色卡片 |
| 主文字 | `textColor` (#353D40) | 白色（除深色容器内） |
| 次要文字 | `textMuted` (#83898C) | 比 #83898C 更浅的灰色 |
| 主操作/强调 | `accentColor` (#00AA88) / `accentLight` (#21E2C2) | 红色、粉色、蓝色 |
| 分割线/边框 | `dividerColor` (#C8CACC) / `glassBorder` (白30%) | 深色实线 |
| 结果语义色 | 仅用于**评估结果标识**：normal/moderate/severe | 不用于按钮、菜单、装饰 |

**severeColor(红色) 使用限制：**
- 仅允许：评估结果 badge、红旗征区域背景
- **禁止：** 退出按钮、菜单 icon、任何常规 UI 元素

### 4.1 文字对比度规则

| 文字位置 | 颜色 | 说明 |
|---------|------|------|
| 浅灰背景上的标签/按钮文字 | `textColor` (#353D40) | 必须高对比可读 |
| 浅灰背景上的辅助信息 | `textMuted` (#83898C) | 仅用于时间戳/说明 |
| 毛玻璃卡片内 | `textColor` (#353D40) | 高对比 |
| 深色容器内 | 白色 / accentLight | 高对比 |

**关键：任何用户需要阅读的文字（标签、分类名、按钮文字）必须用 `textColor`。`textMuted` 仅限非关键辅助信息。**

### 4.2 组件颜色一致性

| 组件 | 规范 |
|------|------|
| 菜单项 icon | `accentColor`，圆形容器 accent 12% 背景 |
| 列表箭头 (chevron) | `textMuted` |
| 编辑 icon | `textMuted` |
| 退出登录按钮 | Ghost 样式：`textMuted` 文字 + `dividerColor` 边框，不用红色 |
| 分类按钮 label | `textColor`（深色，确保可读） |
| 分类按钮 icon | `accentColor` |
| 分类按钮容器 | GlassCard 毛玻璃 |
| 头像容器 | CircleAvatar bg = accentColor 12% |
| CupertinoPicker overlay | `accentColor` 线 |
| 进度条 | track: `dividerColor`, active: `accentColor` |

---

## 5. 不改动的部分

- Provider / StateNotifier / API 逻辑
- 数据模型
- 路由结构
- 后端
- pubspec.yaml 不引入新包

---

## 6. 技术约束

- 使用 `BackdropFilter` + `ImageFilter.blur(sigmaX: 12, sigmaY: 12)` 实现毛玻璃
- GlassCard 组件内部用 `ClipRRect` + `BackdropFilter` + 半透明 Container
- 这是 **Light Mode** (Brightness.light)
- 颜色统一走 AppConstants
- `withOpacity()` 已废弃，使用 `withValues(alpha:)`
