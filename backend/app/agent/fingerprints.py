"""Keyed canonical fingerprints for Agent audit/context/argument values.

Every Agent fingerprint is a keyed ``HMAC-SHA256`` over a canonical
serialization, using a dedicated server-only key (``AGENT_AUDIT_HMAC_KEY``) and
a stored key version (``AGENT_AUDIT_HMAC_KEY_VERSION``). Plain hashes are
forbidden for low-entropy health values (weights, tiers, small enums) because
they are trivially enumerable; this module therefore exposes ONLY the keyed
path. When no key (or no key version) is configured the capability fails closed
(spec Entry And Context Contracts, Provider And Orchestrator Contract,
Acceptance #15).

The canonical serialization accepts ONLY JSON-compatible structured values: no
``default=str`` coercion (which would let arbitrary object identity into the
digest), no ``NaN``/``Infinity`` (non-portable / non-deterministic), and no free
text. Callers pass structured, minimized fields only.
"""
from __future__ import annotations

import hmac
import json
import math
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Optional

from app.agent.messages import AgentError, ResultCode
from app.core.config import settings

@dataclass(frozen=True)
class AgentFingerprint:
    """A keyed fingerprint plus the key version used to produce it."""

    value: str
    key_version: str


def canonical_serialize(payload: Mapping[str, Any]) -> bytes:
    """Deterministically serialize a structured payload.

    Order-independent (``sort_keys``), compact, and UTF-8 encoded. Only
    JSON-compatible structured values are accepted: non-serializable types and
    non-finite floats (``NaN``/``Infinity``) raise ``AgentError`` (fail closed)
    instead of being coerced into the digest. Free text must never be placed in
    ``payload``.
    """
    try:
        normalized = _normalize_json_value(payload)
        return json.dumps(
            normalized,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AgentError(ResultCode.FINGERPRINT_INVALID_VALUE) from exc


def _normalize_json_value(value: Any) -> Any:
    """Return JSON-native data while rejecting ambiguous coercions."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float")
        return value
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("mapping keys must be strings")
        return {key: _normalize_json_value(item) for key, item in value.items()}
    raise TypeError("value is not JSON-native")


def compute_fingerprint(
    payload: Mapping[str, Any],
    *,
    key: Optional[str] = None,
    key_version: Optional[str] = None,
) -> AgentFingerprint:
    """Compute a keyed HMAC-SHA256 fingerprint over ``payload``.

    When ``key``/``key_version`` are omitted they are read from server-only
    settings. A missing/blank key OR a missing/blank key version fails closed
    with ``agent_fingerprint_key_missing`` - the low-entropy value is never
    reduced to a plain, enumerable hash.
    """
    if key is None:
        key = settings.AGENT_AUDIT_HMAC_KEY
        key_version = settings.AGENT_AUDIT_HMAC_KEY_VERSION
    if not key or not key.strip():
        raise AgentError(ResultCode.FINGERPRINT_KEY_MISSING)
    if not key_version or not str(key_version).strip():
        raise AgentError(ResultCode.FINGERPRINT_KEY_MISSING)

    message = canonical_serialize(payload)
    digest = hmac.new(key.encode("utf-8"), message, sha256).hexdigest()
    return AgentFingerprint(value=digest, key_version=str(key_version))


__all__ = ["AgentFingerprint", "canonical_serialize", "compute_fingerprint"]
