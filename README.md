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

### 运行（Android 模拟器）

```bash
flutter run
```

> **注意：** API 地址当前硬编码为 `http://10.0.2.2:8000/api/v1`（Android 模拟器宿主机地址）。Task 2 将改为通过 `--dart-define=API_BASE_URL=...` 覆盖。

## 数据模式

当前默认只使用合成数据。禁止使用真实照片或真实健康数据。

旧照片上传和分析路径尚未实现显式门禁，Task 3 将关闭该路径并要求显式启用。在门禁完成前，不得调用照片相关接口处理真实数据。

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

- Android command-line tools 缺失，license 状态未确认
- Flutter API 地址硬编码（Task 2 将处理）
- 照片路径无显式门禁（Task 3 将关闭该路径）
- 当前仅有体态问题浏览和图示自测功能
