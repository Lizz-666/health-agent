# Phase 3 Training Knowledge And Safety Engine Implementation Plan

> Status: Task 0 verified. Phase 2 is complete at `1818e74`; no Phase 3 runtime behavior is complete yet.

**Goal:** Deliver a deterministic, source-traceable home-exercise catalog, training safety gate, candidate engine, and `validate_training_plan` Tool without plan generation, AI, or Flutter training UI.

**Spec:** `docs/specs/training/2026-07-26-training-knowledge-safety-engine.md`

**Architecture:** Add a pure backend `training` domain backed by versioned curated JSON and typed Pydantic contracts. Compose current health/posture facts through adapters, but keep classification, candidate selection, and validation callable without HTTP, persistence, or an LLM.

**Safety:** Missing data, stale versions, unreviewed content, invalid sources, restricted status, and red flags fail closed. External exercise metadata is untrusted until mapped and reviewed. Red flags cannot be bypassed by substitution or draft validation.

**Verification:** Focused pytest and ruff per task; schema/source checks; synthetic safety matrix; full backend regression; real PostgreSQL regression for adapters even though Phase 3 adds no migration; Fast/Full GitHub CI after the user authorizes the first push; no Flutter gate unless Flutter files are unexpectedly touched.

## Phase 3 Collaboration Experiment

Phase 3 is the agreed OpenCode/Codex collaboration experiment:

- OpenCode with the user's selected Claude model writes all runtime and CI implementation for Tasks 1-7, but does not choose safety policy.
- Codex owns Task 0 specification, task prompts, scope control, safety-policy tables, state precedence, normalization behavior, executable safety cases, actual diff review, verification, commits, local integration, and final phase assessment.
- One OpenCode task writes one branch/worktree at a time. No second writer modifies the same task files.
- Before Tasks 4-6, Codex locks the exact relevant policy table and test matrix. OpenCode mechanically implements that contract and must stop on an unspecified safety choice. Codex directly takes over any affected change that cannot be reduced to a bounded implementation contract.
- Codex still performs the governance-required review before committing each task. To reduce coordination overhead, routine tasks receive a concise scope/diff/test review; Task 4 has both a pre-implementation contract lock and post-implementation independent checkpoint, and the full two-pass acceptance occurs in Task 7.
- The experiment records implementation time, Codex/OpenCode interaction count, first-pass acceptance, P0-P3 findings, rework, test quality, scope compliance, integration conflicts, and residual risk. The Phase 3 exit report compares this mode with the Phase 2 collaboration pattern.

## Layered Local And CI Verification

This plan follows `docs/product/roadmap.md` section 13.1. No GitHub workflow exists at the Task 0 base. Task 1 establishes it before the first Phase 3 remote candidate validation. Local results must not be reported as CI results.

| Task | Local focused | Fast CI | Full CI / manual gate |
| --- | --- | --- | --- |
| Task 0 spec/plan/ledger | links, source pins, charter completeness, diff check | not required | not required |
| Task 1 CI foundation | workflow syntax, shared runner dry-run, focused backend checks | required after user-authorized push | manual dispatch must prove full job; no deployment |
| Task 2 contracts/source intake | schema, malformed content, manifest/license/media exclusion, ruff | required | required at integration with Task 3 |
| Task 3 reviewed catalog/assets | complete catalog validation, relation graph, hashes, coverage, no external media | required | required; artifact includes catalog/source summary |
| Task 4 safety gate | safety matrix, stale/missing data, health/posture adapter tests, auth isolation | required | required; formal Codex contract checkpoint and PostgreSQL adapter regression |
| Task 5 candidates/policy | filter, de-duplication, conflicts, volume/recovery/progression invariants | required | required on the Task 5 candidate SHA and again with Task 4-6 integration |
| Task 6 validator Tool | typed contract, stale versions, blocked gates, no mutation/side effect | required | required; full backend and PostgreSQL regression |
| Task 7 exit audit | Phase 3 E2E, source/license audit, full backend/ruff, doc consistency | required | required on integrated SHA; no Android gate because Phase 3 has no UI |

CI constraints:

