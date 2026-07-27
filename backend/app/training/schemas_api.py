"""Phase 4 training plan REST request/response models (Task 4).

All models use ``extra="forbid"`` (unknown fields fail closed) and never embed
raw health payloads, pain notes, or another user's data. Identity is JWT-derived
at the router; no model carries a ``user_id``.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

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


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback_id: str
    outcome_state: str
    status: str  # "recorded" | "replayed"


class SubstitutionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    substitution_id: str
    status: str  # "recorded" | "replayed"


__all__ = [
    "DraftRequest",
    "ConfirmRequest",
    "FeedbackRequest",
    "SubstitutionRequest",
    "ExerciseView",
    "PrescriptionView",
    "SessionView",
    "PlanVersionView",
    "DraftResponse",
    "ConfirmResponse",
    "ActivePlanResponse",
    "TodayResponse",
    "FeedbackResponse",
    "SubstitutionResponse",
]
