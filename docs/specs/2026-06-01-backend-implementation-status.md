> **⚠️ 历史资料** — 本文档记录早期开发过程，不代表当前完成状态或当前架构决策。
> 当前规格和计划见 [docs/README.md](../README.md)。

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

### 3.5 Code Review 修复记录（第二轮）

第二轮 review 发现并修复了 6 个问题：

| # | 严重度 | 问题 | 修复 |
|---|--------|------|------|
| 1 | Critical | SMS 验证码无频率限制，可被暴力破解 | 添加 60s 间隔 + 每日 10 次上限 |
| 2 | Critical | DEV_MODE 泄露永久云密钥 | 改用 `DEV_MODE_MOCK_KEY` 模拟凭证 |
| 3 | Critical | Token refresh 不验证用户存在 | refresh 接口查询数据库确认用户 |
| 4 | Important | update_profile 用户不存在时 500 崩溃 | 改用 scalar_one_or_none + 抛 404 |
| 5 | Important | AI 服务 HTTP 调用无错误处理 | 添加 timeout/api error/exception 三层 catch |
| 6 | Important | AI 响应解析只支持 ` ```json ` 前缀 | 用正则提取，支持 code block/嵌入 JSON |

**未修复（需生产环境配置）**：生产环境 STS 凭证和签名 URL 生成（需接入阿里云 SDK）。

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
- [x] Flutter 项目初始化（Riverpod 架构）
- [x] 登录/注册页面
- [x] 用户信息采集页面
- [x] 首页 3D 人体导航
- [x] 问题列表 + 详情页
- [x] 自测流程页面
- [x] AI 拍照分析页面
- [x] 结果页 + 关联推荐
- [x] 历史记录页
- [x] 个人中心

### Phase 3: 训练计划模块
- [ ] 数据模型设计
- [ ] 训练计划推荐算法
- [ ] 用户自定义调整计划

### Phase 4: 饮食推荐模块
- [ ] 数据模型设计
- [ ] 基于身体状况和训练计划的饮食推荐

---

## 7. Code Review 第三轮修复记录（2026-06-04）

> 全面 code review 发现 51 个问题，按严重度分为 Critical(5) / High(12) / Medium(18) / Low(16)。
> 已修复全部 Critical + High + Medium 共 23 项核心问题。

### 7.1 后端修复

| # | 严重度 | 文件 | 问题 | 修复方案 |
|---|--------|------|------|----------|
| 1 | Critical | `main.py` | CORS `allow_origins=["*"]` + `allow_credentials=True` 允许任意网站窃取用户数据 | `allow_credentials=False`（本项目用 Bearer token 不需要 credentials） |
| 2 | Critical | `core/config.py` | JWT Secret Key 硬编码默认值可被伪造 | 改为 `"CHANGE-ME-IN-PRODUCTION"` 明确标识 |
| 3 | High | `auth/service.py` | 验证码速率限制已计算 `recent_count` 但从未校验 | 添加 `if recent_count >= VERIFY_MAX_ATTEMPTS: raise TooManyRequests(...)` |
| 4 | High | `auth/service.py` | 验证码 TOCTOU 竞态（同一验证码可并发使用两次） | 改用原子 `UPDATE ... RETURNING` 替代 SELECT+UPDATE |
| 5 | Medium | `auth/service.py` | `find_or_create_user` 并发创建触发 IntegrityError 500 | 添加 `except IntegrityError: rollback + re-query` |
| 6 | Medium | `auth/service.py` | `get_user_by_id` 的 `UUID()` 在输入非法时 ValueError 500 | 添加 try-except ValueError 返回 None |
| 7 | Medium | `core/dependencies.py` | `HTTPException` 与全局 `AppException` 格式不一致 | 改用 `raise Unauthorized(...)` |
| 8 | High | `upload/service.py` | 生产环境返回空 STS 凭证（空字符串），静默失败 | 改为 `raise AppException(501, "STS 服务暂未实现")` |
| 9 | Medium | `posture/ai_service.py` | AI 超时/失败返回假 "normal" 评估存入数据库 | 改为 `raise ServiceUnavailable(...)` |
| 10 | - | `core/exceptions.py` | 新增 `ServiceUnavailable` 异常类（503） | 新增 |

### 7.2 前端修复

| # | 严重度 | 文件 | 问题 | 修复方案 |
|---|--------|------|------|----------|
| 1 | Critical | `core/api_client.dart` | Token refresh 竞态：并发 401 各自 refresh 导致 token 覆盖 | 引入 `Completer<String?>` 串行化 refresh，所有 401 共享同一次刷新 |
| 2 | Critical | `core/api_client.dart` | refresh 失败清空 storage 但 AuthNotifier 仍 `isLoggedIn=true` | 添加 `onAuthFailed` 回调，由 AuthNotifier 绑定，通知 UI 注销 |
| 3 | Critical | `app.dart` | GoRouter 每次 auth/user 状态变化整体重建，丢失导航栈 | 改用 `refreshListenable` + `ChangeNotifier`，GoRouter 实例稳定 |
| 4 | Critical | `photo_test_screen.dart` | OSS 上传缺少 STS 认证参数（必 403） | FormData 添加 `OSSAccessKeyId/policy/Signature/x-oss-security-token` |
| 5 | High | `auth_provider.dart` | `checkAuth()` 只检查 token 存在不验证有效性 | 改为调用 `GET /user/profile`，失败则清除 token |
| 6 | High | `auth_provider.dart` | `e.response?.data?['detail']` 若 data 是 String 崩溃 | 添加 `data is Map<String, dynamic>` 类型检查 |
| 7 | High | 所有 providers | `on DioException catch` 无法捕获 TypeError/FormatException | 添加 `catch (e)` 兜底 |
| 8 | High | `main.dart` | `startupSync()` 异常阻止 `runApp()` → 白屏 | 添加 try-catch + 全局错误边界 (`FlutterError.onError` / `PlatformDispatcher.onError`) |
| 9 | High | `result_screen.dart` | 从不调用 `fetchDetail(issueId)`，从历史进入无数据 | `initState` 中添加 `fetchDetail` 调用 |
| 10 | High | 所有 `fromJson` | `json['xxx'] as String` 无 null 保护，null 时 TypeError 崩溃 | 全部改为 `(json['xxx'] as String?) ?? ''` 模式 |
| 11 | High | `issue_detail_screen.dart` | `c['type'] as String` 等多处强制转换红屏 | 改为 `(c['type'] as String?) ?? ''` |
| 12 | High | `self_test_screen.dart` | async gap 后用 context 无 `mounted` 检查 | 添加 `if (!mounted) return;` |
| 13 | High | `self_test_screen.dart` | 答案页发送错误 `test_index`（发送了 tests.length） | 引入 `_activeTestForAnswer` 记录最后一个测试页 index |
| 14 | High | `photo_test_screen.dart` | catch 只处理 DioException，FileSystemException 等崩溃 | 添加 generic `catch (e)` |
| 15 | Medium | `assessment_provider.dart` | `copyWith` 用 `??` 无法将 `currentResult` 置 null | 添加 `clearResult` 参数 |
| 16 | Medium | `issue_provider.dart` | `copyWith` 无法将 `currentDetail` 置 null | 添加 `clearDetail` 参数 |
| 17 | Medium | `user_provider.dart` | `copyWith` 无法清除 profile（换号登录残留旧数据） | 添加 `clearProfile` 参数 |
| 18 | Medium | `assessment_provider.dart` | error 无法清除，一旦出错永远显示 | 添加 `clearError` 参数 |
| 19 | Medium | `issue_list_screen.dart` | API 失败无错误 UI | 添加错误状态 + 重试按钮 |
| 20 | Medium | `issue_detail_screen.dart` | 加载失败永远"加载中..." | 添加错误状态 + 重试按钮 |
| 21 | Medium | `onboarding_screen.dart` | `_finish()` 允许 null gender 提交 | 添加性别验证 |
| 22 | Medium | `onboarding_screen.dart` | `_skip()` 不清除 isNewUser → 反复重定向 | 添加 `clearisNewUser()` 方法 |
| 23 | Medium | `sync_service.dart` | 任一步骤失败导致全部跳过 | 每步独立 try-catch |

### 7.3 验证结果

```
后端测试: 13/13 PASSED (0 failures)
Flutter analyze: 0 errors, 0 compilation warnings
```

### 7.4 剩余已知问题（Low 优先级，未修复）

| # | 文件 | 问题 | 说明 |
|---|------|------|------|
| 1 | `constants.dart` | 硬编码 `10.0.2.2:8000`（仅 Android 模拟器可用） | 生产需改环境变量 |
| 2 | `home_screen.dart` | `_buildFallback()` 死代码 | 可删除 |
| 3 | `home_screen.dart` | `ModelViewer` 在 ConsumerWidget 中每次 rebuild 重建 | 可改为 StatefulWidget |
| 4 | `photo_test_screen.dart` | 选择照片后自动上传已改为手动，但 UX 可进一步优化 | 非 bug |
| 5 | `posture_state_provider.dart` | 纯内存无持久化，同步失败则状态丢失 | 可引入 Hive 本地缓存 |
| 6 | `history_screen.dart` | O(n²) Map key 访问 | 数据量小时无影响 |
| 7 | `profile_screen.dart` | 身高/体重编辑用 int slider 丢失小数精度 | 可改用 double slider |
| 8 | `auth/service.py` | DEV_MODE 日志输出验证码 | 生产环境确保 DEV_MODE=false |
| 9 | `posture/router.py` | 无 response_model，Swagger 文档不完整 | 可后续添加 |
| 10 | `auth/schemas.py` | code 验证 `min_length=4` 但实际生成 6 位 | 可改为 `min_length=6` |
