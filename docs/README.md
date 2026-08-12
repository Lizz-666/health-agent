# 文档导航

> 日期：2026-07-11
> 当前阶段：阶段 0 已完成，下一步为阶段 1 规格设计（真实 PostgreSQL 迁移演练、真实后端 API 和 Android 完整业务冒烟全部通过；APK 构建日志无 KGP 兼容性警告）

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

2026-06-01 至 2026-06-10 的早期计划、规格和状态记录已被当前产品文档、阶段 0 基线文档、阶段 1 体态核心产品化文档和代码实现覆盖。为减少模型检索噪音和旧 agent 指令误读，这批历史文件已从工作树移除；需要追溯时查看 git 历史。

## 当前验证状态

2026-07-11 验证结果：

| 验证项 | 结果 |
| --- | --- |
| 后端 pytest | 81 passed |
| Alembic 离线 upgrade/downgrade SQL | 通过（PostgreSQL 方言，含 3 表、索引、外键） |
| 真实 PostgreSQL 迁移演练 | 通过（upgrade/downgrade base/re-upgrade + schema/索引/外键核验） |
| Flutter analyze | No issues found |
| Flutter test | 7 passed |
| Pixel_6 模拟器启动 | 成功（emulator-5554, Android 14 API 34） |
| 当前源码 APK 构建 | 成功 — `flutter build apk --debug`，app-debug.apk，构建日志无 KGP 兼容性警告 |
| 真实后端 API 流程 | 通过（health/send-code/verify-login/issues/detail/assess/history，数据真实持久化到 PG） |
| Android 核心业务流程验收 | 通过（登录→问题列表→详情→图示自测→结果→历史，真实后端 + 真实 PG） |

## 未解决阻塞项

无。阶段 0 验收标准 1-9 全部满足。

### 已解决

- **APK 构建阻塞（原记为“Gradle 依赖下载停滞”）**：根因实为 Windows 未启用 Developer Mode，Flutter 在 Gradle 启动前的插件 symlink 创建阶段报 “Building with plugins requires symlink support” 而中止，Gradle 从未运行。启用 Developer Mode 后 `flutter build apk --debug` 成功。
- **数据库迁移真实演练**：Task 9 在真实 PostgreSQL（Docker `postgres:16`）上完成 upgrade/downgrade base/re-upgrade 闭环并核验 schema。
- **Android 完整业务冒烟**：Task 9 在真实后端 + 真实 PG 上完成登录→问题→详情→自测→结果→历史六页流程。
- **APK 构建 KGP 兼容性警告**：`image_picker_android` 0.8.13+17 会触发 Flutter 的“applies Kotlin Gradle Plugin / Future versions of Flutter will fail to build”警告；通过 `flutter pub upgrade image_picker_android` 升级到 0.8.13+19（仅此一个传递依赖变动），`flutter build apk --debug` 日志中该警告已消失。

## 已知限制

- Android cmdline-tools 缺失，`flutter doctor --android-licenses` 无法执行（工具链告警，不阻塞构建或模拟器）
- 照片分析默认关闭，启用需要先完成隐私门
- 当前仅支持体态问题浏览、图示自测和评估历史
- 开发登录依赖后端 DEV_MODE=true 和 SMS 验证码模拟，后端必须使用可连接的数据库运行
- 详情页首次加载偶现"加载失败"，重试后恢复
- 历史页登录后首次进入且评估记录为空时不提供下拉刷新入口

## 运行时版本

| 工具 | 版本 |
| --- | --- |
| Python | 3.12.13（Phase 9 候选；Phase 0 历史基线为 3.9.13） |
| Flutter | 3.44.0 |
| Dart | 3.12.0 |
| Java | 21.0.10 |
| Android SDK | 36.1.0 |
| 后端测试数 | 81 |
| Flutter 测试数 | 7 |
