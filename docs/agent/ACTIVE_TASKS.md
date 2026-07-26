# Active Agent Tasks

> 当前开发协调账本，不是产品规格。最后核对：2026-07-26。
> 所有会话先遵守根目录 `AGENTS.md` 的“开发总纲”，再读取本文件中与当前 Task 对应的行和链接。

## Current Initiative

- 阶段：Phase 2 健康档案、签到与趋势。
- 规格：`docs/specs/platform/2026-07-22-health-profile-checkins-trends.md`
- 计划：`docs/plans/platform/2026-07-22-health-profile-checkins-trends.md`
- Phase 1 最终证据：`docs/reports/phase1-exit-audit-2026-07-22.md`
- Phase 2 当前退出证据：`docs/reports/phase2-exit-audit-2026-07-26.md`（Android 冒烟未完成）。
- Phase 2 Task 0 charter 基线：`4ed1c0e`。
- 执行模式：Codex 对最终结果负责；一个 Task 一个写入者；默认只运行一个外部实现会话；只有满足 `AGENTS.md` 总纲中的隔离条件时才允许第二个实现会话并行。
- 验证交付策略：跨阶段规则见 `docs/product/roadmap.md` §13.1；当前 Task 映射见 Phase 2 计划的 `Layered Local And CI Verification`。仓库目前未配置 GitHub Actions，现有本地证据不得标记为 CI 通过。

## Status Definitions

`planned -> in_progress -> review -> fixes -> verified -> committed -> merged`；无法继续时为 `blocked`。

## Active Work

| Task | Executor | Branch / worktree | Base SHA | Status | Scope and coordination note |
| --- | --- | --- | --- | --- | --- |
| Phase 2 Task 0 | Codex coordinator + OpenCode implementation | `codex/phase2-spec-plan` / root worktree | `10f0c65` | `merged` | Phase 2 规格、Task 0-8 charter 和路线图基线；提交证据 `0e92e2c`、`4ed1c0e`。 |
| Phase 2 Task 1 | OpenCode implementation + Codex coordination | `codex/phase2-task1-health-profile-domain` / `health-worktrees/phase2-task1-health-profile-domain` | `4ed1c0e` | `merged` | 后端 health profile domain、迁移和 risk-readiness primitives；Codex 已复核真实 diff、重跑验证并集成到 Phase 2 协调分支（集成提交 `b774d7f`）。 |
| Phase 2 Task 2 | OpenCode implementation + Codex coordination | `codex/phase2-task2-health-profile-api` / `health-worktrees/phase2-task2-health-profile-api` | `495a33a` | `merged` | `GET/PUT/DELETE /api/v1/health/profile` 已实现并经 Codex 复核真实 diff、重跑验证后集成到 Phase 2 协调分支（集成提交 `50929a8`）：JWT-only 鉴权、token 派生 ownership（无 user_id 参数）、PUT 全量替换 + version 自增、GET 未配置返回显式 not-configured（profile=null，readiness=missing_required_data）、DELETE 幂等、确定性 readiness 由 Task 1 分类器计算、OpenAPI 覆盖三个方法及 request/response 组件；未改 models/risk/migration。 |
| Phase 2 Task 3 | OpenCode implementation + Codex coordination | `codex/phase2-task3-health-checkins` / `health-worktrees/phase2-task3-health-checkins` | `8e56ede` | `merged` | Daily check-in、异常疼痛追问和签到风险摘要已实现并经 Codex 复核真实 diff、重跑验证后集成到 Phase 2 协调分支（集成提交 `0e6b078`）；新增 `0005_health_checkins`，覆盖 today/history/delete、pain_followup_required、normal/caution/restricted/red_flag、daily uniqueness 和跨用户隔离；不生成训练调整或计划。 |
| Phase 2 Task 4 | OpenCode implementation + Codex coordination | `codex/phase2-task4-health-weight-grid` / `health-worktrees/phase2-task4-health-weight-grid` | `4491f6e` | `merged` | Weight CRUD、趋势元数据和 activity grid projection 已实现并经 Codex 复核真实 diff、重跑验证后集成到 Phase 2 协调分支（集成提交 `4b73ea4`）；新增 `0006_health_weight_tracking`，覆盖 manual weight CRUD、insufficient_data、移动平均趋势、activity grid 四状态、范围限制和跨用户隔离；不输出训练或饮食调整建议。 |
| Phase 2 Task 5 | OpenCode implementation + Codex coordination | `codex/phase2-task5-flutter-health-state` / `health-worktrees/phase2-task5-flutter-health-state` | `f50e193` | `merged` | Flutter models、providers、session reset 和测试已实现并经 Codex 复核真实 diff、重跑验证后集成到 Phase 2 协调分支（集成提交 `3901314`）；覆盖 health profile、today check-in、weight trend、activity grid、logout/token failure/account switch reset、parse-error 清空旧状态和 stale response 丢弃；不新增页面或 nav。 |
| Phase 2 Task 6 | OpenCode implementation + Codex coordination | `codex/phase2-task6-flutter-my-health-ui` / `health-worktrees/phase2-task6-flutter-my-health-ui` | `92fb9f8` | `merged` | My 页面健康档案、体重趋势、activity grid 和 Phase 2 数据删除 UI 已实现并经 Codex 复核真实 diff、修正体重输入边界为后端契约 `20–300 kg`、重跑验证后集成到 Phase 2 协调分支（集成提交 `3ead452`）；健康档案与 posture profile 保持分离；新增 `/profile/health`、`/profile/weight`、`/profile/grid` 子路由；不混入 Today check-in 或 bottom-nav。 |
| Phase 2 Task 7 | OpenCode implementation + Codex coordination | `codex/phase2-task7-flutter-today-checkin` / `health-worktrees/phase2-task7-flutter-today-checkin` | `bedb238` | `merged` | Today 页面 20 秒签到、异常疼痛条件追问、active_rest/safety_adjustment 有效状态、red_flag 有限升级提示、offline/networkError/parseError 显式状态、训练计划显式不可用（不渲染为可用）已实现并经 Codex 复核真实 diff、补齐 bottom-nav 行为测试、在集成验证中拆分 risk summary 测试以隔离 state 复用问题（修复提交 `6fa17e1`）、重跑 `flutter analyze --no-pub` 和全量 `flutter test --no-pub`（300 passed）后集成到 Phase 2 协调分支（集成提交 `56ff02d`）；消费 `daily_checkin_provider`；新增 `/today` 路由与 bottom-nav destination。 |
| Phase 2 Task 8 | OpenCode verification + Codex coordination | `codex/phase2-task8-phase2-exit-audit` / `health-worktrees/phase2-task8-phase2-exit-audit` | `26f785f` | `blocked` | Phase 2 E2E（新增 `test_phase2_e2e.py` 6 项）、OpenAPI 覆盖核验（无缺口）、隐私/账户隔离/删除保留验证、退出审计报告已完成；Codex 复核真实 diff 并清理 13 个预存 ruff 问题。自动化证据：后端 798 passed（含真实 PG16 集成 11 passed）、ruff clean、一次性 PG16 容器裸 CLI `alembic upgrade head/current` 通过、Flutter 300 passed、迁移头 0006。**不标记阶段完成**：Android 模拟器冒烟未执行。证据见 `docs/reports/phase2-exit-audit-2026-07-26.md`。 |

