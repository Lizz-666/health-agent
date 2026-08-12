from __future__ import annotations

import random
import logging
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Tuple
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from app.auth.credentials import hash_password, offline_password_provider
from app.auth.models import (
    AuthAttempt,
    AuthSession,
    TrialCredential,
    TrialDeviceEnrollment,
    TrialInvitation,
    User,
    VerificationCode,
)
from app.core.config import settings
from app.core.exceptions import AppException, TooManyRequests
from app.core.security import create_access_token, create_refresh_token

logger = logging.getLogger(__name__)
DUMMY_CREDENTIAL_HASH = hash_password(
    "synthetic-dummy-credential", salt=b"phase9-dummy-salt"
)


@dataclass(frozen=True)
class ProvisionedTrialAccount:
    user_id: str
    account_name: str
    invitation_code: str
    invitation_expires_at: datetime


@dataclass(frozen=True)
class TrialTokens:
    access_token: str
    refresh_token: str
    is_new_user: bool = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _subject_digest(account_name: str) -> str:
    key = (settings.AUTH_AUDIT_HMAC_KEY or settings.SECRET_KEY).encode("utf-8")
    return hmac.new(
        key, account_name.strip().casefold().encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _source_digest(source_key: str) -> str:
    key = (settings.AUTH_AUDIT_HMAC_KEY or settings.SECRET_KEY).encode("utf-8")
    return hmac.new(key, source_key.encode("utf-8"), hashlib.sha256).hexdigest()


def _auth_error() -> AppException:
    return AppException(401, "账号或凭据无效", "auth_failed")


def _activation_error() -> AppException:
    return AppException(400, "邀请码或账号凭据无效", "activation_failed")


async def _attempt_count(
    db: AsyncSession, account_name: str, source_key: str, result_code: str
) -> int:
    now = _utcnow()
    count = await db.scalar(
        select(func.count())
        .select_from(AuthAttempt)
        .where(
            (
                (AuthAttempt.subject_digest == _subject_digest(account_name))
                | (AuthAttempt.source_digest == _source_digest(source_key))
            ),
            AuthAttempt.attempted_at
            > now - timedelta(minutes=settings.AUTH_LOGIN_WINDOW_MINUTES),
            AuthAttempt.result_code == result_code,
        )
    )
    return count or 0


async def _record_attempt(
    db: AsyncSession, account_name: str, source_key: str, result_code: str
) -> None:
    db.add(
        AuthAttempt(
            subject_digest=_subject_digest(account_name),
            source_digest=_source_digest(source_key),
            result_code=result_code,
        )
    )
    await db.commit()


async def provision_trial_account(
    db: AsyncSession,
    *,
    account_name: str,
    password: str,
    invitation_ttl: timedelta = timedelta(days=7),
) -> ProvisionedTrialAccount:
    """Provision an offline-distributed account; never exposed as an HTTP route."""
    normalized = account_name.strip().casefold()
    if len(normalized) < 4 or len(password) < 12:
        raise ValueError("trial account name or password does not meet policy")
    code = secrets.token_urlsafe(32)
    now = _utcnow()
    user = User(phone=None)
    db.add(user)
    await db.flush()
    db.add_all(
        [
            TrialCredential(
                user_id=user.id,
                login_id=normalized,
                credential_hash=hash_password(password),
            ),
            TrialInvitation(
                user_id=user.id,
                code_digest=_digest(code),
                expires_at=now + invitation_ttl,
            ),
        ]
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError("trial account or invitation already exists") from None
    return ProvisionedTrialAccount(
        user_id=str(user.id),
        account_name=normalized,
        invitation_code=code,
        invitation_expires_at=now + invitation_ttl,
    )


async def reissue_trial_invitation(
    db: AsyncSession,
    *,
    account_name: str,
    invitation_ttl: timedelta = timedelta(days=7),
) -> str:
    """Operator-only device recovery: revoke sessions/device, issue a new invite."""
    stored = await _credential_for(db, account_name)
    if stored is None or stored.disabled_at is not None:
        raise ValueError("trial account is unavailable")
    now = _utcnow()
    code = secrets.token_urlsafe(32)
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == stored.user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    device_ids = select(TrialDeviceEnrollment.id).where(
        TrialDeviceEnrollment.user_id == stored.user_id
    )
    await db.execute(
        update(TrialDeviceEnrollment)
        .where(
            TrialDeviceEnrollment.id.in_(device_ids),
            TrialDeviceEnrollment.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await db.execute(
        update(TrialInvitation)
        .where(
            TrialInvitation.user_id == stored.user_id,
            TrialInvitation.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    db.add(
        TrialInvitation(
            user_id=stored.user_id,
            code_digest=_digest(code),
            expires_at=now + invitation_ttl,
        )
    )
    await db.commit()
    return code


async def _credential_for(
    db: AsyncSession, account_name: str
) -> TrialCredential | None:
    result = await db.execute(
        select(TrialCredential).where(
            TrialCredential.login_id == account_name.strip().casefold()
        )
    )
    return result.scalar_one_or_none()


async def _new_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    device: TrialDeviceEnrollment,
    is_new_user: bool = False,
) -> TrialTokens:
    # Serialize session replacement per account. This keeps a single active
    # mobile session even when two valid login requests race on PostgreSQL.
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=_utcnow())
    )
    session = AuthSession(
        user_id=user_id,
        device_id=device.id,
        expires_at=_utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(session)
    await db.flush()
    refresh = create_refresh_token(str(user_id), session_id=str(session.id))
    session.refresh_token_digest = _digest(refresh)
    await db.commit()
    return TrialTokens(
        access_token=create_access_token(str(user_id), session_id=str(session.id)),
        refresh_token=refresh,
        is_new_user=is_new_user,
    )


async def activate_trial_account(
    db: AsyncSession,
    *,
    invitation_code: str,
    account_name: str,
    provider_id: str,
    credential_value: str,
    device_key: str,
    source_key: str,
) -> TrialTokens:
    if await _attempt_count(
        db, account_name, source_key, "activation_rejected"
    ) >= settings.AUTH_LOGIN_MAX_ATTEMPTS:
        raise AppException(429, "激活尝试过多，请稍后重试", "auth_rate_limited")
    stored = await _credential_for(db, account_name)
    credential_hash = stored.credential_hash if stored else DUMMY_CREDENTIAL_HASH
    verified = offline_password_provider.verify(
        credential_value, credential_hash
    ).accepted
    if (
        not stored
        or stored.disabled_at is not None
        or stored.provider_id != provider_id
        or provider_id != settings.AUTH_CREDENTIAL_PROVIDER
        or not verified
    ):
        await _record_attempt(db, account_name, source_key, "activation_rejected")
        raise _activation_error()

    now = _utcnow()
    claimed = await db.execute(
        update(TrialInvitation)
        .where(
            TrialInvitation.code_digest == _digest(invitation_code),
            TrialInvitation.user_id == stored.user_id,
            TrialInvitation.consumed_at.is_(None),
            TrialInvitation.revoked_at.is_(None),
            TrialInvitation.expires_at > now,
        )
        .values(consumed_at=now)
        .returning(TrialInvitation.user_id)
    )
    if claimed.scalar_one_or_none() is None:
        await db.rollback()
        await _record_attempt(db, account_name, source_key, "activation_rejected")
        raise _activation_error()

    device = await db.scalar(
        select(TrialDeviceEnrollment).where(
            TrialDeviceEnrollment.user_id == stored.user_id
        )
    )
    if device is None:
        device = TrialDeviceEnrollment(
            user_id=stored.user_id, device_key_digest=_digest(device_key)
        )
        db.add(device)
    elif device.revoked_at is not None:
        device.device_key_digest = _digest(device_key)
        device.enrolled_at = now
        device.revoked_at = None
    else:
        await db.rollback()
        raise _activation_error()
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise _activation_error() from None
    return await _new_session(
        db, user_id=stored.user_id, device=device, is_new_user=True
    )


async def login_trial_account(
    db: AsyncSession,
    *,
    account_name: str,
    provider_id: str,
    credential_value: str,
    device_key: str,
    source_key: str,
) -> TrialTokens:
    if await _attempt_count(
        db, account_name, source_key, "login_rejected"
    ) >= settings.AUTH_LOGIN_MAX_ATTEMPTS:
        raise AppException(429, "登录尝试过多，请稍后重试", "auth_rate_limited")

    stored = await _credential_for(db, account_name)
    credential_hash = stored.credential_hash if stored else DUMMY_CREDENTIAL_HASH
    verified = offline_password_provider.verify(
        credential_value, credential_hash
    ).accepted
    if (
        not stored
        or stored.disabled_at is not None
        or stored.provider_id != provider_id
        or provider_id != settings.AUTH_CREDENTIAL_PROVIDER
        or not verified
    ):
        await _record_attempt(db, account_name, source_key, "login_rejected")
        raise _auth_error()

    device = await db.scalar(
        select(TrialDeviceEnrollment).where(
            TrialDeviceEnrollment.user_id == stored.user_id,
            TrialDeviceEnrollment.revoked_at.is_(None),
        )
    )
    if device is None or not hmac.compare_digest(
        device.device_key_digest, _digest(device_key)
    ):
        raise AppException(403, "此账号已绑定其他试用设备", "trial_device_conflict")
    return await _new_session(db, user_id=stored.user_id, device=device)


async def rotate_trial_refresh(
    db: AsyncSession, refresh_token: str, payload: dict
) -> TrialTokens:
    try:
        session_id = uuid.UUID(payload["sid"])
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise _auth_error() from None
    now = _utcnow()
    current = await db.scalar(
        select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
            AuthSession.refresh_token_digest == _digest(refresh_token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
    )
    if current is None:
        raise _auth_error()
    device = await db.scalar(
        select(TrialDeviceEnrollment).where(
            TrialDeviceEnrollment.id == current.device_id,
            TrialDeviceEnrollment.user_id == user_id,
            TrialDeviceEnrollment.revoked_at.is_(None),
        )
    )
    credential = await db.scalar(
        select(TrialCredential).where(
            TrialCredential.user_id == user_id,
            TrialCredential.disabled_at.is_(None),
        )
    )
    if device is None or credential is None:
        raise _auth_error()

    replacement = AuthSession(
        user_id=user_id,
        device_id=device.id,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(replacement)
    await db.flush()
    replacement_refresh = create_refresh_token(
        str(user_id), session_id=str(replacement.id)
    )
    replacement.refresh_token_digest = _digest(replacement_refresh)
    rotated = await db.execute(
        update(AuthSession)
        .where(AuthSession.id == current.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now, replaced_by_session_id=replacement.id)
        .returning(AuthSession.id)
    )
    if rotated.scalar_one_or_none() is None:
        await db.rollback()
        raise _auth_error()
    await db.commit()
    return TrialTokens(
        access_token=create_access_token(
            str(user_id), session_id=str(replacement.id)
        ),
        refresh_token=replacement_refresh,
    )


async def revoke_trial_session(
    db: AsyncSession, refresh_token: str, payload: dict
) -> None:
    try:
        session_id = uuid.UUID(payload["sid"])
    except (KeyError, ValueError, TypeError):
        return
    await db.execute(
        update(AuthSession)
        .where(
            AuthSession.id == session_id,
            AuthSession.refresh_token_digest == _digest(refresh_token),
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=_utcnow())
    )
    await db.commit()


async def is_trial_session_active(
    db: AsyncSession, *, session_id: str, user_id: str
) -> bool:
    try:
        sid = uuid.UUID(session_id)
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        return False
    now = _utcnow()
    session = await db.scalar(
        select(AuthSession.id)
        .join(TrialCredential, TrialCredential.user_id == AuthSession.user_id)
        .join(
            TrialDeviceEnrollment,
            TrialDeviceEnrollment.id == AuthSession.device_id,
        )
        .where(
            AuthSession.id == sid,
            AuthSession.user_id == uid,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
            TrialCredential.disabled_at.is_(None),
            TrialDeviceEnrollment.revoked_at.is_(None),
        )
    )
    return session is not None

# 频率限制常量
SEND_CODE_INTERVAL_SECONDS = 60  # 同一手机号两次发送间隔
SEND_CODE_DAILY_LIMIT = 10  # 同一手机号每天最多发送次数
VERIFY_MAX_ATTEMPTS = 5  # 同一手机号最大验证尝试次数


async def send_verification_code(db: AsyncSession, phone: str) -> None:
    now = datetime.now(timezone.utc)

    # 检查发送间隔（60秒内不得重复发送）
    recent_stmt = (
        select(VerificationCode)
        .where(
            VerificationCode.phone == phone,
            VerificationCode.created_at
            > now - timedelta(seconds=SEND_CODE_INTERVAL_SECONDS),
        )
        .order_by(VerificationCode.created_at.desc())
        .limit(1)
    )
    recent_result = await db.execute(recent_stmt)
    if recent_result.scalar_one_or_none() is not None:
        raise TooManyRequests(f"发送过于频繁，请{SEND_CODE_INTERVAL_SECONDS}秒后重试")

    # 检查每日发送上限
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    count_stmt = select(func.count()).where(
        VerificationCode.phone == phone,
        VerificationCode.created_at > today_start,
    )
    count_result = await db.execute(count_stmt)
    daily_count = count_result.scalar()
    if daily_count >= SEND_CODE_DAILY_LIMIT:
        raise TooManyRequests("今日发送次数已达上限")

    code = f"{random.randint(100000, 999999)}"
    vc = VerificationCode(
        phone=phone,
        code=code,
        expires_at=now + timedelta(minutes=5),
    )
    db.add(vc)
    await db.commit()

    if settings.DEV_MODE:
        logger.info(f"[DEV] 验证码: phone={phone}, code={code}")
    else:
        # TODO: 调用阿里云短信服务发送验证码
        pass


async def verify_code(db: AsyncSession, phone: str, code: str) -> bool:
    now = datetime.now(timezone.utc)
    recent_codes_stmt = (
        select(func.count())
        .select_from(VerificationCode)
        .where(
            VerificationCode.phone == phone,
            VerificationCode.created_at > now - timedelta(minutes=5),
        )
    )
    recent_count: int = (await db.execute(recent_codes_stmt)).scalar() or 0
    if recent_count >= VERIFY_MAX_ATTEMPTS:
        raise TooManyRequests("验证尝试次数过多，请重新获取验证码")

    stmt = (
        update(VerificationCode)
        .where(
            VerificationCode.phone == phone,
            VerificationCode.code == code,
            VerificationCode.used.is_(False),
            VerificationCode.expires_at > now,
        )
        .values(used=True)
        .returning(VerificationCode.id)
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        await db.commit()
        return True
    return False


async def find_or_create_user(db: AsyncSession, phone: str) -> Tuple[str, bool]:
    """返回 (user_id, is_new_user)"""
    stmt = select(User).where(User.phone == phone)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        return str(user.id), False

    try:
        user = User(phone=phone)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return str(user.id), True
    except IntegrityError:
        await db.rollback()
        result = await db.execute(select(User).where(User.phone == phone))
        user = result.scalar_one()
        return str(user.id), False


async def get_user_by_id(db: AsyncSession, user_id: str):
    from uuid import UUID

    try:
        uid = UUID(user_id)
    except ValueError:
        return None
    stmt = select(User).where(User.id == uid)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
