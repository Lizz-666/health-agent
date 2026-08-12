from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Union

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import (
    AgentActionProposal,
    AgentCloudConsent,
    AgentRun,
    AgentToolEvent,
)
from app.auth.credentials import offline_password_provider
from app.auth.models import (
    AuthAttempt,
    AuthSession,
    TrialCredential,
    TrialDeviceEnrollment,
    TrialInvitation,
    User,
)
from app.core.config import settings
from app.core.exceptions import AppException
from app.health.models import DailyCheckIn, HealthProfile, WeightRecord
from app.nutrition.models import NutritionRecommendation
from app.posture.models import (
    IdempotencyRecord,
    PostureAssessmentEvent,
    PostureProfileEntry,
    PostureSafetySignal,
    PostureUserGoal,
)
from app.posture.user_lock import acquire_user_transaction_lock
from app.privacy.models import AccountDeletionMarker, SensitiveHealthConsentEvent
from app.training.models import (
    PostureRecheckDismissal,
    TrainingDayAdjustment,
    TrainingDayAdjustmentItem,
    TrainingPlanVersion,
    TrainingPrescription,
    TrainingSession,
    TrainingSessionFeedback,
    TrainingSessionSubstitution,
    TrainingWeeklyReview,
)

SENSITIVE_HEALTH_PURPOSE = "controlled_trial_sensitive_health"
DELETION_POLICY_VERSION = "controlled-trial-deletion-2026-08-12"
EXPORT_SCHEMA_VERSION = "controlled-trial-export-v1"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def subject_digest(user_id: Union[str, uuid.UUID]) -> str:
    key = settings.PRIVACY_AUDIT_HMAC_KEY.encode("utf-8")
    if len(key) < 32:
        raise RuntimeError("PRIVACY_AUDIT_HMAC_KEY is not configured")
    return hmac.new(key, str(user_id).encode("utf-8"), hashlib.sha256).hexdigest()


async def current_consent(
    db: AsyncSession, user_id: Union[str, uuid.UUID]
) -> SensitiveHealthConsentEvent | None:
    uid = uuid.UUID(str(user_id))
    return await db.scalar(
        select(SensitiveHealthConsentEvent)
        .where(
            SensitiveHealthConsentEvent.user_id == uid,
            SensitiveHealthConsentEvent.purpose == SENSITIVE_HEALTH_PURPOSE,
        )
        .order_by(SensitiveHealthConsentEvent.sequence_no.desc())
        .limit(1)
    )


async def consent_is_active(
    db: AsyncSession, user_id: Union[str, uuid.UUID]
) -> bool:
    event = await current_consent(db, user_id)
    return bool(
        event
        and event.action == "grant"
        and event.notice_version == settings.PRIVACY_NOTICE_VERSION
    )


