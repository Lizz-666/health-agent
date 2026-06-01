from fastapi import APIRouter, Depends
from app.core.dependencies import get_current_user
from app.upload import service
from app.upload.schemas import STSTokenResponse

router = APIRouter(prefix="/api/v1/upload", tags=["upload"])


@router.post("/sts-token", response_model=STSTokenResponse)
async def get_sts_token(user_id: str = Depends(get_current_user)):
    return service.generate_sts_credentials(user_id)
