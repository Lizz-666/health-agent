from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.exceptions import AppException
from app.auth.router import router as auth_router

app = FastAPI(title="体态分析 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
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
