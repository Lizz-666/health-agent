"""Loopback-only ASGI guard for the synthetic Phase 8 device server."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})


def install_loopback_guard(app: FastAPI) -> None:
    @app.middleware("http")
    async def require_loopback_scope(request: Request, call_next):
        server = request.scope.get("server")
        if not server or server[0] not in LOOPBACK_HOSTS:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Phase 8 synthetic server requires loopback",
                    "code": "phase8_loopback_required",
                },
            )
        return await call_next(request)


__all__ = ["LOOPBACK_HOSTS", "install_loopback_guard"]
