"""Schema-level tests for the Phase 3 training contracts (Task 2).

Covers the DATA-shape invariants: extra-field rejection, the Phase 3 equipment
scope, illustration local-asset / no-URL rules, content-hash format, required
non-empty lists, prescription ordering, and the review-status/scope vocabulary.
Cross-record invariants live in test_training_sources.py.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.training.schemas import (
    Difficulty,
    Equipment,
    Exercise,
    ExerciseCatalog,
    Illustration,
    IllustrationProvenance,
    ImportedExerciseDraft,
    PrescriptionBounds,
    ReviewScope,
    ReviewStatus,
    SourceManifest,
    TrainingRole,
)

HASH_OK = "a" * 64
HASH_BAD = "not-a-hex-hash"


def _minimal_exercise(over=None):
    base = {
        "exercise_id": "ex1",
        "names": {"name_en": "Squat", "name_zh": "深蹲"},
        "training_roles": ["strength"],
        "difficulty": "beginner",
        "goals": ["basic_strength"],
        "movement_patterns": ["squat"],
        "movement_purposes": ["lower_push_strength"],
        "primary_muscles": ["quadriceps"],
        "secondary_muscles": [],
        "equipment": ["bodyweight"],
        "applicable_posture_signals": [],
        "not_applicable_posture_signals": [],
        "contraindications": {"risk_qualifiers": [], "body_regions": [],
                              "requires_complete_pain_screening": True},
        "stop_conditions": [{"code": "pain", "display_text_en": "Stop.",
                             "display_text_zh": "停止。"}],
        "instruction_steps": ["step one"],
        "form_cues": ["chest tall"],
        "common_mistakes": [],
        "progression_ids": [], "regression_ids": [], "substitution_ids": [],
        "prescription": {"mode": "reps", "sets_min": 3, "sets_max": 4,
                         "reps_min": 8, "reps_max": 12,
                         "rest_seconds_min": 30, "rest_seconds_max": 60,
                         "conservative_sets_max": 3, "conservative_reps_max": 10,
                         "recovery_hours_min": 48, "weekly_sessions_max": 3,
                         "conservative_eligible": True,
                         "progression_condition": "add a rep",
                         "regression_condition": "reduce depth"},
        "illustration": {"asset_key": "assets/training/illustrations/ex1.svg",
                         "alt_text_en": "squat", "alt_text_zh": "深蹲",
                         "provenance": {"creator_type": "project_authored",
                            "generation_tool": "svg", "created_at": "2026-07-26",
                            "source_declaration": "original_no_external_reference",
                            "content_hash": HASH_OK, "review_status": "approved",
                            "review_scope": "personal_development",
                            "reviewer_role": "project_reviewer",
                            "reviewed_at": "2026-07-26"}},
        "provenance": {"sources": [{"source_id": "cat", "source_type":
                            "project_authored", "name": "catalog",
                            "pinned_version": "v1", "url": "internal:cat",
                            "license": "Project", "scope": "personal-dev",
                            "verified_date": "2026-07-26"}],
                       "imported_fields": [], "review_status": "approved",
                       "review_scope": "personal_development",
                       "reviewer_role": "project_reviewer",
                       "reviewed_at": "2026-07-26", "content_version": "v1"},
    }
    if over:
        base.update(over)
    return base


def test_exercise_extra_field_forbidden():
    ex = _minimal_exercise({"surprise": 1})
    with pytest.raises(ValidationError):
        Exercise.model_validate(ex)


def test_illustration_has_no_url_field_structurally():
    prov = _minimal_exercise()["illustration"]["provenance"]
    # An external URL cannot be added (extra forbidden)...
    with pytest.raises(ValidationError):
        IllustrationProvenance.model_validate({**prov, "url": "https://x"})
    # ...and an Illustration cannot carry one either.
    ill = {"asset_key": "assets/training/illustrations/a.svg",
           "alt_text_en": "a", "alt_text_zh": "a", "provenance": prov}
    with pytest.raises(ValidationError):
        Illustration.model_validate({**ill, "image_url": "https://x"})


@pytest.mark.parametrize("bad_key", [
    "assets/training/illustrations/a.png",   # not svg
    "https://host/a.svg",                     # remote url
    "ftp://host/a.svg",                       # url
    "other/dir/a.svg",                        # wrong location
])
def test_asset_key_must_be_local_svg(bad_key):
    ex = _minimal_exercise()
    ex["illustration"]["asset_key"] = bad_key
    with pytest.raises(ValidationError):
        Exercise.model_validate(ex)


def test_content_hash_must_be_sha256_hex():
    ex = _minimal_exercise()
    ex["illustration"]["provenance"]["content_hash"] = HASH_BAD
    with pytest.raises(ValidationError):
        Exercise.model_validate(ex)


def test_equipment_limited_to_phase3_scope():
    # barbell / dumbbell are not valid Equipment values at all.
    ex = _minimal_exercise({"equipment": ["barbell"]})
    with pytest.raises(ValidationError):
        Exercise.model_validate(ex)


def test_required_lists_must_be_non_empty():
    for field in ("training_roles", "goals", "movement_patterns",
                  "movement_purposes", "primary_muscles", "equipment",
                  "stop_conditions", "instruction_steps", "form_cues"):
        ex = _minimal_exercise({field: []})
        with pytest.raises(ValidationError):
            Exercise.model_validate(ex)


def test_prescription_ordering_validators():
    # sets_max < sets_min
    with pytest.raises(ValidationError):
        PrescriptionBounds.model_validate(
            {**_minimal_exercise()["prescription"], "sets_max": 2})
    # reps_max < reps_min
    rx = _minimal_exercise()["prescription"]
    rx = {**rx, "reps_min": 12, "reps_max": 8}
    with pytest.raises(ValidationError):
        PrescriptionBounds.model_validate(rx)
    # rest_seconds_max < rest_seconds_min
    rx = {**_minimal_exercise()["prescription"], "rest_seconds_max": 10}
    with pytest.raises(ValidationError):
        PrescriptionBounds.model_validate(rx)


def test_review_status_and_scope_vocabulary():
    assert ReviewStatus.approved.value == "approved"
    assert ReviewScope.personal_development.value == "personal_development"
    # An unknown review status is rejected.
    ex = _minimal_exercise()
    ex["provenance"]["review_status"] = "public_release_approved"
    with pytest.raises(ValidationError):
        Exercise.model_validate(ex)


def test_self_progression_rejected_at_model_level():
    ex = _minimal_exercise({"exercise_id": "ex1",
                            "progression_ids": ["ex1"]})
    with pytest.raises(ValidationError):
        Exercise.model_validate(ex)


def test_catalog_exercises_min_length_one():
    cat = {"catalog_id": "c", "content_version": "v1", "schema_version": "v1",
           "published_at": "2026-07-26", "policy_compatibility": ["v1"],
           "source_manifest_version": "v1", "exercises": []}
    with pytest.raises(ValidationError):
        ExerciseCatalog.model_validate(cat)


def test_imported_draft_defaults_to_needs_review():
    draft = ImportedExerciseDraft(exercise_id="x", name_en="X",
                                  equipment=[Equipment.bodyweight],
                                  movement_patterns=["squat"],
                                  primary_muscles=["quadriceps"],
                                  imported_fields=["name"],
                                  source_id="ds",
                                  source_pinned_version="abc")
    assert draft.review_status == ReviewStatus.needs_review
    assert draft.difficulty is None


def test_source_manifest_min_length_and_version():
    with pytest.raises(ValidationError):
        SourceManifest.model_validate({"manifest_version": "v1", "sources": []})


def test_training_role_and_difficulty_vocab():
    assert {r.value for r in TrainingRole} == {
        "warmup", "strength", "corrective", "mobility", "recovery"}
    assert {d.value for d in Difficulty} == {
        "beginner", "intermediate", "advanced"}
