"""Phase 2 Task 8: final end-to-end acceptance for the health profile,
daily check-in, weight trend, and activity-grid vertical slice.

This suite is the Phase 2 acceptance gate. It exercises the complete user
journey against the integrated Phase 2 delivery (migrations 0004-0006), plus
the safety/privacy invariants that must hold end-to-end:

  Coverage (plan Task 8, roadmap section 6, spec Domain Model):
    A. Migration head == 0006_health_weight_tracking; Phase 2 tables present.
    B. Full user journey (user A): profile (not-configured -> configure ready,
       missing stays missing) -> today check-in (not-checked-in -> normal) ->
       abnormal pain follow-up gate (pain_followup_required) -> red_flag
       routing (red_flag != normal/success) -> weight (insufficient ->
       sufficient trend, no advice) -> activity grid (four statuses) ->
       delete profile -> not-configured.
    C. restricted profile qualifier routes the check-in to ``restricted``,
       never ordinary/normal.
    D. Cross-user isolation / account switch: user B sees none of user A's
       profile/check-in/weight/grid data; cross-user delete is a 404.
    E. Privacy: the readiness/audit-shaped outputs carry no raw sensitive
       health values (allergy labels, pain notes, diet exclusions).

All data is synthetic. PostgreSQL migration rehearsal and the Android emulator
smoke are environment-gated (see the exit-audit report); this suite runs on the
default SQLite test database alongside the rest of the pytest session.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from app.auth.models import VerificationCode
from tests.conftest import TestSession


_BACKEND_DIR = Path(__file__).resolve().parent.parent

AUTH = "/api/v1/auth"
PROFILE = "/api/v1/health/profile"
TODAY = "/api/v1/health/checkins/today"
CHECKINS = "/api/v1/health/checkins"
WEIGHT = "/api/v1/health/weight-records"
TREND = "/api/v1/health/trends/weight"
GRID = "/api/v1/health/activity-grid"


# ---------------------------------------------------------------------------
# Shared helpers (mirror tests/test_phase1_e2e.py + tests/test_health_*.py)
# ---------------------------------------------------------------------------


async def _login_user(client, phone: str) -> str:
    """Register/login a synthetic user and return its access token."""
    await client.post(f"{AUTH}/send-code", json={"phone": phone})
    async with TestSession() as db:
        result = await db.execute(
            select(VerificationCode)
            .where(VerificationCode.phone == phone)
            .order_by(VerificationCode.created_at.desc())
        )
        code = result.scalar_one().code
    resp = await client.post(
        f"{AUTH}/verify-login", json={"phone": phone, "code": code}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _ready_profile(**overrides) -> dict:
    """A fully-configured profile that classifies as ``ready``."""
    payload = {
        "fitness_goal": "basic_strength",
        "training_experience": "some_experience",
        "weekly_frequency": 3,
        "session_duration_minutes": 30,
        "equipment": {"bodyweight": True, "resistance_band": False},
        "pain_injury_limitations": [],
        "risk_screen": {},
        "allergies": [{"label": "synthetic-peanut", "note": "synthetic"}],
        "diet_exclusions": [],
    }
    payload.update(overrides)
    return payload


def _normal_checkin(day: str, **overrides) -> dict:
    payload = {
        "local_date": day,
        "sleep_quality": "good",
        "energy": "normal",
        "muscle_soreness": "mild",
        "available_time": "30_min",
        "daily_status": "checked_in",
        "abnormal_pain": False,
    }
    payload.update(overrides)
    return payload


def _pain_followup(**overrides) -> dict:
    payload = {
        "pain_area": "lower_back",
        "pain_started": "today",
        "pain_intensity": "mild",
        "has_neurological_symptom": False,
        "has_dizziness_or_chest_symptom": False,
        "has_acute_trauma": False,
        "pain_note": "synthetic-note",
    }
    payload.update(overrides)
    return payload


def _weight(recorded_at: str, kg: float, **overrides) -> dict:
    payload = {"recorded_at": recorded_at, "weight_kg": kg}
    payload.update(overrides)
    return payload


# ===========================================================================
# Section A: migration head + Phase 2 schema (points 1-2)
# ===========================================================================


def _run_alembic(*args):
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(_BACKEND_DIR),
        capture_output=True,
        text=True,
    )


def test_e2e_migration_head_is_current():
    """Point 1: Alembic has exactly one head, at the current chain tip.

    Tracks the live migration head; advances per migration. Currently
    ``0007_training_plans`` (Phase 4), advanced from the Phase 2 head
    ``0006_health_weight_tracking``.
    """
    proc = _run_alembic("heads")
    assert proc.returncode == 0, proc.stderr
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1, f"expected exactly one head, got: {lines}"
    assert lines[0].split()[0] == "0007_training_plans", lines[0]


def test_e2e_phase2_tables_present():
    """Point 2: Phase 2 tables are registered in the ORM metadata."""
    from app.db.base import Base
    import app.health.models  # noqa: F401  (registers tables on Base)
    import app.auth.models  # noqa: F401

    tables = set(Base.metadata.tables)
    for name in ("health_profiles", "health_checkins", "weight_records"):
        assert name in tables, f"Phase 2 table {name!r} missing from metadata"


# ===========================================================================
# Section B: full Phase 2 user journey (user A)
# ===========================================================================


@pytest.mark.asyncio
async def test_e2e_phase2_full_user_journey(client):
    """Profile -> today check-in -> abnormal pain -> red_flag -> weight ->
    trend/grid -> delete -> not-configured. All data synthetic."""
    token = await _login_user(client, "13900800001")
    h = _h(token)

    # --- Profile: not-configured first ---
    resp = await client.get(PROFILE, headers=h)
    assert resp.status_code == 200
    not_cfg = resp.json()
    assert not_cfg["configured"] is False
    assert not_cfg["profile"] is None
    readiness = not_cfg["readiness"]
    assert readiness["readiness"] == "missing_required_data"
    # Missing data is named, never guessed / silently "ready".
    assert "fitness_goal" in readiness["missing_fields"]
    assert readiness["missing_fields"]  # non-empty

    # --- Profile: configure (ready). Missing stays missing: leave pain /
    #     diet lists empty; allergy is carried but must NOT leak into readiness.
    resp = await client.put(PROFILE, json=_ready_profile(), headers=h)
    assert resp.status_code == 200, resp.text
    configured = resp.json()
    assert configured["configured"] is True
    assert configured["profile"]["version"] >= 1
    assert configured["readiness"]["readiness"] == "ready"
    assert configured["readiness"]["missing_fields"] == []
    # Privacy: the raw allergy label never appears in the readiness payload.
    assert "synthetic-peanut" not in resp.text.split('"readiness"')[1]

    # --- Today check-in: not checked in yet ---
    resp = await client.get(f"{TODAY}?local_date=2026-07-23", headers=h)
    assert resp.status_code == 200
    assert resp.json() == {"checked_in": False, "checkin": None}

    # --- Normal quick check-in (the ~20s path) ---
    resp = await client.put(
        TODAY, json=_normal_checkin("2026-07-23"), headers=h
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["risk_summary"] == "normal"

    # --- abnormal_pain=true WITHOUT follow-up is deterministically rejected ---
    resp = await client.put(
        TODAY,
        json=_normal_checkin("2026-07-23", abnormal_pain=True),
        headers=h,
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "pain_followup_required"

    # --- abnormal pain with a non-red-flag follow-up -> caution ---
    resp = await client.put(
        TODAY,
        json=_normal_checkin(
            "2026-07-23",
            abnormal_pain=True,
            pain_followup=_pain_followup(pain_intensity="mild"),
        ),
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["risk_summary"] == "caution"

    # --- red-flag routing: acute trauma follow-up -> red_flag (NOT normal) ---
    resp = await client.put(
        TODAY,
        json=_normal_checkin(
            "2026-07-22",
            abnormal_pain=True,
            daily_status="safety_adjustment",
            pain_followup=_pain_followup(has_acute_trauma=True),
        ),
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    red = resp.json()
    assert red["risk_summary"] == "red_flag"
    # red_flag must never read as an ordinary / success / normal state.
    assert red["risk_summary"] != "normal"
    assert red["risk_summary"] != "caution"

    # --- Weight: one record -> insufficient trend (no fabricated precision) ---
    resp = await client.post(
        WEIGHT,
        json=_weight("2026-07-21T08:00:00Z", 70.0),
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["source"] == "manual"  # server-set, never client-supplied

    resp = await client.get(f"{TREND}?window=3", headers=h)
    assert resp.status_code == 200
    trend1 = resp.json()
    assert trend1["sufficient"] is False
    assert trend1["trend"] == []  # no fabricated trend points
    # No advice / warning / pass-fail keys exist on the trend payload.
    for forbidden in ("advice", "warning", "adjustment", "verdict"):
        assert forbidden not in trend1

    # --- Weight: add two more -> sufficient moving trend ---
    await client.post(WEIGHT, json=_weight("2026-07-22T08:00:00Z", 69.5), headers=h)
    await client.post(WEIGHT, json=_weight("2026-07-23T08:00:00Z", 69.0), headers=h)
    resp = await client.get(f"{TREND}?window=3", headers=h)
    trend2 = resp.json()
    assert trend2["sufficient"] is True
    assert len(trend2["trend"]) >= 1
    assert len(trend2["records"]) == 3

    # --- Activity grid: projects the four Phase 2 statuses only ---
    # Seed two more engagement days to cover active_rest / safety_adjustment.
    await client.put(
        TODAY,
        json=_normal_checkin("2026-07-21", daily_status="active_rest"),
        headers=h,
    )
    resp = await client.get(
        f"{GRID}?start_date=2026-07-19&end_date=2026-07-24", headers=h
    )
    assert resp.status_code == 200
    grid = resp.json()
    statuses = {c["status"] for c in grid["cells"]}
    assert statuses.issubset(
        {"none", "checked_in", "active_rest", "safety_adjustment"}
    )
    # The seeded engagement days are reflected; plan-execution statuses absent.
    assert "active_rest" in statuses
    assert "checked_in" in statuses
    assert "none" in statuses
    for forbidden in ("partial_execution", "main_plan_completed"):
        assert forbidden not in statuses

    # --- Delete profile -> post-delete reflects not-configured (retention) ---
    resp = await client.delete(PROFILE, headers=h)
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] is True
    resp = await client.get(PROFILE, headers=h)
    assert resp.json()["configured"] is False
    assert resp.json()["profile"] is None


# ===========================================================================
# Section C: restricted qualifier never becomes ordinary (point: red_flag /
# restricted routing). A restricted profile routes a normal check-in to
# ``restricted``, distinct from ``normal``/``caution``.
# ===========================================================================


@pytest.mark.asyncio
async def test_e2e_restricted_profile_routes_checkin_to_restricted(client):
    token = await _login_user(client, "13900800002")
    h = _h(token)

    # Profile with a structured restricted qualifier (underage == yes).
    resp = await client.put(
        PROFILE,
        json=_ready_profile(risk_screen={"underage": "yes"}),
        headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["readiness"]["readiness"] == "restricted"
    assert resp.json()["readiness"]["restricted_reason"] == "underage"

    # A normal (non-pain) check-in is classified ``restricted`` (not normal),
    # because the profile qualifier is forwarded to the check-in classifier.
    resp = await client.put(
        TODAY, json=_normal_checkin("2026-07-23"), headers=h
    )
    assert resp.status_code == 200, resp.text
    summary = resp.json()["risk_summary"]
    assert summary == "restricted"
    assert summary != "normal"


# ===========================================================================
# Section D: cross-user isolation / account switch (point: switching accounts
# leaves no previous-user health data; cross-user read/write/delete blocked).
# ===========================================================================


@pytest.mark.asyncio
async def test_e2e_cross_user_isolation_account_switch(client):
    token_a = await _login_user(client, "13900800003")
    token_b = await _login_user(client, "13900800004")
    ha, hb = _h(token_a), _h(token_b)

    # A configures a profile and records a check-in + weight.
    await client.put(PROFILE, json=_ready_profile(), headers=ha)
    await client.put(TODAY, json=_normal_checkin("2026-07-23"), headers=ha)
    w = await client.post(
        WEIGHT, json=_weight("2026-07-23T08:00:00Z", 70.0), headers=ha
    )
    a_weight_id = w.json()["id"]
    a_today = await client.get(f"{TODAY}?local_date=2026-07-23", headers=ha)
    a_checkin_id = a_today.json()["checkin"]["id"]

    # --- "Account switch": user B sees a completely empty Phase 2 state ---
    resp = await client.get(PROFILE, headers=hb)
    assert resp.json()["configured"] is False
    assert resp.json()["profile"] is None

    resp = await client.get(f"{TODAY}?local_date=2026-07-23", headers=hb)
    assert resp.json() == {"checked_in": False, "checkin": None}

    resp = await client.get(CHECKINS, headers=hb)
    assert resp.json() == []

    resp = await client.get(TREND, headers=hb)
    assert resp.json()["records"] == []

    resp = await client.get(GRID, headers=hb)
    assert {c["status"] for c in resp.json()["cells"]} == {"none"}

    # --- Cross-user delete is rejected (404 not_found); A still owns the data ---
    resp = await client.delete(f"{CHECKINS}/{a_checkin_id}", headers=hb)
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"

    resp = await client.delete(f"{WEIGHT}/{a_weight_id}", headers=hb)
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"

    # A still sees their check-in and weight (B could not touch them).
    assert (
        await client.get(f"{TODAY}?local_date=2026-07-23", headers=ha)
    ).json()["checked_in"] is True
    assert len((await client.get(WEIGHT, headers=ha)).json()) == 1


# ===========================================================================
# Section E: privacy — deterministic outputs carry no raw sensitive values.
# The readiness reason / missing_fields / restricted_reason name fields and
# qualifiers only; allergy labels, pain notes and diet exclusions never leak.
# ===========================================================================


@pytest.mark.asyncio
async def test_e2e_no_raw_sensitive_values_in_outputs(client):
    token = await _login_user(client, "13900800005")
    h = _h(token)

    private_allergy = "SYNTHETIC-PRIVATE-allergy-label"
    private_diet = "SYNTHETIC-PRIVATE-diet-exclusion"
    private_pain_note = "SYNTHETIC-PRIVATE-pain-note"

    resp = await client.put(
        PROFILE,
        json=_ready_profile(
            allergies=[{"label": private_allergy}],
            diet_exclusions=[{"item": private_diet}],
        ),
        headers=h,
    )
    assert resp.status_code == 200

    # readiness payload must not echo the raw allergy / diet values.
    readiness_blob = str(resp.json()["readiness"])
    assert private_allergy not in readiness_blob
    assert private_diet not in readiness_blob

    # A red-flag check-in: the pain_note is untrusted free text and must not
    # appear in the stored risk_summary / reason fields.
    resp = await client.put(
        TODAY,
        json=_normal_checkin(
            "2026-07-23",
            abnormal_pain=True,
            pain_followup=_pain_followup(
                has_neurological_symptom=True, pain_note=private_pain_note
            ),
        ),
        headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["risk_summary"] == "red_flag"
    # The stored check-in response carries pain_followup (owner-visible) but
    # the risk_summary is just the tier string, never the free-text note.
    assert resp.json()["risk_summary"] != private_pain_note
