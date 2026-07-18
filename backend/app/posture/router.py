from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.dependencies import get_current_user
from app.core.actor_context import ActorContext, get_actor_context
from app.core.exceptions import NotFound, BadRequest, AppException
from app.core.privacy_gate import require_photo_privacy
from app.posture import service, tools
from app.posture.schemas import (
    SelfAssessRequest,
    PhotoAssessRequest,
    IssueSummary,
    IssueDetail,
    RelatedIssue,
    SelfAssessResponse,
    AssessmentRecord,
    SafetySignalRequest,
    SafetySignalResponse,
    PostureProfileResponse,
    PostureProfileEntryResponse,
    PrioritySuggestionsResponse,
    ConfirmGoalsRequest,
    ConfirmedGoalsResponse,
)
from app.posture.knowledge import get_issue_by_id

router = APIRouter(prefix="/api/v1/posture", tags=["posture"])


# --- Public knowledge routes (spec §10.1 / §10.2): no actor, no DB -----------
# These delegate to the read-only knowledge Tools. No authentication.


@router.get("/issues", response_model=List[IssueSummary])
async def list_issues(category: Optional[str] = Query(None)):
    return tools.list_posture_issues(category)


@router.get("/issues/{issue_id}", response_model=IssueDetail)
async def get_issue_detail(issue_id: str):
    return tools.get_posture_issue(issue_id)


@router.get("/issues/{issue_id}/related", response_model=List[RelatedIssue])
async def get_related(issue_id: str):
    # No equivalent Tool (related-issue listing is not one of the 8). Kept on
    # the original service call so behaviour is unchanged.
    return service.get_related_issues(issue_id)


# --- Self-test submission (no equivalent Tool among the 8): unchanged --------


@router.post("/assess", response_model=SelfAssessResponse)
async def self_assess(
    request: SelfAssessRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if request.answer not in ("positive", "negative", "uncertain"):
        raise BadRequest("答案只能是 positive/negative/uncertain")
    result = await service.save_self_assessment(
        db, user_id, request.issue_id, request.answer, request.test_index
    )
    if result is None:
        raise NotFound("体态问题不存在")
    return result


# --- Photo analysis (spec §10.4): gate (decorator) -> Tool -------------------
# The decorator-level privacy gate is INTENTIONALLY retained so an
# unauthenticated / gate-disabled request surfaces 503 BEFORE any body reading
# (invalid JSON must not bypass the gate with a 4xx). The Tool re-checks the
# gate internally so direct Tool / Agent callers hit the same boundary.


@router.post(
    "/assess/photo",
    response_model=SelfAssessResponse,
    dependencies=[Depends(require_photo_privacy)],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": PhotoAssessRequest.model_json_schema()
                }
            },
        }
    },
)
async def photo_assess(
    request: Request,
    actor: ActorContext = Depends(get_actor_context),
    db: AsyncSession = Depends(get_db),
):
    """Photo assessment endpoint (spec §10.4).

    Body is parsed manually (rather than via a Pydantic function parameter) so
    that the decorator-level auth+gate dependency chain is guaranteed to
    complete before any body reading occurs.  This prevents invalid JSON from
    producing a 422 that bypasses the 503 feature-gate response. The Tool
    enforces gate -> ownership -> idempotent orchestration. The client-provided
    ``idempotency_key`` is required and validated by ``PhotoAssessRequest``.
    """
    try:
        body = await request.json()
    except Exception:
        raise BadRequest("请求体JSON格式错误")

    try:
        photo_req = PhotoAssessRequest.model_validate(body)
    except ValidationError:
        raise BadRequest("请求参数错误")

    issue = get_issue_by_id(photo_req.issue_id)
    if issue is None:
        raise NotFound("体态问题不存在")
    if not photo_req.photo_keys:
        raise BadRequest("请上传至少一张照片")

    return await tools.analyze_posture_photo(
        db,
        actor,
        photo_req.issue_id,
        photo_req.photo_keys,
        photo_req.idempotency_key,
    )


# --- History (no equivalent Tool among the 8): unchanged ---------------------


