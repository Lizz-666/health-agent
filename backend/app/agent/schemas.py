"""Strict typed Agent contracts (Task 1, read-only boundary).

Design invariants:

- ``TurnInput`` is the ONLY client-facing shape and is strict (``extra="forbid"``).
  It carries a closed ``entry_type``, an optional owned ``entity_id``, one bounded
  ``message``, and a required IANA timezone. It CANNOT carry ``user_id``, an
  actor, consent, risk tier, a Tool set, a policy version, a context fingerprint,
  or a server clock: identity, authorization, safety policy, and time are
  server-injected only (spec Architecture, API Contracts).
- Every read Tool result is two separately typed projections: a minimal
  ``provider_view`` (untrusted structured data the model may see) and an owned
  ``display_view`` (rendered by server templates for the user). A full Tool
  result is never auto-forwarded to the provider.

``ActorContext`` and ``AsyncSession`` are never represented here; they are passed
positionally into server code and are not model-controllable parameters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.health.schemas import (
    AvailableTime,
    DailyStatus,
    Energy,
    MuscleSoreness,
    SleepQuality,
)


# --------------------------------------------------------------------------- #
# Closed enums                                                                 #
# --------------------------------------------------------------------------- #


class EntryType(str, Enum):
    """The closed set of Agent entry points (spec Entry And Context Contracts)."""

    general = "general"
    health_profile = "health_profile"
    posture_issue = "posture_issue"
    training_plan = "training_plan"
    training_session = "training_session"
    training_exercise = "training_exercise"


class SideEffectClass(str, Enum):
    """Tool side-effect class. Task 1 registers only ``read`` Tools."""

    READ = "read"


# --------------------------------------------------------------------------- #
# Client-facing turn contract                                                  #
# --------------------------------------------------------------------------- #


class TurnInput(BaseModel):
    """One ephemeral turn request body.

    Strict by construction: unknown fields (including any attempt to inject
    ``user_id`` / ``actor`` / ``consent`` / ``risk_tier`` / ``allowed_tools`` /
    ``policy_version`` / ``context_fingerprint`` / ``server_time``) are rejected.
    """

    model_config = ConfigDict(extra="forbid")

    client_turn_id: str = Field(..., min_length=1, max_length=64)
    entry_type: EntryType
    entity_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    message: str = Field(..., min_length=1, max_length=2000)
    iana_timezone: str = Field(..., min_length=1, max_length=60)


# --------------------------------------------------------------------------- #
# Strict Tool input models                                                     #
# --------------------------------------------------------------------------- #
#
# Each provider-selectable read Tool binds a strict (``extra="forbid"``) input
# model containing ONLY the provider-typeable arguments. Identity (``db``,
# ``ActorContext``/``user_id``), the server clock, and the validated timezone
# are server-injected positional adapter arguments and are NEVER fields here, so
# the provider cannot select an actor, a tool set, or a clock.


class ToolInput(BaseModel):
    """Base for all Tool input models: strict and identity-free by construction."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class EmptyToolInput(ToolInput):
    """No provider-typeable arguments: identity/context comes from the server."""


class ListPostureIssuesInput(ToolInput):
    category: Optional[str] = Field(default=None, min_length=1, max_length=30)


class GetPostureIssueInput(ToolInput):
    issue_id: str = Field(..., min_length=1, max_length=60)


class GetTrainingExerciseInput(ToolInput):
    exercise_id: str = Field(..., min_length=1, max_length=60)


class AuthModel(str, Enum):
    """How a Tool's authorization/identity is bound (server-side only)."""

    PUBLIC = "public"  # catalog knowledge only, no identity
    OWNER = "owner"  # actor-scoped owned data
    ENTRY_OWNER = "entry_owner"  # entity must match a current owned entity
    CURRENT_SESSION = "current_session"  # bound to today's owned session


# --------------------------------------------------------------------------- #
# View base classes                                                            #
# --------------------------------------------------------------------------- #


class ProviderView(BaseModel):
    """Minimal, redacted projection the untrusted provider may receive."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class DisplayView(BaseModel):
    """Owned projection rendered for the user by server templates only."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- #
