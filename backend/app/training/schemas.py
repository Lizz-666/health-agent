"""Typed contracts for the Phase 3 training catalog, provenance, illustration,
prescription bounds, and source manifest (Task 2).

Design rules (spec: Training Knowledge And Safety Engine, Domain Model):

- Every model uses ``ConfigDict(extra="forbid")``: a catalog record carrying an
  unknown field fails closed instead of being silently dropped.
- Enumerations pin the Phase 3 vocabulary. ``Equipment`` is intentionally
  limited to ``bodyweight`` / ``resistance_band`` (Phase 3 scope); gym machines,
  barbells, dumbbells, kettlebells, cables, Smith machines and pull-up bars are
  out of scope and therefore not representable.
- ``Illustration`` / ``IllustrationProvenance`` have NO URL field at all. An
  external-media URL is structurally impossible in the model; combined with
  ``extra="forbid"`` it cannot sneak in either.
- A ``PainNote`` / free-text safety rule is never a model field: classification
  consumes structured selectors only.
- These models are DATA shape contracts only. Cross-record invariants (relation
  integrity, recommendation-ready gating, review-date vs publication) are
  enforced by ``app.training.knowledge`` where the whole catalog is visible.

Conventions mirror ``app.health.schemas`` / ``app.posture.schemas``.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Phase 3 vocabulary (enumerations)
# ---------------------------------------------------------------------------


class TrainingRole(str, Enum):
    """A non-empty subset is required per exercise (spec Domain Model)."""

    warmup = "warmup"
    strength = "strength"
    corrective = "corrective"
    mobility = "mobility"
    recovery = "recovery"


class Difficulty(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class PrescriptionMode(str, Enum):
    """Phase 3 supports bounded reps OR duration; no 1RM / load-to-failure."""

    reps = "reps"
    duration = "duration"


class ReviewStatus(str, Enum):
    """Only ``approved`` is recommendation-ready.

    Phase 3 ``approved`` means approved for this repository's personal-
    development validation scope; it is NOT a clinical endorsement, professional
    certification, or public-release approval (spec Domain Model).
    """

    draft = "draft"
    needs_review = "needs_review"
    approved = "approved"
    retired = "retired"


class ReviewScope(str, Enum):
    """``personal_development`` is the only scope the initial catalog may use.

    ``public_release`` requires a separate qualified review and a new version;
    it is declared here so a premature public-release claim is detectable.
    """

    personal_development = "personal_development"
    public_release = "public_release"


class Equipment(str, Enum):
    """Phase 3 equipment scope. Adding an item here is a scope change."""

    bodyweight = "bodyweight"
    resistance_band = "resistance_band"


class CreatorType(str, Enum):
    """Illustration ownership. Phase 3 ships only project-authored art."""

    project_authored = "project_authored"


class SourceDeclaration(str, Enum):
    """Asserts an illustration is original with no external media reference."""

    original_no_external_reference = "original_no_external_reference"


class GoalTag(str, Enum):
    """Mirror of the health profile fitness goals, for deterministic filtering."""

    posture_improvement = "posture_improvement"
    fat_loss = "fat_loss"
    basic_strength = "basic_strength"
    mobility = "mobility"
    general_wellness = "general_wellness"


class SourceType(str, Enum):
    """Kind of provenance source recorded in the manifest / per-item records."""

    dataset = "dataset"
    comparison_project = "comparison_project"
    guideline = "guideline"
    position_stand = "position_stand"
    questionnaire_reference = "questionnaire_reference"
    project_authored = "project_authored"


# SHA-256 lowercase hex (used for illustration content hashes).
_HEX64_PATTERN = r"^[0-9a-f]{64}$"


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------


class LocalizedName(BaseModel):
    """Chinese + English name pair. Both required and non-empty."""

    model_config = ConfigDict(extra="forbid")

    name_en: str = Field(..., min_length=1, max_length=80)
    name_zh: str = Field(..., min_length=1, max_length=80)


# ---------------------------------------------------------------------------
# Illustration (local asset only; external URLs structurally impossible)
# ---------------------------------------------------------------------------


class IllustrationProvenance(BaseModel):
    """Ownership / review metadata for a local illustration asset.

    Deliberately has NO ``url`` field: Phase 3 forbids external illustration
    media. ``source_declaration`` must assert original authorship; a local file
    alone does not establish ownership (spec Domain Model).
    """

    model_config = ConfigDict(extra="forbid")

    creator_type: CreatorType = CreatorType.project_authored
    generation_tool: str = Field(..., min_length=1, max_length=80)
    created_at: date
    source_declaration: SourceDeclaration = (
        SourceDeclaration.original_no_external_reference
    )
    content_hash: str = Field(..., pattern=_HEX64_PATTERN)
    review_status: ReviewStatus
    review_scope: ReviewScope
    reviewer_role: str = Field(..., min_length=1, max_length=60)
    reviewed_at: date


class Illustration(BaseModel):
    """A local SVG illustration reference with its provenance.

    ``asset_key`` is a repository-relative path under
    ``assets/training/illustrations/`` ending in ``.svg``. No URL / remote
    reference is representable.
    """

    model_config = ConfigDict(extra="forbid")

    asset_key: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Repository-relative path to a local .svg asset.",
    )
    alt_text_en: str = Field(..., min_length=1, max_length=160)
    alt_text_zh: str = Field(..., min_length=1, max_length=160)
    provenance: IllustrationProvenance

    @field_validator("asset_key")
    @classmethod
    def _asset_key_is_local_svg(cls, v: str) -> str:
        v = v.strip()
        if not v.endswith(".svg"):
            raise ValueError("asset_key must reference a .svg asset")
        if "://" in v or v.startswith("//"):
            raise ValueError("asset_key must be a local path, not a URL")
        if not v.startswith("assets/training/illustrations/"):
            raise ValueError(
                "asset_key must live under assets/training/illustrations/"
            )
        return v


# ---------------------------------------------------------------------------
# Safety: stop conditions + structured contraindication selectors
# ---------------------------------------------------------------------------


class StopCondition(BaseModel):
    """A structured stop condition with bounded display text (no free-text rule).

    ``code`` is the machine-readable token; the display texts are bounded
    wellness-scope wording, never a clinical protocol.
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=60)
    display_text_en: str = Field(..., min_length=1, max_length=160)
    display_text_zh: str = Field(..., min_length=1, max_length=160)


