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

    # 照片隐私门数据生命周期配置（规格 §13.3/§13.4）
    # 注意：这些配置项本身不满足隐私门条件，条件需要可验证的实现证据。
    PHOTO_RETENTION_DAYS: int = 90
    PHOTO_CONSENT_REQUIRED: bool = True

    # Purge 应用层加密密钥（规格 §6.7）：hex 编码的 32 字节 AES-256 密钥。
    # 用于加密 purge_operations.encrypted_object_keys（photo_keys）。密钥不入库、
    # 不入日志。调用 purge 时必须配置；生产环境无默认值，留空则 purge 拒绝执行。
    PURGE_ENCRYPTION_KEY: str = ""

    # Hardening fix #7: versioned key ring (JSON map: {"v1": "<hex>", "v2": "<hex>"}).
    # When set, takes precedence over PURGE_ENCRYPTION_KEY for new encryptions.
    # Decrypt reads key_version from blob header and selects the corresponding key.
    PURGE_ENCRYPTION_KEYS: str = ""  # JSON string, e.g. '{"v1":"<64hex>","v2":"<64hex>"}'
    PURGE_ACTIVE_KEY_VERSION: str = "v1"

    # 开发管理员账号（仅 DEV_MODE=True 时可用）
    DEV_ADMIN_PHONE: str = ""
    DEV_ADMIN_PASSWORD: str = ""

    # Phase 5 Agent MVP (Task 1): dedicated server-only audit HMAC key + version.
    # Empty by default and never client/model input. The Agent audit/context/
    # argument fingerprints are keyed HMAC-SHA256 with this secret; when it is
    # empty the fingerprint capability fails closed (spec Provider And
    # Orchestrator Contract, Consent And Privacy Gate #9, Acceptance #15).
    # Changing the key/version invalidates and scrubs pending proposals before
    # new runs are accepted (wired in a later batch). The secret never enters the
    # repository, responses, logs, CI artifacts, or Flutter defines.
    AGENT_AUDIT_HMAC_KEY: str = ""
    AGENT_AUDIT_HMAC_KEY_VERSION: str = ""

    # Phase 5 Agent runtime/live provider. The runtime remains fail-closed until
    # every value, current consent, disclosure, and privacy-gate condition is
    # satisfied. No client/model field can override these server settings.
    AGENT_RUNTIME_ENABLED: bool = False
    AGENT_PROVIDER_ID: str = ""
    AGENT_MODEL_ID: str = ""
    AGENT_DISCLOSURE_VERSION: str = ""
    AGENT_PROVIDER_BASE_URL: str = (
        "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    AGENT_PROVIDER_CONNECT_TIMEOUT_SECONDS: float = 5.0
    AGENT_PROVIDER_READ_TIMEOUT_SECONDS: float = 20.0
    AGENT_PROVIDER_MAX_RESPONSE_BYTES: int = 65536

    # Phase 6 nutrition recommendation runtime. Default-off while the feature
    # is under staged review. Deletion remains available even when disabled.
    NUTRITION_RUNTIME_ENABLED: bool = False


settings = Settings()
