# Phase 9 Gate 2 隐私、安全与运维审查

> 完成日期：2026-08-13
> Gate 1 closure：`9be5db1d6d8bcf70b08115b0432969b5aabe3011`
> 唯一 Phase 8 业务基线：`2ae03345a93d8cc22d0e47fcac415411798df48b`
> 接受实现：`80135bc3aa551a0fe7c1f2898ab5cebe61f67ab3`
> 分支：`codex/phase9-implementation`
> 状态：accepted；严格 exact-SHA GitHub CI run `31622194153` 全部通过

## Findings First

### P0

无。

### P1

无未解决项。实现期发现并关闭：

- 账号删除原先可能在 purge operation 持久化前先禁用凭据。现将身份冻结、会话撤销和
  purge operation 首次提交放在同一用户锁与同一事务中；失败重试期间账号保持不可登录。

### P2

无未解决项。实现期发现并关闭：

- 体态路由最初把无需登录的公共知识接口也置于敏感健康同意门后；现只对本人健康数据接口加门，
  `/api/v1/posture/issues*` 保持公开知识语义。
- 备份恢复最初只有数据库内删除标记检查，不能执行 runbook 的独立账本合并。现提供带 HMAC
  完整性、字段白名单、冲突拒绝和幂等合并的 `app.privacy.ledger` 命令，并用合成恢复演练证明
  先合并新标记后会阻断删除身份复活。
- 候选配置最初只要求 purge key 非空；现启动阶段验证 AES-256 hex、非空 keyring 和 active
  version，格式错误直接拒绝。
- 新安全测试在 `backend` 工作目录不能导入根目录脚本；现显式、局部引入仓库根路径，Full
  收集通过。
- Phase 1/2 迁移回归仍固定 `0013`；已更新为唯一 head `0014_controlled_trial_privacy`。
- 首轮 CI `31617341156` 暴露 Windows 生成的 `uvicorn[standard]` hash lock 缺少 Linux 专属
  `uvloop` pin。现改用产品实际需要的 plain Uvicorn，空环境 hashed install 与 Linux CI 均通过，
  并增加禁止平台专属 extra 漂移的仓库安全门。
- 严格 CI `31619020475` 的 Full `1798/0/0` 已通过，但 Fast 在 15 分钟 job 上限被取消；日志无
  测试失败。Fast 保持原测试和失败语义，仅将上限调整为 25 分钟；最终 run 在 4 分 23 秒完成。

### P3 / Residual

- 本地没有 Docker/PostgreSQL，35 个 PostgreSQL 条件用例被跳过；必须由 GitHub Full 的零 PG
  skip 和显式 PostgreSQL 计数补齐。
- 本机无法权威访问 GitHub API，15 个 Action tag 在线校验跳过；结构和 commit pin 检查已执行，
  GitHub runner 负责权威验证。
- 真实对象存储 adapter 未批准；候选继续禁止照片。若历史合成对象键存在，删号返回
  `account_deletion_pending` 并保持账号冻结，不能伪造完成。
- 法律/隐私、健康专业和独立安全审查均为 `not obtained`。Codex 的内部审查不能替代这些意见。

## 实现结论

- 新增当前版本敏感健康同意事件；撤回或告知版本变化立即阻断档案写入及健康、体态、训练、
  饮食和 Agent 本人数据路径，身份摘要、同意状态、本人导出和删号权利保持可用。
- 本人 JSON 导出使用显式所有权查询，排除 credential、邀请码、设备、refresh、auth attempt digest
  和服务端 secret。
- 账号删除要求当前 provider 凭据与当前设备重新认证；完成路径删除领域数据、同意、邀请、设备、
  session、credential 和 User，只留下不可关联 HMAC 标记与回执。
- 候选启动检查删除标记对应身份是否被备份复活；独立删除账本可在数据库恢复前后安全导出、验证、
  合并和检查。
