# Active Agent Tasks

> 当前开发协调账本，不是产品规格。最后核对：2026-08-12。
> 所有会话先遵守根目录 `AGENTS.md` 的“开发总纲”，再读取本文件中与当前 Task 对应的行和链接。

## Current Initiative

- 阶段：Phase 9 Android 小范围受控试用候选准备，状态 `in_progress`；Task 0 / Gate 0
  已进入最终 metadata closure，不写业务代码。唯一业务基线为 Phase 8 exact closure
  `2ae03345a93d8cc22d0e47fcac415411798df48b`，当前分支
  `codex/phase9-controlled-trial` 从该 SHA 创建。
- Phase 9 已批准产品方向：中国大陆一般健康成年人、Android 非公开小范围候选；运营
  责任暂由项目所有者承担；Gate 0-4 只使用合成数据；live AI 和真实照片保持关闭。
- Phase 9 身份方向：“唯一邀请码 + 每名测试者独立的单机内测账号”，凭据线下发放；
  邀请资格、稳定内部用户 ID、credential provider、设备登记和会话分离，未来短信验证码
  只替换 provider，不改变授权、数据所有权、同意或删除契约。
- 用户当前无外部专业审查渠道，决定 Phase 9 暂不产生该成本。Codex 负责内部工程、
  安全、隐私材料和健康边界预审，但不能替代律师、健康专业人员或独立渗透测试意见；
  外部审查标记 `not obtained`，阻止真实健康数据试用、真实测试者正式启动和公开发布。
- Phase 9 采用单写入者 Gate：Gate 0、Gate 1 身份/鉴权、Gate 2 隐私/安全/运维、
  Gate 3B Android 可靠性和 Gate 4 最终 E2E 均由 Codex；只有 Gate 2 合约冻结后的
  Gate 3A Flutter 中文化/可访问性局部 allowlist 可交给一个 OpenCode + Claude 会话。
- 当前契约：`docs/specs/platform/2026-08-12-controlled-trial-readiness.md`、
  `docs/plans/platform/2026-08-12-controlled-trial-readiness.md`、ADR-0009。Gate 4 最高
  结论是 `controlled-trial candidate`，不授权部署、真实数据、生产凭据、分发或发布。
