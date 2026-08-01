# Phase 6 Nutrition Recommendation MVP Implementation Plan

> Status: proposed for Gate 0 review, 2026-07-30. Runtime implementation is not
> authorized until this plan, the specification, and ADR-0005/0006 pass a cold
> findings-first review.

**Goal:** Deliver deterministic, allergy-aware training/rest meal
recommendations for the supported healthy-adult scope without creating an
intake-tracking product.

**Spec:** `docs/specs/nutrition/2026-07-30-nutrition-recommendation-mvp.md`

**ADRs:** `docs/adr/0005-curated-nutrition-data-and-estimate-ranges.md` and
`docs/adr/0006-immutable-nutrition-recommendation-versions.md`

**Architecture:** Versioned local policy/catalog/media + pure safety/calculation/
portion/generation/validation engines + owned immutable recommendation versions
+ authenticated API + static Agent Tools + Flutter review/confirmation flow.

**Safety:** Latest structured context gates every operation. Unknown allergies,
exclusions, risk answers, formula inputs, source versions, or candidates fail
closed. No model arithmetic, invented nutrient data, disease diet, exact
deficit/surplus, meal intake state, live AI, or real health data.

## Branch And Gate Strategy

- Task 0 runs on `codex/phase6-spec-plan` from Phase 5 closure
  `5b268445faab0578ace23b9ecd9757449155a44f`.
- After Gate 0 acceptance, create one implementation branch/worktree from the
  accepted Task 0 SHA. Codex is the only writer and commits one cohesive
  milestone at each gate.
- Gate 1 accepts Tasks 1-2; Gate 2 accepts Task 3; Gate 3 accepts Tasks 4-5;
  Gate 4 accepts Task 6 and the phase exit audit.
- Each gate requires a findings-first cold review of the real base..HEAD diff,
  focused tests, Fast verification, and exact-SHA CI. Gates 2-4 also require
  PostgreSQL Full; Gates 3-4 require Flutter CI.

## Task 0: Specification, ADRs, Source Decisions, And Charters

**Files:**

- `docs/specs/nutrition/2026-07-30-nutrition-recommendation-mvp.md`
- `docs/plans/nutrition/2026-07-30-nutrition-recommendation-mvp.md`
- `docs/adr/0005-curated-nutrition-data-and-estimate-ranges.md`
- `docs/adr/0006-immutable-nutrition-recommendation-versions.md`
- `docs/agent/ACTIVE_TASKS.md`
- `docs/reports/phase6-gate0-review-2026-07-30.md`

**Work:** Freeze supported population, formula/uncertainty contract, BMI/risk
scope, DRIs/guideline ranges, allergy vocabulary, portion ranges, candidate
source/license decisions, immutable version model, API/Agent/UI contracts,
task files, gates, verification, and rollback.

**Verification:** Link/source audit, `git diff --check`, internal contract search,
and a fresh findings-first review. No runtime files.

**Done when:** P0/P1/P2 findings are zero, accepted Task 0 SHA is recorded, and
only then is the implementation worktree created.

## Task 1: Curated Food Catalog, Media, Importers, And License Validation

**Primary files:**

- `backend/app/nutrition/data/{foods.v1,nutrition_policy.v1,source_manifest.v1,media_manifest.v1}.json`
- `backend/app/nutrition/data/THIRD_PARTY_NOTICES.md`
- `backend/app/nutrition/{schemas,knowledge,importers}.py`
- `scripts/import_nutrition_data.py`
- `app/assets/images/nutrition/**`
- `app/pubspec.yaml`
- `backend/tests/test_nutrition_{knowledge,importers,licenses}.py`
- `scripts/verify.py`

**Work:**

- implement strict schemas and allowlisted versioned loaders
- fetch only pinned FDC records through an explicit offline import command;
  normalize nulls without converting missing to zero
- create at least 24 reviewed generic foods and three safe candidates per
  replacement exchange group before exclusions; include enough reviewed dark
  vegetables to enforce the daily half-of-vegetables rule
- create Chinese aliases/group mappings as project-authored fields with reviewer
  state, not as USDA claims
- acquire at least 12 ingredient and three prepared-meal CC0/public-domain real
  photos; resize/crop locally and record checksum/transformation/attribution
- reject Open Food Facts, GPL-derived files, branded records/images, unknown
  licenses, missing lineage, orphan media, and unreviewed source rows
- document manual update/removal procedure and prove no runtime network/API key

**Tests:** Strict unknown fields, duplicate IDs, invalid nutrients, NaN/infinity,
missing source/license/reviewer, disallowed data type/license, checksum mismatch,
catalog/media cross references, safe-candidate counts, allergen/exclusion tags,
and deterministic import output.

**Done when:** Focused tests and Fast CI pass; a source/media audit can trace
every committed datum and binary to its exact official/file page.

