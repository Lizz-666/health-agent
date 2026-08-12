# Phase 9 Gate 2 隐私、安全与运维审查

> 完成日期：2026-08-13
> Gate 1 closure：`9be5db1d6d8bcf70b08115b0432969b5aabe3011`
> 唯一 Phase 8 业务基线：`2ae03345a93d8cc22d0e47fcac415411798df48b`
> 实现候选：`0bb260638da00d10d539a70a52a3853749b298ed`
> 分支：`codex/phase9-implementation`
> 状态：本地接受候选；exact-SHA GitHub CI 待运行

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

## 回滚与恢复

1. 应用回滚必须保持 `0014` 表和 privacy gate；不得 downgrade 后继续候选服务。
2. 紧急止损先停候选入口、撤销 session/邀请并保持删除 worker；不能恢复 legacy 开发鉴权。
3. 数据库恢复必须先合并独立删除账本，再执行 `python -m app.privacy.ledger check`；发现复活主体时
   保持服务关闭并重新运行完整 purge。
4. purge keyring 旧版本保留到所有删除重试完成；没有迁移证明时不得删除旧 key。

## Gate 结论

实现候选本地 P0/P1/P2 为零，可进入 exact-SHA GitHub CI。绿色 CI 只证明本 Gate 的合成工程门，
不授权真实测试者、真实健康数据/照片、生产凭据、live AI、部署、分发或公开发布。Gate 2 只有在
报告/状态 closure 自身的 Fast、Flutter、Full、Phase 8、Phase 9 security 与 PostgreSQL 证据全部
通过后才能标记 `verified`。
