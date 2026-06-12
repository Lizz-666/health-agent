from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.core.security import decode_token
from app.core.exceptions import Unauthorized

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
    return user_id
