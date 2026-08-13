# Phase 9 Gate 1 身份与候选配置审查

> 日期：2026-08-12
> 基线：Gate 0 exact closure `5cdd43bc808bc08897c05e31f22941239812f294`
> 分支：`codex/phase9-implementation`
> 接受实现：`407ce9ce5de3f53140db8660505e8c15cf94e628`
> 状态：accepted；严格 exact-SHA CI run `31569996543` 全部通过

## Findings First

### P0

无。

### P1

无未解决项。

### P2

无未解决项。实现期间发现并关闭：

- 候选模式可能接受 legacy 无状态 token：现按 `AUTH_MODE` 双向拒绝错误 token 类型；
- refresh/logout 竞态可能遗留新会话：客户端登出改用不自动 refresh 的独立 HTTP 通道；
- 只按账号限速可被随机账号轮换绕过：失败计数同时按账号 HMAC 和请求来源 HMAC；
- Flutter 候选误用明文默认 API 地址仍可登录：候选构建要求 HTTPS、照片关闭、无开发凭据；
- scrypt 参数可被数据库串降级：adapter 只接受固定 `N=32768,r=8,p=1`；
- 工具并发误用同一 SQLite 测试库会产生伪失败：已结束残留进程、删除合成库并串行复验。

### P3 / Residual

- Gate 1 只提供 operator service，不提供公开或网络管理端；真实运营工具属于后续授权范围。
- 本地无可用 PostgreSQL，因此两个新增 PG 用例在本地条件 skip；严格 GitHub Full 已以
  零 skip 覆盖邀请/refresh 并发单赢家及 `0013` downgrade/upgrade。
- 外部法律、健康专业和独立安全审查仍为 `not obtained`；本审查不替代外部意见。

## 实现结论

- 邀请、稳定用户、credential provider、设备登记和会话分表持久化；试用账号不伪装手机号。
- 邀请码使用高熵随机值，库中只保存 SHA-256 digest；一次性消费用条件更新原子声明。
- 线下凭据使用固定参数 scrypt 慢哈希；未知账号走同一 dummy KDF 和稳定错误 envelope。
- 每账号一个设备登记、一个活动会话；refresh 轮换、登出、禁用、换机重签均可撤销。
- JWT 校验强制签名、issuer、audience、expiry 和 token type；候选 access 最长 15 分钟。
- 候选配置拒绝默认 DB/secret/issuer/audience、开发认证、照片和 live Agent。
- Flutter API 使用 `provider_id + credential`，未来短信 adapter 不改变主体、设备或会话契约。
- 未使用真实手机号、邮箱、健康数据、照片、生产凭据或 live provider；未部署、未发布。

## 验证证据

候选 diff 上已通过：

- `python -m pytest backend/tests/test_auth.py backend/tests/test_auth_trial.py backend/tests/test_migrations.py -q`
  -> `82 passed, 2 skipped`（仅新增 PG 条件用例）；
- `python -m pytest backend/tests/test_migrations.py -q` -> `55 passed`；
- `flutter analyze` -> 无问题；
- `flutter test` -> `498 passed`；
- 候选有效配置测试 -> `1 passed`；候选无效配置 fail-closed -> `1 passed`；
- 干净实现 SHA `db6e344988254159df7f22e144a7b8b2ff6889ad` 本地
  `python scripts/verify.py full` -> `1731 passed, 0 failed, 38 skipped`，本机缺少
  PostgreSQL 时 PG 用例按条件跳过；
- 首轮严格 CI `31569256501` 暴露旧 `0012` 迁移测试降级后 teardown 仍引用新表；
  schema-aware 清理修复后，接受 SHA 为
  `407ce9ce5de3f53140db8660505e8c15cf94e628`；
- 接受 SHA 的严格 CI `31569996543`：Fast、Flutter、Full、Phase 8 acceptance 全部
  `success`；Full 为 `1769 passed, 0 failed, 0 skipped`，PostgreSQL
  `expected=30 actual=30` 且版本证据存在；
- `git merge-base 407ce9ce5de3f53140db8660505e8c15cf94e628
  5cdd43bc808bc08897c05e31f22941239812f294` 精确等于 Gate 0 closure。

## 回滚与恢复

1. 先将候选身份入口停止服务，撤销所有 `auth_sessions`、设备登记和未消费邀请。
2. 若只回退应用，保留 `0013` 表可避免身份记录丢失；legacy 开发认证不得在候选配置恢复。
3. 若回退 schema，先导出/删除 `phone IS NULL` 的候选账号，再 downgrade 至 `0012`；否则
   `users.phone SET NOT NULL` 按设计失败关闭。
4. 数据库恢复后必须再次撤销恢复点之后本应失效的会话/邀请，不能让旧 token 复活。

## Gate 结论

接受实现的 P0/P1/P2 为零，Gate 1 标记为 `accepted`。Gate 2 可从
`407ce9ce5de3f53140db8660505e8c15cf94e628` 顺序开始；绿色 CI 不授权真实试用、真实数据、
生产凭据、部署或发布，外部专业审查仍为 `not obtained`。
