> **⚠️ 历史资料** — 本文档记录早期开发过程，不代表当前完成状态或当前架构决策。
> 当前规格和计划见 [docs/README.md](../README.md)。

# 体态分析后端 API 实施计划 (修订版)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建体态分析 App 的后端 API 服务（认证、体态问题库、自测评估、AI 照片分析、OSS 上传凭证）

**Architecture:** FastAPI 单体应用，按 auth/user/posture/upload 模块划分。PostgreSQL 作主库，Qwen VL 做图像分析，阿里云 OSS 做图片存储。认证采用纯验证码模式（无密码），登录即注册。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Alembic, PostgreSQL, Pydantic v2, httpx, python-jose (JWT), pytest + pytest-asyncio

**工作目录:** `C:\Users\Lenovo\Desktop\develop\health\backend`

---

## 修订说明（相对原计划的变化）

| # | 原计划 | 修订 | 原因 |
|---|--------|------|------|
| 1 | RegisterRequest 含 password 字段 | 移除 password，统一为验证码登录即注册 | 中国 App 主流模式，减少用户流失 |
| 2 | login 和 register 逻辑分离 | 合并为 send-code + verify-login 一个流程 | 登录即注册，流程更简洁 |
| 3 | AI prompt 不传用户信息 | 传入用户身高/体重/性别/年龄 | 符合 Spec 要求，提升分析精度 |
| 4 | 无 CORS 中间件 | 添加 CORSMiddleware | Flutter 开发必需 |
| 5 | knowledge.py 内联所有数据 | 拆为 JSON 文件 + Python 加载器 | 可维护性 |
| 6 | send_code 返回明文验证码 | 开发模式打印到日志，不返回 API | 安全性 |

---

## 文件结构总览

```
backend/
├── requirements.txt
├── .env.example
├── .gitignore
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 入口 + CORS + 全局异常
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py           # pydantic-settings 环境变量
│   │   ├── security.py         # JWT 工具
│   │   ├── dependencies.py     # get_db, get_current_user
│   │   └── exceptions.py       # 全局异常类
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py             # DeclarativeBase
│   │   └── database.py         # async engine + session
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── models.py           # User, VerificationCode ORM
│   │   ├── schemas.py          # Pydantic 请求/响应
│   │   ├── service.py          # 验证码生成/校验、用户查找或创建
│   │   └── router.py           # POST /auth/send-code, /auth/verify-login, /auth/refresh
│   ├── user/
│   │   ├── __init__.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   └── router.py           # GET/PUT /user/profile
│   ├── posture/
│   │   ├── __init__.py
│   │   ├── models.py           # PostureAssessment ORM
│   │   ├── schemas.py
│   │   ├── service.py          # 评估保存、历史查询、关联推荐
│   │   ├── ai_service.py       # Qwen VL API 调用（含用户信息）
│   │   ├── knowledge.py        # JSON 加载器
│   │   ├── data/               # 26 个问题 JSON 文件
│   │   │   ├── head_neck.json
│   │   │   ├── shoulder_thorax.json
│   │   │   ├── pelvis_spine.json
│   │   │   ├── lower_limb.json
│   │   │   └── compound.json
│   │   └── router.py
│   └── upload/
│       ├── __init__.py
│       ├── schemas.py
│       ├── service.py          # STS 临时凭证 + 签名 URL
│       └── router.py           # POST /upload/sts-token
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_auth.py
    ├── test_user.py
    ├── test_posture.py
    └── test_upload.py
```

---

### Task 1: 项目脚手架 + 配置

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`
- Create: `backend/.gitignore`
- Create: `backend/app/__init__.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/db/__init__.py`
- Create: `backend/app/auth/__init__.py`
- Create: `backend/app/user/__init__.py`
- Create: `backend/app/posture/__init__.py`
- Create: `backend/app/upload/__init__.py`
- Create: `backend/tests/__init__.py`

- [ ] **Step 1: 创建目录结构**

```powershell
cd C:\Users\Lenovo\Desktop\develop\health
mkdir -p backend/app/core backend/app/db backend/app/auth backend/app/user backend/app/posture/data backend/app/upload backend/tests
```

创建空 `__init__.py`：

```powershell
touch backend/app/__init__.py backend/app/core/__init__.py backend/app/db/__init__.py backend/app/auth/__init__.py backend/app/user/__init__.py backend/app/posture/__init__.py backend/app/upload/__init__.py backend/tests/__init__.py
```

- [ ] **Step 2: 编写 requirements.txt**

```txt
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
alembic==1.14.1
pydantic[email]==2.10.4
pydantic-settings==2.7.1
python-jose[cryptography]==3.3.0
python-multipart==0.0.19
httpx==0.28.1
oss2==2.19.1
pytest==8.3.4
pytest-asyncio==0.25.0
aiosqlite==0.20.0
```

- [ ] **Step 3: 编写 .env.example**

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/posture_app
SECRET_KEY=your-secret-key-change-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=120
REFRESH_TOKEN_EXPIRE_DAYS=7

ALIBABA_CLOUD_ACCESS_KEY_ID=your-access-key
ALIBABA_CLOUD_ACCESS_KEY_SECRET=your-secret
OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
OSS_BUCKET=posture-app-bucket
OSS_REGION=cn-hangzhou

DASHSCOPE_API_KEY=your-dashscope-api-key

SMS_SIGN_NAME=your-sign-name
SMS_TEMPLATE_CODE=SMS_123456789

DEV_MODE=true
```

- [ ] **Step 4: 编写 .gitignore**

```
__pycache__/
*.pyc
.env
*.db
.pytest_cache/
.venv/
```

- [ ] **Step 5: 提交**

```bash
cd C:\Users\Lenovo\Desktop\develop\health
git add backend/
git commit -m "chore: add backend project scaffolding"
```

