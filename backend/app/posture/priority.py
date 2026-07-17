"""Deterministic posture priority engine (Phase 1 Task 6, spec §9.2 / §10.6 /
§10.7 / §12.3 / §12.4).

This module owns the *pure* priority computation and the server-generated
control values used by the optimistic-lock confirm flow:

  * ``profile_version``      -- stable SHA-256 over the user's full
    qualification input (sorted profile entries + sorted active safety
    signals), never including ``generated_at`` or DB read order (spec §12.3).
  * ``priority_context_digest`` -- stable SHA-256 over the current knowledge
    association edges (weight>=0.9), each candidate's source count, and its
    ``older_than_30_days`` derived bit, so a ranking-input change invalidates
    an old suggestion even without a profile-version change.
  * ``suggestion_id``        -- deterministic ``uuid5`` over
    ``user_id + profile_version + PRIORITY_RULE_VERSION + RISK_VERSION +
    priority_context_digest`` (spec §10.6 / §12.3).

Read-only contract (spec §10.6 / §17.1): ``build_priority_suggestions``
performs NO writes, persists NO risk recompute, creates NO plan. The
per-issue risk reclassification uses ``safety.compute_profile_risk`` (the
global-first / issue-scoped invariant lives there, exactly one place).

Safety routing priority (spec §12.4): ``safety_blocked`` > ``retest_required``
> ``normal_candidates``. An issue whose recomputed ``risk_tier`` is
``restricted``/``red_flag`` is routed to ``safety_blocked`` even when the
stored certainty was forced to ``provisional`` by an active signal -- it must
never be downgraded to the plain retest path. Restricted entries are a
product-policy gate (spec §12.6); their wording must not pose as a clinical
red flag.

Ranking (spec §12.4, decided): severity base score severe=300 / moderate=200 /
mild=100 (hundreds gap so a sub-bonus can never cross a severity band); strong
knowledge association (weight>=0.9) to another confirmed non-normal candidate
+20; two distinct sources +2; latest source event strictly older than 30 days
-1; final tie-break by ``score DESC, latest_event_at DESC, issue_id ASC``.
Association only expresses possible co-occurrence, never a causal claim.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid5, NAMESPACE_URL

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.posture import risk_rules, safety
from app.posture.knowledge import get_all_issues, get_issue_by_id
from app.posture.models import PostureProfileEntry


# --- Versions / constants ---------------------------------------------------

# Priority weight-formula version. INDEPENDENT from risk_rules.RISK_VERSION:
# bump only when the ranking rule changes, never merge the two.
PRIORITY_RULE_VERSION = "2026-07-17-v1"

MAX_NORMAL_CANDIDATES = 3

DISCLAIMER = "优先级属于建议，关联图谱仅用于排查参考，不作为病因认定。"

# Severity base scores (spec §12.4). The hundreds gap guarantees a sub-bonus
# (+20 / +2 / -1) can never overtake a full severity band.
_SEVERITY_BASE = {"severe": 300, "moderate": 200, "mild": 100}

_ASSOCIATION_BONUS = 20
_DUAL_SOURCE_BONUS = 2
_STALE_PENALTY = -1

_STALE_THRESHOLD = timedelta(days=30)

# Risk tiers that take the safety-blocked path (spec §12.4).
_SAFETY_BLOCKED_TIERS = frozenset({risk_rules.RESTRICTED, risk_rules.RED_FLAG})


# ---------------------------------------------------------------------------
# Time helpers (clock is injectable for deterministic tests)
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_iso(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 string (or pass through a datetime) into aware UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return _to_utc(value)
    if not isinstance(value, str):
        return None
    try:
        return _to_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _iso(value: Any) -> Optional[str]:
    """Normalise a datetime / ISO string to a canonical UTC ISO-8601 string."""
    dt = _parse_iso(value)
    return dt.isoformat() if dt is not None else None


def _older_than_30_days(latest_event_at: Optional[datetime], now: datetime) -> bool:
    """True when the latest source event is STRICTLY older than 30 days.

    Spec §12.4: "最新 source event 距当前时间严格超过 30 天". ``None`` (no
    parseable event time) is treated as not stale so a projection glitch can
    never silently bury a candidate via the staleness penalty.
    """
    if latest_event_at is None:
        return False
    return (now - latest_event_at) > _STALE_THRESHOLD


# ---------------------------------------------------------------------------
# Stable hashing
# ---------------------------------------------------------------------------


def _sha256_obj(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _latest_source(sources: Optional[list]) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(event_id, created_at_iso)`` for the newest source in a stored
    projection ``sources`` array (newest by ``created_at``, tie-break by
    ``event_id`` so the result is independent of DB / JSON order)."""
    if not sources:
        return (None, None)
    best: Optional[dict] = None
    best_dt: Optional[datetime] = None
    for s in sources:
        if not isinstance(s, dict):
            continue
        dt = _parse_iso(s.get("created_at"))
        if best is None or (dt is not None and (best_dt is None or dt > best_dt or (
            dt == best_dt and str(s.get("event_id", "")) > str(best.get("event_id", ""))
        ))):
            best = s
            best_dt = dt
    if best is None:
        return (None, None)
    return (str(best.get("event_id")) if best.get("event_id") is not None else None,
            _iso(best.get("created_at")))


