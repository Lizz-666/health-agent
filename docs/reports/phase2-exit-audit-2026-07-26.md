# Phase 2 Exit Audit — Health Profile, Check-Ins, and Trends

> 审计日期：2026-07-26
> 审计者：OpenCode 验证 Agent + Codex 复核/收敛
> 规格：`docs/specs/platform/2026-07-22-health-profile-checkins-trends.md`
> 计划：`docs/plans/platform/2026-07-22-health-profile-checkins-trends.md`（Task 8）
> 基线分支：`codex/phase2-task8-phase2-exit-audit`，Base SHA `26f785f`（Tasks 1–7 已合并于 `codex/phase2-spec-plan`）
> 路线图：`docs/product/roadmap.md` §6

## 总结论

**阶段 2 自动化验证全部通过，PostgreSQL 16 真实迁移/集成通过，Android Pixel 6 AVD 已完成构建、安装、启动证据，Phase 2 业务流由 HTTP 实时旅程 + Flutter widget tests 覆盖。** 经用户决策（2026-07-26 Final Closure，见文末），**Android 人工逐屏冒烟由用户决定跳过**（接受的残余风险），Phase 2 收敛为**完成**。本审计未 push、未发布。

- 后端：`798 passed`（含真实 PostgreSQL 16 集成路径，0 skipped）；新增 Phase 2 E2E `6 passed`。
- Flutter：`flutter analyze` 无问题；`flutter test` `300 passed`。
- PostgreSQL：Docker Desktop 启动后可用，`test_pg_integration.py` `11 passed`（真实 PG16，UUID/JSONB/advisory lock），并用一次性 `postgres:16` 容器独立执行裸 CLI `alembic upgrade head` / `alembic current` 至 `0006`。
- ruff：Codex 复核阶段清理 13 个预存 lint 问题后，`python -m ruff check app tests` 通过。
- Android：Task 8B 在 Pixel 6 AVD 上完成真实 `flutter run` 构建、安装、启动（MainActivity resumed）；业务流由一次性 PG16/uvicorn HTTP 实时旅程 15/15 + 300 widget 测试覆盖。Android 人工逐屏业务回放由用户决定跳过并接受为残余风险。

## 修改文件

- `backend/tests/test_phase2_e2e.py`（**新增**，6 个用例：迁移头/Schema、完整用户旅程、restricted 路由、跨用户隔离/账号切换、隐私无原始敏感值）
- `backend/tests/test_openapi_contracts.py`（**未改**：核验后 Phase 2 全部 health 路由已覆盖，无缺口）
- `docs/reports/phase2-exit-audit-2026-07-26.md`（本文件，新增）
- 仅状态登记/澄清：`docs/agent/ACTIVE_TASKS.md`、`docs/product/roadmap.md` §6、`docs/specs/.../2026-07-22-...md`、`docs/plans/.../2026-07-22-...md`、`README.md`（测试状态表与阶段行）
- Codex ruff 收敛（机械性 lint 修复）：`backend/app/auth/service.py`、`backend/app/main.py`、`backend/app/posture/purge.py`、`backend/app/posture/safety.py`、`backend/tests/conftest.py`

## 证据表

| # | 命令 | 工作目录 | 退出码 | 关键结果 |
| --- | --- | --- | --- | --- |
| 1 | `python -m pytest -q` | `backend/` | 0 | **798 passed**，0 failed，0 skipped（含真实 PG16 集成） |
| 2 | `python -m pytest tests/test_phase2_e2e.py tests/test_openapi_contracts.py tests/test_migrations.py -q` | `backend/` | 0 | **137 passed**（其中新增 Phase 2 E2E 6 项） |
| 3 | `python -m pytest tests/test_pg_integration.py -q -rs` | `backend/` | 0 | **11 passed**，0 skipped（真实 PostgreSQL 16；UUID/JSONB/advisory lock） |
| 4 | `python -m alembic heads` | `backend/` | 0 | 单一头 `0006_health_weight_tracking` |
| 5 | `python -m alembic upgrade head && python -m alembic current`（一次性 PG16 容器，显式 `DATABASE_URL`） | `backend/` | 0 | 升级链 `0001`→`0006` 成功；`current` 输出 `0006_health_weight_tracking (head)` |
| 6 | `python -m ruff check app tests` | `backend/` | 0 | All checks passed（13 个预存 lint 问题已由 Codex 机械性清理） |
| 7 | `python -m compileall app -q` | `backend/` | 0 | 干净 |
| 8 | `flutter analyze --no-pub` | `app/` | 0 | No issues found |
| 9 | `flutter test --no-pub` | `app/` | 0 | **300 passed** |
| 10 | `flutter emulators` | `app/` | 0 | 可列出 `Pixel_6` Android AVD |
| 11 | Android 构建/启动（Task 8B） | `app/` + Pixel 6 AVD | 0 | `flutter run` 构建、安装、启动；`com.health.posture_app/.MainActivity` resumed |
| 12 | 一次性 HTTP 旅程脚本（Task 8B） | `backend/` | 0 | **15/15 checks PASSED**（登录、健康档案、签到、abnormal/red_flag、体重、趋势/网格、账号切换、删除） |

