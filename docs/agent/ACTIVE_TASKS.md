# Active Agent Tasks

> 这是并行开发协调总账，不是产品规格。最后核对：2026-07-18，基于各 worktree 的 `git status` 和 HEAD。
> 协调者在分配任务前、进入 review 时、创建 commit 后和完成集成后更新本文件。

## Current Initiative

- 阶段：Phase 1 体态核心产品化
- 规格：`docs/specs/posture/2026-07-11-posture-core-productization.md`
- 计划：`docs/plans/posture/2026-07-11-posture-core-productization.md`
- 当前下一实现任务代码基线：`49f9a8d`

## Status Definitions

`planned -> in_progress -> review -> fixes -> verified -> committed -> merged`，无法继续时为 `blocked`。

## Active Work

| Task | Executor | Branch / worktree | Base SHA | Status | Scope and coordination note |
| --- | --- | --- | --- | --- | --- |
| Phase 1 Task 2 | Coordinator clean integration | `codex/phase1-integration-clean` / `health-worktrees/phase1-integration-clean` | `d309969` | `merged` via `cc92449` | 双写评估事件投影 + profile 投影（spec §6.3/§6.4/§8.5）；service.py 的 safety/purge 导入在本 commit 为防御式（模块尚未存在），于后续 commit 移除 |
| Phase 1 Task 6.5 | Coordinator clean integration | `codex/phase1-integration-clean` / `health-worktrees/phase1-integration-clean` | `d309969` | `merged` via `cc92449` | 结构化安全信号分类 + risk_rules + safety-signals 端点；safety.py 的 purge 导入仍为防御式（purge 未存在）；依赖 Task 2 的 service 投影 |
| Phase 1 Task 9 | Coordinator clean integration | `codex/phase1-integration-clean` / `health-worktrees/phase1-integration-clean` | `d309969` | `merged` via `cc92449` | 隐私门 photo→privacy_gate + crash-safe purge + 配置/路由/conftest 条件补丁；移除全部防御式导入，恢复 service/safety 为直接导入，恢复完整 test_posture_safety.py |
| Phase 1 integration | Coordinator clean integration | `codex/phase1-integration-clean` / `health-worktrees/phase1-integration-clean` | `d309969` | `merged` via `cc92449` | Task 2/6.5/9 以干净可审计的 5-commit 链提交并已本地 fast-forward 到 main；最新 reviewer fix 为 `64afd6b`；尚未 push/PR，未标记 Phase 1 完成；参考 worktree（`codex/phase1-integration`）仅作历史最终态参照，不得修改 |
| Phase 1 Task 4 | OpenCode (impl) + Codex review | `codex/phase1-task4-profile-api` / `health-worktrees/phase1-task4-profile-api` | `552fb41` | `merged` via `9892c3e` | 体态档案读取 API：GET /profile + GET /profile/{issue_id}（spec §9.2）；JWT-only 跨用户隔离（无 user_id 参数）；sources 只透传 profile 投影结构化内容，不暴露 photo_keys/原始 ai_response；未实现 priorities 与 related_priority（属 Task 6）；Codex 已检查真实 diff、重跑验证并 fast-forward 到 main |
| Phase 1 Task 5 | OpenCode (impl) + Codex review | `codex/phase1-task5-conflict-state` / `health-worktrees/phase1-task5-conflict-state` | `9892c3e` | `merged` via `f00098e` | 冲突状态收口（spec §6.3/§6.4/§11.1）：审计确认 `project_profile` 已完整正确实现 §11.1 全表且无“取更严重”自动合并路径，/profile 与 /profile/{issue_id} 已透传 conflict；零生产代码改动，仅补测试缺口——新建 test_posture_conflict.py（§11.1 全量参数化矩阵 + 单来源 + no-take-severe + DB 冲突解决重建）并补 test_posture_profile_api.py 单条目 conflict 详情；未实现 priorities/goals（Task 6），conflict 无提前放行路径；Codex 已检查真实 diff 并重跑验证 |
| Phase 1 Task 6 | OpenCode (impl) + Codex review | `codex/phase1-task6-priority-goals` / `health-worktrees/phase1-task6-priority-goals` | `8d3f3ab` | `merged` via `7566968` | 确定性优先级 + 目标确认：restricted/red_flag 优先进入 `safety_blocked` 且语义分离，确认分别返回 409 `restricted_blocked` / `red_flag_blocked`；1–3 个当前候选、服务端稳定控制值、30 天边界失效、统一幂等批次锚点重放/410、OpenAPI ref 已实现。Codex review 修复批次时间碰撞导致跨批重放、微秒级排序丢失，并把双来源数量纳入 suggestion 上下文摘要，补齐安全信号变化后 stale 优先与上述回归测试。主分支 `7566968` 新鲜验证：priority 44 passed；profile/safety 163 passed；posture/OpenAPI 87 passed；全量 482 passed、11 个 PostgreSQL/Docker 条件测试 skipped。未生成训练计划，未改 models/migration，未抽取或重构 safety 幂等路径 |
| Phase 1 Task 7 | OpenCode (impl) + Codex review | `codex/phase1-task7-posture-tools` / `health-worktrees/phase1-task7-posture-tools` | `1c14319` | `merged` via `4eb0bd2` | 体态 Tool 应用层（spec §10.0–§10.8）：8 个 Tool 使用真实 Pydantic 输入/输出契约，REST 与未来 Agent 共用同一应用层；JWT 注入 frozen ActorContext，照片总开关→证据门→用户同意→ownership→统一幂等/模型/事件链默认 fail closed。照片 REST 显式要求客户端 idempotency_key。Codex review 修复随机幂等键、Tool 绕过总开关、缺少用户同意、裸 dict/Any 契约、图片顺序哈希和非法 category 等问题；未创建 Tool HTTP 路由/Agent/migration，未重构 safety/confirm 幂等。主分支 `4eb0bd2` 新鲜验证：Tool 69 passed；全量 551 passed、11 个 PostgreSQL/Docker 条件测试 skipped |
| Phase 1 Task 8A | OpenCode (impl) + Codex review | `codex/phase1-task8a-history-source` / `health-worktrees/phase1-task8a-history-source` | `55acc62` | `merged` via `9fcea74` | history 同时返回真实 `source` 与同值 `method` 兼容别名，legacy nullable source 回退 method；OpenAPI 将 source 保持为可选追加字段。Codex review 修复过时精确 keyset 断言并补 OpenAPI optional 守护；主分支全量后端 558 passed、11 个 PostgreSQL/Docker 条件测试 skipped |
| Phase 1 Task 8B | OpenCode (impl) + Codex review | `codex/phase1-task8b-flutter-foundation` / `health-worktrees/phase1-task8b-flutter-foundation` | `55acc62` | `merged` via `cf7a889` | Flutter 类型模型、Provider、状态与 UUID 幂等基础层。Codex review 修复无效照片响应降级 normal、旧 priorities 乱序回写、安全信号 2xx 解析失败未失效旧建议、扩展自测安全字段不完整、宽松数值/枚举解析和重复确认；主分支 flutter analyze 通过、flutter test 134 passed |
| Phase 1 Task 8C | OpenCode (impl) + Codex review | `codex/phase1-task8c-flutter-posture-ui` / `health-worktrees/phase1-task8c-flutter-posture-ui` | `ef18d22` | `merged` via `edde8b0` | Flutter 体态档案/结果/自测/历史页面与状态徽标已完成。Codex review 正式扩展范围至 `app.dart`、auth/user/assessment/posture-profile providers 与认证会话清理测试：修复缺失结果静默降级 normal、跨账号健康缓存泄露、注销后旧请求回写、2xx 安全响应解析失败仍保留旧目标、非 conflict 来源缺失、空档案分类缺失、mild 显示未知及窄屏溢出；constants/theme/home/issues 和既有共享 widget 未改，`starlit-galaxy-rolls-21h55` 未触碰。主分支 `edde8b0` 新鲜验证：analyze 通过；全量 196 passed；debug APK 构建成功；未做实体 Android 冒烟 |
| Phase 1 Task 10.5 | OpenCode (impl) + Codex review | `codex/phase1-task10-5-migration-contract` / `health-worktrees/phase1-task10-5-migration-contract` | `49f9a8d` | `review` | Migration Phase C contract/cleanup：0003 收紧 source/lifecycle NOT NULL，severity 永久 nullable，删除数据库 method/result 旧列并移除 dual-write；API method/result 兼容字段继续由 source/severity 映射。必须完成 PostgreSQL 16 upgrade/downgrade/re-upgrade 与普通/null severity 数据往返；Task 10 最终 E2E 在本任务合入前不得启动 |

