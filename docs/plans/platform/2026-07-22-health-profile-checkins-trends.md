# Phase 2 Health Profile, Check-Ins, And Trends Implementation Plan

**Goal:** Deliver a verified Phase 2 vertical slice where users can maintain structured health profile data, complete daily check-ins, record optional weight, and review trends/grid data without AI inference or training-plan generation.

**Spec:** `docs/specs/platform/2026-07-22-health-profile-checkins-trends.md`

**Architecture:** Add a backend health/tracking domain with deterministic safety readiness, authenticated REST endpoints, migrations, and Flutter models/providers/screens. Existing `user` remains basic account profile. Existing posture profile remains posture-specific evidence.

**Safety:** Phase 2 stores sensitive health data, requires abnormal-pain follow-up, classifies red-flag/restricted states deterministically, blocks future recommendation readiness when data is missing or unsafe, and never treats AI or missing data as normal.

**Verification:** Focused backend tests per task, OpenAPI contract tests, migration checks, Flutter model/provider/widget tests, `flutter analyze`, full relevant test suites, and an Android emulator smoke before phase exit.

## File And Module Map

Likely backend additions:

- `backend/app/health/__init__.py`
- `backend/app/health/models.py`
- `backend/app/health/schemas.py`
- `backend/app/health/service.py`
- `backend/app/health/router.py`
- `backend/app/health/risk.py`
- `backend/app/health/trends.py`
- `backend/app/health/audit.py`
- `backend/alembic/versions/0004_health_profile_tracking.py`
- `backend/app/main.py`
- `backend/tests/test_health_profile.py`
- `backend/tests/test_health_checkins.py`
- `backend/tests/test_health_weight_trends.py`
- `backend/tests/test_health_activity_grid.py`
- `backend/tests/test_health_privacy.py`
- `backend/tests/test_openapi_contracts.py`
- `backend/tests/test_phase2_e2e.py`

Likely Flutter additions and edits:

- `app/lib/models/health_profile.dart`
- `app/lib/models/daily_checkin.dart`
- `app/lib/models/weight_record.dart`
- `app/lib/models/activity_grid.dart`
- `app/lib/providers/health_profile_provider.dart`
- `app/lib/providers/daily_checkin_provider.dart`
- `app/lib/providers/weight_trend_provider.dart`
- `app/lib/providers/activity_grid_provider.dart`
- `app/lib/screens/today/today_screen.dart`
- `app/lib/screens/profile/health_profile_screen.dart`
- `app/lib/screens/profile/weight_trend_screen.dart`
- `app/lib/screens/profile/activity_grid_screen.dart`
- `app/lib/app.dart`
- `app/test/models/*`
- `app/test/providers/*`
- `app/test/screens/*`

Existing files to treat carefully:

- `backend/app/auth/models.py`: do not keep expanding the account user table for Phase 2 health fields unless a migration decision explicitly requires it.
- `backend/app/user/*`: keep basic account profile compatibility.
- `backend/app/posture/*`: do not move posture safety logic during Phase 2 unless a task explicitly scopes a shared safety extraction.
- `app/lib/providers/auth_provider.dart`, `app/lib/providers/user_provider.dart`, `app/lib/app.dart`: update only as needed for cache clearing and navigation.

## Ordered Tasks

### Task 0: Phase 2 specification and task ledger

**Files:** `docs/specs/platform/2026-07-22-health-profile-checkins-trends.md`, `docs/plans/platform/2026-07-22-health-profile-checkins-trends.md`, `docs/agent/ACTIVE_TASKS.md`.

**Behavior:** Establish the approved Phase 2 scope, safety boundaries, task split, and coordination rules. Do not implement runtime behavior.

**Tests/Evals:** Markdown/link inspection and `git diff --check`.

**Done when:** Spec and implementation plan exist, `ACTIVE_TASKS.md` identifies Phase 2 as current initiative, and all implementation tasks are registered as planned with non-overlap rules.

