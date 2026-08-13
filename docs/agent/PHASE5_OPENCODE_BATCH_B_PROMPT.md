# Phase 5 OpenCode Batch B Prompt

将下面内容作为 OpenCode 的下一条提示词，并同时提供 Codex 在交付消息中给出的
精确 `START_SHA`。本轮由同一个 OpenCode 会话串行完成 Tasks 2-3；Task 2 有内部
commit/CI 检查点，但只在整个 Batch B 完成后停在 Gate 2 与 Codex 交互。

```text
你是 health-agent Phase 5 Batch B / Tasks 2-3 的唯一实现者和 CI 操作者。目标是在不降低规格、安全、隐私、迁移和事务验证深度的前提下减少交接：先完整完成 Task 2 并通过内部检查点，再顺序完成 Task 3；最后停在 Gate 2。不得开始 Tasks 4-6。

工作目录：C:\Users\Lenovo\Desktop\develop\health-worktrees\phase5-opencode-implementation
分支：codex/phase5-opencode-implementation
START_SHA：使用 Codex 与本提示词同时给出的精确值；未给出则停止，不自行猜测。
Gate 1 accepted code SHA：3df574b7051ef9a9342816c9b116f436ddf8513c
Draft PR：https://github.com/Lizz-666/health-agent/pull/3

开始前执行并记录：
1. git status --short --branch
2. git rev-parse HEAD
3. git merge-base --is-ancestor 3df574b7051ef9a9342816c9b116f436ddf8513c HEAD
4. git log -5 --oneline

要求：工作目录和分支必须完全匹配，HEAD 必须等于 START_SHA，祖先检查 exit 0，工作区干净。不满足立即停止并报告；不修改、不清理、不 stash、不 checkout、不 rebase。不要重写或回退 Gate 1 已接受行为。

读取范围：
- AGENTS.md
- docs/agent/ACTIVE_TASKS.md 中 Phase 5 Tasks 2-3 行
- docs/agent/PHASE5_COLLABORATION_CHARTER.md
- docs/specs/agent/2026-07-28-agent-mvp.md 的 Approved Task 0 Decisions、Provider/Consent/Privacy Gate、Persistence And State、Write Confirmation Semantics、Safety/Failure/Observability、Acceptance Criteria #7-21
- docs/adr/0003-server-controlled-agent-tools.md
- docs/adr/0004-agent-consent-audit-and-memory.md
- docs/plans/agent/2026-07-28-agent-mvp.md 的 Tasks 2-3
- docs/product/safety-boundaries.md 中安全信号、Agent Tool、同意/隐私边界
- Gate 1 的 backend/app/agent 代码和测试
- 被允许修改的现有 purge、health、training、migration、idempotency 代码和相关测试

不要读取 health-agent-project skill；OpenCode 使用已安装的开发 skills。不要通读旧计划、旧报告或无关模块。实现细节可从现有代码发现；普通工程问题自行解决。只有规格冲突会实质改变产品/安全/隐私结果，或正确实现确实要求修改允许范围外生产文件时才停止报告。

本 Batch 唯一允许修改/新增：

Task 2：
- backend/app/agent/models.py
- backend/app/agent/persistence.py
- backend/app/agent/privacy_gate.py
- backend/alembic/versions/0008_agent_mvp.py
- backend/alembic/env.py
- backend/app/posture/purge.py
- backend/tests/test_agent_privacy.py
- backend/tests/test_agent_persistence.py
- backend/tests/test_agent_migrations.py
- backend/tests/test_migrations.py
- backend/tests/test_privacy_gate.py（只添加 account-deletion 集成覆盖）
- backend/tests/test_pg_integration.py（只添加必要 PostgreSQL account-deletion/约束覆盖）
- scripts/verify.py

Task 3：
- backend/app/agent/action_tools.py
- backend/app/agent/schemas.py
- backend/app/agent/persistence.py
- backend/app/health/service.py
- backend/app/training/service.py
- backend/app/training/persistence.py
- backend/tests/test_agent_action_tools.py
- backend/tests/test_agent_confirmation.py
- backend/tests/test_training_api.py
- backend/tests/test_health_checkins.py
- backend/tests/test_health_weight_trends.py
- scripts/verify.py

禁止修改其他文件，包括 router/API、provider/orchestrator、app.main、core config、.env、Flutter、CI workflow、规格/ADR/治理文档和迁移 0001-0007。Task 2 只实现可独立调用的 cleanup/privacy/persistence 服务；startup 和 Agent API 边界接线属于 Task 4，不要为接线扩大范围。不要添加 live provider、网络调用、自由文本存储或新的健康阈值。

共同硬边界：
1. 测试优先；所有数据/日志/fixture 必须是合成数据。不得使用真实健康数据、照片、凭据或 live AI。
2. Actor/user_id、服务器时间、consent、provider/disclosure、policy/context fingerprint 和允许 Tool 集只能服务端注入；客户端/模型参数不得覆盖。
3. 无 transcript、user message、assistant prose、raw context、prompt、provider request/response、raw Tool arguments/results进入 run/tool audit 或日志。低熵健康值的 fingerprint 只能使用 Gate 1 的 dedicated keyed HMAC。
4. 缺失配置、非法状态、跨用户、过期、stale、partial idempotency hit、事务异常和未知枚举一律 fail closed；绝不能变成 success/normal/healthy/已执行。
5. 写入只能经过 proposal -> 独立 authenticated confirmation -> latest-data/domain gate -> atomic execution；模型和 turn orchestration 永远不能确认、取消、撤回同意或删除数据。

Task 2：Consent、Audit、Proposal Persistence、Migration

A. 四张表和迁移
- 严格实现 spec 的 agent_cloud_consents、agent_runs、agent_tool_events、agent_action_proposals 四表字段、FK、唯一约束、状态约束、ownership indexes、级联关系和 PostgreSQL 约束。
- SQLite 应用层行为必须与 PostgreSQL invariants 一致；不要依赖 SQLite 忽略约束。
- env.py 显式导入 agent.models，metadata parity 完整。
- 0008 必须从 0007 单头升级，支持 upgrade/downgrade；离线 SQL 不泄露连接串/凭据。
- 不在 schema 中加入任何 raw text/context/prompt/provider payload 列。

B. Consent 和 privacy gate
- immutable agent_cloud_processing events；每用户 sequence_no 通过现有 user transaction lock 串行分配，最高序列唯一决定 current state，不依赖 timestamp tie。
- grant 只能确认服务器当前 provider/disclosure；accepted 值不等于当前配置返回 agent_disclosure_stale，不得授予更新或其他 provider。
- grant/withdraw 使用共享 idempotency_records 的 agent_consent_grant / agent_consent_withdraw namespace，覆盖 replay、same-key conflict、gone anchor 和并发。
- withdrawal 立即使 consent inactive，并在同一拥有者事务中 invalidate + scrub 所有 pending proposals；失败必须 rollback。
- privacy gate 要求 runtime、provider/model/disclosure、当前匹配 consent、受支持 context、无 transcript persistence 契约、deletion capability 和非默认 dedicated HMAC key 全部满足。单一 runtime switch、客户端 consent 或 fake provider 都不能通过 live gate。
- Task 4 才添加实际 config/env/API；Task 2 的 gate 应使用明确、可测试、服务端构造的输入契约，不得偷偷添加客户端选择路径。

C. Minimal audit、proposal lifecycle、retention/deletion
- run 唯一 (user_id, client_turn_id)；Tool event 只存 metadata/fingerprints/result_ref；跨用户存在性不可枚举。
- proposal 仅 pending 保留 typed bounded arguments_json；15 分钟后 lazy expire；executed/invalidated/expired/cancelled、withdrawal、Agent-data deletion 都必须 NULL scrub arguments。
- arguments_hash/context/request fingerprints 使用 Gate 1 HMAC/key version；key/version 变化会 invalidate + scrub pending proposals before accepting new work。
- 30 天清理 runs 和 dependent Tool events；提供可独立调用、幂等、并发安全的 cleanup。记录 Phase 5 仅 best-effort startup/request-bound，durable scheduler 留作 public-release gate；本 Task 不修改 app.main。
- DELETE Agent data 删除当前用户四表记录和 agent_action_confirm / agent_consent_grant / agent_consent_withdraw 三个共享 idempotency namespaces；保留独立 health/posture/training domain rows 和其 domain idempotency evidence。
- reviewed cross-domain extension：把四张 Agent 表和三个 Agent namespace 纳入现有 posture.purge account_deletion/retry orchestration；不得声称修复平台既有 health/training account deletion gap。
- proposal lifecycle 与 consent/deletion/cleanup 操作必须有 user lock、ownership、事务 rollback 和并发测试。

Task 2 最低测试矩阵：
- migration upgrade/downgrade、offline SQL、metadata parity、表/FK/index/unique/check constraint；SQLite + PostgreSQL。
- active consent highest-sequence derivation、provider/disclosure stale、grant/withdraw replay/conflict/410、并发序列、cross-user isolation。
- duplicate client_turn_id、run/tool metadata minimization、无 raw text/context columns。
- proposal create/load/foreign、15-minute boundary、每个 terminal transition scrub、withdraw scrub、key rotation invalidation、rollback。
- Agent data deletion和 account deletion/retry：四表+三个 namespace 删除；无关用户、domain health/training rows 和 domain idempotency保留。
- 30-day boundary/cascade cleanup、幂等/并发、事务失败回滚。

Task 2 本地验证：
cd backend
python -m pytest tests/test_agent_privacy.py tests/test_agent_persistence.py tests/test_agent_migrations.py tests/test_migrations.py tests/test_privacy_gate.py -q
cd ..
python scripts/verify.py fast
$env:VERIFY_REQUIRE_PG='1'; python scripts/verify.py full
git diff --check

Task 2 内部检查点：
1. 两轮自审：先逐条对照 spec/Task 2，再审 migration、授权、隐私最小化、锁、并发、事务、删除、retention、回滚和范围。
2. 生成并检查 0008 upgrade/downgrade PostgreSQL offline SQL，报告关键 DDL；不得提交临时 SQL 文件。
3. 只显式 stage Task 2 允许文件，创建内聚 commit：feat(agent): add consent audit and proposal persistence
4. 普通 push 到 origin/codex/phase5-opencode-implementation，不得 force-push。
5. 使用一次有界 gh pr checks --watch 等待该 exact Task 2 SHA 的自动 CI。Fast/Flutter/Full 所有已触发 job 都必须成功；失败只读取 failed job log，修复后重跑受影响的本地 focused/Fast/PG Full，新增 fix commit，push 并等待新 exact SHA。
6. Task 2 CI 全绿且自审无 P0/P1/P2 后，直接继续 Task 3，不等待 Codex；保留 Task 2 SHA、CI URL、计数供 Gate 2 报告。

Task 3：Confirmed Write Adapters

A. 闭合的 server-side action contract
- 只允许五个 write actions：upsert_today_checkin、create_weight_record、generate_training_plan_draft、substitute_today_exercise、record_training_feedback。
- 为每个 action 建立严格 extra=forbid、无自由文本、无 actor/user/time/policy/consent/fingerprint 字段的 typed arguments、proposal/diff/result schemas。
- write action metadata/dispatch 放在 action_tools.py 的独立 server-side closed registry；不要把写 Tool 注册进 provider-exposed read registry，也不要给模型 confirm/cancel/consent/delete 权限。
- diff 由服务端确定性模板/typed values 生成，不能保存或显示 provider 自由文本。

B. 五个动作的领域边界
- check-in 仅 ordinary abnormal_pain=false，禁止 pain 字段；若同日现有 abnormal_pain=true，拒绝覆盖并返回 dedicated safety-signal route，不得降级为普通 check-in。
- weight 要求明确 value/time 且强制 note=null；拒绝任何 note/free text。
- plan generation 只创建/替换 pending draft，仍需 Phase 4 独立 plan review/confirm，Agent 不激活计划。
- substitution 和 feedback 仅 current local day、owned current session/exercise，重新执行最新 risk/restriction/catalog/policy/domain validation；pain feedback 路由安全信号流程，不作为 ordinary feedback。
- proposal 创建不产生任何 domain write；confirmation 不信任保存的 safety/context，必须重建最新 context并比较 HMAC/policy/key versions。

C. 事务和 idempotency
- 当前 health/training 方法内部 commit，必须抽取共享 transaction-neutral operation（只 flush/return，不 commit）。现有 button/API wrapper 调用同一 operation 后照旧 commit，外部签名和行为兼容；不得复制业务规则。
- Agent confirmation 在一个 unit of work 内完成 owned proposal lock、agent_action_confirm idempotency、latest-data gate、transaction-neutral domain write、domain idempotency（仅 training）、Tool event、proposal terminal/result_ref 和 commit。
- training 的 server-derived per-proposal domain key必须进入既有 plan_generate/session_substitute/session_feedback namespace。Agent 和 domain 两层 idempotency 的 new/replay/partial/mismatch/conflict 必须一致；任何 partial hit inconsistency fail closed，无第二次写。
- health 不新增 domain idempotency；依赖 agent_action_confirm + owned proposal lifecycle + user lock + 单事务保证 exactly once。
- deterministic stale/safety/validation rejection 可在独立拥有者事务中 invalidate+scrub 且无 domain write；transient exception rollback 后 proposal 保持 pending/retriable，不得标记 executed。
- 在 domain flush 前、flush 后、audit/proposal update 前和 commit 点注入失败，证明无 half-recorded side effect、false executed 或不可重试状态。

Task 3 最低测试矩阵：
- 五 action 均证明 confirm 前零写、首次 confirm 恰好一写、相同 key replay 不重复写、不同 proposal same key conflict、expired/foreign/cancelled/inactive-consent拒绝。
- profile/check-in/posture/risk/policy/catalog/session/context/key-version 变化导致 stale invalidation + scrub + 零写；restricted/red-flag全阻断。
- pain check-in/feedback route、existing abnormal-pain overwrite refusal、weight note rejection。
- spies 证明 Agent 和 button/API 复用同一 transaction-neutral operation，现有 API contract/commit 行为不回归。
- 每个 training write 覆盖：两层均 new、两层均 replay、仅 Agent record、仅 domain record、mismatched result_ref、request-hash conflict、gone anchor。
- 每个 health write 证明无第二 domain idempotency record但 replay exactly once。
- 所有事务注入点覆盖 rollback/retry；并发 confirm 至多一次 side effect。

Task 3 / Gate 2 本地验证：
cd backend
python -m pytest tests/test_agent_action_tools.py tests/test_agent_confirmation.py tests/test_training_api.py tests/test_health_checkins.py tests/test_health_weight_trends.py -q
cd ..
python scripts/verify.py fast
$env:VERIFY_REQUIRE_PG='1'; python scripts/verify.py full
git diff --check

Gate 2 提交、CI 和停止条件：
1. 两轮自审：先对照完整 Tasks 2-3/spec，再审迁移、consent、authorization、replay、latest-data safety、atomicity、shared-operation compatibility、scrubbing、deletion、rollback和敏感信息。
2. 检查 git status、完整 START_SHA..HEAD diff、Task 2..HEAD diff、敏感信息和意外生成文件；只显式 stage Task 3 允许文件。
3. 创建内聚 Task 3 commit：feat(agent): add confirmed write adapters
4. 普通 push；PR #3保持 draft，base保持 codex/phase4-opencode-implementation。不得创建新 PR、改 ready、merge、rebase、force-push、写 main、改 settings/secrets或部署。
5. 使用一次有界 gh pr checks --watch 等待最终 exact SHA。Fast/Flutter/Full 所有已触发 job 必须成功；任何修复都要新 commit、push，并在新 SHA 上重跑相关 focused/Fast/PG Full 和 CI。

完成报告必须包含：
- START_SHA、Task 2 checkpoint SHA、最终 HEAD、所有 Batch B commits、draft PR URL
- Task 2/Task 3 修改文件和逐项契约变化
- focused/Fast/PG Full 本地命令、退出码、通过/失败/skip 计数
- 两个 exact-SHA CI run URL、headSha、Fast/Flutter/Full 结论
- migration upgrade/downgrade SQL、metadata/PG constraint、account/Agent deletion证据
- consent sequence/replay、privacy gate、retention/scrub、cross-user、latest-data safety、五动作零写-before-confirm、两层 idempotency、事务注入/rollback测试证据
- git diff --stat、意外生成文件、剩余风险/延期项
- 明确确认：无 live AI/network、无真实健康数据/照片/凭据、无范围外文件、无 Tasks 4-6、无 merge/rebase/force-push/deploy

然后停止在 Gate 2 / review，等待 Codex 独立检查真实 diff、迁移和 exact-SHA 重新验证。不得继续 Task 4。
```
