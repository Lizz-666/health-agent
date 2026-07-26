"""Deterministic training safety classifier + versioned safety policy (Task 4).

The PURE engine ``classify_safety(context, policy) -> TrainingSafetyDecision``
consumes an already-assembled ``TrainingSafetyContext`` (no HTTP/DB/LLM) and
returns a deterministic decision honouring the spec precedence:

    red_flag > restricted > clarification_required > eligible_conservative > eligible

Hard safety rules (spec: Risk And Eligibility Rules, Safety decision):

- Red flags are recomputed from structured check-in pain follow-ups (current AND
  retained) and from an active posture red_flag tier. A retained record that
  still classifies as red flag stays blocking; a later normal day, time elapsed,
  acknowledgement or free text never clears it.
- Restricted comes from a structured risk_screen qualifier == yes or an active
  posture restricted tier.
- Missing/unknown safety data (profile fields, risk screen, pain limitations,
  current-day check-in, qualifying posture goal, untrusted timezone / client
  date) yields ``clarification_required``.
- Caution (-> eligible_conservative) comes from the approved caution sources.
- Free text, posture severity alone, knowledge prose, AI output and
  acknowledgement never lower risk. Restricted / red_flag expose no candidates.

Reason codes / blocking refs are tokens + field names, never raw sensitive
values. The decision fingerprint excludes user_id and all raw payloads.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.training.schemas import (
    GateStatus,
    SafetyRiskTier,
    TrainingSafetyContext,
    TrainingSafetyDecision,
)

RED_FLAG = "red_flag"
RESTRICTED = "restricted"
CAUTION = "caution"
NORMAL = "normal"


class SafetyPolicy(BaseModel):
    """Typed view of ``training_safety_policy.v1.json``.

    Reverse alias maps are built and uniqueness-validated on load so a raw
    pain value maps to exactly one canonical code (ambiguous aliases fail
    closed).
    """

    model_config = ConfigDict(extra="forbid")

    policy_version: str = Field(..., min_length=1)
    body_region_aliases: Dict[str, List[str]]
    status_aliases: Dict[str, List[str]]
    all_risk_screen_qualifiers: List[str]
    restricted_risk_screen_qualifiers: List[str]
    red_flag_followup_signals: List[str]
    required_profile_fields: List[str]
    risk_precedence: List[str]
    caution_sources: Dict[str, bool]
    recovery: Dict[str, bool]

    # Reverse lookup maps (alias -> canonical), built + validated post-load.
    _body_region_index: Dict[str, str]
    _status_index: Dict[str, str]

    @model_validator(mode="after")
    def _build_reverse_maps(self):
        body_index: Dict[str, str] = {}
        status_index: Dict[str, str] = {}
        for canonical, aliases in self.body_region_aliases.items():
            for alias in aliases:
                key = alias.strip().lower()
                if key in body_index and body_index[key] != canonical:
                    raise ValueError(
                        f"ambiguous body_region alias {alias!r}")
                body_index[key] = canonical
        for canonical, aliases in self.status_aliases.items():
            for alias in aliases:
                key = alias.strip().lower()
                if key in status_index and status_index[key] != canonical:
                    raise ValueError(
                        f"ambiguous status alias {alias!r}")
                status_index[key] = canonical
        object.__setattr__(self, "_body_region_index", body_index)
        object.__setattr__(self, "_status_index", status_index)
        return self

    def normalize_body_area(self, raw: Optional[str]) -> Optional[str]:
        if not isinstance(raw, str) or not raw.strip():
            return None
        return self._body_region_index.get(raw.strip().lower())

    def normalize_status(self, raw: Optional[str]) -> Optional[str]:
        if not isinstance(raw, str) or not raw.strip():
            return None
        return self._status_index.get(raw.strip().lower())


def load_safety_policy(path: Union[str, Path]) -> SafetyPolicy:
    with Path(path).open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    # Drop non-model keys present in the JSON (review_scope/source/
    # fingerprint_components are documentation, not classifier inputs).
    keep = {
        "policy_version", "body_region_aliases", "status_aliases",
        "all_risk_screen_qualifiers", "restricted_risk_screen_qualifiers",
        "red_flag_followup_signals", "required_profile_fields",
        "risk_precedence", "caution_sources", "recovery",
    }
    return SafetyPolicy.model_validate({k: data[k] for k in keep})


def _is_missing_profile_field(hp, field_name: str) -> bool:
    if field_name == "equipment":
        return not (hp.equipment_bodyweight or hp.equipment_resistance_band)
    return getattr(hp, field_name) is None


def _goal_fingerprint(goals) -> str:
    active = [g for g in goals if g.active]
    parts = [f"{g.issue_id}:{int(g.blocked)}" for g in active]
    return "|".join(sorted(parts))


def compose_fingerprint(ctx: TrainingSafetyContext) -> str:
    """Deterministic sha256 over the version + freshness components.

    Excludes user_id and every raw sensitive payload (pain notes, values).
    """
    payload = {
        "profile_version": ctx.health.profile_version,
        "profile_updated_at": _iso(ctx.health.profile_updated_at),
        "current_checkin_token": ctx.checkin.token,
        "retained_pain_token_aggregate": "|".join(
            sorted(r.token for r in ctx.retained_pain)),
        "posture_signals_digest": ctx.posture.active_signals_digest,
        "posture_goal_fingerprint": _goal_fingerprint(ctx.posture.goals),
        "policy_version": ctx.versions.policy_version,
        "catalog_version": ctx.versions.catalog_version,
        "source_manifest_version": ctx.versions.source_manifest_version,
        "current_local_date": _iso(ctx.eval.current_local_date),
        "iana_timezone": ctx.eval.iana_timezone,
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if value is not None else None


def classify_safety(
    ctx: TrainingSafetyContext, policy: SafetyPolicy
) -> TrainingSafetyDecision:
    """Classify a training safety context into a deterministic decision."""
    reason: List[str] = []
    missing: List[str] = []

    # --- Timezone / client-date trust ---
    tz_ok = ctx.eval.timezone_trusted and bool(ctx.eval.iana_timezone)
    if not tz_ok:
        missing.append("iana_timezone")
        reason.append("untrusted_timezone")
    if ctx.request.client_local_date is not None:
        if (ctx.eval.current_local_date is None
                or ctx.request.client_local_date != ctx.eval.current_local_date):
            missing.append("client_local_date")
            reason.append("client_date_mismatch")

    # --- Red flag (recomputed; does not require a complete profile) ---
    red_sources: List[str] = []
    if ctx.checkin.present and ctx.checkin.recomputed_risk == RED_FLAG:
        red_sources.append("current_checkin")
    for rec in ctx.retained_pain:
        if rec.recomputed_risk == RED_FLAG:
            red_sources.append(
                "retained_pain:" + _iso(rec.local_date))
    if ctx.posture.global_risk_tier == RED_FLAG:
        red_sources.append("posture_signal")
    is_red = bool(red_sources)

    # --- Restricted (risk_screen qualifier yes / posture restricted) ---
    restr_sources: List[str] = []
    risk_screen = ctx.health.risk_screen or {}
    for q in policy.restricted_risk_screen_qualifiers:
        if risk_screen.get(q) == "yes":
            restr_sources.append("risk_screen." + q)
    if ctx.posture.global_risk_tier == RESTRICTED:
        restr_sources.append("posture_signal")
    is_restricted = bool(restr_sources)

    # --- Missing data (collected; applied per precedence below) ---
    hp = ctx.health
    if not hp.configured:
        missing.append("health_profile")
        reason.append("health_profile_missing")
    else:
        for f in policy.required_profile_fields:
            if _is_missing_profile_field(hp, f):
                missing.append(f)
                reason.append("profile_field_missing:" + f)
        if hp.pain_limitations is None:
            missing.append("pain_injury_limitations")
            reason.append("pain_limitations_not_answered")
        else:
            for lim in hp.pain_limitations:
                if lim.body_area_canonical is None:
                    missing.append("pain_body_area")
                    reason.append("pain_body_area_unnormalizable")
                if lim.status_canonical is None:
                    missing.append("pain_status")
                    reason.append("pain_status_unnormalizable")
        if hp.risk_screen is None:
            missing.append("risk_screen")
            reason.append("risk_screen_missing")
        else:
            for q in policy.all_risk_screen_qualifiers:
                v = risk_screen.get(q)
                if v is None or v == "unknown":
                    missing.append("risk_screen." + q)
                    reason.append("risk_screen_incomplete:" + q)
    if not ctx.checkin.present:
        missing.append("current_day_checkin")
        reason.append("current_checkin_missing")
    if not any(g.active and not g.blocked for g in ctx.posture.goals):
        missing.append("confirmed_posture_goal")
        reason.append("posture_goal_missing_or_blocked")

    has_clarification = bool(missing)

    # --- Caution sources (approved caution tier) ---
    cs = policy.caution_sources
    caution = False
    if (cs.get("checkin_caution") and ctx.checkin.present
            and ctx.checkin.recomputed_risk == CAUTION):
        caution = True
    if cs.get("retained_pain_caution") and any(
            r.recomputed_risk == CAUTION for r in ctx.retained_pain):
        caution = True
    if cs.get("posture_cautious") and ctx.posture.global_risk_tier == CAUTION:
        caution = True
    if cs.get("non_empty_pain_limitations") and hp.pain_limitations:
        caution = True
    if (cs.get("training_experience_beginner")
            and hp.training_experience == "beginner"):
        caution = True

    # --- Precedence ---
    if is_red:
        gate = GateStatus.red_flag
        risk_tier: Optional[SafetyRiskTier] = SafetyRiskTier.red_flag
        blocking = sorted(set(red_sources))
    elif is_restricted:
        gate = GateStatus.restricted
        risk_tier = SafetyRiskTier.restricted
        blocking = sorted(set(restr_sources))
    elif has_clarification:
        gate = GateStatus.clarification_required
        risk_tier = None
        blocking = []
    elif caution:
        gate = GateStatus.eligible_conservative
        risk_tier = SafetyRiskTier.caution
        blocking = []
    else:
        gate = GateStatus.eligible
        risk_tier = SafetyRiskTier.normal
        blocking = []

    return TrainingSafetyDecision(
        gate_status=gate,
        risk_tier=risk_tier,
        reason_codes=reason,
        missing_fields=missing,
        blocking_source_refs=blocking,
        profile_version=hp.profile_version,
        checkin_token=ctx.checkin.token,
        posture_risk_version=ctx.posture.risk_version,
        training_policy_version=ctx.versions.policy_version,
        catalog_version=ctx.versions.catalog_version,
        fingerprint=compose_fingerprint(ctx),
    )
