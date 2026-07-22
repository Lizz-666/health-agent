from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import hashlib
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, update
from app.posture.models import (
    PostureAssessment,
    PostureAssessmentEvent,
    PostureProfileEntry,
    PostureUserGoal,
    IdempotencyRecord,
)
from app.posture.knowledge import get_issue_by_id, get_all_issues
from app.posture.user_lock import acquire_user_transaction_lock
from app.core.exceptions import AppException


# --- Phase 1 projection constants (spec §6.3 / §6.4 / §8.5) -----------------
# These mirror the migration 0002 backfill values exactly.
RISK_TIER_NORMAL = "normal"
RISK_VERSION = "phase1-initial-v1"

SOURCE_SELF_TEST = "self_test"
SOURCE_AI_PHOTO = "ai_photo"

LIFECYCLE_ACTIVE = "active"
LIFECYCLE_SUPERSEDED = "superseded"

CERTAINTY_CONFIRMED = "confirmed"
CERTAINTY_PROVISIONAL = "provisional"
CERTAINTY_CONFLICT = "conflict"

# Hardening fix #9: valid enum values for service-layer validation
_VALID_BODY_REGIONS = frozenset({
    "head_neck", "cervical", "upper_back", "thoracic", "lower_back",
    "shoulder_thorax", "pelvis_spine", "lower_limb", "compound",
})
_VALID_SEVERITY_HINTS = frozenset({"mild", "moderate", "severe"})
_VALID_ANSWERS = frozenset({"positive", "negative", "uncertain"})


def get_all_issues_list(category: Optional[str] = None) -> List[dict]:
    return get_all_issues(category)


def get_related_issues(issue_id: str) -> List[dict]:
    issue = get_issue_by_id(issue_id)
    if not issue:
        return []
    result = []
    for rel in issue.get("related_issues", []):
        related = get_issue_by_id(rel["id"])
        if related and rel.get("weight", 0) >= 0.6:
            result.append(
                {
                    "id": rel["id"],
                    "name_cn": related["name_cn"],
                    "weight": rel["weight"],
                    "relation": rel["relation"],
                }
            )
    result.sort(key=lambda x: x["weight"], reverse=True)
    return result[:3]


def _evaluate_result(issue: dict, answer: str) -> Tuple[str, str]:
    if answer == "negative":
        return "normal", "自测结果为阴性，你该方面的体态目前正常。保持良好习惯即可。"
    elif answer == "positive":
        return (
            "moderate",
            "自测结果为阳性，建议进行以下纠正训练。如伴红旗征请及时就医。",
        )
    else:
        return "uncertain", "自测结果不确定。建议使用 AI 拍照分析进行更精确的判断。"


# ---------------------------------------------------------------------------
# Profile projection (spec §6.4 / §8.5 / §11.1) -- mirrors migration 0002
# backfill CTE. Pure function: identical output for identical input.
# ---------------------------------------------------------------------------


