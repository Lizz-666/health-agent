from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.auth.models import User as UserModel
from app.user.schemas import UpdateProfileRequest, UserProfileResponse
from app.core.exceptions import NotFound


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


async def get_profile(db: AsyncSession, user_id: str) -> Optional[UserProfileResponse]:
    result = await db.execute(select(UserModel).where(UserModel.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        return None
    return _to_profile(user)


async def update_profile(db: AsyncSession, user_id: str, request: UpdateProfileRequest) -> UserProfileResponse:
    result = await db.execute(select(UserModel).where(UserModel.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFound("用户不存在")
    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)
    await db.commit()
    await db.refresh(user)
    return _to_profile(user)
