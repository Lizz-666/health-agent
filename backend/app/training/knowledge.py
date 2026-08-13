"""Fail-closed catalog + source-manifest loaders and the recommendation-ready
invariant engine (Task 2; extended by Task 3).

Two layers of checking (spec: Domain Model, Recommendation-Ready Invariant,
Safety/Failure Handling):

1. STRUCTURAL (load-time, raises ``CatalogValidationError``):
   - unknown fields, duplicate IDs, unsupported schema/manifest versions
   - missing/empty required fields (Pydantic models, ``extra="forbid"``)
   - relation errors: unresolved relation IDs, self-relations, progression /
     regression cycles
   - external media / URLs in ANY exercise field
   - unsupported equipment (enum already; reaffirmed)
   A structural failure is explicit and NEVER yields an empty-but-successful
   catalog.

2. RECOMMENDATION-READY (per-exercise gate, ``recommendation_ready``):
   - review_status == approved (provenance AND illustration)
   - review_scope == personal_development (Phase 3 runtime scope)
   - reviewed_at <= published_at (provenance AND illustration)
   - every relation resolves to an existing APPROVED exercise
   - conservative bounds never exceed normal bounds
   Non-ready exercises may exist in a file but can never be selected.

Everything here is PURE: no HTTP, no DB, no LLM, no network.
"""
from __future__ import annotations

import json
import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Union

from app.training.schemas import (
    Exercise,
    ExerciseCatalog,
    SourceManifest,
)

_ITEM_REVIEW_SOURCE_TYPES = frozenset({
    "guideline", "position_stand", "professional_reference",
})

SUPPORTED_CATALOG_SCHEMA_VERSIONS = frozenset({"v1"})
SUPPORTED_MANIFEST_VERSIONS = frozenset({"v1"})

# Phrases that indicate external media / remote references in free text. The
# illustration model already blocks URL fields structurally; this scans authored
# text fields so an external link cannot hide in instructions or stop text.
_EXTERNAL_MEDIA_PATTERNS = (
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"(^|[^a-zA-Z])www\.", re.IGNORECASE),
    re.compile(r"data:image/", re.IGNORECASE),
    re.compile(r"(^|[^a-zA-Z])//[^/]"),  # protocol-relative "//host"
)


class CatalogValidationError(ValueError):
    """Raised when a catalog fails structural validation.

    Carries a list of ``CatalogIssue`` so callers (and tests) can assert the
    exact failure codes rather than grepping prose.
    """

    def __init__(self, issues: List["CatalogIssue"]) -> None:
        self.issues = issues
        lines = [f"[{i.scope}] {i.code}: {i.detail}" for i in issues]
        super().__init__("catalog validation failed:\n" + "\n".join(lines))


@dataclass(frozen=True)
class CatalogIssue:
    """One structured validation finding (scope = catalog or exercise_id)."""

    scope: str
    code: str
    detail: str


@dataclass(frozen=True)
class RecommendationResult:
    """Outcome of the recommendation-ready gate for one exercise."""

    exercise_id: str
    ready: bool
    issues: List[CatalogIssue] = field(default_factory=list)


def _read_json(path: Union[str, Path]) -> dict:
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_source_manifest(path: Union[str, Path]) -> SourceManifest:
    """Load and validate the global source manifest (fail-closed)."""
    data = _read_json(path)
    manifest = SourceManifest.model_validate(data)
    if manifest.manifest_version not in SUPPORTED_MANIFEST_VERSIONS:
        raise CatalogValidationError([
            CatalogIssue(
                scope="manifest",
                code="unsupported_manifest_version",
                detail=(
                    f"manifest_version {manifest.manifest_version!r} not in "
                    f"{sorted(SUPPORTED_MANIFEST_VERSIONS)}"
                ),
            )
        ])
    seen: Dict[str, int] = {}
    for entry in manifest.sources:
        if entry.source_id in seen:
            raise CatalogValidationError([
                CatalogIssue(
                    scope="manifest",
                    code="duplicate_source_id",
                    detail=f"source_id {entry.source_id!r} appears twice",
                )
            ])
        seen[entry.source_id] = 1
    return manifest


def build_index(catalog: ExerciseCatalog) -> Dict[str, Exercise]:
    """Return exercise_id -> Exercise for a catalog (last one wins on dup,
    but duplicate IDs are rejected at load time so this is unambiguous)."""
    return {ex.exercise_id: ex for ex in catalog.exercises}


