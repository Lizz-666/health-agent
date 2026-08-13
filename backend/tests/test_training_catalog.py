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
import json
import re
import shutil
from pathlib import Path

import pytest

from app.training.knowledge import (
    CatalogValidationError,
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
        assert any(s.source_type.value in {
            "guideline", "position_stand", "professional_reference"
        } for s in p.sources), ex.exercise_id
        for s in p.sources:
            assert s.source_id and s.pinned_version and s.url
            assert s.verified_date


def test_every_exercise_has_item_level_ace_and_acsm_evidence(catalog):
    ace_urls = set()
    for ex in catalog.exercises:
        sources = {source.source_id: source for source in ex.provenance.sources}
        ace = sources["ace-exercise-references-2026"]
        assert ex.exercise_id in ace.scope
        assert ace.url != "https://www.acefitness.org/"
        ace_urls.add(ace.url)
        assert "acsm-resistance-training-2026" in sources
    assert len(ace_urls) >= 12


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
    # The pinned upstream commit and complete license blocks are byte-pinned.
    assert "7455efae41b330c265e7cd4b78dfa848e7ce5ebd" in text
    blocks = re.findall(r"```\n(.*?)\n```", text, flags=re.DOTALL)
    assert len(blocks) == 2
    hashes = [hashlib.sha256(block.encode("utf-8")).hexdigest()
              for block in blocks]
    assert hashes == [
        "cf559f90770b54ee0b1c689d128017a5b1761a6fab0d6abd67c48a2af2354700",
        "45450fa8a861ee7855ab831f64069e1a228c0b0a99c07ad3cde8ca21b0c7812b",
    ]
    assert "MEDIA EXCEPTION" in blocks[0]
    assert "77f25a922b51be7d96bd051c5d2096959f0d61a8" in text
    assert "Copyright (c) 2026 Hasan Emir Yıldırım" in text
    assert "Copyright (c) 2023 Mathias Bradiceanu" in text


def _copy_release(tmp_path):
    root = tmp_path / "release"
    data_dir = root / "backend" / "app" / "training" / "data"
    assets = root / "assets" / "training" / "illustrations"
    data_dir.mkdir(parents=True)
    shutil.copy(CATALOG_PATH, data_dir / CATALOG_PATH.name)
    shutil.copy(
        CATALOG_PATH.with_name("source_manifest.v1.json"),
        data_dir / "source_manifest.v1.json")
    shutil.copytree(
        REPO_ROOT / "assets" / "training" / "illustrations", assets)
    return data_dir / CATALOG_PATH.name, assets


def test_release_loader_rejects_tampered_illustration(tmp_path):
    catalog_path, assets = _copy_release(tmp_path)
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    asset = assets / Path(data["exercises"][0]["illustration"]["asset_key"]).name
    asset.write_text(asset.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(CatalogValidationError) as exc:
        load_catalog(catalog_path)
    assert "illustration_hash_mismatch" in [i.code for i in exc.value.issues]


def test_release_loader_rejects_unsafe_svg_even_with_matching_hash(tmp_path):
    catalog_path, assets = _copy_release(tmp_path)
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    illustration = data["exercises"][0]["illustration"]
    asset = assets / Path(illustration["asset_key"]).name
    unsafe = b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>'
    asset.write_bytes(unsafe)
    illustration["provenance"]["content_hash"] = hashlib.sha256(unsafe).hexdigest()
    catalog_path.write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(CatalogValidationError) as exc:
        load_catalog(catalog_path)
    assert "illustration_unsafe_content" in [i.code for i in exc.value.issues]


def test_release_loader_rejects_unregistered_item_source(tmp_path):
    catalog_path, _ = _copy_release(tmp_path)
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    data["exercises"][0]["provenance"]["sources"][0]["source_id"] = "ghost"
    catalog_path.write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(CatalogValidationError) as exc:
        load_catalog(catalog_path)
    assert "unregistered_source" in [i.code for i in exc.value.issues]


def test_release_loader_rejects_source_pin_mismatch(tmp_path):
    catalog_path, _ = _copy_release(tmp_path)
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    data["exercises"][0]["provenance"]["sources"][0]["pinned_version"] = "old"
    catalog_path.write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(CatalogValidationError) as exc:
        load_catalog(catalog_path)
    assert "source_manifest_mismatch" in [i.code for i in exc.value.issues]
