# Active Agent Tasks

> 当前开发协调账本，不是产品规格。最后核对：2026-07-27。
> 所有会话先遵守根目录 `AGENTS.md` 的“开发总纲”，再读取本文件中与当前 Task 对应的行和链接。

## Current Initiative

- 阶段：Phase 4 四周训练计划 MVP OpenCode 全阶段委派实验准备中；Codex 仅做最终独立验收。
- 委派章程：`docs/agent/PHASE4_OPENCODE_CHARTER.md`。
- Phase 4 当前规格和实施计划由 OpenCode 在 Task 0 创建并自审；在它们落地前，路线图和委派章程是范围输入，不得开始运行时代码。
- Phase 2 最终证据：`docs/reports/phase2-exit-audit-2026-07-26.md`；Final Closure commit `1818e74`。用户接受的残余风险仍是 Android 人工逐屏业务回放未执行，不改写为已通过。
- Phase 3 基线：Task 0 主体提交 `2ed211a`（base `1818e74`）；整阶段 OpenCode 实现实验的精确 base 为 `c49eb618759ff85d7235f515b57c9d3fad38d6cb`。
- Phase 3 远程证据：PR `#1` 在精确 SHA `8459384dbbcb339e8d78fa243b4e8690c76b7bba` 上 Fast 和 Full GitHub CI 均成功；PR 仍为 draft，尚未合并到 `main`。
- 执行实验：一个 OpenCode + Claude 会话在单一实现分支/worktree 中顺序完成 Phase 4 Tasks 0-7，包括规格、计划、实现、测试、milestone commits、GitHub CI 操作、逐 Task 自验收、修复和最终交接。Codex 不进行例行中期审查或并行写入，只在完整交接后审查 `base..HEAD`、重新验证并决定是否接受。
- 安全边界：OpenCode 不得绕过或放宽 Phase 3 安全引擎；未明确情况 fail closed。新健康阈值必须有当前权威一手来源和版本化策略。会实质改变产品/安全结果的歧义才请求澄清，普通工程选择由 OpenCode 负责。
- 并行规则：Phase 4 只有一个实现写入者。Tasks 0-7 是同一会话中的顺序里程碑，不启动第二个实现会话，Codex 也不修改该 worktree。
- 验证策略：每个 Task 必须完成 focused local、适用的 Fast/Full CI 和两轮自审，并将证据绑定到 exact SHA。OpenCode 已获本阶段分支 push、draft PR 和 CI 读写权限；不得 merge、force-push、写 `main`、改仓库 secrets/settings 或部署。

## Status Definitions

`planned -> in_progress -> review -> fixes -> verified -> committed -> merged`；无法继续时为 `blocked`。

## Active Work

| Task | Executor | Branch / worktree | Base SHA | Status | Scope and coordination note |
| --- | --- | --- | --- | --- | --- |
| Phase 3 Task 0 | Codex coordinator | `codex/phase3-spec-plan` / root worktree | `1818e74` | `committed` | 规格、来源/许可 pin、workout.cool 对照矩阵、Tasks 0-7 charters、CI 分层和实验评价口径；独立复核的 4 P1、5 P2、2 P3 已全部关闭；commit `2ed211a`。 |
| Phase 3 Tasks 1-7 | OpenCode + Claude implementation; Codex final acceptance and fixes | `codex/phase3-opencode-implementation` / `health-worktrees/phase3-opencode-implementation` | `c49eb618759ff85d7235f515b57c9d3fad38d6cb` | `merged` | OpenCode handoff `9ccaa35` failed first-pass acceptance. Codex closed findings in `423bf55`; local Full `989 passed`, PostgreSQL `13/13`; integration closure `e7fd6d9` and CI dependency test fix `8459384`. PR #1 remote Fast/Full both pass at `8459384`; draft remains unmerged. |
| Phase 4 Tasks 0-7 | OpenCode + selected Claude model; Codex final acceptance only | `codex/phase4-opencode-implementation` / `health-worktrees/phase4-opencode-implementation` | `b7f8391e17a2adbb4ae52d012b360d17ff4550fd` | `review` | Follow `docs/agent/PHASE4_OPENCODE_CHARTER.md`. OpenCode delivered Tasks 0-7 (spec/plan/ADR-0001/0002, CI, persistence+migration 0007, generator, authenticated API, Flutter models/provider/UI, full-phase E2E). Final handoff `docs/reports/phase4-opencode-handoff-2026-07-27.md`; implementation tip `3db3303`, draft PR #2. Local fast 262 / full PG16 1067 passed 0 failed, PG 18/18; Flutter analyze clean + 319 tests; Android smoke (build/install/launch). Status is `review`, not verified; only Codex may mark verified or integrate. |

## Integration Order

1. Codex 提交并推送 Phase 4 协调基线，建立独立 branch/worktree；不在其中实现业务代码。
2. OpenCode Task 0：审计 -> 规格/ADR/计划 -> 自审 -> commit/push -> 创建以 `codex/phase3-spec-plan` 为 base 的 draft PR。
3. OpenCode Tasks 1-7 按章程顺序执行。每个 Task 只有在 local checks 和 exact-SHA GitHub CI 通过、P0/P1/P2 清零后才能内部接受并继续。
4. OpenCode 完成最终 handoff 后停止，状态保持 `review`；Codex 再做完整 diff/commit 审查、冷审、独立验证和实验评价。
5. rebase、冲突修复、迁移/schema/policy 变化或实质修改后，受影响证据失效并必须在新 SHA 重跑。OpenCode 不得自行 rebase、merge、force-push、写 `main` 或修改其他 worktree。

## Worktree State

- `health` 根 worktree：当前 `codex/phase3-spec-plan`，用于协调基线和 Phase 3 draft PR。未跟踪 `.opencode/package-lock.json` 与当前工作无关，保持未暂存、未提交。
- Phase 4 独立 worktree/branch 将由 Codex 从本协调基线创建为 `health-worktrees/phase4-opencode-implementation` / `codex/phase4-opencode-implementation`；创建后在本节记录精确 SHA。
- Phase 3 单一实现 worktree 为 `health-worktrees/phase3-opencode-implementation`，分支 `codex/phase3-opencode-implementation`，从 `c49eb618759ff85d7235f515b57c9d3fad38d6cb` 创建；旧 Task 1 worktree/分支已在确认干净后移除。
- Phase 2 Task worktree 是干净历史实现/审计 tip，不是 Phase 3 基线；可在独立 housekeeping 中移除，分支和历史保留。
- `starlit-galaxy-rolls-21h55` 及列出的 Phase 1 历史 worktree 含未提交或冻结改动，不得删除、覆盖、提交或用作 Phase 3 基线。

## Completed Initiative References

- Phase 1：`docs/reports/phase1-exit-audit-2026-07-22.md`
- Phase 2：`docs/reports/phase2-exit-audit-2026-07-26.md`
- Phase 3：`docs/reports/phase3-exit-audit-2026-07-26.md`；远程 CI 后续事实以本账本和 PR #1 exact-SHA checks 为准。
- Phase 2 任务明细保留在 Git 历史和对应计划中，不在当前活动账本重复维护。
