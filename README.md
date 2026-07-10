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

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # 按需修改
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

> **注意：数据库初始化缺失。** 当前仓库没有 Alembic migration 或自动建表逻辑。
> `uvicorn` 启动后如果 PostgreSQL 中不存在对应表，API 调用会失败。
> 测试使用文件型 SQLite 测试数据库 `./test.db`（`conftest.py` 自动建表和删表），不依赖 PostgreSQL。
> 此问题已记录为 Phase 0 阻塞项，需要后续任务补齐数据库初始化方式。

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

- Android command-line tools 缺失，license 状态未确认，Android 冒烟未完成
- 照片分析默认关闭，隐私门和 STS 凭证尚未实现
- 当前仅有体态问题浏览、图示自测和评估历史功能
- AI 模型不可用时返回 503，不降级为正常结果

## 当前测试状态

| 验证项 | 结果 | 日期 |
| --- | --- | --- |
| 后端 pytest | 69 passed | 2026-07-10 |
| Flutter analyze | No issues found | 2026-07-10 |
| Flutter test | 7 passed | 2026-07-10 |
| Android 冒烟 | 未执行（环境阻塞） | — |