- 阶段：Phase 8 个人开发版验收，状态 `verified`。Gate 4 接受实现 `6c4e48bdd5a878012bc3a6377d40f76c5799fa2f`；本地 Phase8 HTTP 11/11、eval 13/13、Full 1715/0/30 条件 PG skips、Flutter 493、Android API 34 正常 8/8 + 不可达 1/1。文档候选 `fe6f18481235aea6d246c1a8166d28b2ca901483` 的严格 CI run `31506247788` 为 Fast 1015/0/11、Flutter 493、Full 1745/0/0、PostgreSQL 28/28、Phase8 全绿；最终 closure `2ae03345a93d8cc22d0e47fcac415411798df48b` 的 exact-SHA CI run `31507902602` 亦为 Fast/Flutter/Full/Phase8 全绿；P0/P1/P2 为零。
- Phase 8 已批准边界：图示自测为硬门、照片仅为另行同意的可选合成 smoke；脚本化 provider 为硬门、live 云模型不作为门；Android 模拟器为硬门、实体机可选；离线只要求明确失败/安全重试而非完整离线业务；reset 清除完整合成账户的全部域数据。
- Phase 8 采用混合单写入者模式：Gate 0、测试隔离、跨域删除、真实 HTTP、评测、CI、最终 Android/E2E 和冷审由 Codex；只有 Gate 2 合约冻结后的 Flutter 自动化锚点与驱动 Task 3 可交给一个 OpenCode + Claude 会话。Task 3 提示词只在本 metadata closure exact-SHA CI 通过后生效。
- Phase 8 当前契约位于 `docs/specs/platform/2026-08-09-personal-development-acceptance.md`、`docs/plans/platform/2026-08-09-personal-development-acceptance.md` 和 ADR-0008。现有 `FakeDio` Android tests 不是 Phase 8 真实链路证据；内部 `account_deletion` 对基础 health/training/nutrition 的覆盖缺口必须在 Gate 1 由 Codex 关闭。
- 阶段：Phase 7 弹性闭环与综合复盘，状态 `verified`。Gate 4 接受实现 SHA `7bee078b3456c71ea902446e3d92a8cd9d6c1e06`；本地 Full 1627 passed/38 个条件 PG skips、Flutter analyze clean + 472 tests、Android API 34 enabled/unavailable 2/2，严格 exact-SHA CI run `31273365507` 为 1665 passed/0 failed/0 skipped、PostgreSQL 27/27，Fast/Flutter/Full 全绿。退出审计见 `docs/reports/phase7-codex-exit-audit-2026-08-09.md`。
- Phase 7 已批准的产品边界：前台按钮可在最新确定性安全复核后直接应用同日小调整；Agent 写入仍为提案加独立确认；长期训练/营养变化只生成草案且不自动激活；体重趋势不参与训练决策；体态复查提醒仅为应用内每周期状态，不引入调度或系统通知。
- Phase 7 采用有门禁的混合单写入者模式：Gate 0、后端状态机/迁移/安全契约、跨域复盘/Agent 权限和最终 E2E 由 Codex；Gate 1 后仅 Flutter Today/Plan/周复盘局部纵切可交给一个 OpenCode + Claude 会话，严格使用计划内 allowlist，Codex 在其写入期间只读。
- Phase 7 当前规格、计划和架构决策位于 `docs/specs/training/2026-08-02-adaptive-closure-weekly-review.md`、`docs/plans/training/2026-08-02-adaptive-closure-weekly-review.md` 和 ADR-0007。Gate 0 本地与 CI 证据必须绑定候选/closure exact SHA。
- Phase 7 Gate 2 接受集成实现 SHA `52057d102941de3b3a66361ee07b895bee64ada7`：Codex 接管 OpenCode 交接，关闭普通休息日越权 mutation、原始会话身份回退、stale/安全状态误标、权威回读、周回顾严格 DTO/幂等/显式生成等 findings；本地 Flutter analyze clean、目标 122/122、全量 468/468，exact-SHA CI run `30752998183` 的 Fast/Flutter/Full 全绿。审查记录见 `docs/reports/phase7-gate2-review-2026-08-02.md`。
- Phase 7 Gate 3 接受实现 SHA `6c69f9ee07de732f3adda73cecf4e9591e0252d0`：周复盘不可变快照/replay/四周门槛、训练与营养草案来源、体态周期比较、Agent 窄权限/独立确认/隐私删除和迁移 `0012` 已经 Codex 双轮冷审；本地 Full 1617 passed/38 个条件 PG skips、Flutter analyze clean + 472 tests，严格 exact-SHA CI run `31267141017` 为 1655 passed/0 failed/0 skipped、PostgreSQL 27/27，Fast/Flutter/Full 全绿。审查记录见 `docs/reports/phase7-gate3-review-2026-08-08.md`。
- Phase 7 Gate 4 接受实现 SHA `7bee078b3456c71ea902446e3d92a8cd9d6c1e06`：完整合成 E2E、Android enabled/unavailable、隐私/版本/排除项审计和最终双轮冷审完成；closure CI 暴露的重复 OSS 删除竞态已关闭，P0/P1/P2/P3 为零。严格 CI `31273365507` 三项全绿；未 merge、部署或写 `main`。
- Phase 6 饮食推荐 MVP 状态 `verified`。Gate 4 接受实现 SHA `1ff8395c8ecd68a8fbd3c3f1e292caea363d7d2e`；本地严格 Full 1569/1569、PostgreSQL 23/23、Flutter 384、Android enabled/disabled 2/2，exact-SHA CI run `30730437996` 的 Fast/Flutter/Full 全通过；退出 closure 为 `8eeb28a3a4156eaac5763260129fdde6fedee835`。
- Phase 6 Gate 0 基线为 Phase 5 关闭 SHA `5b268445faab0578ace23b9ecd9757449155a44f`；当前规格、实施计划与 ADR 位于 `docs/specs/nutrition/2026-07-30-nutrition-recommendation-mvp.md`、`docs/plans/nutrition/2026-07-30-nutrition-recommendation-mvp.md`、ADR-0005/0006。
- Phase 6 采用 Codex 单写入者顺序模式。营养公式、BMI/受限范围、过敏硬排除、食物/图片许可、迁移、Agent 权限和最终 Android E2E 均由 Codex 实现并在 Gate 1-4 做冷启动 findings-first 复审；不把这些高风险契约委派给外部实现 Agent。
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
| Phase 9 Task 0 | Codex specification, architecture, safety/privacy audit, task split, cold review, CI, and Gate 0 closure | `codex/phase9-controlled-trial` / current worktree | `2ae03345a93d8cc22d0e47fcac415411798df48b` | `committed` | 文档候选 `b828b046baaa8c74186396481b52713828586570` 本地 Fast/Flutter 通过；metadata 候选 `af508a795c340226fae1ddabec0a42f13a9fd192` 的严格 CI `31559582176` 为 Fast 1015/0/11、Flutter 493、Full 1745/0/0、PG 28/28、Phase8 11/11 + 13/13。仅 7 个 Gate 0 文档文件，无业务代码；最终 status commit 必须通过自身 exact-SHA CI 才可宣布 Gate 0 verified。 |
| Phase 9 Task 1 | Codex sole identity/auth/config writer, cold reviewer, CI operator, and Gate 1 acceptor | implementation branch/worktree to be created from Gate 0 exact closure | Gate 0 exact closure TBD | `planned` | 唯一邀请码、独立账号、单活动设备、session rotation/revocation、provider-neutral auth 和候选配置 fail-closed；不得接短信/邮件、真实联系方式或生产凭据。 |
| Phase 9 Task 2 | Codex sole privacy/security/operations writer and Gate 2 acceptor | same implementation branch/worktree | accepted Gate 1 SHA TBD | `planned` | 数据流、同意/导出/删除/备份、威胁模型、供应链、日志/监控和事故 runbook；只用合成数据；外部专业审查保持 not obtained。 |
| Phase 9 Task 3A | One OpenCode + Claude Flutter writer; Codex review/takeover and acceptance | separate branch/worktree from accepted Gate 2 SHA | accepted Gate 2 SHA TBD | `planned` | 仅冻结的 Flutter 中文化/可访问性 allowlist；禁止 backend/auth/API/migration/健康规则/provider/依赖/CI；OpenCode 报告不是验收。 |
| Phase 9 Task 3B | Codex sole Android reliability/E2E writer and Gate 3 acceptor | Phase 9 implementation branch/worktree | accepted Gate 2 SHA plus reviewed 3A commit | `planned` | API 设备矩阵、慢网/断网/不可达、token 过期、Asia/Shanghai 边界、兼容/升级/回滚；Phase9 synthetic runner/CI。 |
| Phase 9 Task 4 | Codex sole final E2E writer, cold reviewer, CI operator, and exit acceptor | Phase 9 implementation branch/worktree | accepted Gate 3 SHA TBD | `planned` | Full/Flutter/Phase8/Phase9/Android、隐私 artifact scan、事故演练、exit audit 和 exact-SHA CI；最高结论 controlled-trial candidate，仍不得真实试用/部署/发布。 |
| Phase 8 Task 0 | Codex specification, architecture, safety/privacy audit, task split, cold review, CI, and Gate 0 closure | `codex/phase8-spec-plan` / `health-worktrees/phase8-spec-plan` | `36be9a0f0cd989f32c8f4f7f7b9e2bc5fb4c66e6` | `committed` | 本地接受候选 `02229fa566d5765d75ef45a379b6800fef84ae53`；closure `ad876d1b8b60a386f970ff1dfcd4ea78907b67b9` 的 CI `31296538532` 为 Fast 936/0/10、Flutter 472、Full 1665/0/0、PG 27/27，三项全绿；P0/P1/P2 为零。 |
| Phase 8 Task 1 | Codex sole privacy/isolation writer, cold reviewer, CI operator, and Gate 1 acceptor | `codex/phase8-implementation` / `health-worktrees/phase8-implementation` | `ad876d1b8b60a386f970ff1dfcd4ea78907b67b9` | `committed` | 接受候选 `b964de14ecd6be3cde042223e2fd92cef488d4e3`；closure `3de6d3f1b47b6403e321710b4216eeb81636aa6a` 的 CI `31305119808` 为 Full 1687/0/0、PG 28/28，P0/P1/P2 为零。 |
| Phase 8 Task 2 | Codex sole real-HTTP runner, evaluation, CI, cold reviewer, and Gate 2 acceptor | `codex/phase8-implementation` / `health-worktrees/phase8-implementation` | `3de6d3f1b47b6403e321710b4216eeb81636aa6a` | `committed` | 接受实现 `cedda243221f0b04ac44d5dda816559201c48103`；本地 HTTP 11/11、eval 13/13、Fast 1007/0/11、Full 1707/0/30；严格 CI `31317248713` 为 Fast 1007/0/11、Flutter 474、Full 1737/0/0、PostgreSQL 28/28、Phase8 HTTP/eval 全绿。六轮独立冷审最终 P0/P1/P2/P3 全零，报告见 `docs/reports/phase8-gate2-review-2026-08-09.md`。 |
| Phase 8 Task 3 | OpenCode initial Flutter writer ended; Codex sole takeover writer, reviewer, CI operator, and Gate 3 acceptor | `codex/phase8-flutter-driver` / `health-worktrees/phase8-flutter-driver` | Gate 2 closure `01290da1eac242dc0ff3e9f39a552580c3edcd8a` | `verified` | 接受实现 `de7e799255e1554bb22fe318f29b460a7a6ea7a7`、closure `0a027b35ccffa7c92944cac0eb6be9557f687923`。冷审 P0/P1/P2/P3 全零；本地 HTTP 11/11、eval 13/13、Fast 1003/0/23、Flutter 492、Full 1715/0/30、harness 35/35、Android 8/8；严格 CI `31334065045` 为 Fast 1015/0/11、Flutter 492、Full 1745/0/0、PostgreSQL 28/28、Phase8 HTTP/eval 全绿。报告见 `docs/reports/phase8-gate3-review-2026-08-10.md`。 |
| Phase 8 Task 4 | Codex sole Android replay, visual/privacy cold reviewer, documentation, CI, and final acceptor | `codex/phase8-flutter-driver` / `health-worktrees/phase8-flutter-driver` | Gate 3 final closure `ffb97ade27746ffeaf0826f762a2b7f8e7d90423` | `verified` | 接受实现 `6c4e48bdd5a878012bc3a6377d40f76c5799fa2f`；本地 Phase8 11/11 + 13/13、Full 1715/0/30 条件 PG skips、Flutter 493、Android API 34 正常 8/8 + 不可达 1/1，10 张合成截图目检及端口/DB/reset/隐私闭环通过。文档候选 `fe6f18481235aea6d246c1a8166d28b2ca901483` 的严格 CI `31506247788` 为 Fast 1015/0/11、Flutter 493、Full 1745/0/0、PG 28/28、Phase8 全绿；P0/P1/P2 为零。不得 merge、部署、写 `main`、使用真实健康数据/照片/生产凭据或 live AI。 |
| Phase 3 Task 0 | Codex coordinator | `codex/phase3-spec-plan` / root worktree | `1818e74` | `committed` | 规格、来源/许可 pin、workout.cool 对照矩阵、Tasks 0-7 charters、CI 分层和实验评价口径；独立复核的 4 P1、5 P2、2 P3 已全部关闭；commit `2ed211a`。 |
| Phase 3 Tasks 1-7 | OpenCode + Claude implementation; Codex final acceptance and fixes | `codex/phase3-opencode-implementation` / `health-worktrees/phase3-opencode-implementation` | `c49eb618759ff85d7235f515b57c9d3fad38d6cb` | `merged` | OpenCode handoff `9ccaa35` failed first-pass acceptance. Codex closed findings in `423bf55`; local Full `989 passed`, PostgreSQL `13/13`; integration closure `e7fd6d9` and CI dependency test fix `8459384`. PR #1 remote Fast/Full both pass at `8459384`; draft remains unmerged. |
| Phase 4 Tasks 0-7 | OpenCode + selected Claude model; Codex final acceptance and fixes | `codex/phase4-opencode-implementation` plus review worktree `health-worktrees/phase4-codex-review` | `b7f8391e17a2adbb4ae52d012b360d17ff4550fd` | `verified` | OpenCode handoff `2a409e8` failed first-pass acceptance. Codex closed week progression, current-plan validation, substitution safety, full idempotency, duration, profile-equality, SVG, and execution-state findings in `c308189`; audit commit `dd31d21`; status commit `e560552`. Local Full: 1074 passed/0 failed/0 skipped, PostgreSQL 18/18; Flutter analyze clean + 322 tests. Exact-SHA CI run `30272758915` on `e560552`: Fast/Flutter/Full all success. Audit: `docs/reports/phase4-codex-exit-audit-2026-07-27.md`. PR #2 remains draft and unmerged. |
| Phase 5 Task 0 | Codex author; OpenCode independent Gate 0 reviewer | `codex/phase5-spec-plan` / `health-worktrees/phase5-spec-plan` | `e560552` | `committed` | 接受的规格 SHA `f6c2eae`；首轮 2 P2/4 P3 已全部关闭，独立复审 P0/P1/P2/P3 全零。 |
| Phase 5 Task 1 | OpenCode primary implementation and CI; Codex Gate 1 review/fixes | `codex/phase5-opencode-implementation` / `health-worktrees/phase5-opencode-implementation` | `f6c2eae` plus Gate 0 closure metadata | `committed` | Gate 1 接受 SHA `3df574b`；typed context、静态 read registry/adapters、时区、安全预路由、HMAC 指纹和最小 provider context 已由 Codex 独立修复、复核、提交并通过 exact-SHA Fast/Flutter/Full CI。 |
| Phase 5 Tasks 2-3 | OpenCode primary implementation and CI; Codex Gate 2 review/fixes | same implementation branch/worktree | accepted Gate 1 SHA `3df574b` plus Batch B handoff metadata | `committed` | Gate 2 接受实现 `57facf2`；consent/audit/proposal persistence、migration、privacy gate、transaction-neutral domain operations 和 confirmed writes 已由 Codex 独立修复、复核、提交并通过 exact-SHA Fast/Flutter/Full CI。 |
| Phase 5 Task 4 | Codex implementation and independent cold review | same implementation branch/worktree after Gate 2 coordinator handoff | Gate 2 coordinator handoff `cb9b4b1` | `committed` | Gate 3 接受 `9af9bdc`；本地 Full 1383/1383、PostgreSQL 20/20，exact-SHA CI Fast/Flutter/Full 全通过。 |
| Phase 5 Tasks 5-7 | Codex implementation, cold review, CI and Gate 4 acceptance | same implementation branch/worktree after `9af9bdc` | `9af9bdc` | `committed` | Gate 4 接受 `517d548`；Flutter Agent、E2E、Android enabled/unconsented/disabled 与退出审计完成。本地 Full 1387/1387、Flutter 361；CI `30517131521` 全通过。Phase 5 状态 `verified`，PR #3 保持 draft/unmerged。 |
| Phase 6 Task 0 | Codex specification, source/license research, and cold review | `codex/phase6-spec-plan` / `health-worktrees/phase6-spec-plan` | `5b268445faab0578ace23b9ecd9757449155a44f` | `verified` | 契约候选 `0109f96` 与 closure `8ef22b4`；P0/P1/P2 为零，closure exact-SHA CI run `30696742677` 的 Fast/Flutter/Full 全通过。 |
| Phase 6 Tasks 1-6 | Codex sole implementation writer, cold reviewer, CI operator, and final acceptor | `codex/phase6-implementation` / `health-worktrees/phase6-implementation` | `8ef22b4a9a1056ce94570b0c95483a124574243c` | `committed` | Gate 4 接受 `1ff8395`：确定性营养规则/数据、生命周期/API、Agent Tools、Flutter、完整合成 E2E、源/媒体审计及 Android enabled/disabled 完成。本地 Full 1569/0 skipped、PostgreSQL 23/23、Flutter 384；CI `30730437996` 全通过。Phase 6 状态 `verified`，PR #5 保持 draft/unmerged。 |
| Phase 7 Task 0 | Codex specification, architecture, task split, cold review, CI, and Gate 0 closure | `codex/phase7-spec-plan` / current worktree | `8eeb28a3a4156eaac5763260129fdde6fedee835` | `committed` | 契约 `dceceb7` 已通过本地 exact-SHA Fast/Flutter 和 CI `30732748723` 三项；P0/P1/P2/P3 为零。审查报告 `docs/reports/phase7-gate0-review-2026-08-02.md`；业务实现等待元数据 closure exact-SHA 验证。 |
| Phase 7 Task 1 | Codex sole high-risk backend writer and Gate 1 acceptor | `codex/phase7-implementation` / `health-worktrees/phase7-implementation` | `5edfa0fcaced135fd434629945f60c49095e6665` | `verified` | 接受实现 `a27dddc944973d25e1c974f709068c67ae6f2d00`；本地 Full 1615/0/0、PostgreSQL 25/25，CI `30744694166` 的 Fast/Flutter/Full 全绿；审查报告 `docs/reports/phase7-gate1-review-2026-08-02.md`。 |
| Phase 7 Task 2 | One OpenCode + Claude Flutter writer; Codex review/fixes/integration | `codex/phase7-flutter` / `health-worktrees/phase7-flutter` | `fbf96d389de1eb36689411fb13eaf2ce91ad34fd` | `verified` | OpenCode 交接后由 Codex 接管修复和冷审；Task 分支提交 `2fa6c3fc9e4badc84b9519e823a6674b64561e89`，接受的集成实现为 `52057d102941de3b3a66361ee07b895bee64ada7`。本地 Flutter analyze、122 个目标测试和 468 个全量测试通过；CI `30752998183` 三项全绿，P0/P1/P2 为零。 |
| Phase 7 Task 3 | Codex sole cross-domain writer and Gate 3 acceptor | `codex/phase7-implementation` / `health-worktrees/phase7-implementation` | Gate 2 closure `6b0e3b1e9fea2f65e0a1790cabdaba5c2cd69a84` | `verified` | 接受实现 `6c69f9ee07de732f3adda73cecf4e9591e0252d0`：周复盘聚合、训练/营养草案来源、体态复查状态/对比、Agent allowlist/确认/隐私与跨域删除完成；本地 Full 1617/38 条件 PG skips、Flutter 472，严格 CI `31267141017` 为 1655/0/0、PostgreSQL 27/27，P0/P1/P2 为零。 |
| Phase 7 Task 4 | Codex sole E2E writer, cold reviewer, CI operator, and final acceptor | same implementation branch/worktree | accepted Gate 3 SHA `6c69f9ee07de732f3adda73cecf4e9591e0252d0` | `verified` | Gate 4 接受 `7bee078b3456c71ea902446e3d92a8cd9d6c1e06`：完整合成 E2E、Android API 34 enabled/unavailable 2/2、最终双轮冷审和退出审计完成；closure CI 暴露的隐私删除竞态已修复。本地 Full 1627/38 条件 PG skips、Flutter 472；严格 CI `31273365507` 为 1665/0/0、PostgreSQL 27/27；P0/P1/P2/P3 为零。 |

