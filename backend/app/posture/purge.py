"""Posture health-data purge service (spec §6.6 / §6.7).

Reuses the ``purge_operations`` and ``posture_purge_tombstones`` tables created
by migration 0002 (no new migration). Implements the 7-step ordered state
machine with an injectable object-store adapter (``ObjectStore``) and an
in-memory ``FakeObjectStore`` for tests — no real OSS integration.

Key guarantees enforced here:
  * ``photo_keys`` are copied into ``purge_operations.encrypted_object_keys``
    (step 1) and survive there until OSS deletion is confirmed. The blob is
    real AES-256-GCM ciphertext (nonce + ciphertext+tag); plaintext keys are
    NEVER persisted or logged.
  * ``encrypted_object_keys`` is cleared (and committed) AFTER all OSS objects
    are confirmed deleted (success or 404) and BEFORE any DB health-data row is
    deleted (step 4 strictly precedes step 5).
  * A completed tombstone is written only on full success; it contains only the
    unlinkable fields (receipt_id/deleted_at/purge_reason/policy_version/
    object_delete_status). The tombstone INSERT and the purge_operations
    linkable-field scrub happen in ONE transaction (atomic: all-or-nothing).
  * On OSS failure the operation stays ``failed_oss_retry`` (keys + targets
    retained for retry) and NO tombstone is written.
  * On DB failure the operation stays ``failed_db_retry`` (keys already
    cleared; targets retained) and NO tombstone is written.
  * On decrypt failure (wrong/corrupted key during retry) the operation becomes
    ``failed_decrypt``: data is RETAINED, no tombstone, no deletion.
  * After completion, ``purge_operations`` keeps its row (方案 B, spec §6.7.3)
    but all linkable fields (user_id/target_event_ids/target_signal_ids/
    encrypted_object_keys) are scrubbed to null.
  * Re-running a completed/empty purge is an idempotent no-op (no duplicate
    tombstone, no error).
  * Purge scope (spec §6.6) differentiates what is deleted:
    ``account_deletion`` (full cascade), ``consent_withdrawn`` (photo events +
    their OSS/idempotency only), ``retention_expired`` (only expired photo
    events + their OSS).
  * A write-freeze guard (``is_user_write_frozen``) is exported for Task 2
    integration: writes are frozen while a non-terminal purge_operation exists.
"""

import json
import logging
import os
import uuid as _uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException
from app.agent.models import (
    AgentActionProposal,
    AgentCloudConsent,
    AgentRun,
    AgentToolEvent,
)
from app.posture.models import (
    IdempotencyRecord,
    PostureAssessmentEvent,
    PostureProfileEntry,
    PosturePurgeTombstone,
    PostureSafetySignal,
    PostureUserGoal,
    PurgeOperation,
)
from app.posture.user_lock import acquire_user_transaction_lock

logger = logging.getLogger("app.posture.purge")

POLICY_VERSION = "retention-policy-2026-07-11"
_TOMBSTONE_COMPLETED_STATUSES = (
    "oss_deleted",
    "oss_not_applicable",
    "oss_deleted_or_not_found",
)

# Default retry budgets (spec §6.7.2). A single max_attempts ceiling is stored
# on the purge_operation; OSS and DB failures share the row's retry window.
DEFAULT_MAX_ATTEMPTS = 10
DEFAULT_RETRY_WINDOW_DAYS = 7

# AEAD configuration (AES-256-GCM).
_AES_KEY_BYTES = 32  # AES-256
_AES_KEY_HEX_LEN = _AES_KEY_BYTES * 2  # 64 hex chars
_NONCE_BYTES = 12  # 96-bit GCM nonce
KEY_VERSION = "v1"

# Retry backoff (spec §6.7.2 / Task-9 FIX 4): base 5 min, factor 2, cap 24h.
_RETRY_BASE_DELAY = timedelta(minutes=5)
_RETRY_MAX_DELAY = timedelta(hours=24)

# Hardening fix #4: recoverable lease duration for worker claims.
# If a worker claims a job but crashes (doesn't complete within this window),
# the job becomes re-claimable (next_retry_at < now again).
LEASE_DURATION = timedelta(minutes=5)

# Purge_operation lifecycle status sets.
# Only "completed" and explicit auditable "cancelled" release the write freeze.
# failed_permanent and failed_decrypt remain frozen (require manual intervention).
TERMINAL_STATUSES = frozenset({"completed", "cancelled"})

# P1-2: lease statuses claimed by a worker while it actively processes a retry.
# While claimed the row is NOT re-claimable until its lease (next_retry_at)
# expires. They are non-terminal → the write freeze is maintained.
RETRYING_OSS = "retrying_oss"
RETRYING_DB = "retrying_db"
RETRYING_STATUSES = frozenset({RETRYING_OSS, RETRYING_DB})
OSS_RESUME_STATUSES = frozenset(
    {"freezing", "oss_deleting", "failed_oss_retry", RETRYING_OSS}
)
DB_RESUME_STATUSES = frozenset({"db_deleting", "failed_db_retry", RETRYING_DB})

# Due/reclaimable statuses for the retry worker. Includes both the failed_*_retry
# states (normally due via exponential backoff) and the retrying_* lease states
# (reclaimable once next_retry_at <= now, i.e. the claiming worker crashed).
RETRYABLE_STATUSES = OSS_RESUME_STATUSES | DB_RESUME_STATUSES


class PurgeConfigError(RuntimeError):
    """Raised when purge cannot run due to misconfiguration (e.g. missing or
    invalid ``PURGE_ENCRYPTION_KEY``). Raised BEFORE any deletion so no data is
    touched when the purge is not properly configured."""


# --------------------------------------------------------------------------- #
# Object-store adapter
# --------------------------------------------------------------------------- #


class ObjectStoreError(Exception):
    """Raised when an OSS object could not be verified as deleted.

    A delete is considered successful only when the store returns success OR
    confirms the object no longer exists (404). Any other outcome raises.
    """


class ObjectStore(ABC):
    """Adapter interface for deleting OSS objects (spec §6.7 step 3)."""

    @abstractmethod
    async def delete_object(self, object_key: str) -> None:
        """Delete one object. Raise ``ObjectStoreError`` on non-404 failure.

        A successful response and a not-found (404) response are BOTH treated
        as a verified deletion and must therefore NOT raise.
        """
        raise NotImplementedError


class FakeObjectStore(ObjectStore):
    """In-memory object store for tests.

    Keys registered via ``add_existing`` simulate objects that exist (delete
    returns success). Any key NOT registered and NOT marked as a failure
    simulates an already-absent object (delete returns 404) and is accepted.
    Keys in ``_failures`` simulate a real deletion error.
    """

    def __init__(self) -> None:
        self._existing: set[str] = set()
        self._failures: set[str] = set()
        self._deleted: list[str] = []

    def add_existing(self, object_key: str) -> None:
        self._existing.add(object_key)

    def mark_failure(self, object_key: str) -> None:
        self._failures.add(object_key)

    @property
    def deleted_keys(self) -> List[str]:
        return list(self._deleted)

    async def delete_object(self, object_key: str) -> None:
        if object_key in self._failures:
            raise ObjectStoreError(f"simulated delete failure: {object_key}")
        # success (existed) or 404 (already absent) — both verified deletions
        self._deleted.append(object_key)


