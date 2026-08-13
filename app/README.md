# 体态健康教练 Flutter 客户端

Android 优先的体态评估、健康签到、训练计划、营养建议和受控 Agent 客户端。

从仓库根 README 获取运行版本、`dart-define`、后端启动、验证和 release 签名要求。常用命令：

```bash
flutter pub get
flutter analyze
flutter test
flutter run
```

默认配置只用于本机 Android 模拟器开发。受控候选配置必须使用 HTTPS、
`AUTH_MODE=controlled_trial`、关闭照片入口，并遵守根目录发布门；不得把 token、密码或云密钥放入
`dart-define`。