class Contraindication(BaseModel):
    """Structured contraindication selectors (spec: safety selectors).

    ``risk_qualifiers`` are health ``risk_screen`` qualifier names (e.g.
    ``pregnancy_or_postpartum``) that contraindicate this exercise.
    ``body_regions`` are canonical pain body-region codes from the versioned
    normalization map. Both drive deterministic filtering; free text never does.
    """

    model_config = ConfigDict(extra="forbid")

    risk_qualifiers: List[str] = Field(default_factory=list)
    body_regions: List[str] = Field(default_factory=list)
    requires_complete_pain_screening: bool = True


# ---------------------------------------------------------------------------
# Prescription bounds (versioned product policy within the source envelope)
# ---------------------------------------------------------------------------


class PrescriptionBounds(BaseModel):
    """Bounded reps-or-duration prescription with a conservative path.

    ``mode=reps`` requires reps_min/reps_max; ``mode=duration`` requires
    duration_seconds_min/max. Conservative bounds must be at least as strict as
    the normal bounds (validated in ``knowledge`` with full context; the model
    only enforces the cheap non-negativity / ordering checks here).
    """

    model_config = ConfigDict(extra="forbid")

    mode: PrescriptionMode
    sets_min: int = Field(..., ge=1, le=6)
    sets_max: int = Field(..., ge=1, le=6)
    reps_min: Optional[int] = Field(None, ge=1, le=100)
    reps_max: Optional[int] = Field(None, ge=1, le=100)
    duration_seconds_min: Optional[int] = Field(None, ge=5, le=3600)
    duration_seconds_max: Optional[int] = Field(None, ge=5, le=3600)
    rest_seconds_min: int = Field(..., ge=0, le=600)
    rest_seconds_max: int = Field(..., ge=0, le=600)
    conservative_sets_max: int = Field(..., ge=1, le=6)
    conservative_reps_max: Optional[int] = Field(None, ge=1, le=100)
    conservative_duration_seconds_max: Optional[int] = Field(None, ge=5, le=3600)
    recovery_hours_min: int = Field(..., ge=0, le=168)
    weekly_sessions_max: int = Field(..., ge=1, le=7)
    conservative_eligible: bool = True
    progression_condition: str = Field(..., min_length=1, max_length=200)
    regression_condition: str = Field(..., min_length=1, max_length=200)

    @field_validator("sets_max")
    @classmethod
    def _sets_max_ge_min(cls, v, info):
        mn = info.data.get("sets_min")
        if mn is not None and v < mn:
            raise ValueError("sets_max must be >= sets_min")
        return v

    @field_validator("reps_max")
    @classmethod
    def _reps_max_ge_min(cls, v, info):
        mn = info.data.get("reps_min")
        if v is not None and mn is not None and v < mn:
            raise ValueError("reps_max must be >= reps_min")
        return v

    @field_validator("duration_seconds_max")
    @classmethod
    def _dur_max_ge_min(cls, v, info):
        mn = info.data.get("duration_seconds_min")
        if v is not None and mn is not None and v < mn:
            raise ValueError("duration_seconds_max must be >= min")
        return v

    @field_validator("rest_seconds_max")
    @classmethod
    def _rest_max_ge_min(cls, v, info):
        mn = info.data.get("rest_seconds_min")
        if mn is not None and v < mn:
            raise ValueError("rest_seconds_max must be >= rest_seconds_min")
        return v


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class SourceRecord(BaseModel):
    """A self-contained provenance source for one exercise item.

    Records a stable source identifier, pinned version, URL (provenance, NOT
    media), license, permitted scope and verification date. URLs are allowed
    here because this is source lineage, not illustration media.
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(..., min_length=1, max_length=80)
    source_type: SourceType
    name: str = Field(..., min_length=1, max_length=120)
    pinned_version: str = Field(..., min_length=1, max_length=120)
    url: str = Field(..., min_length=1, max_length=300)
    license: Optional[str] = Field(None, max_length=80)
    scope: str = Field(..., min_length=1, max_length=200)
    verified_date: date


class Provenance(BaseModel):
    """Review + source lineage for one exercise.

    ``imported_fields`` lists fields sourced from an external dataset (empty for
    purely project-authored entries) so a reviewer can see exactly what came in
    untrusted. ``review_scope`` must be explicit; personal-development approval
    cannot masquerade as public-release approval.
    """

    model_config = ConfigDict(extra="forbid")

    sources: List[SourceRecord] = Field(..., min_length=1)
    imported_fields: List[str] = Field(default_factory=list)
    review_status: ReviewStatus
    review_scope: ReviewScope
    reviewer_role: str = Field(..., min_length=1, max_length=60)
    reviewed_at: date
    content_version: str = Field(..., min_length=1, max_length=40)


# ---------------------------------------------------------------------------
# Exercise + catalog envelope
# ---------------------------------------------------------------------------


class Exercise(BaseModel):
    """A single training exercise with full safety / prescription metadata.

    Non-empty requirements are enforced at the model level (min_length on
    lists). Cross-record invariants (relations resolve, recommendation-ready
    gating, review date <= publication) are enforced by ``app.training.knowledge``
    with the whole catalog in scope.
    """

    model_config = ConfigDict(extra="forbid")

    exercise_id: str = Field(..., min_length=1, max_length=60)
    names: LocalizedName
    training_roles: List[TrainingRole] = Field(..., min_length=1)
    difficulty: Difficulty
    goals: List[GoalTag] = Field(..., min_length=1)
    movement_patterns: List[str] = Field(..., min_length=1, max_length=12)
    movement_purposes: List[str] = Field(..., min_length=1, max_length=12)
    primary_muscles: List[str] = Field(..., min_length=1, max_length=20)
    secondary_muscles: List[str] = Field(default_factory=list, max_length=20)
    equipment: List[Equipment] = Field(..., min_length=1)

    applicable_posture_signals: List[str] = Field(
        default_factory=list, max_length=40
    )
    not_applicable_posture_signals: List[str] = Field(
        default_factory=list, max_length=40
    )

    contraindications: Contraindication
    stop_conditions: List[StopCondition] = Field(..., min_length=1)

    instruction_steps: List[str] = Field(..., min_length=1, max_length=30)
    form_cues: List[str] = Field(..., min_length=1, max_length=30)
    common_mistakes: List[str] = Field(default_factory=list, max_length=30)

    progression_ids: List[str] = Field(default_factory=list, max_length=20)
    regression_ids: List[str] = Field(default_factory=list, max_length=20)
    substitution_ids: List[str] = Field(default_factory=list, max_length=20)

    prescription: PrescriptionBounds
    illustration: Illustration
    provenance: Provenance

    @field_validator("movement_patterns", "movement_purposes",
                     "primary_muscles", "secondary_muscles",
                     "applicable_posture_signals",
                     "not_applicable_posture_signals",
                     "training_roles", "goals", "equipment",
                     "instruction_steps", "form_cues", "common_mistakes")
    @classmethod
    def _string_lists_trimmed_and_non_blank(cls, v):
        # Covers only str / str-enum list fields (model-list fields like
        # stop_conditions validate their own nested strings).
        for item in v:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("list items must be non-blank strings")
            if item != item.strip():
                raise ValueError("list items must be trimmed")
        return v

    @field_validator("progression_ids", "regression_ids", "substitution_ids")
    @classmethod
    def _relation_ids_trimmed(cls, v):
        for item in v:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("relation ids must be non-blank strings")
        return v

    @field_validator("progression_ids")
    @classmethod
    def _no_self_progression(cls, v, info):
        eid = info.data.get("exercise_id")
        if eid and eid in v:
            raise ValueError("an exercise must not progress to itself")
        return v


class ExerciseCatalog(BaseModel):
    """The versioned catalog envelope.

    A catalog-load failure is explicit (raises) and NEVER yields an empty-but-
    successful catalog. ``policy_compatibility`` lists the training-policy
    versions this catalog content is approved for.
    """

    model_config = ConfigDict(extra="forbid")

    catalog_id: str = Field(..., min_length=1, max_length=60)
    content_version: str = Field(..., min_length=1, max_length=40)
    schema_version: str = Field(..., min_length=1, max_length=20)
    published_at: date
    policy_compatibility: List[str] = Field(..., min_length=1)
    source_manifest_version: str = Field(..., min_length=1, max_length=20)
    exercises: List[Exercise] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Source manifest (Task 2) + importer draft (Task 2)
# ---------------------------------------------------------------------------


class SourceManifestEntry(BaseModel):
    """One entry in the global source manifest.

    Records license, pinned commit/version, the imported fields and the media
    exclusion for an external dataset, plus the explicit exclusion scope. This
    is the authoritative registry consulted by the source/license audit.
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(..., min_length=1, max_length=80)
    source_type: SourceType
    name: str = Field(..., min_length=1, max_length=120)
    pinned_version: str = Field(..., min_length=1, max_length=120)
    url: str = Field(..., min_length=1, max_length=300)
    license: Optional[str] = Field(None, max_length=80)
    copyright: Optional[str] = Field(None, max_length=300)
    permitted_use: str = Field(..., min_length=1, max_length=300)
    explicit_exclusion: str = Field(..., min_length=1, max_length=300)
    imported_fields: List[str] = Field(default_factory=list)
    field_mapping: Dict[str, str] = Field(default_factory=dict)
    media_exclusion: str = Field(..., min_length=1, max_length=300)
    verified_date: date


