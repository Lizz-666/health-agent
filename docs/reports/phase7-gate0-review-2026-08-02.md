# Phase 7 Gate 0 Codex Review

## Decision

PASS for contract SHA `dceceb7dcd7955359e91939853c5290be799c277`.
The branch is `codex/phase7-spec-plan`; the exact source baseline is Phase 6
closure `8eeb28a3a4156eaac5763260129fdde6fedee835`. Gate 0 contains documentation
and governance only. No business code, migration, health data, photo, provider
credential, deployment, merge, or `main` write was included.

The implementation branch must be created from the later metadata closure SHA
after that SHA also passes exact-SHA verification. It must not start from `main`,
the Phase 6 implementation SHA, or the contract candidate alone.

## Findings First

Final cold review findings:

- P0: 0
- P1: 0
- P2: 0
- P3: 0

Closed before the contract commit:

- P2: the first draft allowed a review `GET` to persist/replay a snapshot.
  Closed by making GET read-only and requiring an explicit idempotent POST.
- P2: the first plan allowed Gate 3 to edit migration `0011` after Gate 1
  acceptance. Closed by freezing `0011` at Gate 1 and assigning cross-domain
  draft-origin columns to additive migration `0012`.
- P2: long-term training proposal eligibility was underspecified. Closed with
  explicit version-1 product-policy mappings, pain/safety precedence, a complete-
  cycle-only progression offer, and explicit missing-data behavior.
- P3: posture comparison anchors, nutrition refresh cause, and substitution/
  overlay composition were implicit. Closed with owned timestamp anchors,
  source-pin staleness, and deterministic collision rules.

## Contract Review

The accepted contract closes the Task 0 audit findings:

- Foreground user button may directly apply one deterministic same-day overlay
  only after latest-context safety and independent validation. There is no
  background action or screen-load/check-in-save side effect.
- Agent writes remain persisted proposal plus separate explicit confirmation and
  invoke the same revalidated domain command.
- Active training and nutrition versions remain immutable. Same-day changes are
  append-only execution overlays; long-term changes are inactive drafts using
  existing activation gates.
- Red flags, restricted state, pain, missing input, stale fingerprints, unknown
  enums, collisions, and validator failures fail closed. Adjustment cannot
  acknowledge or route around a safety state.
- Weight trend is structurally absent from training-decision input and is
  explanation-only. Nutrition refresh is based on current version pins and uses
  the existing Phase 6 service.
- Posture recheck is an in-app per-cycle state with structured owned comparison;
  it adds no scheduler, notification provider, raw-photo comparison, or
  diagnostic claim.
- Migration, API, Agent permission, deletion, privacy, Flutter, Android, E2E,
  rollback, and exact-SHA Gates have named owners and verification.

No new clinical threshold or external health fact was introduced. Existing
structured categories, reviewed policy/catalog bounds, and authoritative safety
engines remain the source of health behavior. The new counts are conservative
product eligibility rules for offering an inactive draft, not clinical claims.

## Ownership And Delegation

- Codex owns Gate 0, Gate 1 backend policy/state/migration/API, Gate 3 cross-
  domain review/posture/Agent contracts, and Gate 4 E2E/final acceptance.
- One OpenCode + Claude session may own only Gate 2 Flutter files after Gate 1.
  The exact allowlist, prompt, base, stop conditions, commands, and handoff format
  are in the implementation plan.
- Same-Task concurrent writing, backend contract edits by OpenCode, and Codex
  edits during the active OpenCode write session are prohibited.

## Exact-SHA Evidence

Local, repository root, SHA
`dceceb7dcd7955359e91939853c5290be799c277`:

```text
python scripts/verify.py fast
PASS: ruff 0.15.22; backend 903 passed, 0 failed, 10 expected PostgreSQL skips

cd app
flutter analyze
PASS: no issues found

flutter test
PASS: 384 tests
```

GitHub Actions workflow dispatch run `30732748723`, exact head SHA
`dceceb7dcd7955359e91939853c5290be799c277`:

```text
Fast (lint + SQLite tests): success
Flutter (analyze + test): success
Full (complete tests + PostgreSQL 16): success
```

The 10 local Fast skips are the expected PostgreSQL-only cases; Full CI ran with
PostgreSQL 16 and succeeded. Verification produced only line-ending changes in
seven generated Flutter registrant files; Codex inspected and restored those
unstaged tool side effects. They are absent from the contract commit.

## Scope And Sensitive-Data Audit

Contract commit changed only:

- `docs/specs/training/2026-08-02-adaptive-closure-weekly-review.md`
- `docs/plans/training/2026-08-02-adaptive-closure-weekly-review.md`
- `docs/adr/0007-execution-overlays-and-review-drafts.md`
- `docs/agent/ACTIVE_TASKS.md`

Staged diff check and secret-pattern scan passed. No runtime artifact, dependency,
generated platform file, database, log, health payload, note, photo, credential,
or provider output was committed.

## Residual Risk And Gate

No P0/P1/P2/P3 remains in Gate 0. Phase 7 behavior is not implemented or claimed
as implemented. Migration feasibility, policy invariants, concurrency, deletion,
cross-domain contracts, Flutter behavior, Android E2E, and rollback remain future
Gate 1-4 acceptance work exactly as listed in the implementation plan.

Gate 0 is accepted at the contract SHA. Business implementation remains blocked
until the metadata closure commit is itself pushed and exact-SHA CI is green.