def _scan_text_for_media(exercise: Exercise) -> List[CatalogIssue]:
    """Scan every authored string field for external-media / URL patterns."""
    fields = [
        exercise.names.name_en, exercise.names.name_zh,
        *exercise.movement_patterns, *exercise.movement_purposes,
        *exercise.primary_muscles, *exercise.secondary_muscles,
        *exercise.applicable_posture_signals,
        *exercise.not_applicable_posture_signals,
        *exercise.instruction_steps, *exercise.form_cues,
        *exercise.common_mistakes,
        exercise.illustration.asset_key,
        exercise.illustration.alt_text_en,
        exercise.illustration.alt_text_zh,
    ]
    for sc in exercise.stop_conditions:
        fields.extend([sc.code, sc.display_text_en, sc.display_text_zh])
    issues: List[CatalogIssue] = []
    for value in fields:
        for pattern in _EXTERNAL_MEDIA_PATTERNS:
            if pattern.search(value):
                issues.append(CatalogIssue(
                    scope=exercise.exercise_id,
                    code="external_media_in_text",
                    detail=(
                        f"field value matches external-media pattern "
                        f"{pattern.pattern!r}"
                    ),
                ))
                break
    return issues


def _has_cycle(edges: Dict[str, List[str]]) -> bool:
    """Return True if the directed graph ``edges`` contains a cycle."""
    color: Dict[str, int] = {}  # 0=unvisited 1=in-progress 2=done

    def visit(node: str) -> bool:
        color[node] = 1
        for nxt in edges.get(node, []):
            if color.get(nxt, 0) == 1:
                return True
            if color.get(nxt, 0) == 0 and visit(nxt):
                return True
        color[node] = 2
        return False

    for start in edges:
        if color.get(start, 0) == 0 and visit(start):
            return True
    return False


def _validate_structure(catalog: ExerciseCatalog) -> List[CatalogIssue]:
    """Run all STRUCTURAL (load-time) checks. Returns [] when sound."""
    issues: List[CatalogIssue] = []

    if catalog.schema_version not in SUPPORTED_CATALOG_SCHEMA_VERSIONS:
        issues.append(CatalogIssue(
            scope="catalog",
            code="unsupported_schema_version",
            detail=(
                f"schema_version {catalog.schema_version!r} not in "
                f"{sorted(SUPPORTED_CATALOG_SCHEMA_VERSIONS)}"
            ),
        ))

    # Duplicate IDs.
    seen: Dict[str, int] = {}
    for ex in catalog.exercises:
        seen[ex.exercise_id] = seen.get(ex.exercise_id, 0) + 1
    for eid, count in seen.items():
        if count > 1:
            issues.append(CatalogIssue(
                scope=eid,
                code="duplicate_exercise_id",
                detail=f"exercise_id {eid!r} appears {count} times",
            ))

    index = build_index(catalog)

    # Relations resolve to an existing exercise; no self-reference.
    relation_kinds = (
        ("progression_ids", "progression"),
        ("regression_ids", "regression"),
        ("substitution_ids", "substitution"),
    )
    for ex in catalog.exercises:
        for attr, label in relation_kinds:
            ids = getattr(ex, attr)
            for rid in ids:
                if rid == ex.exercise_id:
                    issues.append(CatalogIssue(
                        scope=ex.exercise_id,
                        code="relation_self",
                        detail=f"{label} references itself",
                    ))
                elif rid not in index:
                    issues.append(CatalogIssue(
                        scope=ex.exercise_id,
                        code="relation_unresolved",
                        detail=(
                            f"{label} id {rid!r} does not exist in catalog"
                        ),
                    ))

    # Progression / regression must be acyclic (ordinal difficulty ordering).
    progress_edges: Dict[str, List[str]] = {}
    regress_edges: Dict[str, List[str]] = {}
    for ex in catalog.exercises:
        progress_edges[ex.exercise_id] = list(ex.progression_ids)
        regress_edges[ex.exercise_id] = list(ex.regression_ids)
    if _has_cycle(progress_edges):
        issues.append(CatalogIssue(
            scope="catalog",
            code="progression_cycle",
            detail="progression graph contains a cycle",
        ))
    if _has_cycle(regress_edges):
        issues.append(CatalogIssue(
            scope="catalog",
            code="regression_cycle",
            detail="regression graph contains a cycle",
        ))

    # External media / URL scan over every authored text field.
    for ex in catalog.exercises:
        issues.extend(_scan_text_for_media(ex))

    return issues