# ---------------------------------------------------------------------------
# Knowledge association edges (weight >= 0.9)
# ---------------------------------------------------------------------------


def _strong_edges() -> Dict[str, List[Tuple[str, float, str]]]:
    """Directed knowledge edges with weight>=0.9 (spec §12.4 "+20").

    Direction matters: an edge ``A -> B`` only contributes to candidate ``A``.
    The relation label is carried for display; it never asserts causation.
    """
    edges: Dict[str, List[Tuple[str, float, str]]] = {}
    for issue in get_all_issues():
        src = issue["id"]
        for rel in issue.get("related_issues", []) or []:
            weight = rel.get("weight", 0) or 0
            if weight >= 0.9:
                edges.setdefault(src, []).append(
                    (rel["id"], float(weight), rel.get("relation", ""))
                )
    return edges


def _edges_canonical(edges: Dict[str, List[Tuple[str, float, str]]]) -> List[dict]:
    flat = []
    for src, lst in edges.items():
        for dst, weight, relation in lst:
            flat.append({"from": src, "to": dst, "weight": weight, "relation": relation})
    flat.sort(key=lambda x: (x["from"], x["to"]))
    return flat


# ---------------------------------------------------------------------------
# Server control values
# ---------------------------------------------------------------------------


def _profile_version(
    entry_states: List[Dict[str, Any]], signals: List[Any]
) -> str:
    """Stable SHA-256 over the full qualification input (spec §12.3).

    Entries are sorted by ``issue_id`` and carry the qualification fields
    (severity, certainty, conflict flag, recomputed risk tier/version, latest
    source event id & time). Signals are sorted by id and carry their type /
    scope / severity / timestamps. All times are UTC ISO-8601. ``generated_at``
    and DB read order are deliberately excluded.
    """
    entries_payload = []
    for es in sorted(entry_states, key=lambda e: e["entry"].issue_id):
        e: PostureProfileEntry = es["entry"]
        cls = es["classification"]
        entries_payload.append({
            "issue_id": e.issue_id,
            "combined_severity": e.combined_severity,
            "certainty": e.certainty,
            "has_conflict": bool(e.has_conflict),
            "risk_tier": cls.risk_tier,
            "risk_version": cls.risk_version,
            "latest_event_id": es["latest_event_id"],
            "latest_event_at": es["latest_event_iso"],
        })

    signals_payload = []
    for s in sorted(signals, key=lambda x: str(x.id)):
        signals_payload.append({
            "id": str(s.id),
            "signal_type": s.signal_type,
            "related_issue_id": s.related_issue_id,
            "body_region": s.body_region,
            "severity_hint": s.severity_hint,
            "reported_at": _iso(s.reported_at),
            "invalidates_until": _iso(s.invalidates_until),
        })

    return _sha256_obj({"entries": entries_payload, "signals": signals_payload})


