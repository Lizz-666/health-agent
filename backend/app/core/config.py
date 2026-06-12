from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/posture_app"
    SECRET_KEY: str = "CHANGE-ME-IN-PRODUCTION"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    ALIBABA_CLOUD_ACCESS_KEY_ID: str = ""
    ALIBABA_CLOUD_ACCESS_KEY_SECRET: str = ""
    OSS_ENDPOINT: str = "oss-cn-hangzhou.aliyuncs.com"
    OSS_BUCKET: str = "posture-app-bucket"
    OSS_REGION: str = "cn-hangzhou"

    DASHSCOPE_API_KEY: str = ""

    SMS_SIGN_NAME: str = ""
    SMS_TEMPLATE_CODE: str = ""

    DEV_MODE: bool = False
    TEST_DATABASE_URL: str = "sqlite+aiosqlite:///./test.db"

    # 照片分析门禁：默认关闭，需显式启用
    PHOTO_ANALYSIS_ENABLED: bool = False

    # 开发管理员账号（仅 DEV_MODE=True 时可用）
    DEV_ADMIN_PHONE: str = ""
    DEV_ADMIN_PASSWORD: str = ""


settings = Settings()
