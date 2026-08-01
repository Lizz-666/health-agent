"""Ownership-scoped nutrition recommendation application service."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException
from app.nutrition import persistence
from app.nutrition.calculator import calculate_targets
from app.nutrition.context import resolve_nutrition_context
from app.nutrition.generator import (
    NutritionGenerationError,
    generate_recommendation,
    preview_replacement,
)
from app.nutrition.knowledge import (
    load_catalog,
    load_media_manifest,
    load_policy,
    load_source_manifest,
)
from app.nutrition.models import NutritionRecommendation
from app.nutrition.safety import classify_nutrition
from app.nutrition.schemas import (
    DayKind,
    GateStatus,
    MealName,
    NutritionContext,
    NutritionDecision,
    NutritionTargetRanges,
    NutritionVersions,
    RecommendationContextPins,
    RecommendationPayload,
)
from app.nutrition.schemas_api import (
    ConfirmRequest,
    DeletionResponse,
    DraftRequest,
    EligibilityResponse,
    FoodListResponse,
    RecommendationStateResponse,
    RecommendationView,
    ReplacementConfirmRequest,
    ReplacementRequest,
    TargetsResponse,
)
from app.nutrition.validator import validate_recommendation
from app.posture.user_lock import acquire_user_transaction_lock

DATA = Path(__file__).resolve().parent / "data"
_catalog = None
_policy = None
_media = None
_sources = None


@dataclass(frozen=True)
class CurrentNutritionState:
    context: NutritionContext
    decision: NutritionDecision
    allergen_codes: set[str]
    excluded_food_ids: set[str]


@dataclass(frozen=True)
class PreparedNutritionDraft:
    payload: RecommendationPayload
    pins: RecommendationContextPins
    state: CurrentNutritionState


@dataclass(frozen=True)
class PreparedNutritionReplacement:
    payload: RecommendationPayload
    pins: RecommendationContextPins
    state: CurrentNutritionState
    source: NutritionRecommendation


def _resources():
    global _catalog, _policy, _media, _sources
    if _catalog is None:
        _catalog = load_catalog(DATA / "foods.v1.json")
        _policy = load_policy(DATA / "nutrition_policy.v1.json")
        _media = load_media_manifest(DATA / "media_manifest.v1.json")
        _sources = load_source_manifest(DATA / "source_manifest.v1.json")
    return _catalog, _policy, _media, _sources


def versions() -> NutritionVersions:
    catalog, policy, media, sources = _resources()
    return NutritionVersions(
        policy_version=policy.policy_version,
        catalog_version=catalog.catalog_version,
        source_manifest_version=sources.manifest_version,
        media_manifest_version=media.manifest_version,
    )


def require_runtime_enabled() -> None:
    if not settings.NUTRITION_RUNTIME_ENABLED:
        raise AppException(
            503,
            "营养推荐功能尚未启用",
            "nutrition_runtime_disabled",
        )


async def _current_state(
    db: AsyncSession,
    user_id: str,
    iana_timezone: str,
    *,
    now: Optional[datetime] = None,
) -> CurrentNutritionState:
    catalog, policy, _media, _sources = _resources()
    try:
        context = await resolve_nutrition_context(
            db,
            user_id,
            iana_timezone,
            versions(),
            now=now,
        )
    except ValueError as exc:
        raise AppException(422, "时区无效", "invalid_timezone") from exc
    allowed_exclusions = {code.value for code in policy.exclusion_food_ids}
    decision = classify_nutrition(context, allowed_exclusions)
    allergens = {code.value for code in (context.food_allergen_codes or [])}
    excluded_food_ids: set[str] = set()
    for code in context.excluded_food_codes or []:
        for enum_code, food_ids in policy.exclusion_food_ids.items():
            if enum_code.value == code:
                excluded_food_ids.update(food_ids)
                break
    return CurrentNutritionState(context, decision, allergens, excluded_food_ids)


def _raise_for_gate(decision: NutritionDecision) -> None:
    mapping = {
        GateStatus.red_flag: "nutrition_red_flag",
        GateStatus.restricted: "nutrition_restricted",
        GateStatus.limited_education: "nutrition_limited_education",
        GateStatus.clarification_required: "nutrition_clarification_required",
    }
    if decision.gate in mapping:
        raise AppException(409, "当前状态不支持自动营养推荐", mapping[decision.gate])


def _targets(state: CurrentNutritionState):
    _raise_for_gate(state.decision)
    context = state.context
    if context.weight_source is None or context.height_cm is None or context.age is None:
        raise AppException(409, "营养资料不完整", "nutrition_clarification_required")
    try:
        return calculate_targets(
            context.weight_source.weight_kg,
            context.height_cm,
            context.age,
        )
    except ValueError as exc:
        raise AppException(409, "营养资料不在支持范围", "nutrition_limited_education") from exc


def _pins(state: CurrentNutritionState) -> RecommendationContextPins:
    context = state.context
    if (
        context.profile_version is None
        or context.active_plan_version_id is None
        or context.checkin_token is None
    ):
        raise AppException(409, "营养资料不完整", "nutrition_clarification_required")
    return RecommendationContextPins(
        profile_version=context.profile_version,
        training_plan_version_id=context.active_plan_version_id,
        checkin_token=context.checkin_token,
    )


def _validate(payload: RecommendationPayload, state: CurrentNutritionState) -> None:
    catalog, policy, media, _sources = _resources()
    result = validate_recommendation(
        payload,
        catalog,
        policy,
        media,
        state.decision,
        versions(),
        state.allergen_codes,
        state.excluded_food_ids,
    )
    if not result.valid:
        codes = {issue.code for issue in result.issues}
        code = (
            "stale_context"
            if codes & {"stale_context", "stale_version", "decision_gate_mismatch"}
            else "recommendation_validation_failed"
        )
        raise AppException(409, "营养推荐未通过校验", code)


def _view(row: NutritionRecommendation) -> RecommendationView:
    try:
        payload = RecommendationPayload.model_validate(row.payload)
    except Exception as exc:
        raise AppException(503, "营养推荐数据不可用", "recommendation_integrity_error") from exc
    return RecommendationView(
        recommendation_id=str(row.recommendation_id),
        version=row.version,
        status=row.status,
        change_reason=row.change_reason,
        source_recommendation_id=(
            str(row.source_recommendation_id) if row.source_recommendation_id else None
        ),
        superseded_by_id=str(row.superseded_by_id) if row.superseded_by_id else None,
        payload=payload,
        validation_codes=row.validation_codes,
        generated_at=row.generated_at,
        confirmed_at=row.confirmed_at,
        superseded_at=row.superseded_at,
    )


def _assert_row_current(row: NutritionRecommendation, state: CurrentNutritionState) -> None:
    _raise_for_gate(state.decision)
    context = state.context
    if (
        row.profile_version != context.profile_version
        or row.training_plan_version_id != context.active_plan_version_id
        or row.checkin_token != context.checkin_token
        or row.source_context_fingerprint != state.decision.context_fingerprint
    ):
        raise AppException(409, "营养推荐上下文已变化", "stale_context")
    _validate(RecommendationPayload.model_validate(row.payload), state)


async def eligibility(
    db: AsyncSession, user_id: str, iana_timezone: str
) -> EligibilityResponse:
    require_runtime_enabled()
    state = await _current_state(db, user_id, iana_timezone)
    return EligibilityResponse(
        gate=state.decision.gate,
        reason_codes=state.decision.reason_codes,
        missing_field_codes=state.decision.missing_field_codes,
        bmi_category=state.decision.bmi_category,
        versions=versions(),
    )


async def targets(db: AsyncSession, user_id: str, iana_timezone: str) -> TargetsResponse:
    require_runtime_enabled()
    state = await _current_state(db, user_id, iana_timezone)
    target = _targets(state)
    display = NutritionTargetRanges.model_validate(
        target.model_dump(exclude={"reference_center_kcal"})
    )
    return TargetsResponse(gate=state.decision.gate, targets=display, versions=versions())


def list_foods() -> FoodListResponse:
    require_runtime_enabled()
    catalog, _policy, _media, _sources = _resources()
    return FoodListResponse(catalog_version=catalog.catalog_version, foods=catalog.foods)


def get_food(food_id: str):
    require_runtime_enabled()
    catalog, _policy, _media, _sources = _resources()
    food = next((item for item in catalog.foods if item.food_id == food_id), None)
    if food is None:
        raise AppException(404, "食物不存在", "food_not_found")
    return food


async def read_agent_targets(
    db: AsyncSession, user_id: str, iana_timezone: str
) -> tuple[CurrentNutritionState, NutritionTargetRanges | None]:
    """Return the deterministic gate and, only when eligible, rounded targets."""
    require_runtime_enabled()
    state = await _current_state(db, user_id, iana_timezone)
    if state.decision.gate not in {
        GateStatus.eligible,
        GateStatus.eligible_conservative,
    }:
        return state, None
    target = _targets(state)
    return state, NutritionTargetRanges.model_validate(
        target.model_dump(exclude={"reference_center_kcal"})
    )


def read_agent_portion_ranges() -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    """Return versioned policy ranges without model-side arithmetic."""
    require_runtime_enabled()
    _catalog, policy, _media, _sources = _resources()
    food_groups = {
        code: [bounds[0], bounds[1]]
        for code, bounds in policy.food_group_daily_ranges.items()
    }
    meal_shares = {
        code: [bounds[0], bounds[1]]
        for code, bounds in policy.meal_share_pct.items()
    }
    return food_groups, meal_shares


async def prepare_draft_domain(
    db: AsyncSession, user_id: str, iana_timezone: str
) -> PreparedNutritionDraft:
    """Build and independently validate a draft without persisting it."""
    require_runtime_enabled()
    state = await _current_state(db, user_id, iana_timezone)
    target = _targets(state)
    catalog, policy, media, _sources = _resources()
    try:
        payload = generate_recommendation(
            catalog=catalog,
            policy=policy,
            media_manifest=media,
            decision=state.decision,
            targets=target,
            versions=versions(),
            requested_goal=state.context.active_plan_goal or "",
            allergen_codes=state.allergen_codes,
            excluded_food_ids=state.excluded_food_ids,
        )
    except NutritionGenerationError as exc:
        raise AppException(409, "无法生成安全候选", exc.code) from exc
    _validate(payload, state)
    return PreparedNutritionDraft(payload, _pins(state), state)


async def resolve_agent_recommendation(
    db: AsyncSession,
    user_id: str,
    iana_timezone: str,
    recommendation_id: str | None = None,
) -> tuple[CurrentNutritionState, NutritionRecommendation | None]:
    """Resolve only the current owned active/draft row for Agent reads."""
    state, row = await resolve_agent_context(
        db, user_id, iana_timezone, recommendation_id
    )
    _raise_for_gate(state.decision)
    if row is not None:
        _assert_row_current(row, state)
    return state, row


async def resolve_agent_context(
    db: AsyncSession,
    user_id: str,
    iana_timezone: str,
    recommendation_id: str | None = None,
) -> tuple[CurrentNutritionState, NutritionRecommendation | None]:
    """Resolve the current owned row plus gate codes without bypassing safety."""
    require_runtime_enabled()
    active = await persistence.get_active(db, user_id)
    draft = await persistence.get_current_draft(db, user_id)
    current = [row for row in (active, draft) if row is not None]
    row = active or draft
    if recommendation_id is not None:
        row = next(
            (
                item
                for item in current
                if str(item.recommendation_id) == recommendation_id
            ),
            None,
        )
        if row is None:
            raise AppException(
                404,
                "推荐不存在",
                "not_owner_or_missing_recommendation",
            )
    state = await _current_state(db, user_id, iana_timezone)
    if row is not None and state.decision.gate in {
        GateStatus.eligible,
        GateStatus.eligible_conservative,
    }:
        _assert_row_current(row, state)
    return state, row


async def prepare_replacement_domain(
    db: AsyncSession,
    user_id: str,
    iana_timezone: str,
    *,
    day_kind: DayKind,
    meal: MealName,
    item_index: int,
    from_food_id: str,
    to_food_id: str,
) -> PreparedNutritionReplacement:
    """Build and independently validate a current-active replacement."""
    state, row = await resolve_agent_recommendation(
        db, user_id, iana_timezone
    )
    if row is None or row.status != "active":
        raise AppException(409, "当前没有可替换的生效推荐", "invalid_recommendation_state")
    catalog, policy, _media, _sources = _resources()
    try:
        payload = preview_replacement(
            RecommendationPayload.model_validate(row.payload),
            catalog=catalog,
            policy=policy,
            day_kind=day_kind,
            meal=meal,
            item_index=item_index,
            from_food_id=from_food_id,
            to_food_id=to_food_id,
            allergen_codes=state.allergen_codes,
            excluded_food_ids=state.excluded_food_ids,
        )
    except NutritionGenerationError as exc:
        raise AppException(409, "替换不可用", exc.code) from exc
    _validate(payload, state)
    return PreparedNutritionReplacement(payload, _pins(state), state, row)


async def generate_draft(
    db: AsyncSession, user_id: str, request: DraftRequest
) -> RecommendationStateResponse:
    require_runtime_enabled()
    await acquire_user_transaction_lock(db, user_id)
    request_hash = persistence.hash_request(
        {"operation": "draft_generate", "iana_timezone": request.iana_timezone}
    )
    replay = await persistence.peek_idempotency(
        db,
        user_id,
        persistence.OP_DRAFT_GENERATE,
        request.idempotency_key,
        request_hash,
    )
    if replay is not None:
        return RecommendationStateResponse(
            has_recommendation=True,
            recommendation=_view(replay),
            operation_status="replayed",
        )
    prepared = await prepare_draft_domain(
        db, user_id, request.iana_timezone
    )
    result = await persistence.create_draft(
        db,
        user_id,
        payload=prepared.payload,
        pins=prepared.pins,
        idempotency_key=request.idempotency_key,
        request_hash=request_hash,
        lock=False,
    )
    row = await persistence.get_owned(db, user_id, result.recommendation_id)
    if row is None:
        raise AppException(503, "营养推荐数据不可用", "recommendation_integrity_error")
    return RecommendationStateResponse(
        has_recommendation=True,
        recommendation=_view(row),
        operation_status=result.status,
        superseded_recommendation_id=(
            str(result.superseded_recommendation_id)
            if result.superseded_recommendation_id
            else None
        ),
    )


async def _get_current(
    db: AsyncSession,
    user_id: str,
    iana_timezone: str,
    *,
    active: bool,
) -> RecommendationStateResponse:
    require_runtime_enabled()
    row = (
        await persistence.get_active(db, user_id)
        if active
        else await persistence.get_current_draft(db, user_id)
    )
    if row is None:
        return RecommendationStateResponse(has_recommendation=False)
    state = await _current_state(db, user_id, iana_timezone)
    _assert_row_current(row, state)
    return RecommendationStateResponse(has_recommendation=True, recommendation=_view(row))


async def get_draft(db: AsyncSession, user_id: str, iana_timezone: str):
    return await _get_current(db, user_id, iana_timezone, active=False)


async def get_active(db: AsyncSession, user_id: str, iana_timezone: str):
    return await _get_current(db, user_id, iana_timezone, active=True)


async def confirm(
    db: AsyncSession,
    user_id: str,
    draft_id: uuid.UUID,
    request: ConfirmRequest,
) -> RecommendationStateResponse:
    require_runtime_enabled()
    await acquire_user_transaction_lock(db, user_id)
    request_hash = persistence.hash_request(
        {
            "operation": "draft_confirm",
            "draft_id": str(draft_id),
            "expected_version": request.expected_version,
            "expected_fingerprint": request.expected_fingerprint,
            "iana_timezone": request.iana_timezone,
        }
    )
    replay = await persistence.peek_idempotency(
        db,
        user_id,
        persistence.OP_DRAFT_CONFIRM,
        request.idempotency_key,
        request_hash,
    )
    if replay is not None:
        return RecommendationStateResponse(
            has_recommendation=True,
            recommendation=_view(replay),
            operation_status="replayed",
        )
    row = await persistence.get_owned(db, user_id, draft_id)
    if row is None:
        raise AppException(404, "推荐不存在", "not_owner_or_missing_recommendation")
    state = await _current_state(db, user_id, request.iana_timezone)
    _assert_row_current(row, state)
    result = await persistence.confirm_draft(
        db,
        user_id,
        draft_id=draft_id,
        expected_version=request.expected_version,
        expected_fingerprint=request.expected_fingerprint,
        current_fingerprint=state.decision.context_fingerprint,
        idempotency_key=request.idempotency_key,
        request_hash=request_hash,
        lock=False,
    )
    active = await persistence.get_owned(db, user_id, result.recommendation_id)
    if active is None:
        raise AppException(503, "营养推荐数据不可用", "recommendation_integrity_error")
    return RecommendationStateResponse(
        has_recommendation=True,
        recommendation=_view(active),
        operation_status=result.status,
        superseded_recommendation_id=(
            str(result.superseded_recommendation_id)
            if result.superseded_recommendation_id
            else None
        ),
    )


def _replacement_hash(active_id: uuid.UUID, request: ReplacementRequest) -> str:
    return persistence.hash_request(
        {
            "operation": "replacement_confirm",
            "active_id": str(active_id),
            **request.model_dump(mode="json", exclude={"idempotency_key"}),
        }
    )


async def _replacement_preview(
    db: AsyncSession,
    user_id: str,
    active_id: uuid.UUID,
    request: ReplacementRequest,
) -> tuple[RecommendationPayload, CurrentNutritionState, NutritionRecommendation]:
    row = await persistence.get_owned(db, user_id, active_id)
    if row is None:
        raise AppException(404, "推荐不存在", "not_owner_or_missing_recommendation")
    if row.status != "active":
        raise AppException(409, "当前推荐状态已变化", "invalid_recommendation_state")
    state = await _current_state(db, user_id, request.iana_timezone)
    _assert_row_current(row, state)
    if row.version != request.expected_version or row.source_context_fingerprint != request.expected_fingerprint:
        raise AppException(409, "营养推荐上下文已变化", "stale_context")
    catalog, policy, _media, _sources = _resources()
    try:
        payload = preview_replacement(
            RecommendationPayload.model_validate(row.payload),
            catalog=catalog,
            policy=policy,
            day_kind=request.day_kind,
            meal=request.meal,
            item_index=request.item_index,
            from_food_id=request.from_food_id,
            to_food_id=request.to_food_id,
            allergen_codes=state.allergen_codes,
            excluded_food_ids=state.excluded_food_ids,
        )
    except NutritionGenerationError as exc:
        raise AppException(409, "替换不可用", exc.code) from exc
    _validate(payload, state)
    return payload, state, row


async def replacement_preview(
    db: AsyncSession,
    user_id: str,
    active_id: uuid.UUID,
    request: ReplacementRequest,
) -> RecommendationStateResponse:
    require_runtime_enabled()
    payload, _state, row = await _replacement_preview(
        db, user_id, active_id, request
    )
    resulting_version = await persistence.get_next_version(db, user_id)
    preview = _view(row).model_copy(update={"payload": payload})
    return RecommendationStateResponse(
        has_recommendation=True,
        recommendation=preview,
        operation_status="preview",
        preview_resulting_version=resulting_version,
    )


async def replacement_confirm(
    db: AsyncSession,
    user_id: str,
    active_id: uuid.UUID,
    request: ReplacementConfirmRequest,
) -> RecommendationStateResponse:
    require_runtime_enabled()
    await acquire_user_transaction_lock(db, user_id)
    request_hash = _replacement_hash(active_id, request)
    replay = await persistence.peek_idempotency(
        db,
        user_id,
        persistence.OP_REPLACEMENT_CONFIRM,
        request.idempotency_key,
        request_hash,
    )
    if replay is not None:
        return RecommendationStateResponse(
            has_recommendation=True,
            recommendation=_view(replay),
            operation_status="replayed",
        )
    payload, state, row = await _replacement_preview(db, user_id, active_id, request)
    result = await persistence.create_replacement_active(
        db,
        user_id,
        source_id=row.recommendation_id,
        expected_version=request.expected_version,
        expected_fingerprint=request.expected_fingerprint,
        payload=payload,
        pins=_pins(state),
        idempotency_key=request.idempotency_key,
        request_hash=request_hash,
        lock=False,
    )
    active = await persistence.get_owned(db, user_id, result.recommendation_id)
    if active is None:
        raise AppException(503, "营养推荐数据不可用", "recommendation_integrity_error")
    return RecommendationStateResponse(
        has_recommendation=True,
        recommendation=_view(active),
        operation_status=result.status,
        superseded_recommendation_id=(
            str(result.superseded_recommendation_id)
            if result.superseded_recommendation_id
            else None
        ),
    )


async def delete_data(db: AsyncSession, user_id: str) -> DeletionResponse:
    result = await persistence.delete_nutrition_data(db, user_id)
    return DeletionResponse(**result.__dict__)


__all__ = [
    "eligibility",
    "targets",
    "list_foods",
    "get_food",
    "read_agent_targets",
    "read_agent_portion_ranges",
    "prepare_draft_domain",
    "resolve_agent_recommendation",
    "resolve_agent_context",
    "prepare_replacement_domain",
    "generate_draft",
    "get_draft",
    "get_active",
    "confirm",
    "replacement_preview",
    "replacement_confirm",
    "delete_data",
]