> SHA：Task 8 自动化/PG 证据采集于 `26f785f` 工作树 `health-worktrees/phase2-task8-phase2-exit-audit` 加本任务变更（新增 E2E、文档与 Codex ruff 清理）；Task 8B Android 启动与 HTTP 旅程证据采集于 `351ce81` 工作树 `health-worktrees/phase2-task8b-android-smoke`。Final Closure 文档收敛基于主线 `4a26b0c`，无代码变更；验证后若再发生实质代码改动，相关证据即失效。

## Android 冒烟结果

Task 8B 已补充目标平台启动证据：Pixel 6 AVD（Android 14/API34）真实 `flutter run` 构建、安装并启动 App，`adb dumpsys` 确认 `com.health.posture_app/.MainActivity` 前台运行。截图产物位于 `%LOCALAPPDATA%\Temp\opencode\smoke-01-login.png`，作为人工核验产物；本模型未目视核验截图。

业务路径未通过 Android App 人工逐屏点击回放；用户在 2026-07-26 明确决定跳过该人工逐屏冒烟并接受残余风险。业务流由一次性 PostgreSQL 16 + uvicorn 的 HTTP 实时旅程（15/15）和 Flutter widget 测试（300 passed）覆盖。该结论不得写作“Android 人工逐屏冒烟通过”。

## 路线图 §6 退出标准逐条核对

| §6 退出标准 | 判定 | 证据 |
| --- | --- | --- |
| 缺失数据不会被 AI 自动猜测 | **PASS**（自动化） | 后端：not-configured 显式 `missing_required_data`+`missing_fields`；E2E 断言缺失字段被命名、空值保持空（`test_e2e_phase2_full_user_journey`）。Phase 2 全程无 AI/推荐生成（规格 Domain Model）。 |
| 用户可在 20 秒左右完成普通签到 | **PASS（功能）/ 时序未人工计时** | Flutter：`today_checkin_test.dart` 普通路径一键提交（合理默认值）；后端 PUT normal → `risk_summary=normal`。20 秒时序未在目标平台人工计时；用户决定跳过 Android 人工逐屏回放并接受该残余风险。 |
| 体重趋势不依据单日波动给出调整 | **PASS** | 后端：`sufficient=false` 时 `trend=[]` 且无 advice/warning/adjustment/verdict 字段（E2E 断言）；Flutter 体重页“数据不足”横幅不渲染趋势。 |
| 切换账号或退出后不残留上一用户的健康数据 | **PASS**（自动化） | 后端：`test_e2e_cross_user_isolation_account_switch`——B 账号 profile/checkin/weight/grid 全空；跨用户删除 404 `not_found`，A 数据仍在。Flutter：`auth_session_reset_test.dart` 覆盖 logout/token failure/account-switch/parse-failure 清空。 |
| 用户可查阅、更正和删除真实健康档案，保存期限规则可验证 | **PASS** | 后端：GET/PUT/DELETE profile；E2E 删除后 GET 回到 not-configured（保留期=删除即移除用户可关联值）；Flutter 健康档案页查看/更正/删除确认。 |

> 跨阶段质量门（§13）相关项：普通/谨慎/受限/红旗案例（E2E + 单测覆盖）、每次入口的确定性风险分类（`risk.py` 纯函数）、权限与账号隔离（E2E）、敏感数据日志（readiness 无原始值，E2E 隐私断言）、失败/重试路径（Flutter provider 测试）、无模型时确定性基线（Phase 2 无 AI）。

## 安全 / 隐私 Findings（P0–P3）