---

### Task 2: 数据库基础 + 配置模块

**Files:**
- Create: `backend/app/core/config.py`
- Create: `backend/app/db/base.py`
- Create: `backend/app/db/database.py`

- [ ] **Step 1: 编写配置模块**

`backend/app/core/config.py`:
```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/posture_app"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    ALIBABA_CLOUD_ACCESS_KEY_ID: str = ""
    ALIBABA_CLOUD_ACCESS_KEY_SECRET: str = ""
    OSS_ENDPOINT: str = "oss-cn-hangzhou.aliyuncs.com"
    OSS_BUCKET: str = "posture-app-bucket"
    OSS_REGION: str = "cn-hangzhou"

    DASHSCOPE_API_KEY: str = ""

    SMS_SIGN_NAME: str = ""
    SMS_TEMPLATE_CODE: str = ""

    DEV_MODE: bool = False
    TEST_DATABASE_URL: str = "sqlite+aiosqlite:///./test.db"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
```

- [ ] **Step 2: 编写数据库基础**

`backend/app/db/base.py`:
```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

`backend/app/db/database.py`:
```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def create_all():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_all():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
```

注意：`get_db` 中不 import `Base`，避免循环引用。`create_all`/`drop_all` 仅用于测试。

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/config.py backend/app/db/base.py backend/app/db/database.py
git commit -m "feat: add database base and config module"
```

---

### Task 3: 安全模块 + 异常处理 + 依赖注入

**Files:**
- Create: `backend/app/core/security.py`
- Create: `backend/app/core/exceptions.py`
- Create: `backend/app/core/dependencies.py`

- [ ] **Step 1: 编写安全工具**

`backend/app/core/security.py`:
```python
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from app.core.config import settings


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": user_id, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return {}
```

注意：移除了 `passlib/bcrypt` 相关代码，因为认证方案是验证码登录，不需要密码哈希。

- [ ] **Step 2: 编写异常处理**

`backend/app/core/exceptions.py`:
```python
class AppException(Exception):
    def __init__(self, status_code: int, detail: str, code: str = "error"):
        self.status_code = status_code
        self.detail = detail
        self.code = code


class Unauthorized(AppException):
    def __init__(self, detail: str = "未登录或登录已过期"):
        super().__init__(401, detail, "unauthorized")


class Forbidden(AppException):
    def __init__(self, detail: str = "无权限"):
        super().__init__(403, detail, "forbidden")


class NotFound(AppException):
    def __init__(self, detail: str = "资源不存在"):
        super().__init__(404, detail, "not_found")


class BadRequest(AppException):
    def __init__(self, detail: str = "请求参数错误"):
        super().__init__(400, detail, "bad_request")
```

- [ ] **Step 3: 编写依赖注入**

`backend/app/core/dependencies.py`:
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.core.security import decode_token

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    if user_id is None or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 无效或已过期")
    return user_id
```

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/security.py backend/app/core/exceptions.py backend/app/core/dependencies.py
git commit -m "feat: add security, exceptions, and dependency injection"
```

---

### Task 4: 用户认证模块（统一验证码登录）

**Files:**
- Create: `backend/app/auth/models.py`
- Create: `backend/app/auth/schemas.py`
- Create: `backend/app/auth/service.py`

- [ ] **Step 1: 编写 ORM 模型**

