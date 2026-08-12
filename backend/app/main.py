import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.agent.messages import ResultCode, render
from app.agent.persistence import cleanup_expired_runs
from app.agent.router import router as agent_router
from app.agent.schemas import AgentTurnResponse
from app.auth.router import router as auth_router
from app.core.exceptions import AppException
from app.health.router import router as health_router
from app.nutrition.router import router as nutrition_router
from app.posture.router import router as posture_router
from app.training.router import router as training_router
from app.upload.router import router as upload_router
from app.user.router import router as user_router
from app.db.database import async_session

logger = logging.getLogger("app.main")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Best-effort Agent audit retention cleanup; no payloads are logged."""
    async with async_session() as db:
        try:
            result = await cleanup_expired_runs(db)
            if result.runs_deleted:
                logger.info(
                    "Agent retention cleanup runs=%d events=%d proposals=%d",
                    result.runs_deleted,
                    result.tool_events_deleted,
                    result.proposals_deleted,
                )
        except Exception as exc:
            await db.rollback()
            logger.warning(
                "Agent retention cleanup failed type=%s", type(exc).__name__
            )
    yield


app = FastAPI(title="体态分析 API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Turn validation uses a stable fail-closed envelope. A missing timezone
    # keeps its dedicated code; all other validation errors are generic. Never
    # echo validation input because it may contain the ephemeral user message.
    if request.url.path.startswith("/api/v1/auth/trial/"):
        return JSONResponse(
            status_code=422,
            content={
                "detail": "认证请求格式无效",
                "code": "auth_invalid_request",
            },
        )
    if request.url.path == "/api/v1/agent/turns":
        code = (
            ResultCode.INVALID_TIMEZONE
            if any(
                error.get("loc", ())[-1:] == ("iana_timezone",)
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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Hardening fix #9: catch-all for unhandled exceptions on posture routes.

    Returns a structured 503 response instead of raw 500, preventing internal
    error details from leaking to clients. The exception is logged server-side.
    """
    # Do not log the exception message or traceback here: DB/validation errors
    # can embed health payloads or object keys in parameters. Operational logs
    # retain only the exception type and request route.
    scope = getattr(request, "scope", {}) or {}
    route = scope.get("route")
    route_path = getattr(route, "path", "unmatched-route")
    logger.error(
        "Unhandled exception type=%s on %s %s",
        type(exc).__name__,
        request.method,
        route_path,
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": "服务暂时不可用，请稍后重试",
            "code": "service_unavailable",
        },
    )


app.include_router(auth_router)
app.include_router(user_router)
app.include_router(posture_router)
app.include_router(upload_router)
app.include_router(health_router)
app.include_router(training_router)
app.include_router(nutrition_router)
app.include_router(agent_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