# --------------------------------------------------------------------------- #
# Purge scope (spec §6.6)
# --------------------------------------------------------------------------- #


class PurgeScope(str, Enum):
    """What a purge is allowed to delete (spec §6.6 purge_reason semantics)."""

    ACCOUNT_DELETION = "account_deletion"
    CONSENT_WITHDRAWN = "consent_withdrawn"
    RETENTION_EXPIRED = "retention_expired"


_TRIGGER_TO_SCOPE = {
    "user_delete": PurgeScope.ACCOUNT_DELETION,
    "account_deletion": PurgeScope.ACCOUNT_DELETION,
    "consent_withdrawn": PurgeScope.CONSENT_WITHDRAWN,
    "retention_expired": PurgeScope.RETENTION_EXPIRED,
}


def _scope_from_trigger(trigger) -> PurgeScope:
    if isinstance(trigger, PurgeScope):
        return trigger
    scope = _TRIGGER_TO_SCOPE.get(str(trigger))
    if scope is None:
        raise ValueError(f"unknown purge trigger: {trigger}")
    return scope


# --------------------------------------------------------------------------- #
# AEAD object-key encryption (spec §6.7 — application-layer encryption)
# --------------------------------------------------------------------------- #


def _load_encryption_key(key_hex: Optional[str]) -> bytes:
    """Validate and decode the configured AES-256 key.

    Raises ``PurgeConfigError`` (never proceeds) when the key is missing or
    malformed. Returns the raw 32-byte key.
    """
    if not key_hex:
        raise PurgeConfigError(
            "PURGE_ENCRYPTION_KEY is empty; purge is disabled until a valid "
            "AES-256 key (64 hex chars) is configured"
        )
    try:
        key = bytes.fromhex(key_hex)
    except (ValueError, TypeError):
        raise PurgeConfigError("PURGE_ENCRYPTION_KEY is not valid hexadecimal")
    if len(key) != _AES_KEY_BYTES:
        raise PurgeConfigError(
            f"PURGE_ENCRYPTION_KEY must be {_AES_KEY_BYTES} bytes "
            f"({_AES_KEY_HEX_LEN} hex chars), got {len(key)} bytes"
        )
    return key


def _load_keyring() -> dict:
    """Load the versioned key ring from settings.PURGE_ENCRYPTION_KEYS.

    Returns a dict mapping version -> hex key string. Returns empty dict if
    not configured (falls back to single-key mode via PURGE_ENCRYPTION_KEY).
    """
    raw = settings.PURGE_ENCRYPTION_KEYS
    if not raw or not raw.strip():
        return {}
    try:
        keyring = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise PurgeConfigError("PURGE_ENCRYPTION_KEYS is not valid JSON")
    if not isinstance(keyring, dict):
        raise PurgeConfigError("PURGE_ENCRYPTION_KEYS must be a JSON object")
    return keyring


def _validate_hex_key(raw_key: object, label: str) -> None:
    """Validate that ``raw_key`` is a 64-hex-char AES-256 key.

    Raises ``PurgeConfigError`` (never proceeds) on any violation. Used for
    both the legacy single key and each entry in the versioned keyring.
    """
    if not isinstance(raw_key, str) or not raw_key:
        raise PurgeConfigError(f"{label} must be a non-empty hex string")
    try:
        key = bytes.fromhex(raw_key)
    except (ValueError, TypeError):
        raise PurgeConfigError(f"{label} is not valid hexadecimal")
    if len(key) != _AES_KEY_BYTES:
        raise PurgeConfigError(
            f"{label} must be {_AES_KEY_BYTES} bytes ({_AES_KEY_HEX_LEN} hex chars)"
        )


def _validate_keyring(keyring: dict) -> None:
    """Validate the structure of the versioned key ring (fail closed).

    Each version must be a non-empty string; each key must be a valid
    64-hex-char AES-256 key. Raises ``PurgeConfigError`` on any violation.
    """
    for ver, raw_key in keyring.items():
        if not isinstance(ver, str) or not ver:
            raise PurgeConfigError(
                "PURGE_ENCRYPTION_KEYS version keys must be non-empty strings"
            )
        _validate_hex_key(raw_key, f"PURGE_ENCRYPTION_KEYS['{ver}']")


def _resolve_encryption_key(
    key_hex: Optional[str] = None,
    key_version: Optional[str] = None,
) -> tuple[str, str]:
    """Resolve ``(key_hex, key_version)`` for encryption or decryption.

    Production path self-resolves from settings (no caller-supplied key):
      * Explicit ``key_hex`` (legacy/test override) → returned together with
        the supplied or default ``KEY_VERSION``.
      * No keyring configured → legacy single-key mode:
        ``(settings.PURGE_ENCRYPTION_KEY, KEY_VERSION)``.
      * Keyring configured (PURGE_ENCRYPTION_KEYS JSON object):
          - encryption (``key_version`` is None/empty): use
            settings.PURGE_ACTIVE_KEY_VERSION;
          - decryption (``key_version`` read from the blob header): select
            that exact version.
        A missing requested/active version, or any malformed entry, raises
        ``PurgeConfigError`` (fail closed — no data is touched).
    """
    # Legacy/test override: caller passed an explicit key.
    if key_hex:
        return key_hex, key_version or KEY_VERSION
    keyring_configured = bool(
        settings.PURGE_ENCRYPTION_KEYS
        and settings.PURGE_ENCRYPTION_KEYS.strip()
    )
    keyring = _load_keyring()
    if not keyring_configured:
        # Legacy single-key mode (backward compatibility).
        return settings.PURGE_ENCRYPTION_KEY, KEY_VERSION
    _validate_keyring(keyring)  # raises PurgeConfigError on malformed entries
    if key_version:
        # Decryption: select the exact version recorded in the blob header.
        if key_version not in keyring:
            raise PurgeConfigError(
                f"key_version '{key_version}' not found in PURGE_ENCRYPTION_KEYS; "
                f"available versions: {sorted(keyring)}"
            )
        return keyring[key_version], key_version
    # Encryption: use the configured active version.
    active = settings.PURGE_ACTIVE_KEY_VERSION
    if not active or active not in keyring:
        raise PurgeConfigError(
            f"PURGE_ACTIVE_KEY_VERSION '{active}' is missing from "
            f"PURGE_ENCRYPTION_KEYS; available versions: {sorted(keyring)}"
        )
    return keyring[active], active


def _build_aad(
    operation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    trigger: Optional[str] = None,
    key_version: Optional[str] = None,
) -> Optional[bytes]:
    """Build AAD = operation_id:user_id:trigger:key_version (review fix #9).

    If all fields are provided, returns the encoded AAD. Otherwise returns None
    for backward-compatibility with blobs encrypted before AAD was introduced.
    """
    if operation_id and user_id and trigger and key_version:
        return f"{operation_id}:{user_id}:{trigger}:{key_version}".encode()
    return None


