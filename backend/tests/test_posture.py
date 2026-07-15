import pytest
from unittest.mock import patch, AsyncMock
from pydantic import ValidationError
from app.core.config import settings
from app.core.exceptions import ServiceUnavailable
from app.posture.models import PostureAssessment
from app.posture import knowledge
from app.posture.schemas import Source, SelfTestSchema, KnowledgeIssue
from sqlalchemy import select


@pytest.fixture
def photo_analysis_enabled(monkeypatch):
    monkeypatch.setattr(settings, "PHOTO_ANALYSIS_ENABLED", True)


async def _login_user(client, phone="13800138000"):
    await client.post("/api/v1/auth/send-code", json={"phone": phone})
    from tests.conftest import TestSession
    from app.auth.models import VerificationCode
    from sqlalchemy import select

    async with TestSession() as db:
        result = await db.execute(
            select(VerificationCode)
            .where(VerificationCode.phone == phone)
            .order_by(VerificationCode.created_at.desc())
        )
        code = result.scalar_one().code

    resp = await client.post(
        "/api/v1/auth/verify-login", json={"phone": phone, "code": code}
    )
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_list_issues(client):
    token = await _login_user(client)
    resp = await client.get(
        "/api/v1/posture/issues", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 26


@pytest.mark.asyncio
async def test_list_issues_by_category(client):
    token = await _login_user(client)
    resp = await client.get(
        "/api/v1/posture/issues?category=head_neck",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    for issue in resp.json():
        assert issue["category"] == "head_neck"


@pytest.mark.asyncio
async def test_get_issue_detail(client):
    token = await _login_user(client)
    resp = await client.get(
        "/api/v1/posture/issues/HN-01", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["name_cn"] == "头部前倾"


@pytest.mark.asyncio
async def test_self_assess(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "moderate"


@pytest.mark.asyncio
async def test_self_assess_negative(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "negative"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "normal"


@pytest.mark.asyncio
async def test_get_history(client):
    token = await _login_user(client)
    await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "negative"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.get(
        "/api/v1/posture/history", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_get_related(client):
    token = await _login_user(client)
    resp = await client.get(
        "/api/v1/posture/issues/HN-01/related",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) > 0


# --- Photo analysis gate tests ---


@pytest.fixture()
def _force_photo_disabled(monkeypatch):
    """Ensure PHOTO_ANALYSIS_ENABLED is False regardless of environment."""
    monkeypatch.setattr(settings, "PHOTO_ANALYSIS_ENABLED", False)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_force_photo_disabled")
async def test_photo_assess_returns_503_when_photo_disabled(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess/photo",
        json={"issue_id": "HN-01", "photo_keys": ["test/placeholder.jpg"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503
    assert resp.json() == {
        "detail": "照片分析在当前数据模式下未启用",
        "code": "photo_analysis_disabled",
    }


@pytest.mark.asyncio
@pytest.mark.usefixtures("_force_photo_disabled")
async def test_photo_assess_does_not_call_ai_when_disabled(client):
    token = await _login_user(client)
    with patch(
        "app.posture.ai_service.analyze_posture_photo", new_callable=AsyncMock
    ) as mock_ai:
        await client.post(
            "/api/v1/posture/assess/photo",
            json={"issue_id": "HN-01", "photo_keys": ["test/placeholder.jpg"]},
            headers={"Authorization": f"Bearer {token}"},
        )
    mock_ai.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_force_photo_disabled")
async def test_photo_assess_does_not_create_assessment_when_disabled(client):
    token = await _login_user(client)
    await client.post(
        "/api/v1/posture/assess/photo",
        json={"issue_id": "HN-01", "photo_keys": ["test/placeholder.jpg"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.get(
        "/api/v1/posture/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("_force_photo_disabled")
async def test_photo_assess_returns_401_when_unauthenticated(client):
    """Unauthenticated request must return 401, not 503 (auth before gate)."""
    resp = await client.post(
        "/api/v1/posture/assess/photo",
        json={"issue_id": "HN-01", "photo_keys": ["test/placeholder.jpg"]},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.usefixtures("_force_photo_disabled")
async def test_photo_assess_invalid_json_returns_503_when_disabled(client):
    """Authenticated + invalid JSON body + disabled -> 503, not 422."""
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess/photo",
        content=b"not valid json {{{",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 503
    data = resp.json()
    assert data["detail"] == "照片分析在当前数据模式下未启用"
    assert data["code"] == "photo_analysis_disabled"


@pytest.mark.asyncio
async def test_photo_assess_ai_failure_returns_503(client, photo_analysis_enabled):
    """When AI service fails, photo assessment returns 503 and saves no record."""
    token = await _login_user(client)
    with patch(
        "app.posture.ai_service.analyze_posture_photo",
        new_callable=AsyncMock,
        side_effect=ServiceUnavailable("AI service failed"),
    ):
        resp = await client.post(
            "/api/v1/posture/assess/photo",
            json={"issue_id": "HN-01", "photo_keys": ["fake-key.jpg"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 503

    # Verify no assessment was persisted
    resp = await client.get(
        "/api/v1/posture/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_photo_assess_need_retake_returns_503_without_saving(
    client, photo_analysis_enabled
):
    token = await _login_user(client)
    with patch(
        "app.posture.ai_service.analyze_posture_photo",
        new_callable=AsyncMock,
        side_effect=ServiceUnavailable("照片质量不足，请重新拍照"),
    ):
        resp = await client.post(
            "/api/v1/posture/assess/photo",
            json={"issue_id": "HN-01", "photo_keys": ["fake-key.jpg"]},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 503

    from tests.conftest import TestSession

    async with TestSession() as db:
        result = await db.execute(select(PostureAssessment))
        assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_photo_assess_mild_mapped_to_moderate(client, photo_analysis_enabled):
    """AI mild must be mapped to moderate for Flutter, not stored as mild or normal."""
    token = await _login_user(client)
    mock_ai_result = {
        "level": "mild",
        "confidence": 0.7,
        "evidence": ["slight forward head position"],
        "suggestion": "轻度前倾，建议关注",
        "need_retake": False,
        "retake_reason": "",
    }
    with patch(
        "app.posture.ai_service.analyze_posture_photo",
        new_callable=AsyncMock,
        return_value=mock_ai_result,
    ):
        resp = await client.post(
            "/api/v1/posture/assess/photo",
            json={"issue_id": "HN-01", "photo_keys": ["fake-key.jpg"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        # Flutter sees "moderate", not "mild" or "normal"
        assert resp.json()["result"] == "moderate"

    from tests.conftest import TestSession

    async with TestSession() as db:
        result = await db.execute(select(PostureAssessment))
        assessment = result.scalar_one()
        assert assessment.result == "moderate"
        assert assessment.ai_response["level"] == "mild"


# --- Response shape and serialization tests ---


@pytest.mark.asyncio
async def test_all_issues_serialize_through_detail_model(client):
    """All 26 knowledge entries must serialize through IssueDetail response model."""
    token = await _login_user(client)
    resp = await client.get(
        "/api/v1/posture/issues", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    issues = resp.json()
    assert len(issues) == 26

    for issue_summary in issues:
        detail_resp = await client.get(
            f"/api/v1/posture/issues/{issue_summary['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert detail_resp.status_code == 200, (
            f"Issue {issue_summary['id']} failed to serialize"
        )
        detail = detail_resp.json()
        # Verify Flutter-required fields are present
        assert "id" in detail
        assert "name_cn" in detail
        assert "name_en" in detail
        assert "category" in detail
        assert "aliases" in detail
        assert "definition" in detail
        assert "severity_levels" in detail
        assert "causes" in detail
        assert "self_tests" in detail
        assert "corrections" in detail
        assert "consequences" in detail
        assert "red_flags" in detail
        assert "related_issues" in detail


@pytest.mark.asyncio
async def test_list_response_shape_matches_flutter(client):
    """List response must have exactly the fields Flutter IssueSummary expects."""
    token = await _login_user(client)
    resp = await client.get(
        "/api/v1/posture/issues", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    for item in resp.json():
        assert set(item.keys()) == {
            "id",
            "name_cn",
            "category",
            "aliases",
            "definition",
        }


@pytest.mark.asyncio
async def test_detail_self_tests_shape(client):
    """Self tests in detail response must have Flutter SelfTest fields."""
    token = await _login_user(client)
    resp = await client.get(
        "/api/v1/posture/issues/HN-01",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    detail = resp.json()
    assert len(detail["self_tests"]) > 0
    for st in detail["self_tests"]:
        assert "name" in st
        assert "steps" in st
        assert isinstance(st["steps"], list)
        assert "positive_sign" in st
        assert "image_key" in st
        assert "tools_needed" in st


@pytest.mark.asyncio
async def test_history_response_shape(client):
    """History response must match Flutter AssessmentRecord fields."""
    token = await _login_user(client)
    # Create an assessment first
    await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.get(
        "/api/v1/posture/history", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    records = resp.json()
    assert len(records) >= 1
    for rec in records:
        assert set(rec.keys()) == {
            "id",
            "issue_id",
            "issue_name",
            "method",
            "result",
            "created_at",
        }


@pytest.mark.asyncio
async def test_assess_response_shape(client):
    """Self-assess response must match Flutter SelfAssessResult fields."""
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/assess",
        json={"issue_id": "HN-01", "test_index": 0, "answer": "positive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"id", "issue_id", "result", "suggestion"}


# --- Self-test content schema + structured source validation (Task 3) ---


def _valid_source() -> dict:
    return {
        "identifier": "https://example.org/guidelines/posture-screening",
        "type": "L1",
        "version": "2026-edition-1",
        "reviewed_at": "2026-07-11",
        "scope": "成人颈部体态筛查",
        "license": "CC-BY-4.0",
    }


def _valid_self_test() -> dict:
    return {
        "name": "靠墙站立测试",
        "steps": ["背靠墙站立", "后脑勺、上背、臀部贴墙"],
        "positive_sign": "后脑勺无法自然贴墙",
        "image_key": "assets/images/tests/hn01_wall_test.png",
        "tools_needed": "无",
        "preparation": "背靠平整墙面站立，脱鞋，臀部和上背贴墙。",
        "correct_posture": "自然放松，目视前方，后脑勺轻贴墙面",
        "common_errors": ["强行仰头让后脑勺贴墙"],
        "stop_conditions": ["出现头晕或颈部剧烈疼痛"],
        "safety_notes": ["动作轻柔，仅作筛查，不能替代医学诊断"],
        "content_version": "phase1-v1",
        "source": _valid_source(),
    }


def _valid_issue() -> dict:
    return {
        "id": "HN-01",
        "name_cn": "头部前倾",
        "name_en": "Forward Head Posture",
        "category": "head_neck",
        "aliases": ["乌龟颈"],
        "definition": "耳垂落于肩峰垂线前方",
        "severity_levels": ["轻度", "中度", "重度"],
        "causes": [{"type": "行为习惯", "desc": "长期低头看手机"}],
        "self_tests": [_valid_self_test()],
        "corrections": [{"type": "拉伸", "target_muscle": "枕下肌群"}],
        "consequences": [{"timeframe": "短期", "desc": "颈肩僵硬"}],
        "red_flags": ["伴手臂放射痛需就医"],
        "related_issues": [{"id": "HN-02", "weight": 0.9, "relation": "共存"}],
    }


def test_valid_structured_source_accepted():
    source = Source.model_validate(_valid_source())
    assert source.type.value == "L1"
    assert source.reviewed_at.isoformat() == "2026-07-11"


@pytest.mark.parametrize(
    "identifier",
    [
        "10.1016/j.math.2007.01.013",
        "DOI:10.1016/j.math.2007.01.013",
        "978-7-117-12345-6",
        "ISBN 9787117123456",
        "https://example.org/guidelines/posture-screening",
    ],
)
def test_source_identifier_accepts_verifiable_formats(identifier):
    data = _valid_source()
    data["identifier"] = identifier
    Source.model_validate(data)


def test_self_test_rejects_bare_string_source():
    st = _valid_self_test()
    st["source"] = "Magee DJ 2014"
    with pytest.raises(ValidationError):
        SelfTestSchema.model_validate(st)


def test_knowledge_issue_rejects_bare_string_source():
    issue = _valid_issue()
    issue["self_tests"][0]["source"] = "bare string reference"
    with pytest.raises(ValidationError):
        KnowledgeIssue.model_validate(issue)


@pytest.mark.parametrize("missing", ["identifier", "type", "version", "reviewed_at", "scope", "license"])
def test_source_rejects_missing_required_field(missing):
    data = _valid_source()
    del data[missing]
    with pytest.raises(ValidationError):
        Source.model_validate(data)


@pytest.mark.parametrize(
    "identifier",
    ["Magee DJ", "some book title", "not-a-valid-identifier", "10.1016", "ISBN-invalid"],
)
def test_source_rejects_malformed_identifier(identifier):
    data = _valid_source()
    data["identifier"] = identifier
    with pytest.raises(ValidationError):
        Source.model_validate(data)


def test_source_rejects_vague_version():
    data = _valid_source()
    data["version"] = "最新版"
    with pytest.raises(ValidationError):
        Source.model_validate(data)


def test_source_rejects_fabricated_license():
    data = _valid_source()
    data["license"] = "CC-BY-4.0-internal-summary"
    with pytest.raises(ValidationError):
        Source.model_validate(data)


def test_self_test_optional_new_fields_default_empty():
    st = SelfTestSchema.model_validate(
        {
            "name": "t",
            "steps": ["a"],
            "positive_sign": "p",
            "image_key": "k",
            "tools_needed": "无",
        }
    )
    assert st.correct_posture == ""
    assert st.common_errors == []
    assert st.stop_conditions == []
    assert st.safety_notes == []
    assert st.preparation == ""
    assert st.content_version is None
    assert st.source is None


def test_knowledge_issue_validates_without_new_fields():
    issue = _valid_issue()
    issue["self_tests"][0] = {
        "name": "t",
        "steps": ["a"],
        "positive_sign": "p",
        "image_key": "k",
        "tools_needed": "无",
    }
    KnowledgeIssue.model_validate(issue)


def test_load_issues_blocks_invalid_source():
    issue = _valid_issue()
    issue["self_tests"][0]["source"] = {
        "identifier": "not-a-valid-identifier",
        "type": "L1",
        "version": "2026-v1",
        "reviewed_at": "2026-07-11",
        "scope": "成人筛查",
        "license": "CC-BY-4.0",
    }
    with pytest.raises(RuntimeError):
        knowledge.load_issues([issue])


def test_load_all_blocks_invalid_source_via_loader(monkeypatch):
    import app.posture.knowledge as k

    issue = _valid_issue()
    issue["self_tests"][0]["source"] = "bare string"
    monkeypatch.setattr(k, "_read_raw_issues", lambda: [issue])
    monkeypatch.setattr(k, "_ISSUES_CACHE", None)
    with pytest.raises(RuntimeError):
        k._load_all()


def test_all_shipped_issues_validate_against_schema():
    issues = knowledge.get_all_issues()
    assert len(issues) == 26
    for issue in issues:
        knowledge.validate_issue(issue)


@pytest.mark.asyncio
async def test_detail_self_tests_expose_new_schema_fields(client):
    token = await _login_user(client)
    resp = await client.get(
        "/api/v1/posture/issues/HN-01",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    for st in resp.json()["self_tests"]:
        assert "correct_posture" in st
        assert "common_errors" in st
        assert "stop_conditions" in st
        assert "safety_notes" in st
        assert "source" in st


# --- Conditional quality gate: legacy backward-compat + extended entry gate ---


def _complete_extended_self_test() -> dict:
    """A fully-populated extended self-test that must pass the gate."""
    return {
        "name": "靠墙站立测试",
        "steps": ["背靠墙站立", "后脑勺、上背、臀部贴墙"],
        "positive_sign": "后脑勺无法自然贴墙",
        "image_key": "assets/images/tests/hn01_wall_test.png",
        "tools_needed": "无",
        "preparation": "背靠平整墙面站立，臀部和上背贴墙。",
        "correct_posture": "自然收下巴，目视前方，后脑勺轻贴墙面",
        "common_errors": ["强行仰头让后脑勺贴墙"],
        "stop_conditions": ["出现手臂放射痛或麻木"],
        "safety_notes": ["动作轻柔，仅作筛查"],
        "content_version": "phase1-v1",
        "source": {
            "identifier": "10.54393/pbmj.v7i10.1141",
            "type": "L5",
            "version": "2024",
            "reviewed_at": "2026-07-15",
            "scope": "成人头部前倾体态筛查",
            "license": "CC-BY-4.0",
        },
    }


def test_legacy_entry_loads_without_extended_fields():
    """A minimal entry with none of the extended fields loads fine (legacy)."""
    st = SelfTestSchema.model_validate(
        {
            "name": "t",
            "steps": ["a"],
            "positive_sign": "p",
            "image_key": "k",
            "tools_needed": "无",
        }
    )
    assert st.source is None
    assert st.content_version is None


def test_complete_extended_entry_passes_gate():
    st = SelfTestSchema.model_validate(_complete_extended_self_test())
    assert st.content_version == "phase1-v1"
    assert st.source is not None
    assert st.source.identifier == "10.54393/pbmj.v7i10.1141"


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("preparation", ""),
        ("preparation", "   "),
        ("correct_posture", ""),
        ("correct_posture", "   "),
        ("common_errors", []),
        ("common_errors", ["", "  "]),
        ("stop_conditions", []),
        ("stop_conditions", ["  "]),
        ("content_version", None),
        ("content_version", ""),
        ("source", None),
    ],
)
def test_extended_entry_missing_required_field_fails(field, bad_value):
    data = _complete_extended_self_test()
    data[field] = bad_value
    with pytest.raises(ValidationError):
        SelfTestSchema.model_validate(data)


def test_bare_string_source_rejected_in_extended_entry():
    data = _complete_extended_self_test()
    data["source"] = "Magee DJ 2014"
    with pytest.raises(ValidationError):
        SelfTestSchema.model_validate(data)


def test_gate_triggers_when_only_one_extended_field_present():
    """Opting into any single extended field activates the gate."""
    data = {
        "name": "t",
        "steps": ["a"],
        "positive_sign": "p",
        "image_key": "k",
        "tools_needed": "无",
        "preparation": "仅写了准备，但其余扩展字段缺失",
    }
    with pytest.raises(ValidationError):
        SelfTestSchema.model_validate(data)


def test_gate_does_not_trigger_for_legacy_entry_with_only_defaults():
    """Empty/whitespace-only extended fields keep an entry legacy."""
    data = {
        "name": "t",
        "steps": ["a"],
        "positive_sign": "p",
        "image_key": "k",
        "tools_needed": "无",
        "correct_posture": "   ",
        "common_errors": [],
        "stop_conditions": [],
        "content_version": None,
        "source": None,
    }
    st = SelfTestSchema.model_validate(data)
    assert st.source is None


def test_load_issues_blocks_incomplete_extended_entry():
    """The loader fails loudly when an extended self-test is incomplete."""
    issue = _valid_issue()
    issue["self_tests"][0] = {
        "name": "靠墙站立测试",
        "steps": ["背靠墙站立"],
        "positive_sign": "后脑勺无法贴墙",
        "image_key": "k",
        "tools_needed": "无",
        "correct_posture": "收下巴，后脑勺轻贴墙",
        # missing common_errors / stop_conditions / content_version / source
    }
    with pytest.raises(RuntimeError):
        knowledge.load_issues([issue])


# --- Shipped catalog acceptance (Phase 1 Task 3) ---


def _is_extended_self_test(st: dict) -> bool:
    """Mirror of the schema gate: any extended field present opts into the set."""
    return (
        bool((st.get("preparation") or "").strip())
        or bool((st.get("correct_posture") or "").strip())
        or bool(st.get("common_errors"))
        or bool(st.get("stop_conditions"))
        or bool((st.get("content_version") or "").strip())
        or st.get("source") is not None
    )


def test_shipped_catalog_has_complete_extended_self_tests():
    """Shipped catalog: the 5 Phase-1 issues each carry a fully-complete
    extended self_test, and the whole catalog (re)loads without errors."""
    raw = knowledge._read_raw_issues()
    knowledge.load_issues(raw)  # proves shipped data validates with no errors

    by_id = {i["id"]: i for i in raw}

    # 驼背 / Hyperkyphosis is located by name_en (not a stable id in the spec)
    hyperkyphosis_id = next(
        i["id"] for i in raw if i["name_en"] == "Hyperkyphosis"
    )

    targets = [
        ("HN-01", "HN-01"),
        ("ST-04", "ST-04"),
        ("PS-13", "PS-13"),
        ("LL-21", "LL-21"),
        ("Hyperkyphosis", hyperkyphosis_id),
    ]

    for label, issue_id in targets:
        assert issue_id in by_id, f"shipped catalog missing issue {label} ({issue_id})"
        extended_tests = [
            st for st in by_id[issue_id]["self_tests"] if _is_extended_self_test(st)
        ]
        assert extended_tests, (
            f"{label} ({issue_id}) must ship at least one extended self_test"
        )
        for st in extended_tests:
            assert (st.get("preparation") or "").strip(), (
                f"{label} extended self_test has empty preparation"
            )
            assert (st.get("correct_posture") or "").strip(), (
                f"{label} extended self_test has empty correct_posture"
            )
            assert any((e or "").strip() for e in st["common_errors"]), (
                f"{label} extended self_test common_errors must have >=1 non-empty"
            )
            assert any((e or "").strip() for e in st["stop_conditions"]), (
                f"{label} extended self_test stop_conditions must have >=1 non-empty"
            )
            assert (st.get("content_version") or "").strip(), (
                f"{label} extended self_test has empty content_version"
            )
            src = st.get("source")
            assert isinstance(src, dict) and src is not None, (
                f"{label} extended self_test source must be structured (not a bare string)"
            )
            assert (src.get("license") or "").strip(), (
                f"{label} extended self_test source.license must be non-empty"
            )
