"""Atomic nutrition recommendation lifecycle and scoped deletion."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import AgentActionProposal, AgentRun, AgentToolEvent
from app.core.exceptions import AppException
from app.health.models import HealthProfile
from app.nutrition.models import NutritionRecommendation
from app.nutrition.schemas import (
    RecommendationContextPins,
    RecommendationPayload,
    RecommendationStatus,
)
from app.posture.models import IdempotencyRecord
from app.posture.user_lock import acquire_user_transaction_lock

OP_DRAFT_GENERATE = "nutrition_draft_generate"
OP_DRAFT_CONFIRM = "nutrition_draft_confirm"
OP_REPLACEMENT_CONFIRM = "nutrition_replacement_confirm"
NUTRITION_IDEMPOTENCY_OPERATIONS = frozenset(
    {OP_DRAFT_GENERATE, OP_DRAFT_CONFIRM, OP_REPLACEMENT_CONFIRM}
)
NUTRITION_TOOL_NAMES = frozenset(
    {
        "calculate_nutrition_targets",
        "convert_targets_to_portions",
        "generate_meal_plan_draft",
        "replace_food",
        "validate_nutrition_plan",
    }
)
IDEMPOTENCY_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class PersistenceResult:
    recommendation_id: uuid.UUID
    status: str
    superseded_recommendation_id: Optional[uuid.UUID] = None


@dataclass(frozen=True)
class NutritionDeletionResult:
    recommendations_deleted: int
    idempotency_deleted: int
    proposals_deleted: int
    tool_events_deleted: int
    runs_deleted: int
    profile_updated: bool


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_request(payload: dict) -> str:
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AppException(400, "请求无法规范化", "invalid_request") from exc
    return hashlib.sha256(encoded).hexdigest()


async def _check_idempotency(
    db: AsyncSession,
    user_id: str,
    operation: str,
    idempotency_key: str,
    request_hash: str,
    now: datetime,
) -> Optional[NutritionRecommendation]:
    result = await db.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == uuid.UUID(user_id),
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        return None
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        await db.delete(record)
        await db.flush()
        return None
    if record.request_hash != request_hash:
        raise AppException(
            400, "idempotency_key 已用于不同请求", "idempotency_key_conflict"
        )
    try:
        result_id = uuid.UUID(record.result_ref or "")
    except (ValueError, TypeError) as exc:
        raise AppException(
            409, "幂等状态不完整", "idempotency_state_inconsistent"
        ) from exc
    row = await get_owned(db, user_id, result_id)
    if row is None or record.status != "completed":
        raise AppException(409, "幂等状态不完整", "idempotency_state_inconsistent")
    return row


async def peek_idempotency(
    db: AsyncSession,
    user_id: str,
    operation: str,
    idempotency_key: str,
    request_hash: str,
    now: Optional[datetime] = None,
) -> Optional[NutritionRecommendation]:
    if operation not in NUTRITION_IDEMPOTENCY_OPERATIONS:
        raise AppException(400, "未知幂等操作", "invalid_request")
    return await _check_idempotency(
        db,
        user_id,
        operation,
        idempotency_key,
        request_hash,
        now or utc_now(),
    )


async def _record_idempotency(
    db: AsyncSession,
    user_id: str,
    operation: str,
    idempotency_key: str,
    request_hash: str,
    result_ref: uuid.UUID,
    now: datetime,
) -> None:
    db.add(
        IdempotencyRecord(
            user_id=uuid.UUID(user_id),
            operation=operation,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            status="completed",
            result_ref=str(result_ref),
            expires_at=now + IDEMPOTENCY_TTL,
        )
    )


async def get_owned(
    db: AsyncSession, user_id: str, recommendation_id: uuid.UUID | str
) -> Optional[NutritionRecommendation]:
    try:
        rid = recommendation_id if isinstance(recommendation_id, uuid.UUID) else uuid.UUID(recommendation_id)
    except (ValueError, TypeError):
        return None
    result = await db.execute(
        select(NutritionRecommendation).where(
            NutritionRecommendation.user_id == uuid.UUID(user_id),
            NutritionRecommendation.recommendation_id == rid,
        )
    )
    return result.scalar_one_or_none()


async def get_current_draft(
    db: AsyncSession, user_id: str
) -> Optional[NutritionRecommendation]:
    result = await db.execute(
        select(NutritionRecommendation).where(
            NutritionRecommendation.user_id == uuid.UUID(user_id),
            NutritionRecommendation.status == RecommendationStatus.draft.value,
        )
    )
    return result.scalar_one_or_none()


async def get_active(
    db: AsyncSession, user_id: str
) -> Optional[NutritionRecommendation]:
    result = await db.execute(
        select(NutritionRecommendation).where(
            NutritionRecommendation.user_id == uuid.UUID(user_id),
            NutritionRecommendation.status == RecommendationStatus.active.value,
        )
    )
    return result.scalar_one_or_none()


async def _next_version(db: AsyncSession, user_id: str) -> int:
    value = await db.scalar(
        select(func.max(NutritionRecommendation.version)).where(
            NutritionRecommendation.user_id == uuid.UUID(user_id)
        )
    )
    return int(value or 0) + 1


async def get_next_version(db: AsyncSession, user_id: str) -> int:
    return await _next_version(db, user_id)


def _new_row(
    *,
    recommendation_id: uuid.UUID,
    user_id: str,
    version: int,
    status: RecommendationStatus,
    change_reason: str,
    payload: RecommendationPayload,
    pins: RecommendationContextPins,
    now: datetime,
    source_recommendation_id: Optional[uuid.UUID] = None,
    origin_weekly_review_id: Optional[uuid.UUID] = None,
) -> NutritionRecommendation:
    versions = payload.versions
    return NutritionRecommendation(
        recommendation_id=recommendation_id,
        user_id=uuid.UUID(user_id),
        version=version,
        status=status.value,
        change_reason=change_reason,
        source_recommendation_id=source_recommendation_id,
        origin_weekly_review_id=origin_weekly_review_id,
        superseded_by_id=None,
        source_context_fingerprint=payload.source_context_fingerprint,
        profile_version=pins.profile_version,
        training_plan_version_id=pins.training_plan_version_id,
        checkin_token=pins.checkin_token,
        policy_version=versions.policy_version,
        catalog_version=versions.catalog_version,
        source_manifest_version=versions.source_manifest_version,
        media_manifest_version=versions.media_manifest_version,
        decision_gate=payload.decision_gate.value,
        payload=payload.model_dump(mode="json"),
        validation_codes=["recommendation_valid"],
        generated_at=now,
        confirmed_at=now if status == RecommendationStatus.active else None,
        superseded_at=None,
    )


def _supersede(
    row: NutritionRecommendation,
    replacement_id: uuid.UUID,
    now: datetime,
    reason: str,
) -> None:
    if row.status not in {RecommendationStatus.draft.value, RecommendationStatus.active.value}:
        raise AppException(409, "推荐状态不可变更", "invalid_recommendation_state")
    row.status = RecommendationStatus.superseded.value
    row.change_reason = reason
    row.superseded_by_id = replacement_id
    row.superseded_at = now


async def create_draft(
    db: AsyncSession,
    user_id: str,
    *,
    payload: RecommendationPayload,
    pins: RecommendationContextPins,
    idempotency_key: str,
    request_hash: str,
    now: Optional[datetime] = None,
    lock: bool = True,
    commit: bool = True,
) -> PersistenceResult:
    current = now or utc_now()
    try:
        if lock:
            await acquire_user_transaction_lock(db, user_id)
        replay = await _check_idempotency(
            db, user_id, OP_DRAFT_GENERATE, idempotency_key, request_hash, current
        )
        if replay is not None:
            return PersistenceResult(replay.recommendation_id, "replayed")
        result = await create_draft_core(
            db, user_id, payload=payload, pins=pins, now=current
        )
        await _record_idempotency(
            db,
            user_id,
            OP_DRAFT_GENERATE,
            idempotency_key,
            request_hash,
            result.recommendation_id,
            current,
        )
        if commit:
            await db.commit()
        return result
    except Exception:
        if commit:
            await db.rollback()
        raise


async def create_draft_core(
    db: AsyncSession,
    user_id: str,
    *,
    payload: RecommendationPayload,
    pins: RecommendationContextPins,
    now: datetime,
    origin_weekly_review_id: Optional[uuid.UUID] = None,
) -> PersistenceResult:
    """Create one draft inside the caller's locked transaction.

    The caller owns locking, idempotency, commit, and rollback. This is shared
    by the HTTP wrapper and the Agent confirmation unit of work.
    """
    recommendation_id = uuid.uuid4()
    prior = await get_current_draft(db, user_id)
    if prior is not None:
        _supersede(prior, recommendation_id, now, "superseded_by_new_draft")
        await db.flush()
    row = _new_row(
        recommendation_id=recommendation_id,
        user_id=user_id,
        version=await _next_version(db, user_id),
        status=RecommendationStatus.draft,
        change_reason="initial_generation",
        payload=payload,
        pins=pins,
        now=now,
        origin_weekly_review_id=origin_weekly_review_id,
    )
    db.add(row)
    await db.flush()
    return PersistenceResult(
        recommendation_id,
        "created",
        prior.recommendation_id if prior is not None else None,
    )


async def confirm_draft(
    db: AsyncSession,
    user_id: str,
    *,
    draft_id: uuid.UUID,
    expected_version: int,
    expected_fingerprint: str,
    current_fingerprint: str,
    idempotency_key: str,
    request_hash: str,
    now: Optional[datetime] = None,
    lock: bool = True,
    commit: bool = True,
) -> PersistenceResult:
    current = now or utc_now()
    try:
        if lock:
            await acquire_user_transaction_lock(db, user_id)
        replay = await _check_idempotency(
            db, user_id, OP_DRAFT_CONFIRM, idempotency_key, request_hash, current
        )
        if replay is not None:
            return PersistenceResult(replay.recommendation_id, "replayed")
        draft = await get_owned(db, user_id, draft_id)
        if draft is None:
            raise AppException(404, "推荐不存在", "not_owner_or_missing_recommendation")
        if draft.status != RecommendationStatus.draft.value:
            raise AppException(409, "草稿状态已变化", "invalid_recommendation_state")
        if (
            draft.version != expected_version
            or draft.source_context_fingerprint != expected_fingerprint
            or expected_fingerprint != current_fingerprint
        ):
            raise AppException(409, "推荐上下文已变化", "stale_context")
        prior_active = await get_active(db, user_id)
        if prior_active is not None:
            _supersede(prior_active, draft.recommendation_id, current, "superseded_by_confirmation")
            await db.flush()
        draft.status = RecommendationStatus.active.value
        draft.change_reason = "user_confirmation"
        draft.confirmed_at = current
        await db.flush()
        await _record_idempotency(
            db,
            user_id,
            OP_DRAFT_CONFIRM,
            idempotency_key,
            request_hash,
            draft.recommendation_id,
            current,
        )
        if commit:
            await db.commit()
        return PersistenceResult(
            draft.recommendation_id,
            "confirmed",
            prior_active.recommendation_id if prior_active is not None else None,
        )
    except Exception:
        if commit:
            await db.rollback()
        raise


async def create_replacement_active(
    db: AsyncSession,
    user_id: str,
    *,
    source_id: uuid.UUID,
    expected_version: int,
    expected_fingerprint: str,
    payload: RecommendationPayload,
    pins: RecommendationContextPins,
    idempotency_key: str,
    request_hash: str,
    now: Optional[datetime] = None,
    lock: bool = True,
    commit: bool = True,
) -> PersistenceResult:
    current = now or utc_now()
    try:
        if lock:
            await acquire_user_transaction_lock(db, user_id)
        replay = await _check_idempotency(
            db, user_id, OP_REPLACEMENT_CONFIRM, idempotency_key, request_hash, current
        )
        if replay is not None:
            return PersistenceResult(replay.recommendation_id, "replayed")
        result = await create_replacement_active_core(
            db,
            user_id,
            source_id=source_id,
            expected_version=expected_version,
            expected_fingerprint=expected_fingerprint,
            payload=payload,
            pins=pins,
            now=current,
        )
        await _record_idempotency(
            db,
            user_id,
            OP_REPLACEMENT_CONFIRM,
            idempotency_key,
            request_hash,
            result.recommendation_id,
            current,
        )
        if commit:
            await db.commit()
        return result
    except Exception:
        if commit:
            await db.rollback()
        raise


async def create_replacement_active_core(
    db: AsyncSession,
    user_id: str,
    *,
    source_id: uuid.UUID,
    expected_version: int,
    expected_fingerprint: str,
    payload: RecommendationPayload,
    pins: RecommendationContextPins,
    now: datetime,
) -> PersistenceResult:
    """Create a replacement version inside the caller's locked transaction."""
    source = await get_owned(db, user_id, source_id)
    if source is None:
        raise AppException(404, "推荐不存在", "not_owner_or_missing_recommendation")
    if source.status != RecommendationStatus.active.value:
        raise AppException(409, "当前推荐已变化", "invalid_recommendation_state")
    if (
        source.version != expected_version
        or source.source_context_fingerprint != expected_fingerprint
        or payload.source_context_fingerprint != expected_fingerprint
    ):
        raise AppException(409, "推荐上下文已变化", "stale_context")
    if payload.replacement_diff is None:
        raise AppException(400, "缺少替换差异", "invalid_replacement")
    recommendation_id = uuid.uuid4()
    row = _new_row(
        recommendation_id=recommendation_id,
        user_id=user_id,
        version=await _next_version(db, user_id),
        status=RecommendationStatus.active,
        change_reason="confirmed_food_replacement",
        payload=payload,
        pins=pins,
        now=now,
        source_recommendation_id=source.recommendation_id,
    )
    _supersede(source, recommendation_id, now, "superseded_by_replacement")
    await db.flush()
    db.add(row)
    await db.flush()
    return PersistenceResult(recommendation_id, "confirmed", source.recommendation_id)


