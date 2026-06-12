# 开发基线收敛实施计划

**Goal:** 让当前体态 MVP 在合成数据模式下可重复启动、验证，并消除阻碍阶段 1 的配置、API 契约和 AI 安全缺口。

**Spec:** [开发基线收敛规格](../../specs/platform/2026-06-12-baseline-contract.md)

**Architecture:** 保持 Flutter + Riverpod 客户端和 FastAPI 模块化单体；本计划只收敛平台基线，不引入新领域模块。

**Safety:** 照片分析默认关闭；AI 失败不得转化为 `normal`；测试不得使用真实健康数据。

**Verification:** `python -m pytest tests -q`、`flutter analyze`、`flutter test`、OpenAPI 契约测试和 Android 模拟器冒烟。

## Execution Rules

- 每次只把一个 Task 交给 Claude Code。
- 每个 Task 独立提交；不要把多个任务合并为一次大改。
- Claude 开始前必须运行 `git status --short`。
- 当前 `docs/product/vision.md`、`docs/product/safety-boundaries.md` 和 `docs/product/roadmap.md` 已有未提交修改，不得覆盖或回退。
- 不修改 `issue.md`，不把旧计划中的健康结论复制到当前规则。
- 不使用真实照片、真实健康档案或真实密钥。
- Claude 完成后由 Codex 检查真实 diff，并重新运行任务验证。

## Current Baseline

```text
Python 3.9.13
Flutter 3.44.0
Dart 3.12.0
Java 21.0.10
Backend: 15 tests passed
Flutter: analyze passed, 1 test passed
Android: SDK and Pixel_6 emulator found
Blocker: Android cmdline-tools missing and licenses unresolved
```

## File Map

| Area | Likely files |
| --- | --- |
| Runtime/config | `README.md`, `backend/app/core/config.py`, `backend/.env.example`, `backend/pytest.ini` |
| Flutter API config | `app/lib/core/constants.dart`, `app/test/core/constants_test.dart` |
| Photo data gate | backend config/routers, Flutter constants and photo screens, focused tests |
| AI validation | `backend/app/posture/ai_service.py`, posture schemas/service, focused tests |
| API contracts | `backend/app/posture/schemas.py`, `backend/app/posture/router.py`, posture tests |
| Documentation | `docs/README.md`, historical plans/specs, this spec and plan |

## Tasks

### Task 1: 固化运行时、测试配置和启动文档

**Status:** [x]

**Files:**

- Create: `README.md`
- Create: `backend/pytest.ini`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`

**Behavior:**

- 记录当前支持的 Python、Flutter、Dart、Java 和 Android 工具链。
- 给出后端安装、启动、测试和 Flutter analyze/test/run 命令。
- 将 Pydantic `class Config` 迁移为当前 v2 配置方式，同时保持 Python 3.9 兼容。
- 显式设置 pytest asyncio fixture loop scope，消除当前警告。
- `.env.example` 保持纯占位值，不包含真实凭据。
- 不在此任务安装 Android SDK 组件，也不更改业务行为。

**Tests/Evals:**

```powershell
cd backend
python -m pytest tests -q

cd ..\app
flutter analyze
flutter test
```

**Done when:**

- 三条验证命令通过。
- Pydantic 配置和 pytest loop scope 的当前弃用警告消失。
- 新开发者可仅依据根目录 README 启动后端并找到 Flutter 运行命令。

**Suggested commit:** `chore: document and stabilize local runtime baseline`

### Task 2: 让 Flutter API 地址可配置

**Status:** [x]

**Files:**

- Modify: `app/lib/core/constants.dart`
- Create: `app/test/core/constants_test.dart`
- Modify: `README.md`

**Behavior:**

- `AppConstants.apiBaseUrl` 从 `API_BASE_URL` 编译参数读取。
- 未提供参数时保留 `http://10.0.2.2:8000/api/v1` 作为 Android 模拟器开发默认值。
- 不把 Token、密码或云密钥放入编译参数。
- Dio 调用方继续只依赖 `AppConstants.apiBaseUrl`，不复制配置逻辑。

**Tests/Evals:**

```powershell
cd app
flutter test test/core/constants_test.dart
flutter test --dart-define=API_BASE_URL=http://127.0.0.1:8000/api/v1 test/core/constants_test.dart
flutter analyze
```

**Done when:**

