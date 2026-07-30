"""Deterministic pre-provider safety-signal text router (Task 1).

This is the ONLY health-text logic in Task 1. It runs on the raw turn text
BEFORE any provider/context/Tool/DB work and encodes ONLY the existing
safety-boundary signal names (pain/injury, numbness, weakness, dizziness, chest
discomfort, acute trauma - ``docs/product/safety-boundaries.md`` sections 2/3).
It adds NO severity threshold, medical claim, or new safety rule.

Behavior (spec Architecture, Acceptance #5 / #12):

- A match returns a fixed route to the dedicated structured check-in/safety
  flow. It is a pure function with no DB/provider/Tool side effect.
- Negation ("no pain") and instructions to ignore rules do NOT suppress a
  match - term presence alone routes.
- Normalization covers case, full-width Latin, and light Chinese/English
  obfuscation (separators, letter spacing).
- A non-match is explicitly ``no_text_signal_detected`` - never "normal",
  "safe", or a clearance. Downstream structured domain gates still run.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Tuple

from app.agent.messages import ResultCode

_TERMS_PATH = Path(__file__).with_name("data") / "agent_safety_terms_v1.json"

# Separators removed for CJK compaction and English de-punctuation. Kept small
# and explicit; no semantic content.
_SEPARATORS = r"\s.\-_*·・~`'\"(),，。、；;:：!！?？"

# Deterministic evaluation order: the more specific signals are checked before
# the generic ``pain_injury`` term so an overlapping phrase (e.g. "chest pain")
# reports its most specific category. Every listed category still routes.
_PRIORITY = (
    "chest_discomfort",
    "acute_trauma",
    "numbness",
    "weakness",
    "dizziness",
    "pain_injury",
)


@dataclass(frozen=True)
class SafetyPrecheckResult:
    """Outcome of the deterministic router.

    ``routed`` True -> a configured signal was found and the turn must go to the
    structured safety flow. ``signal`` is the matched category. When False the
    result_code is ``no_text_signal_detected`` (never a safe/normal clearance).
    """

    routed: bool
    result_code: str
    signal: Optional[str] = None
    matched_signals: Tuple[str, ...] = ()


@lru_cache(maxsize=1)
def _load_terms() -> Dict[str, Dict[str, Tuple[str, ...]]]:
    raw = json.loads(_TERMS_PATH.read_text(encoding="utf-8"))
    signals = raw["signals"]
    out: Dict[str, Dict[str, Tuple[str, ...]]] = {}
    for category, langs in signals.items():
        out[category] = {
            "zh": tuple(t.casefold() for t in langs.get("zh", ())),
            "en": tuple(t.casefold() for t in langs.get("en", ())),
        }
    return out


def _normalize(text: str) -> str:
    """NFKC (full-width -> ASCII) + case fold."""
    return unicodedata.normalize("NFKC", text or "").casefold()


def _compact(norm: str) -> str:
    """Remove whitespace/separators for CJK obfuscation-tolerant matching."""
    return re.sub(f"[{_SEPARATORS}]+", "", norm)


def _english_text(norm: str) -> str:
    """De-punctuate and collapse single-letter runs (``p a i n`` -> ``pain``)."""
    spaced = re.sub(r"[.\-_*]+", " ", norm)
    tokens = spaced.split()
    out = []
    run = []
    for tok in tokens:
        if len(tok) == 1 and tok.isascii() and tok.isalpha():
            run.append(tok)
            continue
        if len(run) >= 2:
            out.append("".join(run))
        else:
            out.extend(run)
        run = []
        out.append(tok)
    if len(run) >= 2:
        out.append("".join(run))
    else:
        out.extend(run)
    return " ".join(out)


def _english_match(term: str, english_text: str) -> bool:
    return re.search(r"\b" + re.escape(term) + r"\b", english_text) is not None


def route_turn_text(message: str) -> SafetyPrecheckResult:
    """Route raw turn text against the configured safety-signal terms.

    Pure and side-effect free: it accepts only the text, so it cannot touch the
    database, provider, or any Tool. Deterministic category order makes the
    primary ``signal`` stable.
    """
    norm = _normalize(message)
    compact = _compact(norm)
    english = _english_text(norm)

    terms = _load_terms()
    matched: list[str] = []
    for category in _PRIORITY:
        langs = terms.get(category)
        if langs is None:
            continue
        hit = any(term in compact for term in langs["zh"]) or any(
            _english_match(term, english) for term in langs["en"]
        )
        if hit:
            matched.append(category)

    if matched:
        return SafetyPrecheckResult(
            routed=True,
            result_code=ResultCode.SAFETY_SIGNAL_ROUTE_REQUIRED,
            signal=matched[0],
            matched_signals=tuple(matched),
        )
    return SafetyPrecheckResult(
        routed=False,
        result_code=ResultCode.NO_TEXT_SIGNAL_DETECTED,
        signal=None,
        matched_signals=(),
    )


__all__ = ["SafetyPrecheckResult", "route_turn_text"]