def _conservative_within_normal(ex: Exercise) -> List[CatalogIssue]:
    """Conservative bounds must be at least as strict as normal bounds."""
    p = ex.prescription
    issues: List[CatalogIssue] = []
    if p.conservative_sets_max > p.sets_max:
        issues.append(CatalogIssue(
            scope=ex.exercise_id,
            code="conservative_exceeds_normal",
            detail="conservative_sets_max > sets_max",
        ))
    if p.mode.value == "reps":
        if p.reps_max is None or p.conservative_reps_max is None:
            issues.append(CatalogIssue(
                scope=ex.exercise_id,
                code="reps_bounds_incomplete",
                detail="mode=reps requires reps_max and conservative_reps_max",
            ))
        elif p.conservative_reps_max > p.reps_max:
            issues.append(CatalogIssue(
                scope=ex.exercise_id,
                code="conservative_exceeds_normal",
                detail="conservative_reps_max > reps_max",
            ))
    else:  # duration
        if (p.duration_seconds_max is None
                or p.conservative_duration_seconds_max is None):
            issues.append(CatalogIssue(
                scope=ex.exercise_id,
                code="duration_bounds_incomplete",
                detail="mode=duration requires duration + conservative max",
            ))
        elif (p.conservative_duration_seconds_max
                > p.duration_seconds_max):
            issues.append(CatalogIssue(
                scope=ex.exercise_id,
                code="conservative_exceeds_normal",
                detail="conservative_duration_seconds_max > duration max",
            ))
    return issues


def recommendation_ready(
    exercise: Exercise,
    index: Dict[str, Exercise],
    published_at: date,
) -> RecommendationResult:
    """Evaluate the recommendation-ready invariant for one exercise.

    Returns a ``RecommendationResult`` (``ready`` is True only when there are
    zero issues). Never raises; callers decide how to use non-ready results.
    """
    issues: List[CatalogIssue] = []
    eid = exercise.exercise_id
    prov = exercise.provenance
    ill = exercise.illustration.provenance

    if prov.content_version == "" or not prov.content_version:
        issues.append(CatalogIssue(
            eid, "content_version_missing", "provenance content_version missing"))
    if not any(source.source_type.value in _ITEM_REVIEW_SOURCE_TYPES
               for source in prov.sources):
        issues.append(CatalogIssue(
            eid, "item_review_source_missing",
            "approved item lacks a guideline, position stand, or professional "
            "exercise reference"))

    if prov.review_status.value != "approved":
        issues.append(CatalogIssue(eid, "review_status_not_approved",
                                   f"provenance review_status="
                                   f"{prov.review_status.value}"))
    if ill.review_status.value != "approved":
        issues.append(CatalogIssue(eid, "illustration_not_approved",
                                   f"illustration review_status="
                                   f"{ill.review_status.value}"))
    if prov.review_scope.value != "personal_development":
        issues.append(CatalogIssue(
            eid, "review_scope_not_personal_development",
            f"provenance review_scope={prov.review_scope.value}",
        ))
    if ill.review_scope.value != "personal_development":
        issues.append(CatalogIssue(
            eid, "illustration_scope_not_personal_development",
            f"illustration review_scope={ill.review_scope.value}",
        ))
    if prov.reviewed_at > published_at:
        issues.append(CatalogIssue(
            eid, "reviewed_after_publication",
            f"provenance reviewed_at {prov.reviewed_at} > "
            f"published_at {published_at}",
        ))
    if ill.reviewed_at > published_at:
        issues.append(CatalogIssue(
            eid, "illustration_reviewed_after_publication",
            f"illustration reviewed_at {ill.reviewed_at} > "
            f"published_at {published_at}",
        ))

    # Relations must resolve to existing APPROVED exercises.
    for attr, label in (
        ("progression_ids", "progression"),
        ("regression_ids", "regression"),
        ("substitution_ids", "substitution"),
    ):
        for rid in getattr(exercise, attr):
            target = index.get(rid)
            if target is None:
                issues.append(CatalogIssue(
                    eid, "relation_unresolved",
                    f"{label} id {rid!r} not in catalog",
                ))
            elif target.provenance.review_status.value != "approved":
                issues.append(CatalogIssue(
                    eid, "relation_not_approved",
                    f"{label} id {rid!r} is not approved",
                ))

    issues.extend(_conservative_within_normal(exercise))
    return RecommendationResult(eid, ready=not issues, issues=issues)


def validate_catalog(catalog: ExerciseCatalog) -> List[CatalogIssue]:
    """Run structural checks ONLY. Returns [] when the catalog is sound.

    (Per-exercise recommendation-ready gating is a separate, non-fatal layer.)
    """
    return _validate_structure(catalog)