- 默认地址和覆盖地址都有自动化证据。
- `rg "10\.0\.2\.2" app/lib` 只允许在集中配置的默认值中出现。

**Suggested commit:** `fix: make Flutter API endpoint configurable`

### Task 3: 默认关闭真实照片路径

**Status:** [ ]

**Files:**

- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/app/upload/router.py`
- Modify: `backend/app/posture/router.py`
- Create: `backend/tests/test_upload.py`
- Modify: `backend/tests/test_posture.py`
- Modify: `app/lib/core/constants.dart`
- Modify: `app/lib/screens/test/self_test_screen.dart`
- Modify: `app/lib/screens/test/photo_test_screen.dart`
- Create: `app/test/screens/photo_analysis_gate_test.dart`

**Behavior:**

- 后端增加 `PHOTO_ANALYSIS_ENABLED=false`，并作为最终门禁。
- 开关关闭时，上传凭证和照片分析接口在任何副作用前返回：

```json
{
  "detail": "照片分析在当前数据模式下未启用",
  "code": "photo_analysis_disabled"
}
```

- 状态码为 `503`。
- Flutter 增加同名布尔编译参数，默认关闭照片入口。
- 用户直接进入照片路由时仍只能看到明确的不可用说明，不能选择或上传照片。
- 此任务不实现同意 UX，不启用真实 STS，也不修复图片素材。

**Tests/Evals:**

```powershell
cd backend
python -m pytest tests/test_upload.py tests/test_posture.py -q

cd ..\app
flutter test test/screens/photo_analysis_gate_test.dart
flutter analyze
```

验证至少包括：

- 关闭时不调用 `generate_sts_credentials`。
- 关闭时不调用模型适配器。
- 关闭时不新增 `PostureAssessment`。
- Flutter 默认不提供可执行的照片上传操作。

**Done when:**

- 前后端默认关闭，且后端无法被客户端绕过。
- 所有门禁测试使用合成用户和占位数据。

**Suggested commit:** `fix: gate photo analysis behind explicit data mode`

### Task 4: 消除 AI 失败变成正常结果的路径

**Status:** [ ]

**Files:**

- Modify: `backend/app/posture/ai_service.py`
- Modify: `backend/app/posture/schemas.py`
- Modify: `backend/app/posture/service.py`
- Create: `backend/tests/test_posture_ai_service.py`
- Modify: `backend/tests/test_posture.py`

**Behavior:**

- 为模型输出定义类型化 schema，限制等级、置信度、证据和重拍字段。
- 超时、HTTP 错误、JSON 解析失败、缺失字段和非法枚举均返回明确不可用状态。
- 删除 `setdefault("level", "normal")` 等静默健康降级。
- 无效 issue 不返回 `normal`。
- 只有完成 schema 校验的结果才能进入 `save_photo_assessment`。
- 日志不记录完整模型响应、照片 URL 或用户健康档案。
- 将内部模型角色表述改为“体态筛查辅助”，不宣称替代专业康复评估。

**Tests/Evals:**

```powershell
cd backend
python -m pytest tests/test_posture_ai_service.py tests/test_posture.py -q
python -m pytest tests -q
```

验证至少包括：

- 超时返回 `503`。
- 非 JSON 返回 `503`。
- `level` 缺失或非法返回 `503`。
- 失败后数据库评估记录数不变。
- 合法结构能够通过验证，但测试不调用真实模型。

**Done when:**

- 代码中不存在把解析失败、缺失字段或模型异常转成 `normal` 的路径。
- 测试不依赖 DashScope 网络或真实密钥。

**Suggested commit:** `fix: reject invalid posture AI results`

### Task 5: 补齐体态 API response schema

**Status:** [ ]

**Files:**

- Modify: `backend/app/posture/schemas.py`
- Modify: `backend/app/posture/router.py`
- Modify: `backend/tests/test_posture.py`
- Create: `backend/tests/test_openapi_contracts.py`

**Behavior:**

- 为列表、详情、关联问题、评估结果和历史记录定义明确响应模型。
- 嵌套知识字段采用结构化 Pydantic 模型；仅对确实不固定的字段使用受限可选字段。
- 保持现有 Flutter 使用的 snake_case 字段和响应形状。
- response model 不得静默丢弃 Flutter 当前需要的字段。

**Tests/Evals:**

```powershell
cd backend
python -m pytest tests/test_posture.py tests/test_openapi_contracts.py -q
python -m pytest tests -q
```

验证至少包括：

- 六个体态路由在 OpenAPI 中具有响应 schema。
- 当前 26 个知识条目都能通过详情响应模型序列化。
- 列表、详情、自测和历史响应仍能被现有 Flutter 模型解析。

**Done when:**

- `/openapi.json` 不再把体态成功响应暴露为无约束对象。
- 完整后端测试通过。

**Suggested commit:** `feat: define posture API response contracts`

### Task 6: 整理当前文档并完成阶段 0 验收

**Status:** [ ]

**Files:**

- Create: `docs/README.md`
- Modify: `docs/plans/2026-06-01-backend-revised.md`
- Modify: `docs/plans/2026-06-01-posture-app-plan-v2.md`
- Modify: `docs/plans/2026-06-04-ui-redesign-glassmorphism.md`
- Modify: `docs/specs/2026-06-01-backend-implementation-status.md`
- Modify: `docs/specs/2026-06-01-posture-frontend-design.md`
- Modify: `docs/specs/2026-06-04-ui-redesign-spec.md`
- Modify: `docs/specs/2026-06-10-home-redesign.md`
- Modify: `docs/specs/platform/2026-06-12-baseline-contract.md`
- Modify only after all evidence passes: `docs/product/roadmap.md`

**Behavior:**

- `docs/README.md` 指明当前产品、安全、规格和计划入口。
- 旧计划和旧状态文档顶部标记“历史资料，不代表当前完成状态”。
- 不移动或删除历史文件。
- 记录最终运行版本、测试数量、Android 冒烟结果和已知限制。
- 只有全部退出标准有新鲜证据时，才在路线图中标记阶段 0 完成。

**Manual prerequisite:**

当前 `flutter doctor -v` 显示 Android command-line tools 缺失且 licenses 未确认。需要先通过 Android Studio SDK Manager 安装 command-line tools，并完成：

```powershell
flutter doctor --android-licenses
flutter doctor -v
flutter emulators --launch Pixel_6
flutter devices
```

不要把 Windows 桌面或 Chrome 冒烟替代 Android 验收。

**Tests/Evals:**

```powershell
cd backend
python -m pytest tests -q
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

