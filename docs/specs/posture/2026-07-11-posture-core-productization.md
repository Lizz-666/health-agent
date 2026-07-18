# 体态核心产品化规格

> 日期：2026-07-11
> 状态：当前规格
> 对应路线图：阶段 1 — 体态核心产品化
> 上游规格：[开发基线收敛规格](../platform/2026-06-12-baseline-contract.md)
> 安全边界：[安全边界](../../product/safety-boundaries.md) 第 2、3、6、7 节
> 路线图：[阶段 1](../../product/roadmap.md#5-阶段-1体态核心产品化)

---

## 1. Outcome

把当前体态 MVP 转化为用户可理解、结果可追踪、来源和不确定性明确，并能被后续 Agent 通过受控 Tools 调用的领域能力。完成后，系统具备：

- 独立保留的图示自测与照片分析来源
- 显式的冲突与不确定状态
- 服务端体态档案，区分已评估与未评估区域
- 确定性规则驱动的多问题优先级建议
- 用户确认的主要改善目标
- 供 Agent 调用的 8 个体态 Tool 契约
- 明确的隐私门启用条件（但 Phase 1 期间仍默认关闭）

## 2. Non-Goals

- 不实现训练计划生成、Agent 对话或饮食推荐
- 不启用照片分析功能（`PHOTO_ANALYSIS_ENABLED` 保持 `false`）
- 不创建 Alembic migration（本任务仅设计数据模型，不执行迁移）
- 不生成图片、插图或最终医学内容
- 不采集真实健康数据或真实照片
- 不修改 roadmap 的 Phase 1 完成状态
- 不把体态筛查描述为医学诊断
- 不实现照片同意 UX 或真实 STS 凭证流程
- 不重构 auth、user 或 upload 模块

## 3. Current-state Audit

### 3.1 后端体态模块（`backend/app/posture/`）

**数据模型（单表）：**

`PostureAssessment` 表存储自测和照片两种结果，靠 `method` 列区分：

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `id` | UUID PK | 自动生成 |
| `user_id` | UUID FK → users.id | 索引 |
| `issue_id` | String(20) | 软引用知识库，无 FK 约束 |
| `method` | String(20) | `self_test` / `ai_photo` |
| `result` | String(20) | `normal` / `moderate` / `severe` / `uncertain` |
| `self_test_answers` | JSONB | `{test_index, answer}` |
| `ai_response` | JSONB | 完整 AI 输出 |
| `photo_keys` | JSONB | OSS 对象 key |
| `created_at` | DateTime(tz) | `now()` |

**关键行为：**

- 自测采用确定性映射：`positive→moderate`、`negative→normal`、`uncertain→uncertain`
- AI 输出经 `AIAnalysisResult` 严格校验，任何失败返回 503 且不落库
- AI 的 `mild` 被映射为 `moderate`，原始值保留在 `ai_response["level"]`
- 历史是扁平列表，分页查询，从知识缓存补充问题名称
- `issue_id` 无 FK 约束，是软引用

**知识库（`posture/data/*.json`）：**

5 个文件、26 条问题，覆盖头颈、肩胸、骨盆脊柱、下肢、复合综合征。每条包含 `id, name_cn, name_en, abbr, category, aliases, definition, severity_levels, causes, self_tests, corrections, consequences, red_flags, related_issues`。

**关键缺口：**

| 缺口 | 当前状态 | Phase 1 要求 |
| --- | --- | --- |
| 多来源评估 | 同一问题的自测和照片结果互相覆盖 | 独立保留，不互相覆盖 |
| 冲突/不确定 | `uncertain` 只来自自测"不确定"答案 | 自测与照片冲突时进入显式 conflict 状态 |
| 体态档案 | 客户端 `UserPostureState` 从历史重建 | 服务端档案，当前状态投影 |
| 已评估/未评估 | 不追踪 | 显式追踪已评估和未评估区域 |
| 严重度与确定性 | 单一 `result` 混淆（含 uncertain） | 分离 severity（可空，不含 uncertain）、certainty（confirmed/provisional/conflict）和 lifecycle（active/superseded/expired/purged） |
| 版本/溯源 | 仅 `created_at` | 来源、版本、模型元数据、内容版本 |
| 用户目标 | 未建模 | 用户确认的主要改善目标 |
| 优先级建议 | 仅知识库关联权重 | 确定性规则优先级 + 用户确认 |
| 自测内容结构 | 最小字段 | 扩展结构：准备、正确姿势、常见错误、停止条件 |
| Tool 契约 | 仅 REST API | 类型化 Tool 层供 Agent 调用 |
| 隐私门形式化 | 功能开关 + 503 | 启用条件、同意模型、数据生命周期 |

### 3.2 后端测试（`backend/tests/`）

- 81 个后端测试全部通过
- `test_posture.py`：6 个路由的 happy path、照片门禁、AI 失败路径
- `test_posture_ai_service.py`：AI 输出校验、15 种失败场景
- `test_openapi_contracts.py`：6 个路由的 response schema 完整性
- `conftest.py`：SQLite + aiosqlite 测试环境，patch UUID/JSONB

**关键限制：** 测试不覆盖多来源冲突、档案投影、优先级建议或 Tool 调用。

### 3.3 前端（`app/lib/`）

**模型层：**

- `AssessmentRecord`：历史条目（`id, issueId, issueName, method, result, createdAt`）
- `SelfAssessResult`：即时结果（`id, issueId, result, suggestion`）
- `UserPostureState`：客户端缓存（`issueId, result, method, updatedAt, synced`）
- `IssueDetail`：问题详情（含 `selfTests`，但字段最小化）

**状态管理（Riverpod StateNotifier）：**

- `assessmentProvider`：提交自测/照片、拉取历史
- `postureStateProvider`：从历史重建的客户端状态 Map
- `issueProvider`：按类别拉取问题列表和详情
- `syncService`：启动时同步 profile → issues → history → rebuild state

**关键限制：** 无服务端档案概念；冲突状态无 UI；优先级和目标确认无入口；自测内容展示缺少结构化步骤和安全提示。

### 3.4 数据库迁移（`backend/alembic/`）

- 单一 head：`0001_initial_schema`
- 3 张表：users、verification_codes、posture_assessments
- 真实 PostgreSQL upgrade/downgrade/re-upgrade 闭环已验证
- conftest 使用 SQLite，不依赖 Alembic

---

## 4. Domain Terminology

| 术语 | 定义 |
| --- | --- |
| **体态问题（Posture Issue）** | 知识库中的一个体态问题条目，如"头部前倾"，有唯一 `issue_id` |
| **评估事件（Assessment Event）** | 一次不可变的评估行为记录，包含来源、严重度、时间、版本和生命周期状态 |
| **评估来源（Assessment Source）** | 产生评估结果的方式：`self_test`（图示自测）或 `ai_photo`（照片分析） |
| **严重度（Severity）** | 问题本身的严重程度（枚举，**可空**）：`normal`、`mild`、`moderate`、`severe`。为空表示该来源未产出确定严重度结论（如用户选择"不确定"）。`uncertain` **不是** severity 值，而是 severity 为空的语义 |
| **确定性（Certainty）** | 评估结果的可信状态（枚举）：`confirmed`、`provisional`、`conflict`。注意：与 AI 模型返回的数值型 `confidence`（置信度，0-1 浮点数）不同，后者属于模型元数据 |
| **置信度（Confidence）** | AI 模型返回的数值型分数（0-1），属于 `ai_model_meta` 的字段，不参与确定性判断，仅作为参考信息展示 |
| **事件生命周期（Event Lifecycle）** | 评估事件的管理状态（枚举）：`active`、`superseded`、`expired`、`purged`。`superseded` 是生命周期状态，**不是** certainty 值 |
| **体态档案（Posture Profile）** | 用户当前所有已评估问题的最新有效状态投影 |
| **档案条目（Profile Entry）** | 体态档案中针对单一问题的当前状态记录 |
| **合并严重度（Combined Severity）** | 档案条目中多来源投影后的严重度。仅 `certainty=confirmed` 且所有非空来源 severity 完全一致时有值；`certainty=conflict` 或 `provisional` 时 **必须为 null** |
| **冲突（Conflict）** | 同一问题的不同来源评估结果在严重度上不一致（跨 2 级以上） |
| **主要改善目标（Primary Goal）** | 用户从优先级建议中确认的 1-N 个问题，作为后续训练计划的前置输入 |
| **优先级建议（Priority Suggestion）** | 确定性规则基于档案和关联图谱生成的候选改善顺序 |
| **关联图谱（Association Graph）** | 知识库中 `related_issues` 的 weight/relation 关系，仅用于建议排查 |
| **安全信号（Safety Signal）** | 用户报告的结构化症状输入（疼痛、麻木、无力、眩晕、急性创伤等），影响风险分类 |
| **风险分类（Risk Classification）** | 版本化的风险等级判定（普通/谨慎/受限/红旗），基于档案和安全信号，使旧资格判断失效 |
| **隐私门（Privacy Gate）** | 照片分析功能的授权、同意、告知和数据生命周期控制集合 |
| **内容版本（Content Version）** | 自测内容和知识库条目的版本标识，用于溯源 |

### 4.1 三个独立状态维度

评估事件和档案条目使用三个 **正交、不混用** 的状态维度：

| 维度 | 作用对象 | 枚举值 | 为空规则 | 判断主体 |
| --- | --- | --- | --- | --- |
| **Severity** | 单次评估事件 + 档案条目 | `normal` / `mild` / `moderate` / `severe` | **可为空**（来源未产出确定严重度） | 评估来源 |
| **Certainty** | 档案条目 | `confirmed` / `provisional` / `conflict` | **不可为空** | 系统投影逻辑 |
| **Event Lifecycle** | 评估事件 | `active` / `superseded` / `expired` / `purged` | **不可为空** | 时间和用户操作 |

**禁止混用规则：**

- `uncertain` 不是 severity 值；"用户选择不确定"对应 severity 为空
- `superseded` 不是 certainty 值；它是 event lifecycle 值
- severity 仅描述问题严重程度，不携带可信度信息
- certainty 仅描述结果可信状态，不携带严重度信息
- event lifecycle 仅描述事件管理状态，不携带可信度信息

---

## 5. User Journeys

### 5.1 图示自测（主要路径）

```text
用户选择关注部位
  → 浏览该部位的问题列表
  → 打开问题详情
  → 进入图示自测
  → 按步骤完成自测（含安全提示和停止条件）
  → 选择阳性/阴性/不确定
  → 提交，生成 self_test 来源评估事件
  → 查看结果（严重度 + 确定性 + 来源标注）
  → 事件写入档案，更新当前条目
```

### 5.2 照片分析（Phase 1 默认不可用，设计预留）

```text
用户在自测不确定后尝试照片分析
  → 隐私门检查：未启用 → 返回不可用，保留自测路径
  → 启用后：告知 → 同意 → 上传 → AI 分析
  → 生成 ai_photo 来源评估事件
  → 与已有 self_test 结果合并或冲突
  → 查看结果
```

### 5.3 体态档案查阅

```text
用户打开体态档案
  → 查看已评估区域（绿色/黄色/红色标识）
  → 查看未评估区域（灰色，引导前往自测）
  → 查看冲突问题（橙色标识，标注来源差异）
  → 查看每个问题的最新有效结果、来源和时间
```

### 5.4 多问题优先级确认

```text
用户有多个已评估问题
  → 系统生成优先级建议（确定性规则 + 关联图谱）
  → 展示候选优先级和理由（标注"建议排查"而非"病因"）
  → 用户确认主要改善目标（1-N 个）
  → 结果页出现"生成改善计划"入口（Phase 1 不生成计划）
```

---

## 6. State Model

### 6.1 三个正交状态维度

详见 §4.1。三个维度独立、不混用：

- **Severity**（可空）：单次评估和投影后的严重度
- **Certainty**（不可空）：档案条目的可信状态：`confirmed` / `provisional` / `conflict`
- **Event Lifecycle**（不可空）：事件的管理状态：`active` / `superseded` / `expired` / `purged`

### 6.2 评估事件生命周期

评估事件的载荷一旦创建即不可变。可变的只有 lifecycle 状态。

```text
[创建] ──→ active ──→ superseded (同来源新事件取代)
              │
              ├──→ expired (保留期到期，参与惰性删除)
              │
              └──→ purged (健康数据已删除/不可逆匿名化，仅保留最小 tombstone)
```

> `purged` 与 `expired`/`archived` 不同。`purged` 表示原始健康内容（答案、照片 key、AI 响应）已被删除或不可逆匿名化。详见 §6.5 删除与保留。

### 6.3 档案条目状态转换

档案条目是用户对某一问题的当前有效状态投影，随新评估事件动态更新。

```text
                         ┌────────────────────────────────────────┐
                         ▼                                        │
[无条目] ──首次 active 评估──→ confirmed ──同来源新 active 评估──→ confirmed
                              │            │
                              │            └──不同来源 active 评估──→ 一致性检查
                              │                                         │
                              │                    ┌────────────────────┴────────────────────┐
                              │                    ▼                                           ▼
                              │           severity 完全一致 → confirmed              否则 → conflict
                              │           (combined_severity = 该共同值)             (combined_severity = null)
                              │           （任一来源 severity 为空 → provisional）       │
                              │                                                              │
                              │                                                  新 active 评估覆盖 → 重新一致性检查
                              │
                              ├──安全信号触发──→ provisional (combined_severity = null)
                              │
                              └──所有事件 purged/expired──→ [无条目]
```

**关键规则：**

- `confirmed`：**所有** 来源 severity **完全一致** 且非空
- `provisional`：安全信号触发，或任一来源 severity 为空
- `conflict`：多个非空来源 severity **任意不一致**（包括差 1 级）
- `conflict` 或 `provisional` 状态下 `combined_severity` **必须为空**（无合并结论）
- 不存在"差 1 级取更严重并 confirmed"的规则
- provisional 时即使有单一非空来源，combined_severity 仍为 null（保守原则，鼓励重新评估）

### 6.4 冲突解决规则

冲突是指 **多个非空来源 severity 任意不一致**，不自动合并。

| self_test severity | ai_photo severity | certainty | combined_severity |
| --- | --- | --- | --- |
| normal | normal | confirmed | normal |
| mild | mild | confirmed | mild |
| moderate | moderate | confirmed | moderate |
| severe | severe | confirmed | severe |
| normal | mild | **conflict** | **null** |
| mild | moderate | **conflict** | **null** |
| moderate | severe | **conflict** | **null** |
| normal | moderate | **conflict** | **null** |
| normal | severe | **conflict** | **null** |
| mild | severe | **conflict** | **null** |
| 空 | 任意 | provisional | **null** |
| 任意 | 空 | provisional | **null** |
| 空 | 空 | provisional | **null** |
| 仅一个来源（任一） | — | confirmed | = 该来源 severity |

> **不存在"差 1 级取更严重并 confirmed"规则。** 任何非空来源 severity 不一致（无论差几级）均进入 `conflict`，`combined_severity` 必须为 null。

### 6.5 删除、保留、重新评估和新安全信号语义

| 操作 | 语义 | 数据处理 |
| --- | --- | --- |
| **用户删除评估** | 标记 lifecycle 为 `purged` | **实际删除**原始健康数据（answers、ai_response、ai_model_meta、photo_keys）；**不保留**可关联的 user_id + issue_id 组合；仅保留不可还原健康内容的最小删除回执（详见 tombstone 规范） |
| **保留期到期** | lifecycle → `expired` → 惰性触发 `purged` | 同上，实际删除健康数据 |
| **重新评估** | 同来源新 active 事件使旧事件 `superseded` | 旧事件载荷保留（仍是 active→superseded，未删除） |
| **照片对象删除** | 事件 purge 时同步删除 OSS 对象 | 可验证删除结果（删除响应或 404） |
| **新安全信号** | 相关问题 certainty → `provisional`，触发风险分类重算 | 不删除数据，只调整 certainty 和使优先级快照失效 |
| **用户删除账号/健康数据** | 级联清理（详见下方级联顺序） | 安全信号原始载荷也必须删除或不可逆匿名化 |

### 6.6 Tombstone 规范

purge 后保留的最小删除回执 **不得** 包含可关联到健康内容的字段组合（如 user_id + issue_id）。

**允许保留的字段（无法还原健康内容）：**

```json
{
  "receipt_id": "random-uuid-不可关联到原 event_id/user_id/issue_id",
  "deleted_at": "2026-07-11T...",
  "purge_reason": "user_delete|retention_expired|consent_withdrawn|account_deletion",
  "policy_version": "retention-policy-2026-07-11",
  "object_delete_status": "oss_deleted|oss_not_applicable|oss_deleted_or_not_found"
}
```

> tombstone 的 `object_delete_status` **只表示完成态**，允许值为 `oss_deleted` / `oss_not_applicable` / `oss_deleted_or_not_found`（任选一致命名）。
> **不得** 在 tombstone 中使用 pending/failed 状态（如 `oss_failed_retry_pending`）。失败重试状态（`failed_oss_retry` / `failed_permanent`）只存在于 `purge_operations`，**不写入** completed tombstone，**不对外声明**"已完全删除"。
> purge 失败时，不写 tombstone；purge_operations 保持 failed 状态并触发告警，直到重试成功后才写 completed tombstone。

**禁止保留的字段（可关联或还原健康内容）：**

- user_id（原始用户 ID）
- issue_id（原始问题 ID）
- source（来源类型）
- self_test_answers、ai_response、ai_model_meta、photo_keys
- 原 event_id（如需审计连续性，使用 receipt_id 的随机新 ID）
- created_at（原事件创建时间，可能间接关联健康事件时间线）

> 如安全审计需要留痕，只保留上述不可关联的最小删除回执。`receipt_id` 是新的随机 ID，不是原始 event_id。

### 6.7 Purge 执行流程与 photo_keys 保护

#### 6.7.1 核心约束

在 photo_keys 的 OSS 对象被确认删除（成功响应或 404）之前，**不得** 删除包含 photo_keys 的数据库行。违反此约束将导致 OSS 孤岛对象无法定位和清理。

#### 6.7.2 持久化 Purge Job

purge 不在单次事务中完成，而是通过持久化 `purge_operations` 表驱动异步执行：

**状态机：**

```text
[创建] ──→ freezing ──→ oss_deleting ──→ db_deleting ──→ completed
             │               │                  │
             └─租约超时──────┴─→ retrying_oss   └─→ retrying_db
                             │                  │
                             └─失败─→ failed_oss_retry
                                                └─失败─→ failed_db_retry
                                                             │
                                                    超过 max_attempts ─→ failed_permanent（告警）
```

**执行顺序：**

1. **冻结写入 + 创建 purge operation**：标记相关事件为不可变（lifecycle→expired），创建 purge_operations 记录，收集 photo_keys 到 purge operation 的 `encrypted_object_keys` 字段
2. **删除投影和目标**：posture_user_goals → posture_profile_entries（快速，同步）
3. **删除 OSS 对象**：逐个删除 `encrypted_object_keys` 中的对象，每个成功后更新 purge operation 状态。验证每个删除（成功响应或 404）
4. **立即清除 encrypted_object_keys**：OSS 全部确认删除（成功或 404）后，**立即**将 purge operation 的 `encrypted_object_keys` 置为 null。此步必须在任何数据库健康数据行删除之前完成，以确保待删除对象定位信息在 DB 删除前已被销毁，且后续 DB 删除失败时不会留下可还原的加密对象 key
5. **删除数据库健康数据**：删除 posture_assessment_events 行、posture_safety_signals 行、idempotency_records 相关记录
6. **写入 tombstone**：在 posture_purge_tombstones 中写入不可关联回执（仅完成态，见 §6.6）
7. **标记 purge operation 为 completed**（completed 后清理可关联字段，见 §6.7.3）
8. **删除或匿名化用户记录**（仅账号删除场景，由 auth 模块负责；此时所有 FK 引用的健康数据已删除，不受 NOT NULL FK 阻塞）

> **顺序约束（重要）：** 步骤 4（清除 encrypted_object_keys）**必须** 在步骤 5（删除数据库健康数据行）之前完成。理由：在 OSS 确认删除后立即销毁对象 key，可保证即使后续 DB 删除失败重试，也不会在数据库中残留可还原的加密对象定位信息。这与 photo_keys 保护规则不冲突——步骤 1 已将 photo_keys 复制到 purge_operations，步骤 3 已确认 OSS 删除完毕，此时清除 key 不影响重试能力。

**photo_keys 保护规则：**

- photo_keys 在步骤 1 从事件行复制到 `purge_operations.encrypted_object_keys`（加密存储）
- 步骤 3（OSS 删除）完成前，photo_keys 在 purge operation 中持续可用于重试
- 步骤 4 在 OSS 全部确认删除（成功或 404）后**立即**清除 encrypted_object_keys，且此步在步骤 5（DB 健康数据行删除）之前
- encrypted_object_keys 严格限制访问，不进入日志或 tombstone
- purge operation 的 encrypted_object_keys 使用应用层加密（密钥不在数据库中）

**失败重试规则：**

- OSS 删除失败：进入 `failed_oss_retry`，按指数退避重试（最多 10 次，最长 7 天）
- DB 删除失败：进入 `failed_db_retry`，按指数退避重试（最多 5 次）
- 超过最大重试次数：进入 `failed_permanent`，触发告警
- 不允许"部分清理完成"状态对外可见（用户视角：删除请求已接受；后台保证最终一致）
- 清理操作幂等（重复执行不报错，已删除对象返回成功）
- `freezing` / `oss_deleting` / `db_deleting` 也必须携带可恢复租约；进程在初始执行任一阶段崩溃后，worker 可按对应 OSS/DB 阶段恢复，不得永久冻结
- `failed_permanent` 状态需人工介入

> **关键：** 不得在持久化重试能力建立前删除唯一的对象定位信息。tombstone 只能在相关数据库健康数据已删除、OSS 已删除或确认 404 后标记 completed。不得声称后台仍有待删除对象时"删除已完全完成"。

#### 6.7.3 Completed 后的关联字段清理

purge_operations 进入 `completed` 状态后，**不得** 保留任何可关联到用户或健康内容的字段（user_id、target_event_ids、target_signal_ids、encrypted_object_keys）。

**pending / failed 状态：** 保留 user_id、target_event_ids、target_signal_ids（以及未清除的 encrypted_object_keys）用于重试和人工修复。

**completed 后处理（二选一，实现时确定）：**

- **方案 A（推荐）**：删除整行 purge_operations 记录。tombstone（posture_purge_tombstones）已保留不可关联的完成回执，purge_operations 行无需保留。
- **方案 B**：保留行但 scrub 所有可关联字段——将 user_id、target_event_ids、target_signal_ids、encrypted_object_keys 全部置为 null，仅保留不可关联的 operational metadata（id、trigger、status=completed、attempt_count、created_at、completed_at）。

**FK 约束：** `purge_operations.user_id` 为 nullable FK（ON DELETE SET NULL）。账号删除场景中，先完成所有健康数据 purge（步骤 1-7），此时所有引用 user 的健康数据行已删除；随后 auth 模块删除 user 行时，purge_operations.user_id 被 SET NULL（方案 B）或行已删除（方案 A），**不被 NOT NULL FK 阻塞**。

---

## 7. Data Ownership

| 数据 | 所有者 | 读取范围 | 写入权限 |
| --- | --- | --- | --- |
| 体态知识库 | 系统（版本化 JSON） | 所有用户可读（无认证） | 仅开发者通过代码更新 |
| 评估事件 | 创建用户 | 仅创建用户 | 仅创建用户通过 API/Tool |
| 体态档案 | 所属用户 | 仅所属用户 | 系统根据事件投影维护 |
| 改善目标 | 所属用户 | 仅所属用户 | 仅所属用户通过确认 API |
| 照片对象 | 所属用户 | 仅所属用户 | 仅系统在同意后写入 |
| AI 模型元数据 | 系统 | 仅所属用户 | 系统在照片分析时写入 |

Agent 不直接访问数据库，不通过 Tool 绕过照片门，不跨用户读写。

---

## 8. Data Model Options and Decision

### 8.1 方案 A：扩展现有 `posture_assessments`

在现有表上增加 `source_type`、`certainty`、`content_version`、`model_metadata`、`superseded_by` 等列。

| 维度 | 评价 |
| --- | --- |
| 数据一致性 | 中。单表无投影一致性问题 |
| 历史可追踪性 | 中。靠 `superseded_by` 链条 |
| 查询复杂度 | 高。当前档案需 `MAX(created_at) GROUP BY (issue_id, source_type)` |
| Flutter 兼容 | 中。历史 API 兼容，但档案需客户端聚合 |
| migration 风险 | 低。ADD COLUMN 可选默认值 |
| 后续训练与 Agent 复用 | 低。Agent 需复杂查询获取当前状态 |

### 8.2 方案 B：评估事件表 + 当前档案投影（推荐）

新表：
- `posture_assessment_events`（重命名现有表，追加列）— 不可变事件日志
- `posture_profile_entries` — 每用户每问题每来源的当前状态
- `posture_user_goals` — 用户确认的主要改善目标

| 维度 | 评价 |
| --- | --- |
| 数据一致性 | 高。事件和投影在同一事务中写入 |
| 历史可追踪性 | 高。事件表是不可变审计日志 |
| 查询复杂度 | 低。档案直接读取投影表 |
| Flutter 兼容 | 高。档案 API 返回投影，无需客户端聚合 |
| migration 风险 | 中。需要重命名 + 回填 + 新表 |
| 后续训练与 Agent 复用 | 高。`get_posture_profile` 直接读投影 |

### 8.3 方案 C：事件溯源 + 物化视图

事件表为唯一真相来源，档案通过物化视图计算。

| 维度 | 评价 |
| --- | --- |
| 数据一致性 | 最高。投影可重建 |
| 历史可追踪性 | 最高。完整事件溯源 |
| 查询复杂度 | 中。物化视图需 REFRESH |
| Flutter 兼容 | 高 |
| migration 风险 | 高。物化视图刷新策略复杂 |
| 后续训练与 Agent 复用 | 中。物化视图刷新时机需协调 |

### 8.4 推荐方案：B

**理由：**

1. **Agent Tool 契约匹配**：`get_posture_profile` 直接返回投影表，类型化、快速
2. **冲突显式化**：投影表有 `certainty` 字段，冲突在写入时检测并存储
3. **Flutter 简化**：档案 API 返回当前状态，历史 API 仍从事件表读取
4. **迁移安全**：重命名现有表 → 回填投影 → 向后兼容
5. **不过度工程**：方案 C 的物化视图在单用户场景下增加复杂度但收益有限

### 8.5 推荐方案的表结构设计（不在本任务创建 migration）

#### `posture_assessment_events`（由 `posture_assessments` 重命名 + 追加）

| 列 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID PK | 否 | 事件 ID |
| `user_id` | UUID FK → users.id | 否 | 索引 |
| `issue_id` | String(20) | 否 | 知识库问题 ID |
| `source` | String(20) | 否 | `self_test` / `ai_photo`（从 `method` 回填） |
| `severity` | String(20) | **是** | `normal` / `mild` / `moderate` / `severe`；**空表示来源未给出确定严重度**（原 `uncertain` → severity 为空） |
| `self_test_answers` | JSONB | 是 | 原始答案 |
| `ai_response` | JSONB | 是 | 校验后的 AI 输出 |
| `ai_model_meta` | JSONB | 是 | 模型名称、版本、置信度、evidence |
| `photo_keys` | JSONB | 是 | OSS 对象 key |
| `content_version` | String(20) | 是 | 自测内容版本 |
| `lifecycle` | String(20) | 否 | `active` / `superseded` / `expired` / `purged` |
| `created_at` | DateTime(tz) | 否 | `now()` |

索引：`(user_id, issue_id, source, lifecycle)` 复合索引，`(user_id, created_at DESC)`

> **purge 语义：** 当 lifecycle 进入 `purged` 时，**整行事件被删除**，所有载荷列（`self_test_answers`、`ai_response`、`ai_model_meta`、`photo_keys`）连同 `user_id`、`issue_id`、`source`、原始 `event_id` 等可关联字段全部移除。仅在独立的 tombstone 表中保留不可关联的最小删除回执（§6.6）。purge 通过持久化 `purge_operations` 异步执行（§6.7），确保 photo_keys 在 OSS 确认删除前不丢失。

#### `posture_profile_entries`

| 列 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID PK | 否 | 条目 ID |
| `user_id` | UUID FK → users.id | 否 | 索引 |
| `issue_id` | String(20) | 否 | 知识库问题 ID |
| `latest_self_test_event_id` | UUID FK → events | 是 | |
| `latest_photo_event_id` | UUID FK → events | 是 | |
| `combined_severity` | String(20) | **是** | 合并后严重度；仅在所有非空来源 severity **完全一致** 且 certainty=confirmed 时有值；`certainty=conflict` 或 `provisional` 时 **必须为 null** |
| `certainty` | String(20) | 否 | `confirmed` / `provisional` / `conflict` |
| `sources` | JSONB | 否 | `[{source, event_id, severity, created_at, confidence?}]`，`confidence` 仅 ai_photo 来源包含 |
| `has_conflict` | Boolean | 否 | 冗余标记加速查询 |
| `risk_tier` | String(20) | 否 | 当前风险等级：`normal` / `cautious` / `restricted` / `red_flag` |
| `risk_version` | String(30) | 否 | 风险分类规则版本 |
| `updated_at` | DateTime(tz) | 否 | 最近更新时间 |

约束：`(user_id, issue_id)` 唯一

#### `posture_user_goals`

| 列 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID PK | 否 | |
| `user_id` | UUID FK → users.id | 否 | 索引 |
| `issue_id` | String(20) | 否 | 目标问题 |
| `priority_rank` | Integer | 否 | 用户确认的优先级（1 最高） |
| `confirmed_at` | DateTime(tz) | 否 | 确认时间 |
| `suggestion_id` | String(64) | 否 | 服务端生成的优先级建议 ID（乐观锁） |
| `profile_version` | String(64) | 否 | 确认时的档案版本哈希 |
| `rule_version` | String(30) | 否 | 确认时的优先级规则版本 |
| `risk_version` | String(30) | 否 | 确认时的风险分类版本 |
| `superseded_at` | DateTime(tz) | 是 | 被新确认取代 |

#### `posture_safety_signals`（Phase 1 实现，非推迟）

| 列 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID PK | 否 | |
| `user_id` | UUID FK → users.id | 否 | 索引。purge 时 **整行删除**（非清空 user_id），仅在 tombstone 表保留不可关联回执 |
| `signal_type` | String(30) | 否 | `pain` / `numbness` / `weakness` / `dizziness` / `acute_trauma` / `other` |
| `body_region` | String(30) | 是 | 关联部位（可空，表示全身） |
| `related_issue_id` | String(20) | 是 | 关联问题（可空） |
| `severity_hint` | String(20) | 是 | 用户主观描述的严重度提示（仅参考，不单独触发医学升级） |
| `reported_at` | DateTime(tz) | 否 | 用户报告时间 |
| `lifecycle` | String(20) | 否 | `active` / `resolved` |
| `invalidates_until` | DateTime(tz) | 否 | 快照失效/复查提醒截止时间（**仅用于失效和提醒，不用于自动降低 risk_tier**） |
| `resolved_at` | DateTime(tz) | 是 | 解除时间（lifecycle=resolved 时必填） |
| `resolution_basis` | String(30) | 是 | `reclassification`（基于新的结构化信息重新分类） |
| `resolution_source` | JSONB | 是 | 解除依据：重新分类时的档案快照、新的安全信号集、适用的 rule_version |
| `resolved_risk_version` | String(30) | 是 | 解除时使用的风险规则版本 |
| `created_at` | DateTime(tz) | 否 | `now()` |

索引：`(user_id, reported_at DESC)`，`(user_id, lifecycle)`

> 此表在 Phase 1 实现，用于闭环验证"新安全信号使旧资格判断失效"。写入入口：API + Tool。
> 安全信号支持 `active` → `resolved` 生命周期转换。**restricted/red_flag 的解除只能通过基于新的结构化信息重新分类**，不能仅因时间经过、用户点击确认或声称已就医自动恢复。

#### `idempotency_records`（Phase 1 实现，所有副作用 Tool 的唯一幂等机制）

统一幂等表，覆盖 `analyze_posture_photo`、`confirm_posture_goals`、`report_safety_signal` 三个副作用 Tool。这是副作用操作的 **唯一** 幂等机制，不在业务表（如 assessment_events）中重复设置幂等列。

| 列 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID PK | 否 | |
| `user_id` | UUID FK → users.id | 否 | 索引 |
| `operation` | String(40) | 否 | `analyze_photo` / `confirm_goals` / `report_safety_signal` |
| `idempotency_key` | String(64) | 否 | 客户端生成的防重键 |
| `request_hash` | String(64) | 否 | 请求体哈希（用于检测相同 key 但不同请求） |
| `status` | String(20) | 否 | `in_progress` / `completed` / `failed` |
| `result_ref` | String(64) | 是 | 指向首次执行结果的引用 ID（如 event_id 或 goal_id），**不存储完整健康响应** |
| `created_at` | DateTime(tz) | 否 | `now()` |
| `expires_at` | DateTime(tz) | 否 | 幂等保留期（默认 24h，到期由定期清理任务删除） |

约束：`(user_id, operation, idempotency_key)` **唯一**

索引：`(user_id, operation, idempotency_key)` 唯一索引，`(expires_at)` 用于定期清理

**数据最小化原则：**

- **不默认持久化完整健康响应**（原 `response` JSONB 列已移除）
- `result_ref` 仅存储结果的引用 ID（如 event_id），客户端重试时服务端通过 ID 查询原始结果重建响应
- 如幂等记录仍存在但 `result_ref` 已悬空（如部分清理只删除了事件），重放返回
  `410 Gone`，不返回旧缓存健康内容；完整隐私清除会删除关联幂等记录，不为维持 410
  语义保留可关联的用户/健康元数据

**到期清理（确定性机制）：**

- `expires_at` 到期后，定期清理任务 **删除** 记录（非仅标记）
- 清理频率：每小时检查一次（Phase 1 可由惰性触发代替）
- 已过期的 idempotency_key 不再阻止新请求

**隐私删除覆盖：**

idempotency_records 纳入以下场景的清理：

- 用户删除账号：级联清理中删除该用户所有 idempotency_records
- 用户删除全部健康数据：删除相关 idempotency_records
- 撤回相关同意：删除照片分析相关的 idempotency_records
- 定期过期清理：expires_at 到期后删除

**幂等规则：**

- 相同 `(user_id, operation, idempotency_key)` + 相同 `request_hash` → 通过 `result_ref` 查询并重建响应（不重复执行副作用）
- 相同 `(user_id, operation, idempotency_key)` + **不同** `request_hash` → **拒绝**（400 `idempotency_key_conflict`）
- `status=in_progress` 时并发请求等待首次完成或超时

#### `posture_purge_tombstones`（Phase 1 实现，不可关联的删除回执）

当评估事件或安全信号被 purge 时，原始行被删除，仅在此表中保留不可关联的最小删除回执（§6.6）。

| 列 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `receipt_id` | UUID PK | 否 | 随机新 UUID，**不可关联**到原 event_id/user_id/issue_id |
| `deleted_at` | DateTime(tz) | 否 | purge 执行时间 |
| `purge_reason` | String(30) | 否 | `user_delete` / `retention_expired` / `consent_withdrawn` / `account_deletion` |
| `policy_version` | String(40) | 否 | 保留策略版本（如 `retention-policy-2026-07-11`） |
| `object_delete_status` | String(30) | 否 | `oss_deleted` / `oss_not_applicable` / `oss_deleted_or_not_found`（仅完成态；pending/failed 不写 tombstone，见 §6.6） |

索引：`(deleted_at)` 用于审计查询

> 此表 **不包含** user_id、issue_id、source、原始 event_id 或任何健康内容。仅用于证明 purge 操作已执行，不可逆向还原健康数据。

#### `purge_operations`（Phase 1 实现，持久化 purge job）

驱动异步 purge 执行的持久化任务表（§6.7）。

| 列 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID PK | 否 | purge operation ID |
| `user_id` | UUID FK → users.id | 是 | 发起 purge 的用户。**pending/failed 状态保留**用于重试和人工修复；**completed 后必须置 null 或删除整行**（见 §6.7.3），不得保留可关联字段。FK 为 nullable（ON DELETE SET NULL），确保账号删除时 user 行删除不被 NOT NULL FK 阻塞 |
| `trigger` | String(30) | 否 | `user_delete` / `retention_expired` / `consent_withdrawn` / `account_deletion` |
| `status` | String(30) | 否 | `freezing` / `oss_deleting` / `db_deleting` / `retrying_oss` / `retrying_db` / `completed` / `failed_oss_retry` / `failed_db_retry` / `failed_decrypt` / `failed_permanent` / `cancelled` |
| `encrypted_object_keys` | BYTEA | 是 | 待删除的 OSS 对象 key（应用层加密，OSS 全部确认删除后 **立即清除此列**，见 §6.7 步骤 4） |
| `target_event_ids` | JSONB | 是 | 待 purge 的 assessment event IDs。**pending/failed 状态保留**用于重试；**completed 后必须置 null 或随行删除**（见 §6.7.3） |
| `target_signal_ids` | JSONB | 是 | OSS 前为待 purge 的 safety signal ID 列表；OSS 完成、DB 待重试时可暂存 `{signal_ids, oss_outcome}` 最小 envelope。不得写入对象 key 或健康载荷；completed 后清理 |
| `attempt_count` | Integer | 否 | 当前重试次数 |
| `max_attempts` | Integer | 否 | 最大重试次数（默认 OSS:10, DB:5） |
| `next_retry_at` | DateTime(tz) | 是 | 下次重试时间（指数退避） |
| `expires_at` | DateTime(tz) | 否 | 最长重试期限（默认 7 天，到期进入 failed_permanent） |
| `created_at` | DateTime(tz) | 否 | `now()` |
| `completed_at` | DateTime(tz) | 是 | 完成时间 |

索引：`(status, next_retry_at)` 用于重试调度

**安全规则：**

- `encrypted_object_keys` 使用应用层加密（密钥由配置注入，不在数据库中）
- `encrypted_object_keys` 严格限制访问，**不进入日志或 tombstone**
- OSS 全部确认删除后 **立即** 将此列设为 null（§6.7 步骤 4，在 DB 健康数据删除之前）
- 仅 purge 执行器有权读取此列
- **completed 后不得保留可关联字段**（user_id、target_event_ids、target_signal_ids、encrypted_object_keys），见 §6.7.3

---

## 9. API Contracts

### 9.1 现有 API（保持向后兼容）

| 方法 | 路径 | 变更 |
| --- | --- | --- |
| GET | `/api/v1/posture/issues` | 不变 |
| GET | `/api/v1/posture/issues/{issue_id}` | 不变 |
| GET | `/api/v1/posture/issues/{issue_id}/related` | 不变 |
| POST | `/api/v1/posture/assess` | 写入 events 表 + 更新 profile |
| POST | `/api/v1/posture/assess/photo` | 写入 events 表 + 更新 profile（门禁不变） |
| GET | `/api/v1/posture/history` | 从 events 表读取，新增 source 字段 |

### 9.2 新增 API

#### GET `/api/v1/posture/profile`

获取当前用户的完整体态档案。

**认证：** JWT Bearer

**响应（200）：**

```json
{
  "user_id": "uuid",
  "evaluated_issues": [
    {
      "issue_id": "HN-01",
      "issue_name": "头部前倾",
      "category": "head_neck",
      "combined_severity": "moderate",
      "certainty": "confirmed",
      "has_conflict": false,
      "sources": [
        {"source": "self_test", "severity": "moderate", "event_id": "uuid", "created_at": "2026-07-11T..."}
      ],
      "updated_at": "2026-07-11T..."
    }
  ],
  "unevaluated_categories": ["lower_limb"],
  "summary": {
    "total_evaluated": 3,
    "total_conflict": 0,
    "total_provisional": 0
  }
}
```

#### GET `/api/v1/posture/profile/{issue_id}`

获取单个问题的档案详情。

**响应（200）：**

```json
{
  "issue_id": "HN-01",
  "issue_name": "头部前倾",
  "combined_severity": "moderate",
  "certainty": "conflict",
  "has_conflict": true,
  "sources": [
    {"source": "self_test", "severity": "moderate", "event_id": "uuid", "created_at": "...", "answers": [...]},
    {"source": "ai_photo", "severity": "normal", "event_id": "uuid", "created_at": "...", "confidence": 0.82}
  ],
  "related_priority": "high",
  "updated_at": "..."
}
```

#### GET `/api/v1/posture/priorities`

获取基于当前档案的多问题优先级建议。

**资格规则（确定性）：**

- `normal` severity 条目 **不进入** 改善目标候选
- `provisional` / `conflict` 条目进入 **重测或专业评估路径**（不进入普通优先级排序）
- `risk_tier=restricted` / `red_flag` 的条目优先进入 **安全阻断路径**，不得因同时为
  `provisional` 而降级到普通重测路径
- 仅 `certainty=confirmed`、severity 非 `normal` 且 `risk_tier=normal/cautious`
  的条目可进入普通优先级排序

**响应（200）：**

```json
{
  "suggestion_id": "srv-generated-uuid",
  "profile_version": "hash-of-current-profile",
  "rule_version": "2026-07-17-v1",
  "risk_version": "2026-07-16-v4",
  "generated_at": "...",
  "normal_candidates": [
    {
      "issue_id": "HN-01",
      "issue_name": "头部前倾",
      "suggested_rank": 1,
      "reasons": ["严重度为 moderate", "与已确认的圆肩强关联"],
      "relation_type": "共存(UCS)",
      "association_weight": 0.9
    }
  ],
  "retest_required": [
    {
      "issue_id": "SS-02",
      "reason": "来源不一致（conflict），建议重新评估或咨询专业人士"
    }
  ],
  "safety_blocked": [
    {
      "issue_id": "SC-10",
      "risk_tier": "restricted",
      "reason": "存在受限安全信号，当前不进入普通自动建议路径",
      "next_action": "仅提供健康教育，并建议按需寻求专业评估"
    }
  ],
  "disclaimer": "优先级属于建议，关联图谱仅用于排查参考，不作为病因认定。"
}
```

#### POST `/api/v1/posture/goals/confirm`

用户确认主要改善目标。

**资格前置检查（服务端执行）：**

1. 重新读取最新档案（不从快照）
2. 重新执行风险分类（使用最新安全信号）
3. 校验 `suggestion_id` 与当前服务端生成的 ID 匹配
4. 校验 `profile_version` 与当前档案版本匹配
5. 拒绝 restricted、red_flag、provisional、conflict、normal 和未评估条目
6. 通过后写入 goals

**请求：**

```json
{
  "suggestion_id": "from-server-priorities-response",
  "profile_version": "from-server-priorities-response",
  "goals": [
    {"issue_id": "HN-01", "priority_rank": 1},
    {"issue_id": "SS-01", "priority_rank": 2}
  ],
  "idempotency_key": "client-generated-uuid"
}
```

> 客户端 **不接受** 自报的 `priority_context_snapshot`。`suggestion_id`、`profile_version`、`rule_version` 均由服务端在 priorities 响应中生成，客户端回传用于乐观锁校验。

> `goals` 必须包含 1–3 个当前 `normal_candidates` 中的不同 issue；`priority_rank`
> 必须唯一且连续为 `1..N`。用户可在候选范围内调整顺序，但不能确认未出现在当前候选列表中的
> 条目。

**响应（200）：**

```json
{
  "confirmed_goals": [
    {"issue_id": "HN-01", "priority_rank": 1, "confirmed_at": "..."}
  ],
  "can_generate_plan": true,
  "risk_version": "2026-07-16-v4"
}
```

> `can_generate_plan: true` 仅表示前置条件满足，Phase 1 不实现计划生成。

### 9.3 响应错误码

| 状态码 | code | 场景 |
| --- | --- | --- |
| 400 | `invalid_goal` | goals 数量/排名非法，或确认未评估、normal、provisional、conflict、非当前候选条目 |
| 401 | — | 未认证 |
| 403 | — | 跨用户访问 |
| 404 | `issue_not_found` | 问题 ID 不存在 |
| 409 | `stale_priority` | suggestion_id 或 profile_version 不匹配（有新评估或安全信号） |
| 409 | `restricted_blocked` | 受限条目阻止普通目标确认 |
| 409 | `red_flag_blocked` | 红旗条目阻止目标确认 |
| 503 | `photo_analysis_disabled` | 照片分析未启用 |
| 503 | `model_unavailable` | AI 模型不可用 |

---

## 10. Tool Contracts

Tools 是内部应用层类型化函数，不暴露独立 HTTP 路由。REST API 和未来 Agent orchestrator 共同调用同一组函数。

### 10.0 Tool 身份边界（共享规则）

所有 Tool 共享以下身份和安全约束：

**ActorContext（服务端注入，非模型参数）：**

- `user_id` 由服务端从 JWT 会话注入为 `ActorContext.user_id`，**不作为模型可控的 Tool 参数**
- `consent_record`（同意记录）由服务端隐私上下文读取，**不暴露给模型**
- `risk_context`（风险分类快照）由服务端在调用前生成，**不暴露给模型**
- 模型/Agent 只能传递业务意图参数（issue_id、photo_keys、answer 等），不能传递身份或授权信息

**photo_keys 所有权校验：**

- 副作用 Tool 接收 `photo_keys` 时，通过服务端 `PhotoOwnershipVerifier` 校验这些 key
  是当前 `ActorContext.user_id` 的已上传对象
- 不接受跨用户的 photo_keys
- 对象 key 中包含 user_id 或匹配路径前缀只能用于格式预检，**不能**单独作为所有权证明
- Phase 1 没有上传授权记录或可核验对象元数据，默认 verifier 必须 fail closed；
  照片隐私门仍先返回 `PhotoAnalysisDisabled`，不得触发模型、写事件或创建幂等记录
- 隐私门未来启用前，必须提供持久化上传授权或由对象存储返回的可信 owner metadata，
  并完成真实实现与测试；测试 fake 不能作为生产启用证据

**幂等性（统一 `idempotency_records` 表，§8.5）：**

- 3 个副作用 Tool（`analyze_posture_photo`、`confirm_posture_goals`、`report_safety_signal`）使用客户端提供的 `idempotency_key`
- 服务端通过 `idempotency_records` 表记录 `(user_id, operation, idempotency_key)` 组合
- 相同组合 + 相同 `request_hash` → 返回首次结果（不重复执行副作用）
- 相同组合 + **不同** `request_hash` → 拒绝（400 `idempotency_key_conflict`）
- 业务表（如 assessment_events）不重复设置幂等列
- `confirm_posture_goals` 的 `result_ref` 指向该次确认批次的锚点 goal ID；同批 goals
  使用同一个服务端 `confirmed_at`。重放必须按锚点恢复首次确认的完整批次，即使该批次后来
  已被 supersede，也不得返回后续确认结果或重复写入

**优先级确认的服务端控制值：**

- `suggestion_id`、`profile_version`、`rule_version`、`risk_version` 均由服务端在 priorities 响应中生成
- 客户端回传这些值用于乐观锁校验，**不接受客户端自报的 `priority_context_snapshot`**

**共享安全约束：**

- 当前用户授权检查（不跨用户读写）
- 最小必要数据读取
- 不直接执行 SQL
- 不绕过照片门
- 失败状态和审计记录
- 审计字段不含照片 URL、原始模型响应或健康档案

### 10.1 `list_posture_issues`

```python
def list_posture_issues(
    category: Optional[str] = None,
) -> List[IssueSummary]
```

| 属性 | 说明 |
| --- | --- |
| 输入 | `category`（可选，值域为 5 个部位） |
| 输出 | `List[IssueSummary]`，含 `id, name_cn, category, aliases, definition` |
| 授权 | 无（公开知识数据） |
| 数据读取 | 知识库缓存 |
| 副作用 | 无 |
| 幂等性 | 是 |
| 错误类型 | `IssueNotFound`（category 无效） |
| 审计字段 | 无（只读公开数据） |

### 10.2 `get_posture_issue`

```python
def get_posture_issue(
    issue_id: str,
) -> IssueDetail
```

| 属性 | 说明 |
| --- | --- |
| 输入 | `issue_id` |
| 输出 | `IssueDetail`，含完整知识字段和扩展自测结构 |
| 授权 | 无 |
| 数据读取 | 知识库缓存 |
| 副作用 | 无 |
| 幂等性 | 是 |
| 错误类型 | `IssueNotFound` |
| 审计字段 | 无 |

### 10.3 `guide_posture_self_test`

```python
async def guide_posture_self_test(
    actor: ActorContext,
    issue_id: str,
) -> SelfTestGuide
```

| 属性 | 说明 |
| --- | --- |
| 输入 | `actor`（服务端注入）、`issue_id` |
| 输出 | `SelfTestGuide`，含步骤、正确姿势、常见错误、停止条件、图示 key、内容版本 |
| 授权 | JWT 用户（从 actor 提取） |
| 数据读取 | 知识库 + 用户档案（用于个性化提示，如已有结果） |
| 副作用 | 无 |
| 幂等性 | 是 |
| 错误类型 | `IssueNotFound`, `UserNotFound` |
| 审计字段 | 无（只读引导） |
| 照片门关闭行为 | 不受影响（自测路径始终可用） |
| 重新安全分类 | 不需要（只读引导） |

### 10.4 `analyze_posture_photo`

```python
async def analyze_posture_photo(
    actor: ActorContext,
    issue_id: str,
    photo_keys: List[str],
    idempotency_key: str,
) -> PhotoAssessmentResult
```

| 属性 | 说明 |
| --- | --- |
| 输入 | `actor`（服务端注入，含 user_id 和 consent_record）、`issue_id`、`photo_keys`、`idempotency_key` |
| consent_token | **从 `actor.consent_record` 读取，非模型参数** |
| photo_keys 所有权 | 通过 `PhotoOwnershipVerifier` 校验已上传对象归属；路径前缀不构成证明 |
| 输出 | `PhotoAssessmentResult`，含 severity（可空）、confidence、evidence、model_meta |
| 授权 | JWT 用户 + 照片门 + 同意记录（从 actor 读取） |
| 数据读取 | 知识库 + 用户档案 + 模型 API |
| 副作用 | 创建评估事件 + 更新档案条目 |
| 幂等性 | 通过 `idempotency_key` 实现：相同 `(user_id, idempotency_key)` 在 24h 内返回首次结果 |
| 错误类型 | `PhotoAnalysisDisabled`, `ConsentRequired`, `PhotoOwnershipUnavailable`, `PhotoOwnershipDenied`, `ModelUnavailable`, `SchemaValidationFailed`, `IssueNotFound` |
| 审计字段 | `user_id, issue_id, model_name, model_version, confidence, created_at`（不含照片 URL 或原始响应） |
| 照片门关闭行为 | 认证后先返回 `PhotoAnalysisDisabled`；不探测对象是否存在，不创建幂等记录/事件，不调用模型，保留自测路径 |
| 重新安全分类 | 新事件触发档案 certainty 重算和风险分类更新 |

### 10.5 `get_posture_profile`

```python
async def get_posture_profile(
    actor: ActorContext,
    issue_id: Optional[str] = None,
) -> PostureProfile
```

| 属性 | 说明 |
| --- | --- |
| 输入 | `actor`、`issue_id`（可选） |
| 输出 | `PostureProfile`（完整档案或单条目），含 combined_severity（可空）、certainty、risk_tier |
| 授权 | JWT 用户 |
| 数据读取 | 档案投影表 + 知识库 |
| 副作用 | 无 |
| 幂等性 | 是 |
| 错误类型 | `UserNotFound`, `IssueNotFound` |
| 审计字段 | 无（只读） |
| 照片门关闭行为 | 不受影响。档案中的照片来源条目标注为"历史记录" |
| 重新安全分类 | 不需要（只读） |

### 10.6 `suggest_posture_priorities`

```python
async def suggest_posture_priorities(
    actor: ActorContext,
) -> PrioritySuggestions
```

| 属性 | 说明 |
| --- | --- |
| 输入 | `actor` |
| 输出 | `PrioritySuggestions`，含 `suggestion_id`（服务端生成）、`profile_version`、`rule_version`、`risk_version`、normal_candidates、retest_required、safety_blocked |
| 授权 | JWT 用户 |
| 数据读取 | 档案 + 安全信号 + 知识库关联图谱 |
| 资格规则 | restricted/red_flag 优先进入 safety_blocked；normal 不入候选；其余 provisional/conflict 进 retest_required；仅 confirmed+非normal+risk_tier normal/cautious 进 normal_candidates |
| 副作用 | 无（纯计算）。返回服务端生成的 `suggestion_id` 和 `profile_version` 供后续 confirm 乐观锁 |
| 幂等性 | 是（相同档案、安全信号和规则版本产生相同 suggestion_id） |
| 错误类型 | `UserNotFound`；无评估或无合格候选时返回三个空分区，不报错 |
| 审计字段 | 无（只读计算） |
| 照片门关闭行为 | 不受影响 |
| 重新安全分类 | **是。** 每次调用前重新读取档案 + 安全信号 + 重新执行风险分类。新安全信号使旧 suggestion_id 失效。 |
| 自动创建计划 | 否。优先级建议不自动创建训练计划。 |

### 10.7 `confirm_posture_goals`

```python
async def confirm_posture_goals(
    actor: ActorContext,
    suggestion_id: str,
    profile_version: str,
    goals: List[GoalInput],
    idempotency_key: str,
) -> ConfirmedGoals
```

| 属性 | 说明 |
| --- | --- |
| 输入 | `actor`、`suggestion_id`（来自 priorities 响应）、`profile_version`、`goals`、`idempotency_key` |
| 服务端控制值 | suggestion_id、profile_version、rule_version、risk_version 由服务端生成，客户端回传校验 |
| 资格前置检查 | 重新读取最新档案 → 重新执行风险分类 → 校验 suggestion_id 和 profile_version → 拒绝 restricted/red_flag/provisional/conflict/normal/未评估/非当前候选 |
| 输出 | `ConfirmedGoals`，含 confirmed_goals、can_generate_plan、risk_version |
| 授权 | JWT 用户 |
| 数据读取 | 档案 + 安全信号 + 优先级规则 |
| 副作用 | 写入 posture_user_goals，supersede 旧 goals |
| 幂等性 | 通过 `idempotency_key` 实现 |
| 错误类型 | `StalePriority`(409), `RestrictedBlocked`(409), `RedFlagBlocked`(409), `InvalidGoal`(400), `IssueNotFound`(404) |
| 审计字段 | user_id、goals、confirmed_at、risk_version（不含健康档案） |
| 照片门关闭行为 | 不受影响 |
| 重新安全分类 | **是。** 执行前重新执行风险分类。新 restricted/red_flag 信号阻止确认。 |

### 10.8 `report_safety_signal`

```python
async def report_safety_signal(
    actor: ActorContext,
    signal: SafetySignalInput,
    idempotency_key: str,
) -> SafetySignalResult
```

| 属性 | 说明 |
| --- | --- |
| 输入 | `actor`、`signal`（signal_type、body_region、related_issue_id、severity_hint、reported_at）、`idempotency_key` |
| consent_record | **从 `actor` 读取，非模型参数**（安全信号不涉及照片，但 actor 边界一致） |
| 输出 | `SafetySignalResult`，含 signal_id、lifecycle=active、risk_tier（更新后）、risk_version、invalidates_until |
| 授权 | JWT 用户 |
| 数据读取 | 档案 + 风险规则 |
| 副作用 | 写入 posture_safety_signals → 触发相关条目 certainty 降级 → 重新执行风险分类 → 使旧 suggestion_id 失效 |
| 幂等性 | 通过 `idempotency_key` 实现（24h 去重，相同 key + 不同 request_hash 拒绝） |
| 错误类型 | `InvalidSignal`(400)、`IdempotencyKeyConflict`(400)、`UserNotFound` |
| 审计字段 | user_id、signal_type、reported_at、risk_tier、risk_version（不含 severity_hint 原始文案） |
| 照片门关闭行为 | 不受影响（安全信号不涉及照片） |
| 重新安全分类 | **是。** 写入即触发风险分类重算。 |
| 恢复路径 | 此 Tool 仅写入 active 信号。解除（resolved）通过 `reclassify_risk` Tool（Phase 3 完整实现，Phase 1 可通过 API 触发重新分类）。 |

> 此 Tool 是第 8 个体态 Tool。全文 Tool 总数为 **8**。

---

## 11. Conflict Behavior

### 11.1 冲突检测规则

两个来源（self_test 和 ai_photo）的 severity 存在排序：`normal < mild < moderate < severe`。severity 为空表示来源未给出确定结论。

**合并规则：**

- 所有非空来源 severity **完全一致** → `confirmed`，`combined_severity` = 该共同值
- 任一来源 severity 为空 → `provisional`，`combined_severity` = **null**
- 多个非空来源 severity **任意不一致**（包括差 1 级）→ `conflict`，`combined_severity` = **null**
- 仅一个来源 → `confirmed`，`combined_severity` = 该来源 severity

| self_test severity | ai_photo severity | certainty | combined_severity | 说明 |
| --- | --- | --- | --- | --- |
| normal | normal | confirmed | normal | 完全一致 |
| mild | mild | confirmed | mild | 完全一致 |
| moderate | moderate | confirmed | moderate | 完全一致 |
| severe | severe | confirmed | severe | 完全一致 |
| normal | mild | **conflict** | **null** | 不一致 |
| mild | moderate | **conflict** | **null** | 不一致（差 1 级也冲突） |
| moderate | severe | **conflict** | **null** | 不一致（差 1 级也冲突） |
| normal | moderate | **conflict** | **null** | 不一致 |
| normal | severe | **conflict** | **null** | 不一致 |
| mild | severe | **conflict** | **null** | 不一致 |
| 空 | 任意非空 | provisional | **null** | 自测无结论 |
| 任意非空 | 空 | provisional | **null** | 照片无结论 |
| 空 | 空 | provisional | **null** | 两者都无结论 |
| 仅自测（无照片） | — | confirmed | = self_test severity | 单来源 |
| — | 仅照片 | confirmed | = ai_photo severity | 单来源 |

**关键规则：**

- **不存在"差 1 级取更严重并 confirmed"规则**
- 任何非空来源 severity 不一致（无论差几级）均进入 `conflict`
- `conflict` 和 `provisional` 的 `combined_severity` **必须为 null**
- `conflict` 状态不自动合并为确定结论

### 11.2 冲突展示规则

- 冲突条目在 UI 中显式标注为"来源不一致"
- 分别展示两个来源各自的 severity 和时间，**不混合、不选取其中之一作为结论**
- `combined_severity` 为空时 UI 显示"无合并结论"
- 不自动合并为确定结论
- 提供"重新评估"入口，引导用户通过新的评估或咨询专业人士获取确定结论
- **不建议** 用户"以更严重结果为准"作为确定结论（原"取更严重"建议已删除）

### 11.3 冲突对优先级的影响

- 冲突条目 **不进入** 普通优先级排序（`normal_candidates`）
- 冲突条目进入 `retest_required` 路径
- 理由标注"来源不一致，需重新评估或咨询专业人士"
- 不自动上调排序位次（原设计的"上调 1 位"会绕过资格规则，已修正）

---

## 12. Safety Rules

### 12.1 体态安全规则（确定性执行）

| 规则 | 执行位置 | 说明 |
| --- | --- | --- |
| 体态结果记录为"筛查信号"而非"确诊" | API response schema + UI 文案 | 所有结果页含免责声明 |
| 明确展示评估方式、时间、范围和不确定性 | 档案 API + 结果页 | 来源、时间戳、certainty、severity（可空）字段必填 |
| 自测与照片冲突时保留冲突状态 | 档案投影写入逻辑 | combined_severity 为 null，不自动合并 |
| 关联图谱只用于建议排查 | 优先级 Tool + UI 文案 | 标注"可能关联" |
| 新发严重疼痛等配置为停止条件 | 安全信号写入 + 风险分类重算（Phase 1 实现） | certainty 降级为 provisional，risk_tier 可能升级 |
| 图示展示安全姿势和停止条件 | 自测内容 schema | 新增 `correct_posture`, `common_errors`, `stop_conditions` |

### 12.2 安全信号闭环（Phase 1 实现，非推迟）

**结构化安全信号输入：**

```json
{
  "signal_type": "pain|numbness|weakness|dizziness|acute_trauma|other",
  "body_region": "head_neck|cervical|upper_back|thoracic|lower_back|shoulder_thorax|pelvis_spine|lower_limb|compound|null",
  "related_issue_id": "HN-01|null",
  "severity_hint": "mild|moderate|severe|null",
  "reported_at": "2026-07-11T...",
  "idempotency_key": "client-uuid"
}
```

> `body_region` 枚举值与 `schemas.BodyRegion` 及 `service._VALID_BODY_REGIONS` 完全一致：`head_neck / cervical / upper_back / thoracic / lower_back / shoulder_thorax / pelvis_spine / lower_limb / compound`（外加 `null`）。红旗规则按 region 限定（见 §12.6）。

> `severity_hint` 是用户主观描述，仅作为风险分类输入之一，**不单独**作为医学升级判定依据。红旗判定必须由版本化规则（§12.6）综合多个信号决定。

**版本化风险分类：**

- 风险分类规则版本化为 `risk_version`（当前 `2026-07-16-v4`）
- 规则由版本化代码或策略数据实现，不依赖 Prompt
- 每个档案条目携带当前 `risk_tier` 和 `risk_version`
- 风险分类结果：`normal` / `cautious` / `restricted` / `red_flag`
- 每条规则必须关联权威来源、版本、reviewed_at 和适用范围（详见 §12.6）

**风险作用域（global-first 算法，统一函数 `compute_profile_risk`）：**

- 写入/重算安全信号时调用统一函数 `compute_profile_risk(db, user_id, issue_id)`（`safety.py`），它 **先做全局分类**（覆盖该用户全部 active 信号）。
- 若全局分类为 `red_flag` → **短路**：对任意 `issue_id` 都返回该 red_flag（该用户所有 profile entry 的 `risk_tier` 均降为 `red_flag`，global scope）。这保证某 issue 的信号触发的红旗不会被另一个 issue 的局部重投影覆盖。
- 否则按 issue 作用域分类（仅 `related_issue_id == issue_id` 或 `related_issue_id IS NULL` 的全局信号参与），`cautious`/`restricted`/`normal` 只影响对应 issue 的 profile entry。
- 这避免了"按写入顺序跨 issue 误升级"。`service._recompute_and_upsert_profile` 与 `safety.record_safety_signal` 均复用此函数，而非各自手写风险叠加。

**安全信号生命周期：**

```text
[写入] ──→ active ──→ resolved（仅通过基于新的结构化信息重新分类）
```

| 状态 | 含义 | 对 risk_tier 的影响 |
| --- | --- | --- |
| `active` | 信号生效，参与风险分类 | 可能升级 risk_tier |
| `resolved` | 信号已通过重新分类解除 | 不再参与风险分类 |

**写入和更新入口：**

- `POST /api/v1/posture/safety-signals`（新端点）：用户报告安全信号
- `report_safety_signal` Tool（见 §10.8）：Agent 可调用的安全信号写入 Tool
- 写入后触发：
  1. 相关档案条目 certainty → `provisional`（如有 related_issue_id）
  2. 重新执行风险分类（更新 risk_tier 和 risk_version）
  3. 使旧优先级快照失效（suggestion_id 不再匹配）

**快照失效与复查提醒（invalidates_until 的作用）：**

- `invalidates_until` **仅用于** 使旧优先级快照失效和触发复查提醒
- **不用于** 自动降低 risk_tier 或自动解除红旗
- 在 `invalidates_until` 之前的所有优先级快照不可用于确认
- 到期后系统可提醒用户复查，但不改变 risk_tier

**恢复规则（在 Task 6.5 中确定，不留作 Open Question）：**

- `restricted` / `red_flag` 的解除 **只能** 通过基于新的结构化信息重新分类
- 解除路径：用户提供新的安全信号集或更新的档案 → 系统使用最新 rule_version 重新分类 → 如果新分类结果为更低风险等级，将相关 active 信号标记为 `resolved`（记录 `resolved_at`、`resolution_basis=reclassification`、`resolution_source`、`resolved_risk_version`）→ 更新档案 risk_tier
- **不得** 仅因以下原因自动恢复：
  - 时间经过（删除任何"30 天后自然恢复"的隐含语义）
  - 用户点击确认按钮
  - 用户声称已就医（口头声称不是结构化信息）
- 恢复必须基于可验证的结构化输入和版本化规则的重新计算结果
- `resolution_source` 必须记录重新分类时的档案快照、安全信号集和适用的 rule_version

**安全阻止规则：**

- `risk_tier=restricted` / `red_flag` 的条目进入 `safety_blocked` 列表，不进入普通候选；
  每个条目显式返回其 `risk_tier`，不得把 restricted 文案表述成临床红旗
- 路由优先级为 `safety_blocked` > `retest_required` > `normal_candidates`。因此安全信号导致
  条目同时变为 provisional 时，仍必须展示在安全阻断路径
- `confirm_posture_goals` 拒绝包含 restricted 条目的确认请求（409
  `restricted_blocked`），拒绝包含 red_flag 条目的确认请求（409
  `red_flag_blocked`）
- restricted 仅提供有限健康教育和专业评估建议；red_flag 停止规划并提供升级指引。
  两者都不自动转诊
- restricted/red_flag 解除必须通过上述恢复规则（新的结构化信息 + 重新分类），
  不接受"已就医"口头确认

**红旗推断禁止规则：**

- **不得** 用 `severity=severe` + 知识库存在 `red_flags` 推断用户实际出现红旗
- 红旗 **只能** 由用户报告的结构化安全信号触发，并由版本化规则综合判定（§12.6）
- 知识库的 `red_flags` 字段是科普内容，不是用户级别的红旗判定
- **不得** 仅凭未经评审的 `severity_hint` 文案制定医学升级规则

### 12.3 推荐请求安全门

`suggest_posture_priorities` 和 `confirm_posture_goals` 每次执行前必须：

1. 读取最新档案（不从缓存）
2. 读取最新 active 安全信号（resolved 信号不参与）
3. 重新执行风险分类
4. 如有新安全信号，生成新 `suggestion_id`（旧 ID 失效）
5. 重新计算优先级

`profile_version` 必须是对当前用户完整资格输入的稳定 SHA-256：按 `issue_id` 排序的档案条目
（严重度、certainty、冲突标记、risk tier/version、最新 source event 标识与时间）以及按 ID
排序的 active 安全信号（类型、作用域、severity、reported_at、invalidates_until）。时间统一
为 UTC ISO-8601；不得包含 `generated_at` 或数据库读取顺序。

`suggestion_id` 必须由 `user_id + profile_version + PRIORITY_RULE_VERSION +
RISK_VERSION + priority_context_digest` 确定性生成。`priority_context_digest`
至少覆盖知识关联数据和每条候选的 `older_than_30_days` 派生位；这样知识数据变化或评估跨过
30 天衰减边界时，即使没有数据库写入，旧 suggestion 仍会失效。相同输入和相同派生状态必须
产生相同 ID。

### 12.4 优先级资格矩阵

| 档案条目状态 | 优先级路径 | 说明 |
| --- | --- | --- |
| `risk_tier=restricted` | `safety_blocked` | 优先于 certainty 路由；阻止普通建议和目标确认 |
| `risk_tier=red_flag` | `safety_blocked` | 优先于 certainty 路由；停止规划并提供升级指引 |
| `certainty=confirmed` + severity 非 normal + `risk_tier=normal/cautious` | `normal_candidates` | 可进入普通优先级排序 |
| `certainty=confirmed` + severity=normal | 排除 | normal 不进入改善目标候选 |
| `certainty=provisional` | `retest_required` | 进入重测或专业评估路径 |
| `certainty=conflict` | `retest_required` | 进入重测或专业评估路径 |
| 未评估 | 排除 | 不进入任何候选 |

普通候选最多返回 3 条。排序采用可解释的分层分数，确保严重度不会被次级加分反超：

- severity 基础分：`severe=300`、`moderate=200`、`mild=100`
- 与另一条 confirmed 非 normal 候选存在 `weight>=0.9` 的知识关联：`+20`
- 最新投影包含两个不同 source：`+2`
- 最新 source event 距当前时间严格超过 30 天：`-1`
- 最终按 `score DESC, latest_event_at DESC, issue_id ASC` 排序，保证完全确定性

知识关联按当前知识库中的显式有向边计算；不得把关联解释成病因。知识关联内容和
`older_than_30_days` 派生位必须进入 `priority_context_digest`。

### 12.5 安全案例矩阵

`risk_rules.py` 必须覆盖以下合成安全案例，每个案例有预期 risk_tier 和行为：

| 案例 | 输入特征 | 预期 risk_tier | 预期行为 |
| --- | --- | --- | --- |
| **普通** | 无安全信号，confirmed 非 normal 评估 | normal | 进入 normal_candidates |
| **谨慎** | 单个 mild pain 信号，无其他风险 | cautious | 保守参数，仍可生成建议 |
| **受限** | 多个 moderate 信号、单个 severe 非神经症状、`acute_trauma`（任意 body_region）、或 head_neck/cervical/upper_back 区域 `severity_hint=severe` 的 `numbness`/`weakness`（**不含 dizziness**） | restricted | 进入 safety_blocked；阻止普通自动建议和目标确认，仅教育和体态辅助（product-policy，非临床主张） |
| **红旗** | Phase 1 **不自动产生** red_flag（无 clinical-source 红旗规则）。`acute_trauma` 与 severe neuro 均为 `restricted`（product-policy）。`red_flag` tier 保留给未来结构化输入。 | （Phase 1 不产生） | 当前无规则触发；若存在预留 red_flag 状态，仍必须进入 safety_blocked 并阻止确认 |
| **恶意/模糊输入** | 矛盾信号（同一时刻 pain+no_pain）、空字段、非法枚举、超长字符串 | 拒绝写入（400） | 不创建安全信号，返回校验错误 |
| **降级恢复尝试** | red_flag 状态下用户点击"已就医"按钮 | 维持 red_flag | 拒绝自动恢复，要求结构化重新分类 |

> 恶意/模糊输入案例必须验证服务端校验在写入前拒绝，不产生部分状态。

> **红旗边界（与 §12.6 一致，risk_version `2026-07-16-v4`）：** Phase 1 **没有任何自动临床红旗规则**。原 `RF-acute-trauma` / `RF-severe-neuro` 已降级为 product-policy `restricted`（`RST-acute-trauma` / `RST-severe-neuro`，无 DOI）。
> - `acute_trauma`（任意 body_region）与 head_neck/cervical/upper_back 区域 severe `numbness`/`weakness` → **restricted**（product-policy），**不**判 red_flag；
> - `dizziness` 任何严重度 **不**判 red_flag；Phase 1 未建立足以支持该临床推断的结构化输入与来源规则；
> - `severity_hint` 单独 **不**推断任何红旗（§12.2 红旗推断禁止规则）。
> `red_flag` tier 的枚举/排序/startup guard 仍保留，但 Phase 1 无规则产生它，预留给未来经核验的结构化输入。`restricted`/`cautious` 的解除仍只能通过新的结构化信息重新分类（§12.2 恢复规则）。

### 12.6 风险规则来源与许可

**规则来源要求：**

- `risk_rules.py` 的每条红旗判定必须关联结构化来源对象：
  - `source_identifier`：权威来源标识（DOI、ISBN、官方指南 URL）
  - `source_type`：引用层级（L1 机构指南 > L2 教科书 > L3 综述 > L4 RCT > L5 横断面）
  - `source_version`：具体版本（版次、年份）
  - `reviewed_at`：规则核验日期
  - `scope`：适用范围（如"成人急性创伤筛查"）
- **不得** 仅凭未经评审的 `severity_hint` 文案制定医学升级规则
- **不得** 把模糊书名字符串（如 "Magee DJ"）作为来源；必须提供 DOI/ISBN/URL

**许可要求：**

- `source.license` 必须记录来源的 **真实许可或使用限制**
- **不得** 创造类似 `CC-BY-4.0-internal-summary` 的虚构许可名称
- 如来源为开源或公有领域，记录真实许可（如 `CC-BY-4.0`、`Public Domain`）
- 如来源为商业出版物，记录 `commercial-restricted` 或具体订阅许可
- 如许可状态未知，记录 `unknown-pending-review`，并在规则上线前完成人工核验

**核验边界：**

- DOI/ISBN/URL 格式校验 **不能替代** 来源内容和许可的人工核验
- 格式校验仅确认标识符结构合法
- 内容准确性、引用恰当性和许可合规性必须由人工审查
- 规则上线前必须记录 `reviewed_at` 和审查者标识（个人开发阶段为开发者本人）

**两层来源区分（hardening v3 → v4 更新，risk_version `2026-07-16-v4`）：**

- `clinical-source`：红旗规则由经过验证的临床文献支撑（DOI/ISBN/URL）。**Phase 1 无任何 clinical-source 规则在册** —— startup guard 仍强制"任何 red_flag 规则必须携带 clinical-source provenance"，因此当前没有规则能产生 `red_flag`。原 v3 的 `RF-severe-neuro` / `RF-acute-trauma` 已在 v4 **降级为 product-policy `restricted`**（重命名为 `RST-severe-neuro` / `RST-acute-trauma`，无 DOI），原因：单人结构化自报不足以做临床红旗主张。
  - 历史背景：`RST-severe-neuro`（原 RF-severe-neuro）仅 numbness/weakness 触发；dizziness 不在此 product-policy 规则输入范围内，body_region 限定 head_neck/cervical/upper_back。
  - `RST-acute-trauma`（原 RF-acute-trauma）任意 body_region 的 `acute_trauma` 均触发 restricted（空 body_region 亦触发 restricted，不再有"仅脊柱区域"的红旗限定）。
- `product-policy`：受限规则为保守产品资质门槛，非临床主张。Phase 1 所有受限规则（含原 RF-* 降级项）均为 product-policy。

> **`red_flag` tier 状态：** 枚举、`_TIER_ORDER` 排序与 startup guard 保留，但 Phase 1 无规则产生它。`red_flag` 预留给未来经核验的 clinical-source 结构化输入；在启用前，`restricted`（product-policy）是 acute_trauma / severe neuro 的实际阻断 tier。

**reclassify_and_resolve 成功路径暂停：** 成功路径（将信号标记为 resolved）暂未启用，需要可持久化的 follow-up 结构化事件和服务端生成的 profile_version。验证/拒绝路径保持活跃。

---

### 12.7 Purge 范围与冻结补充

**3 种 purge 作用域：**

1. `account_deletion`：全量级联删除（事件、信号、档案、目标、幂等记录、OSS 对象）
2. `consent_withdrawn`：仅删除 `source='ai_photo'` 的事件及其 OSS 对象（**按 `source` 字段选取**，而非 photo_keys 是否非空）。Scoped purge 删除事件后对受影响的 `(user_id, issue_id)` 复用共享投影函数重建：先调 `service.project_profile` 从剩余 active 事件重建投影，再叠加 safety-aware 覆盖（`safety.has_active_signals_for_issue`，存在 active 信号时强制 `certainty=provisional`、`combined_severity=null`）。风险 tier 本身在写入/重算路径由统一函数 `compute_profile_risk`（global-first，见 §12.2）推导，而非手写 overlay；若某 issue 已无任何事件，则删除对应 profile entry。
3. `retention_expired`：同 consent_withdrawn，但仅选取 `created_at < 过期截止日` 的 ai_photo 事件

Scoped purge 若没有任何符合范围的 ai_photo 事件，必须返回幂等 no-op，不写 completed tombstone，也不得改动 self_test 事件或档案。

**Profile FK 解除与重建：** 在删除事件前，将任何引用被删事件的 `latest_photo_event_id` 置为 NULL。删除后从剩余 active 事件重建投影（调用 `project_profile`）。若某 issue 已无任何事件，则删除对应 profile entry。

**冻结释放条件：** 仅 `completed` 和 `cancelled` 状态释放写冻结。`failed_permanent` / `failed_decrypt` 维持冻结（需人工介入）。非终态 purge 存在时，新 `run_purge` 调用返回 409（retry 仅通过 worker claim 路径）。

**AEAD AAD 绑定：** `encrypted_object_keys` 使用 AES-256-GCM 加密，AAD = `operation_id:user_id:trigger:key_version`。错误 AAD 导致解密失败（GCM 性质），确保密文无法在不同操作间移用。

**版本化密钥环（keyring）实际行为：**

- **加密**：始终使用 `PURGE_ACTIVE_KEY_VERSION` 指向的密钥（`PURGE_ENCRYPTION_KEYS` JSON map 中的当前激活版本）；key_version 与密文一同写入 blob header（`kv_len(2B) || key_version || nonce || ciphertext+tag`）。
- **解密**：从 blob header 读取 `key_version`，从 keyring 中选取对应历史密钥；找不到该版本 → fail closed（`InvalidTag` → `failed_decrypt`，数据保留、不写 tombstone）。这使密钥轮换后旧密文仍可解密。
- **向后兼容**：当 keyring 为空（未配置 `PURGE_ENCRYPTION_KEYS`）时回退到单密钥模式（`PURGE_ENCRYPTION_KEY`），仅作为兼容路径，新部署应使用版本化 keyring。

**幂等：** 若幂等记录指向已被 purge 的信号，返回 HTTP 410（Gone）。`request_hash`（`safety._hash_request`）覆盖信号身份字段（`signal_type` / `body_region` / `related_issue_id` / `severity_hint`）**以及 `reported_at`**（UTC 归一化的 ISO-8601 字符串；服务端生成时为 `null`），**故意排除** `idempotency_key`（它是查找键，不是请求身份）。因此：相同 `idempotency_key` + 相同身份（含相同 `reported_at`）→ 重放（重新基于当前 active 信号集分类）；相同 `idempotency_key` + **不同** `reported_at`（或其它身份字段）→ 400 `idempotency_key_conflict`。非法 `reported_at`（未来 >5s 或早于一年前）在写入前被 400 拒绝，不静默回退到 `now`。

**Recoverable lease（hardening fix #4）：** 初始执行的 `freezing` / `oss_deleting` / `db_deleting` 与失败重试都设置 `next_retry_at = now + 5min`。Worker claim（`run_due_purge_jobs`）时按持久化状态映射为 `retrying_oss` 或 `retrying_db` 并刷新租约，随后提交释放 SKIP LOCKED 行。恢复执行获取同一用户级 advisory transaction lock，并在锁内刷新状态；若原 worker 仍存活，后继 worker 等待锁并在刷新后返回幂等 no-op，不重复执行 OSS。若 worker 崩溃，lease 到期后可由其他 worker按持久化阶段恢复。

---

## 13. Privacy Gate

### 13.1 Phase 1 状态

Phase 1 开始和结束时 `PHOTO_ANALYSIS_ENABLED` 保持 `false`。照片分析功能不可用，图示自测路径完整保留。

### 13.2 开关与同意的关系

- 前后端开关 **不能替代** 用户同意
- 开关是系统级授权边界，同意是用户级授权
- 即使开关开启，未取得同意也不上传

### 13.3 启用照片分析的前置条件

以下条件 **全部满足并验证通过** 后才允许启用 `PHOTO_ANALYSIS_ENABLED`：

1. 处理目的告知已实现并验证（照片用途、AI 分析范围、不用于其他目的）
2. 云端模型提供者边界已明确告知并验证（模型名称、提供方、处理位置）
3. 上传前单独同意流程已实现并验证（显式"同意上传照片用于体态分析"）
4. 保存期限已定义并验证（默认 90 天，到期实际删除原始数据）
5. 删除路径已实现并验证（用户可删除事件，实际删除原始健康数据 + 照片对象，保留 tombstone）
6. 撤回同意后的行为已实现并验证（停止新上传，触发已有数据 purge）
7. 日志脱敏规则已实现并验证（不记录照片 URL、原始模型响应）
8. 未同意时保留图示自测路径并验证（不因未同意降级核心功能）

> **重要：** 不是"8 个配置布尔值全 true 即允许"。每个条件必须有可验证的实现证据（代码路径、测试覆盖），而非配置标志位。Phase 1 中这些条件均 **未实现**，隐私门 **硬拒绝** 所有照片分析请求。启用决策需要人工审查和验证证据，不接受配置绕过。

### 13.4 数据生命周期

| 阶段 | 行为 | 数据处理 |
| --- | --- | --- |
| 上传前 | 检查同意记录，未同意不上传 | — |
| 处理中 | 调用模型，校验输出，记录审计字段 | — |
| 事件创建 | 写入 events 表，photo_keys 记录对象 key（非 URL） | 载荷完整 |
| 档案投影 | 更新 profile entries | — |
| 保留期到期（90 天） | lifecycle → `expired` → 惰性触发 `purged` | **实际删除**原始健康数据（answers、ai_response、ai_model_meta、photo_keys），保留不可关联的 tombstone receipt |
| 用户删除 | lifecycle → `purged` | **实际删除**原始健康数据，保留不可关联的 tombstone receipt |
| 照片对象删除 | 事件 purge 时同步删除 OSS 对象 | 可验证删除结果（删除响应或 404） |
| 撤回同意 | 后续上传阻止，已有事件触发 purge | 实际删除，保留 tombstone receipt |
| 用户删除账号/健康数据 | 级联清理（§6.7） | 安全信号原始载荷也必须删除或不可逆匿名化 |

**关键：** `archived`/`expired`/`purged` lifecycle 状态本身 **不是** 数据删除。`purged` 要求实际删除或不可逆匿名化原始健康内容（answers、photo_keys、ai_response、ai_model_meta）。

**Tombstone receipt 规范（详见 §6.6）：** purge 后保留的最小删除回执 **不得** 包含可关联到健康内容的字段组合（user_id + issue_id、原始 event_id、source 等）。只保留：

```json
{
  "receipt_id": "random-uuid-不可关联到原 event_id/user_id/issue_id",
  "deleted_at": "2026-07-11T...",
  "purge_reason": "user_delete|retention_expired|consent_withdrawn|account_deletion",
  "policy_version": "retention-policy-2026-07-11",
  "object_delete_status": "oss_deleted|oss_not_applicable|oss_deleted_or_not_found"
}
```

> tombstone 只表示完成态（详见 §6.6），不得使用 pending/failed 状态。

照片对象删除必须有可验证结果：OSS 删除响应成功，或对象已不存在（404）。不允许"仅标记不删除"。

**Purge 执行流程（详见 §6.7）：** 通过持久化 purge_operations 异步执行。顺序：冻结 + 收集 photo_keys → 删除 goals/profile → 删除 OSS 对象（验证成功/404）→ **立即清除 encrypted_object_keys** → 删除 events/signals/idempotency → 写 completed tombstone → completed 后清理 purge_operations 可关联字段（见 §6.7.3）。photo_keys 在 OSS 确认删除前不可被删除。

---

## 14. Failure Behavior

| 场景 | 行为 |
| --- | --- |
| AI 模型不可用 | 503 `model_unavailable`，不创建事件，不更新档案 |
| AI 输出校验失败 | 503 `schema_validation_failed`，不创建事件 |
| 照片门关闭 | 503 `photo_analysis_disabled`，不生成凭证，保留自测路径 |
| 档案投影写入失败 | 事务回滚，事件不创建（保证一致性） |
| 优先级计算无数据 | 200 `InsufficientData`（空建议列表，非错误） |
| 确认目标时优先级过期 | 409 `stale_priority`，要求重新获取 |
| 数据库连接失败 | 500，事务回滚 |
| 并发评估同一问题 | 乐观锁（`updated_at` 比较），冲突时重试投影更新 |

**核心原则：** 任何失败都不能产生半落库状态。事件和投影在同一事务中。

---

## 15. Backward Compatibility

| 组件 | 兼容策略 |
| --- | --- |
| Flutter 历史页 | history API 响应形状不变，新增 `source` 字段（原 `method` 保留为别名） |
| Flutter 评估提交 | `POST /assess` 和 `POST /assess/photo` 请求不变 |
| Flutter 结果页 | 新增 `certainty` 和 `sources` 字段，旧字段（`result`）保留 |
| OpenAPI schema | 现有 6 路由 response model 保持兼容（追加可选字段） |
| 数据库 | 重命名 migration + 数据回填，现有数据不丢失 |
| 知识库 JSON | 现有字段不变，自测字段追加可选新字段 |

---

## 16. Migration Strategy

> 本任务不创建 migration。以下为后续 Task 1 的设计约束。所有 schema 决策必须在 migration 编写前确定。

### 16.1 迁移模式：expand → dual-write/backfill → contract

采用兼容性迁移模式，确保每个 Task 合并后现有 API 都可运行：

```text
Phase A (expand, Task 1):
  0002: 重命名 posture_assessments → posture_assessment_events
        新增列（全部 nullable 或有 server_default）：source、severity、lifecycle、content_version、ai_model_meta
        创建新表：posture_profile_entries、posture_user_goals、posture_safety_signals、idempotency_records、purge_operations、posture_purge_tombstones
        创建索引和约束
        旧列 method/result 保留（不删除）

Phase B (dual-write / backfill, Task 2):
  service 同时写入 method/source、result/severity
  回填脚本：method→source、result→severity（uncertain→severity null）、lifecycle→active
  回填 posture_profile_entries：按 (user_id, issue_id) 分组，取最新 active 事件

Phase C (contract / cleanup, Task 10.5):
  0003: 收紧 NOT NULL 约束（仅 source、lifecycle 等真正必填字段）
        severity 保持 nullable（永久，因为"不确定"答案合法产生 null）
        删除旧列 method、result（确认无代码引用后）
```

**关键：** `severity` 列 **永久 nullable**，**绝不**收紧为 NOT NULL。severity 为空是合法状态（用户选择"不确定"或来源未给出确定严重度）。仅 `source`、`lifecycle` 等真正必填的字段可在回填完成后收紧。

### 16.2 过渡期处理

**旧 `method`/`result` 与新 `source`/`severity` 的过渡期：**

| 阶段 | method/result | source | severity | lifecycle | 读取策略 |
| --- | --- | --- | --- | --- | --- |
| Phase A 后 | 保留 | nullable | nullable | nullable | 读取优先 source/severity，回退 method/result |
| Phase B 后 | 保留（双写） | 完整（回填） | 完整（回填，含 null） | 完整（回填） | 读取 source/severity |
| Phase C 后 | 删除 | NOT NULL（收紧） | **nullable（永久）** | NOT NULL（收紧） | 读取 source/severity |

**`uncertain` → severity null 的映射：**

- 旧 `result='uncertain'` 回填为 `severity=null`（空表示无确定结论）
- `result='normal'` → `severity='normal'`
- `result='moderate'` → `severity='moderate'`
- `result='severe'` → `severity='severe'`

### 16.3 迁移步骤（Task 1 范围）

1. migration 0002：重命名 + expand（新增 nullable 列 + 6 个新表 + 索引）
2. migration 0002：回填 source/severity/lifecycle（在 migration 内执行，不依赖 service）
3. 回填 posture_profile_entries（在 migration 内或独立脚本）
4. **不在 Task 1 收紧 NOT NULL**（留给 Phase C 的 cleanup Task 10.5）
5. **severity 永远不收紧 NOT NULL**

### 16.4 回滚策略

migration 0002 downgrade（按 FK 依赖逆序）：
1. 删除 purge_operations 表
2. 删除 posture_purge_tombstones 表
3. 删除 idempotency_records 表
4. 删除 posture_safety_signals 表
5. 删除 posture_user_goals 表
6. 删除 posture_profile_entries 表
7. 删除 events 表的新增列（source、severity、lifecycle、content_version、ai_model_meta）
8. 重命名 posture_assessment_events 回 posture_assessments

> Phase C 的 0003 cleanup migration 有独立 downgrade：先以 nullable
> 恢复 method/result，按 `method=source`、
> `result=COALESCE(severity, 'uncertain')` 回填并重新收紧为 NOT NULL，再把
> source/lifecycle 恢复为 nullable。severity 在 0003 中仍保持 nullable，
> 无需恢复。数据库旧列删除后，对外 API 仍保留 method/result 兼容字段：
> method 是 source 的同值别名，result 由 severity 确定性映射，null 映射为
> `uncertain`。

### 16.5 测试策略

- migration 测试：离线 SQL 生成 + 校验表结构（test_migrations.py 是 **Modify**，追加 0002 和 0003 测试）
- 回填测试：合成数据回填后校验 source/severity/lifecycle/profile 正确性
- **真实 PostgreSQL upgrade/downgrade/re-upgrade 验证**（Docker postgres:16）
- 每个 migration 合并后，现有 API 必须可运行（expand 模式保证兼容）

---

## 17. Acceptance Criteria

对应 [roadmap 阶段 1 退出标准](../../product/roadmap.md#退出标准)：

| # | 退出标准 | 验收方式 |
| --- | --- | --- |
| 1 | 用户可完成至少一个部位的图示自测 | Android 手工冒烟：自测流程含扩展内容 |
| 2 | 照片和自测冲突能够正确展示 | 后端测试：冲突检测规则覆盖 + combined_severity=null + Flutter UI 测试 |
| 3 | 体态档案明确区分已评估与未评估区域 | 档案 API 测试 + Flutter 档案页 UI |
| 4 | Tool 输出全部通过类型校验和权限检查 | Tool 层单元测试 + ActorContext 注入 + 权限隔离；照片 Tool 默认 fail closed，并用合成 verifier 验证 owner 契约（不代表照片门可启用） |
| 5 | 新安全信号会使旧资格判断失效，并在继续建议前重新执行风险分类 | 安全信号写入 → certainty 降级 → suggestion_id 失效 → confirm 409 全链路测试 |

### 17.1 额外验收项

- 优先级资格矩阵正确执行（restricted/red_flag 优先进入 safety_blocked；normal 排除；
  其余 provisional/conflict 进 retest）
- 优先级建议不自动创建训练计划
- 结果页存在"生成改善计划"入口但 Phase 1 不触发
- 用户可确认主要改善目标（服务端控制 suggestion_id/profile_version）
- 自测内容包含停止条件、正确姿势、常见错误、权威来源标识
- 隐私门硬拒绝（非配置布尔值），8 个启用条件有验证检查点
- 照片 Tool 在无可信 `PhotoOwnershipVerifier` 时 fail closed；路径前缀不作为所有权证明，
  合成 verifier 测试不计入隐私门启用证据
- 8 个 Tool 有类型化契约定义和单元测试（含 confirm_posture_goals 和 report_safety_signal）
- 历史数据迁移后档案投影正确（expand/contract 模式验证）
- purged 事件实际删除原始健康数据，仅保留不含健康内容的 tombstone
- 红旗由结构化安全信号触发，不由 severity+知识库 red_flags 推断
- 风险分类版本化，重新分类使旧 suggestion_id 失效

---

## 18. Test and Evaluation Strategy

### 18.1 后端测试

| 类别 | 测试范围 |
| --- | --- |
| 事件写入 | self_test 和 ai_photo 事件正确写入 events 表；severity 可空 |
| 档案投影 | 单来源 → confirmed；多来源一致 → confirmed；多来源冲突 → conflict（combined_severity=null）；空 severity → provisional |
| 冲突检测 | 全部严重度组合的冲突规则（§11.1 表） |
| 删除/保留 | purged 实际删除原始健康数据，保留 tombstone；照片对象删除可验证 |
| 过期 | expired 惰性触发 purge |
| 档案 API | 完整档案、单问题档案、未评估区域 |
| 优先级资格 | restricted/red_flag 优先进入 safety_blocked；normal 排除；其余 provisional/conflict 进 retest；仅 confirmed+非normal+risk_tier normal/cautious 进 normal_candidates |
| 目标确认 | 1–3 个不同的当前候选；排名唯一连续；过期 suggestion_id/profile_version 返回 409；restricted/red_flag 阻止返回 409；normal/provisional/conflict/未评估/非当前候选返回 400 |
| Tool 身份 | ActorContext 注入 user_id；photo_keys 所有权校验；idempotency_key 去重；suggestion_id 服务端生成 |
| 权限隔离 | 跨用户读写拒绝 |
| 安全信号闭环 | 写入安全信号 → 相关条目 certainty→provisional → 优先级 suggestion_id 失效 → confirm 返回 409 |
| 风险分类 | 版本化；红旗由安全信号触发（非 severity+red_flags 推断）；重新分类使旧资格失效 |
| 照片门 | 关闭时全部行为；硬拒绝（非配置布尔值） |

### 18.2 Flutter 测试

| 类别 | 测试范围 |
| --- | --- |
| 档案模型 | PostureProfile 解析 |
| 冲突展示 | conflict 状态 UI 标识 |
| 优先级 | 优先级列表渲染 |
| 目标确认 | 确认交互 |
| 自测内容 | 扩展字段渲染（停止条件、正确姿势） |

### 18.3 Android 手工验证

- 登录 → 选择部位 → 完成自测 → 查看结果（含 certainty 和 source） → 查看档案（已评估/未评估） → 多问题优先级 → 确认目标 → 确认"生成改善计划"入口存在但不触发

### 18.4 评测命令

```powershell
cd backend
python -m pytest tests -q
python -m alembic upgrade head --sql

cd ..\app
flutter analyze --no-pub
flutter test --no-pub
```

---

## 19. Rollout and Rollback

### 19.1 Rollout

- 本规格仅在 `codex/phase1-task1` 分支实现
- 每个 Task 独立提交，Codex 审查后合并
- 照片分析保持默认关闭
- 合并到 main 前需通过全部验收标准

### 19.2 Rollback

- 任意 Task 失败时，回滚该 Task 对应提交
- migration 回滚按 16.2 策略执行
- 不跨 Task 混合回滚
- Flutter 回滚需确保 API 版本兼容

---

## 20. Open Questions

| # | 问题 | 暂定方向 | 需要决策的时机 |
| --- | --- | --- | --- |
| 1 | `mild` 严重度是否对 Flutter 暴露？ | events 表保留原始 mild；Phase 1 档案 API 暴露 mild；Flutter UI 渲染 mild 为"轻度" | Task 8 |
| 2 | 优先级规则的具体权重公式？ | **已决策：** severe/moderate/mild=300/200/100；强关联 +20；双来源 +2；超过 30 天 -1；再按最新事件、issue_id 稳定破同分 | Task 6 已关闭 |
| 3 | 自测内容的最小填充集（5 条）选哪些问题？ | 头部前倾、圆肩、骨盆前倾、驼背、扁平足（覆盖 4 个部位） | Task 3 |
| 4 | 照片保留期 90 天是否足够？ | 默认 90 天，用户可缩短，不可延长；到期实际 purge | Task 9 |
| 5 | `posture_user_goals` 最多确认几个目标？ | **已决策：** 每次确认 1–3 个当前候选，issue 不重复，rank 唯一且连续 1..N | Task 6 已关闭 |
| 6 | 档案过期扫描是定时任务还是惰性删除？ | Phase 1 惰性删除（读取时检查 lifecycle，触发 purge），Phase 7 定时任务 | Task 2 |

> 安全信号恢复规则（原 #7/8/9）已移至 §12.2 和 Task 6.5 中明确决定，不再作为 Open Question。决定摘要：active/resolved 生命周期；restricted/red_flag 只能通过新的结构化信息重新分类解除；不得仅因时间经过、用户确认或声称已就医自动恢复；`invalidates_until` 仅用于快照失效和复查提醒，不影响 risk_tier。
