"""Typed application Tool contract for ``validate_training_plan`` (Task 6).

This module is the authoritative typed contract for the Phase 3 validator Tool
that Phase 4 plan generation will reuse. The Tool:

- accepts typed, schema-validated inputs only (``TrainingPlanDraft``);
- authorizes and loads the current user context in the application adapter
  before entering the pure validator (ownership comes from ``user_id``);
- recomputes safety and candidate eligibility for every call;
- returns structured ``PlanValidationResult`` violations;
- has NO write side effect, NO LLM call, NO automatic repair;
- never returns ``valid=True`` for a blocked / stale / version-mismatched plan.

The pure logic lives in ``app.training.validator``; the application adapter
lives in ``app.training.tools``.
"""
from __future__ import annotations

from typing import Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.training.schemas import (
    PlanValidationResult,
    RequestSnapshot,
    TrainingPlanDraft,
)


class ValidateTrainingPlanRequest(BaseModel):
    """Typed request envelope for the validator Tool."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., min_length=1, max_length=80)
    draft: TrainingPlanDraft
    request: RequestSnapshot


class ValidateTrainingPlanTool(Protocol):
    """Typed contract for ``validate_training_plan`` (implemented in tools)."""

    async def __call__(
        self,
        db,
        user_id: str,
        draft: TrainingPlanDraft,
        *,
        request: RequestSnapshot,
        catalog,
        safety_policy,
        training_policy,
        catalog_version: Optional[str] = ...,
        source_manifest_version: Optional[str] = ...,
        evaluated_at_utc=None,
    ) -> PlanValidationResult: ...


__all__ = [
    "ValidateTrainingPlanRequest",
    "ValidateTrainingPlanTool",
    "PlanValidationResult",
    "TrainingPlanDraft",
]