def _parse_encrypted_blob_header(blob: bytes) -> tuple[str, int]:
    """Return ``(stored_key_version, payload_offset)`` or fail closed.

    The header is untrusted persisted data.  Invalid UTF-8 must be normalized
    to ``InvalidTag`` so the retry state machine records ``failed_decrypt``
    instead of leaking a decoder exception and leaving the job claimed.
    """
    if len(blob) < 2:
        raise InvalidTag()
    kv_len = int.from_bytes(bytes(blob[:2]), "big")
    offset = 2 + kv_len
    if len(blob) < offset + _NONCE_BYTES + 16:
        raise InvalidTag()
    try:
        stored_kv = bytes(blob[2:offset]).decode("utf-8") if kv_len else ""
    except UnicodeDecodeError as exc:
        raise InvalidTag() from exc
    return stored_kv, offset


def _encrypt_with_resolved_key(
    keys: List[str],
    key_hex: str,
    key_version: str,
    operation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    trigger: Optional[str] = None,
) -> bytes:
    """Encrypt ``keys`` with an already-resolved ``key_hex``/``key_version``.

    Wire format (hardening fix #9 — key_version persisted alongside ciphertext):
    ``key_version_len (2 bytes big-endian) || key_version (UTF-8) || nonce (12)
    || ciphertext+tag``

    ``operation_id:user_id:trigger:key_version`` form the AAD when all are
    provided; wrong AAD on decrypt → InvalidTag (GCM property).
    """
    key = _load_encryption_key(key_hex)
    aesgcm = AESGCM(key)
    nonce = os.urandom(_NONCE_BYTES)
    plaintext = json.dumps(list(keys), ensure_ascii=False).encode("utf-8")
    aad = _build_aad(operation_id, user_id, trigger, key_version)
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
    kv_bytes = (key_version or "").encode("utf-8")
    kv_len = len(kv_bytes).to_bytes(2, "big")
    return kv_len + kv_bytes + nonce + ciphertext


def encrypt_object_keys(
    keys: List[str],
    key_hex: Optional[str] = None,
    operation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    trigger: Optional[str] = None,
    key_version: Optional[str] = None,
) -> bytes:
    """Encrypt a list of OSS object keys with AES-256-GCM.

    P1-3 production path (no ``key_hex``): the active key is self-resolved from
    settings — the versioned keyring when ``PURGE_ENCRYPTION_KEYS`` is set, else
    the legacy single ``PURGE_ENCRYPTION_KEY``.

    ``key_hex`` / ``key_version`` are accepted only as deprecated back-compat
    overrides for out-of-scope callers that still pass an explicit key; they are
    ignored by the production path and by the purge tests, which rely on
    self-resolution.
    """
    if key_hex is not None:
        resolved_hex, resolved_ver = key_hex, key_version or KEY_VERSION
    else:
        resolved_hex, resolved_ver = _resolve_encryption_key(None, None)
    return _encrypt_with_resolved_key(
        keys, resolved_hex, resolved_ver, operation_id, user_id, trigger
    )


def _decrypt_with_resolved_key(
    blob: Optional[bytes],
    key_hex: str,
    operation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    trigger: Optional[str] = None,
) -> List[str]:
    """Decrypt a blob using an already-resolved ``key_hex``.

    Raises ``InvalidTag`` on a wrong key, corrupted ciphertext, bad header, or
    AAD mismatch (GCM property). Raises ``PurgeConfigError`` if the decrypted
    plaintext is not a valid JSON list of strings (fail closed). Returns ``[]``
    when the blob is empty/None.
    """
    if not blob:
        return []
    stored_kv, offset = _parse_encrypted_blob_header(bytes(blob))
    nonce = bytes(blob[offset:offset + _NONCE_BYTES])
    ciphertext = bytes(blob[offset + _NONCE_BYTES:])
    key = _load_encryption_key(key_hex)
    aesgcm = AESGCM(key)
    # AAD must match what was used at encryption time (stored key_version).
    aad = _build_aad(operation_id, user_id, trigger, stored_kv or None)
    plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
    try:
        data = json.loads(plaintext.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PurgeConfigError(
            "Decrypted object keys are not valid JSON; refusing to proceed"
        ) from exc
    if not isinstance(data, list) or not all(isinstance(k, str) for k in data):
        raise PurgeConfigError(
            "Decrypted object keys must be a JSON list of strings; refusing to proceed"
        )
    return [str(k) for k in data]


def decrypt_object_keys(
    blob: Optional[bytes],
    operation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    trigger: Optional[str] = None,
) -> List[str]:
    """Decrypt an ``encrypted_object_keys`` blob (self-resolving key).

    P1-3: reads ``key_version`` from the blob header and resolves the matching
    key — from the versioned keyring when ``PURGE_ENCRYPTION_KEYS`` is set
    (fail closed if that version is absent), else the legacy single
    ``PURGE_ENCRYPTION_KEY``. No caller-supplied key.

    All fail-closed cases raise and map to ``failed_decrypt`` in the retry path:
    bad header, wrong key, corrupted ciphertext, AAD mismatch, key version
    missing from the keyring, non-JSON plaintext, or non-string-list payload.
    """
    if not blob:
        return []
    # Read the stored key_version from the blob header to resolve the key.
    stored_kv, _ = _parse_encrypted_blob_header(bytes(blob))
    key_hex, _ = _resolve_encryption_key(None, key_version=stored_kv or None)
    return _decrypt_with_resolved_key(
        blob, key_hex, operation_id, user_id, trigger
    )


# --------------------------------------------------------------------------- #
# Result type
# --------------------------------------------------------------------------- #


@dataclass
class PurgeResult:
    status: str
    purge_operation_id: Optional[UUID] = None
    tombstone_receipt_id: Optional[UUID] = None
    object_delete_status: str = "oss_not_applicable"
    steps: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


@dataclass
class PurgeTargets:
    """Resolved set of rows/objects a specific scope may delete."""

    event_ids: List[str] = field(default_factory=list)  # events to delete (str)
    signal_ids: List[str] = field(default_factory=list)
    photo_keys: List[str] = field(default_factory=list)
    delete_projections: bool = False  # goals + profile_entries (account only)
    delete_all_idempotency: bool = False  # vs only records tied to events
    delete_all_signals: bool = False  # vs no signals


def _to_uuid(user_id) -> UUID:
    return user_id if isinstance(user_id, UUID) else UUID(str(user_id))


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize a datetime to offset-aware UTC.

    SQLite returns naive datetimes (no tz info) while PostgreSQL returns aware
    ones; comparisons against ``datetime.now(timezone.utc)`` must be tz-safe.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _to_uuid_list(values: List[str]) -> List[UUID]:
    out: List[UUID] = []
    for v in values:
        if isinstance(v, UUID):
            out.append(v)
        else:
            try:
                out.append(UUID(str(v)))
            except (ValueError, AttributeError) as exc:
                raise PurgeConfigError(
                    "persisted purge target_event_ids contains an invalid UUID"
                ) from exc
    return out


async def _find_purge_operation(db: AsyncSession, user_id: UUID) -> Optional[PurgeOperation]:
    result = await db.execute(
        select(PurgeOperation).where(PurgeOperation.user_id == user_id)
    )
    return result.scalars().first()


async def _has_purgeable_data(db: AsyncSession, user_id: UUID) -> bool:
    """Check ALL data types: events, profiles, goals, safety_signals,
    idempotency_records. If ANY exist → proceed with purge. Only if ALL are
    empty → no-op (hardening fix #7).
    """
    for model in (
        PostureAssessmentEvent,
        PostureProfileEntry,
        PostureUserGoal,
        PostureSafetySignal,
        IdempotencyRecord,
    ):
        row = (
            await db.execute(
                select(model.id)
                .where(model.user_id == user_id)
                .limit(1)
            )
        ).first()
        if row is not None:
            return True
    # Phase 5 Agent tables (PK columns are not named ``id``): an account that
    # only ever used the Agent still has purgeable data and must be processed.
    for agent_model, pk_col in (
        (AgentCloudConsent, AgentCloudConsent.consent_id),
        (AgentRun, AgentRun.run_id),
        (AgentToolEvent, AgentToolEvent.event_id),
        (AgentActionProposal, AgentActionProposal.proposal_id),
    ):
        row = (
            await db.execute(
                select(pk_col).where(agent_model.user_id == user_id).limit(1)
            )
        ).first()
        if row is not None:
            return True
    # Phase 7 adaptive execution rows can outlive their idempotency TTL and
    # therefore must independently make an account purge non-empty.
    from app.training.models import (
        PostureRecheckDismissal,
        TrainingDayAdjustment,
        TrainingWeeklyReview,
    )

    for adaptive_model, pk_col in (
        (TrainingDayAdjustment, TrainingDayAdjustment.adjustment_id),
        (TrainingWeeklyReview, TrainingWeeklyReview.review_id),
        (PostureRecheckDismissal, PostureRecheckDismissal.dismissal_id),
    ):
        adaptive = (
            await db.execute(
                select(pk_col).where(adaptive_model.user_id == user_id).limit(1)
            )
        ).first()
        if adaptive is not None:
            return True
    return False


async def _collect_targets(
    db: AsyncSession, user_id: UUID, scope: PurgeScope
) -> tuple[List[PostureAssessmentEvent], PurgeTargets]:
    """Resolve which events/signals/objects ``scope`` is permitted to delete.

    Returns the event rows that must be frozen (lifecycle->expired) along with a
    ``PurgeTargets`` describing the deletion set.
    """
    events = (
        await db.execute(
            select(PostureAssessmentEvent).where(
                PostureAssessmentEvent.user_id == user_id
            )
        )
    ).scalars().all()

    def _flatten(rows: List[PostureAssessmentEvent]) -> List[str]:
        keys: List[str] = []
        for evt in rows:
            for key in (evt.photo_keys or []):
                if key not in keys:
                    keys.append(str(key))
        return keys

    if scope == PurgeScope.ACCOUNT_DELETION:
        signals = (
            await db.execute(
                select(PostureSafetySignal).where(
                    PostureSafetySignal.user_id == user_id
                )
            )
        ).scalars().all()
        targets = PurgeTargets(
            event_ids=[str(e.id) for e in events],
            signal_ids=[str(s.id) for s in signals],
            photo_keys=_flatten(events),
            delete_projections=True,
            delete_all_idempotency=True,
            delete_all_signals=True,
        )
        return events, targets

    # consent_withdrawn / retention_expired: ONLY ai_photo source events.
    # Select by source='ai_photo' (NOT by photo_keys non-empty) per review fix #7.
    if scope == PurgeScope.RETENTION_EXPIRED:
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=configured_retention_days()
        )
        photo_events = [
            e
            for e in events
            if e.source == "ai_photo"
            and (e.created_at is not None)
            and (_as_utc(e.created_at) < cutoff)
        ]
    else:  # CONSENT_WITHDRAWN
        photo_events = [e for e in events if e.source == "ai_photo"]

    targets = PurgeTargets(
        event_ids=[str(e.id) for e in photo_events],
        signal_ids=[],
        photo_keys=_flatten(photo_events),
        delete_projections=False,
        delete_all_idempotency=False,
        delete_all_signals=False,
    )
    return photo_events, targets


