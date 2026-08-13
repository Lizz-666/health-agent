"""Phase 5 Agent privacy gate tests (Task 2).

The live-cloud-provider privacy gate is a pure evaluator over an explicit,
server-constructed ``PrivacyGateInput``. A single runtime switch, a client
consent, or an injectable test fake can never satisfy it: every condition is
independent and required, and any missing condition fails closed with a stable
blocking code. The gate never turns a failure into a success.
"""
import dataclasses

import pytest

from app.agent.privacy_gate import (
    AGENT_CONSENT_REQUIRED,
    AGENT_DISCLOSURE_STALE,
    AGENT_PRIVACY_GATE_BLOCKED,
    ActiveConsentSnapshot,
    PrivacyGateInput,
    evaluate_privacy_gate,
)


def _fully_satisfied() -> PrivacyGateInput:
    """Every condition satisfied: the only input shape that may pass."""
    return PrivacyGateInput(
        runtime_enabled=True,
        provider_id="cloud-provider-a",
        model_id="model-a",
        disclosure_version="disclosure-2026-07",
        consent=ActiveConsentSnapshot(
            active=True,
            provider_id="cloud-provider-a",
            disclosure_version="disclosure-2026-07",
        ),
        no_transcript_persistence=True,
        log_redaction_verified=True,
        withdrawal_path_available=True,
        agent_data_deletion_path_available=True,
        non_agent_flows_available_on_failure=True,
        supported_context=True,
        dedicated_audit_hmac_key_configured=True,
    )


def test_all_conditions_satisfied_passes():
    decision = evaluate_privacy_gate(_fully_satisfied())
    assert decision.passed is True
    assert decision.blocking_code is None
    assert decision.failed_conditions == []


@pytest.mark.parametrize(
    "field",
    [
        "runtime_enabled",
        "no_transcript_persistence",
        "log_redaction_verified",
        "withdrawal_path_available",
        "agent_data_deletion_path_available",
        "non_agent_flows_available_on_failure",
        "supported_context",
        "dedicated_audit_hmac_key_configured",
    ],
)
def test_any_single_missing_condition_blocks(field):
    """No single condition can be dropped while still passing."""
    inp = dataclasses.replace(_fully_satisfied(), **{field: False})
    decision = evaluate_privacy_gate(inp)
    assert decision.passed is False
    assert field in decision.failed_conditions
    # The reported blocking code is the privacy-gate-blocked code (not consent).
    assert decision.blocking_code == AGENT_PRIVACY_GATE_BLOCKED


def test_runtime_switch_alone_is_insufficient():
    """A single global runtime switch never authorizes a live call."""
    decision = evaluate_privacy_gate(
        PrivacyGateInput(runtime_enabled=True)
    )
    assert decision.passed is False
    assert "runtime_enabled" not in decision.failed_conditions  # it IS enabled
    # Multiple other conditions miss; the specific code is not important, only
    # that the gate fails closed.
    assert decision.blocking_code is not None


def test_client_consent_alone_is_insufficient():
    """An active consent snapshot alone (no provider config / switch / key) is
    not authorization."""
    decision = evaluate_privacy_gate(
        PrivacyGateInput(
            consent=ActiveConsentSnapshot(
                active=True, provider_id="p", disclosure_version="d"
            )
        )
    )
    assert decision.passed is False


def test_fake_provider_without_real_config_is_insufficient():
    """An injectable test fake has no runtime configuration value and cannot
    satisfy the gate (provider/model/disclosure must be configured)."""
    decision = evaluate_privacy_gate(
        PrivacyGateInput(
            runtime_enabled=True,
            provider_id="",  # unconfigured == fake/test-only
            model_id="",
            disclosure_version="",
            dedicated_audit_hmac_key_configured=True,
        )
    )
    assert decision.passed is False
    assert "provider_model_disclosure_configured" in decision.failed_conditions


def test_missing_active_consent_returns_consent_required():
    inp = dataclasses.replace(
        _fully_satisfied(), consent=ActiveConsentSnapshot(active=False)
    )
    decision = evaluate_privacy_gate(inp)
    assert decision.passed is False
    assert decision.blocking_code == AGENT_CONSENT_REQUIRED
    assert "active_consent" in decision.failed_conditions


def test_stale_disclosure_returns_disclosure_stale():
    """Active consent for a different provider/disclosure than current config
    must re-acknowledge (agent_disclosure_stale), not silently grant."""
    inp = dataclasses.replace(
        _fully_satisfied(),
        consent=ActiveConsentSnapshot(
            active=True,
            provider_id="old-provider",
            disclosure_version="old-disclosure",
        ),
    )
    decision = evaluate_privacy_gate(inp)
    assert decision.passed is False
    assert decision.blocking_code == AGENT_DISCLOSURE_STALE
    assert "consent_matches_current_provider_disclosure" in decision.failed_conditions


def test_missing_dedicated_hmac_key_blocks():
    """A non-default dedicated Agent audit HMAC key is required (Acceptance #15)."""
    inp = dataclasses.replace(_fully_satisfied(), dedicated_audit_hmac_key_configured=False)
    decision = evaluate_privacy_gate(inp)
    assert decision.passed is False
    assert "dedicated_audit_hmac_key_configured" in decision.failed_conditions


def test_consent_wrong_purpose_treated_as_stale():
    """A consent snapshot for a different purpose cannot authorize this gate."""
    inp = dataclasses.replace(
        _fully_satisfied(),
        consent=ActiveConsentSnapshot(
            active=True,
            provider_id="cloud-provider-a",
            disclosure_version="disclosure-2026-07",
            purpose="something_else",
        ),
    )
    decision = evaluate_privacy_gate(inp)
    assert decision.passed is False
    assert decision.blocking_code == AGENT_DISCLOSURE_STALE
