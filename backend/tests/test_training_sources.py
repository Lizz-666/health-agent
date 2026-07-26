"""Loader, source-manifest and importer tests for Phase 3 Task 2.

Covers the STRUCTURAL (fail-closed) layer of the catalog loader and the
deterministic non-media import adapter, plus the global source manifest. All
data is synthetic; the only real artifact loaded is the project's own
``source_manifest.v1.json`` so the source/license pins stay covered.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.training.importers import (
    MissingRequiredFieldError,
    UnsupportedEquipmentError,
    UnrecognizedMediaFieldError,
    import_upstream_record,
)
from app.training.knowledge import (
    CatalogValidationError,
    build_index,
    load_catalog,
    load_source_manifest,
    recommendation_ready,
    validate_catalog,
)
from app.training.schemas import ExerciseCatalog, ReviewStatus

FIXTURE = Path("tests/fixtures/training/valid_catalog.json")
REAL_MANIFEST = Path("app/training/data/source_manifest.v1.json")


def _catalog_dict():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _structural_issues(mutator):
    data = _catalog_dict()
    mutator(data)
    catalog = ExerciseCatalog.model_validate(data)
    return validate_catalog(catalog)


def _codes(issues):
    return [i.code for i in issues]


# ---------------------------------------------------------------------------
# Source manifest
# ---------------------------------------------------------------------------


def test_real_manifest_loads_and_pins_sources():
    manifest = load_source_manifest(REAL_MANIFEST)
    assert manifest.manifest_version == "v1"
    ids = {s.source_id: s for s in manifest.sources}
    assert "hasaneyldrm-exercises-dataset" in ids
    assert (ids["hasaneyldrm-exercises-dataset"].pinned_version
            == "7455efae41b330c265e7cd4b78dfa848e7ce5ebd")
    assert ids["hasaneyldrm-exercises-dataset"].license == "MIT"
    assert "images" in ids["hasaneyldrm-exercises-dataset"].media_exclusion
    assert "snouzy-workout-cool" in ids
    assert (ids["snouzy-workout-cool"].pinned_version
            == "77f25a922b51be7d96bd051c5d2096959f0d61a8")


def test_manifest_duplicate_source_id_fails():
    data = {"manifest_version": "v1", "sources": [
        {"source_id": "dup", "source_type": "dataset", "name": "a",
         "pinned_version": "v1", "url": "https://a", "license": "MIT",
         "permitted_use": "x", "explicit_exclusion": "y", "media_exclusion": "z",
         "verified_date": "2026-07-26"},
        {"source_id": "dup", "source_type": "dataset", "name": "b",
         "pinned_version": "v1", "url": "https://b", "license": "MIT",
         "permitted_use": "x", "explicit_exclusion": "y", "media_exclusion": "z",
         "verified_date": "2026-07-26"}]}
    p = Path("tests/fixtures/training/_dup_manifest.json")
    p.write_text(json.dumps(data), encoding="utf-8")
    try:
        with pytest.raises(CatalogValidationError) as exc:
            load_source_manifest(p)
        assert "duplicate_source_id" in _codes(exc.value.issues)
    finally:
        p.unlink()


def test_manifest_unsupported_version_fails():
    data = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    data["manifest_version"] = "v9"
    p = Path("tests/fixtures/training/_bad_manifest.json")
    p.write_text(json.dumps(data), encoding="utf-8")
    try:
        with pytest.raises(CatalogValidationError) as exc:
            load_source_manifest(p)
        assert "unsupported_manifest_version" in _codes(exc.value.issues)
    finally:
        p.unlink()


# ---------------------------------------------------------------------------
# Catalog structural validation (fail-closed)
# ---------------------------------------------------------------------------


def test_valid_fixture_loads_all_ready(tmp_path):
    catalog = load_catalog(FIXTURE)
    assert catalog.catalog_id == "phase3-fixture-catalog"
    index = build_index(catalog)
    ready = [e for e in catalog.exercises
             if recommendation_ready(e, index, catalog.published_at).ready]
    assert len(ready) == 3


def test_duplicate_exercise_id_fails():
    def mut(d):
        d["exercises"][0]["exercise_id"] = d["exercises"][1]["exercise_id"]
    assert "duplicate_exercise_id" in _codes(_structural_issues(mut))


def test_unsupported_schema_version_fails():
    def mut(d):
        d["schema_version"] = "v9"
    assert "unsupported_schema_version" in _codes(_structural_issues(mut))


def test_relation_unresolved_fails():
    def mut(d):
        d["exercises"][0]["progression_ids"] = ["does_not_exist"]
    assert "relation_unresolved" in _codes(_structural_issues(mut))


def test_relation_self_fails():
    def mut(d):
        d["exercises"][0]["substitution_ids"] = [d["exercises"][0]["exercise_id"]]
    assert "relation_self" in _codes(_structural_issues(mut))


def test_progression_cycle_fails():
    def mut(d):
        a, b = d["exercises"][0]["exercise_id"], d["exercises"][1]["exercise_id"]
        d["exercises"][0]["progression_ids"] = [b]
        d["exercises"][1]["progression_ids"] = [a]
    assert "progression_cycle" in _codes(_structural_issues(mut))


def test_external_media_url_in_text_fails():
    def mut(d):
        d["exercises"][0]["instruction_steps"].append(
            "see https://example.com/image.png")
    assert "external_media_in_text" in _codes(_structural_issues(mut))


def test_external_protocol_relative_url_fails():
    def mut(d):
        d["exercises"][0]["form_cues"].append("//cdn.example.com/x")
    assert "external_media_in_text" in _codes(_structural_issues(mut))


def test_load_catalog_raises_does_not_yield_empty(tmp_path):
    data = _catalog_dict()
    data["exercises"][0]["progression_ids"] = ["ghost"]
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CatalogValidationError):
        load_catalog(p)


# ---------------------------------------------------------------------------
# Recommendation-ready gate (non-fatal per-exercise layer)
# ---------------------------------------------------------------------------


def test_not_ready_when_review_status_not_approved():
    data = _catalog_dict()
    data["exercises"][0]["provenance"]["review_status"] = "needs_review"
    catalog = ExerciseCatalog.model_validate(data)
    index = build_index(catalog)
    res = recommendation_ready(catalog.exercises[0], index,
                               catalog.published_at)
    assert not res.ready
    assert "review_status_not_approved" in _codes(res.issues)


def test_not_ready_when_illustration_not_approved():
    data = _catalog_dict()
    data["exercises"][0]["illustration"]["provenance"]["review_status"] = "draft"
    catalog = ExerciseCatalog.model_validate(data)
    index = build_index(catalog)
    res = recommendation_ready(catalog.exercises[0], index,
                               catalog.published_at)
    assert not res.ready
    assert "illustration_not_approved" in _codes(res.issues)


def test_not_ready_when_reviewed_after_publication():
    data = _catalog_dict()
    data["exercises"][0]["provenance"]["reviewed_at"] = "2026-12-31"
    catalog = ExerciseCatalog.model_validate(data)
    index = build_index(catalog)
    res = recommendation_ready(catalog.exercises[0], index,
                               catalog.published_at)
    assert not res.ready
    assert "reviewed_after_publication" in _codes(res.issues)


def test_not_ready_when_conservative_exceeds_normal():
    data = _catalog_dict()
    # Make conservative reps stricter-violation: conservative > normal.
    data["exercises"][0]["prescription"]["conservative_reps_max"] = 99
    data["exercises"][0]["prescription"]["reps_max"] = 12
    catalog = ExerciseCatalog.model_validate(data)
    index = build_index(catalog)
    res = recommendation_ready(catalog.exercises[0], index,
                               catalog.published_at)
    assert not res.ready
    assert "conservative_exceeds_normal" in _codes(res.issues)


def test_not_ready_when_relation_points_to_non_approved():
    data = _catalog_dict()
    # Exercise 2 becomes needs_review; exercise 1 progresses to it.
    data["exercises"][1]["provenance"]["review_status"] = "needs_review"
    data["exercises"][0]["progression_ids"] = [data["exercises"][1]["exercise_id"]]
    catalog = ExerciseCatalog.model_validate(data)
    index = build_index(catalog)
    res = recommendation_ready(catalog.exercises[0], index,
                               catalog.published_at)
    assert not res.ready
    assert "relation_not_approved" in _codes(res.issues)


# ---------------------------------------------------------------------------
# Importer (deterministic non-media adapter)
# ---------------------------------------------------------------------------


def _upstream_record(**over):
    base = {"id": "up-1", "name": "Push Up", "force": "push",
            "level": "beginner", "mechanic": "compound",
            "equipment": "body weight", "category": "strength",
            "primaryMuscles": ["chest"], "secondaryMuscles": ["triceps"],
            "instructions": ["lower slowly", "press up"],
            "translations": {"zh": "俯卧撑"},
            "images": ["a.png"], "gif_url": "a.gif", "media_id": "m1"}
    base.update(over)
    return base


def test_importer_maps_whitelisted_fields_and_strips_media():
    draft = import_upstream_record(
        _upstream_record(), source_id="ds",
        source_pinned_version="7455efa")
    assert draft.exercise_id == "up-1"
    assert draft.name_en == "Push Up"
    assert draft.equipment == ["bodyweight"]
    assert draft.primary_muscles == ["chest"]
    assert draft.secondary_muscles == ["triceps"]
    assert "push" in draft.movement_patterns
    assert draft.difficulty.value == "beginner"
    # Forbidden media/instruction fields recorded as stripped.
    for forbidden in ("instructions", "translations", "images",
                      "gif_url", "media_id"):
        assert forbidden in draft.excluded_fields
    # The draft is never recommendation-ready.
    assert draft.review_status == ReviewStatus.needs_review


def test_importer_maps_band_equipment():
    draft = import_upstream_record(
        _upstream_record(equipment="bands"), source_id="ds",
        source_pinned_version="7455efa")
    assert draft.equipment == ["resistance_band"]


def test_importer_rejects_unsupported_equipment():
    with pytest.raises(UnsupportedEquipmentError):
        import_upstream_record(_upstream_record(equipment="dumbbell"),
                               source_id="ds", source_pinned_version="v")


def test_importer_rejects_unrecognized_media_field():
    # A field name we do not know that looks media-like must be rejected,
    # not silently kept.
    with pytest.raises(UnrecognizedMediaFieldError):
        import_upstream_record(_upstream_record(photo_url="x"),
                               source_id="ds", source_pinned_version="v")


@pytest.mark.parametrize("missing", [
    "id", "name", "primaryMuscles",
])
def test_importer_rejects_missing_required_fields(missing):
    rec = _upstream_record()
    if missing == "id":
        rec["id"] = ""
    elif missing == "name":
        rec["name"] = ""
    else:
        rec["primaryMuscles"] = []
    with pytest.raises(MissingRequiredFieldError):
        import_upstream_record(rec, source_id="ds",
                               source_pinned_version="v")


def test_importer_rejects_no_supported_equipment():
    rec = _upstream_record()
    rec.pop("equipment")
    with pytest.raises(MissingRequiredFieldError):
        import_upstream_record(rec, source_id="ds",
                               source_pinned_version="v")


def test_importer_never_emits_approved():
    draft = import_upstream_record(_upstream_record(), source_id="ds",
                                   source_pinned_version="v")
    # Hard contract: the adapter cannot produce an approved record.
    assert draft.review_status != ReviewStatus.approved
