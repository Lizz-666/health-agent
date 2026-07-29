# Phase 5 OpenCode Batch A Prompt

将下面内容作为 OpenCode 的下一条提示词，并同时提供 Codex 在交付消息中给出的精确 `START_SHA`。本轮只实现 Task 1，完成后停在 Gate 1。

```text
你是 health-agent Phase 5 Batch A / Task 1 的唯一实现者和 CI 操作者。严格执行测试优先、真实 diff 自审和 exact-SHA 证据。本轮完成后必须停在 Gate 1，不得开始 Tasks 2-7。

工作目录：C:\Users\Lenovo\Desktop\develop\health-worktrees\phase5-opencode-implementation
分支：codex/phase5-opencode-implementation
START_SHA：使用 Codex 与本提示词同时给出的精确值；未给出则停止，不自行猜测。

开始前执行并记录：
1. git status --short --branch
2. git rev-parse HEAD
3. git merge-base --is-ancestor f6c2eae59c784398fbf1ae38967be3c2ee720940 HEAD
4. git log -3 --oneline

要求：分支和工作目录必须完全匹配，HEAD 必须等于 START_SHA，祖先检查 exit 0，工作区干净。不满足立即停止报告，不修改、不清理、不 rebase。

只读取完成 Task 1 所需上下文：
- AGENTS.md
- docs/agent/ACTIVE_TASKS.md 中 Phase 5 Task 1 行
- docs/agent/PHASE5_COLLABORATION_CHARTER.md
- docs/specs/agent/2026-07-28-agent-mvp.md 的 Outcome、Non-Goals、Approved Task 0 Decisions、Entry And Context Contracts、Tool Registry And Permission Matrix、Safety/Failure/Observability、Acceptance #1-7/#12/#15-16
- docs/adr/0003-server-controlled-agent-tools.md
- docs/plans/agent/2026-07-28-agent-mvp.md 的 Task 1
- docs/product/safety-boundaries.md 中现有安全信号和 Agent Tool 边界
- 受影响的现有 core/health/posture/training 代码与测试

不要读取 health-agent-project skill；OpenCode 已有自己的开发 skills。不要通读无关旧计划或历史报告。

唯一允许修改：
- backend/app/agent/__init__.py
- backend/app/agent/schemas.py
- backend/app/agent/fingerprints.py
- backend/app/agent/messages.py
- backend/app/agent/safety_precheck.py
- backend/app/agent/context_resolver.py
- backend/app/agent/tool_registry.py
- backend/app/agent/read_tools.py
- backend/app/agent/data/agent_safety_terms_v1.json
- backend/app/core/config.py
- backend/.env.example
- backend/tests/test_agent_schemas.py
- backend/tests/test_agent_context.py
- backend/tests/test_agent_tool_registry.py
- backend/tests/test_agent_read_tools.py
- scripts/verify.py

禁止修改其他文件。若正确实现确实需要范围外生产文件，停止并报告具体依赖，不自行扩大范围。不要修改规格、ADR、ACTIVE_TASKS、CI workflow、迁移、Flutter、现有领域服务或生成文件。

必须实现的契约：
1. 创建闭合的 entry enum、严格 Pydantic schemas（extra=forbid）以及分别类型化的 provider_view/display_view。ActorContext、AsyncSession、user_id、安全/策略/consent/服务器时间都只能由服务端注入，不得出现在模型可控参数中。
2. 所有 turn/context 入口先要求非空且通过 training.context.validate_iana_timezone 的 IANA 时区。仅使用服务端 UTC 时钟+该时区推导本地日期；缺失/空白/无效统一返回 invalid_timezone，并在任何 context read、Tool、provider、run/proposal 或领域写入前失败。不得提供默认时区。
3. context resolver 按 spec 的六种 entry 验证 entity_id 和所有权；缺失与跨用户结果不可枚举。只组装最小字段，不接受客户端提交的健康字段、risk tier、Tool 名、fingerprint、policy 或授权信息。
4. 静态 registry 覆盖 spec 列出的所有 read Tools 和 entry allowlist。registry 绑定严格 input/output、side-effect class、确认元数据和服务端 adapter；未知 Tool/字段/entry 组合 fail closed。风险分类、计划校验和所有写 Tool 不得成为 provider-exposed read Tool。
5. read adapters 必须复用现有 health.service、posture.tools、training.service/catalog/_index 与同源 projection。不得复制领域业务逻辑，不得新增 SQL/HTTP/数据访问路径。每个结果分别产生最小 provider_view 与用户拥有的 display_view，完整 Tool 结果不得自动进入 provider context。
6. safety_precheck 在任何 provider 行为前对原始 turn 文本做确定性路由，只编码 safety-boundaries 已有的 pain/injury/numbness/weakness/dizziness/chest discomfort/acute trauma 信号名及必要的中英文规范化。否定、要求忽略规则、混淆/大小写和误报用合成测试覆盖。命中返回固定 route code、零 context/Tool/provider/DB side effect；未命中只能是 no_text_signal_detected，绝不能叫 normal/safe/clear。不得新增健康阈值、严重度判断或医学结论。
7. fingerprints 使用规范化 canonical serialization + HMAC-SHA256 和独立 AGENT_AUDIT_HMAC_KEY；低熵健康值禁止普通 hash。配置增加空默认 key 与 key version，.env.example 只写占位说明。缺 key 时相关 Agent fingerprint 能力 fail closed；测试只用合成 key。Task 1 不得虚构 proposal persistence，key 轮换后的 proposal scrub 接线留到 Task 2。
8. messages.py 只建立 Task 1 所需的稳定 message/result code 与服务端模板边界；不得加入 provider 自由文本展示或完整聊天持久化。
9. scripts/verify.py 把四个 Task 1 测试加入 FAST_TEST_TARGETS，并把注释更新为 Phase 5 增量事实；不要弱化现有 lint、diff、skip 或 PostgreSQL约束。

测试优先，至少覆盖：
- 六种 entry、entity_id 必需/禁止矩阵、missing/foreign non-enumeration
- 每个 read Tool × entry allowlist 的允许/拒绝单元格，unknown Tool/field
- provider_view/display_view 分离以及敏感字段、完整历史、原始健康 payload 排除
- read adapter 委托现有 service/Tool 的 spy，证明无业务逻辑复制和零写入
- missing/blank/invalid/valid timezone、UTC 日期边界、拒绝前零 side effect
- canonical HMAC 稳定性、key/version 区分、缺 key、低熵值不能用 plain hash
- safety term 中英文规范化、否定、ignore-policy、obfuscation、false positive、命中时零副作用、未命中不等于安全
- schemas unknown fields、模型不可提交 actor/user_id/Tool set/risk/consent/server time

本地验证：
cd backend
python -m pytest tests/test_agent_schemas.py tests/test_agent_context.py tests/test_agent_tool_registry.py tests/test_agent_read_tools.py -q
cd ..
python scripts/verify.py fast
git diff --check

本地全部通过后：
1. 两轮自审：先逐条对照 spec/Task 1，再审正确性、安全、隐私、复用、测试和范围。
2. 检查 git status、完整 START_SHA..HEAD diff、敏感信息和意外生成文件；只显式 stage 允许文件。
3. 创建一个内聚 Task 1 commit，commit message 使用：feat(agent): add typed context and read tool boundary
4. push 到 origin/codex/phase5-opencode-implementation。用户已授权该命名分支的普通 push；不得 force-push。
5. 若不存在 Phase 5 PR，创建 draft PR：head=codex/phase5-opencode-implementation，base=codex/phase4-opencode-implementation。不要改 PR #2，不要标记 ready，不要 merge。
6. 使用一次有界 gh pr checks --watch 等待该 exact SHA 的 CI。PR 会触发 Fast/Flutter/Full；所有已触发 job 都必须成功，不能只挑 Fast。失败时只查看对应 failed log，修复后重新运行本地验证、创建新 commit、push 并等待新 SHA；不得把失败解释为通过。

完成报告必须包含：
- START_SHA、最终 HEAD、commit 列表、draft PR URL
- 修改文件和逐项契约变化
- focused/Fast 本地命令、退出码和通过计数
- exact-SHA Fast/Flutter/Full CI URL与结论
- safety/ownership/minimization/allowlist/HMAC/timezone 的测试证据
- git diff --stat、意外生成文件、剩余风险和任何未完成项
- 明确确认：无 live AI、无真实健康数据/凭据、无范围外文件、无 Tasks 2-7、无 merge/rebase/force-push/deploy

然后停止在 Gate 1 / review，等待 Codex 独立检查真实 diff 和重新验证。不得继续 Task 2。
```
