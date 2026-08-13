from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.nutrition.schemas import (
    DayKind, GateStatus, NutritionContext, NutritionVersions, WeightSource,
)
from app.nutrition.safety import RISK_FIELDS, classify_nutrition, compose_context_fingerprint

NOW = datetime(2026, 8, 1, 4, tzinfo=timezone.utc)
ALLOWED_EXCLUSIONS = {"avoid_pork", "avoid_beef"}


def _context(**updates):
    data = dict(
        age=30, height_cm=170.0, account_updated_at=NOW,
        weight_source=WeightSource(kind="manual_record", record_id="weight-1",
                                   recorded_at=NOW, timestamp=NOW, weight_kg=65),
        profile_version=2, profile_updated_at=NOW,
        risk_screen={field: "no" for field in RISK_FIELDS},
        food_allergen_codes=[], excluded_food_codes=[],
        checkin_present=True, checkin_risk="normal", checkin_token="checkin-v1",
        posture_risk="normal", active_plan_present=True,
        active_plan_goal="posture_improvement", active_plan_version_id="plan-1",
        training_decision_gate="eligible",
        day_kind=DayKind.training_day, current_local_date=date(2026, 8, 1),
        iana_timezone="Asia/Shanghai",
        versions=NutritionVersions(policy_version="v1", catalog_version="v1",
                                   source_manifest_version="v1", media_manifest_version="v1"),
    )
    data.update(updates)
    return NutritionContext(**data)


def test_complete_supported_context_is_eligible():
    decision = classify_nutrition(_context(), ALLOWED_EXCLUSIONS)
    assert decision.gate == GateStatus.eligible
    assert decision.missing_field_codes == []
    assert decision.bmi_category == "supported"


@pytest.mark.parametrize("field", RISK_FIELDS)
def test_every_yes_risk_answer_is_restricted(field):
    risk = {name: "no" for name in RISK_FIELDS}
    risk[field] = "yes"
    result = classify_nutrition(_context(risk_screen=risk), ALLOWED_EXCLUSIONS)
    assert result.gate == GateStatus.restricted
    assert f"risk_screen_yes:{field}" in result.reason_codes


@pytest.mark.parametrize("age,expected", [
    (17, GateStatus.restricted), (18, GateStatus.limited_education),
    (19, GateStatus.eligible), (64, GateStatus.eligible),
    (65, GateStatus.limited_education),
])
def test_age_boundaries(age, expected):
    assert classify_nutrition(_context(age=age), ALLOWED_EXCLUSIONS).gate == expected


def test_underage_age_cannot_be_downgraded_by_no_answer():
    result = classify_nutrition(_context(age=17), ALLOWED_EXCLUSIONS)
    assert result.gate == GateStatus.restricted


@pytest.mark.parametrize("bmi,expected", [
    (18.49, GateStatus.limited_education), (18.5, GateStatus.eligible),
    (23.99, GateStatus.eligible), (24, GateStatus.eligible_conservative),
    (27.99, GateStatus.eligible_conservative), (28, GateStatus.limited_education),
])
def test_bmi_boundaries(bmi, expected):
    weight = bmi * 1.7 ** 2
    result = classify_nutrition(_context(weight_source=WeightSource(
        kind="manual_record", record_id="w", recorded_at=NOW,
        timestamp=NOW, weight_kg=weight)), ALLOWED_EXCLUSIONS)
    assert result.gate == expected


def test_energy_center_outside_supported_envelope_is_limited():
    context = _context(age=19, height_cm=200, weight_source=WeightSource(
        kind="account", timestamp=NOW, weight_kg=80))
    assert classify_nutrition(context, ALLOWED_EXCLUSIONS).gate == GateStatus.limited_education


def test_account_weight_above_manual_record_limit_is_limited_not_an_exception():
    context = _context(weight_source=WeightSource(
        kind="account", timestamp=NOW, weight_kg=350,
    ))
    assert classify_nutrition(context, ALLOWED_EXCLUSIONS).gate == GateStatus.limited_education


def test_invalid_legacy_body_measurement_requires_clarification_not_an_exception():
    result = classify_nutrition(_context(height_cm=0), ALLOWED_EXCLUSIONS)
    assert result.gate == GateStatus.clarification_required
    assert "body_measurements_out_of_range" in result.missing_field_codes


