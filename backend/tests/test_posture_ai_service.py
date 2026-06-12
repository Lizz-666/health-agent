"""Tests for posture AI service: validate that AI failures never produce normal results."""

import json
import pytest
import httpx
from unittest.mock import patch, AsyncMock
from pydantic import ValidationError

from app.posture.ai_service import analyze_posture_photo
from app.posture.schemas import AIAnalysisResult
from app.core.exceptions import ServiceUnavailable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_AI_JSON = json.dumps(
    {
        "level": "moderate",
        "confidence": 0.85,
        "evidence": ["shoulder angle > 15 degrees"],
        "suggestion": "建议进行纠正训练",
        "need_retake": False,
        "retake_reason": "",
    }
)


def _fake_dashscope_response(content_text, status_code=200):
    """Build a fake httpx.Response mimicking DashScope chat/completions."""
    body = {"choices": [{"message": {"content": content_text}}]}
    return httpx.Response(
        status_code=status_code,
        json=body,
        request=httpx.Request("POST", "https://fake"),
    )


def _fake_http_error_response(status_code=500):
    """Build a response whose raise_for_status() will throw."""
    return httpx.Response(
        status_code=status_code,
        text="error",
        request=httpx.Request("POST", "https://fake"),
    )


def _mock_httpx_client(response=None, side_effect=None):
    """Return a patched httpx.AsyncClient context-manager."""
    ctx = patch("app.posture.ai_service.httpx.AsyncClient")
    mock_cls = ctx.start()
    instance = AsyncMock()
    if side_effect:
        instance.post.side_effect = side_effect
    else:
        instance.post.return_value = response
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=False)
    mock_cls.return_value = instance
    return ctx


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def patch_deps():
    """Patch generate_signed_url and _get_user_info so no real calls happen."""
    with (
        patch(
            "app.posture.ai_service.generate_signed_url",
            return_value="https://fake/photo.jpg",
        ),
        patch(
            "app.posture.ai_service._get_user_info",
            new_callable=AsyncMock,
            return_value={
                "gender": "男",
                "age": "30",
                "height": "175cm",
                "weight": "70kg",
            },
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# Schema unit tests
# ---------------------------------------------------------------------------


class TestAIAnalysisResultSchema:
    def test_valid_result_accepted(self):
        r = AIAnalysisResult.model_validate_json(
            json.dumps({
                "level": "moderate",
                "confidence": 0.85,
                "evidence": ["visible forward head"],
                "suggestion": "建议纠正训练",
                "need_retake": False,
                "retake_reason": "",
            }),
        )
        assert r.level.value == "moderate"
        assert r.confidence == 0.85

    def test_all_valid_levels_accepted(self):
        for lvl in ("normal", "mild", "moderate", "severe"):
            r = AIAnalysisResult.model_validate_json(
                json.dumps({
                    "level": lvl,
                    "confidence": 0.5,
                    "evidence": ["x"],
                    "suggestion": "",
                    "need_retake": False,
                    "retake_reason": "",
                }),
            )
            assert r.level.value == lvl

    def test_missing_level_rejected(self):
        with pytest.raises(ValidationError):
            AIAnalysisResult.model_validate_json(
                json.dumps({
                    "confidence": 0.8,
                    "evidence": [],
                    "suggestion": "",
                    "need_retake": False,
                    "retake_reason": "",
                }),
            )

    def test_invalid_level_enum_rejected(self):
        with pytest.raises(ValidationError):
            AIAnalysisResult.model_validate_json(
                json.dumps({
                    "level": "bad_value",
                    "confidence": 0.8,
                    "evidence": [],
                    "suggestion": "",
                    "need_retake": False,
                    "retake_reason": "",
                }),
            )

    def test_confidence_above_1_rejected(self):
        with pytest.raises(ValidationError):
            AIAnalysisResult.model_validate_json(
                json.dumps({
                    "level": "normal",
                    "confidence": 1.5,
                    "evidence": [],
                    "suggestion": "",
                    "need_retake": False,
                    "retake_reason": "",
                }),
            )

    def test_missing_evidence_rejected(self):
        with pytest.raises(ValidationError):
            AIAnalysisResult.model_validate_json(
                json.dumps({
                    "level": "mild",
                    "confidence": 0.5,
                    "suggestion": "",
                    "need_retake": False,
                    "retake_reason": "",
                }),
            )

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            AIAnalysisResult.model_validate_json(
                json.dumps({
                    "level": "normal",
                    "confidence": 0.5,
                    "evidence": [],
                    "suggestion": "",
                    "need_retake": False,
                    "retake_reason": "",
                    "unexpected_field": "oops",
                }),
            )

    def test_model_dump_json_produces_plain_values(self):
        r = AIAnalysisResult.model_validate_json(
            json.dumps({
                "level": "moderate",
                "confidence": 0.85,
                "evidence": ["x"],
                "suggestion": "ok",
                "need_retake": False,
                "retake_reason": "",
            }),
        )
        d = r.model_dump(mode="json")
        assert isinstance(d["level"], str)
        assert d["level"] == "moderate"
        # Must not be an Enum instance
        assert type(d["level"]) is str

    def test_integer_confidence_accepted_as_json_number(self):
        result = AIAnalysisResult.model_validate_json(
            json.dumps({
                "level": "normal",
                "confidence": 1,
                "evidence": ["x"],
                "suggestion": "",
                "need_retake": False,
                "retake_reason": "",
            })
        )
        assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# AI service failure tests (mocked HTTP, no real DashScope)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAnalyzePosturePhotoFailures:
    async def test_timeout_raises_503(self, mock_db, patch_deps):
        ctx = _mock_httpx_client(side_effect=httpx.TimeoutException("timeout"))
        try:
            with pytest.raises(ServiceUnavailable):
                await analyze_posture_photo("HN-01", ["p.jpg"], "u1", mock_db)
        finally:
            ctx.stop()

    async def test_http_500_raises_503(self, mock_db, patch_deps):
        ctx = _mock_httpx_client(response=_fake_http_error_response(500))
        try:
            with pytest.raises(ServiceUnavailable):
                await analyze_posture_photo("HN-01", ["p.jpg"], "u1", mock_db)
        finally:
            ctx.stop()

    async def test_http_429_raises_503(self, mock_db, patch_deps):
        ctx = _mock_httpx_client(response=_fake_http_error_response(429))
        try:
            with pytest.raises(ServiceUnavailable):
                await analyze_posture_photo("HN-01", ["p.jpg"], "u1", mock_db)
        finally:
            ctx.stop()

    async def test_non_json_text_raises_503(self, mock_db, patch_deps):
        ctx = _mock_httpx_client(
            response=_fake_dashscope_response("I cannot analyze this image."),
        )
        try:
            with pytest.raises(ServiceUnavailable):
                await analyze_posture_photo("HN-01", ["p.jpg"], "u1", mock_db)
        finally:
            ctx.stop()

    async def test_missing_level_field_raises_503(self, mock_db, patch_deps):
        ctx = _mock_httpx_client(
            response=_fake_dashscope_response(
                json.dumps(
                    {
                        "confidence": 0.8,
                        "evidence": ["x"],
                        "suggestion": "",
                        "need_retake": False,
                    }
                )
            )
        )
        try:
            with pytest.raises(ServiceUnavailable):
                await analyze_posture_photo("HN-01", ["p.jpg"], "u1", mock_db)
        finally:
            ctx.stop()

    async def test_invalid_level_enum_raises_503(self, mock_db, patch_deps):
        ctx = _mock_httpx_client(
            response=_fake_dashscope_response(
                json.dumps(
                    {
                        "level": "very_bad",
                        "confidence": 0.8,
                        "evidence": ["x"],
                        "suggestion": "",
                        "need_retake": False,
                        "retake_reason": "",
                    }
                )
            )
        )
        try:
            with pytest.raises(ServiceUnavailable):
                await analyze_posture_photo("HN-01", ["p.jpg"], "u1", mock_db)
        finally:
            ctx.stop()

    async def test_invalid_issue_id_raises_503(self, mock_db, patch_deps):
        with pytest.raises(ServiceUnavailable):
            await analyze_posture_photo("NONEXIST-99", ["p.jpg"], "u1", mock_db)

    async def test_confidence_above_1_raises_503(self, mock_db, patch_deps):
        ctx = _mock_httpx_client(
            response=_fake_dashscope_response(
                json.dumps(
                    {
                        "level": "mild",
                        "confidence": 2.0,
                        "evidence": ["x"],
                        "suggestion": "",
                        "need_retake": False,
                        "retake_reason": "",
                    }
                )
            )
        )
        try:
            with pytest.raises(ServiceUnavailable):
                await analyze_posture_photo("HN-01", ["p.jpg"], "u1", mock_db)
        finally:
            ctx.stop()

    # -- F1: need_retake=true must return 503 --

    async def test_need_retake_true_raises_503(self, mock_db, patch_deps):
        """Model says photo needs retake -> unreliable result, must not save."""
        retake_json = json.dumps(
            {
                "level": "moderate",
                "confidence": 0.3,
                "evidence": ["blurry image"],
                "suggestion": "请重新拍照",
                "need_retake": True,
                "retake_reason": "照片角度不足",
            }
        )
        ctx = _mock_httpx_client(response=_fake_dashscope_response(retake_json))
        try:
            with pytest.raises(ServiceUnavailable):
                await analyze_posture_photo("HN-01", ["p.jpg"], "u1", mock_db)
        finally:
            ctx.stop()

    # -- F2: content type and top-level JSON type validation --

    async def test_non_string_content_raises_503(self, mock_db, patch_deps):
        """If model returns content that is not a string (e.g. list), must 503."""
        body = {"choices": [{"message": {"content": ["not", "a", "string"]}}]}
        resp = httpx.Response(
            200, json=body, request=httpx.Request("POST", "https://f")
        )
        ctx = _mock_httpx_client(response=resp)
        try:
            with pytest.raises(ServiceUnavailable):
                await analyze_posture_photo("HN-01", ["p.jpg"], "u1", mock_db)
        finally:
            ctx.stop()

    async def test_null_content_raises_503(self, mock_db, patch_deps):
        """If model returns null content, must 503."""
        body = {"choices": [{"message": {"content": None}}]}
        resp = httpx.Response(
            200, json=body, request=httpx.Request("POST", "https://f")
        )
        ctx = _mock_httpx_client(response=resp)
        try:
            with pytest.raises(ServiceUnavailable):
                await analyze_posture_photo("HN-01", ["p.jpg"], "u1", mock_db)
        finally:
            ctx.stop()

    async def test_json_array_toplevel_raises_503(self, mock_db, patch_deps):
        """Valid JSON but top-level is array, not object."""
        ctx = _mock_httpx_client(
            response=_fake_dashscope_response('[{"level": "normal"}]'),
        )
        try:
            with pytest.raises(ServiceUnavailable):
                await analyze_posture_photo("HN-01", ["p.jpg"], "u1", mock_db)
        finally:
            ctx.stop()

    async def test_json_null_toplevel_raises_503(self, mock_db, patch_deps):
        """Valid JSON but top-level is null."""
        ctx = _mock_httpx_client(
            response=_fake_dashscope_response("null"),
        )
        try:
            with pytest.raises(ServiceUnavailable):
                await analyze_posture_photo("HN-01", ["p.jpg"], "u1", mock_db)
        finally:
            ctx.stop()

    async def test_json_string_toplevel_raises_503(self, mock_db, patch_deps):
        """Valid JSON but top-level is a bare string."""
        ctx = _mock_httpx_client(
            response=_fake_dashscope_response('"just a string"'),
        )
        try:
            with pytest.raises(ServiceUnavailable):
                await analyze_posture_photo("HN-01", ["p.jpg"], "u1", mock_db)
        finally:
            ctx.stop()

    async def test_extra_field_in_ai_output_raises_503(self, mock_db, patch_deps):
        """extra=forbid: unexpected field must reject."""
        ctx = _mock_httpx_client(
            response=_fake_dashscope_response(
                json.dumps(
                    {
                        "level": "normal",
                        "confidence": 0.5,
                        "evidence": ["x"],
                        "suggestion": "",
                        "need_retake": False,
                        "retake_reason": "",
                        "hallucinated_field": True,
                    }
                )
            )
        )
        try:
            with pytest.raises(ServiceUnavailable):
                await analyze_posture_photo("HN-01", ["p.jpg"], "u1", mock_db)
        finally:
            ctx.stop()

    # -- valid responses --

    async def test_valid_response_returns_dict(self, mock_db, patch_deps):
        ctx = _mock_httpx_client(response=_fake_dashscope_response(VALID_AI_JSON))
        try:
            result = await analyze_posture_photo("HN-01", ["p.jpg"], "u1", mock_db)
            assert result["level"] == "moderate"
            assert result["confidence"] == 0.85
            assert isinstance(result["evidence"], list)
            # level must be a plain str, not Enum
            assert type(result["level"]) is str
        finally:
            ctx.stop()

    async def test_valid_response_in_markdown_block(self, mock_db, patch_deps):
        wrapped = "```json\n" + VALID_AI_JSON + "\n```"
        ctx = _mock_httpx_client(response=_fake_dashscope_response(wrapped))
        try:
            result = await analyze_posture_photo("HN-01", ["p.jpg"], "u1", mock_db)
            assert result["level"] == "moderate"
        finally:
            ctx.stop()
