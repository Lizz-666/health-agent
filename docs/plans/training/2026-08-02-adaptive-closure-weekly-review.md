# Phase 7 Adaptive Closure And Weekly Review Implementation Plan

**Goal:** Deliver conservative same-day execution overlays and an explainable
weekly cross-domain review without weakening existing safety or activation
boundaries.

**Spec:** `docs/specs/training/2026-08-02-adaptive-closure-weekly-review.md`

**Architecture:** Keep confirmed training/nutrition versions immutable. Add
append-only same-day adjustment versions, weekly review snapshots, and ordinary
posture-recheck dismissal events. Domain services remain deterministic; Flutter
and Agent call narrow application contracts.

**Safety:** Every execution/draft command rebuilds owned current context and
reruns existing safety/validation. Weight is excluded from training decisions.
Agent writes require persisted proposal plus explicit confirmation.

**Verification:** Focused pytest/widget tests at each task; strict PostgreSQL Full
for backend/migration Gates; `flutter analyze` and Flutter tests for UI Gates;
final Android synthetic smoke and exact-SHA GitHub Fast/Flutter/Full.

## Baseline And Working Rules

- Gate 0 starts from exact Phase 6 closure
  `8eeb28a3a4156eaac5763260129fdde6fedee835`, never `main` or an older PR.
- `codex/phase7-spec-plan` is the Gate 0 documentation branch.
- After Gate 0 closure, Codex creates `codex/phase7-implementation` from the
  exact accepted Gate 0 SHA. No business implementation starts earlier.
- One Task has one writer. OpenCode receives only the Flutter batch after Gate 1
  backend contracts are accepted. Codex does not edit that batch while its
  implementation session is active.
- OpenCode may not merge, rebase, push, change CI/settings/secrets, use live AI,
  real health data/photos, or modify files outside its allowlist.
- Every handoff is evidence only. Codex reviews the real diff, reruns verification,
  fixes or rejects findings, and binds acceptance to a new exact SHA.

## File And Ownership Map

| Area | Owner | Likely files |
| --- | --- | --- |
| Gate 0 contracts | Codex | this spec/plan, ADR-0007, `docs/agent/ACTIVE_TASKS.md` |
| Adjustment policy/state/migration/API | Codex | `backend/app/training/{state,models,schemas_api,service,router,adaptive_policy}.py`, `backend/app/training/data/training_adaptive_policy.v1.json`, `backend/alembic/versions/0011_adaptive_reviews.py`, training/migration tests |
| Review aggregation/origin pins | Codex | training service/schema/model files, `backend/app/health/{service,trends}.py` read-only adapters as needed, nutrition models/service/schema for origin pins, focused tests |
| Flutter Today/Plan/review surfaces | OpenCode, one session | exact allowlist in Task 2 only |
| Posture comparison and Agent permissions | Codex | posture read adapter/service/schema as needed, agent registry/schemas/action tools/context/orchestrator tests, final Flutter integration edits if needed |
| Final E2E/audit | Codex | integration tests, device harness, reports, task ledger |

## Gate 0: Contract Closure

### Task 0: Specification, ADR, plan, and task ledger

**Writer:** Codex only.

**Allowed files:**

- `docs/specs/training/2026-08-02-adaptive-closure-weekly-review.md`
- `docs/plans/training/2026-08-02-adaptive-closure-weekly-review.md`
- `docs/adr/0007-execution-overlays-and-review-drafts.md`
- `docs/agent/ACTIVE_TASKS.md`
- Gate 0 review report under `docs/reports/` after candidate review

**Behavior:** Close product ambiguities, state/data ownership, APIs, migration
and rollback, Agent permissions, Flutter boundary, delegation contract, Gates,
and exact verification. No business code.

**Acceptance:** Findings-first cold review has no unresolved P0/P1/P2; docs agree
on foreground direct adjustment, Agent confirmation, draft-only long-term
changes, weight isolation, in-app reminder scope, branch/base, and ownership.

**Verification:**

```powershell
python scripts/verify.py fast
Set-Location app
flutter analyze
flutter test
```

Then push the named branch and require exact-SHA GitHub `Fast`, `Flutter`, and
`Full`. Record run IDs and counts in the Gate 0 report/ledger before closure.

## Gate 1: High-Risk Backend Foundation

### Task 1: Adjustment state, policy, migration, resolver, and API

**Writer:** Codex only.