### Task 1: Backend health profile domain and migration

**Files:** `backend/app/health/models.py`, `backend/app/health/schemas.py`, `backend/app/health/risk.py`, `backend/alembic/versions/0004_health_profile_tracking.py`, migration tests.

**Behavior:** Add health profile, profile audit metadata, and deterministic profile readiness/risk classification primitives. Keep basic account profile unchanged.

**Tests/Evals:** Migration upgrade against SQLite test DB and PostgreSQL path where available; unit tests for allowed enums, missing required data, equipment invariants, restricted cases, and raw sensitive field exclusion from audit metadata.

**Done when:** Schema and domain functions can represent complete, incomplete, restricted, and red-flag-ready profile states without API or Flutter changes.

### Task 2: Health profile API, deletion, and OpenAPI contract

**Files:** `backend/app/health/router.py`, `backend/app/health/service.py`, `backend/app/main.py`, `backend/tests/test_health_profile.py`, `backend/tests/test_health_privacy.py`, `backend/tests/test_openapi_contracts.py`.

**Behavior:** Implement authenticated `GET/PUT/DELETE /api/v1/health/profile`. Enforce token-derived user ownership, validation, structured missing data, and deletion semantics.

**Tests/Evals:** API tests for unauthenticated access, invalid enum/range values, no `user_id` parameter, cross-user isolation, deletion not returned, and OpenAPI response/request schemas.

**Done when:** A user can view, update, and delete Phase 2 profile data through the API, and another user cannot read or mutate it.

### Task 3: Daily check-in and conditional safety follow-up

**Files:** `backend/app/health/models.py`, `backend/app/health/schemas.py`, `backend/app/health/risk.py`, `backend/app/health/router.py`, `backend/app/health/service.py`, `backend/tests/test_health_checkins.py`.

**Behavior:** Implement today check-in read/write, check-in history, deletion, daily uniqueness, abnormal-pain follow-up requirements, and deterministic `normal/caution/restricted/red_flag` check-in risk summary.

**Tests/Evals:** Normal 20-second payload, abnormal pain missing follow-up, severe acute pain, neurological symptom, dizziness/chest symptom, active rest, safety adjustment, stale local date handling, and cross-user isolation.

**Done when:** Check-ins can be safely recorded and red-flag check-ins cannot be mistaken for ordinary readiness by later services.

### Task 4: Weight records, trend calculation, and activity grid API

**Files:** `backend/app/health/trends.py`, `backend/app/health/router.py`, `backend/app/health/service.py`, `backend/tests/test_health_weight_trends.py`, `backend/tests/test_health_activity_grid.py`.

**Behavior:** Implement manual weight CRUD, trend endpoint with raw points and moving trend metadata, and activity grid projection over Phase 2 check-in statuses.

**Tests/Evals:** Valid/invalid weight bounds, update/delete, insufficient data metadata, deterministic moving trend values, date-range bounds, no recommendation text from trend, and grid statuses `none`, `checked_in`, `active_rest`, `safety_adjustment`.

**Done when:** The backend can render Phase 2 trend/grid data without training plans and without single-day adjustment claims.

### Task 5: Flutter Phase 2 models and providers

**Files:** `app/lib/models/health_profile.dart`, `app/lib/models/daily_checkin.dart`, `app/lib/models/weight_record.dart`, `app/lib/models/activity_grid.dart`, `app/lib/providers/health_profile_provider.dart`, `app/lib/providers/daily_checkin_provider.dart`, `app/lib/providers/weight_trend_provider.dart`, `app/lib/providers/activity_grid_provider.dart`, auth/session reset tests.

**Behavior:** Add typed client models and providers for health profile, today check-in, weight trend, and activity grid. Clear all Phase 2 state on logout, token failure, account switch, and parse failure.

**Tests/Evals:** Model parsing tests for null/missing/unknown values; provider tests for fetch/update/delete, stale response handling, parse errors, logout reset, and cross-account state clearing.

