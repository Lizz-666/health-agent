# Phase 5 OpenCode Gate 0 Review Prompt

将下面内容作为 OpenCode 的下一条提示词。本轮只审查 Codex 编写的 Task 0，
不得实现或修改文件。

```text
你负责 health-agent Phase 5 Task 0 的独立 Gate 0 规格审查。使用代码审查立场，findings first；当前步骤不是实现任务。

工作目录：
C:\Users\Lenovo\Desktop\develop\health-worktrees\phase5-spec-plan

先执行：
1. git status --short --branch
2. git rev-parse HEAD
3. git merge-base --is-ancestor e560552e0b0dcd3fb5d892f177be1bd80c17c6dd HEAD
要求：分支 codex/phase5-spec-plan、祖先检查 exit 0、工作区干净。记录实际 HEAD；不满足则停止报告。

必须读取：
- AGENTS.md
- docs/agent/ACTIVE_TASKS.md
- docs/agent/PHASE5_COLLABORATION_CHARTER.md
- docs/reports/phase5-opencode-preflight-2026-07-28.md
- docs/specs/agent/2026-07-28-agent-mvp.md
- docs/adr/0003-server-controlled-agent-tools.md
- docs/adr/0004-agent-consent-audit-and-memory.md
- docs/plans/agent/2026-07-28-agent-mvp.md
- docs/product/vision.md 的 Agent、长期记忆、导航部分
- docs/product/safety-boundaries.md 的推荐门、Agent Tool、隐私部分
- docs/product/roadmap.md 的 Phase 5、CI、Phase 7 部分
- 为验证结论所需的现有代码和 Phase 3/4 规格

不要读取 health-agent-project skill。只审查仓库当前事实和 Task 0 候选。

禁止：修改/生成文件、commit、push、PR、live AI、真实健康数据、开始 Tasks 1-7。

按 P0/P1/P2/P3 审查并给出精确文档章节/行号。重点检查：
1. 规格、ADR、计划、路线图、ACTIVE_TASKS 是否互相一致，有无未决产品问题伪装成实现细节。
2. 模型是否存在任何路径可控制 actor/user_id、Tool 注册/allowlist、安全分类、计划校验、确认、consent/provider 或服务端时间。
3. 每个 roadmap Tool 是否明确复用现有 service；是否遗漏、重复或错误开放长期写入、照片、Profile/Goal/Safety mutation。
4. “所有写入先 proposal + 独立确认”是否在 API、状态机、幂等、事务、Flutter 和测试中闭合；模型能否绕过确认。
5. proposal arguments_json 的敏感性、15 分钟过期、scrub、lazy cleanup、withdraw/delete/account deletion 是否足够一致；30 天 run/tool audit 清理与 consent retention 是否闭合；是否有无法清理的保留路径。
6. 云模型调用是否被 runtime switch + provider disclosure/config + 当前 consent + privacy gate 同时阻断；fake/dev provider 能否意外进入普通/生产路径。
7. 不存完整聊天的承诺是否与 duplicate turn、审计、日志、provider 调试、Flutter 状态、重试语义冲突。
8. provider 是否只能返回结构化 intent/Tool/message code；是否仍有模型自由文本可直接展示；未知 message code 是否 fail closed。
9. context/request/argument fingerprint 是否全部使用独立服务端 HMAC key，能否被低熵健康值字典枚举，缺 key 时是否阻止 live runtime。
10. 用户文本中的现有疼痛/麻木/无力/眩晕/胸部不适/急性创伤信号是否在 provider 前由确定性规则保守路由；否定/“忽略规则”能否绕过；未命中是否会被错误当成正常。
11. provider failure、schema failure、partial read failure、step limit、stale context、red flag、restricted、cross-user、idempotency conflict 是否全部 fail closed 且没有 failure-to-success。
12. 迁移 0008、SQLite/PG parity、FK/account deletion、shared idempotency/user lock、downgrade/rollback 是否可实施；现有 health/training 自提交 service 抽取 transaction-neutral 共享操作后，是否真能避免领域写入与 proposal/audit 半状态，文件/测试范围是否完整。
13. navigation 改为 今日/计划/Agent/我的 时，原 posture 首页、legacy `/` 和现有 deep links 是否有明确兼容路径。
14. Tasks 是否可按 Gate 独立验收，文件边界/命令/CI 是否现实，是否存在会导致 Batch 后期集中返工的依赖顺序。
15. 是否引入了需要当前一手来源的新健康阈值、外部 provider 事实或法律结论；若有却未验证，列为 finding。

Finding 格式：
- [P级] 标题
- 证据：文件:行号/章节
- 影响：具体失败或风险
- 修复要求：可验证的规格修改

最后给出：
- Gate 0 verdict: PASS 或 FAIL
- P0/P1/P2/P3 数量
- Open decisions（仅真正改变产品/安全/隐私/不可逆数据模型）
- No-files-changed confirmation

PASS 条件：没有 P0/P1/P2；P3 必须明确且不伪装成阻塞。完成后停止，等待 Codex 处理审查结果。不得开始实现。
```
