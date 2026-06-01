from typing import List
from pydantic import BaseModel
from datetime import datetime


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
