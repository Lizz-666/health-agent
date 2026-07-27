# Phase 4 Four-Week Training Plan MVP

> Status: planned, 2026-07-27. This is the current Phase 4 product specification,
> authored by the delegated OpenCode session as Task 0 of the Phase 4 charter
> (`docs/agent/PHASE4_OPENCODE_CHARTER.md`). It is personal-development validation,
> not clinical or public-release approval. Runtime code is implemented by Tasks 2-7
> against this document; until then behavior is undefined and must not be claimed.

## Outcome

A user can generate, review, explicitly confirm, and execute a **deterministic**
four-week posture-priority home-training plan built from the Phase 3 training
knowledge and safety engine, then record one day's execution outcome and see the
plan's version and change rationale.

The deterministic engine produces a complete executable baseline without an LLM.
Phase 4 adds **no** new AI provider and makes **no** live-model call. It reuses
the Phase 3 catalog, safety context, candidate engine, policy, and draft
validator as authoritative dependencies and does not bypass, duplicate, or relax
them.

## Non-Goals

- No chat Agent, LLM provider, prompt, or AI-written exercise prescription.
- No automatic multi-day plan restructuring, weekly review, or long-term adaptive
  progression (Phase 7). Phase 4 records feedback and applies only the explicitly
  scoped conservative same-day behavior defined in §10 (feedback states plus one
  re-validated user-initiated substitution).
- No automatic same-day shortening, deferral, or recovery substitution in Phase 4
  (Phase 7). The only same-day execution mutation is the feedback state and one
  optional substitution.
- No diagnosis, treatment, rehabilitation protocol, disease-specific exercise,
  pregnancy/underage planning, nutrition, payment, rankings, video tracking,
  gym-machine exercise, or professional-clearance workflow.
- No real health data, photos, production credentials, or live AI in code,
  fixtures, logs, screenshots, or reports.
- No change to the Phase 3 catalog, safety policy, training policy, candidate
  engine, validator, or provenance/source manifest. Those are read-only inputs.
- No copying of `Snouzy/workout-cool` code, data, UI, text, or media. Its Prisma
  model is a structural design comparison only (pinned in Phase 3 spec).

## Source And License Baseline

Phase 4 introduces **no new external source, dataset, code, or media**. It
operates entirely over the Phase 3 versioned catalog, safety policy, training
policy, and source manifest, whose pins and licenses are governed by the Phase 3
spec `Source And License Baseline` section:

- `hasaneyldrm/exercises-dataset` `7455efae41b330c265e7cd4b78dfa848e7ce5ebd` — MIT non-media metadata only.
- `Snouzy/workout-cool` `77f25a922b51be7d96bd051c5d2096959f0d61a8` — read-only structural comparison; no code/data/media copied.
- WHO 2020, ACSM 2026 position stand, PAR-Q+/ePARmed-X+ (reference only).

Phase 4 plan exercises must be recommendation-ready Phase 3 catalog items. Plan
illustrations are the existing project-authored local SVG assets referenced by
the catalog (`assets/training/illustrations/*.svg`); Phase 4 adds no new media.
The `workout.cool` comparison matrix is in §11.

## Users And Scenarios

- A generally healthy adult with a complete structured profile, a current
  non-blocking same-day check-in, and at least one confirmed active posture goal
  generates a deterministic four-week plan draft, reviews it, explicitly confirms
  it, and the confirmed plan becomes the single active plan.
- A cautious user receives a plan built only from conservative-policy candidates
  and conservative prescription bounds.
- A user with missing safety-required data (profile fields, current-day check-in,
  confirmed posture goal, or timezone) receives `clarification_required`, never a
  fabricated plan.
- A restricted user is hard-blocked from ordinary plan generation; no draft is
  persisted and no candidate IDs are exposed.
- A red-flag user is hard-stopped; generation, confirmation, substitution, and
  feedback cannot bypass the stop.
- Confirming a second draft supersedes the previously active plan; the old
  version is preserved as immutable history with a structured change reason.
- A user can record one day's execution as completed / partially completed / too
  busy / intentional rest / physical discomfort, and may apply one
  user-initiated, re-validated exercise substitution within today's session.
- A stale context (changed profile, check-in, posture signal, or version)
  invalidates a pending draft; confirmation re-runs the safety gate and rejects a
  stale draft rather than activating it.

## Assumptions And Open Decisions

### Approved decisions (this Task 0)

