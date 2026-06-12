# 首页 UI 重构 + 搜索增强 Spec

> 版本: v1.1
> 日期: 2026-06-10
> 原因: 3D 模型效果不达预期，改为仪表盘卡片布局；搜索页增加热门问题

---

## 1. 改动范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `screens/home/home_screen.dart` | **重写** | 去掉 3D + model_viewer_plus，改为仪表盘布局 |
| `screens/search/search_screen.dart` | **增强** | 增加热门标签云 + 分类 Tab |
| `widgets/body_region_button.dart` | 退役 | 不再使用，保留文件不删 |
| `pubspec.yaml` | 清理 | 移除 model_viewer_plus 依赖 |
| `assets/models/` | 清理 | 删除 human_body.glb 和 astronaut.glb |

**不影响**：路由、Provider、其他页面、底部导航栏均不变。

---

## 2. 首页布局

### 2.1 AppBar

标题: "体态分析"
右侧: IconButton 搜索（→ `/search`）+ IconButton 档案（→ `/profile/posture`）

### 2.2 统计卡片区

首页正文 ScrollView 顶部，横向 Row 两张卡片：

| | 左卡 | 右卡 |
|------|------|------|
| 标题 | "已评估" | "⚠ 需关注" |
| 大字 | `assessedCount` | `needAttentionCount` |
| 副文 | "/ 26 项" | "个问题" |
| 点击 | → `/profile/posture` | → `/profile/posture` |

**数据计算**（从 Provider 实时拉取）：

```dart
final postureStates = ref.watch(postureStateProvider);
final assessedCount = postureStates.length;
final needAttentionCount = postureStates.values.where(
  (s) => s.result == 'moderate' || s.result == 'severe'
).length;
```

**空状态**：已评估=0，需关注=0，正常显示 0，不需要特殊处理。

### 2.3 区域卡片列表

5 张 GlassCard，每张一行内容：

| # | 图标 | 标题 | 副标题（预览问题名） | 右侧 badge | 点击 |
|:--:|:--:|------|------|------|------|
| 1 | 🦴 | 头颈部 | 前 3 个 issue.nameCn，逗号分隔 | 已评数/总数 | `/issues/head_neck` |
| 2 | 🫁 | 肩胸区 | 同上 | 同上 | `/issues/shoulder_thorax` |
| 3 | 🦿 | 骨盆腰椎 | 同上 | 同上 | `/issues/pelvis_spine` |
| 4 | 🦵 | 下肢区 | 同上 | 同上 | `/issues/lower_limb` |
| 5 | 📋 | 综合评估 | 同上 | 同上 | `/issues/compound` |

**数据计算**：

```dart
final issues = ref.watch(issueProvider).issuesByCategory[category] ?? [];
final assessedInCat = issues.where(
  (i) => postureStates.containsKey(i.id)
).length;
final previewNames = issues.take(3).map((i) => i.nameCn).join('、');
```

**已全部评估完**：该卡片右侧 badge 文字改为 "✓ 7/7" 绿色。

**空状态**：已评估=0 组显示 "0/3"、"0/7" 等。

### 2.4 底部 Disclaimer

固定底部 DisclaimerBanner。

---

## 3. 搜索页增强

### 3.1 热门标签云（搜索框为空时显示）

```
┌──────────────────────────┐
│  骨盆前倾  圆肩  头前倾   │
│  驼背  肋骨外翻  X型腿   │
│  脊柱侧弯  扁平足  膝超伸 │
└──────────────────────────┘
```

- **9 个固定热门问题**：骨盆前倾、圆肩、头前倾、驼背、肋骨外翻、X型腿、脊柱侧弯、扁平足、膝超伸
- 样式：Glass 风格 Chip，`Wrap` 布局，圆角
- 点击 → `context.push('/issue/${issue.id}/detail')`

### 3.2 分类 Tab

热门标签下方，横向可滚动的 `Wrap` 或小号 Chip 行：

```
  [全部] [头颈] [肩胸] [骨盆] [下肢] [综合]
```

- 选中态高亮（AccentColor）
- 点击 → 下方搜索结果按分类过滤
- Tab 过滤不影响上方的热门标签云

### 3.3 搜索框交互

- 输入文字 → 标签云隐藏，Tab 隐藏，实时过滤列表（已有功能）
- 清空输入 → 恢复标签云 + Tab
- 搜索逻辑：匹配 issue.nameCn、aliases、definition

---

## 4. 清理项

| 项目 | 操作 |
|------|------|
| `pubspec.yaml` | 删除 `model_viewer_plus: ^1.10.0` |
| `assets/models/human_body.glb` | 删除 |
| `assets/models/astronaut.glb` | 删除 |
| `assets/models/` 目录 | 删除（空目录清理） |
| `pubspec.yaml` assets 配置 | 删除 `- assets/models/` 行 |

---

## 5. 兼容性

- GoRouter 路由不变
- Provider API 不变
- 底部导航不变
- 只替换 HomeScreen 和增强 SearchScreen
