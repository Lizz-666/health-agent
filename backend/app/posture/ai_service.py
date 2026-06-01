import json
import logging
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import settings
from app.posture.knowledge import get_issue_by_id
from app.upload.service import generate_signed_url
from app.auth.models import User
from uuid import UUID

logger = logging.getLogger(__name__)

QWEN_VL_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


async def _get_user_info(db: AsyncSession, user_id: str) -> dict:
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user:
        return {
            "gender": user.gender or "未知",
            "age": user.age or "未知",
            "height": f"{user.height}cm" if user.height else "未知",
            "weight": f"{user.weight}kg" if user.weight else "未知",
        }
    return {"gender": "未知", "age": "未知", "height": "未知", "weight": "未知"}


async def analyze_posture_photo(
    issue_id: str,
    photo_keys: list[str],
    user_id: str,
    db: AsyncSession,
) -> dict:
    issue = get_issue_by_id(issue_id)
    if not issue:
        return {"level": "normal", "confidence": 0, "evidence": [], "suggestion": "问题不存在", "need_retake": False}

    signed_urls = [generate_signed_url(key) for key in photo_keys]
    user_info = await _get_user_info(db, user_id)

    content_parts = []
    for url in signed_urls:
        content_parts.append({"type": "image_url", "image_url": {"url": url}})

    prompt = f"""你是一位专业的运动康复评估师，具备丰富的体态评估经验。

当前评估问题：{issue['name_cn']}（{issue['definition']}）

用户信息：
- 性别：{user_info['gender']}
- 年龄：{user_info['age']}
- 身高：{user_info['height']}
- 体重：{user_info['weight']}

请分析用户上传的照片，完成以下任务：

1. 识别照片中与"{issue['name_cn']}"相关的体征
2. 给出判定等级：normal（正常）/ mild（轻度）/ moderate（中度）/ severe（重度）
3. 给出判定依据（具体哪些视觉特征支持你的判断）
4. 如果照片角度、清晰度不足以准确判断，明确说明并建议重拍

请以 JSON 格式输出：
{{"level": "normal|mild|moderate|severe", "confidence": 0.0-1.0, "evidence": ["特征1", "特征2"], "suggestion": "建议文字", "need_retake": false, "retake_reason": ""}}

重要提示：
- 你的分析仅供参考，不构成医疗诊断
- 如发现可能的严重病理问题，请在 suggestion 中建议用户就医
- 保持客观、专业、谨慎的态度"""

    content_parts.append({"type": "text", "text": prompt})

    body = {
        "model": "qwen-vl-max",
        "messages": [{"role": "user", "content": content_parts}],
        "max_tokens": 1000,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            QWEN_VL_URL,
            headers={
                "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]

    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("\n", 1)[0]
        if content.startswith("json"):
            content = content[4:]

    try:
        ai_result = json.loads(content)
    except json.JSONDecodeError:
        logger.error(f"AI response parse error: {content[:200]}")
        ai_result = {"level": "normal", "confidence": 0, "evidence": [], "suggestion": "AI 分析结果解析失败，建议重新尝试", "need_retake": False}

    ai_result.setdefault("level", "normal")
    ai_result.setdefault("confidence", 0)
    ai_result.setdefault("evidence", [])
    ai_result.setdefault("suggestion", "")
    ai_result.setdefault("need_retake", False)
    return ai_result