async def record_consent(
    db: AsyncSession,
    user_id: str,
    *,
    action: str,
    notice_version: str,
) -> SensitiveHealthConsentEvent:
    if notice_version != settings.PRIVACY_NOTICE_VERSION:
        raise AppException(409, "隐私告知版本已更新，请重新确认", "privacy_notice_stale")
    await acquire_user_transaction_lock(db, user_id)
    uid = uuid.UUID(user_id)
    sequence = await db.scalar(
        select(func.max(SensitiveHealthConsentEvent.sequence_no)).where(
            SensitiveHealthConsentEvent.user_id == uid,
            SensitiveHealthConsentEvent.purpose == SENSITIVE_HEALTH_PURPOSE,
        )
    )
    event = SensitiveHealthConsentEvent(
        user_id=uid,
        purpose=SENSITIVE_HEALTH_PURPOSE,
        notice_version=notice_version,
        action=action,
        sequence_no=(sequence or 0) + 1,
        occurred_at=_utcnow(),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


def consent_state(event: SensitiveHealthConsentEvent | None) -> dict[str, Any]:
    return {
        "purpose": SENSITIVE_HEALTH_PURPOSE,
        "active": bool(
            event
            and event.action == "grant"
            and event.notice_version == settings.PRIVACY_NOTICE_VERSION
        ),
        "notice_version": event.notice_version if event else None,
        "sequence_no": event.sequence_no if event else 0,
        "occurred_at": event.occurred_at if event else None,
    }


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _safe_row(row: Any, excluded: Iterable[str] = ()) -> dict[str, Any]:
    excluded_set = set(excluded)
    return {
        column.name: _json_value(getattr(row, column.name))
        for column in row.__table__.columns
        if column.name not in excluded_set
    }


async def _owned_rows(db: AsyncSession, model: Any, uid: uuid.UUID) -> list[Any]:
    return list((await db.scalars(select(model).where(model.user_id == uid))).all())


async def export_user_data(db: AsyncSession, user_id: str) -> dict[str, Any]:
    uid = uuid.UUID(user_id)
    user = await db.get(User, uid)
    if user is None:
        raise AppException(404, "用户不存在", "not_found")
    credential = await db.scalar(
        select(TrialCredential).where(TrialCredential.user_id == uid)
    )
    invitations = await _owned_rows(db, TrialInvitation, uid)
    devices = await _owned_rows(db, TrialDeviceEnrollment, uid)
    sessions = await _owned_rows(db, AuthSession, uid)
    consents = await _owned_rows(db, SensitiveHealthConsentEvent, uid)

    direct_models = (
        HealthProfile,
        DailyCheckIn,
        WeightRecord,
        PostureAssessmentEvent,
        PostureProfileEntry,
        PostureUserGoal,
        PostureSafetySignal,
        IdempotencyRecord,
        TrainingPlanVersion,
        TrainingSessionFeedback,
        TrainingSessionSubstitution,
        TrainingDayAdjustment,
        TrainingWeeklyReview,
        PostureRecheckDismissal,
        NutritionRecommendation,
        AgentCloudConsent,
        AgentRun,
        AgentToolEvent,
        AgentActionProposal,
    )
    records: dict[str, list[dict[str, Any]]] = {}
    raw_by_model: dict[Any, list[Any]] = {}
    for model in direct_models:
        rows = await _owned_rows(db, model, uid)
        raw_by_model[model] = rows
        records[model.__tablename__] = [_safe_row(row) for row in rows]

    plan_ids = [row.plan_version_id for row in raw_by_model[TrainingPlanVersion]]
    training_sessions = list(
        (await db.scalars(
            select(TrainingSession).where(TrainingSession.plan_version_id.in_(plan_ids))
        )).all()
    ) if plan_ids else []
    session_ids = [row.session_id for row in training_sessions]
    records[TrainingSession.__tablename__] = [_safe_row(row) for row in training_sessions]
    records[TrainingPrescription.__tablename__] = [
        _safe_row(row)
        for row in (
            (await db.scalars(
                select(TrainingPrescription).where(
                    TrainingPrescription.session_id.in_(session_ids)
                )
            )).all()
            if session_ids else []
        )
    ]
    adjustment_ids = [row.adjustment_id for row in raw_by_model[TrainingDayAdjustment]]
    records[TrainingDayAdjustmentItem.__tablename__] = [
        _safe_row(row)
        for row in (
            (await db.scalars(
                select(TrainingDayAdjustmentItem).where(
                    TrainingDayAdjustmentItem.adjustment_id.in_(adjustment_ids)
                )
            )).all()
            if adjustment_ids else []
        )
    ]

    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "generated_at": _utcnow(),
        "subject_id": str(uid),
        "identity": {
            "account_name": credential.login_id if credential else None,
            "credential_provider": credential.provider_id if credential else None,
            "account_created_at": _json_value(user.created_at),
            "profile": _safe_row(user, excluded=("phone",)),
            "invitations": [
                _safe_row(row, excluded=("code_digest", "user_id"))
                for row in invitations
            ],
            "device_enrollments": [
                _safe_row(row, excluded=("device_key_digest", "user_id"))
                for row in devices
            ],
            "sessions": [
                _safe_row(
                    row,
                    excluded=("refresh_token_digest", "user_id", "device_id"),
                )
                for row in sessions
            ],
        },
        "consent_history": [_safe_row(row, excluded=("user_id",)) for row in consents],
        "domain_records": records,
        "excluded_security_fields": [
            "credential_hash",
            "invitation_code_digest",
            "device_key_digest",
            "refresh_token_digest",
            "auth_attempt_source_digest",
            "server_secrets",
        ],
    }


