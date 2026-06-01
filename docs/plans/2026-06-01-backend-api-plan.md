# 体态分析后端 API 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建体态分析 App 的后端 API 服务（用户认证、体态问题库查询、自测提交、AI 照片分析、OSS 上传凭证）

**Architecture:** FastAPI 单体应用，按 auth/user/posture/upload 模块划分，PostgreSQL 作主库，通过 Qwen VL API 做图像分析，阿里云 OSS 做图片存储

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Alembic, PostgreSQL, Pydantic v2, httpx, python-jose (JWT), pytest + pytest-asyncio

**工作目录:** `C:\Users\Lenovo\Desktop\develop\health\backend`

---

## 文件结构总览

```
backend/
├── requirements.txt
├── .env.example
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 入口
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py           # 环境变量配置 (pydantic-settings)
│   │   ├── security.py         # JWT + 密码哈希
│   │   ├── dependencies.py     # FastAPI 依赖注入 (get_db, get_current_user)
│   │   └── exceptions.py       # 全局异常处理
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py         # async session + engine
│   │   └── base.py             # SQLAlchemy declarative base
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── models.py           # User, VerificationCode ORM
│   │   ├── schemas.py          # Pydantic 请求/响应
│   │   ├── service.py          # 验证码生成/校验、用户创建
│   │   └── router.py           # POST /auth/send-code, /register, /login, /refresh
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
│   │   ├── ai_service.py       # Qwen VL API 调用
│   │   ├── knowledge.py        # 26 个问题的结构化数据
│   │   └── router.py           # GET /issues, GET /issues/:id, POST /assess, POST /assess/photo, GET /history, GET /issues/:id/related
│   └── upload/
│       ├── __init__.py
│       ├── schemas.py
│       ├── service.py          # STS 临时凭证生成
│       └── router.py           # POST /upload/sts-token
└── tests/
    ├── __init__.py
    ├── conftest.py             # 测试 fixtures (async client, test db)
    ├── test_auth.py
    ├── test_user.py
    ├── test_posture.py
    └── test_upload.py
```

---

### Task 1: 项目脚手架

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`
- Create: `backend/app/__init__.py`
- Create: `backend/tests/__init__.py`

- [ ] **Step 1: 创建目录结构 + __init__.py**

```powershell
cd C:\Users\Lenovo\Desktop\develop\health
mkdir backend\app\core, backend\app\db, backend\app\auth, backend\app\user, backend\app\posture, backend\app\upload, backend\tests
```

在每个 Python 包目录下创建空 `__init__.py`：

```powershell
cd backend
echo. > app\__init__.py
echo. > app\core\__init__.py
echo. > app\db\__init__.py
echo. > app\auth\__init__.py
echo. > app\user\__init__.py
echo. > app\posture\__init__.py
echo. > app\upload\__init__.py
echo. > tests\__init__.py
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
passlib[bcrypt]==1.7.4
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
```

- [ ] **Step 4: 提交**

```powershell
cd C:\Users\Lenovo\Desktop\develop\health && git add backend/requirements.txt backend/.env.example && git commit -m "feat: add backend project scaffolding"
```

---

### Task 2: 数据库基础 + 配置

**Files:**
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/db/__init__.py`
- Create: `backend/app/db/base.py`
- Create: `backend/app/db/database.py`

- [ ] **Step 1: 编写配置模块**

`backend/app/core/__init__.py` (empty)
`backend/app/db/__init__.py` (empty)

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
from app.db.base import Base

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncSession:
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

- [ ] **Step 3: 提交**

```powershell
git add backend/app/db/ backend/app/core/ && git commit -m "feat: add database base and config"
```

---

### Task 3: 安全模块 + 依赖注入

**Files:**
- Create: `backend/app/core/security.py`
- Create: `backend/app/core/dependencies.py`
- Create: `backend/app/core/exceptions.py`

- [ ] **Step 1: 编写安全工具**

`backend/app/core/security.py`:
```python
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

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

```powershell
git add backend/app/core/security.py backend/app/core/dependencies.py backend/app/core/exceptions.py && git commit -m "feat: add security and dependency injection"
```

---

### Task 4: 用户认证模块（模型 + 服务）

**Files:**
- Create: `backend/app/auth/models.py`
- Create: `backend/app/auth/schemas.py`
- Create: `backend/app/auth/service.py`

- [ ] **Step 1: 编写 ORM 模型**

`backend/app/auth/models.py`:
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Numeric, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    height: Mapped[float] = mapped_column(Numeric(5, 1), nullable=True)
    weight: Mapped[float] = mapped_column(Numeric(5, 1), nullable=True)
    age: Mapped[int] = mapped_column(Integer, nullable=True)
    gender: Mapped[str] = mapped_column(String(10), nullable=True)
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

- [ ] **Step 2: 编写 Pydantic schemas**

`backend/app/auth/schemas.py`:
```python
from pydantic import BaseModel, Field

class SendCodeRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11, pattern=r"^1[3-9]\d{9}$")

class SendCodeResponse(BaseModel):
    message: str = "验证码已发送"

class RegisterRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11, pattern=r"^1[3-9]\d{9}$")
    code: str = Field(..., min_length=4, max_length=6)
    password: str = Field(..., min_length=6, max_length=32)

class LoginRequest(BaseModel):
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

- [ ] **Step 3: 编写服务层**

`backend/app/auth/service.py`:
```python
import uuid
import random
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.auth.models import User, VerificationCode
from app.auth.schemas import SendCodeRequest, RegisterRequest, LoginRequest
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token
from app.core.config import settings

async def send_verification_code(db: AsyncSession, phone: str) -> str:
    code = f"{random.randint(100000, 999999)}"
    vc = VerificationCode(
        phone=phone,
        code=code,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db.add(vc)
    await db.commit()
    # TODO: 对接阿里云短信服务发送验证码
    return code

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

async def register_user(db: AsyncSession, request: RegisterRequest) -> str:
    if not await verify_code(db, request.phone, request.code):
        return None
    stmt = select(User).where(User.phone == request.phone)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        return None
    user = User(
        phone=request.phone,
        hashed_password=hash_password(request.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return str(user.id)

async def login_user(db: AsyncSession, request: LoginRequest) -> str:
    if not await verify_code(db, request.phone, request.code):
        return None
    stmt = select(User).where(User.phone == request.phone)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        user = User(phone=request.phone, hashed_password=hash_password(uuid.uuid4().hex))
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return str(user.id)
```

- [ ] **Step 4: 提交**

```powershell
git add backend/app/auth/ && git commit -m "feat: add auth models, schemas, and service"
```

---

### Task 5: 认证路由

**Files:**
- Create: `backend/app/auth/router.py`
- Create: `backend/app/main.py`

- [ ] **Step 1: 编写认证路由**

