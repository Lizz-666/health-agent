from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import async_session
from app.privacy.models import AccountDeletionMarker
from app.privacy.service import ensure_no_restored_deleted_subjects

LEDGER_SCHEMA_VERSION = "controlled-trial-deletion-ledger-v1"
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_SIGNATURE_CONTEXT = b"phase9-deletion-ledger-v1\x00"


class DeletionLedgerError(RuntimeError):
    pass


def _privacy_key() -> bytes:
    key = settings.PRIVACY_AUDIT_HMAC_KEY.encode("utf-8")
    if len(key) < 32:
        raise DeletionLedgerError("PRIVACY_AUDIT_HMAC_KEY is not configured")
    return key


def _canonical_payload(payload: dict[str, Any]) -> bytes:
    unsigned = {key: value for key, value in payload.items() if key != "integrity"}
    return json.dumps(
        unsigned,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _signature(payload: dict[str, Any]) -> str:
    digest = hmac.new(
        _privacy_key(),
        _SIGNATURE_CONTEXT + _canonical_payload(payload),
        hashlib.sha256,
    ).hexdigest()
    return f"hmac-sha256:{digest}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def build_deletion_ledger(db: AsyncSession) -> dict[str, Any]:
    markers = list(
        (
            await db.scalars(
                select(AccountDeletionMarker).order_by(
                    AccountDeletionMarker.deleted_at,
                    AccountDeletionMarker.receipt_id,
                )
            )
        ).all()
    )
    payload: dict[str, Any] = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "markers": [
            {
                "receipt_id": str(marker.receipt_id),
                "subject_digest": marker.subject_digest,
                "deleted_at": _as_utc(marker.deleted_at).isoformat(),
                "policy_version": marker.policy_version,
            }
            for marker in markers
        ],
    }
    payload["integrity"] = _signature(payload)
    return payload


def _validated_markers(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise DeletionLedgerError("deletion ledger must be a JSON object")
    if payload.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise DeletionLedgerError("unsupported deletion ledger schema")
    supplied = payload.get("integrity")
    if not isinstance(supplied, str) or not hmac.compare_digest(
        supplied, _signature(payload)
    ):
        raise DeletionLedgerError("deletion ledger integrity check failed")
    raw_markers = payload.get("markers")
    if not isinstance(raw_markers, list):
        raise DeletionLedgerError("deletion ledger markers must be a list")

    validated: list[dict[str, Any]] = []
    seen_receipts: set[uuid.UUID] = set()
    seen_digests: set[str] = set()
    for raw in raw_markers:
        if not isinstance(raw, dict) or set(raw) != {
            "receipt_id",
            "subject_digest",
            "deleted_at",
            "policy_version",
        }:
            raise DeletionLedgerError("deletion ledger marker has invalid fields")
        try:
            receipt_id = uuid.UUID(raw["receipt_id"])
            deleted_at = datetime.fromisoformat(raw["deleted_at"])
        except (TypeError, ValueError, AttributeError) as exc:
            raise DeletionLedgerError("deletion ledger marker is malformed") from exc
        digest = raw["subject_digest"]
        policy = raw["policy_version"]
        if deleted_at.tzinfo is None:
            raise DeletionLedgerError("deletion timestamp must include a timezone")
        if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
            raise DeletionLedgerError("subject digest must be lowercase SHA-256 hex")
        if not isinstance(policy, str) or not policy or len(policy) > 64:
            raise DeletionLedgerError("deletion policy version is invalid")
        if receipt_id in seen_receipts or digest in seen_digests:
            raise DeletionLedgerError("deletion ledger contains duplicate markers")
        seen_receipts.add(receipt_id)
        seen_digests.add(digest)
        validated.append(
            {
                "receipt_id": receipt_id,
                "subject_digest": digest,
                "deleted_at": deleted_at.astimezone(timezone.utc),
                "policy_version": policy,
            }
        )
    return validated


async def merge_deletion_ledger(db: AsyncSession, payload: Any) -> int:
    markers = _validated_markers(payload)
    added = 0
    for marker in markers:
        existing = await db.scalar(
            select(AccountDeletionMarker).where(
                or_(
                    AccountDeletionMarker.receipt_id == marker["receipt_id"],
                    AccountDeletionMarker.subject_digest == marker["subject_digest"],
                )
            )
        )
        if existing is None:
            db.add(AccountDeletionMarker(**marker))
            added += 1
            continue
        if (
            existing.receipt_id != marker["receipt_id"]
            or existing.subject_digest != marker["subject_digest"]
            or _as_utc(existing.deleted_at) != marker["deleted_at"]
            or existing.policy_version != marker["policy_version"]
        ):
            raise DeletionLedgerError("deletion ledger conflicts with database marker")
    await db.commit()
    return added


def write_ledger(path: Path, payload: dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=True, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


async def _run(command: str, path: Path | None) -> int:
    async with async_session() as db:
        if command == "export":
            assert path is not None
            payload = await build_deletion_ledger(db)
            write_ledger(path, payload)
            print(f"deletion ledger exported: markers={len(payload['markers'])}")
            return 0
        if command == "import":
            assert path is not None
            payload = json.loads(path.read_text(encoding="utf-8"))
            added = await merge_deletion_ledger(db, payload)
            try:
                await ensure_no_restored_deleted_subjects(db)
            except RuntimeError:
                print("deletion ledger imported; restored identity detected")
                return 2
            print(f"deletion ledger imported: added={added}")
            return 0
        await ensure_no_restored_deleted_subjects(db)
        print("deletion restore check: PASS")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 9 deletion marker ledger")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("export", "import"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("path", type=Path)
    subparsers.add_parser("check")
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args.command, getattr(args, "path", None)))
    except (DeletionLedgerError, json.JSONDecodeError, OSError) as exc:
        print(f"deletion ledger command failed: {type(exc).__name__}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
