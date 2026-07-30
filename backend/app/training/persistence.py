"""Phase 4 plan persistence (Task 2).

Atomic, idempotent, ownership-scoped writes for plan versions, daily feedback,
and same-day substitution. Reuses the shared ``posture.idempotency_records``
table (ADR-0001) with Phase 4 ``operation`` names; it never duplicates that
table and never stores an idempotency key on a plan/feedback/substitution row.

Atomicity model (mirrors ``app.posture.safety.record_safety_signal``):

    acquire_user_transaction_lock
    -> idempotency check (replay / conflict / proceed)
    -> perform side effect (state transition via app.training.state)
    -> persist idempotency record (result_ref = created entity id)
    -> commit (one transaction)

A replay returns the recorded entity; a same-key-different-request attempt is
rejected; an expired record no longer blocks. Ownership is enforced everywhere
(``user_id`` filter), so cross-account access is impossible by construction.
``user_id`` is always the JWT-derived principal (never client-supplied).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.posture.models import IdempotencyRecord
from app.posture.user_lock import acquire_user_transaction_lock
from app.training.models import (
    TrainingPlanVersion,
    TrainingPrescription,
    TrainingSession,
    TrainingSessionFeedback,
    TrainingSessionSubstitution,
)
from app.training.schemas import TrainingPlanDraft
from app.training.state import (
    PlanStatus,
    assert_transition,
    is_legal_transition,
)

# --- Idempotency operation names (ADR-0001 namespace; must not collide with
# posture operation names). ---
OP_PLAN_GENERATE = "plan_generate"
OP_PLAN_CONFIRM = "plan_confirm"
OP_SESSION_SUBSTITUTE = "session_substitute"
OP_SESSION_FEEDBACK = "session_feedback"

IDEMPOTENCY_TTL = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_request(payload: dict) -> str:
    """Stable SHA-256 hex of a canonicalized request payload.

    The caller builds ``payload`` from validated request fields EXCLUDING the
    idempotency key (the key is the lookup, not part of request identity). The
    same logical request always hashes identically across retries.
    """
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


# --- Result types -----------------------------------------------------------


@dataclass(frozen=True)
class DraftResult:
    plan_version_id: uuid.UUID
    status: str  # "created" | "replayed"


@dataclass(frozen=True)
class ConfirmResult:
    plan_version_id: uuid.UUID
    status: str  # "confirmed" | "replayed"
    superseded_version_id: Optional[uuid.UUID]


@dataclass(frozen=True)
class CancelResult:
    plan_version_id: uuid.UUID
    status: str  # "cancelled"


@dataclass(frozen=True)
class FeedbackResult:
    feedback_id: uuid.UUID
    status: str  # "recorded" | "replayed"


@dataclass(frozen=True)
class SubstitutionResult:
    substitution_id: uuid.UUID
    status: str  # "recorded" | "replayed"


# --- Idempotency helper -----------------------------------------------------


async def _check_idempotency(
    db: AsyncSession,
    user_id: str,
    operation: str,
    idempotency_key: str,
    request_hash: str,
    now: datetime,
):
    """Return ``(action, record)``.

    action is ``"replay"`` (same key+hash, not expired), ``"conflict"`` (same
    key, different hash, not expired), or ``"proceed"`` (no record, or an
    expired record that has been deleted). On ``"proceed"`` the caller performs
    the side effect and records a fresh idempotency entry.
    """
    existing = await db.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == uuid.UUID(user_id),
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
    )
    record = existing.scalar_one_or_none()
    if record is None:
        return "proceed", None
    if record.expires_at.replace(tzinfo=timezone.utc) > now:
        if record.request_hash == request_hash:
            return "replay", record
        return "conflict", record
    # Expired: no longer blocks. Remove and proceed.
    await db.delete(record)
    await db.flush()
    return "proceed", None


async def _record_idempotency(
    db: AsyncSession,
    user_id: str,
    operation: str,
    idempotency_key: str,
    request_hash: str,
    result_ref: str,
    now: datetime,
) -> None:
    db.add(
        IdempotencyRecord(
            user_id=uuid.UUID(user_id),
            operation=operation,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            status="completed",
            result_ref=result_ref,
            expires_at=now + IDEMPOTENCY_TTL,
        )
    )


async def peek_idempotency(
    db: AsyncSession,
    user_id: str,
    operation: str,
    idempotency_key: str,
    request_hash: str,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Return the recorded ``result_ref`` for a replay, or None to proceed.

    Used by callers that must resolve a replay BEFORE another precondition (e.g.
    confirm must replay even after the pending draft has become active). A
    same-key-different-hash record raises ``idempotency_key_conflict``. An
    expired record is treated as absent (caller proceeds and may re-record).
    """
    now = now or _now()
    res = await db.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == uuid.UUID(user_id),
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
    )
    record = res.scalar_one_or_none()
    if record is None:
        return None
    if record.expires_at.replace(tzinfo=timezone.utc) <= now:
        return None
    if record.request_hash != request_hash:
        raise AppException(
            400, "idempotency_key 已用于不同的请求", "idempotency_key_conflict"
        )
    return record.result_ref


