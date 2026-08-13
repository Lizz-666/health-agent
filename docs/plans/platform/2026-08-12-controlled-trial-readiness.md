# Phase 9 Android 小范围受控试用候选版实施计划

**Goal:** 在不使用真实数据、生产凭据、live AI 或照片的前提下，形成可审查、
可回滚的 Android 小范围受控试用候选版。

**Spec:** `docs/specs/platform/2026-08-12-controlled-trial-readiness.md`

**Architecture:** 邀请资格、稳定账号、credential provider、设备登记和会话分离；
生产意图配置 fail closed；隐私、安全、中文化、可访问性和运维证据分 Gate 建立。

**Safety:** 所有测试/评测只用合成数据；live AI 和照片保持关闭；Codex 内部预审
不替代法律、健康专业或独立安全意见；Gate 4 不授权真实试用、部署或公开发布。

**Verification:** 每个 Gate 绑定候选 exact SHA、本地命令、findings-first 冷审和
GitHub CI。rebase、冲突修复或实质改动后旧证据失效。

## 1. 基线与分支

- 唯一业务基线：`2ae03345a93d8cc22d0e47fcac415411798df48b`。
- 基线关系要求：`HEAD`、`codex/phase8-flutter-driver` 和
  `origin/codex/phase8-flutter-driver` 在开始时均指向该 SHA，merge-base 等于该 SHA。
- Gate 0 分支：`codex/phase9-controlled-trial`。
- 后续实现分支只能从 Gate 0 exact closure SHA 创建，不能从 `main`、旧 Phase
  worktree 或其他分支开始。
- 同一 Task 一个写入者。高风险身份、隐私、安全、迁移、跨端契约和最终 E2E 由
  Codex 直接完成或接管。

## 2. Gate 0: 决策与契约关闭

### Task 0: 只读审计、规格、ADR、计划和任务总账

**Writer:** Codex only.

**Allowed files:**

- `docs/specs/platform/2026-08-12-controlled-trial-readiness.md`
- `docs/plans/platform/2026-08-12-controlled-trial-readiness.md`
- `docs/adr/0009-invited-trial-authentication-boundary.md`
- `docs/product/roadmap.md`
- `docs/product/public-release-gate.md`
- `docs/agent/ACTIVE_TASKS.md`
- `docs/reports/phase9-gate0-review-2026-08-12.md`

**Forbidden:** `app/`、`backend/`、`scripts/`、`.github/` 和所有业务代码、迁移、
依赖或生成文件。

**Behavior:** 固化地区/受众/渠道/责任、合成数据边界、邀请账号模型、外部审查
缺失、Gate 0-4、单写入者批次、allowlist、命令、CI 与退出标准。不得把绿色 CI
写作试用或发布批准。

**Acceptance:**

- Phase 8 closure 关系和 CI 事实可追溯；
- 用户五项决策完整记录，文档间无冲突；
- findings-first 冷审无未解决 P0/P1/P2；
- 文档候选 `git diff --check`、链接和状态一致性通过；
- commit/push 后 Fast/Flutter/Full/Phase8 在同一 exact SHA 通过，或明确记录未获
  外部写入授权而尚未运行。

**Local commands:**

```powershell
git status --short --branch
git rev-parse HEAD
git merge-base HEAD 2ae03345a93d8cc22d0e47fcac415411798df48b
git diff --check
python scripts/verify.py fast
Set-Location app
flutter analyze
flutter test
```

## 3. Gate 1: 身份与候选配置硬门

### Task 1: 邀请、独立账号、设备登记、会话和 provider 边界

**Writer:** Codex only.

**Expected allowlist:**

- `backend/app/auth/**`
- `backend/app/core/config.py`
- `backend/app/core/security.py`
- `backend/app/db/**` 及一个必要的 auth migration
- `backend/tests/test_auth*.py`
- `backend/tests/test_pg_integration.py` 中只与该迁移直接相关的部分
- `app/lib/core/constants.dart`
- `app/lib/screens/auth/**`
- `app/lib/providers/auth_provider.dart` 及直接 auth models/services/tests
- 当前 Phase 9 spec/plan/ADR/Gate 1 report

开始实现前以现行文件重新冻结精确路径；不存在的路径不能据此新建跨域抽象。

**Contract:**

