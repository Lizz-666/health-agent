from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.core.security import decode_token
from app.core.exceptions import Unauthorized
from app.auth.service import is_trial_session_active
from app.core.config import settings

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> str:
    if credentials is None:
        raise Unauthorized("请先登录")
    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    if user_id is None or payload.get("type") != "access":
        raise Unauthorized("Token 无效或已过期")
    session_id = payload.get("sid")
    if settings.AUTH_MODE == "controlled_trial" and not session_id:
        raise Unauthorized("Token invalid or expired")
    if session_id and settings.AUTH_MODE != "controlled_trial":
        raise Unauthorized("Token invalid or expired")
    if session_id and not await is_trial_session_active(
        db, session_id=session_id, user_id=user_id
    ):
        raise Unauthorized("Token invalid or expired")
    return user_id