| 级别 | Finding | 处置 |
| --- | --- | --- |
| Resolved | `python -m ruff check app tests` 初始复现 13 个预存错误（F401/E402/E712）。 | Codex 做机械性 lint 清理；复跑 `python -m ruff check app tests` 通过。 |
| Resolved | 裸 CLI `alembic upgrade head` 初次因默认 PostgreSQL 端口无服务而失败。 | Docker Desktop 启动后，使用一次性 `postgres:16` 容器和显式 `DATABASE_URL` 复跑 `alembic upgrade head/current`，通过到 `0006_health_weight_tracking (head)`。 |
| — | 隐私正面向：readiness/reason/missing_fields/restricted_reason 仅命名字段与限定词；E2E 断言原始过敏标签/饮食排除/疼痛备注不出现在 readiness 与 risk_summary 中；`pain_note` 为不可信自由文本，从不参与分类。 | 通过（无 P0/P1 隐私问题）。 |
| — | 红旗/受限不退化为普通：E2E 断言 `red_flag != normal/caution`；受限 profile 将普通签到路由至 `restricted`（非 normal）。 | 通过。 |

> 无未解决 P0/P1/P2 finding。Android 人工逐屏业务回放缺口已由用户明确接受为残余风险，不再阻断 Phase 2 Final Closure。

## 剩余风险

1. **Android 人工逐屏业务回放未执行**：登录→我的健康档案→今日签到→异常疼痛追问→体重→趋势/网格→登出/账号切换未由人逐屏点击。用户明确决定跳过并接受该残余风险；Android 启动证据、HTTP 实时旅程和 widget 测试作为替代证据组合。
2. **Phase 2 迁移 PG 降级/再升级未专项演练**：phase1 e2e 的 PG round-trip 仅覆盖 0002↔0003；Phase 2（0004/0005/0006）在真实 PG 上的降级/再升级未单独脚本化（升级至 0006 已证明）。低风险。
3. **Flutter today 为登录后默认落地页**（Task 7 引入，重定向 `/`→`/today`）：功能已测，目标平台已启动，但未做人工逐屏体验确认；包含在用户接受的残余风险内。

## git diff --stat

Codex 收敛后以 `git diff --stat` 为准；除新增 E2E/审计文档与状态文档外，包含 5 个机械性 ruff 清理文件。

## 意外生成文件

- `flutter pub get` 可能重写 `app/{linux,macos,windows}/flutter/generated_plugin_registrant*`（CRLF 归一化，净 diff 为 0）；`pytest` 产生 `backend/test.db`、`__pycache__`、PG 一次性容器（由 conftest_pg atexit 清理）。均为工具副作用，**未提交**。

## 声明

本审计由 OpenCode 验证 Agent 执行，Codex 复核真实 diff、补齐 ruff 收敛和新鲜验证证据。**未 push、未发布。** Final Closure 记录用户决定跳过 Android 人工逐屏冒烟并接受残余风险；Phase 2 收敛为完成。

---

# Task 8B — Android 启动与业务流替代证据（2026-07-26 续）

> 承接上文“Android 模拟器冒烟未执行”阻断项。本节记录 Task 8B 在真实 Android 模拟器 + 一次性 PostgreSQL 16 + 本地后端上收集的证据。
> 基线分支：`codex/phase2-task8b-android-smoke`，Base SHA `351ce81`。

## 方法（混合证据）

Flutter 应用由 Skia 自绘，`adb uiautomator` 无法可靠定位元素；本任务也不新增 `app/test/**` 集成测试。故采用以下证据组合：

1. 真实 Android 构建+启动：Pixel 6 AVD 上 `flutter run` 构建、安装并启动 App，截图 + Activity dump 证明前台运行。
2. 真实后端+PG 全链路：一次性 PG16 + uvicorn 运行时，对同一监听端口跑完整 Phase 2 HTTP 旅程（15/15 通过）。
3. Flutter widget 测试（300 passed）：覆盖登录、Today、异常疼痛门、red_flag/active_rest/safety_adjustment 展示、体重新增、网格、账号切换重置、Plan 不可用。
4. Android 人工逐屏业务回放未执行，用户明确决定跳过并接受该残余风险。

## 环境与设备

- 设备/模拟器：Pixel 6 AVD（`sdk_gphone64_x86_64`），Android 14 / API 34，ABI x86_64。
- 后端 DB：一次性 `postgres:16` 容器（`phase2b-pg`，库名 `posture_app`，一次性密码未写入仓库/未打印敏感凭据）。
- 迁移：`alembic upgrade head` → `0006_health_weight_tracking (head)`。
- 后端：`uvicorn app.main:app --host 127.0.0.1 --port 8000`；App 经 `API_BASE_URL=http://10.0.2.2:8000/api/v1`。
- 全程仅使用合成手机号和合成档案数据；无真实健康数据、照片、凭据或密钥。

