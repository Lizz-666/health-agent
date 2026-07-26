"""Training safety context assembly (Task 4).

Two layers:

- PURE helpers: IANA timezone validation, server-derived local date, the
  canonical structured check-in hash and freshness token. No DB / HTTP / LLM.
- ASYNC application adapter ``build_context``: composes the typed
  ``TrainingSafetyContext`` from current structured sources using existing
  domain-owned public read services (health profile / check-ins, posture active
  signals / global risk / priority suggestions). The only direct read query is a
  narrow ownership-filtered lookup of active confirmed posture goals in this
  module - the posture domain exposes no public accessor for that (spec-sanctioned
  gap fill). It writes nothing and duplicates no classifier.

Free text (pain_note) never reaches the engine input; it is excluded from the
structured hash and token. The server UTC clock is the freshness authority; a
client date is only compared, never trusted.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python < 3.9
    ZoneInfo = None  # type: ignore[misc, assignment]
    ZoneInfoNotFoundError = Exception  # type: ignore[misc, assignment]

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.health.risk import classify_checkin, restricted_reason
from app.health.schemas import YesNoUnknown
from app.health.service import get_profile_result, list_checkins
from app.posture.models import PostureUserGoal
from app.posture.safety import (
    compute_profile_risk,
    compute_signals_digest,
    load_active_signals,
)
from app.posture.service import get_priority_suggestions
from app.training.safety import SafetyPolicy
from app.training.schemas import (
    CheckInSnapshot,
    EvalMeta,
    HealthProfileSnapshot,
    PainLimitationSnapshot,
    PostureGoalSnapshot,
    PostureSnapshot,
    RequestSnapshot,
    RetainedPainRecord,
    TrainingSafetyContext,
    VersionMeta,
)

_ALL_QUALIFIERS = (
    "underage", "pregnancy_or_postpartum", "recent_surgery_or_major_injury",
    "major_chronic_condition", "eating_disorder_concern",
    "professional_instruction_limitations",
)


# ---------------------------------------------------------------------------
# PURE helpers
# ---------------------------------------------------------------------------


def validate_iana_timezone(tz: Optional[str]) -> bool:
    """Return True iff ``tz`` is a usable IANA timezone identifier."""
    if not isinstance(tz, str) or not tz.strip():
        return False
    if ZoneInfo is None:
        return False
    try:
        ZoneInfo(tz.strip())
    except (ZoneInfoNotFoundError, Exception):  # noqa: BLE001
        return False
    return True


def derive_local_date(utc: datetime, tz: Optional[str]) -> Optional[date]:
    """Derive the current local date from a server UTC clock + IANA tz."""
    if not validate_iana_timezone(tz):
        return None
    aware = utc if utc.tzinfo else utc.replace(tzinfo=timezone.utc)
    return aware.astimezone(ZoneInfo(tz)).date()  # type: ignore[arg-type]


def _structured_checkin_hash(checkin: Any, recomputed_risk: str) -> str:
    """sha256 over structured safety fields EXCLUDING ``pain_note``."""
    followup = getattr(checkin, "pain_followup", None)
    payload = {
        "abnormal_pain": bool(getattr(checkin, "abnormal_pain", False)),
        "pain_area": getattr(followup, "pain_area", None),
        "pain_started": _enum_val(getattr(followup, "pain_started", None)),
        "pain_intensity": _enum_val(getattr(followup, "pain_intensity", None)),
        "has_neurological_symptom": getattr(followup, "has_neurological_symptom", None),
        "has_dizziness_or_chest_symptom": getattr(followup, "has_dizziness_or_chest_symptom", None),
        "has_acute_trauma": getattr(followup, "has_acute_trauma", None),
        "recomputed_risk": recomputed_risk,
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _enum_val(value: Any) -> Optional[str]:
    return value.value if hasattr(value, "value") else value


def checkin_token(checkin: Any, recomputed_risk: str) -> str:
    """Freshness token: sha256(id | local_date | utc updated_at | risk_version |
    canonical structured safety hash). Excludes free text."""
    structured = _structured_checkin_hash(checkin, recomputed_risk)
    payload = {
        "id": str(getattr(checkin, "id")),
        "local_date": _iso(getattr(checkin, "local_date")),
        "updated_at": _iso(getattr(checkin, "updated_at")),
        "risk_version": getattr(checkin, "risk_version"),
        "structured_hash": structured,
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return aware.astimezone(timezone.utc).isoformat()
    return value.isoformat()


# ---------------------------------------------------------------------------
# ASYNC application adapter
# ---------------------------------------------------------------------------


def _risk_screen_dict(profile: Any) -> Optional[Dict[str, Optional[str]]]:
    screen = getattr(profile, "risk_screen", None)
    if screen is None:
        return None
    out: Dict[str, Optional[str]] = {}
    for q in _ALL_QUALIFIERS:
        val = getattr(screen, q, None)
        out[q] = val.value if isinstance(val, YesNoUnknown) else (
            val if val is None else str(val))
    return out


def _pain_limitations(
    profile: Any, policy: SafetyPolicy
) -> Optional[List[PainLimitationSnapshot]]:
    raw = getattr(profile, "pain_injury_limitations", None)
    if raw is None:
        return None
    out: List[PainLimitationSnapshot] = []
    for item in raw:
        body_raw = getattr(item, "body_area", "")
        status_raw = getattr(item, "status", "")
        out.append(PainLimitationSnapshot(
            body_area_raw=body_raw,
            status_raw=status_raw,
            body_area_canonical=policy.normalize_body_area(body_raw),
            status_canonical=policy.normalize_status(status_raw),
        ))
    return out


async def _active_goals(
    db: AsyncSession, user_id: str, suggestions: Dict[str, Any]
) -> List[PostureGoalSnapshot]:
    """Narrow ownership-filtered read of active confirmed posture goals.

    The posture domain has no public accessor for active goals, so this module
    performs a read-only query scoped to ``user_id``. It writes nothing and
    duplicates no classifier.
    """
    result = await db.execute(
        select(PostureUserGoal).where(
            PostureUserGoal.user_id == UUID(user_id),
            PostureUserGoal.superseded_at.is_(None),
        ).order_by(PostureUserGoal.priority_rank)
    )
    rows = list(result.scalars().all())
    current_candidate_ids = {
        item.get("issue_id") for item in suggestions.get("normal_candidates", [])
        if item.get("issue_id")
    }
    blocked_issue_ids = {
        item.get("issue_id") for key in ("safety_blocked", "retest_required")
        for item in suggestions.get(key, []) if item.get("issue_id")
    }
    return [
        PostureGoalSnapshot(
            issue_id=r.issue_id,
            active=(
                r.issue_id in current_candidate_ids
                and r.suggestion_id == suggestions.get("suggestion_id")
                and r.profile_version == suggestions.get("profile_version")
                and r.rule_version == suggestions.get("rule_version")
                and r.risk_version == suggestions.get("risk_version")
            ),
            blocked=r.issue_id in blocked_issue_ids,
            confirmed_at=r.confirmed_at,
            suggestion_id=r.suggestion_id,
            profile_version=r.profile_version,
            rule_version=r.rule_version,
            risk_version=r.risk_version)
        for r in rows
    ]


async def build_context(
    db: AsyncSession,
    user_id: str,
    *,
    request: RequestSnapshot,
    policy: SafetyPolicy,
    catalog_version: Optional[str],
    source_manifest_version: Optional[str],
    evaluated_at_utc: Optional[datetime] = None,
) -> TrainingSafetyContext:
    """Assemble a ``TrainingSafetyContext`` from current structured sources."""
    now = evaluated_at_utc or datetime.now(timezone.utc)

    # --- Health profile (recomputed; never trust stored labels) ---
    profile_result = await get_profile_result(db, user_id)
    profile = profile_result.profile
    qualifier = restricted_reason(profile) if profile is not None else None
    if profile is None:
        health_snap = HealthProfileSnapshot(configured=False)
    else:
        equip = profile.equipment
        health_snap = HealthProfileSnapshot(
            configured=True,
            fitness_goal=_enum_val(profile.fitness_goal),
            training_experience=_enum_val(profile.training_experience),
            weekly_frequency=profile.weekly_frequency,
            session_duration_minutes=_enum_val(
                profile.session_duration_minutes),
            equipment_bodyweight=getattr(equip, "bodyweight", None) if equip else None,
            equipment_resistance_band=getattr(equip, "resistance_band", None) if equip else None,
            pain_limitations=_pain_limitations(profile, policy),
            risk_screen=_risk_screen_dict(profile),
            profile_version=profile.version,
            profile_updated_at=profile.updated_at,
        )

    # --- Timezone / current local date (server-derived) ---
    tz = request.iana_timezone
    tz_trusted = validate_iana_timezone(tz)
    current_local = derive_local_date(now, tz) if tz_trusted else None

    # --- Check-ins: current day + retained abnormal-pain history ---
    checkins = await list_checkins(db, user_id)
    current = next(
        (c for c in checkins
         if current_local is not None and c.local_date == current_local),
        None,
    )
    if current is not None:
        risk = classify_checkin(current, restricted_qualifier=qualifier)
        token = checkin_token(current, risk.risk_summary)
        followup = current.pain_followup
        checkin_snap = CheckInSnapshot(
            present=True, local_date=current.local_date,
            recomputed_risk=risk.risk_summary, token=token,
            abnormal_pain=current.abnormal_pain,
            pain_area_canonical=(
                policy.normalize_body_area(followup.pain_area)
                if current.abnormal_pain and followup is not None else None
            ))
    else:
        checkin_snap = CheckInSnapshot(present=False)

    retained: List[RetainedPainRecord] = []
    for c in checkins:
        if not c.abnormal_pain:
            continue
        if current_local is not None and c.local_date == current_local:
            continue  # current day is handled by the checkin snapshot
        risk = classify_checkin(c, restricted_qualifier=qualifier)
        followup = c.pain_followup
        retained.append(RetainedPainRecord(
            token=checkin_token(c, risk.risk_summary),
            recomputed_risk=risk.risk_summary,
            local_date=c.local_date,
            pain_area_canonical=(
                policy.normalize_body_area(followup.pain_area)
                if followup is not None else None
            ),
        ))

    # --- Posture: active signals digest, global risk, priority suggestions,
    #     and the narrow active-goal read ---
    signals = await load_active_signals(db, user_id)
    digest = compute_signals_digest(signals)
    classification = await compute_profile_risk(db, user_id, None)
    suggestions = await get_priority_suggestions(db, user_id, now=now)
    goals = await _active_goals(db, user_id, suggestions)
    posture_snap = PostureSnapshot(
        active_signals_digest=digest,
        global_risk_tier=classification.risk_tier,
        risk_version=classification.risk_version,
        goals=goals,
    )

    versions = VersionMeta(
        policy_version=policy.policy_version,
        catalog_version=catalog_version,
        source_manifest_version=source_manifest_version,
        schema_version="v1",
    )
    eval_meta = EvalMeta(
        evaluated_at_utc=now,
        iana_timezone=tz if tz_trusted else None,
        current_local_date=current_local,
        timezone_trusted=tz_trusted,
    )

    return TrainingSafetyContext(
        user_id=user_id,
        health=health_snap,
        checkin=checkin_snap,
        retained_pain=retained,
        posture=posture_snap,
        request=request,
        versions=versions,
        eval=eval_meta,
    )