## Integration Order

**Phase 9:**

1. Phase 9 Gate 0 仅在 `codex/phase9-controlled-trial` 上从 exact Phase 8 closure
   `2ae03345a93d8cc22d0e47fcac415411798df48b` 关闭；通过本地冷审、commit/push 和
   exact-SHA CI 后，才从该 closure 创建唯一实现分支/worktree。
2. Phase 9 Gate 1 和 Gate 2 由 Codex 在唯一实现分支顺序完成；Gate 2 接受后才可创建
   独立 OpenCode Gate 3A Flutter worktree。Gate 3A 经 Codex 验收后再集成并执行 3B。
3. Phase 9 Gate 4 只集成已验证 commit；任何 rebase、冲突修复、schema/auth/privacy/
   safety 变化都会使原证据失效并要求在新 exact SHA 重跑。

**Historical integration:**

1. OpenCode 已完成只读预审和 Gate 0 审查；Codex 收敛 finding 后，独立复审在 `f6c2eae` 通过。
2. Codex 从 Gate 0 关闭提交创建唯一实现分支/worktree；Batch A 已在 `3df574b` 通过 Gate 1，Batch B 已在 `57facf2` 通过 Gate 2。
3. Batches A-B 由 OpenCode 完成并经 Codex 验收；Batches C-D 由 Codex 直接实现、冷审、验证和操作 CI，Phase 5 已关闭。
4. Phase 6 Gate 0 closure `8ef22b4` 已通过 exact-SHA CI run `30696742677`；唯一实现分支已从该 SHA 创建。
5. Phase 6 Tasks 1-6 已在单一 Codex 实现 worktree 顺序完成；Gate 4 接受 `1ff8395`，退出审计与状态关闭在其后独立提交。
6. Phase 3、Phase 4、Phase 5 后续进入主线时仍按依赖顺序；rebase、冲突修复、迁移/schema/policy 变化或实质修改后，相关证据失效并重跑。
7. Phase 7 Gate 0 只在 `codex/phase7-spec-plan` 上关闭；接受后从 exact closure SHA 创建唯一 Codex 实现分支。Gate 1 完成后创建的 OpenCode Flutter 分支已在 Gate 2 经 Codex 验收并集成为 `52057d1`；Gate 3 接受 `6c69f9e`，Gate 4 最终接受 `7bee078`，Phase 7 状态为 `verified`。