def _priority_context_digest(
    edges: Dict[str, List[Tuple[str, float, str]]],
    candidate_issue_ids: List[str],
    latest_event_at_by_issue: Dict[str, Optional[datetime]],
    distinct_source_count_by_issue: Dict[str, int],
    now: datetime,
) -> str:
    """SHA-256 over knowledge edges and candidate ranking inputs.

    This makes a knowledge edit, source-count change, or 30-day boundary
    crossing invalidate an old ``suggestion_id`` even when the exact
    ``profile_version`` fields are unchanged (spec §12.3).
    """
    bits = []
    for iid in candidate_issue_ids:
        bits.append({
            "issue_id": iid,
            "distinct_source_count": distinct_source_count_by_issue.get(iid, 0),
            "older_than_30_days": _older_than_30_days(
                latest_event_at_by_issue.get(iid), now
            ),
        })
    bits.sort(key=lambda x: x["issue_id"])
    canonical = {"edges": _edges_canonical(edges), "candidate_staleness": bits}
    return _sha256_obj(canonical)


def _suggestion_id(
    user_id: str,
    profile_version: str,
    context_digest: str,
) -> str:
    """Deterministic suggestion id (spec §10.6: identical inputs -> identical id)."""
    key = (
        f"posture-priority:{user_id}:{profile_version}:"
        f"{PRIORITY_RULE_VERSION}:{risk_rules.RISK_VERSION}:{context_digest}"
    )
    return str(uuid5(NAMESPACE_URL, key))


# ---------------------------------------------------------------------------
# Routing (spec §12.4) and ranking
# ---------------------------------------------------------------------------


_SEVERITY_CN = {"severe": "严重", "moderate": "中度", "mild": "轻度"}


def _route(
    certainty: str,
    combined_severity: Optional[str],
    risk_tier: str,
) -> str:
    """Return the qualification bucket for one profile entry.

    Routing priority: ``safety_blocked`` > ``retest_required`` >
    ``normal_candidates``. Restricted/red_flag wins over a provisional
    certainty so a safety signal can never be hidden in the plain retest path.
    """
    if risk_tier in _SAFETY_BLOCKED_TIERS:
        return "safety_blocked"
    if certainty in ("provisional", "conflict"):
        return "retest_required"
    if certainty == "confirmed" and combined_severity not in (None, "normal"):
        return "normal_candidates"
    # confirmed+normal or anything unexpected -> excluded
    return "excluded"


def _candidate_score(
    severity: str,
    distinct_source_count: int,
    has_strong_association: bool,
    stale: bool,
) -> int:
    score = _SEVERITY_BASE.get(severity, 0)
    if has_strong_association:
        score += _ASSOCIATION_BONUS
    if distinct_source_count >= 2:
        score += _DUAL_SOURCE_BONUS
    if stale:
        score += _STALE_PENALTY
    return score


# ---------------------------------------------------------------------------
# Orchestration: GET /priorities (read-only)
# ---------------------------------------------------------------------------


