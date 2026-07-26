# Phase 3 Training Knowledge And Safety Engine

> Status: approved Task 0 baseline, 2026-07-26. OpenCode delivered the Tasks 1-7
> runtime implementation, static data, tests and CI configuration on the single
> implementation branch `codex/phase3-opencode-implementation`
> (exit report: `docs/reports/phase3-exit-audit-2026-07-26.md`). Verified/complete
> status is recorded by Codex only after independent final acceptance; this note
> is delivery evidence, not a verified/complete/public-release claim.

## Outcome

Phase 3 provides a deterministic, versioned training-knowledge and safety core that later plan generation can call without an LLM. Given a synthetic current user context, the system can decide whether ordinary training selection is allowed, return a traceable set of recommendation-ready home exercises, and validate a structured draft plan without silently repairing unsafe input.

The phase does not generate, persist, display, or execute a four-week plan. Those user flows belong to Phase 4.

## Non-Goals

- No Flutter training catalog, plan, or execution UI.
- No four-week plan generator, plan persistence, enrollment, workout history, or progression execution.
- No Agent chat, LLM provider, prompt, or AI-written exercise prescription.
- No medical diagnosis, treatment, rehabilitation protocol, disease-specific exercise, or professional-clearance workflow.
- No gym machines, barbells, dumbbells, kettlebells, cable stations, Smith machines, pull-up bars, or other unapproved equipment.
- No third-party exercise images, videos, GIFs, thumbnails, or copied media.
- No direct import of posture `corrections` prose as approved exercise or safety content.
- No public API solely to expose internal safety-policy details. Phase 4 may add authenticated product APIs over these services.

## Users And Scenarios

- A generally healthy adult with complete structured profile data and a current non-blocking check-in receives a deterministic allowed exercise set compatible with bodyweight and/or resistance-band equipment.
- A cautious user receives only exercises and prescription bounds approved for the conservative policy path.
- A user with missing safety-required data receives `clarification_required`, not a fabricated normal result or a partial candidate set.
- A restricted user receives a hard block from ordinary automatic training selection, with bounded education-only next actions.
- A red-flag user receives a hard stop. Exercise substitution, progression, or plan validation cannot bypass the stop.
- Multiple confirmed posture goals produce a de-duplicated candidate set with deterministic conflict handling.
- An exercise with incomplete safety metadata, unreviewed provenance, invalid relations, or unapproved media cannot become recommendation-ready.
- A draft plan containing a forbidden exercise, excessive prescription, insufficient recovery, or stale context fails structured validation.

## Assumptions And Open Decisions

### Approved decisions

- Phase 3 uses a versioned curated JSON catalog and versioned policy JSON loaded through typed Pydantic models. Curated content changes less often than user state and does not require a database migration in this phase.
- The backend package is `backend/app/training/`. Domain functions remain callable without HTTP, a database session, or an LLM.
- Phase 3 composes existing Phase 1 posture and Phase 2 health facts. It does not redefine their clinical meaning or infer risk from free text.
- A training decision always has two dimensions: `gate_status` and `risk_tier`. Missing data is `clarification_required`, not a health tier disguised as `normal`.
- Recommendation requests recompute from current structured data. Stored historical labels alone are not accepted as a fresh decision.
- Phase 3 ships no automated professional-clearance flow. Restricted/red-flag recovery requires changed structured source data and a fresh classification; time elapsed, disclaimer acceptance, free text, or a button click never clears a block.
- This Task 0 specification and implementation plan define the safety-policy boundaries, state precedence, normalization behavior, and executable safety cases. OpenCode implements Tasks 1-7 on one branch without choosing, adding, or relaxing safety behavior. Unspecified cases fail closed and are documented; only an ambiguity whose alternatives materially change product or safety behavior pauses the affected work for Codex clarification. There is no routine intermediate checkpoint.
- The initial catalog targets 24-36 reviewed exercises. Coverage and safety completeness matter more than importing all available external records.
- `validate_training_plan` is an internal typed application Tool in Phase 3. It has no write side effects and no public router endpoint.

### Deferred decisions

- Phase 4 decides plan persistence, confirmation, execution records, and product API shapes.
- Phase 4 decides final illustration presentation and Flutter asset packaging. Phase 3 requires only original/local illustration references with verifiable ownership; no external media may enter the catalog.
- A future approved workflow may record professional guidance. Until then, professional claims in free text cannot relax restrictions.

## Source And License Baseline

Last verified: 2026-07-26. Every imported or reviewed item records a stable source identifier, applicable scope, version/date, and review status.

