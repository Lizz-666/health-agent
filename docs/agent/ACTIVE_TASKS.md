# Active Agent Tasks

> 当前开发协调账本，不是产品规格。最后核对：2026-07-26。
> 所有会话先遵守根目录 `AGENTS.md` 的“开发总纲”，再读取本文件中与当前 Task 对应的行和链接。

## Current Initiative

- 阶段：Phase 3 训练知识与安全引擎已完成并本地集成；下一阶段尚未启动。
- 规格：`docs/specs/training/2026-07-26-training-knowledge-safety-engine.md`
- 计划：`docs/plans/training/2026-07-26-training-knowledge-safety-engine.md`
- Phase 2 最终证据：`docs/reports/phase2-exit-audit-2026-07-26.md`；Final Closure commit `1818e74`。用户接受的残余风险仍是 Android 人工逐屏业务回放未执行，不改写为已通过。
- Phase 3 基线：Task 0 主体提交 `2ed211a`（base `1818e74`）；整阶段 OpenCode 实现实验的精确 base 为 `c49eb618759ff85d7235f515b57c9d3fad38d6cb`。
- 执行实验：一个 OpenCode + Claude 会话在单一实现分支/worktree 中连续完成 Tasks 1-7 的全部代码、静态数据、测试、CI 配置和退出证据，并可创建内聚的本地 milestone commits。Codex 不进行逐 Task 审查、提交、集成或例行中期检查，只在整个 Phase 3 报告完成后审查完整 `base..HEAD` diff、重新验证、修复或退回 findings、执行本地集成并评价合作模式。
- 安全边界：OpenCode 按已批准规格实现，不自行新增或放宽健康/安全/隐私规则。未明确情况 fail closed 并记录；只有不同解释会实质改变产品或安全结果时才请求 Codex 澄清，不把普通工程选择升级为检查点。
- 并行规则：Phase 3 只有一个实现写入者。Tasks 1-7 是同一会话中的顺序里程碑，不启动第二个实现会话，Codex 也不并行修改实现 worktree。
- 验证策略：路线图 §13.1 和 Phase 3 计划的 `Layered Local And CI Verification`。Task 1 落地 CI foundation；在用户授权首次 push 前，远程 CI 仍是 `not authorized/not run`，本地证据不得标为 CI。

## Status Definitions

`planned -> in_progress -> review -> fixes -> verified -> committed -> merged`；无法继续时为 `blocked`。

## Active Work

| Task | Executor | Branch / worktree | Base SHA | Status | Scope and coordination note |
| --- | --- | --- | --- | --- | --- |
| Phase 3 Task 0 | Codex coordinator | `codex/phase3-spec-plan` / root worktree | `1818e74` | `committed` | 规格、来源/许可 pin、workout.cool 对照矩阵、Tasks 0-7 charters、CI 分层和实验评价口径；独立复核的 4 P1、5 P2、2 P3 已全部关闭；commit `2ed211a`。 |
| Phase 3 Tasks 1-7 | OpenCode + Claude implementation; Codex final acceptance and fixes | `codex/phase3-opencode-implementation` / `health-worktrees/phase3-opencode-implementation` | `c49eb618759ff85d7235f515b57c9d3fad38d6cb` | `merged` | OpenCode handoff `9ccaa35` failed first-pass acceptance. Codex closed safety, validator, source/media/license and CI-evidence findings in `423bf55`; local Full: `989 passed`, 0 failed, 0 skipped, PostgreSQL `13/13`, ruff/diff clean. Final report/status `663f262` was fast-forward integrated into `codex/phase3-spec-plan`. Remote CI remains `not authorized/not run`. |

## Integration Order

1. Phase 3 已按既定顺序完成：Task 0 基线 -> OpenCode Tasks 1-7 -> Codex 终验与修复 -> 本地 fast-forward 集成。
2. 内部 Task 完成后 OpenCode 先自审、运行 focused verification 并创建内聚本地 commit，再继续下一项；不等待 Codex 例行验收。
3. Task 1 实现 CI foundation；push/PR 仍需用户明确授权，未授权前远程 CI 证据必须标记 `not authorized/not run`。
4. rebase、冲突修复、catalog/policy 内容变化或最终集成后，受影响的旧验证证据失效并在新 SHA 上重跑。
5. OpenCode 可 commit 当前实现分支，但不得 merge、rebase、push、创建 PR 或修改其他 worktree。Codex 在 OpenCode 整阶段交付前不写该 worktree。

## Worktree State

- `health` 根 worktree：当前 `codex/phase3-spec-plan`，Phase 3 已本地集成。未跟踪 `.opencode/package-lock.json` 与 Phase 3 无关，保持未暂存、未提交。
- Phase 3 单一实现 worktree 为 `health-worktrees/phase3-opencode-implementation`，分支 `codex/phase3-opencode-implementation`，从 `c49eb618759ff85d7235f515b57c9d3fad38d6cb` 创建；旧 Task 1 worktree/分支已在确认干净后移除。
- Phase 2 Task worktree 是干净历史实现/审计 tip，不是 Phase 3 基线；可在独立 housekeeping 中移除，分支和历史保留。
- `starlit-galaxy-rolls-21h55` 及列出的 Phase 1 历史 worktree 含未提交或冻结改动，不得删除、覆盖、提交或用作 Phase 3 基线。

## Completed Initiative References

- Phase 1：`docs/reports/phase1-exit-audit-2026-07-22.md`
- Phase 2：`docs/reports/phase2-exit-audit-2026-07-26.md`
- Phase 2 任务明细保留在 Git 历史和对应计划中，不在当前活动账本重复维护。
