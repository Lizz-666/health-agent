"""Phase 5 Task 1 (Batch A) - strict Agent schemas + keyed fingerprints.

These tests pin the closed entry enum, the strict (``extra="forbid"``) turn
contract that a client/model can never use to inject identity/authority, the
separation of the minimal ``provider_view`` from the owned ``display_view``, and
the keyed-HMAC fingerprint contract (no plain hashes of low-entropy health
values, fail-closed without a configured server key). Synthetic data only.
"""
from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from app.agent import fingerprints
from app.agent.messages import AgentError
from app.agent.schemas import (
    DisplayView,
    EntryType,
    HealthProfileDisplayView,
    HealthProfileProviderView,
    ProviderView,
    ReadToolResult,
    SideEffectClass,
    TurnInput,
    WeightTrendDisplayView,
    WeightTrendProviderView,
)


# --------------------------------------------------------------------------- #
# Closed entry enum                                                            #
# --------------------------------------------------------------------------- #


def test_entry_type_is_closed_to_the_six_spec_entries():
    assert {e.value for e in EntryType} == {
        "general",
        "health_profile",
        "posture_issue",
        "training_plan",
        "training_session",
        "training_exercise",
    }


def test_side_effect_class_only_exposes_read_in_task1():
    # Task 1 is read-only. Write/proposal classes arrive with Task 3.
    assert SideEffectClass.READ.value == "read"


# --------------------------------------------------------------------------- #
# TurnInput strictness                                                         #
# --------------------------------------------------------------------------- #


def _valid_turn():
    return {
        "client_turn_id": "turn-1",
        "entry_type": "general",
        "message": "今天练什么",
        "iana_timezone": "Asia/Shanghai",
    }


def test_turn_input_accepts_a_minimal_valid_body():
    turn = TurnInput.model_validate(_valid_turn())
    assert turn.entry_type is EntryType.general
    assert turn.entity_id is None
    assert turn.iana_timezone == "Asia/Shanghai"


def test_turn_input_rejects_unknown_fields():
    body = _valid_turn()
    body["surprise"] = "x"
    with pytest.raises(ValidationError):
        TurnInput.model_validate(body)


@pytest.mark.parametrize(
    "forbidden",
    [
        "user_id",
        "actor",
        "consent",
        "consent_record",
        "risk_tier",
        "risk_context",
        "allowed_tools",
        "tool_names",
        "policy_version",
        "context_fingerprint",
        "server_time",
        "now",
    ],
)
def test_turn_input_cannot_carry_server_controlled_identity_or_authority(forbidden):
    body = _valid_turn()
    body[forbidden] = "attacker-supplied"
    with pytest.raises(ValidationError):
        TurnInput.model_validate(body)


def test_turn_input_requires_non_empty_timezone_field_presence():
    body = _valid_turn()
    del body["iana_timezone"]
    with pytest.raises(ValidationError):
        TurnInput.model_validate(body)


def test_turn_input_rejects_message_over_2000_code_points():
    body = _valid_turn()
    body["message"] = "a" * 2001
    with pytest.raises(ValidationError):
        TurnInput.model_validate(body)


def test_turn_input_accepts_message_at_2000_code_points():
    body = _valid_turn()
    body["message"] = "b" * 2000
    assert len(TurnInput.model_validate(body).message) == 2000


# --------------------------------------------------------------------------- #
# provider_view / display_view separation                                     #
# --------------------------------------------------------------------------- #


def test_views_are_strict_and_forbid_extra_fields():
    with pytest.raises(ValidationError):
        HealthProfileProviderView.model_validate(
            {"configured": True, "phone": "13800000000"}
        )


def test_provider_and_display_views_are_distinct_typed_projections():
    assert issubclass(HealthProfileProviderView, ProviderView)
    assert issubclass(HealthProfileDisplayView, DisplayView)
    assert not issubclass(HealthProfileProviderView, DisplayView)


def test_provider_weight_view_carries_no_raw_weight_value():
    fields = set(WeightTrendProviderView.model_fields)
    # The provider never receives the raw kg value or the full history list.
    assert "weight_kg" not in fields
    assert "latest_weight_kg" not in fields
    assert "records" not in fields
    assert "trend" not in fields


def test_display_weight_view_may_carry_the_owned_latest_value():
    fields = set(WeightTrendDisplayView.model_fields)
    assert "latest_weight_kg" in fields
    # Even the owned display view stays a bounded summary, never full history.
    assert "records" not in fields


def test_read_tool_result_binds_both_typed_projections():
    result = ReadToolResult(
        tool_name="get_weight_trend_summary",
        provider_view=WeightTrendProviderView(
            sufficient=False, window=7, record_count=0, trend_point_count=0
        ),
        display_view=WeightTrendDisplayView(
            sufficient=False,
            window=7,
            record_count=0,
            trend_point_count=0,
            latest_weight_kg=None,
        ),
    )
    assert isinstance(result.provider_view, ProviderView)
    assert isinstance(result.display_view, DisplayView)


# --------------------------------------------------------------------------- #
# Keyed fingerprints                                                           #
# --------------------------------------------------------------------------- #

