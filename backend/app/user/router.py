from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.core.dependencies import get_current_user, require_sensitive_health_consent
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
    user_id: str = Depends(require_sensitive_health_consent),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_profile(db, user_id, request)
