# Phase 4 Four-Week Training Plan MVP Implementation Plan

> Status: planned, 2026-07-27. Implementation is performed sequentially by the
> single delegated OpenCode session against
> `docs/specs/training/2026-07-27-four-week-plan-mvp.md`. Each Task follows the
> charter self-acceptance protocol: failing test first -> minimal implementation
> -> focused local verification -> spec-compliance review -> engineering/security/
> privacy review -> fix all P0/P1/P2 -> cohesive milestone commit -> push -> wait
> for exact-SHA Fast+Full CI -> read failing logs only if needed -> fix + add
> regression -> re-green -> record evidence.

**Goal:** Deliver deterministic four-week plan generation, confirmation, today
execution, feedback, and one-substitution, reusing the Phase 3 safety engine
without bypass or relaxation, plus the Flutter flow and the CI verification
matrix.

**Spec:** `docs/specs/training/2026-07-27-four-week-plan-mvp.md`

**Architecture:** New `backend/app/training/` modules (`models`, `state`,
`persistence`, `generator`, `rationale`, `service`, `schemas_api`, `router`)
reuse the unchanged Phase 3 pure engine + `validate_training_plan` Tool. A new
Alembic `0007` migration adds immutable plan versions and execution records. A
new authenticated `/api/v1/training` router is registered in `main.py`. Flutter
adds typed models, a provider, a 计划 tab, and the plan/today flow. The shared CI
runner and workflow are extended, not duplicated.

**Safety:** Blocked gates, stale versions, missing data, restricted and red-flag
cases fail closed everywhere. Identity is JWT-derived; no client-supplied
`user_id`, decision, candidate set, or version fingerprint is trusted. Writes are
atomic and idempotent. Free-text feedback notes are not stored.

## File And Module Map

Planned new/modified files:

- `docs/specs/training/2026-07-27-four-week-plan-mvp.md` (T0)
- `docs/plans/training/2026-07-27-four-week-plan-mvp.md` (T0)
- `docs/adr/0001-reuse-posture-idempotency-records.md` (T0)
- `docs/adr/0002-immutable-plan-versions-single-active.md` (T0)
- `docs/agent/ACTIVE_TASKS.md` (T0, T7)
- `.github/workflows/ci.yml` (T1: action SHA upgrades + Flutter job)
- `scripts/verify.py` (T1: Phase 4 fast targets)
- `backend/tests/test_verify_runner.py` (T1)
- `backend/app/training/models.py` (T2)
- `backend/app/training/state.py` (T2)
- `backend/app/training/persistence.py` (T2)
- `backend/alembic/env.py` (T2: import training.models)
- `backend/alembic/versions/0007_training_plans.py` (T2)
- `backend/tests/test_training_plan_state.py` (T2)
- `backend/tests/test_training_plan_persistence.py` (T2)
- `backend/tests/test_training_plan_migrations.py` (T2, incl. `requires_pg`)
- `backend/app/training/generator.py` (T3)
- `backend/app/training/rationale.py` (T3)
- `backend/tests/test_training_generator.py` (T3)
- `backend/tests/test_training_generator_safety.py` (T3)
- `backend/app/training/schemas_api.py` (T4)
- `backend/app/training/service.py` (T4)
- `backend/app/training/router.py` (T4)
- `backend/app/main.py` (T4: register router)
- `backend/tests/test_training_api.py` (T4)
- `backend/tests/test_training_api_safety.py` (T4)
- `backend/tests/test_openapi_contracts.py` (T4: extend)
- `backend/tests/test_phase4_e2e.py` (T7)
- `app/lib/models/plan_draft.dart`, `plan_version.dart`, `plan_session.dart`,
  `plan_feedback.dart` (T5)
- `app/lib/providers/plan_provider.dart` (T5)
- `app/lib/core/api_client.dart` (T5: training paths, optional)
- `app/lib/providers/auth_provider.dart` (T5: resetSessionState wiring)
- `app/test/models/plan_*_test.dart`, `app/test/providers/plan_provider_test.dart` (T5)
- `app/lib/screens/plan/{plan_entry,goal_schedule,draft_review,active_plan,today_session,feedback}_screen.dart` (T6)
- `app/lib/app.dart` (T6: 计划 tab + routes)
- `app/lib/screens/today/today_screen.dart` (T6: wire plan tasks)
- `app/lib/screens/profile/posture_profile_screen.dart` (T6: enable entry button)
- `app/test/screens/plan_*_test.dart` (T6)
- `docs/reports/phase4-opencode-handoff-2026-07-27.md` (T7)