- invitation、account、credential、device enrollment、session 分离；
- 邀请码高熵、digest 存储、一次性、过期、撤销、原子消费；
- 每个账号独立，最多一个活动设备，运营者辅助换机；
- 密码/本地凭据使用审查过的慢哈希；access 短时效，refresh 可轮换和撤销；
- issuer/audience/expiry/secret 均强制配置，候选配置拒绝默认 secret 和 dev-login；
- provider 错误映射稳定，不泄露账号存在性，不回退到开发登录；
- API 与 Flutter 只消费 provider-neutral contract，为未来短信 adapter 保留边界。

**Required tests:** 邀请猜测/重放/并发、过期/撤销、账号枚举、暴力限制、设备冲突、
token 过期/撤销/轮换、跨账号 IDOR、候选配置启动拒绝、日志脱敏、SQLite/PG 迁移与
回滚/恢复计划。

**Acceptance commands:**

```powershell
python -m pytest backend/tests/test_auth*.py -q
python scripts/verify.py full
Set-Location app
flutter analyze
flutter test test/screens/login_screen_test.dart
flutter test
```

**CI:** Fast/Flutter/Full，严格 PostgreSQL 零条件 skip；同一 exact SHA。

**Accepted evidence (2026-08-12):** 实现
`407ce9ce5de3f53140db8660505e8c15cf94e628` 已经 Codex findings-first 冷审，
P0/P1/P2 为零；本地 Full 为 `1731 passed / 0 failed / 38` 个条件 PG skips，严格
exact-SHA CI run `31569996543` 为 `1769 passed / 0 failed / 0 skipped`、PostgreSQL
`30/30`，Fast/Flutter/Full/Phase8 全通过。Gate 1 accepted，不构成真实试用或发布授权。

**Rollback:** 禁用候选模式并撤销所有邀请/refresh/device enrollment；不得通过回滚
恢复开发登录、默认 secret 或已确认的鉴权漏洞。迁移必须有恢复说明。

## 4. Gate 2: 隐私、安全、供应链与运维

### Task 2: 数据生命周期和运行准备证据

**Writer:** Codex only.

**Expected allowlist:**

- `docs/security/**`、`docs/privacy/**`、`docs/operations/**`（按现行结构创建最小文件）
- `backend/app/core/**` 中 secret、日志、错误和可观测性窄改动
- 当前各域 purge/deletion service 与其测试，仅限审计证明的缺口
- `backend/tests/test_privacy_gate.py`
- `backend/tests/test_phase8_deletion.py`
- `backend/tests/test_logging*.py`、`backend/tests/test_security*.py` 等窄测试
- `backend/requirements.txt` 和锁/审计文件仅在确认依赖变更必要时
- `.github/workflows/ci.yml` 与 `scripts/verify.py` 的供应链/Phase9 验证扩展
- 当前 Phase 9 spec/plan/Gate 2 report

**Deliverables:**

- 数据清单、数据流图、目的/最小化/位置/访问/保存/删除/备份矩阵；
- 同意、撤回、导出、删除和备份恢复语义；
- STRIDE 或等价威胁模型及风险处置记录；
- 依赖、license、漏洞、Action pin、最小权限与 secret 扫描；
- 脱敏日志/指标设计和 synthetic 验证；
- 事故响应、账号/邀请紧急禁用、回滚、备份恢复演练 runbook；
- 外部审查登记为 `not obtained`，阻止真实健康数据试用和公开发布。

**Acceptance commands:**

```powershell
python -m pytest backend/tests/test_privacy_gate.py backend/tests/test_phase8_deletion.py -q
python scripts/verify.py full
Set-Location app
flutter analyze
flutter test
```

增加依赖审计和 secret scan 时，命令必须固定版本、输出摘要且不上传仓库内容到未经
批准的第三方服务。

**CI:** Fast/Flutter/Full/Phase8 + 新增非 live Phase9 security/privacy job；exact SHA。

**Rollback:** 可单独撤销监控集成；不能回滚到记录敏感正文、删除不完整或备份复活
已删除账号的状态。此类问题只能修复前进或缩窄产品声明。

## 5. Gate 3: 中文化、可访问性与 Android 可靠性

### Task 3A: Flutter 中文化与可访问性局部批次

**Writer:** 一个 OpenCode + Claude 会话；Codex 冻结合约、真实 diff 审查、修复接管
和验收。OpenCode 写入时 Codex 不并行修改同一文件。

**Dependency:** Gate 2 accepted exact SHA；Codex 提示词必须列出每个文件、文本契约、
Semantics 要求、测试和禁止项。

**Provisional allowlist:**

