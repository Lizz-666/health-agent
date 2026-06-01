from typing import Optional
from pydantic import BaseModel, Field


class UserProfileResponse(BaseModel):
    id: str
    phone: str
    nickname: Optional[str] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    membership_level: str = "free"
    created_at: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    nickname: Optional[str] = Field(None, max_length=50)
    height: Optional[float] = Field(None, gt=0, le=300)
    weight: Optional[float] = Field(None, gt=0, le=500)
    age: Optional[int] = Field(None, gt=0, lt=150)
    gender: Optional[str] = Field(None, pattern="^(male|female)$")