class SourceManifest(BaseModel):
    """The versioned global source manifest."""

    model_config = ConfigDict(extra="forbid")

    manifest_version: str = Field(..., min_length=1, max_length=20)
    sources: List[SourceManifestEntry] = Field(..., min_length=1)


class ImportedExerciseDraft(BaseModel):
    """Deterministic output of the non-media import adapter.

    This is deliberately NOT an ``Exercise``: it is a ``needs_review`` draft
    missing safety / posture / prescription / illustration completeness, so it
    can never be recommendation-ready. ``excluded_fields`` records every
    upstream media / instruction / translation field that was stripped.
    """

    model_config = ConfigDict(extra="forbid")

    exercise_id: str = Field(..., min_length=1, max_length=60)
    name_en: str = Field(..., min_length=1, max_length=80)
    equipment: List[Equipment] = Field(..., min_length=1)
    movement_patterns: List[str] = Field(..., min_length=1, max_length=12)
    primary_muscles: List[str] = Field(..., min_length=1, max_length=20)
    secondary_muscles: List[str] = Field(default_factory=list, max_length=20)
    difficulty: Optional[Difficulty] = None
    imported_fields: List[str] = Field(..., min_length=1)
    excluded_fields: List[str] = Field(
        default_factory=list,
        description=(
            "Upstream media / instruction / translation fields that were "
            "present and stripped. Empty when none were present."
        ),
    )
    review_status: ReviewStatus = ReviewStatus.needs_review
    source_id: str = Field(..., min_length=1, max_length=80)
    source_pinned_version: str = Field(..., min_length=1, max_length=120)