Files intentionally not touched: Phase 3 pure modules (`safety.py`,
`candidates.py`, `validator.py`, `context.py`, `knowledge.py`, `policy.py`,
`tools.py`, `tool_contracts.py`, `schemas.py`, catalog/policy/manifest JSON,
SVG assets), posture/health domain code, auth/core, `main` branch, other
worktrees.

## Layered Verification Matrix

| Task | Local focused | Fast CI | Full CI |
| --- | --- | --- | --- |
| T0 spec/plan/ADR/ledger | links, source pins, contradiction/placeholder scan, `git diff --check` | draft PR CI runs on push | not required |
| T1 CI foundation | `verify.py fast` dry-run, workflow syntax, Flutter analyze/test local | required (exact SHA) | required (exact SHA) |
| T2 domain/state/persistence/migration | state/persistence tests, migration up/down (SQLite + PG16) | required | required (PG16, `VERIFY_REQUIRE_PG=1`) |
| T3 generator | generation property + safety matrix tests | required | required |
| T4 API | API/safety/OpenAPI/auth-isolation/concurrency tests | required | required (PG16) |
| T5 Flutter models/provider | model + provider tests, `flutter analyze`/`flutter test` | required (Flutter job) | required |
| T6 Flutter flow | widget + behavior tests, honest-state tests; Android smoke or honest skip | required (Flutter job) | required |
| T7 full phase | Phase 4 E2E + safety matrix + source/license/media audit + migration rehearsal | required | required on final SHA |

Local commands (run from repo root unless noted):

- `python scripts/verify.py fast`
- `VERIFY_REQUIRE_PG=1 python scripts/verify.py full` (set `PG_TEST_DSN` /
  `PG_TEST_ALLOW_DESTRUCTIVE=1` or rely on Docker `postgres:16`)
- `cd backend; python -m pytest tests/test_training_<x>.py -q`
- `cd app; flutter analyze; flutter test`

## Ordered Tasks

### Task 0: Specification, ADRs, plan, and task ledger

**Goal:** Authoritative Phase 4 behavior, source pins, workout.cool matrix,
state model, API contracts, generation behavior, failure semantics,
auth/idempotency, migrations, Flutter flow, observability, rollback, and the
executable acceptance matrix, plus ADRs for the costly cross-module choices.

**Allowed files:** `docs/specs/training/2026-07-27-four-week-plan-mvp.md`,
`docs/plans/training/2026-07-27-four-week-plan-mvp.md`,
`docs/adr/0001-*.md`, `docs/adr/0002-*.md`, `docs/agent/ACTIVE_TASKS.md`,
`opencode.json` (the one push-permission relaxation).

**Forbidden:** any `backend/**`, `app/**`, `.github/**`, `scripts/**` runtime
change; other worktrees; `main`.

**Steps:** audit repo truth (done: baseline `b7f8391`, Phase 3 head
`8459384`, training contracts as surveyed); write spec + 2 ADRs + this plan;
update `ACTIVE_TASKS.md` Phase 4 row to `in_progress` with base SHA
`b7f8391e17a2adbb4ae52d012b360d17ff4550fd`; self-review
(contradiction/placeholder/scope + `git diff --check`); commit; push; create
draft PR `codex/phase4-opencode-implementation` -> `codex/phase3-spec-plan`.

**Acceptance:** spec covers every charter-required section; ADRs justify reuse +
immutability; plan has a file/module map and per-task TDD ordering; ledger row
consistent; diff clean.

### Task 1: Phase 4 verification matrix (extend shared CI)

**Goal:** Fast CI covers Phase 4 backend + Flutter analyze + targeted tests; Full
CI covers complete backend + PostgreSQL 16 migration/integration + complete
Flutter tests + Phase 4 safety/E2E; machine-readable summaries; one workflow, not
a copy. Also: replace the deprecated Node-20 actions with current-major
immutable-SHA pins (verified against each action repo), not just suppress the
warning.

**Allowed files:** `.github/workflows/ci.yml`, `scripts/verify.py`,
`backend/tests/test_verify_runner.py`.

**Steps:**
1. Verify current major versions + commit SHAs for `actions/checkout`,
   `actions/setup-python`, `actions/upload-artifact`, and add
   `actions/setup-java` + `subosito/flutter-action` (SHA-pinned) for the Flutter
   job. Record the verified versions in the workflow comments.
2. Add a `flutter` job to `ci.yml`: checkout, setup-java, setup-flutter (pinned
   SDK `3.44.0`), `flutter pub get`, `flutter analyze`, `flutter test` with a
   JUnit-style machine-readable summary; same least-permission/cancel/timeout/
   synthetic-data rules.