async def delete_nutrition_data(
    db: AsyncSession, user_id: str
) -> NutritionDeletionResult:
    """Delete only owned nutrition data and explicit Agent nutrition references."""
    await acquire_user_transaction_lock(db, user_id)
    uid = uuid.UUID(user_id)
    try:
        recommendation_ids = list(
            await db.scalars(
                select(NutritionRecommendation.recommendation_id).where(
                    NutritionRecommendation.user_id == uid
                )
            )
        )
        run_ids = set(
            await db.scalars(
                select(AgentRun.run_id).where(
                    AgentRun.user_id == uid,
                    AgentRun.entry_type == "nutrition_plan",
                )
            )
        )
        nutrition_result_refs = {str(value) for value in recommendation_ids}
        proposal_filter = (
            (AgentActionProposal.tool_name.in_(NUTRITION_TOOL_NAMES))
            | (AgentActionProposal.run_id.in_(run_ids))
            | (AgentActionProposal.result_ref.in_(nutrition_result_refs))
        )
        proposals_deleted = (
            await db.execute(
                delete(AgentActionProposal).where(
                    AgentActionProposal.user_id == uid,
                    proposal_filter,
                )
            )
        ).rowcount or 0
        event_filter = (
            (AgentToolEvent.tool_name.in_(NUTRITION_TOOL_NAMES))
            | (AgentToolEvent.run_id.in_(run_ids))
            | (AgentToolEvent.result_ref.in_(nutrition_result_refs))
        )
        tool_events_deleted = (
            await db.execute(
                delete(AgentToolEvent).where(
                    AgentToolEvent.user_id == uid,
                    event_filter,
                )
            )
        ).rowcount or 0
        runs_deleted = 0
        if run_ids:
            runs_deleted = (
                await db.execute(
                    delete(AgentRun).where(AgentRun.user_id == uid, AgentRun.run_id.in_(run_ids))
                )
            ).rowcount or 0
        recommendations_deleted = (
            await db.execute(
                delete(NutritionRecommendation).where(NutritionRecommendation.user_id == uid)
            )
        ).rowcount or 0
        idempotency_deleted = (
            await db.execute(
                delete(IdempotencyRecord).where(
                    IdempotencyRecord.user_id == uid,
                    IdempotencyRecord.operation.in_(NUTRITION_IDEMPOTENCY_OPERATIONS),
                )
            )
        ).rowcount or 0
        profile = await db.scalar(select(HealthProfile).where(HealthProfile.user_id == uid))
        profile_updated = bool(
            profile is not None
            and (
                profile.food_allergen_codes is not None
                or profile.excluded_food_codes is not None
            )
        )
        if profile_updated:
            profile.food_allergen_codes = None
            profile.excluded_food_codes = None
            profile.version += 1
        await db.commit()
        return NutritionDeletionResult(
            recommendations_deleted,
            idempotency_deleted,
            proposals_deleted,
            tool_events_deleted,
            runs_deleted,
            profile_updated,
        )
    except Exception:
        await db.rollback()
        raise


__all__ = [
    "OP_DRAFT_GENERATE",
    "OP_DRAFT_CONFIRM",
    "OP_REPLACEMENT_CONFIRM",
    "NUTRITION_IDEMPOTENCY_OPERATIONS",
    "PersistenceResult",
    "NutritionDeletionResult",
    "hash_request",
    "peek_idempotency",
    "get_owned",
    "get_current_draft",
    "get_active",
    "get_next_version",
    "create_draft",
    "create_draft_core",
    "confirm_draft",
    "create_replacement_active",
    "create_replacement_active_core",
    "delete_nutrition_data",
]
