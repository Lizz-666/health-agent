# Phase 9 Android 可靠性矩阵

> 执行日期：2026-08-13
> 实现 exact SHA：`9c5670714fd113061948c1daf2315f3e2dbde9e1`
> 数据边界：固定合成账号、邀请码、凭据和可丢弃 SQLite；无真实健康数据、照片、联系方式或生产凭据

## 设备矩阵

| AVD | Android | API | ABI | 主路径 | 服务不可达 | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
| `Pixel_6` / `emulator-5554` | 14 | 34 | `x86_64` | 4/4 | 1/1 | PASS |
| `Phase9_API_28` / `emulator-5554` | 9 | 28 | `google_apis/x86_64` | 4/4 | 1/1 | PASS |

API 28 使用 Android 官方 `system-images;android-28;google_apis;x86_64` revision 11；
AVD 配置固定 `target=android-28`、`hw.device.name=pixel_2`。两个 AVD 串行执行，测试后均正常关闭。

## 主路径覆盖

`phase9_controlled_trial_test.dart` 在两个 API 上均覆盖：

1. 唯一邀请码激活、单机设备键、后台暂停/恢复和 600 ms 合成慢响应；
2. session 过期后请求失败、access/refresh 清除、用户态清空并回到认证；
3. session 撤销后的同等 fail-closed 清态；
4. 服务端兼容窗口拒绝客户端时返回 `426`，客户端清态并进入版本阻断页，领域写入未发生。

`phase9_unreachable_test.dart` 在两个 API 上均把候选 API 固定到不可达端口 `65533`，只通过
本机合成服务预置 session；Today 进入 network error，不显示调整或打卡写按钮，保留显式重试，
重试后仍不伪造成功状态。

## 非设备矩阵

| Surface | 结果 | 关键证明 |
| --- | --- | --- |
| 真实本机 HTTP | 11/11 PASS | 两个独立账号、邀请重放、设备冲突、refresh rotation/replay、慢响应显式重试、426 零写入、撤销、过期、零残留 |
| `Asia/Shanghai` | 2/2 PASS | UTC 注入跨本地午夜与周日到周一周界，客户端日期不覆盖服务端推导 |
| Flutter 单元/widget | 531/531 PASS | 401 并发只 refresh 一次、迟到旧 401 复用新 token、426 清态、重复认证提交只有一次请求 |
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