## Task 2: Nutrition Safety Context, Estimates, Portions, And Pure Validation

**Primary files:**

- `backend/app/nutrition/{context,safety,calculator,portions,validator}.py`
- `backend/app/nutrition/schemas.py`
- `backend/app/health/{models,schemas,service,router}.py`
- `backend/alembic/versions/0009_nutrition_profile_codes.py`
- focused user/health service changes required for current context versions
- `backend/tests/test_nutrition_{context,safety,calculator,portions,validator}.py`
- affected health schema/API and migration tests
- `scripts/verify.py`

**Work:**

- add explicit nullable structured `food_allergen_codes` and
  `excluded_food_codes`; preserve legacy text but treat unresolved non-empty
  text as a blocker
- assemble current owner/user/profile/check-in/posture/training/version context
  through existing services; no client-supplied risk/version/candidate data
- resolve weight from the newest non-future owned manual record, then explicit
  account weight only when no such record exists; pin the selected source
- implement pure decision precedence and recovery semantics
- implement both Mifflin branches, PAL 1.40, uncertainty band, outward rounding,
  China DRIs ranges, BMI/age/energy-envelope gates, and categorical goal logic
- implement household portion projections with explicit approximate ranges
- implement an independent structural/allergen/source/version validator
- ensure all context fingerprints contain versions/codes only, never raw allergy
  labels, notes, or body values

**Tests:** Formula golden vectors, branch ordering, rounding, no gender use,
missing/zero/out-of-range/NaN/infinity, age 17/18/19/64/65 and contradictory
underage answers, BMI 18.5/24/28, energy envelope, weight-record/account
precedence and future-record rejection, every risk qualifier, risk
unknown/missing, red flag/caution,
stale check-in/profile/user/plan/policy/catalog, unresolved legacy text, each
allergen category, unknown exclusions, timezone/date boundary, and privacy-safe
fingerprint/log assertions.

**Gate 1:** Cold-review Tasks 1-2 together. Re-run focused suites, migration
upgrade/downgrade, Fast, Full PostgreSQL, license validation, source diff, and
exact-SHA Fast/Full CI. Any unsafe default, ambiguous source, schema mismatch,
or allergy leak is P1/P2 and blocks Task 3.

## Task 3: Generator, Immutable Persistence, Migration, And Domain API

**Primary files:**

- `backend/app/nutrition/{generator,models,persistence,service,router}.py`
- `backend/app/nutrition/{schemas,validator}.py`
- `backend/alembic/versions/0010_nutrition_recommendations.py`
- `backend/alembic/env.py`
- `backend/app/main.py`
- `backend/app/core/config.py`
- `backend/.env.example`
- scoped deletion/idempotency integration files
- `backend/tests/test_nutrition_{generator,persistence,migrations,service,api}.py`
- `backend/tests/test_openapi_contracts.py`
- `backend/tests/test_migrations.py`
- `scripts/verify.py`

**Work:**

- generate deterministic training/rest breakfast/lunch/dinner templates from
  the filtered catalog and independently validate before persistence
- add immutable draft/active/superseded recommendation versions, one-active
  and one-current-draft invariants, source/version/freshness pins, and
  recommendation-only payload
- implement draft generation/review/confirmation, active retrieval, replacement
  preview/confirmation, catalog reads, eligibility/targets, and nutrition-data
  deletion, including structured nutrition profile fields and explicit Agent
  nutrition proposal/audit references
- reuse reviewed idempotency/user-lock helpers with nutrition namespaces;
  atomically supersede/activate and fail closed on partial replay state
- rebuild current context and validate on generation, confirmation, preview, and
  replacement; stale or unsafe operations produce no active-state change
- make SQLite invariants match PostgreSQL; add PG partial unique index
- add default-off `NUTRITION_RUNTIME_ENABLED`; disabling routes leaves existing
  health/training/Agent features usable
- ensure ordinary logs and errors contain only stable codes/IDs/versions

**Tests:** Determinism, complete meal structure, goal/training-rest differences,
meal-share and daily food-group bounds, non-generation-eligible incomplete
nutrient rows, allergen property matrix, no-safe-candidate, at least two alternatives,
replacement equivalence, immutable versions, one active, ownership isolation,
single-current-draft regeneration,
idempotent replay/conflict/partial hit, stale every source, concurrent confirms,
rollback injection, deletion, disabled gate, strict API/OpenAPI, SQLite/PG parity,
migration upgrade/downgrade/constraint/index metadata, and an explicit schema/
route audit proving no intake state. Deletion tests distinguish nutrition data
from general Agent conversation data and point to the existing Agent deletion
control.

**Gate 2 commands:**

