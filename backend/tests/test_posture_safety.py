"""Tests for Phase 1 Task 6.5: safety signals + versioned risk classification.

Covers spec §12.2 / §12.5 / §12.6 and the recovery rules decided in Task 6.5.
All signals are synthetic. No raw signal payloads are logged.
"""
import uuid as _uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.exceptions import AppException
from app.posture import risk_rules
from app.posture.models import (
    IdempotencyRecord,
    PostureProfileEntry,
    PostureSafetySignal,
)
from app.posture.risk_rules import RISK_VERSION
from tests.conftest import TestSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _login_user(client, phone="13800138000"):
    await client.post("/api/v1/auth/send-code", json={"phone": phone})
    from app.auth.models import VerificationCode

    async with TestSession() as db:
        result = await db.execute(
            select(VerificationCode)
            .where(VerificationCode.phone == phone)
            .order_by(VerificationCode.created_at.desc())
        )
        code = result.scalar_one().code

    resp = await client.post(
        "/api/v1/auth/verify-login", json={"phone": phone, "code": code}
    )
    return resp.json()["access_token"]


async def _create_profile_entry(
    user_id: str,
    issue_id: str = "HN-01",
    certainty: str = "confirmed",
    combined_severity: str = "moderate",
    risk_tier: str = "normal",
) -> PostureProfileEntry:
    """Create a profile entry directly (service.py is not modified in this task)."""
    entry = PostureProfileEntry(
        user_id=_uuid.UUID(user_id),
        issue_id=issue_id,
        certainty=certainty,
        combined_severity=combined_severity,
        sources={},
        has_conflict=False,
        risk_tier=risk_tier,
        risk_version=RISK_VERSION,
    )
    async with TestSession() as db:
        db.add(entry)
        await db.commit()
    return entry


def _signal_payload(
    signal_type="pain",
    body_region="head_neck",
    related_issue_id="HN-01",
    severity_hint="mild",
    idempotency_key="key-1",
):
    return {
        "signal_type": signal_type,
        "body_region": body_region,
        "related_issue_id": related_issue_id,
        "severity_hint": severity_hint,
        "idempotency_key": idempotency_key,
    }


# ===========================================================================
# Pure classification rules (risk_rules.classify) — no DB
# ===========================================================================


def _sig(signal_type, severity_hint=None, body_region="head_neck"):
    return {
        "signal_type": signal_type,
        "severity_hint": severity_hint,
        "body_region": body_region,
    }


def test_classify_no_signals_is_normal():
    result = risk_rules.classify([])
    assert result.risk_tier == "normal"
    assert result.risk_version == RISK_VERSION
    assert result.rule_id == "N-baseline"


def test_classify_single_mild_pain_is_cautious():
    result = risk_rules.classify([_sig("pain", "mild")])
    assert result.risk_tier == "cautious"
    assert result.rule_id == "C-any-signal"


def test_classify_single_moderate_is_cautious_not_restricted():
    """A single moderate signal alone must NOT be restricted (combinatorial)."""
    result = risk_rules.classify([_sig("pain", "moderate")])
    assert result.risk_tier == "cautious"


def test_classify_multiple_moderate_is_restricted():
    """Multiple moderate signals combined drive restricted — not a single hint."""
    result = risk_rules.classify(
        [_sig("pain", "moderate"), _sig("numbness", "moderate")]
    )
    assert result.risk_tier == "restricted"
    assert result.rule_id == "RST-multiple-moderate"


def test_classify_severe_non_neuro_pain_is_restricted():
    result = risk_rules.classify([_sig("pain", "severe")])
    assert result.risk_tier == "restricted"
    assert result.rule_id == "RST-severe-symptom"


def test_classify_acute_trauma_is_restricted_regardless_of_severity():
    """P2-1: acute_trauma is a restricted product-policy gate (NOT red_flag)."""
    result = risk_rules.classify([_sig("acute_trauma", None)])
    assert result.risk_tier == "restricted"
    assert result.rule_id == "RST-acute-trauma"
    assert result.risk_tier != "red_flag"


def test_classify_acute_trauma_restricted_even_with_mild_severity():
    result = risk_rules.classify([_sig("acute_trauma", "mild")])
    assert result.risk_tier == "restricted"
    assert result.risk_tier != "red_flag"


def test_classify_acute_trauma_is_restricted_without_body_region():
    """P2-1: any acute_trauma signal → restricted, regardless of body_region
    (the spine/trunk filter was specific to the removed red_flag rule)."""
    # body_region="" (empty string) → still restricted
    result = risk_rules.classify([_sig("acute_trauma", None, body_region="")])
    assert result.risk_tier == "restricted"
    assert result.rule_id == "RST-acute-trauma"

    # body_region=None → same
    result2 = risk_rules.classify(
        [{"signal_type": "acute_trauma", "severity_hint": "severe", "body_region": None}]
    )
    assert result2.risk_tier == "restricted"

    # body_region="lower_limb" (extremity) → still restricted (uniform gate)
    result3 = risk_rules.classify(
        [_sig("acute_trauma", "severe", body_region="lower_limb")]
    )
    assert result3.risk_tier == "restricted"


@pytest.mark.parametrize("neuro", ["numbness", "weakness"])
def test_classify_severe_neuro_is_restricted(neuro):
    """P2-1: severe numbness/weakness (cervical region) → restricted
    (downgraded from red_flag). Dizziness excluded per Bier 2018."""
    result = risk_rules.classify([_sig(neuro, "severe")])
    assert result.risk_tier == "restricted"
    assert result.rule_id == "RST-severe-neuro"
    assert result.risk_tier != "red_flag"


