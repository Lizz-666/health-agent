"""JWT-authenticated Phase 6 nutrition recommendation routes."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.exceptions import AppException
from app.db.database import get_db
from app.nutrition import service
from app.nutrition.schemas import FoodRecord
from app.nutrition.schemas_api import (
    ConfirmRequest,
    DeletionResponse,
    DraftRequest,
    EligibilityResponse,
    FoodListResponse,
    RecommendationStateResponse,
    ReplacementConfirmRequest,
    ReplacementRequest,
    TargetsResponse,
)

router = APIRouter(prefix="/api/v1/nutrition", tags=["nutrition"])


@router.get("/eligibility", response_model=EligibilityResponse)
async def get_eligibility(
    iana_timezone: str = Query(..., min_length=1, max_length=60),
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.eligibility(db, user_id, iana_timezone)


@router.get("/targets", response_model=TargetsResponse)
async def get_targets(
    iana_timezone: str = Query(..., min_length=1, max_length=60),
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.targets(db, user_id, iana_timezone)


@router.get("/foods", response_model=FoodListResponse)
async def get_foods(_user_id: str = Depends(get_current_user)):
    return service.list_foods()


@router.get("/foods/{food_id}", response_model=FoodRecord)
async def get_food(
    food_id: str = Path(..., pattern=r"^[a-z0-9_]{3,60}$"),
    _user_id: str = Depends(get_current_user),
):
    return service.get_food(food_id)


@router.post("/recommendations/drafts", response_model=RecommendationStateResponse)
async def post_draft(
    request: DraftRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.generate_draft(db, user_id, request)


@router.get("/recommendations/draft", response_model=RecommendationStateResponse)
async def get_draft(
    iana_timezone: str = Query(..., min_length=1, max_length=60),
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_draft(db, user_id, iana_timezone)


@router.get("/recommendations/active", response_model=RecommendationStateResponse)
async def get_active(
    iana_timezone: str = Query(..., min_length=1, max_length=60),
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_active(db, user_id, iana_timezone)


@router.post(
    "/recommendations/{draft_id}:confirm",
    response_model=RecommendationStateResponse,
)
async def post_confirm(
    draft_id: UUID,
    request: ConfirmRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.confirm(db, user_id, draft_id, request)


@router.post(
    "/recommendations/{active_id}/replacements:preview",
    response_model=RecommendationStateResponse,
)
async def post_replacement_preview(
    active_id: UUID,
    request: ReplacementRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.replacement_preview(db, user_id, active_id, request)


@router.post(
    "/recommendations/{active_id}/replacements:confirm",
    response_model=RecommendationStateResponse,
)
async def post_replacement_confirm(
    active_id: UUID,
    request: ReplacementConfirmRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.replacement_confirm(db, user_id, active_id, request)


@router.delete("/data", response_model=DeletionResponse)
async def delete_data(
    request: Request,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if await request.body():
        raise AppException(422, "删除请求不接受请求体", "invalid_request")
    return await service.delete_data(db, user_id)


__all__ = ["router"]
