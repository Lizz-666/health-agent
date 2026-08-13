"""Phase 5 Agent consent / audit / proposal persistence (Task 2).

Server-owned, ownership-scoped, transaction-safe persistence for the four Agent
tables and the three shared ``idempotency_records`` Agent namespaces
(``agent_action_confirm``, ``agent_consent_grant``, ``agent_consent_withdraw``).
It reuses the existing shared idempotency table (ADR-0001) and the existing
per-user transaction lock (``app.posture.user_lock``); it does not duplicate
domain logic or create a new idempotency table.

Privacy minimization is enforced structurally: nothing accepts or stores raw
user text, assistant prose, raw context, prompts, provider request/response
payloads, raw Tool arguments/results, or health identifiers. Proposal
arguments are typed/bounded, retained only while ``pending``, and scrubbed
(NULL) on every terminal transition, consent withdrawal, Agent-data deletion,
and lazy expiry. Fingerprints are keyed HMAC-SHA256 (``app.agent.fingerprints``).

Fail-closed semantics: a missing record, illegal state, cross-user access,
stale/partial idempotency hit, or transaction exception never becomes a
success, a normal/healthy result, or an executed side effect.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import (
    AGENT_CLOUD_PROCESSING_PURPOSE,
    AgentActionProposal,
    AgentCloudConsent,
    AgentRun,
    AgentToolEvent,
    CONSENT_GRANTED,
    CONSENT_WITHDRAWN,
    PROPOSAL_CANCELLED,
    PROPOSAL_EXECUTED,
    PROPOSAL_EXPIRED,
    PROPOSAL_INVALIDATED,
    PROPOSAL_PENDING,
    PROPOSAL_TERMINAL_STATUSES,
)
from app.agent.privacy_gate import ActiveConsentSnapshot
from app.agent.messages import AgentError, ResultCode
from app.core.exceptions import AppException
from app.posture.models import IdempotencyRecord
from app.posture.user_lock import acquire_user_transaction_lock
from app.training.context import validate_iana_timezone

# --- Shared idempotency operation namespaces (ADR-0001; must not collide). ---
OP_AGENT_ACTION_CONFIRM = "agent_action_confirm"
OP_AGENT_CONSENT_GRANT = "agent_consent_grant"
OP_AGENT_CONSENT_WITHDRAW = "agent_consent_withdraw"

_AGENT_NAMESPACES = (
    OP_AGENT_ACTION_CONFIRM,
    OP_AGENT_CONSENT_GRANT,
    OP_AGENT_CONSENT_WITHDRAW,
)

# Lifetimes (spec Persistence And State).
PROPOSAL_TTL = timedelta(minutes=15)
RUN_RETENTION = timedelta(days=30)
IDEMPOTENCY_TTL = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    """Normalize a datetime to aware UTC.

    SQLite returns naive datetimes for ``DateTime(timezone=True)``; PostgreSQL
    returns aware ones. Treat naive values as UTC (the only canonical form
    written) so comparisons are dialect-independent.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_uuid(user_id) -> uuid.UUID:
    if isinstance(user_id, uuid.UUID):
        return user_id
    return uuid.UUID(str(user_id))


def hash_request(payload: dict) -> str:
    """Stable SHA-256 hex of a canonicalized request payload.

    Mirrors ``app.training.persistence.hash_request`` / ``app.posture.safety``
    so the shared idempotency table has one canonicalization convention. The
    caller builds ``payload`` from validated fields EXCLUDING the idempotency
    key (the key is the lookup index, not part of request identity).
    """
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


# --- Idempotency helpers (operate on the shared IdempotencyRecord table) -----


async def _check_idempotency(
    db: AsyncSession,
    user_id: str,
    operation: str,
    idempotency_key: str,
    request_hash: str,
    now: datetime,
):
    """Return ``(action, record)``: replay / conflict / proceed.

    On ``proceed`` with an expired record, the record is removed first. The
    caller performs the side effect and records a fresh entry on proceed.
    """
    existing = await db.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == _to_uuid(user_id),
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
    *,
    status: str = "completed",
) -> None:
    db.add(
        IdempotencyRecord(
            user_id=_to_uuid(user_id),
            operation=operation,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            status=status,
            result_ref=result_ref,
            expires_at=now + IDEMPOTENCY_TTL,
        )
    )


def _idempotency_conflict() -> AppException:
    return AppException(
        400, "idempotency_key 已用于不同的请求", "idempotency_key_conflict"
    )


def _gone() -> AppException:
    return AppException(
        410, "幂等记录指向的内容已被清除", "idempotency_result_gone"
    )


# --------------------------------------------------------------------------- #
# Consent                                                                      #
# --------------------------------------------------------------------------- #


async def _highest_consent_row(
    db: AsyncSession, user_id: str
) -> Optional[AgentCloudConsent]:
    """Load the highest-``sequence_no`` consent row for the user/purpose.

    The current active state is derived deterministically from this single row;
    a later withdrawal invalidates every earlier grant without timestamp-tie
    ambiguity (spec Persistence).
    """
    max_seq = (
        await db.execute(
            select(func.max(AgentCloudConsent.sequence_no)).where(
                AgentCloudConsent.user_id == _to_uuid(user_id),
                AgentCloudConsent.purpose == AGENT_CLOUD_PROCESSING_PURPOSE,
            )
        )
    ).scalar()
    if max_seq is None:
        return None
    res = await db.execute(
        select(AgentCloudConsent).where(
            AgentCloudConsent.user_id == _to_uuid(user_id),
            AgentCloudConsent.purpose == AGENT_CLOUD_PROCESSING_PURPOSE,
            AgentCloudConsent.sequence_no == max_seq,
        )
    )
    return res.scalar_one_or_none()


