# 文档导航

> 日期：2026-07-10
> 当前阶段：阶段 0 基线收敛（未完成 — PostgreSQL schema 初始化缺失；Android 当前源码验收未完成）

## 当前产品文档

| 文档 | 职责 |
| --- | --- |
| [product/vision.md](product/vision.md) | 产品定义、核心原则和信息架构 |
| [product/safety-boundaries.md](product/safety-boundaries.md) | 安全边界、风险分级和数据隐私 |
| [product/roadmap.md](product/roadmap.md) | 阶段总览和退出标准 |

## 当前规格

| 文档 | 职责 |
| --- | --- |
| [specs/platform/2026-06-12-baseline-contract.md](specs/platform/2026-06-12-baseline-contract.md) | 阶段 0 开发基线收敛规格 |

## 当前实施计划

| 文档 | 职责 |
| --- | --- |
| [plans/platform/2026-06-12-baseline-convergence.md](plans/platform/2026-06-12-baseline-convergence.md) | 阶段 0 任务清单和执行规则 |

## 历史资料

以下文档记录了早期开发过程，不代表当前完成状态或当前架构决策。保留用于追溯历史上下文。

### 历史计划

| 文档 | 原始日期 | 内容 |
| --- | --- | --- |
| [plans/2026-06-01-backend-revised.md](plans/2026-06-01-backend-revised.md) | 2026-06-01 | 后端 API 初始实施计划 |
| [plans/2026-06-01-posture-app-plan-v2.md](plans/2026-06-01-posture-app-plan-v2.md) | 2026-06-01 | Flutter 前端初始实施计划 |
| [plans/2026-06-04-ui-redesign-glassmorphism.md](plans/2026-06-04-ui-redesign-glassmorphism.md) | 2026-06-04 | UI 重设计实施计划（已执行） |

### 历史规格与状态

| 文档 | 原始日期 | 内容 |
| --- | --- | --- |
| [specs/2026-06-01-backend-implementation-status.md](specs/2026-06-01-backend-implementation-status.md) | 2026-06-01 | 后端 MVP 进展与踩坑记录 |
| [specs/2026-06-01-posture-frontend-design.md](specs/2026-06-01-posture-frontend-design.md) | 2026-06-01 | 体态模块 Flutter 前端设计 |
| [specs/2026-06-04-ui-redesign-spec.md](specs/2026-06-04-ui-redesign-spec.md) | 2026-06-04 | UI Glassmorphism 重设计规格 |
| [specs/2026-06-10-home-redesign.md](specs/2026-06-10-home-redesign.md) | 2026-06-10 | 首页重构和搜索增强规格 |

## 当前验证状态

2026-07-10 验证结果：

| 验证项 | 结果 |
| --- | --- |
| 后端 pytest | 69 passed |
| Flutter analyze | No issues found |
| Flutter test | 7 passed |
| Pixel_6 模拟器启动 | 成功（emulator-5554, Android 14 API 34） |
| 当前源码 APK 构建 | **未完成** — `flutter build apk --debug` 在验证时限内未完成，Gradle 依赖下载停滞 |
| Android 核心流程验收 | **未执行** — 未生成当前源码 APK |

## 未解决阻塞项

- **APK 构建未完成**：`flutter build apk --debug` 在验证时限内未完成，Gradle 依赖下载停滞；根因和解决方案待后续任务调查
- **后端无数据库初始化方式**：Alembic 已在 requirements.txt 但从未执行 `alembic init`，无 migration 文件，`main.py` 无 `create_all`；新开发者无法在 PostgreSQL 上创建 schema（需要后续任务实现）
- Android cmdline-tools 缺失，`flutter doctor --android-licenses` 无法执行（工具链告警，不阻塞模拟器启动）

## 已知限制

- 照片分析默认关闭，启用需要先完成隐私门
- 当前仅支持体态问题浏览、图示自测和评估历史
- 开发登录依赖后端 DEV_MODE=true 和 SMS 验证码模拟，后端必须使用可连接的数据库运行

## 运行时版本

| 工具 | 版本 |
| --- | --- |
| Python | 3.9.13 |
| Flutter | 3.44.0 |
| Dart | 3.12.0 |
| Java | 21.0.10 |
| Android SDK | 36.1.0 |
| 后端测试数 | 69 |
| Flutter 测试数 | 7 |