**Done when:** Flutter can consume Phase 2 APIs with safe state behavior before UI screens are added.

### Task 6: Flutter My page health profile, weight trend, and grid UI

**Files:** `app/lib/screens/profile/profile_screen.dart`, `app/lib/screens/profile/health_profile_screen.dart`, `app/lib/screens/profile/weight_trend_screen.dart`, `app/lib/screens/profile/activity_grid_screen.dart`, related widget tests.

**Behavior:** Add My page entries for health profile, optional weight trend, activity grid, and Phase 2 data deletion. Keep posture profile separate from health profile.

**Tests/Evals:** Widget tests for missing data, edit flows, deletion confirmation, trend insufficient data, grid statuses, narrow-screen text fit, loading/error states, and logout clearing.

**Done when:** A user can view/correct/delete Phase 2 health profile data and inspect weight/grid data from My without seeing stale data.

### Task 7: Flutter Today page check-in flow

**Files:** `app/lib/screens/today/today_screen.dart`, `app/lib/app.dart`, related provider and screen tests.

**Behavior:** Create the Today page for daily check-in. Normal check-in should be short; abnormal pain opens conditional follow-up. Active rest and safety adjustment count as valid states. Do not display future plan data as if a plan exists.

**Tests/Evals:** Widget tests for normal check-in path, abnormal pain follow-up, red-flag result display, active rest, safety adjustment, offline/error handling, and bottom navigation behavior.

**Done when:** Today owns today's check-in and safety state, while plan functionality remains absent or explicitly unavailable.

### Task 8: Phase 2 final E2E, documentation, and exit audit

**Files:** `backend/tests/test_phase2_e2e.py`, `docs/reports/phase2-exit-audit-2026-07-22.md` or current exit date, roadmap/spec/plan status sections, README updates if commands change.

**Behavior:** Verify the complete Phase 2 flow and update documentation to actual behavior only after fresh evidence.

**Tests/Evals:** Backend full tests, PostgreSQL migration/integration path where available, `ruff`/compile checks if used by current repo, `flutter analyze`, full Flutter tests, Android emulator smoke for login, My health profile, Today check-in, pain follow-up, weight entry, trend/grid, logout/account switch.

**Done when:** Phase 2 exit criteria are met with fresh evidence and no unresolved P0/P1/P2 findings.

## Migration And Compatibility

- Use a new Alembic revision after current head `0003_posture_contract.py`.
- Do not mutate Phase 1 posture tables unless explicitly needed and reviewed.
- Existing `/api/v1/user/profile` and Flutter onboarding must remain compatible while Phase 2 screens are introduced.
- If downgrade is not practical for a personal-development data migration, document a local reset path and keep destructive cleanup out of automatic test setup.
- SQLite tests and PostgreSQL behavior must both be considered for JSON fields, date handling, uniqueness constraints, and cascade/deletion semantics.

## Rollout And Rollback

Rollout:

1. Land backend domain and API first.
2. Land Flutter client models/providers after API contracts stabilize.
3. Land My page health data surfaces.
4. Land Today check-in flow.
5. Run E2E and update docs.

Rollback:

- Disable or hide Phase 2 routes in Flutter if backend endpoints are unavailable.
- Keep posture Phase 1 flows independent so rollback of Phase 2 UI does not break posture assessment.
- Maintain a documented local DB downgrade or reset path for Phase 2 tables.

## Task Coordination Rules

- Each implementation task uses a separate `codex/phase2-taskN-*` branch and worktree.
- Tasks that edit the same file must run serially unless the file ownership is explicitly split in `ACTIVE_TASKS.md`.
- Do not start Task 5 before API response shapes from Tasks 2-4 are stable or mocked from committed schemas.
- Do not start Task 7 before Task 5 provider state reset behavior is verified.
- Do not mark Phase 2 complete until Task 8 reruns backend and Flutter verification on the integrated branch.