def test_restricted_age_does_not_require_formula_domain_to_be_valid():
    result = classify_nutrition(_context(age=1, height_cm=0), ALLOWED_EXCLUSIONS)
    assert result.gate == GateStatus.restricted


@pytest.mark.parametrize("risk", ["red_flag", "restricted", "caution"])
def test_current_checkin_risk_precedence(risk):
    result = classify_nutrition(_context(checkin_risk=risk), ALLOWED_EXCLUSIONS)
    expected = {"red_flag": GateStatus.red_flag, "restricted": GateStatus.restricted,
                "caution": GateStatus.eligible_conservative}[risk]
    assert result.gate == expected


def test_red_flag_wins_over_restricted_and_missing():
    risk = {field: "no" for field in RISK_FIELDS}
    risk["pregnancy_or_postpartum"] = "yes"
    result = classify_nutrition(_context(checkin_risk="red_flag", risk_screen=risk,
                                         food_allergen_codes=None), ALLOWED_EXCLUSIONS)
    assert result.gate == GateStatus.red_flag


@pytest.mark.parametrize("updates,missing", [
    ({"food_allergen_codes": None}, "food_allergen_codes"),
    ({"excluded_food_codes": None}, "excluded_food_codes"),
    ({"excluded_food_codes": ["unknown"]}, "excluded_food_codes"),
    ({"has_legacy_allergies": True}, "legacy_allergies"),
    ({"has_legacy_diet_exclusions": True}, "legacy_diet_exclusions"),
    ({"checkin_present": False, "checkin_token": None}, "current_day_checkin"),
    ({"active_plan_present": False}, "active_training_plan"),
    ({"active_plan_goal": "mobility"}, "active_plan_goal"),
    ({"training_decision_gate": None}, "training_decision_gate"),
    ({"day_kind": None}, "effective_training_day_state"),
])
def test_missing_unknown_and_unresolved_context_requires_clarification(updates, missing):
    result = classify_nutrition(_context(**updates), ALLOWED_EXCLUSIONS)
    assert result.gate == GateStatus.clarification_required
    assert missing in result.missing_field_codes


@pytest.mark.parametrize("field", RISK_FIELDS)
def test_unknown_or_missing_risk_answer_requires_clarification(field):
    risk = {name: "no" for name in RISK_FIELDS}
    risk[field] = "unknown"
    result = classify_nutrition(_context(risk_screen=risk), ALLOWED_EXCLUSIONS)
    assert result.gate == GateStatus.clarification_required
    assert f"risk_screen.{field}" in result.missing_field_codes


def test_fingerprint_contains_no_raw_body_or_legacy_text_and_tracks_versions():
    context = _context()
    fingerprint = compose_context_fingerprint(context)
    changed_raw_values = context.model_copy(deep=True)
    changed_raw_values.height_cm = 171
    changed_raw_values.weight_source.weight_kg = 66
    assert compose_context_fingerprint(changed_raw_values) == fingerprint
    changed_version = context.model_copy(deep=True)
    changed_version.profile_version = 3
    assert compose_context_fingerprint(changed_version) != fingerprint
    changed_weight_freshness = context.model_copy(deep=True)
    changed_weight_freshness.weight_source.timestamp = datetime(2026, 8, 1, 5, tzinfo=timezone.utc)
    assert compose_context_fingerprint(changed_weight_freshness) != fingerprint


def test_every_owned_freshness_source_changes_the_fingerprint():
    context = _context()
    variants = []

    account = context.model_copy(deep=True)
    account.account_updated_at = datetime(2026, 8, 1, 5, tzinfo=timezone.utc)
    variants.append(account)

    profile = context.model_copy(deep=True)
    profile.profile_updated_at = datetime(2026, 8, 1, 5, tzinfo=timezone.utc)
    variants.append(profile)

    checkin = context.model_copy(deep=True)
    checkin.checkin_token = "checkin-v2"
    variants.append(checkin)

    plan = context.model_copy(deep=True)
    plan.active_plan_version_id = "plan-2"
    variants.append(plan)

    training_gate = context.model_copy(deep=True)
    training_gate.training_decision_gate = "eligible_conservative"
    variants.append(training_gate)

    for field in NutritionVersions.model_fields:
        version = context.model_copy(deep=True)
        setattr(version.versions, field, "v2")
        variants.append(version)

    baseline = compose_context_fingerprint(context)
    assert all(compose_context_fingerprint(variant) != baseline for variant in variants)
