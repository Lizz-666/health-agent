"""Safety signal recording + versioned risk classification wiring.

Spec references: §12.2 (closed loop), §12.5 (case matrix), §12.6 (source/license),
§8.5 (idempotency_records).

Isolation note: this module owns ALL Task 6.5 logic. ``service.py`` is intentionally
untouched (a parallel task owns it). The only existing files this task edits are
``router.py`` (one new endpoint) and ``schemas.py`` (request/response models).

Privacy: raw signal payloads are never logged. The idempotency record stores only
a ``request_hash`` and a ``result_ref`` (signal id), never the full payload.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ServiceUnavailable
from app.posture import risk_rules
from app.posture.models import (
    IdempotencyRecord,
    PostureProfileEntry,
    PostureSafetySignal,
)
from app.posture.risk_rules import RiskClassification, RISK_VERSION
from app.posture.schemas import SafetySignalRequest
from app.posture.user_lock import acquire_user_transaction_lock


# Operation name stored in idempotency_records (spec §8.5).
IDEMPOTENCY_OPERATION = "report_safety_signal"

# Idempotency retention window (spec §8.5: default 24h).
IDEMPOTENCY_TTL = timedelta(hours=24)

# invalidates_until window — recheck reminder ONLY. Never used to auto-recover
# a restricted/red_flag tier (spec §12.2).
INVALIDATES_UNTIL_DELTA = timedelta(days=30)


# ---------------------------------------------------------------------------
# Active signal query helper (used by service.py profile recompute)
# ---------------------------------------------------------------------------


async def has_active_signals_for_issue(
    db: AsyncSession, user_id: str, issue_id: str
) -> bool:
    """Return True if any active signal has related_issue_id==issue_id OR
    related_issue_id IS NULL (global signal) OR any global red_flag signal
    exists for this user (spec §12.2).

    Hardening fix #5: global signals (related_issue_id IS NULL) affect ALL
    issues — not just those with a red_flag classification.

    This is used by service.py to force provisional certainty on the affected
    profile entry.
    """
    signals = await _load_active_signals(db, user_id)
    if not signals:
        return False
    for s in signals:
        if s.related_issue_id == issue_id:
            return True
        if s.related_issue_id is None:
            # Global signal affects all issues
            return True
    # Check if any signal triggers red_flag (global scope → affects all issues)
    classification = risk_rules.classify([_signal_to_dict(s) for s in signals])
    if classification.risk_tier == risk_rules.RED_FLAG:
        return True
    return False


# ---------------------------------------------------------------------------
# Recovery basis guard (spec §12.2 恢复规则)
# ---------------------------------------------------------------------------

RECOVERY_BASIS_RECLASSIFICATION = "reclassification"

# These recovery reasons are explicitly FORBIDDEN from resolving a signal.
_FORBIDDEN_RECOVERY_REASONS = frozenset(
    {"time_elapsed", "user_confirmed", "free_text_claim", "sought_medical_care_verbal"}
)


def is_structured_recovery_basis(basis: str) -> bool:
    """Only a structured reclassification may resolve restricted/red_flag signals."""
    return basis == RECOVERY_BASIS_RECLASSIFICATION


def assert_recovery_is_structured(basis: str) -> None:
    if basis in _FORBIDDEN_RECOVERY_REASONS:
        raise AppException(
            400,
            "受限/红旗信号只能通过新的结构化信息重新分类解除，不接受时间经过、用户确认或声称已就医",
            "recovery_requires_reclassification",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_aware_utc(dt: datetime) -> datetime:
    """Normalize a datetime to aware UTC for safe comparison.

    SQLite returns *naive* datetimes even for ``DateTime(timezone=True)``
    columns (it stores them without tz info), while PostgreSQL returns aware
    ones. Comparing a naive DB value against an aware ``now`` raises
    ``TypeError`` under SQLite, so expiry checks are normalized here to stay
    correct on both backends.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _hash_request(signal: dict) -> str:
    """Stable sha256 over the canonical signal identity (no raw payload logging).

    P1-5: ``reported_at`` IS now part of the canonical identity. ``reported_at``
    is a UTC-normalised ISO-8601 string when the client supplied it, or ``null``
    when the server generated it (so two server-generated replays with the same
    fields still deduplicate). ``idempotency_key`` stays excluded (it is the
    lookup key, not part of the request identity). Including ``reported_at``
    means the same idempotency key reused with a different ``reported_at`` now
    yields a different hash → ``idempotency_key_conflict``.
    """
    identity = {
        "signal_type": signal.get("signal_type"),
        "body_region": signal.get("body_region"),
        "related_issue_id": signal.get("related_issue_id"),
        "severity_hint": signal.get("severity_hint"),
        "reported_at": signal.get("reported_at"),
    }
    payload = json.dumps(identity, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _signal_to_dict(sig: PostureSafetySignal) -> dict:
    return {
        "signal_type": sig.signal_type,
        "severity_hint": sig.severity_hint,
        "body_region": sig.body_region,
    }


async def _load_active_signals(db: AsyncSession, user_id: str) -> List[PostureSafetySignal]:
    result = await db.execute(
        select(PostureSafetySignal).where(
            PostureSafetySignal.user_id == UUID(user_id),
            PostureSafetySignal.lifecycle == "active",
        )
    )
    return list(result.scalars().all())


async def load_active_signals(db: AsyncSession, user_id: str) -> List[PostureSafetySignal]:
    """Public accessor for the user's current active signals (spec §12.2)."""
    return await _load_active_signals(db, user_id)


async def _load_active_signals_for_scope(
    db: AsyncSession, user_id: str, issue_id: str
) -> List[PostureSafetySignal]:
    """Load active signals scoped to a specific issue (hardening fix #5).

    Returns signals with ``related_issue_id == issue_id`` OR
    ``related_issue_id IS NULL`` (global signals). This prevents cross-issue
    escalation by write-order.
    """
    from sqlalchemy import or_
    result = await db.execute(
        select(PostureSafetySignal).where(
            PostureSafetySignal.user_id == UUID(user_id),
            PostureSafetySignal.lifecycle == "active",
            or_(
                PostureSafetySignal.related_issue_id == issue_id,
                PostureSafetySignal.related_issue_id.is_(None),
            ),
        )
    )
    return list(result.scalars().all())


def compute_signals_digest(signals: List[PostureSafetySignal]) -> str:
    """Stable sha256 summary of an active signal set (no raw payload logging).

    Used as the reclassification attestation: a caller must present the digest
    of the *current* active set (excluding the target signal) so a resolution
    can never be driven by a stale view of the user's signals.
    """
    items = [
        {
            "signal_type": s.signal_type,
            "severity_hint": s.severity_hint,
            "body_region": s.body_region,
            "lifecycle": s.lifecycle,
            "related_issue_id": s.related_issue_id,
        }
        for s in signals
    ]
    payload = json.dumps(items, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Classification + profile downgrade
# ---------------------------------------------------------------------------


async def classify_user_risk(
    db: AsyncSession, user_id: str, issue_id: Optional[str] = None
) -> RiskClassification:
    """Recompute the user's risk tier from their CURRENT active structured signals.

    Pure w.r.t. assessment severity: a severe posture assessment with no
    structured signal stays ``normal`` (anti-inference rule, spec §12.2).

    Hardening fix #5 (explicit risk scope):
    - When ``issue_id`` is provided: only load signals with
      ``related_issue_id == issue_id`` OR ``related_issue_id IS NULL`` (global).
      This prevents cross-issue escalation by write-order.
    - When ``issue_id`` is None: load ALL active signals (global evaluation).
    """
    if issue_id is not None:
        signals = await _load_active_signals_for_scope(db, user_id, issue_id)
    else:
        signals = await _load_active_signals(db, user_id)
    return risk_rules.classify([_signal_to_dict(s) for s in signals])


async def compute_profile_risk(
    db: AsyncSession, user_id: str, issue_id: Optional[str]
) -> RiskClassification:
    """Unified, reusable profile-risk recompute (P1-4).

    Implements the global-first / issue-scoped invariant (spec §12.2):

      1. Classify over ALL the user's active signals (global).
      2. If the global classification is ``red_flag`` → return it for ANY
         ``issue_id`` (short-circuit). A red_flag anywhere downgrades EVERY
         profile, regardless of ``related_issue_id`` — so an issue-scoped
         re-project can never overwrite a red_flag set by another issue's signal.
      3. Otherwise (no global red_flag): if ``issue_id`` is None, return the
         global classification; if ``issue_id`` is set, classify over only the
         signals scoped to that issue (``related_issue_id == issue_id`` OR
         global ``related_issue_id IS NULL``). Different issues' cautious /
         restricted signals therefore never cross-escalate.

    Both ``service._resolve_risk_overlay`` (assessment re-project) and the
    scoped-purge projection rebuild import and call this same function, so the
    invariant lives in exactly one place. Phase 1 ships no auto ``red_flag``
    rule, so step 2 is vacuous today; the branch is retained so a future
    clinical-source red_flag rule is honoured automatically.
    """
    global_signals = await _load_active_signals(db, user_id)
    global_classification = risk_rules.classify(
        [_signal_to_dict(s) for s in global_signals]
    )
    if global_classification.risk_tier == risk_rules.RED_FLAG:
        return global_classification
    if issue_id is None:
        return global_classification
    scoped_signals = await _load_active_signals_for_scope(db, user_id, issue_id)
    return risk_rules.classify([_signal_to_dict(s) for s in scoped_signals])


async def apply_classification_to_profile(
    db: AsyncSession,
    user_id: str,
    issue_id: Optional[str],
    classification: RiskClassification,
    *,
    scope: Optional[str] = None,
) -> int:
    """Apply a classification to the relevant profile entry/entries.

    Risk scope (spec §12.2): a ``red_flag`` tier downgrades the user's GLOBAL
    risk (every profile entry they own); restricted/cautious/normal only affect
    the ``issue_id`` entry. ``scope`` overrides the inferred behaviour
    (``"global"`` | ``"issue"``); when omitted it is derived from the tier.
    Returns the number of rows updated.
    """
    if scope is None:
        scope = "global" if classification.risk_tier == risk_rules.RED_FLAG else "issue"

    if scope == "global":
        result = await db.execute(
            select(PostureProfileEntry).where(
                PostureProfileEntry.user_id == UUID(user_id),
            )
        )
        entries = list(result.scalars().all())
    else:
        if not issue_id:
            return 0
        result = await db.execute(
            select(PostureProfileEntry).where(
                PostureProfileEntry.user_id == UUID(user_id),
                PostureProfileEntry.issue_id == issue_id,
            )
        )
        entry = result.scalar_one_or_none()
        entries = [entry] if entry is not None else []

    for entry in entries:
        entry.certainty = "provisional"
        entry.combined_severity = None
        entry.risk_tier = classification.risk_tier
        entry.risk_version = classification.risk_version
    return len(entries)


# ---------------------------------------------------------------------------
# Signal recording (main write path)
# ---------------------------------------------------------------------------


async def _rebuild_result(
    db: AsyncSession, user_id: str, signal_id: str, status: str
) -> dict:
    """Rebuild a response from a stored signal id (idempotent replay).

    The replay reclassifies over the user's CURRENT active signal set so a
    later signal that escalates the tier is reflected — it never returns a
    stale single-signal snapshot (spec §12.2). If the referenced signal was
    purged/deleted the replay surfaces HTTP 410 (Gone) rather than 400.
    """
    sig = await db.get(PostureSafetySignal, UUID(signal_id))
    if sig is None:
        raise AppException(410, "幂等记录指向的信号已被清除", "idempotency_result_gone")
    classification = await compute_profile_risk(db, user_id, sig.related_issue_id)
    return _build_response(sig, classification, status=status)


def _build_response(
    sig: PostureSafetySignal,
    classification: RiskClassification,
    status: str,
) -> dict:
    return {
        "signal_id": str(sig.id),
        "status": status,
        "lifecycle": sig.lifecycle,
        "risk_tier": classification.risk_tier,
        "risk_version": classification.risk_version,
        "invalidates_until": sig.invalidates_until.isoformat(),
        "classification": {
            "risk_tier": classification.risk_tier,
            "risk_version": classification.risk_version,
            "rule_id": classification.rule_id,
            "reason": classification.reason,
            "sources": [vars(s) for s in classification.sources],
        },
    }


async def record_safety_signal(
    db: AsyncSession,
    user_id: str,
    signal: dict,
    idempotency_key: str,
) -> dict:
    """Record a structured safety signal with idempotency + risk reclassification.

    ``signal`` keys: signal_type, body_region, related_issue_id, severity_hint,
    reported_at (optional).

    P1-5 strict input validation: the SAME ``SafetySignalRequest`` model the HTTP
    router uses is applied here (before any lock or write), so direct service /
    Tool callers get identical validation. Validation failure → 400 and NO
    signal / idempotency record / profile mutation. ``reported_at`` is part of
    the request hash (UTC-normalised, or ``null`` when server-generated); an
    invalid ``reported_at`` is rejected (400) rather than silently replaced.

    P1-4: classification uses ``compute_profile_risk`` (global-first, then
    issue-scoped) so a global red_flag is never overwritten by an issue-scoped
    write.

    Error contract: ``AppException`` propagates as-is (after rollback). Any other
    unexpected DB / classification error rolls back and surfaces 503 with a
    Chinese message (does not rely on the app.main catch-all).
    """
    # --- P1-5: STRICT service-layer validation (BEFORE lock, BEFORE any write) ---
    # extra="forbid" rejects unknown fields; enums reject invalid
    # signal_type / body_region / severity_hint; idempotency_key is checked
    # (non-blank, <=64); reported_at plausibility is enforced (not >5s future,
    # not >365d past). Invalid reported_at → 400 (NO silent fallback to now).
    validation_payload = dict(signal) if isinstance(signal, dict) else {}
    validation_payload["idempotency_key"] = idempotency_key
    try:
        req = SafetySignalRequest.model_validate(validation_payload)
    except ValidationError:
        raise AppException(400, "安全信号请求参数错误", "invalid_signal_input")

    from app.posture.knowledge import get_issue_by_id
    if req.related_issue_id and get_issue_by_id(req.related_issue_id) is None:
        raise AppException(400, "关联的体态问题不存在", "issue_not_found")

    # Normalise the validated fields into plain DB-ready values.
    sig_type = req.signal_type.value
    body_region = req.body_region.value if req.body_region else None
    related_issue_id = req.related_issue_id
    severity_hint = req.severity_hint.value if req.severity_hint else None

    # reported_at: client-supplied → UTC normalise + include in hash; missing →
    # server-generate now, hash uses null (stable across replays).
    if req.reported_at is not None:
        reported_at = req.reported_at
        if reported_at.tzinfo is None:
            reported_at = reported_at.replace(tzinfo=timezone.utc)
        else:
            reported_at = reported_at.astimezone(timezone.utc)
        hash_reported_at = reported_at.isoformat()
    else:
        reported_at = _now()
        hash_reported_at = None

    request_hash = _hash_request(
        {
            "signal_type": sig_type,
            "body_region": body_region,
            "related_issue_id": related_issue_id,
            "severity_hint": severity_hint,
            "reported_at": hash_reported_at,
        }
    )

    # --- Write path: lock, freeze check, idempotency, signal, classify, commit ---
    # AppException propagates as-is (after rollback); any unexpected error
    # rolls back and surfaces 503 (no reliance on app.main catch-all).
    try:
        await acquire_user_transaction_lock(db, user_id)

        from app.posture.purge import is_user_write_frozen
        if await is_user_write_frozen(db, user_id):
            raise AppException(
                409,
                "用户数据正在清除中，写入已冻结，请稍后重试",
                "write_frozen_during_purge",
            )

        now = _now()

        # --- Idempotency resolution (spec §8.5) ---
        existing = await db.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.user_id == UUID(user_id),
                IdempotencyRecord.operation == IDEMPOTENCY_OPERATION,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        record = existing.scalar_one_or_none()
        if record is not None:
            if _to_aware_utc(record.expires_at) > now:
                if record.request_hash == request_hash:
                    # Same key + same request → replay, reclassifying over the
                    # user's *current* active signal set (updated classification).
                    response = await _rebuild_result(
                        db, str(record.user_id), record.result_ref, status="deduplicated"
                    )
                    # The user transaction lock is xact-scoped. A successful
                    # replay performs no writes, so end the read transaction
                    # explicitly instead of holding the lock until session close.
                    await db.rollback()
                    return response
                # Same key + DIFFERENT request (incl. different reported_at) → reject.
                raise AppException(
                    400,
                    "idempotency_key 已用于不同的请求",
                    "idempotency_key_conflict",
                )
            # Expired record no longer blocks; remove it and proceed.
            await db.delete(record)
            await db.flush()

        # --- Write the signal ---
        sig = PostureSafetySignal(
            user_id=UUID(user_id),
            signal_type=sig_type,
            body_region=body_region,
            related_issue_id=related_issue_id,
            severity_hint=severity_hint,
            reported_at=reported_at,
            lifecycle="active",
            invalidates_until=reported_at + INVALIDATES_UNTIL_DELTA,
        )
        db.add(sig)
        await db.flush()  # populate sig.id; make it visible to the classification query

        # --- Reclassify over active signals (incl. the new one) via the unified
        # global-first / issue-scoped function (P1-4). ---
        classification = await compute_profile_risk(db, user_id, sig.related_issue_id)

        # Risk scope (spec §12.2):
        # - red_flag → ALWAYS global (all profiles)
        # - No related_issue_id (any tier above normal) → global
        # - With related_issue_id + cautious/restricted → issue-scoped
        if classification.risk_tier == risk_rules.RED_FLAG or not sig.related_issue_id:
            scope = "global"
        else:
            scope = "issue"
        await apply_classification_to_profile(
            db, user_id, sig.related_issue_id, classification, scope=scope
        )

        # --- Persist idempotency record (result_ref = signal id, no raw payload) ---
        db.add(
            IdempotencyRecord(
                user_id=UUID(user_id),
                operation=IDEMPOTENCY_OPERATION,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                status="completed",
                result_ref=str(sig.id),
                expires_at=now + IDEMPOTENCY_TTL,
            )
        )

        await db.commit()
        await db.refresh(sig)
        return _build_response(sig, classification, status="recorded")
    except AppException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise ServiceUnavailable("安全信号记录失败，请稍后重试")


# ---------------------------------------------------------------------------
# Recovery — ONLY structured reclassification may resolve restricted/red_flag
# ---------------------------------------------------------------------------


async def attempt_recovery_by_time_elapsed(
    db: AsyncSession, user_id: str, elapsed_days: int
) -> bool:
    """Guard: time passing NEVER recovers a restricted/red_flag signal.

    ``time_elapsed`` is one of the explicitly forbidden recovery modes, so this
    returns ``False`` and mutates nothing. Spec §12.2: 不得仅因时间经过自动恢复
    （删除任何"30 天后自然恢复"语义）.
    """
    return False


async def attempt_recovery_by_free_text(
    db: AsyncSession, user_id: str, claim: str
) -> bool:
    """Guard: free-text claims such as 已就医 NEVER recover a red_flag signal.

    ``free_text_claim`` is one of the explicitly forbidden recovery modes, so
    this returns ``False`` and mutates nothing. Spec §12.2: 用户声称已就医
    （口头声称不是结构化信息）.
    """
    return False


async def reclassify_and_resolve(
    db: AsyncSession,
    user_id: str,
    signal_id: str,
    *,
    profile_snapshot: dict,
    active_signals_digest: str,
    rule_version: str,
) -> dict:
    """The ONLY supported recovery path (spec §12.2).

    Requires NEW structured attestation from the caller — it must NOT resolve a
    signal merely by excluding the target. The caller supplies:

      * ``profile_snapshot`` — the updated profile snapshot; must carry a
        non-empty ``profile_version`` for the affected issue.
      * ``active_signals_digest`` — digest of the *current* active signal set
        EXCLUDING the target signal. The function recomputes the actual digest
        and rejects a stale view.
      * ``rule_version`` — must equal the current ``RISK_VERSION``.

    If the recomputed tier (over the remaining structured signals) is STRICTLY
    lower than the tier implied by the full active set, the target signal is
    marked ``resolved`` and ``resolution_source`` records profile_version +
    active_signals_digest + rule_version.
    """
    if (
        profile_snapshot is None
        or active_signals_digest is None
        or not rule_version
    ):
        raise AppException(
            400,
            "重新分类需提供档案快照、信号摘要和 rule_version（不接受仅排除目标信号）",
            "reclassify_missing_structured_input",
        )

    profile_version = (
        profile_snapshot.get("profile_version")
        if isinstance(profile_snapshot, dict)
        else None
    )
    if not (profile_version and str(profile_version).strip()):
        raise AppException(
            400,
            "档案快照缺少 profile_version",
            "reclassify_missing_structured_input",
        )

    if rule_version != RISK_VERSION:
        raise AppException(
            409,
            "rule_version 已过期，请使用最新版本重新分类",
            "stale_rule_version",
        )

    sig = await db.get(PostureSafetySignal, UUID(signal_id))
    if sig is None or sig.user_id != UUID(user_id):
        raise AppException(400, "安全信号不存在", "signal_not_found")
    if sig.lifecycle == "resolved":
        return {"resolved": True, "risk_tier": None, "already_resolved": True}

    all_active = await _load_active_signals(db, user_id)
    current = risk_rules.classify([_signal_to_dict(s) for s in all_active])

    remaining = [s for s in all_active if s.id != sig.id]
    actual_digest = compute_signals_digest(remaining)
    if actual_digest != active_signals_digest:
        # The caller's view of the active set is stale — refuse to resolve.
        raise AppException(
            409,
            "安全信号集摘要不匹配，请基于最新信号重新分类",
            "stale_signals_digest",
        )

    new_classification = risk_rules.classify(
        [_signal_to_dict(s) for s in remaining]
    )

    if not risk_rules.is_lower_risk(new_classification.risk_tier, than=current.risk_tier):
        # Remaining structured information still constitutes the higher risk.
        return {
            "resolved": False,
            "risk_tier": current.risk_tier,
            "reason": "剩余结构化信号仍构成同等或更高风险，需新的低风险结构化信息重新分类",
        }

    # DISABLED: success path requires persistent follow-up structured event +
    # server-generated profile_version (not arbitrary strings). Re-enable when
    # follow-up event service exists.
    raise AppException(
        501,
        "reclassify_and_resolve 成功路径暂未启用：需要可持久化的 follow-up 结构化事件和服务端生成的 profile_version",
        "reclassify_not_implemented",
    )
