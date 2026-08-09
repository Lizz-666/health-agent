# Phase 8 Personal Development Acceptance Implementation Plan

**Goal:** Reproduce the complete supported-adult core journey in the real
Flutter application on an Android emulator over a deterministic local FastAPI
backend, with safe reset, failure evidence, and exact-SHA acceptance.

**Spec:** `docs/specs/platform/2026-08-09-personal-development-acceptance.md`

**Architecture:** ADR-0008 test-only full application assembly, disposable
database, scripted Agent provider, named fixture checkpoints, real HTTP Flutter
driver, and separate completion of production account-deletion orchestration.

**Safety:** Existing rules are reused unchanged. Scripted AI cannot decide
safety, reset cannot target non-disposable storage, and every missing/error/
restricted path fails closed.

**Verification:** Focused tests at each Gate; strict Full/PostgreSQL for privacy
and state changes; Flutter analyze/test; real-HTTP runner; Android emulator
journey; exact-SHA GitHub Fast/Flutter/Full and Phase 8 acceptance jobs.

## Baseline And Working Rules

- Gate 0 exact base is Phase 7 closure
  `36be9a0f0cd989f32c8f4f7f7b9e2bc5fb4c66e6`, never `main` or an older branch.
- Gate 0 branch/worktree is `codex/phase8-spec-plan` /
  `health-worktrees/phase8-spec-plan`; it contains documentation only.
- After Gate 0 closure, Codex creates one implementation branch/worktree from
  the accepted exact SHA. No Phase 8 business or harness code starts earlier.
- One Task has one writer. Codex owns all privacy deletion, test isolation,
  cross-domain contracts, CI, integration, fixes, and final E2E.
- OpenCode receives only Task 3 after Gate 2 freezes the HTTP/control contract.
  Codex is read-only on its allowlisted files while that session writes.
- OpenCode may not commit, push, merge, rebase, change dependencies/CI/settings,
  use live AI, real health data/photos, or edit outside its exact allowlist.
- Every Gate accepts an exact committed SHA only after real diff review and fresh
  local verification. GitHub CI must check out the same SHA. Reports are inputs,
  never acceptance proof.

## Ownership Map

| Area | Writer | Scope |
| --- | --- | --- |
| Gate 0 contracts | Codex | Phase 8 spec, plan, ADR-0008, task ledger, review report |
| Full test app and reset isolation | Codex | backend test factories/server/control plane and focused tests |
| Complete internal account deletion | Codex | posture purge plus health/training/nutrition/Agent adapters and privacy/PG tests |
| HTTP runner, fixtures, evals, commands | Codex | scripts, backend tests/data, CI acceptance job, run docs |
| Flutter automation anchors and driver | One OpenCode + Claude session | exact Task 3 app allowlist only |
| Integration fixes, Android replay, screenshots, final audit | Codex | any accepted Task 3 files plus final test/docs/CI scope |

## Gate 0: Contract Closure

### Task 0: Audit, specification, ADR, plan, and ledger

**Writer:** Codex only.

**Allowed files:**

- `docs/specs/platform/2026-08-09-personal-development-acceptance.md`
- `docs/plans/platform/2026-08-09-personal-development-acceptance.md`
- `docs/adr/0008-isolated-synthetic-acceptance-harness.md`
- `docs/agent/ACTIVE_TASKS.md`
- `docs/reports/phase8-gate0-review-2026-08-09.md`

**Behavior:** Close product defaults, real-HTTP definition, reset/production
deletion separation, safety/failure matrix, checkpoint limits, Flutter boundary,
task ownership, Gates, commands, CI, and rollback. No business code.

**Done when:** A findings-first cold review has no unresolved P0/P1/P2; documents
agree on the exact Phase 7 base and all approved decisions; the branch is clean
after commit and exact-SHA CI Fast/Flutter/Full is green.

**Verification:**

```powershell
python scripts/verify.py fast
Set-Location app
flutter analyze
flutter test
```

## Gate 1: Isolation And Privacy Foundation

### Task 1: Full test app, reset control plane, and complete account purge

**Writer:** Codex only.

**Expected files:**

- `backend/tests/phase8_app_factory.py`
- `backend/tests/phase8_device_server.py`
- `backend/tests/phase8_fixtures.py`
- `backend/tests/test_phase8_harness.py`
- `backend/tests/test_phase8_deletion.py`
- `backend/app/posture/purge.py`
- narrow deletion adapters in `backend/app/health/`, `backend/app/training/`,
  `backend/app/nutrition/`, and `backend/app/agent/` only as proven necessary
- `backend/tests/test_privacy_gate.py`, `backend/tests/test_pg_integration.py`

**Behavior:** Assemble all production routers with test dependencies; enforce
the exact disposable DB path and production non-import invariant; implement
authenticated closed control routes; reset every table/object/provider/fault;
seed closed checkpoints through validated builders; extend internal
`account_deletion` to every current owned table without exposing a new public
identity endpoint or weakening object-first purge/retry semantics.

**Required tests:**

- production app has no `/__phase8` routes and imports no Phase 8 test module;
- external/malformed DB URLs, wrong control header, unknown checkpoint/fault,
  and concurrent reset fail closed before destructive work;
- reset removes every table and synthetic object, including rows that exist only
  in health, base training, nutrition, Agent, adaptive, and idempotency domains;
- account purge owner isolation, empty-domain detection, FK order, retries,
  expired lease, duplicate invocation, rollback/fault injection, and tombstone
  invariants on SQLite and disposable PostgreSQL;
- scripted provider is bounded and no live provider method is invoked.

**Acceptance commands:**