# ---------------------------------------------------------------------------
# Training safety context + decision (Task 4)
# ---------------------------------------------------------------------------


class GateStatus(str, Enum):
    """Safety gate outcomes in precedence order (highest first).

    red_flag > restricted > clarification_required > eligible_conservative >
    eligible (spec: Safety decision). Restricted / red_flag expose no
    candidate IDs (enforced in candidates.py, not here).
    """

    red_flag = "red_flag"
    restricted = "restricted"
    clarification_required = "clarification_required"
    eligible_conservative = "eligible_conservative"
    eligible = "eligible"


class SafetyRiskTier(str, Enum):
    """The two-dimensional risk classification. ``None`` on the decision means
    classification could not run because required data was missing."""

    normal = "normal"
    caution = "caution"
    restricted = "restricted"
    red_flag = "red_flag"


class PainLimitationSnapshot(BaseModel):
    """A user-stated pain limitation with normalization results filled in.

    ``*_canonical`` is None when the reviewed alias map could not normalize the
    raw value (the caller then fails the context to clarification_required).
    """

    model_config = ConfigDict(extra="forbid")

    body_area_raw: str = Field(..., min_length=1, max_length=60)
    status_raw: str = Field(..., min_length=1, max_length=30)
    body_area_canonical: Optional[str] = None
    status_canonical: Optional[str] = None


