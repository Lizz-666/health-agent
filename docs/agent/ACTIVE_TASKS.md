# Active Agent Tasks

> 当前开发协调账本，不是产品规格。最后核对：2026-07-22。
> 所有会话先遵守根目录 `AGENTS.md` 的“开发总纲”，再读取本文件中与当前 Task 对应的行和链接。

## Current Initiative

- 阶段：Phase 2 健康档案、签到与趋势。
- 规格：`docs/specs/platform/2026-07-22-health-profile-checkins-trends.md`
- 计划：`docs/plans/platform/2026-07-22-health-profile-checkins-trends.md`
- Phase 1 最终证据：`docs/reports/phase1-exit-audit-2026-07-22.md`
- Phase 2 Task 0 charter 基线：`4ed1c0e`。
- 执行模式：Codex 对最终结果负责；一个 Task 一个写入者；默认只运行一个外部实现会话；只有满足 `AGENTS.md` 总纲中的隔离条件时才允许第二个实现会话并行。

## Status Definitions

`planned -> in_progress -> review -> fixes -> verified -> committed -> merged`；无法继续时为 `blocked`。

## Active Work

| Task | Executor | Branch / worktree | Base SHA | Status | Scope and coordination note |
| --- | --- | --- | --- | --- | --- |
| Phase 2 Task 0 | Codex coordinator + OpenCode implementation | `codex/phase2-spec-plan` / root worktree | `10f0c65` | `merged` | Phase 2 规格、Task 0-8 charter 和路线图基线；提交证据 `0e92e2c`、`4ed1c0e`。 |
| Phase 2 Task 1 | OpenCode implementation + Codex coordination | `codex/phase2-task1-health-profile-domain` / `health-worktrees/phase2-task1-health-profile-domain` | `4ed1c0e` | `in_progress` | 后端 health profile domain、迁移和 risk-readiness primitives。当前 worktree 有实现中改动；`backend/test.db-journal` 是运行产物，不得提交。 |
| Phase 2 Task 2 | Unassigned | Task 1 合并后创建 | Task 1 merge SHA | `planned` | `GET/PUT/DELETE /api/v1/health/profile`、鉴权、跨用户隔离、删除和 OpenAPI；依赖 Task 1。 |
| Phase 2 Task 3 | Unassigned | Task 2 合并后创建 | Task 2 merge SHA | `planned` | Daily check-in、异常疼痛追问和签到风险摘要；依赖 Task 1/2，不生成训练调整或计划。 |
| Phase 2 Task 4 | Unassigned | Task 3 合并后创建 | Task 3 merge SHA | `planned` | Weight CRUD、趋势元数据和 activity grid projection；不输出训练或饮食调整建议。 |
| Phase 2 Task 5 | Unassigned | 后端 API 契约稳定后创建 | Task 2-4 merge SHA | `planned` | Flutter models、providers、session reset 和测试；先做状态层，不新增页面主流程。 |
| Phase 2 Task 6 | Unassigned | Task 5 合并后创建 | Task 5 merge SHA | `planned` | My 页面健康档案、体重趋势、activity grid 和删除 UI；不混入 Today check-in。 |
| Phase 2 Task 7 | Unassigned | Task 5 合并后创建 | Task 5 merge SHA | `planned` | Today 页面签到、异常疼痛追问和主动休息/安全调整 UI；不得渲染不存在的训练计划。 |
| Phase 2 Task 8 | Codex final integration | Task 6/7 集成后创建 | 最新集成 SHA | `planned` | Phase 2 E2E、OpenAPI、隐私、缓存、账户切换、Android 冒烟和退出审计。 |

## Integration Order

1. Task 1 -> Task 2 -> Task 3 -> Task 4 按迁移和 API 契约顺序串行集成。
2. Task 5 在 Task 2-4 契约稳定后开始。
3. Task 6 和 Task 7 默认串行；只有 Codex 核对实际允许文件无重叠、无共享状态后才可并行。
4. Task 8 由 Codex 在全部实现 Task 验证并集成后执行。
5. rebase、冲突修复或集成后的旧验证证据失效，必须在新 SHA 上重跑。

## Preserved Worktrees

以下 worktree 含未提交改动或仍是当前任务，禁止自动删除、覆盖或顺手提交：

- `health` 根 worktree：未跟踪 `.opencode/package-lock.json` 与当前治理任务无关，保持未暂存。
- `phase2-task1-health-profile-domain`：当前 Phase 2 Task 1 实现 worktree。
- `starlit-galaxy-rolls-21h55`：未登记的 Flutter/UI、资源和计划改动，保持隔离。
- `phase1-integration`、`phase1-task2`、`phase1-task6-priority-goals`、`phase1-task6_5`、`phase1-task7-posture-tools`、`phase1-task9`：含历史未提交改动，仅作冻结参考；不得作为新 Task 基线。

已完成且干净的 Phase 1 worktree 于 2026-07-22 从 Git worktree 登记中收敛移除；对应分支和 Git 历史保留。`phase1-task10-5-migration-contract/backend` 与 `phase1-task10-final-e2e/app` 因现有进程占用仍有磁盘残目录，但已不是 Git worktree，不得继续使用；占用释放后删除。Phase 1 的任务明细、验证计数和最终状态统一查阅退出审计，不在活动账本重复维护。
