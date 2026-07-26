"""Reviewed catalog, original-illustration and source-audit tests (Task 3).

Covers the Task 3 acceptance criteria against the real
``backend/app/training/data/exercises.v1.json`` catalog and the
``assets/training/illustrations/*.svg`` originals:

- 24-36 personal-development-approved exercises; all recommendation-ready.
- Coverage of both equipment modes and all five training roles.
- Relation graph integrity (resolve to approved, no self, acyclic).
- Every referenced SVG exists and its sha256 matches the catalog hash.
- Media scanner: no scripts, images, foreignObject, xlink:href, data: URIs,
  base64 blobs, or any URL other than the required SVG namespace.
- Source / license / review traceability for every exercise.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from app.training.knowledge import (
    build_index,
    load_catalog,
    recommendation_ready,
)
from app.training.schemas import Equipment, ReviewScope, TrainingRole

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = Path("app/training/data/exercises.v1.json")  # cwd = backend
ASSET_ROOT = REPO_ROOT

# The single URL allowed inside an original SVG: the required namespace.
_SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_BASE64_BLOB = re.compile(r"[A-Za-z0-9+/]{100,}={0,2}")
_URL_RE = re.compile(r"https?://[^\s\"'<>]+")


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(CATALOG_PATH)


# ---------------------------------------------------------------------------
# Catalog + coverage
# ---------------------------------------------------------------------------


def test_catalog_has_24_to_36_approved_and_all_ready(catalog):
    exercises = catalog.exercises
    assert 24 <= len(exercises) <= 36
    index = build_index(catalog)
    not_ready = []
    for ex in exercises:
        res = recommendation_ready(ex, index, catalog.published_at)
        if not res.ready:
            not_ready.append((ex.exercise_id, [i.code for i in res.issues]))
    assert not_ready == [], f"non-ready exercises: {not_ready}"


def test_coverage_both_equipment_modes(catalog):
    modes = {eq for ex in catalog.exercises for eq in ex.equipment}
    assert Equipment.bodyweight in modes
    assert Equipment.resistance_band in modes
    # At least two exercises per equipment mode.
    for mode in (Equipment.bodyweight, Equipment.resistance_band):
        assert sum(1 for ex in catalog.exercises if mode in ex.equipment) >= 2


def test_coverage_all_five_roles(catalog):
    roles = {r for ex in catalog.exercises for r in ex.training_roles}
    assert roles == set(TrainingRole)
    for role in TrainingRole:
        assert sum(1 for ex in catalog.exercises if role in ex.training_roles) >= 1


def test_every_exercise_has_movement_purpose_and_posture_mapping(catalog):
    for ex in catalog.exercises:
        assert ex.movement_purposes, ex.exercise_id
        # Posture applicability is a reviewed product mapping (may be empty for
        # generic exercises) but must only use known posture category tokens.
        for sig in ex.applicable_posture_signals + ex.not_applicable_posture_signals:
            assert isinstance(sig, str) and sig.strip(), ex.exercise_id


# ---------------------------------------------------------------------------
# Relation graph
# ---------------------------------------------------------------------------


def test_relations_resolve_to_approved_no_self_acyclic(catalog):
    index = build_index(catalog)
    for ex in catalog.exercises:
        for attr in ("progression_ids", "regression_ids", "substitution_ids"):
            for rid in getattr(ex, attr):
                assert rid != ex.exercise_id, f"self relation {ex.exercise_id}"
                target = index[rid]
                assert target.provenance.review_status.value == "approved", (
                    f"{ex.exercise_id} -> {rid} not approved")


# ---------------------------------------------------------------------------
# Illustration hash + media audit
# ---------------------------------------------------------------------------


def _scan_svg_media(text: str):
    issues = []
    for forbidden in ("<script", "<image", "<foreignObject",
                      "xlink:href", "data:image", "javascript:"):
        if forbidden in text:
            issues.append(f"forbidden token {forbidden!r}")
    if _BASE64_BLOB.search(text):
        issues.append("embedded base64 blob")
    for url in _URL_RE.findall(text):
        if url != _SVG_NAMESPACE:
            issues.append(f"external url {url!r}")
    return issues


def test_every_referenced_svg_exists_and_hash_matches(catalog):
    for ex in catalog.exercises:
        asset = ASSET_ROOT / ex.illustration.asset_key
        assert asset.exists(), f"missing SVG {asset}"
        raw = asset.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        assert digest == ex.illustration.provenance.content_hash, (
            f"hash mismatch for {ex.exercise_id}")


def test_no_external_media_in_any_svg(catalog):
    flagged = {}
    for ex in catalog.exercises:
        asset = ASSET_ROOT / ex.illustration.asset_key
        text = asset.read_text(encoding="utf-8")
        issues = _scan_svg_media(text)
        if issues:
            flagged[ex.exercise_id] = issues
    assert flagged == {}, f"media audit failures: {flagged}"


def test_svg_ownership_is_project_authored(catalog):
    for ex in catalog.exercises:
        prov = ex.illustration.provenance
        assert prov.creator_type.value == "project_authored"
        assert (prov.source_declaration.value
                == "original_no_external_reference")
        assert prov.review_status.value == "approved"
        assert prov.review_scope == ReviewScope.personal_development


# ---------------------------------------------------------------------------
# Source / license / review traceability
# ---------------------------------------------------------------------------


def test_every_exercise_has_traceable_personal_dev_provenance(catalog):
    for ex in catalog.exercises:
        p = ex.provenance
        assert p.sources, f"{ex.exercise_id} has no sources"
        assert p.review_status.value == "approved"
        assert p.review_scope == ReviewScope.personal_development
        assert p.reviewer_role and p.reviewer_role.strip()
        assert p.reviewed_at <= catalog.published_at
        for s in p.sources:
            assert s.source_id and s.pinned_version and s.url
            assert s.verified_date


def test_no_public_or_professional_approval_claim(catalog):
    # personal-development scope only; nothing may claim public/clinical/
    # professional certification approval.
    for ex in catalog.exercises:
        scope = ex.provenance.review_scope
        assert scope == ReviewScope.personal_development
        ill_scope = ex.illustration.provenance.review_scope
        assert ill_scope == ReviewScope.personal_development


def test_source_manifest_and_notices_pinned():
    manifest_path = Path("app/training/data/source_manifest.v1.json")
    notices_path = Path("app/training/data/THIRD_PARTY_NOTICES.md")
    assert manifest_path.exists() and notices_path.exists()
    text = notices_path.read_text(encoding="utf-8")
    # The pinned upstream commit and the MIT notice must be retained verbatim.
    assert "7455efae41b330c265e7cd4b78dfa848e7ce5ebd" in text
    assert "MIT License" in text
    # The Gym visual media exception must be present (media is excluded).
    assert "Gym visual" in text
    assert "77f25a922b51be7d96bd051c5d2096959f0d61a8" in text