- **Backend package**: Phase 4 lives in `backend/app/training/` alongside the
  Phase 3 pure engine. New modules: `models.py` (SQLAlchemy persistence),
  `state.py` (legal-transition rules), `persistence.py` (atomic/idempotent
  writes), `generator.py` (deterministic four-week builder), `rationale.py`
  (stable change-reason codes), `service.py` (application services over the
  engine + persistence), `schemas_api.py` (request/response), `router.py`
  (authenticated REST). The Phase 3 pure modules (`schemas`, `safety`,
  `candidates`, `context`, `validator`, `knowledge`, `policy`, `tools`,
  `tool_contracts`) are reused unchanged.
- **Generation is pure given a context + decision + candidate result**. The
  generator consumes `TrainingSafetyContext`, `TrainingSafetyDecision`, and
  `CandidateResult` produced by the Phase 3 engine, selects exercises, assigns
  prescriptions within bounds, and emits a `TrainingPlanDraft` that is validated
  by the Phase 3 `validate_training_plan` Tool before persistence or presentation.
  No LLM, no random ordering, no client-supplied fingerprint/version.
- **Goals supported for plan generation**: `posture_improvement`, `fat_loss`,
  `basic_strength` (roadmap Phase 4 scope). `mobility` and `general_wellness` are
  not Phase 4 plan-generation goals; a request for them returns
  `goal_not_supported_yet`. Goal support does not change safety: restricted and
  red-flag users are blocked regardless of goal.
- **Schedule model**: the user chooses weekly frequency (2-5) and per-session
  duration (15/30/45/60 minutes). The generator deterministically distributes
  sessions across the week (posture-priority ordering, evenly spaced recovery)
  and emits exactly four weeks. The user does not pick days of week.
- **Same-day scope (MVP)**: record a feedback state per today's session
  (`completed`, `partial`, `too_busy`, `intentional_rest`, `discomfort`) plus at
  most one user-initiated exercise substitution within today's session, each
  re-running the current safety gate. Auto shortening, deferral, and recovery
  substitution are Phase 7.
- **Generation and confirmation are separate**. A draft has no execution effect.
  Only an explicitly confirmed draft, revalidated at confirm time, becomes
  active. At most one active plan per user (enforced by DB constraint).
- **Immutable versions**. Every generated draft that is confirmed becomes an
  immutable plan version. Superseding/cancelling creates a new version row; the
  old row is never overwritten. Source/catalog/policy/profile/context
  fingerprints are stored with each version.
- **Idempotency**. Generation, confirmation, substitution, and feedback writes
  accept an idempotency key and are atomic. Retries with the same key return the
  recorded result and do not create a second active plan or a duplicate feedback
  record. The existing `posture.idempotency_records` table is **reused** (see
  ADR-0001) rather than duplicated, with a Phase 4 operation namespace.
- **Auth/ownership**. Identity is JWT-derived via `Depends(get_current_user) ->
  str`. No endpoint accepts `user_id`, a risk decision, a candidate set, a
  version fingerprint, or an authorization claim from the client. The server
  assembles context via the Phase 3 `build_context` ownership-scoped reads.
- **`can_generate_plan`** (posture confirm response) remains a soft UI hint that
  confirmed goals exist; it is **not** an authorization. The authoritative gate
  is `classify_safety` re-run at every generation/confirmation/substitution.
  Phase 4 does not modify the posture domain.
- **Illustrations** are the catalog's existing local SVG references. Final
  illustration presentation and Flutter asset packaging are a Phase 4
  presentation decision (Task 6); no new media assets are authored.

### Deferred decisions

- Long-term adaptive progression, weekly review, multi-day restructuring, and
  automatic same-day shortening/deferral/recovery substitution belong to Phase 7.
- Agent chat entry (Phase 5) and nutrition (Phase 6) are out of scope.
- Public-release media review and AI-content labeling are release-gate work
  (roadmap §13), not this MVP.

## workout.cool Comparison Matrix (Required By Roadmap §8)

`Snouzy/workout-cool` Prisma model is a structural design comparison only (pinned
`77f25a922b51be7d96bd051c5d2096959f0d61a8`). No code, data, UI, text, or media is
copied. Phase 4 keeps the structural idea of program/week/session/prescription/
progress separation but adds the safety, versioning, confirmation, and ownership
guarantees workout.cool lacks.