**Allowed modules:** `backend/app/training/**`,
`backend/alembic/versions/0011_adaptive_reviews.py`, training and migration test
files, plus minimal database/app registration files proven necessary by diff.
No Flutter, Agent, posture write, or nutrition behavior in this task.

**Behavior:** Add versioned adaptive policy, append-only adjustment/item and
review/dismissal persistence foundations, current-context resolver, deterministic
shorten/recovery/defer/active-rest engine, Today composition, strict API,
idempotency, ownership, deletion integration, and migration parity.

**Required tests:**

- policy mappings for every existing structured input enum;
- red-flag/restricted/pain/missing/stale precedence and no bypass;
- shortened required-role/load/recovery invariants;
- recovery catalog eligibility and independent validation;
- deferral earliest-slot, plan-end, collision, recovery, no-chain, no-stack;
- edited check-in invalidates old overlay;
- authorization, strict schema, timezone, idempotency, concurrent duplicate,
  transaction fault injection, account deletion;
- migration upgrade/downgrade/constraints on SQLite and disposable PostgreSQL.

**Acceptance commands:**

```powershell
python -m pytest backend/tests/test_training_adaptive_policy.py backend/tests/test_training_adjustments.py backend/tests/test_training_api.py backend/tests/test_training_plan_migrations.py backend/tests/test_migrations.py -q
$env:VERIFY_REQUIRE_PG='1'
python scripts/verify.py full
```

Codex performs a cold specification and engineering/safety review, commits the
accepted SHA, pushes, and requires exact-SHA GitHub Fast/Flutter/Full.

## Gate 2: Delegated Flutter Vertical Slice

### Task 2: Today adjustment and weekly review UI

**Writer:** One OpenCode + Claude session. Codex is read-only during the session
and becomes writer only after handoff if review fixes are required.

**Base:** Exact Gate 1 accepted SHA on a dedicated
`codex/phase7-flutter` branch/worktree.

**Only allowed implementation files:**

- `app/lib/app.dart`
- `app/lib/models/plan.dart`
- `app/lib/models/adaptive_review.dart` (new)
- `app/lib/providers/plan_provider.dart`
- `app/lib/providers/adaptive_review_provider.dart` (new)
- `app/lib/screens/today/today_screen.dart`
- `app/lib/screens/plan/plan_screen.dart`
- `app/lib/screens/plan/weekly_review_screen.dart` (new)
- `app/test/models/plan_test.dart`
- `app/test/models/adaptive_review_test.dart` (new)
- `app/test/providers/plan_provider_test.dart`
- `app/test/providers/adaptive_review_provider_test.dart` (new)
- `app/test/screens/plan_screen_test.dart`
- `app/test/screens/today_checkin_test.dart`
- `app/test/screens/weekly_review_screen_test.dart` (new)

No backend, Agent screen/provider/model, nutrition screen/provider/model, health
profile, generated platform file, dependency, asset, or documentation edit.

**Behavior:** Parse strict Gate 1 contracts; expose a foreground adjustment
button with loading/replay/stale/safety/unavailable states; render original vs
effective session, reason codes, deferral date, and history; render weekly facts,
trend availability, training/nutrition draft boundaries, and posture due state.
Never trigger on screen load or check-in save. Never label active rest as failure
or a draft as active.

**Acceptance commands:**

```powershell
Set-Location app
flutter analyze
flutter test test/models/plan_test.dart test/models/adaptive_review_test.dart test/providers/plan_provider_test.dart test/providers/adaptive_review_provider_test.dart test/screens/plan_screen_test.dart test/screens/today_checkin_test.dart test/screens/weekly_review_screen_test.dart
flutter test
```

After handoff, Codex checks `Gate1..HEAD`, scope, generated files, API parsing,
phone overflow, lifecycle/concurrency behavior, and tests. Accepted UI commit is
cherry-picked onto the implementation branch, reverified, pushed, and bound to
exact-SHA GitHub Fast/Flutter/Full.

### OpenCode prompt

