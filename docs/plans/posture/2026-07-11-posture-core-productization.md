# 体态核心产品化实施计划

> 日期：2026-07-11
> 分支：codex/phase1-task1
> 规格：[体态核心产品化规格](../../specs/posture/2026-07-11-posture-core-productization.md)
> 安全边界：[安全边界](../../product/safety-boundaries.md)
> 路线图：[阶段 1](../../product/roadmap.md#5-阶段-1体态核心产品化)

---

## Goal

把当前体态 MVP 转化为用户可理解、结果可追踪、来源和不确定性明确，并能被后续 Agent 通过受控 Tools 调用的领域能力。

## Architecture

保持 Flutter + Riverpod 客户端和 FastAPI 模块化单体。本计划引入：

- 事件表 + 档案投影表 + 目标表 + 安全信号表 + 幂等表 + purge 任务表 + tombstone 表（方案 B）
- 内部 Tool 应用层（非独立 HTTP 路由，ActorContext 边界）
- 扩展自测内容 schema（结构化 source 对象，向后兼容）
- 隐私门检查点（硬拒绝，非配置布尔值；purge 实际删除数据）
- 安全信号闭环 + 版本化风险分类（Phase 1 实现）
- 三个正交状态维度（severity 可空、certainty、lifecycle）
- expand → dual-write/backfill → contract 迁移模式

## Safety

- 照片分析全程默认关闭（硬拒绝，非配置布尔值）
- AI 失败不降级为正常
- 测试只使用合成数据
- 冲突不自动合并（combined_severity=null）
- 关联图谱不表述为病因
- 新安全信号使旧优先级失效（Phase 1 实现，不推迟）
- 红旗由结构化安全信号触发（非 severity+red_flags 推断）
- restricted/red_flag 均阻止普通目标确认，且两者语义分开
- normal 不进入改善目标候选
- provisional/conflict 进入重测路径
- purged 实际删除原始健康数据（非仅标记）
- user_id 由服务端注入（非模型可控 Tool 参数）
- consent_record 不暴露给模型
- 服务端生成 suggestion_id/profile_version（不接受客户端自报）
- 三个状态维度正交（severity 可空、certainty、lifecycle 不混用）

## Verification

```powershell
cd backend
python -m pytest tests -q
python -m alembic upgrade head --sql

cd ..\app
flutter analyze --no-pub
flutter test --no-pub
```

## Execution Rules

- 每次只把一个 Task 交给实现者
- 每个 Task 独立提交
- 不修改 `docs/product/` 下文档（roadmap 完成状态不在本计划修改）
- 不使用真实照片、真实健康数据或真实密钥
- 不启用 `PHOTO_ANALYSIS_ENABLED`
- migration 测试通过子进程运行 `alembic ... --sql`，不依赖 conftest SQLite
- 实现者完成后由审查者检查真实 diff 并重新运行验证

## Current Baseline

```text
Python 3.9.13
Flutter 3.44.0
Dart 3.12.0
Java 21.0.10
PostgreSQL 16
Backend: 81 tests passed
Flutter: analyze passed, 7 tests passed
Alembic head: 0001_initial_schema
Photo analysis: disabled (default)
```

## Dependency Graph

```text
Task 1 (领域状态 & migration, expand)
  │
  ├──→ Task 2 (评估写入 & 档案投影, dual-write)
  │       │
  │       ├──→ Task 4 (体态档案 API)
  │       │       │
  │       │       └──→ Task 6 (优先级 & 用户确认)
  │       │
  │       └──→ Task 5 (冲突状态)
  │               │
  │               └──→ Task 6
  │
  ├──→ Task 3 (自测内容 schema + 来源核验)
  │
  ├──→ Task 6.5 (安全信号闭环 + 风险分类 + 恢复规则)  ← 依赖 Task 1
  │       │
  │       └──→ Task 7 (Tool 应用层)  ← 依赖 Task 2, 3, 4, 5, 6, 6.5
  │
  ├──→ Task 8 (Flutter UI)  ← 依赖 Task 4, 5, 6, 6.5, 7
  │
  ├──→ Task 9 (隐私门 + purge 执行流程 + tombstone)
  │
  ├──→ Task 10.5 (Migration Phase C, contract/cleanup)  ← 依赖 Task 1-9
  │       │
  │       └──→ Task 10 (最终 E2E 验收)  ← 依赖 Task 10.5
```

**无循环依赖。** Task 1 是根；Task 10 是最终验收（在 Task 10.5 contract/cleanup 之后）。

**关键依赖说明：**

- Task 6.5（安全信号 + 恢复规则）依赖 Task 1（safety_signals 表），是 Task 7（Tool 层）的前置
- Task 7 依赖 Task 2、3、4、5、6、6.5（整合所有领域能力为 Tool 契约）
- Task 8 依赖 Task 4、5、6、6.5、7（Flutter 需要所有后端 API 和 Tool 层就绪）
- Task 10.5（Phase C contract/cleanup）依赖 Task 1-9 全部完成，可先做 pre-contract 集成检查
- **Task 10（最终 E2E 验收）在 Task 10.5（Phase C）之后执行**，验证 migration 0003 后的最终交付形态
- Task 10.5 收紧 source/lifecycle 为 NOT NULL，**severity 保持永久 nullable**

---

## Task 1: 领域状态与 migration（expand 阶段）

**目标：** 创建新表结构，重命名现有表，回填档案投影。使用 expand 模式确保合并后现有 API 可运行。

**非目标：** 不修改业务逻辑（service/router）；不修改 Flutter；**不收紧 NOT NULL 约束**（留给 Phase C cleanup）；不删除旧列 method/result。

**预计修改文件：**

- Create: `backend/alembic/versions/0002_posture_core.py`
- Modify: `backend/app/posture/models.py`（重命名 model + 新增 model）
- Modify: `backend/tests/conftest.py`（适配新表）
- Modify: `backend/tests/test_migrations.py`（追加 0002 测试，非 Create）

**数据/API 契约：**

按规格 §8.5 和 §16 设计：

- `posture_assessments` → 重命名为 `posture_assessment_events`
- 追加列（**全部 nullable 或有 server_default**）：`source`（从 `method` 回填）、`severity`（从 `result` 回填，`uncertain`→null）、`lifecycle`（默认 `active`）、`content_version`、`ai_model_meta`
- **旧列 `method`/`result` 保留**（不删除，过渡期兼容）
- 新表 `posture_profile_entries`：`(user_id, issue_id)` 唯一，含 `risk_tier`、`risk_version`
- 新表 `posture_user_goals`：含 `suggestion_id`、`profile_version`、`rule_version`、`risk_version`
- 新表 `posture_safety_signals`：含 `signal_type`、`invalidates_until`、`lifecycle`(active/resolved)
- 新表 `idempotency_records`：`(user_id, operation, idempotency_key)` 唯一，副作用 Tool 的唯一幂等机制
- 新表 `posture_purge_tombstones`：不可关联的删除回执（receipt_id、deleted_at、purge_reason、policy_version、object_delete_status）
- 新表 `purge_operations`：持久化 purge job（encrypted_object_keys、状态机、重试调度）

**migration expand 模式约束（规格 §16.1 Phase A）：**

1. 重命名 + 新增 nullable 列（source、severity、lifecycle、content_version、ai_model_meta）+ 6 个新表 + 索引
2. 回填 source（method→source）、severity（result→severity，uncertain→null）、lifecycle（→active）
3. 回填 posture_profile_entries（按 user_id+issue_id 分组，取最新 active 事件）
4. **不在本 Task 收紧 NOT NULL**（source/severity 允许 null，过渡期）
5. **不删除旧列 method/result**

**安全与隐私要求：**

- migration 不含真实数据
- 回填逻辑保守：现有数据 certainty 全部设为 `confirmed`，lifecycle 为 `active`，risk_tier 为 `normal`
- uncertain → severity null（不保留为 severity 值）
- downgrade 可完全回滚（恢复 method/result 列和表结构）

**migration 和兼容策略：**

- upgrade：rename → add nullable columns → create tables → backfill
- downgrade：drop new tables → drop new columns → rename back
- 每个 Task 合并后现有 API 必须可运行（expand 模式保证兼容）
- conftest 适配新表结构（SQLite 仍用 JSON 替代 JSONB）

**后端测试：**

```powershell
cd backend
python -m alembic heads
python -m alembic upgrade head --sql
python -m alembic downgrade head:base --sql
python -m pytest tests/test_migrations.py -q
python -m pytest tests -q
```

**真实 PostgreSQL 验证（Docker postgres:16）：**

```powershell
docker run -d --name health-task1-pg -e POSTGRES_PASSWORD=... -p 55432:5432 postgres:16
# 设置 DATABASE_URL 指向 55432
python -m alembic upgrade head
python -m alembic current
python -m alembic downgrade base
python -m alembic upgrade head   # re-upgrade
# 核验 schema、索引、外键
docker stop health-task1-pg && docker rm health-task1-pg && docker volume rm ...
```

验证至少包括：

- 单一 head：`0002_posture_core`
- 离线 SQL 含 7 表（events 重命名 + 6 个新表：posture_profile_entries、posture_user_goals、posture_safety_signals、idempotency_records、posture_purge_tombstones、purge_operations）、索引、外键
- downgrade SQL 反序删除
- conftest 新表创建/删除正常
- 现有 81 测试不回归（适配新表名后，旧 method/result 列保留兼容）
- uncertain → severity null 回填正确
- 真实 PostgreSQL upgrade/downgrade/re-upgrade 闭环通过

**Flutter 测试：** 无（本任务不修改前端）

**Android 手工验证：** 无（本任务不修改业务逻辑）

**验收条件：**

- migration 离线 SQL 可生成且含全部新表和列
- 现有测试全部通过（适配后）
- 回填逻辑有单元测试
- conftest 与新表兼容
- 真实 PostgreSQL 闭环通过
- 旧列 method/result 保留（过渡期兼容）
- source/severity 为 nullable（未收紧 NOT NULL）

**Suggested commit:** `feat: add posture domain schema migration (expand phase)`

---

## Task 2: 评估写入和当前档案投影（dual-write 阶段）

**目标：** 实现事件创建 + 档案投影更新的事务性写入逻辑。采用 dual-write 确保过渡期兼容。

**非目标：** 不修改 API 路由的响应形状；不实现 Tool 层；不删除旧 method/result 列。

**预计修改文件：**

- Modify: `backend/app/posture/service.py`（事件创建 + 投影更新 + dual-write）
- Modify: `backend/app/posture/models.py`（如需调整）
- Modify: `backend/tests/test_posture.py`（适配新写入逻辑）
- Create: `backend/tests/test_posture_profile.py`

**数据/API 契约：**

- `save_self_assessment` 改为：创建 events（dual-write method/source、result/severity）→ 更新 profile entries（事务）
- `save_photo_assessment` 改为：创建 events（dual-write）→ 更新 profile entries（事务）
- severity 可空（用户选择"不确定"时 severity=null，不写入 uncertain）
- 投影更新逻辑：
  - 读取该 `(user_id, issue_id)` 的最新 active 事件（按来源分组）
  - 计算合并 severity 和 certainty（按规格 §6.4 和 §11.1 规则）
  - conflict 时 combined_severity=null
  - upsert profile entry

**dual-write 策略（规格 §16.2 Phase B）：**

- service 同时写入 method/source、result/severity
- 读取优先 source/severity，回退 method/result
- 过渡期 method 列同步写入（旧 API 兼容）

**安全与隐私要求：**

- 事件和投影在同一事务中（失败时全部回滚）
- AI 失败仍返回 503，不创建事件
- 照片门关闭时不创建照片事件
- 日志不记录照片 URL 或原始模型响应
- severity=null 正确处理（不默认为 normal）

**migration 和兼容策略：**

- 依赖 Task 1 的 migration（expand 阶段）
- history API 从 events 表读取，兼容旧响应形状（method 作为 source 别名）

**后端测试：**

验证至少包括：

- 自测事件创建后 profile 正确更新（severity 非 null）
- 自测"不确定"答案 → severity=null，certainty=provisional
- 照片事件创建后 profile 正确更新
- 同来源重新评估：旧事件 superseded，profile 更新
- 不同来源一致（severity 完全相同）：certainty=confirmed，combined_severity=该共同值
- 不同来源 severity 不一致（包括差 1 级）：certainty=conflict，**combined_severity=null**
- 任一来源 severity=null：certainty=provisional，**combined_severity=null**
- 单来源：certainty=confirmed，combined_severity=该来源 severity
- 事务失败时无半落库状态
- history API 仍返回兼容响应（method/source 双字段）
- dual-write：method 和 source 同时写入

**Flutter 测试：** 无

**Android 手工验证：** 无（API 响应兼容）

**验收条件：**

- 事件和投影写入是事务性的
- 现有 history API 兼容（method 保留为 source 别名）
- 投影逻辑有单元测试覆盖全部 severity 组合（含 null）
- conflict 时 combined_severity=null（不取更严重值）
- dual-write 正确（method/source 同时写入）

**Suggested commit:** `feat: transactional assessment events and profile projection (dual-write)`

---

## Task 3: 图示自测内容 schema

**目标：** 扩展知识库自测内容结构，定义质量门和内容版本。

**非目标：** 不生成图片；不填充全部 26 条（最小 5 条）。

**预计修改文件：**

- Modify: `backend/app/posture/data/head_neck.json`（头部前倾自测扩展）
- Modify: `backend/app/posture/data/shoulder_thorax.json`（圆肩自测扩展）
- Modify: `backend/app/posture/data/pelvis_spine.json`（骨盆前倾自测扩展）
- Modify: `backend/app/posture/data/lower_limb.json`（扁平足自测扩展）
- Modify: `backend/app/posture/data/compound.json`（驼背自测扩展）
- Modify: `backend/app/posture/schemas.py`（自测 response model 扩展）
- Modify: `backend/app/posture/knowledge.py`（内容版本和校验）
- Modify: `backend/tests/test_posture.py`（扩展自测结构校验）
- Create: `backend/tests/test_posture_knowledge.py`

**数据/API 契约：**

每个 `self_tests[]` 条目扩展为：

```json
{
  "name": "靠墙站立测试",
  "steps": ["..."],
  "positive_sign": "...",
  "image_key": "self_test_hn01_wall_stand",
  "tools_needed": "无",
  "preparation": "靠墙站立，后脑勺、上背、臀部贴墙",
  "correct_posture": "自然放松，目视前方",
  "common_errors": ["强行贴墙导致代偿", "未自然站立"],
  "stop_conditions": ["出现头晕", "出现颈部剧烈疼痛"],
  "content_version": "2026-07-11-v1",
  "source": {
    "identifier": "DOI:10.1016/j.math.2007.01.013",
    "type": "L4_RCT",
    "title": "Yip CHT et al. Man Ther 2008",
    "version": "2008-original",
    "reviewed_at": "2026-07-11",
    "scope": "成人颈部体态筛查",
    "license": "elsevier-subscription"
  }
}
```

新增字段全部可选（向后兼容）。质量门要求最小填充 5 条。

**权威来源核验要求：**

- `source.identifier` 必须是可验证的标识符（DOI、ISBN、官方指南 URL），**不接受**模糊书名字符串
- `source.type` 使用引用层级（L1-L5），对应 issue.md 的引用层级体系
- `source.version` 标明具体版本（版次、年份），不接受"最新版"等模糊表述
- `source.reviewed_at` 记录内容核验日期
- `source.scope` 标明适用范围（如"成人筛查"，区别于"青少年"或"术后"）
- `source.license` 记录内容引用和再分发许可
- 不得把 `issue.md` 中的模糊书名字符串（如 "Kendall FP et al. 2005"）直接复制为 source；必须提供 DOI 或 ISBN
- 知识库加载时校验 source.identifier 格式和存在性

**安全与隐私要求：**

- `stop_conditions` 至少含 1 条（防止用户过度强迫）
- `correct_posture` 必填（防止错误姿势导致损伤）
- `common_errors` 至少含 1 条
- 内容来源标注必须是结构化 source 对象，不接受裸字符串

**migration 和兼容策略：** 无 migration（JSON 数据）

**后端测试：**

验证至少包括：

- 扩展字段可正确序列化
- 最小 5 条问题含全部新字段（含结构化 source 对象）
- 未扩展问题仍可正常返回（可选字段）
- 知识库加载时校验内容版本存在
- 知识库加载时校验 source.identifier 格式（DOI/ISBN/URL）
- 拒绝裸字符串 source_ref（旧格式不兼容新质量门，但旧条目向后兼容）

**Flutter 测试：** 无（UI 在 Task 8）

**Android 手工验证：** 无

**验收条件：**

- 至少 5 条问题含 `preparation, correct_posture, common_errors, stop_conditions, content_version, source`（结构化对象）
- 每条 source 含 identifier、type、version、reviewed_at、scope、license
- identifier 为可验证格式（DOI/ISBN/URL），不接受模糊书名字符串
- schema 向后兼容
- 知识库校验测试通过

**Suggested commit:** `feat: expand self-test content schema with safety fields`

---

## Task 4: 体态档案 API

**目标：** 实现 `GET /profile` 和 `GET /profile/{issue_id}` 端点。

**非目标：** 不实现优先级；不修改 Flutter。

**预计修改文件：**

- Modify: `backend/app/posture/router.py`（新增 2 端点）
- Modify: `backend/app/posture/schemas.py`（新增 response models）
- Modify: `backend/app/posture/service.py`（档案查询逻辑）
- Modify: `backend/tests/test_posture.py`（档案 API 测试）
- Modify: `backend/tests/test_openapi_contracts.py`（新增端点 schema 校验）

**数据/API 契约：**

按规格第 9.2 节定义：

- `GET /api/v1/posture/profile` → `PostureProfileResponse`
- `GET /api/v1/posture/profile/{issue_id}` → `PostureProfileEntryResponse`

响应包含：evaluated_issues、unevaluated_categories、summary、sources、certainty、has_conflict

**安全与隐私要求：**

- JWT 认证必须
- 跨用户读取返回 403
- 不暴露照片 URL

**migration 和兼容策略：** 依赖 Task 1 和 2

**后端测试：**

验证至少包括：

- 无评估记录时返回空档案 + 全部未评估类别
- 有自测记录时正确返回 confirmed 条目
- 有冲突时返回 conflict 条目
- 跨用户读取返回 403
- OpenAPI 有 response schema

**Flutter 测试：** 无

**Android 手工验证：** 无

**验收条件：**

- 档案 API 返回已评估和未评估区域
- certainty 和 sources 字段正确
- OpenAPI schema 完整

**Suggested commit:** `feat: posture profile API with evaluated and unevaluated tracking`

---

## Task 5: 冲突状态

**目标：** 实现冲突检测、存储和 API 表示。

**非目标：** 不实现冲突 UI（Task 8）。

**预计修改文件：**

- Modify: `backend/app/posture/service.py`（冲突检测逻辑）
- Modify: `backend/app/posture/schemas.py`（冲突表示）
- Modify: `backend/tests/test_posture.py`（冲突场景测试）
- Create: `backend/tests/test_posture_conflict.py`

**数据/API 契约：**

按规格 §11.1 定义冲突检测规则：

- severity 排序：normal < mild < moderate < severe（severity 为空表示无确定结论）
- 所有非空来源 severity **完全一致** → confirmed，combined_severity=共同值
- 多个非空来源 severity **任意不一致**（包括差 1 级）→ conflict，combined_severity=**null**
- 任一来源 severity=null → provisional，combined_severity=**null**
- 单来源 → confirmed，combined_severity=该来源 severity
- 冲突条目 `certainty=conflict`，`has_conflict=true`，`combined_severity=null`

**安全与隐私要求：**

- 冲突不自动合并（combined_severity=null）
- 冲突问题在结果页标注"来源不一致，无合并结论"
- 冲突问题进入 retest_required 路径（不进入普通优先级排序）

**migration 和兼容策略：** 依赖 Task 1 和 2

**后端测试：**

验证至少包括全部 severity 组合（含 null）：

- normal + normal → confirmed, combined=normal
- mild + mild → confirmed, combined=mild
- moderate + moderate → confirmed, combined=moderate
- severe + severe → confirmed, combined=severe
- mild + moderate → **conflict**, combined=**null**（差 1 级也冲突）
- moderate + severe → **conflict**, combined=**null**（差 1 级也冲突）
- normal + mild → **conflict**, combined=**null**
- normal + moderate → conflict, combined=**null**
- normal + severe → conflict, combined=**null**
- mild + severe → conflict, combined=**null**
- null + moderate → provisional, combined=**null**
- moderate + null → provisional, combined=**null**
- null + null → provisional, combined=**null**
- 单来源（仅自测）→ confirmed, combined=该来源 severity
- 删除某来源后从剩余重建

**Flutter 测试：** 无

**Android 手工验证：** 无

**验收条件：**

- 冲突检测规则全部实现且有测试
- conflict 时 combined_severity=null（代码中无自动取更严重值路径）
- 冲突状态在档案 API 中正确表示
- 不存在自动合并冲突的代码路径

**Suggested commit:** `feat: explicit conflict detection and state for multi-source assessments`

---

## Task 6: 多问题优先级和用户确认

**目标：** 实现确定性优先级引擎和目标确认端点。

**非目标：** 不实现训练计划生成；不实现 Agent 对话。

**预计修改文件：**

- Create: `backend/app/posture/priority.py`（优先级引擎）
- Modify: `backend/app/posture/router.py`（2 新端点）
- Modify: `backend/app/posture/schemas.py`（优先级和目标 models）
- Modify: `backend/app/posture/service.py`（目标写入）
- Create: `backend/tests/test_posture_priority.py`
- Modify: `backend/tests/test_openapi_contracts.py`（新增路由的 schema/ref 契约）

`PostureUserGoal` 已由 Task 1 完整创建；本 Task 不修改 `models.py`，不新增 migration。
Task 6 不抽取或重构 `safety.py` 的既有幂等流程，也不新建通用 `idempotency.py`。
`confirm_goals` 在 service 内按统一表和统一错误语义实现领域专用的最小路径；是否抽公共 helper
留到 Task 7 后的独立重构，并以现有 safety 全量回归为前提。

**数据/API 契约：**

按规格 §9.2 和 §12.4 定义：

- `GET /api/v1/posture/priorities` → `PrioritySuggestionsResponse`（含 suggestion_id、profile_version、rule_version、risk_version、normal_candidates、retest_required、safety_blocked）
- `POST /api/v1/posture/goals/confirm` → `ConfirmedGoalsResponse`

**优先级资格规则（确定性，规格 §12.4）：**

- `risk_tier=restricted/red_flag` → `safety_blocked`，且该路由优先于 certainty
- `certainty=confirmed` + severity 非 normal + `risk_tier=normal/cautious` → `normal_candidates`
- `certainty=confirmed` + severity=normal → **排除**（normal 不进入改善目标候选）
- `certainty=provisional` → `retest_required`（重测或专业评估路径）
- `certainty=conflict` → `retest_required`
- 未评估 → 排除

**服务端控制值（规格 §10.0）：**

- suggestion_id、profile_version、rule_version、risk_version 由服务端生成
- 客户端 **不接受** 自报 priority_context_snapshot
- goals/confirm 使用服务端生成的值做乐观锁校验

**优先级权重（仅 normal_candidates 排序）：**

1. 严重度基础分：severe=300、moderate=200、mild=100
2. 关联强度加分：与另一条 confirmed 非 normal 候选存在显式有向边且 weight≥0.9，+20
3. 来源多样性加分：两个不同 source，+2
4. 时间衰减：超过 30 天的评估 -1 分

按 `score DESC, latest_event_at DESC, issue_id ASC` 排序，取前 3 条并标注理由。
严重度百位分保证次级加分不能反超一个严重度等级。关联只表示可能共存，不解释为病因。

**版本与失效：**

- `PRIORITY_RULE_VERSION = "2026-07-17-v1"`，独立于
  `risk_rules.RISK_VERSION = "2026-07-16-v4"`，不得混用
- `profile_version` 为当前用户全部档案资格字段 + active 安全信号的 canonical JSON
  SHA-256；排序稳定、时间统一 UTC，不包含 generated_at
- `suggestion_id` 由 user_id、profile_version、两个规则版本和
  `priority_context_digest` 确定性生成
- `priority_context_digest` 至少覆盖当前知识关联和每条候选的
  `older_than_30_days` 派生位，确保知识变化或跨过 30 天边界会使旧 suggestion 失效

**安全与隐私要求：**

- 优先级是建议，不自动创建计划
- 关联图谱标注"可能关联"
- restricted/red_flag 进入 safety_blocked，并显式返回 risk_tier；restricted 不得使用
  临床红旗文案
- normal 不进入候选
- 非安全阻断条目的 provisional/conflict 进入 retest_required
- 每次调用重新计算（安全门）：重读档案 + 安全信号 + 重新风险分类
- 确认时执行资格前置检查（规格 §10.7）：重读档案 → 重新风险分类 →
  校验 suggestion_id/profile_version → 拒绝 restricted/red_flag/provisional/conflict/
  normal/未评估/非当前候选
- 过期 suggestion_id/profile_version 返回 409 stale_priority
- restricted 阻止返回 409 restricted_blocked
- 红旗阻止返回 409 red_flag_blocked
- goals 必须为当前 normal_candidates 中 1–3 个不同 issue，priority_rank 唯一且连续 1..N
- 幂等记录 result_ref 指向确认批次锚点 goal ID；同批 goals 使用同一 confirmed_at，
  重放恢复首次完整批次，即使后来已 supersede

**migration 和兼容策略：** 依赖 Task 1（goals 表）

**后端测试：**

验证至少包括：

- 无评估数据返回空建议
- 单 confirmed+非normal 问题返回单条 normal_candidate
- normal 问题排除（不进入候选）
- provisional 问题进入 retest_required
- conflict 问题进入 retest_required
- restricted/red_flag 优先进入 safety_blocked，且 risk_tier 和文案正确
- 多问题正确排序（权重公式）
- 关联强度加分正确
- 双来源加分、超过 30 天衰减和稳定破同分正确
- 跨过 30 天边界后旧 suggestion_id 失效
- 确认目标成功（suggestion_id/profile_version 匹配）
- goals 为空、超过 3 个、issue 重复、rank 重复/不连续、非当前候选均返回 400
- 确认 normal 问题返回 400 invalid_goal
- 确认 provisional/conflict 问题返回 400
- 确认 restricted 问题返回 409 restricted_blocked
- 确认红旗问题返回 409 red_flag_blocked
- suggestion_id 不匹配返回 409 stale_priority
- profile_version 不匹配返回 409 stale_priority
- 新评估后旧 suggestion_id 失效
- 新安全信号后旧 suggestion_id 失效
- 不接受客户端自报 priority_context_snapshot
- 相同幂等 key + 相同请求返回首次确认批次且不重复写；相同 key + 不同请求返回 400
- 幂等请求哈希按 `priority_rank` 规范化 goals；锚点 goal 已被 purge 时重放返回 410
- 新端点 OpenAPI request/response component ref 存在

**Flutter 测试：** 无

**Android 手工验证：** 无

**验收条件：**

- 优先级引擎是确定性的（相同输入相同 suggestion_id）
- 资格矩阵正确执行（restricted/red_flag 安全阻断优先；normal/provisional/conflict 路由正确）
- 不自动创建训练计划
- 安全门（重新计算 + 重新风险分类）有测试
- 确认端点使用服务端生成的 suggestion_id/profile_version
- restricted/red_flag 均阻止目标确认，且错误语义不混淆

**Suggested commit:** `feat: deterministic priority engine with qualification rules and user goal confirmation`

---

## Task 6.5: 安全信号闭环与版本化风险分类

> **状态：实现完成、review 修复中**（非最终完成）。代码（`safety.py` / `risk_rules.py` / 端点）已实现并有测试覆盖；`reclassify_and_resolve` 成功路径暂未启用（需可持久化的 follow-up 结构化事件 + 服务端生成的 `profile_version`）；review 修复仍在进行，验收/合并状态以 `docs/agent/ACTIVE_TASKS.md` 为准。

**目标：** 实现结构化安全信号输入、版本化风险分类、写入入口和资格失效闭环。Phase 1 实现，不推迟。

**非目标：** 不实现签到集成（Phase 2）；不实现完整受限模式策略（Phase 3）；不实现 Agent 对话。

**预计修改文件：**

- Create: `backend/app/posture/safety.py`（安全信号写入 + 风险分类引擎）
- Create: `backend/app/posture/risk_rules.py`（版本化风险分类规则）
- Modify: `backend/app/posture/router.py`（`POST /api/v1/posture/safety-signals` 端点）
- Modify: `backend/app/posture/schemas.py`（SafetySignalRequest、RiskClassification 响应 models）
- Modify: `backend/app/posture/service.py`（安全信号写入触发 certainty 降级 + 风险分类更新）
- Modify: `backend/app/posture/models.py`（PostureSafetySignal model 在 Task 1 migration 中建表）
- Create: `backend/tests/test_posture_safety.py`

**数据/API 契约：**

按规格 §12.2 定义：

- `POST /api/v1/posture/safety-signals` → 写入安全信号，触发 certainty 降级 + 风险分类更新
- `report_safety_signal` Tool（供 Agent 调用）

**结构化安全信号输入（规格 §12.2）：**

```json
{
  "signal_type": "pain|numbness|weakness|dizziness|acute_trauma|other",
  "body_region": "head_neck|...|null",
  "related_issue_id": "HN-01|null",
  "severity_hint": "mild|moderate|severe|null",
  "idempotency_key": "client-uuid"
}
```

**版本化风险分类（规格 §12.2 和 §12.6）：**

- 规则版本化为 `risk_version`（当前 `2026-07-16-v4`）
- 规则由版本化代码实现（`risk_rules.py`），不依赖 Prompt
- 风险分类结果：`normal` / `cautious` / `restricted` / `red_flag`
- 每个档案条目携带当前 `risk_tier` 和 `risk_version`
- **每条红旗判定必须关联结构化来源**（source_identifier/DOI/ISBN/URL、source_type、source_version、reviewed_at、scope）
- **不得** 仅凭未经评审的 severity_hint 文案制定医学升级规则
- `source.license` 必须记录真实许可或使用限制，**不得** 创造虚构许可名称（如 `CC-BY-4.0-internal-summary`）
- DOI/ISBN/URL 格式校验 **不能替代** 来源内容和许可的人工核验

**失效规则（规格 §12.2）：**

- 新疼痛、麻木、无力、眩晕、急性创伤信号 → 立即使旧 suggestion_id 和优先级快照失效
- 信号设置 `invalidates_until`（用于快照失效和复查提醒，**不用于自动降低 risk_tier**）
- 红旗判定由版本化规则综合多个信号决定（§12.6 案例矩阵），**不仅** 凭单个 severity_hint

**安全信号生命周期（规格 §12.2）：**

- `active` / `resolved` 生命周期
- `resolved` 字段：`resolved_at`、`resolution_basis=reclassification`、`resolution_source`、`resolved_risk_version`

**恢复规则（规格 §12.2，在 Task 6.5 中确定，不留作 Open Question）：**

- `restricted` / `red_flag` 的解除 **只能** 通过基于新的结构化信息重新分类
- 解除路径：用户提供新的安全信号集或更新的档案 → 系统使用最新 rule_version 重新分类 → 如果新分类结果为更低风险等级，将相关 active 信号标记为 `resolved`（记录 resolved_at、resolution_basis=reclassification、resolution_source、resolved_risk_version）→ 更新档案 risk_tier
- **不得** 仅因以下原因自动恢复：时间经过（删除"30 天后自然恢复"语义）、用户点击确认、用户声称已就医
- 恢复必须基于可验证的结构化输入和版本化规则的重新计算结果

**红旗推断禁止（规格 §12.2）：**

- **不得** 用 severity=severe + 知识库存在 red_flags 推断用户红旗
- 红旗 **只能** 由用户报告的结构化安全信号触发，并由版本化规则综合判定
- 知识库 red_flags 字段是科普内容

**安全案例矩阵（规格 §12.5）：**

覆盖普通、谨慎、受限、红旗、恶意/模糊输入和降级恢复尝试案例。

**安全与隐私要求：**

- 安全信号是敏感健康数据，按规格 §13 处理
- 测试只使用合成安全信号
- 日志不记录安全信号原始内容
- 用户删除账号/健康数据时，安全信号原始载荷也必须删除或不可逆匿名化（保留最小删除回执，详见规格 §6.5 和 §13.4）
- idempotency_key 防重复写入

**migration 和兼容策略：** posture_safety_signals 表在 Task 1 migration 中创建

**后端测试：**

验证至少包括：

- 写入 pain 信号 → 相关问题 certainty→provisional（如有 related_issue_id）
- 写入 pain 信号 → risk_tier 可能升级
- 写入 acute_trauma 信号 → risk_tier=restricted（`RST-acute-trauma`，product-policy，**任意 body_region** 均触发受限；空/肢端区域同样 restricted，见 §12.6。Phase 1 不产生 red_flag）
- 写入 severe numbness/weakness（head_neck/cervical/upper_back）→ restricted（`RST-severe-neuro`）；**dizziness 不触发** restricted 之外的升级
- 写入多个信号触发受限（规则综合判定，非仅 severity_hint）
- 写入信号后旧 suggestion_id 失效（priorities 返回新 ID）
- 写入信号后 confirm_posture_goals 返回 409 stale_priority
- 受限（restricted）信号进入 `safety_blocked` 并阻止普通自动建议/目标确认；
  red_flag 使用同一分区但保留独立风险等级与升级文案
- 验证 **不使用** severity=severe + 知识库 red_flags 推断红旗（红旗只能由结构化信号 + 版化规则综合判定）
- **恢复测试**：restricted 状态下用户点击"已就医" → 维持 restricted（拒绝自动恢复）
- **恢复测试**：restricted 状态下用户提供新结构化信息 → 重新分类 → 信号 resolved → risk_tier 降级
- **恢复测试**：30 天后 restricted 不自动恢复（删除时间经过自动恢复语义）
- 恶意/模糊输入（矛盾信号、空字段、非法枚举）→ 400 拒绝写入
- idempotency_key 去重
- risk_version 正确记录
- resolved_at、resolution_basis、resolution_source、resolved_risk_version 正确记录

**Flutter 测试：** 无

**Android 手工验证：** 无

**验收条件：**

- 安全信号写入端点实现且有测试
- 风险分类版本化（risk_version，当前 `2026-07-16-v4`）
- Phase 1 无 clinical-source 红旗规则；所有受限规则为 product-policy，每条 product-policy 规则有 policy_id/version/rationale/owner（无虚构 DOI）
- 新安全信号使旧 suggestion_id 失效（全链路测试）
- 红旗不由 severity+知识库 red_flags 推断（仅结构化信号 + 版本化规则）；Phase 1 实际阻断 tier 为 restricted，red_flag tier 保留
- 受限（restricted）阻止普通自动建议/目标确认路径
- **恢复规则实现**：仅通过新的结构化信息重新分类解除 restricted/red_flag，拒绝时间经过/用户确认/声称已就医自动恢复
- 安全案例矩阵全部通过（普通/谨慎/受限/恶意/降级恢复；红旗 tier Phase 1 不产生）
- report_safety_signal Tool 契约定义（见 Task 7）

**Suggested commit:** `feat: safety signal closed loop with versioned risk classification and recovery rules`

---

## Task 7: 体态 Tool 应用层

**目标：** 实现 8 个类型化 Tool 函数（含 confirm_posture_goals 和 report_safety_signal），供 REST API 和未来 Agent 共用。

**非目标：** 不创建独立 Tool HTTP 路由；不实现 Agent orchestrator。

**依赖与并行约束：** Task 7 的写实现必须基于已验证并合入的 Task 6 head；两者都修改
`router.py`，不得并行实现。Task 6 期间仅允许 Task 7 只读审计，不提前写
`actor_context.py` / `tool_contracts.py`，避免契约漂移。

**预计修改文件：**

- Create: `backend/app/posture/tools.py`（8 个 Tool 函数）
- Create: `backend/app/posture/tool_contracts.py`（仅 Tool 业务 I/O TypedDict / Pydantic 契约）
- Create: `backend/app/core/actor_context.py`（服务端 ActorContext 定义）
- Create: `backend/app/upload/ownership.py`（PhotoOwnershipVerifier 协议 + Phase 1 fail-closed 默认实现）
- Modify: `backend/app/posture/service.py`（仅新增照片分析的统一幂等编排；Tool 不直接 ORM）
- Modify: `backend/app/posture/schemas.py`（照片请求显式要求客户端 `idempotency_key`）
- Modify: `backend/app/posture/router.py`（REST 端点改为调用 Tool 函数，注入 ActorContext）
- Create: `backend/tests/test_posture_tools.py`

**数据/API 契约：**

按规格 §10 定义 8 个 Tool：

- `list_posture_issues(category) -> List[IssueSummary]`
- `get_posture_issue(issue_id) -> IssueDetail`
- `guide_posture_self_test(actor, issue_id) -> SelfTestGuide`
- `analyze_posture_photo(actor, issue_id, photo_keys, idempotency_key) -> PhotoAssessmentResult`
- `get_posture_profile(actor, issue_id?) -> PostureProfile`
- `suggest_posture_priorities(actor) -> PrioritySuggestions`
- `confirm_posture_goals(actor, suggestion_id, profile_version, goals, idempotency_key) -> ConfirmedGoals`
- `report_safety_signal(actor, signal, idempotency_key) -> SafetySignalResult`

**ActorContext 边界（规格 §10.0）：**

- `ActorContext` 由服务端从 JWT 会话注入（user_id、consent_record、risk_context）
- user_id **不是** 模型可控 Tool 参数
- consent_record 从服务端隐私上下文读取，**不暴露给模型**
- photo_keys 所有权校验通过 `PhotoOwnershipVerifier`；路径前缀只做格式预检，不作为证明
- 有副作用 Tool 使用 idempotency_key（统一幂等表，规格 §8.5 idempotency_records）
- suggest_posture_priorities 返回服务端生成的 suggestion_id、profile_version、rule_version、risk_version
- confirm_posture_goals 不接受客户端自报 priority_context_snapshot
- report_safety_signal 写入触发风险分类重算

**幂等性（规格 §8.5 idempotency_records）：**

- 统一幂等表：`(user_id, operation, idempotency_key)` 唯一
- 覆盖 analyze_photo、confirm_goals、report_safety_signal
- 相同 key + 相同 request_hash → 返回首次结果
- 相同 key + **不同** request_hash → 拒绝（400 `idempotency_key_conflict`）

**安全与隐私要求：**

- 每个 Tool 检查当前用户授权（从 actor 提取，非参数）
- Tool 不直接执行 SQL
- Tool 不绕过照片门
- 照片门关闭时 `analyze_posture_photo` 返回 `PhotoAnalysisDisabled`（硬拒绝，非配置布尔值）
- `suggest_posture_priorities` 每次重新计算 + 重新风险分类（安全门）
- `confirm_posture_goals` 执行前重新风险分类，restricted/red_flag 均阻止
- `report_safety_signal` 写入触发风险分类重算
- 审计字段不含照片 URL、原始模型响应或健康档案
- photo_keys 所有权校验（PhotoOwnershipDenied 错误）
- 无可信 ownership backend 时返回 PhotoOwnershipUnavailable；Phase 1 隐私门应更早
  PhotoAnalysisDisabled，且不得探测对象、创建幂等记录/事件或调用模型
- idempotency_key 去重验证（统一幂等表）
- 照片分析的幂等检查必须在模型调用前完成，由 service 层持有用户事务锁并编排
  `检查/重放 -> 模型调用 -> 评估事件/档案投影/idempotency_record`；Tool 层不得为此直接查询
  `idempotency_records`。Phase 1 不抽取或重构 `safety.py` / `confirm_posture_goals` 的既有幂等流程

**migration 和兼容策略：** idempotency_records 表在 Task 1 migration 中创建。不创建新 migration。

**后端测试：**

验证至少包括：

- 每个 Tool 的输入输出类型校验（8 个 Tool）
- ActorContext 注入正确（user_id 不在模型参数中）
- 未认证调用拒绝
- 跨用户调用拒绝
- 合成 `PhotoOwnershipVerifier` 覆盖 owned / cross-user / unavailable；fake 只验证 Tool 契约，
  不作为生产照片门启用证据
- 默认 verifier fail closed；不得通过解析 `posture_photos/{user_id}/...` 前缀声称对象已上传或归属
- idempotency_key 重复调用返回首次结果（不重复副作用）
- **idempotency_key 相同但 request_hash 不同 → 拒绝（400）**
- **统一幂等表覆盖 analyze_photo、confirm_goals、report_safety_signal**
- idempotency_records 数据最小化：不存储完整健康响应（仅 result_ref 引用 ID）
- 幂等记录仍存在但 result_ref 已悬空时重放返回 410 Gone；完整隐私清除删除关联幂等记录，
  不保留可关联健康元数据
- 过期 idempotency_records 清理后，相同 key 可重新使用
- 照片门关闭时 `analyze_posture_photo` 硬拒绝
- `suggest_posture_priorities` 安全门（重新计算 + 重新风险分类）
- `confirm_posture_goals` 资格前置检查 + restricted/red_flag 阻止
- `report_safety_signal` 写入触发风险分类重算
- suggestion_id/profile_version 服务端生成
- 不接受客户端 priority_context_snapshot
- REST 端点调用 Tool 后响应兼容

**Flutter 测试：** 无

**Android 手工验证：** REST API 行为不变

**验收条件：**

- 8 个 Tool 有类型化契约定义（含 confirm_posture_goals 和 report_safety_signal）
- ActorContext 正确注入（user_id 非模型参数）
- photo_keys owner verifier 契约有合成测试，默认运行时 fail closed；真实 provider-backed
  ownership 实现仍是照片隐私门未来启用的前置，不在 Phase 1 伪造
- 统一幂等表有测试（覆盖 3 个副作用 Tool，相同 key 不同 hash 拒绝）
- REST 端点和 Tool 共享同一逻辑
- 权限、照片门和安全门检查有测试
- 现有 API 响应兼容

**Suggested commit:** `feat: typed posture tool application layer with actor context boundary`

---

## Task 8: Flutter 体态档案与结果 UI

**目标：** Flutter 端展示档案、冲突、优先级和目标确认。

**非目标：** 不实现训练计划 UI；不实现 Agent 聊天 UI。

**依赖与并行约束：** 基于已合入 Task 7 的主分支最新 HEAD。现有
`starlit-galaxy-rolls-21h55` worktree 含未提交 UI 改动，不得读取为当前产品事实、复制、清理
或覆盖。主分支已经存在 `/profile/posture` 路由和本地状态占位档案页，Task 8 复用路由并把
占位页改为服务端档案；不修改与 starlit 重叠的 `app.dart`、`core/constants.dart`、
`core/theme.dart`、home/issues/widgets 文件。

Task 8 拆分为以下依赖有向图：

```text
Task 8A（history source 后端兼容补丁） ──┐
                                           ├──→ Task 8C（Flutter 页面集成与验收）
Task 8B（Flutter 模型/Provider/幂等基础） ┘
```

Task 8A 与 8B 文件范围不重叠，可以从同一已登记 base 并行；Task 8C 必须等待二者均经
Codex review、提交并合入后再开始。实现 Agent 不修改 `ACTIVE_TASKS.md`，状态由协调者维护，
避免并行任务争用治理总账。

### Task 8A: history source 后端兼容补丁

**目标：** 补齐规格 §9.1/§15 已要求但当前实现遗漏的 history `source` 字段，同时保留
旧 `method` 字段作为兼容别名。

**预计修改文件：**

- Modify: `backend/app/posture/schemas.py`
- Modify: `backend/app/posture/service.py`
- Modify: `backend/tests/test_posture.py`
- Modify: `backend/tests/test_posture_profile.py`（更新旧 shape 兼容断言）
- Modify: `backend/tests/test_openapi_contracts.py`（`source` 为可选追加字段）

**契约与验收：**

- `GET /api/v1/posture/history` 每条记录同时返回 `source` 与 `method`
- `source` 来自事件记录的真实 `source`；`method` 保持兼容且值与 `source` 一致
- 不新增 migration，不改变事件写入、档案投影、风险分类或其他 API
- 覆盖 self_test/photo 的序列化、空历史、鉴权和跨用户隔离；只用合成数据
- 相关测试与后端全量测试通过

### Task 8B: Flutter 模型、Provider 与幂等基础

**目标：** 建立 Task 8C 页面所需的类型模型、API 状态层和稳定客户端幂等键，不修改页面。

**预计修改文件：**

- Create: `app/lib/core/idempotency_key.dart`
- Create: `app/lib/models/posture_profile.dart`
- Create: `app/lib/models/priority_suggestion.dart`
- Create: `app/lib/models/safety_signal.dart`
- Modify: `app/lib/models/assessment.dart`（解析 history source，兼容 method）
- Modify: `app/lib/models/issue.dart`（解析扩展自测字段）
- Modify: `app/lib/providers/assessment_provider.dart`
- Create: `app/lib/providers/posture_profile_provider.dart`
- Modify: `app/pubspec.yaml` / `app/pubspec.lock`（将已锁定的 `uuid` 声明为直接依赖）
- Create: `app/test/core/idempotency_key_test.dart`
- Create: `app/test/models/posture_profile_test.dart`
- Create: `app/test/models/priority_suggestion_test.dart`
- Create: `app/test/models/safety_signal_test.dart`
- Create: `app/test/providers/posture_profile_provider_test.dart`

**契约与验收：**

- 为 profile、profile detail、priorities、confirm goals、safety signals 提供类型化调用和
  loading/error/data 状态；有效空档案与网络/解析失败必须可区分
- 未知关键枚举或缺失必需字段不得默认成 `normal`、空档案或“无问题”
- `combined_severity` 保持可空；conflict/provisional/restricted/red_flag 信息不丢失
- 照片分析、目标确认和安全信号上报使用客户端 UUID v4；一次用户动作及其网络重试复用同一
  key，新用户动作生成新 key
- `409 stale_priority` 清除旧选择/旧建议状态并刷新 priorities，不自动重放确认
- 安全信号成功后刷新 profile 与 priorities，不继续暴露旧 suggestion
- 不修改任何 screen、route、theme、home/issues/widgets 文件
- `dart format`、`flutter analyze`、相关测试和 Flutter 全量测试通过

### Task 8C: Flutter 页面集成与统一验收

**依赖：** Task 8A、Task 8B 均已验证并合入。

**预计修改文件：**

- Modify: `app/lib/screens/profile/posture_profile_screen.dart`（替换本地状态占位实现）
- Modify: `app/lib/screens/result/result_screen.dart`（certainty + source 标注）
- Modify: `app/lib/screens/test/self_test_screen.dart`（扩展自测内容渲染）
- Modify: `app/lib/screens/history/history_screen.dart`（source 字段）
- Create: `app/lib/widgets/posture_status_badge.dart`
- Create: `app/test/screens/posture_profile_test.dart`

**数据/API 契约：**

Flutter 模型对应后端新 API：

- `PostureProfile`：evaluated_issues、unevaluated_categories、summary
- `PostureProfileEntry`：issue_id、combined_severity（**可空**）、certainty、sources、has_conflict、risk_tier
- `PrioritySuggestions`：suggestion_id、profile_version、rule_version、risk_version、normal_candidates、retest_required、safety_blocked
- `PrioritySuggestion`：issue_id、suggested_rank、reasons、association_weight
- `SafetySignal`：signal_type、body_region、related_issue_id、severity_hint
- 照片分析、目标确认和安全信号上报必须发送客户端生成的 1–64 字符
  `idempotency_key`；一次用户动作/网络重试复用同一 key，不以时间戳充当唯一性保证
- 目标确认只提交当前 `normal_candidates` 中 1–3 个不同 issue，rank 连续为 `1..N`
- `409 stale_priority` 不自动重放确认：刷新 priorities，提示用户重新核对和选择

**安全与隐私要求：**

- 冲突状态显式标注"来源不一致，无合并结论"（combined_severity=null 时）
- 未评估区域引导前往自测
- 优先级建议标注"仅供参考"
- restricted 显示有限教育/专业评估提示；red_flag 显示停止规划和升级指引
- provisional 条目标注"建议重新评估"
- 安全信号报告入口（Phase 1 最小实现）
- 安全信号上报成功后刷新档案和 priorities；不得继续展示或提交旧 suggestion_id
- 结果页保留免责声明
- combined_severity 为空时 UI 显示"无合并结论"
- 网络/解析失败显示明确错误和重试，不得渲染成空档案、normal 或“无问题”

**migration 和兼容策略：** 无（前端）

**后端测试：** 无

**Flutter 测试：**

验证至少包括：

- `PostureProfile` 模型解析正确（含 combined_severity 可空）
- `PrioritySuggestions` 模型解析正确（含 suggestion_id 等服务端控制值）
- 档案页渲染已评估和未评估区域
- 冲突条目有冲突标识（combined_severity=null 显示"无合并结论"）
- provisional 条目标注
- restricted/red_flag 按各自 risk_tier 渲染不同安全提示
- 优先级列表渲染（normal_candidates、retest_required、safety_blocked 分区）
- 目标确认交互（回传 suggestion_id/profile_version）
- 目标确认重复点击不重复提交；stale_priority 刷新后要求用户重新确认
- 安全信号上报使用结构化枚举，成功后旧优先级失效并刷新
- 自测扩展字段（停止条件、正确姿势）渲染

**Android 手工验证：**

```text
登录 → 选择部位 → 完成自测（含安全提示） → 查看结果（certainty + source + severity 可空）
→ 查看档案（已评估/未评估，combined_severity 可空） → 多问题优先级（三路分区） → 确认目标
→ 报告安全信号 → 验证优先级失效
→ 确认"生成改善计划"入口存在但不触发
```

**验收条件：**

- 档案页区分已评估/未评估
- 冲突条目有显式 UI 标识（combined_severity=null）
- 优先级建议三路分区（normal_candidates、retest_required、safety_blocked）
- 目标确认回传服务端生成的 suggestion_id/profile_version
- 安全信号报告入口可用
- 自测页展示停止条件和正确姿势
- flutter analyze 无问题
- flutter test 通过

**Suggested commit:** `feat: flutter posture profile, conflict display, and priority confirmation UI`

---

## Task 9: 隐私门实现

> **状态：实现完成、review 修复中**（非最终完成）。隐私门（`privacy_gate.py`，Phase 1 硬拒绝）与 purge 执行流程（`purge.py` 状态机、tombstone、加密 keyring、retry lease）已实现并有测试覆盖；review 修复仍在进行，验收/合并状态以 `docs/agent/ACTIVE_TASKS.md` 为准。

**目标：** 实现照片隐私门的检查点和启用条件验证逻辑。

**非目标：** 不启用照片分析；不实现真实 STS；不实现同意 UX（Phase 1 仅预留检查点）。

**预计修改文件：**

- Create: `backend/app/core/privacy_gate.py`（隐私门检查器）
- Modify: `backend/app/core/config.py`（隐私门配置项）
- Modify: `backend/app/posture/tools.py`（`analyze_posture_photo` 集成）
- Modify: `backend/app/upload/router.py`（集成隐私门）
- Create: `backend/tests/test_privacy_gate.py`
- Modify: `backend/.env.example`（隐私门配置占位）

**数据/API 契约：**

隐私门检查器定义 8 个启用条件（规格 §13.3），每个条件需要 **可验证的实现证据**（非配置布尔值）：

1. 处理目的告知已实现并验证
2. 云端模型提供者边界已明确告知并验证
3. 上传前单独同意流程已实现并验证
4. 保存期限已定义并验证（默认 90 天，到期实际删除原始数据）
5. 删除路径已实现并验证（实际删除原始健康数据 + 照片对象，保留 tombstone）
6. 撤回同意行为已实现并验证（触发已有数据 purge）
7. 日志脱敏规则已实现并验证
8. 未同意时保留自测路径并验证

**Phase 1 硬拒绝（规格 §13.3）：**

- Phase 1 中 8 个条件均 **未实现**
- 隐私门 **硬拒绝** 所有照片分析请求（非配置布尔值全 true 即允许）
- 每个条件需要人工审查和验证证据（代码路径、测试覆盖），不接受配置绕过
- 启用决策需要单独 Task 和人工审查

新增配置项：

```text
PHOTO_RETENTION_DAYS=90
PHOTO_CONSENT_REQUIRED=true
```

**purge 实现要求（规格 §6.6 和 §13.4）：**

- 用户删除或保留期到期后，**实际删除**原始健康数据（answers、ai_response、ai_model_meta、photo_keys）
- **不保留**可关联到健康内容的字段组合（user_id + issue_id、原始 event_id、source 等）
- 仅保留不可还原健康内容的最小删除回执（receipt_id 随机新 UUID、deleted_at、purge_reason、policy_version、object_delete_status）
- 照片对象删除必须有可验证结果（OSS 删除响应或 404）
- `archived`/`expired`/`purged` lifecycle 状态本身 **不是** 数据删除
- purge 需要实际删除或不可逆匿名化

**级联清理顺序（规格 §6.7）：**

用户删除账号或全部健康数据时，按以下顺序执行（每步失败进入重试队列，最长 7 天，清理操作幂等）：

1. 冻结写入 + 创建 purge_operations + 收集 photo_keys（从事件行复制到 encrypted_object_keys）
2. 删除 goals → profile_entries
3. 删除 OSS 对象并验证（成功响应或 404）
4. **立即清除** purge_operations.encrypted_object_keys（OSS 全部确认后，在 DB 健康数据删除之前）
5. 删除 assessment_events → safety_signals → idempotency_records
6. 写 completed tombstone（仅完成态，见 §6.6）
7. completed 后清理 purge_operations 可关联字段（删除行或 scrub user_id/target_event_ids/target_signal_ids，见 §6.7.3）
8. 账号删除场景再处理 user 记录（此时所有 FK 引用的健康数据已删除，不受 NOT NULL FK 阻塞）

> **注意：** "assessment_events（purge）" 指删除事件行，不是先于照片删除。photo_keys 必须在 OSS 确认删除后才可从数据库中消失。

**安全与隐私要求：**

- 隐私门是最终授权边界，不可被客户端绕过
- 即使 `PHOTO_ANALYSIS_ENABLED=true`，隐私门条件未全部满足时仍拒绝
- 非"8 个布尔值全 true 即允许"的假实现
- 日志不记录照片 URL
- 未同意时保留自测路径
- purge 实际删除数据（非仅标记）
- tombstone 不含可关联健康内容的字段组合
- 安全信号原始载荷在账号删除时也必须删除或不可逆匿名化

**migration 和兼容策略：** 复用 Task 1 已创建的 purge_operations、posture_purge_tombstones 和 idempotency_records 表。不创建新 migration。

**后端测试：**

验证至少包括：

- 隐私门默认硬拒绝（Phase 1）
- 8 个条件逐个检查（未实现时全部拒绝）
- 非"布尔值全 true 即允许"（验证条件需要实现证据）
- 日志脱敏验证（照片 key 记录，URL 不记录）
- 保留期限配置读取
- purge 实际删除原始健康数据（answers/ai_response/photo_keys 清空）
- purge 后 tombstone **不含** user_id、issue_id、source、原始 event_id
- purge 后 tombstone **仅含** receipt_id（随机新 UUID）、deleted_at、purge_reason、policy_version、object_delete_status
- tombstone 的 object_delete_status **只含完成态**（`oss_deleted` / `oss_not_applicable` / `oss_deleted_or_not_found`），**不含** `oss_failed_retry_pending` 或任何 pending/failed 状态
- purge 失败时 **不写 tombstone**；purge_operations 保持 failed 状态并告警，直到重试成功后才写 completed tombstone
- 照片对象删除可验证（OSS 响应或 404）
- 级联清理顺序正确：goals → profile → OSS 删除（验证）→ 清除 encrypted_object_keys → events/signals/idempotency → tombstone → completed 后清理 purge_operations 可关联字段 → 账号删除再处理 user
- 级联清理失败时进入重试队列
- 清理操作幂等（重复执行不报错）
- 安全信号原始载荷在账号删除时也 purge
- purge 执行流程验证：冻结→收集 photo_keys→删除 goals/profile→删除 OSS（验证成功/404）→**立即清除 encrypted_object_keys**→删除 events/signals/idempotency→写 completed tombstone→completed 后清理 purge_operations 可关联字段
- **顺序约束**：encrypted_object_keys 清除 **必须在** DB 健康数据行删除之前（OSS 确认后立即清除 key，再删 DB 行）
- photo_keys 在 OSS 确认删除前不可被数据库删除（purge_operations 保护 encrypted_object_keys）
- OSS 删除失败时 purge_operations 进入 failed_oss_retry，encrypted_object_keys 保留（pending/failed 状态保留可关联字段用于重试）
- 超过最大重试次数时 purge_operations 进入 failed_permanent 并告警（**不写 tombstone**，不对外声明已完全删除）
- encrypted_object_keys 不进入日志或 tombstone
- OSS 结果仅持久化聚合完成态，不得把原始对象 key 作为 JSON 字段名或值明文写入 purge_operations
- purge_operations.encrypted_object_keys 在 OSS 全部确认删除后立即清除（在 DB 删除之前）
- **completed 后 purge_operations 无可关联字段残留**：completed 后 user_id、target_event_ids、target_signal_ids、encrypted_object_keys 全部为 null 或行已删除（见规格 §6.7.3）
- **completed 后无 user_id、event_id、signal_id、photo key 残留**（purge_operations 行或 scrub 后）
- purge_operations.user_id FK 为 nullable（ON DELETE SET NULL），账号删除时不受 NOT NULL FK 阻塞
- idempotency_records 到期清理（expires_at 后删除，非仅标记）
- 已 purge 数据的 idempotency result_ref 查询返回 410 Gone
- 用户删除账号时 idempotency_records 级联删除
- scoped purge 无符合范围的 ai_photo 事件时返回幂等 no-op，不写 tombstone
- 初始 `freezing` / `oss_deleting` / `db_deleting` 阶段崩溃后可由 lease worker 恢复；原 worker 仍存活时不得重复删除 OSS

**Flutter 测试：** 无

**Android 手工验证：** 照片入口仍不可用

**验收条件：**

- 8 个启用条件在代码中有检查点（每个需验证证据）
- 隐私门硬拒绝（Phase 1，非配置布尔值）
- 检查逻辑有单元测试
- purge 实际删除原始健康数据
- tombstone 不含可关联健康内容的字段组合（仅 receipt_id 等不可关联字段）
- 照片对象删除可验证
- 级联清理顺序和失败重试有测试
- 安全信号 purge 覆盖
- purge 执行流程正确（photo_keys 在 OSS 确认删除前不可被删除；encrypted_object_keys 在 OSS 确认后、DB 删除前清除）
- tombstone 只含完成态（无 pending/failed 状态）；purge 失败不写 tombstone
- purge_operations completed 后无可关联字段残留（user_id/event_id/signal_id/photo key 为 null 或行已删除）
- purge_operations.user_id FK 为 nullable，账号删除不被 NOT NULL FK 阻塞
- purge_operations 状态机有测试（pending→oss_deleting→db_deleting→completed，含失败重试路径）
- idempotency_records 纳入隐私删除（账号删除、同意撤回、过期清理）
- `.env.example` 含新配置占位

**Suggested commit:** `feat: privacy gate checkpoints with anonymized tombstone and cascade cleanup`

---

## Task 10.5: Migration Phase C（contract / cleanup）

**目标：** 收紧 NOT NULL 约束（仅 source/lifecycle 等真正必填字段，severity 永久 nullable），删除旧列 method/result 和 dual-write 逻辑。在最终 E2E 验收（Task 10）之前完成。

**非目标：** **不收紧 severity 为 NOT NULL**（永久 nullable）；不新增业务功能。

**前置条件：** Task 1-9 全部完成且通过 pre-contract 集成检查；确认无代码引用旧 method/result 列。

**预计修改文件：**

- Create: `backend/alembic/versions/0003_posture_contract.py`
- Modify: `backend/app/posture/models.py`（移除 method/result 列定义）
- Modify: `backend/app/posture/service.py`（移除数据库旧列读写；对外 API 的 method/result 兼容字段由 source/severity 确定性映射）
- Modify: `backend/tests/test_migrations.py`（追加 0003 测试）
- Modify: `backend/tests/test_posture.py`（Phase C 后 history 兼容字段与 NOT NULL 契约）
- Modify: `backend/tests/test_posture_profile.py`（移除 dual-write 旧列断言，保留 source/severity 投影断言）
- Modify: `backend/tests/test_pg_integration.py`（事件 fixture 移除旧列）
- Modify: `backend/tests/test_posture_safety.py`（事件 fixture 移除旧列）
- Modify: `backend/tests/test_privacy_gate.py`（事件 fixture 移除旧列）
- Modify: `docs/agent/ACTIVE_TASKS.md`（仅更新本 Task 状态）

`backend/tests/conftest.py` 当前没有 method/result 旧列适配，不因历史计划描述做无关修改。

**数据/API 契约：**

- migration 0003：
  - 收紧 `source` 为 NOT NULL（回填完成后）
  - 收紧 `lifecycle` 为 NOT NULL（回填完成后）
  - **severity 保持 nullable**（永久，"不确定"答案合法产生 null）
  - 删除旧列 `method`、`result`（确认无代码引用后）
- 数据库旧列删除不等于删除 API 兼容字段：
  - history 继续返回 `method`，其值恒等于 `source`
  - assessment/history 继续返回 `result`，由 `severity` 映射；`severity=null` 映射为 `uncertain`
  - 不允许 schemas/router/Flutter 因本迁移发生破坏性契约变化

**安全与隐私要求：**

- 删除旧列前确认无 ORM 构造、查询、回放或 fixture 引用
  `PostureAssessmentEvent.method/result`；grep 命中的 API response 字段必须逐项区分，不能机械删除
- severity 保持 nullable 不影响数据完整性（null 是合法值）
- downgrade 可恢复旧列和 nullable 状态

**migration 和兼容策略（规格 §16.1 Phase C）：**

- upgrade：先验证 source/lifecycle 无 null → 收紧 source/lifecycle NOT NULL → 删除 method/result 列
- downgrade：先以 nullable 恢复 method/result 列 → `method=source`、
  `result=COALESCE(severity, 'uncertain')` 回填 → 收紧 method/result NOT NULL →
  恢复 source/lifecycle nullable
- severity 在 0003 中仍保持 nullable，无需变更

**后端测试：**

```powershell
cd backend
python -m alembic heads
python -m alembic upgrade head --sql
python -m alembic downgrade head:base --sql
python -m pytest tests/test_migrations.py -q
python -m pytest tests -q
```

**真实 PostgreSQL 验证（Docker postgres:16）：**

```powershell
# upgrade 到 0003 → 核验 source/lifecycle NOT NULL、severity nullable、method/result 已删除
# downgrade 0003 → 核验 method/result 恢复、source/lifecycle 恢复 nullable
# re-upgrade 0003 → 核验一致
```

验证至少包括：

- 单一 head：`0003_posture_contract`
- source、lifecycle 为 NOT NULL
- **severity 仍为 nullable**（不收紧）
- method、result 列已删除
- downgrade 恢复 method/result NOT NULL 列并按确定性映射保留数据，同时恢复 source/lifecycle nullable
- 现有测试不回归（移除 dual-write 后）
- 真实 PostgreSQL upgrade/downgrade/re-upgrade 闭环通过
- 真实 PostgreSQL 合成行覆盖普通 severity 与 null severity，在 downgrade/re-upgrade 后语义不丢失
- grep 确认无代码引用旧数据库 method/result 列；API 兼容字段仍保留

**Flutter 测试：** 无

**Android 手工验证：** REST API 行为不变

**验收条件：**

- source、lifecycle 收紧为 NOT NULL
- **severity 保持 nullable**（永久）
- method、result 旧列删除
- dual-write 逻辑移除（service 仅使用 source/severity）
- 真实 PostgreSQL upgrade/downgrade/re-upgrade 闭环通过
- 完整后端测试通过

**Suggested commit:** `feat: posture migration phase c contract and cleanup`

---

## Task 10: Phase 1 最终 E2E 验收（Phase C 后）

**目标：** 在 migration 0003（Phase C contract/cleanup）完成、旧列删除、dual-write 移除后，对最终交付形态执行完整端到端验收。

**非目标：** 不新增功能；不修改 roadmap 完成状态。**此为 Phase C 后的最终验收，不是 pre-contract 检查。**

**前置条件：** Task 10.5（Phase C contract/cleanup）已完成。

**预计修改文件：**

- Create: `backend/tests/test_phase1_e2e.py`（端到端集成测试）
- Modify: `backend/tests/test_openapi_contracts.py`（全路由校验）
- Modify: `docs/specs/posture/2026-07-11-posture-core-productization.md`（验证证据）
- Modify: `docs/plans/posture/2026-07-11-posture-core-productization.md`（标记完成）

**数据/API 契约：** 无新契约

**安全与隐私要求：**

- 全部测试使用合成数据
- 照片分析全程关闭
- 冲突不自动合并
- 新安全信号使优先级失效

**migration 和兼容策略：** 无（Phase C 已在 Task 10.5 完成）

**后端测试：**

端到端集成测试覆盖完整流程：

```text
  → 验证 migration head 为 0003
  → 验证 source/lifecycle 为 NOT NULL，severity 为 nullable
  → 验证旧列 method/result 已删除
  → 真实 PostgreSQL upgrade/downgrade/re-upgrade（0001→0002→0003）
合成用户注册
  → 浏览问题列表
  → 查看问题详情（含扩展自测 + 结构化 source）
  → 完成自测（事件 + 档案）
  → 查看档案（已评估/未评估，combined_severity 可空）
  → 完成第二个问题自测
  → 产生冲突场景（combined_severity=null）
  → 获取优先级建议（三路分区：normal_candidates、retest_required、safety_blocked）
  → 确认目标（回传 suggestion_id/profile_version）
  → 验证"生成计划"前置条件
  → 报告安全信号（pain）
  → 验证相关条目 certainty→provisional
  → 验证旧 suggestion_id 失效
  → 验证 confirm 返回 409 stale_priority
  → 报告 acute_trauma 安全信号
  → 验证 risk_tier=restricted（product-policy，Phase 1 不自动产生 red_flag）
  → 验证条目优先进入 safety_blocked，不因 provisional 降级到 retest_required
  → 删除评估事件
  → 验证原始健康数据已删除（仅保留 tombstone）
  → purge 执行流程验证（photo_keys 保护→OSS 删除验证→立即清除 encrypted_object_keys→DB 删除→completed tombstone→completed 后清理 purge_operations 可关联字段）
  → idempotency 过期清理和隐私删除验证
  → 照片分析返回 503（门禁硬拒绝）
```

**Flutter 测试：**

- 全部 widget 测试通过
- analyze 无问题

**Android 手工验证：**

```text
登录 → 选择部位 → 完成自测（含安全提示） → 查看结果（certainty + source）
→ 查看档案（已评估/未评估） → 多问题优先级 → 确认目标
→ 确认"生成改善计划"入口存在但不触发
→ 照片入口不可用
```

**验收条件（对应规格第 17 节）：**

> 验收证据记录于规格 §17.2。E2E 测试：`backend/tests/test_phase1_e2e.py`（6 tests）；OpenAPI 全路由校验：`backend/tests/test_openapi_contracts.py`（40 tests）。验证日期：2026-07-22，PostgreSQL 16.14。

1. 用户可完成至少一个部位的图示自测 ✓（E2E test_e2e_full_user_journey step 6）
2. 照片和自测冲突能够正确展示 ✓（E2E step 8：conflict, combined_severity=null）
3. 体态档案明确区分已评估与未评估区域 ✓（E2E step 7）
4. Tool 输出全部通过类型校验和权限检查 ✓（Task 7 已验证，69 passed）
5. 新安全信号使旧资格判断失效 ✓（E2E step 12：409 stale_priority）
6. 优先级不自动创建训练计划 ✓（E2E step 10：can_generate_plan=True 但无计划生成）
7. 结果页有"生成改善计划"入口但不触发 ✓（E2E step 10：can_generate_plan=True）
8. 自测内容含停止条件、正确姿势 ✓（E2E step 5：detail 验证扩展字段）
9. 隐私门 8 个条件有检查点 ✓（E2E step 16：/assess/photo 503）
10. 8 个 Tool 有类型化契约 ✓（Task 7 已验证）
11. migration head 为 0003，旧列已删除 ✓（E2E test_e2e_migration_head_is_0003 + test_e2e_schema_*）
12. purge 执行流程正确（photo_keys 保护；encrypted_object_keys 在 OSS 确认后、DB 删除前清除；completed 后无可关联字段残留）✓（E2E test_e2e_purge_full_flow）
13. idempotency 过期复用与隐私删除覆盖 ✓（E2E test_e2e_idempotency_expiry_and_purge_coverage）

**Suggested commit:** `test: phase one final e2e acceptance after migration phase c`

---

## Review And Handoff

每个 Task 完成后：

1. 审查者检查任务范围和真实 diff
2. 先做规格符合性审查，再做工程质量与安全审查
3. 实现者修复 P1/P2 findings
4. 审查者重新运行该任务验证
5. 用户确认后再提交，并进入下一个 Task

Phase 1 未完成前，不开始 Phase 2、训练计划、Agent 对话或饮食推荐。

Phase 1 全部 Task 完成后，由用户决定是否更新 roadmap 的 Phase 1 完成状态。本计划不修改 roadmap。
