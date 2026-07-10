from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime


class PostureLevel(str, Enum):
    normal = "normal"
    mild = "mild"
    moderate = "moderate"
    severe = "severe"


# --- Nested structured models for IssueDetail ---


class Cause(BaseModel):
    type: str
    desc: str


class SelfTestSchema(BaseModel):
    name: str
    steps: List[str]
    positive_sign: str
    image_key: str
    tools_needed: str


class Correction(BaseModel):
    type: str
    target_muscle: Optional[str] = None
    method: Optional[str] = None
    freq: Optional[str] = None
    desc: Optional[str] = None


class Consequence(BaseModel):
    timeframe: str
    desc: str


class RelatedIssueRef(BaseModel):
    id: str
    weight: float
    relation: str


# --- Response models ---


class IssueSummary(BaseModel):
    id: str
    name_cn: str
    category: str
    aliases: List[str]
    definition: str


class IssueDetail(BaseModel):
    id: str
    name_cn: str
    name_en: str
    category: str
    aliases: List[str]
    definition: str
    severity_levels: List[str]
    causes: List[Cause]
    self_tests: List[SelfTestSchema]
    corrections: List[Correction]
    consequences: List[Consequence]
    red_flags: List[str]
    related_issues: List[RelatedIssueRef]


class RelatedIssue(BaseModel):
    id: str
    name_cn: str
    weight: float
    relation: str


# --- AI analysis schema ---


class AIAnalysisResult(BaseModel):
    """Strict schema for AI model output. Rejects missing or invalid fields."""

    level: PostureLevel
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: List[str]
    suggestion: str
    need_retake: bool
    retake_reason: str = ""

    model_config = ConfigDict(strict=True, extra="forbid")


# --- Request models ---


class SelfAssessRequest(BaseModel):
    issue_id: str
    test_index: int = 0
    answer: str  # "positive" | "negative" | "uncertain"


class PhotoAssessRequest(BaseModel):
    issue_id: str
    photo_keys: List[str]


# --- Response models for assessment ---


class SelfAssessResponse(BaseModel):
    id: str
    issue_id: str
    result: str
    suggestion: str


class AssessmentRecord(BaseModel):
    id: str
    issue_id: str
    issue_name: str
    method: str
    result: str
    created_at: datetime