cd ..\app
flutter analyze
flutter test
flutter run -d <android-device-id> --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1
```

Android 手工流程：

```text
开发登录
-> 浏览体态问题
-> 打开问题详情
-> 完成图示自测
-> 查看结果
-> 查看历史
-> 确认照片分析默认不可用
```

**Done when:**

- 后端完整测试、Flutter analyze 和 Flutter 测试全部通过。
- Android 核心流程通过。
- 当前文档与实际行为一致。
- 未解决项被列为限制，而不是被标记为完成。

**Suggested commit:** `docs: close phase zero baseline convergence`

## Claude Code Task Prompt

每次只替换下面的 `<TASK_NUMBER>`：

```text
先阅读：
- docs/product/vision.md
- docs/product/safety-boundaries.md
- docs/product/roadmap.md
- docs/specs/platform/2026-06-12-baseline-contract.md
- docs/plans/platform/2026-06-12-baseline-convergence.md

只执行实施计划中的 Task <TASK_NUMBER>。

要求：
1. 使用已安装的 Superpowers 工作流进行检查、测试驱动实现和验证。
2. 先运行 git status --short，并检查任务涉及的当前代码和测试。
3. 保留所有无关修改，尤其不要回退 docs/product 下的未提交修改。
4. 严格遵守 Files、Behavior、Tests/Evals 和 Done when。
5. 不扩展到其他 Task，不做无关重构或依赖升级。
6. 测试只使用合成数据，不使用真实照片、健康档案或密钥。
7. 对行为修复先添加失败测试，再做最小实现。
8. 运行任务列出的全部验证；失败时调查根因，不隐藏失败。
9. 不提交代码。
10. 完成后报告：
   - 修改文件
   - 关键行为变化
   - 运行的命令和实际结果
   - 剩余风险或未完成项
   - git diff --stat
```

## Review And Handoff

每个 Task 完成后：

1. Codex 检查任务范围和真实 diff。
2. Codex 先做规格符合性审查，再做工程质量与安全审查。
3. Claude Code 修复 P1/P2 findings。
4. Codex 重新运行该任务验证。
5. 用户确认后再提交，并进入下一个 Task。

阶段 0 未完成前，不开始阶段 1、训练计划、Agent 对话或饮食推荐。
