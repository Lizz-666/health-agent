from fastapi import Depends

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.exceptions import AppException


async def require_photo_analysis(user_id: str = Depends(get_current_user)):
    """FastAPI dependency that blocks photo-related endpoints when disabled.

    Depends on get_current_user so that authentication (401) is enforced
    before the feature-gate check (503).  Use as
    ``dependencies=[Depends(require_photo_analysis)]`` on route decorators
    so the combined auth+gate check runs before request-body validation.
    """
    if not settings.PHOTO_ANALYSIS_ENABLED:
        raise AppException(
            503,
            "照片分析在当前数据模式下未启用",
            "photo_analysis_disabled",
        )