async def _require_owned_version(
    db: AsyncSession, user_id: str, plan_version_id: uuid.UUID
) -> TrainingPlanVersion:
    """Load a plan version scoped to ``user_id``; 404 if missing/not owned."""
    res = await db.execute(
        select(TrainingPlanVersion).where(
            TrainingPlanVersion.user_id == uuid.UUID(user_id),
            TrainingPlanVersion.plan_version_id == plan_version_id,
        )
    )
    version = res.scalar_one_or_none()
    if version is None:
        raise AppException(404, "计划版本不存在", "not_owner_or_missing_plan_version")
    return version


# --- Plan version writes ----------------------------------------------------


async def _persist_draft_core(
    db: AsyncSession,
    user_id: str,
    *,
    draft: TrainingPlanDraft,
    weekly_frequency: int,
    session_duration_minutes: int,
    decision_gate: str,
    decision_fingerprint: str,
    generated_at: datetime,
    change_reason: str,
) -> uuid.UUID:
    """Transaction-neutral side-effect core of ``create_draft``.

    Supersedes any existing pending draft, inserts the plan version + sessions +
    prescriptions, and ``flush``es so the caller receives populated ids. It does
    NOT acquire the user lock, record idempotency, or commit: the committing
    ``create_draft`` wrapper and the Agent confirmation path both call this core
    so chat and button behaviour share one operation (ADR-0003). No business
    rule is duplicated. Returns the new ``plan_version_id``.
    """
    pending = await get_pending_draft(db, user_id)
    if pending is not None:
        assert_transition(PlanStatus.draft, PlanStatus.superseded)
        pending.status = PlanStatus.superseded.value
        pending.change_reason = "superseded_by_new_draft"

    version = TrainingPlanVersion(
        user_id=uuid.UUID(user_id),
        requested_goal=draft.requested_goal,
        source_context_fingerprint=draft.source_context_fingerprint,
        profile_version=draft.profile_version,
        catalog_version=draft.catalog_version,
        policy_version=draft.policy_version,
        source_manifest_version=draft.source_manifest_version,
        weekly_frequency=weekly_frequency,
        session_duration_minutes=session_duration_minutes,
        status=PlanStatus.draft.value,
        change_reason=change_reason,
        decision_gate=decision_gate,
        decision_fingerprint=decision_fingerprint,
        generated_at=generated_at,
        confirmed_at=None,
    )
    db.add(version)
    await db.flush()  # populate plan_version_id

    for session in draft.sessions:
        ses = TrainingSession(
            plan_version_id=version.plan_version_id,
            week_index=session.week_index,
            day_of_week=session.day_of_week,
            session_order=session.session_order,
            target_minutes=session.target_minutes or session_duration_minutes,
        )
        db.add(ses)
        await db.flush()
        for order, prescription in enumerate(session.prescriptions):
            db.add(
                TrainingPrescription(
                    session_id=ses.session_id,
                    exercise_id=prescription.exercise_id,
                    sets=prescription.sets,
                    reps=prescription.reps,
                    duration_seconds=prescription.duration_seconds,
                    rest_seconds=prescription.rest_seconds,
                    relation_reason=prescription.relation_reason,
                    relation_source_exercise_id=prescription.relation_source_exercise_id,
                    display_order=order,
                )
            )
    return version.plan_version_id


