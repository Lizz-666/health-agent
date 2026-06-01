# 后端实现进展与踩坑记录

> 日期: 2026-06-01
> 状态: 体态分析模块后端 MVP 完成，前端待开发

---

## 1. 当前完成状态

### 已完成模块

| 模块 | 文件 | 状态 |
|------|------|------|
| 项目配置 | `app/core/config.py` | 完成 |
| JWT 安全 | `app/core/security.py` | 完成 |
| 异常处理 | `app/core/exceptions.py` | 完成 |
| 依赖注入 | `app/core/dependencies.py` | 完成 |
| 数据库 | `app/db/database.py`, `app/db/base.py` | 完成 |
| 认证模型 | `app/auth/models.py` | 完成 |
| 认证接口 | `app/auth/router.py`, `service.py`, `schemas.py` | 完成 |
| 用户模块 | `app/user/router.py`, `service.py`, `schemas.py` | 完成 |
| 体态知识库 | `app/posture/knowledge.py` + 5 个 JSON 文件 | 完成 |
| 体态评估服务 | `app/posture/service.py` | 完成 |
| AI 分析 | `app/posture/ai_service.py` | 完成 |
| 体态路由 | `app/posture/router.py` | 完成 |
| OSS 上传 | `app/upload/router.py`, `service.py` | 完成 |
| FastAPI 入口 | `app/main.py` | 完成 |
| 测试 | `tests/` (13 个测试全部通过) | 完成 |

### 未完成

| 任务 | 说明 |
|------|------|
| Alembic 迁移 | 需连接 PostgreSQL 迧行 `alembic revision --autogenerate` |
| Flutter 前端 | 整个 App 端未开始 |
| 短信发送 | `send_verification_code` 中短信调用为 TODO |
| STS 凭证 | 生产环境需接入阿里云 STS SDK |
| 体态问题数据完善 | 部分 JSON 数据的 corrections/content 需补充 |

---

## 2. 关键设计决策

### 2.1 统一登录/注册（无密码）

用户首次验证码登录自动注册，无需单独注册接口。`verify-login` 接口返回 `is_new_user` 标识。

### 2.2 体态知识库用 JSON 文件而非数据库

26 个体态问题以 JSON 文件形式按身体区域拆分为 5 个文件存储在 `app/posture/data/` 目录下，运行时加载并缓存。理由：
- 内容稳定、低频更新
- 避免 seed 脚本和迁移复杂度
- 便于版本控制

### 2.3 评估记录存数据库

用户评估结果存 `posture_assessments` 表，与知识库分离。查询历史走数据库。

---

## 3. 踩坑记录

### 3.1 Python 3.9 兼容性

**问题**: Python 3.9 不支持 `str | None`、`list[X]`、`tuple[X, Y]` 等类型标注语法。

**解决方案**: 全部改用 `Optional[X]`、`List[X]`、`Tuple[X, Y]`。注意不能用 `from __future__ import annotations`，因为与 SQLAlchemy 的 `Mapped` 注解冲突。

**涉及文件**: `app/auth/models.py`, 所有 `schemas.py`, `app/posture/ai_service.py`

### 3.2 PostgreSQL UUID 类型在 SQLite 测试中不可用

**问题**: 生产用 PostgreSQL（UUID 类型），测试用 SQLite（无原生 UUID），导致 `InterfaceError: Error binding parameter`。

**解决方案** (`tests/conftest.py`):
1. 创建 `_SQLiteUUID(String)` 类替代 `pg.UUID`，实现 `bind_processor`（UUID→str）和 `result_processor`（str→UUID）
2. `sqlite3.register_adapter(_uuid.UUID, lambda u: str(u))`
3. `pg.JSONB = JSON`（JSONB→JSON 适配）
4. `_SQLiteUUID.coerce_compared_value` 确保 WHERE 比较时参数也被转换
5. aiosqlite `_execute` monkey-patch 转换 UUID 参数

**注意**: 这套适配方案是为了让同一套 ORM 模型在 PostgreSQL（生产）和 SQLite（测试）下都能工作。如果未来切换到 PostgreSQL 测试，可移除这些 patch。

### 3.3 SQLite 测试中跨 Session 事务隔离问题

**问题**: `test_verify_login_existing_user` 失败。`_get_code` 打开独立 `TestSession()` 读取验证码，但看不到 API session 已提交的数据（SQLite StaticPool 共享连接导致事务状态混乱）。

**解决方案**: 不再从数据库读验证码。用 `unittest.mock.patch("app.auth.service.random.randint")` 控制验证码生成值，测试直接使用已知验证码。

```python
with patch("app.auth.service.random.randint", side_effect=[111111, 222222]):
    await client.post("/api/v1/auth/send-code", json={"phone": "13800138001"})
    resp1 = await client.post("/api/v1/auth/verify-login", json={"phone": "13800138001", "code": "111111"})
    # ...
```

### 3.4 Agent 生成的 JSON 字段名错误

**问题**: `lower_limb.json` 和 `compound.json` 中部分条目使用了 `"name"` 而非 `"name_cn"`。

**解决方案**: 脚本批量修复，将 `"name"` key 替换为 `"name_cn"`。检查所有 JSON 文件确保字段一致。

---

## 4. 测试运行方式

```bash
cd health/backend
python -m pytest tests/ -v
```

当前 13 个测试全部通过：
- `test_auth.py`: 4 个（发送验证码、首次登录创建用户、已有用户登录、错误验证码）
- `test_posture.py`: 7 个（列表、分类筛选、详情、自评、阴性自评、历史记录、关联推荐）
- `test_user.py`: 2 个（获取资料、更新资料）

### 测试注意事项

- 测试使用 SQLite (`test.db`)，每个测试函数自动建表/删表
- `DEV_MODE = True` 时验证码打印到日志而非发送短信
- conftest.py 中的 monkey-patch 仅用于测试环境

---

## 5. 环境变量

在 `health/backend/.env` 中配置（不提交到 Git）：

```env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/health
SECRET_KEY=your-secret-key
DASHSCOPE_API_KEY=your-dashscope-key
DEV_MODE=true

# OSS（生产环境需要）
OSS_ACCESS_KEY_ID=
OSS_ACCESS_KEY_SECRET=
OSS_ENDPOINT=
OSS_BUCKET_NAME=
```

---

## 6. 后续开发路线图

### Phase 1: Alembic + 部署准备
- [ ] 配置 Alembic 迁移（需 PostgreSQL）
- [ ] 接入阿里云短信 SDK
- [ ] 接入阿里云 STS 临时凭证
- [ ] 生产环境 `.env` 配置

### Phase 2: Flutter 前端
- [ ] Flutter 项目初始化（Riverpod 架构）
- [ ] 登录/注册页面
- [ ] 用户信息采集页面
- [ ] 首页 3D 人体导航
- [ ] 问题列表 + 详情页
- [ ] 自测流程页面
- [ ] AI 拍照分析页面
- [ ] 结果页 + 关联推荐
- [ ] 历史记录页
- [ ] 个人中心

### Phase 3: 训练计划模块
- [ ] 数据模型设计
- [ ] 训练计划推荐算法
- [ ] 用户自定义调整计划

### Phase 4: 饮食推荐模块
- [ ] 数据模型设计
- [ ] 基于身体状况和训练计划的饮食推荐