def _validate_release_files(
    catalog: ExerciseCatalog, catalog_path: Path
) -> List[CatalogIssue]:
    """Cross-check the canonical release against its manifest and local art."""
    manifest_path = catalog_path.with_name("source_manifest.v1.json")
    if not manifest_path.exists():
        return [CatalogIssue(
            "catalog", "source_manifest_missing",
            "strict catalog loading requires source_manifest.v1.json")]
    manifest = load_source_manifest(manifest_path)
    issues: List[CatalogIssue] = []
    if manifest.manifest_version != catalog.source_manifest_version:
        issues.append(CatalogIssue(
            "catalog", "source_manifest_version_mismatch",
            "catalog and source manifest versions differ"))
    registered = {entry.source_id: entry for entry in manifest.sources}
    for exercise in catalog.exercises:
        if exercise.provenance.content_version != catalog.content_version:
            issues.append(CatalogIssue(
                exercise.exercise_id, "content_version_mismatch",
                "exercise provenance is not bound to catalog content_version"))
        for source in exercise.provenance.sources:
            manifest_source = registered.get(source.source_id)
            item_reference = source.source_id == "ace-exercise-references-2026"
            url_matches = (
                source.url.startswith(manifest_source.url)
                if manifest_source is not None and item_reference
                else manifest_source is not None
                and source.url == manifest_source.url
            )
            if manifest_source is None:
                issues.append(CatalogIssue(
                    exercise.exercise_id, "unregistered_source",
                    f"source {source.source_id!r} is absent from manifest"))
            elif (
                source.source_type != manifest_source.source_type
                or source.pinned_version != manifest_source.pinned_version
                or not url_matches
                or source.license != manifest_source.license
            ):
                issues.append(CatalogIssue(
                    exercise.exercise_id, "source_manifest_mismatch",
                    f"source {source.source_id!r} does not match its manifest pin"))

    repo_root = next(
        (parent for parent in catalog_path.resolve().parents
         if (parent / "assets" / "training" / "illustrations").is_dir()),
        None,
    )
    if repo_root is None:
        issues.append(CatalogIssue(
            "catalog", "asset_root_missing", "repository asset root not found"))
        return issues
    asset_root = (repo_root / "assets" / "training" / "illustrations").resolve()
    for exercise in catalog.exercises:
        asset = (repo_root / exercise.illustration.asset_key).resolve()
        try:
            asset.relative_to(asset_root)
        except ValueError:
            issues.append(CatalogIssue(
                exercise.exercise_id, "illustration_path_escape",
                "illustration asset resolves outside the approved asset root"))
            continue
        if not asset.is_file():
            issues.append(CatalogIssue(
                exercise.exercise_id, "illustration_missing",
                f"local asset {exercise.illustration.asset_key!r} is missing"))
            continue
        digest = hashlib.sha256(asset.read_bytes()).hexdigest()
        if digest != exercise.illustration.provenance.content_hash:
            issues.append(CatalogIssue(
                exercise.exercise_id, "illustration_hash_mismatch",
                f"local asset {exercise.illustration.asset_key!r} hash differs"))
        issues.extend(_validate_svg_content(exercise.exercise_id, asset))
    return issues


def _validate_svg_content(exercise_id: str, asset: Path) -> List[CatalogIssue]:
    """Reject active, embedded, or externally referenced SVG content."""
    raw = asset.read_bytes()
    lowered = raw.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        return [CatalogIssue(
            exercise_id, "illustration_unsafe_content",
            "SVG declarations and entities are forbidden")]
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return [CatalogIssue(
            exercise_id, "illustration_unsafe_content", "SVG is not valid XML")]
    forbidden_tags = {"script", "image", "foreignobject"}
    forbidden_values = (
        "javascript:", "data:", "url(", "http://", "https://", "//",
    )
    for element in root.iter():
        local_tag = element.tag.rsplit("}", 1)[-1].lower()
        if local_tag in forbidden_tags:
            return [CatalogIssue(
                exercise_id, "illustration_unsafe_content",
                f"SVG element {local_tag!r} is forbidden")]
        values = list(element.attrib.values())
        if element.text:
            values.append(element.text)
        if any(token in value.lower() for value in values
               for token in forbidden_values):
            return [CatalogIssue(
                exercise_id, "illustration_unsafe_content",
                "SVG contains an embedded or external reference")]
    return []


def load_catalog(
    path: Union[str, Path], *, verify_release: bool = True
) -> ExerciseCatalog:
    """Load + structurally validate a catalog. Fail-closed (raises on issues)."""
    data = _read_json(path)
    try:
        catalog = ExerciseCatalog.model_validate(data)
    except Exception:  # noqa: BLE001 - surface as a single structured error
        raise
    issues = validate_catalog(catalog)
    if verify_release:
        issues.extend(_validate_release_files(catalog, Path(path)))
    if issues:
        raise CatalogValidationError(issues)
    return catalog


def ready_exercises(
    catalog: ExerciseCatalog,
    index: Optional[Dict[str, Exercise]] = None,
) -> List[Exercise]:
    """Return only the recommendation-ready exercises, preserving order."""
    if index is None:
        index = build_index(catalog)
    out: List[Exercise] = []
    for ex in catalog.exercises:
        res = recommendation_ready(ex, index, catalog.published_at)
        if res.ready:
            out.append(ex)
    return out
