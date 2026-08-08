# Phase 7 Codex 退出审计

> 日期：2026-08-09。范围：Gate 0 契约、Tasks 1-4 实现、跨端合成验收、
> Android 设备回放和 exact-SHA CI。本结论仅批准合成数据个人开发版的工程验收，
> 不批准医疗用途、真实健康数据处理、公开发布、部署或合并到 `main`。

## 结论

状态：**verified**。

Gate 4 接受 `codex/phase7-implementation` 上的实现 SHA
`7bee078b3456c71ea902446e3d92a8cd9d6c1e06`。Codex 完成两轮 findings-first
冷审，未留下 P0/P1/P2/P3。分支已推送但未合并；当前没有为该分支创建 PR。

## Findings First

### 已关闭 P1/P2

1. 真实健康档案的器材适配器读取了不存在的扁平字段，使已有自重器材的用户被误判为
   缺少器材并进入 `clarification_required`。现改为读取权威嵌套
   `profile.equipment.bodyweight/resistance_band`，完整 API E2E 覆盖真实档案路径。
2. Plan 页在 Today 服务不可用时虽已失败关闭，但缺少稳定设备验收锚点。现增加
   `today-status-unavailable`，Android unavailable 流明确验证无调整按钮且零 POST。
3. Fast 验证清单未包含最终 Phase 7 E2E。现将 `test_phase7_e2e.py` 纳入
   `FAST_TEST_TARGETS`，并用 runner 回归测试要求 Phase 5/6/7 E2E 均存在。
4. 首次 closure 严格 CI 暴露隐私删除竞态：初始 purge 的短 lease 过期后，重试 worker
   可先完成 OSS 删除；等待用户锁的初始路径取得锁后仍使用陈旧 ORM 状态，导致同一对象
   删除被调用两次。现于锁内权威 refresh，已完成或已 scrub 的 operation 直接 no-op；
   PostgreSQL 并发回归和完整严格 CI 均通过。

### 冷审结论

- 后端 E2E 通过 JWT、FastAPI、服务层和持久化执行；只固定合成时钟、确定性安全上下文
  和营养上下文。测试禁止任何 `DashScopeProvider.decide` 调用。
- 疼痛、restricted 和 red flag 均验证零 adjustment 写入；stale overlay 必须显式刷新；
  replay 保持同一 adjustment identity。
- `active_rest` 仅表示无法合法顺延时的确定性回退；`intentional_rest` 仅是用户反馈事实，
  两者没有混用。
- 周复盘先呈现事实再呈现提案；体重只展示，不进入训练决策；训练与营养长期变化只生成
  draft，原 active plan 不变；体态 dismissal 不隐藏后续比较或安全状态。
- API 响应、复盘快照和审计载荷经隐私扫描，不暴露备注、疼痛细节、原始体重值、照片、
  餐食或聊天文本；测试只使用合成健康记录，不含密钥或真实健康数据。

## 验证证据

所有最终本地证据均绑定 accepted SHA
`7bee078b3456c71ea902446e3d92a8cd9d6c1e06`：

| 命令或检查 | 结果 |
| --- | --- |
| `python scripts/verify.py fast` | ruff clean；`927 passed / 0 failed / 19 skipped`；diff clean |
| `python scripts/verify.py full` | `1627 passed / 0 failed / 38 conditional PG skips`，总计 `1665`；diff clean |
| `flutter analyze` | no issues |
| `flutter test` | `472 passed` |
| `flutter test integration_test/phase7_adaptive_review_smoke_test.dart -d emulator-5554` | Android 14/API 34，enabled 与 unavailable fail-closed 流程 `2/2` |
| `python -m pytest tests/test_phase7_e2e.py -q` | `9 passed` |
| 隐私删除状态机 + Phase 7 E2E 聚焦集合 | `79 passed / 1 expected PG skip` |
| 训练 API/周回顾/Phase 6-7 聚焦集合 | `66 passed` |
| Phase 7 迁移与 E2E 隔离数据库集合 | `13 passed / 3 conditional PG skips` |