async def create_draft(
    db: AsyncSession,
    user_id: str,
    *,
    draft: TrainingPlanDraft,
    weekly_frequency: int,
    session_duration_minutes: int,
    decision_gate: str,
    decision_fingerprint: str,
    generated_at: datetime,
    change_reason: str,
    idempotency_key: str,
    request_hash: str,
) -> DraftResult:
    """Persist a generated draft (idempotent).

    Thin committing wrapper around ``_persist_draft_core`` plus the user lock +
    domain idempotency record. A pending ``draft`` has no execution effect.
    Generating a new draft when a pending draft already exists supersedes that
    pending draft (it never had an effect). The active plan is never touched by
    generation.
    """
    now = _now()
    await acquire_user_transaction_lock(db, user_id)
    action, record = await _check_idempotency(
        db, user_id, OP_PLAN_GENERATE, idempotency_key, request_hash, now
    )
    if action == "replay":
        # Replay: return the recorded draft. The replayed read performs no write.
        result_ref = record.result_ref
        await db.rollback()
        assert result_ref is not None
        return DraftResult(uuid.UUID(result_ref), "replayed")
    if action == "conflict":
        raise AppException(
            400, "idempotency_key 已用于不同的请求", "idempotency_key_conflict"
        )

    plan_version_id = await _persist_draft_core(
        db,
        user_id,
        draft=draft,
        weekly_frequency=weekly_frequency,
        session_duration_minutes=session_duration_minutes,
        decision_gate=decision_gate,
        decision_fingerprint=decision_fingerprint,
        generated_at=generated_at,
        change_reason=change_reason,
    )
    await _record_idempotency(
        db, user_id, OP_PLAN_GENERATE, idempotency_key, request_hash,
        str(plan_version_id), now,
    )
    await db.commit()
    return DraftResult(plan_version_id, "created")


async def confirm_and_activate(
    db: AsyncSession,
    user_id: str,
    *,
    plan_version_id: uuid.UUID,
    confirmed_at: datetime,
    change_reason: str,
    idempotency_key: str,
    request_hash: str,
) -> ConfirmResult:
    """Atomically confirm a pending draft and activate it (idempotent).

    Sets any current ``active`` plan to ``superseded`` and the target ``draft``
    to ``active`` in one transaction, preserving the single-active invariant.
    Re-validation/staleness is the service layer's responsibility (Task 4); this
    function is the mechanical atomic transition and refuses illegal states.
    """
    now = _now()
    await acquire_user_transaction_lock(db, user_id)
    action, record = await _check_idempotency(
        db, user_id, OP_PLAN_CONFIRM, idempotency_key, request_hash, now
    )
    if action == "replay":
        result_ref = record.result_ref
        await db.rollback()
        assert result_ref is not None
        return ConfirmResult(uuid.UUID(result_ref), "replayed", None)
    if action == "conflict":
        raise AppException(
            400, "idempotency_key 已用于不同的请求", "idempotency_key_conflict"
        )

    target = await _require_owned_version(db, user_id, plan_version_id)
    if target.status != PlanStatus.draft.value:
        raise AppException(
            409, "该计划版本不是待确认草案", "no_pending_draft"
        )

    prior_active = await get_active_version(db, user_id)
    superseded_id: Optional[uuid.UUID] = None
    if prior_active is not None and prior_active.plan_version_id != target.plan_version_id:
        assert_transition(PlanStatus.active, PlanStatus.superseded)
        prior_active.status = PlanStatus.superseded.value
        prior_active.change_reason = "superseded_by_new_draft"
        superseded_id = prior_active.plan_version_id

    assert_transition(PlanStatus.draft, PlanStatus.active)
    target.status = PlanStatus.active.value
    target.change_reason = change_reason
    target.confirmed_at = confirmed_at

    await _record_idempotency(
        db, user_id, OP_PLAN_CONFIRM, idempotency_key, request_hash,
        str(target.plan_version_id), now,
    )
    await db.commit()
    return ConfirmResult(target.plan_version_id, "confirmed", superseded_id)