# Health profile views                                                         #
# --------------------------------------------------------------------------- #


class HealthProfileProviderView(ProviderView):
    configured: bool
    profile_version: Optional[int] = None
    readiness_code: Optional[str] = None
    risk_version: Optional[str] = None
    fitness_goal: Optional[str] = None
    training_experience: Optional[str] = None
    weekly_frequency: Optional[int] = None
    session_duration_minutes: Optional[str] = None
    equipment_bodyweight: Optional[bool] = None
    equipment_resistance_band: Optional[bool] = None
    has_pain_limitations: bool = False
    has_allergies: bool = False
    has_diet_exclusions: bool = False
    restricted: bool = False


class HealthProfileDisplayView(DisplayView):
    configured: bool
    profile_version: Optional[int] = None
    readiness_code: Optional[str] = None
    risk_version: Optional[str] = None
    fitness_goal: Optional[str] = None
    training_experience: Optional[str] = None
    weekly_frequency: Optional[int] = None
    session_duration_minutes: Optional[str] = None
    equipment_bodyweight: Optional[bool] = None
    equipment_resistance_band: Optional[bool] = None
    pain_limitation_count: int = 0
    allergies_count: int = 0
    diet_exclusions_count: int = 0
    restricted: bool = False


# --------------------------------------------------------------------------- #
# Today check-in views                                                         #
# --------------------------------------------------------------------------- #


class TodayCheckinProviderView(ProviderView):
    checked_in: bool
    local_date: Optional[date] = None
    risk_summary_code: Optional[str] = None
    risk_version: Optional[str] = None
    abnormal_pain: Optional[bool] = None
    has_pain_followup: bool = False


class TodayCheckinDisplayView(DisplayView):
    checked_in: bool
    local_date: Optional[date] = None
    risk_summary_code: Optional[str] = None
    risk_version: Optional[str] = None
    abnormal_pain: Optional[bool] = None
    sleep_quality: Optional[str] = None
    energy: Optional[str] = None
    muscle_soreness: Optional[str] = None
    available_time: Optional[str] = None
    daily_status: Optional[str] = None


# --------------------------------------------------------------------------- #
# Weight trend views                                                           #
# --------------------------------------------------------------------------- #


class WeightTrendProviderView(ProviderView):
    sufficient: bool
    window: int
    record_count: int
    trend_point_count: int


class WeightTrendDisplayView(DisplayView):
    sufficient: bool
    window: int
    record_count: int
    trend_point_count: int
    latest_weight_kg: Optional[float] = None


# --------------------------------------------------------------------------- #
# Posture issue catalog views (public knowledge)                               #
# --------------------------------------------------------------------------- #


class PostureIssueProviderItem(ProviderView):
    id: str
    name_cn: str
    category: str


class PostureIssueDisplayItem(DisplayView):
    id: str
    name_cn: str
    category: str
    aliases: List[str] = Field(default_factory=list)
    definition: Optional[str] = None


class PostureIssueListProviderView(ProviderView):
    issues: List[PostureIssueProviderItem] = Field(default_factory=list)


class PostureIssueListDisplayView(DisplayView):
    issues: List[PostureIssueDisplayItem] = Field(default_factory=list)


class PostureIssueDetailProviderView(ProviderView):
    id: str
    name_cn: str
    category: str
    severity_levels: List[str] = Field(default_factory=list)
    self_test_count: int = 0
    has_red_flags: bool = False


class PostureIssueDetailDisplayView(DisplayView):
    id: str
    name_cn: str
    name_en: str
    category: str
    definition: Optional[str] = None
    severity_levels: List[str] = Field(default_factory=list)
    red_flags: List[str] = Field(default_factory=list)
    self_test_count: int = 0


# --------------------------------------------------------------------------- #
# Posture self-test guide views                                                #
# --------------------------------------------------------------------------- #


class SelfTestGuideProviderView(ProviderView):
    issue_id: str
    issue_name: str
    category: str
    self_test_count: int = 0
    has_existing_result: bool = False