本机未配置 `PG_TEST_DSN`、`TEST_POSTGRES_DSN` 或 `DATABASE_URL`，Docker daemon
查询超时，因此本地 PostgreSQL 不可用。上述 38 个条件 skip 没有被改写为通过；严格证据
由 GitHub PostgreSQL 16 服务容器提供。

## Exact-SHA CI

严格验收 run
[31273365507](https://github.com/Lizz-666/health-agent/actions/runs/31273365507)
的 event SHA 与 checked-out SHA 均为
`7bee078b3456c71ea902446e3d92a8cd9d6c1e06`：

- Fast：success；ruff clean；`936 passed / 0 failed / 10 expected skips`；diff clean。
- Flutter：success；analyze clean；`472 tests passed`。
- Full：success；`1665 passed / 0 failed / 0 skipped`；
  `VERIFY_REQUIRE_PG=1`；PostgreSQL expected `27` / actual `27`，版本证据存在。

首次候选 `56058591cb970c5bfa0627bb0d5effadbaa8fcc3` 的严格 run
[31271328357](https://github.com/Lizz-666/health-agent/actions/runs/31271328357)
曾为 `1665/0/0`。其文档 closure `8a19af7608ef873b5155f55361125f4e1bb27b96`
在 run
[31272112939](https://github.com/Lizz-666/health-agent/actions/runs/31272112939)
复现 `test_pg_initial_purge_lease_does_not_duplicate_oss_delete`：
`1664 passed / 1 failed / 0 skipped`，因此该 closure 未被接受。Codex 修复真实竞态后，
以最终 `7bee078b` 和 run `31273365507` 重新完成全部本地/设备/严格 CI 验证。

更早的辅助 run
[31271174140](https://github.com/Lizz-666/health-agent/actions/runs/31271174140)
未传 `run_full=true`，因此 Full 被条件跳过。它只提供 Fast/Flutter 辅助证据，不属于
Gate 4 验收证据，也没有被用来替代严格 run。

## 退出标准

- 忙碌、疲劳、无时间/漏练、主动休息、疼痛、restricted/red flag 和 stale 均有明确、
  可回放的结构化结果；安全阻断不会被缩短、顺延、恢复替换或 active rest 绕过。
- Today overlay 保留原始与有效会话身份、来源/目标日期、原因、kind 和历史；并发、幂等、
  stale 和 replay 由服务端约束。
- 周复盘是不可变、带输入指纹和版本 pin 的快照；缺失数据保持 unavailable，不转成零或失败。
- 训练/营养提案只生成 draft，仍需既有独立确认才能激活；Agent 只有窄工具权限，不能注入
  日期、动作、策略、阈值或安全身份。
- 体态复查是应用内周期状态，不引入后台调度或系统通知；普通 dismissal 不影响安全信息。
- 迁移 `0011`/`0012` 的 upgrade/downgrade、约束、外键和 PostgreSQL parity 已在严格 CI
  验证；删除路径覆盖 Phase 7 rows 和 Agent 引用。

## 残余边界

- Phase 7 没有独立运行时 feature flag。Android 第二条流程验证服务 unavailable 时的
  失败关闭；后端 enabled 流同时在禁止 live provider 调用时通过，证明确定性核心不依赖 AI。
- 本阶段不提供公开发布、后台提醒调度、系统通知、真实数据遥测、医疗诊断/康复、治疗性营养
  或自动激活长期变化。
- 个人开发版之外仍需要独立的隐私/合规、可观测性、事件响应、容量、应用商店和发布门。
- 没有执行 merge、部署、写 `main`、真实健康数据/照片处理或生产凭据访问。

## 回滚

Phase 7 schema 为 additive；应用回滚会忽略新增表和 nullable origin 列。迁移 downgrade
会删除 Phase 7 历史或移除 origin 关联，只允许在可丢弃合成数据库执行。任何真实环境回滚、
破坏性迁移或数据保留决定都需要单独授权，本审计未授权这些操作。

## 范围关闭

Phase 7 在 `codex/phase7-implementation` 上完成工程验收。后续只能从最终 closure SHA
继续 Phase 8；若发生 rebase、冲突修复、schema/policy 或实质代码变更，本审计证据失效，
必须在新 exact SHA 上重跑风险匹配的本地验证和严格 CI。
