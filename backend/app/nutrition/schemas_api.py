"""Strict JWT nutrition request and response contracts."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.nutrition.schemas import (
    DayKind,
    FoodRecord,
    GateStatus,
    MealName,
    NutritionTargetRanges,
    NutritionVersions,
    RecommendationPayload,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EligibilityResponse(ApiModel):
    gate: GateStatus
    reason_codes: List[str]
    missing_field_codes: List[str]
    bmi_category: Optional[str] = None
    versions: NutritionVersions


class TargetsResponse(ApiModel):
    gate: GateStatus
    targets: NutritionTargetRanges
    versions: NutritionVersions


class FoodListResponse(ApiModel):
    catalog_version: str
    foods: List[FoodRecord]


class RecommendationView(ApiModel):
    recommendation_id: str
    version: int
    status: str
    change_reason: str
    source_recommendation_id: Optional[str] = None
    origin_weekly_review_id: Optional[str] = None
    superseded_by_id: Optional[str] = None
    payload: RecommendationPayload
    validation_codes: List[str]
    generated_at: datetime
    confirmed_at: Optional[datetime] = None
    superseded_at: Optional[datetime] = None


class RecommendationStateResponse(ApiModel):
    has_recommendation: bool
    recommendation: Optional[RecommendationView] = None
    operation_status: Optional[str] = None
    superseded_recommendation_id: Optional[str] = None
    preview_resulting_version: Optional[int] = None


class DraftRequest(ApiModel):
    idempotency_key: str = Field(..., min_length=1, max_length=64)
    iana_timezone: str = Field(..., min_length=1, max_length=60)


class ConfirmRequest(ApiModel):
    idempotency_key: str = Field(..., min_length=1, max_length=64)
    iana_timezone: str = Field(..., min_length=1, max_length=60)
    expected_version: int = Field(..., ge=1)
    expected_fingerprint: str = Field(..., pattern=r"^[0-9a-f]{64}$")


class ReplacementRequest(ApiModel):
    iana_timezone: str = Field(..., min_length=1, max_length=60)
    expected_version: int = Field(..., ge=1)
    expected_fingerprint: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    day_kind: DayKind
    meal: MealName
    item_index: int = Field(..., ge=0, le=20)
    from_food_id: str = Field(..., pattern=r"^[a-z0-9_]{3,60}$")
    to_food_id: str = Field(..., pattern=r"^[a-z0-9_]{3,60}$")


class ReplacementConfirmRequest(ReplacementRequest):
    idempotency_key: str = Field(..., min_length=1, max_length=64)


class DeletionResponse(ApiModel):
    status: str = "deleted"
    recommendations_deleted: int
    idempotency_deleted: int
    proposals_deleted: int
    tool_events_deleted: int
    runs_deleted: int
    profile_updated: bool


__all__ = [
    "EligibilityResponse",
    "TargetsResponse",
    "FoodListResponse",
    "RecommendationView",
    "RecommendationStateResponse",
    "DraftRequest",
    "ConfirmRequest",
    "ReplacementRequest",
    "ReplacementConfirmRequest",
    "DeletionResponse",
]