async def cancel(
    db: AsyncSession,
    user_id: str,
    *,
    plan_version_id: uuid.UUID,
    change_reason: str = "cancelled_by_user",
) -> CancelResult:
    """Cancel a draft or active plan (terminal afterwards).

    Cancel is a user-initiated state change; it is not idempotency-tracked
    (charter lists generation/confirmation/substitution/feedback). Cancelling an
    already-terminal version is rejected with 409.
    """
    await acquire_user_transaction_lock(db, user_id)
    version = await _require_owned_version(db, user_id, plan_version_id)
    current = PlanStatus(version.status)
    if not is_legal_transition(current, PlanStatus.cancelled):
        raise AppException(409, "该计划版本已结束，无法取消", "already_terminal")
    assert_transition(current, PlanStatus.cancelled)
    version.status = PlanStatus.cancelled.value
    version.change_reason = change_reason
    await db.commit()
    return CancelResult(version.plan_version_id, "cancelled")


# --- Execution records ------------------------------------------------------


async def _persist_feedback_core(
    db: AsyncSession,
    user_id: str,
    *,
    plan_version_id: uuid.UUID,
    session_id: uuid.UUID,
    local_date: date,
    outcome_state: str,
) -> uuid.UUID:
    """Transaction-neutral side-effect core of ``record_feedback``.

    Inserts one ``TrainingSessionFeedback`` and ``flush``es; it does NOT acquire
    the user lock, record idempotency, or commit. Shared by the committing
    wrapper and the Agent confirmation path (ADR-0003). Returns feedback_id.
    """
    feedback = TrainingSessionFeedback(
        user_id=uuid.UUID(user_id),
        plan_version_id=plan_version_id,
        session_id=session_id,
        local_date=local_date,
        outcome_state=outcome_state,
    )
    db.add(feedback)
    await db.flush()
    return feedback.feedback_id


async def record_feedback(
    db: AsyncSession,
    user_id: str,
    *,
    plan_version_id: uuid.UUID,
    session_id: uuid.UUID,
    local_date: date,
    outcome_state: str,
    idempotency_key: str,
    request_hash: str,
) -> FeedbackResult:
    """Record one day's outcome for one session (idempotent; one per day).

    Thin committing wrapper around ``_persist_feedback_core`` plus the user lock
    + domain idempotency + the per-(session,day) collision guard.
    """
    now = _now()
    await acquire_user_transaction_lock(db, user_id)
    action, record = await _check_idempotency(
        db, user_id, OP_SESSION_FEEDBACK, idempotency_key, request_hash, now
    )
    if action == "replay":
        result_ref = record.result_ref
        await db.rollback()
        assert result_ref is not None
        return FeedbackResult(uuid.UUID(result_ref), "replayed")
    if action == "conflict":
        raise AppException(
            400, "idempotency_key 已用于不同的请求", "idempotency_key_conflict"
        )

    await _assert_session_owned(db, user_id, plan_version_id, session_id)

    # Different key, same (session, day) -> a real same-day collision (not replay).
    existing = await get_feedback(db, user_id, session_id, local_date)
    if existing is not None:
        raise AppException(
            409, "该训练日已记录反馈", "feedback_already_recorded"
        )

    feedback_id = await _persist_feedback_core(
        db,
        user_id,
        plan_version_id=plan_version_id,
        session_id=session_id,
        local_date=local_date,
        outcome_state=outcome_state,
    )
    await _record_idempotency(
        db, user_id, OP_SESSION_FEEDBACK, idempotency_key, request_hash,
        str(feedback_id), now,
    )
    await db.commit()
    return FeedbackResult(feedback_id, "recorded")


