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
