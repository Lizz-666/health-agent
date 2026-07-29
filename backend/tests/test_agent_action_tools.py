"""Phase 5 Agent write-action adapter tests (Task 3).

Covers the closed server-side write registry: strict typed arguments (no actor/
user/time/policy/consent/fingerprint/free-text fields), the five-action closure,
deterministic typed diffs (no provider prose), the pain-check-in / weight-note
boundaries, and that write action names are NOT registered in the provider-
exposed read registry.
"""
import pytest

from app.agent import action_tools as at
from app.agent import schemas as S
from app.agent import tool_registry as read_registry
from app.agent.messages import AgentError
from app.core.config import settings

HMAC_KEY = "test-agent-audit-key-0123456789abcdef"
HMAC_VERSION = "v1"


@pytest.fixture(autouse=True)
def _hmac_key(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY", HMAC_KEY)
    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY_VERSION", HMAC_VERSION)


def test_exactly_five_write_actions_and_not_in_read_registry():
    assert set(at._ARGUMENTS_MODELS.keys()) == set(S.WRITE_ACTION_NAMES)
    # Write actions are NOT provider-exposed read tools.
    for name in S.WRITE_ACTION_NAMES:
        assert not read_registry.is_read_tool(name)


def test_arguments_reject_unknown_fields_and_identity():
    with pytest.raises(AgentError):
        at.validate_arguments(
            S.CREATE_WEIGHT_RECORD,
            {"recorded_at": "2026-07-29T00:00:00Z", "weight_kg": 70.0, "user_id": "x"},
        )
    with pytest.raises(AgentError):
        at.validate_arguments(S.UPSERT_TODAY_CHECKIN, {"local_date": "2026-07-29"})


def test_weight_arguments_have_no_note_field():
    args = at.validate_arguments(
        S.CREATE_WEIGHT_RECORD,
        {"recorded_at": "2026-07-29T08:00:00+00:00", "weight_kg": 70.0},
    )
    assert "note" not in args.model_dump()
    with pytest.raises(AgentError):
        at.validate_arguments(
            S.CREATE_WEIGHT_RECORD,
            {"recorded_at": "2026-07-29T08:00:00+00:00", "weight_kg": 70.0, "note": "fat"},
        )


def test_checkin_arguments_have_no_pain_fields():
    raw = {
        "local_date": "2026-07-29",
        "sleep_quality": "good",
        "energy": "high",
        "muscle_soreness": "none",
        "available_time": "30_min",
        "daily_status": "checked_in",
    }
    args = at.validate_arguments(S.UPSERT_TODAY_CHECKIN, raw)
    dump = args.model_dump()
    for forbidden in ("abnormal_pain", "pain_followup", "pain_area", "pain_note"):
        assert forbidden not in dump


def test_feedback_excludes_discomfort_pain_outcome():
    args = at.validate_arguments(
        S.RECORD_TRAINING_FEEDBACK, {"outcome_state": "completed"}
    )
    assert args.outcome_state == "completed"
    # discomfort is a pain signal routed to the dedicated flow, not ordinary.
    with pytest.raises(AgentError):
        at.validate_arguments(
            S.RECORD_TRAINING_FEEDBACK, {"outcome_state": "discomfort"}
        )


def test_unknown_write_action_rejected():
    with pytest.raises(AgentError):
        at.validate_arguments("delete_everything", {})


def test_diffs_are_typed_and_deterministic():
    w = at.validate_arguments(
        S.CREATE_WEIGHT_RECORD,
        {"recorded_at": "2026-07-29T08:00:00+00:00", "weight_kg": 70.0},
    )
    diff = at.build_diff(S.CREATE_WEIGHT_RECORD, w)
    assert isinstance(diff, S.CreateWeightRecordDiff)
    assert diff.weight_kg == 70.0
    assert diff.action == S.CREATE_WEIGHT_RECORD

    c = at.validate_arguments(
        S.UPSERT_TODAY_CHECKIN,
        {
            "local_date": "2026-07-29",
            "sleep_quality": "good",
            "energy": "high",
            "muscle_soreness": "none",
            "available_time": "30_min",
            "daily_status": "checked_in",
        },
    )
    cdiff = at.build_diff(S.UPSERT_TODAY_CHECKIN, c)
    assert isinstance(cdiff, S.UpsertTodayCheckinDiff)
    assert cdiff.abnormal_pain is False


def test_arguments_fingerprint_is_keyed_and_stable():
    w = at.validate_arguments(
        S.CREATE_WEIGHT_RECORD,
        {"recorded_at": "2026-07-29T08:00:00+00:00", "weight_kg": 70.0},
    )
    fp = at.compute_arguments_fingerprint(w)
    assert fp.key_version == HMAC_VERSION
    assert len(fp.value) == 64
    # Same arguments -> same fingerprint.
    assert at.compute_arguments_fingerprint(w).value == fp.value
    # Different arguments -> different fingerprint.
    w2 = at.validate_arguments(
        S.CREATE_WEIGHT_RECORD,
        {"recorded_at": "2026-07-29T08:00:00+00:00", "weight_kg": 71.0},
    )
    assert at.compute_arguments_fingerprint(w2).value != fp.value