async def active_consent(db: AsyncSession, user_id: str) -> ActiveConsentSnapshot:
    """Derive the current consent snapshot from the highest sequence event.

    Returns an inactive snapshot when there is no consent or the latest event is
    a withdrawal. Never raises for a missing consent.
    """
    row = await _highest_consent_row(db, user_id)
    if row is None:
        return ActiveConsentSnapshot(active=False)
    if row.status == CONSENT_GRANTED:
        return ActiveConsentSnapshot(
            active=True,
            provider_id=row.provider_id,
            disclosure_version=row.disclosure_version,
            purpose=row.purpose,
        )
    return ActiveConsentSnapshot(
        active=False,
        provider_id=row.provider_id,
        disclosure_version=row.disclosure_version,
        purpose=row.purpose,
    )


@dataclass(frozen=True)
class ConsentGrantResult:
    consent_id: uuid.UUID
    sequence_no: int
    status: str
    replayed: bool


async def grant_consent(
    db: AsyncSession,
    user_id: str,
    *,
    accepted_provider_id: str,
    accepted_disclosure_version: str,
    current_provider_id: str,
    current_disclosure_version: str,
    idempotency_key: str,
    now: Optional[datetime] = None,
) -> ConsentGrantResult:
    """Grant cloud-processing consent for the CURRENT server provider/disclosure.

    The ``accepted`` acknowledgement values must equal the current server
    configuration exactly; otherwise ``agent_disclosure_stale`` is raised and
    nothing is granted (the user cannot select a different provider/model).
    Grant is idempotent via the ``agent_consent_grant`` namespace (replay
    returns the recorded grant; same-key-different-request conflicts; a gone
    anchor returns 410). Sequence allocation is serialized by the user lock.
    """
    now = now or _now()
    if (
        accepted_provider_id != current_provider_id
        or accepted_disclosure_version != current_disclosure_version
        or not accepted_provider_id
        or not accepted_disclosure_version
    ):
        raise AppException(
            409, "披露版本与当前服务端配置不一致", "agent_disclosure_stale"
        )

    await acquire_user_transaction_lock(db, user_id)
    request_hash = hash_request(
        {
            "op": "consent_grant",
            "accepted_provider_id": accepted_provider_id,
            "accepted_disclosure_version": accepted_disclosure_version,
        }
    )
    action, record = await _check_idempotency(
        db, user_id, OP_AGENT_CONSENT_GRANT, idempotency_key, request_hash, now
    )
    if action == "replay":
        result_ref = record.result_ref
        await db.rollback()
        assert result_ref is not None
        # Gone-anchor: the referenced consent was deleted (Agent-data deletion).
        still = await _load_consent(db, user_id, uuid.UUID(result_ref))
        if still is None:
            raise _gone()
        return ConsentGrantResult(still.consent_id, still.sequence_no, still.status, True)
    if action == "conflict":
        raise _idempotency_conflict()

    previous = await _highest_consent_row(db, user_id)
    seq = (previous.sequence_no + 1) if previous is not None else 1
    row = AgentCloudConsent(
        user_id=_to_uuid(user_id),
        purpose=AGENT_CLOUD_PROCESSING_PURPOSE,
        provider_id=current_provider_id,
        disclosure_version=current_disclosure_version,
        status=CONSENT_GRANTED,
        sequence_no=seq,
    )
    db.add(row)
    await db.flush()
    await _record_idempotency(
        db, user_id, OP_AGENT_CONSENT_GRANT, idempotency_key, request_hash,
        str(row.consent_id), now,
    )
    await db.commit()
    return ConsentGrantResult(row.consent_id, seq, CONSENT_GRANTED, False)


async def _load_consent(
    db: AsyncSession, user_id: str, consent_id: uuid.UUID
) -> Optional[AgentCloudConsent]:
    res = await db.execute(
        select(AgentCloudConsent).where(
            AgentCloudConsent.user_id == _to_uuid(user_id),
            AgentCloudConsent.consent_id == consent_id,
        )
    )
    return res.scalar_one_or_none()


