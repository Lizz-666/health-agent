# 开发基线收敛规格

> 日期：2026-06-12
> 状态：当前规格
> 对应路线图：阶段 0

## Outcome

建立一个可重复启动、可验证、默认只处理合成数据的 Flutter + FastAPI 开发基线，使后续体态产品化工作不再依赖硬编码配置、隐式运行环境、无类型 API 或不安全的 AI 降级行为。

## Non-Goals

- 不新增训练、营养或 Agent 功能
- 不实现公开发布所需的完整同意和隐私中心
- 不启用真实用户照片或真实健康数据测试
- 不更换 FastAPI、Riverpod、SQLAlchemy 或数据库架构
- 不重构现有体态知识库内容

## Current Evidence

2026-06-12 本机验证结果：

- Python `3.9.13`
- Flutter `3.44.0`
- Dart `3.12.0`
- Java `21.0.10`
- 后端测试：`15 passed`
- Flutter analyze：`No issues found`
- Flutter 测试：`1 passed`
- Android SDK `36.1.0` 已发现，存在 `Pixel_6` 模拟器
- Android command-line tools 缺失，license 状态未知，当前无 Android 设备连接

当前已确认的基线缺口：

- Flutter API 地址硬编码为 Android 模拟器地址
- 体态路由缺少明确的 response model
- pytest 和 Pydantic 存在弃用警告
- 真实照片路径没有开发期隐私门
- AI JSON 解析失败会降级为 `normal`
- 旧计划和旧状态文档没有统一标记为历史资料

## Users And Scenarios

- 开发者可按根目录文档启动后端并运行 Flutter
- Claude Code 可在不猜测环境和命令的情况下执行单个任务
- 本地测试默认只使用合成账号、合成档案和占位图片
- 未完成照片隐私门时，客户端和后端都拒绝真实照片分析
- AI 服务超时、异常或返回无效结构时，系统显示明确失败且不落库

## Runtime And Configuration Contract

阶段 0 继续支持 Python 3.9，不引入要求 Python 3.10 以上的新语法。

Flutter 通过编译参数读取：

```text
API_BASE_URL
PHOTO_ANALYSIS_ENABLED
```

后端通过环境变量读取：

```text
PHOTO_ANALYSIS_ENABLED=false
```

约束：

- `API_BASE_URL` 未提供时可保留 Android 模拟器开发默认值
- 照片分析在前后端都必须显式启用，后端是最终授权边界
- 密钥不得通过 Flutter `--dart-define` 传递
- `.env.example` 只包含占位值，不包含真实凭据

## API And State Contracts

所有当前体态路由必须声明 Pydantic response model：

- `GET /api/v1/posture/issues`
- `GET /api/v1/posture/issues/{issue_id}`
- `GET /api/v1/posture/issues/{issue_id}/related`
- `POST /api/v1/posture/assess`
- `POST /api/v1/posture/assess/photo`
- `GET /api/v1/posture/history`

响应字段名称保持与现有 Flutter 模型兼容。

当照片分析未启用时：

```json
{
  "detail": "照片分析在当前数据模式下未启用",
  "code": "photo_analysis_disabled"
}
```

对应上传凭证和照片评估接口均返回 `503`，且不得生成凭证、签名 URL、模型请求或数据库记录。

当模型不可用、超时、响应无法解析或不符合 schema 时：

- 返回明确的 `503`
- 不把缺失字段补成 `normal`
- 不保存评估记录
- 不在日志中记录照片地址、用户健康档案或完整模型响应

## Safety, Privacy, And Failure Handling

- 阶段 0 默认只使用合成数据
- 照片分析默认关闭
- 当前阶段不以免责声明替代隐私门
- 无效 AI 输出不得转化为健康或正常结论
- 后端开关不能被客户端参数绕过
- 任何失败都不能形成半落库状态

## Observability And Audit

允许日志记录：

- 请求失败类型
- 上游状态码
- schema 校验失败类别
- 请求关联标识

禁止日志记录：

- 原始健康档案
- 原始模型响应
- 照片对象地址或签名 URL
- Token、云服务密钥和模型密钥

## Acceptance Criteria

1. 根目录存在当前有效的运行和验证命令。
2. 后端测试、Flutter analyze 和 Flutter 测试通过且无当前已知弃用警告。
3. Flutter API 地址可通过 `--dart-define` 覆盖。
4. 照片上传和分析默认在前后端关闭。
5. AI 失败或无效输出不会产生 `normal` 结果或数据库记录。
6. 当前体态 API 具有 OpenAPI 可见的 response schema。
7. Android 模拟器完成一次登录、问题浏览和图示自测冒烟流程。
8. 旧计划和旧状态文档明确标记为历史资料。
9. 阶段 0 的验证证据和未解决限制被记录。

## Test And Evaluation Strategy

- 后端：完整 pytest、OpenAPI schema、照片门禁、AI 无效输出和无落库回归测试
- Flutter：配置单元测试、照片关闭状态组件测试、完整 analyze 和 test
- 集成：后端 `/health`、登录、问题列表、自测和历史接口
- Android：`Pixel_6` 模拟器手工冒烟
- 数据：只使用合成账号、合成档案和占位图片

## Rollout

所有改变仅作用于开发基线。照片能力保持默认关闭，直到后续规格完成告知、同意、真实 STS、保存期限和删除策略。任何任务失败时，回滚该任务对应提交，不跨任务混合回滚。