| workout.cool model / relationship | Useful reference | Phase 4 decision | Required health-project difference |
| --- | --- | --- | --- |
| `Program -> ProgramWeek -> ProgramSession` | Clear cycle/week/session hierarchy | Keep the four-week / week / session hierarchy with typed Pydantic + SQLAlchemy models | Every generated structure references current safety/profile/policy/catalog fingerprints; generation re-runs risk classification and requires explicit user confirmation before activation |
| `ProgramSessionExercise -> ProgramSuggestedSet` | Ordered prescription and set structure | Use typed reps-or-duration prescriptions within Phase 3 `PrescriptionBounds`; bounded rest/load; conservative path | Prescriptions must be recommendation-ready Phase 3 catalog items inside deterministic prescription, volume, recovery, ordering, equipment, schedule, and contraindication constraints; re-validated before persistence |
| `WorkoutSession -> WorkoutSessionExercise -> WorkoutSet` | Actual execution separate from template | Keep execution-record separation: `training_session_feedback` records one day's outcome, distinct from the plan template | Add structured completion states (completed/partial/too_busy/intentional_rest/discomfort), ownership, idempotency, safety re-check on substitution, and no punitive treatment of rest |
| `UserProgramEnrollment` | Active program and current position | Keep "one active plan per user" with versioned activation/confirmation | Add immutable plan versions, structured change reasons, atomic supersede semantics, server-derived identity, and stale-version rejection |
| `UserSessionProgress` | Link prescribed session to actual workout | Keep the link via session + local-date feedback | Add idempotent per-day feedback, re-validated substitution, audit without raw health payloads, and red-flag stop |
| Overall model | Useful plan/execution separation | Structural reference only at pinned commit | Reject absence of user risk tier, missing-data gate, contraindications, red-flag stop, source lineage, policy version, validator, ownership isolation, and confirmation gating |

## Domain And State Model

### Plan version

A **plan version** is an immutable snapshot of one generated draft that reached a
terminal lifecycle state. Fields:

- `plan_version_id` (UUID PK), `user_id` (FK, ownership)
- `requested_goal` (one of the three supported goals)
- `source_context_fingerprint`, `profile_version`, `catalog_version`,
  `policy_version`, `source_manifest_version` (freshness pins, server-populated)
- `weekly_frequency` (2-5), `session_duration_minutes` (15/30/45/60)
- `status` (`draft`, `active`, `superseded`, `cancelled`)
- `change_reason` (stable code from `rationale.py`, e.g. `initial_confirmation`,
  `superseded_by_new_draft`, `cancelled_by_user`)
- `decision_gate` (the `GateStatus` at confirmation), `decision_fingerprint`
- `generated_at`, `confirmed_at` (nullable until confirmation), timestamps

The four-week/week/session/prescription structure is stored as normalized child
rows mirroring `TrainingPlanDraft.sessions`:

- `training_sessions`: `plan_version_id` FK, `week_index` 1-4, `day_of_week` 1-7,
  `session_order` 1-20 (unique within week), `target_minutes`.
- `training_prescriptions`: `session_id` FK, `exercise_id` (FK-by-value to
  catalog `exercise_id`), `sets`, `reps` (nullable), `duration_seconds`
  (nullable), `rest_seconds`, `relation_reason` (nullable),
  `relation_source_exercise_id` (nullable), `display_order`.

Catalog references are by value (`exercise_id`) because the catalog is versioned
JSON, not a DB table. A prescription whose `exercise_id` is not in the current
catalog is a data-integrity error caught at read time (fail-closed display).

### Feedback (execution record)

`training_session_feedback` records one day's outcome for one session of the
active plan:

- `feedback_id` PK, `user_id` FK, `plan_version_id` FK, `session_id` FK,
  `local_date` (server-relevant), `outcome_state` (`completed`, `partial`,
  `too_busy`, `intentional_rest`, `discomfort`), `note` is **not** stored (free
  text is never a safety rule input and is excluded to minimize sensitive-data
  retention), `created_at`, `idempotency_key` (UNIQUE).
- At most one feedback row per `(session_id, local_date)`; replay returns the
  recorded row.

### Substitution (execution record)

A substitution is recorded as a structured delta on today's session, not a
rewrite of the immutable plan version:

- `training_session_substitutions`: `user_id`, `plan_version_id`, `session_id`,
  `local_date`, `original_exercise_id`, `replacement_exercise_id`,
  `relation_reason`, `decision_gate` (re-validated), `created_at`,
  `idempotency_key` UNIQUE. At most one substitution per
  `(session_id, local_date)`.

### Lifecycle state machine

Legal transitions:

```text
draft --confirm(revalidate ok)--> active
draft --supersede(new draft confirmed)--> superseded   (a pending draft is replaced when a newer draft is confirmed)
draft --cancel(user)--> cancelled
active --supersede(new draft confirmed)--> superseded
active --cancel(user)--> cancelled
superseded --(terminal)--> (none)
cancelled --(terminal)--> (none)
```

Invariants:

- At most one `active` plan per user (DB partial unique index on `user_id WHERE
  status='active'`).
- Confirming a new draft atomically sets the previous active (or pending draft)
  to `superseded`/`cancelled` and the new one to `active`, in one transaction.
- Terminal states (`superseded`, `cancelled`) are immutable.
- A `draft` is short-lived: at most one non-terminal plan per user; generating a
  new draft when a pending draft exists replaces that pending draft (the pending
  draft never had execution effect).

### Idempotency

Reuses `posture.idempotency_records` (`(user_id, operation, idempotency_key)`
UNIQUE) with Phase 4 `operation` values: `plan_generate`, `plan_confirm`,
`session_substitute`, `session_feedback`. A replay with a seen key returns the
stored `result_ref` and does not re-execute the side effect. See ADR-0001.

## Deterministic Generation Behavior

`generator.generate_plan_draft(ctx, decision, candidate_result, catalog, policy,
safety_policy, *, request) -> TrainingPlanDraft` is **pure** given the Phase 3
inputs. Behavior:

1. Require an eligible gate (`eligible` or `eligible_conservative`). Any blocking
   gate (`clarification_required`, `restricted`, `red_flag`) returns no draft and
   a structured `GenerationResult` with `gate_status` and reason codes; nothing is
   persisted.
2. Require the supported requested goal; else `goal_not_supported_yet`.
3. Bind to the current request/profile/versions exactly (reuse the Phase 3
   `_context_is_current` semantics via the candidate result).
4. From the ordered `CandidateResult.candidates`, select a posture-priority set:
   warmup + strength/corrective + mobility/recovery roles, capped by
   `policy.max_exercises_per_session` and bounded by session duration.
5. Assign prescriptions within each exercise's `PrescriptionBounds` (conservative
   caps when `decision.gate_status == eligible_conservative`), respecting
   `weekly_sessions_max`, `recovery_hours_min`, and movement-pattern recovery.
6. Distribute `weekly_frequency` sessions across 7 days with even recovery
   spacing; emit exactly four weeks; each session has `week_index` 1-4,
   `day_of_week` 1-7, unique `session_order` within the week.
7. Populate `source_context_fingerprint` from `decision.fingerprint` and all
   version pins from the current context; never accept these from the client.
8. Build a `TrainingPlanDraft` and run the Phase 3 `validate_training_plan` Tool
   (authorization-aware adapter). A draft that fails validation is **never**
   persisted or presented as usable; the failure is returned as a structured
   `GenerationResult` with the validator's violation codes. This is fail-closed:
   the generator does not self-repair by dropping violations.

Stable rationale codes (`rationale.py`) drive `change_reason` and UI text, e.g.
`initial_confirmation`, `superseded_by_new_draft`, `cancelled_by_user`,
`substitution_applied`, `feedback_recorded`. Codes are stable strings; display
text is bounded and wellness-scoped, never clinical.

## Product API Contracts

All endpoints under `APIRouter(prefix="/api/v1/training", tags=["training"])`,
JWT-only via `Depends(get_current_user) -> str`. No endpoint accepts `user_id` or
safety/version fields from the client. Request bodies are typed Pydantic
(`extra="forbid"`). Responses never include raw health payloads, pain notes, or
another user's data. Stable error codes are returned as `{detail, code}`.

| Method + path | Purpose | Idempotency | Notes |
| --- | --- | --- | --- |
| `POST /plans:draft` | Generate (or regenerate) the user's single pending draft from current context | key required | Body: `{fitness_goal, weekly_frequency, session_duration_minutes, equipment_bodyweight, equipment_resistance_band, iana_timezone, idempotency_key}`. Re-runs `classify_safety`; blocked gate -> structured error, no draft persisted. Replaces any existing pending `draft`. |
| `GET /plans/draft` | Retrieve the current pending draft or an explicit `no_draft` state | n/a | Ownership-scoped; returns draft + validation status. |
| `POST /plans:confirm` | Explicitly confirm+activate the pending draft | key required | Re-runs safety + validator on the stored draft; rejects stale fingerprint/version; atomically supersedes the previous active plan. Returns the new active version. |
| `GET /plans/active` | Retrieve the single active plan or `no_active_plan` | n/a | Includes immutable version + change reason. |
| `GET /plans/today?iana_timezone={tz}` | Today's prescriptions for the active plan | n/a | Derives the local date and current plan week from the injected UTC clock, confirmation time, and validated IANA timezone. Returns `no_active_plan` / `blocked` / `rest_day` / `session` / `plan_complete`; a session includes the effective substitution and recorded feedback state. |
| `POST /plans/sessions/{session_id}:substitute?iana_timezone={tz}` | One user-initiated substitution within today's session | key required | Body: `{original_exercise_id, replacement_exercise_id, idempotency_key}`. The validated timezone is required for the server-derived date. The original must be prescribed today; the replacement must be an original catalog substitution, survive current candidate selection, and pass whole-plan validation. |
| `POST /plans/sessions/{session_id}:feedback?iana_timezone={tz}` | Record today's outcome state | key required | Body: `{outcome_state, idempotency_key}`. The validated timezone is required for the server-derived date. No free-text note accepted. At most one per `(session_id, local_date)`; replay returns the recorded row. |

