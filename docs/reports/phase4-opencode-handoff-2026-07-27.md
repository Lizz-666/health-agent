# Phase 4 OpenCode Handoff: Four-Week Training Plan MVP

> Date: 2026-07-27. Author: the delegated OpenCode implementation session (one
> writer, one branch, one worktree) per `docs/agent/PHASE4_OPENCODE_CHARTER.md`.
> Final reviewer: Codex (independent acceptance pending). Scope is personal-
> development validation, not clinical or public-release approval.
>
> **Phase 4 candidate status: `review`** (NOT `verified`, `complete`, or
> `merged`). Only Codex may mark Phase 4 verified or integrate it. OpenCode
> stops here and awaits Codex final independent acceptance.

## 1. Branch, SHAs, worktree, PR

| Item | Value |
| --- | --- |
| Repository | `Lizz-666/health-agent` |
| Base SHA | `b7f8391e17a2adbb4ae52d012b360d17ff4550fd` |
| Implementation tip (last code) | `3db3303` (Task 7 E2E) |
| Final HEAD | this report commit (docs-only on top of `3db3303`) |
| Branch | `codex/phase4-opencode-implementation` |
| Worktree | `health-worktrees/phase4-opencode-implementation` |
| Draft PR | https://github.com/Lizz-666/health-agent/pull/2 (head `codex/phase4-opencode-implementation`, base `codex/phase3-spec-plan`, **draft**) |

Base..tip diff: **40 files changed, 6986 insertions(+), 47 deletions(-)** across 10
milestone commits (this report is the 11th, docs-only).

## 2. Milestone commits and ownership

| Task | Commit(s) | Scope |
| --- | --- | --- |
| 0 | `b8f710f` (docs), `a828485` (opencode push allow) | spec, plan, ADR-0001/0002, ledger; push permission relaxed `deny`->`ask` (separately auditable) |
| 1 | `899c0ee` (CI failed: upload-artifact SHA typo), `b439e9f` (fix + regression test) | shared CI: Node-24 v7 action SHA pins, Flutter job, `test_ci_action_pins.py` |
| 2 | `bcfb1d9` | plan models, state machine, persistence (atomic/idempotent), Alembic `0007`, tests; migration-contract tests updated |
| 3 | `09d7d60` | deterministic four-week generator + rationale codes + safety matrix |
| 4 | `1f0c813` | authenticated product API + application services + OpenAPI/auth/error tests |
| 5 | `cfbf70a` | Flutter typed models, provider, account-reset wiring, tests |
| 6 | `3b60c85` | Flutter plan + daily execution flow, 计划 tab, entry-point enablement, widget tests, Android smoke |
| 7 | `3db3303` (+ this report) | full-phase E2E + safety matrix + no-live-AI assertion, handoff |

Changed-file ownership by Task is recorded in the plan
(`docs/plans/training/2026-07-27-four-week-plan-mvp.md`, File And Module Map).
No file is owned by two Tasks; the shared files touched (`scripts/verify.py`,
`backend/alembic/env.py`, `backend/app/main.py`, `backend/app/providers/auth_provider.dart`,
`backend/tests/test_migrations.py`, `backend/tests/test_phase{1,2}_e2e.py`,
`app/lib/app.dart`, `app/lib/screens/profile/posture_profile_screen.dart`,
`app/test/screens/posture_profile_test.dart`, `opencode.json`) are coherent
consequences of the relevant Task and were verified together with it.

## 3. Actual behavior and explicit non-goals

Delivered (spec `docs/specs/training/2026-07-27-four-week-plan-mvp.md`):
- A user generates a deterministic four-week plan draft reusing the Phase 3
  safety engine (catalog, safety context, candidate engine, policy, draft
  validator) without bypass or relaxation, then explicitly confirms it; only a
  revalidated draft becomes the single active plan (atomic supersede).
- Today's session view (steps/reps or duration/rest/alternatives/illustration
  asset key) and five feedback states (completed/partial/too_busy/intentional_rest/
  discomfort) plus one user-initiated, re-validated substitution per session/day.
- Immutable plan versions with stable change reasons; idempotent generation,
  confirmation, substitution, and feedback (reuses `posture.idempotency_records`,
  ADR-0001).
- Honest states everywhere: blocked/restricted/red_flag/clarification_required/
  no_active_plan/rest_day/stale/parse-error are never coerced to success.

Explicit non-goals (deferred): no LLM/live-AI (deterministic only); no auto
same-day shortening/deferral/recovery-substitution, weekly review, or multi-day
restructuring (Phase 7); no chat Agent (Phase 5) or nutrition (Phase 6); no
change to the Phase 3 catalog/policy/engine; no new external source/license/media.