async def _delete_projections(db: AsyncSession, user_id: UUID) -> List[str]:
    """Step 2: delete goals then profile entries (account_deletion only)."""
    await db.execute(
        delete(PostureUserGoal).where(PostureUserGoal.user_id == user_id)
    )
    await db.execute(
        delete(PostureProfileEntry).where(PostureProfileEntry.user_id == user_id)
    )
    return ["delete_goals", "delete_profile_entries"]


async def _delete_db_health_data(db: AsyncSession, user_id: UUID) -> List[str]:
    """Step 5 (account_deletion): delete the actual health-payload rows by user.

    Returns the ordered list of completed sub-step names. Does NOT commit; the
    caller commits on success or rolls back on failure. Exposed at module scope
    so retry/failure behaviour can be verified and monkeypatched in tests.
    """
    done: List[str] = []
    await db.execute(
        delete(PostureAssessmentEvent).where(
            PostureAssessmentEvent.user_id == user_id
        )
    )
    done.append("delete_assessment_events")
    await db.execute(
        delete(PostureSafetySignal).where(PostureSafetySignal.user_id == user_id)
    )
    done.append("delete_safety_signals")
    from app.training.persistence import delete_adaptive_data

    await delete_adaptive_data(db, str(user_id), commit=False)
    done.append("delete_training_adaptive_data")
    await db.execute(
        delete(IdempotencyRecord).where(IdempotencyRecord.user_id == user_id)
    )
    done.append("delete_idempotency_records")
    # Phase 5 reviewed cross-domain extension (spec Persistence; ADR-0004):
    # account_deletion also removes the four Agent-owned tables. Delete
    # proposals + tool_events before runs (FKs reference runs); consents have no
    # such dependency. This does NOT repair the pre-existing platform gap of
    # independently owned health/training domain-row deletion, and the
    # idempotency delete above already covers the three Agent namespaces
    # (agent_action_confirm / agent_consent_grant / agent_consent_withdraw) by
    # user_id, alongside all other operations' rows.
    await db.execute(
        delete(AgentToolEvent).where(AgentToolEvent.user_id == user_id)
    )
    done.append("delete_agent_tool_events")
    await db.execute(
        delete(AgentActionProposal).where(AgentActionProposal.user_id == user_id)
    )
    done.append("delete_agent_action_proposals")
    await db.execute(delete(AgentRun).where(AgentRun.user_id == user_id))
    done.append("delete_agent_runs")
    await db.execute(
        delete(AgentCloudConsent).where(AgentCloudConsent.user_id == user_id)
    )
    done.append("delete_agent_cloud_consents")
    return done


