from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, update
from app.posture.models import (
    PostureAssessment,
    PostureAssessmentEvent,
    PostureProfileEntry,
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
    try:
        from app.posture.purge import is_user_write_frozen
    except ImportError:
        return
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
    """Persist a self-test assessment event (dual-write) and recompute the
    profile entry in a single transaction.

    Dual-write: ``method`` + ``source`` and ``result`` + ``severity`` are
    populated together. For an ``uncertain`` answer the legacy ``result`` stays
    ``'uncertain'`` (compatibility) while ``severity`` is set to ``None``
    (severity is permanently nullable, migration 0002). Prior same-source
    active events are superseded; the projection honours only the latest event
    per source.
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
            method=SOURCE_SELF_TEST,
            result=result_level,
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


async def save_photo_assessment(
    db: AsyncSession,
    user_id: str,
    issue_id: str,
    photo_keys: List[str],
    ai_result: dict,
) -> dict:
    """Persist a photo assessment event (dual-write) and recompute the profile
    entry in a single transaction.

    ``ai_result`` is already validated by ``ai_service.analyze_posture_photo``
    (level in normal/mild/moderate/severe, ``need_retake`` False). AI failures
    / retakes / disabled photo gate are handled upstream (they raise 503 before
    this function is ever called), so this path always produces an event. The
    raw ``ai_response`` (with the original AI level) is preserved verbatim.
    """
    # Hardening fix #9: service-layer validation (defense in depth)
    if not photo_keys:
        raise AppException(400, "photo_keys 不能为空", "invalid_photo_keys")
    issue = get_issue_by_id(issue_id)
    if not issue:
        raise AppException(400, "体态问题不存在", "issue_not_found")

    ai_level = ai_result["level"]
    db_result = _map_ai_level_to_db(ai_level)

    if db_result == "normal":
        suggestion = (
            ai_result.get("suggestion", "")
            or "AI 分析结果为正常，保持良好的体态习惯即可。"
        )
    elif db_result == "moderate":
        suggestion = (
            ai_result.get("suggestion", "")
            or "存在需要关注的体态问题，建议进行纠正训练。"
        )
    else:  # severe
        suggestion = (
            ai_result.get("suggestion", "")
            or "体态问题较为明显，建议尽快咨询专业医师。"
        )

    try:
        await _acquire_user_lock(db, user_id)
        await _assert_not_frozen(db, user_id)
        await _supersede_active_events(db, user_id, issue_id, SOURCE_AI_PHOTO)
        assessment = PostureAssessment(
            user_id=UUID(user_id),
            issue_id=issue_id,
            method=SOURCE_AI_PHOTO,
            result=db_result,
            source=SOURCE_AI_PHOTO,
            severity=db_result,
            lifecycle=LIFECYCLE_ACTIVE,
            ai_response=ai_result,
            photo_keys=photo_keys,
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
        "result": db_result,
        "suggestion": suggestion,
    }


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
        output.append(
            {
                "id": str(r.id),
                "issue_id": r.issue_id,
                "issue_name": issue["name_cn"] if issue else r.issue_id,
                "method": r.method,
                "result": r.result,
                "created_at": r.created_at,
            }
        )
    return output
