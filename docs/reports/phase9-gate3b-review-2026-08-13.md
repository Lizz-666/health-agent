# Phase 9 Gate 3B Android 可靠性审查

> 审查日期：2026-08-13
> Gate 3A closure：`a3c8b5a5e4fb4f8129a397c1593185bdbf346a87`
> 唯一 Phase 8 业务基线：`2ae03345a93d8cc22d0e47fcac415411798df48b`
> 本地接受实现：`9c5670714fd113061948c1daf2315f3e2dbde9e1`
> 分支：`codex/phase9-implementation`
> 状态：accepted；实现 exact-SHA CI `31674663884` success，等待 closure SHA 自证

## Findings First

### P0

无。

### P1

无未解决项。

### P2

无未解决项。实现与设备验收期间发现并关闭：

- 独立 Uvicorn 设备服务在应用模型先于 SQLite 双类型适配导入时，无法编译 PostgreSQL `JSONB`；
  调整测试服务导入顺序，并由真实子进程启动测试覆盖。
- HTTP runner 完成后启动的时区 pytest 与默认 `backend/test.db` 发生并行 DDL 竞态；矩阵改用独立
  `phase9_matrix.db`，前后清理 db/journal/wal/shm，并新增隔离回归测试。
- Flutter 全量分析发现一个无效测试 import；已删除并重跑 analyze/widget/full test。
- API 34 路由转场中认证表单出现时旧会话页面可能尚未移除；E2E 改为有界等待完整转场，而非用
  单帧断言产生偶发失败。
- API 28 小屏软键盘可能覆盖认证提交按钮；E2E 通过运行时 unfocus、等待布局稳定和
  `ensureVisible` 后点击，API 28/API 34 均重跑通过。

### P3 / Residual

- Android 证据来自 API 34/API 28 x86_64 模拟器，不等同于实体机、OEM 定制系统或蜂窝网络覆盖。
- 慢响应使用本机 600 ms 确定性 fault，不模拟丢包、抖动、代理、TLS 中间设备或真实跨地域网络。
- 本地后端完整非 PG 套件耗时约 24 分钟；一次 `verify.py full` 因工具 20 分钟外层上限未形成有效
  汇总，后续拆分为 33/33 PostgreSQL 和 1765/18 非 PG 证据。实现 CI 已在单一 SHA 上补齐
  `1816/0/0` 和 PostgreSQL `33/33`。
- 法律/隐私、健康专业和独立安全审查均为 `not obtained`。Codex 内部审查不能替代外部意见。

## 范围与行为结论

- 生产变更严格位于冻结的 7 个鉴权/兼容性文件；测试、runner、CI 与证据文件均在 Gate 3B
  allowlist。没有 migration、模型、健康规则、依赖、live AI、照片或其他业务界面变更。
- 候选客户端统一发送 Android platform/version 头；服务端仅在
  `controlled_trial_candidate` 对 `/api/v1/*` 强制版本窗，并在领域读写前返回稳定 `426`。
- 并发 401 共享一次 refresh；迟到旧 401 复用已旋转 token；refresh 失败、撤销、过期和 426
  均清除 token 与跨域用户缓存，不把失败转换为成功。
- 合成 runner 只允许 localhost、可丢弃 SQLite、固定合成身份和稳定脱敏输出；真实 HTTP 11 个
  转换结束后恢复两账号基线且无 session/设备/同意残留。
- `Asia/Shanghai` 日界和周界由服务端 UTC 注入时钟推导；迁移只在服务关闭的可丢弃 PostgreSQL
  演练 downgrade/re-upgrade，运行中禁止降到 `0013`。

## 本地验证证据

实现 SHA `9c5670714fd113061948c1daf2315f3e2dbde9e1` 及其仅测试前驱候选：

- `python scripts/phase9.py verify --surface all`：真实 HTTP `11/11`、时区 `2/2`、零失败、零残留；
- `python scripts/phase9_security.py verify/dependencies`：secret/artifact、VEX 和 dependency audit 通过；
- `flutter analyze`：无问题；`flutter test`：`531/531` 通过；
- PostgreSQL 16 `pytest -m requires_pg`：`33/33` 通过、0 skip，含 `0014 -> 0013 -> head`；
- 非 PG 完整套件：`1765 passed, 18 skipped, 33 deselected`；PG 的 33 项已由上一条完整执行；
- Android API 34：主路径 `4/4`、不可达 `1/1`；
- Android API 28：主路径 `4/4`、不可达 `1/1`；
- `git diff --check`、冻结 allowlist、敏感信息和意外生成文件检查通过；模拟器、8000 端口和
  `phase9_acceptance.db` 已清理。

详细设备与行为矩阵见 `docs/operations/phase9-android-reliability-matrix.md`。

## GitHub CI

实现 SHA 的 workflow dispatch run `31674663884` 精确绑定
`9c5670714fd113061948c1daf2315f3e2dbde9e1`，六个 job 全部成功：

- Fast：`1052 passed, 0 failed, 14 skipped`；
- Flutter：analyze success，`531/531` tests；
- Full：`1816 passed, 0 failed, 0 skipped`，PostgreSQL `33/33`；
- Phase 8：真实 HTTP `11/11`、评测 `13/13`，零残留；
- Phase 9 security：secret/artifact/VEX/dependency audit 通过，`19/19`；
- Phase 9 reliability：真实 HTTP `11/11`、时区矩阵 `2/2`，零残留。

CI URL：`https://github.com/Lizz-666/health-agent/actions/runs/31674663884`。承载本报告的 closure
SHA 仍必须执行同一严格 workflow；若失败，Gate 3B 接受结论立即失效。

## 回滚

1. 客户端/服务端版本窗回滚遵循 runbook 的先停服或只读、恢复兼容窗、撤销故障版本 session、
   重跑双 API 和 HTTP 11 转换顺序。
2. 不得通过关闭版本校验、恢复开发登录、跳过隐私同意或删除证据来恢复可用性。
3. 数据库不能随 APK 回退到 `0013` 继续服务；无法证明旧 APK 兼容 `0014/head` 时保持服务关闭并前向修复。

## Gate 结论

实现 P0/P1/P2 为零，Android API 34/API 28、合成可靠性矩阵和实现 exact-SHA CI 均通过。
Gate 3B 接受并进入 Gate 4；该结论以承载本报告的 closure exact-SHA CI 成功为生效条件。

绿色本地/CI 证据均不授权真实测试者、真实健康数据/照片、生产凭据、live AI、部署、分发或公开发布。
