# Phase 5 OpenCode Preflight Prompt

将下面内容作为 Phase 5 的第一条 OpenCode 提示词。此步骤只读，不实现、不修改、不提交。

```text
你负责 health-agent Phase 5 Agent MVP 的只读实现前审计。当前步骤不是编码任务。

工作目录：
C:\Users\Lenovo\Desktop\develop\health-worktrees\phase5-spec-plan

必须包含的 Phase 4 验证基线：
e560552e0b0dcd3fb5d892f177be1bd80c17c6dd

先执行：
1. git status --short --branch
2. git rev-parse HEAD
3. git merge-base --is-ancestor e560552e0b0dcd3fb5d892f177be1bd80c17c6dd HEAD
如果当前分支不是 codex/phase5-spec-plan、第三条命令非零，或工作区存在任何变化，停止并报告。报告实际 HEAD，不要求 HEAD 本身等于 Phase 4 基线。

必须读取：
- AGENTS.md
- docs/agent/ACTIVE_TASKS.md
- docs/agent/PHASE5_COLLABORATION_CHARTER.md
- docs/product/vision.md 的 Agent 权限与长期记忆相关部分
- docs/product/safety-boundaries.md 的推荐请求安全门、Agent 工具安全、数据隐私部分
- docs/product/roadmap.md 的 Phase 5 与 CI 分层部分
- docs/specs/training/2026-07-26-training-knowledge-safety-engine.md 中 Tool/ActorContext/安全门相关章节
- docs/specs/training/2026-07-27-four-week-plan-mvp.md 中 API、确认、幂等、调整范围相关章节
- 与结论直接相关的 backend/app、backend/tests、app/lib、app/test 代码

你可以使用已安装的 OpenCode skills/superpowers，但不要读取或依赖 health-agent-project skill。仓库当前文档和代码才是本次审计事实。

只输出审计报告，不修改任何文件，不生成规格，不创建 commit，不 push，不创建 PR，不调用 live AI，不使用真实健康数据或凭据。

审计必须回答：
1. Phase 5 首批每个 Tool 对应的现有领域 service/Tool/API 是什么；哪些可直接复用，哪些缺失，哪些路线图名称会诱导重复业务逻辑。
2. Context Resolver 为 action/session/posture/profile/general 五类入口最少需要哪些服务端字段；实体所有权和不存在/越权如何区分，哪些敏感字段不应发送给模型。
3. 每个 Tool 是 read、draft/proposal、需要用户确认的长期写入，还是允许的当日小副作用；列出授权、最新安全门、幂等、审计和失败语义。
4. 明确指出路线图 Phase 5 的“当日小调整”与 Phase 4 将自动缩短、顺延、恢复性调整推迟到 Phase 7 的冲突。不要自行选择或实现扩展范围，给出 2 个保守解释及其影响。
5. 提出最小 Agent orchestration 边界：固定 tool allowlist、类型化输入输出、最大调用步数、provider fake、schema 失败、timeout、partial failure、prompt injection 和 confirmation bypass 的处理。
6. 建议最小持久化与审计模型，确保不把完整聊天作为长期记忆、不记录原始健康数据，同时能追踪 actor、tool、输入摘要、结果、策略/模型版本和副作用。
7. 列出预计受影响文件/新模块、迁移、OpenAPI、Flutter 入口、测试与 CI 矩阵；标注高风险依赖顺序，避免把整个 Phase 做成一次不可审查的大提交。
8. 列出规格必须先决定的问题，按 P0/P1/P2/P3 排序。只有会改变产品、安全、隐私或不可逆数据模型的事项才作为阻塞项。

报告格式：
- Base/HEAD/status
- Existing capability map（表格）
- Missing contracts and scope conflicts
- Proposed architecture boundaries
- Tool permission/confirmation matrix
- Persistence/privacy proposal
- Adversarial and failure test matrix
- Suggested file/task decomposition
- Blocking decisions and assumptions
- No-files-changed confirmation

完成后停止，等待 Codex 编写并批准 Phase 5 Task 0 规格。不得提前实现运行时代码。
```