async def _delete_scoped_db_health_data(
    db: AsyncSession, targets: PurgeTargets, user_id: Optional[UUID] = None
) -> List[str]:
    """Step 5 (consent_withdrawn / retention_expired): delete only the scoped
    photo events + their associated idempotency records.

    Before deletion: unlink any profile latest_photo_event_id referencing these
    events to NULL (review fix #7). After deletion: rebuild projection for
    affected (user_id, issue_id) from remaining active events. If no events
    remain for an issue, the profile entry is deleted.

    Self-test events, safety signals, goals and profile entries are preserved.
    """
    done: List[str] = []
    evt_uuids = _to_uuid_list(targets.event_ids)

    # Unlink profile FK references to the events being deleted (fix #7).
    if evt_uuids:
        profile_filters = [PostureProfileEntry.latest_photo_event_id.in_(evt_uuids)]
        if user_id is not None:
            profile_filters.append(PostureProfileEntry.user_id == user_id)
        profiles_referencing = (
            await db.execute(
                select(PostureProfileEntry).where(*profile_filters)
            )
        ).scalars().all()
        for profile in profiles_referencing:
            profile.latest_photo_event_id = None
        if profiles_referencing:
            await db.flush()
        done.append("unlink_profile_photo_fk")

    if evt_uuids:
        # Capture affected issue_ids before deletion for rebuild
        event_filters = [PostureAssessmentEvent.id.in_(evt_uuids)]
        if user_id is not None:
            event_filters.append(PostureAssessmentEvent.user_id == user_id)
        affected_events = (
            await db.execute(
                select(PostureAssessmentEvent).where(*event_filters)
            )
        ).scalars().all()
        affected_issues = list(set(e.issue_id for e in affected_events))
        affected_user_id = affected_events[0].user_id if affected_events else user_id

        await db.execute(delete(PostureAssessmentEvent).where(*event_filters))
    else:
        affected_issues = []
        affected_user_id = user_id
    done.append("delete_assessment_events")

    if targets.event_ids:
        idempotency_filters = [IdempotencyRecord.result_ref.in_(targets.event_ids)]
        if user_id is not None:
            idempotency_filters.append(IdempotencyRecord.user_id == user_id)
        await db.execute(delete(IdempotencyRecord).where(*idempotency_filters))
    done.append("delete_idempotency_records")

    # Rebuild each affected profile through the one authoritative projection +
    # risk function.  Duplicating only the projection fields here previously
    # left stale risk_tier/risk_version values after a scoped purge.
    if affected_issues and affected_user_id is not None:
        from app.posture.service import _recompute_and_upsert_profile

        uid_str = str(affected_user_id)
        for issue_id in sorted(affected_issues):
            await _recompute_and_upsert_profile(db, uid_str, issue_id)
        done.append("rebuild_projection")

    return done


def _object_delete_status_for(photo_keys: List[str]) -> str:
    if not photo_keys:
        return "oss_not_applicable"
    # Both success and 404 are accepted as verified deletion, so any real OSS
    # deletion batch resolves to the "deleted or not found" completed state.
    return "oss_deleted_or_not_found"


def _signal_outcome_envelope(value: object, oss_outcome: str) -> dict:
    """Preserve signal IDs while storing only aggregate OSS completion state."""
    if value is None:
        signal_ids: List[str] = []
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        signal_ids = list(value)
    elif isinstance(value, dict):
        stored_ids = value.get("signal_ids", [])
        if not isinstance(stored_ids, list) or not all(
            isinstance(item, str) for item in stored_ids
        ):
            raise PurgeConfigError(
                "persisted purge target_signal_ids contains invalid signal IDs"
            )
        signal_ids = list(stored_ids)
    else:
        raise PurgeConfigError(
            "persisted purge target_signal_ids has an invalid JSON shape"
        )
    return {"signal_ids": signal_ids, "oss_outcome": oss_outcome}


def _next_retry(attempt_count: int) -> datetime:
    """Exponential backoff: base 5 min, factor 2, capped at 24h."""
    delay = min(
        _RETRY_BASE_DELAY * (2 ** max(0, attempt_count)),
        _RETRY_MAX_DELAY,
    )
    return datetime.now(timezone.utc) + delay


def _to_failed_permanent(op: PurgeOperation) -> None:
    """Mark an operation permanently failed (no further retries)."""
    op.status = "failed_permanent"
    op.next_retry_at = None


async def _finalize_purge(
    db: AsyncSession,
    op: PurgeOperation,
    trigger: str,
    photo_keys: List[str],
    *,
    oss_outcome: Optional[str] = None,
) -> UUID:
    """Step 6 + step 7 in a SINGLE transaction (atomic, spec §6.7 / FIX 5).

    Writes the completed tombstone AND scrubs the purge_operation linkable
    fields in one commit: if the commit fails both are rolled back, so a
    completed tombstone can never exist alongside retained linkable fields.
    Returns the tombstone receipt_id.

    Hardening fix #9: accepts ``oss_outcome`` parameter directly instead of
    inferring from photo_keys when called from DB-retry path.
    """
    if oss_outcome is not None:
        object_delete_status = oss_outcome
    else:
        object_delete_status = _object_delete_status_for(photo_keys)
    assert object_delete_status in _TOMBSTONE_COMPLETED_STATUSES
    tombstone = PosturePurgeTombstone(
        receipt_id=_uuid.uuid4(),
        deleted_at=datetime.now(timezone.utc),
        purge_reason=trigger,
        policy_version=POLICY_VERSION,
        object_delete_status=object_delete_status,
    )
    db.add(tombstone)
    op.status = "completed"
    op.user_id = None
    op.target_event_ids = None
    op.target_signal_ids = None
    op.encrypted_object_keys = None
    op.completed_at = datetime.now(timezone.utc)
    op.next_retry_at = None
    try:
        await db.commit()
    except Exception:
        # Atomic guarantee: roll back BOTH the tombstone insert and the scrub so
        # neither takes effect on commit failure.
        await db.rollback()
        raise
    return tombstone.receipt_id


async def _delete_oss_objects(
    db: AsyncSession,
    op: PurgeOperation,
    object_store: ObjectStore,
    photo_keys: List[str],
) -> bool:
    """Step 3: delete OSS objects (verify success or 404).

    Returns True on success. On failure sets the op to ``failed_oss_retry``
    (keys + targets retained), commits, and returns False.

    On success, persists the oss_outcome into target_signal_ids (repurposed
    JSONB field, review fix #10) so DB-retry can read the stored outcome
    instead of recomputing (OSS already done).
    """
    op.status = "oss_deleting"
    op.next_retry_at = datetime.now(timezone.utc) + LEASE_DURATION
    await db.commit()
    # The commit above makes this phase crash-recoverable but releases the
    # transaction-scoped user lock. Reacquire it before external deletion so
    # an expired-lease worker cannot execute the same live operation in parallel.
    if op.user_id is not None:
        await acquire_user_transaction_lock(db, str(op.user_id))
        # A retry worker may have completed while this caller waited for the
        # lock. Refresh before touching OSS so stale ORM state cannot replay
        # an already completed external deletion.
        await db.refresh(op)
        if op.status in TERMINAL_STATUSES or op.user_id is None:
            return True
    try:
        for key in photo_keys:
            await object_store.delete_object(key)
    except ObjectStoreError:
        op.status = "failed_oss_retry"
        op.next_retry_at = _next_retry(op.attempt_count)
        await db.commit()
        logger.info(
            "purge failed during oss deletion (attempt=%d); no tombstone written",
            op.attempt_count,
        )
        return False
    # Persist only the aggregate completed outcome. Never persist plaintext
    # object keys after encrypted_object_keys is cleared. Preserve signal IDs
    # in the same temporary JSON envelope for account-deletion DB retries.
    oss_outcome = _object_delete_status_for(photo_keys)
    op.target_signal_ids = _signal_outcome_envelope(
        op.target_signal_ids, oss_outcome
    )
    # Publish OSS completion and the DB resume phase atomically. A lease worker
    # that was already waiting on the user lock must never observe an
    # oss_deleting row after the original worker has finished OSS.
    op.encrypted_object_keys = None
    op.status = "db_deleting"
    op.next_retry_at = datetime.now(timezone.utc) + LEASE_DURATION
    await db.commit()
    return True


