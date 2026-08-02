# Phase 7 Gate 1 Codex Review

## Decision

**PASS.** Gate 1 accepts implementation SHA
`a27dddc944973d25e1c974f709068c67ae6f2d00` on
`codex/phase7-implementation`. Open P0/P1/P2 findings: zero. The accepted scope
is the high-risk backend foundation only; Flutter, Agent adjustment authority,
weekly-review behavior, cross-domain drafts, and final E2E remain later Gates.

## Findings First

### P1 Closed

1. A stale overlay could permanently block Today when a fresh check-in no longer
   required an adjustment. The append-only state machine now records an explicit
   no-item `unchanged` version, returns to the immutable source session, and
   reruns current safety and full-plan validation.
2. Substitution and adjustment were not safe in both creation orders: a later
   substitution could be recorded without appearing in a shortened snapshot,
   while recovery/deferral/active-rest collisions could be admitted. The
   resolver now composes only a retained substitution with shortened/unchanged,
   independently validates the effective plan, and fails closed for all other
   collisions.
3. Account deletion's preflight recognized adjustment rows but not independently
   existing weekly-review or posture-dismissal rows. All three owner-scoped root
   types now make the purge non-empty, and the same transaction deletes child
   items, roots, and adjustment idempotency records without touching another
   owner.

### P2 Closed

1. Adjustment mutation responses hard-coded `safety_status=eligible`, which was
   false for conservative eligibility and misleading on replay. Mutation no
   longer claims a live safety result; every effective Today branch carries the
   freshly recomputed status.
2. Historical `unchanged` versions initially fell through the item-snapshot
   loader and were rejected as invalid. History composition now preserves the
   original session and applies only a valid owned substitution.
3. SQLite timestamp precision made newest append-only versions ambiguous.
   Application writes now use timezone-aware microsecond timestamps with UUID
   tie-breaking, and readers collapse to the newest version per source/date.
4. Initial model metadata omitted migration CHECK parity, and legacy migration
   tests pinned the old head/table set. ORM and Alembic constraints now match;
   current-head, downgrade isolation, SQLite, and disposable PostgreSQL tests
   cover migration `0011_adaptive_reviews`.
5. The first shortening path treated a lower time bucket as unchanged when the
   exercise count was already under the cap. Policy selection is based on the
   requested duration change; the overlay preserves a reviewed warm-up and a
   priority item and still passes the complete validator.
6. Existing effective overlays were not initially composed into later
   validation. The resolver now rebuilds only the latest version per source,
   excludes the source being superseded, rejects invalid history, and prevents
   deferred chains, collisions, and stacking.

## Accepted Behavior

- Versioned strict policy consumes only existing closed check-in categories.
  Red flag, restricted, missing/stale context, and pain remain higher-priority
  deterministic blocks; AI is not a safety or adjustment authority.
- Plans, sessions, and prescriptions remain immutable. Shortened, recovery,
  deferred, active-rest, and unchanged decisions are append-only owned versions
  with policy/catalog/source pins and typed item snapshots.
- Deferral selects the earliest legal unoccupied date inside the four-week plan,
  runs the complete validator, and falls back to bounded active rest without
  chain-deferral or accumulated work.
- `GET /api/v1/training/today` reruns current safety and renders only a valid
  effective state. `POST /api/v1/training/today/adjustments` is strict,
  JWT-owned, foreground-only, idempotent, and button-scoped in Gate 1.
- Migration `0011` creates adjustment/item, weekly-review foundation, and
  posture-dismissal tables. No scheduler, notification, Agent permission,
  Flutter behavior, long-term activation, real data, photo, or provider access
  is included.

## Verification

Local repository root, exact SHA
`a27dddc944973d25e1c974f709068c67ae6f2d00`:

```text
GITHUB_TOKEN=(gh auth token) VERIFY_REQUIRE_PG=1 python scripts/verify.py full
PASS: ruff clean
PASS: 1615 passed / 0 failed / 0 skipped
PASS: PostgreSQL expected=25 / actual=25 / version evidence present
PASS: working, staged, and candidate diff clean
OVERALL: PASS
```

Focused post-review suite: `65 passed / 0 skipped`, including PostgreSQL
`0011` downgrade/upgrade and concurrent same-key exactly-once persistence.

GitHub Actions workflow-dispatch run `30744694166`, exact event and checked-out
SHA `a27dddc944973d25e1c974f709068c67ae6f2d00`:

```text
Fast: success; 915 passed / 0 failed / 10 expected PostgreSQL-only skips
Flutter: success; analyze clean / 384 tests passed
Full: success; 1615 passed / 0 failed / 0 skipped; PostgreSQL 25/25
```

## Rollback And Audit

- Alembic downgrade from `0011_adaptive_reviews` to
  `0010_nutrition_recommendations` drops only the four Phase 7 tables in
  dependency order; upgrade/downgrade was exercised on SQLite and disposable
  PostgreSQL.
- Owner-scoped adaptive deletion is transaction-neutral when called by central
  account purge and child-first. Fault injection proves adjustment, item, and
  idempotency writes roll back atomically.
- Staged diff and private-key/token pattern scans passed. Tests use synthetic
  UUIDs and structured fixtures only. No real health data, photo, credential,
  log, database, runtime artifact, deployment, merge, or `main` write exists.

## Residual Risk And Next Gate

No P0/P1/P2 remains. Gate 1 intentionally does not provide Flutter UI, Agent
proposal/confirmation, weekly-review generation, cross-domain draft origins, or
final Android/E2E acceptance. Task 2 may start only from the subsequent
docs-only Gate 1 closure SHA, in one OpenCode + Claude worktree with the plan's
Flutter allowlist and no backend writes.
