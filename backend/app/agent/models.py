"""Phase 5 Agent MVP persistence models (Task 2).

Four narrowly scoped tables backing the Agent consent, audit, and proposal
lifecycle (spec ``2026-07-28-agent-mvp.md`` Persistence And State; ADR-0004):

- ``agent_cloud_consents``  immutable cloud-processing consent events.
- ``agent_runs``            privacy-minimized run audit metadata.
- ``agent_tool_events``     privacy-minimized Tool event metadata.
- ``agent_action_proposals`` short-lived typed write proposals.

Privacy minimization is structural: NONE of these tables has a column for raw
user text, assistant prose, raw context, prompts, provider request/response
payloads, raw Tool arguments/results, photos, or health identifiers. Only
stable codes, versions, counts, keyed HMAC fingerprints, and short bounded
typed proposal arguments (retained only while ``pending``) are stored. Low-
entropy health values are never reduced to a plain hash; every fingerprint is a
keyed HMAC produced by ``app.agent.fingerprints`` (Acceptance #15, #16).

Ownership is enforced everywhere via the JWT-derived ``user_id`` (UUID FK to
``users.id``, ownership-indexed on every table), so cross-user access is
impossible by construction and cross-user existence is non-enumerable.

Idempotency is NOT a new table: Phase 5 reuses the existing shared
``idempotency_records`` table (ADR-0001) with three new ``operation`` values
(``agent_action_confirm``, ``agent_consent_grant``, ``agent_consent_withdraw``).

SQLite/PostgreSQL parity: enum/bounds are validated at the application layer
(same convention as the health/posture/training domains); the migration adds
CHECK constraints for the closed consent/proposal status lifecycles that both
databases enforce, and the state machine in ``app.agent.persistence`` enforces
every legal transition deterministically regardless of dialect.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Fixed consent purpose. The server binds the current provider/disclosure; the
# client/model never selects a purpose or provider (spec Consent And Privacy Gate).
AGENT_CLOUD_PROCESSING_PURPOSE = "agent_cloud_processing"

# Closed lifecycle statuses (mirrored as CHECK constraints in migration 0008).
CONSENT_GRANTED = "granted"
CONSENT_WITHDRAWN = "withdrawn"

PROPOSAL_PENDING = "pending"
PROPOSAL_EXECUTED = "executed"
PROPOSAL_INVALIDATED = "invalidated"
PROPOSAL_EXPIRED = "expired"
PROPOSAL_CANCELLED = "cancelled"
PROPOSAL_TERMINAL_STATUSES = frozenset(
    {PROPOSAL_EXECUTED, PROPOSAL_INVALIDATED, PROPOSAL_EXPIRED, PROPOSAL_CANCELLED}
)


class AgentCloudConsent(Base):
    """Immutable Agent cloud-processing consent events (spec Persistence).

    Append-only event log: every grant/withdraw appends one row with the next
    per-user ``sequence_no``, serialized by the existing per-user transaction
    lock. The current active state is derived deterministically from the
    highest ``sequence_no`` (a later withdrawal invalidates every earlier grant
    without timestamp-tie ambiguity). ``UniqueConstraint(user_id, purpose,
    sequence_no)`` guarantees monotonic sequences.

    No client-selected purpose/provider: the server binds the current
    disclosure. ``accepted`` acknowledgement equality with current server
    configuration is enforced in ``app.agent.persistence`` (returns
    ``agent_disclosure_stale`` on a race).
    """

    __tablename__ = "agent_cloud_consents"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "purpose",
            "sequence_no",
            name="uq_agent_cloud_consents_user_purpose_seq",
        ),
        CheckConstraint(
            "status IN ('granted', 'withdrawn')",
            name="ck_agent_cloud_consents_status",
        ),
        Index("ix_agent_cloud_consents_user", "user_id"),
    )

    consent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(60), nullable=False)
    disclosure_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AgentRun(Base):
    """Privacy-minimized Agent run audit metadata (spec Persistence).

    Unique ``(user_id, client_turn_id)`` so a duplicate turn returns the prior
    structured status/proposal metadata without prose replay and never creates a
    second proposal. There is NO column for user message, assistant message,
    raw context, prompt, or model response: only stable codes, versions, keyed
    context fingerprint, counts, and timing. Eligible for 30-day cleanup.
    """

    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "client_turn_id",
            name="uq_agent_runs_user_turn",
        ),
        Index("ix_agent_runs_user", "user_id"),
        Index("ix_agent_runs_expires_at", "expires_at"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    client_turn_id: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(30), nullable=False)
    intent_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    context_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    fingerprint_key_version: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )
    prompt_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    provider_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    policy_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    result_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    tool_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AgentToolEvent(Base):
    """Privacy-minimized Agent Tool event metadata (spec Persistence).

    One row per Tool call inside a run. Stores stable ``tool_name``,
    side-effect class, request fingerprint (keyed HMAC), status/result codes,
    optional domain ``result_ref``, and the policy/context/fingerprint-key
    versions - never the raw arguments or the Tool result payload. Follows the
    parent run's 30-day retention and cascade cleanup.
    """

    __tablename__ = "agent_tool_events"
    __table_args__ = (
        Index("ix_agent_tool_events_run", "run_id"),
        Index("ix_agent_tool_events_user", "user_id"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(60), nullable=False)
    side_effect_class: Mapped[str] = mapped_column(String(20), nullable=False)
    request_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    fingerprint_key_version: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )
    policy_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    context_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    result_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    result_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AgentActionProposal(Base):
    """Short-lived typed Agent write proposal (spec Persistence, Write
    Confirmation Semantics).

    Statuses: ``pending -> executed | invalidated | expired | cancelled``.
    Only ``pending`` rows retain typed bounded ``arguments_json``; every
    terminal transition, consent withdrawal, Agent-data deletion, and lazy
    expiry scrubs (NULLs) the arguments. Arguments never contain free text,
    photos, secrets, actor IDs, or safety claims (enforced by the strict
    ``extra="forbid"`` action schemas in ``app.agent.schemas``).

    Confirmation reuses the shared ``idempotency_records`` operation
    ``agent_action_confirm``. ``arguments_hash``/context/request fingerprints
    are keyed HMAC-SHA256 with the dedicated Agent audit key and stored key
    version; a key/version change invalidates and scrubs pending proposals
    before new runs are accepted.
    """

    __tablename__ = "agent_action_proposals"
    __table_args__ = (
        Index(
            "ix_agent_action_proposals_user_status",
            "user_id",
            "status",
        ),
        Index("ix_agent_action_proposals_run", "run_id"),
        Index("ix_agent_action_proposals_expires_at", "expires_at"),
        CheckConstraint(
            "status IN ('pending', 'executed', 'invalidated', 'expired', 'cancelled')",
            name="ck_agent_action_proposals_status",
        ),
    )

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.run_id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(60), nullable=False)
    # Typed bounded arguments; retained ONLY while status == pending. Scrubbed
    # (NULL) on every terminal transition / withdrawal / deletion / lazy expiry.
    arguments_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    arguments_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    context_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    policy_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    fingerprint_key_version: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )
    context_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    result_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    result_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


__all__ = [
    "AGENT_CLOUD_PROCESSING_PURPOSE",
    "CONSENT_GRANTED",
    "CONSENT_WITHDRAWN",
    "PROPOSAL_PENDING",
    "PROPOSAL_EXECUTED",
    "PROPOSAL_INVALIDATED",
    "PROPOSAL_EXPIRED",
    "PROPOSAL_CANCELLED",
    "PROPOSAL_TERMINAL_STATUSES",
    "AgentCloudConsent",
    "AgentRun",
    "AgentToolEvent",
    "AgentActionProposal",
]