## Worktree State

- 当前 worktree `C:\Users\Lenovo\.codex\worktrees\be24\health` 已从 Phase 8 exact
  closure `2ae03345a93d8cc22d0e47fcac415411798df48b` 切换到
  `codex/phase9-controlled-trial`，仅用于 Phase 9 Gate 0 文档、审查、提交和 CI；
  Gate 0 接受前不得写业务代码。
- Phase 7 Task 2 worktree `health-worktrees/phase7-flutter` 位于已推送分支 `codex/phase7-flutter`；OpenCode 写入已结束，Codex 接管后的已验收提交为 `2fa6c3fc9e4badc84b9519e823a6674b64561e89`，worktree 干净，不再作为 Task 3 写入目录。
- Phase 7 唯一 Codex 实现 worktree 为 `health-worktrees/phase7-implementation`，分支 `codex/phase7-implementation`，精确 base `5edfa0fcaced135fd434629945f60c49095e6665`；Gate 4 已接受并推送实现 `7bee078b3456c71ea902446e3d92a8cd9d6c1e06`，当前只允许提交退出 closure 文档。
- Phase 7 规格 worktree 为当前 Codex 规格目录，分支 `codex/phase7-spec-plan`，停在已验证 Gate 0 closure `5edfa0fcaced135fd434629945f60c49095e6665`；业务实现不在该目录写入。
- `health` 根 worktree：当前 `codex/phase3-spec-plan`，用于协调基线和 Phase 3 draft PR。未跟踪 `.opencode/package-lock.json` 与当前工作无关，保持未暂存、未提交。
- Phase 6 规格 worktree 为 `health-worktrees/phase6-spec-plan`，分支 `codex/phase6-spec-plan`，停在已验证 closure `8ef22b4`。
- Phase 6 唯一实现 worktree 为 `health-worktrees/phase6-implementation`，分支 `codex/phase6-implementation`，精确 base `8ef22b4a9a1056ce94570b0c95483a124574243c`；Gate 4 已接受实现 `1ff8395`，当前仅提交退出关闭文档。
- Phase 5 规划 worktree 为 `health-worktrees/phase5-spec-plan`，分支 `codex/phase5-spec-plan`；保留用于 Codex 规格、Gate 和任务提示词工作。
- Phase 5 唯一实现 worktree 为 `health-worktrees/phase5-opencode-implementation`，分支 `codex/phase5-opencode-implementation`；实现停在 Gate 4 接受提交 `517d548`，仅剩本退出文档提交，PR #3 未合并。
- Phase 4 OpenCode worktree 为 `health-worktrees/phase4-opencode-implementation`，停在原始交接 `2a409e8`；Codex 最终审查 worktree 为 `health-worktrees/phase4-codex-review`，分支 `codex/phase4-final-review`，停在 `e560552`。
- Phase 3 单一实现 worktree 为 `health-worktrees/phase3-opencode-implementation`，分支 `codex/phase3-opencode-implementation`，从 `c49eb618759ff85d7235f515b57c9d3fad38d6cb` 创建；旧 Task 1 worktree/分支已在确认干净后移除。
- Phase 2 Task worktree 是干净历史实现/审计 tip，不是 Phase 3 基线；可在独立 housekeeping 中移除，分支和历史保留。
- `starlit-galaxy-rolls-21h55` 及列出的 Phase 1 历史 worktree 含未提交或冻结改动，不得删除、覆盖、提交或用作 Phase 3 基线。