async def build_priority_suggestions(
    db: AsyncSession, user_id: str, *, now: Optional[datetime] = None
) -> Dict[str, Any]:
    """Compute the deterministic priority suggestions for the current user.

    Read-only: no writes, no commit, no persisted risk recompute, no plan
    generation. Reclassifies every evaluated issue via
    ``safety.compute_profile_risk`` (the safety gate, spec §12.3). Returns
    three buckets plus the server-generated control values used by the
    confirm optimistic lock. With no data, returns three empty buckets and
    stable control values (never ``InsufficientData``, spec §10.6).
    """
    clock = _to_utc(now) if now is not None else _now_utc()

    entries_result = await db.execute(
        select(PostureProfileEntry)
        .where(PostureProfileEntry.user_id == UUID(user_id))
        .order_by(PostureProfileEntry.issue_id.asc())
    )
    entries: List[PostureProfileEntry] = list(entries_result.scalars().all())

    signals = await safety.load_active_signals(db, user_id)
    edges = _strong_edges()

    # Per-issue reclassification + latest-source resolution (single pass).
    entry_states: List[Dict[str, Any]] = []
    for entry in entries:
        issue = get_issue_by_id(entry.issue_id)
        if issue is None:
            # Catalog dropped an evaluated issue: cannot represent -> skip.
            continue
        classification = await safety.compute_profile_risk(db, user_id, entry.issue_id)
        latest_id, latest_iso = _latest_source(entry.sources)
        latest_dt = _parse_iso(latest_iso)
        entry_states.append({
            "entry": entry,
            "issue": issue,
            "classification": classification,
            "latest_event_id": latest_id,
            "latest_event_iso": latest_iso,
            "latest_event_dt": latest_dt,
            "distinct_sources": len(
                {
                    s.get("source")
                    for s in (entry.sources or [])
                    if isinstance(s, dict)
                }
            ),
        })

    # --- Routing into buckets ---
    normal_raw: List[Dict[str, Any]] = []
    retest: List[Dict[str, Any]] = []
    safety_blocked: List[Dict[str, Any]] = []

    for es in entry_states:
        entry: PostureProfileEntry = es["entry"]
        issue = es["issue"]
        cls = es["classification"]
        bucket = _route(entry.certainty, entry.combined_severity, cls.risk_tier)
        if bucket == "safety_blocked":
            safety_blocked.append({
                "issue_id": entry.issue_id,
                "issue_name": issue["name_cn"],
                "risk_tier": cls.risk_tier,
                "reason": _safety_blocked_reason(cls.risk_tier),
                "next_action": _safety_blocked_next_action(cls.risk_tier),
            })
        elif bucket == "retest_required":
            retest.append({
                "issue_id": entry.issue_id,
                "issue_name": issue["name_cn"],
                "certainty": entry.certainty,
                "reason": _retest_reason(entry),
            })
        elif bucket == "normal_candidates":
            normal_raw.append(es)

    # --- Rank normal candidates ---
    candidate_issue_ids = [es["entry"].issue_id for es in normal_raw]
    candidate_id_set = set(candidate_issue_ids)
    latest_dt_by_issue = {es["entry"].issue_id: es["latest_event_dt"] for es in entry_states}
    source_count_by_issue = {
        es["entry"].issue_id: es["distinct_sources"] for es in entry_states
    }

    scored: List[Dict[str, Any]] = []
    for es in normal_raw:
        entry = es["entry"]
        issue = es["issue"]
        severity = entry.combined_severity or ""
        stale = _older_than_30_days(es["latest_event_dt"], clock)
        assoc = _strong_association(entry.issue_id, edges, candidate_id_set)
        score = _candidate_score(severity, es["distinct_sources"], assoc is not None, stale)
        scored.append({
            "entry": entry,
            "issue": issue,
            "severity": severity,
            "score": score,
            "latest_event_dt": es["latest_event_dt"],
            "stale": stale,
            "assoc": assoc,
            "distinct_sources": es["distinct_sources"],
        })

    scored.sort(
        key=lambda c: (
            -c["score"],
            _sort_dt_desc(c["latest_event_dt"]),
            c["entry"].issue_id,
        )
    )
    top = scored[:MAX_NORMAL_CANDIDATES]

    normal_candidates: List[Dict[str, Any]] = []
    for rank, c in enumerate(top, start=1):
        normal_candidates.append({
            "issue_id": c["entry"].issue_id,
            "issue_name": c["issue"]["name_cn"],
            "suggested_rank": rank,
            "severity": c["severity"],
            "reasons": _candidate_reasons(c),
            "relation_type": c["assoc"][2] if c["assoc"] else None,
            "association_weight": c["assoc"][1] if c["assoc"] else None,
        })

    # --- Server control values ---
    profile_version = _profile_version(entry_states, signals)
    context_digest = _priority_context_digest(
        edges,
        candidate_issue_ids,
        latest_dt_by_issue,
        source_count_by_issue,
        clock,
    )
    suggestion_id = _suggestion_id(user_id, profile_version, context_digest)

    return {
        "suggestion_id": suggestion_id,
        "profile_version": profile_version,
        "rule_version": PRIORITY_RULE_VERSION,
        "risk_version": risk_rules.RISK_VERSION,
        "generated_at": clock,
        "normal_candidates": normal_candidates,
        "retest_required": retest,
        "safety_blocked": safety_blocked,
        "disclaimer": DISCLAIMER,
    }