`backend/app/auth/router.py`:
```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.auth.schemas import SendCodeRequest, SendCodeResponse, RegisterRequest, LoginRequest, TokenResponse, RefreshRequest
from app.auth import service
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.core.exceptions import BadRequest, Unauthorized

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

@router.post("/send-code", response_model=SendCodeResponse)
async def send_code(request: SendCodeRequest, db: AsyncSession = Depends(get_db)):
    await service.send_verification_code(db, request.phone)
    return SendCodeResponse()

@router.post("/register", response_model=TokenResponse)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    user_id = await service.register_user(db, request)
    if user_id is None:
        raise BadRequest("验证码错误或手机号已注册")
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)

@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    user_id = await service.login_user(db, request)
    if user_id is None:
        raise BadRequest("验证码错误或已过期")
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)

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

- [ ] **Step 2: 编写 main.py + 全局异常处理器**

`backend/app/main.py`:
```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.core.exceptions import AppException
from app.auth.router import router as auth_router

app = FastAPI(title="体态分析 API", version="0.1.0")

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

```powershell
git add backend/app/auth/router.py backend/app/main.py && git commit -m "feat: add auth routes and FastAPI entrypoint"
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
    height: float | None = None
    weight: float | None = None
    age: int | None = None
    gender: str | None = None
    membership_level: str = "free"
    created_at: str | None = None

class UpdateProfileRequest(BaseModel):
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

async def get_profile(db: AsyncSession, user_id: str) -> UserProfileResponse | None:
    result = await db.execute(select(UserModel).where(UserModel.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        return None
    return UserProfileResponse(
        id=str(user.id),
        phone=user.phone,
        height=float(user.height) if user.height else None,
        weight=float(user.weight) if user.weight else None,
        age=user.age,
        gender=user.gender,
        membership_level=user.membership_level,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )

async def update_profile(db: AsyncSession, user_id: str, request: UpdateProfileRequest) -> UserProfileResponse:
    result = await db.execute(select(UserModel).where(UserModel.id == UUID(user_id)))
    user = result.scalar_one()
    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)
    await db.commit()
    await db.refresh(user)
    return UserProfileResponse(
        id=str(user.id),
        phone=user.phone,
        height=float(user.height) if user.height else None,
        weight=float(user.weight) if user.weight else None,
        age=user.age,
        gender=user.gender,
        membership_level=user.membership_level,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )
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

```python
# 在 main.py 中添加
from app.user.router import router as user_router
app.include_router(user_router)
```

- [ ] **Step 5: 提交**

```powershell
git add backend/app/user/ backend/app/main.py && git commit -m "feat: add user profile module"
```

---

### Task 7: 体态问题知识库

**Files:**
- Create: `backend/app/posture/knowledge.py`

- [ ] **Step 1: 编写 26 个问题的结构化数据**

`backend/app/posture/knowledge.py`:
```python
ISSUES = [
    {
        "id": "HN-01",
        "name_cn": "头部前倾",
        "name_en": "Forward Head Posture",
        "category": "head_neck",
        "aliases": ["乌龟颈", "探颈"],
        "definition": "耳垂落于肩峰垂线前方，颈椎下段屈曲、上段过伸",
        "severity_levels": ["轻度", "中度", "重度"],
        "causes": [
            {"type": "行为习惯", "desc": "长期低头看手机/电脑、伏案工作"},
            {"type": "睡眠因素", "desc": "枕头过高或过低，破坏颈椎中立位"},
            {"type": "肌肉失衡", "desc": "枕下肌群、胸锁乳突肌紧张缩短；颈深屈肌薄弱"},
        ],
        "self_tests": [
            {
                "name": "靠墙站立测试",
                "steps": ["背靠墙站立", "后脑勺、上背、臀部贴墙", "观察后脑勺是否能自然贴墙"],
                "positive_sign": "后脑勺无法自然贴墙",
                "image_key": "assets/images/tests/hn01_wall_test.png",
                "tools_needed": "无",
            },
            {
                "name": "侧面拍照法",
                "steps": ["自然站姿", "请他人从侧面拍照", "过肩峰画垂线，观察耳垂位置"],
                "positive_sign": "耳垂明显落在垂线前方",
                "image_key": "assets/images/tests/hn01_side_photo.png",
                "tools_needed": "手机",
            },
        ],
        "corrections": [
            {"type": "拉伸", "target_muscle": "枕下肌群", "method": "收下巴训练（Chin Tuck）", "freq": "30秒×3，每日2次"},
            {"type": "拉伸", "target_muscle": "上斜方肌", "method": "侧屈拉伸", "freq": "30秒×3，每日2次"},
            {"type": "强化", "target_muscle": "颈深屈肌", "method": "收下巴抗阻训练", "freq": "10次×3组/日"},
            {"type": "习惯", "desc": "屏幕抬至眼平、每30分钟活动颈部"},
        ],
        "consequences": [
            {"timeframe": "短期", "desc": "颈肩僵硬、紧张性头痛、易疲劳"},
            {"timeframe": "长期", "desc": "椎间盘压力增大加速退变、富贵包、颈源性头痛"},
        ],
        "red_flags": ["伴手臂放射痛、麻木、握力下降→提示神经根受压，需就医"],
        "related_issues": [
            {"id": "HN-02", "weight": 0.9, "relation": "因果/共存"},
            {"id": "ST-04", "weight": 0.9, "relation": "共存(UCS)"},
        ],
    },
    {
        "id": "HN-02",
        "name_cn": "颈曲变直",
        "name_en": "Loss of Cervical Lordosis",
        "category": "head_neck",
        "aliases": ["军人颈", "直颈"],
        "definition": "颈椎生理前凸减小或反向（正常C2-C7 Cobb角约20°-40°）",
        "severity_levels": ["轻度", "中度", "重度"],
        "causes": [
            {"type": "行为习惯", "desc": "长期FHP累积代偿"},
            {"type": "创伤", "desc": "颈部外伤（挥鞭伤）后肌肉保护性痉挛"},
            {"type": "退变", "desc": "颈椎退行性变、椎间盘脱水"},
        ],
        "self_tests": [
            {
                "name": "仰卧触摸法",
                "steps": ["仰卧平躺", "用手指触摸颈后与床面的间隙", "感受空隙大小"],
                "positive_sign": "颈后几乎贴床、无空隙",
                "image_key": "assets/images/tests/hn02_supine_test.png",
                "tools_needed": "无",
            },
        ],
        "corrections": [
            {"type": "拉伸", "target_muscle": "颈后肌群", "method": "仰卧颈后垫毛巾卷做轻柔伸展", "freq": "每天10分钟"},
            {"type": "强化", "target_muscle": "颈深屈肌", "method": "收下巴训练", "freq": "10次×3组/日"},
        ],
        "consequences": [
            {"timeframe": "长期", "desc": "椎间盘前侧压力增大、退变加速、颈源性头痛"},
        ],
        "red_flags": ["多需影像确诊，App引导而非诊断"],
        "related_issues": [
            {"id": "HN-01", "weight": 0.9, "relation": "因果/共存"},
            {"id": "ST-04", "weight": 0.6, "relation": "代偿"},
        ],
    },
    {
        "id": "HN-03",
        "name_cn": "斜颈",
        "name_en": "Torticollis",
        "category": "head_neck",
        "aliases": ["歪脖"],
        "definition": "头部歪向一侧，下巴转向对侧",
        "severity_levels": ["轻度", "中度", "重度"],
        "causes": [
            {"type": "先天性", "desc": "胸锁乳突肌纤维化、胎位异常（婴幼儿多见）"},
            {"type": "姿势性", "desc": "长期单侧用力、颈肌痉挛"},
        ],
        "self_tests": [
            {
                "name": "镜像观察法",
                "steps": ["正对镜子自然站立", "观察头部是否习惯性歪向一侧", "检查下巴是否转向对侧"],
                "positive_sign": "头部明显歪向一侧",
                "image_key": "assets/images/tests/hn03_mirror_test.png",
                "tools_needed": "镜子",
            },
        ],
        "corrections": [
            {"type": "拉伸", "target_muscle": "紧张侧胸锁乳突肌", "method": "紧张侧拉伸", "freq": "30秒×3，每日2次"},
            {"type": "强化", "target_muscle": "对侧肌肉", "method": "对侧抗阻训练", "freq": "每日1次"},
        ],
        "consequences": [
            {"timeframe": "短期", "desc": "持续性颈痛、活动受限"},
            {"timeframe": "长期", "desc": "颜面不对称、继发高低肩与脊柱侧弯"},
        ],
        "red_flags": ["新发斜颈、伴疼痛或神经症状必须就医"],
        "related_issues": [
            {"id": "ST-05", "weight": 0.6, "relation": "继发"},
            {"id": "PS-11", "weight": 0.6, "relation": "继发"},
        ],
    },
    {
        "id": "ST-04",
        "name_cn": "圆肩",
        "name_en": "Rounded Shoulders",
        "category": "shoulder_thorax",
        "aliases": ["含胸"],
        "definition": "肩胛骨前引+前倾+内旋，肩峰前移超过耳垂垂线",
        "severity_levels": ["轻度", "中度", "重度"],
        "causes": [
            {"type": "肌肉失衡", "desc": "胸小肌、胸大肌紧张缩短；中下斜方肌、菱形肌薄弱"},
            {"type": "行为习惯", "desc": "长期含胸驼背、健身只练"镜子肌""},
        ],
        "self_tests": [
            {
                "name": "拇指朝向测试",
                "steps": ["自然站立放松", "双臂自然下垂", "观察手掌拇指的朝向"],
                "positive_sign": "双手拇指指向大腿内侧甚至后方",
                "image_key": "assets/images/tests/st04_thumb_test.png",
                "tools_needed": "无",
            },
        ],
        "corrections": [
            {"type": "拉伸", "target_muscle": "胸小肌", "method": "门框胸肌拉伸", "freq": "30秒×3，每日2次"},
            {"type": "强化", "target_muscle": "中下斜方肌", "method": "俯身W-Y-T划船", "freq": "12次×3组，隔日1次"},
            {"type": "强化", "target_muscle": "菱形肌", "method": "面拉（Face Pull）", "freq": "15次×3组，隔日1次"},
        ],
        "consequences": [
            {"timeframe": "短期", "desc": "肩峰下撞击综合征、肩袖损伤"},
            {"timeframe": "长期", "desc": "与FHP共同发展为上交叉综合征、呼吸效率下降"},
        ],
        "red_flags": ["伴持续肩痛、活动受限需就医"],
        "related_issues": [
            {"id": "HN-01", "weight": 0.9, "relation": "共存(UCS)"},
            {"id": "ST-08", "weight": 0.9, "relation": "共存(UCS)"},
            {"id": "ST-07", "weight": 0.9, "relation": "归属(UCS)"},
        ],
    },
    {
        "id": "ST-05",
        "name_cn": "高低肩",
        "name_en": "Uneven Shoulders",
        "category": "shoulder_thorax",
        "aliases": [],
        "definition": "左右肩峰高度差 ≥ 1cm（非结构性而言）",
        "severity_levels": ["轻度", "中度", "重度"],
        "causes": [
            {"type": "功能性", "desc": "单侧背包、单侧用力运动、习惯性单侧耸肩"},
            {"type": "结构性", "desc": "脊柱侧弯代偿、长短腿、骨盆侧倾向上传导"},
        ],
        "self_tests": [
            {
                "name": "正面对镜测试",
                "steps": ["正对镜子放松站立", "观察双侧肩峰高度", "目测差异"],
                "positive_sign": "双侧肩峰高度差异 ≥1cm",
                "image_key": "assets/images/tests/st05_mirror_test.png",
                "tools_needed": "镜子",
            },
        ],
        "corrections": [
            {"type": "拉伸", "target_muscle": "高侧上斜方肌、肩胛提肌", "method": "高侧放松", "freq": "30秒×3"},
            {"type": "强化", "target_muscle": "低侧肌肉", "method": "低侧耸肩训练", "freq": "每日1次"},
            {"type": "习惯", "desc": "改双肩背包、纠正单侧负重"},
        ],
        "consequences": [
            {"timeframe": "短期", "desc": "慢性颈肩痛"},
            {"timeframe": "长期", "desc": "若为侧弯代偿，忽视可致侧弯进展"},
        ],
        "red_flags": ["明显高低肩务必先排查脊柱侧弯，尤其青少年"],
        "related_issues": [
            {"id": "PS-11", "weight": 0.9, "relation": "因果(结构)"},
            {"id": "PS-16", "weight": 0.9, "relation": "向上传导"},
        ],
    },
    {
        "id": "ST-06",
        "name_cn": "翼状肩胛",
        "name_en": "Winged Scapula",
        "category": "shoulder_thorax",
        "aliases": [],
        "definition": "肩胛骨内侧缘翘离胸壁",
        "severity_levels": ["轻度", "中度", "重度"],
        "causes": [
            {"type": "肌肉", "desc": "前锯肌薄弱/麻痹（内侧翼状）"},
            {"type": "神经", "desc": "胸长神经损伤、斜方肌麻痹（外侧翼状）"},
        ],
        "self_tests": [
            {
                "name": "俯卧撑墙测试",
                "steps": ["面墙站立", "双手推墙做俯卧撑动作", "在动作过程中观察肩胛骨内侧缘"],
                "positive_sign": "肩胛骨内侧缘明显翘起离开胸壁",
                "image_key": "assets/images/tests/st06_pushup_test.png",
                "tools_needed": "无",
            },
        ],
        "corrections": [
            {"type": "强化", "target_muscle": "前锯肌", "method": "Serratus Punch、Push-up Plus", "freq": "12次×3组"},
            {"type": "强化", "target_muscle": "肩胛稳定肌群", "method": "四足支撑前推", "freq": "每日1次"},
        ],
        "consequences": [
            {"timeframe": "短期", "desc": "肩关节上举受限、肩胛骨动力障碍"},
            {"timeframe": "长期", "desc": "肩部撞击与疼痛"},
        ],
        "red_flags": ["突发明显翼状肩胛伴无力→排查神经损伤，应就医"],
        "related_issues": [
            {"id": "ST-04", "weight": 0.6, "relation": "肌力失衡相关"},
        ],
    },
    {
        "id": "ST-07",
        "name_cn": "上交叉综合征",
        "name_en": "Upper Crossed Syndrome",
        "category": "shoulder_thorax",
        "aliases": ["UCS"],
        "definition": "Janda提出的肌肉失衡模式——头前倾+圆肩+驼背三合一",
        "severity_levels": ["轻度", "中度", "重度"],
        "causes": [
            {"type": "行为习惯", "desc": "长期伏案久坐导致交叉式肌肉失衡"},
        ],
        "self_tests": [
            {
                "name": "三联征综合判断",
                "steps": ["侧面拍照", "检查是否有头前倾（耳垂在肩峰前方）", "检查是否有圆肩（肩峰前移）", "检查是否有驼背（上背弯曲）"],
                "positive_sign": "同时存在三个特征",
                "image_key": "assets/images/tests/st07_side_photo.png",
                "tools_needed": "手机",
            },
        ],
        "corrections": [
            {"type": "拉伸", "target_muscle": "上斜方肌、胸肌、枕下肌群", "method": "综合拉伸", "freq": "30秒×3，每日2次"},
            {"type": "强化", "target_muscle": "中下斜方肌、菱形肌、颈深屈肌", "method": "收下巴+面拉+墙天使", "freq": "每日1次"},
            {"type": "灵活性", "target_muscle": "胸椎", "method": "泡沫轴胸椎伸展、猫驼式", "freq": "每日1次"},
        ],
        "consequences": [
            {"timeframe": "短期", "desc": "慢性颈肩痛、头痛"},
            {"timeframe": "长期", "desc": "肩部撞击、退行性颈椎病加速、呼吸模式异常"},
        ],
        "red_flags": [],
        "related_issues": [
            {"id": "HN-01", "weight": 0.9, "relation": "组成部分"},
            {"id": "ST-04", "weight": 0.9, "relation": "组成部分"},
            {"id": "ST-08", "weight": 0.9, "relation": "组成部分"},
            {"id": "CP-25", "weight": 0.7, "relation": "共同构成分层综合征"},
        ],
    },
    {
        "id": "ST-08",
        "name_cn": "驼背",
        "name_en": "Hyperkyphosis",
        "category": "shoulder_thorax",
        "aliases": ["胸椎后凸"],
        "definition": "胸椎后凸Cobb角 >40°（正常20°-40°）",
        "severity_levels": ["轻度", "中度", "重度"],
        "causes": [
            {"type": "姿势性（可逆）", "desc": "长期含胸、肌力失衡，主动挺直可纠正"},
            {"type": "结构性", "desc": "舒尔曼病（青少年椎体楔形变）"},
            {"type": "老年性", "desc": "骨质疏松致椎体压缩骨折"},
        ],
        "self_tests": [
            {
                "name": "靠墙测试",
                "steps": ["背靠墙站立", "后脑勺、上背、臀部贴墙", "观察上背与头部离墙程度"],
                "positive_sign": "上背明显离墙无法贴住",
                "image_key": "assets/images/tests/st08_wall_test.png",
                "tools_needed": "无",
            },
        ],
        "corrections": [
            {"type": "拉伸", "target_muscle": "胸部、上斜方肌", "method": "泡沫轴放松+胸椎伸展", "freq": "每日1次"},
            {"type": "强化", "target_muscle": "背部伸肌", "method": "俯卧抬头、Y-T-W-L", "freq": "12次×3组，隔日1次"},
        ],
        "consequences": [
            {"timeframe": "短期", "desc": "慢性背痛、身高变矮"},
            {"timeframe": "长期", "desc": "严重者影响心肺功能"},
        ],
        "red_flags": ["青少年僵硬性驼背、伴疼痛、进行性加重需就医（排查舒尔曼病）"],
        "related_issues": [
            {"id": "ST-04", "weight": 0.9, "relation": "共存(UCS)"},
            {"id": "ST-07", "weight": 0.9, "relation": "归属(UCS)"},
            {"id": "PS-13", "weight": 0.6, "relation": "矢状面代偿"},
        ],
    },
    {
        "id": "ST-09",
        "name_cn": "平背",
        "name_en": "Flat Back",
        "category": "shoulder_thorax",
        "aliases": [],
        "definition": "正常胸椎后凸和腰椎前凸生理曲度减小或消失",
        "severity_levels": ["轻度", "中度", "重度"],
        "causes": [
            {"type": "肌肉失衡", "desc": "腘绳肌过紧、竖脊肌薄弱、骨盆后倾"},
        ],
        "self_tests": [
            {
                "name": "靠墙站立测试",
                "steps": ["背靠墙站立", "用手测试腰部与墙壁的空隙"],
                "positive_sign": "腰部几乎无空隙、完全贴墙",
                "image_key": "assets/images/tests/st09_wall_test.png",
                "tools_needed": "无",
            },
        ],
        "corrections": [
            {"type": "强化", "target_muscle": "竖脊肌", "method": "小燕飞", "freq": "12次×3组"},
            {"type": "拉伸", "target_muscle": "腘绳肌", "method": "坐姿前屈", "freq": "30秒×3"},
        ],
        "consequences": [
            {"timeframe": "短期", "desc": "缓冲能力下降、久站久坐易疲劳"},
            {"timeframe": "长期", "desc": "椎间盘负荷增大、慢性腰痛"},
        ],
        "red_flags": [],
        "related_issues": [
            {"id": "PS-14", "weight": 0.9, "relation": "共存"},
            {"id": "PS-12", "weight": 0.6, "relation": "共存"},
        ],
    },
    # --- ST-10 肋骨外翻 ---
    {
        "id": "ST-10", "name_cn": "肋骨外翻", "name_en": "Rib Flare", "category": "shoulder_thorax",
        "aliases": [], "definition": "下肋骨向前外翻突出，常见于胸式呼吸过度或核心薄弱",
        "severity_levels": ["轻度", "中度", "重度"],
        "causes": [
            {"type": "呼吸模式", "desc": "长期胸式呼吸过度、腹式呼吸不足"},
            {"type": "肌肉失衡", "desc": "腹横肌、腹斜肌薄弱；膈肌紧张"},
            {"type": "代偿", "desc": "骨盆前倾向上传导代偿"},
        ],
        "self_tests": [{"name": "仰卧观察法", "steps": ["仰卧放松", "双腿弯曲", "观察下肋骨是否明显向外突起"], "positive_sign": "下肋骨明显高于腹部平面", "image_key": "assets/images/tests/st10_supine_test.png", "tools_needed": "无"}],
        "corrections": [
            {"type": "强化", "target_muscle": "腹横肌", "method": "死虫式（Dead Bug）", "freq": "10次×3组/日"},
            {"type": "强化", "target_muscle": "腹斜肌", "method": "侧平板支撑", "freq": "30秒×3/侧"},
            {"type": "训练", "desc": "练习腹式呼吸、360度呼吸", "freq": "每日5分钟"},
        ],
        "consequences": [{"timeframe": "短期", "desc": "核心稳定性差、呼吸效率低"}, {"timeframe": "长期", "desc": "腰痛风险增加"}],
        "red_flags": [], "related_issues": [{"id": "PS-13", "weight": 0.6, "relation": "代偿"}],
    },
    # --- PS-11 ~ PS-17 骨盆腰椎区 ---
    # 以下每项完整数据需参照 issue.md 第四~五章填入，结构与上方相同
    {"id": "PS-11", "name_cn": "脊柱侧弯", "name_en": "Scoliosis", "category": "pelvis_spine", "aliases": [], "definition": "脊柱冠状面侧弯Cobb角>10°，伴椎体旋转", "severity_levels": ["轻度", "中度", "重度"], "causes": [{"type": "特发性", "desc": "病因未明，可能遗传"}], "self_tests": [{"name": "Adams前屈测试", "steps": ["双脚并拢", "双手合十弯腰", "从背后观察两侧是否等高"], "positive_sign": "一侧背部隆起（剃刀背）", "image_key": "assets/images/tests/ps11_adams_test.png", "tools_needed": "需他人观察"}], "corrections": [{"type": "康复", "method": "Schroth施罗特疗法（需专业指导）", "freq": "遵医嘱"}], "consequences": [{"timeframe": "长期", "desc": "进展性弯曲、外观畸形、重度影响心肺"}], "red_flags": ["任何疑似侧弯都应就医确诊"], "related_issues": [{"id": "ST-05", "weight": 0.9, "relation": "因果(结构)"}, {"id": "PS-16", "weight": 0.9, "relation": "因果/共存"}]},
    {"id": "PS-12", "name_cn": "摇摆背", "name_en": "Sway Back", "category": "pelvis_spine", "aliases": [], "definition": "骨盆后移+胸椎段后移，腰椎前凸减小，腹部突出", "severity_levels": ["轻度", "中度", "重度"], "causes": [{"type": "姿势", "desc": "习惯性挂在韧带上的省力站姿"}], "self_tests": [{"name": "侧面拍照", "steps": ["自然站立", "侧面拍照", "观察骨盆是否整体前移于踝关节前方"], "positive_sign": "上半身后倾、腹部前突、臀部下垂", "image_key": "assets/images/tests/ps12_side_photo.png", "tools_needed": "手机"}], "corrections": [{"type": "强化", "target_muscle": "下腹核心、臀肌", "method": "臀桥+死虫式", "freq": "每日1次"}], "consequences": [{"timeframe": "长期", "desc": "腰骶部慢性劳损"}], "red_flags": [], "related_issues": [{"id": "PS-14", "weight": 0.6, "relation": "共存"}]},
    {"id": "PS-13", "name_cn": "骨盆前倾", "name_en": "Anterior Pelvic Tilt", "category": "pelvis_spine", "aliases": ["APT"], "definition": "髂前上棘前移，骨盆向前旋转，腰椎前凸增大", "severity_levels": ["轻度", "中度", "重度"], "causes": [{"type": "肌肉失衡", "desc": "髂腰肌、股直肌紧张；腹肌、臀大肌薄弱"}, {"type": "行为习惯", "desc": "久坐、长期高跟鞋"}], "self_tests": [{"name": "靠墙测试", "steps": ["贴墙站立", "测量腰后空隙"], "positive_sign": "空隙明显大于一掌厚", "image_key": "assets/images/tests/ps13_wall_test.png", "tools_needed": "无"}], "corrections": [{"type": "拉伸", "target_muscle": "髂腰肌", "method": "弓步拉伸", "freq": "30秒×3"}, {"type": "强化", "target_muscle": "臀大肌", "method": "臀桥", "freq": "12次×3组"}], "consequences": [{"timeframe": "长期", "desc": "慢性腰痛、膝足代偿"}], "red_flags": [], "related_issues": [{"id": "PS-15", "weight": 0.9, "relation": "组成部分(LCS)"}, {"id": "LL-20", "weight": 0.6, "relation": "矢状面代偿"}]},
    {"id": "PS-14", "name_cn": "骨盆后倾", "name_en": "Posterior Pelvic Tilt", "category": "pelvis_spine", "aliases": ["PPT"], "definition": "骨盆向后旋转，尾骨内收，腰椎前凸变平", "severity_levels": ["轻度", "中度", "重度"], "causes": [{"type": "肌肉失衡", "desc": "腘绳肌、腹直肌紧张；髋屈肌薄弱"}], "self_tests": [{"name": "靠墙站立", "steps": ["贴墙站立", "测量腰后空隙"], "positive_sign": "腰后空隙几乎消失", "image_key": "assets/images/tests/ps14_wall_test.png", "tools_needed": "无"}], "corrections": [{"type": "拉伸", "target_muscle": "腘绳肌", "method": "坐姿前屈", "freq": "30秒×3"}], "consequences": [{"timeframe": "长期", "desc": "椎间盘后侧压力增大→突出风险"}], "red_flags": [], "related_issues": [{"id": "ST-09", "weight": 0.9, "relation": "共存"}, {"id": "PS-12", "weight": 0.6, "relation": "共存"}]},
    {"id": "PS-15", "name_cn": "下交叉综合征", "name_en": "Lower Crossed Syndrome", "category": "pelvis_spine", "aliases": ["LCS"], "definition": "Janda提出的骨盆带肌肉失衡模式，常与APT共存", "severity_levels": ["轻度", "中度", "重度"], "causes": [{"type": "行为习惯", "desc": "长期久坐导致骨盆带交叉式失衡"}], "self_tests": [{"name": "托马斯测试", "steps": ["仰卧抱一侧膝至胸", "观察对侧大腿是否抬离床面"], "positive_sign": "对侧大腿抬离床面（髋屈肌紧张）", "image_key": "assets/images/tests/ps15_thomas_test.png", "tools_needed": "床/瑜伽垫"}], "corrections": [{"type": "拉伸", "target_muscle": "髂腰肌、竖脊肌", "method": "弓步拉伸+猫牛式", "freq": "每日1次"}, {"type": "强化", "target_muscle": "臀大肌、腹肌", "method": "臀桥+死虫式+平板", "freq": "每日1次"}], "consequences": [{"timeframe": "长期", "desc": "慢性腰痛、髋关节问题"}], "red_flags": [], "related_issues": [{"id": "PS-13", "weight": 0.9, "relation": "组成部分"}, {"id": "CP-25", "weight": 0.7, "relation": "共同构成分层综合征"}]},
    {"id": "PS-16", "name_cn": "骨盆侧倾", "name_en": "Pelvic Obliquity", "category": "pelvis_spine", "aliases": [], "definition": "骨盆一侧高于另一侧（冠状面倾斜）", "severity_levels": ["轻度", "中度", "重度"], "causes": [{"type": "结构性", "desc": "结构性长短腿"}, {"type": "功能性", "desc": "单侧臀中肌薄弱"}], "self_tests": [{"name": "双手叉腰触髂嵴", "steps": ["正面对镜", "双手叉腰触摸髂嵴", "比较双侧高度"], "positive_sign": "双侧髂嵴明显不等高", "image_key": "assets/images/tests/ps16_hip_test.png", "tools_needed": "镜子"}], "corrections": [{"type": "强化", "target_muscle": "薄弱侧臀中肌", "method": "侧桥、蚌式", "freq": "12次×3组"}], "consequences": [{"timeframe": "长期", "desc": "继发高低肩、脊柱侧弯"}], "red_flags": [], "related_issues": [{"id": "PS-11", "weight": 0.9, "relation": "因果/共存"}, {"id": "ST-05", "weight": 0.6, "relation": "向上传导"}]},
    {"id": "PS-17", "name_cn": "骨盆旋转", "name_en": "Pelvic Rotation", "category": "pelvis_spine", "aliases": [], "definition": "骨盆在水平面上不对称旋转", "severity_levels": ["轻度", "中度", "重度"], "causes": [{"type": "行为习惯", "desc": "长期单侧运动、习惯性翘腿"}], "self_tests": [{"name": "仰卧ASIS观察", "steps": ["仰卧放松", "触摸双侧ASIS（髂前上棘）", "判断是否一侧更前突"], "positive_sign": "一侧ASIS明显比另一侧前突", "image_key": "assets/images/tests/ps17_asis_test.png", "tools_needed": "无"}], "corrections": [{"type": "灵活性", "method": "平衡双侧髋关节灵活性与力量", "freq": "每日1次"}], "consequences": [{"timeframe": "长期", "desc": "步态异常、单侧关节磨损"}], "red_flags": [], "related_issues": []},
    # --- LL-18 ~ LL-24 下肢区 ---
    {"id": "LL-18", "name_cn": "X型腿", "name_en": "Genu Valgum", "category": "lower_limb", "aliases": ["膝外翻"], "definition": "双膝并拢时双侧内踝间距>8cm（成人）", "severity_levels": ["轻度", "中度", "重度"], "causes": [{"type": "肌肉失衡", "desc": "股骨内旋内收、足外翻、臀中肌薄弱"}], "self_tests": [{"name": "并膝测量", "steps": ["双膝并拢站立", "测双侧内踝间距"], "positive_sign": "间距>8cm", "image_key": "assets/images/tests/ll18_knee_test.png", "tools_needed": "尺子"}], "corrections": [{"type": "强化", "target_muscle": "臀中肌", "method": "蚌式、侧向行走带", "freq": "12次×3组"}], "consequences": [{"timeframe": "长期", "desc": "膝骨关节炎风险增加"}], "red_flags": ["单侧、进行性加重或伴疼痛需就医"], "related_issues": [{"id": "LL-23", "weight": 0.9, "relation": "自下而上传导"}, {"id": "PS-13", "weight": 0.6, "relation": "力线代偿"}]},
    {"id": "LL-19", "name_cn": "O型腿", "name_en": "Genu Varum", "category": "lower_limb", "aliases": ["膝内翻"], "definition": "双脚并拢时双侧膝关节内侧间距>5cm", "severity_levels": ["轻度", "中度", "重度"], "causes": [{"type": "结构性", "desc": "股骨外旋、退行性内侧间室磨损"}], "self_tests": [{"name": "并脚测量", "steps": ["双脚并拢站立", "测双膝内侧间距"], "positive_sign": "间距>5cm", "image_key": "assets/images/tests/ll19_knee_test.png", "tools_needed": "尺子"}], "corrections": [{"type": "强化", "target_muscle": "大腿内收肌", "method": "内收肌训练+臀肌平衡", "freq": "12次×3组"}], "consequences": [{"timeframe": "长期", "desc": "膝内侧间室过度磨损"}], "red_flags": ["成人结构性O型腿改善有限，明显畸形需骨科评估"], "related_issues": [{"id": "LL-24", "weight": 0.6, "relation": "力线相关"}]},
    {"id": "LL-20", "name_cn": "膝超伸", "name_en": "Genu Recurvatum", "category": "lower_limb", "aliases": [], "definition": "膝关节过度向后伸展，超过中立位>5°", "severity_levels": ["轻度", "中度", "重度"], "causes": [{"type": "肌肉失衡", "desc": "股四头肌过度主导、腘绳肌无力"}], "self_tests": [{"name": "侧面拍照", "steps": ["自然站立放松", "侧面拍照", "观察膝关节是否向后超伸"], "positive_sign": "小腿明显向后超过中立位", "image_key": "assets/images/tests/ll20_side_test.png", "tools_needed": "手机"}], "corrections": [{"type": "强化", "target_muscle": "腘绳肌", "method": "罗马尼亚硬拉", "freq": "12次×3组"}, {"type": "习惯", "desc": "站立时保持膝关节微屈不锁死"}], "consequences": [{"timeframe": "长期", "desc": "膝关节前侧及后关节囊慢性劳损"}], "red_flags": [], "related_issues": [{"id": "PS-13", "weight": 0.6, "relation": "矢状面代偿"}]},
    {"id": "LL-21", "name_cn": "扁平足", "name_en": "Pes Planus", "category": "lower_limb", "aliases": [], "definition": "足内侧纵弓塌陷，承重时足弓消失", "severity_levels": ["轻度", "中度", "重度"], "causes": [{"type": "结构性", "desc": "胫骨后肌功能不全、韧带松弛、遗传"}], "self_tests": [{"name": "湿足印测试", "steps": ["脚沾水踩纸", "观察足印形状"], "positive_sign": "足中部内侧印迹几乎填满", "image_key": "assets/images/tests/ll21_wet_foot.png", "tools_needed": "纸+水"}], "corrections": [{"type": "强化", "target_muscle": "足内在肌", "method": "短足运动（Short Foot）、抓毛巾", "freq": "每日2次"}], "consequences": [{"timeframe": "长期", "desc": "足底筋膜炎、向上连锁膝外翻"}], "red_flags": ["僵硬性扁平足、单侧突发塌陷伴疼痛需就医"], "related_issues": [{"id": "LL-23", "weight": 0.9, "relation": "共存"}, {"id": "LL-18", "weight": 0.9, "relation": "自下而上传导"}]},
    {"id": "LL-22", "name_cn": "高弓足", "name_en": "Pes Cavus", "category": "lower_limb", "aliases": [], "definition": "内侧纵弓异常增高，足印中段缺失", "severity_levels": ["轻度", "中度", "重度"], "causes": [{"type": "神经/遗传", "desc": "可能与Charcot-Marie-Tooth病等神经系统疾病相关"}], "self_tests": [{"name": "湿足印测试", "steps": ["脚沾水踩纸", "观察足印形状"], "positive_sign": "足中部印迹严重缺失", "image_key": "assets/images/tests/ll22_wet_foot.png", "tools_needed": "纸+水"}], "corrections": [{"type": "拉伸", "target_muscle": "足底筋膜、小腿后侧", "method": "足底滚球+小腿拉伸", "freq": "每日1次"}], "consequences": [{"timeframe": "长期", "desc": "减震差→应力性骨折、踝关节易扭伤"}], "red_flags": ["进行性高弓足或伴足部无力/麻木→就医排查神经疾病"], "related_issues": [{"id": "LL-24", "weight": 0.9, "relation": "共存"}]},
    {"id": "LL-23", "name_cn": "足外翻", "name_en": "Overpronation", "category": "lower_limb", "aliases": ["过度内旋"], "definition": "跟骨外翻，内侧纵弓过度塌陷", "severity_levels": ["轻度", "中度", "重度"], "causes": [{"type": "结构性", "desc": "跟骨外翻、胫骨后肌无力"}], "self_tests": [{"name": "后侧观察", "steps": ["从后方观察跟腱", "判断跟腱是否垂直"], "positive_sign": "跟腱向内侧弯曲、跟骨向外倾", "image_key": "assets/images/tests/ll23_rear_test.png", "tools_needed": "需他人观察"}], "corrections": [{"type": "强化", "target_muscle": "胫骨后肌、足内在肌", "method": "短足运动+提踵", "freq": "每日1次"}], "consequences": [{"timeframe": "长期", "desc": "足底筋膜炎、膝外翻连锁"}], "red_flags": [], "related_issues": [{"id": "LL-21", "weight": 0.9, "relation": "共存"}, {"id": "LL-18", "weight": 0.9, "relation": "自下而上传导"}]},
    {"id": "LL-24", "name_cn": "足内翻", "name_en": "Oversupination", "category": "lower_limb", "aliases": ["过度外旋"], "definition": "跟骨内翻，足外侧受力过多", "severity_levels": ["轻度", "中度", "重度"], "causes": [{"type": "结构性", "desc": "高弓足倾向、腓骨肌薄弱"}], "self_tests": [{"name": "鞋底观察", "steps": ["检查常穿鞋的鞋底磨损情况"], "positive_sign": "鞋底外侧磨损严重", "image_key": "assets/images/tests/ll24_shoe_test.png", "tools_needed": "常穿的鞋"}], "corrections": [{"type": "强化", "target_muscle": "腓骨肌", "method": "足外翻抗阻训练", "freq": "12次×3组"}], "consequences": [{"timeframe": "长期", "desc": "反复踝扭伤、足外侧劳损"}], "red_flags": [], "related_issues": [{"id": "LL-22", "weight": 0.9, "relation": "共存"}, {"id": "LL-19", "weight": 0.6, "relation": "力线相关"}]},
    # --- CP-25 ~ CP-26 复合综合征 ---
    {"id": "CP-25", "name_cn": "分层综合征", "name_en": "Layer Syndrome", "category": "compound", "aliases": [], "definition": "Janda提出的上交叉+下交叉混合型，上下半身同时存在肌肉失衡", "severity_levels": ["中度", "重度"], "causes": [{"type": "行为习惯", "desc": "长期久坐缺乏运动者（程序员、中年人群）"}], "self_tests": [{"name": "全身侧面拍照", "steps": ["侧面拍照", "综合检查是否同时有UCS和LCS特征"], "positive_sign": "同时具备头前倾+圆肩+驼背+骨盆前倾+腰曲增大", "image_key": "assets/images/tests/cp25_full_side.png", "tools_needed": "手机"}], "corrections": [{"type": "综合", "method": "需系统性分区域逐步纠正，建议专业指导", "freq": "长期"}], "consequences": [{"timeframe": "长期", "desc": "全身性慢性疼痛、多关节退变加速"}], "red_flags": [], "related_issues": [{"id": "ST-07", "weight": 0.9, "relation": "包含UCS"}, {"id": "PS-15", "weight": 0.9, "relation": "包含LCS"}]},
    {"id": "CP-26", "name_cn": "短信颈", "name_en": "Text Neck", "category": "compound", "aliases": [], "definition": "长期低头看手机导致的FHP+颈曲变直复合问题", "severity_levels": ["轻度", "中度", "重度"], "causes": [{"type": "行为习惯", "desc": "每天低头用手机>2-4小时"}], "self_tests": [{"name": "习惯自查", "steps": ["回忆每天低头用手机时长", "检查是否伴颈肩僵痛", "参照FHP自测（靠墙测试）"], "positive_sign": "每天低头>2小时且伴FHP体征", "image_key": "assets/images/tests/cp26_habit_test.png", "tools_needed": "无"}], "corrections": [{"type": "习惯", "desc": "抬高手机至眼平、每20-30分钟活动颈部", "freq": "持续"}, {"type": "强化", "target_muscle": "颈深屈肌", "method": "收下巴训练", "freq": "10次×3组/日"}], "consequences": [{"timeframe": "长期", "desc": "加速颈椎退变、慢性颈痛头痛"}], "red_flags": [], "related_issues": [{"id": "HN-01", "weight": 0.9, "relation": "同源"}, {"id": "HN-02", "weight": 0.9, "relation": "共存"}]},
]