- 经 `rg` 审计确认仍含英文/机器值的具体 `app/lib/screens/**` 文件
- 对应 `app/lib/models/**` 显示映射文件
- 对应 `app/test/**` widget tests
- 最多一个局部 `app/lib/core/` localization/accessibility helper，只有消除真实重复时
- 不允许 backend、migration、auth、health/safety rule、provider、CI、依赖或文档

**Behavior:** 用户可见核心流程中文化；安全未知 fail closed；Semantics 标签/状态/错误
播报；200% 大字不阻断；颜色非唯一状态表达；不改变领域状态机或健康规则。

**OpenCode commands:**

```powershell
Set-Location app
flutter analyze
flutter test <prompt 中的目标测试>
flutter test
```

### Task 3B: Android 设备/网络/时区/升级回滚验证

**Writer:** Codex only.

**Expected allowlist:**

- `app/integration_test/phase9_*`
- 必要的稳定 UI keys/semantics 及对应测试
- `scripts/phase9.py` 或对现有 Phase 8 runner 的最小可审查扩展
- 合成 Phase 9 fixtures/evals
- `.github/workflows/ci.yml` Phase9 非 live job
- Android 运行矩阵、升级/回滚 runbook 和 Gate 3 report

**Matrix:** 当前 API 34 + 一个较低受支持 API；正常/慢网/断网/服务不可达；token 过期；
跨午夜/周界 `Asia/Shanghai`；重复提交；客户端/服务端不兼容；升级和可恢复回滚。

**Gate 3B frozen execution contract (2026-08-13):**

- 设备矩阵固定为 Android API 34 和 API 28；两者均高于应用 `minSdk 24`。API 34
  执行完整受控账号、慢响应、撤销/过期、版本不兼容和不可达回放；API 28 至少执行
  受控账号核心流程、后台恢复与不可达回放。设备证据必须记录 emulator ID、API、ABI、
  exact SHA 和每条用例计数，不提交 APK、截图、数据库或日志产物。
- 候选 Flutter 请求统一发送稳定 Android platform/version-code 头。只有
  `controlled_trial_candidate` 服务端强制校验；缺失、格式错误、低于最小版本或高于
  当前兼容上限均在进入业务路由前返回 `426` 稳定中文码，不产生领域写入。客户端收到
  `426` 后清除 token 和全部用户态并阻断继续认证，不显示原始响应。
- 401 并发请求共享一次 refresh；refresh 旋转失败、重放、会话撤销或账号/设备失效时
  清除 token 及全部用户域缓存，不把失败转换为成功。原请求仅在 refresh 成功后重放一次；
  业务写请求继续复用原 idempotency key。
- Phase 9 synthetic server 只绑定 loopback、只使用可丢弃 SQLite 和固定合成账号/邀请码/
  凭据；runner 输出仅 exact SHA、稳定 checkpoint/transitions 和计数。覆盖激活、邀请码
  重放、设备冲突、refresh rotation/replay、慢响应后显式重试、撤销后拒绝、版本矩阵和
  零意外写入。CI 不接触 live provider、照片、生产 secret 或网络服务。
- `Asia/Shanghai` 以注入 UTC 时钟验证跨 `23:59:59 -> 00:00:00` 日界和周日到周一周界；
  客户端日期不覆盖服务端推导。迁移仅在可丢弃 PostgreSQL 演练 `0013 -> head` 数据保留
  和服务关闭状态的 downgrade/re-upgrade；运行中不得 downgrade 到移除同意/删除标记的
  `0013`，应用回滚只能回到仍兼容 `0014/head` 的版本。

**Exact allowlist:**

- production: `backend/app/main.py`, `backend/app/core/config.py`,
  `backend/app/core/compatibility.py`, `app/lib/core/constants.dart`,
  `app/lib/core/api_client.dart`, `app/lib/providers/auth_provider.dart`,
  `app/lib/screens/auth/login_screen.dart`;
- tests/harness: `backend/tests/phase8_app_factory.py`, `backend/tests/phase9_*`,
  `backend/tests/test_client_compatibility.py`, `backend/tests/test_trial_privacy.py`,
  `app/test/core/api_client_test.dart`, `app/test/providers/auth_session_reset_test.dart`,
  `app/test/screens/login_screen_test.dart`, `app/integration_test/phase9_*`,
  `scripts/phase9.py`, `scripts/verify.py`, `.github/workflows/ci.yml`;
- evidence: this plan, `docs/agent/ACTIVE_TASKS.md`, Phase 9 operations/Android matrix and
  Gate 3 report only. No migration, domain model, health/safety policy, dependency, live/photo or
  unrelated UI change is allowed without a findings-first scope amendment.