class SelfTestGuideDisplayView(DisplayView):
    issue_id: str
    issue_name: str
    category: str
    self_test_count: int = 0
    has_existing_result: bool = False


# --------------------------------------------------------------------------- #
# Posture profile views (owned structured result codes)                        #
# --------------------------------------------------------------------------- #


class PostureProfileEntryView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    issue_id: str
    issue_name: str
    category: str
    combined_severity: Optional[str] = None
    certainty: str
    has_conflict: bool
    risk_tier: str
    risk_version: Optional[str] = None
    source_codes: List[str] = Field(default_factory=list)


class PostureProfileProviderView(ProviderView):
    present: bool
    total_evaluated: int = 0
    total_conflict: int = 0
    total_provisional: int = 0
    entries: List[PostureProfileEntryView] = Field(default_factory=list)


class PostureProfileDisplayView(DisplayView):
    present: bool
    total_evaluated: int = 0
    total_conflict: int = 0
    total_provisional: int = 0
    entries: List[PostureProfileEntryView] = Field(default_factory=list)
    unevaluated_categories: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Posture priority views (suggestion codes only)                               #
# --------------------------------------------------------------------------- #


class PriorityItemView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    issue_id: str
    issue_name: str
    suggested_rank: Optional[int] = None
    severity: Optional[str] = None
    certainty: Optional[str] = None
    risk_tier: Optional[str] = None


class PosturePrioritiesProviderView(ProviderView):
    suggestion_id: str
    profile_version: str
    rule_version: str
    risk_version: str
    normal_candidate_count: int = 0
    retest_count: int = 0
    safety_blocked_count: int = 0


class PosturePrioritiesDisplayView(DisplayView):
    suggestion_id: str
    profile_version: str
    rule_version: str
    risk_version: str
    normal_candidates: List[PriorityItemView] = Field(default_factory=list)
    retest_required: List[PriorityItemView] = Field(default_factory=list)
    safety_blocked: List[PriorityItemView] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Training plan / draft / active views                                         #
# --------------------------------------------------------------------------- #


class TrainingPlanSummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_version_id: str
    status: str
    requested_goal: str
    weekly_frequency: int
    session_duration_minutes: int
    decision_gate: str
    session_count: int
    change_reason: Optional[str] = None
    catalog_version: Optional[str] = None
    policy_version: Optional[str] = None


class TrainingDraftProviderView(ProviderView):
    has_draft: bool
    decision_gate: Optional[str] = None
    plan: Optional[TrainingPlanSummaryView] = None


class TrainingDraftDisplayView(DisplayView):
    has_draft: bool
    decision_gate: Optional[str] = None
    plan: Optional[TrainingPlanSummaryView] = None


class ActivePlanProviderView(ProviderView):
    has_active: bool
    plan: Optional[TrainingPlanSummaryView] = None


class ActivePlanDisplayView(DisplayView):
    has_active: bool
    plan: Optional[TrainingPlanSummaryView] = None


# --------------------------------------------------------------------------- #
# Today training views                                                         #
# --------------------------------------------------------------------------- #


class TodayTrainingProviderView(ProviderView):
    state: str
    local_date: Optional[date] = None
    decision_gate: Optional[str] = None
    has_session: bool = False
    session_id: Optional[str] = None
    prescription_count: int = 0
    prescription_ids: List[str] = Field(default_factory=list)
    exercise_ids: List[str] = Field(default_factory=list)
    substitution_applied: bool = False
    feedback_outcome_state: Optional[str] = None


class TodayTrainingDisplayView(DisplayView):
    state: str
    local_date: Optional[date] = None
    decision_gate: Optional[str] = None
    change_reason: Optional[str] = None
    session_id: Optional[str] = None
    prescription_count: int = 0
    exercise_ids: List[str] = Field(default_factory=list)
    substitution_applied: bool = False
    feedback_outcome_state: Optional[str] = None


# --------------------------------------------------------------------------- #
# Training exercise views                                                      #
# --------------------------------------------------------------------------- #