```text
Implement Phase 7 Task 2 only. Start from the exact Gate 1 SHA supplied by
Codex in the dedicated codex/phase7-flutter worktree. Read root AGENTS.md, the
Task 2 section of docs/plans/training/2026-08-02-adaptive-closure-weekly-review.md,
the matching spec UI/API sections, and only affected Flutter files/tests.

You are the sole writer for this Task. Modify only the explicit Task 2 allowlist.
Do not edit backend, docs, Agent/nutrition/health files, dependencies, generated
platform files, assets, CI, or another worktree. Do not commit, push, merge,
rebase, use real health data/photos/credentials, or call live AI.

Implement strict typed parsing and the Today/Plan/weekly-review flow against the
accepted backend contract. Adjustment is performed only after an explicit
foreground button press; never on load or check-in save. Render stale, safety,
missing, unavailable and replay states; distinguish original/effective sessions,
active rest, draft, and active versions. Add behavior tests and run the exact
Task 2 commands.

Stop and report if backend contract changes or an out-of-allowlist file is
required. Handoff must include base/head SHA, changed files, behavior, commands
and exact results, remaining risks, git diff --stat, git status, and unexpected
generated files. Your report is not acceptance.
```

## Gate 3: Cross-Domain Review And Agent Contracts

### Task 3: Weekly review, draft origins, posture recheck, and Agent tools

**Writer:** Codex only, after Gate 2 is integrated and reverified.

**Allowed modules:** focused files under `backend/app/training`, read-only health
trend adapter, nullable review-origin additions in nutrition persistence/API,
minimal posture structured-summary comparison, reviewed Agent registry/schema/
adapter/orchestration/prompts, matching backend/Flutter tests, and additive
migration `0012_review_draft_origins.py`. Accepted migration `0011` is immutable;
any safety-policy or schema expansion triggers a fresh Gate 3 review.

**Behavior:** Complete immutable weekly snapshot aggregation, explicit no-data,
training/nutrition draft materialization with stale checks and no activation,
per-cycle posture due/dismiss/structured comparison, deletion, and narrow Agent
read/action tools using existing proposal-confirmation machinery.

**Required tests:**

- weekly boundary/timezone/replay/new-version behavior;
- activity-state semantics and no missing-as-zero;
- weight direction cannot alter any training proposal under mutation/property
  tests; nutrition refresh uses only Phase 6 domain service;
- training/nutrition draft origin and no activation under success/failure/race;
- posture ownership, cycle due/dismissal, safety-reminder isolation, structured
  comparison, no raw photo/prose persistence;
- Agent allowlist, minimal context, consent/privacy, proposal expiry/stale,
  confirmation revalidation, prompt injection, provider disabled/failure;
- account/domain deletion and audit privacy.

**Acceptance commands:** focused affected pytest, Agent adversarial/eval suites,
Flutter analyze/tests, then strict PostgreSQL Full. Exact-SHA GitHub
Fast/Flutter/Full must pass after cold review and commit.

## Gate 4: Integrated Acceptance

### Task 4: E2E, Android smoke, cold audit, and closure

**Writer:** Codex only.

**Behavior:** Exercise the complete enabled/disabled synthetic flows for busy,
fatigue, no-time/missed, intentional rest, pain, restricted/red-flag, stale
overlay, weekly review, training draft, nutrition draft, and posture recheck.
Audit privacy, source/policy versions, migration recovery, feature exclusions,
and documentation against actual code.

**Acceptance commands:**

```powershell
$env:VERIFY_REQUIRE_PG='1'
python scripts/verify.py full
Set-Location app
flutter analyze
flutter test
flutter test integration_test/phase7_adaptive_review_smoke_test.dart
```

Run Android synthetic enabled/disabled smoke through the existing guarded device
harness. Push only the reviewed named branch, keep the PR draft/unmerged, and
require exact-SHA GitHub Fast/Flutter/Full. Publish a findings-first exit audit
with counts, run IDs, rollback limits, exclusions, and residual risks.

## Migration And Compatibility

- Migration `0011` is additive and owns adjustment/item/review/dismissal tables.
- Migration `0012` is additive and owns nullable review-origin foreign keys on
  training/nutrition versions. Gate 3 does not rewrite accepted `0011`.
- Existing plans, feedback, substitutions, nutrition versions, and clients stay
  readable. Missing Phase 7 fields parse as explicit absent/unavailable states
  during the controlled transition; server responses become strict after Gate 2.
- Resolver reads only the newest overlay matching current fingerprints. Historical
  rows never authorize execution.
- Application rollback leaves additive tables/columns unused. Downgrade drops
  Phase 7 data and is authorized only on disposable synthetic databases.

## Gate Evidence Template

For every Gate record: base SHA, candidate/accepted SHA, writer, changed files,
two-pass findings, local commands with exit code/counts/skips, PostgreSQL result
when applicable, CI run IDs/job conclusions for exact SHA, scope audit, sensitive
data/generated-file audit, rollback note, and unresolved P0-P3. P0/P1/P2 must be
zero before automatic commit/integration.