def test_classify_severe_dizziness_is_NOT_red_flag():
    """Hardening fix #8: dizziness+severe+head_neck does NOT trigger red_flag.

    Bier 2018 CPG does NOT mention dizziness/vertigo as a cervical red-flag
    indicator. Dizziness is classified as restricted (severe non-neuro symptom)
    or cautious depending on other signals present.
    """
    result = risk_rules.classify([_sig("dizziness", "severe")])
    assert result.risk_tier != "red_flag"
    # severe non-neuro → restricted (RST-severe-symptom)
    assert result.risk_tier == "restricted"
    assert result.rule_id == "RST-severe-symptom"


def test_classify_moderate_neuro_is_not_red_flag():
    """severity_hint=severe of neuro is red_flag; moderate is NOT."""
    result = risk_rules.classify([_sig("numbness", "moderate")])
    assert result.risk_tier != "red_flag"


def test_classify_combines_signals_not_single_hint():
    """Two mild signals stay cautious; adding acute_trauma escalates to restricted."""
    two_mild = risk_rules.classify([_sig("pain", "mild"), _sig("numbness", "mild")])
    assert two_mild.risk_tier == "cautious"

    escalated = risk_rules.classify(
        [_sig("pain", "mild"), _sig("acute_trauma", None)]
    )
    assert escalated.risk_tier == "restricted"
    assert escalated.rule_id == "RST-acute-trauma"


# ===========================================================================
# Two-tier provenance (§12.6): clinical-source for red_flag, product-policy
# for restricted. No fabricated DOIs/ISBNs; no internal-heuristic.
# ===========================================================================


@pytest.mark.parametrize("rule_id", ["RST-acute-trauma", "RST-severe-neuro"])
def test_downgraded_rules_carry_product_policy_not_clinical(rule_id):
    """P2-1: the former red_flag rules are now restricted product-policy gates
    (no clinical-source, no DOI/ISBN/URL)."""
    rule = risk_rules.get_rule(rule_id)
    assert rule is not None
    assert rule.risk_tier == "restricted"
    src = rule.provenance
    assert isinstance(src, risk_rules.ProductPolicy)
    assert not isinstance(src, risk_rules.ClinicalSource)
    assert src.provenance_type == "product-policy"
    for attr in ("policy_id", "policy_version", "rationale", "owner", "reviewed_at"):
        assert getattr(src, attr), f"{rule_id} policy missing {attr}"
    assert "暂停普通自动建议" in src.rationale
    # Product-policy carries NO DOI/ISBN/URL identifier (not a clinical claim).
    assert not risk_rules._is_valid_clinical_identifier(src.policy_id)


@pytest.mark.parametrize("rule_id", ["RST-multiple-moderate", "RST-severe-symptom"])
def test_restricted_rules_carry_product_policy_not_clinical(rule_id):
    rule = risk_rules.get_rule(rule_id)
    src = rule.provenance
    assert isinstance(src, risk_rules.ProductPolicy)
    assert src.provenance_type == "product-policy"
    # Product-policy carries NO DOI/ISBN/URL identifier (not a clinical claim).
    for attr in ("policy_id", "policy_version", "rationale", "owner", "reviewed_at"):
        assert getattr(src, attr), f"{rule_id} policy missing {attr}"
    assert "暂停普通自动建议" in src.rationale
    assert not risk_rules._is_valid_clinical_identifier(src.policy_id)


def test_no_rule_uses_internal_heuristic_provenance():
    """The fake 'internal-heuristic' source type is fully removed."""
    for rule in risk_rules.all_rules():
        if rule.provenance is None:
            continue
        assert rule.provenance.provenance_type in {"clinical-source", "product-policy"}
        assert rule.provenance.provenance_type != "internal-heuristic"


def test_phase1_ships_no_red_flag_or_clinical_source_rule():
    """P2-1: Phase 1 ships NO red_flag rule and NO clinical-source provenance.
    Product-policy rules must never carry a DOI/ISBN/URL identifier."""
    for rule in risk_rules.all_rules():
        assert rule.risk_tier != risk_rules.RED_FLAG, (
            f"{rule.rule_id} is red_flag — Phase 1 ships no auto red_flag rule"
        )
        prov = rule.provenance
        if prov is None:
            continue
        assert not isinstance(prov, risk_rules.ClinicalSource), (
            f"{rule.rule_id} carries clinical-source provenance (none ship in Phase 1)"
        )
        assert isinstance(prov, risk_rules.ProductPolicy)
        # Product-policy must NOT carry a DOI/clinical identifier.
        for attr_name in ("policy_id", "policy_version", "rationale", "owner"):
            attr_val = getattr(prov, attr_name)
            assert not risk_rules._is_valid_clinical_identifier(attr_val), (
                f"{rule.rule_id} product-policy attr {attr_name} looks clinical: {attr_val!r}"
            )


def test_clinical_source_and_product_policy_remain_distinguishable():
    """P2-1: no clinical-source rule ships, but the two provenance TYPES remain
    distinct (reserved for future clinical-source red_flag rules)."""
    clinical = risk_rules.ClinicalSource(
        "10.1093/ptj/pzx118", "L1", "v", "2026-07-16", "s", "l"
    )
    policy = risk_rules.get_rule("RST-acute-trauma").provenance
    assert isinstance(clinical, risk_rules.ClinicalSource)
    assert isinstance(policy, risk_rules.ProductPolicy)
    assert not isinstance(policy, risk_rules.ClinicalSource)
    assert not isinstance(clinical, risk_rules.ProductPolicy)
    assert clinical.provenance_type != policy.provenance_type


def test_risk_version_bumped_for_p2_1_downgrade():
    """P2-1: RISK_VERSION bumped to the new value after the downgrade."""
    assert RISK_VERSION == "2026-07-16-v4"


# ===========================================================================
# API: POST /api/v1/posture/safety-signals
# ===========================================================================


