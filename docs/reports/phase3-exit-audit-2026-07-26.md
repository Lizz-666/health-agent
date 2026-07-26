# Phase 3 Exit Audit — Training Knowledge And Safety Engine (OpenCode Delivery)

> Date: 2026-07-26. Author: OpenCode (full-phase implementation session).
> Audience: Codex final acceptance.
> **This is an implementation delivery report, not a verified/complete/merged
> claim.** Per the Phase 3 collaboration experiment, only Codex records Phase 3
> verified/complete status after independent diff review and re-verification.

## 1. SHAs and baseline

| Item | SHA |
| --- | --- |
| Comparison baseline (`base`) | `c49eb618759ff85d7235f515b57c9d3fad38d6cb` |
| Session start HEAD | `7984189c366575191b9820e82a284a926c36a79d` |
| Implementation final HEAD | `5cd1b65` (Task 7 implementation commit; this report is the branch-tip commit on top of it) |

Branch / worktree: `codex/phase3-opencode-implementation` /
`health-worktrees/phase3-opencode-implementation`. No merge, rebase, push or PR
was performed; no other worktree was modified.

## 2. Milestone commits (`base..implementation HEAD`)

```
7984189 docs: start phase 3 opencode implementation          (pre-existing start HEAD)
c777103 ci(phase3): add layered GitHub CI foundation and verify runner   (Task 1)
3fbf86c feat(training): task 2 schemas, loaders, source intake           (Task 2)
d659b28 feat(training): task 3 reviewed home-exercise catalog + SVGs     (Task 3)
8f504a6 feat(training): task 4 safety context and eligibility gate       (Task 4)
612356a feat(training): task 5 versioned policy and candidate engine     (Task 5)
79dc125 feat(training): task 6 validate_training_plan tool and contract  (Task 6)
5cd1b65 feat(training): task 7 phase 3 e2e and exit evidence             (Task 7a)
+ this docs(phase3): task 7 exit audit report                           (Task 7b)
```

## 3. Files by task and behavioral change

**Task 1 — CI foundation.** `scripts/verify.py` (shared local runner: `fast` =
ruff + SQLite tests + `git diff --check`; `full` = complete tests + PostgreSQL,
`VERIFY_REQUIRE_PG=1` makes any skip a hard failure; JUnit-based counts;
fail-closed on missing ruff), `.github/workflows/ci.yml` (fast on push/PR to
`codex/phase3-*`; full manual `workflow_dispatch(run_full)` on a `postgres:16`
service with the guarded `PG_TEST_DSN`/`PG_TEST_ALLOW_DESTRUCTIVE` contract;
actions pinned to reviewed immutable SHAs; `contents: read`; concurrency
cancel; timeouts; text summary artifacts; no deploy/secret/real-data),
`backend/tests/test_verify_runner.py`, `README.md` (verification section).

**Task 2 — schemas/loaders/source.** `backend/app/training/{__init__,schemas,
knowledge,importers}.py`, `data/source_manifest.v1.json`,
`data/THIRD_PARTY_NOTICES.md`, `tests/test_training_{schema,sources}.py`,
`tests/fixtures/training/valid_catalog.json`. Strict `extra="forbid"` models;
Equipment limited to bodyweight/resistance_band; Illustration has no URL field;
fail-closed catalog/manifest loaders (duplicate ids, unsupported versions,
relation unresolved/self/cycle, external-media URL scan); recommendation-ready
gate; deterministic non-media importer that can only emit `needs_review`.

**Task 3 — catalog + assets.** `data/exercises.v1.json` (24 personal-
development-approved exercises; both equipment modes; all 5 roles),
`assets/training/illustrations/*.svg` (24 original project-authored SVGs, sha256
recorded), `tests/test_training_catalog.py`, `.gitattributes` (`*.svg binary`
for deterministic cross-platform hashes).

**Task 4 — safety context/gate.** `training/context.py` (pure tz/date/token
helpers excluding `pain_note` + async read-adapter composing health/posture via
existing public services + narrow ownership-filtered active-goal read),
`training/safety.py` (SafetyPolicy loader + pure `classify_safety`,
precedence red_flag > restricted > clarification_required >
eligible_conservative > eligible), `data/training_safety_policy.v1.json`
(alias map, precedence, recovery), schemas additions,
`tests/test_training_{context,safety,integration}.py`.

