# Phase 6 Gate 1 Independent Review

> Review completed 2026-08-01 against Gate 0 closure
> `8ef22b4a9a1056ce94570b0c95483a124574243c` on
> `codex/phase6-implementation`. This report covers Tasks 1-2 only. The
> candidate remains at `review` until exact-SHA Fast/Flutter/Full CI passes.

## Decision

**PASS.** Open P0/P1/P2 findings: zero. The
candidate contains the curated catalog and media, structured profile migration,
current owned nutrition context, deterministic scope/calculation engines, and
independent validators. It contains no recommendation persistence, API, Agent
write tools, or Flutter nutrition workflow from later tasks.

## Findings Closed

### P1

1. The first context adapter trusted the check-in's stored write-time risk.
   It now reclassifies the structured check-in against the current profile via
   the existing deterministic health/training functions and uses their
   privacy-safe freshness token.
2. A proposed `lacto_vegetarian` exclusion contradicted the frozen special-diet
   non-goal. It was removed; version 1 supports only explicit reviewed
   `avoid_pork` and `avoid_beef` food-ID sets.
3. Extreme but source-valid account measurements could raise during formula
   evaluation. Safety classification now skips unnecessary calculations after
   higher gates and converts invalid formula inputs to bounded clarification or
   limited-education states instead of a server exception.

### P2

1. All 24 Chinese food names had been silently encoded as question marks. The
   catalog now contains reviewed Chinese labels, including the unambiguous
   `巴旦木（扁桃仁）`, and schema validation requires a CJK character.
2. The catalog initially trusted only source-file checksums. Release audit now
   normalizes each pinned raw FDC record and compares its ID, data type,
   description, publication date, and nutrients with the released projection.
3. Exclusion metadata could drift between policy and food rows. The release
   audit now checks the mapping in both directions and rejects duplicates.
4. The original milk image included doughnuts and was misleading for an
   ingredient/allergen surface. It was replaced by a milk-only CC0 image from
   Wikimedia Commons; the local derivative, source page, author, and checksum
   were independently updated and inspected.
5. Importers accepted empty source descriptions/publication dates and duplicate
   FDC IDs. These inputs now fail closed with regression tests.
6. Two historical E2E tests still pinned Alembic head `0008`. Their current-head
   assertions now track migration `0009_nutrition_profile_codes`.
7. Structured profile safety lists accepted duplicates, creating multiple
   representations of the same state. API and catalog schemas now reject them.
8. The first CI candidate exposed an undeclared local Pillow dependency in the
   media test and PR checkout reported the synthetic merge SHA. The test now
   parses JPEG dimensions with the standard library; every checkout explicitly
   selects the PR head (with push fallback), and summaries record both event and
   checked-out SHAs.
9. The second CI candidate exposed platform-dependent CRLF conversion in the
   checksum-pinned FDC subsets. Both files now have explicit `text eol=lf`
   attributes, LF byte checksums, and a regression test that rejects CRLF bytes.

## Data And License Evidence

- Catalog: 24 generic foods, eight exchange groups with three reviewed
  generation-eligible candidates before exclusions, and reviewed dark
  vegetables.
- USDA FDC Foundation 04/2026 archive SHA-256:
  `186e988ec542e913f51ef62b86a47758e8cdd0d1dc3889e7b055581f3c09c77a`.
- USDA FDC SR Legacy 04/2018 archive SHA-256:
  `0fe8ae486a2c8eb42cb96413f058deb51863a46c8fb8ee8b4b1fb45006dd338ef`.
- Committed raw subsets are exact reviewed slices and are checksum-pinned in
  `source_manifest.v1.json`. No branded, Open Food Facts, ODbL, or GPL-derived
  data/code is present.
- Media: 12 reviewed ingredient images and three prepared-meal examples, all
  local 800x600 JPEG derivatives with exact file page, author, CC0/public-domain
  status, transformation, and checksum. No unrelated image fallback is used.

## Verification

- Focused Gate 1 suites after review fixes: 180 passed, then targeted safety and
  context reruns passed after each material change.
- `python scripts/verify.py fast`: PASS; ruff clean; backend `831 passed / 0
  failed / 7 expected Fast-only skips`; candidate diff clean.
- `flutter analyze`: no issues.
- `flutter test`: `361 passed`.
- `GH_TOKEN=(gh auth token) VERIFY_REQUIRE_PG=1 python scripts/verify.py full`:
  PASS; `1494 passed / 0 failed / 0 skipped`; PostgreSQL expected `20`, actual
  `20`, version evidence present.
- Migration SQL checks prove `0009` adds only two nullable JSONB columns, does
  no backfill, and downgrade drops only those columns.
- `git diff --check`: exit 0; Windows LF/CRLF notices only.
- Exact-SHA GitHub Actions run `30702540222` on accepted implementation SHA
  `b3c1bfa8ed2f1519d11790a658fdd2ea07dc2019`: Fast, Flutter, and Full
  PostgreSQL jobs all passed.

## Residual P3 Risks

1. FDC nutrient values describe reviewed generic records and may not match a
   specific product or preparation. The UI must continue to present ranges and
   source limitations rather than exact intake claims.
2. Commons files provide no warranty. License/source pages must be rechecked
   before public distribution or a media release.
3. The context fingerprint intentionally excludes raw body values and relies on
   owned source IDs, versions, and timestamps for freshness. Later persistence
   and API tasks must preserve those invariants transactionally.
4. This remains a private wellness MVP without dietitian sign-off and is not
   approved for production health-data use.

## Gate Condition

Satisfied. Gate 1 accepts implementation SHA `b3c1bfa8ed2f1519d11790a658fdd2ea07dc2019`
with exact-SHA CI run `30702540222`; Task 3 may start from the subsequent
metadata closure commit.
