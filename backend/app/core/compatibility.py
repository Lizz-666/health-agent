from __future__ import annotations

import re

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import settings


CLIENT_PLATFORM_HEADER = "X-Client-Platform"
CLIENT_VERSION_HEADER = "X-Client-Version-Code"
_ANDROID = "android"
_VERSION_PATTERN = re.compile(r"^[1-9][0-9]*$")


def reject_incompatible_client(request: Request) -> JSONResponse | None:
    """Fail closed before candidate API routes can read or write domain state."""
    if settings.DEPLOYMENT_PROFILE != "controlled_trial_candidate":
        return None
    path = str((getattr(request, "scope", {}) or {}).get("path") or "")
    if not path.startswith("/api/v1/"):
        return None

    platform = request.headers.get(CLIENT_PLATFORM_HEADER)
    raw_version = request.headers.get(CLIENT_VERSION_HEADER, "")
    accepted = platform == _ANDROID and _VERSION_PATTERN.fullmatch(raw_version)
    version = int(raw_version) if accepted else None
    if (
        version is not None
        and settings.MIN_ANDROID_CLIENT_VERSION_CODE
        <= version
        <= settings.MAX_ANDROID_CLIENT_VERSION_CODE
    ):
        return None
    return JSONResponse(
        status_code=426,
        content={
            "detail": "当前应用版本不兼容，请更新后重试",
            "code": "client_version_incompatible",
        },
    )


__all__ = [
    "CLIENT_PLATFORM_HEADER",
    "CLIENT_VERSION_HEADER",
    "reject_incompatible_client",
]
