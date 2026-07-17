# Active Agent Tasks

> 这是并行开发协调总账，不是产品规格。最后核对：2026-07-16，基于各 worktree 的 `git status` 和 HEAD。
> 协调者在分配任务前、进入 review 时、创建 commit 后和完成集成后更新本文件。

## Current Initiative

- 阶段：Phase 1 体态核心产品化
- 规格：`docs/specs/posture/2026-07-11-posture-core-productization.md`
- 计划：`docs/plans/posture/2026-07-11-posture-core-productization.md`
- 当前并行实现任务的共享基线：`e4705726ad857cc9af50806827749b562c11472d`

## Status Definitions

`planned -> in_progress -> review -> fixes -> verified -> committed -> merged`，无法继续时为 `blocked`。

## Active Work

| Task | Executor | Branch / worktree | Base SHA | Status | Scope and coordination note |
| --- | --- | --- | --- | --- | --- |
| Phase 1 Task 2 | Coordinator clean integration | `codex/phase1-integration-clean` / `health-worktrees/phase1-integration-clean` | `d309969` | `committed` at `d01492c` | 双写评估事件投影 + profile 投影（spec §6.3/§6.4/§8.5）；service.py 的 safety/purge 导入在本 commit 为防御式（模块尚未存在），于后续 commit 移除 |
| Phase 1 Task 6.5 | Coordinator clean integration | `codex/phase1-integration-clean` / `health-worktrees/phase1-integration-clean` | `d309969` | `committed` at `f420a48` | 结构化安全信号分类 + risk_rules + safety-signals 端点；safety.py 的 purge 导入仍为防御式（purge 未存在）；依赖 Task 2 的 service 投影 |
| Phase 1 Task 9 | Coordinator clean integration | `codex/phase1-integration-clean` / `health-worktrees/phase1-integration-clean` | `d309969` | `committed` at `99afcd8` | 隐私门 photo→privacy_gate + crash-safe purge + 配置/路由/conftest 条件补丁；移除全部防御式导入，恢复 service/safety 为直接导入，恢复完整 test_posture_safety.py |
| Phase 1 integration | Coordinator clean integration | `codex/phase1-integration-clean` / `health-worktrees/phase1-integration-clean` | `d309969` | `committed`, NOT merged | Task 2/6.5/9 以干净可审计的 5-commit 链提交；最新 reviewer fix 为 `64afd6b`；尚未 push/PR/merge，未标记 Phase 1 完成；参考 worktree（`codex/phase1-integration`）仅作历史最终态参照，不得修改 |

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

## Other Worktrees

- `starlit-galaxy-rolls-21h55` 有未提交 Flutter/UI 和资源改动，当前不属于 Phase 1 已登记 Task。保持隔离，不合并、不清理，等待用户另行决定。
- 已合并任务的旧 worktree 目前干净；删除 worktree 或分支仍需用户明确授权。

## Integration Order

1. Task 2 独立 review、验证、commit。
2. Task 6.5 基于已验证依赖处理冲突，重新 review、验证、commit。
3. Task 9 在 posture router 等共享文件的最新集成基线上处理冲突，重新 review、验证、commit。
4. integration worktree 只接收上述已验证 commit；集成后运行组合验证，旧分支证据不再视为充分。
