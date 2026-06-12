from fastapi import APIRouter, Depends
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.exceptions import AppException
from app.upload import service
from app.upload.schemas import STSTokenResponse

router = APIRouter(prefix="/api/v1/upload", tags=["upload"])


def _check_photo_analysis_enabled():
    if not settings.PHOTO_ANALYSIS_ENABLED:
        raise AppException(
            503,
            "照片分析在当前数据模式下未启用",
            "photo_analysis_disabled",
        )


@router.post("/sts-token", response_model=STSTokenResponse)
async def get_sts_token(user_id: str = Depends(get_current_user)):
    _check_photo_analysis_enabled()
    return service.generate_sts_credentials(user_id)