- 安全日志只接受枚举事件码、枚举结果、服务端生成 request ID 和非负聚合计数；不记录账号、凭据、
  请求体、健康正文、照片或对象键。
- Python 基线提升至 3.12.13；运行时与开发依赖分离、全量 pin 并生成 hash lock；PyJWT 替换
  python-jose。`pip-audit` 结果必须与 exact VEX 一致，新增漏洞或陈旧 VEX 均失败。
- CI 新增独立 Phase 9 security job，执行 hashed install、secret/artifact 扫描、VEX 对账和隐私安全
  测试；摘要只写 runner temp。

## 本地验证证据

实现候选 `0bb260638da00d10d539a70a52a3853749b298ed`：

- `python scripts/verify.py full`：`1747 passed, 0 failed, 50 skipped`，Ruff 和 working/staged/
  candidate diff check 全通过。skip 为 35 个本机无 PostgreSQL/Docker、15 个本机 GitHub API
  tag 权威查询不可用；无业务功能 skip。
- 新增、鉴权、迁移和安全定向组：`100 passed, 5 skipped`；5 个均为 PostgreSQL 条件用例。
- `flutter analyze`：无问题；`flutter test`：`498 passed`。Flutter 生成器触达的 7 个平台注册文件
  经 staged diff 核对为零，未进入提交。
- `python scripts/phase9_security.py verify`：tracked secret/artifact 与 VEX invariant 通过。
- `python scripts/phase9_security.py dependencies`：dependency audit 与 exact VEX 对账通过。
- `git merge-base 0bb260638da00d10d539a70a52a3853749b298ed
  9be5db1d6d8bcf70b08115b0432969b5aabe3011` 精确等于 Gate 1 closure；与 Phase 8 closure 的
  merge-base 精确等于 `2ae03345a93d8cc22d0e47fcac415411798df48b`。

## GitHub CI 证据

接受实现 `80135bc3aa551a0fe7c1f2898ab5cebe61f67ab3` 的严格 workflow dispatch
run `31622194153`：

- Fast：`1034 passed, 0 failed, 14 skipped`；14 个均为 Fast 层允许的 PostgreSQL 条件用例；
- Flutter：analyze success，`498 passed`；
- Full：`1798 passed, 0 failed, 0 skipped`；PostgreSQL `expected=33 actual=33`，版本证据存在；
- Phase 8：真实 HTTP `11/11`、eval `13/13`、零残留；
- Phase 9 security：secret/artifact、VEX、dependency audit 全通过，`19 passed`；
- 五个 job 的 checkout SHA 与 event SHA 均精确等于接受实现 SHA。

历史 run 不被隐藏：`31617341156` 因跨平台 hash lock 失败；`31618479425` 未启用 Full，不能作为
严格验收；`31619020475` 的 Full 成功但 Fast 达到旧 timeout，run 总状态 cancelled。上述原因均在
后续提交关闭，最终 run 全部 success。

## 回滚与恢复

1. 应用回滚必须保持 `0014` 表和 privacy gate；不得 downgrade 后继续候选服务。
2. 紧急止损先停候选入口、撤销 session/邀请并保持删除 worker；不能恢复 legacy 开发鉴权。
3. 数据库恢复必须先合并独立删除账本，再执行 `python -m app.privacy.ledger check`；发现复活主体时
   保持服务关闭并重新运行完整 purge。
4. purge keyring 旧版本保留到所有删除重试完成；没有迁移证明时不得删除旧 key。

## Gate 结论

接受实现 P0/P1/P2 为零，Gate 2 标记 `accepted`。绿色 CI 只证明本 Gate 的合成工程门，不授权
真实测试者、真实健康数据/照片、生产凭据、live AI、部署、分发或公开发布。报告/状态 closure
仍必须通过自身 exact-SHA Fast、Flutter、Full、Phase 8、Phase 9 security 与 PostgreSQL CI，
才能作为 Gate 3 的精确基线。