## 结果

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| App 在 Android 启动 | PASS | Gradle 构建成功 + `MainActivity` resumed + 截图产物 |
| 合成账号登录 | PASS | 实时旅程 send-code → 读码 → verify-login |
| 健康档案创建/更正/删除 | PASS | 实时旅程 GET 未配置 → PUT ready → DELETE → 未配置；widget 测试 |
| Today 默认落地 | PASS（路由） | widget `today_checkin_test` bottom-nav + 重定向 `/today` |
| 正常签到 | PASS | 实时旅程 PUT → `risk_summary=normal`；widget 测试 |
| abnormal_pain 必填追问 | PASS | 实时旅程 422 `pain_followup_required`；widget 测试 |
| red_flag/restricted 不显示为 normal/success | PASS | 实时旅程 acute trauma → red_flag；widget 测试 |
| active_rest/safety_adjustment 有效非失败态 | PASS | 实时旅程网格含 active_rest/safety_adjustment；widget 测试 |
| 体重录入、趋势、网格 | PASS | 实时旅程 3 记录 → sufficient + trend；widget 测试 |
| 登出/账号切换不残留 | PASS | 实时旅程 B 账号全空 + 跨用户隔离；widget reset |
| 无训练计划渲染为可用 | PASS | 无 plan API；widget today `PlanUnavailableCard` |
| 仅合成数据 | PASS | 合成手机号 + 一次性 DB；无敏感输入 |

一次性脚本对 `http://127.0.0.1:8000/api/v1` 执行完整 Phase 2 路径：登录 → profile → today → abnormal(422) → red_flag → weight/trend → grid → 账号 B 全空 → delete profile。结果为 **15/15 checks PASSED**。

## Task 8B 剩余风险

- Android 人工逐屏业务回放未执行。App 与后端联通由“App 在 Android 启动 + 同一监听端口的实时 HTTP 旅程 + `10.0.2.2` 到 `127.0.0.1` 映射”间接证明；各屏 UI 行为由 300 widget 测试断言。
- 截图未由本模型目视核验，已作为人工核验产物保存。

---

# Final Closure（2026-07-26）

> 用户决策（2026-07-26）：**跳过 Android 人工逐屏冒烟，接受该残余风险**。不再开 Task 8C。本节据此将 Phase 2 收敛为完成，并如实记录依据与残余风险。

## Phase 2 最终状态

**完成（completed）**，基于以下证据与用户接受项：

1. 自动化验证通过：后端 `798 passed`（含真实 PostgreSQL 16 集成，0 skipped）；后端 ruff `app tests` clean；`flutter analyze` 无问题；`flutter test` `300 passed`。
2. PostgreSQL 16 真实迁移/集成通过：一次性 `postgres:16` 容器裸 CLI `alembic upgrade head` → `0006_health_weight_tracking (head)`；真实 PG16 UUID/JSONB/advisory-lock 集成测试 `11 passed`，0 skipped。
3. Android Pixel 6 AVD 构建/安装/启动证据：`flutter run` Gradle `assembleDebug` 成功 → 安装 `app-debug.apk` → 启动；`adb dumpsys` 确认 `com.health.posture_app/.MainActivity` 前台运行。
4. Phase 2 业务流覆盖：HTTP 实时旅程 15/15 PASSED + Flutter 300 widget 测试共同覆盖登录、健康档案、签到、异常疼痛门、red_flag/restricted/active_rest/safety_adjustment、体重/趋势/grid、账号切换和 Plan 不可用。

## 用户接受的残余风险

- Android 人工逐屏业务回放（login → My health profile → Today check-in → abnormal pain follow-up → weight → trend/grid → logout/account switch）未执行。该缺口由用户明确决定跳过并接受为残余风险，不写作“人工逐屏冒烟通过”。
- App 与后端联通由 Android 启动、同端口实时 HTTP 旅程、`10.0.2.2` 到 `127.0.0.1` 映射间接证明；Flutter 各屏 UI 行为由 300 widget 测试断言。
- 截图为人工核验产物，本模型未目视核验。

## Final Closure 声明

Phase 2 收敛为完成：自动化 + PostgreSQL 16 + Android 启动证据齐备，业务流由 HTTP 实时旅程 + widget 测试覆盖；Android 人工逐屏冒烟由用户决定跳过并接受残余风险。未 push、未发布。
