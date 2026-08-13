# Phase 9 Android 可靠性矩阵

> 执行日期：2026-08-13
> Gate 4 接受实现 exact SHA：`4d013120cbe499b55d008679915d7eb0a3740701`
> 数据边界：固定合成账号、邀请码、凭据和可丢弃 SQLite；无真实健康数据、照片、联系方式或生产凭据

## 设备矩阵

| AVD | Android | API | ABI | 主路径 | 服务不可达 | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
| `Pixel_6` / `emulator-5554` | 14 | 34 | `x86_64` | 5/5 | 1/1 | PASS（TalkBack 开启） |
| `Phase9_API_28` / `emulator-5554` | 9 | 28 | `google_apis/x86_64` | 5/5 | 1/1 | PASS |

API 28 使用 Android 官方 `system-images;android-28;google_apis;x86_64` revision 11；
AVD 配置固定 `target=android-28`、`hw.device.name=pixel_2`。两个 AVD 串行执行，测试后均正常关闭。

## 主路径覆盖

`phase9_controlled_trial_test.dart` 在两个 API 上均覆盖：

1. 错误合成凭据保持未登录、无 token 残留，稳定中文错误节点具有 live-region 语义；
2. 唯一邀请码激活、单机设备键、敏感健康同意、健康档案写入/回读、后台恢复和慢响应；
3. session 过期后请求失败、access/refresh 清除、用户态清空并回到认证；
4. session 撤销后的同等 fail-closed 清态；
5. 服务端兼容窗口拒绝客户端时返回 `426`，客户端清态并进入版本阻断页，领域写入未发生。

API 34 执行时 TalkBack 服务已绑定且 accessibility enabled。Flutter 最终合成语义树证明内测账号、
邀请码和内测凭据均为具名 text field；错误节点为中文 live region。Android API 28+ 把 TextField
标签暴露为 `AccessibilityNodeInfo.hintText`，`uiautomator dump` 不导出该字段，因此不把 XML 中空的
`content-desc`/`NAF` 作为字段无名称证据。本矩阵没有人工手势遍历或音频转写，不声称无障碍认证。

`phase9_unreachable_test.dart` 在两个 API 上均把候选 API 固定到不可达端口 `65533`，只通过
本机合成服务预置 session；Today 进入 network error，不显示调整或打卡写按钮，保留显式重试，
重试后仍不伪造成功状态。

## 非设备矩阵

| Surface | 结果 | 关键证明 |
| --- | --- | --- |
| 真实本机 HTTP | 11/11 PASS | 两个独立账号、邀请重放、设备冲突、refresh rotation/replay、慢响应显式重试、426 零写入、撤销、过期、零残留 |
| `Asia/Shanghai` | 2/2 PASS | UTC 注入跨本地午夜与周日到周一周界，客户端日期不覆盖服务端推导 |
| Flutter 单元/widget | 532/532 PASS | 401 并发只 refresh 一次、迟到旧 401 复用新 token、426 清态、字段最终语义名称、重复认证提交只有一次请求 |
| PostgreSQL 16 | 33/33 PASS | 含 `0014 -> 0013 -> head` 服务关闭迁移演练，身份/凭据/邀请数据保留 |
| 后端非 PG | 1765 PASS、18 条件 skip | 33 个 PG 标记另行 33/33 执行；skip 为既有环境/条件路径，不是 Gate 3B 行为豁免 |

## 升级与回退

- 客户端请求携带 `X-Client-Platform: android` 与受控 `X-Client-Version-Code`；候选服务在领域路由前
  拒绝缺失、格式错误、过旧和高于上限的版本。
- 分发顺序固定为先扩服务端兼容窗口，再分发新 APK，最后在观察窗后提高最小版本；不能先提高
  最小版本导致存量客户端突然失效。
- APK 回退只允许回到兼容 `0014/head` 的已验收版本。数据库 downgrade 到 `0013` 时服务必须关闭，
  re-upgrade 和隐私/删除证据检查通过后才可恢复。
- 详细止损和恢复步骤见 `phase9-controlled-trial-runbook.md`。

## 边界

设备矩阵是合成工程证据，不是实体机覆盖、蜂窝运营商网络、真实分发、真实数据、部署或发布批准。
法律/隐私、健康专业和独立安全审查仍为 `not obtained`。
