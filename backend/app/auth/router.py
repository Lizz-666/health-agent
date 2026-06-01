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
