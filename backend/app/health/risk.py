"""Pure deterministic profile readiness / risk classification (Phase 2 spec).

Design constraints (mirror ``app.posture.risk_rules``):
- PURE functions only: no HTTP, no DB session, no LLM, no I/O.
- Classification consumes the structured ``HealthProfileData`` fields only.
- Free-text ``note`` fields (pain note, allergy note, diet note) NEVER
  influence the tier - only structured fields (spec Safety, Recommendation
  And AI Behavior).
- Phase 2 profile classification emits ``ready`` / ``missing_required_data`` /
  ``restricted`` only. ``red_flag`` is reserved for the daily check-in pain
  follow-up (Task 3); NO profile field produces ``red_flag`` in Phase 2.

The returned ``ReadinessResult`` carries no raw sensitive values - only the
tier, a reason naming field names, the list of missing field names, and the
restricted qualifier name. Allergy labels, pain notes, diet exclusions and
body values never appear in it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.health.schemas import HealthProfileData, PainIntensity, PainStarted, YesNoUnknown


# Bumped only when a rule's behaviour changes.
RISK_VERSION = "2026-07-22-v1"

# Readiness tiers produced by the PROFILE in Phase 2.
READY = "ready"
MISSING_REQUIRED_DATA = "missing_required_data"
RESTRICTED = "restricted"

# ``red_flag`` is intentionally NOT produced by the profile in Phase 2; it is
# reserved for the check-in pain follow-up (Task 3). The constant documents
# the complete tier vocabulary for downstream code.
RED_FLAG = "red_flag"

# Check-in risk_summary tiers (spec Domain Model, Daily Check-In). ``normal``
# and ``caution`` are check-in-specific; ``restricted`` / ``red_flag`` are
# shared with the profile tier vocabulary.
NORMAL = "normal"
CAUTION = "caution"

# Fields required to consider a profile "ready" for ordinary recommendation
# readiness (safety-boundaries section 4). Missing any of these yields
# ``missing_required_data``; the value is never inferred.
_REQUIRED_FIELDS = (
    "fitness_goal",
    "training_experience",
    "weekly_frequency",
    "session_duration_minutes",
    "equipment",
)

# risk_screen qualifiers that place a user in the ``restricted`` bucket until a
# future limited-mode specification exists (safety-boundaries section 2).
_RESTRICTED_QUALIFIERS = (
    "underage",
    "pregnancy_or_postpartum",
    "recent_surgery_or_major_injury",
    "major_chronic_condition",
    "eating_disorder_concern",
    "professional_instruction_limitations",
)


@dataclass(frozen=True)
class ReadinessResult:
    """Deterministic profile readiness classification result.

    Carries NO raw sensitive payloads: ``reason`` / ``missing_fields`` /
    ``restricted_reason`` name fields and qualifiers only, never allergy
    labels, pain notes, diet exclusions or body values.
    """

    readiness: str
    risk_version: str
    reason: str
    missing_fields: List[str] = field(default_factory=list)
    restricted_reason: Optional[str] = None


def _equipment_complete(profile: HealthProfileData) -> bool:
    """Equipment counts as present only when the object exists AND at least one
    of bodyweight / resistance_band is true (spec Domain Model)."""
    equipment = profile.equipment
    if equipment is None:
        return False
    return bool(equipment.bodyweight or equipment.resistance_band)


def missing_required_fields(profile: HealthProfileData) -> List[str]:
    """Return the required-field names that are absent on ``profile``."""
    missing: List[str] = []
    for name in _REQUIRED_FIELDS:
        if name == "equipment":
            if not _equipment_complete(profile):
                missing.append(name)
            continue
        if getattr(profile, name) is None:
            missing.append(name)
    return missing


def restricted_reason(profile: HealthProfileData) -> Optional[str]:
    """Return the first structured ``risk_screen`` qualifier equal to ``yes``.

    Only structured ``YesNoUnknown`` values drive this; free-text notes never
    do. Returns ``None`` when the screen is absent or no qualifier is ``yes``.
    """
    screen = profile.risk_screen
    if screen is None:
        return None
    for qualifier in _RESTRICTED_QUALIFIERS:
        if getattr(screen, qualifier) == YesNoUnknown.yes:
            return qualifier
    return None


def classify_readiness(profile: HealthProfileData) -> ReadinessResult:
    """Classify a profile into a readiness tier.

    Ordering (most safety-restrictive wins):
      1. ``restricted`` - a structured risk_screen qualifier is ``yes``. This
         takes precedence over missing data: a restricted user is restricted
         even when training inputs are incomplete.
      2. ``missing_required_data`` - at least one required training input is
         absent (never inferred).
      3. ``ready`` - all required inputs present and no restricted qualifier.
    """
    qualifier = restricted_reason(profile)
    if qualifier is not None:
        return ReadinessResult(
            readiness=RESTRICTED,
            risk_version=RISK_VERSION,
            reason=f"structured risk_screen qualifier '{qualifier}' is 'yes'",
            missing_fields=[],
            restricted_reason=qualifier,
        )

    missing = missing_required_fields(profile)
    if missing:
        return ReadinessResult(
            readiness=MISSING_REQUIRED_DATA,
            risk_version=RISK_VERSION,
            reason="missing required profile data: " + ", ".join(missing),
            missing_fields=missing,
            restricted_reason=None,
        )

    return ReadinessResult(
        readiness=READY,
        risk_version=RISK_VERSION,
        reason="all required training inputs present and no restricted qualifier",
        missing_fields=[],
        restricted_reason=None,
    )


# ---------------------------------------------------------------------------
# Daily check-in risk classification (Task 3)
#
# PURE function: consumes the structured ``CheckInCreate`` pain fields plus an
# optional profile ``restricted_reason`` qualifier. Free-text ``pain_note`` is
# NEVER read - only structured booleans / enums drive the tier (spec Safety,
# Recommendation And AI Behavior). Ordering is most-safety-restrictive wins.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckinRiskResult:
    """Deterministic daily check-in risk_summary classification result.

    Carries NO raw sensitive payloads: ``reason`` / ``red_flag_reason`` /
    ``restricted_reason`` name fields and qualifiers only, never pain notes.
    """

    risk_summary: str
    risk_version: str
    reason: str
    red_flag_reason: Optional[str] = None
    restricted_reason: Optional[str] = None


# Structured pain follow-up signals that unconditionally produce ``red_flag``
# (spec Safety). Each entry maps a follow-up field to the reason text used when
# it triggers, so the red_flag reason names the field deterministically.
_REDFLAG_SIGNALS = (
    ("has_neurological_symptom", "neurological symptom reported"),
    ("has_dizziness_or_chest_symptom", "dizziness or chest symptom reported"),
    ("has_acute_trauma", "acute trauma reported"),
)


def _redflag_signal(followup) -> Optional[str]:
    """Return the reason for the first unconditional red-flag signal, or None.

    Only structured boolean fields are inspected. ``pain_note`` is never read.
    """
    for field_name, reason in _REDFLAG_SIGNALS:
        if getattr(followup, field_name, False):
            return reason
    return None


def _severe_after_acute(followup) -> bool:
    """Configured severe-after-acute red-flag rule: severe pain that started
    after an acute event (spec Safety)."""
    return (
        followup.pain_intensity == PainIntensity.severe
        and followup.pain_started == PainStarted.after_acute_event
    )


def classify_checkin(checkin, restricted_qualifier: Optional[str] = None) -> CheckinRiskResult:
    """Classify a daily check-in into a deterministic risk_summary tier.

    Ordering (most safety-restrictive wins):
      1. ``red_flag`` - a structured red-flag pain follow-up signal is present
         (neurological symptom, dizziness/chest symptom, acute trauma, or the
         severe-after-acute rule).
      2. ``restricted`` - the caller's profile risk_screen has a ``yes``
         qualifier (passed in from the profile classifier). This is the
         ``restricted`` tier surfaced in the check-in risk_summary.
      3. ``caution`` - abnormal pain was reported with a complete, non-red-flag
         follow-up.
      4. ``normal`` - no abnormal pain and no restricted qualifier.

    ``restricted_qualifier`` is the profile qualifier name (e.g. ``underage``)
    or ``None`` when the profile is absent / has no restricted qualifier.
    """
    followup = checkin.pain_followup
    if checkin.abnormal_pain and followup is not None:
        signal_reason = _redflag_signal(followup)
        if signal_reason is not None:
            return CheckinRiskResult(
                risk_summary=RED_FLAG,
                risk_version=RISK_VERSION,
                reason=signal_reason,
                red_flag_reason=signal_reason,
                restricted_reason=None,
            )
        if _severe_after_acute(followup):
            reason = "severe pain reported after an acute event"
            return CheckinRiskResult(
                risk_summary=RED_FLAG,
                risk_version=RISK_VERSION,
                reason=reason,
                red_flag_reason=reason,
                restricted_reason=None,
            )

    if restricted_qualifier is not None:
        return CheckinRiskResult(
            risk_summary=RESTRICTED,
            risk_version=RISK_VERSION,
            reason=f"profile risk_screen qualifier '{restricted_qualifier}' is 'yes'",
            red_flag_reason=None,
            restricted_reason=restricted_qualifier,
        )

    if checkin.abnormal_pain:
        return CheckinRiskResult(
            risk_summary=CAUTION,
            risk_version=RISK_VERSION,
            reason="abnormal pain reported with no red-flag signal",
            red_flag_reason=None,
            restricted_reason=None,
        )

    return CheckinRiskResult(
        risk_summary=NORMAL,
        risk_version=RISK_VERSION,
        reason="no abnormal pain and no restricted qualifier",
        red_flag_reason=None,
        restricted_reason=None,
    )
