import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.exceptions import AppException
from app.auth.router import router as auth_router

logger = logging.getLogger("app.main")

app = FastAPI(title="体态分析 API", version="0.1.0")

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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Hardening fix #9: catch-all for unhandled exceptions on posture routes.

    Returns a structured 503 response instead of raw 500, preventing internal
    error details from leaking to clients. The exception is logged server-side.
    """
    # Do not log the exception message or traceback here: DB/validation errors
    # can embed health payloads or object keys in parameters. Operational logs
    # retain only the exception type and request route.
    logger.error(
        "Unhandled exception type=%s on %s %s",
        type(exc).__name__,
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": "服务暂时不可用，请稍后重试",
            "code": "service_unavailable",
        },
    )


app.include_router(auth_router)

from app.user.router import router as user_router

app.include_router(user_router)

from app.posture.router import router as posture_router

app.include_router(posture_router)

from app.upload.router import router as upload_router

app.include_router(upload_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