def project_profile(latest_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Project the latest-per-source active events for one (user, issue) into a
    profile projection.

    Input: list of dicts, each carrying ``source`` / ``severity`` / ``id`` /
    ``created_at`` for the LATEST active event of a given source (one dict per
    source -- same-source older history must NOT participate, spec §8.5).

    The combination is NULL-aware and mirrors the migration 0002 backfill CTE
    (``posture_profile_entries`` INSERT ... SELECT) branch-for-branch:

      * single source, severity non-null     -> confirmed,  combined = severity
      * single source, severity null         -> provisional, combined = null
      * multi source, ANY severity null      -> provisional, combined = null
      * multi source, all non-null & equal   -> confirmed,  combined = common
      * multi source, non-null & differ      -> conflict,   combined = null,
                                                  has_conflict = True

    There is intentionally NO "差1级取更严重" rule: any non-null disagreement
    (even by one level) is an explicit conflict (spec §6.4).
    """
    src_cnt = len(latest_events)
    null_cnt = sum(1 for e in latest_events if e["severity"] is None)
    non_null = [e["severity"] for e in latest_events if e["severity"] is not None]
    distinct_non_null = len(set(non_null))

    if src_cnt == 1 and null_cnt == 0:
        # single source, non-null
        combined_severity: Optional[str] = latest_events[0]["severity"]
        certainty = CERTAINTY_CONFIRMED
    elif src_cnt > 1 and null_cnt == 0 and distinct_non_null == 1:
        # multi source, all non-null and equal
        combined_severity = non_null[0]
        certainty = CERTAINTY_CONFIRMED
    elif src_cnt > 1 and null_cnt == 0 and distinct_non_null >= 2:
        # multi source, non-null disagreement -> conflict
        combined_severity = None
        certainty = CERTAINTY_CONFLICT
    else:
        # single-null / multi-any-null -> provisional
        combined_severity = None
        certainty = CERTAINTY_PROVISIONAL

    has_conflict = src_cnt > 1 and null_cnt == 0 and distinct_non_null >= 2

    # sources JSON: only the latest-per-source rows, newest first (mirrors
    # jsonb_agg(...) ORDER BY created_at DESC, id DESC in the backfill).
    ordered = sorted(
        latest_events,
        key=lambda e: (e["created_at"], str(e["id"])),
        reverse=True,
    )
    sources = [
        {
            "source": e["source"],
            "event_id": str(e["id"]),
            "severity": e["severity"],
            "created_at": (
                e["created_at"].isoformat()
                if isinstance(e["created_at"], datetime)
                else e["created_at"]
            ),
        }
        for e in ordered
    ]

    latest_self_test_event_id = next(
        (e["id"] for e in latest_events if e["source"] == SOURCE_SELF_TEST), None
    )
    latest_photo_event_id = next(
        (e["id"] for e in latest_events if e["source"] == SOURCE_AI_PHOTO), None
    )

    return {
        "combined_severity": combined_severity,
        "certainty": certainty,
        "has_conflict": has_conflict,
        "sources": sources,
        "latest_self_test_event_id": latest_self_test_event_id,
        "latest_photo_event_id": latest_photo_event_id,
    }


async def _fetch_latest_active_per_source(
    db: AsyncSession, user_id: str, issue_id: str
) -> List[Dict[str, Any]]:
    """Return the LATEST active (non-superseded) event PER SOURCE for one
    (user, issue).

    Mirrors the migration 0002 window CTE::

        ROW_NUMBER() OVER (
            PARTITION BY user_id, issue_id, source
            ORDER BY created_at DESC, id DESC
        ) AS rn   -- then rn = 1

    Ordering by ``created_at DESC, id DESC`` and keeping the first row seen per
    source yields exactly one row per source.
    """
    stmt = (
        select(PostureAssessmentEvent)
        .where(
            PostureAssessmentEvent.user_id == UUID(user_id),
            PostureAssessmentEvent.issue_id == issue_id,
            PostureAssessmentEvent.lifecycle == LIFECYCLE_ACTIVE,
        )
        .order_by(
            PostureAssessmentEvent.created_at.desc(),
            PostureAssessmentEvent.id.desc(),
        )
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    latest: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if r.source not in latest:
            latest[r.source] = {
                "source": r.source,
                "severity": r.severity,
                "id": r.id,
                "created_at": r.created_at,
            }
    return list(latest.values())


async def _acquire_user_lock(db: AsyncSession, user_id: str) -> None:
    """Acquire a per-user advisory lock via the shared user_lock module.

    Delegates to ``acquire_user_transaction_lock`` (hardening fix #1).
    """
    await acquire_user_transaction_lock(db, user_id)


async def _resolve_risk_overlay(
    db: AsyncSession, user_id: str, issue_id: str, existing: Optional[PostureProfileEntry]
) -> Tuple[str, str]:
    """Resolve ``(risk_tier, risk_version)`` for a profile recompute.

    Connects the projection (severity/certainty) with the versioned risk
    classification (Task 6.5): if the user currently has ANY active safety
    signal, the profile's risk tier is re-derived via ``compute_profile_risk``
    (P1-4): a GLOBAL red_flag short-circuits to red_flag for EVERY issue (so an
    issue-scoped re-project can never overwrite it), otherwise the
    issue-scoped classification (signals with related_issue_id==issue_id OR
    global signals) is used. When there are no active signals the existing tier
    is preserved on UPDATE (the safety system may have written a
    cautious/restricted tier that must survive a re-project, spec §12.2 /
    Task 2 FIX 5), and the normal baseline is seeded on CREATE.

    Hardening fix #4: NO defensive except/pass — if classification or signal
    query fails, the exception propagates and the entire transaction rolls back.

    Hardening fix #5 / P1-4: the unified global-first / issue-scoped function
    prevents cross-issue escalation while preserving a global red_flag.
    """
    from app.posture import safety

    signals = await safety.load_active_signals(db, user_id)
    if signals:
        # P1-4: use the unified global-first / issue-scoped recompute so a
        # global red_flag is never overwritten by an issue-scoped re-project.
        classification = await safety.compute_profile_risk(db, user_id, issue_id)
        return classification.risk_tier, classification.risk_version

    # No active signals: preserve on UPDATE, seed the normal baseline on CREATE.
    if existing is not None:
        return existing.risk_tier, existing.risk_version
    return RISK_TIER_NORMAL, RISK_VERSION


async def _recompute_and_upsert_profile(
    db: AsyncSession, user_id: str, issue_id: str
) -> None:
    """Recompute the profile projection for (user, issue) from the latest
    active events per source and upsert ``posture_profile_entries``.

    Seeds ``risk_tier='normal'`` and ``risk_version='phase1-initial-v1'`` on
    CREATE only (consistent with the migration 0002 backfill). If no active
    events remain, any stale profile row is removed.
    """
    latest = await _fetch_latest_active_per_source(db, user_id, issue_id)

    existing = await db.scalar(
        select(PostureProfileEntry).where(
            PostureProfileEntry.user_id == UUID(user_id),
            PostureProfileEntry.issue_id == issue_id,
        )
    )

    if not latest:
        # Defensive: no active source -> drop a stale projection row.
        if existing is not None:
            await db.delete(existing)
        return None

    projection = project_profile(latest)
    fields = {
        "combined_severity": projection["combined_severity"],
        "certainty": projection["certainty"],
        "sources": projection["sources"],
        "has_conflict": projection["has_conflict"],
        "latest_self_test_event_id": projection["latest_self_test_event_id"],
        "latest_photo_event_id": projection["latest_photo_event_id"],
        "updated_at": datetime.now(timezone.utc),
    }

    # risk_tier/risk_version are managed by the safety overlay (Task 6.5);
    # projection must not reset them once set. They are re-derived from the
    # user's current active safety signals when any exist (risk overlay, spec
    # §12.2), preserved on UPDATE when no signals are present, and seeded with
    # the normal baseline ONLY on CREATE.
    # Hardening fix #5: issue-scoped classification.
    risk_tier, risk_version = await _resolve_risk_overlay(db, user_id, issue_id, existing)

    # Active safety signals force certainty=provisional + combined_severity=null
    # for this issue (spec §12.2 / review fix #3).
    # Hardening fix #4: NO defensive except/pass — propagate on failure.
    from app.posture.safety import has_active_signals_for_issue
    if await has_active_signals_for_issue(db, user_id, issue_id):
        fields["certainty"] = CERTAINTY_PROVISIONAL
        fields["combined_severity"] = None

    if existing is None:
        db.add(
            PostureProfileEntry(
                id=uuid4(),
                user_id=UUID(user_id),
                issue_id=issue_id,
                risk_tier=risk_tier,
                risk_version=risk_version,
                **fields,
            )
        )
    else:
        for key, value in fields.items():
            setattr(existing, key, value)
        existing.risk_tier = risk_tier
        existing.risk_version = risk_version
    await db.flush()
    return None


async def _supersede_active_events(
    db: AsyncSession, user_id: str, issue_id: str, source: str
) -> None:
    """Mark prior SAME-SOURCE active events as ``superseded``.

    Only the same source is superseded (a new self-test does not retire an
    active photo assessment, and vice versa). Spec §6.2 / §8.5.
    """
    await db.execute(
        update(PostureAssessmentEvent)
        .where(
            PostureAssessmentEvent.user_id == UUID(user_id),
            PostureAssessmentEvent.issue_id == issue_id,
            PostureAssessmentEvent.source == source,
            PostureAssessmentEvent.lifecycle == LIFECYCLE_ACTIVE,
        )
        .values(lifecycle=LIFECYCLE_SUPERSEDED)
    )


async def _assert_not_frozen(db: AsyncSession, user_id: str) -> None:
    """Reject the write if a non-terminal purge is in flight for this user.

    A purge_operation in a non-terminal status freezes health-data writes (spec
    §6.7). Hardening fix #4: NO defensive import wrapping — if the purge module
    fails to load or the freeze query fails, the exception propagates (503).
    """
    from app.posture.purge import is_user_write_frozen
    if await is_user_write_frozen(db, user_id):
        raise AppException(
            409,
            "用户数据正在清除中，写入已冻结，请稍后重试",
            "write_frozen_during_purge",
        )


async def save_self_assessment(
    db: AsyncSession,
    user_id: str,
    issue_id: str,
    answer: str,
    test_index: int,
) -> Optional[dict]:
    """Persist a self-test assessment event and recompute the profile entry
    in a single transaction.

    Phase C: only ``source`` and ``severity`` are written (``method``/``result``
    columns have been dropped). For an ``uncertain`` answer ``severity`` is set
    to ``None`` (severity is permanently nullable). Prior same-source active
    events are superseded; the projection honours only the latest event per
    source.
    """
    # Hardening fix #9: service-layer validation (defense in depth)
    if answer not in _VALID_ANSWERS:
        raise AppException(400, "无效的 answer 值", "invalid_answer")

    issue = get_issue_by_id(issue_id)
    if not issue:
        return None

    result_level, suggestion = _evaluate_result(issue, answer)
    severity: Optional[str] = None if result_level == "uncertain" else result_level

    # Stamp the knowledge-base content_version of the chosen self_test onto the
    # event for provenance (extended entries carry one; legacy entries -> None).
    content_version: Optional[str] = None
    self_tests = issue.get("self_tests") or []
    if 0 <= test_index < len(self_tests):
        content_version = self_tests[test_index].get("content_version")

    try:
        await _acquire_user_lock(db, user_id)
        await _assert_not_frozen(db, user_id)
        await _supersede_active_events(db, user_id, issue_id, SOURCE_SELF_TEST)
        assessment = PostureAssessment(
            user_id=UUID(user_id),
            issue_id=issue_id,
            source=SOURCE_SELF_TEST,
            severity=severity,
            lifecycle=LIFECYCLE_ACTIVE,
            content_version=content_version,
            self_test_answers={"test_index": test_index, "answer": answer},
        )
        db.add(assessment)
        await db.flush()
        await _recompute_and_upsert_profile(db, user_id, issue_id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await db.refresh(assessment)
    return {
        "id": str(assessment.id),
        "issue_id": assessment.issue_id,
        "result": result_level,
        "suggestion": suggestion,
    }


def _map_ai_level_to_db(ai_level: str) -> str:
    """Map AI analysis level to a DB/Flutter-compatible result.

    Flutter currently recognises normal / moderate / severe / uncertain.
    AI ``mild`` is deterministically promoted to ``moderate`` so that
    Flutter does not encounter an unknown state.  The original AI level
    is preserved in the ``ai_response`` JSONB column.
    """
    if ai_level == "mild":
        return "moderate"
    return ai_level


def _photo_suggestion(db_result: str, ai_result: dict) -> str:
    """Pick the user-facing suggestion text for a photo assessment.

    Prefers the model's own suggestion when present; otherwise falls back to a
    deterministic message keyed off the mapped DB level. Shared by the legacy
    write path (``save_photo_assessment``), the new idempotent orchestration
    (``analyze_and_save_photo``) and the replay path so all three agree.
    """
    if db_result == "normal":
        return ai_result.get("suggestion", "") or (
            "AI 分析结果为正常，保持良好的体态习惯即可。"
        )
    if db_result == "moderate":
        return ai_result.get("suggestion", "") or (
            "存在需要关注的体态问题，建议进行纠正训练。"
        )
    return ai_result.get("suggestion", "") or (
        "体态问题较为明显，建议尽快咨询专业医师。"
    )


def _photo_response(assessment: Any, db_result: str, suggestion: str) -> dict:
    """Build the photo-assessment response dict (shape shared by all paths)."""
    return {
        "id": str(assessment.id),
        "issue_id": assessment.issue_id,
        "result": db_result,
        "suggestion": suggestion,
    }


def _photo_tool_response(
    assessment: Any,
    db_result: str,
    suggestion: str,
    ai_result: Optional[dict],
) -> dict:
    """Build the richer typed Tool result while preserving the REST response.

    The REST endpoint still declares ``SelfAssessResponse`` and therefore
    serializes only its legacy four fields. Direct Tool callers additionally
    receive the structured, schema-validated analysis fields required by
    spec §10.4. Missing analysis metadata after a retention/purge operation is
    represented explicitly instead of inventing a healthy result.
    """
    result = _photo_response(assessment, db_result, suggestion)
    analysis = ai_result or {}
    result.update(
        {
            "severity": analysis.get("level") or assessment.severity,
            "confidence": analysis.get("confidence"),
            "evidence": analysis.get("evidence") or [],
            "model_meta": assessment.ai_model_meta,
        }
    )
    return result


async def _persist_photo_event(
    db: AsyncSession,
    user_id: str,
    issue_id: str,
    photo_keys: List[str],
    ai_result: dict,
) -> tuple:
    """Write-core for a photo assessment event (Task 7 photo-idempotency split).

    Creates the immutable event, superseding prior same-source active events,
    and recomputes the profile entry. Assumes the caller already holds the user
    transaction lock and has done the freeze / idempotency checks. Does NOT
    commit -- the orchestration entry points (``save_photo_assessment`` /
    ``analyze_and_save_photo``) own the commit so the write, the profile
    projection and (for the new path) the idempotency record land in ONE
    consistent transaction result (spec §10.0 / plan Task 7).

    Returns ``(assessment, db_result, suggestion)`` so callers can refresh and
    build the response dict after commit.
    """
    db_result = _map_ai_level_to_db(ai_result["level"])
    suggestion = _photo_suggestion(db_result, ai_result)
    await _supersede_active_events(db, user_id, issue_id, SOURCE_AI_PHOTO)
    assessment = PostureAssessment(
        user_id=UUID(user_id),
        issue_id=issue_id,
        source=SOURCE_AI_PHOTO,
        severity=db_result,
        lifecycle=LIFECYCLE_ACTIVE,
        ai_response=ai_result,
        photo_keys=photo_keys,
    )
    db.add(assessment)
    await db.flush()
    await _recompute_and_upsert_profile(db, user_id, issue_id)
    return assessment, db_result, suggestion


async def save_photo_assessment(
    db: AsyncSession,
    user_id: str,
    issue_id: str,
    photo_keys: List[str],
    ai_result: dict,
) -> dict:
    """Persist a photo assessment event and recompute the profile entry in a
    single transaction.

    Legacy entry point: the caller has ALREADY run the model and supplies
    ``ai_result``. AI failures / retakes / disabled photo gate are handled
    upstream (they raise 503 before this function is ever called), so this path
    always produces an event. The raw ``ai_response`` (with the original AI
    level) is preserved verbatim.

    Behaviour and signature are unchanged after the Task 7 write-core
    extraction (``_persist_photo_event``): lock -> freeze -> write core ->
    commit. Existing callers / tests see identical output.
    """
    # Hardening fix #9: service-layer validation (defense in depth)
    if not photo_keys:
        raise AppException(400, "photo_keys 不能为空", "invalid_photo_keys")
    if not get_issue_by_id(issue_id):
        raise AppException(400, "体态问题不存在", "issue_not_found")

    try:
        await _acquire_user_lock(db, user_id)
        await _assert_not_frozen(db, user_id)
        assessment, db_result, suggestion = await _persist_photo_event(
            db, user_id, issue_id, photo_keys, ai_result
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await db.refresh(assessment)
    return _photo_response(assessment, db_result, suggestion)


# --- Photo analysis idempotent orchestration (Task 7, spec §10.0 / §10.4) ---
#
# The idempotency check MUST run before the model call, under the user
# transaction lock, and the orchestration (check/replay -> model -> event +
# profile + idempotency_record) lands in one consistent transaction result
# (plan Task 7 photo-idempotency boundary). This path does NOT extract or
# refactor ``safety.py`` / ``confirm_posture_goals``' existing idempotency
# flows; it mirrors their rules against the SAME unified ``idempotency_records``
# table (spec §8.5).

_IDEMPOTENCY_OPERATION_PHOTO = "analyze_photo"


def _hash_photo_request(issue_id: str, photo_keys: List[str]) -> str:
    """Stable sha256 over the photo-analysis request identity (spec §8.5).

    ``photo_keys`` preserve caller order because image order can affect model
    interpretation. ``idempotency_key`` is intentionally excluded (it is the
    lookup key, not request identity), mirroring ``safety`` /
    ``confirm_posture_goals``.
    """
    identity = {"issue_id": issue_id, "photo_keys": list(photo_keys)}
    payload = json.dumps(identity, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _replay_photo_event(
    db: AsyncSession, user_id: str, event_id: str
) -> dict:
    """Rebuild a photo-assessment response from its stored event id.

    Restores the FIRST result without re-calling the model or re-writing. If
    the event was purged (cascade delete removed the row, or it belongs to
    another user) the replay surfaces HTTP 410 -- the cached health content is
    never served once its source is gone (spec §10.0 / §8.5).
    """
    try:
        event_uuid = UUID(event_id)
    except (AttributeError, TypeError, ValueError):
        raise AppException(
            410, "幂等记录指向的评估事件已被清除", "idempotency_result_gone"
        )
    event = await db.get(PostureAssessmentEvent, event_uuid)
    if event is None or event.user_id != UUID(user_id):
        raise AppException(
            410, "幂等记录指向的评估事件已被清除", "idempotency_result_gone"
        )
    # Phase C: derive db_result from severity (method/result columns dropped).
    # severity=None maps to 'uncertain' for API compatibility.
    db_result = event.severity if event.severity is not None else "uncertain"
    suggestion = _photo_suggestion(
        db_result, (event.ai_response or {})
    )
    return _photo_tool_response(
        event, db_result, suggestion, event.ai_response
    )


async def analyze_and_save_photo(
    db: AsyncSession,
    user_id: str,
    issue_id: str,
    photo_keys: List[str],
    idempotency_key: str,
    *,
    now: Optional[datetime] = None,
) -> dict:
    """Idempotent photo-analysis orchestration (spec §10.4 / plan Task 7).

    Runs under the user transaction lock and sequences: freeze check ->
    idempotency check / replay -> MODEL CALL -> event + profile projection +
    idempotency_record -> commit. The model is invoked at most once per
    ``(user, operation, idempotency_key)``; a replay returns the first result
    via ``result_ref`` and never calls the model or repeats the write.

    Idempotency rules (mirrors ``safety.record_safety_signal`` /
    ``confirm_posture_goals``):

      * same ``(user, op, key)`` + same ``request_hash`` -> replay first result
        (no model call, no repeat write)
      * same key + DIFFERENT ``request_hash`` -> 400 ``idempotency_key_conflict``
      * ``result_ref`` event purged / cross-user -> 410 ``idempotency_result_gone``
      * expired record -> removed, the key is reusable
      * ``idempotency_records`` stores ONLY ``result_ref`` (event id), never the
        full health response

    ``request_hash`` excludes ``idempotency_key`` (lookup key, not identity).
    Photo ownership and the privacy gate are enforced OUTSIDE this function
    (Tool layer): this orchestration assumes the caller already passed both.
    """
    from app.posture.ai_service import analyze_posture_photo

    if not photo_keys:
        raise AppException(400, "photo_keys 不能为空", "invalid_photo_keys")
    if (
        not isinstance(idempotency_key, str)
        or not idempotency_key.strip()
        or len(idempotency_key) > 64
    ):
        raise AppException(
            400, "idempotency_key 必须为 1-64 个非空字符", "invalid_idempotency_key"
        )
    if not get_issue_by_id(issue_id):
        raise AppException(400, "体态问题不存在", "issue_not_found")

    clock = _to_aware_utc(now) if now is not None else datetime.now(timezone.utc)
    request_hash = _hash_photo_request(issue_id, photo_keys)

    try:
        await _acquire_user_lock(db, user_id)
        await _assert_not_frozen(db, user_id)

        # --- Idempotency resolution (unified idempotency_records) ---
        existing = await db.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.user_id == UUID(user_id),
                IdempotencyRecord.operation == _IDEMPOTENCY_OPERATION_PHOTO,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        record = existing.scalar_one_or_none()
        if record is not None:
            if _to_aware_utc(record.expires_at) > clock:
                if record.request_hash == request_hash:
                    # Same key + same request -> replay the FIRST result. The
                    # model is NOT called and nothing is written. End the read
                    # transaction explicitly instead of holding the user lock.
                    response = await _replay_photo_event(
                        db, user_id, record.result_ref
                    )
                    await db.rollback()
                    return response
                # Same key + DIFFERENT request -> reject.
                raise AppException(
                    400,
                    "idempotency_key 已用于不同的请求",
                    "idempotency_key_conflict",
                )
            # Expired record no longer blocks; remove it and proceed.
            await db.delete(record)
            await db.flush()

        # --- Model call (under the lock, per the photo-idempotency boundary).
        # The Tool layer has already enforced the privacy gate and ownership,
        # so reaching here means both passed.
        ai_result = await analyze_posture_photo(
            issue_id, photo_keys, user_id, db
        )
        assessment, db_result, suggestion = await _persist_photo_event(
            db, user_id, issue_id, photo_keys, ai_result
        )

        # --- Persist the idempotency record (result_ref = event id only). ---
        db.add(
            IdempotencyRecord(
                user_id=UUID(user_id),
                operation=_IDEMPOTENCY_OPERATION_PHOTO,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                status="completed",
                result_ref=str(assessment.id),
                expires_at=clock + _IDEMPOTENCY_TTL,
            )
        )

        await db.commit()
    except AppException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise

    await db.refresh(assessment)
    return _photo_tool_response(
        assessment, db_result, suggestion, assessment.ai_response
    )


async def get_user_history(
    db: AsyncSession, user_id: str, limit: int = 20, offset: int = 0
) -> List[dict]:
    stmt = (
        select(PostureAssessment)
        .where(PostureAssessment.user_id == UUID(user_id))
        .order_by(desc(PostureAssessment.created_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    output = []
    for r in records:
        issue = get_issue_by_id(r.issue_id)
        # Phase C: source is NOT NULL; method is an API-compat alias of source.
        # result is derived from severity; severity=None maps to 'uncertain'.
        api_result = r.severity if r.severity is not None else "uncertain"
        output.append(
            {
                "id": str(r.id),
                "issue_id": r.issue_id,
                "issue_name": issue["name_cn"] if issue else r.issue_id,
                "method": r.source,
                "source": r.source,
                "result": api_result,
                "created_at": r.created_at,
            }
        )
    return output


# ---------------------------------------------------------------------------
# Profile reads (Phase 1 Task 4, spec §9.2)
# ---------------------------------------------------------------------------


def _all_knowledge_categories() -> List[str]:
    """Distinct categories present in the shipped knowledge base, sorted for
    deterministic output."""
    return sorted({i["category"] for i in get_all_issues()})


def build_profile_entry_detail(entry: PostureProfileEntry, issue: dict) -> dict:
    """Build the response dict for one profile entry.

    ``sources`` is passed through verbatim from the stored projection (built by
    ``project_profile``): it only ever carries ``source`` / ``event_id`` /
    ``severity`` / ``created_at`` -- never ``photo_keys``, photo URLs or the
    raw ``ai_response`` (privacy: spec §9.2 / Task 4 source-leakage rule).
    """
    return {
        "issue_id": entry.issue_id,
        "issue_name": issue["name_cn"],
        "category": issue["category"],
        "combined_severity": entry.combined_severity,
        "certainty": entry.certainty,
        "has_conflict": entry.has_conflict,
        "sources": entry.sources or [],
        "risk_tier": entry.risk_tier,
        "risk_version": entry.risk_version,
        "updated_at": entry.updated_at,
    }


async def get_user_profile_entry(
    db: AsyncSession, user_id: str, issue_id: str
) -> Optional[PostureProfileEntry]:
    """Return the current user's profile entry for one issue, or None.

    Scoped strictly to ``user_id`` (taken from the JWT) -- there is no
    ``user_id`` query parameter, so one user can never address another user's
    row (spec §9.2 / Task 4 cross-user isolation rule).
    """
    return await db.scalar(
        select(PostureProfileEntry).where(
            PostureProfileEntry.user_id == UUID(user_id),
            PostureProfileEntry.issue_id == issue_id,
        )
    )


async def get_user_profile(db: AsyncSession, user_id: str) -> dict:
    """Build the full profile response for the current user.

    Loads all of the user's profile entries, enriches each with its knowledge
    issue name/category, derives the evaluated categories and the complementary
    unevaluated categories, and the certainty-keyed summary counts. Read-only:
    no writes, no commit, no risk overlay re-evaluation.
    """
    result = await db.execute(
        select(PostureProfileEntry)
        .where(PostureProfileEntry.user_id == UUID(user_id))
        .order_by(PostureProfileEntry.issue_id.asc())
    )
    entries = result.scalars().all()

    evaluated_issues: List[dict] = []
    evaluated_categories: set = set()
    total_conflict = 0
    total_provisional = 0

    for entry in entries:
        issue = get_issue_by_id(entry.issue_id)
        # A profile entry should always reference a shipped knowledge issue.
        # If the catalog ever drops an evaluated issue, skip it rather than
        # exposing an unrepresentable / partial row.
        if issue is None:
            continue
        evaluated_categories.add(issue["category"])
        if entry.certainty == CERTAINTY_CONFLICT:
            total_conflict += 1
        elif entry.certainty == CERTAINTY_PROVISIONAL:
            total_provisional += 1
        evaluated_issues.append(build_profile_entry_detail(entry, issue))

    all_categories = _all_knowledge_categories()
    unevaluated_categories = [
        c for c in all_categories if c not in evaluated_categories
    ]

    return {
        "user_id": user_id,
        "evaluated_issues": evaluated_issues,
        "unevaluated_categories": unevaluated_categories,
        "summary": {
            "total_evaluated": len(evaluated_issues),
            "total_conflict": total_conflict,
            "total_provisional": total_provisional,
        },
    }


# ---------------------------------------------------------------------------
# Priority suggestions read + goal confirmation (Phase 1 Task 6, spec §9.2 /
# §10.6 / §10.7 / §12.3 / §12.4)
# ---------------------------------------------------------------------------

# Idempotency operation name stored in idempotency_records (spec §8.5). The
# confirm path uses the SAME unified idempotency table as the other
# side-effect tools; no separate idempotency module is introduced.
_IDEMPOTENCY_OPERATION_CONFIRM = "confirm_goals"
_IDEMPOTENCY_TTL = timedelta(hours=24)

MIN_GOALS = 1
MAX_GOALS = 3


async def get_priority_suggestions(
    db: AsyncSession, user_id: str, *, now: Optional[datetime] = None
) -> dict:
    """Read-only deterministic priority suggestions (spec §10.6).

    Thin wrapper around ``priority.build_priority_suggestions`` so the router
    layer depends on the service module only. Performs NO writes and NO plan
    generation.
    """
    from app.posture import priority

    return await priority.build_priority_suggestions(db, user_id, now=now)


def _hash_confirm_request(
    suggestion_id: str, profile_version: str, goals: List[Any]
) -> str:
    """Stable sha256 over the confirm request identity (spec §8.5).

    Goals are normalised by ``priority_rank`` so re-ordering the JSON array
    does not change the hash. ``idempotency_key`` is intentionally excluded
    (it is the lookup key, not request identity), mirroring ``safety``.
    """
    identity = {
        "suggestion_id": suggestion_id,
        "profile_version": profile_version,
        "goals": sorted(
            [
                {"issue_id": g.issue_id, "priority_rank": g.priority_rank}
                for g in goals
            ],
            key=lambda x: x["priority_rank"],
        ),
    }
    payload = json.dumps(identity, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _to_aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def _replay_confirm_batch(
    db: AsyncSession, user_id: str, anchor_id: str
) -> dict:
    """Rebuild the FIRST confirmed batch from its anchor goal id.

    Restores the complete first batch even if it was later superseded; does
    NOT re-check staleness or re-write. If the anchor was purged (cascade
    delete removed the goal rows) the replay surfaces HTTP 410 (spec §10.0 /
    §8.5).
    """
    anchor = await db.get(PostureUserGoal, UUID(anchor_id))
    if anchor is None or anchor.user_id != UUID(user_id):
        raise AppException(
            410, "幂等记录指向的目标批次已被清除", "idempotency_result_gone"
        )
    result = await db.execute(
        select(PostureUserGoal)
        .where(
            PostureUserGoal.user_id == UUID(user_id),
            PostureUserGoal.confirmed_at == anchor.confirmed_at,
        )
        .order_by(PostureUserGoal.priority_rank.asc())
    )
    batch = list(result.scalars().all())
    confirmed = [
        {
            "issue_id": g.issue_id,
            "priority_rank": g.priority_rank,
            "confirmed_at": _to_aware_utc(g.confirmed_at),
        }
        for g in batch
    ]
    return {
        "confirmed_goals": confirmed,
        "can_generate_plan": True,
        "risk_version": anchor.risk_version,
    }


async def _next_goal_batch_time(
    db: AsyncSession, user_id: str, requested: datetime
) -> datetime:
    """Return a per-user monotonically unique confirmation batch timestamp.

    Batch replay uses ``(user_id, confirmed_at)`` to recover every row that
    belongs to the anchor goal. The user transaction lock serializes writers,
    while this helper makes the timestamp itself unique even when two requests
    observe the same wall-clock instant or a test injects a frozen clock.
    """
    latest = await db.scalar(
        select(PostureUserGoal.confirmed_at)
        .where(PostureUserGoal.user_id == UUID(user_id))
        .order_by(PostureUserGoal.confirmed_at.desc())
        .limit(1)
    )
    requested_utc = _to_aware_utc(requested)
    if latest is None:
        return requested_utc
    latest_utc = _to_aware_utc(latest)
    if requested_utc <= latest_utc:
        return latest_utc + timedelta(microseconds=1)
    return requested_utc


async def confirm_posture_goals(
    db: AsyncSession,
    user_id: str,
    suggestion_id: str,
    profile_version: str,
    goals: List[Any],
    idempotency_key: str,
    *,
    now: Optional[datetime] = None,
) -> dict:
    """Confirm 1-3 of the user's current normal-candidate goals (spec §10.7).

    Write path (spec §10.7 / plan Task 6): user transaction lock -> purge
    freeze check -> idempotency resolution -> recompute (reload profile +
    reload signals + reclassify) -> stale check -> goal qualification ->
    supersede prior goals -> write the new batch -> persist idempotency
    record.

    Server control values (``suggestion_id`` / ``profile_version`` /
    ``rule_version`` / ``risk_version``) are regenerated server-side and used
    as the optimistic lock; a client-supplied ``priority_context_snapshot``
    is rejected earlier by the request schema (``extra="forbid"``).

    Batch semantics (spec §10.0): every goal in one batch shares the same
    server ``confirmed_at``; the idempotency record's ``result_ref`` points
    at the batch's anchor goal (rank 1) so a replay can restore the full
    first batch.
    """
    from app.posture import priority, risk_rules

    clock = _to_aware_utc(now) if now is not None else datetime.now(timezone.utc)
    request_hash = _hash_confirm_request(suggestion_id, profile_version, goals)

    try:
        await _acquire_user_lock(db, user_id)
        await _assert_not_frozen(db, user_id)

        # --- Idempotency resolution (unified idempotency_records) ---
        existing = await db.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.user_id == UUID(user_id),
                IdempotencyRecord.operation == _IDEMPOTENCY_OPERATION_CONFIRM,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        record = existing.scalar_one_or_none()
        if record is not None:
            if _to_aware_utc(record.expires_at) > clock:
                if record.request_hash == request_hash:
                    # Same key + same request -> replay the FIRST batch. No
                    # writes; the user lock is transaction-scoped so end the
                    # read transaction explicitly instead of holding it.
                    response = await _replay_confirm_batch(
                        db, user_id, record.result_ref
                    )
                    await db.rollback()
                    return response
                # Same key + DIFFERENT request -> reject.
                raise AppException(
                    400,
                    "idempotency_key 已用于不同的请求",
                    "idempotency_key_conflict",
                )
            # Expired record no longer blocks; remove it and proceed.
            await db.delete(record)
            await db.flush()

        # --- Recompute (safety gate): reload profile + signals + reclassify.
        # Read-only; build_priority_suggestions persists nothing.
        current = await priority.build_priority_suggestions(db, user_id, now=clock)

        # --- Stale check BEFORE goal qualification (spec §10.7) ---
        if (
            current["suggestion_id"] != suggestion_id
            or current["profile_version"] != profile_version
        ):
            raise AppException(
                409,
                "优先级建议已过期，请重新获取（档案或安全信号已变化）",
                "stale_priority",
            )

        candidate_ids = {c["issue_id"] for c in current["normal_candidates"]}
        safety_blocked_map = {
            item["issue_id"]: item["risk_tier"]
            for item in current["safety_blocked"]
        }

        # --- Goal qualification ---
        _validate_goal_structure(goals)
        for g in goals:
            issue = get_issue_by_id(g.issue_id)
            if issue is None:
                raise AppException(404, "体态问题不存在", "issue_not_found")
            if g.issue_id in candidate_ids:
                continue
            if g.issue_id in safety_blocked_map:
                tier = safety_blocked_map[g.issue_id]
                if tier == "red_flag":
                    raise AppException(
                        409, "红旗条目阻止目标确认", "red_flag_blocked"
                    )
                raise AppException(
                    409,
                    "受限安全信号条目阻止普通目标确认",
                    "restricted_blocked",
                )
            raise AppException(
                400,
                "目标问题不在当前候选列表中（未评估/normal/provisional/conflict）",
                "invalid_goal",
            )

        # --- Supersede prior active goals, then write the new batch ---
        batch_confirmed_at = await _next_goal_batch_time(db, user_id, clock)
        await db.execute(
            update(PostureUserGoal)
            .where(
                PostureUserGoal.user_id == UUID(user_id),
                PostureUserGoal.superseded_at.is_(None),
            )
            .values(superseded_at=batch_confirmed_at)
        )

        goals_sorted = sorted(goals, key=lambda g: g.priority_rank)
        new_goals: List[PostureUserGoal] = []
        for g in goals_sorted:
            goal = PostureUserGoal(
                user_id=UUID(user_id),
                issue_id=g.issue_id,
                priority_rank=g.priority_rank,
                confirmed_at=batch_confirmed_at,
                suggestion_id=suggestion_id,
                profile_version=profile_version,
                rule_version=priority.PRIORITY_RULE_VERSION,
                risk_version=risk_rules.RISK_VERSION,
            )
            db.add(goal)
            new_goals.append(goal)
        await db.flush()  # populate ids

        anchor = new_goals[0]  # rank-1 goal is the batch anchor
        db.add(
            IdempotencyRecord(
                user_id=UUID(user_id),
                operation=_IDEMPOTENCY_OPERATION_CONFIRM,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                status="completed",
                result_ref=str(anchor.id),
                expires_at=clock + _IDEMPOTENCY_TTL,
            )
        )

        await db.commit()
    except AppException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise

    confirmed = [
        {
            "issue_id": g.issue_id,
            "priority_rank": g.priority_rank,
            "confirmed_at": _to_aware_utc(g.confirmed_at),
        }
        for g in new_goals
    ]
    return {
        "confirmed_goals": confirmed,
        "can_generate_plan": True,
        "risk_version": risk_rules.RISK_VERSION,
    }


def _validate_goal_structure(goals: List[Any]) -> None:
    """Structural checks that surface as 400 ``invalid_goal`` (spec §9.3 /
    §10.7): 1-3 goals, distinct issue_ids, ranks unique and exactly the
    consecutive set ``1..N``. Called AFTER the stale check per §10.7 ordering."""
    if not isinstance(goals, list) or len(goals) < MIN_GOALS or len(goals) > MAX_GOALS:
        raise AppException(
            400, "需确认 1-3 个目标", "invalid_goal"
        )
    issue_ids = [g.issue_id for g in goals]
    if len(set(issue_ids)) != len(issue_ids):
        raise AppException(400, "目标问题不能重复", "invalid_goal")
    ranks = [g.priority_rank for g in goals]
    if len(set(ranks)) != len(ranks):
        raise AppException(400, "priority_rank 不能重复", "invalid_goal")
    expected = set(range(1, len(goals) + 1))
    if set(ranks) != expected:
        raise AppException(
            400, "priority_rank 必须唯一且连续为 1..N", "invalid_goal"
        )
