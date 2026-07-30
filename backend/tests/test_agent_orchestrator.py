"""Bounded, side-effect-free-until-terminal Agent orchestration tests."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.agent import orchestrator as orch
from app.agent.action_tools import PreparedAction
from app.agent.fingerprints import compute_fingerprint
from app.agent.provider import ScriptedProvider
from app.agent.schemas import (
    ContextProviderView,
    EntryType,
    ReadToolResult,
    ResolvedContext,
    TodayTrainingDisplayView,
    TodayTrainingProviderView,
    TurnInput,
)
from app.core.actor_context import ActorContext
from app.core.config import settings


@pytest.fixture(autouse=True)
def _hmac(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY", "x" * 32)
    monkeypatch.setattr(settings, "AGENT_AUDIT_HMAC_KEY_VERSION", "v1")


def _turn(entry=EntryType.general) -> TurnInput:
    return TurnInput(
        client_turn_id="turn-1",
        entry_type=entry,
        message="请解释今天的训练",
        iana_timezone="Asia/Shanghai",
    )


def _context(entry=EntryType.general, tools=("get_today_training",)) -> ResolvedContext:
    local = date(2026, 7, 30)
    return ResolvedContext(
        entry_type=entry,
        entity_id=None,
        iana_timezone="Asia/Shanghai",
        current_local_date=local,
        allowed_tools=tools,
        provider_context=ContextProviderView(
            entry_type=entry,
            current_local_date=local,
            today_state="session",
        ),
        fingerprint_payload={"entry_type": entry.value, "today_state": "session"},
    )


async def test_answer_is_a_reviewed_code_not_provider_text():
    provider = ScriptedProvider([
        {"type": "answer", "message_code": "agent_answer_ready", "references": ["context"]}
    ])
    result = await orch.orchestrate(
        None, ActorContext("user-1"), _turn(), _context(), provider
    )
    assert result.status == "answer"
    assert result.result_code == "agent_answer_ready"
    assert result.provider_decisions == 1
    assert result.read_calls == 0
    assert result.proposal is None


async def test_read_result_sends_provider_projection_only(monkeypatch):
    provider_view = TodayTrainingProviderView(
        state="session", has_session=True, prescription_count=1,
        exercise_ids=["safe-exercise"],
    )
    display_view = TodayTrainingDisplayView(
        state="session", prescription_count=1,
        exercise_ids=["safe-exercise"],
    )

    async def fake_execute(*_args, **_kwargs):
        return (
            ReadToolResult("get_today_training", provider_view, display_view),
            compute_fingerprint({"tool_name": "get_today_training", "arguments": {}}),
        )

    monkeypatch.setattr(orch, "_execute_read_tool", fake_execute)
    provider = ScriptedProvider([
        {"type": "read_tool_call", "tool_name": "get_today_training", "arguments": {}},
        {"type": "answer", "message_code": "agent_answer_ready", "references": ["get_today_training"]},
    ])
    result = await orch.orchestrate(
        None, ActorContext("user-1"), _turn(), _context(), provider
    )
    assert result.read_calls == 1
    assert result.display_results[0].display_view is display_view
    second = provider.calls[1]
    assert second.read_results[0].provider_view == provider_view.model_dump(
        mode="json", exclude_none=True
    )
    assert "display_view" not in second.model_dump(mode="json")["read_results"][0]


async def test_disallowed_or_unknown_read_tool_fails_closed_before_adapter():
    provider = ScriptedProvider([
        {"type": "read_tool_call", "tool_name": "delete_agent_data", "arguments": {}}
    ])
    with pytest.raises(orch.OrchestrationFailure) as exc:
        await orch.orchestrate(
            None, ActorContext("user-1"), _turn(), _context(), provider
        )
    assert exc.value.code == "agent_tool_not_allowed"


async def test_four_read_decisions_end_at_step_limit(monkeypatch):
    async def fake_execute(*_args, **_kwargs):
        return (
            ReadToolResult(
                "get_today_training",
                TodayTrainingProviderView(state="no_active_plan", has_session=False),
                TodayTrainingDisplayView(state="no_active_plan"),
            ),
            compute_fingerprint({"tool_name": "get_today_training", "arguments": {}}),
        )

    monkeypatch.setattr(orch, "_execute_read_tool", fake_execute)
    provider = ScriptedProvider([
        {"type": "read_tool_call", "tool_name": "get_today_training", "arguments": {}}
        for _ in range(4)
    ])
    with pytest.raises(orch.OrchestrationFailure) as exc:
        await orch.orchestrate(
            None, ActorContext("user-1"), _turn(), _context(), provider
        )
    assert exc.value.code == "agent_step_limit"
    assert len(provider.calls) == 4


async def test_unknown_message_code_is_invalid_output():
    provider = ScriptedProvider([
        {"type": "answer", "message_code": "attacker_selected_text", "references": []}
    ])
    with pytest.raises(orch.OrchestrationFailure) as exc:
        await orch.orchestrate(
            None, ActorContext("user-1"), _turn(), _context(), provider
        )
    assert exc.value.code == "agent_output_invalid"


async def test_action_proposal_is_prepared_but_not_executed(monkeypatch):
    executed = False

    async def execute():
        nonlocal executed
        executed = True

    async def fake_prepare(*_args, **_kwargs):
        return PreparedAction(
            context_fingerprint_payload={"profile_version": 1},
            execute=execute,
        )

    monkeypatch.setattr(orch.action_tools, "prepare", fake_prepare)
    provider = ScriptedProvider([
        {
            "type": "action_proposal",
            "tool_name": "create_weight_record",
            "arguments": {
                "recorded_at": "2026-07-30T00:00:00Z",
                "weight_kg": 70.0,
            },
        }
    ])
    result = await orch.orchestrate(
        None, ActorContext("user-1"), _turn(), _context(), provider,
        now=datetime(2026, 7, 30, tzinfo=timezone.utc),
    )
    assert result.status == "proposal"
    assert result.proposal.tool_name == "create_weight_record"
    assert result.proposal.diff.weight_kg == 70.0
    assert executed is False


async def test_write_identity_injection_is_rejected_before_prepare(monkeypatch):
    called = False

    async def fake_prepare(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(orch.action_tools, "prepare", fake_prepare)
    provider = ScriptedProvider([
        {
            "type": "action_proposal",
            "tool_name": "create_weight_record",
            "arguments": {
                "recorded_at": "2026-07-30T00:00:00Z",
                "weight_kg": 70.0,
                "user_id": "other-user",
            },
        }
    ])
    with pytest.raises(orch.OrchestrationFailure) as exc:
        await orch.orchestrate(
            None, ActorContext("user-1"), _turn(), _context(), provider
        )
    assert exc.value.code == "agent_tool_not_allowed"
    assert called is False


async def test_posture_entry_cannot_propose_a_write():
    provider = ScriptedProvider([
        {
            "type": "action_proposal",
            "tool_name": "create_weight_record",
            "arguments": {
                "recorded_at": "2026-07-30T00:00:00Z",
                "weight_kg": 70.0,
            },
        }
    ])
    with pytest.raises(orch.OrchestrationFailure) as exc:
        await orch.orchestrate(
            None,
            ActorContext("user-1"),
            _turn(EntryType.posture_issue),
            _context(EntryType.posture_issue, tools=()),
            provider,
        )
    assert exc.value.code == "agent_tool_not_allowed"