`backend/app/auth/models.py`:
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True)
    height: Mapped[float | None] = mapped_column(nullable=True)
    weight: Mapped[float | None] = mapped_column(nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    membership_level: Mapped[str] = mapped_column(String(20), default="free")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(6), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

注意：User 表没有 `hashed_password` 字段。认证方案是纯验证码，不需要密码。

- [ ] **Step 2: 编写 Pydantic schemas**

`backend/app/auth/schemas.py`:
```python
from pydantic import BaseModel, Field


class SendCodeRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11, pattern=r"^1[3-9]\d{9}$")


class SendCodeResponse(BaseModel):
    message: str = "验证码已发送"


class VerifyLoginRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11, pattern=r"^1[3-9]\d{9}$")
    code: str = Field(..., min_length=4, max_length=6)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    is_new_user: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str
```

注意：移除了 `RegisterRequest` 和 `LoginRequest`，统一为 `VerifyLoginRequest`。

- [ ] **Step 3: 编写服务层**

`backend/app/auth/service.py`:
```python
import random
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.auth.models import User, VerificationCode
from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_verification_code(db: AsyncSession, phone: str) -> None:
    code = f"{random.randint(100000, 999999)}"
    vc = VerificationCode(
        phone=phone,
        code=code,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db.add(vc)
    await db.commit()

    if settings.DEV_MODE:
        logger.info(f"[DEV] 验证码: phone={phone}, code={code}")
    else:
        # TODO: 调用阿里云短信服务发送验证码
        pass


async def verify_code(db: AsyncSession, phone: str, code: str) -> bool:
    stmt = (
        select(VerificationCode)
        .where(
            VerificationCode.phone == phone,
            VerificationCode.code == code,
            VerificationCode.used == False,
            VerificationCode.expires_at > datetime.now(timezone.utc),
        )
        .order_by(VerificationCode.created_at.desc())
    )
    result = await db.execute(stmt)
    vc = result.scalar_one_or_none()
    if vc:
        vc.used = True
        await db.commit()
        return True
    return False


async def find_or_create_user(db: AsyncSession, phone: str) -> tuple[str, bool]:
    """返回 (user_id, is_new_user)"""
    stmt = select(User).where(User.phone == phone)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        return str(user.id), False

    user = User(phone=phone)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return str(user.id), True
```

- [ ] **Step 4: 提交**

```bash
git add backend/app/auth/
git commit -m "feat: add auth module (SMS code login, no password)"
```

---

### Task 5: 认证路由 + FastAPI 入口

**Files:**
- Create: `backend/app/auth/router.py`
- Create: `backend/app/main.py`

- [ ] **Step 1: 编写认证路由**

`backend/app/auth/router.py`:
```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.auth.schemas import SendCodeRequest, SendCodeResponse, VerifyLoginRequest, TokenResponse, RefreshRequest
from app.auth import service
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.core.exceptions import BadRequest, Unauthorized

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/send-code", response_model=SendCodeResponse)
async def send_code(request: SendCodeRequest, db: AsyncSession = Depends(get_db)):
    await service.send_verification_code(db, request.phone)
    return SendCodeResponse()


@router.post("/verify-login", response_model=TokenResponse)
async def verify_login(request: VerifyLoginRequest, db: AsyncSession = Depends(get_db)):
    if not await service.verify_code(db, request.phone, request.code):
        raise BadRequest("验证码错误或已过期")
    user_id, is_new = await service.find_or_create_user(db, request.phone)
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        is_new_user=is_new,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: RefreshRequest):
    payload = decode_token(request.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise Unauthorized("Refresh Token 无效")
    user_id = payload["sub"]
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )
```

- [ ] **Step 2: 编写 main.py + CORS + 全局异常**

`backend/app/main.py`:
```python
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.exceptions import AppException
from app.auth.router import router as auth_router

app = FastAPI(title="体态分析 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
    )


app.include_router(auth_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/auth/router.py backend/app/main.py
git commit -m "feat: add auth routes and FastAPI entry with CORS"
```

---

### Task 6: 用户信息模块

**Files:**
- Create: `backend/app/user/schemas.py`
- Create: `backend/app/user/service.py`
- Create: `backend/app/user/router.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 编写用户 schemas**

`backend/app/user/schemas.py`:
```python
from pydantic import BaseModel, Field


class UserProfileResponse(BaseModel):
    id: str
    phone: str
    nickname: str | None = None
    height: float | None = None
    weight: float | None = None
    age: int | None = None
    gender: str | None = None
    membership_level: str = "free"
    created_at: str | None = None


class UpdateProfileRequest(BaseModel):
    nickname: str | None = Field(None, max_length=50)
    height: float | None = Field(None, gt=0, le=300)
    weight: float | None = Field(None, gt=0, le=500)
    age: int | None = Field(None, gt=0, lt=150)
    gender: str | None = Field(None, pattern="^(male|female)$")
```

- [ ] **Step 2: 编写用户服务**

`backend/app/user/service.py`:
```python
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.auth.models import User as UserModel
from app.user.schemas import UpdateProfileRequest, UserProfileResponse


def _to_profile(user: UserModel) -> UserProfileResponse:
    return UserProfileResponse(
        id=str(user.id),
        phone=user.phone,
        nickname=user.nickname,
        height=float(user.height) if user.height else None,
        weight=float(user.weight) if user.weight else None,
        age=user.age,
        gender=user.gender,
        membership_level=user.membership_level,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


async def get_profile(db: AsyncSession, user_id: str) -> UserProfileResponse | None:
    result = await db.execute(select(UserModel).where(UserModel.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        return None
    return _to_profile(user)


async def update_profile(db: AsyncSession, user_id: str, request: UpdateProfileRequest) -> UserProfileResponse:
    result = await db.execute(select(UserModel).where(UserModel.id == UUID(user_id)))
    user = result.scalar_one()
    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)
    await db.commit()
    await db.refresh(user)
    return _to_profile(user)
```

- [ ] **Step 3: 编写用户路由**

`backend/app/user/router.py`:
```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFound
from app.user.schemas import UserProfileResponse, UpdateProfileRequest
from app.user import service

router = APIRouter(prefix="/api/v1/user", tags=["user"])


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(user_id: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profile = await service.get_profile(db, user_id)
    if profile is None:
        raise NotFound("用户不存在")
    return profile


@router.put("/profile", response_model=UserProfileResponse)
async def update_profile(
    request: UpdateProfileRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_profile(db, user_id, request)
```

- [ ] **Step 4: 注册路由到 main.py**

在 `backend/app/main.py` 底部（`@app.get("/health")` 之前）添加：

```python
from app.user.router import router as user_router
app.include_router(user_router)
```

- [ ] **Step 5: 提交**

```bash
git add backend/app/user/ backend/app/main.py
git commit -m "feat: add user profile module"
```

---

### Task 7: 体态问题知识库（JSON 拆分）

**Files:**
- Create: `backend/app/posture/data/head_neck.json`
- Create: `backend/app/posture/data/shoulder_thorax.json`
- Create: `backend/app/posture/data/pelvis_spine.json`
- Create: `backend/app/posture/data/lower_limb.json`
- Create: `backend/app/posture/data/compound.json`
- Create: `backend/app/posture/knowledge.py`

- [ ] **Step 1: 编写 JSON 数据文件**

每个 JSON 文件是一个数组，包含该分类下的所有问题。结构严格遵循 Spec 定义的 schema。

`backend/app/posture/data/head_neck.json`:
```json
[
  {
    "id": "HN-01",
    "name_cn": "头部前倾",
    "name_en": "Forward Head Posture",
    "abbr": "FHP",
    "category": "head_neck",
    "aliases": ["乌龟颈", "探颈"],
    "definition": "耳垂落于肩峰垂线前方，颈椎下段屈曲、上段过伸",
    "severity_levels": ["轻度", "中度", "重度"],
    "causes": [
      {"type": "行为习惯", "desc": "长期低头看手机/电脑、伏案工作"},
      {"type": "睡眠因素", "desc": "枕头过高或过低，破坏颈椎中立位"},
      {"type": "肌肉失衡", "desc": "枕下肌群、胸锁乳突肌紧张缩短；颈深屈肌薄弱"}
    ],
    "self_tests": [
      {
        "name": "靠墙站立测试",
        "steps": ["背靠墙站立", "后脑勺、上背、臀部贴墙", "观察后脑勺是否能自然贴墙"],
        "positive_sign": "后脑勺无法自然贴墙",
        "image_key": "assets/images/tests/hn01_wall_test.png",
        "tools_needed": "无"
      },
      {
        "name": "侧面拍照法",
        "steps": ["自然站姿", "请他人从侧面拍照", "过肩峰画垂线，观察耳垂位置"],
        "positive_sign": "耳垂明显落在垂线前方",
        "image_key": "assets/images/tests/hn01_side_photo.png",
        "tools_needed": "手机"
      }
    ],
    "corrections": [
      {"type": "拉伸", "target_muscle": "枕下肌群", "method": "收下巴训练（Chin Tuck）", "freq": "30秒×3，每日2次"},
      {"type": "拉伸", "target_muscle": "上斜方肌", "method": "侧屈拉伸", "freq": "30秒×3，每日2次"},
      {"type": "强化", "target_muscle": "颈深屈肌", "method": "收下巴抗阻训练", "freq": "10次×3组/日"},
      {"type": "习惯", "desc": "屏幕抬至眼平、每30分钟活动颈部"}
    ],
    "consequences": [
      {"timeframe": "短期", "desc": "颈肩僵硬、紧张性头痛、易疲劳"},
      {"timeframe": "长期", "desc": "椎间盘压力增大加速退变、富贵包、颈源性头痛"}
    ],
    "red_flags": ["伴手臂放射痛、麻木、握力下降→提示神经根受压，需就医"],
    "related_issues": [
      {"id": "HN-02", "weight": 0.9, "relation": "因果/共存"},
      {"id": "ST-04", "weight": 0.9, "relation": "共存(UCS)"}
    ]
  },
  {
    "id": "HN-02",
    "name_cn": "颈曲变直",
    "name_en": "Loss of Cervical Lordosis",
    "abbr": "LCL",
    "category": "head_neck",
    "aliases": ["军人颈", "直颈"],
    "definition": "颈椎生理前凸减小或反向（正常C2-C7 Cobb角约20°-40°）",
    "severity_levels": ["轻度", "中度", "重度"],
    "causes": [
      {"type": "行为习惯", "desc": "长期FHP累积代偿"},
      {"type": "创伤", "desc": "颈部外伤（挥鞭伤）后肌肉保护性痉挛"},
      {"type": "退变", "desc": "颈椎退行性变、椎间盘脱水"}
    ],
    "self_tests": [
      {
        "name": "仰卧触摸法",
        "steps": ["仰卧平躺", "用手指触摸颈后与床面的间隙", "感受空隙大小"],
        "positive_sign": "颈后几乎贴床、无空隙",
        "image_key": "assets/images/tests/hn02_supine_test.png",
        "tools_needed": "无"
      }
    ],
    "corrections": [
      {"type": "拉伸", "target_muscle": "颈后肌群", "method": "仰卧颈后垫毛巾卷做轻柔伸展", "freq": "每天10分钟"},
      {"type": "强化", "target_muscle": "颈深屈肌", "method": "收下巴训练", "freq": "10次×3组/日"}
    ],
    "consequences": [
      {"timeframe": "长期", "desc": "椎间盘前侧压力增大、退变加速、颈源性头痛"}
    ],
    "red_flags": ["多需影像确诊，App引导而非诊断"],
    "related_issues": [
      {"id": "HN-01", "weight": 0.9, "relation": "因果/共存"},
      {"id": "ST-04", "weight": 0.6, "relation": "代偿"}
    ]
  },
  {
    "id": "HN-03",
    "name_cn": "斜颈",
    "name_en": "Torticollis",
    "abbr": "TORT",
    "category": "head_neck",
    "aliases": ["歪脖"],
    "definition": "头部歪向一侧，下巴转向对侧",
    "severity_levels": ["轻度", "中度", "重度"],
    "causes": [
      {"type": "先天性", "desc": "胸锁乳突肌纤维化、胎位异常（婴幼儿多见）"},
      {"type": "姿势性", "desc": "长期单侧用力、颈肌痉挛"}
    ],
    "self_tests": [
      {
        "name": "镜像观察法",
        "steps": ["正对镜子自然站立", "观察头部是否习惯性歪向一侧", "检查下巴是否转向对侧"],
        "positive_sign": "头部明显歪向一侧",
        "image_key": "assets/images/tests/hn03_mirror_test.png",
        "tools_needed": "镜子"
      }
    ],
    "corrections": [
      {"type": "拉伸", "target_muscle": "紧张侧胸锁乳突肌", "method": "紧张侧拉伸", "freq": "30秒×3，每日2次"},
      {"type": "强化", "target_muscle": "对侧肌肉", "method": "对侧抗阻训练", "freq": "每日1次"}
    ],
    "consequences": [
      {"timeframe": "短期", "desc": "持续性颈痛、活动受限"},
      {"timeframe": "长期", "desc": "颜面不对称、继发高低肩与脊柱侧弯"}
    ],
    "red_flags": ["新发斜颈、伴疼痛或神经症状必须就医"],
    "related_issues": [
      {"id": "ST-05", "weight": 0.6, "relation": "继发"},
      {"id": "PS-11", "weight": 0.6, "relation": "继发"}
    ]
  }
]
```

其余 4 个 JSON 文件（shoulder_thorax.json、pelvis_spine.json、lower_limb.json、compound.json）的结构完全相同，数据参照原计划 Task 7 中 knowledge.py 的 ISSUES 列表填入。每个 JSON 文件包含对应分类的所有问题。

**执行者需从原计划 `2026-06-01-backend-api-plan.md` Task 7 的 ISSUES 列表中提取数据，按分类拆分到 5 个 JSON 文件中。**

- [ ] **Step 2: 编写知识库加载器**

`backend/app/posture/knowledge.py`:
```python
import json
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"

CATEGORY_MAP = {
    "head_neck": "头颈部",
    "shoulder_thorax": "肩胸区",
    "pelvis_spine": "骨盆腰椎",
    "lower_limb": "下肢",
    "compound": "复合综合征",
}

_FILE_MAP = {
    "head_neck": "head_neck.json",
    "shoulder_thorax": "shoulder_thorax.json",
    "pelvis_spine": "pelvis_spine.json",
    "lower_limb": "lower_limb.json",
    "compound": "compound.json",
}

_ISSUES_CACHE: list[dict] | None = None


def _load_all() -> list[dict]:
    global _ISSUES_CACHE
    if _ISSUES_CACHE is not None:
        return _ISSUES_CACHE
    issues = []
    for filename in _FILE_MAP.values():
        filepath = _DATA_DIR / filename
        with open(filepath, "r", encoding="utf-8") as f:
            issues.extend(json.load(f))
    _ISSUES_CACHE = issues
    return _ISSUES_CACHE


def get_all_issues(category: str | None = None) -> list[dict]:
    issues = _load_all()
    if category:
        return [i for i in issues if i["category"] == category]
    return issues


def get_issue_by_id(issue_id: str) -> dict | None:
    for i in _load_all():
        if i["id"] == issue_id:
            return i
    return None
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/posture/data/ backend/app/posture/knowledge.py
git commit -m "feat: add posture knowledge base (JSON files + loader)"
```

---

### Task 8: 体态评估 — 模型 + Schema + 服务

**Files:**
- Create: `backend/app/posture/models.py`
- Create: `backend/app/posture/schemas.py`
- Create: `backend/app/posture/service.py`

- [ ] **Step 1: 编写 ORM 模型**

`backend/app/posture/models.py`:
```python
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class PostureAssessment(Base):
    __tablename__ = "posture_assessments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    issue_id: Mapped[str] = mapped_column(String(20), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    self_test_answers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ai_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    photo_keys: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 2: 编写 schemas**

`backend/app/posture/schemas.py`:
```python
from pydantic import BaseModel
from datetime import datetime


class SelfAssessRequest(BaseModel):
    issue_id: str
    test_index: int = 0
    answer: str  # "positive" | "negative" | "uncertain"


class SelfAssessResponse(BaseModel):
    id: str
    issue_id: str
    result: str
    suggestion: str


class PhotoAssessRequest(BaseModel):
    issue_id: str
    photo_keys: list[str]


class AssessmentRecord(BaseModel):
    id: str
    issue_id: str
    issue_name: str
    method: str
    result: str
    created_at: datetime


class RelatedIssue(BaseModel):
    id: str
    name_cn: str
    weight: float
    relation: str
```

- [ ] **Step 3: 编写服务层**

`backend/app/posture/service.py`:
```python
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.posture.models import PostureAssessment
from app.posture.knowledge import get_issue_by_id, get_all_issues


def get_all_issues_list(category: str | None = None) -> list[dict]:
    return get_all_issues(category)


def get_related_issues(issue_id: str) -> list[dict]:
    issue = get_issue_by_id(issue_id)
    if not issue:
        return []
    result = []
    for rel in issue.get("related_issues", []):
        related = get_issue_by_id(rel["id"])
        if related and rel.get("weight", 0) >= 0.6:
            result.append({
                "id": rel["id"],
                "name_cn": related["name_cn"],
                "weight": rel["weight"],
                "relation": rel["relation"],
            })
    result.sort(key=lambda x: x["weight"], reverse=True)
    return result[:3]


def _evaluate_result(issue: dict, answer: str) -> tuple[str, str]:
    if answer == "negative":
        return "normal", "自测结果为阴性，你该方面的体态目前正常。保持良好习惯即可。"
    elif answer == "positive":
        return "moderate", "自测结果为阳性，建议进行以下纠正训练。如伴红旗征请及时就医。"
    else:
        return "uncertain", "自测结果不确定。建议使用 AI 拍照分析进行更精确的判断。"


async def save_self_assessment(
    db: AsyncSession,
    user_id: str,
    issue_id: str,
    answer: str,
    test_index: int,
) -> dict | None:
    issue = get_issue_by_id(issue_id)
    if not issue:
        return None
    result_level, suggestion = _evaluate_result(issue, answer)
    assessment = PostureAssessment(
        user_id=UUID(user_id),
        issue_id=issue_id,
        method="self_test",
        result=result_level,
        self_test_answers={"test_index": test_index, "answer": answer},
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)
    return {
        "id": str(assessment.id),
        "issue_id": assessment.issue_id,
        "result": result_level,
        "suggestion": suggestion,
    }


async def save_photo_assessment(
    db: AsyncSession,
    user_id: str,
    issue_id: str,
    photo_keys: list[str],
    ai_result: dict,
) -> dict:
    ai_level = ai_result.get("level", "normal")
    if ai_level in ("normal", "mild"):
        db_result = "normal"
        suggestion = "AI分析结果为正常/轻微。保持良好的体态习惯即可。"
    elif ai_level == "moderate":
        db_result = "moderate"
        suggestion = ai_result.get("suggestion", "建议进行纠正训练。")
    else:
        db_result = "severe"
        suggestion = ai_result.get("suggestion", "建议尽快咨询专业医师。")

    assessment = PostureAssessment(
        user_id=UUID(user_id),
        issue_id=issue_id,
        method="ai_photo",
        result=db_result,
        ai_response=ai_result,
        photo_keys=photo_keys,
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)
    return {
        "id": str(assessment.id),
        "issue_id": assessment.issue_id,
        "result": db_result,
        "suggestion": suggestion,
    }


async def get_user_history(db: AsyncSession, user_id: str, limit: int = 20, offset: int = 0) -> list[dict]:
    stmt = (
        select(PostureAssessment)
        .where(PostureAssessment.user_id == UUID(user_id))
        .order_by(desc(PostureAssessment.created_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    output = []
    for r in records:
        issue = get_issue_by_id(r.issue_id)
        output.append({
            "id": str(r.id),
            "issue_id": r.issue_id,
            "issue_name": issue["name_cn"] if issue else r.issue_id,
            "method": r.method,
            "result": r.result,
            "created_at": r.created_at,
        })
    return output
```

- [ ] **Step 4: 提交**

```bash
git add backend/app/posture/models.py backend/app/posture/schemas.py backend/app/posture/service.py
git commit -m "feat: add posture assessment service layer"
```

---

### Task 9: AI 服务（含用户信息传递）

**Files:**
- Create: `backend/app/posture/ai_service.py`

- [ ] **Step 1: 编写 AI 服务**

`backend/app/posture/ai_service.py`:
```python
import json
import logging
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import settings
from app.posture.knowledge import get_issue_by_id
from app.upload.service import generate_signed_url
from app.auth.models import User
from uuid import UUID

logger = logging.getLogger(__name__)

QWEN_VL_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


async def _get_user_info(db: AsyncSession, user_id: str) -> dict:
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user:
        return {
            "gender": user.gender or "未知",
            "age": user.age or "未知",
            "height": f"{user.height}cm" if user.height else "未知",
            "weight": f"{user.weight}kg" if user.weight else "未知",
        }
    return {"gender": "未知", "age": "未知", "height": "未知", "weight": "未知"}


async def analyze_posture_photo(
    issue_id: str,
    photo_keys: list[str],
    user_id: str,
    db: AsyncSession,
) -> dict:
    issue = get_issue_by_id(issue_id)
    if not issue:
        return {"level": "normal", "confidence": 0, "evidence": [], "suggestion": "问题不存在", "need_retake": False}

    signed_urls = [generate_signed_url(key) for key in photo_keys]
    user_info = await _get_user_info(db, user_id)

    content_parts = []
    for url in signed_urls:
        content_parts.append({"type": "image_url", "image_url": {"url": url}})

    prompt = f"""你是一位专业的运动康复评估师，具备丰富的体态评估经验。

当前评估问题：{issue['name_cn']}（{issue['definition']}）

用户信息：
- 性别：{user_info['gender']}
- 年龄：{user_info['age']}
- 身高：{user_info['height']}
- 体重：{user_info['weight']}

请分析用户上传的照片，完成以下任务：

1. 识别照片中与"{issue['name_cn']}"相关的体征
2. 给出判定等级：normal（正常）/ mild（轻度）/ moderate（中度）/ severe（重度）
3. 给出判定依据（具体哪些视觉特征支持你的判断）
4. 如果照片角度、清晰度不足以准确判断，明确说明并建议重拍

请以 JSON 格式输出：
{{"level": "normal|mild|moderate|severe", "confidence": 0.0-1.0, "evidence": ["特征1", "特征2"], "suggestion": "建议文字", "need_retake": false, "retake_reason": ""}}

重要提示：
- 你的分析仅供参考，不构成医疗诊断
- 如发现可能的严重病理问题，请在 suggestion 中建议用户就医
- 保持客观、专业、谨慎的态度"""

    content_parts.append({"type": "text", "text": prompt})

    body = {
        "model": "qwen-vl-max",
        "messages": [{"role": "user", "content": content_parts}],
        "max_tokens": 1000,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            QWEN_VL_URL,
            headers={
                "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]

    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("\n", 1)[0]
        if content.startswith("json"):
            content = content[4:]

    try:
        ai_result = json.loads(content)
    except json.JSONDecodeError:
        logger.error(f"AI response parse error: {content[:200]}")
        ai_result = {"level": "normal", "confidence": 0, "evidence": [], "suggestion": "AI 分析结果解析失败，建议重新尝试", "need_retake": False}

    ai_result.setdefault("level", "normal")
    ai_result.setdefault("confidence", 0)
    ai_result.setdefault("evidence", [])
    ai_result.setdefault("suggestion", "")
    ai_result.setdefault("need_retake", False)
    return ai_result
```

关键改进：
- 添加了 `_get_user_info` 从数据库读取用户身高/体重/性别/年龄
- Prompt 中包含完整的用户信息（符合 Spec 要求）
- 添加了 JSON 解析失败的容错处理

- [ ] **Step 2: 提交**

```bash
git add backend/app/posture/ai_service.py
git commit -m "feat: add Qwen VL AI analysis service with user info"
```

---

### Task 10: 体态 API 路由

**Files:**
- Create: `backend/app/posture/router.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 编写路由**

`backend/app/posture/router.py`:
```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFound, BadRequest
from app.posture import service
from app.posture.schemas import SelfAssessRequest, PhotoAssessRequest
from app.posture.knowledge import get_issue_by_id

router = APIRouter(prefix="/api/v1/posture", tags=["posture"])


@router.get("/issues")
async def list_issues(category: str | None = Query(None)):
    issues = service.get_all_issues_list(category)
    return [
        {"id": i["id"], "name_cn": i["name_cn"], "category": i["category"], "aliases": i["aliases"], "definition": i["definition"]}
        for i in issues
    ]


@router.get("/issues/{issue_id}")
async def get_issue_detail(issue_id: str):
    issue = get_issue_by_id(issue_id)
    if issue is None:
        raise NotFound("体态问题不存在")
    return issue


@router.get("/issues/{issue_id}/related")
async def get_related(issue_id: str):
    return service.get_related_issues(issue_id)


@router.post("/assess")
async def self_assess(
    request: SelfAssessRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if request.answer not in ("positive", "negative", "uncertain"):
        raise BadRequest("答案只能是 positive/negative/uncertain")
    result = await service.save_self_assessment(db, user_id, request.issue_id, request.answer, request.test_index)
    if result is None:
        raise NotFound("体态问题不存在")
    return result


@router.post("/assess/photo")
async def photo_assess(
    request: PhotoAssessRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.posture.ai_service import analyze_posture_photo
    issue = get_issue_by_id(request.issue_id)
    if issue is None:
        raise NotFound("体态问题不存在")
    if not request.photo_keys:
        raise BadRequest("请上传至少一张照片")
    ai_result = await analyze_posture_photo(request.issue_id, request.photo_keys, user_id, db)
    result = await service.save_photo_assessment(db, user_id, request.issue_id, request.photo_keys, ai_result)
    return result


@router.get("/history")
async def get_history(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return await service.get_user_history(db, user_id, limit, offset)
```

关键改进：
- History API 添加了 `offset` 分页参数
- `list_issues` 只返回摘要字段（不含完整 knowledge），减少传输量

- [ ] **Step 2: 注册路由到 main.py**

在 `backend/app/main.py` 中添加：

```python
from app.posture.router import router as posture_router
app.include_router(posture_router)
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/posture/router.py backend/app/main.py
git commit -m "feat: add posture API routes with pagination"
```

---

### Task 11: OSS 上传模块

**Files:**
- Create: `backend/app/upload/schemas.py`
- Create: `backend/app/upload/service.py`
- Create: `backend/app/upload/router.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 编写上传 schemas**

`backend/app/upload/schemas.py`:
```python
from pydantic import BaseModel


class STSTokenResponse(BaseModel):
    access_key_id: str
    access_key_secret: str
    security_token: str
    bucket: str
    region: str
    endpoint: str
    path_prefix: str
```

- [ ] **Step 2: 编写上传服务**

`backend/app/upload/service.py`:
```python
import uuid
from app.core.config import settings


def generate_sts_credentials(user_id: str) -> dict:
    path_prefix = f"posture_photos/{user_id}/{uuid.uuid4().hex[:8]}/"
    if settings.DEV_MODE:
        return {
            "access_key_id": settings.ALIBABA_CLOUD_ACCESS_KEY_ID,
            "access_key_secret": settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET,
            "security_token": "",
            "bucket": settings.OSS_BUCKET,
            "region": settings.OSS_REGION,
            "endpoint": settings.OSS_ENDPOINT,
            "path_prefix": path_prefix,
        }
    # TODO: 生产环境调用阿里云 STS SDK 获取临时凭证
    return {
        "access_key_id": "",
        "access_key_secret": "",
        "security_token": "",
        "bucket": settings.OSS_BUCKET,
        "region": settings.OSS_REGION,
        "endpoint": settings.OSS_ENDPOINT,
        "path_prefix": path_prefix,
    }


def generate_signed_url(object_key: str, expires_in: int = 3600) -> str:
    if settings.DEV_MODE:
        return f"https://{settings.OSS_BUCKET}.{settings.OSS_ENDPOINT}/{object_key}"
    # TODO: 生产环境用 OSS SDK 生成签名 URL
    return f"https://{settings.OSS_BUCKET}.{settings.OSS_ENDPOINT}/{object_key}"
```

- [ ] **Step 3: 编写上传路由**

`backend/app/upload/router.py`:
```python
from fastapi import APIRouter, Depends
from app.core.dependencies import get_current_user
from app.upload import service
from app.upload.schemas import STSTokenResponse

router = APIRouter(prefix="/api/v1/upload", tags=["upload"])


@router.post("/sts-token", response_model=STSTokenResponse)
async def get_sts_token(user_id: str = Depends(get_current_user)):
    return service.generate_sts_credentials(user_id)
```

- [ ] **Step 4: 注册到 main.py**

在 `backend/app/main.py` 中添加：

```python
from app.upload.router import router as upload_router
app.include_router(upload_router)
```

- [ ] **Step 5: 提交**

```bash
git add backend/app/upload/ backend/app/main.py
git commit -m "feat: add OSS upload module"
```

---

### Task 12: Alembic 迁移配置

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/` (空目录)

- [ ] **Step 1: 初始化 Alembic**

```bash
cd C:\Users\Lenovo\Desktop\develop\health\backend && alembic init alembic
```

- [ ] **Step 2: 修改 alembic/env.py**

```python
import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

from app.core.config import settings
from app.db.base import Base
from app.auth.models import User, VerificationCode
from app.posture.models import PostureAssessment

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: 生成初始迁移**

```bash
cd C:\Users\Lenovo\Desktop\develop\health\backend && alembic revision --autogenerate -m "init"
```

- [ ] **Step 4: 提交**

```bash
git add backend/alembic.ini backend/alembic/
git commit -m "feat: add Alembic migration setup"
```

---

### Task 13: 测试

**Files:**
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_auth.py`
- Create: `backend/tests/test_user.py`
- Create: `backend/tests/test_posture.py`

- [ ] **Step 1: 编写测试 fixtures**

`backend/tests/conftest.py`:
```python
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.db.base import Base
from app.db.database import get_db
from app.main import app
from app.core.config import settings

TEST_DB_URL = "sqlite+aiosqlite:///./test.db"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
```

- [ ] **Step 2: 编写认证测试**

`backend/tests/test_auth.py`:
```python
import pytest
from app.core.config import settings

settings.DEV_MODE = True


@pytest.mark.asyncio
async def test_send_code(client):
    resp = await client.post("/api/v1/auth/send-code", json={"phone": "13800138000"})
    assert resp.status_code == 200
    assert resp.json()["message"] == "验证码已发送"


@pytest.mark.asyncio
async def test_verify_login_creates_user(client):
    # 先发验证码
    await client.post("/api/v1/auth/send-code", json={"phone": "13800138000"})
    # DEV_MODE 下需要从数据库读取验证码
    from tests.conftest import TestSession
    from app.auth.models import VerificationCode
    from sqlalchemy import select

    async with TestSession() as db:
        result = await db.execute(
            select(VerificationCode).where(VerificationCode.phone == "13800138000").order_by(VerificationCode.created_at.desc())
        )
        code = result.scalar_one().code

    resp = await client.post("/api/v1/auth/verify-login", json={"phone": "13800138000", "code": code})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["is_new_user"] is True


@pytest.mark.asyncio
async def test_verify_login_existing_user(client):
    # 注册第一次
    await client.post("/api/v1/auth/send-code", json={"phone": "13800138001"})
    from tests.conftest import TestSession
    from app.auth.models import VerificationCode
    from sqlalchemy import select

    async with TestSession() as db:
        result = await db.execute(
            select(VerificationCode).where(VerificationCode.phone == "13800138001").order_by(VerificationCode.created_at.desc())
        )
        code = result.scalar_one().code

    resp1 = await client.post("/api/v1/auth/verify-login", json={"phone": "13800138001", "code": code})
    assert resp1.json()["is_new_user"] is True

    # 第二次登录
    await client.post("/api/v1/auth/send-code", json={"phone": "13800138001"})
    async with TestSession() as db:
        result = await db.execute(
            select(VerificationCode).where(VerificationCode.phone == "13800138001").order_by(VerificationCode.created_at.desc())
        )
        code2 = result.scalar_one().code

    resp2 = await client.post("/api/v1/auth/verify-login", json={"phone": "13800138001", "code": code2})
    assert resp2.json()["is_new_user"] is False


@pytest.mark.asyncio
async def test_verify_login_wrong_code(client):
    resp = await client.post("/api/v1/auth/verify-login", json={"phone": "13800138000", "code": "000000"})
    assert resp.status_code == 400
```

- [ ] **Step 3: 编写用户信息测试**

`backend/tests/test_user.py`:
```python
import pytest
from tests.conftest import TestSession
from app.auth.models import VerificationCode
from sqlalchemy import select


async def _login_user(client, phone="13800138000"):
    await client.post("/api/v1/auth/send-code", json={"phone": phone})
    async with TestSession() as db:
        result = await db.execute(
            select(VerificationCode).where(VerificationCode.phone == phone).order_by(VerificationCode.created_at.desc())
        )
        code = result.scalar_one().code
    resp = await client.post("/api/v1/auth/verify-login", json={"phone": phone, "code": code})
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_get_profile(client):
    token = await _login_user(client)
    resp = await client.get("/api/v1/user/profile", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["phone"] == "13800138000"


@pytest.mark.asyncio
async def test_update_profile(client):
    token = await _login_user(client)
    resp = await client.put(
        "/api/v1/user/profile",
        json={"height": 175.0, "weight": 70.0, "age": 25, "gender": "male"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["height"] == 175.0
```

- [ ] **Step 4: 编写体态问题测试**

`backend/tests/test_posture.py`:
```python
import pytest
from tests.conftest import TestSession
from app.auth.models import VerificationCode
from sqlalchemy import select


async def _login_user(client, phone="13800138000"):
    await client.post("/api/v1/auth/send-code", json={"phone": phone})
    async with TestSession() as db:
        result = await db.execute(
            select(VerificationCode).where(VerificationCode.phone == phone).order_by(VerificationCode.created_at.desc())
        )
        code = result.scalar_one().code
    resp = await client.post("/api/v1/auth/verify-login", json={"phone": phone, "code": code})
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_list_issues(client):
    token = await _login_user(client)
    resp = await client.get("/api/v1/posture/issues", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert len(resp.json()) > 0


@pytest.mark.asyncio
async def test_list_issues_by_category(client):
    token = await _login_user(client)
    resp = await client.get("/api/v1/posture/issues?category=head_neck", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    for issue in resp.json():
        assert issue["category"] == "head_neck"


@pytest.mark.asyncio
async def test_get_issue_detail(client):
    token = await _login_user(client)
    resp = await client.get("/api/v1/posture/issues/HN-01", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["name_cn"] == "头部前倾"


@pytest.mark.asyncio
async def test_self_assess(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "moderate"


@pytest.mark.asyncio
async def test_get_history(client):
    token = await _login_user(client)
    # 先提交一个评估
    await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "negative"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.get("/api/v1/posture/history", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1
```

- [ ] **Step 5: 运行测试验证**

```bash
cd C:\Users\Lenovo\Desktop\develop\health\backend
pip install -r requirements.txt
pytest tests/ -v
```

- [ ] **Step 6: 提交**

```bash
git add backend/tests/
git commit -m "test: add auth, user, posture tests"
```

---

## 执行顺序

```
阶段一：基础骨架（T1 → T2 → T3 → T4 → T5）
  完成后：API 可以发验证码、登录（自动注册）、刷新 Token

阶段二：核心业务（T6 → T7 → T8 → T9 → T10 → T11）
  完成后：完整的体态分析 API（问题库、自测、AI分析、上传、历史）

阶段三：迁移和测试（T12 → T13）
  完成后：数据库迁移就绪，测试通过
```

---

## 与原计划的主要差异

1. **认证简化**：移除密码，统一为验证码登录即注册
2. **知识库拆分**：从单一 .py 文件拆为 JSON + loader
3. **AI 服务增强**：传入用户身体信息
4. **CORS 支持**：开发阶段必需
5. **历史 API 分页**：添加 offset 参数
6. **安全增强**：验证码不再通过 API 返回，开发模式打印到日志
7. **JSON 解析容错**：AI 服务增加解析失败的降级处理