class ExerciseCatalogProviderView(ProviderView):
    exercise_id: str
    name_en: str
    name_zh: str
    difficulty: str
    training_roles: List[str] = Field(default_factory=list)
    has_substitutions: bool = False


class ExerciseCatalogDisplayView(DisplayView):
    exercise_id: str
    name_en: str
    name_zh: str
    difficulty: str
    training_roles: List[str] = Field(default_factory=list)
    instruction_steps: List[str] = Field(default_factory=list)
    form_cues: List[str] = Field(default_factory=list)
    # Only the safety-filtered substitutions (already returned by ``get_today``
    # on ``prescription.exercise``); the full catalog list is never re-expanded.
    substitution_ids: List[str] = Field(default_factory=list)
    illustration_asset_key: Optional[str] = None
    illustration_alt_zh: Optional[str] = None


class StopConditionCode(BaseModel):
    """A structured training stop-condition code (machine-readable only)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str


class StopConditionView(BaseModel):
    """A stop condition with bounded, reviewed display text (no free-text rule).

    Mirrors ``training.schemas.StopCondition`` but re-validated here so the
    agent projection stays independent of the domain model surface. The display
    text is bounded wellness-scope wording, never a clinical protocol.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(..., min_length=1, max_length=60)
    display_text_zh: str = Field(..., min_length=1, max_length=160)


class TrainingExerciseProviderView(ProviderView):
    exercise_id: str
    prescribed: bool
    sets: Optional[int] = None
    reps: Optional[int] = None
    duration_seconds: Optional[int] = None
    rest_seconds: Optional[int] = None
    catalog: Optional[ExerciseCatalogProviderView] = None
    stop_condition_codes: List[str] = Field(default_factory=list)


class TrainingExerciseDisplayView(DisplayView):
    exercise_id: str
    prescribed: bool
    sets: Optional[int] = None
    reps: Optional[int] = None
    duration_seconds: Optional[int] = None
    rest_seconds: Optional[int] = None
    relation_reason: Optional[str] = None
    catalog: Optional[ExerciseCatalogDisplayView] = None
    stop_conditions: List[StopConditionView] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Read Tool result + resolved context                                          #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ReadToolResult:
    """A read Tool's two separately typed projections.

    A plain frozen dataclass (not a Pydantic model) so the concrete
    ``provider_view`` / ``display_view`` subclass instances are preserved rather
    than being re-validated down to their base type.
    """

    tool_name: str
    provider_view: ProviderView
    display_view: DisplayView


