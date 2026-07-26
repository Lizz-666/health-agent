# Active Agent Tasks

> 当前开发协调账本，不是产品规格。最后核对：2026-07-26。
> 所有会话先遵守根目录 `AGENTS.md` 的“开发总纲”，再读取本文件中与当前 Task 对应的行和链接。

## Current Initiative

- 阶段：Phase 3 训练知识与安全引擎。
- 规格：`docs/specs/training/2026-07-26-training-knowledge-safety-engine.md`
- 计划：`docs/plans/training/2026-07-26-training-knowledge-safety-engine.md`
- Phase 2 最终证据：`docs/reports/phase2-exit-audit-2026-07-26.md`；Final Closure commit `1818e74`。用户接受的残余风险仍是 Android 人工逐屏业务回放未执行，不改写为已通过。
- Phase 3 基线：Task 0 主体提交 `2ed211a`（base `1818e74`），Task 1 登记与 PostgreSQL CI 契约修正后最终实现基线为 `ee87a92`。
- 执行实验：OpenCode + Claude 负责 Tasks 1-7 的运行时/CI 代码实现；Codex 负责规格、提示词、真实 diff 审查、验证、提交、本地集成、中期契约检查点、最终验收和合作模式评价。安全策略表、状态优先级、规范化规则和可执行安全案例由 Codex 在 Tasks 4-6 前锁定；OpenCode 不自行选择或放宽安全规则，存在未决安全选择时停止，Codex 直接接管该变更。
- 并行规则：Phase 3 初始默认串行，一次只运行一个 OpenCode 实现 Task。训练 schema、catalog、policy、safety、candidates 和 validator 共享契约，不启动第二个并行写入会话。
- 验证策略：路线图 §13.1 和 Phase 3 计划的 `Layered Local And CI Verification`。Task 1 落地 CI foundation；在用户授权首次 push 前，远程 CI 仍是 `not authorized/not run`，本地证据不得标为 CI。

## Status Definitions

`planned -> in_progress -> review -> fixes -> verified -> committed -> merged`；无法继续时为 `blocked`。

## Active Work

| Task | Executor | Branch / worktree | Base SHA | Status | Scope and coordination note |
| --- | --- | --- | --- | --- | --- |
| Phase 3 Task 0 | Codex coordinator | `codex/phase3-spec-plan` / root worktree | `1818e74` | `committed` | 规格、来源/许可 pin、workout.cool 对照矩阵、Tasks 0-7 charters、CI 分层和实验评价口径；独立复核的 4 P1、5 P2、2 P3 已全部关闭；commit `2ed211a`。 |
| Phase 3 Task 1 | OpenCode implementation + Codex review | `codex/phase3-task1-ci-foundation` / `health-worktrees/phase3-task1-ci-foundation` | `ee87a92` | `in_progress` | Worktree 已快进到最终 Task 1 基线，等待 OpenCode 执行 `.github/workflows/ci.yml`、共享验证入口和 README 命令；无部署、无训练代码、无 push。 |
| Phase 3 Task 2 | OpenCode implementation + Codex review | `codex/phase3-task2-training-contracts` / `health-worktrees/phase3-task2-training-contracts` | Task 1 integrated SHA | `planned` | 严格 schema、fail-closed loader、source manifest、非媒体 importer 和合成 fixtures；不含 approved catalog。 |
| Phase 3 Task 3 | OpenCode implementation + Codex review | `codex/phase3-task3-exercise-catalog` / `health-worktrees/phase3-task3-exercise-catalog` | Task 2 integrated SHA | `planned` | 24-36 个经审查居家动作、完整来源/关系/训练量字段和原创本地 SVG；禁止外部媒体。 |
| Phase 3 Task 4 | OpenCode mechanical implementation + Codex policy owner/checkpoint | `codex/phase3-task4-safety-gate` / `health-worktrees/phase3-task4-safety-gate` | Task 3 integrated SHA | `planned` | Codex 先锁定 safety policy/matrix；OpenCode 组合当前 health/posture 结构化事实，输出 freshness-bound decision，不修改既有领域代码；完成后正式契约审查。 |
| Phase 3 Task 5 | OpenCode mechanical implementation + Codex policy owner/review | `codex/phase3-task5-candidate-engine` / `health-worktrees/phase3-task5-candidate-engine` | Task 4 integrated SHA | `planned` | Codex 先锁定候选/训练量/恢复/冲突规则；OpenCode 实现版本化 policy 和确定性候选引擎；不生成计划。 |
| Phase 3 Task 6 | OpenCode mechanical implementation + Codex contract owner/review | `codex/phase3-task6-plan-validator` / `health-worktrees/phase3-task6-plan-validator` | Task 5 integrated SHA | `planned` | Codex 先锁定 validator precedence/四周时间轴；OpenCode 实现 typed Tool；无修复、无持久化、无公共 API。 |
| Phase 3 Task 7 | OpenCode evidence implementation + Codex final acceptance | `codex/phase3-task7-exit-audit` / `health-worktrees/phase3-task7-exit-audit` | Task 6 integrated SHA | `planned` | Phase 3 E2E、来源/许可审计、全量回归、退出报告和 OpenCode/Codex 实验评价；无新功能。 |

## Integration Order

1. Task 0 -> 1 -> 2 -> 3 -> 4 串行；Task 4 后执行 Codex 中期契约检查点。
2. Task 4 -> 5 -> 6 -> 7 串行；Task 7 在最新集成 SHA 上执行最终两轮审查和退出验收。
3. Task 1 在首次远程候选验证前完成；push/PR 仍需用户明确授权。
4. rebase、冲突修复、catalog/policy 内容变化或集成后，旧验证证据失效并在新 SHA 上重跑。
5. OpenCode 不 commit、merge、rebase 或 push；Codex 只提交已审查并重新验证的精确 Task 范围。

## Worktree State

- `health` 根 worktree：当前 `codex/phase3-spec-plan` 协调分支。未跟踪 `.opencode/package-lock.json` 与 Phase 3 无关，保持未暂存、未提交。
- Phase 3 Task 1 worktree 已快进到 `ee87a92` 并分配给 OpenCode；Task 2-7 worktree 尚未创建，仅在前置 Task 完成并集成后从最新协调 SHA 创建。
- Phase 2 Task worktree 是干净历史实现/审计 tip，不是 Phase 3 基线；可在独立 housekeeping 中移除，分支和历史保留。
- `starlit-galaxy-rolls-21h55` 及列出的 Phase 1 历史 worktree 含未提交或冻结改动，不得删除、覆盖、提交或用作 Phase 3 基线。

## Completed Initiative References

- Phase 1：`docs/reports/phase1-exit-audit-2026-07-22.md`
- Phase 2：`docs/reports/phase2-exit-audit-2026-07-26.md`
- Phase 2 任务明细保留在 Git 历史和对应计划中，不在当前活动账本重复维护。
