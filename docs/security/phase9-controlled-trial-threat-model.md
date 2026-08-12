# Phase 9 受控试用威胁模型

> 内部工程威胁模型，2026-08-12。范围为合成数据 Android 候选后端，不是独立安全审计或渗透测试。

## 1. 资产、信任边界与攻击者

关键资产包括邀请码、凭据、设备绑定、session、健康领域数据、同意证据、删除状态、HMAC/加密/JWT
密钥和运维日志。信任边界为 Android 到 API、API 到 PostgreSQL、未来对象存储、备份介质、CI 到
PyPI/GitHub、运营者线下发放渠道。攻击者包括收到 APK 的非受邀者、恶意/失窃测试设备、越权账号、
网络攻击者、依赖投毒者和误操作运维者。

## 2. STRIDE 处置

| 类别 | 场景 | 当前控制与证据 | 状态/剩余门 |
| --- | --- | --- | --- |
| S | 猜邀请码、撞库、冒用设备 | 邀请 digest/一次性/到期/并发消费；慢哈希；单设备；统一错误；限流；session rotation | 已做合成测试；真实线下流程待演练 |
| S | 伪造/重放 JWT | HS256 算法固定，issuer/audience/expiry，候选 32+ 字节非默认 secret，session/jti/revocation | PyJWT 替换旧 python-jose；生产 secret 管理未授权 |
| T | 篡改同意或序号 | 当前版本、追加事件、用户事务锁、唯一约束；健康路由统一 fail closed | SQLite/PG 迁移和并发证据；Gate 3 UI 待做 |
| T | 修改客户端配置开启 live/photo | 服务端候选配置拒绝 live Agent/photo/dev login；客户端字段不能覆盖 | 真实 APK 签名/完整性属于 Gate 3/4 |
| R | 否认登录/同意/删除 | 认证审计 digest、同意事件、不可关联删除回执；稳定事件码和 request ID | 日志存储/时钟/告警平台待运营决定 |
| I | 错误/日志泄露正文或凭据 | 不记录异常正文/请求体；安全日志闭合 schema；secret/artifact 扫描；导出显式排除认证器 | crash/monitor 供应商未批准 |
| I | Host/path 解释差异绕过 | 鉴权路由只用 ASGI `scope.path`；运行时代码禁止 `request.url` 安全判断 | VEX 不变量持续 CI 检查 |
| I | 越权导出/跨账号访问 | session 用户 ID 作为唯一查询主体；不接受客户端 subject ID | 已做本人范围测试；外部渗透未取得 |
| D | 登录/表单/上传资源耗尽 | 登录窗口限制；候选无表单、multipart 上传和照片路径；新版 multipart | 网关 body/rate/capacity 门待部署前批准 |
| D | 依赖解析/恶意产物 | Python 3.12；运行时/dev 双哈希锁；固定 Action SHA；只读 CI；secret/artifact 门 | PyPI 可用性与镜像策略待运营决定 |
| E | `StaticFiles`/`HTTPEndpoint` 隐式方法 | 运行时不挂载二者；VEX 代码不变量 | 新增对应调用会使 CI 失败 |
| E | 删除后由备份恢复账号 | HMAC 删除标记、独立账本要求、候选启动复活检测 | 必须完成隔离恢复演练后才可部署 |

## 3. 供应链审计与 VEX

- `backend/requirements.lock` 只含运行时闭包；`requirements-dev.lock` 额外含测试工具；两者由 Python
  3.12 `pip-compile --generate-hashes` 生成，CI 使用 `--require-hashes`。
- `pip-audit==2.9.0` 的结果必须与 `phase9-dependency-vex.json` 精确相等。新漏洞、版本变化、VEX
  缺失或陈旧都会失败，不使用通配 ignore。
- 当前运行时无已知且适用的未处置漏洞。Starlette 五项处于框架兼容区间之外，但其触发 API 均未使用，
  并由代码扫描不变量约束。pytest Unix 多用户临时目录问题仅存在于隔离、单租户 CI/dev 锁中。
- 任一不变量改变必须重新做适用性评估；不能沿用本 VEX。正式候选前仍需独立安全审查/渗透测试。

## 4. 安全事件和指标

允许事件码：`auth.trial_activation`、`auth.trial_login`、`privacy.consent`、`privacy.export`、
`privacy.account_deletion`、`privacy.restore_deleted_subject`、`request.validation`、
`request.unhandled`。字段只允许 outcome、request ID 和非负聚合 count。

建议告警：5 分钟登录拒绝率异常、邀请码连续失败、同账号多源失败、5xx 比例、删除失败/冻结、恢复
复活阻断。阈值必须由真实容量和误报演练确定，当前不声称已接入监控平台。

## 5. 明确不接受的降级

不得关闭 session/设备校验、恢复开发登录、记录验证码/凭据/健康正文、把对象删除失败当成功、删除
标记随旧备份回滚、对新漏洞沿用旧 VEX、启用 live AI/照片，或把绿色 CI 表述为发布批准。
