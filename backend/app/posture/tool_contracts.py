"""Typed Tool business I/O contracts (spec §10.0-§10.8, plan Task 7).

This module defines constrained Tool business inputs and typed outputs.
Existing REST response models are reused wherever the contracts are identical;
``SelfTestGuide`` and the richer ``PhotoAssessmentResult`` are Tool-specific.
The photo REST route retains its legacy four-field response model while direct
Tool callers receive the validated structured analysis fields from spec §10.4.

Design decision (Task 7 D2): shared outputs are not redeclared here. A Tool
that returns ``IssueDetail`` / ``PostureProfileResponse`` /
``PrioritySuggestionsResponse`` / ``ConfirmedGoalsResponse`` /
``SafetySignalResponse`` imports it directly from ``schemas``. Inputs that
already exist in ``schemas`` (``GoalInput``) are re-exported so Tools have a
single contract import surface.
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated, List, Optional, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.posture.schemas import (
    BodyRegion,
    ConfirmedGoalsResponse,
    GoalInput,
    IssueDetail,
    IssueSummary,
    PostureLevel,
    PostureProfileEntryResponse,
    PostureProfileResponse,
    PrioritySuggestionsResponse,
    SafetySignalResponse,
    SelfAssessResponse,
    SelfTestSchema,
    SeverityHint,
    SignalType,
)


__all__ = [
    "SelfTestGuide",
    "SelfTestStep",
    "PhotoAssessmentResult",
    "SafetySignalInput",
    "PostureProfileResult",
    "IdempotencyKey",
    "PhotoKeys",
    "GoalInput",
    "SelfTestSchema",
    "IssueSummary",
    "IssueDetail",
    "PostureProfileResponse",
    "PostureProfileEntryResponse",
    "PrioritySuggestionsResponse",
    "ConfirmedGoalsResponse",
    "SafetySignalResponse",
]


def _reject_blank(value: str) -> str:
    if not value or not value.strip():
        raise ValueError("值不能为空白")
    return value


IdempotencyKey = Annotated[
    str,
    Field(min_length=1, max_length=64),
    AfterValidator(_reject_blank),
]
PhotoKey = Annotated[
    str,
    Field(min_length=1, max_length=512),
    AfterValidator(_reject_blank),
]
PhotoKeys = Annotated[List[PhotoKey], Field(min_length=1, max_length=20)]


# Reuse the knowledge-loader schema so Tool output cannot weaken the sourced
# self-test quality gate or drift from the REST issue-detail contract.
SelfTestStep = SelfTestSchema


class SafetySignalInput(BaseModel):
    """Business input of ``report_safety_signal`` (idempotency key is separate)."""

    model_config = ConfigDict(extra="forbid")

    signal_type: SignalType
    body_region: Optional[BodyRegion] = None
    related_issue_id: Optional[str] = Field(default=None, max_length=20)
    severity_hint: Optional[SeverityHint] = None
    reported_at: Optional[datetime] = None

    @field_validator("reported_at")
    @classmethod
    def _reported_at_must_be_plausible(
        cls, value: Optional[datetime]
    ) -> Optional[datetime]:
        if value is None:
            return value
        now = datetime.now(timezone.utc)
        aware = (
            value
            if value.tzinfo is not None
            else value.replace(tzinfo=timezone.utc)
        )
        if aware > now + timedelta(seconds=5):
            raise ValueError("reported_at 不能晚于当前时间")
        if aware < now - timedelta(days=365):
            raise ValueError("reported_at 不能早于一年前")
        return value


class PhotoAssessmentResult(SelfAssessResponse):
    """Typed Tool result; REST keeps its legacy four-field response model."""

    severity: Optional[PostureLevel] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)
    model_meta: Optional[dict] = None


PostureProfileResult = Union[
    PostureProfileResponse, PostureProfileEntryResponse
]


class SelfTestGuide(BaseModel):
    """Output of ``guide_posture_self_test`` (spec §10.3).

    Agent-only Tool: there is no REST route for the guide today (the existing
    ``GET /issues/{issue_id}`` returns the full ``IssueDetail``; this guide is
    the typed surface a future Agent orchestrator calls to surface the self-test
    flow plus the personalisation hint).

    ``has_existing_result`` reflects whether the caller already has a profile
    entry for this issue (spec §10.3 "用于个性化提示，如已有结果"). It is the
    ONLY user-specific field; everything else is public knowledge data.
    """

    issue_id: str
    issue_name: str
    category: str
    self_tests: List[SelfTestStep]
    has_existing_result: bool = False