```powershell
cd backend
python -m pytest tests/test_nutrition_*.py tests/test_openapi_contracts.py tests/test_migrations.py -q
cd ..
python scripts/verify.py fast
$env:VERIFY_REQUIRE_PG='1'; python scripts/verify.py full
```

Accept only after cold review, migration rollback review, local Full/PG, and
exact-SHA Fast/Full CI pass.

## Task 4: Static Agent Nutrition Tools And Context

**Primary files:**

- `backend/app/agent/{schemas,context_resolver,tool_registry,read_tools,action_tools,orchestrator,messages}.py`
- `backend/app/agent/prompts/agent_v1.txt`
- `backend/tests/test_agent_{schemas,context,tool_registry,read_tools,action_tools,confirmation,orchestrator,api,adversarial}.py`
- `backend/tests/fixtures/agent/agent_eval_v1.json`
- `scripts/verify.py`

**Work:** Add owned `nutrition_plan` entry and five static Tools. Reads expose
only bounded codes. Draft/replacement writes require the existing proposal and
separate confirmation boundary. Mandatory nutrition safety/validation wraps
every operation and cannot be model-selected. Add fixed unsupported responses
for special/disease diets and adversarial attempts to invent nutrients, bypass
allergies, override actor/version, or call hidden Tools.

**Tests:** Entry ownership/non-enumeration, minimal context, strict input/output,
unknown Tool/field, no raw body/allergy payload, no provider arithmetic, zero
writes before confirmation, replay/conflict/stale/restricted/red-flag, button/
Agent service parity, and provider-disabled deterministic domain availability.

## Task 5: Flutter Profile, Recommendation, Confirmation, And Attribution UI

**Primary files:**

- `app/lib/models/nutrition.dart`
- `app/lib/providers/nutrition_provider.dart`
- `app/lib/screens/nutrition/**`
- `app/lib/screens/profile/health_profile_screen.dart`
- `app/lib/models/health_profile.dart`
- `app/lib/providers/health_profile_provider.dart`
- `app/lib/screens/plan/plan_screen.dart`
- `app/lib/app.dart`
- `app/lib/providers/auth_provider.dart`
- focused Flutter tests under `app/test/**`

**Work:** Implement strict typed fail-closed parsing, structured allergy and
catalog exclusion inputs, Plan-tab nutrition entry, eligibility/limited/missing
states, target range/source notices, training/rest templates, real images with
fallback/attribution, draft review/activation, replacement diff/confirmation,
offline/retry/deletion, and auth/profile/safety reset hooks. Do not implement any
intake/meal-completion UI.

**Tests:** Unknown enum/field/result rejection, nullable-vs-empty profile state,
allergen selections, source/uncertainty labels, no false active state, no write
before confirmation, replacement diff, stale/disabled/restricted/red-flag,
image fallback/semantics/attribution, late response after logout/profile change,
offline retry, deletion reset, and widget text audit for forbidden tracking
concepts.

**Gate 3:** Cold-review Tasks 4-5. Run backend focused/Fast/Full PG, Flutter
focused/full/analyze, exact-SHA Fast/Flutter/Full CI, privacy projection audit,
and button/Agent parity tests.

## Task 6: Phase E2E, Android Smoke, Source Audit, And Exit Report

**Primary files:**

- `backend/tests/test_phase6_e2e.py`
- test-only synthetic device helper/fixtures
- `app/integration_test/**` only if supported by the current harness
- `docs/reports/phase6-codex-exit-audit-2026-07-30.md`
- `docs/product/roadmap.md`
- `docs/agent/ACTIVE_TASKS.md`
- README/docs required for synthetic run and data reset
- `scripts/verify.py`

**Work:**

- synthetic full flow: login, account body fields, structured health/risk/
  allergy/exclusion state, current check-in, active training plan, nutrition
  target, draft, confirm, training/rest views, source/attribution, replacement,
  restart/offline/failure, nutrition-data deletion
- prove restricted/red-flag/unresolved-allergy paths make zero recommendation
  writes and never call a live model
- run Android build/install/launch and enabled/disabled flows on the current
  target; verify no diary/photo/barcode/intake surface
- independently re-audit every source/media artifact and generated file
- write findings-first exit report, rollback evidence, residual P3 risks, exact
  local/CI SHA evidence, and only then mark roadmap/ledger verified

**Gate 4 commands:**

```powershell
python scripts/verify.py fast
$env:VERIFY_REQUIRE_PG='1'; python scripts/verify.py full
cd app
flutter analyze
flutter test
flutter build apk --debug --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1
```

**Done when:** All Phase 6 spec exit criteria pass on the final SHA, Android
synthetic evidence is captured, CI Fast/Flutter/Full is green, no P0/P1/P2 is
open, and Phase 7 starts only from the accepted Phase 6 closure commit.
