"""JWT-only HTTP boundary for the Phase 5 Agent MVP."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import service
from app.agent.provider import AgentProvider, DashScopeProvider
from app.agent.schemas import (
    AgentActionResponse,
    AgentCapabilitiesResponse,
    AgentConfirmRequest,
    AgentConsentGrantRequest,
    AgentConsentResponse,
    AgentConsentWithdrawRequest,
    AgentDataDeletionResponse,
    AgentTurnResponse,
    TurnInput,
)
from app.core.actor_context import ActorContext
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.db.database import get_db


router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


def get_agent_provider() -> AgentProvider:
    """Build the sole production provider from server-only settings.

    Tests override this dependency with a scripted provider. Production code
    intentionally has no fake/provider-selector branch.
    """
    return DashScopeProvider(
        api_key=settings.DASHSCOPE_API_KEY,
        model_id=settings.AGENT_MODEL_ID,
        base_url=settings.AGENT_PROVIDER_BASE_URL,
        connect_timeout=settings.AGENT_PROVIDER_CONNECT_TIMEOUT_SECONDS,
        read_timeout=settings.AGENT_PROVIDER_READ_TIMEOUT_SECONDS,
        max_response_bytes=settings.AGENT_PROVIDER_MAX_RESPONSE_BYTES,
    )


@router.get("/capabilities", response_model=AgentCapabilitiesResponse)
async def capabilities(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_capabilities(db, user_id)


@router.post("/consents:grant", response_model=AgentConsentResponse)
async def grant_consent(
    request: AgentConsentGrantRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.grant_cloud_consent(db, user_id, request)


@router.post("/consents:withdraw", response_model=AgentConsentResponse)
async def withdraw_consent(
    request: AgentConsentWithdrawRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.withdraw_cloud_consent(
        db, user_id, request.idempotency_key
    )


@router.delete("/data", response_model=AgentDataDeletionResponse)
async def delete_data(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.delete_current_agent_data(db, user_id)


@router.post(
    "/turns",
    response_model=AgentTurnResponse,
    responses={422: {"model": AgentTurnResponse}},
)
async def process_turn(
    request: TurnInput,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    provider: AgentProvider = Depends(get_agent_provider),
):
    return await service.process_turn(
        db, ActorContext(user_id=user_id), request, provider
    )


@router.post(
    "/actions/{proposal_id}:confirm", response_model=AgentActionResponse
)
async def confirm_action(
    proposal_id: UUID,
    request: AgentConfirmRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.confirm_action(
        db,
        user_id,
        proposal_id,
        idempotency_key=request.idempotency_key,
    )


@router.post(
    "/actions/{proposal_id}:cancel", response_model=AgentActionResponse
)
async def cancel_action(
    proposal_id: UUID,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.cancel_action(db, user_id, proposal_id)


__all__ = ["router", "get_agent_provider"]
