from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFound, BadRequest, AppException
from app.core.privacy_gate import require_photo_privacy
from app.posture import service
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
from app.posture import safety

router = APIRouter(prefix="/api/v1/posture", tags=["posture"])


@router.get("/issues", response_model=List[IssueSummary])
async def list_issues(category: Optional[str] = Query(None)):
    issues = service.get_all_issues_list(category)
    return [
        {
            "id": i["id"],
            "name_cn": i["name_cn"],
            "category": i["category"],
            "aliases": i["aliases"],
            "definition": i["definition"],
        }
        for i in issues
    ]


@router.get("/issues/{issue_id}", response_model=IssueDetail)
async def get_issue_detail(issue_id: str):
    issue = get_issue_by_id(issue_id)
    if issue is None:
        raise NotFound("体态问题不存在")
    return issue


@router.get("/issues/{issue_id}/related", response_model=List[RelatedIssue])
async def get_related(issue_id: str):
    return service.get_related_issues(issue_id)


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


@router.post(
    "/assess/photo",
    response_model=SelfAssessResponse,
    dependencies=[Depends(require_photo_privacy)],
)
async def photo_assess(
    request: Request,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Photo assessment endpoint.

    Body is parsed manually (rather than via a Pydantic function parameter) so
    that the decorator-level auth+gate dependency chain is guaranteed to
    complete before any body reading occurs.  This prevents invalid JSON from
    producing a 422 that bypasses the 503 feature-gate response.
    """
    from app.posture.ai_service import analyze_posture_photo

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
    ai_result = await analyze_posture_photo(
        photo_req.issue_id, photo_req.photo_keys, user_id, db
    )
    result = await service.save_photo_assessment(
        db, user_id, photo_req.issue_id, photo_req.photo_keys, ai_result
    )
    return result


@router.get("/history", response_model=List[AssessmentRecord])
async def get_history(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return await service.get_user_history(db, user_id, limit, offset)


@router.post("/safety-signals", response_model=SafetySignalResponse)
async def report_safety_signal(
    request: Request,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Report a structured safety signal (spec §12.2).

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
    return await safety.record_safety_signal(
        db, user_id, signal, signal_req.idempotency_key
    )


@router.get("/profile", response_model=PostureProfileResponse)
async def get_profile(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Current user's full posture profile (spec §9.2).

    Returns evaluated issues, the complementary unevaluated categories and a
    certainty-keyed summary. Identity comes only from the JWT -- there is no
    ``user_id`` query parameter, so the query is always scoped to the caller
    and one user can never read another user's profile.
    """
    return await service.get_user_profile(db, user_id)


@router.get("/profile/{issue_id}", response_model=PostureProfileEntryResponse)
async def get_profile_entry(
    issue_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """One issue's profile entry for the current user (spec §9.2).

    - unknown ``issue_id`` -> 404 ``issue_not_found``
    - known issue but the caller has no entry -> 404 ``profile_entry_not_found``
      (does not reveal whether any other user has data for this issue)
    """
    issue = get_issue_by_id(issue_id)
    if issue is None:
        raise AppException(404, "体态问题不存在", "issue_not_found")
    entry = await service.get_user_profile_entry(db, user_id, issue_id)
    if entry is None:
        raise AppException(
            404, "当前用户尚未评估该体态问题", "profile_entry_not_found"
        )
    return service.build_profile_entry_detail(entry, issue)


@router.get("/priorities", response_model=PrioritySuggestionsResponse)
async def get_priorities(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Current user's deterministic priority suggestions (spec §9.2 / §10.6).

    Read-only: recomputes risk classification, returns three buckets
    (normal_candidates / retest_required / safety_blocked) plus the
    server-generated suggestion_id / profile_version / rule_version /
    risk_version used by the confirm optimistic lock. Identity comes only
    from the JWT (no user_id param) so the query is always caller-scoped.
    Performs no writes and never auto-creates a plan.
    """
    return await service.get_priority_suggestions(db, user_id)


@router.post("/goals/confirm", response_model=ConfirmedGoalsResponse)
async def confirm_goals(
    request: Request,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm 1-3 of the current normal-candidate goals (spec §9.2 / §10.7).

    Body is parsed manually so a bad payload / unknown field (including a
    client-supplied ``priority_context_snapshot``) surfaces as 400 rather than
    422, mirroring the safety-signals error style. The server regenerates the
    control values and uses them as the optimistic lock; restricted/red_flag
    goals are rejected with their own 409 codes.
    """
    try:
        body = await request.json()
    except Exception:
        raise BadRequest("请求体JSON格式错误")

    try:
        req = ConfirmGoalsRequest.model_validate(body)
    except ValidationError:
        raise BadRequest("目标确认请求参数错误")

    return await service.confirm_posture_goals(
        db,
        user_id,
        req.suggestion_id,
        req.profile_version,
        req.goals,
        req.idempotency_key,
    )
