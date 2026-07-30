"""Test-only FastAPI factory for synthetic Agent E2E and device smoke.

Production ``app.main`` must never import this module. The caller must inject
both a provider instance and a disposable database dependency explicitly; no
environment variable or runtime setting can select this path.
"""
from __future__ import annotations

from typing import Callable

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.agent.messages import ResultCode, render
from app.agent.provider import AgentProvider
from app.agent.router import get_agent_provider, router as agent_router
from app.agent.schemas import AgentTurnResponse
from app.auth.router import router as auth_router
from app.core.exceptions import AppException
from app.db.database import get_db


def create_agent_test_app(
    *,
    provider: AgentProvider,
    get_db_override: Callable,
) -> FastAPI:
    test_app = FastAPI(title="Synthetic Agent Test App")
    test_app.dependency_overrides[get_db] = get_db_override
    test_app.dependency_overrides[get_agent_provider] = lambda: provider

    @test_app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code},
        )

    @test_app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        if request.url.path == "/api/v1/agent/turns":
            code = (
                ResultCode.INVALID_TIMEZONE
                if any(
                    tuple(error.get("loc", ()))[-1:] == ("iana_timezone",)
                    for error in exc.errors()
                )
                else ResultCode.INVALID_REQUEST
            )
            return JSONResponse(
                status_code=422,
                content=AgentTurnResponse(
                    status="failed",
                    result_code=code,
                    message=render(code),
                ).model_dump(mode="json"),
            )
        return await request_validation_exception_handler(request, exc)

    test_app.include_router(auth_router)
    test_app.include_router(agent_router)

    @test_app.get("/health")
    async def health():
        return {"status": "ok", "mode": "synthetic-agent-test"}

    return test_app


__all__ = ["create_agent_test_app"]
