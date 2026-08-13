"""Phase 4 plan lifecycle state machine (Task 2).

Pure, dependency-free rules for plan-version status transitions. This is the
single source of truth consulted by ``persistence`` so the database never lands
in an illegal state (e.g. re-activating an active plan, demoting to draft, or
mutating a terminal version).

Lifecycle (spec ``2026-07-27-four-week-plan-mvp.md`` Domain And State Model)::

    draft   --confirm(revalidate)-->        active
    draft   --supersede(new draft)-->       superseded
    draft   --cancel(user)-->               cancelled
    active  --supersede(new draft)-->       superseded
    active  --cancel(user)-->               cancelled
    superseded --> (terminal)
    cancelled  --> (terminal)

A draft has no execution effect; only confirmation reaches ``active``. At most
one active plan per user is additionally enforced by a DB partial unique index
in migration ``0007`` (see ADR-0002). Terminal versions are immutable.
"""
from __future__ import annotations

from enum import Enum


class PlanStatus(str, Enum):
    """Plan-version lifecycle status (stored as a string in the DB)."""

    draft = "draft"
    active = "active"
    superseded = "superseded"
    cancelled = "cancelled"


# Outgoing legal transitions. Absent or empty => terminal (no outgoing move).
LEGAL_TRANSITIONS: dict[PlanStatus, frozenset[PlanStatus]] = {
    PlanStatus.draft: frozenset(
        {PlanStatus.active, PlanStatus.superseded, PlanStatus.cancelled}
    ),
    PlanStatus.active: frozenset({PlanStatus.superseded, PlanStatus.cancelled}),
    PlanStatus.superseded: frozenset(),
    PlanStatus.cancelled: frozenset(),
}


def is_terminal(status: PlanStatus) -> bool:
    """True when ``status`` cannot transition to anything (immutable)."""
    return len(LEGAL_TRANSITIONS.get(status, frozenset())) == 0


def is_legal_transition(source: PlanStatus, target: PlanStatus) -> bool:
    """True when ``source -> target`` is a permitted lifecycle transition."""
    if not isinstance(source, PlanStatus) or not isinstance(target, PlanStatus):
        return False
    return target in LEGAL_TRANSITIONS.get(source, frozenset())


def assert_transition(source: PlanStatus, target: PlanStatus) -> PlanStatus:
    """Return ``target`` if the transition is legal, else raise ``ValueError``.

    The persistence layer uses this to refuse illegal mutations before any write.
    """
    if not is_legal_transition(source, target):
        raise ValueError(
            f"illegal plan status transition: {source.value} -> {target.value}"
        )
    return target


__all__ = [
    "PlanStatus",
    "LEGAL_TRANSITIONS",
    "is_terminal",
    "is_legal_transition",
    "assert_transition",
]