CATEGORY_MAP = {
    "head_neck": "头颈部",
    "shoulder_thorax": "肩胸区",
    "pelvis_spine": "骨盆腰椎",
    "lower_limb": "下肢",
    "compound": "复合综合征",
}


def get_issue_by_id(issue_id: str) -> dict | None:
    """从 ISSUES 列表中按 id 查找问题"""
    for i in ISSUES:
        if i["id"] == issue_id:
            return i
    return None
```

> **说明：** 全部 26 项问题已完整录入 `ISSUES` 列表（单一列表，无拆分）。`get_issue_by_id` 函数定义在 knowledge.py 中，供 service.py 和 ai_service.py 统一调用。

- [ ] **Step 2: 提交**

```powershell
git add backend/app/posture/knowledge.py && git commit -m "feat: add posture issue knowledge base (26 items)"
```

---

### Task 8: 体态 API — 服务层

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
    self_test_answers: Mapped[dict] = mapped_column(JSONB, nullable=True)
    ai_response: Mapped[dict] = mapped_column(JSONB, nullable=True)
    photo_keys: Mapped[list] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 2: 编写 schemas**

`backend/app/posture/schemas.py`:
```python
from pydantic import BaseModel
from datetime import datetime

class IssueSummary(BaseModel):
    id: str
    name_cn: str
    category: str
    aliases: list[str]
    definition: str

