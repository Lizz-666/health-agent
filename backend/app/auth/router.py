from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.auth.schemas import (
    SendCodeRequest,
    SendCodeResponse,
    VerifyLoginRequest,
    TokenResponse,
    RefreshRequest,
    DevLoginRequest,
    LogoutRequest,
    TrialActivateRequest,
    TrialLoginRequest,
)
from app.auth import service
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.core.exceptions import AppException, BadRequest, Unauthorized

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _require_legacy_auth() -> None:
    if settings.AUTH_MODE != "legacy":
        raise AppException(404, "认证方式不可用", "auth_method_unavailable")


def _require_trial_auth() -> None:
    if settings.AUTH_MODE != "controlled_trial":
        raise AppException(404, "认证方式不可用", "auth_method_unavailable")


@router.post("/send-code", response_model=SendCodeResponse)
async def send_code(request: SendCodeRequest, db: AsyncSession = Depends(get_db)):
    _require_legacy_auth()
    await service.send_verification_code(db, request.phone)
    return SendCodeResponse()


@router.post("/verify-login", response_model=TokenResponse)
async def verify_login(request: VerifyLoginRequest, db: AsyncSession = Depends(get_db)):
    _require_legacy_auth()
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
    if settings.AUTH_MODE == "controlled_trial" and not (
        payload.get("sid") and payload.get("type") == "refresh"
    ):
        raise Unauthorized("Refresh Token 无效")
    if payload.get("sid") and payload.get("type") == "refresh":
        _require_trial_auth()
        tokens = await service.rotate_trial_refresh(db, request.refresh_token, payload)
        return TokenResponse(**tokens.__dict__)
    _require_legacy_auth()
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
    _require_legacy_auth()
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


@router.post("/trial/activate", response_model=TokenResponse)
async def trial_activate(
    request: TrialActivateRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    _require_trial_auth()
    tokens = await service.activate_trial_account(
        db,
        invitation_code=request.invitation_code,
        account_name=request.account_name,
        provider_id=request.provider_id,
        credential_value=request.credential,
        device_key=request.device_key,
        source_key=http_request.client.host if http_request.client else "unknown",
    )
    return TokenResponse(**tokens.__dict__)


@router.post("/trial/login", response_model=TokenResponse)
async def trial_login(
    request: TrialLoginRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    _require_trial_auth()
    tokens = await service.login_trial_account(
        db,
        account_name=request.account_name,
        provider_id=request.provider_id,
        credential_value=request.credential,
        device_key=request.device_key,
        source_key=http_request.client.host if http_request.client else "unknown",
    )
    return TokenResponse(**tokens.__dict__)


@router.post("/trial/logout", status_code=204)
async def trial_logout(request: LogoutRequest, db: AsyncSession = Depends(get_db)):
    _require_trial_auth()
    payload = decode_token(request.refresh_token)
    if payload and payload.get("type") == "refresh" and payload.get("sid"):
        await service.revoke_trial_session(db, request.refresh_token, payload)