## Completed Initiative References

- Phase 9 Gate 0：本地候选 `b828b04`，metadata 候选 `af508a7` 的严格 CI run
  `31559582176` 为 Fast/Flutter/Full/Phase8 全通过；最终 status commit 仍须通过自身
  exact-SHA CI。审查报告 `docs/reports/phase9-gate0-review-2026-08-12.md`。
- Phase 1：`docs/reports/phase1-exit-audit-2026-07-22.md`
- Phase 2：`docs/reports/phase2-exit-audit-2026-07-26.md`
- Phase 3：`docs/reports/phase3-exit-audit-2026-07-26.md`；远程 CI 后续事实以本账本和 PR #1 exact-SHA checks 为准。
- Phase 4：OpenCode 原始交接 `docs/reports/phase4-opencode-handoff-2026-07-27.md`；Codex 独立审计 `docs/reports/phase4-codex-exit-audit-2026-07-27.md`。
- Phase 5 Gate 0：`docs/reports/phase5-gate0-review-2026-07-29.md`，接受规格 `f6c2eae`。
- Phase 5 Gate 1：`docs/reports/phase5-gate1-review-2026-07-29.md`，接受实现 `3df574b`。
- Phase 5 Gate 2：`docs/reports/phase5-gate2-review-2026-07-29.md`，接受实现 `57facf2`。
- Phase 5 Gate 3：接受实现 `9af9bdc`，CI run `30511741109`。
- Phase 5 退出：`docs/reports/phase5-codex-exit-audit-2026-07-30.md`，接受实现 `517d548`，CI run `30517131521`。
- Phase 5 最终关闭：文档 SHA `5b26844`，CI run `30517649834` 的 Fast/Flutter/Full 全通过。
- Phase 8 Gate 0：closure `ad876d1`，CI run `31296538532` 全绿；审查报告 `docs/reports/phase8-gate0-review-2026-08-09.md`。
- Phase 8 Gate 1：接受实现 `b964de1`、closure `3de6d3f`，CI run `31305119808` 全绿；审查报告 `docs/reports/phase8-gate1-review-2026-08-09.md`。
- Phase 8 Gate 2：接受实现 `cedda24`，CI run `31317248713` 的 Fast/Flutter/Full/Phase8 全绿；审查报告 `docs/reports/phase8-gate2-review-2026-08-09.md`。
- Phase 8 Gate 3：接受实现 `de7e799`、closure `0a027b3`；本地 HTTP 11/11、eval 13/13、Fast 1003/0/23、Flutter 492、Full 1715/0/30、harness 35/35、Android 8/8；严格 CI `31334065045` 为 Fast 1015/0/11、Flutter 492、Full 1745/0/0、PostgreSQL 28/28、Phase8 全绿，冷审 P0-P3 全零；报告 `docs/reports/phase8-gate3-review-2026-08-10.md`。
- Phase 6 Gate 0：候选 `0109f96`，closure `8ef22b4`，CI run `30696742677` 的 Fast/Flutter/Full 全通过；审查报告 `docs/reports/phase6-gate0-review-2026-07-30.md`。
- Phase 6 Gate 1：接受实现 `b3c1bfa`，CI run `30702540222` 的 Fast/Flutter/Full 全通过；审查报告 `docs/reports/phase6-gate1-review-2026-08-01.md`。
- Phase 7 Gate 1：接受实现 `a27dddc`，本地 Full 1615/0/0、PostgreSQL 25/25，CI run `30744694166` 的 Fast/Flutter/Full 全通过；审查报告 `docs/reports/phase7-gate1-review-2026-08-02.md`。
- Phase 7 Gate 2：接受集成实现 `52057d1`，本地 Flutter analyze clean、目标 122/122、全量 468/468，CI run `30752998183` 的 Fast/Flutter/Full 全通过；审查报告 `docs/reports/phase7-gate2-review-2026-08-02.md`。
- Phase 7 Gate 3：接受实现 `6c69f9e`，本地 Full 1617/38 条件 PG skips、Flutter analyze clean + 472，严格 CI run `31267141017` 为 1655/0/0、PostgreSQL 27/27，Fast/Flutter/Full 全通过；审查报告 `docs/reports/phase7-gate3-review-2026-08-08.md`。
- Phase 7 退出：接受实现 `7bee078`，本地 Full 1627/38 条件 PG skips、Flutter analyze clean + 472、Android API 34 enabled/unavailable 2/2，严格 CI run `31273365507` 为 1665/0/0、PostgreSQL 27/27，Fast/Flutter/Full 全通过；退出审计 `docs/reports/phase7-codex-exit-audit-2026-08-09.md`。
- Phase 6 Gate 2：接受 `2160bdc`，CI run `30708939766` 的 Fast/Flutter/Full 全通过；审查报告 `docs/reports/phase6-gate2-review-2026-08-01.md`。
- Phase 6 Gate 3：接受 `93e78a6`，CI run `30712669331` 的 Fast/Flutter/Full 全通过；审查报告 `docs/reports/phase6-gate3-review-2026-08-02.md`。
- Phase 6 退出：接受实现 `1ff8395`，CI run `30730437996` 的 Fast/Flutter/Full 全通过；退出审计 `docs/reports/phase6-codex-exit-audit-2026-08-02.md`。
- Phase 2 任务明细保留在 Git 历史和对应计划中，不在当前活动账本重复维护。
