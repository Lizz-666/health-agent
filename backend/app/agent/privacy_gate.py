"""Agent live-cloud-provider privacy gate (Task 2).

Before any live cloud provider call, all nine conditions of the spec Consent And
Privacy Gate must pass. This module is a PURE evaluator over an explicit,
server-constructed ``PrivacyGateInput`` contract: it performs no I/O of its own
and reads no client/model field. The orchestrator (Task 4) builds the input
from authenticated server state (runtime switch, reviewed provider/disclosure
configuration, derived current consent, minimization contract, deletion/withdraw
capability, and the non-default dedicated audit HMAC key) and calls
``evaluate_privacy_gate``.

Hard boundary (spec, ADR-0004): a single runtime switch, a client-supplied
consent, or an injectable test fake can NEVER satisfy the live gate on their
own. Every condition is independent and required; any missing condition fails
closed with a stable blocking code. The gate never returns ``passed`` unless
ALL conditions hold, and it never turns a failure into a success.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.agent.models import AGENT_CLOUD_PROCESSING_PURPOSE

# Stable blocking codes (spec API Contracts). These are string constants owned
# by the gate; Task 4 wires them into the rendered template registry. They are
# distinct from the read-boundary codes in ``app.agent.messages``.
AGENT_CONSENT_REQUIRED = "agent_consent_required"
AGENT_PRIVACY_GATE_BLOCKED = "agent_privacy_gate_blocked"
AGENT_DISCLOSURE_STALE = "agent_disclosure_stale"


@dataclass(frozen=True)
class ActiveConsentSnapshot:
    """Server-derived current consent state for the current user/purpose.

    Derived deterministically from the highest per-user ``sequence_no`` in
    ``agent_cloud_consents`` (see ``app.agent.persistence.active_consent``).
    ``active`` is true only when the highest event is a grant for the current
    provider/disclosure. It is built by trusted server code; the client/model
    never supplies it.
    """

    active: bool
    provider_id: str = ""
    disclosure_version: str = ""
    purpose: str = AGENT_CLOUD_PROCESSING_PURPOSE


@dataclass(frozen=True)
class PrivacyGateInput:
    """The full server-constructed contract evaluated by the privacy gate.

    Every field is populated from authenticated server state, never from
    client/model input. A field defaulting falsy represents the corresponding
    condition not (yet) satisfied; the gate fails closed on any falsy field.
    """

    # 1. Global Agent runtime switch enabled.
    runtime_enabled: bool = False
    # 2. Provider/model identity and processing boundary configured+disclosed.
    provider_id: str = ""
    model_id: str = ""
    disclosure_version: str = ""
    # 3 + 4. Active current server-side consent for the current user/provider/
    # disclosure version (derived server-side; never a Tool argument).
    consent: ActiveConsentSnapshot = field(
        default_factory=lambda: ActiveConsentSnapshot(active=False)
    )
    # 5. No raw transcript persistence and audited log redaction verified.
    no_transcript_persistence: bool = False
    log_redaction_verified: bool = False
    # 6. User-accessible withdrawal and Agent-data deletion paths.
    withdrawal_path_available: bool = False
    agent_data_deletion_path_available: bool = False
    # 7. Provider failure leaves all non-Agent product flows available.
    non_agent_flows_available_on_failure: bool = False
    # 8. Requested entry/context is supported by the minimization contract.
    supported_context: bool = False
    # 9. A dedicated non-default Agent audit HMAC key is configured server-side.
    dedicated_audit_hmac_key_configured: bool = False


@dataclass(frozen=True)
class PrivacyGateDecision:
    """Result of evaluating the privacy gate.

    ``passed`` is true only when every condition holds. ``blocking_code`` is the
    first stable failure code (or None when passed); ``failed_conditions`` lists
    every unsatisfied condition name for diagnostics/audit without leaking any
    sensitive value (the gate stores no health data).
    """

    passed: bool
    blocking_code: Optional[str]
    failed_conditions: List[str] = field(default_factory=list)


def evaluate_privacy_gate(request: PrivacyGateInput) -> PrivacyGateDecision:
    """Evaluate all privacy-gate conditions and fail closed on any miss.

    The order is chosen so the most specific, user-actionable code surfaces
    first: a stale disclosure (user must re-acknowledge) is reported before the
    generic gate-blocked code; a missing consent is reported as
    ``agent_consent_required`` so the caller can drive the consent flow.
    """
    failed: List[str] = []

    # 9. Dedicated non-default audit HMAC key (checked first because every
    # fingerprint depends on it; without it the capability is disabled).
    if not request.dedicated_audit_hmac_key_configured:
        failed.append("dedicated_audit_hmac_key_configured")

    # 1. Global runtime switch.
    if not request.runtime_enabled:
        failed.append("runtime_enabled")

    # 2. Provider/model/disclosure configured and disclosed.
    provider_configured = bool(
        request.provider_id and request.model_id and request.disclosure_version
    )
    if not provider_configured:
        failed.append("provider_model_disclosure_configured")

    # 3 + 5. No transcript persistence and verified log redaction.
    if not request.no_transcript_persistence:
        failed.append("no_transcript_persistence")
    if not request.log_redaction_verified:
        failed.append("log_redaction_verified")

    # 6. Withdrawal and deletion paths.
    if not request.withdrawal_path_available:
        failed.append("withdrawal_path_available")
    if not request.agent_data_deletion_path_available:
        failed.append("agent_data_deletion_path_available")

    # 7. Non-Agent flows remain available on provider failure.
    if not request.non_agent_flows_available_on_failure:
        failed.append("non_agent_flows_available_on_failure")

    # 8. Minimization contract supports the requested entry/context.
    if not request.supported_context:
        failed.append("supported_context")

    # Consent + disclosure-match conditions carry the most specific codes, so
    # they are evaluated last to take precedence as the reported blocking code.
    blocking_code: Optional[str] = None
    if not request.consent.active:
        failed.append("active_consent")
        blocking_code = AGENT_CONSENT_REQUIRED
    elif provider_configured and (
        request.consent.provider_id != request.provider_id
        or request.consent.disclosure_version != request.disclosure_version
        or request.consent.purpose != AGENT_CLOUD_PROCESSING_PURPOSE
    ):
        # Active consent exists but for a different provider/disclosure than the
        # current server configuration: the user must re-acknowledge.
        failed.append("consent_matches_current_provider_disclosure")
        blocking_code = AGENT_DISCLOSURE_STALE

    if failed and blocking_code is None:
        blocking_code = AGENT_PRIVACY_GATE_BLOCKED

    return PrivacyGateDecision(
        passed=not failed,
        blocking_code=blocking_code if failed else None,
        failed_conditions=failed,
    )


__all__ = [
    "AGENT_CONSENT_REQUIRED",
    "AGENT_PRIVACY_GATE_BLOCKED",
    "AGENT_DISCLOSURE_STALE",
    "ActiveConsentSnapshot",
    "PrivacyGateInput",
    "PrivacyGateDecision",
    "evaluate_privacy_gate",
]
