"""Pure helper tests for the training safety context (Task 4).

Covers the deterministic pure helpers in ``app.training.context``: IANA timezone
validation, server-derived local date, and the freshness token / structured
hash which MUST exclude free-text ``pain_note``.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.posture.safety import compute_signals_digest
from app.training.context import (
    checkin_token,
    derive_local_date,
    validate_iana_timezone,
    _structured_checkin_hash,
)
from app.training.schemas import CheckInSnapshot

UTC = datetime(2026, 7, 26, 1, 30, tzinfo=timezone.utc)


def _followup(*, note="secret free text", acute=False):
    return SimpleNamespace(
        pain_area="lower_back",
        pain_started=SimpleNamespace(value="after_acute_event"),
        pain_intensity=SimpleNamespace(value="severe"),
        has_neurological_symptom=False,
        has_dizziness_or_chest_symptom=acute is False and False,
        has_acute_trauma=acute,
        pain_note=note,
    )


def _checkin(note="secret free text", acute=False):
    return SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        local_date=date(2026, 7, 26),
        updated_at=UTC,
        risk_version="2026-07-22-v1",
        energy="normal",
        muscle_soreness="mild",
        available_time="30_min",
        daily_status="checked_in",
        abnormal_pain=True,
        pain_followup=_followup(note=note, acute=acute),
    )


def test_adaptive_checkin_fields_use_closed_existing_enums():
    with pytest.raises(ValueError):
        CheckInSnapshot(present=True, energy="exhausted")


def test_legacy_safety_snapshot_without_adaptive_fields_remains_parseable():
    snapshot = CheckInSnapshot(
        present=True,
        local_date=date(2026, 7, 26),
        recomputed_risk="normal",
        token="current-token",
    )
    assert snapshot.available_time is None


def test_validate_iana_timezone_accepts_real_zones():
    assert validate_iana_timezone("Asia/Shanghai") is True
    assert validate_iana_timezone("America/New_York") is True


def test_validate_iana_timezone_rejects_bad_input():
    assert validate_iana_timezone(None) is False
    assert validate_iana_timezone("") is False
    assert validate_iana_timezone("Mars/Olympus") is False


def test_derive_local_date_from_server_utc():
    # 2026-07-26 01:30 UTC -> 2026-07-26 in Asia/Shanghai (+08:00).
    assert derive_local_date(UTC, "Asia/Shanghai") == date(2026, 7, 26)
    # 2026-07-26 01:30 UTC -> 2026-07-25 in America/New_York (-04:00 DST).
    assert derive_local_date(UTC, "America/New_York") == date(2026, 7, 25)
    assert derive_local_date(UTC, "Mars/Olympus") is None


def test_structured_hash_excludes_pain_note():
    a = _structured_checkin_hash(_checkin(note="note A"), "red_flag")
    b = _structured_checkin_hash(_checkin(note="note B"), "red_flag")
    assert a == b  # free text never affects the structured hash


def test_structured_hash_changes_with_structured_content():
    a = _structured_checkin_hash(_checkin(acute=False), "caution")
    b = _structured_checkin_hash(_checkin(acute=True), "red_flag")
    assert a != b


def test_checkin_token_excludes_pain_note_and_is_deterministic():
    t1 = checkin_token(_checkin(note="note A"), "red_flag")
    t2 = checkin_token(_checkin(note="note B"), "red_flag")
    assert t1 == t2  # free text excluded -> identical token
    # Token changes when the recomputed risk changes.
    t3 = checkin_token(_checkin(note="note A"), "caution")
    assert t3 != t1


def test_checkin_token_normalizes_equivalent_instants_to_utc():
    utc_checkin = _checkin()
    offset_checkin = _checkin()
    offset_checkin.updated_at = datetime.fromisoformat("2026-07-26T09:30:00+08:00")
    assert checkin_token(utc_checkin, "normal") == checkin_token(
        offset_checkin, "normal")


def test_posture_signal_digest_is_order_independent():
    a = SimpleNamespace(
        signal_type="pain", severity_hint="caution", body_region="knee",
        lifecycle="active", related_issue_id="LL-18")
    b = SimpleNamespace(
        signal_type="neurological", severity_hint="red_flag",
        body_region=None, lifecycle="active", related_issue_id=None)
    assert compute_signals_digest([a, b]) == compute_signals_digest([b, a])