@pytest.mark.asyncio
async def test_pain_signal_downgrades_related_profile(client):
    token = await _login_user(client)
    # Decode user id from token to create a profile entry.
    import jwt

    from app.core.config import settings

    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"verify_aud": False},
    )
    user_id = payload["sub"]
    await _create_profile_entry(user_id, issue_id="HN-01", combined_severity="moderate")

    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(signal_type="pain", severity_hint="mild"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["lifecycle"] == "active"
    assert body["status"] == "recorded"
    assert body["risk_version"] == RISK_VERSION
    assert body["classification"]["risk_tier"] == "cautious"

    async with TestSession() as db:
        result = await db.execute(
            select(PostureProfileEntry).where(
                PostureProfileEntry.user_id == _uuid.UUID(user_id),
                PostureProfileEntry.issue_id == "HN-01",
            )
        )
        entry = result.scalar_one()
        assert entry.certainty == "provisional"
        assert entry.combined_severity is None
        assert entry.risk_tier == "cautious"
        assert entry.risk_version == RISK_VERSION


@pytest.mark.asyncio
async def test_acute_trauma_triggers_restricted(client):
    """P2-1: acute_trauma → restricted (RST-acute-trauma), NOT red_flag."""
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(signal_type="acute_trauma", severity_hint=None),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["risk_tier"] == "restricted"
    assert body["classification"]["rule_id"] == "RST-acute-trauma"
    assert body["risk_tier"] != "red_flag"


@pytest.mark.asyncio
async def test_multiple_signals_combined_drive_classification(client):
    """Two moderate signals push restricted; a single moderate alone is cautious."""
    token = await _login_user(client)
    first = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(
            signal_type="pain", severity_hint="moderate", idempotency_key="k-mod-1"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200
    assert first.json()["risk_tier"] == "cautious"

    second = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(
            signal_type="numbness",
            severity_hint="moderate",
            idempotency_key="k-mod-2",
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.status_code == 200
    assert second.json()["risk_tier"] == "restricted"


@pytest.mark.asyncio
async def test_severe_assessment_alone_does_not_trigger_red_flag(client):
    """Anti-inference: severe profile + knowledge red_flags + NO structured signal
    reclassifies to normal, never red_flag."""
    token = await _login_user(client)
    import jwt

    from app.core.config import settings

    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"verify_aud": False},
    )
    user_id = payload["sub"]
    # Profile with severe severity and knowledge red_flags present (HN-01 ships them).
    await _create_profile_entry(
        user_id, issue_id="HN-01", combined_severity="severe", risk_tier="normal"
    )

    from app.posture import safety

    async with TestSession() as db:
        classification = await safety.classify_user_risk(db, user_id, "HN-01")
    assert classification.risk_tier == "normal"
    assert classification.risk_tier != "red_flag"

    # And downgrading with this classification keeps the entry non-red-flag.
    async with TestSession() as db:
        await safety.apply_classification_to_profile(db, user_id, "HN-01", classification)
        await db.commit()
        result = await db.execute(
            select(PostureProfileEntry).where(
                PostureProfileEntry.user_id == _uuid.UUID(user_id),
                PostureProfileEntry.issue_id == "HN-01",
            )
        )
        entry = result.scalar_one()
        assert entry.risk_tier == "normal"


@pytest.mark.asyncio
async def test_idempotency_same_key_same_request_returns_same_result(client):
    token = await _login_user(client)
    payload = _signal_payload(signal_type="pain", severity_hint="mild", idempotency_key="dup-1")

    first = await client.post(
        "/api/v1/posture/safety-signals",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200
    second = await client.post(
        "/api/v1/posture/safety-signals",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.status_code == 200
    assert first.json()["signal_id"] == second.json()["signal_id"]
    assert second.json()["status"] == "deduplicated"
    # No duplicate write.
    async with TestSession() as db:
        result = await db.execute(select(PostureSafetySignal))
        assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_idempotency_same_key_different_request_rejected(client):
    token = await _login_user(client)
    first_payload = _signal_payload(
        signal_type="pain", severity_hint="mild", idempotency_key="conflict-1"
    )
    await client.post(
        "/api/v1/posture/safety-signals",
        json=first_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    diff_payload = _signal_payload(
        signal_type="acute_trauma", severity_hint=None, idempotency_key="conflict-1"
    )
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=diff_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "idempotency_key_conflict"


@pytest.mark.asyncio
async def test_invalid_signal_type_returns_400(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(signal_type="not_a_real_signal"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_invalid_severity_hint_returns_400(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(severity_hint="catastrophic"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_missing_idempotency_key_returns_400(client):
    token = await _login_user(client)
    payload = _signal_payload()
    del payload["idempotency_key"]
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_missing_required_signal_type_returns_400(client):
    token = await _login_user(client)
    payload = _signal_payload()
    del payload["signal_type"]
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_nonexistent_related_issue_returns_400(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(related_issue_id="DOES-NOT-EXIST"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_risk_version_written_to_profile_and_signal(client):
    token = await _login_user(client)
    import jwt

    from app.core.config import settings

    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"verify_aud": False},
    )
    user_id = payload["sub"]
    await _create_profile_entry(user_id, issue_id="HN-01")

    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(signal_type="pain", severity_hint="mild"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    signal_id = resp.json()["signal_id"]

    async with TestSession() as db:
        sig = await db.get(PostureSafetySignal, _uuid.UUID(signal_id))
        assert sig is not None
        # resolved_risk_version is for resolved signals; the active signal's
        # classification version is reflected on the profile entry.
        entry_result = await db.execute(
            select(PostureProfileEntry).where(
                PostureProfileEntry.user_id == _uuid.UUID(user_id),
                PostureProfileEntry.issue_id == "HN-01",
            )
        )
        entry = entry_result.scalar_one()
        assert entry.risk_version == RISK_VERSION


@pytest.mark.asyncio
async def test_invalidates_until_set_but_does_not_auto_recover(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(signal_type="acute_trauma", severity_hint=None),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_tier"] == "restricted"
    assert body["invalidates_until"] is not None
    signal_id = body["signal_id"]

    # invalidates_until is a reminder window only; advancing past it must NOT
    # auto-resolve the signal. (SQLite returns naive datetimes, so compare
    # against a naive-UTC value.)
    past = datetime.utcnow() + timedelta(days=40)
    async with TestSession() as db:
        sig = await db.get(PostureSafetySignal, _uuid.UUID(signal_id))
        assert sig.invalidates_until < past
        assert sig.lifecycle == "active"
        assert sig.resolved_at is None


@pytest.mark.asyncio
async def test_no_auto_recovery_after_30_days(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(
            signal_type="numbness", severity_hint="severe", idempotency_key="k-30d"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["risk_tier"] == "restricted"
    signal_id = resp.json()["signal_id"]

    from app.posture import safety

    # Simulate 31 days passing: time alone must not recover.
    async with TestSession() as db:
        recovered = await safety.attempt_recovery_by_time_elapsed(
            db, _user_from_token(token), elapsed_days=31
        )
        assert recovered is False
        sig = await db.get(PostureSafetySignal, _uuid.UUID(signal_id))
        assert sig.lifecycle == "active"
        assert sig.resolved_at is None


def _user_from_token(token):
    import jwt

    from app.core.config import settings

    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"verify_aud": False},
    )
    return payload["sub"]


@pytest.mark.asyncio
async def test_free_text_seeked_medical_care_does_not_resolve_red_flag(client):
    """已就医 free-text claim must NOT resolve a red_flag signal."""
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(
            signal_type="acute_trauma", severity_hint=None, idempotency_key="k-freetext"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    signal_id = resp.json()["signal_id"]
    user_id = _user_from_token(token)

    from app.posture import safety

    async with TestSession() as db:
        result = await safety.attempt_recovery_by_free_text(db, user_id, claim="已就医")
        assert result is False
        sig = await db.get(PostureSafetySignal, _uuid.UUID(signal_id))
        assert sig.lifecycle == "active"
        assert sig.resolved_at is None


def test_recovery_guard_explicitly_rejects_forbidden_modes():
    """The explicit recovery guard rejects non-structured bases; only a
    structured reclassification is a valid resolution basis (spec §12.2)."""
    from app.posture.safety import (
        assert_recovery_is_structured,
        is_structured_recovery_basis,
    )

    assert is_structured_recovery_basis("reclassification") is True
    for forbidden in (
        "time_elapsed",
        "user_confirmed",
        "free_text_claim",
        "sought_medical_care_verbal",
    ):
        assert is_structured_recovery_basis(forbidden) is False
        with pytest.raises(AppException) as exc:
            assert_recovery_is_structured(forbidden)
        assert exc.value.status_code == 400
        assert exc.value.code == "recovery_requires_reclassification"


@pytest.mark.asyncio
async def test_structured_reclassification_success_path_disabled(client):
    """The reclassify_and_resolve success path is disabled (review fix #2):
    it raises 501 when the remaining signals produce a lower risk tier.
    Validation/rejection paths remain active."""
    token = await _login_user(client)
    user_id = _user_from_token(token)
    await _create_profile_entry(user_id, issue_id="HN-01", risk_tier="normal")

    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(
            signal_type="acute_trauma", severity_hint=None, idempotency_key="k-resolve"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.json()["risk_tier"] == "restricted"
    signal_id = resp.json()["signal_id"]

    from app.posture import safety

    async with TestSession() as db:
        # Build the structured attestation required for reclassification:
        # the CURRENT active set excluding the target signal (now empty).
        active = await safety.load_active_signals(db, user_id)
        remaining = [s for s in active if str(s.id) != signal_id]
        digest = safety.compute_signals_digest(remaining)
        snapshot = {"profile_version": "profile-v1", "issue_id": "HN-01"}
        # Success path now raises 501 (disabled until follow-up events exist)
        with pytest.raises(AppException) as exc:
            await safety.reclassify_and_resolve(
                db,
                user_id,
                signal_id,
                profile_snapshot=snapshot,
                active_signals_digest=digest,
                rule_version=RISK_VERSION,
            )
        assert exc.value.status_code == 501
        assert exc.value.code == "reclassify_not_implemented"

        # Signal remains active (not resolved)
        sig = await db.get(PostureSafetySignal, _uuid.UUID(signal_id))
        assert sig.lifecycle == "active"
        assert sig.resolved_at is None


@pytest.mark.asyncio
async def test_reclassification_does_not_resolve_when_other_red_flag_remains(client):
    """If another active red-flag signal remains, resolution must not happen."""
    token = await _login_user(client)
    user_id = _user_from_token(token)

    s1 = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(
            signal_type="acute_trauma", severity_hint=None, idempotency_key="k-r1"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    s2 = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(
            signal_type="weakness",
            severity_hint="severe",
            idempotency_key="k-r2",
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    s1_id = s1.json()["signal_id"]

    from app.posture import safety

    async with TestSession() as db:
        active = await safety.load_active_signals(db, user_id)
        remaining = [s for s in active if str(s.id) != s1_id]
        digest = safety.compute_signals_digest(remaining)
        outcome = await safety.reclassify_and_resolve(
            db,
            user_id,
            s1_id,
            profile_snapshot={"profile_version": "profile-v1"},
            active_signals_digest=digest,
            rule_version=RISK_VERSION,
        )
        await db.commit()
        assert outcome["resolved"] is False
        sig = await db.get(PostureSafetySignal, _uuid.UUID(s1_id))
        assert sig.lifecycle == "active"


@pytest.mark.asyncio
async def test_cross_user_isolation(client):
    """User A's signal/profile is not affected by user B."""
    token_a = await _login_user(client, phone="13800138001")
    token_b = await _login_user(client, phone="13800138002")
    user_a = _user_from_token(token_a)
    user_b = _user_from_token(token_b)
    await _create_profile_entry(user_a, issue_id="HN-01", combined_severity="moderate")
    await _create_profile_entry(user_b, issue_id="HN-01", combined_severity="moderate")

    await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(
            signal_type="acute_trauma", severity_hint=None, idempotency_key="k-a"
        ),
        headers={"Authorization": f"Bearer {token_a}"},
    )

    async with TestSession() as db:
        # User A has one signal; user B has none.
        a_sigs = (
            await db.execute(
                select(PostureSafetySignal).where(
                    PostureSafetySignal.user_id == _uuid.UUID(user_a)
                )
            )
        ).scalars().all()
        b_sigs = (
            await db.execute(
                select(PostureSafetySignal).where(
                    PostureSafetySignal.user_id == _uuid.UUID(user_b)
                )
            )
        ).scalars().all()
        assert len(a_sigs) == 1
        assert len(b_sigs) == 0

        b_entry = (
            await db.execute(
                select(PostureProfileEntry).where(
                    PostureProfileEntry.user_id == _uuid.UUID(user_b),
                    PostureProfileEntry.issue_id == "HN-01",
                )
            )
        ).scalar_one()
        # User B's profile untouched: stays confirmed/moderate/normal.
        assert b_entry.certainty == "confirmed"
        assert b_entry.risk_tier == "normal"


@pytest.mark.asyncio
async def test_safety_signal_writes_within_transaction(client):
    """Idempotency record + signal are written atomically."""
    token = await _login_user(client)
    user_id = _user_from_token(token)
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(idempotency_key="k-txn"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    async with TestSession() as db:
        rec = (
            await db.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.user_id == _uuid.UUID(user_id),
                    IdempotencyRecord.idempotency_key == "k-txn",
                )
            )
        ).scalar_one()
        assert rec.operation == "report_safety_signal"
        assert rec.status == "completed"
        assert rec.result_ref == resp.json()["signal_id"]
        assert rec.request_hash  # stored as a hash, never raw payload


# ===========================================================================
# Two-tier provenance — startup guard (FIX 1)
# ===========================================================================


def test_startup_guard_rejects_red_flag_without_clinical_source(monkeypatch):
    """A red_flag rule lacking a clinical-source provenance fails to load."""
    bad = risk_rules.RiskRule("RF-bad", risk_rules.RED_FLAG, "x", provenance=None)
    monkeypatch.setitem(risk_rules._RULES, "RF-bad", bad)
    with pytest.raises(RuntimeError):
        risk_rules._validate_registry()


def test_startup_guard_rejects_product_policy_as_red_flag(monkeypatch):
    """Product-policy may never masquerade as a red_flag rule."""
    pp = risk_rules.ProductPolicy("PP-x", "v1", "rationale", "owner", "2026-07-11")
    bad = risk_rules.RiskRule("RF-pp", risk_rules.RED_FLAG, "x", provenance=pp)
    monkeypatch.setitem(risk_rules._RULES, "RF-pp", bad)
    with pytest.raises(RuntimeError):
        risk_rules._validate_registry()


def test_startup_guard_rejects_fabricated_clinical_identifier(monkeypatch):
    """A clinical-source with a non-DOI/ISBN/URL identifier is rejected."""
    fake = risk_rules.ClinicalSource(
        source_identifier="internal-heuristic:fake",
        evidence_level="L3",
        version="v",
        reviewed_at="2026-07-11",
        scope="s",
        license="l",
    )
    bad = risk_rules.RiskRule("RF-fake", risk_rules.RED_FLAG, "x", provenance=fake)
    monkeypatch.setitem(risk_rules._RULES, "RF-fake", bad)
    with pytest.raises(RuntimeError):
        risk_rules._validate_registry()


def test_startup_guard_rejects_clinical_source_on_non_red_rule(monkeypatch):
    """clinical-source provenance is reserved for red_flag rules only."""
    good = risk_rules.ClinicalSource(
        "10.1093/ptj/pzx118", "L1", "v", "2026-07-11", "s", "l"
    )
    bad = risk_rules.RiskRule("C-bad", risk_rules.CAUTIOUS, "x", provenance=good)
    monkeypatch.setitem(risk_rules._RULES, "C-bad", bad)
    with pytest.raises(RuntimeError):
        risk_rules._validate_registry()


def test_startup_guard_accepts_shipped_registry():
    """The shipped registry passes the guard (sanity)."""
    risk_rules._validate_registry()  # must not raise


# ===========================================================================
# reclassify_and_resolve — requires new structured info (FIX 2)
# ===========================================================================


@pytest.mark.asyncio
async def test_reclassify_rejects_missing_structured_input(client):
    token = await _login_user(client)
    user_id = _user_from_token(token)
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(
            signal_type="acute_trauma", severity_hint=None, idempotency_key="k-miss"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    signal_id = resp.json()["signal_id"]

    from app.posture import safety

    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await safety.reclassify_and_resolve(
                db,
                user_id,
                signal_id,
                profile_snapshot=None,
                active_signals_digest=None,
                rule_version="",
            )
        assert exc.value.status_code == 400
        assert exc.value.code == "reclassify_missing_structured_input"


@pytest.mark.asyncio
async def test_reclassify_rejects_stale_rule_version(client):
    token = await _login_user(client)
    user_id = _user_from_token(token)
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(
            signal_type="acute_trauma", severity_hint=None, idempotency_key="k-stale-rv"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    signal_id = resp.json()["signal_id"]

    from app.posture import safety

    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await safety.reclassify_and_resolve(
                db,
                user_id,
                signal_id,
                profile_snapshot={"profile_version": "v1"},
                active_signals_digest="any-non-empty-attestation",
                rule_version="2020-01-01-v0",
            )
        assert exc.value.status_code == 409
        assert exc.value.code == "stale_rule_version"


@pytest.mark.asyncio
async def test_reclassify_rejects_stale_signals_digest(client):
    token = await _login_user(client)
    user_id = _user_from_token(token)
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(
            signal_type="acute_trauma", severity_hint=None, idempotency_key="k-stale-d"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    signal_id = resp.json()["signal_id"]

    from app.posture import safety

    async with TestSession() as db:
        with pytest.raises(AppException) as exc:
            await safety.reclassify_and_resolve(
                db,
                user_id,
                signal_id,
                profile_snapshot={"profile_version": "v1"},
                active_signals_digest="deadbeef-not-the-real-digest",
                rule_version=RISK_VERSION,
            )
        assert exc.value.status_code == 409
        assert exc.value.code == "stale_signals_digest"


@pytest.mark.asyncio
async def test_reclassify_success_path_returns_501(client):
    """Review fix #2: The success path now returns 501 since it requires
    persistent follow-up events and server-generated profile_version."""
    token = await _login_user(client)
    user_id = _user_from_token(token)
    await _create_profile_entry(user_id, issue_id="HN-01", risk_tier="normal")

    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(
            signal_type="acute_trauma", severity_hint=None, idempotency_key="k-rsrc"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    signal_id = resp.json()["signal_id"]

    from app.posture import safety

    async with TestSession() as db:
        active = await safety.load_active_signals(db, user_id)
        remaining = [s for s in active if str(s.id) != signal_id]
        digest = safety.compute_signals_digest(remaining)
        with pytest.raises(AppException) as exc:
            await safety.reclassify_and_resolve(
                db,
                user_id,
                signal_id,
                profile_snapshot={"profile_version": "profile-v9"},
                active_signals_digest=digest,
                rule_version=RISK_VERSION,
            )
        assert exc.value.status_code == 501
        assert exc.value.code == "reclassify_not_implemented"


# ===========================================================================
# Idempotency replay (FIX 3): updated classification + 410 for purged ref
# ===========================================================================


@pytest.mark.asyncio
async def test_idempotency_replay_returns_updated_classification(client):
    """A replay must reflect the CURRENT combined classification, not a stale
    single-signal snapshot (FIX 3)."""
    token = await _login_user(client)
    p1 = _signal_payload(
        signal_type="pain", severity_hint="moderate", idempotency_key="replay-1"
    )
    first = await client.post(
        "/api/v1/posture/safety-signals",
        json=p1,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.json()["risk_tier"] == "cautious"

    # Replay before any change → still cautious.
    replay = await client.post(
        "/api/v1/posture/safety-signals",
        json=p1,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert replay.json()["status"] == "deduplicated"
    assert replay.json()["risk_tier"] == "cautious"

    # Add a second moderate signal → the combined tier escalates to restricted.
    second = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(
            signal_type="numbness",
            severity_hint="moderate",
            idempotency_key="replay-2",
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.json()["risk_tier"] == "restricted"

    # Replay the FIRST key again → must now report the UPDATED restricted tier.
    replay2 = await client.post(
        "/api/v1/posture/safety-signals",
        json=p1,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert replay2.json()["status"] == "deduplicated"
    assert replay2.json()["risk_tier"] == "restricted"


@pytest.mark.asyncio
async def test_idempotency_replay_preserves_issue_risk_scope(client):
    """Replaying issue A must not inherit a restricted signal from issue B."""
    token = await _login_user(client)
    issue_a = _signal_payload(
        signal_type="pain",
        severity_hint="moderate",
        related_issue_id="HN-01",
        idempotency_key="scoped-replay-a",
    )
    first = await client.post(
        "/api/v1/posture/safety-signals",
        json=issue_a,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.json()["risk_tier"] == "cautious"

    issue_b = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(
            signal_type="acute_trauma",
            severity_hint="severe",
            related_issue_id="HN-02",
            idempotency_key="scoped-replay-b",
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert issue_b.json()["risk_tier"] == "restricted"

    replay = await client.post(
        "/api/v1/posture/safety-signals",
        json=issue_a,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert replay.json()["status"] == "deduplicated"
    assert replay.json()["risk_tier"] == "cautious"


@pytest.mark.asyncio
async def test_purged_result_ref_returns_410(client):
    """If the idempotency result_ref points to a purged signal → HTTP 410."""
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(idempotency_key="purge-1"),
        headers={"Authorization": f"Bearer {token}"},
    )
    signal_id = resp.json()["signal_id"]

    # Simulate purge/deletion of the underlying signal.
    async with TestSession() as db:
        sig = await db.get(PostureSafetySignal, _uuid.UUID(signal_id))
        await db.delete(sig)
        await db.commit()

    replay = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(idempotency_key="purge-1"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert replay.status_code == 410
    assert replay.json()["code"] == "idempotency_result_gone"


# ===========================================================================
# Risk scope: global (red_flag) vs issue-level (restricted) (FIX 4)
# ===========================================================================


def _fake_red_flag_classify(signals):
    """Simulate a future clinical red_flag rule: any non-empty signal set →
    red_flag. Phase 1 ships no auto red_flag rule, so the global-scope
    invariant (P1-4) is exercised through this deterministic stand-in."""
    if signals:
        return risk_rules.RiskClassification(
            risk_tier=risk_rules.RED_FLAG,
            risk_version=RISK_VERSION,
            rule_id="RF-future",
            reason="simulated future red_flag rule",
            sources=[],
        )
    return risk_rules.RiskClassification(
        risk_tier=risk_rules.NORMAL,
        risk_version=RISK_VERSION,
        rule_id="N-baseline",
        reason="no signals",
        sources=[],
    )


@pytest.mark.asyncio
async def test_global_red_flag_downgrades_all_profile_entries(client, monkeypatch):
    """P1-4: a global red_flag (regardless of related_issue_id) downgrades EVERY
    profile entry. Phase 1 has no auto red_flag rule, so the classification is
    simulated via monkeypatch."""
    monkeypatch.setattr(risk_rules, "classify", _fake_red_flag_classify)
    token = await _login_user(client)
    user_id = _user_from_token(token)
    await _create_profile_entry(user_id, issue_id="HN-01", risk_tier="normal")
    await _create_profile_entry(user_id, issue_id="ST-04", risk_tier="normal")

    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(
            signal_type="acute_trauma",
            severity_hint=None,
            related_issue_id="HN-01",
            idempotency_key="k-global-rf",
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.json()["risk_tier"] == "red_flag"

    async with TestSession() as db:
        rows = (
            await db.execute(
                select(PostureProfileEntry).where(
                    PostureProfileEntry.user_id == _uuid.UUID(user_id)
                )
            )
        ).scalars().all()
        assert len(rows) == 2
        for r in rows:
            assert r.risk_tier == "red_flag"
            assert r.certainty == "provisional"
            assert r.combined_severity is None


@pytest.mark.asyncio
async def test_red_flag_without_related_issue_still_downgrades_globally(client, monkeypatch):
    """P1-4: a red_flag with no related_issue_id is global and downgrades all
    profiles. Classification simulated via monkeypatch (Phase 1 has no red_flag rule)."""
    monkeypatch.setattr(risk_rules, "classify", _fake_red_flag_classify)
    token = await _login_user(client)
    user_id = _user_from_token(token)
    await _create_profile_entry(user_id, issue_id="HN-01", risk_tier="normal")
    await _create_profile_entry(user_id, issue_id="ST-04", risk_tier="normal")

    payload = _signal_payload(
        signal_type="acute_trauma",
        severity_hint=None,
        related_issue_id=None,
        idempotency_key="k-g-noref",
    )
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.json()["risk_tier"] == "red_flag"

    async with TestSession() as db:
        rows = (
            await db.execute(
                select(PostureProfileEntry).where(
                    PostureProfileEntry.user_id == _uuid.UUID(user_id)
                )
            )
        ).scalars().all()
        assert {r.risk_tier for r in rows} == {"red_flag"}


@pytest.mark.asyncio
async def test_restricted_signal_only_downgrades_related_issue(client):
    token = await _login_user(client)
    user_id = _user_from_token(token)
    await _create_profile_entry(user_id, issue_id="HN-01", risk_tier="normal")
    await _create_profile_entry(user_id, issue_id="ST-04", risk_tier="normal")

    first = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(
            signal_type="pain",
            severity_hint="moderate",
            related_issue_id="HN-01",
            idempotency_key="k-restr-1",
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.json()["risk_tier"] == "cautious"
    second = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(
            signal_type="numbness",
            severity_hint="moderate",
            related_issue_id="HN-01",
            idempotency_key="k-restr-2",
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.json()["risk_tier"] == "restricted"

    async with TestSession() as db:
        hn = (
            await db.execute(
                select(PostureProfileEntry).where(
                    PostureProfileEntry.user_id == _uuid.UUID(user_id),
                    PostureProfileEntry.issue_id == "HN-01",
                )
            )
        ).scalar_one()
        st = (
            await db.execute(
                select(PostureProfileEntry).where(
                    PostureProfileEntry.user_id == _uuid.UUID(user_id),
                    PostureProfileEntry.issue_id == "ST-04",
                )
            )
        ).scalar_one()
        assert hn.risk_tier == "restricted"  # the related issue is downgraded
        assert hn.certainty == "provisional"
        assert st.risk_tier == "normal"  # the unrelated issue is untouched
        assert st.certainty == "confirmed"


# ===========================================================================
# Schema hardening (FIX 5)
# ===========================================================================


@pytest.mark.asyncio
async def test_safety_request_rejects_unknown_field(client):
    token = await _login_user(client)
    payload = _signal_payload()
    payload["unexpected_field"] = "boom"
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_safety_request_rejects_blank_idempotency_key(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(idempotency_key="   "),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_safety_request_rejects_overlong_idempotency_key(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(idempotency_key="k" * 65),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_safety_request_rejects_overlong_signal_type(client):
    token = await _login_user(client)
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(signal_type="x" * 31),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_safety_request_rejects_future_reported_at(client):
    token = await _login_user(client)
    future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    payload = _signal_payload()
    payload["reported_at"] = future
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_safety_request_rejects_too_old_reported_at(client):
    token = await _login_user(client)
    old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    payload = _signal_payload()
    payload["reported_at"] = old
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


# ===========================================================================
# Session hygiene (FIX 6)
# ===========================================================================


def test_leaky_session_helper_is_removed():
    """FIX 6 regression: the ``_new_session`` helper that returned a bare,
    never-closed ``TestSession()`` must stay removed from the module."""
    import tests.test_posture_safety as mod

    assert not hasattr(mod, "_new_session")


@pytest.mark.asyncio
async def test_all_session_uses_are_context_managed():
    """FIX 6: every ``TestSession()`` call site in this module must be opened
    through an ``async with`` context manager so the session is torn down
    deterministically (no bare, never-closed sessions)."""
    import inspect

    import tests.test_posture_safety as mod

    src = inspect.getsource(mod)
    # Strip this regression test's own text so it cannot match itself.
    src = src.split("# Session hygiene (FIX 6)")[0]
    for idx, line in enumerate(src.splitlines()):
        if "TestSession()" in line and "async_sessionmaker" not in line:
            # A bare construction must be on the same logical line as, or
            # inside, an ``async with``. The only allowed form is the context
            # manager ``async with TestSession() as ...``.
            window = "\n".join(src.splitlines()[max(0, idx - 1): idx + 1])
            assert "async with" in window, (
                f"TestSession() not wrapped in async with at line {idx + 1}: {line!r}"
            )


# ===========================================================================
# Review regression tests (fix #2, #3, #4, #12)
# ===========================================================================


@pytest.mark.asyncio
async def test_reclassify_returns_501_on_success_path(client):
    """Review fix #2: reclassify_and_resolve success path disabled (returns 501)."""
    token = await _login_user(client)
    user_id = _user_from_token(token)
    await _create_profile_entry(user_id, issue_id="HN-01", risk_tier="normal")

    # Create a signal that would be resolvable
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json=_signal_payload(
            signal_type="pain", severity_hint="mild", idempotency_key="k-501"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    signal_id = resp.json()["signal_id"]

    from app.posture import safety

    async with TestSession() as db:
        active = await safety.load_active_signals(db, user_id)
        remaining = [s for s in active if str(s.id) != signal_id]
        digest = safety.compute_signals_digest(remaining)
        with pytest.raises(AppException) as exc:
            await safety.reclassify_and_resolve(
                db, user_id, signal_id,
                profile_snapshot={"profile_version": "v1"},
                active_signals_digest=digest,
                rule_version=RISK_VERSION,
            )
        assert exc.value.status_code == 501
        assert exc.value.code == "reclassify_not_implemented"


@pytest.mark.asyncio
async def test_active_signal_forces_provisional_on_profile(client):
    """Review fix #3: active safety signals force certainty=provisional +
    combined_severity=None on the affected profile entry during recompute."""
    from app.posture import service, safety

    token = await _login_user(client)
    user_id = _user_from_token(token)

    # Create a self-assessment → creates profile with confirmed/moderate
    async with TestSession() as db:
        await service.save_self_assessment(db, user_id, "HN-01", "positive", 0)

    # Record a signal related to HN-01
    async with TestSession() as db:
        await safety.record_safety_signal(
            db, user_id,
            {"signal_type": "pain", "body_region": "head_neck",
             "related_issue_id": "HN-01", "severity_hint": "mild"},
            idempotency_key="k-prov-fix3",
        )

    # Now do another assessment for HN-01 → recompute should force provisional
    async with TestSession() as db:
        await service.save_self_assessment(db, user_id, "HN-01", "negative", 0)

    async with TestSession() as db:
        result = await db.execute(
            select(PostureProfileEntry).where(
                PostureProfileEntry.user_id == _uuid.UUID(user_id),
                PostureProfileEntry.issue_id == "HN-01",
            )
        )
        entry = result.scalar_one()
        assert entry.certainty == "provisional"
        assert entry.combined_severity is None


@pytest.mark.asyncio
async def test_no_related_issue_cautious_signal_downgrades_globally(client):
    """Review fix #4: cautious/restricted signals WITHOUT related_issue_id
    are treated as GLOBAL (downgrade ALL profiles)."""
    token = await _login_user(client)
    user_id = _user_from_token(token)
    await _create_profile_entry(user_id, issue_id="HN-01", risk_tier="normal")
    await _create_profile_entry(user_id, issue_id="ST-04", risk_tier="normal")

    # Signal with no related_issue_id → cautious → should be global
    resp = await client.post(
        "/api/v1/posture/safety-signals",
        json={
            "signal_type": "pain",
            "body_region": "head_neck",
            "related_issue_id": None,
            "severity_hint": "mild",
            "idempotency_key": "k-global-cautious",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["risk_tier"] == "cautious"

    # Both profiles should be downgraded (global scope)
    async with TestSession() as db:
        rows = (
            await db.execute(
                select(PostureProfileEntry).where(
                    PostureProfileEntry.user_id == _uuid.UUID(user_id)
                )
            )
        ).scalars().all()
        for r in rows:
            assert r.risk_tier == "cautious", f"issue {r.issue_id} not downgraded"
            assert r.certainty == "provisional"


def test_body_region_filter_dizziness_lower_limb_not_red_flag():
    """Hardening fix #8: dizziness removed from _NEURO_SIGNAL_TYPES entirely.
    Severe dizziness (any body_region) is now treated as severe non-neuro →
    restricted (RST-severe-symptom), NOT red_flag."""
    result = risk_rules.classify([
        {"signal_type": "dizziness", "severity_hint": "severe", "body_region": "lower_limb"}
    ])
    # Should NOT be red_flag
    assert result.risk_tier != "red_flag"
    # Hardening fix #8: dizziness is no longer a neuro signal type, so severe
    # dizziness is a "severe non-neuro" → restricted (RST-severe-symptom)
    assert result.risk_tier == "restricted"
    assert result.rule_id == "RST-severe-symptom"


def test_body_region_filter_dizziness_head_neck_is_NOT_red_flag():
    """Hardening fix #8: dizziness excluded from _NEURO_SIGNAL_TYPES.
    Even severe dizziness + head_neck does NOT trigger RF-severe-neuro.
    Bier 2018 CPG does NOT mention dizziness/vertigo.
    """
    result = risk_rules.classify([
        {"signal_type": "dizziness", "severity_hint": "severe", "body_region": "head_neck"}
    ])
    assert result.risk_tier != "red_flag"
    # severe non-neuro → restricted
    assert result.risk_tier == "restricted"
    assert result.rule_id == "RST-severe-symptom"


def test_body_region_filter_dizziness_cervical_is_NOT_red_flag():
    """Hardening fix #8: dizziness excluded from _NEURO_SIGNAL_TYPES."""
    result = risk_rules.classify([
        {"signal_type": "dizziness", "severity_hint": "severe", "body_region": "cervical"}
    ])
    assert result.risk_tier != "red_flag"
    assert result.risk_tier == "restricted"


def test_body_region_filter_acute_trauma_is_restricted_any_region():
    """P2-1: acute_trauma is a uniform restricted product-policy gate for ANY
    body_region (the spine/trunk filter was specific to the removed red_flag rule)."""
    for region in ("head_neck", "cervical", "upper_back", "lower_back", "thoracic", "lower_limb"):
        result = risk_rules.classify([
            {"signal_type": "acute_trauma", "severity_hint": None, "body_region": region}
        ])
        assert result.risk_tier == "restricted", f"region={region!r} should be restricted"
        assert result.rule_id == "RST-acute-trauma"
        assert result.risk_tier != "red_flag"


def test_body_region_filter_acute_trauma_extremity_is_restricted():
    """P2-1: extremity acute_trauma is also restricted (uniform product-policy gate)."""
    result = risk_rules.classify([
        {"signal_type": "acute_trauma", "severity_hint": None, "body_region": "lower_limb"}
    ])
    assert result.risk_tier != "red_flag"
    assert result.risk_tier == "restricted"
    assert result.rule_id == "RST-acute-trauma"