| Source | Pinned version | Permitted Phase 3 use | Explicit exclusion |
| --- | --- | --- | --- |
| WHO Guidelines on Physical Activity and Sedentary Behaviour | 2020, ISBN 978-92-4-001512-8 | General adult physical-activity context and major-muscle strengthening baseline | Not a per-exercise contraindication source and not a rehabilitation protocol |
| ACSM Position Stand, *Resistance Training Prescription for Muscle Function, Hypertrophy, and Physical Performance in Healthy Adults* | 2026 official position stand and ACSM summary published 2026-03-17 | Healthy-adult resistance-training policy envelope; supports bodyweight, elastic-band, and home training; supports simple conservative programming over advanced methods | Does not authorize disease-specific, post-operative, pregnancy, underage, injury, or red-flag programming |
| Official PAR-Q+ / ePARmed-X+ site | current official individual version identified as 2025 on 2026-07-26 | Design reference for pre-participation clarification/restriction concepts | Do not copy questionnaire text, claim PAR-Q+ certification, or treat the project's narrower profile as equivalent clearance |
| `hasaneyldrm/exercises-dataset` | commit `7455efae41b330c265e7cd4b78dfa848e7ce5ebd` | MIT-covered non-media metadata only: names, taxonomy, equipment, target/secondary muscles, and schema/import ideas | Exclude upstream instruction/translation text from the initial catalog as well as `images/`, `videos/`, GIFs, thumbnails, `image`, `gif_url`, `media_id`, and media attribution payloads. Retain the pinned LICENSE and copyright notice in the project third-party notices for any copied metadata |
| `Snouzy/workout-cool` | commit `77f25a922b51be7d96bd051c5d2096959f0d61a8` | Read-only comparison of Prisma exercise, program, session, set, enrollment, and progress relationships | Do not copy code or data; do not inherit its missing risk, contraindication, stop-condition, provenance, or safety-validation model |

Primary references:

- https://www.who.int/publications/i/item/9789240015128
- https://acsm.org/education-resources/pronouncements-scientific-communications/position-stands/
- https://acsm.org/resistance-training-guidelines-update-2026/
- https://eparmedx.com/how-to-cite/
- https://github.com/hasaneyldrm/exercises-dataset/tree/7455efae41b330c265e7cd4b78dfa848e7ce5ebd
- https://github.com/Snouzy/workout-cool/tree/77f25a922b51be7d96bd051c5d2096959f0d61a8

## Domain Model

### Catalog envelope

`ExerciseCatalog` contains:

- `catalog_id`
- `content_version`
- `schema_version`
- `published_at`
- `policy_compatibility`
- `source_manifest_version`
- `exercises`

The loader rejects unknown fields, duplicate IDs, unsupported versions, invalid references, and any record that cannot be parsed. A catalog-load failure is explicit and never yields an empty-but-successful catalog.

### Exercise

Every exercise has:

- identity: stable `exercise_id`, Chinese and English names, `training_roles`, difficulty
- scope: `goals`, `movement_patterns`, `movement_purposes`, primary and secondary muscles, allowed equipment
- posture mapping: `applicable_posture_signals`, `not_applicable_posture_signals`
- safety: structured contraindication selectors, stop-condition codes and bounded display text
- instructions: ordered steps, form cues, common mistakes
- relations: regression, progression, and substitution IDs
- prescription bounds: mode (`reps` or `duration`), set/repetition/duration/rest bounds, conservative-policy eligibility, recovery interval, progression and regression conditions
- illustration: local asset key, ownership type, content hash, and review state; external URL fields are forbidden
- provenance: source records, imported fields, license, source commit/version, content version, review status, review scope, reviewer role, reviewed date

`training_roles` is a non-empty set drawn from `warmup`, `strength`, `corrective`, `mobility`, and `recovery`. `movement_purposes` is a non-empty set of versioned policy tags used for deterministic de-duplication; it is not inferred from prose.

`review_status` is one of `draft`, `needs_review`, `approved`, or `retired`. Only `approved` can be recommendation-ready. In Phase 3, `approved` means approved for this repository's personal-development validation scope; it is not a clinical endorsement, professional certification, or public-release approval. `review_scope` must therefore be `personal_development` in the initial catalog. A future public release requires a separate qualified content/safety review and a new review scope/version.

Illustration provenance contains `creator_type=project_authored`, `generation_tool`, `created_at`, `source_declaration=original_no_external_reference`, content hash, review status/scope, reviewer role, and reviewed date. It may not claim ownership merely because a file is local.

### Recommendation-ready invariant

An exercise is recommendation-ready only when all of the following are true:

- all required schema fields are present and non-empty
- provenance and license records are complete
- safety, instructions, relations, posture mapping, prescription bounds, and local illustration metadata are reviewed
- review status is `approved` and review date is not later than catalog publication
- review scope is explicit and compatible with the runtime environment; personal-development approval cannot be represented as public-release approval
- every relation points to an existing approved exercise and does not point to itself
- equipment is within Phase 3 scope
- no external media field or URL is present
- the exercise is compatible with the active policy version

Failure of any invariant excludes the exercise and produces a structured catalog validation error. It is never auto-filled.

### Training safety context

`TrainingSafetyContext` is an immutable request snapshot assembled from current structured sources:

- user ID for authorization at the application boundary, omitted from logs and pure-engine fixtures
- health profile data and version
- validated IANA time zone, server UTC evaluation time, server-derived current local date, and current-day check-in data/token
- retained abnormal-pain check-in records needed to recompute whether an earlier red-flag signal is still present; free-text notes are excluded from the engine input
- active posture safety signals and their lifecycle/version
- current posture profile entries and confirmed active goals
- requested fitness goal, equipment, frequency, and duration
- policy and catalog versions
- `evaluated_at`

Free-text notes, AI response prose, raw photos, and chat history are not safety-rule inputs.

The application boundary validates the IANA time-zone identifier and derives `current_local_date` from the injected/server UTC clock; it never trusts a client-provided date as the freshness authority. Because Phase 2 check-ins have no monotonic version, their freshness token is the canonical hash of `id`, `local_date`, UTC-normalized `updated_at`, `risk_version`, and structured safety fields excluding `pain_note`. Retained abnormal-pain records are represented by a stable sorted aggregate of those tokens. Profile version/updated time, posture active-signal digest, active-goal fingerprint, policy version, and catalog version are also included in the decision fingerprint.

### Safety decision

`TrainingSafetyDecision` contains:

- `gate_status`: `eligible`, `eligible_conservative`, `clarification_required`, `restricted`, `red_flag`
- `risk_tier`: `normal`, `caution`, `restricted`, `red_flag`, or null when classification cannot run because required data is missing
- `reason_codes`
- `missing_fields`
- `blocking_source_refs`
- profile, check-in, posture-risk, training-policy, and catalog versions
- deterministic decision fingerprint

Safety precedence is:

```text
red_flag > restricted > clarification_required > eligible_conservative > eligible
```

Any active red flag is global for ordinary training selection. Restricted status also blocks ordinary automatic selection. Caution can use only conservative-policy exercises and bounds. A missing current-day check-in blocks user-specific recommendation selection; catalog browsing and catalog validation remain available without user context.

### Draft plan validation contract

Phase 3 defines a minimal `TrainingPlanDraft` solely for validation and Phase 4 handoff:

- draft ID and requested goal
- source context fingerprint and all relevant versions
- exactly four weeks; each session has `week_index` 1-4, `day_of_week` 1-7, and a unique `session_order` within the week, giving a strict ordinal timeline for frequency and recovery checks
- each prescription references a catalog exercise and carries sets plus reps or duration, rest, and optional relation reason

It does not include persistence, activation, completion, ratings, or progress state.

Context assembly uses existing health/posture public read services where available. If an existing domain lacks a required read method, Phase 3 may use a narrowly scoped ownership-filtered read query in `training.context`; it must not write another domain's tables, duplicate its classification rules, or expose a generic repository/SQL escape hatch.

`PlanValidationResult` contains `valid`, decision/version metadata, and structured violations. Validation is pure, side-effect free, and fail-closed. It never rewrites a draft, substitutes an exercise, lowers volume, or persists a partial result.

## Risk And Eligibility Rules