**Task 5 — policy/candidates.** `data/training_policy.v1.json`,
`training/policy.py`, `training/candidates.py` (exact filter order; non-eligible
gates → zero candidates and zero excluded IDs; contraindications beat goals;
de-dup by movement-purpose set; stable sort), schemas additions,
`tests/test_training_{policy,candidates,properties}.py` (Hypothesis invariants),
`.gitignore` (`.hypothesis/`).

**Task 6 — validator Tool.** `training/{validator,tool_contracts,tools}.py`,
schemas draft/result contracts, `tests/test_training_{validator,tools}.py`,
additive `tests/test_training_integration.py` cases. Pure `validate_plan`
(blocked/stale/version/unknown/non-candidate/out-of-bounds/volume/recovery/
duplication/relation/timeline) + authorization-aware async Tool that recomputes
safety+candidates per call, no write/AI/repair.

**Task 7 — E2E + exit.** `tests/test_phase3_e2e.py` (13 cases), this report,
and status/evidence lines on the spec/plan/roadmap/ACTIVE_TASKS.

Intentionally NOT produced (per non-goals): no Alembic revision / SQLAlchemy
training model, no `main.py` or public router, no Flutter/lib/pubspec change,
no AI provider/prompt, no plan generator/persistence.

## 4. Verification evidence

All commands run from the worktree root unless noted. Exit code 0 unless stated.

| Command | Workdir | Exit | Result |
| --- | --- | --- | --- |
| `VERIFY_REQUIRE_PG=1 python scripts/verify.py full` | worktree root | 0 | ruff clean; **949 passed, 0 failed, 0 skipped** (skips are hard failures) |
| `python -m pytest tests/test_training_schema.py tests/test_training_sources.py tests/test_training_catalog.py tests/test_training_context.py tests/test_training_safety.py tests/test_training_policy.py tests/test_training_candidates.py tests/test_training_properties.py tests/test_training_validator.py tests/test_training_tools.py tests/test_training_integration.py tests/test_phase3_e2e.py tests/test_verify_runner.py -q` | `backend` | 0 | **151 passed, 0 failed, 0 skipped** (Phase 3 suite) |
| `python -m ruff check backend/app backend/tests scripts` | worktree root | 0 | All checks passed! |
| `git diff --check` | worktree root | 0 | clean (no whitespace/conflict) |
| Phase 3 safety matrix (`test_training_safety.py`) | `backend` | 0 | 25 passed |
| Candidate + property invariants (`test_training_candidates.py`, `test_training_properties.py`) | `backend` | 0 | 9 + (Hypothesis) passed |

## 5. PostgreSQL 16 evidence

- Engine: PostgreSQL 16.14 (Debian) via the repo's `conftest_pg.py` Docker path
  (`postgres:16`), confirmed at session setup:
  `[conftest_pg] PostgreSQL version: PostgreSQL 16.14 (Debian 16.14-1.pgdg13+1)`,
  `[conftest_pg] alembic upgrade head OK`.
- Adapter regression tests that ran on real PostgreSQL 16 (0 skip):
  `test_training_integration.py::test_adapter_builds_eligible_context_postgresql`,
  `test_training_integration.py::test_tool_validates_valid_draft_postgresql`,
  plus the existing Phase 1/2 `requires_pg` suite.
- `VERIFY_REQUIRE_PG=1` full run reported **0 skipped**, proving every
  PostgreSQL-backed test executed under the guarded DSN contract.
- Phase 3 adds no migration and no training DB model, so no upgrade/downgrade
  regression is required or applicable.

## 6. Fast / Full CI status

Remote GitHub Actions: **not authorized / not run** — no push/PR was performed
(push remains user-authorized only). The workflow contract is defined at
`.github/workflows/ci.yml` (Task 1) with actions pinned to immutable SHAs
(verified 2026-07-26): `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683`
(v4.2.2), `actions/setup-python@0b93645e9fea7318ecaed2b359559ac225c90a2b`
(v5.3.0), `actions/upload-artifact@65c4c4a1ddee5b72f698fdd19549f0f0fb45cf08`
(v4.6.0). Local `verify.py fast`/`full` are LOCAL evidence, not CI results.

## 7. Source / license / media exclusion audit

- Source manifest `data/source_manifest.v1.json` pins both comparison sources:
  `hasaneyldrm/exercises-dataset@7455efae41b330c265e7cd4b78dfa848e7ce5ebd`
  (MIT, metadata-only) and `Snouzy/workout-cool@77f25a922b51be7d96bd051c5d2096959f0d61a8`
  (comparison-only), plus WHO 2020, ACSM 2026, PAR-Q+/ePARmed-X+ references and
  the project-authored catalog.
