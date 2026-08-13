# Phase 9 Gate 3A 中文化与可访问性审查

> 完成日期：2026-08-13
> Gate 2 closure：`c0686c42d907c18aa2656372beb08bf869720cdb`
> 唯一 Phase 8 业务基线：`2ae03345a93d8cc22d0e47fcac415411798df48b`
> 接受的 Task 提交：`079a92e18eaac0f93ab14acca987c4e1cc1cabf6`
> 集成实现：`c7c81edfc78d4149052667c6087b56e364d75868`
> 分支：`codex/phase9-gate3a-flutter` -> `codex/phase9-implementation`
> 状态：accepted；metadata closure 必须通过自身 exact-SHA GitHub CI

## Findings First

### P0

无。

### P1

无未解决项。

### P2

无未解决项。实现和冷审期间发现并关闭：

- 核心界面原先会显示内部 ID、机器枚举、后端原因码和原始服务错误。现改为明确的
  中文 allowlist 映射与稳定兜底；安全关键未知状态不伪装成功。
- 动作知识库的 `instructionSteps` 仍为英文源数据。Gate 3A 不修改知识库或健康规则，
  因此客户端不再直接显示英文步骤，并明确提示中文说明待审校；不确定时要求暂停。
- 现行主题中次要文字/背景、白字/主按钮和警示色/背景分别只有约 `2.48:1`、
  `2.96:1`、`1.56:1`。在扩展后的呈现层 allowlist 中调整色值，并用测试锁定关键文字、
  控件和状态面板色对不低于 `4.5:1`。
- 登录、档案、计划、Today、健康助手、饮食和周复盘缺少完整的可访问名称、状态或
  动态播报。现补充 Semantics/live region，并覆盖 `320x720`、`textScaler=2.0` 的关键操作。

### P3 / Residual

- 本批为 widget/静态工程验证；目标 Android API、TalkBack 实机或模拟器焦点顺序、慢网、
  断网、token 过期、时区和升级回滚仍属于 Gate 3B，不由 Gate 3A 自动测试替代。
- 英文动作知识源未翻译或经健康专业人员审校，因此当前保守隐藏。以后若展示中文动作
  指导，必须使用版本化、可追溯且经独立内容审校的知识资产。
- 法律/隐私、健康专业和独立安全审查仍为 `not obtained`。Codex 内部审查不能替代这些
  外部意见，且不授权真实测试者或真实健康数据。

## 协作与范围审查

- OpenCode + Claude 会话从冻结 allowlist 开始实现，但持续无有效完成报告且会话被终止；
  它留下的局部 diff 只作为审查输入。
- Codex 随后在同一 Task/worktree 内接管唯一写入权，检查完整 diff、补齐行为与测试、
  执行两轮冷审并关闭 findings。没有与第二写入者并行修改同一文件。
- 最终提交只含 22 个批准的 Flutter 呈现层/对应测试文件，共 `1573 insertions`、
  `531 deletions`；没有 backend、API、migration、auth、健康规则、provider/model、依赖、
  CI 或规格变更。

## 行为结论

- 核心流程中的用户可见 `Agent` 统一为“健康助手”，标准单位 `kg`、`kcal`、`RPE`
  按契约保留。
- 未知值、失败和安全状态使用稳定中文说明，不显示内部标识，也不把失败转换成正常状态。
- 关键操作具有可理解的名称、状态和播报语义；颜色不是状态的唯一表达。
- 核心登录、档案、计划、Today、健康助手、饮食和周复盘具备 200% 大字回归覆盖；关键
  命令在 `320x720` 视口中可找到且测试无 overflow exception。
- 本批没有改变领域状态机、健康规则、鉴权、数据模型、照片门或 live AI 开关。

## 本地验证证据

Task 提交 `079a92e18eaac0f93ab14acca987c4e1cc1cabf6`：

- `flutter analyze`：无问题。
- Gate 3A 目标测试：`114/114` 通过。
- `flutter test`：`522/522` 通过。
- `git diff --check`、allowlist、意外生成文件和敏感模式扫描通过。

集成实现 `c7c81edfc78d4149052667c6087b56e364d75868`：

- `flutter analyze`：无问题。
- `flutter test`：`522/522` 通过。
- Phase 8 closure 是当前 HEAD 的祖先，且 merge-base 精确为
  `2ae03345a93d8cc22d0e47fcac415411798df48b`。

## GitHub CI 证据

Task exact SHA `079a92e18eaac0f93ab14acca987c4e1cc1cabf6` 的严格 workflow dispatch
run `31629386472`：

- Fast：`1034 passed, 0 failed, 14 skipped`，skip 均为该层允许的 PostgreSQL 条件用例；
- Flutter：analyze success，`522 passed`；
- Full：`1798 passed, 0 failed, 0 skipped`；PostgreSQL `expected=33 actual=33`；
- Phase 8：真实 HTTP `11/11`、eval `13/13`、零残留；
- Phase 9 security：secret/artifact、VEX、dependency audit 全通过，`19 passed`；
- 五个 job 均成功，checkout SHA 与事件 SHA 精确等于 Task SHA。

cherry-pick 后旧 Task 证据不单独作为集成 SHA 的完成证明；因此已在集成实现上重新执行
Flutter 全量本地验证，metadata closure 还必须在自身 exact SHA 上再次运行严格 CI。

## 回滚

1. Gate 3A 只改 Flutter 呈现层与测试，可独立撤销集成提交；回滚不会迁移或删除数据。
2. 不得回滚到暴露内部 ID、机器值、原始服务错误或英文知识步骤的候选 UI。
3. 若新配色或 Semantics 在 Gate 3B 目标设备上产生回归，保持业务状态机不变，只在呈现层
   修复，并在新 SHA 重跑 Flutter、Android 和严格 CI。

## Gate 结论

接受实现 P0/P1/P2 为零，Task 3A 标记 `verified`。这只关闭 Gate 3 的中文化/可访问性
局部批次；完整 Gate 3 仍等待 3B Android 设备、网络、时区和升级回滚验收。

绿色 CI 不是发布批准。未使用真实健康数据、照片、联系方式、生产凭据或 live provider，
未部署、分发、写入 `main` 或公开发布；真实试用和外部审查仍未授权。
