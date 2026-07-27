"""Phase 4 training plan REST routes (Task 4).

JWT-only: ownership is derived exclusively from ``Depends(get_current_user)``.
No endpoint accepts ``user_id``, a risk decision, a candidate set, or a version
fingerprint from the client. The server assembles context from authenticated,
ownership-filtered data and re-runs safety before every generation,
confirmation, substitution, and feedback.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.training import service
from app.training.schemas_api import (
    ActivePlanResponse,
    ConfirmRequest,
    ConfirmResponse,
    DraftRequest,
    DraftResponse,
    FeedbackRequest,
    FeedbackResponse,
    SubstitutionRequest,
    SubstitutionResponse,
    TodayResponse,
)

router = APIRouter(prefix="/api/v1/training", tags=["training"])


@router.post("/plans:draft", response_model=DraftResponse)
async def post_draft(
    request: DraftRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate (or regenerate) the caller's single pending four-week draft.

    Re-runs current safety classification; a blocked gate returns a structured
    error and no draft is persisted. Replaces any existing pending draft.
    """
    return await service.generate_draft(db, user_id, request)


@router.get("/plans/draft", response_model=DraftResponse)
async def get_draft(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the caller's current pending draft, or an explicit no-draft state."""
    return await service.get_draft(db, user_id)


@router.post("/plans:confirm", response_model=ConfirmResponse)
async def post_confirm(
    request: ConfirmRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Explicitly confirm and activate the pending draft.

    Re-runs safety and rejects a stale draft (changed profile / check-in /
    posture signal / version). Atomically supersedes any prior active plan.
    """
    return await service.confirm(db, user_id, request)


@router.get("/plans/active", response_model=ActivePlanResponse)
async def get_active(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the caller's single active plan, or an explicit no-active state."""
    return await service.get_active(db, user_id)


@router.get("/plans/today", response_model=TodayResponse)
async def get_today(
    iana_timezone: str = Query(..., description="User IANA timezone; the local date is server-derived."),
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return today's training state for the active plan.

    ``state`` is one of ``no_active_plan``, ``blocked``, ``rest_day``, or
    ``session``. A blocked safety gate never surfaces as success.
    """
    return await service.get_today(db, user_id, iana_timezone)


@router.post("/plans/sessions/{session_id}:substitute", response_model=SubstitutionResponse)
async def post_substitute(
    session_id: UUID,
    request: SubstitutionRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply one user-initiated exercise substitution within today's session.

    Re-runs safety; a blocked gate or a non-allowed substitution is rejected. At
    most one substitution per (session, local_date); replay returns the recorded
    result.
    """
    return await service.record_substitution(db, user_id, str(session_id), request)


@router.post("/plans/sessions/{session_id}:feedback", response_model=FeedbackResponse)
async def post_feedback(
    session_id: UUID,
    request: FeedbackRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record today's execution outcome for one session.

    No free-text note is accepted. At most one feedback per (session,
    local_date); replay returns the recorded result.
    """
    return await service.record_feedback(db, user_id, str(session_id), request)