- Third-party actions are pinned to reviewed immutable commit SHAs.
- Default permissions are `contents: read`; no deployment, release, package write, production secret, real photo, or real health data.
- Fast CI runs targeted backend lint/tests. Full CI adds complete backend tests, synthetic safety evaluation, source/catalog checks, and PostgreSQL 16 adapter regression.
- Stale runs are cancelled. Jobs have explicit timeouts and dependency caches do not contain secrets.
- Every CI summary names workflow, job, tested SHA, result, failing tests, first useful error, and artifact link/name.
- Rebase, integration conflict resolution, or substantive code/content change invalidates old evidence.

## Task Standard And Report Format

Every task prompt includes goal, non-goals, allowed files, forbidden scope, dependencies, contract, safety rules, acceptance criteria, commands, and report format.

Every OpenCode report includes:

1. Base SHA and current head SHA.
2. Created/modified files grouped by allowed area.
3. Behavioral and contract changes.
4. Commands, working directories, exit codes, pass/fail/skip counts.
5. Remaining risks using P0-P3 and any assumptions.
6. `git diff --stat` and `git status --short`.
7. Unexpected/generated files.
8. Scope-compliance statement.
9. Local/Fast CI/Full CI evidence with tested SHA, or explicit `not configured`, `not authorized`, or `not required`.

OpenCode does not commit, merge, rebase, push, or modify another worktree unless the task prompt explicitly changes that rule.

## File And Module Map

Planned training package:

- `backend/app/training/__init__.py`
- `backend/app/training/schemas.py`
- `backend/app/training/knowledge.py`
- `backend/app/training/importers.py`
- `backend/app/training/context.py`
- `backend/app/training/safety.py`
- `backend/app/training/policy.py`
- `backend/app/training/candidates.py`
- `backend/app/training/validator.py`
- `backend/app/training/tool_contracts.py`
- `backend/app/training/tools.py`
- `backend/app/training/data/source_manifest.v1.json`
- `backend/app/training/data/THIRD_PARTY_NOTICES.md`
- `backend/app/training/data/training_safety_policy.v1.json`
- `backend/app/training/data/training_policy.v1.json`
- `backend/app/training/data/exercises.v1.json`
- `assets/training/illustrations/*.svg`
- focused `backend/tests/test_training_*.py`
- `backend/tests/test_phase3_e2e.py`

Files intentionally not planned:

- no Alembic revision or SQLAlchemy training model
- no `backend/app/main.py` or public router
- no Flutter `lib/`, `test/`, or `pubspec.yaml`
- no AI provider, prompt, or environment variable

## Ordered Tasks

### Task 0: Specification, source baseline, and task ledger

**Goal:** Establish the authoritative Phase 3 behavior, source/license pins, workout.cool comparison, task boundaries, CI mapping, and collaboration experiment before runtime changes.

**Non-goals:** No runtime code, workflow, tests, catalog data, assets, migration, or external write.

**Allowed files:**

- `docs/specs/training/2026-07-26-training-knowledge-safety-engine.md`
- `docs/plans/training/2026-07-26-training-knowledge-safety-engine.md`
- `docs/product/roadmap.md`
- `docs/agent/ACTIVE_TASKS.md`

**Forbidden scope:** `backend/**`, `app/**`, `.github/**`, `scripts/**`, external repository writes, and `.opencode/package-lock.json`.

**Dependencies:** Phase 2 Final Closure at `1818e74`.

**Contract:** Cover every roadmap Phase 3 delivery and exit criterion, pin both GitHub comparison sources, define external-media exclusion, distinguish missing data from risk, and define Tasks 0-7 with non-overlapping ownership.

**Safety rules:** Do not invent clinical thresholds or promote old posture correction prose/external metadata into approved safety content. Record current primary-source scope and limitations.

**Acceptance criteria:** Four allowed docs are mutually consistent, every later task is registered, source URLs/SHAs resolve, and `git diff --check` passes.

**Verification:** From repository root:

```powershell
git diff --check
git status --short
rg -n "2026-07-26-training-knowledge-safety-engine" docs/product/roadmap.md docs/agent/ACTIVE_TASKS.md
```

