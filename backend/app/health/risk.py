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

from app.health.schemas import HealthProfileData, YesNoUnknown


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
