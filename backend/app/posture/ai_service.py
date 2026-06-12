import json
import re
import logging
import httpx
from typing import List
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import settings
from app.posture.knowledge import get_issue_by_id
from app.posture.schemas import AIAnalysisResult
from app.upload.service import generate_signed_url
from app.auth.models import User
from app.core.exceptions import ServiceUnavailable
from uuid import UUID

logger = logging.getLogger(__name__)

QWEN_VL_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


async def _get_user_info(db: AsyncSession, user_id: str) -> dict:
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user:
        return {
            "gender": user.gender or "未知",
            "age": str(user.age) if user.age else "未知",
            "height": "%dcm" % user.height if user.height else "未知",
            "weight": "%dkg" % user.weight if user.weight else "未知",
        }
    return {"gender": "未知", "age": "未知", "height": "未知", "weight": "未知"}


async def analyze_posture_photo(
    issue_id: str,
    photo_keys: List[str],
    user_id: str,
    db: AsyncSession,
) -> dict:
    issue = get_issue_by_id(issue_id)
    if not issue:
        raise ServiceUnavailable("所请求的体态问题不存在，无法分析")

    signed_urls = [generate_signed_url(key) for key in photo_keys]
    user_info = await _get_user_info(db, user_id)

    content_parts = []
    for url in signed_urls:
        content_parts.append({"type": "image_url", "image_url": {"url": url}})

    prompt = (
        "你是一位体态筛查辅助工具，帮助从照片中识别潜在的体态问题。"
        "这只是筛查辅助，不能替代专业康复评估。\n\n"
        "当前筛查项目：%s（%s）\n\n"
        "用户概况：性别=%s，年龄=%s，身高=%s，体重=%s\n\n"
        "请分析上传的照片，完成以下任务：\n"
        "1. 识别与「%s」相关的视觉特征\n"
        "2. 给出判定等级：normal（正常）/ mild（轻度）/ moderate（中度）/ severe（重度）\n"
        "3. 列出支持判断的具体视觉依据\n"
        "4. 如果照片质量不足以准确判断，设置 need_retake=true 并说明原因\n\n"
        "严格以 JSON 格式输出：\n"
        '{"level": "normal|mild|moderate|severe", "confidence": 0.0-1.0, '
        '"evidence": ["特征1", "特征2"], "suggestion": "建议文字", '
        '"need_retake": false, "retake_reason": ""}\n\n'
        "重要提示：\n"
        "- 这只是筛查辅助，不构成医疗诊断\n"
        "- 如发现可能的严重病理问题，请在 suggestion 中建议就医\n"
        "- 保持客观、专业、谨慎的态度"
    ) % (
        issue["name_cn"],
        issue["definition"],
        user_info["gender"],
        user_info["age"],
        user_info["height"],
        user_info["weight"],
        issue["name_cn"],
    )

    content_parts.append({"type": "text", "text": prompt})

    body = {
        "model": "qwen-vl-max",
        "messages": [{"role": "user", "content": content_parts}],
        "max_tokens": 1000,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                QWEN_VL_URL,
                headers={
                    "Authorization": "Bearer %s" % settings.DASHSCOPE_API_KEY,
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
    except httpx.TimeoutException:
        logger.error("AI posture analysis request timed out")
        raise ServiceUnavailable("AI 分析超时，请稍后重试")
    except httpx.HTTPStatusError as e:
        logger.error(
            "AI posture analysis HTTP error: status=%d", e.response.status_code
        )
        raise ServiceUnavailable("AI 服务暂时不可用，请稍后重试")
    except Exception as e:
        logger.error("AI posture analysis unexpected error: %s", type(e).__name__)
        raise ServiceUnavailable("AI 分析失败，请稍后重试")

    # Content must be a string
    if not isinstance(content, str):
        logger.error(
            "AI posture analysis returned non-string content type: %s",
            type(content).__name__,
        )
        raise ServiceUnavailable("AI 分析结果格式异常")

    # Extract JSON from model response
    content = content.strip()

    # Try markdown code block extraction
    code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if code_block_match:
        content = code_block_match.group(1).strip()

    # If not starting with {, try to find JSON object
    if not content.startswith("{"):
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            content = json_match.group(0)

    try:
        raw_result = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        logger.error("AI posture analysis returned non-JSON content")
        raise ServiceUnavailable("AI 分析结果无法解析")

    # Top-level must be a JSON object (dict), not array/null/string/number
    if not isinstance(raw_result, dict):
        logger.error(
            "AI posture analysis returned non-object JSON: %s",
            type(raw_result).__name__,
        )
        raise ServiceUnavailable("AI 分析结果格式异常")

    # Validate against strict schema (strict=False allows JSON-native
    # coercion like int->float and str->enum; extra="forbid" still rejects
    # unexpected fields)
    try:
        validated = AIAnalysisResult.model_validate(raw_result, strict=False)
    except ValidationError as e:
        logger.error(
            "AI posture analysis schema validation failed: %d error(s)",
            len(e.errors()),
        )
        raise ServiceUnavailable("AI 分析结果未通过校验")

    # If model requests retake, the result is unreliable - do not save
    if validated.need_retake:
        logger.warning("AI posture analysis requested photo retake")
        raise ServiceUnavailable(
            "照片质量不足，请重新拍照：%s"
            % (validated.retake_reason or "请确保光线充足、角度正确")
        )

    return validated.model_dump(mode="json")