### Task 1: Layered GitHub CI foundation

**Goal:** Provide a shared local verification entrypoint plus Fast and manually/integration-triggered Full GitHub Actions jobs before Phase 3 remote candidate validation.

**Non-goals:** No deployment, release, PR creation, production secret, training code, catalog, dependency upgrade, or push.

**Allowed files:**

- `.github/workflows/ci.yml`
- `scripts/verify.py`
- `README.md` only for concise verification commands
- focused tests for the runner only if needed under `backend/tests/`

**Forbidden scope:** `backend/app/**`, `app/lib/**`, training data/assets, lockfile regeneration, and any external write.

**Dependencies:** Task 0 committed. Before selecting action SHAs, verify current official action repositories/documentation; do not use floating tags.

**Contract:** `python scripts/verify.py fast` runs deterministic targeted lint/backend checks; `full` runs complete backend, synthetic safety/source checks when present, and PostgreSQL-backed tests when CI supplies `TEST_DATABASE_URL`. The workflow uses least permissions, concurrency cancellation, timeouts, safe caches, PostgreSQL 16 for Full CI, and a short machine-readable/text summary artifact.

**Safety rules:** Synthetic data only. CI output must not dump environment values, health payloads, raw request bodies, or secrets. CI failures remain failures and are never converted to success summaries.

**Acceptance criteria:** Local runner works on Windows and CI Linux semantics; workflow syntax is valid; actions are SHA-pinned; Fast and Full jobs select the documented commands; no deployment permission exists. Remote run remains `not authorized/not run` until user authorizes push.

**Verification:** Runner self/help checks, Fast local run, workflow static inspection, `git diff --check`, ruff for any Python runner test.

### Task 2: Training schemas, loaders, and source intake

**Goal:** Implement strict typed catalog/policy/source contracts, fail-closed loaders, source manifest, and a deterministic non-media import adapter tested against synthetic fixtures.

**Non-goals:** No approved exercise catalog, safety classification, candidate selection, plan validation, DB, API, Flutter, network fetch during tests, or third-party media.

**Allowed files:**

- `backend/app/training/__init__.py`
- `backend/app/training/schemas.py`
- `backend/app/training/knowledge.py`
- `backend/app/training/importers.py`
- `backend/app/training/data/source_manifest.v1.json`
- `backend/app/training/data/THIRD_PARTY_NOTICES.md`
- `backend/tests/test_training_schema.py`
- `backend/tests/test_training_sources.py`
- `backend/tests/fixtures/training/**` with synthetic metadata only

**Forbidden scope:** Existing health/posture code, migrations, main/router, app/Flutter, external media, full upstream dataset, or network-dependent tests.

**Dependencies:** Task 1 integrated. Pin `hasaneyldrm/exercises-dataset` commit `7455efae41b330c265e7cd4b78dfa848e7ce5ebd` and workout.cool commit `77f25a922b51be7d96bd051c5d2096959f0d61a8` in the manifest.

**Contract:** Implement the spec catalog/exercise/provenance/illustration/prescription schemas with `extra="forbid"`. Loader rejects duplicate IDs, invalid versions, missing fields, relation errors, invalid hashes, external media/URLs, and unsupported equipment. Import adapter maps only whitelisted non-media names/taxonomy/equipment/muscle metadata, excludes upstream instructions/translations, and marks outputs `needs_review`; it cannot emit `approved`. The pinned upstream copyright and complete license/media-exception notice are retained in `THIRD_PARTY_NOTICES.md` and integrity-checked by tests.

**Safety rules:** Imported names/taxonomy/equipment/muscle metadata are untrusted source material. No source can self-approve. No missing safety field receives a default that creates recommendation readiness.

**Acceptance criteria:** Valid synthetic content loads; each malformed/unsafe case fails explicitly; source manifest includes license/commit/fields/media exclusion; third-party notice is complete and hash-checked; import is deterministic and strips/rejects all media and upstream instruction/translation fields; no network access is needed in tests.

**Verification:** Focused schema/source pytest, ruff for training/tests, Fast CI after user-authorized push.

### Task 3: Reviewed initial home-exercise catalog and original illustrations

