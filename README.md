# 个人体态健康教练 Agent

体态评估为核心的个人健康教练，Flutter + FastAPI 架构。

当前阶段：阶段 0 已完成，下一步为阶段 1 规格设计

## 运行时要求

| 工具 | 版本 |
| --- | --- |
| Python | 3.9.13 |
| Flutter | 3.44.0 |
| Dart | 3.12.0 |
| Java | 21.0.10 |
| PostgreSQL | 16 |
| Android SDK | 36.1.0（需要 command-line tools） |

## 后端

### 准备 PostgreSQL 数据库

生产/开发后端依赖 PostgreSQL 16。测试（`pytest`）使用文件型 SQLite，不依赖 PostgreSQL。

**方式 A：使用已有 PostgreSQL 16**

以 PostgreSQL 管理员连接，先创建应用用户，再创建由该用户拥有的数据库（命令和用户名/库名按实际环境替换；`<your-password>` 替换为你的密码）：

```sql
-- 以 postgres 管理员执行
CREATE USER posture_app_user WITH PASSWORD '<your-password>';
CREATE DATABASE posture_app OWNER posture_app_user;
```

> 应用用户必须是数据库 owner（或被显式授予 `schema public` 的 `CREATE` 权限），
> 否则 `alembic upgrade head` 会在 `public` schema 上因 `permission denied for schema public` 失败。
> 不要仅依赖 `GRANT ALL PRIVILEGES ON DATABASE`，它不授予 schema 内的 `CREATE`。

**方式 B：使用 Docker（推荐用于可丢弃的开发环境）**

以下示例使用明确的容器名、命名卷和非默认端口（55432），避免与已有 PostgreSQL 冲突。
密码通过环境变量传入，不写入仓库：

```bash
# 设置一次性开发密码（仅当前终端生效，不提交）
export DEV_PG_PASSWORD='your-dev-password'

docker run -d \
  --name health-dev-pg \
  -e POSTGRES_PASSWORD="$DEV_PG_PASSWORD" \
  -e POSTGRES_DB=posture_app \
  -v health-dev-pgdata:/var/lib/postgresql/data \
  -p 55432:5432 \
  postgres:16

# 等待就绪
docker exec health-dev-pg pg_isready -U postgres
```

对应的 `DATABASE_URL`（写入 `backend/.env`，该文件已被 gitignore，不会提交）：

```text
DATABASE_URL=postgresql+asyncpg://postgres:your-dev-password@localhost:55432/posture_app
```

> **删除数据的风险**：以下命令会**永久删除卷中的所有数据**，只能在确认可丢弃时执行。
> 不要对包含需要保留数据的实例运行。
>
> ```bash
> docker stop health-dev-pg && docker rm health-dev-pg
> docker volume rm health-dev-pgdata   # 永久删除数据
> ```

### 启动后端

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

- Android command-line tools 缺失，`flutter doctor --android-licenses` 无法执行（工具链告警，不阻塞构建或模拟器）
- 照片分析默认关闭，隐私门和 STS 凭证尚未实现
- 当前仅有体态问题浏览、图示自测和评估历史功能
- AI 模型不可用时返回 503，不降级为正常结果
- 详情页首次加载偶现"加载失败"，重试后恢复
- 历史页登录后首次进入且评估记录为空时不提供下拉刷新入口

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
| 真实 PostgreSQL 迁移演练 | 通过（upgrade/downgrade base/re-upgrade + schema 核验） | 2026-07-11 |
| Flutter analyze | No issues found | 2026-07-11 |
| Flutter test | 7 passed | 2026-07-11 |
| 当前源码 APK 构建 | 成功（app-debug.apk，构建日志无 KGP 兼容性警告） | 2026-07-11 |
| 真实后端 API 流程 | 通过（health/login/issues/detail/assess/history） | 2026-07-11 |
| Android 完整业务冒烟 | 通过（登录→问题→详情→自测→结果→历史） | 2026-07-11 |

### 依赖升级记录

- `image_picker_android`：0.8.13+17 → 0.8.13+19（通过 `flutter pub upgrade image_picker_android`，仅此一个传递依赖变动；`image_picker` 主依赖保持 1.2.2 不变）。旧版本 0.8.13+17 会触发 Flutter 的 KGP 兼容性警告（“applies Kotlin Gradle Plugin / Future versions of Flutter will fail to build”），升级后 `flutter build apk --debug` 日志中该警告已消失。
