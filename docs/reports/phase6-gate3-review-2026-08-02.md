# Phase 6 Gate 3 Independent Review

> Review completed 2026-08-02 against Gate 2 closure
> `e9dc4d2a5b06deb83aa774326507afa34a277891` on
> `codex/phase6-implementation`. This report covers Tasks 4-5.

## Decision

**PASS.** Open P0/P1/P2 findings: zero. Gate 3 accepts
`93e78a63f9a10138ca7eba0eb157751342df02a8`, containing Task 4 commit
`b96c51ee82d96446157e2e3c1ed7f09bd127f86f` and Task 5 commit `93e78a6`.
Task 6 may begin from the subsequent metadata closure commit.

## Findings Closed

### P1

None.

### P2

1. The first Flutter operation state reused one generation for concurrent
   writes. Every draft, confirmation, preview, replacement, load, deletion,
   auth, and profile boundary now advances or invalidates the generation so a
   late response cannot repopulate current state.
2. A stale-context or newly blocked response could leave an old draft/active
   recommendation visible. Runtime-disabled, red-flag, restricted, limited,
   clarification-required, stale-context, and invalid-state errors now clear
   all usable nutrition state; ordinary offline errors preserve read-only
   content and remain retryable.
3. Health-profile changes invalidated nutrition state, but successful current
   check-ins and training-plan confirmation initially did not. Both safety
   source writes now invalidate the dependent nutrition provider, with focused
   callback tests.
4. The initial strict parser rejected unknown object fields and top-level
   enums but did not validate every nested catalog safety code. Food,
   recommendation, alternative, and exclusion code sets now reject unknown or
   duplicate values; catalog/gate version mismatches also fail closed.
5. A broad formatter invocation created unrelated Flutter churn. The affected
   files and generated desktop registrants were restored, and only Task 5
   semantic files were staged and committed.

## Accepted Behavior

- Five nutrition Agent Tools use bounded deterministic projections. Proposal
  arguments cannot inject identity, body data, risk, targets, fingerprints, or
  validation state; writes remain zero until explicit confirmation.
- Unsupported therapeutic, disease-specific, elimination, keto, and special
  diet requests route to fixed fail-closed responses before any provider call.
- Flutter parses API results strictly, separates draft/active/replacement
  preview states, discards late responses, and resets on auth, profile, safety
  check-in, plan, deletion, stale-context, and runtime-disable boundaries.
- Health profile input distinguishes unanswered (`null`) from explicitly none
  (`[]`) for the complete structured allergen vocabulary and catalog-supported
  exclusions.
- The Plan tab exposes a nutrition route with eligibility, limited/missing,
  rounded target/source/uncertainty, training/rest template, draft review,
  activation, replacement diff, retry, and deletion states. There is no meal
  intake or completion surface.
- Only reviewed local images are rendered. Unknown/missing assets use a
  semantic fallback; approved images expose author, license, and source-page
  attribution from the reviewed media manifest.

## Privacy And Parity Audit

- Provider context includes structured gate/reason/missing codes, versions,
  rounded deterministic targets, selected food IDs, and owned recommendation
  references only. It excludes raw age, height, weight, allergy text, risk
  answers, check-in body, prompt text, and full recommendation payloads.
- The button and Agent paths reuse the same nutrition service preparation,
  validation, persistence, freshness, ownership, transaction lock, and
  idempotency cores. Focused Agent/nutrition tests passed as part of Fast and
  Full; no live provider or real health data was used.

## Verification

- Flutter focused after final fixes: `35 passed`; analyze clean.
- Flutter full on accepted SHA: `384 passed`; analyze clean.
- Local Fast on the Task 4-5 candidate: `898 passed / 0 failed / 10 expected
  PostgreSQL skips`; ruff and candidate diff passed.
- Local strict Full on accepted SHA: `1564 passed / 0 failed / 0 skipped`;
  PostgreSQL expected `23`, actual `23`; ruff and candidate diff passed.
- Exact-SHA GitHub Actions run `30712669331` on `93e78a6`: Fast `898 passed`,
  Flutter analyze/test success, Full `1564 passed / 0 failed / 0 skipped` with
  PostgreSQL `23/23`; all three jobs passed.
- `git diff --check` and staged sensitive-value scan passed. Flutter-generated
  desktop registrants were restored and are not part of the accepted diff.

## Residual P3 Risks

1. Version 1 supports only two catalog-level exclusions and the eight reviewed
   allergen groups. Unknown or free-text cases deliberately require
   clarification instead of approximate matching.
2. Local food images and attribution metadata are duplicated into the Flutter
   package. Task 6 must re-audit every asset hash and metadata field against the
   canonical backend manifest before phase exit.
3. The runtime remains default-off and is not approved for production health
   data. Android enabled/disabled synthetic smoke and the final deletion/source
   audit remain Gate 4 requirements.

## Gate Condition

Satisfied. Gate 3 accepts `93e78a63f9a10138ca7eba0eb157751342df02a8`
with exact-SHA CI run `30712669331`. Task 6 may begin after this report and the
task ledger are committed.