3. Extend `scripts/verify.py` `FAST_TEST_TARGETS` with Phase 4 backend targets as
   they land (start with none beyond Phase 3; the list grows in T2-T4 guarded by
   the file existing). Keep the fail-closed runner contract intact.
4. Update `test_verify_runner.py` to assert the new targets list behavior /
   fail-closed guarantees still hold.
5. Local: `python scripts/verify.py fast`, `cd app; flutter analyze; flutter test`.
6. Commit, push, wait for Fast + Full on the exact SHA.

**Acceptance:** Fast + Full CI green on the exact SHA; Flutter job present and
green; no Node-20 deprecation annotation; action pins are immutable SHAs at
current majors; no workflow duplication.

### Task 2: Plan domain, state machine, persistence, migration

**Goal:** Typed plan version/session/prescription/feedback/substitution models,
legal-transition rules, atomic+idempotent persistence, and Alembic `0007`.

**Contract:** `state.py` exposes `is_legal_transition(from, to) -> bool` and a
`transition(...)` that returns the new status or raises; `persistence.py`
exposes `create_draft`, `confirm_and_activate` (atomic supersede), `cancel`,
`get_active`, `get_pending_draft`, `record_feedback`, `record_substitution` —
all ownership-scoped, reusing the posture idempotency helper. Models: tables and
columns per spec §Domain; partial unique index for single-active.

**Steps (TDD):**
1. Failing `test_training_plan_state.py`: every legal transition accepted; every
   illegal transition rejected; terminal immutability.
2. Implement `state.py`.
3. Failing `test_training_plan_persistence.py` (SQLite): single-active invariant;
   atomic supersede; replay returns recorded result; rollback after injected
   failure leaves no partial active; ownership scoping.
4. Implement `models.py` + `persistence.py`.
5. Failing `test_training_plan_migrations.py`: upgrade creates tables + index;
   downgrade drops only Phase 4 tables; `requires_pg` variant asserts PostgreSQL
   partial unique index behavior.
6. Author `0007_training_plans.py`; add `app.training.models` import to
   `alembic/env.py`.
7. Local: focused pytest; `VERIFY_REQUIRE_PG=1 python scripts/verify.py full`
   (PG16); commit; push; Fast + Full CI.

**Acceptance:** all focused + full tests green on SQLite and PG16; single-active
is a DB guarantee; terminal versions immutable; idempotent replay correct.

### Task 3: Deterministic four-week generator

**Goal:** Pure `generate_plan_draft(ctx, decision, candidate_result, catalog,
policy, safety_policy, *, request) -> GenerationResult` producing a validated
`TrainingPlanDraft`, plus stable rationale codes.

**Contract:** `GenerationResult` carries `ok`, `gate_status`, `draft?`,
`reason_codes`, `validation_violations?`. Eligible/conservative gates only;
supported goals only; server-populated fingerprints/versions; exactly four weeks;
prescriptions within `PrescriptionBounds` (conservative caps when conservative);
`weekly_sessions_max`/`recovery_hours_min`/movement-pattern recovery respected;
draft passed through the Phase 3 `validate_training_plan` Tool; validation
failure is fail-closed (no self-repair).

**Steps (TDD):**
1. Failing `test_training_generator.py`: property tests (within bounds; four
   weeks; unique session_order; stable for equal inputs; server fingerprints).
2. Failing `test_training_generator_safety.py`: scenario matrix (normal, caution,
   missing-data, restricted, red-flag, stale, conflicting-goal, equipment,
   schedule, recovery, provider-independent, unsupported goal).
3. Implement `generator.py` + `rationale.py`.
4. Local: focused pytest; commit; push; Fast + Full CI.

**Acceptance:** all generation + safety tests green; no blocked gate yields a
draft; validator failure never persisted/presented as usable.

### Task 4: Authenticated product API and application services

**Goal:** `/api/v1/training` endpoints per spec §Product API Contracts, enforcing
server-side identity, ownership, idempotency, stale-version rejection, current
safety rechecks, stable error contracts, atomic state changes, no cross-account
leakage.

**Contract:** `service.py` composes `build_context` + `classify_safety` +
`select_candidates` + `generate_plan_draft` + `validate_training_plan` +
`persistence`; `schemas_api.py` request/response models (`extra="forbid"`);
`router.py` endpoints use `Depends(get_current_user) -> str` and
`Depends(get_db)`; `main.py` registers the router.

**Steps (TDD):**
1. Failing `test_training_api.py`: draft generate/regenerate, draft get, confirm
   (success, stale, no-pending, already-confirmed), active get, today
   (active/rest/no-active/blocked), feedback (success, replay, duplicate),
   substitution (success, limit, blocked). Serialization + invalid-input 422/400.
