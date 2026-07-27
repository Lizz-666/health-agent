"""Phase 4 plan lifecycle state-machine tests (Task 2, pure).

These cover the pure legal/illegal transition rules with NO database. The state
module is the single source of truth for which plan-status changes are allowed;
the persistence layer must refuse anything not permitted here.
"""
from __future__ import annotations

import pytest

from app.training.state import (
    LEGAL_TRANSITIONS,
    PlanStatus,
    assert_transition,
    is_legal_transition,
    is_terminal,
)


def test_legal_confirm_and_supersede_and_cancel_transitions():
    assert is_legal_transition(PlanStatus.draft, PlanStatus.active)
    assert is_legal_transition(PlanStatus.draft, PlanStatus.superseded)
    assert is_legal_transition(PlanStatus.draft, PlanStatus.cancelled)
    assert is_legal_transition(PlanStatus.active, PlanStatus.superseded)
    assert is_legal_transition(PlanStatus.active, PlanStatus.cancelled)


def test_terminal_states_have_no_outgoing_transitions():
    assert is_terminal(PlanStatus.superseded)
    assert is_terminal(PlanStatus.cancelled)
    assert LEGAL_TRANSITIONS[PlanStatus.superseded] == frozenset()
    assert LEGAL_TRANSITIONS[PlanStatus.cancelled] == frozenset()
    # A terminal status cannot move anywhere, including to itself.
    for target in PlanStatus:
        assert not is_legal_transition(PlanStatus.superseded, target)
        assert not is_legal_transition(PlanStatus.cancelled, target)


def test_no_re_activation_or_demotion_to_draft():
    # draft is a pre-confirmation state only; you cannot demote to draft or
    # re-confirm an already-active plan in place.
    assert not is_legal_transition(PlanStatus.active, PlanStatus.active)
    assert not is_legal_transition(PlanStatus.active, PlanStatus.draft)
    assert not is_legal_transition(PlanStatus.draft, PlanStatus.draft)


def test_assert_transition_returns_target_on_legal():
    assert assert_transition(PlanStatus.draft, PlanStatus.active) is PlanStatus.active
    assert (
        assert_transition(PlanStatus.active, PlanStatus.superseded)
        is PlanStatus.superseded
    )


def test_assert_transition_raises_on_illegal():
    with pytest.raises(ValueError):
        assert_transition(PlanStatus.active, PlanStatus.draft)
    with pytest.raises(ValueError):
        assert_transition(PlanStatus.superseded, PlanStatus.active)
    with pytest.raises(ValueError):
        assert_transition(PlanStatus.cancelled, PlanStatus.active)


def test_plan_status_values_are_stable_wire_strings():
    # The DB stores these as strings; the values are a wire contract.
    assert {s.value for s in PlanStatus} == {
        "draft",
        "active",
        "superseded",
        "cancelled",
    }