# --------------------------------------------------------------------------- #
# Write-freeze guard (FIX 3 — exported for Task 2 integration)
# --------------------------------------------------------------------------- #


async def is_user_write_frozen(db: AsyncSession, user_id) -> bool:
    """Return True if a non-terminal purge_operation exists for ``user_id``.

    While a purge is in flight (status not in TERMINAL_STATUSES) the user's
    health-data writes must be rejected by callers. Terminal operations have
    their ``user_id`` scrubbed to null (方案 B) so they no longer match.
    """
    user_uuid = _to_uuid(user_id)
    result = await db.execute(
        select(PurgeOperation.id)
        .where(PurgeOperation.user_id == user_uuid)
        .where(PurgeOperation.status.not_in(TERMINAL_STATUSES))
        .limit(1)
    )
    return result.first() is not None


# --------------------------------------------------------------------------- #
# Main state machine
# --------------------------------------------------------------------------- #


async def run_purge(
    db: AsyncSession,
    user_id,
    object_store: ObjectStore,
    trigger: str,
    *,
    encryption_key: Optional[str] = None,
) -> PurgeResult:
    """Execute the full purge state machine for a user's posture health data.

    ``trigger`` is one of user_delete / retention_expired / consent_withdrawn /
    account_deletion (spec §6.6); it selects the purge scope and is recorded on
    the tombstone. Idempotent: re-running after completion (or on a user with
    no data) is a no-op that writes no tombstone.

    P1-1 lock ordering: only cheap format validation happens BEFORE the
    per-user lock (trigger + encryption config). ALL database reads/writes —
    the in-flight check, the purgeable-data check, and target collection —
    happen AFTER the lock is held, so a concurrent writer cannot insert data
    that the purge then misses, and any non-terminal operation (including
    ``failed_permanent`` / ``failed_decrypt`` / ``retrying_*``) blocks a new
    purge with 409 ``purge_already_in_flight``.

    P1-3: the object-key encryption is self-resolved from settings (versioned
    keyring or legacy single key). ``encryption_key`` is retained only as an
    optional legacy/test override; production callers omit it.
    """
    user_uuid = _to_uuid(user_id)

    # --- BEFORE lock: cheap format validation only (no DB reads) ------------
    scope = _scope_from_trigger(trigger)  # raises ValueError on bad trigger
    if encryption_key is not None:
        # Legacy/test override: validate the supplied key format up front.
        _load_encryption_key(encryption_key)
    else:
        # Production: validate the self-resolved config (keyring or legacy key).
        resolved_hex, _ = _resolve_encryption_key(None, None)
        _load_encryption_key(resolved_hex)

    steps: List[str] = []

    # --- step 0: acquire per-user advisory lock (hardening fix #1/#3) ------
    await acquire_user_transaction_lock(db, str(user_uuid))

    # --- AFTER lock: in-flight + idempotency checks (fix #3 / P1-1) --------
    # Any non-terminal purge_operation (failed_permanent, failed_decrypt,
    # retrying_oss/db, failed_*_retry, freezing, ...) → 409. Only
    # completed/cancelled allow a new purge. This is read under the lock so a
    # concurrent writer is serialized.
    inflight = await db.execute(
        select(PurgeOperation)
        .where(PurgeOperation.user_id == user_uuid)
        .where(PurgeOperation.status.not_in(TERMINAL_STATUSES))
    )
    if inflight.scalars().first() is not None:
        await db.rollback()
        raise AppException(
            409,
            "该用户已有进行中的清除操作",
            "purge_already_in_flight",
        )

    # Resolve targets under the lock before the no-op decision. Account purge
    # considers every health table; scoped purge is a no-op unless at least one
    # in-scope ai_photo event exists.
    freeze_events, targets = await _collect_targets(db, user_uuid, scope)
    has_targets = (
        await _has_purgeable_data(db, user_uuid)
        if scope == PurgeScope.ACCOUNT_DELETION
        else bool(targets.event_ids)
    )
    if not has_targets:
        existing = await _find_purge_operation(db, user_uuid)
        operation_id = existing.id if existing is not None else None
        await db.rollback()
        return PurgeResult(
            status="idempotent_noop",
            purge_operation_id=operation_id,
            object_delete_status="oss_not_applicable",
            steps=["noop_no_data"],
        )

    # --- step 1: freeze + collect photo_keys + create purge operation -------
    event_ids = targets.event_ids
    signal_ids = targets.signal_ids
    photo_keys = targets.photo_keys
    for evt in freeze_events:
        evt.lifecycle = "expired"

    op = PurgeOperation(
        id=_uuid.uuid4(),
        user_id=user_uuid,
        trigger=trigger,
        status="freezing",
        attempt_count=0,
        max_attempts=DEFAULT_MAX_ATTEMPTS,
        next_retry_at=datetime.now(timezone.utc) + LEASE_DURATION,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=DEFAULT_RETRY_WINDOW_DAYS),
    )
    db.add(op)
    # AAD binding (review fix #9): operation_id:user_id:trigger:key_version.
    # P1-3: encrypt self-resolves from config unless a legacy override is given.
    if photo_keys:
        if encryption_key is not None:
            op.encrypted_object_keys = _encrypt_with_resolved_key(
                photo_keys, encryption_key, KEY_VERSION,
                operation_id=str(op.id),
                user_id=str(user_uuid),
                trigger=trigger,
            )
        else:
            op.encrypted_object_keys = encrypt_object_keys(
                photo_keys,
                operation_id=str(op.id),
                user_id=str(user_uuid),
                trigger=trigger,
            )
    else:
        op.encrypted_object_keys = None
    op.target_event_ids = event_ids or None
    op.target_signal_ids = signal_ids or None
    # Keep the initial freezing lease. If the process crashes after this commit
    # but before publishing oss_deleting, run_due_purge_jobs can reclaim the
    # operation and resume from the persisted freezing phase.
    await db.commit()
    steps.append("freeze_and_collect_photo_keys")
    logger.info(
        "purge step completed: freeze_and_collect_photo_keys (events=%d, objects=%d)",
        len(event_ids),
        len(photo_keys),
    )

    # --- step 2: delete goals -> profile entries (account_deletion only) ---
    if targets.delete_projections:
        steps.extend(await _delete_projections(db, user_uuid))
        await db.commit()

    # --- step 3: delete OSS objects (verify success or 404) ---------------
    if not await _delete_oss_objects(db, op, object_store, photo_keys):
        return PurgeResult(
            status="failed_oss_retry",
            purge_operation_id=op.id,
            tombstone_receipt_id=None,
            object_delete_status="oss_not_applicable",
            steps=steps,
        )
    steps.append("delete_oss_objects")
    logger.info(
        "purge step completed: delete_oss_objects (count=%d)", len(photo_keys)
    )

    # --- step 4: encrypted keys were cleared atomically with OSS completion --
    steps.append("clear_encrypted_object_keys")

    # --- step 5: delete db health data ------------------------------------
    await acquire_user_transaction_lock(db, str(user_uuid))
    await db.refresh(op)
    if op.status in TERMINAL_STATUSES or op.user_id is None:
        operation_id = op.id
        await db.rollback()
        return PurgeResult(
            status="idempotent_noop",
            purge_operation_id=operation_id,
            object_delete_status=_object_delete_status_for(photo_keys),
            steps=steps,
        )
    operation_id = op.id
    try:
        if scope == PurgeScope.ACCOUNT_DELETION:
            db_steps = await _delete_db_health_data(db, user_uuid)
        else:
            db_steps = await _delete_scoped_db_health_data(db, targets, user_id=user_uuid)
    except Exception:
        await db.rollback()
        # Re-fetch the operation (session was rolled back) and mark failed.
        op = await db.get(PurgeOperation, operation_id)
        op.status = "failed_db_retry"
        op.next_retry_at = _next_retry(op.attempt_count)
        # keys already cleared in step 4 (committed); targets RETAINED.
        await db.commit()
        logger.info(
            "purge failed during db deletion (attempt=%d); no tombstone written",
            op.attempt_count,
        )
        return PurgeResult(
            status="failed_db_retry",
            purge_operation_id=op.id,
            tombstone_receipt_id=None,
            object_delete_status="oss_not_applicable",
            steps=steps,
        )
    steps.extend(db_steps)

    # --- step 6 + step 7: atomic tombstone + scrub (single transaction) ---
    receipt_id = await _finalize_purge(db, op, trigger, photo_keys)
    steps.append("write_completed_tombstone")
    steps.append("scrub_purge_operation_linkable_fields")
    logger.info("purge step completed: write_completed_tombstone")

    return PurgeResult(
        status="completed",
        purge_operation_id=op.id,
        tombstone_receipt_id=receipt_id,
        object_delete_status=_object_delete_status_for(photo_keys),
        steps=steps,
    )