async def withdraw_consent(
    db: AsyncSession,
    user_id: str,
    *,
    idempotency_key: str,
    now: Optional[datetime] = None,
) -> ConsentGrantResult:
    """Withdraw consent: append a withdrawal event and immediately invalidate +
    scrub every pending proposal in the SAME owner transaction.

    Withdrawal is idempotent via the ``agent_consent_withdraw`` namespace. Any
    failure rolls the whole transaction back, so consent is never left active
    while pending proposals are partially scrubbed (spec Consent And Privacy
    Gate).
    """
    now = now or _now()
    await acquire_user_transaction_lock(db, user_id)
    request_hash = hash_request(
        {"op": "consent_withdraw", "purpose": AGENT_CLOUD_PROCESSING_PURPOSE}
    )
    action, record = await _check_idempotency(
        db, user_id, OP_AGENT_CONSENT_WITHDRAW, idempotency_key, request_hash, now
    )
    if action == "replay":
        result_ref = record.result_ref
        await db.rollback()
        assert result_ref is not None
        still = await _load_consent(db, user_id, uuid.UUID(result_ref))
        if still is None:
            raise _gone()
        return ConsentGrantResult(still.consent_id, still.sequence_no, still.status, True)
    if action == "conflict":
        raise _idempotency_conflict()

    previous = await _highest_consent_row(db, user_id)
    seq = (previous.sequence_no + 1) if previous is not None else 1
    row = AgentCloudConsent(
        user_id=_to_uuid(user_id),
        purpose=AGENT_CLOUD_PROCESSING_PURPOSE,
        provider_id=previous.provider_id if previous is not None else "",
        disclosure_version=(
            previous.disclosure_version if previous is not None else ""
        ),
        status=CONSENT_WITHDRAWN,
        sequence_no=seq,
    )
    db.add(row)
    await db.flush()
    # Same-transaction invalidation + scrub of all pending proposals.
    await _invalidate_pending_proposals_for_user(db, user_id, now)
    await _record_idempotency(
        db, user_id, OP_AGENT_CONSENT_WITHDRAW, idempotency_key, request_hash,
        str(row.consent_id), now,
    )
    await db.commit()
    return ConsentGrantResult(row.consent_id, seq, CONSENT_WITHDRAWN, False)


# --------------------------------------------------------------------------- #
# Run + Tool event audit                                                       #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RunRecordResult:
    run: AgentRun
    created: bool


