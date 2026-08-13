# Phase 9 受控试用运维与事故 Runbook

> 2026-08-12 内部工程稿。当前没有部署、真实测试者、生产凭据、监控供应商或外部值班团队。
> 本 runbook 用于合成演练和发布准备，不构成实际运营授权。

## 1. 候选启动前置

1. exact SHA 的 Fast、Flutter、Full、Phase 8 acceptance、Phase 9 security 和 Phase 9
   reliability 六个 CI job 全绿；P0/P1/P2 为零。
2. Python 3.12.13，依赖从 `backend/requirements.lock` 使用 `--require-hashes` 安装；迁移到 `0014`。
3. `DEPLOYMENT_PROFILE=controlled_trial_candidate`、`AUTH_MODE=controlled_trial`、独立非默认 JWT/
   auth HMAC/privacy HMAC/purge keyring；access 1-15 分钟；issuer/audience 非默认。
4. `DEV_MODE=false`、无开发账号、`PHOTO_ANALYSIS_ENABLED=false`、`AGENT_RUNTIME_ENABLED=false`。
5. 不向日志、工单、截图或 CI artifact 写入真实凭据、账号、健康正文、照片或对象键。
6. 真实部署前另行批准 TLS/域名、数据库/备份地域、最小权限、监控和事故负责人。
7. Android release 构建必须由 `ANDROID_RELEASE_STORE_FILE`、
   `ANDROID_RELEASE_STORE_PASSWORD`、`ANDROID_RELEASE_KEY_ALIAS`、
   `ANDROID_RELEASE_KEY_PASSWORD` 注入独立签名；缺失时构建必须失败。release manifest 禁用
   cleartext 且不声明相机权限；debug/profile 的本机 HTTP 例外不得进入候选包。

## 2. 日常合成检查

```powershell
python scripts/phase9_security.py verify
python scripts/phase9_security.py dependencies
python scripts/verify.py fast
python scripts/verify.py full
```

只保留命令、SHA、退出码、测试计数和稳定事件聚合。`pip-audit` 原始输出不含 secret，但对外共享前仍
检查路径和环境信息。CI 摘要写入 runner temp，不写工作树。

## 3. 账号、邀请和会话止损

- 邀请疑似泄露：立即将对应 invitation 标记 revoked；不要在聊天/日志粘贴原邀请码；另发新邀请码。
- 凭据疑似泄露：禁用 `trial_credentials.disabled_at`，撤销该用户全部 auth sessions 和 device enrollment；
  新凭据必须线下独立发放，不通过短信/邮件，因为这些 provider 尚未批准。
- APK 广泛转发：停止签发邀请、批量撤销未消费邀请；已激活账号按风险逐一禁用。APK 本身不是授权。
- JWT secret 疑似泄露：先停止候选服务，轮换 secret，并撤销全部 session；不可仅轮换而保留旧 refresh。
- auth/privacy HMAC key：不得直接覆盖。先停写、保留旧 key 和 version、迁移必要 digest/标记，再切换。
  无已审查迁移时保持服务关闭。
- purge keyring：新写入切换 active version；旧 version 保留到所有重试完成。删除旧 key 前证明无对应密文。

## 4. 删除失败

1. `failed_oss_retry`：账号写入保持冻结；核实对象 adapter/权限；保留加密对象键；不得写成功回执。
2. `failed_db_retry`：对象键已清理但 DB 删除未完成；修复数据库后从状态机重试，不手工跳状态。
3. `failed_decrypt`/永久失败：P1，停止该账号处理并升级；恢复正确 key，不猜测或伪造对象不存在。
4. 完成后核对领域表、身份/会话/同意表为空，purge 操作无可关联字段，删除标记和回执存在。

## 5. 备份恢复与删除复活演练

恢复永远在隔离网络执行，服务不得先对客户端开放：

