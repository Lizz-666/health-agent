from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid
import jwt
from app.core.config import settings


def _base_payload(user_id: str, token_type: str, expire: datetime) -> dict:
    return {
        "sub": user_id,
        "exp": expire,
        "type": token_type,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }


def create_access_token(user_id: str, *, session_id: str | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = _base_payload(user_id, "access", expire)
    if session_id:
        payload.update({"sid": session_id, "jti": str(uuid.uuid4())})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(user_id: str, *, session_id: str | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = _base_payload(user_id, "refresh", expire)
    if session_id:
        payload.update({"sid": session_id, "jti": str(uuid.uuid4())})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
        )
    except jwt.PyJWTError:
        return {}