def _sort_dt_desc(dt: Optional[datetime]) -> Any:
    """Sort key for ``latest_event_dt DESC`` with ``None`` last.

    Returns a tuple ``(0, -timestamp)`` so larger timestamps sort first and
    ``None`` (mapped via ``1``) sorts after every real value. Keeping this as
    a pure-Python key avoids relying on DB-side ordering for the tie-break.
    """
    if dt is None:
        return (1, 0)
    return (0, -dt.timestamp())


def _strong_association(
    issue_id: str,
    edges: Dict[str, List[Tuple[str, float, str]]],
    candidate_ids: set,
) -> Optional[Tuple[str, float, str]]:
    """The strongest weight>=0.9 edge from ``issue_id`` to another candidate.

    Returns ``(other_id, weight, relation)`` or ``None``. Direction is honored:
    only edges stored under ``issue_id`` count (spec §12.4 "显式有向边").
    """
    best: Optional[Tuple[str, float, str]] = None
    for other_id, weight, relation in edges.get(issue_id, []):
        if other_id in candidate_ids and other_id != issue_id:
            if best is None or weight > best[1]:
                best = (other_id, weight, relation)
    return best


# ---------------------------------------------------------------------------
# Wording helpers (restricted is NOT a clinical red flag, spec §12.6)
# ---------------------------------------------------------------------------


def _safety_blocked_reason(risk_tier: str) -> str:
    if risk_tier == risk_rules.RED_FLAG:
        return "存在红旗安全信号，停止普通规划，请先寻求专业医学评估"
    # restricted: product-policy gate, explicitly NOT clinical red-flag wording.
    return "存在受限安全信号，当前不进入普通自动建议路径"


def _safety_blocked_next_action(risk_tier: str) -> str:
    if risk_tier == risk_rules.RED_FLAG:
        return "停止体态规划，按红旗指引尽快就医评估"
    return "仅提供健康教育与体态辅助，并建议按需寻求专业评估"


def _retest_reason(entry: PostureProfileEntry) -> str:
    if entry.certainty == "conflict":
        return "来源不一致（conflict），建议重新评估或咨询专业人士"
    return "当前结论不确定（provisional），建议重新评估或咨询专业人士"


def _candidate_reasons(c: Dict[str, Any]) -> List[str]:
    severity = c["severity"]
    reasons: List[str] = []
    cn = _SEVERITY_CN.get(severity)
    if cn:
        reasons.append(f"严重度为 {cn}")
    else:
        reasons.append(f"严重度为 {severity}")
    if c["assoc"] is not None:
        other_id, _weight, relation = c["assoc"]
        issue = get_issue_by_id(other_id)
        other_name = issue["name_cn"] if issue else other_id
        suffix = f"（{relation}）" if relation else ""
        reasons.append(f"与已确认的 {other_name} 强关联{suffix}")
    if c["distinct_sources"] >= 2:
        reasons.append("多来源评估一致")
    if c["stale"]:
        reasons.append("评估已超过 30 天，建议复查")
    return reasons