class ContextProviderView(BaseModel):
    """Minimal, redacted context the provider may see for the resolved entry.

    Fields are optional because each entry populates only its minimal subset.
    They carry only structured codes/version/presence flags - never raw health
    payloads, free text, owner identity, or a full Tool result.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_type: EntryType
    entity_id: Optional[str] = None
    current_local_date: date
    # Health readiness / current safety decision.
    profile_configured: Optional[bool] = None
    health_profile_version: Optional[int] = None
    readiness_code: Optional[str] = None
    restricted: Optional[bool] = None
    health_fitness_goal: Optional[str] = None
    health_training_experience: Optional[str] = None
    health_weekly_frequency: Optional[int] = None
    health_session_duration_minutes: Optional[str] = None
    today_checkin_present: Optional[bool] = None
    today_checkin_risk: Optional[str] = None
    today_checkin_risk_version: Optional[str] = None
    weight_trend_sufficient: Optional[bool] = None
    weight_trend_window: Optional[int] = None
    weight_record_count: Optional[int] = None
    weight_trend_point_count: Optional[int] = None
    risk_gate_code: Optional[str] = None
    today_decision_gate: Optional[str] = None
    # Plan / today training presence + version/status codes.
    active_plan_present: Optional[bool] = None
    draft_present: Optional[bool] = None
    plan_version_id: Optional[str] = None
    plan_status: Optional[str] = None
    plan_decision_gate: Optional[str] = None
    draft_decision_gate: Optional[str] = None
    plan_change_reason: Optional[str] = None
    plan_requested_goal: Optional[str] = None
    plan_weekly_frequency: Optional[int] = None
    plan_session_duration_minutes: Optional[int] = None
    plan_session_count: Optional[int] = None
    plan_policy_version: Optional[str] = None
    today_state: Optional[str] = None
    # Posture issue codes.
    posture_issue_id: Optional[str] = None
    posture_issue_name_cn: Optional[str] = None
    posture_severity_levels: List[str] = Field(default_factory=list)
    posture_self_test_count: Optional[int] = None
    posture_has_confirmed_goal: Optional[bool] = None
    posture_suggestion_id: Optional[str] = None
    posture_profile_version: Optional[str] = None
    posture_rule_version: Optional[str] = None
    posture_assessment_severity: Optional[str] = None
    posture_assessment_certainty: Optional[str] = None
    posture_assessment_source_codes: List[str] = Field(default_factory=list)
    # Current owned session / exercise references.
    session_id: Optional[str] = None
    exercise_id: Optional[str] = None
    prescription_exercise_ids: List[str] = Field(default_factory=list)
    prescription_ids: List[str] = Field(default_factory=list)
    feedback_outcome_state: Optional[str] = None
    substitution_applied: Optional[bool] = None
    exercise_prescription_id: Optional[str] = None
    exercise_sets: Optional[int] = None
    exercise_reps: Optional[int] = None
    exercise_duration_seconds: Optional[int] = None
    exercise_rest_seconds: Optional[int] = None
    exercise_name_en: Optional[str] = None
    exercise_name_zh: Optional[str] = None
    exercise_difficulty: Optional[str] = None
    exercise_training_roles: List[str] = Field(default_factory=list)
    exercise_stop_condition_codes: List[str] = Field(default_factory=list)
    # Structured version codes.
    health_risk_version: Optional[str] = None
    posture_risk_version: Optional[str] = None
    catalog_version: Optional[str] = None


@dataclass(frozen=True)
class ResolvedContext:
    """The server's minimal, owned resolution of one turn's entry + entity."""

    entry_type: EntryType
    entity_id: Optional[str]
    iana_timezone: str
    current_local_date: date
    allowed_tools: Tuple[str, ...]
    provider_context: ContextProviderView
    fingerprint_payload: Dict[str, object] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Write action contracts (Task 3)                                             #
# --------------------------------------------------------------------------- #
#
# Exactly five server-side write actions. Each has a strict (``extra="forbid"``)
# typed Arguments model carrying ONLY the provider-typeable domain values: no
# actor/user_id, no server time, no policy/consent/fingerprint fields, and no
# free text. Arguments are bounded and stored only while a proposal is pending.
# A deterministic typed Diff is rendered server-side from these values; the
# provider never supplies the diff or any user-visible prose.

# The closed set of allowed write action tool names (server-side registry only;
# never registered in the provider-exposed read registry).
UPSERT_TODAY_CHECKIN = "upsert_today_checkin"
CREATE_WEIGHT_RECORD = "create_weight_record"
GENERATE_TRAINING_PLAN_DRAFT = "generate_training_plan_draft"
SUBSTITUTE_TODAY_EXERCISE = "substitute_today_exercise"
RECORD_TRAINING_FEEDBACK = "record_training_feedback"
WRITE_ACTION_NAMES = (
    UPSERT_TODAY_CHECKIN,
    CREATE_WEIGHT_RECORD,
    GENERATE_TRAINING_PLAN_DRAFT,
    SUBSTITUTE_TODAY_EXERCISE,
    RECORD_TRAINING_FEEDBACK,
)


class WriteActionArguments(BaseModel):
    """Base for all write-action argument models: strict and identity-free."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class UpsertTodayCheckinArguments(WriteActionArguments):
    """Ordinary check-in only: ``abnormal_pain`` is implicitly false and there
    are NO pain fields (no ``pain_followup`` / ``pain_area`` / ``pain_note``).
    A pain report uses the dedicated structured check-in/safety flow, never this
    action. The enums are reused from the health domain so parity is exact."""

    local_date: date
    sleep_quality: SleepQuality
    energy: Energy
    muscle_soreness: MuscleSoreness
    available_time: AvailableTime
    daily_status: DailyStatus