# --------------------------------------------------------------------------- #
# Retry engine (FIX 4)
# --------------------------------------------------------------------------- #


async def _resume_db_delete(
    db: AsyncSession, op: PurgeOperation
) -> List[str]:
    """Resume step 5 from a persisted operation.

    For account_deletion, idempotently repeats goals/profile deletion before
    deleting the payload rows. This covers a crash immediately after the
    ``freezing`` operation was committed but before original step 2 ran. For
    scoped purges, deletes only the target events + their associated
    idempotency records (by target_event_ids).
    """
    scope = _scope_from_trigger(op.trigger)
    if scope == PurgeScope.ACCOUNT_DELETION and op.user_id is not None:
        steps = await _delete_projections(db, op.user_id)
        steps.extend(await _delete_db_health_data(db, op.user_id))
        return steps
    targets = PurgeTargets(event_ids=list(op.target_event_ids or []))
    return await _delete_scoped_db_health_data(db, targets, user_id=op.user_id)


async def _resume_purge(
    db: AsyncSession,
    op: PurgeOperation,
    object_store: ObjectStore,
    encryption_key: Optional[str] = None,
) -> PurgeResult:
    """Resume a retryable purge_operation from its current phase.

    P1-2: the resume phase is driven by the operation's persisted status, not a
    local variable, so a worker that crashes mid-resume leaves the row in a
    reclaimable lease status (``retrying_oss`` / ``retrying_db``):
      * ``failed_oss_retry`` / ``retrying_oss`` → (re)do the OSS phase;
      * ``failed_db_retry`` / ``retrying_db`` → (re)do the DB phase.

    While work is in progress the row stays in its ``retrying_*`` lease status
    so an expired lease lets another worker reclaim it. After OSS succeeds the
    row transitions to ``retrying_db`` (lease refreshed) before DB deletion, so
    a crash during DB deletion reclaims into the DB phase rather than getting
    stuck. On success → ``completed``; on failure → ``failed_*_retry`` with
    exponential backoff (or ``failed_permanent`` when exhausted).

    Hardening fix #3: acquires the shared user lock before resuming.
    """
    # Hardening fix #3: retry_worker acquires user lock before resuming.
    if op.user_id is not None:
        await acquire_user_transaction_lock(db, str(op.user_id))

    # Another worker can claim an expired lease while the original worker is
    # still alive.  It then waits on the same user lock.  Refresh after taking
    # the lock so it observes a completion by the original worker and does not
    # replay OSS/DB deletion or write a second tombstone.
    await db.refresh(op)
    operation_id = op.id
    current_status = op.status
    if current_status in TERMINAL_STATUSES or op.user_id is None:
        await db.rollback()  # release the user transaction lock
        return PurgeResult(
            status="idempotent_noop",
            purge_operation_id=operation_id,
            object_delete_status="oss_not_applicable",
        )
    if current_status not in RETRYABLE_STATUSES:
        await db.rollback()  # release the user transaction lock
        return PurgeResult(status=current_status, purge_operation_id=operation_id)

    # Compute lease/expiry time after any advisory-lock wait, not before it.
    now = datetime.now(timezone.utc)

    # Permanent-failure guards (spec §6.7.2).
    if op.expires_at is not None and _as_utc(op.expires_at) < now:
        _to_failed_permanent(op)
        await db.commit()
        logger.warning("purge expired before retry (op=%s)", op.id)
        return PurgeResult(status="failed_permanent", purge_operation_id=op.id)
    if op.attempt_count >= op.max_attempts:
        _to_failed_permanent(op)
        await db.commit()
        logger.warning(
            "purge exhausted retries (op=%s, attempts=%d)", op.id, op.attempt_count
        )
        return PurgeResult(status="failed_permanent", purge_operation_id=op.id)

    op.attempt_count = op.attempt_count + 1
    attempt = op.attempt_count

    # P1-2: status IS the resume phase. No local "previous_status" variable.
    resume_oss = op.status in OSS_RESUME_STATUSES

    def _user_id_str() -> Optional[str]:
        return str(op.user_id) if op.user_id else None

    # --- resume the OSS phase ---------------------------------------------
    if resume_oss:
        # Decrypt retained keys (self-resolving, or legacy override).
        try:
            if encryption_key is not None:
                photo_keys = _decrypt_with_resolved_key(
                    op.encrypted_object_keys, encryption_key,
                    operation_id=str(op.id),
                    user_id=_user_id_str(),
                    trigger=op.trigger,
                )
            else:
                photo_keys = decrypt_object_keys(
                    op.encrypted_object_keys,
                    operation_id=str(op.id),
                    user_id=_user_id_str(),
                    trigger=op.trigger,
                )
        except (InvalidTag, PurgeConfigError):
            # Fail closed: wrong/corrupted key, bad header, missing key version,
            # non-JSON or non-string-list payload → retain data, no tombstone.
            op.status = "failed_decrypt"
            op.next_retry_at = None
            await db.commit()
            logger.error(
                "purge decrypt failed (op=%s); data retained, no tombstone",
                op.id,
            )
            return PurgeResult(
                status="failed_decrypt",
                purge_operation_id=op.id,
                tombstone_receipt_id=None,
                object_delete_status="oss_not_applicable",
            )

        # Stay in the retrying_oss lease while OSS deletion runs (crash-safe).
        op.status = RETRYING_OSS
        op.next_retry_at = now + LEASE_DURATION
        try:
            for key in photo_keys:
                await object_store.delete_object(key)
        except ObjectStoreError:
            op.status = "failed_oss_retry"
            if attempt >= op.max_attempts:
                _to_failed_permanent(op)
            else:
                op.next_retry_at = _next_retry(attempt)
            await db.commit()
            logger.info(
                "purge retry failed during oss deletion (attempt=%d)", attempt
            )
            return PurgeResult(
                status=op.status,
                purge_operation_id=op.id,
                tombstone_receipt_id=None,
                object_delete_status="oss_not_applicable",
            )
        # OSS succeeded → clear keys, persist real outcome, and transition into
        # the DB-phase lease so a crash during DB delete reclaims into DB.
        oss_outcome = _object_delete_status_for(photo_keys)
        op.encrypted_object_keys = None
        op.target_signal_ids = _signal_outcome_envelope(
            op.target_signal_ids, oss_outcome
        )
        op.status = RETRYING_DB
        op.next_retry_at = now + LEASE_DURATION
        try:
            await _resume_db_delete(db, op)
        except Exception:
            await db.rollback()
            op = await db.get(PurgeOperation, operation_id)
            op.attempt_count = attempt
            op.encrypted_object_keys = None
            op.target_signal_ids = _signal_outcome_envelope(
                op.target_signal_ids, oss_outcome
            )
            op.status = "failed_db_retry"
            if attempt >= op.max_attempts:
                _to_failed_permanent(op)
            else:
                op.next_retry_at = _next_retry(attempt)
            await db.commit()
            return PurgeResult(
                status=op.status,
                purge_operation_id=op.id,
                tombstone_receipt_id=None,
                object_delete_status="oss_not_applicable",
            )
        receipt_id = await _finalize_purge(db, op, op.trigger, photo_keys)
        logger.info("purge retry completed (op=%s, attempt=%d)", op.id, attempt)
        return PurgeResult(
            status="completed",
            purge_operation_id=op.id,
            tombstone_receipt_id=receipt_id,
            object_delete_status=oss_outcome,
        )

    # --- resume the DB phase (failed_db_retry / retrying_db) ---------------
    # On DB-retry, read the stored OSS outcome (fix #9/#10) instead of recomputing.
    stored_oss_outcome = None
    if isinstance(op.target_signal_ids, dict):
        stored_oss_outcome = op.target_signal_ids.get("oss_outcome")

    # Stay in the retrying_db lease while DB deletion runs (crash-safe).
    op.status = RETRYING_DB
    op.next_retry_at = now + LEASE_DURATION
    try:
        await _resume_db_delete(db, op)
    except Exception:
        await db.rollback()
        op = await db.get(PurgeOperation, operation_id)
        op.attempt_count = attempt
        op.status = "failed_db_retry"
        if attempt >= op.max_attempts:
            _to_failed_permanent(op)
        else:
            op.next_retry_at = _next_retry(attempt)
        await db.commit()
        return PurgeResult(
            status=op.status,
            purge_operation_id=op.id,
            tombstone_receipt_id=None,
            object_delete_status="oss_not_applicable",
        )
    # Use stored outcome for the tombstone (fix #9 / #10).
    final_oss_status = stored_oss_outcome or "oss_not_applicable"
    receipt_id = await _finalize_purge(
        db, op, op.trigger, [],
        oss_outcome=final_oss_status,
    )
    logger.info("purge retry completed (op=%s, attempt=%d)", op.id, attempt)
    return PurgeResult(
        status="completed",
        purge_operation_id=op.id,
        tombstone_receipt_id=receipt_id,
        object_delete_status=final_oss_status,
    )


