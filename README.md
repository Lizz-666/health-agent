# 个人体态健康教练 Agent

体态评估为核心的个人健康教练，Flutter + FastAPI 架构。

当前阶段：阶段 6（普通饮食推荐 MVP）已完成工程验收；功能默认关闭，仅批准使用合成数据进行个人开发验证。详见 `docs/reports/phase6-codex-exit-audit-2026-08-02.md`。

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

生产/开发后端依赖 PostgreSQL 16。默认 pytest/Fast 使用文件型 SQLite；严格 Full
还会在一次性 PostgreSQL 16 中运行标记的迁移、约束和并发集成测试。

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
默认测试使用文件型 SQLite 测试数据库 `./test.db`（`conftest.py` 自动建表和删表），
不使用 Alembic migration；严格 Full 的 `requires_pg` 用例另行使用可丢弃 PostgreSQL 16。

### 测试

```bash
cd backend
python -m pytest tests -q
```

### 分层验证（Phase 3 起）

仓库提供共享本地验证入口 `scripts/verify.py`（从仓库根运行），并配置 GitHub
Actions 分层 CI（`.github/workflows/ci.yml`）。三层定义见
`docs/product/roadmap.md` 第 13.1 节：

| 层级 | 命令 | 内容 |
| --- | --- | --- |
| Local focused | `python scripts/verify.py fast` | ruff（`app tests scripts`）+ Phase 3 定向 SQLite 测试 + `git diff --check` |
| Local full | `python scripts/verify.py full` | ruff + 后端全量测试；Docker/`PG_TEST_DSN` 可用时跑真实 PostgreSQL 16 |

`fast` 明确禁用 PostgreSQL 用例；`full` 设置 `VERIFY_REQUIRE_PG=1` 时会核对
预期/实际 PostgreSQL 用例数，且任何跳过都算硬失败。

`ruff` 与 `hypothesis` 是开发/CI 工具，刻意不放入 `backend/requirements.txt`
（非运行时依赖）。本地需自行安装：

```bash
pip install ruff==0.15.22            # lint（fast/full 必需）
pip install hypothesis==6.141.1      # 仅 Task 5 起的 property 测试需要
```

GitHub Actions：

- `fast` 在 push/PR 到 `codex/phase3-*` 分支时运行；`full` 在每个 PR 或
  `workflow_dispatch`（勾选 `run_full`）时运行，用于集成/阶段退出节点。
- 第三方 Action 固定到审查过的 immutable commit SHA（不用浮动 tag）；
  默认权限 `contents: read`；不部署、不发布、不使用生产密钥或真实健康数据；
  同分支取消过时 run；每个 job 有显式超时；pip 缓存不含密钥。
- 远程 CI 在用户首次授权 push 前为 `not authorized / not run`；本地
  `verify.py` 结果是本地证据，不得描述为 CI 结果。

### API 文档

启动后端后访问 `http://127.0.0.1:8000/docs` 查看 OpenAPI 文档。

营养建议 API 由后端 `NUTRITION_RUNTIME_ENABLED` 开关控制，默认关闭。Phase 6 的迁移、
发布审计、客户端流程和 Android 合成数据验收已通过；个人开发时可在 `backend/.env`
中设置 `NUTRITION_RUNTIME_ENABLED=true`。该授权不覆盖真实健康数据或生产流量。
关闭时，营养数据删除接口仍保持可用。

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
- 当前已包含体态、健康档案/签到、训练计划、受控 Agent 和普通饮食建议；营养与 live Agent 运行时默认关闭
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
| 后端 pytest（全量，含真实 PostgreSQL 16 集成） | 798 passed，0 skipped | 2026-07-26 |
| 后端 Phase 2 E2E + OpenAPI + 迁移 | 137 passed（含 Phase 2 E2E 6 项） | 2026-07-26 |
| Alembic 迁移头/CLI 升级 | 单一头 `0006_health_weight_tracking`；一次性 PG16 容器 `upgrade head/current` 通过 | 2026-07-26 |
| 真实 PostgreSQL 集成（UUID/JSONB/advisory lock） | 11 passed，0 skipped（Docker `postgres:16`） | 2026-07-26 |
| 后端 ruff（`app tests`） | All checks passed | 2026-07-26 |
| Flutter analyze | No issues found | 2026-07-26 |
| Flutter test | 300 passed | 2026-07-26 |
| Android（阶段 2） | Pixel 6 AVD 构建、安装、启动（MainActivity resumed）+ 一次性 PG16/uvicorn 实时旅程 15/15 + 300 widget；人工逐屏冒烟由用户决定跳过（接受残余风险） | 2026-07-26 |
| 后端（阶段 6，严格 Full） | 1569 passed，0 failed，0 skipped；PostgreSQL 16 专项 23/23 | 2026-08-02 |
| Flutter（阶段 6） | analyze 无问题；384 tests passed | 2026-08-02 |
| Android（阶段 6） | Pixel 6 AVD / API 34：营养启用与禁用集成测试 2/2；带 API define 的 APK 构建、安装、MainActivity resumed | 2026-08-02 |
| GitHub CI（阶段 6） | exact SHA `1ff8395`，run `30730437996`：Fast/Flutter/Full 全通过 | 2026-08-02 |

### 依赖升级记录

- `image_picker_android`：0.8.13+17 → 0.8.13+19（通过 `flutter pub upgrade image_picker_android`，仅此一个传递依赖变动；`image_picker` 主依赖保持 1.2.2 不变）。旧版本 0.8.13+17 会触发 Flutter 的 KGP 兼容性警告（“applies Kotlin Gradle Plugin / Future versions of Flutter will fail to build”），升级后 `flutter build apk --debug` 日志中该警告已消失。