async def record_run(
    db: AsyncSession,
    user_id: str,
    *,
    client_turn_id: str,
    entry_type: str,
    intent_code: Optional[str] = None,
    context_fingerprint: Optional[str] = None,
    fingerprint_key_version: Optional[str] = None,
    prompt_version: Optional[str] = None,
    provider_id: Optional[str] = None,
    model_version: Optional[str] = None,
    policy_version: Optional[str] = None,
    status: str = "started",
    result_code: Optional[str] = None,
    tool_call_count: int = 0,
    started_at: Optional[datetime] = None,
    expires_at: Optional[datetime] = None,
    now: Optional[datetime] = None,
    commit: bool = True,
) -> RunRecordResult:
    """Record one run; a duplicate ``client_turn_id`` returns the prior run.

    A duplicate turn never creates a second proposal: the caller receives
    ``created=False`` and the existing run, and must replay prior structured
    status/proposal metadata without prose replay (spec API Contracts). The
    per-user lock serializes duplicate-turn resolution.
    """
    now = now or _now()
    await acquire_user_transaction_lock(db, user_id)
    existing = (
        await db.execute(
            select(AgentRun).where(
                AgentRun.user_id == _to_uuid(user_id),
                AgentRun.client_turn_id == client_turn_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Read-only branch: no changes were made, so do not rollback (which
        # would expire the returned ORM object). The per-user lock and any open
        # transaction are released by the caller's session/transaction boundary.
        return RunRecordResult(existing, created=False)

    run = AgentRun(
        user_id=_to_uuid(user_id),
        client_turn_id=client_turn_id,
        entry_type=entry_type,
        intent_code=intent_code,
        context_fingerprint=context_fingerprint,
        fingerprint_key_version=fingerprint_key_version,
        prompt_version=prompt_version,
        provider_id=provider_id,
        model_version=model_version,
        policy_version=policy_version,
        status=status,
        result_code=result_code,
        tool_call_count=tool_call_count,
        started_at=started_at or now,
        expires_at=expires_at or (now + RUN_RETENTION),
    )
    db.add(run)
    if commit:
        await db.commit()
    else:
        await db.flush()
    return RunRecordResult(run, created=True)


async def load_run_for_client_turn(
    db: AsyncSession, user_id: str, client_turn_id: str
) -> Optional[AgentRun]:
    """Load prior owned turn metadata without creating or mutating state."""
    return (
        await db.execute(
            select(AgentRun).where(
                AgentRun.user_id == _to_uuid(user_id),
                AgentRun.client_turn_id == client_turn_id,
            )
        )
    ).scalar_one_or_none()


async def load_proposal_for_run(
    db: AsyncSession, user_id: str, run_id
) -> Optional[AgentActionProposal]:
    """Load the one owned proposal associated with a run, if present."""
    return (
        await db.execute(
            select(AgentActionProposal).where(
                AgentActionProposal.user_id == _to_uuid(user_id),
                AgentActionProposal.run_id
                == (_to_uuid(run_id) if not isinstance(run_id, uuid.UUID) else run_id),
            )
        )
    ).scalar_one_or_none()


async def record_tool_event(
    db: AsyncSession,
    *,
    run_id,
    user_id: str,
    tool_name: str,
    side_effect_class: str,
    status: str,
    request_fingerprint: Optional[str] = None,
    fingerprint_key_version: Optional[str] = None,
    policy_version: Optional[str] = None,
    context_version: Optional[str] = None,
    result_code: Optional[str] = None,
    result_ref: Optional[str] = None,
) -> AgentToolEvent:
    """Record one privacy-minimized Tool event (metadata/fingerprints only).

    Never accepts raw arguments or a Tool result payload.
    """
    owned_run = (
        await db.execute(
            select(AgentRun.run_id).where(
                AgentRun.run_id
                == (_to_uuid(run_id) if not isinstance(run_id, uuid.UUID) else run_id),
                AgentRun.user_id == _to_uuid(user_id),
            )
        )
    ).scalar_one_or_none()
    if owned_run is None:
        raise AppException(
            404, "未找到可访问的对应内容", ResultCode.ENTITY_NOT_FOUND
        )
    event = AgentToolEvent(
        run_id=_to_uuid(run_id) if not isinstance(run_id, uuid.UUID) else run_id,
        user_id=_to_uuid(user_id),
        tool_name=tool_name,
        side_effect_class=side_effect_class,
        request_fingerprint=request_fingerprint,
        fingerprint_key_version=fingerprint_key_version,
        policy_version=policy_version,
        context_version=context_version,
        status=status,
        result_code=result_code,
        result_ref=result_ref,
    )
    db.add(event)
    await db.flush()
    return event


# --------------------------------------------------------------------------- #
# Proposal lifecycle                                                           #
# --------------------------------------------------------------------------- #


def _apply_terminal(
    proposal: AgentActionProposal,
    status: str,
    now: datetime,
    *,
    result_ref: Optional[str] = None,
    result_code: Optional[str] = None,
) -> None:
    """Move a proposal to a terminal state and scrub its arguments.

    Validates the transition is legal (only ``pending`` may go terminal) and
    ALWAYS nulls ``arguments_json`` so typed arguments exist only while pending.
    No commit: callers commit the surrounding unit of work.
    """
    if status not in PROPOSAL_TERMINAL_STATUSES:
        raise AppException(500, "非法 proposal 终态", "agent_proposal_bad_status")
    if proposal.status != PROPOSAL_PENDING:
        raise AppException(409, "该 proposal 已结束", "agent_proposal_already_terminal")
    proposal.status = status
    proposal.arguments_json = None
    proposal.result_ref = result_ref
    proposal.result_code = result_code
    proposal.updated_at = now


async def _invalidate_pending_proposals_for_user(
    db: AsyncSession, user_id: str, now: datetime
) -> int:
    """Invalidate + scrub every pending proposal for the user (no commit)."""
    res = await db.execute(
        select(AgentActionProposal).where(
            AgentActionProposal.user_id == _to_uuid(user_id),
            AgentActionProposal.status == PROPOSAL_PENDING,
        )
    )
    count = 0
    for proposal in res.scalars().all():
        _apply_terminal(proposal, PROPOSAL_INVALIDATED, now, result_code="invalidated")
        count += 1
    return count


async def expire_due_proposals(
    db: AsyncSession, user_id: str, now: Optional[datetime] = None
) -> int:
    """Lazy-expire pending proposals past their 15-minute TTL (turn/confirm
    boundary). Commits its own transaction; returns the count expired.
    """
    now = now or _now()
    await acquire_user_transaction_lock(db, user_id)
    res = await db.execute(
        select(AgentActionProposal).where(
            AgentActionProposal.user_id == _to_uuid(user_id),
            AgentActionProposal.status == PROPOSAL_PENDING,
            AgentActionProposal.expires_at <= now,
        )
    )
    count = 0
    for proposal in res.scalars().all():
        _apply_terminal(proposal, PROPOSAL_EXPIRED, now, result_code="expired")
        count += 1
    if count:
        await db.commit()
    else:
        await db.rollback()
    return count


@dataclass(frozen=True)
class ProposalCreate:
    proposal_id: uuid.UUID
    expires_at: datetime
    arguments_hash: str


async def create_proposal(
    db: AsyncSession,
    *,
    run_id,
    user_id: str,
    tool_name: str,
    arguments_json: dict,
    arguments_hash: str,
    iana_timezone: str,
    context_fingerprint: Optional[str] = None,
    fingerprint_key_version: Optional[str] = None,
    context_version: Optional[str] = None,
    policy_version: Optional[str] = None,
    now: Optional[datetime] = None,
    ttl: Optional[timedelta] = None,
    commit: bool = True,
) -> ProposalCreate:
    """Create one owned pending proposal. No domain write occurs here.

    The persistence boundary independently validates and normalizes the closed
    write-action schema, recomputes the keyed argument fingerprint, verifies
    run ownership/current consent, and serializes creation with withdrawal and
    Agent-data deletion. Only ``pending`` retains arguments.
    """
    from app.agent import action_tools

    now = now or _now()
    if not validate_iana_timezone(iana_timezone):
        raise AppException(400, "时区标识无效", ResultCode.INVALID_TIMEZONE)
    try:
        validated = action_tools.validate_arguments(tool_name, arguments_json)
        computed_arguments = action_tools.compute_arguments_fingerprint(validated)
    except AgentError as exc:
        raise AppException(400, "操作参数无效", exc.code) from exc
    if not hmac.compare_digest(arguments_hash, computed_arguments.value):
        raise AppException(409, "操作参数校验失败", AGENT_CONTEXT_STALE)
    if (
        fingerprint_key_version is not None
        and fingerprint_key_version != computed_arguments.key_version
    ):
        raise AppException(409, "指纹密钥版本不一致", AGENT_CONTEXT_STALE)

    await acquire_user_transaction_lock(db, user_id)
    owned_run = (
        await db.execute(
            select(AgentRun.run_id).where(
                AgentRun.run_id
                == (_to_uuid(run_id) if not isinstance(run_id, uuid.UUID) else run_id),
                AgentRun.user_id == _to_uuid(user_id),
            )
        )
    ).scalar_one_or_none()
    if owned_run is None:
        raise AppException(
            404, "未找到可访问的对应内容", ResultCode.ENTITY_NOT_FOUND
        )
    if not (await active_consent(db, user_id)).active:
        raise AppException(409, "需要有效的云处理同意", "agent_consent_required")
    existing = (
        await db.execute(
            select(AgentActionProposal.proposal_id).where(
                AgentActionProposal.run_id == owned_run
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise AppException(409, "该轮次已存在操作提案", "agent_proposal_already_exists")

    expires_at = now + (ttl or PROPOSAL_TTL)
    proposal = AgentActionProposal(
        run_id=_to_uuid(run_id) if not isinstance(run_id, uuid.UUID) else run_id,
        user_id=_to_uuid(user_id),
        tool_name=tool_name,
        arguments_json=validated.model_dump(mode="json"),
        arguments_hash=computed_arguments.value,
        context_fingerprint=context_fingerprint,
        fingerprint_key_version=computed_arguments.key_version,
        context_version=context_version,
        policy_version=policy_version,
        iana_timezone=iana_timezone,
        status=PROPOSAL_PENDING,
        expires_at=expires_at,
    )
    db.add(proposal)
    if commit:
        await db.commit()
    else:
        await db.flush()
    return ProposalCreate(
        proposal.proposal_id, expires_at, computed_arguments.value
    )


async def load_owned_proposal(
    db: AsyncSession, user_id: str, proposal_id
) -> Optional[AgentActionProposal]:
    """Ownership-scoped proposal load (non-enumerating: missing == foreign)."""
    res = await db.execute(
        select(AgentActionProposal).where(
            AgentActionProposal.user_id == _to_uuid(user_id),
            AgentActionProposal.proposal_id
            == (_to_uuid(proposal_id) if not isinstance(proposal_id, uuid.UUID) else proposal_id),
        )
    )
    return res.scalar_one_or_none()


async def load_pending_owned_proposal(
    db: AsyncSession, user_id: str, proposal_id, now: Optional[datetime] = None
):
    """Load a proposal and, if it is pending but past TTL, expire it first.

    Returns ``(proposal, expired_now: bool)``. ``expired_now`` is true when the
    proposal was lazily expired by this call (the caller should report
    ``agent_action_expired``). A non-pending proposal is returned as-is.
    """
    now = now or _now()
    proposal = await load_owned_proposal(db, user_id, proposal_id)
    if proposal is None:
        return None, False
    if (
        proposal.status == PROPOSAL_PENDING
        and _as_utc(proposal.expires_at) <= now
    ):
        _apply_terminal(proposal, PROPOSAL_EXPIRED, now, result_code="expired")
        await db.flush()
        return proposal, True
    return proposal, False


async def cancel_proposal(
    db: AsyncSession, user_id: str, proposal_id, now: Optional[datetime] = None
) -> AgentActionProposal:
    """Cancel one owned pending proposal: idempotent terminal + argument scrub."""
    now = now or _now()
    await acquire_user_transaction_lock(db, user_id)
    proposal = await load_owned_proposal(db, user_id, proposal_id)
    if proposal is None:
        raise AppException(404, "未找到可访问的对应内容", "agent_entity_not_found")
    if proposal.status == PROPOSAL_CANCELLED:
        # Read-only idempotent branch: nothing to undo, so do not rollback.
        return proposal
    if proposal.status != PROPOSAL_PENDING:
        raise AppException(409, "该 proposal 已结束", "agent_proposal_already_terminal")
    _apply_terminal(proposal, PROPOSAL_CANCELLED, now, result_code="cancelled")
    await db.commit()
    return proposal


def mark_executed(
    proposal: AgentActionProposal,
    *,
    result_ref: Optional[str],
    result_code: Optional[str],
    now: datetime,
) -> None:
    """Terminal executed transition + scrub (no commit; caller commits UoW)."""
    _apply_terminal(
        proposal, PROPOSAL_EXECUTED, now, result_ref=result_ref, result_code=result_code
    )


def mark_invalidated(
    proposal: AgentActionProposal,
    *,
    result_code: str,
    now: datetime,
) -> None:
    """Terminal invalidated transition + scrub (no commit; caller commits UoW).

    Used for deterministic stale/safety/validation rejections: the proposal ends
    with no domain write.
    """
    _apply_terminal(
        proposal, PROPOSAL_INVALIDATED, now, result_code=result_code
    )


# --------------------------------------------------------------------------- #
# Key rotation                                                                 #
# --------------------------------------------------------------------------- #


async def scrub_pending_on_key_change(
    db: AsyncSession, user_id: str, current_key_version: str, now: Optional[datetime] = None
) -> int:
    """Invalidate + scrub pending proposals whose fingerprint key version differs
    from the current configured version, BEFORE new runs/proposals are accepted.

    A key/version rotation must invalidate pending proposals (their stored
    fingerprints are no longer comparable); retained old audit fingerprints
    remain deletable opaque metadata but cannot be re-verified (spec Provider
    And Orchestrator Contract; ADR-0004).
    """
    now = now or _now()
    await acquire_user_transaction_lock(db, user_id)
    res = await db.execute(
        select(AgentActionProposal).where(
            AgentActionProposal.user_id == _to_uuid(user_id),
            AgentActionProposal.status == PROPOSAL_PENDING,
        )
    )
    count = 0
    for proposal in res.scalars().all():
        if (
            proposal.fingerprint_key_version is None
            or proposal.fingerprint_key_version != current_key_version
        ):
            _apply_terminal(
                proposal, PROPOSAL_INVALIDATED, now, result_code="key_rotated"
            )
            count += 1
    if count:
        await db.commit()
    else:
        await db.rollback()
    return count


# --------------------------------------------------------------------------- #
# Retention (best-effort, no scheduler)                                        #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CleanupResult:
    runs_deleted: int
    tool_events_deleted: int
    proposals_deleted: int


async def cleanup_expired_runs(
    db: AsyncSession, now: Optional[datetime] = None
) -> CleanupResult:
    """Delete runs (and their dependent tool events / proposals) older than the
    30-day retention window.

    Independently callable, idempotent, and concurrency-safe: the ``WHERE`` is
    deterministic so a repeated/competing run deletes nothing extra. Phase 5 has
    no scheduler, so this is best-effort at app startup / Agent API boundaries
    (spec Persistence; ADR-0004). It does not touch consent rows (consent lasts
    until Agent-data/account deletion) and does not delete non-Agent data.
    """
    now = now or _now()
    expired_ids = (
        await db.execute(
            select(AgentRun.run_id).where(
                AgentRun.expires_at.is_not(None),
                AgentRun.expires_at <= now,
            )
        )
    ).scalars().all()
    if not expired_ids:
        return CleanupResult(0, 0, 0)
    ids = list(expired_ids)
    te = (
        await db.execute(
            delete(AgentToolEvent).where(AgentToolEvent.run_id.in_(ids))
        )
    ).rowcount or 0
    pp = (
        await db.execute(
            delete(AgentActionProposal).where(AgentActionProposal.run_id.in_(ids))
        )
    ).rowcount or 0
    rr = (
        await db.execute(delete(AgentRun).where(AgentRun.run_id.in_(ids)))
    ).rowcount or 0
    await db.commit()
    return CleanupResult(rr, te, pp)


# --------------------------------------------------------------------------- #
# Agent-data deletion                                                          #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AgentDataDeletionResult:
    consents_deleted: int
    runs_deleted: int
    tool_events_deleted: int
    proposals_deleted: int
    idempotency_deleted: int


async def delete_agent_data(
    db: AsyncSession, user_id: str
) -> AgentDataDeletionResult:
    """DELETE /agent/data: remove the caller's Agent rows and the three Agent
    idempotency namespaces, preserving independently owned health/posture/
    training domain rows and their domain idempotency evidence.

    Serialized by the per-user lock so it cannot race a concurrent proposal.
    The three namespaces are deleted by ``operation`` (not all user idempotency),
    so training ``plan_generate``/``session_substitute``/``session_feedback``
    and posture evidence remain (spec Persistence; Acceptance #19).
    """
    await acquire_user_transaction_lock(db, user_id)
    uid = _to_uuid(user_id)
    pp = (
        await db.execute(
            delete(AgentActionProposal).where(AgentActionProposal.user_id == uid)
        )
    ).rowcount or 0
    te = (
        await db.execute(
            delete(AgentToolEvent).where(AgentToolEvent.user_id == uid)
        )
    ).rowcount or 0
    rr = (await db.execute(delete(AgentRun).where(AgentRun.user_id == uid))).rowcount or 0
    cc = (
        await db.execute(
            delete(AgentCloudConsent).where(AgentCloudConsent.user_id == uid)
        )
    ).rowcount or 0
    ide = (
        await db.execute(
            delete(IdempotencyRecord).where(
                IdempotencyRecord.user_id == uid,
                IdempotencyRecord.operation.in_(_AGENT_NAMESPACES),
            )
        )
    ).rowcount or 0
    await db.commit()
    return AgentDataDeletionResult(cc, rr, te, pp, ide)


# --------------------------------------------------------------------------- #
# Confirmed write execution (Task 3)                                          #
# --------------------------------------------------------------------------- #
#
# ``confirm_proposal`` executes one owned pending proposal inside a single unit
# of work: per-user lock -> lazy expiry -> consent check -> agent_action_confirm
# idempotency -> latest-context revalidation + fingerprint comparison ->
# (training) domain two-layer idempotency consistency -> transaction-neutral
# domain side effect (flush only) -> tool event + proposal terminal state +
# commit. A deterministic stale/safety/validation rejection invalidates +
# scrubs the proposal with NO domain write; a transient exception rolls the
# whole unit of work back and leaves the proposal pending/retriable.

AGENT_CONTEXT_STALE = "agent_context_stale"
AGENT_IDEMPOTENCY_INCONSISTENT = "agent_idempotency_inconsistent"


@dataclass(frozen=True)
class ConfirmationResult:
    proposal_id: uuid.UUID
    status: str  # executed | invalidated | replayed | expired
    result_ref: Optional[str]
    result_code: str


def _domain_idempotency_key(proposal_id) -> str:
    """Server-derived per-proposal domain idempotency key (training two-layer).

    Reuses the existing plan_generate/session_substitute/session_feedback
    namespaces with a derived key scoped to this proposal (spec Persistence).
    """
    pid = proposal_id if isinstance(proposal_id, uuid.UUID) else uuid.UUID(str(proposal_id))
    return f"agent:{pid}"


def _agent_confirm_request_hash(proposal_id) -> str:
    pid = proposal_id if isinstance(proposal_id, uuid.UUID) else uuid.UUID(str(proposal_id))
    return hash_request({"op": "agent_action_confirm", "proposal_id": str(pid)})


async def _reject_proposal(
    db: AsyncSession,
    proposal: AgentActionProposal,
    *,
    result_code: str,
    now: datetime,
    confirm_key: Optional[str] = None,
    confirm_request_hash: Optional[str] = None,
) -> ConfirmationResult:
    """Deterministic rejection: invalidate + scrub the proposal with NO domain
    write, optionally record the agent_action_confirm terminal result, commit."""
    mark_invalidated(proposal, result_code=result_code, now=now)
    if confirm_key is not None and confirm_request_hash is not None:
        await _record_idempotency(
            db, str(proposal.user_id), OP_AGENT_ACTION_CONFIRM, confirm_key,
            confirm_request_hash, "", now, status="invalidated",
        )
    await db.commit()
    return ConfirmationResult(proposal.proposal_id, PROPOSAL_INVALIDATED, None, result_code)


async def confirm_proposal(
    db: AsyncSession,
    user_id: str,
    proposal_id,
    *,
    idempotency_key: str,
    iana_timezone: Optional[str] = None,
    now: Optional[datetime] = None,
) -> ConfirmationResult:
    """Execute one owned pending proposal after authenticated confirmation.

    Re-validates the latest context/safety, enforces two-layer idempotency
    (training) or single-layer (health), and atomically records the domain
    result, Tool event, idempotency, and proposal terminal state. The model
    never calls this; only the authenticated confirmation API does.
    """
    from app.agent import action_tools

    now = now or _now()
    await acquire_user_transaction_lock(db, user_id)

    # Lazy expiry at the confirm boundary.
    proposal, expired_now = await load_pending_owned_proposal(db, user_id, proposal_id, now)
    if proposal is None:
        raise AppException(404, "未找到可访问的对应内容", "agent_entity_not_found")
    pid = proposal.proposal_id
    if expired_now or proposal.status == PROPOSAL_EXPIRED:
        await db.commit()
        return ConfirmationResult(pid, PROPOSAL_EXPIRED, None, "agent_action_expired")

    # Agent-layer idempotency (agent_action_confirm) is resolved FIRST so that a
    # same-key replay returns the recorded terminal result read-only (even for a
    # proposal that has since reached a terminal state), before any consent or
    # status rejection. Attributes are captured before the lock-releasing
    # rollback so no expired-object lazy load occurs.
    confirm_hash = _agent_confirm_request_hash(pid)
    action, record = await _check_idempotency(
        db, user_id, OP_AGENT_ACTION_CONFIRM, idempotency_key, confirm_hash, now
    )
    if action == "replay":
        result_ref = record.result_ref or None
        proposal_result_ref = proposal.result_ref or None
        inconsistent = (
            proposal.status == PROPOSAL_PENDING
            or result_ref != proposal_result_ref
        )
        domain_operation = action_tools.domain_operation_for(proposal.tool_name)
        if not inconsistent and proposal.status == PROPOSAL_EXECUTED and domain_operation:
            domain_record = (
                await db.execute(
                    select(IdempotencyRecord).where(
                        IdempotencyRecord.user_id == _to_uuid(user_id),
                        IdempotencyRecord.operation == domain_operation,
                        IdempotencyRecord.idempotency_key
                        == _domain_idempotency_key(proposal.proposal_id),
                    )
                )
            ).scalar_one_or_none()
            inconsistent = (
                domain_record is None
                or (domain_record.result_ref or None) != proposal_result_ref
            )
        result_code = proposal.result_code or record.status or "replayed"
        await db.rollback()
        if inconsistent:
            raise AppException(
                409,
                "幂等记录状态不一致",
                AGENT_IDEMPOTENCY_INCONSISTENT,
            )
        return ConfirmationResult(pid, "replayed", result_ref, result_code)
    if action == "conflict":
        raise _idempotency_conflict()

    # Not a replay. A non-pending proposal cannot be (re)executed with a new key.
    if proposal.status != PROPOSAL_PENDING:
        status = proposal.status
        rref = proposal.result_ref
        rcode = proposal.result_code
        await db.rollback()
        return ConfirmationResult(pid, status, rref, rcode or "agent_action_invalidated")

    consent = await active_consent(db, user_id)
    if not consent.active:
        return await _reject_proposal(
            db, proposal, result_code="agent_consent_required", now=now,
            confirm_key=idempotency_key, confirm_request_hash=confirm_hash,
        )

    # (proceed path continues below)

    # Latest-context revalidation (deterministic; may raise on safety/stale).
    stored_timezone = proposal.iana_timezone
    if iana_timezone is not None and iana_timezone != stored_timezone:
        return await _reject_proposal(
            db,
            proposal,
            result_code=ResultCode.INVALID_TIMEZONE,
            now=now,
            confirm_key=idempotency_key,
            confirm_request_hash=confirm_hash,
        )
    try:
        arguments = action_tools.validate_arguments(
            proposal.tool_name, proposal.arguments_json
        )
        current_arguments_fp = action_tools.compute_arguments_fingerprint(arguments)
    except AgentError as exc:
        return await _reject_proposal(
            db,
            proposal,
            result_code=exc.code,
            now=now,
            confirm_key=idempotency_key,
            confirm_request_hash=confirm_hash,
        )
    if (
        not hmac.compare_digest(current_arguments_fp.value, proposal.arguments_hash)
        or current_arguments_fp.key_version
        != (proposal.fingerprint_key_version or "")
    ):
        return await _reject_proposal(
            db,
            proposal,
            result_code=AGENT_CONTEXT_STALE,
            now=now,
            confirm_key=idempotency_key,
            confirm_request_hash=confirm_hash,
        )
    try:
        prepared = await action_tools.prepare(
            db, proposal.tool_name, arguments, user_id,
            iana_timezone=stored_timezone, now=now,
        )
    except AppException as exc:
        return await _reject_proposal(
            db, proposal, result_code=exc.code or "agent_action_invalidated", now=now,
            confirm_key=idempotency_key, confirm_request_hash=confirm_hash,
        )

    # Context-fingerprint staleness: the context the user saw must match now.
    current_fp = action_tools.compute_context_fingerprint(prepared.context_fingerprint_payload)
    if (
        proposal.context_fingerprint is None
        or current_fp.value != proposal.context_fingerprint
        or (proposal.fingerprint_key_version or "") != current_fp.key_version
    ):
        return await _reject_proposal(
            db, proposal, result_code=AGENT_CONTEXT_STALE, now=now,
            confirm_key=idempotency_key, confirm_request_hash=confirm_hash,
        )

    # Domain two-layer idempotency (training only).
    domain_key: Optional[str] = None
    if prepared.domain_operation:
        domain_key = _domain_idempotency_key(proposal.proposal_id)
        dom_action, dom_record = await _check_idempotency(
            db, user_id, prepared.domain_operation, domain_key,
            prepared.domain_request_hash, now,
        )
        if dom_action == "replay":
            # Domain already recorded but agent did not -> partial inconsistency.
            return await _reject_proposal(
                db, proposal, result_code=AGENT_IDEMPOTENCY_INCONSISTENT, now=now,
                confirm_key=idempotency_key, confirm_request_hash=confirm_hash,
            )
        if dom_action == "conflict":
            return await _reject_proposal(
                db,
                proposal,
                result_code=AGENT_IDEMPOTENCY_INCONSISTENT,
                now=now,
                confirm_key=idempotency_key,
                confirm_request_hash=confirm_hash,
            )

    # Execute the transaction-neutral domain side effect (flush only). A
    # deterministic rejection raised by the executor (e.g. an existing
    # abnormal-pain safety signal surfacing at execution time) invalidates the
    # proposal with NO domain write; a transient exception propagates and rolls
    # the whole unit of work back, leaving the proposal pending/retriable.
    try:
        execution = await prepared.execute()
    except AppException as exc:
        return await _reject_proposal(
            db, proposal, result_code=exc.code or "agent_action_invalidated", now=now,
            confirm_key=idempotency_key, confirm_request_hash=confirm_hash,
        )
    result_ref = execution.result_ref

    # Record domain idempotency (training two-layer) + agent idempotency.
    if prepared.domain_operation and domain_key is not None:
        await _record_idempotency(
            db, user_id, prepared.domain_operation, domain_key,
            prepared.domain_request_hash, execution.domain_result_ref or result_ref, now,
        )
    await _record_idempotency(
        db, user_id, OP_AGENT_ACTION_CONFIRM, idempotency_key, confirm_hash,
        result_ref, now,
    )

    # Tool event + proposal terminal state.
    await record_tool_event(
        db,
        run_id=proposal.run_id,
        user_id=user_id,
        tool_name=proposal.tool_name,
        side_effect_class="write",
        status=execution.result_code,
        request_fingerprint=proposal.arguments_hash,
        fingerprint_key_version=proposal.fingerprint_key_version,
        result_code=execution.result_code,
        result_ref=result_ref,
    )
    mark_executed(proposal, result_ref=result_ref, result_code=execution.result_code, now=now)
    await db.commit()
    return ConfirmationResult(
        proposal.proposal_id, PROPOSAL_EXECUTED, result_ref, execution.result_code
    )


__all__ = [
    "OP_AGENT_ACTION_CONFIRM",
    "OP_AGENT_CONSENT_GRANT",
    "OP_AGENT_CONSENT_WITHDRAW",
    "PROPOSAL_TTL",
    "RUN_RETENTION",
    "IDEMPOTENCY_TTL",
    "hash_request",
    "ConsentGrantResult",
    "grant_consent",
    "withdraw_consent",
    "active_consent",
    "RunRecordResult",
    "record_run",
    "load_run_for_client_turn",
    "load_proposal_for_run",
    "record_tool_event",
    "ProposalCreate",
    "create_proposal",
    "load_owned_proposal",
    "load_pending_owned_proposal",
    "cancel_proposal",
    "expire_due_proposals",
    "mark_executed",
    "mark_invalidated",
    "scrub_pending_on_key_change",
    "CleanupResult",
    "cleanup_expired_runs",
    "AgentDataDeletionResult",
    "delete_agent_data",
    "AGENT_CONTEXT_STALE",
    "AGENT_IDEMPOTENCY_INCONSISTENT",
    "ConfirmationResult",
    "confirm_proposal",
]
