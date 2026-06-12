from typing import Optional, List, Tuple, Dict
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.posture.models import PostureAssessment
from app.posture.knowledge import get_issue_by_id, get_all_issues


def get_all_issues_list(category: Optional[str] = None) -> List[dict]:
    return get_all_issues(category)


def get_related_issues(issue_id: str) -> List[dict]:
    issue = get_issue_by_id(issue_id)
    if not issue:
        return []
    result = []
    for rel in issue.get("related_issues", []):
        related = get_issue_by_id(rel["id"])
        if related and rel.get("weight", 0) >= 0.6:
            result.append(
                {
                    "id": rel["id"],
                    "name_cn": related["name_cn"],
                    "weight": rel["weight"],
                    "relation": rel["relation"],
                }
            )
    result.sort(key=lambda x: x["weight"], reverse=True)
    return result[:3]


def _evaluate_result(issue: dict, answer: str) -> Tuple[str, str]:
    if answer == "negative":
        return "normal", "自测结果为阴性，你该方面的体态目前正常。保持良好习惯即可。"
    elif answer == "positive":
        return (
            "moderate",
            "自测结果为阳性，建议进行以下纠正训练。如伴红旗征请及时就医。",
        )
    else:
        return "uncertain", "自测结果不确定。建议使用 AI 拍照分析进行更精确的判断。"


async def save_self_assessment(
    db: AsyncSession,
    user_id: str,
    issue_id: str,
    answer: str,
    test_index: int,
) -> Optional[dict]:
    issue = get_issue_by_id(issue_id)
    if not issue:
        return None
    result_level, suggestion = _evaluate_result(issue, answer)
    assessment = PostureAssessment(
        user_id=UUID(user_id),
        issue_id=issue_id,
        method="self_test",
        result=result_level,
        self_test_answers={"test_index": test_index, "answer": answer},
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)
    return {
        "id": str(assessment.id),
        "issue_id": assessment.issue_id,
        "result": result_level,
        "suggestion": suggestion,
    }


def _map_ai_level_to_db(ai_level: str) -> str:
    """Map AI analysis level to a DB/Flutter-compatible result.

    Flutter currently recognises normal / moderate / severe / uncertain.
    AI ``mild`` is deterministically promoted to ``moderate`` so that
    Flutter does not encounter an unknown state.  The original AI level
    is preserved in the ``ai_response`` JSONB column.
    """
    if ai_level == "mild":
        return "moderate"
    return ai_level


async def save_photo_assessment(
    db: AsyncSession,
    user_id: str,
    issue_id: str,
    photo_keys: List[str],
    ai_result: dict,
) -> dict:
    # ai_result is already validated by AIAnalysisResult schema in ai_service.
    # level must be one of: normal, mild, moderate, severe.
    # Never fall back to "normal" on missing/invalid data.
    ai_level = ai_result["level"]
    db_result = _map_ai_level_to_db(ai_level)

    if db_result == "normal":
        suggestion = (
            ai_result.get("suggestion", "")
            or "AI 分析结果为正常，保持良好的体态习惯即可。"
        )
    elif db_result == "moderate":
        suggestion = (
            ai_result.get("suggestion", "")
            or "存在需要关注的体态问题，建议进行纠正训练。"
        )
    else:  # severe
        suggestion = (
            ai_result.get("suggestion", "")
            or "体态问题较为明显，建议尽快咨询专业医师。"
        )

    assessment = PostureAssessment(
        user_id=UUID(user_id),
        issue_id=issue_id,
        method="ai_photo",
        result=db_result,
        ai_response=ai_result,
        photo_keys=photo_keys,
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)
    return {
        "id": str(assessment.id),
        "issue_id": assessment.issue_id,
        "result": db_result,
        "suggestion": suggestion,
    }


async def get_user_history(
    db: AsyncSession, user_id: str, limit: int = 20, offset: int = 0
) -> List[dict]:
    stmt = (
        select(PostureAssessment)
        .where(PostureAssessment.user_id == UUID(user_id))
        .order_by(desc(PostureAssessment.created_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    output = []
    for r in records:
        issue = get_issue_by_id(r.issue_id)
        output.append(
            {
                "id": str(r.id),
                "issue_id": r.issue_id,
                "issue_name": issue["name_cn"] if issue else r.issue_id,
                "method": r.method,
                "result": r.result,
                "created_at": r.created_at,
            }
        )
    return output