class SelfTestStep(BaseModel):
    name: str
    steps: list[str]
    positive_sign: str
    image_key: str
    tools_needed: str

class IssueDetail(BaseModel):
    id: str
    name_cn: str
    name_en: str
    category: str
    aliases: list[str]
    definition: str
    severity_levels: list[str]
    causes: list[dict]
    self_tests: list[dict]
    corrections: list[dict]
    consequences: list[dict]
    red_flags: list[str]
    related_issues: list[dict]

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
import uuid
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.posture.models import PostureAssessment
from app.posture.knowledge import ISSUES, get_issue_by_id

def get_all_issues(category: str | None = None) -> list[dict]:
    if category:
        return [i for i in ISSUES if i["category"] == category]
    return ISSUES

# get_issue_by_id 已从 knowledge.py 导入，无需重复定义

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
        if issue.get("red_flags"):
            return "moderate", "自测结果为阳性，存在体态问题。建议关注纠正训练。如伴红旗征请及时就医。"
        return "moderate", "自测结果为阳性，建议进行以下纠正训练。"
    else:
        return "uncertain", "自测结果不确定。建议你使用AI拍照分析进行更精确的判断。"

async def save_self_assessment(
    db: AsyncSession,
    user_id: str,
    issue_id: str,
    answer: str,
    test_index: int,
) -> dict:
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
    issue = get_issue_by_id(issue_id)
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