class CreateWeightRecordArguments(WriteActionArguments):
    """One manual weight record. ``note`` is forced null and is NOT a field; any
    free text is rejected (spec Tool Registry And Permission Matrix)."""

    recorded_at: datetime
    weight_kg: float = Field(..., ge=20.0, le=300.0)


class GenerateTrainingPlanDraftArguments(WriteActionArguments):
    """Create/replace a pending plan draft. Activation still requires Phase 4's
    independent plan-review confirmation; the Agent never activates a plan."""

    fitness_goal: str = Field(..., min_length=1, max_length=30)
    weekly_frequency: int = Field(..., ge=2, le=5)
    session_duration_minutes: Literal[15, 30, 45, 60]
    equipment_bodyweight: bool
    equipment_resistance_band: bool


class SubstituteTodayExerciseArguments(WriteActionArguments):
    """One current-day, owned, revalidated exercise substitution."""

    original_exercise_id: str = Field(..., min_length=1, max_length=60)
    replacement_exercise_id: str = Field(..., min_length=1, max_length=60)


class RecordTrainingFeedbackArguments(WriteActionArguments):
    """One current-day, owned session outcome. A pain/discomfort report routes
    to the dedicated safety flow, so ``discomfort`` is intentionally NOT an
    ordinary Agent feedback outcome (spec Tool Registry And Permission Matrix)."""

    outcome_state: Literal["completed", "partial", "too_busy", "intentional_rest"]


# --- deterministic typed diffs (server-rendered; no provider free text) -----


class WriteActionDiff(BaseModel):
    """Base for server-rendered write-action diffs (typed values only)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: str
    summary_code: str


class UpsertTodayCheckinDiff(WriteActionDiff):
    local_date: date
    abnormal_pain: bool = False


class CreateWeightRecordDiff(WriteActionDiff):
    recorded_at: datetime
    weight_kg: float


class GenerateTrainingPlanDraftDiff(WriteActionDiff):
    fitness_goal: str
    weekly_frequency: int
    session_duration_minutes: int
    requires_plan_review: bool = True


class SubstituteTodayExerciseDiff(WriteActionDiff):
    session_id: Optional[str] = None
    original_exercise_id: str
    replacement_exercise_id: str


class RecordTrainingFeedbackDiff(WriteActionDiff):
    session_id: Optional[str] = None
    outcome_state: str


# --- typed execution results (returned to the caller, never provider prose) -


class WriteActionResult(BaseModel):
    """Base for write-action execution results."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: str
    status: str  # "executed" | "replayed"
    result_ref: Optional[str] = None


# --------------------------------------------------------------------------- #
# Task 4 authenticated API envelopes                                           #
# --------------------------------------------------------------------------- #


class AgentApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentDisclosureView(AgentApiModel):
    disclosure_version: str
    provider_id: str
    provider_name_zh: str
    purpose_code: str
    processing_boundary_code: str
    data_scope_codes: List[str]
    application_retention_code: str
    withdrawal_available: bool
    agent_data_deletion_available: bool


class AgentCapabilitiesResponse(AgentApiModel):
    runtime_enabled: bool
    provider_configured: bool
    provider_id: Optional[str] = None
    model_id: Optional[str] = None
    disclosure_version: Optional[str] = None
    consent_active: bool
    available: bool
    result_code: str
    message: str
    disclosure: Optional[AgentDisclosureView] = None


class AgentConsentGrantRequest(AgentApiModel):
    accepted_provider_id: str = Field(..., min_length=1, max_length=60)
    accepted_disclosure_version: str = Field(..., min_length=1, max_length=60)
    idempotency_key: str = Field(..., min_length=1, max_length=128)


class AgentConsentWithdrawRequest(AgentApiModel):
    idempotency_key: str = Field(..., min_length=1, max_length=128)


class AgentConsentResponse(AgentApiModel):
    consent_id: UUID
    sequence_no: int
    status: Literal["granted", "withdrawn"]
    replayed: bool


class AgentDataDeletionResponse(AgentApiModel):
    deleted: bool = True
    consents_deleted: int
    runs_deleted: int
    tool_events_deleted: int
    proposals_deleted: int
    idempotency_deleted: int