```powershell
python -m pytest backend/tests/test_phase8_harness.py backend/tests/test_phase8_deletion.py backend/tests/test_privacy_gate.py -q
python scripts/verify.py full
```

Strict GitHub Full must run all PostgreSQL-marked cases with zero skips.

## Gate 2: Real-HTTP Journey And Evaluations

### Task 2: Acceptance CLI, HTTP journey, fixture/eval matrices, and CI job

**Writer:** Codex only.

**Expected files:**

- `scripts/phase8.py`
- `backend/tests/test_phase8_http_journey.py`
- `backend/tests/data/phase8_training_cases.v1.json`
- `backend/tests/data/phase8_agent_cases.v1.json`
- `backend/tests/test_phase8_evaluations.py`
- `backend/tests/test_verify_runner.py`
- `scripts/verify.py`
- `.github/workflows/ci.yml`
- focused local-run documentation under `docs/`

**Behavior:** Provide fail-fast `serve`, `reset`, `http`, `eval`, and `verify`
commands; run the complete API journey through a live localhost server and JWT;
record sanitized exact-SHA evidence; add versioned structured safety and Agent
eval datasets; verify one-shot failure/retry and malformed/unavailable paths;
add a non-live Phase 8 CI acceptance job.

**Required tests:** Every core API state transition, checkpoint disclosure,
wrong-server/mode refusal, port collision, server-not-ready timeout, child
process cleanup, no token/payload leakage, zero live-provider calls, safety
matrix coverage, and runner non-zero propagation.

**Acceptance commands:**

```powershell
python scripts/phase8.py verify --surface http
python scripts/verify.py fast
python scripts/verify.py full
```

Gate 2 freezes `/api/v1` usage, `/__phase8` control schemas, fixture names,
synthetic credentials, CLI commands, and stable evidence fields for Task 3.

## Gate 3: Flutter And Android Driver

### Task 3: Real-app automation anchors and core journey driver

**Writer:** One OpenCode + Claude session. Codex reviews and may later take over
fixes only after the session stops.

**Dependencies:** Accepted Gate 2 exact SHA and a Codex-issued prompt containing
the frozen contracts. Do not start from this Gate 0 branch or infer contracts.

**Allowed files:**

- `app/lib/screens/auth/login_screen.dart`
- `app/lib/screens/home/home_screen.dart`
- `app/lib/screens/issues/issue_list_screen.dart`
- `app/lib/screens/issues/issue_detail_screen.dart`
- `app/lib/screens/test/self_test_screen.dart`
- `app/lib/screens/result/result_screen.dart`
- `app/integration_test/phase8_core_journey_test.dart`
- `app/test/screens/login_screen_test.dart`
- `app/test/screens/self_test_screen_test.dart`
- `app/test/screens/result_screen_test.dart`

No backend, provider/domain model, dependency, generated platform file,
documentation, CI, or older integration-test edits are allowed. Existing keys
on posture profile, plan, Today, activity grid, weight, Agent, nutrition, and
weekly review are the frozen anchors; Task 3 must consume rather than rename
them.

**Behavior:** Add semantics-preserving stable keys where absent; drive the real
`PostureApp` through the required checkpointed journey; use normal ApiClient and
secure token storage; call control endpoints only for reset/checkpoint/fault;
assert visible fail-closed states and no pre-confirmation activation.

**Forbidden:** `FakeDioAdapter`, `apiClientProvider.override*`, direct DB/domain
calls, fixture payloads that imitate production API responses, live AI/photo,
health/safety logic, product copy changes beyond exact approved testability text,
commit/push/merge/rebase, or files outside the allowlist.

**OpenCode verification:**

```powershell
Set-Location app
flutter analyze
flutter test <exact targeted files from prompt>
flutter test
```

The handoff must report base/head, status, exact files, diff stat, commands with
exit codes/counts, generated files, assumptions, and residual risks. Codex then
reviews the real diff, runs focused/full Flutter verification, and executes the
real Android test before accepting an exact SHA.

## Gate 4: Integrated Personal-Development Acceptance

### Task 4: Android replay, visual/privacy cold review, docs, and closure

**Writer:** Codex only.

**Behavior:** Integrate reviewed Task 3, repair any cross-layer findings, run the
real HTTP backend and Android emulator journeys, capture and visually inspect
synthetic screenshots, verify offline/unavailable and safe retry, audit logs and
artifacts for sensitive payloads, prove full reset, finish local run/limitations/
public-release-gate docs, and produce the exit audit.

**Final commands include:**

```powershell
python scripts/phase8.py verify --surface all
python scripts/verify.py full
Set-Location app
flutter analyze
flutter test
flutter test integration_test/phase8_core_journey_test.dart -d emulator-5554 `
  --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1 `
  --dart-define=DEV_ADMIN_PHONE=<synthetic> `
  --dart-define=DEV_ADMIN_PASSWORD=<synthetic>
```

A separate Android unavailable run uses an unreachable emulator host port and
must show unavailable/retry with no false active state. Final acceptance also
requires strict GitHub Fast/Flutter/Full/Phase8 jobs on the same exact SHA,
PostgreSQL zero skips, no unresolved P0/P1/P2, clean worktree, and an exit report
that distinguishes local, Android, and GitHub evidence.

## Rollback

- Test-only harness/CLI/driver files can be removed without production schema or
  runtime changes.
- CI changes are additive and can be reverted independently if runner capacity
  is insufficient; local Android remains mandatory and the gap must be reported.
- Account-purge hardening must be transactionally compatible with existing
  schema. Reverting it is not permitted if that would restore a known incomplete
  deletion claim; fix forward or explicitly rename/narrow the contract.
- Migration downgrade, real-environment deletion, deployment, merge, and public
  release are outside this plan and require separate authorization.