**Goal:** Deliver 24-36 recommendation-ready bodyweight/resistance-band exercises with complete safety/relation/prescription/provenance fields and original local SVG illustration resources.

**Non-goals:** No plan generator, user-specific candidates, API, DB, Flutter integration, external media, medical/rehabilitation claims, or bulk upstream import.

**Allowed files:**

- `backend/app/training/data/exercises.v1.json`
- `assets/training/illustrations/*.svg`
- `backend/tests/test_training_catalog.py`
- Task 2 training schema/loader files only when a discovered contract defect requires a narrow fix
- `backend/app/training/data/source_manifest.v1.json` only to add item-level reviewed source entries

**Forbidden scope:** Existing health/posture code/data, copying posture `corrections`, third-party media, unpinned external content, app/Flutter, migrations, or generated binary assets.

**Dependencies:** Task 2 integrated. Exercise safety/applicability claims require current primary or peer-reviewed source review; external dataset metadata alone is insufficient.

**Contract:** Catalog covers both equipment modes and all five roles: warm-up, strength, corrective, mobility, recovery. Every entry meets the recommendation-ready invariant, has stable relations, local illustration hash/ownership, bounded instructions, and item-level source/review metadata. `approved` is machine-readable as `review_scope=personal_development` and must not be described as clinical/professional/public-release approval. Unsupported or uncertain entries remain absent rather than `approved`.

**Safety rules:** Wording stays in wellness/general-fitness scope. Stop conditions use approved structured codes. Posture applicability is a reviewed product mapping, not a treatment promise. Illustrations are supplemental and cannot override written instructions or stop conditions. SVGs contain no embedded remote content, scripts, raster blobs, or metadata copied from third parties. Public release remains blocked pending a separate qualified content and visual-form review.

**Acceptance criteria:** 24-36 personal-development-approved exercises; catalog loader and graph pass; coverage matrix passes; every referenced SVG exists and hash matches; media scanner finds no external URL/binary/embed; all sources, review scopes, reviewer roles, and review dates are traceable; no public/professional approval claim exists.

**Verification:** Catalog tests, source/license tests, SVG/static scan, ruff, Fast CI, Full CI catalog artifact.

### Task 4: Unified training safety context and eligibility gate

**Goal:** Compose current Phase 1/2 structured facts into a deterministic `TrainingSafetyDecision` with normal, caution, missing, restricted, red-flag, stale, and recovery behavior.

**Non-goals:** No candidate filtering, volume policy, plan validation, public API, new health/posture thresholds, persistence, migration, or UI.

**Allowed files:**

- `backend/app/training/context.py`
- `backend/app/training/safety.py`
- `backend/app/training/data/training_safety_policy.v1.json`
- `backend/app/training/schemas.py` for safety-context/decision contracts
- `backend/tests/test_training_context.py`
- `backend/tests/test_training_safety.py`
- `backend/tests/test_training_integration.py` for read-adapter/account-isolation cases

**Forbidden scope:** Modifying `backend/app/health/**`, `backend/app/posture/**`, migrations, routers, Flutter, catalog entries/assets, or AI.

**Dependencies:** Task 3 integrated. Before OpenCode starts, Codex must lock the Task 4 safety-policy table and executable matrix covering required/unknown fields, normalization aliases/failures, risk precedence, retained red flags, recovery, time-zone/date derivation, fingerprint composition, and posture-goal requirement. Read existing health/posture services/models and adapt without changing their contracts.

**Contract:** Recompute from typed current health profile, current-day check-in, all retained structured abnormal-pain check-ins needed to detect an uncleared historical red flag, active posture safety lifecycle, profile entries, and active confirmed goals. Require non-null pain limitations (empty means answered none), a complete risk screen with no missing/`unknown` qualifier, and at least one current confirmed non-blocked posture goal for every user-specific request. Normalize free-form pain area/status only through the versioned reviewed alias map; any active unknown value returns `clarification_required`. Validate an IANA time zone and derive current local date from an injected/server UTC clock. Build each check-in token from `id + local_date + UTC updated_at + risk_version + canonical structured safety hash`, excluding free text, and include the sorted retained-signal aggregate plus profile/posture/goal/policy/catalog versions in the decision fingerprint. Use existing domain-owned public read services where available; any necessary direct read query is narrow, ownership-filtered, and confined to `training.context`, with no writes or duplicated classifiers. Do not trust stored risk labels without recomputation. Emit deterministic fingerprint/version metadata. Enforce precedence `red_flag > restricted > clarification_required > eligible_conservative > eligible`. Stale or missing sources cannot authorize selection.