async def _persist_substitution_core(
    db: AsyncSession,
    user_id: str,
    *,
    plan_version_id: uuid.UUID,
    session_id: uuid.UUID,
    local_date: date,
    original_exercise_id: str,
    replacement_exercise_id: str,
    relation_reason: str,
    decision_gate: str,
) -> uuid.UUID:
    """Transaction-neutral side-effect core of ``record_substitution``.

    Inserts one ``TrainingSessionSubstitution`` and ``flush``es; it does NOT
    acquire the user lock, record idempotency, or commit. Shared by the
    committing wrapper and the Agent confirmation path (ADR-0003). Returns
    substitution_id.
    """
    sub = TrainingSessionSubstitution(
        user_id=uuid.UUID(user_id),
        plan_version_id=plan_version_id,
        session_id=session_id,
        local_date=local_date,
        original_exercise_id=original_exercise_id,
        replacement_exercise_id=replacement_exercise_id,
        relation_reason=relation_reason,
        decision_gate=decision_gate,
    )
    db.add(sub)
    await db.flush()
    return sub.substitution_id


async def record_substitution(
    db: AsyncSession,
    user_id: str,
    *,
    plan_version_id: uuid.UUID,
    session_id: uuid.UUID,
    local_date: date,
    original_exercise_id: str,
    replacement_exercise_id: str,
    relation_reason: str,
    decision_gate: str,
    idempotency_key: str,
    request_hash: str,
) -> SubstitutionResult:
    """Record one same-day substitution delta (idempotent; one per day).

    Thin committing wrapper around ``_persist_substitution_core`` plus the user
    lock + domain idempotency + the per-(session,day) limit guard.
    """
    now = _now()
    await acquire_user_transaction_lock(db, user_id)
    action, record = await _check_idempotency(
        db, user_id, OP_SESSION_SUBSTITUTE, idempotency_key, request_hash, now
    )
    if action == "replay":
        result_ref = record.result_ref
        await db.rollback()
        assert result_ref is not None
        return SubstitutionResult(uuid.UUID(result_ref), "replayed")
    if action == "conflict":
        raise AppException(
            400, "idempotency_key 已用于不同的请求", "idempotency_key_conflict"
        )

    await _assert_session_owned(db, user_id, plan_version_id, session_id)

    existing = await get_substitution(db, user_id, session_id, local_date)
    if existing is not None:
        raise AppException(
            409, "该训练日已替换过动作", "substitution_limit_reached"
        )

    substitution_id = await _persist_substitution_core(
        db,
        user_id,
        plan_version_id=plan_version_id,
        session_id=session_id,
        local_date=local_date,
        original_exercise_id=original_exercise_id,
        replacement_exercise_id=replacement_exercise_id,
        relation_reason=relation_reason,
        decision_gate=decision_gate,
    )
    await _record_idempotency(
        db, user_id, OP_SESSION_SUBSTITUTE, idempotency_key, request_hash,
        str(substitution_id), now,
    )
    await db.commit()
    return SubstitutionResult(substitution_id, "recorded")


async def _assert_session_owned(
    db: AsyncSession,
    user_id: str,
    plan_version_id: uuid.UUID,
    session_id: uuid.UUID,
) -> None:
    """Verify the session belongs to a plan version owned by ``user_id``."""
    version = await _require_owned_version(db, user_id, plan_version_id)
    res = await db.execute(
        select(TrainingSession).where(
            TrainingSession.session_id == session_id,
            TrainingSession.plan_version_id == version.plan_version_id,
        )
    )
    if res.scalar_one_or_none() is None:
        raise AppException(404, "训练场次不存在", "not_owner_or_missing_session")


# --- Readers (ownership-scoped) ---------------------------------------------


async def get_pending_draft(
    db: AsyncSession, user_id: str
) -> Optional[TrainingPlanVersion]:
    res = await db.execute(
        select(TrainingPlanVersion).where(
            TrainingPlanVersion.user_id == uuid.UUID(user_id),
            TrainingPlanVersion.status == PlanStatus.draft.value,
        )
    )
    return res.scalar_one_or_none()


