import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.exceptions import AppException
from app.core.observability import (
    SecurityEventCode,
    SecurityEventOutcome,
    emit_security_event,
)
from app.db.database import get_db
from app.posture import purge
from app.privacy import service
from app.privacy.schemas import (
    AccountDeletionRequest,
    AccountDeletionResponse,
    ConsentRequest,
    ConsentStateResponse,
    PrivacyExportResponse,
)

router = APIRouter(prefix="/api/v1/privacy", tags=["privacy"])
logger = logging.getLogger("app.security")


@router.get("/consent", response_model=ConsentStateResponse)
async def get_consent(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return service.consent_state(await service.current_consent(db, user_id))


@router.post("/consent", response_model=ConsentStateResponse)
async def post_consent(
    request: ConsentRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    event = await service.record_consent(
        db,
        user_id,
        action=request.action,
        notice_version=request.notice_version,
    )
    emit_security_event(
        logger,
        SecurityEventCode.PRIVACY_CONSENT,
        SecurityEventOutcome.SUCCEEDED,
    )
    return service.consent_state(event)


@router.get("/export", response_model=PrivacyExportResponse)
async def export_data(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await service.export_user_data(db, user_id)
    emit_security_event(
        logger,
        SecurityEventCode.PRIVACY_EXPORT,
        SecurityEventOutcome.SUCCEEDED,
    )
    return result


@router.post("/account-deletion", response_model=AccountDeletionResponse)
async def delete_account(
    request: AccountDeletionRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await service.confirm_trial_credential(
        db,
        user_id,
        provider_id=request.provider_id,
        credential_value=request.credential,
        device_key=request.device_key,
    )
    result = await purge.run_purge(
        db,
        user_id,
        purge.FailClosedObjectStore(),
        trigger="account_deletion",
    )
    if result.status != "completed":
        raise AppException(
            503,
            "账号删除正在等待安全重试，账号已停用",
            "account_deletion_pending",
        )
    emit_security_event(
        logger,
        SecurityEventCode.PRIVACY_ACCOUNT_DELETION,
        SecurityEventOutcome.SUCCEEDED,
    )
    return AccountDeletionResponse(
        status=result.status,
        receipt_id=(
            str(result.tombstone_receipt_id)
            if result.tombstone_receipt_id is not None
            else None
        ),
    )
