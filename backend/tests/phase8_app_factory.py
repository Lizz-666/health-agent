"""Test-only full FastAPI assembly for Phase 8 real-HTTP acceptance."""
from __future__ import annotations

import logging
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.agent.messages import ResultCode, render
from app.agent.router import get_agent_provider, router as agent_router
from app.agent.schemas import AgentTurnResponse
from app.auth.router import router as auth_router
from app.core.exceptions import AppException
from app.db.database import get_db
from app.health.router import router as health_router
from app.nutrition.router import router as nutrition_router
from app.posture.router import router as posture_router
from app.training.router import router as training_router
from app.upload.router import router as upload_router
from app.user.router import router as user_router


logger = logging.getLogger("tests.phase8")


def create_phase8_test_app(
    *,
    get_db_override: Callable,
    get_provider_override: Callable,
    control=None,
    lifespan=None,
) -> FastAPI:
    """Assemble every production router with explicit test dependencies."""
    test_app = FastAPI(title="Synthetic Phase 8 Test App", lifespan=lifespan)
    test_app.dependency_overrides[get_db] = get_db_override
    test_app.dependency_overrides[get_agent_provider] = get_provider_override

    @test_app.exception_handler(AppException)
    async def app_exception_handler(_request: Request, exc: AppException):
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

    @test_app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        route = (getattr(request, "scope", {}) or {}).get("route")
        logger.error(
            "Unhandled exception type=%s on %s %s",
            type(exc).__name__,
            request.method,
            getattr(route, "path", "unmatched-route"),
        )
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Service temporarily unavailable",
                "code": "service_unavailable",
            },
        )

    for router in (
        auth_router,
        user_router,
        posture_router,
        upload_router,
        health_router,
        training_router,
        nutrition_router,
        agent_router,
    ):
        test_app.include_router(router)

    @test_app.get("/health")
    async def health():
        return {"status": "ok", "mode": "synthetic-phase8-test"}

    if control is not None:
        control.install(test_app)
    return test_app


__all__ = ["create_phase8_test_app"]