class HealthProfileSnapshot(BaseModel):
    """Structured current health profile (recomputed, never trusting labels)."""

    model_config = ConfigDict(extra="forbid")

    configured: bool = False
    fitness_goal: Optional[str] = None
    training_experience: Optional[str] = None
    weekly_frequency: Optional[int] = None
    session_duration_minutes: Optional[int] = None
    equipment_bodyweight: Optional[bool] = None
    equipment_resistance_band: Optional[bool] = None
    pain_limitations: Optional[List[PainLimitationSnapshot]] = None
    risk_screen: Optional[Dict[str, Optional[str]]] = None
    profile_version: Optional[int] = None
    profile_updated_at: Optional[datetime] = None


class CheckInSnapshot(BaseModel):
    """The current-day check-in with its recomputed risk and freshness token."""

    model_config = ConfigDict(extra="forbid")

    present: bool = False
    local_date: Optional[date] = None
    recomputed_risk: Optional[str] = None
    token: Optional[str] = None


class RetainedPainRecord(BaseModel):
    """A retained abnormal-pain check-in record (recomputed, token-bearing)."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(..., min_length=1)
    recomputed_risk: str = Field(..., min_length=1)
    local_date: Optional[date] = None


class PostureGoalSnapshot(BaseModel):
    """A confirmed posture goal: active (not superseded) and blocked flags."""

    model_config = ConfigDict(extra="forbid")

    issue_id: str = Field(..., min_length=1, max_length=30)
    active: bool = True
    blocked: bool = False


class PostureSnapshot(BaseModel):
    """Active posture safety-signal digest, global risk and confirmed goals."""

    model_config = ConfigDict(extra="forbid")

    active_signals_digest: Optional[str] = None
    global_risk_tier: Optional[str] = None
    risk_version: Optional[str] = None
    goals: List[PostureGoalSnapshot] = Field(default_factory=list)


class RequestSnapshot(BaseModel):
    """The recommendation/validation request parameters."""

    model_config = ConfigDict(extra="forbid")

    fitness_goal: Optional[str] = None
    equipment_bodyweight: Optional[bool] = None
    equipment_resistance_band: Optional[bool] = None
    weekly_frequency: Optional[int] = None
    session_duration_minutes: Optional[int] = None
    iana_timezone: Optional[str] = None
    client_local_date: Optional[date] = None


class VersionMeta(BaseModel):
    """Version pins included in the decision fingerprint."""

    model_config = ConfigDict(extra="forbid")

    policy_version: str = Field(..., min_length=1)
    catalog_version: Optional[str] = None
    source_manifest_version: Optional[str] = None
    schema_version: str = Field("v1", min_length=1)


class EvalMeta(BaseModel):
    """Evaluation clock / timezone metadata (server-derived, never client)."""

    model_config = ConfigDict(extra="forbid")

    evaluated_at_utc: datetime
    iana_timezone: Optional[str] = None
    current_local_date: Optional[date] = None
    timezone_trusted: bool = False


class TrainingSafetyContext(BaseModel):
    """Immutable request snapshot assembled from current structured sources.

    Pure-engine fixtures omit ``user_id``; the application adapter sets it for
    authorization only and never lets it reach the decision fingerprint or logs.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: Optional[str] = None
    health: HealthProfileSnapshot = Field(default_factory=HealthProfileSnapshot)
    checkin: CheckInSnapshot = Field(default_factory=CheckInSnapshot)
    retained_pain: List[RetainedPainRecord] = Field(default_factory=list)
    posture: PostureSnapshot = Field(default_factory=PostureSnapshot)
    request: RequestSnapshot = Field(default_factory=RequestSnapshot)
    versions: VersionMeta
    eval: EvalMeta