**Safety rules:** Free text, posture severity alone, knowledge `red_flags` prose, AI output, time elapsed, a newer normal check-in alone, and acknowledgement cannot lower risk. Restricted/red-flag decisions expose no candidate IDs. Recovery requires source correction/deletion plus a complete fresh context, an existing allowed posture lifecycle resolution, or a future separately specified controlled workflow; Phase 3 has no manual override.

**Acceptance criteria:** Synthetic matrix covers every tier/source combination, missing/unknown risk-screen values, null/empty pain limitations, known/unknown pain aliases and statuses, trusted/untrusted time zone and client-date mismatch, missing/stale confirmed posture goal for all fitness goals, a prior-day retained red flag followed by a normal current-day check-in, source correction/deletion recovery behavior, stale hashes/versions, cross-account isolation, deleted/missing context, posture conflict, and red-flag global blocking. Decision reasons contain codes/refs, not raw sensitive values.

**Verification:** Focused tests, ruff, backend integration against SQLite and disposable PostgreSQL 16, Fast/Full CI. This is the formal mid-phase Codex contract checkpoint.

### Task 5: Versioned training policy and deterministic candidate engine

**Goal:** Filter recommendation-ready exercises by current safety decision, equipment, goals, posture mappings, contraindications, conservative policy, de-duplication, and conflicts; validate volume/recovery/progression policy structures.

**Non-goals:** No full plan generation, persistence, Tool/API, UI, AI, or automatic progression.

**Allowed files:**

- `backend/app/training/data/training_policy.v1.json`
- `backend/app/training/policy.py`
- `backend/app/training/candidates.py`
- `backend/app/training/schemas.py` for policy/candidate contracts
- `backend/tests/test_training_policy.py`
- `backend/tests/test_training_candidates.py`
- `backend/tests/test_training_properties.py`

**Forbidden scope:** Existing health/posture code, catalog content/assets except a narrowly reported relation defect, migration, router, Flutter, or AI.

**Dependencies:** Task 4 passed the contract checkpoint. Before OpenCode starts, Codex locks exact versioned candidate precedence, de-duplication tags, conflict outcomes, normal/caution volume bounds, recovery rules, and executable expected sets. OpenCode stops instead of selecting a new health/safety threshold.

**Contract:** Execute the exact filter order in the spec; return stable IDs/order and structured include/exclude reason codes. Conservative policy only narrows choices/bounds. Conflicts resolve by explicit versioned priorities, never random order or prose interpretation.

**Safety rules:** Non-eligible decisions return zero candidates. Every returned exercise is recommendation-ready and equipment-compatible. Contraindications always beat goals/applicability. Red flag cannot use substitution. Policy limits are identified as product policy within reviewed source scope.

**Acceptance criteria:** Deterministic allowed sets for all synthetic profiles; no forbidden/duplicate item; multi-posture conflicts stable; caution never exceeds normal bounds; property tests cover invariants; policy/source/version trace included.

**Verification:** Focused policy/candidate/property tests, ruff, Fast CI, Full CI on the Task 5 candidate SHA, then Full CI again after Tasks 4-6 integrate.

### Task 6: `validate_training_plan` Tool and integration contract

**Goal:** Implement the typed, side-effect-free draft-plan validator and narrow authorization-aware application Tool for Phase 4 reuse.

**Non-goals:** No plan generation, repair, substitution execution, persistence, public route, UI, LLM, or audit database.

**Allowed files:**

- `backend/app/training/validator.py`
- `backend/app/training/tool_contracts.py`
- `backend/app/training/tools.py`
- `backend/app/training/schemas.py` for draft/result contracts
- `backend/tests/test_training_validator.py`
- `backend/tests/test_training_tools.py`
- `backend/tests/test_training_integration.py` for additive cases

