# Phase 2 Exit Audit — Health Profile, Check-Ins, and Trends

> 审计日期：2026-07-26
> 审计者：OpenCode 验证 Agent + Codex 复核/收敛
> 规格：`docs/specs/platform/2026-07-22-health-profile-checkins-trends.md`
> 计划：`docs/plans/platform/2026-07-22-health-profile-checkins-trends.md`（Task 8）
> 基线分支：`codex/phase2-task8-phase2-exit-audit`，Base SHA `26f785f`（Tasks 1–7 已合并于 `codex/phase2-spec-plan`）
> 路线图：`docs/product/roadmap.md` §6

## 总结论

**阶段 2 自动化验证全部通过，且 PostgreSQL 16 真实集成证据齐备；但 Android 模拟器冒烟未执行，因此按 Task 8 契约与路线图 §13 规则，阶段 2 暂不标记为“完成”，状态为“有条件通过，待 Android 冒烟补齐”。** 本审计未 push、未发布。

- 后端：`798 passed`（含真实 PostgreSQL 16 集成路径，0 skipped）；新增 Phase 2 E2E `6 passed`。
- Flutter：`flutter analyze` 无问题；`flutter test` `300 passed`。
- PostgreSQL：Docker Desktop 启动后可用，`test_pg_integration.py` `11 passed`（真实 PG16，UUID/JSONB/advisory lock），并用一次性 `postgres:16` 容器独立执行裸 CLI `alembic upgrade head` / `alembic current` 至 `0006`。
- ruff：Codex 复核阶段清理 13 个预存 lint 问题后，`python -m ruff check app tests` 通过。
- Android 模拟器冒烟：**未执行**（`flutter emulators` 可列出 `Pixel_6` AVD，但未启动目标平台冒烟流程）→ 退出标准证据缺口。

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
| 11 | Android 模拟器冒烟（手动） | — | n/a | **未执行** |

> SHA：证据采集于 `26f785f` 工作树 `health-worktrees/phase2-task8-phase2-exit-audit` 加本任务变更（新增 E2E、文档与 Codex ruff 清理）。验证后若再发生实质代码改动，相关证据即失效。

## Android 冒烟结果

**未执行。** `flutter emulators` 可列出 `Pixel_6` Android AVD，但本审计未启动模拟器、后端和数据库组成完整目标平台流程。计划要求的冒烟路径（登录 → 我的健康档案 → 今日签到 → 异常疼痛追问 → 体重录入 → 趋势/网格 → 登出/账号切换）未能在 Android 上验证。

**影响：** Task 8 契约要求 Android emulator smoke；缺少该证据时不得标记 Phase 2 完成。故阶段 2 状态为“有条件通过”，不标记完成。

**补齐路径（建议）：** 启动 `Pixel_6` AVD、可丢弃 PostgreSQL/后端和 Flutter Android app，执行上述冒烟；通过后由 Codex 将路线图 §6 状态从“有条件通过”改为“完成”，并补记冒烟证据。

## 路线图 §6 退出标准逐条核对

| §6 退出标准 | 判定 | 证据 |
| --- | --- | --- |
| 缺失数据不会被 AI 自动猜测 | **PASS**（自动化） | 后端：not-configured 显式 `missing_required_data`+`missing_fields`；E2E 断言缺失字段被命名、空值保持空（`test_e2e_phase2_full_user_journey`）。Phase 2 全程无 AI/推荐生成（规格 Domain Model）。 |
| 用户可在 20 秒左右完成普通签到 | **PASS（功能）/ 时序待冒烟** | Flutter：`today_checkin_test.dart` 普通路径一键提交（合理默认值）；后端 PUT normal → `risk_summary=normal`。20 秒时序未在目标平台计时（依赖 Android 冒烟）。 |
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

> 无未解决 P0/P1/P2 finding。阶段完成仍被 Android 冒烟证据缺口阻断。

## 剩余风险

1. **Android 模拟器冒烟缺失**（阻断“完成”标记）：UI 端到端、20 秒签到时序、真实后端联调均未在目标平台验证。补齐后方可标记阶段完成。
2. **Phase 2 迁移 PG 降级/再升级未专项演练**：phase1 e2e 的 PG round-trip 仅覆盖 0002↔0003；Phase 2（0004/0005/0006）在真实 PG 上的降级/再升级未单独脚本化（升级至 0006 已证明）。低风险。
3. **Flutter today 为登录后默认落地页**（Task 7 引入，重定向 `/`→`/today`）：功能已测，但仅自动化层面；需冒烟确认目标平台体验。

## git diff --stat

Codex 收敛后以 `git diff --stat` 为准；除新增 E2E/审计文档与状态文档外，包含 5 个机械性 ruff 清理文件。

## 意外生成文件

- `flutter pub get` 可能重写 `app/{linux,macos,windows}/flutter/generated_plugin_registrant*`（CRLF 归一化，净 diff 为 0）；`pytest` 产生 `backend/test.db`、`__pycache__`、PG 一次性容器（由 conftest_pg atexit 清理）。均为工具副作用，**未提交**。

## 声明

本审计由 OpenCode 验证 Agent 执行，Codex 复核真实 diff、补齐 ruff 收敛和新鲜验证证据。**未 push、未发布。** 阶段 2 不标记“完成”，待 Android 冒烟补齐后由 Codex 收敛。
