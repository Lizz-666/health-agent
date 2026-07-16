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
