# Active Agent Tasks

> 当前开发协调账本，不是产品规格。最后核对：2026-07-30。
> 所有会话先遵守根目录 `AGENTS.md` 的“开发总纲”，再读取本文件中与当前 Task 对应的行和链接。

## Current Initiative

- 阶段：Phase 5 Agent MVP 已在实现 SHA `517d548` 通过 Gate 4 和最终独立验收，状态 `verified`；下一步从该关闭基线规划 Phase 6 Gate 0，尚未开始 Phase 6 代码。
- Phase 4 已通过 Codex 最终独立验收，状态 `verified`；PR #2 保持 draft、尚未合并，因此不记为 `merged`。
- Phase 5 协作章程：`docs/agent/PHASE5_COLLABORATION_CHARTER.md`。
- Phase 5 首轮 Gate 0 审查在 `8ac8858` 报告 2 P2/4 P3；修复后的 `f6c2eae` 独立复审为 PASS、P0/P1/P2/P3 全零。记录见 `docs/reports/phase5-gate0-review-2026-07-29.md`。
- Phase 5 Gate 1 最终接受 SHA 为 `3df574b7051ef9a9342816c9b116f436ddf8513c`：Codex 关闭 ownership-first reads、严格输入/输出、最小上下文和指纹 fail-closed findings；focused 139 passed，Fast 408 passed/0 failed/7 个预期 PG skips；exact-SHA CI Fast/Flutter/Full 全通过。记录见 `docs/reports/phase5-gate1-review-2026-07-29.md`。
- Phase 5 Gate 2 最终接受实现 SHA 为 `57facf2a7e4589ef843645d7549b89538f1e79fe`：Codex 关闭提案参数/所有权/同意竞态、确认时区、双层幂等、最新数据和普通按钮并发写 findings；本地 Fast 478 passed，严格 Full 1293 passed/0 failed/0 skipped、PostgreSQL 20/20；exact-SHA CI Fast/Flutter/Full 全通过。记录见 `docs/reports/phase5-gate2-review-2026-07-29.md`。
- Phase 5 Gate 3 接受 SHA 为 `9af9bdce091c8c7678ba59ab8e9abaaa9393c054`：provider/orchestrator、独立隐私门、JWT API、固定模板和 adversarial eval 经冷审后，本地 Full 1383 passed、PostgreSQL 20/20；CI run `30511741109` 三项通过。
- Phase 5 Gate 4 接受实现 SHA 为 `517d548164137a8999569c70f20a8cf19630d331`：Flutter Agent、完整合成 E2E、Android enabled/unconsented/disabled 流程和 test-only DB 防护已验证；本地 Full 1387 passed、Flutter 361 passed，CI run `30517131521` 三项通过。退出审计见 `docs/reports/phase5-codex-exit-audit-2026-07-30.md`。
- Phase 5 采用有门禁的混合模式：Codex 负责规格、架构、安全/隐私契约和四个风险门；OpenCode 在单一实现分支按批次主实现并操作 CI，每个风险门停止等待独立验收。
- Phase 5 精确规格基线为 `f6c2eae59c784398fbf1ae38967be3c2ee720940`。实现只能从本次 Gate 0 关闭提交创建的命名分支开始，不能从路线图、`main` 或旧 worktree 直接开始。
- “当日小调整”范围已收敛为复用 Phase 4 用户主动替换和结构化反馈；自动缩短、顺延和恢复性调整仍属于 Phase 7。
- Phase 5 原 P0 隐私缺口已关闭：独立云处理告知/同意、撤回、Agent 数据删除和证据隐私门均有持久化来源与测试；任何单一配置开关仍不能启用 live provider。
- Phase 2 最终证据：`docs/reports/phase2-exit-audit-2026-07-26.md`；Final Closure commit `1818e74`。用户接受的残余风险仍是 Android 人工逐屏业务回放未执行，不改写为已通过。
- Phase 3 基线：Task 0 主体提交 `2ed211a`（base `1818e74`）；整阶段 OpenCode 实现实验的精确 base 为 `c49eb618759ff85d7235f515b57c9d3fad38d6cb`。
- Phase 3 远程证据：PR `#1` 在精确 SHA `8459384dbbcb339e8d78fa243b4e8690c76b7bba` 上 Fast 和 Full GitHub CI 均成功；PR 仍为 draft，尚未合并到 `main`。
- Phase 4 实验结论：整阶段委派提高了实现吞吐，但首轮交付未通过，Codex 最终修复跨层安全和正确性问题；Phase 5 不复用“完成后一次终验”的模式。
- Phase 5 安全边界：OpenCode 不得绕过或放宽既有安全引擎；未明确情况 fail closed。新健康阈值必须有当前权威一手来源和版本化策略。会实质改变产品/安全结果的歧义由 Codex 在规格中收敛。
- Phase 5 并行规则：只有一个实现写入者。OpenCode 可在同一实现会话中顺序推进，但必须在 Gate 1-4 停止；Codex 审查期间不与其并行修改同一分支。
- Phase 5 验证策略：每个 Task 完成 focused local 和适用 CI，证据绑定 exact SHA。只读预审不得 push；Gate 0 后仅命名的实现分支可使用既有 branch push、draft PR 和 CI 授权，不得 merge、force-push、写 `main`、改 secrets/settings 或部署。

