# Phase 9 直接依赖许可证审计

> 2026-08-12 内部工程清单。版本以 `backend/requirements.lock` 为准；此表不是法律意见，
> 也不替代发布时的完整传递依赖、NOTICE、商标和分发义务审查。

| 直接依赖 | 锁定版本 | 项目元数据/上游声明 | Gate 2 结论 |
| --- | --- | --- | --- |
| FastAPI | 0.128.8 | MIT | 可继续内部候选 |
| Starlette | 0.49.3 | BSD-3-Clause | 可继续；安全 VEX 单独约束 |
| Uvicorn | 0.39.0 | BSD-3-Clause | 可继续内部候选 |
| SQLAlchemy | 2.0.36 | MIT | 可继续内部候选 |
| asyncpg | 0.30.0 | Apache-2.0 | 可继续内部候选 |
| Alembic | 1.14.1 | MIT | 可继续内部候选 |
| Pydantic / settings | 2.10.4 / 2.7.1 | MIT | 可继续内部候选 |
| PyJWT | 2.13.0 | MIT | 可继续；替代有未修复适用风险的 python-jose 链 |
| python-multipart | 0.0.32 | Apache-2.0 | 候选不使用表单/上传解析；保留框架依赖 |
| HTTPX | 0.28.1 | BSD-3-Clause | 可继续内部候选 |
| OSS2 SDK | 2.19.1 | 上游仓库 MIT；候选照片/对象 provider 关闭 | 真实启用前重审供应商和分发义务 |
| aiosqlite | 0.20.0 | MIT | 仅开发/SQLite 测试辅助；候选配置强制 PostgreSQL |
| tzdata | 2026.3 | Apache-2.0 | 可继续内部候选 |
| pytest / pytest-asyncio | 8.4.2 / 1.2.0 | MIT / Apache-2.0 | 仅 dev 锁；VEX 记录 pytest 条目 |

运行时与开发依赖已经拆分为两个带哈希锁文件。正式 APK/后端分发前仍需由合格人员对完整
传递依赖、源代码/二进制分发方式和第三方 NOTICE 做重新审查；当前状态为 `not obtained`。