**Forbidden scope:** Existing routers/services outside training, DB models/migrations, Flutter, catalog changes, policy loosening, or AI.

**Dependencies:** Task 5 integrated. Codex locks validator violation precedence and the four-week timeline matrix before implementation.

**Contract:** Validate current safety/candidate eligibility, context fingerprint, versions, exercise IDs, prescription bounds, session/weekly limits, recovery, duplication/conflicts, and relation use. Drafts have exactly four weeks; every session carries `week_index` 1-4, `day_of_week` 1-7, and unique in-week `session_order`, which produces the sole recovery/frequency timeline. Return all structured violations. Input remains unchanged and nothing is persisted.

**Safety rules:** Any stale/missing/blocked decision is invalid. Unknown violations do not downgrade to warnings. Validator failure never becomes `valid=true` or a repaired plan.

**Acceptance criteria:** Valid synthetic draft passes; all specified invalid cases fail with stable codes; authorization prevents cross-account context; mutation/side-effect tests pass; no AI/network/DB write occurs.

**Verification:** Focused validator/tool/integration tests, ruff, Fast CI, Full CI, complete backend regression and PostgreSQL adapter regression.

### Task 7: Phase 3 E2E, source audit, exit report, and experiment evaluation

**Goal:** Verify every Phase 3 exit criterion on the integrated SHA, document actual behavior and residual risk, and evaluate the OpenCode/Codex experiment.

**Non-goals:** No new feature, plan/UI implementation, source-policy relaxation, or roadmap completion without fresh evidence.

**Allowed files:**

- `backend/tests/test_phase3_e2e.py`
- focused training tests only to close verified coverage gaps
- `docs/reports/phase3-exit-audit-2026-07-26.md`
- `docs/specs/training/2026-07-26-training-knowledge-safety-engine.md` status/evidence only
- `docs/plans/training/2026-07-26-training-knowledge-safety-engine.md` status/evidence only
- `docs/product/roadmap.md` Phase 3 completion status only
- `docs/agent/ACTIVE_TASKS.md`

**Forbidden scope:** New product behavior, Flutter, plan generation, external writes without user authorization, real health data, or retroactively changing source pins to make tests pass.

**Dependencies:** Tasks 1-6 verified and integrated.

**Contract:** E2E covers catalog load, normal/caution/missing/restricted/red-flag gates, deterministic candidates, multi-posture conflict, valid/invalid drafts, stale versions, and red-flag non-bypass. Audit verifies licenses/SHAs/import fields/media exclusion/hashes and workout.cool matrix.

**Safety rules:** Only synthetic data. Completion requires no unresolved P0/P1/P2. Residual P3/manual limitations are explicit. No Android smoke is claimed or required because Phase 3 has no UI.

**Acceptance criteria:** Full local and authorized CI evidence is SHA-bound; all roadmap exits pass; source audit has no gap; docs match actual code; experiment metrics and recommendation for Phase 4 collaboration are recorded.

**Verification:** Full backend tests, ruff, PostgreSQL 16 adapter regression, Phase 3 E2E/safety/property suites, CI Fast/Full on integrated SHA, `git diff --check`, and source-link/hash audit.

## Integration Order

```text
Task 0 -> Task 1 -> Task 2 -> Task 3
                              -> Codex locks Task 4 policy/tests
                              -> Task 4 -> formal contract checkpoint
Task 4 -> Task 5 -> Task 6 -> Task 7 final acceptance
```

Tasks are serial by default. A second implementation session is not justified in the initial Phase 3 experiment because schema, catalog, policy, safety context, candidates, and validator share contracts even when their primary files differ.

## Rollback

- Tasks 2-6 add an internal package and static data only; no migration or user-facing activation occurs.
- Revert the latest integrated task commit or remove the training package from future callers. Do not silently select an older catalog/policy version.
- CI foundation can be disabled by reverting its workflow commit; it never deploys.
- Source/license uncertainty disables affected catalog entries or the entire catalog version instead of falling back to unreviewed content.