Task 7 已验证并合入；后续 Agent 编排只能复用这些受控 Tool，不得直接访问数据库或绕过照片门。
负责人裁决：`ActorContext` 归 `app/core`，Tool I/O 归 `tool_contracts.py`；照片所有权使用
fail-closed `PhotoOwnershipVerifier` 边界，禁止用对象 key 前缀冒充已上传对象证明；真实
provider-backed verifier 是未来照片隐私门启用前置，不在 Phase 1 伪造。

## Phase 1 Integration — Clean Chain Verification

> 干净可审计的 5-commit 链，基于 `d309969`，分支 `codex/phase1-integration-clean`，worktree `health-worktrees/phase1-integration-clean`。
> 文件内容最初来自参考 worktree `codex/phase1-integration`（历史参考态，未修改）。`backend/app/posture/models.py` 的参考改动（仅类型注解+注释，无运行时影响）按 copy-list 指令未纳入，是有意偏离；Commit 5 另行修复了参考态中也存在的 initial freezing lease 恢复漏洞。

| # | Commit | Message | Staged files | Verification (fresh evidence) |
| --- | --- | --- | --- | --- |
| 1 | `d01492c` | feat: add posture assessment event projection | user_lock.py, service.py, test_posture_profile.py | `pytest tests/test_posture.py tests/test_posture_profile.py -q` → **99 passed** |
| 2 | `f420a48` | feat: add structured posture safety classification | risk_rules.py, safety.py, schemas.py, router.py, service.py, test_posture_safety.py | `pytest tests/test_posture_safety.py tests/test_posture_profile.py -q` → **106 passed** |
| 3 | `99afcd8` | feat: add privacy gate and crash-safe posture purge | privacy_gate.py, purge.py, service.py, router.py, safety.py, config.py, main.py, upload/router.py, .env.example, conftest.py, conftest_pg.py, test_posture.py, test_posture_safety.py, test_privacy_gate.py, test_pg_integration.py, test_pg_safety_guard.py, test_integration.py, spec, plan | `pytest tests/test_pg_integration.py -q -s` → **10 passed**（PostgreSQL 16.14，未跳过）；`pytest tests -q` → **396 passed** |
| 4 | (this commit) | docs: record verified phase one integration tasks | docs/agent/ACTIVE_TASKS.md | 无代码改动；仅状态与证据记录 |
| 5 | `64afd6b` | fix: make initial posture purge lease recoverable | purge.py, test_privacy_gate.py, test_pg_integration.py | `pytest tests/test_privacy_gate.py::test_real_run_purge_freezing_phase_keeps_reclaimable_lease tests/test_privacy_gate.py::test_interrupted_initial_phase_is_reclaimed -q` → **4 passed**；`pytest tests/test_privacy_gate.py tests/test_posture_safety.py tests/test_posture_profile.py -q` → **190 passed**；`pytest tests/test_pg_integration.py -q -s` → **10 passed**（PostgreSQL 16.14，未跳过）；`pytest tests -q` → **397 passed** |