- `data/THIRD_PARTY_NOTICES.md` retains the upstream MIT notice verbatim
  (Copyright (c) 2026 Hasan Emir Yildirim) and the Gym visual media exception
  verbatim; states Phase 3 reuses NO upstream media.
- Importer (`importers.py`) strips `instructions`/`translations`/`images`/
  `videos`/`gif_url`/`image`/`media_id` and rejects unrecognized media-like
  fields; can only emit `needs_review` (never `approved`).
- Media scanner (Task 3 + E2E): all 24 SVGs contain no `<script>`, `<image>`,
  `<foreignObject>`, `xlink:href`, `data:` URI or base64; the only URL is the
  required SVG namespace. Every SVG's on-disk sha256 equals the catalog
  `content_hash`.
- No posture `corrections` prose, external photo, real health datum, or
  production secret entered code, fixtures, logs or tests.

## 8. Residual risk (P0–P3) and fail-closed assumptions

- **P0:** none.
- **P1:** none.
- **P2:** none.
- **P3 (non-blocking, disclosed):**
  1. `ruff` and `hypothesis` are pinned dev/CI tools kept OUT of
     `backend/requirements.txt` (CI installs `ruff==0.15.22`,
     `hypothesis==6.141.1`; README documents local install). No runtime
     dependency changed.
  2. `training.context` owns one narrow ownership-filtered read query for
     active confirmed posture goals (the posture domain exposes no public
     accessor); spec-sanctioned gap fill, read-only, no classifier duplication.
  3. Remote CI is `not authorized / not run` until the user authorizes the
     first push.
  4. Illustrations are original programmatic line art; public release still
     requires a separate qualified visual-form review (spec requirement).
  5. Retained abnormal-pain = all abnormal-pain check-ins (Phase 3 has no
     auto-expiry); recovery requires source correction/deletion + fresh context.
- **Fail-closed assumptions implemented:** unspecified pain body-area/status →
  `clarification_required`; missing/unknown risk_screen qualifier →
  `clarification_required`; `eligible_conservative` uses conservative bounds;
  beginner experience and non-empty pain limitations → caution (per approved
  safety-boundaries §2 caution tier); any blocked gate → zero candidates and an
  invalid draft; stale context fingerprint or version mismatch → invalid; no
  manual override for restricted/red_flag; newer normal check-in alone, time
  elapsed, acknowledgement and free text never lower risk.

## 9. `git diff --stat` (`base..implementation HEAD 5cd1b65`)

```
63 files changed, 9800 insertions(+), 6 deletions(-)
```
(Net implementation footprint; full per-file stat available via
`git diff --stat c49eb618759ff85d7235f515b57c9d3fad38d6cb..5cd1b65`. The 6
pre-existing doc lines and the `7984189` start-HEAD docs commit are inside this
range because `base` < start HEAD.)

## 10. `git status --short` (at report authoring)

```
?? docs/reports/phase3-exit-audit-2026-07-26.md   (this report, Task 7b)
```
Working tree otherwise clean (no uncommitted implementation changes).

## 11. Unexpected / generated files

None committed. Tool caches `backend/.hypothesis/`, `backend/test.db`,
`__pycache__/`, `.pytest_cache/`, `.ruff_cache/` are gitignored and excluded.
The catalog/SVG generator scripts were authored in the opencode temp dir
(outside the repository) and are not part of the delivery; all committed data
is deterministic and re-verifiable via the loaders and tests.

## 12. Scope-compliance statement

All work was confined to the Phase 3 plan's allowed files for Tasks 1–7 on the
single implementation branch/worktree. No Flutter (`lib/`/`test/`/`pubspec`),
no Alembic migration, no `main.py`/public router, no AI provider/prompt, and no
existing `health`/`posture` domain code was modified (those domains were only
read via their public services). Two narrow, justified repo-config additions
were made and disclosed: `.gitattributes` (`*.svg binary`, required for
deterministic illustration hashes) and a `.gitignore` line (`.hypothesis/`
cache), plus status/evidence-only edits to the spec/plan/roadmap/ACTIVE_TASKS.
GitHub Actions use reviewed immutable commit SHAs (no floating tags), least
permissions, no deployment and synthetic data only. No real health data, photo,
credential or production key was used. OpenCode did not mark Phase 3
verified/complete/merged anywhere; that status is for Codex to record after
independent final acceptance.

---

OpenCode stops here. No merge, rebase, push or PR. Awaiting Codex final
acceptance of the whole Phase 3.