class TrainingSafetyDecision(BaseModel):
    """Deterministic safety decision (pure output, no raw sensitive values)."""

    model_config = ConfigDict(extra="forbid")

    gate_status: GateStatus
    risk_tier: Optional[SafetyRiskTier] = None
    reason_codes: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    blocking_source_refs: List[str] = Field(default_factory=list)
    profile_version: Optional[int] = None
    checkin_token: Optional[str] = None
    posture_risk_version: Optional[str] = None
    training_policy_version: str
    catalog_version: Optional[str] = None
    fingerprint: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Candidate engine contracts (Task 5)
# ---------------------------------------------------------------------------


class Candidate(BaseModel):
    """A selected, recommendation-ready exercise with its deterministic sort key."""

    model_config = ConfigDict(extra="forbid")

    exercise_id: str = Field(..., min_length=1, max_length=60)
    training_roles: List[str] = Field(..., min_length=1)
    movement_purposes: List[str] = Field(..., min_length=1)
    sort_key: str = Field(..., min_length=1)


class ExcludedExercise(BaseModel):
    """An exercise excluded from selection with structured reason codes."""

    model_config = ConfigDict(extra="forbid")

    exercise_id: str = Field(..., min_length=1, max_length=60)
    reason_codes: List[str] = Field(..., min_length=1)