1. Recompute health-profile readiness from current typed fields. A stored `ready` label is not sufficient. Training safety additionally requires `pain_injury_limitations` to be present (an empty list means explicitly none), `risk_screen` to be present, and every risk-screen qualifier to be explicitly `yes` or `no`; missing or `unknown` returns `clarification_required`.
2. Recompute the current check-in risk from structured fields. Missing required follow-up is invalid input, not caution or normal.
3. Recompute retained structured abnormal-pain records instead of trusting only their stored labels. A retained record that still classifies as red flag remains blocking; a later normal day or time elapsed does not clear it.
4. Consume active posture safety-signal lifecycle and current posture risk. Do not infer red flags from posture severity, knowledge prose, or free text.
5. Any active or retained red flag blocks candidate selection, substitution, progression, and plan validation regardless of user goal.
6. A restricted qualifier blocks ordinary automatic training. The response may contain education-only next actions but no exercise candidate IDs.
7. Every user-specific candidate or draft-validation request requires at least one current active user-confirmed posture goal whose profile entry remains confirmed and non-blocked, regardless of fitness goal. Missing or stale posture selection returns `clarification_required`.
8. Phase 2 pain body-area and status fields are untrusted free-form values. A versioned Phase 3 normalization map accepts only reviewed aliases and yields canonical body-region/status codes. Any active limitation or abnormal-pain record that cannot be normalized returns `clarification_required`; it is never ignored or broadly guessed.
9. Missing health profile, required profile/safety fields, current-day check-in, confirmed posture goal, trustworthy time-zone data, or source-version data returns `clarification_required` and no candidate IDs.
10. Caution applies conservative prescription bounds and may exclude exercises not reviewed for the caution path.
11. Time elapsed, a newer normal check-in by itself, user acknowledgement, disclaimer acceptance, or free-text claims cannot lower risk.
12. Recovery requires a structured source correction that causes fresh recomputation, lawful deletion of the source record followed by a complete new context, an existing posture-signal resolution allowed by its lifecycle policy, or a future separately specified controlled recovery workflow. Phase 3 provides no manual override or professional-clearance claim field.
13. Changed structured source data triggers a fresh decision. No old decision token can authorize a new request after profile/check-in/posture/time-zone/policy/catalog version changes.

## Candidate Selection

Candidate generation is deterministic and ordered:

```text
validate context
-> classify safety gate
-> require recommendation-ready catalog entries
-> equipment filter
-> goal and confirmed-posture-signal filter
-> contraindication and not-applicable filter
-> conservative-policy filter when needed
-> de-duplicate by exercise ID and movement purpose
-> resolve conflicts by explicit policy priority
-> stable sort
-> return decision and trace
```

The engine returns exclusion reason codes without raw health values. External taxonomy does not directly establish posture suitability. Posture `corrections` and association weights can be reviewed as discovery inputs but never auto-promoted into applicability rules.

## Volume, Recovery, And Progression Policy

- Policy values are versioned product-policy constraints within the healthy-adult source envelope, not medical prescriptions.
- Phase 3 supports bodyweight and resistance-band prescriptions using bounded repetitions or duration. It does not require 1RM testing or training to failure.
- Each exercise defines allowable sets, reps/duration, rest, frequency, minimum recovery, and conservative-path bounds.
- Plan validation checks per-exercise bounds, session totals, weekly frequency, repeated movement-pattern recovery, and incompatible combinations.
- Progression and regression are explicit conditions. Phase 3 validates their structure but does not automatically apply them.
- No exercise may progress when the current safety decision is stale, restricted, or red flag.

## workout.cool Comparison Matrix

| workout.cool model/relationship | Useful reference | Phase 3 decision | Required health-project difference |
| --- | --- | --- | --- |
| `Exercise` + attribute tables | Exercise identity and many-to-many taxonomy | Keep the identity/taxonomy concept in versioned curated JSON | Add contraindications, stop conditions, posture mappings, prescription bounds, provenance, review state, and media ownership; reject unreviewed nullable safety fields |
| `Program -> ProgramWeek -> ProgramSession` | Clear cycle/week/session hierarchy | Defer to Phase 4 plan model | Every generated structure must reference current safety/profile/policy/catalog versions and require user confirmation |
| `ProgramSessionExercise -> ProgramSuggestedSet` | Ordered prescription and set structure | Use only as a shape comparison for the Phase 3 draft-validator contract | Use typed reps-or-duration prescriptions, bounded rest/load policy, alternatives, and deterministic validation |
| `WorkoutSession -> WorkoutSessionExercise -> WorkoutSet` | Actual execution separate from template | Defer to Phase 4 | Add safety state, partial/rest outcomes, pain feedback, idempotency, and audit; no direct copy |
| `UserProgramEnrollment` | Active program and current position | Defer to Phase 4 | Add versioned activation/confirmation and atomic replacement semantics |
| `UserSessionProgress` | Link prescribed session to actual workout | Defer to Phase 4 | Add structured completion states, feedback, safety adjustment, and no punitive treatment of rest |
| Overall model | Useful plan/execution separation | Structural reference only at pinned commit | Reject absence of user risk tier, missing-data gate, contraindications, red-flag stop, source lineage, policy version, and validator |

## Tool Contract

`validate_training_plan(context, draft) -> PlanValidationResult`:

- accepts typed, schema-validated inputs only
- authorizes and loads current user context in the application adapter before entering the pure validator
- recomputes safety and candidate eligibility for every call
- rejects stale context fingerprints and version mismatches
- returns all deterministic violation codes suitable for tests and bounded UI mapping
- has no write side effect, no LLM call, and no automatic repair
- never returns `valid=true` for `clarification_required`, `restricted`, or `red_flag`

## Safety, Privacy, And Failure Handling

- Tests and evaluations use synthetic profiles only.
- Decision traces contain codes, versions, IDs, and fingerprints, not raw pain notes, allergies, photos, or unrestricted profile payloads.
- Source/import failures, schema failures, version mismatches, unknown enums, unknown exercise IDs, relation cycles, and stale decisions fail closed.
- Catalog data is treated as untrusted at load time, including vendored external metadata.
- A third-party instruction cannot override project policy, mark itself approved, or authorize media use.
- An illustration is supplemental orientation only. It cannot establish exercise safety, override written stop conditions, or substitute for reviewed instructions. Public release requires a separate visual-form review by a suitably qualified reviewer.
- No AI provider is called in Phase 3.
- `backend/app/training/data/THIRD_PARTY_NOTICES.md` preserves the pinned upstream copyright/license notice for copied external metadata. Absence or hash mismatch fails the source audit.

## Observability And Audit

Pure functions return structured traces. Application logging may include:

- decision fingerprint
- gate/risk result
- reason codes
- catalog/policy/schema versions
- count of included/excluded exercises
- validator violation codes

It must not include raw health profile fields, free text, source photos, or another user's identifiers. Phase 4 will decide persistence of plan-generation audit records.

## Acceptance Criteria

- A valid catalog and policy load deterministically; malformed or incomplete content fails closed.
- Every recommendation-ready exercise satisfies the full schema, source, review, relation, policy, and local-media invariants.
- Every approved entry is explicitly scoped to personal-development validation; no artifact claims clinical, professional, or public-release approval.
- The initial approved catalog contains 24-36 home exercises covering bodyweight and resistance band plus warm-up, strength, corrective, mobility, and recovery roles.
- Source manifest records license, pinned commit/version, imported fields, field mapping, and media exclusion.
- Synthetic normal, caution, missing-data, restricted, and red-flag contexts produce the exact expected gate.
- Restricted and red-flag contexts return no ordinary candidate set; red flag cannot be bypassed by substitution or validation.
- Multi-posture candidate results are deterministic, de-duplicated, and conflict-resolved.
- Draft validation rejects unknown/unapproved/forbidden exercises, out-of-bounds prescriptions, inadequate recovery, stale versions, and blocked contexts.
- `validate_training_plan` is typed, pure at the domain layer, authorization-aware at the adapter, and has no persistence or AI side effect.
- The workout.cool comparison matrix remains linked to the pinned commit and accurately states accepted and rejected concepts.
- Full backend tests, ruff, real PostgreSQL regression where affected, source/license checks, and safety evaluation matrix pass on the integrated Phase 3 SHA.

## Test And Evaluation Strategy

- Schema tests: required fields, extra fields, enums, bounds, relation integrity, review gate, media rejection, source manifest.
- Property/invariant tests: forbidden exercises never appear, output order is stable, no duplicate IDs, blocked gates always produce zero candidates, validation never mutates input.
- Safety matrix: healthy beginner, experienced user, incomplete profile, missing/unknown risk-screen fields, null vs empty pain limitations, known and unknown body-area aliases, missing check-in, untrusted time zone/date, cautious pain, restricted qualifier, current and retained red flag, missing/stale confirmed posture goal, active posture signal, conflicting posture goals, stale versions, malicious free text.
- Candidate tests: equipment, goal, posture applicability, contraindications, conservative path, de-duplication, conflicts, substitutions, progressions/regressions.
- Validator tests: valid draft, unknown exercise, catalog/policy mismatch, excessive bounds, recovery conflict, blocked context, stale fingerprint.
- Integration tests: current health/posture adapters, authorization isolation, deletion/missing source behavior, no sensitive logging.
- Full regression: all backend tests and lint. Flutter regression is required only if a Phase 3 task unexpectedly touches Flutter, which is forbidden by default.

## Rollout And Rollback

- Catalog and policy versions are immutable once used as evidence. Corrections publish a new version.
- Phase 3 has no user-facing activation and no plan writes; rollback is removal of the training package registration or reverting the integrated commits.
- A bad catalog/policy version is disabled by compatibility allowlist; the system reports unavailable rather than loading a previous version silently.
- CI validates source manifests, content hashes, schema, safety matrix, and full backend regression before integration.
