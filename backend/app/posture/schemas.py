from typing import List
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime


class PostureLevel(str, Enum):
    normal = "normal"
    mild = "mild"
    moderate = "moderate"
    severe = "severe"


class AIAnalysisResult(BaseModel):
    """Strict schema for AI model output. Rejects missing or invalid fields."""

    level: PostureLevel
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: List[str]
    suggestion: str
    need_retake: bool
    retake_reason: str = ""

    model_config = ConfigDict(strict=True, extra="forbid")


class SelfAssessRequest(BaseModel):
    issue_id: str
    test_index: int = 0
    answer: str  # "positive" | "negative" | "uncertain"


class SelfAssessResponse(BaseModel):
    id: str
    issue_id: str
    result: str
    suggestion: str


class PhotoAssessRequest(BaseModel):
    issue_id: str
    photo_keys: List[str]


class AssessmentRecord(BaseModel):
    id: str
    issue_id: str
    issue_name: str
    method: str
    result: str
    created_at: datetime


class RelatedIssue(BaseModel):
    id: str
    name_cn: str
    weight: float
    relation: str
