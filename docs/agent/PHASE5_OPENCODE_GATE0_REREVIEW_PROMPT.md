# Phase 5 OpenCode Gate 0 Re-review Prompt

将下面内容作为 OpenCode 的下一条提示词。本轮只复审 Gate 0 修复，不得实现或修改文件。

```text
你负责 health-agent Phase 5 Task 0 的独立 Gate 0 复审。使用代码审查立场，findings first；当前步骤不是实现任务。

工作目录：C:\Users\Lenovo\Desktop\develop\health-worktrees\phase5-spec-plan

先执行：
1. git status --short --branch
2. git rev-parse HEAD
3. git merge-base --is-ancestor 8ac8858a4099b5fca49f392f1e6eaf391ccbf7d1 HEAD
4. git diff --check 8ac8858a4099b5fca49f392f1e6eaf391ccbf7d1..HEAD

要求：分支必须是 codex/phase5-spec-plan，祖先检查 exit 0，工作区干净。记录实际 HEAD；不满足则停止报告。

必须读取：
- AGENTS.md
- docs/agent/ACTIVE_TASKS.md
- docs/reports/phase5-gate0-review-2026-07-29.md
- docs/specs/agent/2026-07-28-agent-mvp.md
- docs/plans/agent/2026-07-28-agent-mvp.md
- docs/adr/0003-server-controlled-agent-tools.md
- docs/adr/0004-agent-consent-audit-and-memory.md
- 为验证结论所需的 backend/app/training/context.py、training/service.py、training/knowledge.py、training/persistence.py、posture/purge.py、health/service.py 及相关测试

不要读取 health-agent-project skill。只审查仓库当前事实和 Task 0 候选。

禁止：修改/生成文件、commit、push、PR、live AI、真实健康数据、开始 Tasks 1-7。

首先逐项验证上一轮 findings 是否真正关闭：
1. 每个 /turns 请求的 IANA timezone 是否必需、复用现有校验、无默认值；缺失/无效是否在 context/provider/Tool/run/proposal/domain side effect 前以稳定失败码拒绝，并有明确测试。
2. account deletion 是否准确描述当前 posture.purge 硬编码事实；Task 2 是否明确加入四张 Agent 表和所有 Agent namespace idempotency rows、覆盖 retry/resume；是否避免声称 Phase 5 会清理既有 health/training 数据。
3. training 双层幂等与 health 单层幂等的 first-run/replay/单边幂等记录命中/result-ref mismatch/conflict 测试是否足以阻止半状态。
4. get_training_exercise 是否明确复用 training.service.catalog/_index 和同源 projection，而不是新建数据访问路径。
5. HMAC 轮换后旧指纹不可复验的取舍是否明确、一致且不会产生虚假的审计完整性承诺。
6. 30 天 cleanup 是否明确为无 scheduler 的 best effort，并把 durable scheduler 保留为 public-release gate。

随后对 8ac8858..HEAD 的完整修复做冷启动一致性审查，确认没有新矛盾，特别检查 spec/ADR/plan/roadmap/ACTIVE_TASKS、API 失败码、验收条件、迁移/删除/回滚和 Task/Gate 边界。

Finding 格式：
- [P级别] 标题
- 证据：文件:行号/章节
- 影响：具体失败或风险
- 修复要求：可验证的规格修改

最后给出：
- Gate 0 verdict: PASS 或 FAIL
- P0/P1/P2/P3 数量
- 上一轮 6 项 finding 的逐项状态
- Open decisions（仅真正改变产品/安全/隐私/不可逆数据模型）
- No-files-changed confirmation

PASS 条件：没有 P0/P1/P2；P3 必须明确且不伪装成阻塞。完成后停止，等待 Codex 处理审查结果，不得开始实现。
```
