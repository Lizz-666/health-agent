from pydantic import BaseModel, Field


class SendCodeRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11, pattern=r"^1[3-9]\d{9}$")


class SendCodeResponse(BaseModel):
    message: str = "验证码已发送"


class VerifyLoginRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11, pattern=r"^1[3-9]\d{9}$")
    code: str = Field(..., min_length=4, max_length=6)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    is_new_user: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


class DevLoginRequest(BaseModel):
    phone: str
    password: str


class TrialActivateRequest(BaseModel):
    invitation_code: str = Field(
        ..., min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"
    )
    account_name: str = Field(
        ..., min_length=4, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]+$"
    )
    provider_id: str = Field(
        default="offline_password", min_length=3, max_length=32, pattern=r"^[a-z0-9_]+$"
    )
    credential: str = Field(..., min_length=6, max_length=128)
    device_key: str = Field(..., min_length=32, max_length=128)


class TrialLoginRequest(BaseModel):
    account_name: str = Field(
        ..., min_length=4, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]+$"
    )
    provider_id: str = Field(
        default="offline_password", min_length=3, max_length=32, pattern=r"^[a-z0-9_]+$"
    )
    credential: str = Field(..., min_length=6, max_length=128)
    device_key: str = Field(..., min_length=32, max_length=128)


class LogoutRequest(BaseModel):
    refresh_token: str