Stable error codes (non-exhaustive): `clarification_required`,
`restricted_no_plan`, `red_flag_stop`, `goal_not_supported_yet`,
`stale_context`, `no_pending_draft`, `no_active_plan`, `already_confirmed`,
`substitution_limit_reached`, `feedback_already_recorded`, `not_owner`,
`session_not_today`, `substitution_not_safe`, `stored_draft_invalid`,
`invalid_idempotency_key`. HTTP status follows the existing convention
(`AppException` -> `{detail, code}`; 400 for contract violations, 409 for
conflicting state, 410 for gone idempotency anchors, 503 for service failure).

## Failure Semantics

- Generation/confirmation/substitution/feedback are **atomic and idempotent**. A
  failure mid-way leaves no partially active plan and no duplicate feedback row.
- AI/provider failure is impossible by construction (no provider is called). The
  only external dependencies are the DB and the deterministic engine; a DB error
  surfaces as 503 and never converts to a "normal" plan.
- A blocked safety gate never yields a usable draft or a successful confirmation.
- A stale draft (changed source data/versions) is rejected at confirmation with
  `stale_context`; the client must regenerate.
- Loss of an idempotency anchor (`idempotency_result_gone`, HTTP 410) is
  deterministic and recoverable by regenerating/re-recording.
- Free-text feedback notes are not accepted or stored (minimizes sensitive-data
  retention; free text is never a safety input).

## Auth, Ownership, Privacy, And Observability

- Identity is exclusively JWT-derived. Cross-account access is impossible by
  construction (ownership-scoped reads/writes; no `user_id` parameter).
- Operational logging records decision fingerprint, gate/risk result, reason
  codes, versions, and counts — never raw health profile fields, pain notes,
  photos, or another user's identifiers. This matches the Phase 3 observability
  contract.
- `today`/`feedback`/`substitution` use the server-derived local date (from the injected UTC
  clock + trusted IANA timezone), never a client-supplied date as the authority.
- Tests, fixtures, screenshots, and reports use synthetic data only.

## Migrations

- New Alembic revision `0007_training_plans`, revises `0006_health_weight_tracking`.
- `backend/alembic/env.py` imports `app.training.models` so `Base.metadata`
  includes the new tables.
- Tables: `training_plan_versions`, `training_sessions`, `training_prescriptions`,
  `training_session_feedback`, `training_session_substitutions`. The existing
  `posture.idempotency_records` is reused (no new idempotency table).
- Upgrade creates tables + the per-user single-active partial unique index.
- Downgrade drops the five Phase 4 tables in dependency order; it does **not**
  touch posture/health tables or `idempotency_records` rows for other operations.
  Because plan data is recreation-safe (regenerable from the deterministic
  engine), downgrade is a safe recovery path; users regenerate after rollback.
- Rehearsed on SQLite (tests) and PostgreSQL 16 (`requires_pg`).

## Flutter Flow

- Entry: the existing disabled "生成改善计划" button in
  `posture_profile_screen.dart` is enabled iff
  `confirmedGoals?.canGeneratePlan == true`; it routes to the new plan flow.
- Flow: current health-profile goal (one of three) + frequency + duration and
  equipment review -> draft review
  (exercises, prescriptions, illustrations, alternatives) -> explicit confirm ->
  active plan view (four weeks, sessions, version/change reason) -> today's
  prescriptions (steps, reps/duration, rest, alternatives, illustration) ->
  feedback state selection + optional one substitution.
