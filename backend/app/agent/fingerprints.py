"""Keyed canonical fingerprints for Agent audit/context/argument values.

Every Agent fingerprint is a keyed ``HMAC-SHA256`` over a canonical
serialization, using a dedicated server-only key (``AGENT_AUDIT_HMAC_KEY``) and
a stored key version (``AGENT_AUDIT_HMAC_KEY_VERSION``). Plain hashes are
forbidden for low-entropy health values (weights, tiers, small enums) because
they are trivially enumerable; this module therefore exposes ONLY the keyed
path. When no key is configured the capability fails closed (spec Entry And
Context Contracts, Provider And Orchestrator Contract, Acceptance #15).

The canonical serialization contains no raw user message or free text: callers
pass only structured, minimized fields.
"""
from __future__ import annotations

import hmac
import json
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

    Order-independent (``sort_keys``), compact, and UTF-8 encoded. Non-JSON
    scalars fall back to ``str`` so callers cannot smuggle arbitrary object
    identity into the digest. Free text must never be placed in ``payload``.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def compute_fingerprint(
    payload: Mapping[str, Any],
    *,
    key: Optional[str] = None,
    key_version: Optional[str] = None,
) -> AgentFingerprint:
    """Compute a keyed HMAC-SHA256 fingerprint over ``payload``.

    When ``key``/``key_version`` are omitted they are read from server-only
    settings. A missing or blank key fails closed with
    ``agent_fingerprint_key_missing`` - the low-entropy value is never reduced
    to a plain, enumerable hash.
    """
    if key is None:
        key = settings.AGENT_AUDIT_HMAC_KEY
        key_version = settings.AGENT_AUDIT_HMAC_KEY_VERSION
    if not key or not key.strip():
        raise AgentError(ResultCode.FINGERPRINT_KEY_MISSING)

    message = canonical_serialize(payload)
    digest = hmac.new(key.encode("utf-8"), message, sha256).hexdigest()
    return AgentFingerprint(value=digest, key_version=key_version or "")


__all__ = ["AgentFingerprint", "canonical_serialize", "compute_fingerprint"]
