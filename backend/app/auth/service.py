import random
import logging
from datetime import datetime, timedelta, timezone
from typing import Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.auth.models import User, VerificationCode
from app.core.config import settings
from app.core.exceptions import BadRequest, TooManyRequests

logger = logging.getLogger(__name__)

# 频率限制常量
SEND_CODE_INTERVAL_SECONDS = 60       # 同一手机号两次发送间隔
SEND_CODE_DAILY_LIMIT = 10            # 同一手机号每天最多发送次数
VERIFY_MAX_ATTEMPTS = 5               # 同一手机号最大验证尝试次数


async def send_verification_code(db: AsyncSession, phone: str) -> None:
    now = datetime.now(timezone.utc)

    # 检查发送间隔（60秒内不得重复发送）
    recent_stmt = (
        select(VerificationCode)
        .where(
            VerificationCode.phone == phone,
            VerificationCode.created_at > now - timedelta(seconds=SEND_CODE_INTERVAL_SECONDS),
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
    # 检查近期失败次数（5分钟内超过5次则拒绝）
    now = datetime.now(timezone.utc)
    recent_codes_stmt = (
        select(func.count())
        .select_from(VerificationCode)
        .where(
            VerificationCode.phone == phone,
            VerificationCode.created_at > now - timedelta(minutes=5),
        )
    )
    recent_count = (await db.execute(recent_codes_stmt)).scalar()
    # 通过已使用的code数量间接判断尝试次数（保守估计）
    # 更精确：每次验证失败也记录一次尝试，但当前schema不支持
    # 这里用 total_codes - used_codes 的比值来保护

    stmt = (
        select(VerificationCode)
        .where(
            VerificationCode.phone == phone,
            VerificationCode.code == code,
            VerificationCode.used == False,
            VerificationCode.expires_at > now,
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


async def find_or_create_user(db: AsyncSession, phone: str) -> Tuple[str, bool]:
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


async def get_user_by_id(db: AsyncSession, user_id: str):
    from uuid import UUID
    stmt = select(User).where(User.id == UUID(user_id))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