class AgentToolDisplay(AgentApiModel):
    tool_name: str
    data: Dict[str, Any]


class AgentProposalView(AgentApiModel):
    proposal_id: UUID
    action: str
    diff: Dict[str, Any]
    expires_at: datetime


class AgentTurnResponse(AgentApiModel):
    run_id: Optional[UUID] = None
    status: Literal[
        "answer",
        "clarify",
        "unsupported",
        "proposal_pending",
        "safety_routed",
        "failed",
        "replayed",
    ]
    message: Optional[str] = None
    result_code: str
    display_data: List[AgentToolDisplay] = Field(default_factory=list)
    proposal: Optional[AgentProposalView] = None
    replayed: bool = False


class AgentConfirmRequest(AgentApiModel):
    idempotency_key: str = Field(..., min_length=1, max_length=128)


class AgentActionResponse(AgentApiModel):
    proposal_id: UUID
    status: str
    result_code: str
    result_ref: Optional[str] = None
    message: str


__all__ = [
    "EntryType",
    "SideEffectClass",
    "TurnInput",
    "ToolInput",
    "EmptyToolInput",
    "ListPostureIssuesInput",
    "GetPostureIssueInput",
    "GetTrainingExerciseInput",
    "AuthModel",
    "ProviderView",
    "DisplayView",
    "HealthProfileProviderView",
    "HealthProfileDisplayView",
    "TodayCheckinProviderView",
    "TodayCheckinDisplayView",
    "WeightTrendProviderView",
    "WeightTrendDisplayView",
    "PostureIssueProviderItem",
    "PostureIssueDisplayItem",
    "PostureIssueListProviderView",
    "PostureIssueListDisplayView",
    "PostureIssueDetailProviderView",
    "PostureIssueDetailDisplayView",
    "SelfTestGuideProviderView",
    "SelfTestGuideDisplayView",
    "PostureProfileEntryView",
    "PostureProfileProviderView",
    "PostureProfileDisplayView",
    "PriorityItemView",
    "PosturePrioritiesProviderView",
    "PosturePrioritiesDisplayView",
    "TrainingPlanSummaryView",
    "TrainingDraftProviderView",
    "TrainingDraftDisplayView",
    "ActivePlanProviderView",
    "ActivePlanDisplayView",
    "TodayTrainingProviderView",
    "TodayTrainingDisplayView",
    "ExerciseCatalogProviderView",
    "ExerciseCatalogDisplayView",
    "StopConditionCode",
    "StopConditionView",
    "TrainingExerciseProviderView",
    "TrainingExerciseDisplayView",
    "ReadToolResult",
    "ContextProviderView",
    "ResolvedContext",
    "UPSERT_TODAY_CHECKIN",
    "CREATE_WEIGHT_RECORD",
    "GENERATE_TRAINING_PLAN_DRAFT",
    "SUBSTITUTE_TODAY_EXERCISE",
    "RECORD_TRAINING_FEEDBACK",
    "WRITE_ACTION_NAMES",
    "WriteActionArguments",
    "UpsertTodayCheckinArguments",
    "CreateWeightRecordArguments",
    "GenerateTrainingPlanDraftArguments",
    "SubstituteTodayExerciseArguments",
    "RecordTrainingFeedbackArguments",
    "WriteActionDiff",
    "UpsertTodayCheckinDiff",
    "CreateWeightRecordDiff",
    "GenerateTrainingPlanDraftDiff",
    "SubstituteTodayExerciseDiff",
    "RecordTrainingFeedbackDiff",
    "WriteActionResult",
    "AgentApiModel",
    "AgentDisclosureView",
    "AgentCapabilitiesResponse",
    "AgentConsentGrantRequest",
    "AgentConsentWithdrawRequest",
    "AgentConsentResponse",
    "AgentDataDeletionResponse",
    "AgentToolDisplay",
    "AgentProposalView",
    "AgentTurnResponse",
    "AgentConfirmRequest",
    "AgentActionResponse",
]
