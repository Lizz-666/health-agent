"""Phase 4 training plan REST request/response models (Task 4).

All models use ``extra="forbid"`` (unknown fields fail closed) and never embed
raw health payloads, pain notes, or another user's data. Identity is JWT-derived
at the router; no model carries a ``user_id``.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

_OUTCOME_STATES = ("completed", "partial", "too_busy", "intentional_rest", "discomfort")


# --- requests ---------------------------------------------------------------


class _Idempotent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(..., min_length=1, max_length=64)


class DraftRequest(_Idempotent):
    fitness_goal: str = Field(..., min_length=1, max_length=30)
    weekly_frequency: int = Field(..., ge=2, le=5)
    session_duration_minutes: Literal[15, 30, 45, 60]
    equipment_bodyweight: bool
    equipment_resistance_band: bool
    iana_timezone: str = Field(..., min_length=1, max_length=60)


class ConfirmRequest(_Idempotent):
    # The generation params are re-supplied so the server can rebuild the exact
    # request snapshot and recompute the decision fingerprint; a changed
    # profile / check-in / posture signal / version yields ``stale_context``.
    fitness_goal: str = Field(..., min_length=1, max_length=30)
    weekly_frequency: int = Field(..., ge=2, le=5)
    session_duration_minutes: Literal[15, 30, 45, 60]
    equipment_bodyweight: bool
    equipment_resistance_band: bool
    iana_timezone: str = Field(..., min_length=1, max_length=60)


class FeedbackRequest(_Idempotent):
    outcome_state: str = Field(..., min_length=1, max_length=20)

    @staticmethod
    def allowed_outcomes() -> tuple:
        return _OUTCOME_STATES


class SubstitutionRequest(_Idempotent):
    original_exercise_id: str = Field(..., min_length=1, max_length=60)
    replacement_exercise_id: str = Field(..., min_length=1, max_length=60)


class AdjustmentRequest(_Idempotent):
    intent: Literal["apply_today_adjustment"]
    expected_plan_version_id: UUID
    expected_session_id: UUID
    iana_timezone: str = Field(..., min_length=1, max_length=60)


# --- catalog-enriched views -------------------------------------------------


class ExerciseView(BaseModel):
    """Static catalog info for an exercise, for display only."""

    model_config = ConfigDict(extra="forbid")
    exercise_id: str
    name_en: str
    name_zh: str
    training_roles: List[str]
    difficulty: str
    illustration_asset_key: str
    illustration_alt_zh: str
    instruction_steps: List[str]
    form_cues: List[str]
    substitution_ids: List[str]


class PrescriptionView(BaseModel):
    """A prescription enriched with its catalog exercise + display fields."""

    model_config = ConfigDict(extra="forbid")
    prescription_id: Optional[str] = None
    exercise_id: str
    sets: int
    reps: Optional[int] = None
    duration_seconds: Optional[int] = None
    rest_seconds: int
    relation_reason: Optional[str] = None
    exercise: Optional[ExerciseView] = None


class SessionView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    week_index: int
    day_of_week: int
    session_order: int
    target_minutes: Optional[int] = None
    prescriptions: List[PrescriptionView]


class PlanVersionView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_version_id: str
    origin_weekly_review_id: Optional[str] = None
    requested_goal: str
    weekly_frequency: int
    session_duration_minutes: int
    status: str
    change_reason: str
    decision_gate: str
    generated_at: datetime
    confirmed_at: Optional[datetime] = None
    catalog_version: str
    policy_version: str
    sessions: List[SessionView]


# --- responses --------------------------------------------------------------


class DraftResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    has_draft: bool
    draft: Optional[PlanVersionView] = None
    decision_gate: Optional[str] = None


class ConfirmResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: PlanVersionView
    superseded_prior: bool


class ActivePlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    has_active: bool
    plan: Optional[PlanVersionView] = None


class TodayResponse(BaseModel):
    """Today's training state. ``state`` is one of ``no_active_plan``,
    ``blocked``, ``rest_day``, ``session``."""

    model_config = ConfigDict(extra="forbid")
    state: str
    local_date: Optional[date] = None
    change_reason: Optional[str] = None
    decision_gate: Optional[str] = None
    session: Optional[SessionView] = None
    feedback_outcome_state: Optional[str] = None
    substitution_applied: bool = False
    original_session_id: Optional[str] = None
    source_local_date: Optional[date] = None
    target_local_date: Optional[date] = None
    adjustment_id: Optional[str] = None
    adjustment_kind: Optional[
        Literal["shortened", "recovery", "deferred", "active_rest", "unchanged"]
    ] = None
    adjustment_reason_codes: List[str] = Field(default_factory=list)
    safety_status: Optional[str] = None


class AdjustmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    adjustment_id: str
    status: Literal["recorded", "replayed"]
    adjustment_kind: Literal[
        "shortened", "recovery", "deferred", "active_rest", "unchanged"
    ]
    original_session_id: str
    source_local_date: date
    target_local_date: Optional[date] = None
    target_minutes: Optional[int] = None
    reason_codes: List[str]


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback_id: str
    outcome_state: str
    status: str  # "recorded" | "replayed"


class SubstitutionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    substitution_id: str
    status: str  # "recorded" | "replayed"


class ReviewGenerateRequest(_Idempotent):
    iana_timezone: str = Field(..., min_length=1, max_length=60)


class ReviewMutationRequest(_Idempotent):
    expected_review_id: UUID
    expected_input_fingerprint: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    iana_timezone: str = Field(..., min_length=1, max_length=60)


class ExecutionFactsView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scheduled: int = Field(..., ge=0)
    effective: int = Field(..., ge=0)
    completed: int = Field(..., ge=0)
    partial: int = Field(..., ge=0)
    too_busy: int = Field(..., ge=0)
    intentional_rest: int = Field(..., ge=0)
    discomfort: int = Field(..., ge=0)
    active_rest: int = Field(..., ge=0)
    safety_adjustment: int = Field(..., ge=0)
    unavailable: int = Field(..., ge=0)


class TrendView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    available: bool
    direction: Optional[
        Literal["improving", "steady", "declining", "rising", "falling", "stable"]
    ] = None

    @model_validator(mode="after")
    def validate_availability(self):
        if self.available != (self.direction is not None):
            raise ValueError("trend availability and direction disagree")
        return self


class ExecutionTrendView(TrendView):
    direction: Optional[Literal["improving", "steady", "declining"]] = None


class WeightTrendView(TrendView):
    direction: Optional[Literal["rising", "falling", "stable"]] = None


class AdjustmentFactsView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shortened: int = Field(..., ge=0)
    recovery: int = Field(..., ge=0)
    deferred: int = Field(..., ge=0)
    active_rest: int = Field(..., ge=0)
    unchanged: int = Field(..., ge=0)
    missing: int = Field(..., ge=0)
    unavailable: int = Field(..., ge=0)


class NutritionReviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["none", "active", "stale", "unavailable"]
    age_days: Optional[int] = Field(default=None, ge=0)
    refresh_available: bool
    unavailable_reason: Optional[str] = None
    recommendation_id: Optional[str] = None
    version: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_state(self):
        has_identity = self.recommendation_id is not None and self.version is not None
        if (self.recommendation_id is None) != (self.version is None):
            raise ValueError("nutrition identity must be complete")
        if self.state == "none":
            if has_identity or self.age_days is not None or not self.refresh_available:
                raise ValueError("none nutrition state must offer an initial draft")
        elif self.state == "active":
            if not has_identity or self.refresh_available:
                raise ValueError("active nutrition state cannot offer refresh")
        elif self.state == "stale":
            if not has_identity or not self.refresh_available:
                raise ValueError("stale nutrition state must offer refresh")
        elif (
            self.refresh_available
            or not self.unavailable_reason
            or not self.unavailable_reason.strip()
        ):
            raise ValueError("unavailable nutrition state must fail closed")
        if self.state != "unavailable" and self.unavailable_reason is not None:
            raise ValueError("only unavailable nutrition state has a reason")
        return self


class PostureReviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["not_due", "due", "comparison_available", "unavailable"]
    comparison_signal: Optional[
        Literal["added", "not_detected", "unchanged", "changed"]
    ] = None
    baseline_at: Optional[datetime] = None
    comparison_at: Optional[datetime] = None
    baseline_sources: List[Literal["self_test", "ai_photo"]] = Field(
        default_factory=list
    )
    comparison_sources: List[Literal["self_test", "ai_photo"]] = Field(
        default_factory=list
    )
    reason: Optional[str] = None

    @model_validator(mode="after")
    def validate_status(self):
        if self.status == "comparison_available":
            if (
                self.comparison_signal is None
                or self.baseline_at is None
                or self.comparison_at is None
            ):
                raise ValueError("posture comparison requires both anchors")
        elif self.comparison_signal is not None or self.comparison_at is not None:
            raise ValueError("comparison fields require comparison status")
        if self.status == "due" and self.baseline_at is None:
            raise ValueError("due posture state requires baseline anchor")
        if self.status == "unavailable" and (
            not self.reason or not self.reason.strip()
        ):
            raise ValueError("unavailable posture state requires reason")
        return self


class ReviewSafetyView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gate: str
    blocked: bool
    reason_codes: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)


class ReviewProposalView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Literal[
        "keep_current_plan",
        "offer_training_draft",
        "offer_nutrition_refresh",
        "posture_recheck_due",
        "posture_comparison_available",
        "revisit_goal",
    ]
    state: Literal["proposal", "draft", "active", "unavailable"]
    strategy: Optional[
        Literal[
            "conservative_duration",
            "lower_frequency",
            "progression",
            "regression",
        ]
    ] = None
    origin_weekly_review_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_strategy(self):
        if self.code == "offer_training_draft":
            if self.strategy is None:
                raise ValueError("training draft proposal requires strategy")
        elif self.strategy is not None:
            raise ValueError("strategy is limited to training draft proposals")
        return self


class WeeklyReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_id: str
    plan_version_id: str
    week_index: int = Field(..., ge=1, le=4)
    review_version: int = Field(..., ge=1)
    input_fingerprint: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    period_start: date
    period_end: date
    execution: ExecutionFactsView
    execution_trend: ExecutionTrendView
    adjustments: AdjustmentFactsView
    weight_trend: WeightTrendView
    nutrition: NutritionReviewView
    posture: PostureReviewView
    safety: ReviewSafetyView
    proposals: List[ReviewProposalView]


class ReviewDraftResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_id: str
    draft_id: str
    status: Literal["created", "replayed"]
    origin_weekly_review_id: str


class PostureDismissalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_id: str
    dismissal_id: str
    status: Literal["recorded", "replayed"]


__all__ = [
    "DraftRequest",
    "ConfirmRequest",
    "FeedbackRequest",
    "SubstitutionRequest",
    "AdjustmentRequest",
    "ExerciseView",
    "PrescriptionView",
    "SessionView",
    "PlanVersionView",
    "DraftResponse",
    "ConfirmResponse",
    "ActivePlanResponse",
    "TodayResponse",
    "AdjustmentResponse",
    "FeedbackResponse",
    "SubstitutionResponse",
    "ReviewGenerateRequest",
    "ReviewMutationRequest",
    "WeeklyReviewResponse",
    "ReviewDraftResponse",
    "PostureDismissalResponse",
]