- The plan page does not fabricate request defaults. It loads the current
  structured health profile and blocks generation when required values are
  missing, unsupported, or contain no selected equipment. Changes are made in
  the health-profile flow so Phase 3 request/profile equality remains authoritative.
- A new bottom-nav **计划** tab is added; the shell is reshaped to 今日 / 计划 /
  Agent(disabled placeholder) / 我的 per vision.md. Agent tab is a disabled
  placeholder (Phase 5).
- UI must surface `blocked` / `restricted` / `red_flag` / `no_active_plan` /
  `rest_day` / `plan_complete` / `stale` / `parse_error` states honestly and never pretend success
  or coerce a blocked result to a normal plan (matches existing
  parse-error-never-downgrades convention).
- Typed models under `app/lib/models/plan*.dart` (hand-written strict `fromJson`,
  no codegen); provider under `app/lib/providers/plan_provider.dart`
  (`StateNotifier` + `LoadStatus` + generation counter for stale-response
  protection). The provider is registered in `auth_provider.resetSessionState` so
  account switch/logout clears plan state (no cross-account leakage).
- No recommendation or safety logic lives in Flutter; the client only renders
  server results and collects explicit confirmations/feedback.

## Acceptance Criteria

- Normal, caution, missing-data, restricted, and red-flag synthetic contexts
  produce the exact expected generation outcome (draft / conservative draft /
  clarification / hard-block / hard-stop).
- A confirmed plan is the single active plan; a second confirmation supersedes
  the previous active plan atomically; superseded/cancelled versions are
  immutable.
- Generation failure (blocked gate or validator failure) never persists a draft
  and never leaves a partially active plan.
- Every plan exercise traces to a recommendation-ready Phase 3 catalog item;
  prescriptions stay within bounds; recovery/frequency/ordering constraints hold.
- Each generation, confirmation, substitution, and feedback re-runs the current
  safety gate from current structured data; a stale draft is rejected at confirm.
- Ownership isolation: no endpoint returns or mutates another user's plan; no
  `user_id` is accepted from the client.
- Idempotent writes: replaying generate/confirm/substitute/feedback with the same
  key returns the recorded result and creates no duplicate active plan or
  feedback row.
- Migration upgrade/downgrade is rehearsed on SQLite and PostgreSQL 16.
- Flutter `analyze` clean; targeted Flutter tests + widget tests green; honest
  blocked/restricted/red-flag/stale/parse-error rendering verified.
- OpenAPI contracts extended and asserted; serialization, invalid input, auth
  isolation, concurrent/stale confirmation, and rollback behavior tested.
- The workout.cool comparison matrix (§11) accurately states accepted and
  rejected concepts and links the pinned commit.
- Fast and Full GitHub CI pass on the exact Task commit SHAs; no real health
  data, photo, production credential, or live AI call is used anywhere.

## Test And Evaluation Strategy

- **Generation**: property tests (prescriptions always within bounds; exactly
  four weeks; unique session_order; stable output for equal inputs); scenario
  matrix (normal, caution, missing-data, restricted, red-flag, stale-context,
  conflicting-goal, equipment, schedule, recovery, provider-independent).
- **State machine**: every legal transition accepted; every illegal transition
  rejected; terminal immutability; single-active invariant under concurrency.
- **Persistence/idempotency**: atomic supersede; replay returns recorded result;
  no duplicate active plan; rollback after mid-transaction failure.
- **API**: OpenAPI shape, serialization, invalid input (422/400), auth isolation
  (cross-account 404/403-equivalent), concurrent + stale confirmation (409),
  substitution/feedback limits, service-failure 503.
- **Migration**: upgrade/downgrade on SQLite and PostgreSQL 16; constraint
  checks; partial unique index behavior.
- **Flutter**: model parsing (unknown enum throws, never downgraded); provider
  loading/error/data + stale-response protection; account-reset clears plan
  state; widget tests for the flow and every honest blocked/restricted/red-flag/
  stale/parse-error state.
- **E2E**: synthetic generate -> confirm -> today -> substitute -> feedback, plus
  the full safety matrix, on the final SHA.

## Rollout And Rollback

- No user-facing activation beyond the authenticated API and Flutter UI; no
  deployment or release in this phase.
- Rollback is reverting the Phase 4 commits and/or downgrading migration `0007`.
  Plan data is recreation-safe (regenerable from the deterministic engine), so
  downgrade is a safe recovery path; users regenerate plans after rollback.
- A bad catalog/policy version is governed by the Phase 3 compatibility
  allowlist; Phase 4 surfaces "unavailable" rather than loading a stale version.
