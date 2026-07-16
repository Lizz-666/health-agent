import re
from typing import List, Optional
from enum import Enum
from datetime import date, datetime, timedelta, timezone
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PostureLevel(str, Enum):
    normal = "normal"
    mild = "mild"
    moderate = "moderate"
    severe = "severe"


class EvidenceLevel(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"


# --- Structured source provenance ---

_DOI_RE = re.compile(r"^(?:doi:\s*)?10\.\d{4,9}/\S+$", re.IGNORECASE)
_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_VAGUE_VERSIONS = {"最新版", "新版", "最新", "latest", "latest edition"}


def _is_valid_isbn(value: str) -> bool:
    raw = re.sub(r"^isbn[-:]?\s*", "", value, flags=re.IGNORECASE)
    core = raw.replace("-", "").replace(" ", "")
    if len(core) == 10 and re.fullmatch(r"\d{9}[\dXx]", core):
        return True
    if len(core) == 13 and core.isdigit() and core.startswith(("978", "979")):
        return True
    return False


class Source(BaseModel):
    """结构化来源对象：仅接受可验证的 DOI / ISBN / URL，拒绝裸字符串与模糊书名。"""

    identifier: str = Field(
        ..., description="可验证来源标识符：DOI、ISBN 或官方指南 URL"
    )
    type: EvidenceLevel = Field(
        ...,
        description="引用层级（L1 机构指南 / L2 教科书 / L3 综述 / L4 RCT / L5 横断面）",
    )
    version: str = Field(
        ..., description="来源具体版本（版次/年份），不接受‘最新版’等模糊表述"
    )
    reviewed_at: date = Field(..., description="内容核验日期")
    scope: str = Field(..., description="适用范围，如‘成人颈部体态筛查’")
    license: str = Field(
        ..., description="内容引用与再分发许可；记录真实许可，不得虚构"
    )

    @field_validator("identifier")
    @classmethod
    def _validate_identifier(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("identifier 不能为空")
        if not (_DOI_RE.match(v) or _is_valid_isbn(v) or _URL_RE.match(v)):
            raise ValueError(
                "identifier 必须是合法的 DOI、ISBN 或 URL，不接受模糊书名字符串"
            )
        return v

    @field_validator("version")
    @classmethod
    def _validate_version(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("version 不能为空")
        if v.lower() in _VAGUE_VERSIONS:
            raise ValueError("version 不得使用模糊表述（如‘最新版’/‘latest’）")
        return v

    @field_validator("scope")
    @classmethod
    def _validate_scope(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("scope 不能为空")
        return v

    @field_validator("license")
    @classmethod
    def _validate_license(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("license 不能为空")
        if "internal-summary" in v.lower():
            raise ValueError("license 不得使用虚构许可名称（如 *-internal-summary）")
        return v


# --- Nested structured models for IssueDetail ---


class Cause(BaseModel):
    type: str
    desc: str


class SelfTestSchema(BaseModel):
    name: str
    steps: List[str]
    positive_sign: str
    image_key: str
    tools_needed: str
    preparation: str = ""
    correct_posture: str = ""
    common_errors: List[str] = Field(default_factory=list)
    stop_conditions: List[str] = Field(default_factory=list)
    safety_notes: List[str] = Field(default_factory=list)
    content_version: Optional[str] = None
    source: Optional[Source] = None

    @model_validator(mode="after")
    def _enforce_extended_quality_gate(self):
        # An entry "opts into" the extended content set when ANY of the
        # extended fields is present/non-empty. Legacy entries (all of these
        # absent/empty) load with no extra requirements.
        extended = (
            bool(self.preparation and self.preparation.strip())
            or bool(self.correct_posture and self.correct_posture.strip())
            or len(self.common_errors) > 0
            or len(self.stop_conditions) > 0
            or bool(self.content_version and self.content_version.strip())
            or self.source is not None
        )
        if not extended:
            return self
        # Extended entries must be complete and source-backed; reject loudly.
        if not (self.preparation and self.preparation.strip()):
            raise ValueError(
                "扩展条目（extended self_test）必须提供 preparation（测试前准备说明）"
            )
        if not (self.correct_posture and self.correct_posture.strip()):
            raise ValueError(
                "扩展条目（extended self_test）必须提供 correct_posture（正确姿势说明）"
            )
        if not any(e and str(e).strip() for e in self.common_errors):
            raise ValueError("扩展条目 common_errors 必须至少含 1 条非空项")
        if not any(e and str(e).strip() for e in self.stop_conditions):
            raise ValueError("扩展条目 stop_conditions 必须至少含 1 条非空项")
        if not (self.content_version and self.content_version.strip()):
            raise ValueError("扩展条目必须提供 content_version")
        if self.source is None:
            raise ValueError("扩展条目必须提供结构化 source（不接受裸字符串）")
        return self


class Correction(BaseModel):
    type: str
    target_muscle: Optional[str] = None
    method: Optional[str] = None
    freq: Optional[str] = None
    desc: Optional[str] = None


class Consequence(BaseModel):
    timeframe: str
    desc: str


class RelatedIssueRef(BaseModel):
    id: str
    weight: float
    relation: str


class KnowledgeIssue(BaseModel):
    """知识库加载校验契约：加载时校验每条问题，含每个自测的结构化 source。"""

    id: str
    name_cn: str
    name_en: str
    category: str
    aliases: List[str]
    definition: str
    severity_levels: List[str]
    causes: List[Cause]
    self_tests: List[SelfTestSchema]
    corrections: List[Correction]
    consequences: List[Consequence]
    red_flags: List[str]
    related_issues: List[RelatedIssueRef]

    model_config = ConfigDict(extra="ignore")


# --- Response models ---


class IssueSummary(BaseModel):
    id: str
    name_cn: str
    category: str
    aliases: List[str]
    definition: str


class IssueDetail(BaseModel):
    id: str
    name_cn: str
    name_en: str
    category: str
    aliases: List[str]
    definition: str
    severity_levels: List[str]
    causes: List[Cause]
    self_tests: List[SelfTestSchema]
    corrections: List[Correction]
    consequences: List[Consequence]
    red_flags: List[str]
    related_issues: List[RelatedIssueRef]


class RelatedIssue(BaseModel):
    id: str
    name_cn: str
    weight: float
    relation: str


# --- AI analysis schema ---


class AIAnalysisResult(BaseModel):
    """Strict schema for AI model output. Rejects missing or invalid fields."""

    level: PostureLevel
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: List[str]
    suggestion: str
    need_retake: bool
    retake_reason: str = ""

    model_config = ConfigDict(strict=True, extra="forbid")


# --- Request models ---


class SelfAssessRequest(BaseModel):
    issue_id: str
    test_index: int = 0
    answer: str  # "positive" | "negative" | "uncertain"


class PhotoAssessRequest(BaseModel):
    issue_id: str
    photo_keys: List[str]


# --- Response models for assessment ---


class SelfAssessResponse(BaseModel):
    id: str
    issue_id: str
    result: str
    suggestion: str


class AssessmentRecord(BaseModel):
    id: str
    issue_id: str
    issue_name: str
    method: str
    result: str
    created_at: datetime


# --- Safety signal request/response models (Task 6.5, spec §12.2) ---


class SignalType(str, Enum):
    pain = "pain"
    numbness = "numbness"
    weakness = "weakness"
    dizziness = "dizziness"
    acute_trauma = "acute_trauma"
    other = "other"


class BodyRegion(str, Enum):
    head_neck = "head_neck"
    cervical = "cervical"
    upper_back = "upper_back"
    thoracic = "thoracic"
    lower_back = "lower_back"
    shoulder_thorax = "shoulder_thorax"
    pelvis_spine = "pelvis_spine"
    lower_limb = "lower_limb"
    compound = "compound"


class SeverityHint(str, Enum):
    mild = "mild"
    moderate = "moderate"
    severe = "severe"


class SafetySignalRequest(BaseModel):
    # spec §12.2 / §12.5: reject unknown fields and guard DB column lengths /
    # implausible timestamps before any write (malicious/ambiguous input case).
    model_config = ConfigDict(extra="forbid")

    signal_type: SignalType  # enum enforces DB String(30) value set
    body_region: Optional[BodyRegion] = None  # enum enforces DB String(30)
    related_issue_id: Optional[str] = Field(default=None, max_length=20)
    severity_hint: Optional[SeverityHint] = None  # enum enforces DB String(20)
    reported_at: Optional[datetime] = None
    idempotency_key: str = Field(..., min_length=1, max_length=64)

    @field_validator("idempotency_key")
    @classmethod
    def _reject_blank_idempotency_key(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("idempotency_key 不能为空白")
        return v

    @field_validator("reported_at")
    @classmethod
    def _reported_at_must_be_plausible(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return v
        now = datetime.now(timezone.utc)
        aware = v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)
        # Allow a tiny clock-skew tolerance but reject future timestamps.
        if aware > now + timedelta(seconds=5):
            raise ValueError("reported_at 不能晚于当前时间")
        if aware < now - timedelta(days=365):
            raise ValueError("reported_at 不能早于一年前")
        return v


class RiskClassificationModel(BaseModel):
    risk_tier: str
    risk_version: str
    rule_id: str
    reason: str
    sources: List[dict] = Field(default_factory=list)


class SafetySignalResponse(BaseModel):
    signal_id: str
    status: str  # "recorded" | "deduplicated"
    lifecycle: str  # "active" | "resolved"
    risk_tier: str
    risk_version: str
    invalidates_until: datetime
    classification: RiskClassificationModel
