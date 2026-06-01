import uuid
from app.core.config import settings


def generate_sts_credentials(user_id: str) -> dict:
    path_prefix = f"posture_photos/{user_id}/{uuid.uuid4().hex[:8]}/"
    if settings.DEV_MODE:
        return {
            "access_key_id": "DEV_MODE_MOCK_KEY",
            "access_key_secret": "DEV_MODE_MOCK_SECRET",
            "security_token": "DEV_MODE_MOCK_TOKEN",
            "bucket": settings.OSS_BUCKET,
            "region": settings.OSS_REGION,
            "endpoint": settings.OSS_ENDPOINT,
            "path_prefix": path_prefix,
        }
    # TODO: 生产环境调用阿里云 STS SDK 获取临时凭证
    return {
        "access_key_id": "",
        "access_key_secret": "",
        "security_token": "",
        "bucket": settings.OSS_BUCKET,
        "region": settings.OSS_REGION,
        "endpoint": settings.OSS_ENDPOINT,
        "path_prefix": path_prefix,
    }


def generate_signed_url(object_key: str, expires_in: int = 3600) -> str:
    if settings.DEV_MODE:
        return f"https://{settings.OSS_BUCKET}.{settings.OSS_ENDPOINT}/{object_key}"
    # TODO: 生产环境用 OSS SDK 生成签名 URL
    return f"https://{settings.OSS_BUCKET}.{settings.OSS_ENDPOINT}/{object_key}"
