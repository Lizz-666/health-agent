# 开发基线收敛规格

> 日期：2026-06-12
> 状态：当前规格
> 对应路线图：阶段 0

## Outcome

建立一个可重复启动、可验证、默认只处理合成数据的 Flutter + FastAPI 开发基线，使后续体态产品化工作不再依赖硬编码配置、隐式运行环境、无类型 API 或不安全的 AI 降级行为。

## Non-Goals

- 不新增训练、营养或 Agent 功能
- 不实现公开发布所需的完整同意和隐私中心
- 不启用真实用户照片或真实健康数据测试
- 不更换 FastAPI、Riverpod、SQLAlchemy 或数据库架构
- 不重构现有体态知识库内容

## Current Evidence

2026-06-12 初始验证结果：

- Python `3.9.13`
- Flutter `3.44.0`
- Dart `3.12.0`
- Java `21.0.10`
- 后端测试：`15 passed`
- Flutter analyze：`No issues found`
- Flutter 测试：`1 passed`
- Android SDK `36.1.0` 已发现，存在 `Pixel_6` 模拟器
- Android command-line tools 缺失，license 状态未知，当前无 Android 设备连接

2026-07-10 Task 1-5 完成、Task 6 文档整理后验证结果：

- Python `3.9.13`
- Flutter `3.44.0`
- Dart `3.12.0`
- Java `21.0.10`
- 后端测试：`69 passed`（含 OpenAPI 契约、照片门禁、AI 校验、响应形状）
- Flutter analyze：`No issues found`
- Flutter 测试：`7 passed`（含配置、照片门禁组件、widget）
- Android SDK `36.1.0`，Emulator `36.6.11.0`
- Pixel_6 模拟器：可启动（`emulator-5554`，Android 14 API 34）
- Android toolchain 告警：cmdline-tools 缺失，license 状态未知
- 当前源码 APK：`flutter build apk --debug` 在验证时限内未完成（Gradle 依赖下载停滞）
- Android 核心流程验收：**未执行**（未生成当前源码 APK）
- 后端生产数据库初始化：**无支持方式**（Alembic 已安装但未配置，无 migration）

2026-07-10 Task 7（Alembic schema 初始化闭环）验证结果：

- 新增 `backend/alembic.ini`、`backend/alembic/env.py`、`backend/alembic/script.py.mako`
- 新增初始 migration `0001_initial_schema`，覆盖 users / verification_codes / posture_assessments，含 PostgreSQL UUID、JSONB、主键、外键、唯一索引（users.phone）和索引
- `alembic.ini` 不含数据库凭据；URL 由 `env.py` 从 `settings.DATABASE_URL` 注入
- FastAPI 启动不调用 `Base.metadata.create_all`（保持不变）
- `python -m alembic heads` → 单一 head `0001_initial_schema`
- `python -m alembic upgrade head --sql` → PostgreSQL 方言 SQL，含 3 表、索引、外键
- `python -m alembic downgrade head:base --sql` → 反序删除索引与表
- `python -m pytest tests/test_migrations.py -q` → 12 passed
- `python -m pytest tests -q` → 81 passed
- 真实 PostgreSQL upgrade / downgrade / re-upgrade 演练：**未执行**（本机无可丢弃 PostgreSQL，且未安装外部服务）

2026-07-11 Task 8（Android 当前源码 APK 构建阻塞）验证结果：

- 根因：**并非 Gradle 依赖下载停滞**。`flutter build apk --debug -v` 显示构建在 Gradle 启动前中止，报 “Building with plugins requires symlink support / Please enable Developer Mode”。Flutter 在插件 symlink 创建阶段（`flutter_plugins.dart` `_createPlatformPluginSymlinks`）因 Windows 未启用 Developer Mode 而 `throwToolExit`，`assembleDebug` 从未运行。
- 证据补充：Gradle 9.1.0 发行版已完整缓存（`.ok` 标记存在）；dl.google.com / Maven Central / Gradle Plugin Portal 的 curl HEAD 均可达（含 `--noproxy`）；仓库 Gradle 9.1.0 / AGP 9.0.1 / Kotlin 2.3.20 与 Flutter 3.44.0 模板默认值完全一致（`gradle_utils.dart` `templateDefaultGradleVersion=9.1.0`、`templateAndroidGradlePluginVersion=9.0.1`、`templateKotlinGradlePluginVersion=2.3.20`），非版本不兼容。
- 处置：启用 Windows Developer Mode（`AllowDevelopmentWithoutDevLicense=1`，通过 UAC 提升，用户批准）。未修改仓库 Android 配置、未硬编码镜像、未写入代理。
- `flutter build apk --debug` → 成功，Gradle 完整下载依赖并 `assembleDebug`（410.9s），生成 `app/build/app/outputs/flutter-apk/app-debug.apk`。
- APK：155,855,333 bytes，SHA-256 `b59f29eeea0190c0b51489baf9c4b0335d13bb1b8809b10f4eb4460c0f4dd9b7`，构建时间 2026-07-11 10:03:52 +0800。
- 安装/启动：`adb install -r` 到 `emulator-5554`（先卸载旧 APK）；`am start com.health.posture_app/.MainActivity` 启动无崩溃；`dumpsys package` `lastUpdateTime=2026-07-11 02:06:37`（本次安装，非 2026-06-10 旧 APK）；截图确认登录页可见（体态分析 / 手机号 / 验证码 / 发送验证 / 登录 / 首次验证将自动注册账号）。
- 完整业务冒烟（登录→问题→详情→自测→结果→历史）：**未执行**，依赖可连接的真实后端与 PostgreSQL；照片分析保持默认关闭，未传 `PHOTO_ANALYSIS_ENABLED=true`。

