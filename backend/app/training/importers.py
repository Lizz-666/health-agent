"""Deterministic non-media upstream-metadata import adapter (Task 2).

Maps ONLY whitelisted non-media metadata (names, taxonomy, equipment, target /
secondary muscles) from an external dataset shape into ``needs_review``
``ImportedExerciseDraft`` objects. It explicitly strips known upstream media and
instruction / translation fields, and RAISES on any unrecognized media-like
field so untrusted content cannot smuggle media in under a new name.

Hard guarantees (spec: Source And License Baseline, Safety):

- The adapter can NEVER emit ``approved``; output is always ``needs_review``.
- It excludes upstream instruction / translation text and every media field
  (``images`` / ``videos`` / GIFs / thumbnails / ``image`` / ``gif_url`` /
  ``media_id`` / media attribution payloads).
- Unsupported equipment (anything outside bodyweight / resistance_band) is a
  deterministic rejection, never a silent default.
- It is PURE and synchronous; no network access is needed or performed, so the
  tests run against synthetic fixtures only.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.training.schemas import (
    Difficulty,
    Equipment,
    ImportedExerciseDraft,
)

# Known upstream fields that are forbidden in Phase 3 output. Their PRESENCE is
# recorded in ``excluded_fields`` (proving the strip happened) but their VALUES
# never reach the draft.
FORBIDDEN_FIELDS = frozenset({
    "instructions", "translations",
    "images", "videos", "image", "gif_url", "media_id",
    "thumbnail", "thumbnails", "photos", "pictures", "media_attribution",
})

# Substrings that flag an UNRECOGNIZED field as media-like. An unknown field
# whose name contains one of these is rejected (not silently kept) so a renamed
# media payload cannot slip through.
_MEDIA_LIKE_TOKENS = (
    "image", "video", "gif", "media", "url", "thumb",
    "photo", "picture", "pic",
)

# Whitelisted upstream fields the adapter is allowed to read. Anything else that
# is not forbidden / media-like is ignored and recorded as ignored (not mapped).
WHITELISTED_FIELDS = frozenset({
    "id", "name",
    "force", "level", "mechanic", "equipment", "category",
    "primaryMuscles", "secondaryMuscles",
})

# Upstream equipment string -> Phase 3 Equipment. Values outside bodyweight /
# resistance_band are unsupported and rejected.
EQUIPMENT_MAP: Dict[str, Equipment] = {
    "body weight": Equipment.bodyweight,
    "bodyweight": Equipment.bodyweight,
    "bands": Equipment.resistance_band,
    "band": Equipment.resistance_band,
    "resistance band": Equipment.resistance_band,
    "resistance bands": Equipment.resistance_band,
    "elastic band": Equipment.resistance_band,
}

# Upstream "level" -> Phase 3 Difficulty.
LEVEL_MAP: Dict[str, Difficulty] = {
    "beginner": Difficulty.beginner,
    "intermediate": Difficulty.intermediate,
    "expert": Difficulty.advanced,
}


class ImportError(ValueError):
    """Base error for a deterministic import rejection."""


class UnsupportedEquipmentError(ImportError):
    """The upstream equipment is outside Phase 3 bodyweight / band scope."""


class UnrecognizedMediaFieldError(ImportError):
    """An unknown field whose name looks like media was not allowed."""


class MissingRequiredFieldError(ImportError):
    """A whitelisted required field (id / name / supported equipment) is absent."""


def _split_field(name: str) -> bool:
    """Return True if an unknown field name looks media-like."""
    low = name.lower()
    return any(tok in low for tok in _MEDIA_LIKE_TOKENS)


def _map_equipment(raw: Any) -> List[Equipment]:
    """Map upstream equipment to Phase 3 Equipment, rejecting unsupported ones."""
    if raw is None:
        return []
    values: List[str] = []
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list):
        values = [str(v) for v in raw]
    else:
        raise UnsupportedEquipmentError(
            f"unsupported equipment shape: {raw!r}"
        )
    out: List[Equipment] = []
    for v in values:
        key = v.strip().lower()
        if not key:
            continue
        mapped = EQUIPMENT_MAP.get(key)
        if mapped is None:
            raise UnsupportedEquipmentError(
                f"equipment {v!r} is outside Phase 3 bodyweight/band scope"
            )
        if mapped not in out:
            out.append(mapped)
    return out


def _collect_patterns(record: Dict[str, Any]) -> List[str]:
    """Collect taxonomy tokens (force / mechanic / category) deterministically."""
    out: List[str] = []
    for key in ("force", "mechanic", "category"):
        val = record.get(key)
        if isinstance(val, str) and val.strip():
            token = val.strip().lower()
            if token not in out:
                out.append(token)
    return out


def _collect_muscles(raw: Any) -> List[str]:
    """Collect muscle names from an upstream list, deduplicated, lowercased."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            token = item.strip().lower()
            if token not in out:
                out.append(token)
    return out