**Acceptance commands:**

```powershell
python scripts/phase9.py verify --surface all
python scripts/verify.py full
Set-Location app
flutter analyze
flutter test
flutter test integration_test/phase9_controlled_trial_test.dart -d <emulator>
```

命令和文件名在 Gate 2 冻结后可按真实实现调整，但必须在计划和报告中同步。

**Execution status (2026-08-13):** 本地接受实现
`9c5670714fd113061948c1daf2315f3e2dbde9e1` 已完成 HTTP `11/11`、时区 `2/2`、
Flutter `531/531`、PostgreSQL `33/33`，并在 Android API 34/API 28 各完成主路径 `4/4`
与不可达 `1/1`。实现 exact-SHA CI `31674663884` 为 Fast `1052/0/14`、Flutter `531`、
Full `1816/0/0`、PostgreSQL `33/33`、Phase 8 `11/11 + 13/13`、Phase 9 security `19/19`、
reliability `11/11 + 2/2`，全部成功。P0/P1/P2 为零，Task 3B 接受；本结论必须由承载此
状态的 closure exact-SHA CI 再自证，失败即失效。

## 6. Gate 4: 集成候选退出

### Task 4: 最终 E2E、冷审、CI 与退出审计

**Writer:** Codex only.

**Allowed files:** Phase 9 E2E/runner/CI、审计发现必须修复的现行实现文件、Phase 9
spec/plan/ADR/roadmap/ACTIVE_TASKS、运维与隐私证据、Gate 4/退出报告。任何扩围先在
报告中证明 finding 与文件关系。

**Required evidence:**

- synthetic invitation -> independent account -> device enrollment -> login/session -> core product journey;
- revocation、账号禁用、换机恢复、跨账号隔离、服务不可达和重复操作；
- 删除/备份恢复、日志/截图/artifact 敏感信息扫描；
- 中文、TalkBack、200% 大字、对比度、API 设备矩阵和时区边界；
- threat model 和 incident tabletop 的关闭状态；
- full backend/PG、Flutter、Phase8 regression、Phase9 synthetic E2E 和 Android；
- exact-SHA GitHub Fast/Flutter/Full/Phase8/Phase9 全绿；
- findings-first 冷审 P0/P1/P2 为零。

**Exit wording:** 只允许“Phase 9 Android 小范围受控试用候选版工程验收通过”。报告
必须继续声明：外部法律/隐私、健康专业和独立安全审查未取得；真实数据、真实测试者、
生产凭据、live AI、照片、部署、分发和公开发布未授权。

## 7. OpenCode 提示词硬边界

Gate 3A 是 Phase 9 默认唯一可委派实现批次。提示词必须包含：

- accepted base SHA、唯一分支/worktree 和单写入者声明；
- exact allowlist 与禁止文件；
- 已冻结中文显示映射和 Semantics/200% 验收；
- 禁止更改健康规则、状态机、API、auth、迁移、依赖、照片/live AI 开关；
- 禁止 commit/push/merge/rebase，除非 Codex 在该提示词中特别授权；
- 完成报告的 base/head、status、文件、diff stat、命令/退出码/计数、生成文件和风险。

实现报告只作为审查输入。Codex 必须检查真实 diff、运行完整 Flutter 验证、执行 Android
验证并在 accepted SHA 上关闭 Gate。

## 8. Phase 9 总退出标准

- Gate 0-4 均有 exact accepted SHA、本地证据、GitHub CI 和 findings-first 报告；
- 所有变更从唯一 Phase 8 closure 衍生，分支和 worktree 无范围外改动；
- 无未解决 P0/P1/P2；P3 和外部依赖明确登记；
- 没有真实健康数据/照片/联系方式/生产凭据/live provider/外部成本；
- public release gate 仍为 `not approved`；真实受控试用必须获得新的用户授权。

## 9. Gate 2 实际验证面（2026-08-12）

Gate 2 增加 `python scripts/phase9_security.py verify` 和 `dependencies`，并在 Python 3.12
独立环境从 `backend/requirements-dev.lock` 使用 `--require-hashes` 安装。目标测试为
`test_trial_privacy.py`、`test_security_observability.py`、`test_phase9_security.py`、迁移与既有
privacy/deletion 回归；严格 Full CI 必须执行 PostgreSQL 同意并发、身份删除和 `0014` 升降级且零 skip。
GitHub 新增非 live `phase9-security` job，摘要只含规则、路径、稳定计数和测试结果。