已修复的基线缺口（Task 1-5）：

- [x] Flutter API 地址硬编码 → 改为 `--dart-define` 可配置
- [x] 体态路由缺少 response model → 6 路由全部声明 Pydantic response_model
- [x] pytest 和 Pydantic 弃用警告 → 已消除
- [x] 真实照片路径无隐私门 → 前后端默认关闭，后端为最终边界
- [x] AI JSON 解析失败降级为 normal → 全部返回 503，不落库
- [x] 旧计划和旧状态文档无标记 → 全部加注历史资料标记

未解决的阻塞项：

- Android 完整业务冒烟未完成：当前源码 APK 已成功构建、安装、启动到登录页（无崩溃），但登录→问题→详情→自测→结果→历史流程依赖可连接的真实后端与 PostgreSQL，本机无可丢弃 PostgreSQL，未执行。不得据此判定“Android 核心流程通过”
- 数据库 schema 初始化：Alembic 已配置且离线 SQL 已验证，但真实 PostgreSQL 的 upgrade / downgrade / re-upgrade 演练尚未执行；演练通过前该初始化闭环视为“仅离线验证”，blocker 未完全移除
- Android cmdline-tools 缺失，`flutter doctor --android-licenses` 无法执行（工具链告警，不影响模拟器启动或构建）
- 退出标准第 1 条（新环境可按命令启动前后端）依赖真实 PostgreSQL 迁移演练，第 7 条（Android 冒烟）需完整业务流程真实完成，均未满足

已移除的阻塞项：

- ~~`flutter build apk --debug` 在验证时限内未完成，Gradle 依赖下载停滞~~ → Task 8 定位根因为 Windows 未启用 Developer Mode 导致插件 symlink 创建中止（非 Gradle 下载问题）；启用后当前源码 APK 构建成功并安装启动，该 blocker 移除

## Users And Scenarios

- 开发者可按根目录文档启动后端并运行 Flutter
- Claude Code 可在不猜测环境和命令的情况下执行单个任务
- 本地测试默认只使用合成账号、合成档案和占位图片
- 未完成照片隐私门时，客户端和后端都拒绝真实照片分析
- AI 服务超时、异常或返回无效结构时，系统显示明确失败且不落库

## Runtime And Configuration Contract

阶段 0 继续支持 Python 3.9，不引入要求 Python 3.10 以上的新语法。

Flutter 通过编译参数读取：

```text
API_BASE_URL
PHOTO_ANALYSIS_ENABLED
```

后端通过环境变量读取：

```text
PHOTO_ANALYSIS_ENABLED=false
```

约束：

- `API_BASE_URL` 未提供时可保留 Android 模拟器开发默认值
- 照片分析在前后端都必须显式启用，后端是最终授权边界
- 密钥不得通过 Flutter `--dart-define` 传递
- `.env.example` 只包含占位值，不包含真实凭据

## API And State Contracts

所有当前体态路由必须声明 Pydantic response model：

- `GET /api/v1/posture/issues`
- `GET /api/v1/posture/issues/{issue_id}`
- `GET /api/v1/posture/issues/{issue_id}/related`
- `POST /api/v1/posture/assess`
- `POST /api/v1/posture/assess/photo`
- `GET /api/v1/posture/history`

响应字段名称保持与现有 Flutter 模型兼容。

当照片分析未启用时：

```json
{
  "detail": "照片分析在当前数据模式下未启用",
  "code": "photo_analysis_disabled"
}
```

对应上传凭证和照片评估接口均返回 `503`，且不得生成凭证、签名 URL、模型请求或数据库记录。

当模型不可用、超时、响应无法解析或不符合 schema 时：

- 返回明确的 `503`
- 不把缺失字段补成 `normal`
- 不保存评估记录
- 不在日志中记录照片地址、用户健康档案或完整模型响应

## Safety, Privacy, And Failure Handling

- 阶段 0 默认只使用合成数据
- 照片分析默认关闭
- 当前阶段不以免责声明替代隐私门
- 无效 AI 输出不得转化为健康或正常结论
- 后端开关不能被客户端参数绕过
- 任何失败都不能形成半落库状态

## Observability And Audit

允许日志记录：

- 请求失败类型
- 上游状态码
- schema 校验失败类别
- 请求关联标识

禁止日志记录：

- 原始健康档案
- 原始模型响应
- 照片对象地址或签名 URL
- Token、云服务密钥和模型密钥

## Acceptance Criteria

1. 根目录存在当前有效的运行和验证命令。
2. 后端测试、Flutter analyze 和 Flutter 测试通过且无当前已知弃用警告。
3. Flutter API 地址可通过 `--dart-define` 覆盖。
4. 照片上传和分析默认在前后端关闭。
5. AI 失败或无效输出不会产生 `normal` 结果或数据库记录。
6. 当前体态 API 具有 OpenAPI 可见的 response schema。
7. Android 模拟器完成一次登录、问题浏览和图示自测冒烟流程。
8. 旧计划和旧状态文档明确标记为历史资料。
9. 阶段 0 的验证证据和未解决限制被记录。

## Test And Evaluation Strategy

- 后端：完整 pytest、OpenAPI schema、照片门禁、AI 无效输出和无落库回归测试
- Flutter：配置单元测试、照片关闭状态组件测试、完整 analyze 和 test
- 集成：后端 `/health`、登录、问题列表、自测和历史接口
- Android：`Pixel_6` 模拟器手工冒烟
- 数据：只使用合成账号、合成档案和占位图片

## Rollout

所有改变仅作用于开发基线。照片能力保持默认关闭，直到后续规格完成告知、同意、真实 STS、保存期限和删除策略。任何任务失败时，回滚该任务对应提交，不跨任务混合回滚。