async def get_active_version(
    db: AsyncSession, user_id: str
) -> Optional[TrainingPlanVersion]:
    res = await db.execute(
        select(TrainingPlanVersion).where(
            TrainingPlanVersion.user_id == uuid.UUID(user_id),
            TrainingPlanVersion.status == PlanStatus.active.value,
        )
    )
    return res.scalar_one_or_none()


async def get_version_owned(
    db: AsyncSession, user_id: str, plan_version_id: uuid.UUID
) -> Optional[TrainingPlanVersion]:
    res = await db.execute(
        select(TrainingPlanVersion).where(
            TrainingPlanVersion.user_id == uuid.UUID(user_id),
            TrainingPlanVersion.plan_version_id == plan_version_id,
        )
    )
    return res.scalar_one_or_none()


async def get_feedback(
    db: AsyncSession, user_id: str, session_id: uuid.UUID, local_date: date
) -> Optional[TrainingSessionFeedback]:
    res = await db.execute(
        select(TrainingSessionFeedback).where(
            TrainingSessionFeedback.user_id == uuid.UUID(user_id),
            TrainingSessionFeedback.session_id == session_id,
            TrainingSessionFeedback.local_date == local_date,
        )
    )
    return res.scalar_one_or_none()


async def get_feedback_owned(
    db: AsyncSession, user_id: str, feedback_id: uuid.UUID
) -> Optional[TrainingSessionFeedback]:
    res = await db.execute(
        select(TrainingSessionFeedback).where(
            TrainingSessionFeedback.user_id == uuid.UUID(user_id),
            TrainingSessionFeedback.feedback_id == feedback_id,
        )
    )
    return res.scalar_one_or_none()


async def get_substitution(
    db: AsyncSession, user_id: str, session_id: uuid.UUID, local_date: date
) -> Optional[TrainingSessionSubstitution]:
    res = await db.execute(
        select(TrainingSessionSubstitution).where(
            TrainingSessionSubstitution.user_id == uuid.UUID(user_id),
            TrainingSessionSubstitution.session_id == session_id,
            TrainingSessionSubstitution.local_date == local_date,
        )
    )
    return res.scalar_one_or_none()


async def get_substitution_owned(
    db: AsyncSession, user_id: str, substitution_id: uuid.UUID
) -> Optional[TrainingSessionSubstitution]:
    res = await db.execute(
        select(TrainingSessionSubstitution).where(
            TrainingSessionSubstitution.user_id == uuid.UUID(user_id),
            TrainingSessionSubstitution.substitution_id == substitution_id,
        )
    )
    return res.scalar_one_or_none()


async def load_sessions(
    db: AsyncSession, plan_version_id: uuid.UUID
) -> list[TrainingSession]:
    res = await db.execute(
        select(TrainingSession)
        .where(TrainingSession.plan_version_id == plan_version_id)
        .order_by(
            TrainingSession.week_index.asc(),
            TrainingSession.session_order.asc(),
        )
    )
    return list(res.scalars().all())


async def load_prescriptions(
    db: AsyncSession, session_id: uuid.UUID
) -> list[TrainingPrescription]:
    res = await db.execute(
        select(TrainingPrescription)
        .where(TrainingPrescription.session_id == session_id)
        .order_by(TrainingPrescription.display_order.asc())
    )
    return list(res.scalars().all())


__all__ = [
    "OP_PLAN_GENERATE",
    "OP_PLAN_CONFIRM",
    "OP_SESSION_SUBSTITUTE",
    "OP_SESSION_FEEDBACK",
    "IDEMPOTENCY_TTL",
    "hash_request",
    "peek_idempotency",
    "DraftResult",
    "ConfirmResult",
    "CancelResult",
    "FeedbackResult",
    "SubstitutionResult",
    "_persist_draft_core",
    "_persist_feedback_core",
    "_persist_substitution_core",
    "create_draft",
    "confirm_and_activate",
    "cancel",
    "record_feedback",
    "record_substitution",
    "get_pending_draft",
    "get_active_version",
    "get_version_owned",
    "get_feedback",
    "get_feedback_owned",
    "get_substitution",
    "get_substitution_owned",
    "load_sessions",
    "load_prescriptions",
]