async def run_due_purge_jobs(
    db: AsyncSession,
    object_store: ObjectStore,
    encryption_key: Optional[str] = None,
) -> List[PurgeResult]:
    """Find due/reclaimable purge_operations and resume each from its phase.

    Hardening fix #8: process ONE job at a time within its own logical step.
    1. SELECT one job with FOR UPDATE SKIP LOCKED LIMIT 1.
    2. Claim it: set status to ``retrying_oss``/``retrying_db`` and a lease
       (``next_retry_at = now + LEASE_DURATION``) and COMMIT.
    3. Process that one job (resume the failed step).
    4. Update final status and COMMIT.
    5. Repeat for next due job.

    P1-2 selection (lease crash recovery):
      * normally due: ``status IN {failed_oss_retry, failed_db_retry}`` and
        ``next_retry_at <= now``; OR
      * lease expired / reclaimable: ``status IN {retrying_oss, retrying_db}``
        and ``next_retry_at <= now`` (the claiming worker crashed).
      Combined: ``status IN RETRYABLE_STATUSES AND next_retry_at <= now``. The
      resumed status tells ``_resume_purge`` which phase to resume.

    Each retry increments ``attempt_count`` and sets ``next_retry_at`` via
    exponential backoff (base 5 min, factor 2, cap 24h). Reaching
    ``max_attempts`` or passing ``expires_at`` moves the operation to
    ``failed_permanent``.
    """
    now = datetime.now(timezone.utc)

    # 1) Expire any non-terminal operation past its window.
    expired = (
        await db.execute(
            select(PurgeOperation)
            .where(PurgeOperation.status.not_in(TERMINAL_STATUSES))
            .where(PurgeOperation.expires_at < now)
        )
    ).scalars().all()
    for op in expired:
        if _as_utc(op.expires_at) is not None and _as_utc(op.expires_at) < now:
            _to_failed_permanent(op)
    if expired:
        await db.commit()

    results: List[PurgeResult] = []

    # 2) Process ONE job at a time (fix #8).
    while True:
        # SELECT one due/reclaimable job with FOR UPDATE SKIP LOCKED LIMIT 1.
        stmt = (
            select(PurgeOperation)
            .where(PurgeOperation.status.in_(RETRYABLE_STATUSES))
            .where(PurgeOperation.next_retry_at <= now)
            .where(PurgeOperation.attempt_count < PurgeOperation.max_attempts)
            .limit(1)
        )
        if db.bind.dialect.name != "sqlite":
            stmt = stmt.with_for_update(skip_locked=True)
        row = (await db.execute(stmt)).scalars().first()
        if row is None:
            # A SELECT starts a transaction even when no job is found. End it
            # explicitly so worker sessions do not retain row/relation locks
            # and block test isolation or operational maintenance.
            await db.rollback()
            break
        # Re-check tz-safe due/expiry in Python (SQLite naive datetimes).
        if _as_utc(row.next_retry_at) is None or _as_utc(row.next_retry_at) > now:
            await db.rollback()
            break
        if _as_utc(row.expires_at) is not None and _as_utc(row.expires_at) < now:
            _to_failed_permanent(row)
            await db.commit()
            results.append(PurgeResult(status="failed_permanent", purge_operation_id=row.id))
            continue

        # P1-2: claim the job into a phase-specific lease status and COMMIT to
        # release the SKIP LOCKED row. The lease (next_retry_at = now +
        # LEASE_DURATION) means a crashing worker's job becomes re-claimable
        # once the lease expires; the status records which phase to resume.
        if row.status in OSS_RESUME_STATUSES:
            row.status = RETRYING_OSS
        else:
            row.status = RETRYING_DB
        row.next_retry_at = now + LEASE_DURATION
        await db.commit()

        # Re-fetch to resume (session state after commit). The persisted status
        # drives the resume phase (no local previous_status variable).
        op = await db.get(PurgeOperation, row.id)
        result = await _resume_purge(db, op, object_store, encryption_key)
        results.append(result)

    return results


# Retention read-back helper (used by callers / future expiry triggers).
def configured_retention_days() -> int:
    return settings.PHOTO_RETENTION_DAYS
