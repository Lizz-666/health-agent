from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.auth.schemas import (
    SendCodeRequest,
    SendCodeResponse,
    VerifyLoginRequest,
    TokenResponse,
    RefreshRequest,
    DevLoginRequest,
)
from app.auth import service
from app.core.config import settings
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
async def refresh(request: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(request.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise Unauthorized("Refresh Token 无效")
    user_id = payload["sub"]
    # 验证用户仍然存在
    user = await service.get_user_by_id(db, user_id)
    if user is None:
        raise Unauthorized("用户不存在或已禁用")
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.post("/dev-login", response_model=TokenResponse)
async def dev_login(request: DevLoginRequest, db: AsyncSession = Depends(get_db)):
    """开发环境管理员密码登录，仅 DEV_MODE=True 时可用"""
    if not settings.DEV_MODE:
        raise BadRequest("该接口仅开发环境可用")
    if not settings.DEV_ADMIN_PHONE or not settings.DEV_ADMIN_PASSWORD:
        raise BadRequest("开发管理员账号未配置")
    if (
        request.phone != settings.DEV_ADMIN_PHONE
        or request.password != settings.DEV_ADMIN_PASSWORD
    ):
        raise BadRequest("账号或密码错误")
    user_id, is_new = await service.find_or_create_user(db, request.phone)
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        is_new_user=is_new,
    )