## Status Definitions

`planned -> in_progress -> review -> fixes -> verified -> committed -> merged`；无法继续时为 `blocked`。

## Active Work

| Task | Executor | Branch / worktree | Base SHA | Status | Scope and coordination note |
| --- | --- | --- | --- | --- | --- |
| Phase 3 Task 0 | Codex coordinator | `codex/phase3-spec-plan` / root worktree | `1818e74` | `committed` | 规格、来源/许可 pin、workout.cool 对照矩阵、Tasks 0-7 charters、CI 分层和实验评价口径；独立复核的 4 P1、5 P2、2 P3 已全部关闭；commit `2ed211a`。 |
| Phase 3 Tasks 1-7 | OpenCode + Claude implementation; Codex final acceptance and fixes | `codex/phase3-opencode-implementation` / `health-worktrees/phase3-opencode-implementation` | `c49eb618759ff85d7235f515b57c9d3fad38d6cb` | `merged` | OpenCode handoff `9ccaa35` failed first-pass acceptance. Codex closed findings in `423bf55`; local Full `989 passed`, PostgreSQL `13/13`; integration closure `e7fd6d9` and CI dependency test fix `8459384`. PR #1 remote Fast/Full both pass at `8459384`; draft remains unmerged. |
| Phase 4 Tasks 0-7 | OpenCode + selected Claude model; Codex final acceptance and fixes | `codex/phase4-opencode-implementation` plus review worktree `health-worktrees/phase4-codex-review` | `b7f8391e17a2adbb4ae52d012b360d17ff4550fd` | `verified` | OpenCode handoff `2a409e8` failed first-pass acceptance. Codex closed week progression, current-plan validation, substitution safety, full idempotency, duration, profile-equality, SVG, and execution-state findings in `c308189`; audit commit `dd31d21`; status commit `e560552`. Local Full: 1074 passed/0 failed/0 skipped, PostgreSQL 18/18; Flutter analyze clean + 322 tests. Exact-SHA CI run `30272758915` on `e560552`: Fast/Flutter/Full all success. Audit: `docs/reports/phase4-codex-exit-audit-2026-07-27.md`. PR #2 remains draft and unmerged. |
| Phase 5 Task 0 | Codex author; OpenCode independent Gate 0 reviewer | `codex/phase5-spec-plan` / `health-worktrees/phase5-spec-plan` | `e560552` | `committed` | 接受的规格 SHA `f6c2eae`；首轮 2 P2/4 P3 已全部关闭，独立复审 P0/P1/P2/P3 全零。 |
| Phase 5 Task 1 | OpenCode primary implementation and CI; Codex Gate 1 review/fixes | `codex/phase5-opencode-implementation` / `health-worktrees/phase5-opencode-implementation` | `f6c2eae` plus Gate 0 closure metadata | `committed` | Gate 1 接受 SHA `3df574b`；typed context、静态 read registry/adapters、时区、安全预路由、HMAC 指纹和最小 provider context 已由 Codex 独立修复、复核、提交并通过 exact-SHA Fast/Flutter/Full CI。 |
| Phase 5 Tasks 2-3 | OpenCode primary implementation and CI; Codex Gate 2 review/fixes | same implementation branch/worktree | accepted Gate 1 SHA `3df574b` plus Batch B handoff metadata | `committed` | Gate 2 接受实现 `57facf2`；consent/audit/proposal persistence、migration、privacy gate、transaction-neutral domain operations 和 confirmed writes 已由 Codex 独立修复、复核、提交并通过 exact-SHA Fast/Flutter/Full CI。 |
| Phase 5 Task 4 | Codex implementation and independent cold review | same implementation branch/worktree after Gate 2 coordinator handoff | Gate 2 coordinator handoff `cb9b4b1` | `committed` | Gate 3 接受 `9af9bdc`；本地 Full 1383/1383、PostgreSQL 20/20，exact-SHA CI Fast/Flutter/Full 全通过。 |
| Phase 5 Tasks 5-7 | Codex implementation, cold review, CI and Gate 4 acceptance | same implementation branch/worktree after `9af9bdc` | `9af9bdc` | `committed` | Gate 4 接受 `517d548`；Flutter Agent、E2E、Android enabled/unconsented/disabled 与退出审计完成。本地 Full 1387/1387、Flutter 361；CI `30517131521` 全通过。Phase 5 状态 `verified`，PR #3 保持 draft/unmerged。 |