1. 记录待恢复备份的 SHA/时间、数据库版本和最新独立删除标记账本版本。
2. 在账号删除完成后及每次备份时，从 `backend` 目录运行
   `python -m app.privacy.ledger export <数据库备份之外的受控路径>`；账本带 HMAC 完整性证明，路径不得
   位于仓库、日志或公开 artifact。恢复数据库和对象清单后，运行
   `python -m app.privacy.ledger import <账本路径>` 合并备份之后产生的标记。命令只移动 digest、
   receipt、deleted_at、policy version，不移动原账号映射；完整性失败或冲突时必须终止。
3. 使用与标记一致的 `PRIVACY_AUDIT_HMAC_KEY` 运行候选启动检查。若发现标记对应的 trial identity，
   启动必须失败并产生 `privacy.restore_deleted_subject/blocked`。
4. 在服务关闭状态重新运行完整账号 purge；若对象 adapter 不具备证明能力，保持冻结并终止恢复。
5. 重跑复活检查、迁移检查、合成登录/隔离/删除测试。只有零复活主体时才可考虑开放。
6. 删除标记账本必须至少覆盖最长备份寿命。运营主体和期限未批准前，不得销毁账本或宣称恢复就绪。

回滚应用版本不得 downgrade `0014` 后继续服务；这会移除同意与删除标记证据。数据库回滚只能恢复到
兼容版本并保留这些表，或保持服务关闭进行前向修复。

### Android 客户端版本升级与回退

1. 新 APK 分发前，先把服务端兼容窗口扩为同时接受当前版本和新版本；运行合成激活、刷新、
   注销、同意零意外写入和核心流程检查，再分发。不得先提高最小版本造成存量客户端突然失效。
2. 只有已确认测试者均完成升级、旧版本会话可撤销且新版本观察窗无 P0/P1/P2 后，才可提高
   `MIN_ANDROID_CLIENT_VERSION_CODE`。`MAX_ANDROID_CLIENT_VERSION_CODE` 必须对应已验收版本，
   未验收的更高版本同样返回 `426`。
3. 回退 APK 前先保持服务关闭或只读，把兼容窗口恢复为包含上一已验收版本；确认上一版本仍兼容
   `0014/head`、不恢复开发登录、live AI 或照片，再重新分发。数据库不得随 APK 回退到 `0013`。
4. 回退后撤销故障版本的活动会话，重跑 Phase 9 合成 HTTP 11 个转换、Android API 34/API 28
   核心流程和不可达重试；证据无半写入、无残留会话后才可恢复服务。
5. 若无法证明旧 APK 与现行 schema、隐私同意和删除标记兼容，保持服务关闭并前向修复；不得通过
   放宽版本校验、跳过同意或删除证据来恢复可用性。

## 6. 事故分级与流程

| 级别 | 示例 | 首要动作 |
| --- | --- | --- |
| P0 | 真实健康数据/凭据公开、跨账号大规模读取、删除账号复活且已开放 | 立即停服/撤销凭据/保全证据；通知用户和适用监管流程需专业负责人决定 |
| P1 | 单账号越权、删除不完整、JWT/HMAC/purge key 泄露、live/photo 意外开启 | 停止受影响路径，撤销会话/邀请，禁止新写入，24 小时内形成修复与验证计划 |
| P2 | 无敏感泄露的稳定失败、告警缺口、依赖新增适用漏洞 | 暂停候选晋级，在下一次操作前修复并重新跑 exact-SHA 门 |
| P3 | 文档、可维护性或低风险监控改进 | 登记负责人和期限，不得掩盖为已完成外部审查 |

统一过程：识别 -> 止损 -> 保全最小化证据 -> 范围确认 -> 修复 -> 新 SHA 验证 -> 恢复决定 -> 复盘。
证据只记录 stable code、request ID、时间窗、版本和聚合计数；禁止复制请求体或数据库健康正文。

## 7. 当前责任与阻断

当前内部事故协调、规格和工程复核由 Codex 承担，产品取舍由用户决定。不存在经批准的真实运营值班、
法律/隐私负责人、健康专业负责人或独立安全审查者；其状态均为 `not obtained`。因此本 runbook 通过也
不能授权真实数据、真实测试者、部署、分发或公开发布。
