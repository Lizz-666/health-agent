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