## 4. Migrations and rollback/recovery

- New Alembic revision `0007_training_plans` (revises `0006_health_weight_tracking`):
  five tables (`training_plan_versions`, `training_sessions`,
  `training_prescriptions`, `training_session_feedback`,
  `training_session_substitutions`) + the per-user single-active partial UNIQUE
  index on PostgreSQL (ADR-0002). `alembic/env.py` imports `app.training.models`.
- Upgrade creates the tables + partial index; downgrade drops only the five
  Phase 4 tables in reverse dependency order and never touches posture/health
  tables or other operations' `idempotency_records` rows.
- Plan data is recreation-safe (regenerable from the deterministic engine), so
  downgrade is a documented safe recovery path; users regenerate after rollback.
- Rehearsed on SQLite (tests via `create_all` + application-level single-active)
  and PostgreSQL 16 (`requires_pg`: partial unique index rejects a second active
  plan; superseded+draft for the same user allowed).

## 5. Safety, privacy, authorization, idempotency, failure-path evidence

- Safety: every generation/confirmation/today/substitution/feedback recomputes
  the current safety classification from current structured data. Restricted and
  red-flag contexts produce no plan (`restricted_no_plan`/`red_flag_stop`);
  missing data returns `clarification_required`. The generator self-validates
  every draft with the Phase 3 validator and never self-repairs a violation.
  Coverage: `test_training_generator.py` (12 goal×freq property cases + safety
  matrix), `test_phase4_e2e.py` (restricted/red_flag/missing-data end-to-end),
  `test_training_api.py` (restricted→409).
- Authorization/ownership: identity is JWT-derived only
  (`Depends(get_current_user)`); no endpoint accepts `user_id`, a decision, a
  candidate set, or a version fingerprint from the client. Ownership-scoped
  reads/writes; cross-account access impossible by construction
  (`test_training_api.py` cross-user; `test_training_plan_persistence.py`
  ownership isolation).
- Idempotency: replaying generate/confirm/substitution/feedback with the same
  key returns the recorded result and creates no duplicate active plan or
  feedback row; confirm resolves replay before the pending-draft precondition
  (`peek_idempotency`) so a replay returns the active plan after activation.
  Same-key-different-request is `idempotency_key_conflict`.
- Privacy: responses/logs carry decision fingerprints, gate/risk results,
  reason codes, versions, and counts only; no raw health fields, pain notes, or
  another user's identifiers. No free-text feedback note is stored or accepted.
- Failure: generation/confirmation/substitution/feedback are atomic; a mid-
  transaction failure leaves no partially active plan. AI/provider failure is
  impossible by construction (no provider called; asserted by source inspection
  in `test_phase4_e2e.py`). Stale draft rejected at confirm (`stale_context`).

## 6. Local verification evidence (commands, workdir, exit, counts)

| Command | Workdir | Exit | Result |
| --- | --- | --- | --- |
| `python scripts/verify.py fast` (with `GITHUB_TOKEN`) | repo root | 0 | ruff clean; **262 passed**, 0 failed, 7 PG-skipped; diff clean |
| `VERIFY_REQUIRE_PG=1 python scripts/verify.py full` | repo root | 0 | ruff clean; **1067 passed**, 0 failed, 0 skipped; PostgreSQL expected/actual **18/18**, version_evidence present |
| `flutter analyze` | `app` | 0 | No issues found |
| `flutter test` | `app` | 0 | **319 passed** |
| `flutter build apk --debug` | `app` | 0 | Built `app-debug.apk` (Gradle `assembleDebug`) |
| `flutter install -d emulator-5554 --debug` | `app` | 0 | Installed to `sdk gphone64 x86 64` |
| `adb -s emulator-5554 shell am start -n com.health.posture_app/.MainActivity` | `app` | 0 | launched; `topResumedActivity=...posture_app/.MainActivity` visible |

## 7. GitHub CI evidence (exact SHA, jobs, conclusions)

All Fast + Flutter + Full (PostgreSQL 16) jobs. The Node-20 deprecation
annotation present at base is gone after Task 1 (actions upgraded to Node-24 v7
immutable SHA pins). Cache-service 400s are transient remote alerts (charter:
not real failures); they never affected a conclusion.