@router.get("/history", response_model=List[AssessmentRecord])
async def get_history(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return await service.get_user_history(db, user_id, limit, offset)


# --- Safety signal reporting (spec §10.8): Tool ------------------------------


@router.post("/safety-signals", response_model=SafetySignalResponse)
async def report_safety_signal(
    request: Request,
    actor: ActorContext = Depends(get_actor_context),
    db: AsyncSession = Depends(get_db),
):
    """Report a structured safety signal (spec §12.2 / §10.8).

    Body is parsed manually so invalid enum / missing required fields surface as
    400 (not 422), mirroring the photo-assess error style. Raw signal payloads
    are never logged; only a request hash is persisted for idempotency.
    """
    try:
        body = await request.json()
    except Exception:
        raise BadRequest("请求体JSON格式错误")

    try:
        signal_req = SafetySignalRequest.model_validate(body)
    except ValidationError:
        raise BadRequest("安全信号请求参数错误")

    if signal_req.related_issue_id and get_issue_by_id(signal_req.related_issue_id) is None:
        raise AppException(400, "关联的体态问题不存在", "issue_not_found")

    signal = {
        "signal_type": signal_req.signal_type.value,
        "body_region": signal_req.body_region.value if signal_req.body_region else None,
        "related_issue_id": signal_req.related_issue_id,
        "severity_hint": signal_req.severity_hint.value if signal_req.severity_hint else None,
        "reported_at": signal_req.reported_at.isoformat() if signal_req.reported_at else None,
    }
    return await tools.report_safety_signal(
        db, actor, signal, signal_req.idempotency_key
    )


# --- Profile (spec §10.5): Tool ---------------------------------------------


@router.get("/profile", response_model=PostureProfileResponse)
async def get_profile(
    actor: ActorContext = Depends(get_actor_context),
    db: AsyncSession = Depends(get_db),
):
    """Current user's full posture profile (spec §9.2 / §10.5).

    Identity comes only from the JWT-derived ``ActorContext`` -- there is no
    ``user_id`` query parameter, so the query is always scoped to the caller.
    """
    return await tools.get_posture_profile(db, actor)


@router.get("/profile/{issue_id}", response_model=PostureProfileEntryResponse)
async def get_profile_entry(
    issue_id: str,
    actor: ActorContext = Depends(get_actor_context),
    db: AsyncSession = Depends(get_db),
):
    """One issue's profile entry for the current user (spec §9.2 / §10.5).

    - unknown ``issue_id`` -> 404 ``issue_not_found``
    - known issue but the caller has no entry -> 404 ``profile_entry_not_found``
      (does not reveal whether any other user has data for this issue)
    """
    return await tools.get_posture_profile(db, actor, issue_id)


# --- Priority suggestions (spec §10.6): Tool --------------------------------


@router.get("/priorities", response_model=PrioritySuggestionsResponse)
async def get_priorities(
    actor: ActorContext = Depends(get_actor_context),
    db: AsyncSession = Depends(get_db),
):
    """Current user's deterministic priority suggestions (spec §9.2 / §10.6).

    Read-only: recomputes risk classification, returns three buckets
    (normal_candidates / retest_required / safety_blocked) plus the
    server-generated suggestion_id / profile_version / rule_version /
    risk_version used by the confirm optimistic lock. Identity comes only from
    the JWT (no user_id param). Performs no writes and never auto-creates a
    plan.
    """
    return await tools.suggest_posture_priorities(db, actor)


# --- Goal confirmation (spec §10.7): Tool -----------------------------------


@router.post("/goals/confirm", response_model=ConfirmedGoalsResponse)
async def confirm_goals(
    request: Request,
    actor: ActorContext = Depends(get_actor_context),
    db: AsyncSession = Depends(get_db),
):
    """Confirm 1-3 of the current normal-candidate goals (spec §9.2 / §10.7).

    Body is parsed manually so a bad payload / unknown field (including a
    client-supplied ``priority_context_snapshot``) surfaces as 400 rather than
    422. The server regenerates the control values and uses them as the
    optimistic lock; restricted/red_flag goals are rejected with their own 409
    codes.
    """
    try:
        body = await request.json()
    except Exception:
        raise BadRequest("请求体JSON格式错误")

    try:
        req = ConfirmGoalsRequest.model_validate(body)
    except ValidationError:
        raise BadRequest("目标确认请求参数错误")

    return await tools.confirm_posture_goals(
        db,
        actor,
        req.suggestion_id,
        req.profile_version,
        req.goals,
        req.idempotency_key,
    )
