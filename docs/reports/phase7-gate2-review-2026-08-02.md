# Phase 7 Gate 2 Codex 独立审查

## 结论

**PASS。** Gate 2 接受 `codex/phase7-implementation` 上的集成实现
`52057d102941de3b3a66361ee07b895bee64ada7`。OpenCode Task 分支经 Codex 接管、
修复和独立验证后的提交为 `2fa6c3fc9e4badc84b9519e823a6674b64561e89`。
未解决 P0/P1/P2 finding 为零；本 Gate 只接受 Flutter Today/Plan/周回顾纵切，
周回顾后端聚合、跨域草案、Agent 权限和最终 E2E 仍属于 Tasks 3-4。

## Findings First

### 已关闭 P1

1. 普通休息日仍渲染同日调整按钮，点击后会对不存在的原始会话执行空值断言。
   现在只有具备严格原始来源身份的有效训练日才显示 mutation 控件；普通休息日是
   有效只读状态。

### 已关闭 P2

1. 原始会话缺失时客户端曾回退到有效会话 ID，破坏乐观并发和不可变来源契约。
   `TodayResult` 现在严格要求 session 状态携带原始会话与来源日期，mutation 只使用
   该原始身份。
2. stale、结构冲突和缺失输入曾被统一渲染为健康安全阻断。现在 stale、missing、
   conflict、unavailable、parse-error 与真正的 restricted/red-flag 安全状态分别显示。
3. POST 成功后在权威 `GET /training/today` 失败时仍可能显示 applied。现在只有严格解析
   的权威回读成功后才进入 applied/replayed，否则 fail closed 为 unavailable 或
   parse-error；普通 GET 也会清除旧 mutation 状态。
4. Today check-in 保存后未刷新有效训练状态。现在保存成功只触发只读 Today GET，
   不会从 Today 页面发起调整 POST。
5. 周回顾生成请求缺少时区和幂等键，周序号和响应周次也未双向校验。现在仅允许
   1..4 周，显式按钮 POST 严格携带 `iana_timezone` 与 `idempotency_key`，并拒绝
   response/request 周次不一致。
6. 周回顾 DTO 将缺失计数隐式当作零，并放宽趋势、体态比较、草案来源等结构。
   现在未知枚举、负数、缺失 availability、反向周期和不完整比较均解析失败；训练草案
   来源统一为规格字段 `origin_weekly_review_id`。
7. stale 回顾没有可达的重新生成动作，未生成文案还暗示后台自动生成。现在生成和
   重新生成都只能由显式按钮触发，加载、切周和 Today check-in 均不会隐式 POST。
8. 原始与有效训练只显示 ID，无法完成产品选择要求的可理解对照。Plan 页面现在显示
   两者摘要、时长和动作，并呈现调整类型、原因、延期来源/目标、active-rest 与完整
   loading/replay/stale/safety/missing/conflict/parse/unavailable 状态；Today 仅保留紧凑
   只读状态卡并导航到 Plan。

## 接受范围与安全边界

- `GET /training/today` 是客户端有效 Today 的唯一权威读取；旧
  `/training/plans/today` 不再用于本流程。
- 同日调整按钮只位于 Plan 页面，Today 页面永不托管 mutation；并发点击被锁定，
  请求只携带 intent、expected plan/session、时区和幂等键。
- 周回顾事实先于提案渲染；missing 不等于 zero，active-rest 不等于失败；体重趋势
  只展示，不参与训练提案；体态提醒不隐藏安全状态。
- 周回顾生成不是计划激活。proposal、draft 和 active 明确分离，draft 仍需后续独立
  确认流程。没有 live AI、真实健康数据、照片、生产凭据、部署或 main 写入。

## 本地验证

Task 分支提交 `2fa6c3fc9e4badc84b9519e823a6674b64561e89` 与集成 SHA
`52057d102941de3b3a66361ee07b895bee64ada7` 均在 `app` 目录重新验证：

```text
flutter analyze
PASS: No issues found

flutter test test/models/plan_test.dart test/models/adaptive_review_test.dart \
  test/providers/plan_provider_test.dart \
  test/providers/adaptive_review_provider_test.dart \
  test/screens/plan_screen_test.dart test/screens/today_checkin_test.dart \
  test/screens/weekly_review_screen_test.dart
PASS: 122 passed / 0 failed

flutter test
PASS: 468 passed / 0 failed

git diff --check
PASS
```

真实 staged diff 审查覆盖 15 个计划白名单文件；私钥/token、敏感文件类型、真实健康
数据/照片和新增 payload 日志扫描无命中。Flutter 工具产生的 7 个平台注册文件仅有
CRLF 工作树噪声，已恢复为与索引一致且未进入提交。

## Exact-SHA CI

GitHub Actions workflow-dispatch run `30752998183`，event SHA 与 checked-out SHA
均为 `52057d102941de3b3a66361ee07b895bee64ada7`：

```text
Fast:    success; ruff clean; 915 passed / 0 failed / 10 expected PG skips
Flutter: success; analyze clean; 468 passed / 0 failed
Full:    success; ruff clean; 1615 passed / 0 failed / 0 skipped;
         PostgreSQL expected=25 / actual=25 / version evidence present
```

CI artifact：`ci-fast-summary`、`ci-flutter-summary`、`ci-full-summary`。三个 job
均成功，candidate diff clean。

## 残余风险与下一 Gate

没有未解决 P0/P1/P2。Gate 2 的周回顾客户端 DTO 是 Task 3 后端必须实现的已审查
契约；Task 3 若因服务端模型需要改变字段或状态，必须作为显式跨端契约变更重新冷审并
重跑 Flutter。Task 3 由 Codex 单写入者直接实现周回顾聚合、训练/营养草案来源、体态
复查状态、Agent allowlist/确认/隐私与跨域删除，不委派给 OpenCode。
