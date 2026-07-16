"""Versioned, deterministic risk classification for posture safety signals.

Spec references: §12.2 (safety signal closed loop), §12.5 (safety case matrix),
§12.6 (risk rule source & license).

Design constraints enforced here:
- PURE function ``classify`` — no LLM, no prompt, no DB. It only consumes the
  structured signal fields a user reported.
- Phase 1 (RISK_VERSION "2026-07-16-v4"): NO rule produces ``red_flag``
  automatically. The acute-trauma and severe-neuro combinations that
  previously triggered ``red_flag`` are downgraded to ``restricted``
  product-policy gates. PubMed verification: Bier 2018 (Physical Therapy
  98(3):162-173) and Sizer 2007 (Pain Practice 7(1):53-71) emphasise combined
  clinical assessment and do NOT support a single-signal *unconditional*
  red_flag, so the single-signal auto red_flag was removed (no rule may assert
  clinical literature it cannot back). The ``red_flag`` tier enum value is
  retained for future use when more complete structured input exists; the
  startup guard therefore passes vacuously (there are no red_flag rules to
  check). A severe posture assessment alone still never produces an elevated
  risk tier (spec §12.2 红旗推断禁止规则).
- Classification combines MULTIPLE signals, not a single ``severity_hint``.

Provenance — TWO-TIER discriminable union (spec §12.6):
- ``clinical-source``: reserved for future ``red_flag`` rules backed by
  verified clinical literature (DOI/ISBN/URL). None ship in Phase 1.
- ``product-policy``: restricted rules that are conservative PRODUCT
  qualification gates — NOT clinical claims. They carry a ``policy_id`` /
  ``policy_version`` / ``rationale`` / ``owner`` and never a DOI/ISBN/URL.
- Product-policy rules may be restricted/cautious but NEVER red_flag.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Union


# Bumped only when a rule's behaviour changes. Spec example: "2026-07-11-v1".
# "2026-07-16-v4": RF-acute-trauma / RF-severe-neuro downgraded from
# clinical-source red_flag to product-policy restricted (no DOI).
RISK_VERSION = "2026-07-16-v4"

# Risk levels (spec §12.2).
NORMAL = "normal"
CAUTIOUS = "cautious"
RESTRICTED = "restricted"
RED_FLAG = "red_flag"

# Strict ordering used by the recovery rule: a reclassification may resolve a
# restricted/red_flag signal only if the new tier is *strictly lower*.
_TIER_ORDER = {NORMAL: 0, CAUTIOUS: 1, RESTRICTED: 2, RED_FLAG: 3}


def is_lower_risk(candidate: str, than: str) -> bool:
    return _TIER_ORDER[candidate] < _TIER_ORDER[than]


# Structured neuro symptom signal types that Phase 1 product policy restricts
# when severe in an in-scope body region. Phase 1 does not auto-create red_flag.
# Phase 1 product-policy scope includes only numbness and weakness here.
# Dizziness remains a valid structured signal but is not an input to this
# particular restricted rule; no clinical red-flag inference is made.
_NEURO_SIGNAL_TYPES = frozenset({"numbness", "weakness"})

# Valid structured signal types / severity hints (mirrors spec §12.2 input).
SIGNAL_TYPES = frozenset(
    {"pain", "numbness", "weakness", "dizziness", "acute_trauma", "other"}
)
SEVERITY_HINTS = frozenset({"mild", "moderate", "severe"})


# ---------------------------------------------------------------------------
# Provenance — two-tier discriminable union (spec §12.6)
# ---------------------------------------------------------------------------

CLINICAL_SOURCE = "clinical-source"
PRODUCT_POLICY = "product-policy"
_VALID_EVIDENCE_LEVELS = frozenset({"L1", "L2", "L3", "L4", "L5"})

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


def _is_valid_isbn(value: str) -> bool:
    core = value.replace("-", "").replace(" ", "")
    if len(core) == 10 and re.fullmatch(r"\d{9}[\dXx]", core):
        return True
    if len(core) == 13 and core.isdigit() and core.startswith(("978", "979")):
        return True
    return False


def _is_valid_clinical_identifier(value: str) -> bool:
    v = (value or "").strip()
    return bool(_DOI_RE.match(v) or _is_valid_isbn(v) or _URL_RE.match(v))


@dataclass(frozen=True)
class ClinicalSource:
    """Tier-1 provenance — a red_flag rule backed by verified clinical literature.

    ``source_identifier`` MUST be a real DOI / ISBN / URL, independently
    verified before this object is constructed. Fabricating an identifier here
    is a spec §12.6 violation and the startup guard will refuse to load it.
    """

    source_identifier: str
    evidence_level: str
    version: str
    reviewed_at: str
    scope: str
    license: str
    provenance_type: str = CLINICAL_SOURCE


@dataclass(frozen=True)
class ProductPolicy:
    """Tier-2 provenance — a conservative product qualification gate.

    NOT a clinical claim and therefore never carries a DOI/ISBN/URL. These
    gates pause automatic normal recommendations pending structured
    assessment; they must never produce a red_flag tier.
    """

    policy_id: str
    policy_version: str
    rationale: str
    owner: str
    reviewed_at: str
    provenance_type: str = PRODUCT_POLICY


Provenance = Union[ClinicalSource, ProductPolicy]


@dataclass(frozen=True)
class RiskRule:
    """A single deterministic classification rule."""

    rule_id: str
    risk_tier: str
    reason: str
    provenance: Optional[Provenance] = None


@dataclass(frozen=True)
class RiskClassification:
    """Result of classifying a set of structured signals."""

    risk_tier: str
    risk_version: str
    rule_id: str
    reason: str
    sources: List[Provenance] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tier-1 clinical sources — NONE ship in Phase 1 (RISK_VERSION 2026-07-16-v4).
#
# The acute-trauma and severe-neuro rules were previously clinical-source
# ``red_flag`` rules backed by these verified identifiers:
#   * Sizer PS Jr et al., Pain Practice 7(1):53-71, 2007  (10.1111/j.1533-2500.2007.00112.x)
#   * Bier JD et al., Physical Therapy 98(3):162-173, 2018 (10.1093/ptj/pzx118)
# PubMed review (2026-07-16) confirmed neither source supports a *single-signal
# unconditional* red_flag: Bier 2018 requires combined clinical assessment,
# Sizer 2007 likewise. They are therefore downgraded to conservative
# product-policy ``restricted`` gates below (NO DOI), and the clinical-source
# identifiers are intentionally NOT carried by the product-policy provenance.
# The red_flag tier enum remains available for future rules that CAN meet the
# clinical-source startup guard.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Tier-2 product-policy gates — conservative thresholds, NOT clinical claims.
# ---------------------------------------------------------------------------

_RST_ACUTE_TRAUMA_SOURCE = ProductPolicy(
    policy_id="PP-2026-003",
    policy_version="2026-07-16-v1",
    rationale="急性创伤信号需要专业评估，暂停普通自动建议",
    owner="posture-team",
    reviewed_at="2026-07-16",
)
_RST_SEVERE_NEURO_SOURCE = ProductPolicy(
    policy_id="PP-2026-004",
    policy_version="2026-07-16-v1",
    rationale="成人严重麻木/无力（结构化信号）触发保守产品阈值，暂停普通自动建议并引导专业评估",
    owner="posture-team",
    reviewed_at="2026-07-16",
)
_RST_MULTIPLE_MODERATE_SOURCE = ProductPolicy(
    policy_id="PP-2026-001",
    policy_version="2026-07-11-v1",
    rationale="多个中度信号叠加提示风险升高，暂停普通自动建议，待结构化评估后再行推荐",
    owner="posture-team",
    reviewed_at="2026-07-11",
)
_RST_SEVERE_SYMPTOM_SOURCE = ProductPolicy(
    policy_id="PP-2026-002",
    policy_version="2026-07-11-v1",
    rationale="单个严重非神经症状触发保守阈值，暂停普通自动建议，仅提供教育与体态辅助",
    owner="posture-team",
    reviewed_at="2026-07-11",
)


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

_RULES: dict[str, RiskRule] = {
    "RST-acute-trauma": RiskRule(
        rule_id="RST-acute-trauma",
        risk_tier=RESTRICTED,
        reason="结构化急性创伤信号触发受限，引导专业评估（product-policy，非红旗）",
        provenance=_RST_ACUTE_TRAUMA_SOURCE,
    ),
    "RST-severe-neuro": RiskRule(
        rule_id="RST-severe-neuro",
        risk_tier=RESTRICTED,
        reason="严重麻木/无力（结构化信号，限头颈与上背区域）触发受限（产品策略，非红旗）",
        provenance=_RST_SEVERE_NEURO_SOURCE,
    ),
    "RST-multiple-moderate": RiskRule(
        rule_id="RST-multiple-moderate",
        risk_tier=RESTRICTED,
        reason="多个中度信号叠加触发受限，仅提供教育与体态辅助",
        provenance=_RST_MULTIPLE_MODERATE_SOURCE,
    ),
    "RST-severe-symptom": RiskRule(
        rule_id="RST-severe-symptom",
        risk_tier=RESTRICTED,
        reason="单个严重非神经症状触发受限",
        provenance=_RST_SEVERE_SYMPTOM_SOURCE,
    ),
    # cautious / normal have no clinical claim and no product gate → no provenance.
    "C-any-signal": RiskRule(
        rule_id="C-any-signal",
        risk_tier=CAUTIOUS,
        reason="存在安全信号但未达到受限/红旗阈值，保守建议",
        provenance=None,
    ),
    "N-baseline": RiskRule(
        rule_id="N-baseline",
        risk_tier=NORMAL,
        reason="无结构化安全信号，基线正常",
        provenance=None,
    ),
}


# ---------------------------------------------------------------------------
# Startup guard (spec §12.6) — fail loud at import if provenance is wrong.
# ---------------------------------------------------------------------------


def _validate_registry() -> None:
    """Enforce the two-tier provenance contract before serving any request.

    - Every red_flag rule MUST carry a verified ``clinical-source`` provenance
      with a valid DOI/ISBN/URL, evidence level and complete metadata.
    - A ``product-policy`` rule MUST NOT be red_flag (product gates are never
      clinical red flags).
    - A ``clinical-source`` provenance MUST NOT decorate a non-red_flag rule
      (only red_flag rules may assert clinical literature).
    """
    for rule in _RULES.values():
        prov = rule.provenance
        if rule.risk_tier == RED_FLAG:
            if not isinstance(prov, ClinicalSource):
                raise RuntimeError(
                    f"red_flag 规则 {rule.rule_id} 缺少临床来源（clinical-source）"
                    f"provenance，拒绝加载（spec §12.6）"
                )
            if not _is_valid_clinical_identifier(prov.source_identifier):
                raise RuntimeError(
                    f"临床来源 {rule.rule_id} 的 source_identifier 非合法 DOI/ISBN/URL："
                    f"{prov.source_identifier!r}（禁止虚构标识符）"
                )
            if prov.evidence_level not in _VALID_EVIDENCE_LEVELS:
                raise RuntimeError(
                    f"临床来源 {rule.rule_id} 的 evidence_level 非法：{prov.evidence_level!r}"
                )
            for attr in (prov.version, prov.reviewed_at, prov.scope, prov.license):
                if not (attr and attr.strip()):
                    raise RuntimeError(
                        f"临床来源 {rule.rule_id} 元数据不完整（version/reviewed_at/scope/license）"
                    )
        else:
            if isinstance(prov, ClinicalSource):
                raise RuntimeError(
                    f"规则 {rule.rule_id} 非 red_flag 却携带 clinical-source provenance"
                )
            if isinstance(prov, ProductPolicy) and rule.risk_tier == RED_FLAG:
                raise RuntimeError(
                    f"product-policy 规则 {rule.rule_id} 不得为 red_flag"
                )


_validate_registry()


def get_rule(rule_id: str) -> Optional[RiskRule]:
    return _RULES.get(rule_id)


def all_rules() -> List[RiskRule]:
    return list(_RULES.values())


# ---------------------------------------------------------------------------
# Pure classification
# ---------------------------------------------------------------------------


def _signal_type(sig: dict) -> str:
    return (sig.get("signal_type") or "").strip()


def _severity(sig: dict) -> Optional[str]:
    v = sig.get("severity_hint")
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def classify(signals: List[dict]) -> RiskClassification:
    """Classify a list of structured signals into a risk tier.

    Pure and deterministic. ``signals`` is a list of dicts with at least
    ``signal_type`` and optionally ``severity_hint`` / ``body_region``.

    Phase 1 (RISK_VERSION "2026-07-16-v4"): NO rule produces ``red_flag``.
    acute_trauma and severe-neuro are downgraded to ``restricted`` product-policy
    gates.

    Ordering (most specific wins, evaluated over the FULL signal set):
      1. restricted (RST-acute-trauma) — any ``acute_trauma`` signal
      2. restricted (RST-severe-neuro) — severe (numbness|weakness) with
                     body_region in head_neck/cervical/upper_back
      3. restricted (RST-multiple-moderate) — >= 2 moderate signals
      4. restricted (RST-severe-symptom) — a severe non-neuro symptom
      5. cautious  — at least one signal present
      6. normal    — no signals

    Hardening fix #8:
      - dizziness is outside this product-policy rule's input scope
      - severe neuro only triggers for head_neck/cervical/upper_back
    """
    if not signals:
        rule = _RULES["N-baseline"]
        return _result(rule)

    types = [_signal_type(s) for s in signals]
    severities = [_severity(s) for s in signals]
    body_regions = [(s.get("body_region") or "") for s in signals]

    # 1. Restricted — acute trauma (product-policy gate, ANY body_region).
    if any(t == "acute_trauma" for t in types):
        return _result(_RULES["RST-acute-trauma"])

    # 2. Restricted — severe neuro (numbness|weakness) in cervical region.
    _NEURO_BODY_REGIONS = frozenset({"head_neck", "cervical", "upper_back"})
    if any(
        t in _NEURO_SIGNAL_TYPES and sev == "severe"
        and br in _NEURO_BODY_REGIONS
        for t, sev, br in zip(types, severities, body_regions)
    ):
        return _result(_RULES["RST-severe-neuro"])

    # 3. Restricted — combinatorial: multiple moderate, or a severe non-neuro.
    moderate_count = sum(1 for sev in severities if sev == "moderate")
    has_severe_non_neuro = any(
        sev == "severe" and t not in _NEURO_SIGNAL_TYPES
        for t, sev in zip(types, severities)
    )
    if moderate_count >= 2:
        return _result(_RULES["RST-multiple-moderate"])
    if has_severe_non_neuro:
        return _result(_RULES["RST-severe-symptom"])

    # 4. Cautious — a signal exists but does not reach restricted/red_flag.
    return _result(_RULES["C-any-signal"])


def _result(rule: RiskRule) -> RiskClassification:
    sources: List[Provenance] = [rule.provenance] if rule.provenance else []
    return RiskClassification(
        risk_tier=rule.risk_tier,
        risk_version=RISK_VERSION,
        rule_id=rule.rule_id,
        reason=rule.reason,
        sources=sources,
    )