## Integration Order

1. OpenCode 已完成只读预审和 Gate 0 审查；Codex 收敛 finding 后，独立复审在 `f6c2eae` 通过。
2. Codex 从 Gate 0 关闭提交创建唯一实现分支/worktree；Batch A 已在 `3df574b` 通过 Gate 1，Batch B 已在 `57facf2` 通过 Gate 2。
3. Batches A-B 由 OpenCode 完成并经 Codex 验收；Batches C-D 由 Codex 直接实现、冷审、验证和操作 CI，Phase 5 已关闭。
4. Phase 6 必须先从 Phase 5 关闭提交建立独立规格/计划分支，完成营养公式、安全受限模式和来源/许可 Gate 0，再创建实现 worktree。
5. Phase 3、Phase 4、Phase 5 后续进入主线时仍按依赖顺序；rebase、冲突修复、迁移/schema/policy 变化或实质修改后，相关证据失效并重跑。

## Worktree State

- `health` 根 worktree：当前 `codex/phase3-spec-plan`，用于协调基线和 Phase 3 draft PR。未跟踪 `.opencode/package-lock.json` 与当前工作无关，保持未暂存、未提交。
- Phase 5 规划 worktree 为 `health-worktrees/phase5-spec-plan`，分支 `codex/phase5-spec-plan`；保留用于 Codex 规格、Gate 和任务提示词工作。
- Phase 5 唯一实现 worktree 为 `health-worktrees/phase5-opencode-implementation`，分支 `codex/phase5-opencode-implementation`；实现停在 Gate 4 接受提交 `517d548`，仅剩本退出文档提交，PR #3 未合并。
- Phase 4 OpenCode worktree 为 `health-worktrees/phase4-opencode-implementation`，停在原始交接 `2a409e8`；Codex 最终审查 worktree 为 `health-worktrees/phase4-codex-review`，分支 `codex/phase4-final-review`，停在 `e560552`。
- Phase 3 单一实现 worktree 为 `health-worktrees/phase3-opencode-implementation`，分支 `codex/phase3-opencode-implementation`，从 `c49eb618759ff85d7235f515b57c9d3fad38d6cb` 创建；旧 Task 1 worktree/分支已在确认干净后移除。
- Phase 2 Task worktree 是干净历史实现/审计 tip，不是 Phase 3 基线；可在独立 housekeeping 中移除，分支和历史保留。
- `starlit-galaxy-rolls-21h55` 及列出的 Phase 1 历史 worktree 含未提交或冻结改动，不得删除、覆盖、提交或用作 Phase 3 基线。

## Completed Initiative References

- Phase 1：`docs/reports/phase1-exit-audit-2026-07-22.md`
- Phase 2：`docs/reports/phase2-exit-audit-2026-07-26.md`
- Phase 3：`docs/reports/phase3-exit-audit-2026-07-26.md`；远程 CI 后续事实以本账本和 PR #1 exact-SHA checks 为准。
- Phase 4：OpenCode 原始交接 `docs/reports/phase4-opencode-handoff-2026-07-27.md`；Codex 独立审计 `docs/reports/phase4-codex-exit-audit-2026-07-27.md`。
- Phase 5 Gate 0：`docs/reports/phase5-gate0-review-2026-07-29.md`，接受规格 `f6c2eae`。
- Phase 5 Gate 1：`docs/reports/phase5-gate1-review-2026-07-29.md`，接受实现 `3df574b`。
- Phase 5 Gate 2：`docs/reports/phase5-gate2-review-2026-07-29.md`，接受实现 `57facf2`。
- Phase 5 Gate 3：接受实现 `9af9bdc`，CI run `30511741109`。
- Phase 5 退出：`docs/reports/phase5-codex-exit-audit-2026-07-30.md`，接受实现 `517d548`，CI run `30517131521`。
- Phase 2 任务明细保留在 Git 历史和对应计划中，不在当前活动账本重复维护。