| Commit (Task) | Run | Conclusion |
| --- | --- | --- |
| `a828485` (T0) | https://github.com/Lizz-666/health-agent/actions/runs/30249824954 | success (Fast + Full) |
| `899c0ee` (T1 first) | https://github.com/Lizz-666/health-agent/actions/runs/30250634924 | **failure** (upload-artifact SHA typo; fixed in `b439e9f`) |
| `b439e9f` (T1 fix) | https://github.com/Lizz-666/health-agent/actions/runs/30251065780 | success (Fast + Flutter + Full) |
| `bcfb1d9` (T2) | https://github.com/Lizz-666/health-agent/actions/runs/30255426730 | success |
| `09d7d60` (T3) | https://github.com/Lizz-666/health-agent/actions/runs/30256556187 | success |
| `1f0c813` (T4) | https://github.com/Lizz-666/health-agent/actions/runs/30258283949 | success |
| `cfbf70a` (T5) | https://github.com/Lizz-666/health-agent/actions/runs/30259437151 | success |
| `3b60c85` (T6) | https://github.com/Lizz-666/health-agent/actions/runs/30260607413 | success |
| `3db3303` + report (T7, final) | (filled after the final push — see ACTIVE_TASKS) | (filled) |

The final CI run on the report SHA is the authoritative Phase 4 remote
evidence; it is docs-only on top of the green `3db3303` implementation tip.

## 8. Self-review findings and fixes

- **Task 1 first-pass CI failed**: `actions/upload-artifact` was pinned to a
  typo'd SHA (`656e3c…` vs `656e7c…`) and could not resolve. Fixed the SHA and
  added `test_ci_action_pins.py` to authoritatively verify every pinned action
  SHA against its declared tag (resolves via the GitHub API when reachable;
  skips on network/rate-limit so it is non-flaky; structural format guards
  always run).
- **Task 2**: the single-active partial UNIQUE index could not be declared on
  the SQLAlchemy model (SQLite `create_all` drops `postgresql_where` but keeps
  `unique=True`, wrongly enforcing UNIQUE(user_id) for all rows). Moved it to
  migration `0007` only (PostgreSQL); application-checked on SQLite; a
  `requires_pg` test proves the DB-level guarantee. Updated `test_migrations.py`
  and the Phase 1/2 head-regression tests for the new head `0007`.
- **Task 3**: initial exercise selection included related variants in one
  session (`incompatible_combination`). Reworked selection to an independent set
  over the progression/regression/substitution graph. basic_strength at freq 4-5
  fail-closes (`insufficient_candidates_for_frequency`) because the catalog lacks
  enough high-recovery basic_strength candidates — honest, documented.
- **Task 4**: `confirm` initially checked `pending==None` before replay, so a
  confirm replay failed after activation. Reworked to replay-first
  (`peek_idempotency`); also fixed two un-awaited async calls in
  feedback/substitution.

First-pass Task acceptance failed for Tasks 1 and 4 (above); both were repaired
with regression tests before continuing.

## 9. Android / manual evidence

Android smoke (honest, real device — not a full business-flow replay): debug APK
built, installed on `emulator-5554` (Android 14 / API 34), and
`com.health.posture_app/.MainActivity` launched with
`topResumedActivity`/`visible=true`. The full plan UI flow is covered by widget
tests (`plan_screen_test.dart`); a manual end-to-end on-device business replay
was not performed and is left for Codex/user acceptance.

## 10. Source / license / media audit; generated files; residual risk

- **No new external source, code, or media** in Phase 4. It operates over the
  Phase 3 versioned catalog, safety policy, training policy, and source manifest
  (pins unchanged: `hasaneyldrm/exercises-dataset` `7455efae…`, `Snouzy/workout-cool`
  `77f25a92…` — read-only structural comparison, no code/data/media copied). The
  workout.cool comparison matrix is in the spec. Plan illustrations are the
  catalog's existing project-authored local SVG assets; Phase 4 adds no new media.
- **Unexpected generated files**: Flutter `pub get`/`analyze` regenerates
  `app/{linux,macos,windows}/flutter/generated_plugin_registrant.*` with CRLF
  churn (no content change; `git diff` empty after normalization). These were
  never staged or committed. No other generated artifacts.
- Residual P3 risks: (1) basic_strength plan generation is unavailable at
  frequency 4-5 (catalog coverage); (2) cross-day confirm is rejected as stale
  by design (fingerprint includes the daily check-in token) — same-day
  generate+confirm is the MVP contract; (3) original SVG visual-form review still
  pending for public release (inherited from Phase 3); (4) manual on-device
  business replay not performed; (5) `test_ci_action_pins` skips (does not fail)
  when the GitHub API is unreachable.

## 11. Statement

No real health data, real photo, production credential, live AI call, push to
`main`, merge, deployment, or external cost occurred. Synthetic data only.
opencode.json `git push` was relaxed `deny`->`ask` (charter-approved, separately
committed) to enable exact-SHA CI; pushes were branch-only.

OpenCode stops at `review`. Codex performs the final independent diff/commit
review, cold review, re-verification, and decides verification/integration.
