# Phase 9 Codex 退出审计

日期：2026-08-13

唯一业务基线：`2ae03345a93d8cc22d0e47fcac415411798df48b`

Gate 4 输入基线：`1783573067d6eb599591ead8fc938a909ab08d43`

Gate 4 接受实现：`4d013120cbe499b55d008679915d7eb0a3740701`

最终已验证 Phase 9 代码基线：`7f801255b0ecfab50b92f959a4f093a7919126a2`

分支：`codex/phase9-implementation`

> 状态：Phase 9 Android 小范围受控试用候选版工程验收通过。本报告不授权 merge、写
> `main`、部署、真实测试者、真实健康数据/照片、生产凭据、live AI、分发或公开发布。

## Findings First

最终 Codex 规格符合性和工程质量冷审无未解决 P0、P1 或 P2。

已关闭 finding：

1. P2：Gate 3B Android 主路径验证了身份和会话，但未把受控身份连接到敏感健康同意及核心领域
   写读。Gate 4 在真实 HTTP runner 和双 API Android 流程增加同意、健康档案写入/回读，并证明
   第二独立账号看不到第一账号数据；最终 checkpoint 为 `controlled_trial_core_journey_isolated`。
2. P2 调查项：`uiautomator dump` 对候选登录 TextField 显示空 `content-desc` 和 `NAF`。Flutter
   Android 桥接源码确认 API 28+ 把 label/hint 写入 `AccessibilityNodeInfo.hintText`，而 dump 不导出
   该字段。撤销会产生重复 EditText 的外包 `Semantics` 试验，改由最终合成语义树断言三个具名
   text field，并在 TalkBack 开启的 API 34 上执行错误 live-region 和完整设备流程。

残余 P3 / 外部门：

- TalkBack 证据包含服务绑定、最终语义树和真实设备流程，不包含真人手势遍历、音频转写或认证。
- API 34/28 为模拟器，不是实体机、蜂窝运营商网络或大规模设备覆盖。
- 法律/隐私、健康专业和独立安全审查均为 `not obtained`；Codex 内部审查不能替代这些意见。
- 真实运营主体联系方式、托管/备份地域、监控平台、真实保留期限和外部供应商尚未批准。

## 范围与边界

- 所有变更可追溯到唯一 Phase 8 closure；`merge-base` 精确为该 SHA。
- Gate 4 只使用固定合成账号、邀请码、凭据和健康档案；无手机号、邮箱、真实照片或生产 secret。
- live provider 和照片路径保持关闭；没有外部成本、部署、分发、PR、merge 或 `main` 写入。
- 冷审覆盖 Phase 8 closure 到接受实现的 103 个文件，并重点复核鉴权/授权、同意、删除/恢复、
  版本窗、日志、供应链、Flutter 错误态与 Android E2E。Gate 4 增量未改变健康规则或迁移。

## 本地与设备证据

| 检查 | 结果 |
| --- | --- |
| `python scripts/phase9.py verify --surface all` | HTTP 11/11；Asia/Shanghai 2/2；33 表；零残留 |
| Phase 9 security/dependencies + focused tests | secret/artifact/VEX/dependency audit PASS；19/19 |
| `flutter analyze` / `flutter test` | 无问题；532/532 |
| Android API 34（TalkBack 开启） | 主路径 5/5；不可达 1/1 |
| Android API 28 | 主路径 5/5；不可达 1/1 |
| PostgreSQL 16 | 33/33；含 `0014 -> 0013 -> head` 停服迁移演练 |
| 事故 tabletop focused suite | 29/29；设备冲突/换机、撤销、删除失败冻结、恢复阻断、账本完整性、live/photo 关闭 |
| 清理 | 模拟器关闭；8000 无 listener；合成 DB/工作树无残留 |

不可达测试把候选 API 固定到空端口 `65533`，只经 localhost 合成服务预置 session；Today 保持
network error 和显式重试，不显示成功/调整/写入状态。API 34/28 主路径均验证错误凭据无 token、
邀请激活、同意与档案、后台恢复、慢响应、过期、撤销和 426 领域写入前阻断。

## GitHub CI

严格 workflow-dispatch run
[`31686265174`](https://github.com/Lizz-666/health-agent/actions/runs/31686265174)
精确检出接受实现 `4d013120cbe499b55d008679915d7eb0a3740701`，六个 job 全部成功：

- Fast：1052 passed、0 failed、14 条件 skip；ruff/diff clean；
- Flutter：analyze success，532 tests passed；
- Full：1816 passed、0 failed、0 skipped，PostgreSQL expected/actual 33/33；
- Phase 8：HTTP 11/11、eval 13/13，零残留；
- Phase 9 security：扫描和依赖审计 PASS，19/19；
- Phase 9 reliability：HTTP 11/11、时区 2/2，零残留。

此前 run `31685813557` 未启用 `run_full`，Full 被条件跳过，因此明确不作为严格 Gate 4 证据。
承载本报告和状态更新的 closure exact SHA 必须再运行同一严格 workflow；失败则本验收立即失效。

后续 onboarding/navigation 修复后的最终代码基线 `7f801255b0ecfab50b92f959a4f093a7919126a2`
由严格 workflow-dispatch run
[`31701841156`](https://github.com/Lizz-666/health-agent/actions/runs/31701841156)
自证，六个 job 全部成功：Fast 1052 passed/14 条件 skip、Flutter 539、Full 1816/0/0、
PostgreSQL 33/33、Phase 8 HTTP 11/11 + eval 13/13、Phase 9 security 19/19、Phase 9
reliability HTTP 11/11 + 时区 2/2。该 run 不改写上文 Android API 34/28 设备回放绑定的 Gate 4
接受实现 SHA；后续提交的设备重跑仍需单独证据。

## 决定

Gate 0-4 工程门均有 exact SHA、本地验证和 GitHub CI；P0/P1/P2 为零。Phase 9 Android
小范围受控试用候选版工程验收通过。

`docs/product/public-release-gate.md` 继续为 `not approved`。真实受控试用仍需新的用户授权以及
运营主体、支持/事故联系人、实际数据流/期限/文本、托管与生产 secret 决策；真实健康数据试用和
公开发布仍被外部专业审查及发布门阻断。
