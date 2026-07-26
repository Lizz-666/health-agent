"""Authorization-aware ``validate_training_plan`` application Tool (Task 6).

This is the application adapter that Phase 4 plan generation will call. It:

- authorizes via ``user_id`` (the only principal; ``build_context`` performs
  ownership-scoped reads, so cross-account access is impossible by construction);
- recomputes the safety decision AND the candidate set for every call from the
  current structured sources (never trusts stored labels or a stale candidate
  set);
- delegates to the pure ``validator.validate_plan``;
- performs NO write, NO LLM call, NO automatic repair.

It implements the ``ValidateTrainingPlanTool`` contract from
``app.training.tool_contracts``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.training.candidates import select_candidates
from app.training.context import build_context
from app.training.policy import TrainingPolicy
from app.training.safety import SafetyPolicy, classify_safety
from app.training.schemas import (
    ExerciseCatalog,
    PlanValidationResult,
    RequestSnapshot,
    TrainingPlanDraft,
)
from app.training.validator import validate_plan


async def validate_training_plan(
    db: AsyncSession,
    user_id: str,
    draft: TrainingPlanDraft,
    *,
    request: RequestSnapshot,
    catalog: ExerciseCatalog,
    safety_policy: SafetyPolicy,
    training_policy: TrainingPolicy,
    catalog_version: Optional[str] = None,
    source_manifest_version: Optional[str] = None,
    evaluated_at_utc: Optional[datetime] = None,
) -> PlanValidationResult:
    """Authorize, recompute current context, and validate ``draft`` (pure check).

    No persistence / AI / repair. A blocked, stale-fingerprint or version-
    mismatched context is returned as ``valid=False``; the draft is never
    mutated.
    """
    context = await build_context(
        db, user_id, request=request, policy=safety_policy,
        catalog_version=catalog_version or catalog.content_version,
        source_manifest_version=source_manifest_version,
        evaluated_at_utc=evaluated_at_utc,
    )
    decision = classify_safety(context, safety_policy)
    candidate_result = select_candidates(
        context, decision, catalog, training_policy, safety_policy)
    return validate_plan(
        draft, context, decision, candidate_result, catalog, training_policy)