2. Failing `test_training_api_safety.py`: cross-account isolation (no leakage,
   not-owner deterministic 404/410); concurrent confirm (one active); red-flag/
   restricted block; service-failure 503; stale-context 409.
3. Extend `test_openapi_contracts.py` with the Phase 4 paths + status codes.
4. Implement `schemas_api.py`, `service.py`, `router.py`; register in `main.py`.
5. Local: focused pytest; PG16 full; commit; push; Fast + Full CI.

**Acceptance:** OpenAPI extended and asserted; auth isolation; atomic single
active; idempotent; stable error codes; no raw health payloads in responses/logs.

### Task 5: Flutter contracts and state

**Goal:** Typed models, provider with loading/error/retry + stale-response
protection, account/session reset wiring, backend contract alignment.

**Contract:** hand-written strict `fromJson` models (unknown enum throws,
parse-error never downgraded); `plan_provider.dart` `StateNotifier` +
`LoadStatus` + generation counter; registered in `resetSessionState`; no safety
or recommendation logic in Flutter.

**Steps (TDD):**
1. Failing model tests: parse valid; reject unknown enum/missing field; no
   downgrade of blocked result.
2. Failing provider tests: loading/error/data; stale-response discarded;
   parse-error clears state; retry behavior.
3. Failing `auth_session_reset_test` extension: plan provider invalidated on
   logout/switch.
4. Implement models + provider + reset wiring (+ api client paths as needed).
5. Local: `flutter analyze; flutter test`; commit; push; Fast + Full CI.

**Acceptance:** Flutter analyze clean; model + provider + reset tests green;
parse-error never coerced.

### Task 6: Flutter plan and daily execution flow

**Goal:** End-to-end UI from entry (gated by `canGeneratePlan`) through goal/
schedule selection, draft review, explicit confirm, active plan, today's
prescriptions (illustration/steps/reps/rest/alternatives), version/change reason,
feedback states, and one substitution. Honest blocked/restricted/red-flag/stale/
parse-error states.

**Contract:** new 计划 tab (shell reshaped to 今日/计划/Agent(placeholder)/我的);
disabled Agent placeholder (Phase 5); entry button enabled iff
`canGeneratePlan`; UI never fakes success.

**Steps (TDD):**
1. Failing widget tests: entry gating; draft review renders prescriptions +
   alternatives; confirm triggers provider; active plan renders version/reason;
   today renders steps/reps/rest; feedback selection; honest states render.
2. Implement screens + shell changes + today wiring + entry enablement.
3. Local: `flutter analyze; flutter test`; Android smoke if a device/emulator is
   available (`flutter devices` then `flutter run` on Android, exercise the flow);
   otherwise record an explicit not-run reason.
4. Commit; push; Fast + Full CI.

**Acceptance:** widget + behavior tests green; honest states verified; Android
smoke evidence OR explicit honest not-run reason.

### Task 7: Full-phase self-acceptance and handoff

**Goal:** Complete local + remote verification matrix on the final SHA; synthetic
Phase 4 E2E (generate -> confirm -> today -> substitute -> feedback); safety
matrix; source/license/media audit; migration rehearsal; OpenAPI/Flutter checks;
reconcile spec/plan/roadmap/ledger with behavior.

**Steps:**
1. Failing `test_phase4_e2e.py`: full synthetic journey + safety matrix
   assertions.
2. Run `VERIFY_REQUIRE_PG=1 python scripts/verify.py full`, `flutter analyze`,
   `flutter test`; source/license/media audit (no new external sources; pinned
   unchanged); migration rehearsal on PG16.
3. Write `docs/reports/phase4-opencode-handoff-2026-07-27.md` with all charter
   §6 required content; mark Phase 4 candidate `review` (not verified/complete/
   merged). Update `ACTIVE_TASKS.md`.
4. Commit; push; wait for Fast + Full CI on the final SHA.

**Acceptance:** final SHA Fast + Full CI green; handoff complete and honest;
status `review`; stop and await Codex independent acceptance.

## Self-Review (Plan Author)

- **Spec coverage:** every charter §3 milestone maps to a Task; every spec
  section (domain/state, generation, API, failure, auth/idempotency, migrations,
  Flutter, acceptance) maps to Task steps.
- **Placeholders:** none; code-level detail is at signature/contract granularity
  sufficient to execute, with full implementations produced during each Task.
- **Type consistency:** `GenerationResult`, `plan_version_id`, `outcome_state`,
  operation names (`plan_generate`, `plan_confirm`, `session_substitute`,
  `session_feedback`), and rationale codes are used consistently across spec,
  ADRs, and plan.