def import_upstream_record(
    record: Dict[str, Any],
    *,
    source_id: str,
    source_pinned_version: str,
) -> ImportedExerciseDraft:
    """Map ONE upstream-shaped record into a ``needs_review`` draft.

    Raises ``MissingRequiredFieldError`` / ``UnsupportedEquipmentError`` /
    ``UnrecognizedMediaFieldError`` on deterministic rejections. The returned
    draft is structurally incomplete (no safety / posture / prescription /
    illustration) and is therefore never recommendation-ready.
    """
    if not isinstance(record, dict):
        raise ImportError("upstream record must be a JSON object")

    excluded_fields: List[str] = []
    ignored_fields: List[str] = []
    for key in record.keys():
        if key in FORBIDDEN_FIELDS:
            excluded_fields.append(key)
            continue
        if key in WHITELISTED_FIELDS:
            continue
        if _split_field(key):
            raise UnrecognizedMediaFieldError(
                f"unrecognized media-like field {key!r} is not allowed"
            )
        ignored_fields.append(key)

    raw_id = record.get("id")
    if not isinstance(raw_id, str) or not raw_id.strip():
        raise MissingRequiredFieldError("upstream record missing string 'id'")
    exercise_id = raw_id.strip()

    raw_name = record.get("name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise MissingRequiredFieldError(
            f"record {exercise_id!r} missing string 'name'"
        )
    name_en = raw_name.strip()

    equipment = _map_equipment(record.get("equipment"))
    if not equipment:
        raise MissingRequiredFieldError(
            f"record {exercise_id!r} has no Phase 3 supported equipment"
        )

    movement_patterns = _collect_patterns(record)
    if not movement_patterns:
        movement_patterns = ["unspecified_pattern"]

    primary_muscles = _collect_muscles(record.get("primaryMuscles"))
    if not primary_muscles:
        raise MissingRequiredFieldError(
            f"record {exercise_id!r} has no primary muscles"
        )
    secondary_muscles = _collect_muscles(record.get("secondaryMuscles"))

    raw_level = record.get("level")
    difficulty: Optional[Difficulty] = None
    if isinstance(raw_level, str) and raw_level.strip():
        difficulty = LEVEL_MAP.get(raw_level.strip().lower())

    imported_fields = ["id", "name", "equipment", "primaryMuscles"]
    if movement_patterns != ["unspecified_pattern"]:
        imported_fields.append("taxonomy")
    if secondary_muscles:
        imported_fields.append("secondaryMuscles")
    if difficulty is not None:
        imported_fields.append("level")

    return ImportedExerciseDraft(
        exercise_id=exercise_id,
        name_en=name_en,
        equipment=equipment,
        movement_patterns=movement_patterns,
        primary_muscles=primary_muscles,
        secondary_muscles=secondary_muscles,
        difficulty=difficulty,
        imported_fields=imported_fields,
        excluded_fields=excluded_fields,
        review_status="needs_review",  # type: ignore[arg-type]
        source_id=source_id,
        source_pinned_version=source_pinned_version,
    )


def import_upstream_records(
    records: List[Dict[str, Any]],
    *,
    source_id: str,
    source_pinned_version: str,
) -> List[ImportedExerciseDraft]:
    """Map a list of upstream records. Any rejection aborts the whole batch."""
    return [
        import_upstream_record(
            r,
            source_id=source_id,
            source_pinned_version=source_pinned_version,
        )
        for r in records
    ]
