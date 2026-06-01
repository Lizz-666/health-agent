from pydantic import BaseModel, Field


class UserProfileResponse(BaseModel):
    id: str
    phone: str
    nickname: str | None = None
    height: float | None = None
    weight: float | None = None
    age: int | None = None
    gender: str | None = None
    membership_level: str = "free"
    created_at: str | None = None


class UpdateProfileRequest(BaseModel):
    nickname: str | None = Field(None, max_length=50)
    height: float | None = Field(None, gt=0, le=300)
    weight: float | None = Field(None, gt=0, le=500)
    age: int | None = Field(None, gt=0, lt=150)
    gender: str | None = Field(None, pattern="^(male|female)$")
