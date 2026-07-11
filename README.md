# 个人体态健康教练 Agent

体态评估为核心的个人健康教练，Flutter + FastAPI 架构。

当前阶段：基线收敛（阶段 0）

## 运行时要求

| 工具 | 版本 |
| --- | --- |
| Python | 3.9.13 |
| Flutter | 3.44.0 |
| Dart | 3.12.0 |
| Java | 21.0.10 |
| Android SDK | 36.1.0（需要 command-line tools） |

## 后端

新环境按以下顺序启动（首次需要初始化数据库 schema）：

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env                     # 按需修改，设置 DATABASE_URL 指向你的 PostgreSQL
python -m alembic upgrade head           # 在空数据库上创建当前完整 schema
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 数据库 schema（Alembic）

schema 生命周期由 Alembic 管理，URL 从 `DATABASE_URL` 环境配置读取，`alembic.ini` 不含凭据。

```bash
cd backend
python -m alembic upgrade head           # 升级到最新 schema
python -m alembic current                # 查看当前 revision
python -m alembic downgrade base         # 回退到空库（会删除所有表和数据）
```

> **警告：`downgrade` 会删除表和其中的全部数据。** 只能对可丢弃的开发数据库执行，
> 不要对包含真实或需要保留数据的数据库运行 `downgrade`。

FastAPI 启动时**不会**自动建表；必须先运行 `alembic upgrade head`。
测试使用文件型 SQLite 测试数据库 `./test.db`（`conftest.py` 自动建表和删表），
不依赖 PostgreSQL，也不使用 Alembic migration。

### 测试

```bash
cd backend
python -m pytest tests -q
```

### API 文档

启动后端后访问 `http://127.0.0.1:8000/docs` 查看 OpenAPI 文档。

## Flutter 客户端

```bash
cd app
flutter pub get
flutter analyze
flutter test
```

### 编译参数

| 参数 | 默认值 | 用途 |
| --- | --- | --- |
| `API_BASE_URL` | `http://10.0.2.2:8000/api/v1` | 后端 API 地址 |
| `PHOTO_ANALYSIS_ENABLED` | `false` | 是否启用照片分析入口 |

不得通过 `--dart-define` 传递 Token、密码或云服务密钥。

### 运行（Android 模拟器）

```bash
flutter run
```

默认使用 Android 模拟器宿主机地址。覆盖示例（宿主机换端口）：

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:9000/api/v1
```

## 数据模式

当前默认只使用合成数据。禁止使用真实照片或真实健康数据。

照片上传和分析路径已默认关闭（`PHOTO_ANALYSIS_ENABLED=false`）。前后端都必须显式启用，后端是最终授权边界。启用前需完成隐私告知、同意、STS 凭证、保存期限和删除策略。

## 项目结构

```
health/
├── app/              # Flutter 客户端
├── backend/          # FastAPI 后端
├── docs/             # 产品、规格和计划文档
│   ├── product/      # 愿景、安全边界、路线图
│   ├── specs/        # 功能规格
│   └── plans/        # 实施计划
└── tools/            # 开发工具
```

## 已知限制

- 当前源码 APK 已可构建/安装/启动到登录页；完整业务冒烟（登录→问题→详情→自测→结果→历史）依赖真实后端与 PostgreSQL，尚未执行
- Android command-line tools 缺失，`flutter doctor --android-licenses` 无法执行（工具链告警，不阻塞构建或模拟器）
- 照片分析默认关闭，隐私门和 STS 凭证尚未实现
- 当前仅有体态问题浏览、图示自测和评估历史功能
- AI 模型不可用时返回 503，不降级为正常结果
- Alembic 初始 migration 仅完成离线 SQL 验证；真实 PostgreSQL 的
  upgrade / downgrade / re-upgrade 演练尚未执行（本机无可丢弃 PostgreSQL）

## Windows 构建前置

在 Windows 上首次构建 Android APK 前，必须启用 **开发者模式**（Developer Mode），
否则 Flutter 在创建插件 symlink 时会中止并提示
“Building with plugins requires symlink support”，Gradle 不会启动。

```powershell
start ms-settings:developers   # 打开设置并启用开发者模式
```

启用后 `flutter build apk --debug` 才能进入 Gradle 构建。

## 当前测试状态

| 验证项 | 结果 | 日期 |
| --- | --- | --- |
| 后端 pytest | 81 passed | 2026-07-11 |
| Alembic 离线 upgrade/downgrade SQL | 通过 | 2026-07-11 |
| 真实 PostgreSQL 迁移演练 | 未执行（无可丢弃 PostgreSQL） | — |
| Flutter analyze | No issues found | 2026-07-11 |
| Flutter test | 7 passed | 2026-07-11 |
| 当前源码 APK 构建 | 成功（app-debug.apk） | 2026-07-11 |
| 当前源码 APK 安装/启动 | 成功（emulator-5554，登录页无崩溃） | 2026-07-11 |
| Android 完整业务冒烟 | 未执行（依赖真实后端/PostgreSQL） | — |