中间 commit 的防御式导入说明（可审计性）：safety.py / purge.py 在其所属 commit 尚不存在时，引用方（service.py / safety.py）用 `try/except ImportError` 退化到安全默认；purge.py / test_privacy_gate.py 依赖的 test_posture_safety.py 测试在 Commit 2 暂时截断，于 Commit 3 全量恢复。Commit 5 修复了 reviewer 在 clean 分支和参考 worktree 中共同发现的 initial freezing lease 恢复漏洞，因此最终 clean 分支不再与参考 worktree 逐字节完全一致；以 `64afd6b` 为当前已验证最终态。

## Merged Work

| Work | Commit evidence | Status |
| --- | --- | --- |
| Phase 1 规格和实施计划 | `87f7b74`, merged by `083f6d9` | `merged` |
| Phase 1 Task 1 migration foundation | `c510d49`, merged by `eb5210b` | `merged` |
| Phase 1 Task 3 sourced self-test content gate | `b65b4e7`, merged by `e470572` | `merged` |
| Phase 1 Task 2/6.5/9 clean integration | `d01492c` → `cc92449`, fast-forwarded to main | `merged` |
| Phase 1 Task 4/5/6 posture profile and priorities | `9892c3e`, `f00098e`, `7566968` | `merged` |
| Phase 1 Task 7 typed posture Tool layer | `4eb0bd2` | `merged` |
| Phase 1 Task 8A/8B/8C Flutter posture delivery | `9fcea74`, `cf7a889`, `edde8b0` | `merged` |

## Other Worktrees

- `starlit-galaxy-rolls-21h55` 有未提交 Flutter/UI 和资源改动，当前不属于 Phase 1 已登记 Task。保持隔离，不合并、不清理，等待用户另行决定。
- 已合并任务的旧 worktree 目前干净；删除 worktree 或分支仍需用户明确授权。

## Integration Order

1. Task 2 独立 review、验证、commit。
2. Task 6.5 基于已验证依赖处理冲突，重新 review、验证、commit。
3. Task 9 在 posture router 等共享文件的最新集成基线上处理冲突，重新 review、验证、commit。
4. integration worktree 只接收上述已验证 commit；集成后运行组合验证，旧分支证据不再视为充分。