## Integration Order

1. Task 1 -> Task 2 -> Task 3 -> Task 4 按迁移和 API 契约顺序串行集成。
2. Task 5 在 Task 2-4 契约稳定后开始。
3. Task 6 和 Task 7 默认串行；只有 Codex 核对实际允许文件无重叠、无共享状态后才可并行。
4. Task 8 由 Codex 在全部实现 Task 验证并集成后执行。
5. rebase、冲突修复或集成后的旧验证证据失效，必须在新 SHA 上重跑。

## Worktree State

- `health` 根 worktree：当前 Phase 2 集成分支；Android 冒烟和退出审计收口必须验证这里的最新集成 SHA。未跟踪 `.opencode/package-lock.json` 与当前文档任务无关，保持未暂存。
- `phase2-task1-*` 至 `phase2-task8-*`：2026-07-26 核对均为干净的历史实现/审计 worktree，分支 tip 不是当前集成 SHA，不得继续验证或作为新 Task 基线；后续可在独立 housekeeping 中移除，分支和 Git 历史保留。
- `starlit-galaxy-rolls-21h55`：含未提交 Flutter/UI、资源和计划改动，保持隔离。
- `phase1-integration`、`phase1-task2`、`phase1-task6-priority-goals`、`phase1-task6_5`、`phase1-task7-posture-tools`、`phase1-task9`：含历史未提交改动，仅作冻结参考；不得删除、覆盖、顺手提交或作为新 Task 基线。

已完成且干净的 Phase 1 worktree 于 2026-07-22 从 Git worktree 登记中收敛移除；对应分支和 Git 历史保留。`phase1-task10-5-migration-contract/backend` 与 `phase1-task10-final-e2e/app` 因现有进程占用仍有磁盘残目录，但已不是 Git worktree，不得继续使用；占用释放后删除。Phase 1 的任务明细、验证计数和最终状态统一查阅退出审计，不在活动账本重复维护。