_KEY = "test-synthetic-agent-key-0123456789abcdef"
_KEY_V = "test-v1"


def test_canonical_serialize_is_order_independent():
    a = fingerprints.canonical_serialize({"a": 1, "b": 2})
    b = fingerprints.canonical_serialize({"b": 2, "a": 1})
    assert a == b
    assert isinstance(a, bytes)


def test_fingerprint_is_stable_for_the_same_payload_and_key():
    payload = {"entry_type": "training_plan", "plan_version_id": "pv1"}
    one = fingerprints.compute_fingerprint(payload, key=_KEY, key_version=_KEY_V)
    two = fingerprints.compute_fingerprint(payload, key=_KEY, key_version=_KEY_V)
    assert one.value == two.value
    assert one.key_version == _KEY_V


def test_fingerprint_depends_on_the_key():
    payload = {"x": "y"}
    a = fingerprints.compute_fingerprint(payload, key=_KEY, key_version=_KEY_V)
    b = fingerprints.compute_fingerprint(payload, key="another-key", key_version=_KEY_V)
    assert a.value != b.value


def test_fingerprint_records_the_key_version_distinctly():
    payload = {"x": "y"}
    a = fingerprints.compute_fingerprint(payload, key=_KEY, key_version="v1")
    b = fingerprints.compute_fingerprint(payload, key=_KEY, key_version="v2")
    assert a.key_version == "v1"
    assert b.key_version == "v2"


def test_fingerprint_fails_closed_without_a_configured_key(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY", "", raising=False)
    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY_VERSION", "", raising=False)
    with pytest.raises(AgentError) as exc:
        fingerprints.compute_fingerprint({"x": "y"})
    assert exc.value.code == "agent_fingerprint_key_missing"


def test_fingerprint_uses_settings_key_when_none_passed(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY", _KEY, raising=False)
    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY_VERSION", _KEY_V, raising=False)
    got = fingerprints.compute_fingerprint({"x": "y"})
    assert got.value == fingerprints.compute_fingerprint(
        {"x": "y"}, key=_KEY, key_version=_KEY_V
    ).value


def test_low_entropy_health_value_is_not_a_plain_hash():
    # A plain sha256 of a low-entropy weight is trivially enumerable; the keyed
    # HMAC must not equal it.
    payload = {"weight_kg": 70.0}
    keyed = fingerprints.compute_fingerprint(payload, key=_KEY, key_version=_KEY_V)
    plain = hashlib.sha256(fingerprints.canonical_serialize(payload)).hexdigest()
    assert keyed.value != plain


def test_canonical_serialize_rejects_non_json_values():
    import datetime as _dt

    # Arbitrary objects (no default=str coercion) fail closed.
    with pytest.raises(AgentError):
        fingerprints.canonical_serialize({"when": _dt.datetime(2026, 7, 29)})
    # Sets are not JSON-serializable.
    with pytest.raises(AgentError):
        fingerprints.canonical_serialize({"ids": {1, 2}})


def test_canonical_serialize_rejects_nan_and_infinity():
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(AgentError):
            fingerprints.canonical_serialize({"value": bad})


def test_canonical_serialize_accepts_only_json_native_structured_values():
    # Strings, ints, bools, lists and nested dicts of those are accepted.
    payload = {
        "entry_type": "training_plan",
        "plan_version_id": "pv1",
        "active_plan_present": True,
        "prescription_exercise_ids": ["ex1", "ex2"],
        "nested": {"gate": "normal", "count": 3},
    }
    data = fingerprints.canonical_serialize(payload)
    assert isinstance(data, bytes)
    # Stable / order-independent.
    other = {
        "nested": {"count": 3, "gate": "normal"},
        "prescription_exercise_ids": ["ex1", "ex2"],
        "active_plan_present": True,
        "entry_type": "training_plan",
        "plan_version_id": "pv1",
    }
    assert data == fingerprints.canonical_serialize(other)


def test_fingerprint_fails_closed_with_empty_key_version():
    # Even with a non-empty key, a missing/blank key version fails closed.
    with pytest.raises(AgentError) as exc:
        fingerprints.compute_fingerprint({"x": "y"}, key=_KEY, key_version="")
    assert exc.value.code == "agent_fingerprint_key_missing"
    with pytest.raises(AgentError) as exc:
        fingerprints.compute_fingerprint({"x": "y"}, key=_KEY, key_version="   ")
    assert exc.value.code == "agent_fingerprint_key_missing"


def test_fingerprint_is_fresh_to_context_version_and_risk_changes():
    base = {
        "entry_type": "training_plan",
        "plan_version_id": "pv1",
        "plan_status": "active",
        "risk_gate_code": "normal",
    }
    same = fingerprints.compute_fingerprint(base, key=_KEY, key_version=_KEY_V)
    changed_version = fingerprints.compute_fingerprint(
        {**base, "plan_version_id": "pv2"}, key=_KEY, key_version=_KEY_V
    )
    changed_risk = fingerprints.compute_fingerprint(
        {**base, "risk_gate_code": "red_flag"}, key=_KEY, key_version=_KEY_V
    )
    assert same.value != changed_version.value
    assert same.value != changed_risk.value