class CandidateResult(BaseModel):
    """Deterministic candidate selection output (pure, no raw health values).

    Non-eligible gates (red_flag / restricted / clarification_required) always
    return an empty candidate list; restricted/red_flag expose NO candidate IDs.
    """

    model_config = ConfigDict(extra="forbid")

    gate_status: GateStatus
    decision_fingerprint: str = Field(..., min_length=1)
    candidates: List[Candidate] = Field(default_factory=list)
    excluded: List[ExcludedExercise] = Field(default_factory=list)
    policy_version: str
    catalog_version: Optional[str] = None
    conservative: bool = False


# ---------------------------------------------------------------------------
# Draft plan + validation result contracts (Task 6)
# ---------------------------------------------------------------------------


class PlanPrescription(BaseModel):
    """One exercise prescription within a session."""

    model_config = ConfigDict(extra="forbid")

    exercise_id: str = Field(..., min_length=1, max_length=60)
    sets: int = Field(..., ge=1, le=10)
    reps: Optional[int] = Field(None, ge=1, le=100)
    duration_seconds: Optional[int] = Field(None, ge=5, le=3600)
    rest_seconds: int = Field(..., ge=0, le=600)
    relation_reason: Optional[str] = Field(None, max_length=30)


class PlanSession(BaseModel):
    """A session in the four-week timeline.

    ``week_index`` 1-4, ``day_of_week`` 1-7, ``session_order`` unique within the
    week. Together they form the sole ordinal recovery/frequency timeline.
    """

    model_config = ConfigDict(extra="forbid")

    week_index: int = Field(..., ge=1, le=4)
    day_of_week: int = Field(..., ge=1, le=7)
    session_order: int = Field(..., ge=1, le=20)
    prescriptions: List[PlanPrescription] = Field(..., min_length=1)

    @field_validator("prescriptions")
    @classmethod
    def _no_blank_relation(cls, v):
        for p in v:
            if p.relation_reason is not None and not p.relation_reason.strip():
                raise ValueError("relation_reason must be non-blank")
        return v


class TrainingPlanDraft(BaseModel):
    """A minimal four-week draft plan for validation + Phase 4 handoff.

    Carries NO persistence / activation / completion state. Validation never
    mutates or repairs it.
    """

    model_config = ConfigDict(extra="forbid")

    draft_id: str = Field(..., min_length=1, max_length=60)
    requested_goal: str = Field(..., min_length=1, max_length=30)
    source_context_fingerprint: str = Field(..., min_length=1)
    profile_version: Optional[int] = None
    catalog_version: str = Field(..., min_length=1, max_length=40)
    policy_version: str = Field(..., min_length=1, max_length=20)
    source_manifest_version: str = Field(..., min_length=1, max_length=20)
    sessions: List[PlanSession] = Field(..., min_length=1)


class PlanViolation(BaseModel):
    """One structured validation violation (code + scope, no raw health data)."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=60)
    scope: str = Field("plan", min_length=1, max_length=80)
    detail: str = Field(..., min_length=1, max_length=240)


class PlanValidationResult(BaseModel):
    """Pure, side-effect-free validation result (fail-closed)."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    gate_status: GateStatus
    decision_fingerprint: str = Field(..., min_length=1)
    violations: List[PlanViolation] = Field(default_factory=list)
    profile_version: Optional[int] = None
    catalog_version: Optional[str] = None
    policy_version: str
