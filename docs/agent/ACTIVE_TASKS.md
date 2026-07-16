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
| Phase 1 Task 2 | OpenCode implementation session | `codex/phase1-task2` / `health-worktrees/phase1-task2` | `e470572` | `in_progress`, unreviewed | 允许范围以当前计划 Task 2 的 `Files` 段为准；当前修改 service 和 profile 测试；依赖已合并的 Task 1 |
| Phase 1 Task 6.5 | OpenCode implementation session | `codex/phase1-task6_5` / `health-worktrees/phase1-task6_5` | `e470572` | `in_progress`, unreviewed | 允许范围以当前计划 Task 6.5 的 `Files` 段为准；当前修改 router/schema、安全规则和测试；依赖 Task 1 |
| Phase 1 Task 9 | OpenCode implementation session | `codex/phase1-task9` / `health-worktrees/phase1-task9` | `e470572` | `in_progress`, unreviewed | 允许范围以当前计划 Task 9 的 `Files` 段为准；当前修改隐私门、purge、配置、路由和测试；与 Task 6.5 必须串行集成 |
| Phase 1 integration | Coordination/integration worktree | `codex/phase1-integration` / `health-worktrees/phase1-integration` | `e470572` | `blocked` for integration | 含 Task 2、6.5、9 的重叠未提交改动；不得作为完成来源或继续吸收实现，直到各 Task 独立 review、commit 并确定集成顺序 |

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