async def confirm_trial_credential(
    db: AsyncSession,
    user_id: str,
    *,
    provider_id: str,
    credential_value: str,
    device_key: str,
) -> None:
    uid = uuid.UUID(user_id)
    stored = await db.scalar(
        select(TrialCredential).where(TrialCredential.user_id == uid)
    )
    device = await db.scalar(
        select(TrialDeviceEnrollment).where(
            TrialDeviceEnrollment.user_id == uid,
            TrialDeviceEnrollment.revoked_at.is_(None),
        )
    )
    valid = bool(
        stored
        and stored.disabled_at is None
        and stored.provider_id == provider_id
        and offline_password_provider.verify(
            credential_value, stored.credential_hash
        ).accepted
        and device
        and hmac.compare_digest(
            device.device_key_digest,
            hashlib.sha256(device_key.encode("utf-8")).hexdigest(),
        )
    )
    if not valid:
        raise AppException(401, "账号或凭据无效", "reauthentication_failed")


async def freeze_trial_identity_for_deletion(
    db: AsyncSession, user_id: Union[str, uuid.UUID]
) -> None:
    """Disable login and sessions inside the purge-operation transaction."""
    uid = uuid.UUID(str(user_id))
    now = _utcnow()
    await db.execute(
        update(TrialCredential)
        .where(TrialCredential.user_id == uid, TrialCredential.disabled_at.is_(None))
        .values(disabled_at=now)
    )
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == uid, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def is_trial_identity(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return await db.scalar(
        select(TrialCredential.user_id).where(TrialCredential.user_id == user_id)
    ) is not None


async def finalize_trial_identity_deletion(
    db: AsyncSession, user_id: uuid.UUID
) -> uuid.UUID:
    credential = await db.scalar(
        select(TrialCredential).where(TrialCredential.user_id == user_id)
    )
    digest = subject_digest(user_id)
    marker = await db.scalar(
        select(AccountDeletionMarker).where(
            AccountDeletionMarker.subject_digest == digest
        )
    )
    if marker is None:
        marker = AccountDeletionMarker(
            subject_digest=digest,
            deleted_at=_utcnow(),
            policy_version=DELETION_POLICY_VERSION,
        )
        db.add(marker)
        await db.flush()
    if credential is not None:
        auth_key = (settings.AUTH_AUDIT_HMAC_KEY or settings.SECRET_KEY).encode("utf-8")
        login_digest = hmac.new(
            auth_key,
            credential.login_id.strip().casefold().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        await db.execute(delete(AuthAttempt).where(AuthAttempt.subject_digest == login_digest))
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id)
        .values(replaced_by_session_id=None)
    )
    await db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    await db.execute(
        delete(SensitiveHealthConsentEvent).where(
            SensitiveHealthConsentEvent.user_id == user_id
        )
    )
    await db.execute(delete(TrialInvitation).where(TrialInvitation.user_id == user_id))
    await db.execute(
        delete(TrialDeviceEnrollment).where(TrialDeviceEnrollment.user_id == user_id)
    )
    await db.execute(delete(TrialCredential).where(TrialCredential.user_id == user_id))
    await db.execute(delete(User).where(User.id == user_id))
    return marker.receipt_id


async def deletion_marker_digests(db: AsyncSession) -> list[str]:
    return list((await db.scalars(select(AccountDeletionMarker.subject_digest))).all())


async def restored_trial_subjects(
    db: AsyncSession, marker_digests: set[str]
) -> list[uuid.UUID]:
    restored: list[uuid.UUID] = []
    for user_id in (await db.scalars(select(TrialCredential.user_id))).all():
        if subject_digest(user_id) in marker_digests:
            restored.append(user_id)
    return restored


async def ensure_no_restored_deleted_subjects(db: AsyncSession) -> None:
    """Fail candidate startup if a restore revived a deleted login identity."""
    markers = set(await deletion_marker_digests(db))
    if markers and await restored_trial_subjects(db, markers):
        raise RuntimeError("deleted trial subject was restored")
