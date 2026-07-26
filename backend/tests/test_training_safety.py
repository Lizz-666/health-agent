"""Synthetic safety matrix for the pure training safety classifier (Task 4).

Covers every gate tier and source combination required by the spec Test And
Evaluation Strategy: healthy/expereenced user, beginner caution, pain-limit
caution, missing profile/fields, null vs empty pain limitations, unknown pain
aliases, missing/unknown risk-screen, missing check-in, untrusted timezone,
client-date mismatch, restricted qualifier, posture restricted, current and
retained red flag, missing/stale posture goal, precedence, and the
deterministic fingerprint.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.training.safety import (
    SafetyPolicy,
    classify_safety,
    compose_fingerprint,
    load_safety_policy,
)
from app.training.schemas import (
    GateStatus,
    SafetyRiskTier,
    TrainingSafetyContext,
)

POLICY = load_safety_policy("app/training/data/training_safety_policy.v1.json")
EVAL_AT = datetime(2026, 7, 26, 1, 30, tzinfo=timezone.utc)
TODAY = date(2026, 7, 26)


def _full_risk_screen(value="no"):
    return {q: value for q in (
        "underage", "pregnancy_or_postpartum", "recent_surgery_or_major_injury",
        "major_chronic_condition", "eating_disorder_concern",
        "professional_instruction_limitations")}


def _ctx(**over):
    base = {
        "health": {
            "configured": True,
            "fitness_goal": "basic_strength",
            "training_experience": "experienced",
            "weekly_frequency": 3,
            "session_duration_minutes": 30,
            "equipment_bodyweight": True,
            "equipment_resistance_band": False,
            "pain_limitations": [],
            "risk_screen": _full_risk_screen(),
            "profile_version": 1,
            "profile_updated_at": EVAL_AT,
        },
        "checkin": {
            "present": True, "local_date": TODAY,
            "recomputed_risk": "normal", "token": "current-token",
        },
        "retained_pain": [],
        "posture": {
            "active_signals_digest": "empty-signals-digest",
            "global_risk_tier": "normal", "risk_version": "posture-rv",
            "goals": [{
                "issue_id": "lower_limb", "active": True, "blocked": False,
                "confirmed_at": EVAL_AT, "suggestion_id": "s1",
                "profile_version": "pv1", "rule_version": "rv1",
                "risk_version": "posture-rv",
            }],
        },
        "request": {
            "fitness_goal": "basic_strength", "equipment_bodyweight": True,
            "equipment_resistance_band": False, "weekly_frequency": 3,
            "session_duration_minutes": 30,
            "iana_timezone": "Asia/Shanghai",
        },
        "versions": {"policy_version": "v1", "catalog_version": "v1cat",
                     "source_manifest_version": "v1", "schema_version": "v1"},
        "eval": {"evaluated_at_utc": EVAL_AT, "iana_timezone": "Asia/Shanghai",
                 "current_local_date": TODAY, "timezone_trusted": True},
    }
    base.update(over)
    return TrainingSafetyContext.model_validate(base)


def test_eligible_complete_experienced_profile():
    d = classify_safety(_ctx(), POLICY)
    assert d.gate_status is GateStatus.eligible
    assert d.risk_tier is SafetyRiskTier.normal


def test_eligible_conservative_for_beginner():
    d = classify_safety(_ctx(**{"health": {**_ctx().health.model_dump(),
        "training_experience": "beginner"}}), POLICY)
    assert d.gate_status is GateStatus.eligible_conservative
    assert d.risk_tier is SafetyRiskTier.caution


def test_eligible_conservative_for_non_empty_pain_limitations():
    health = _ctx().health.model_dump(exclude_none=False)
    health["pain_limitations"] = [
        {"body_area_raw": "knee", "status_raw": "aching",
         "body_area_canonical": "knee", "status_canonical": "aching"}]
    d = classify_safety(_ctx(health=health), POLICY)
    assert d.gate_status is GateStatus.eligible_conservative


def test_clarification_when_profile_missing():
    d = classify_safety(_ctx(health={"configured": False}), POLICY)
    assert d.gate_status is GateStatus.clarification_required
    assert "health_profile" in d.missing_fields


def test_clarification_when_required_field_missing():
    health = _ctx().health.model_dump()
    health["weekly_frequency"] = None
    d = classify_safety(_ctx(health=health), POLICY)
    assert d.gate_status is GateStatus.clarification_required
    assert "weekly_frequency" in d.missing_fields


def test_clarification_when_request_is_incomplete_or_mismatched():
    incomplete = _ctx().request.model_dump()
    incomplete["weekly_frequency"] = None
    decision = classify_safety(_ctx(request=incomplete), POLICY)
    assert decision.gate_status is GateStatus.clarification_required
    assert "recommendation_request" in decision.missing_fields

    mismatched = _ctx().request.model_dump()
    mismatched["weekly_frequency"] = 5
    decision = classify_safety(_ctx(request=mismatched), POLICY)
    assert decision.gate_status is GateStatus.clarification_required
    assert "recommendation_request" in decision.missing_fields


def test_clarification_when_pain_limitations_null_vs_empty():
    # None = not answered -> clarification.
    health = _ctx().health.model_dump()
    health["pain_limitations"] = None
    d = classify_safety(_ctx(health=health), POLICY)
    assert d.gate_status is GateStatus.clarification_required
    assert "pain_injury_limitations" in d.missing_fields
    # [] = explicitly answered none -> not a missing field (eligible stays).
    health2 = _ctx().health.model_dump()
    health2["pain_limitations"] = []
    assert classify_safety(_ctx(health=health2), POLICY).gate_status is GateStatus.eligible


def test_clarification_when_pain_alias_unknown():
    health = _ctx().health.model_dump()
    health["pain_limitations"] = [
        {"body_area_raw": "left kneee", "status_raw": "weird",
         "body_area_canonical": None, "status_canonical": None}]
    d = classify_safety(_ctx(health=health), POLICY)
    assert d.gate_status is GateStatus.clarification_required
    assert "pain_body_area" in d.missing_fields
    assert "pain_status" in d.missing_fields


def test_clarification_when_risk_screen_unknown_or_missing():
    for bad in ("unknown", None):
        screen = _full_risk_screen()
        screen["underage"] = bad
        health = _ctx().health.model_dump()
        health["risk_screen"] = screen
        d = classify_safety(_ctx(health=health), POLICY)
        assert d.gate_status is GateStatus.clarification_required, bad


def test_clarification_when_current_checkin_missing():
    d = classify_safety(_ctx(checkin={"present": False}), POLICY)
    assert d.gate_status is GateStatus.clarification_required
    assert "current_day_checkin" in d.missing_fields


def test_clarification_when_current_pain_area_cannot_be_normalized():
    d = classify_safety(_ctx(checkin={
        "present": True, "local_date": TODAY, "recomputed_risk": "caution",
        "token": "t", "abnormal_pain": True,
        "pain_area_canonical": None}), POLICY)
    assert d.gate_status is GateStatus.clarification_required
    assert "current_checkin.pain_area" in d.missing_fields


def test_clarification_when_retained_pain_area_cannot_be_normalized():
    d = classify_safety(_ctx(retained_pain=[{
        "token": "old", "recomputed_risk": "caution",
        "local_date": date(2026, 7, 20), "pain_area_canonical": None,
    }]), POLICY)
    assert d.gate_status is GateStatus.clarification_required
    assert "retained_pain.pain_area" in d.missing_fields


@pytest.mark.parametrize("field", ["catalog_version", "source_manifest_version"])
def test_clarification_when_release_version_is_missing(field):
    versions = _ctx().versions.model_dump()
    versions[field] = None
    d = classify_safety(_ctx(versions=versions), POLICY)
    assert d.gate_status is GateStatus.clarification_required


@pytest.mark.parametrize("path,value", [
    ("checkin", "danger"),
    ("posture", "danger"),
])
def test_context_schema_rejects_unknown_risk_tier(path, value):
    payload = _ctx().model_dump()
    if path == "checkin":
        payload[path]["recomputed_risk"] = value
    else:
        payload[path]["global_risk_tier"] = value
    with pytest.raises(Exception):
        TrainingSafetyContext.model_validate(payload)


def test_context_schema_rejects_unknown_risk_screen_answer():
    payload = _ctx().model_dump()
    payload["health"]["risk_screen"]["underage"] = "maybe"
    with pytest.raises(Exception):
        TrainingSafetyContext.model_validate(payload)


def test_clarification_when_no_qualifying_posture_goal():
    blocked_goal = {
        **_ctx().posture.goals[0].model_dump(),
        "issue_id": "x", "blocked": True,
    }
    for goals in ([], [blocked_goal],
                  [{"issue_id": "x", "active": False, "blocked": False}]):
        posture = _ctx().posture.model_dump()
        posture["goals"] = goals
        d = classify_safety(_ctx(posture=posture), POLICY)
        assert d.gate_status is GateStatus.clarification_required, goals


def test_clarification_when_timezone_untrusted():
    ev = _ctx().eval.model_dump()
    ev["timezone_trusted"] = False
    ev["iana_timezone"] = None
    d = classify_safety(_ctx(eval=ev), POLICY)
    assert d.gate_status is GateStatus.clarification_required
    assert "iana_timezone" in d.missing_fields


def test_clarification_when_client_date_mismatches_server():
    req = _ctx().request.model_dump()
    req["client_local_date"] = date(2026, 7, 25)  # != server TODAY
    d = classify_safety(_ctx(request=req), POLICY)
    assert d.gate_status is GateStatus.clarification_required
    assert "client_local_date" in d.missing_fields


def test_restricted_from_risk_screen_yes():
    screen = _full_risk_screen()
    screen["pregnancy_or_postpartum"] = "yes"
    health = _ctx().health.model_dump()
    health["risk_screen"] = screen
    d = classify_safety(_ctx(health=health), POLICY)
    assert d.gate_status is GateStatus.restricted
    assert d.risk_tier is SafetyRiskTier.restricted
    assert any("risk_screen." in s for s in d.blocking_source_refs)


def test_restricted_from_posture():
    posture = _ctx().posture.model_dump()
    posture["global_risk_tier"] = "restricted"
    d = classify_safety(_ctx(posture=posture), POLICY)
    assert d.gate_status is GateStatus.restricted
    assert "posture_signal" in d.blocking_source_refs


def test_red_flag_from_current_checkin():
    d = classify_safety(_ctx(checkin={
        "present": True, "local_date": TODAY,
        "recomputed_risk": "red_flag", "token": "t"}), POLICY)
    assert d.gate_status is GateStatus.red_flag
    assert "current_checkin" in d.blocking_source_refs


def test_red_flag_from_retained_pain_uncleared():
    ctx = _ctx(retained_pain=[{
        "token": "ret-tok", "recomputed_risk": "red_flag",
        "local_date": date(2026, 7, 20)}])
    d = classify_safety(ctx, POLICY)
    assert d.gate_status is GateStatus.red_flag
    assert any(s.startswith("retained_pain:") for s in d.blocking_source_refs)


def test_newer_normal_checkin_does_not_clear_retained_red_flag():
    # A retained historical red flag plus a normal current day stays red_flag.
    ctx = _ctx(retained_pain=[{
        "token": "ret-tok", "recomputed_risk": "red_flag",
        "local_date": date(2026, 7, 20)}])
    assert classify_safety(ctx, POLICY).gate_status is GateStatus.red_flag


def test_red_flag_precedence_over_clarification():
    # Retained red flag + missing current check-in -> red_flag, not clarification.
    ctx = _ctx(checkin={"present": False}, retained_pain=[{
        "token": "ret-tok", "recomputed_risk": "red_flag",
        "local_date": date(2026, 7, 20)}])
    assert classify_safety(ctx, POLICY).gate_status is GateStatus.red_flag


def test_restricted_precedence_over_clarification():
    # risk_screen yes + a missing field -> restricted, not clarification.
    screen = _full_risk_screen()
    screen["underage"] = "yes"
    health = _ctx().health.model_dump()
    health["risk_screen"] = screen
    health["weekly_frequency"] = None  # a missing field
    d = classify_safety(_ctx(health=health), POLICY)
    assert d.gate_status is GateStatus.restricted


def test_red_flag_precedence_over_restricted():
    screen = _full_risk_screen()
    screen["underage"] = "yes"
    health = _ctx().health.model_dump()
    health["risk_screen"] = screen
    ctx = _ctx(health=health, checkin={
        "present": True, "local_date": TODAY,
        "recomputed_risk": "red_flag", "token": "t"})
    assert classify_safety(ctx, POLICY).gate_status is GateStatus.red_flag


def test_checkin_caution_is_conservative():
    d = classify_safety(_ctx(checkin={
        "present": True, "local_date": TODAY,
        "recomputed_risk": "caution", "token": "t"}), POLICY)
    assert d.gate_status is GateStatus.eligible_conservative


def test_decision_carries_no_raw_sensitive_values():
    screen = _full_risk_screen()
    screen["underage"] = "yes"
    health = _ctx().health.model_dump()
    health["risk_screen"] = screen
    d = classify_safety(_ctx(health=health), POLICY)
    blob = d.model_dump_json()
    # No raw pain notes / values leak into the decision (codes only).
    assert "pain_note" not in blob
    assert "underage" in blob  # qualifier code is allowed


def test_fingerprint_is_deterministic_and_version_sensitive():
    ctx = _ctx()
    fp1 = compose_fingerprint(ctx)
    fp2 = compose_fingerprint(ctx)
    assert fp1 == fp2
    # Changing profile_version changes the fingerprint.
    changed = _ctx(health={**ctx.health.model_dump(), "profile_version": 2})
    assert compose_fingerprint(changed) != fp1
    goal = ctx.posture.goals[0].model_dump()
    goal["suggestion_id"] = "new-suggestion"
    posture = ctx.posture.model_dump()
    posture["goals"] = [goal]
    assert compose_fingerprint(_ctx(posture=posture)) != fp1


def test_decision_has_no_candidate_ids():
    # Restricted/red_flag must expose no candidate IDs; the decision structurally
    # carries none (candidates live in candidates.py).
    d = classify_safety(_ctx(checkin={
        "present": True, "local_date": TODAY,
        "recomputed_risk": "red_flag", "token": "t"}), POLICY)
    assert not hasattr(d, "candidate_ids")
    assert not hasattr(d, "candidates")


def test_safety_policy_rejects_ambiguous_alias():
    with pytest.raises(Exception):
        SafetyPolicy.model_validate({
            "policy_version": "v1",
            "body_region_aliases": {"knee": ["kneecap"],
                                    "shoulder": ["kneecap"]},
            "status_aliases": {"aching": ["dull"]},
            "all_risk_screen_qualifiers": ["underage"],
            "restricted_risk_screen_qualifiers": ["underage"],
            "red_flag_followup_signals": ["has_acute_trauma"],
            "required_profile_fields": ["fitness_goal"],
            "risk_precedence": ["red_flag"],
            "caution_sources": {},
            "recovery": {},
        })


@pytest.mark.parametrize("field,bad_value", [
    ("required_profile_fields", ["fitness_goal"]),
    ("caution_sources", {}),
    ("recovery", {}),
])
def test_safety_policy_rejects_incomplete_control_sets(field, bad_value):
    payload = POLICY.model_dump()
    payload[field] = bad_value
    with pytest.raises(Exception):
        SafetyPolicy.model_validate(payload)
