"""Typed posture Tool application layer (spec §10.0-§10.8, plan Task 7).

Eight typed functions that the REST layer and a future Agent orchestrator
call in common. Tools NEVER execute ORM / SQL directly: they delegate to the
existing application services (``service`` / ``safety`` / ``priority`` /
``knowledge``) and to the ownership + privacy-gate boundaries. They create no
independent HTTP routes and no Agent orchestrator (spec §10 / plan Task 7
non-goals).

Identity boundary (spec §10.0): every identity-bearing Tool takes an
``ActorContext`` whose ``user_id`` is injected from the JWT session.
``user_id`` / ``AsyncSession`` / ``consent_record`` / ``risk_context`` are
NEVER model-controllable parameters: ``db`` is a server-injected first
parameter and ``actor`` carries only server-supplied identity. The two public
knowledge Tools (``list_posture_issues`` / ``get_posture_issue``) take no
``actor`` at all (spec §10.1 / §10.2 -- public knowledge data).

Photo path ordering (plan Task 7): ``analyze_posture_photo`` enforces
``total switch -> evidence gate -> consent -> ownership -> service
orchestration``. Any closed authorization boundary stops before ownership,
idempotency, event writes, or model calls. Photo idempotency runs inside
``service.analyze_and_save_photo`` under the user transaction lock and BEFORE
the model call -- the Tool layer does not touch ``idempotency_records``
directly.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import ConfigDict, validate_call
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor_context import ActorContext
from app.core.config import settings
from app.core.exceptions import AppException, NotFound
from app.core.privacy_gate import evaluate_photo_privacy_gate
from app.posture import safety, service
from app.posture.knowledge import get_issue_by_id
from app.posture.tool_contracts import (
    ConfirmedGoalsResponse,
    GoalInput,
    IdempotencyKey,
    IssueDetail,
    IssueSummary,
    PhotoAssessmentResult,
    PhotoKeys,
    PostureProfileResult,
    PrioritySuggestionsResponse,
    SafetySignalInput,
    SafetySignalResponse,
    SelfTestGuide,
    SelfTestStep,
)
from app.upload.ownership import get_photo_ownership_verifier


_TOOL_VALIDATION = ConfigDict(arbitrary_types_allowed=True)


# --- Public knowledge Tools (spec §10.1 / §10.2) ------------------------------
# These read only the versioned knowledge cache; no identity and no DB session.


@validate_call(validate_return=True)
def list_posture_issues(category: Optional[str] = None) -> List[IssueSummary]:
    """List posture issues, optionally filtered by category (spec §10.1).

    Public knowledge data: no ``actor`` / ``db``. Returns the ``IssueSummary``
    projection shape (``id`` / ``name_cn`` / ``category`` / ``aliases`` /
    ``definition``) so the REST layer can serialise it verbatim. Invalid
    category is rejected as ``IssueNotFound`` per spec §10.1.
    """
    issues = service.get_all_issues_list(category)
    if category is not None and not issues:
        raise NotFound("体态分类不存在")
    return [
        IssueSummary.model_validate({
            "id": i["id"],
            "name_cn": i["name_cn"],
            "category": i["category"],
            "aliases": i["aliases"],
            "definition": i["definition"],
        })
        for i in issues
    ]


@validate_call(validate_return=True)
def get_posture_issue(issue_id: str) -> IssueDetail:
    """Fetch one issue's full detail (spec §10.2).

    Public knowledge data: no ``actor`` / ``db``. Raises ``NotFound`` when the
    issue id does not exist, matching the existing REST error contract.
    """
    issue = get_issue_by_id(issue_id)
    if issue is None:
        raise NotFound("体态问题不存在")
    return IssueDetail.model_validate(issue)


# --- Identity-bearing Tools (spec §10.3-§10.8) --------------------------------


@validate_call(config=_TOOL_VALIDATION, validate_return=True)
async def guide_posture_self_test(
    db: AsyncSession, actor: ActorContext, issue_id: str
) -> SelfTestGuide:
    """Build a typed self-test guide for one issue (spec §10.3).

    Read-only: knowledge data plus the caller's existing-result hint. The
    guide surfaces the full extended self-test content (preparation, correct
    posture, common errors, STOP CONDITIONS) verbatim from the catalog.
    """
    issue = get_issue_by_id(issue_id)
    if issue is None:
        raise NotFound("体态问题不存在")

    existing_entry = await service.get_user_profile_entry(
        db, actor.user_id, issue_id
    )
    steps = [
        SelfTestStep.model_validate(st) for st in (issue.get("self_tests") or [])
    ]
    return SelfTestGuide(
        issue_id=issue["id"],
        issue_name=issue["name_cn"],
        category=issue["category"],
        self_tests=steps,
        has_existing_result=existing_entry is not None,
    )


@validate_call(config=_TOOL_VALIDATION, validate_return=True)
async def analyze_posture_photo(
    db: AsyncSession,
    actor: ActorContext,
    issue_id: str,
    photo_keys: PhotoKeys,
    idempotency_key: IdempotencyKey,
) -> PhotoAssessmentResult:
    """Run a photo assessment end-to-end (spec §10.4 / plan Task 7).

    Strict ordering: TOTAL SWITCH -> EVIDENCE GATE -> CONSENT -> OWNERSHIP ->
    service orchestration.

    1. The global ``PHOTO_ANALYSIS_ENABLED`` switch and evidence-backed
       ``evaluate_photo_privacy_gate`` must both pass.
    2. ``actor.consent_record`` must be active, purpose-scoped, and not
       withdrawn. It is loaded from trusted server state, never a business
       input.
    3. ``PhotoOwnershipVerifier`` proves every ``photo_key`` belongs to
       ``actor.user_id``. The default verifier is fail-closed; a forged path
       prefix is never accepted as proof. Cross-user keys raise
       ``PhotoOwnershipDenied`` (400); no backend raises
       ``PhotoOwnershipUnavailable`` (503).
    4. ``service.analyze_and_save_photo`` runs the idempotent orchestration
       (check/replay -> model -> event + profile + idempotency_record) under
       the user transaction lock. Idempotency is resolved BEFORE the model is
       called.

    Authorization runs first by design: a fake ownership verifier that returns
    ``owned`` cannot enable the production photo path by itself.
    """
    if not settings.PHOTO_ANALYSIS_ENABLED:
        raise AppException(
            503,
            "照片分析在当前数据模式下未启用",
            "photo_analysis_disabled",
        )

    gate = evaluate_photo_privacy_gate()
    if not gate.satisfied:
        raise AppException(
            503,
            "照片分析隐私门启用条件未满足，照片分析暂不可用",
            "photo_analysis_disabled",
        )

    consent = actor.consent_record
    if consent is None or not consent.permits_posture_photo_analysis():
        raise AppException(
            403,
            "缺少有效的体态照片分析同意记录",
            "consent_required",
        )

    # Ownership: fail-closed by default. Runs only AFTER the gate, so a closed
    # gate performs zero ownership probes (plan Task 7).
    await get_photo_ownership_verifier().verify(actor.user_id, photo_keys)

    return await service.analyze_and_save_photo(
        db, actor.user_id, issue_id, photo_keys, idempotency_key
    )


@validate_call(config=_TOOL_VALIDATION, validate_return=True)
async def get_posture_profile(
    db: AsyncSession, actor: ActorContext, issue_id: Optional[str] = None
) -> PostureProfileResult:
    """Read the caller's posture profile (spec §10.5).

    ``issue_id=None`` returns the full profile; otherwise the single-issue
    detail. Identity comes only from ``actor.user_id`` -- there is no
    ``user_id`` query parameter, so one user can never address another user's
    row (spec §9.2 cross-user isolation). Unknown ``issue_id`` -> 404
    ``issue_not_found``; known issue with no caller entry -> 404
    ``profile_entry_not_found`` (does not reveal whether other users have
    data).
    """
    if issue_id is None:
        return await service.get_user_profile(db, actor.user_id)

    issue = get_issue_by_id(issue_id)
    if issue is None:
        raise AppException(404, "体态问题不存在", "issue_not_found")
    entry = await service.get_user_profile_entry(db, actor.user_id, issue_id)
    if entry is None:
        raise AppException(
            404, "当前用户尚未评估该体态问题", "profile_entry_not_found"
        )
    return service.build_profile_entry_detail(entry, issue)


@validate_call(config=_TOOL_VALIDATION, validate_return=True)
async def suggest_posture_priorities(
    db: AsyncSession, actor: ActorContext
) -> PrioritySuggestionsResponse:
    """Compute deterministic priority suggestions (spec §10.6).

    Read-only safety gate: every call reloads the profile + active signals and
    reclassifies via ``safety.compute_profile_risk`` (inside
    ``priority.build_priority_suggestions``). Returns the server-generated
    ``suggestion_id`` / ``profile_version`` / ``rule_version`` /
    ``risk_version`` used by the confirm optimistic lock. With no qualifying
    data returns three empty buckets (never ``InsufficientData``).
    """
    return await service.get_priority_suggestions(db, actor.user_id)


@validate_call(config=_TOOL_VALIDATION, validate_return=True)
async def confirm_posture_goals(
    db: AsyncSession,
    actor: ActorContext,
    suggestion_id: str,
    profile_version: str,
    goals: List[GoalInput],
    idempotency_key: IdempotencyKey,
) -> ConfirmedGoalsResponse:
    """Confirm 1-3 of the current normal-candidate goals (spec §10.7).

    Delegates to ``service.confirm_posture_goals`` which owns the full write
    path: user lock -> freeze -> unified idempotency (batch anchor replay /
    410) -> recompute safety gate -> stale check -> qualification ->
    restricted/red_flag rejection (409 ``restricted_blocked`` /
    ``red_flag_blocked``) -> supersede prior goals -> write batch ->
    idempotency record. ``suggestion_id`` / ``profile_version`` are regenerated
    server-side; a client ``priority_context_snapshot`` is rejected by the
    request schema (``extra="forbid"``).
    """
    return await service.confirm_posture_goals(
        db,
        actor.user_id,
        suggestion_id,
        profile_version,
        goals,
        idempotency_key,
    )


@validate_call(config=_TOOL_VALIDATION, validate_return=True)
async def report_safety_signal(
    db: AsyncSession,
    actor: ActorContext,
    signal: SafetySignalInput,
    idempotency_key: IdempotencyKey,
) -> SafetySignalResponse:
    """Record a structured safety signal (spec §10.8 / §12.2).

    Thin wrapper over ``safety.record_safety_signal``, which is already
    tool-ready: it owns unified idempotency (24h, ``result_ref`` = signal id,
    410 on purge), strict input validation, the user transaction lock, the
    freeze check, and the risk reclassification cascade. The privacy gate does
    NOT apply (safety signals are not photos).
    """
    return await safety.record_safety_signal(
        db,
        actor.user_id,
        signal.model_dump(mode="json"),
        idempotency_key,
    )
