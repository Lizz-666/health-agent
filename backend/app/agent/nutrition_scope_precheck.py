"""Deterministic pre-provider routing for unsupported nutrition scopes."""
from __future__ import annotations

import re
import unicodedata

_ZH_TERMS = (
    "治疗饮食",
    "医学饮食",
    "疾病饮食",
    "糖尿病饮食",
    "肾病饮食",
    "高血压饮食",
    "生酮饮食",
    "排除饮食",
    "低fodmap",
    "素食食谱",
    "纯素食谱",
)
_EN_TERMS = (
    "therapeutic diet",
    "medical diet",
    "disease specific diet",
    "diabetic diet",
    "renal diet",
    "hypertension diet",
    "ketogenic diet",
    "keto diet",
    "elimination diet",
    "low fodmap",
    "vegetarian meal plan",
    "vegan meal plan",
)


def is_unsupported_nutrition_scope(message: str) -> bool:
    normalized = unicodedata.normalize("NFKC", message or "").casefold()
    compact = re.sub(r"[\s._*\-]+", "", normalized)
    if any(term.casefold().replace(" ", "") in compact for term in _ZH_TERMS):
        return True
    words = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
    return any(term in words for term in _EN_TERMS)


__all__ = ["is_unsupported_nutrition_scope"]