async def get_user_history(db: AsyncSession, user_id: str, limit: int = 20) -> list[dict]:
    stmt = (
        select(PostureAssessment)
        .where(PostureAssessment.user_id == UUID(user_id))
        .order_by(desc(PostureAssessment.created_at))
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

```powershell
git add backend/app/posture/models.py backend/app/posture/schemas.py backend/app/posture/service.py && git commit -m "feat: add posture service layer"
```

---

### Task 9: 体态 API — 路由

**Files:**
- Create: `backend/app/posture/router.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 编写姿势分析路由**

`backend/app/posture/router.py`:
```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFound, BadRequest
from app.posture import service
from app.posture.schemas import (
    IssueDetail, SelfAssessRequest, PhotoAssessRequest, AssessmentRecord, RelatedIssue,
)

router = APIRouter(prefix="/api/v1/posture", tags=["posture"])

@router.get("/issues")
async def list_issues(category: str | None = Query(None)):
    issues = service.get_all_issues(category)
    return [{"id": i["id"], "name_cn": i["name_cn"], "category": i["category"], "aliases": i["aliases"], "definition": i["definition"]} for i in issues]

@router.get("/issues/{issue_id}")
async def get_issue_detail(issue_id: str):
    issue = service.get_issue_by_id(issue_id)
    if issue is None:
        raise NotFound("体态问题不存在")
    return issue

@router.get("/issues/{issue_id}/related")
async def get_related(issue_id: str):
    return service.get_related_issues(issue_id)

@router.post("/assess")
async def self_assess(request: SelfAssessRequest, user_id: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if request.answer not in ("positive", "negative", "uncertain"):
        raise BadRequest("答案只能是 positive/negative/uncertain")
    result = await service.save_self_assessment(db, user_id, request.issue_id, request.answer, request.test_index)
    if result is None:
        raise NotFound("体态问题不存在")
    return result

@router.post("/assess/photo")
async def photo_assess(request: PhotoAssessRequest, user_id: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.posture.ai_service import analyze_posture_photo
    issue = service.get_issue_by_id(request.issue_id)
    if issue is None:
        raise NotFound("体态问题不存在")
    if not request.photo_keys:
        raise BadRequest("请上传至少一张照片")
    ai_result = await analyze_posture_photo(request.issue_id, request.photo_keys, user_id, db)
    result = await service.save_photo_assessment(db, user_id, request.issue_id, request.photo_keys, ai_result)
    return result

@router.get("/history")
async def get_history(user_id: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await service.get_user_history(db, user_id)
```

- [ ] **Step 2: 注册路由到 main.py**

```python
# 在 main.py 中添加
from app.posture.router import router as posture_router
app.include_router(posture_router)
```

- [ ] **Step 3: 提交**

```powershell
git add backend/app/posture/router.py backend/app/main.py && git commit -m "feat: add posture API routes"
```

---

### Task 10: AI 服务 (Qwen VL)

**Files:**
- Create: `backend/app/posture/ai_service.py`

- [ ] **Step 1: 编写 AI 服务**

`backend/app/posture/ai_service.py`:
```python
import json
import httpx
from app.core.config import settings
from app.posture.knowledge import get_issue_by_id
from app.upload.service import generate_signed_url

QWEN_VL_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

async def analyze_posture_photo(
    issue_id: str,
    photo_keys: list[str],
    user_id: str,
    db,
) -> dict:
    issue = get_issue_by_id(issue_id)
    if not issue:
        return {"level": "normal", "confidence": 0, "evidence": [], "suggestion": "问题不存在", "need_retake": False}

    signed_urls = [generate_signed_url(key) for key in photo_keys]

    content_parts = []
    for url in signed_urls:
        content_parts.append({"type": "image_url", "image_url": {"url": url}})

    prompt = f"""你是一位专业的运动康复评估师。

当前评估问题：{issue['name_cn']}（{issue['definition']}）

请分析上传的照片，只用 JSON 格式回应（不要额外文字）：
{{"level": "normal|mild|moderate|severe", "confidence": 0.0-1.0, "evidence": ["依据1", "依据2"], "suggestion": "建议", "need_retake": false, "retake_reason": ""}}

重要：
- 仅供参考，不构成医疗诊断
- 如发现严重问题请建议就医
- 如照片角度/清晰度不足，need_retake设为true"""

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

    ai_result = json.loads(content)
    ai_result.setdefault("level", "normal")
    ai_result.setdefault("confidence", 0)
    ai_result.setdefault("evidence", [])
    ai_result.setdefault("suggestion", "")
    return ai_result
```

- [ ] **Step 2: 提交**

```powershell
git add backend/app/posture/ai_service.py && git commit -m "feat: add Qwen VL AI analysis service"
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
from datetime import datetime, timedelta, timezone
from app.core.config import settings

def generate_sts_credentials(user_id: str) -> dict:
    # 生产环境需调用阿里云 STS SDK 获取临时凭证
    # 此处为开发阶段占位实现，返回模拟凭证
    path_prefix = f"posture_photos/{user_id}/{uuid.uuid4().hex[:8]}/"
    return {
        "access_key_id": settings.ALIBABA_CLOUD_ACCESS_KEY_ID,
        "access_key_secret": settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET,
        "security_token": "",
        "bucket": settings.OSS_BUCKET,
        "region": settings.OSS_REGION,
        "endpoint": settings.OSS_ENDPOINT,
        "path_prefix": path_prefix,
    }

def generate_signed_url(object_key: str, expires_in: int = 3600) -> str:
    # 生产环境需用 OSS SDK 生成签名URL
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

```python
from app.upload.router import router as upload_router
app.include_router(upload_router)
```

- [ ] **Step 5: 提交**

```powershell
git add backend/app/upload/ backend/app/main.py && git commit -m "feat: add OSS upload module"
```

---

### Task 12: Alembic 迁移配置

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`

- [ ] **Step 1: 初始化 Alembic**

```powershell
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

```powershell
cd C:\Users\Lenovo\Desktop\develop\health\backend && alembic revision --autogenerate -m "init"
```

- [ ] **Step 4: 提交**

```powershell
git add backend/alembic.ini backend/alembic/ && git commit -m "feat: add Alembic migration setup"
```

---

### Task 13: 测试

**Files:**
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_auth.py`
- Create: `backend/tests/test_user.py`
- Create: `backend/tests/test_posture.py`

- [ ] **Step 1: 编写测试配置**

`backend/tests/conftest.py`:
```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.db.base import Base
from app.core.config import settings
from app.main import app

@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(settings.TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
```

- [ ] **Step 2: 编写认证测试**

`backend/tests/test_auth.py`:
```python
import pytest

@pytest.mark.asyncio
async def test_send_code(client):
    resp = await client.post("/api/v1/auth/send-code", json={"phone": "13800138000"})
    assert resp.status_code == 200
    assert resp.json()["message"] == "验证码已发送"

@pytest.mark.asyncio
async def test_register_invalid_code(client):
    resp = await client.post("/api/v1/auth/register", json={
        "phone": "13800138000",
        "code": "0000",
        "password": "123456",
    })
    assert resp.status_code == 400

@pytest.mark.asyncio
async def test_login_invalid_code(client):
    resp = await client.post("/api/v1/auth/login", json={
        "phone": "13800138000",
        "code": "0000",
    })
    assert resp.status_code == 400
```

- [ ] **Step 3: 运行测试**

```powershell
cd C:\Users\Lenovo\Desktop\develop\health\backend && python -m pytest tests/ -v
```

预期：3 个测试通过（验证码错误时返回 400）

- [ ] **Step 4: 提交**

```powershell
git add backend/tests/ && git commit -m "test: add auth tests"
```

---
