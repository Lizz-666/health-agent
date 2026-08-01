# Phase 6 Gate 0 Independent Review

> Review completed 2026-08-01 against base
> `5b268445faab0578ace23b9ecd9757449155a44f` in
> `codex/phase6-spec-plan`. This is a findings-first review of specification,
> source, license, persistence, safety, Agent, UI, and execution contracts. No
> Phase 6 runtime code was present or authorized.

## Decision

**PASS.** Open P0/P1/P2 findings: zero. Contract candidate
`0109f96e51ae600365d0de0cdba9b12292d22ae8` passed local Fast and exact-SHA
GitHub Fast/Flutter/Full CI run `30696443907`. Runtime implementation must start
from the subsequent metadata closure SHA only after that SHA's own CI is green.

## Findings Closed

### P1

1. **Incorrect physical-activity factor.** The draft used PAL `1.5`, while all
   six reviewed Chinese DRIs 2023 adult tables define low intensity as `1.40`.
   The spec, plan, and ADR now use `1.40` and pin Tables 9-14.
2. **Underage tier downgrade.** Treating every age outside 19-64 as limited
   education would have classified a user under 18 below the required
   restricted tier. Age `<18` is now deterministically restricted; age `18` is
   limited because it is outside the Mifflin derivation scope used by this MVP.
3. **Incomplete nutrition-data deletion.** The first contract deleted only
   recommendations/idempotency state. It now also clears the two
   nutrition-specific profile fields and removes explicit nutrition Tool
   proposal/audit references while documenting the separate Agent-history
   deletion control.

### P2

1. The energy range originally applied uncertainty to the mean of the equation
   branches. It now applies the lower allowance to the lower branch and the
   upper allowance to the upper branch; the mean is used only for scope gating.
2. The nutrition validation Tool was named `validate_meal_plan`, conflicting
   with the roadmap. It is now `validate_nutrition_plan` everywhere.
3. Structured nutrition profile fields were scheduled before their migration.
   Task 2 now owns migration `0009`; recommendation persistence uses `0010`, and
   Gate 1 requires PostgreSQL Full verification.
4. Weight had two possible current sources with no precedence. The newest owned
   non-future manual record now wins, with explicit account weight as the only
   fallback; source identity/timestamp are pinned.
5. The draft claimed a nearest training meal although Phase 4 stores no
   time-of-day. It now emits only a bounded choose-nearest-meal guidance code.
6. The media minimum contradicted a required image on every food. Images are now
   optional and never misleadingly reused; at least 12 food records and three
   meal examples still require reviewed real imagery.
7. Singular draft retrieval had no one-current-draft invariant. Regeneration
   now supersedes the prior draft and inserts a new immutable-payload version;
   PostgreSQL and SQLite invariants cover both draft and active status.
8. Chinese Dietary Guidelines food-group quantities were referenced but not
   executable. The spec now pins daily group ranges, dark-vegetable coverage,
   meal-share checks, and explicit oil/salt limitations.
9. Exclusion codes could have implied arbitrary tag/substring matching. They are
   now allowlisted policy keys that expand to reviewed explicit food-ID sets.
10. The idempotency contract introduced a header unlike existing services and
    conflicted with bodyless deletion. State-changing POSTs now use the existing
    strict body field; preview reads do not, and deletion is state-idempotent.
11. Active-plan and goal semantics were ambiguous. Personalized nutrition now
    requires an effective `session`/`rest_day` plan state and uses only the
    confirmed Phase 4 goal set; completed, blocked, missing, or unsupported
    plans fail closed.
12. Records with missing core nutrient fields could have entered generation.
    Such rows remain source-traceable but are not generation eligible, and no
    fibre-adequacy claim is made.

## Source And License Review

- Chinese DRIs official Tables 9-14 were downloaded from the six exact CNS URLs
  recorded in the spec and visually inspected. All returned HTTP 200 on
  2026-08-01. Adult protein RNI, macro AMDR, fibre, water, and PAL values match
  the frozen contract.
- The Mifflin source was checked against DOI `10.1093/ajcn/51.2.241` and PMID
  `2305711`: 498 healthy subjects, age 19-78, with the two published branches.
  The Phase 6 combined range is explicitly product policy, not a validated
  confidence interval or measured expenditure.
- Chinese Dietary Guidelines 2022 official pages were checked for the
  `1600-2400 kcal` food-group envelope, three-meal structure, food quantities,
  meal shares, oil, and salt. Official graphics are excluded because the site
  limits their reuse.
- WS/T 428-2013 and the 2024 NHC weight-management guidance corroborate the BMI
  cut points. A 2025 public-consultation draft modification was found, but no
  issued replacement was located as of the review date; public release must
  recheck current status.
- GB 7718-2025 is published but does not become effective until 2027-03-16. Its
  eight allergen categories are used only as a fail-closed vocabulary, not as a
  legal-labeling or cross-contact guarantee.
- USDA FoodData Central official documentation confirms CC0/public-domain data
  and requested citation. The implementation must pin the 04/2026 source
  release and may not use a runtime API.
- Open Food Facts remains excluded because ODbL/DbCL, CC BY-SA image, and
  packaging/trademark obligations are out of scope. OpenNutriTracker GPL-3.0
  code, UI, schema, and pipeline remain excluded.
- Wikimedia Commons is only an index. Every accepted image still needs a
  per-file CC0/public-domain decision, revision URL, author, checksum,
  transformation, and removal procedure during Task 1.

## Residual P3 Risks

1. Mifflin was not derived specifically for the current user or exclusively for
   a Chinese population. The broad branch/uncertainty range and strict scope
   gate reduce false precision but do not eliminate estimation error.
2. FDC represents the US food supply and analytical records. China-common names,
   portions, and group mappings require manual review and remain approximate.
3. Commons provides no warranty. Every file license and source revision must be
   rechecked before public distribution or a media release.
4. Phase 6 is a personal-development wellness MVP without qualified dietitian
   sign-off. It is not approved for public deployment or real-health-data
   development workflows.

## Verification

- `git status --short --branch`: only the five allowed Gate 0 document groups
  are modified/untracked.
- `git diff --check`: exit 0; only the standard Windows LF/CRLF warning appeared.
- `python scripts/verify.py fast` on candidate `0109f96`: PASS; ruff clean,
  backend `653 passed / 0 failed / 7 skipped`, candidate diff clean.
- GitHub CI run `30696443907` on exact candidate `0109f96`: Fast, Flutter, and
  Full PostgreSQL all passed.
- Contract searches found no remaining PAL `1.5`, old Tool name, header
  idempotency contract, old migration assignment, or nearest-meal claim.
- Six exact DRI image URLs: HTTP 200.
- FDC API/data/download and Open Food Facts license pages: HTTP 200.
- AJCN/NHC/Commons/dg.cnsoc pages may return anti-bot/TLS responses to command-
  line clients; their content was independently checked through official pages,
  search indexes, direct source files, or stable identifiers.

## Gate Conditions

The contract candidate conditions are satisfied. Gate 0 closes after this
metadata-only acceptance commit passes exact-SHA CI and a final status check
shows no runtime or unrelated files. Later source, policy, migration, or
contract changes invalidate this review and require a new gate review.
