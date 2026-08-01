# Phase 6 Gate 2 Independent Review

> Review completed 2026-08-01 against Gate 1 closure
> `8fb26eba68802fc75e37d10adeca8543c2343dd9` on
> `codex/phase6-implementation`. This report covers Task 3 only.

## Decision

**PASS.** Open P0/P1/P2 findings: zero. Gate 2 accepts
`2160bdc5380db625dad33b8ae8103d17fc8a9508`, containing implementation commit
`6431ad274d92022616215a9c851433e2fc871b01` plus the CI zero-skip fix. Task 4
may start from the subsequent metadata closure commit.

## Findings Closed

### P1

1. Replacement alternatives initially proved only exchange-group and portion
   overlap. Generation and independent validation now recompute whole-day meal
   shares and food-group ranges for every exposed alternative and replacement.
2. Nutrition generation could race with account/profile/check-in/weight writes
   that did not all use the shared per-user transaction lock. Every freshness
   source write now uses the same lock before mutation; generation,
   confirmation, and replacement still rebuild the latest owned context.

### P2

1. Whole-grain membership was a hidden Python constant. It is now versioned in
   the reviewed nutrition policy and checked by release audit.
2. SQLite migration coverage originally inspected SQL only. Migrations `0009`
   and `0010` now perform real SQLite upgrade/downgrade tests, while PostgreSQL
   tests prove partial unique indexes, concurrent confirmation, and deletion of
   self-referenced recommendation chains.
3. Household portions and stable-code fields were not independently projected
   in full. The validator now compares the complete catalog projection and
   rejects rationale/source/uncertainty/validation free text.
4. Replacement preview accepted non-active rows and derived the next version
   from the active version rather than the user's maximum version. Both paths
   now fail closed or return the actual pending version.
5. Two historical E2E tests still pinned migration head `0009`; they now track
   the single `0010_nutrition_recommendations` head.
6. A pre-existing Hypothesis speed health check could fail after a Windows
   scheduler pause despite valid property inputs. Only `HealthCheck.too_slow`
   is suppressed; sample counts and all business assertions remain unchanged.
7. The first exact-SHA Full CI run executed PostgreSQL 23/23 but skipped nine
   network action-pin checks after the unauthenticated API quota was exhausted.
   Full now receives the same read-only workflow token as Fast, with a
   structural regression test; the next exact-SHA run completed with zero
   skips.

## Accepted Behavior

- Deterministic catalog-only training/rest three-meal generation with strict
  typed payloads, two-stage independent validation, allergy/exclusion hard
  filtering, and fail-closed no-safe-candidate behavior.
- Immutable draft/active/superseded versions, one-current-draft and one-active
  database invariants, transaction-locked state changes, replay/conflict
  idempotency, stale-context rejection, rollback, and ownership isolation.
- JWT-only eligibility, targets, catalog, draft, confirmation, active, preview,
  replacement, and deletion APIs. The runtime defaults off; scoped deletion
  remains available while disabled.
- Nutrition deletion removes only owned recommendations, nutrition
  idempotency, structured nutrition profile answers, and explicit nutrition
  Agent references. It preserves general Agent, posture, and training data.
- No intake/completion/diary fields, live AI, real health data, credentials, or
  client-supplied identity/risk/version/validation state were introduced.

## Verification

- Focused migration/E2E rerun after migration-head repair: `63 passed`.
- Current local Fast after the CI contract fix: `881 passed / 0 failed`; ten
  PostgreSQL-only cases skipped by the Fast contract; ruff and candidate diff
  passed.
- Local strict Full on implementation `6431ad2`: `1546 passed / 0 failed / 0
  skipped`; PostgreSQL expected `23`, actual `23`; ruff and candidate diff
  passed.
- Exact-SHA GitHub Actions run `30708939766` on accepted SHA `2160bdc`: Fast
  `881 passed`, Flutter analyze/test success, and Full `1547 passed / 0 failed /
  0 skipped`; Fast, Flutter, and Full jobs all passed.
- `git diff --check`: exit 0; Windows working-tree LF/CRLF notices only.

## Residual P3 Risks

1. Some supported allergen combinations leave fewer than the required safe
   catalog groups. Version 1 deliberately refuses generation instead of
   constructing a weak or unreviewed template.
2. Generic food and household-portion ranges are guidance, not measured intake
   or product-specific nutrition. UI wording and attribution must preserve that
   limitation.
3. Context fingerprints intentionally omit raw body values and rely on owned
   source IDs, versions, and timestamps plus the shared write lock for
   freshness. Later Agent and Flutter paths must not weaken those checks.
4. The runtime remains default-off and is not approved for production health
   data. Task 6 must complete Android synthetic E2E and the final source audit.

## Gate Condition

Satisfied. Gate 2 accepts `2160bdc5380db625dad33b8ae8103d17fc8a9508`
with exact-SHA CI run `30708939766`. Task 4 may begin after this report and the
task ledger are committed.
