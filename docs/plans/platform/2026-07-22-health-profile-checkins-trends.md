# Phase 2 Health Profile, Check-Ins, And Trends Implementation Plan

> 状态（2026-07-26 Final Closure）：Tasks 1–8B 已完成，Phase 2 已完成。证据：后端 798 passed、ruff clean、Phase 2 E2E 6 passed、Flutter 300 passed、真实 PG16 集成 11 passed、一次性 PG16 容器裸 CLI `alembic upgrade head/current` 到 0006、Android Pixel 6 AVD 构建/安装/启动（MainActivity resumed）、一次性 PG16/uvicorn 实时旅程 15/15。**Android 人工逐屏业务回放由用户决定跳过，作为接受的残余风险；不写作“人工逐屏冒烟通过”。** 详见 `docs/reports/phase2-exit-audit-2026-07-26.md`。

**Goal:** Deliver a verified Phase 2 vertical slice where users can maintain structured health profile data, complete daily check-ins, record optional weight, and review trends/grid data without AI inference or training-plan generation.

**Spec:** `docs/specs/platform/2026-07-22-health-profile-checkins-trends.md`

**Architecture:** Add a backend health/tracking domain with deterministic safety readiness, authenticated REST endpoints, migrations, and Flutter models/providers/screens. Existing `user` remains the basic account profile. Existing posture profile remains posture-specific evidence.

**Safety:** Phase 2 stores sensitive health data, requires abnormal-pain follow-up, classifies red-flag/restricted states deterministically, blocks future recommendation readiness when data is missing or unsafe, and never treats AI or missing data as normal.

**Verification:** Focused backend tests per task, OpenAPI contract tests, migration checks, Flutter model/provider/widget tests, `flutter analyze`, full relevant test suites, and an Android emulator smoke before phase exit.

## Layered Local And CI Verification

本计划遵守路线图 `docs/product/roadmap.md` §13.1。仓库当前没有 `.github/workflows`，因此 Tasks 1-8 已记录的验证均为本地或可丢弃 PostgreSQL 环境的真实证据，不得改写为 CI 证据；后续 CI 落地不追溯改变这些结果。CI 只承担验证，不自动部署。

| Phase 2 Task | Local focused | Fast CI（workflow 落地后） | Full CI / manual gate |
| --- | --- | --- | --- |
| Task 0 规格和账本 | 链接、charter 完整性、diff check | 可并入下一候选批次 | 不需要 |
| Task 1 health domain + `0004` | domain/migration 相关 pytest、upgrade/downgrade、ruff | 必须 | 迁移属于高风险；候选和集成后必须含真实 PostgreSQL 演练 |
| Task 2 profile API | API、鉴权、跨用户、删除、OpenAPI | 必须 | 与 Task 1 契约集成后必须 |
| Task 3 daily check-in + `0005` | check-in、疼痛追问、风险分类、迁移测试 | 必须 | 健康安全和迁移均为高风险；候选和集成后必须 |
| Task 4 weight/trends + `0006` | CRUD、趋势/grid、边界和迁移测试 | 必须 | 可与 Task 3/4 后端集成节点合并执行一次全量验证 |
| Task 5 Flutter state | model/provider/session-reset 测试和 analyze | 必须 | 可延后到 Task 5-7 Flutter 集成节点 |
| Task 6 My health UI | widget/navigation、删除和 analyze | 必须 | 与 Task 7 集成后运行 Flutter 全量测试和构建 |
| Task 7 Today check-in UI | widget/navigation、失败状态、安全文案和 analyze | 必须 | 与 Task 6 集成后运行 Flutter 全量测试和构建 |
| Task 8 exit audit | E2E、OpenAPI、迁移、隐私、账户切换、全量后端/Flutter | 必须 | 必须；Android 模拟器人工冒烟仍是独立退出门，CI build 不能替代 |

实现 Agent 在 Task 内保持本地快速反馈，不等待或轮询 CI。Codex 审查真实 diff 并形成候选 commit 后，才按风险层级申请 push 并触发 CI；读取顺序为结果摘要 -> 失败 job -> 必要的局部日志，不默认把完整日志送入模型上下文。CI 摘要必须关联被验证 SHA，集成后旧证据失效。

## Task Definition Standard

Every task below is a self-contained charter that an independent implementation agent executes on its own branch/worktree. Each charter carries the fields required by `AGENTS.md` section 4:

- **Goal** - what the task delivers.
- **Non-goals** - what the task must not do.
- **Allowed files** - the only paths the task may create or modify.
- **Forbidden scope** - explicit hard exclusions.
- **Dependencies** - tasks/state that must be merged before this task starts.
- **Contract** - the API/model/cache contract the task must honor.
- **Safety rules** - the determinism and privacy invariants the task must enforce.
- **Behavior** - the observable behavior change.
- **Acceptance criteria** - the done-when conditions.
- **Verification commands** - exact commands (with working directory) and expected outcome.
- **Verification layers** - required Local focused, Fast CI, Full CI, and manual/device gates according to roadmap section 13.1.
- **Report format** - see Task Report Format (shared by all tasks).

## Task Report Format

Every implementation-task completion report MUST include (per `AGENTS.md` section 3):

1. Base SHA (the committed parent) and head SHA (the task branch tip).
2. Modified files (created and changed), grouped by allowed-file area.
3. Behavior changes and contract changes (API shapes, schemas, migration revision id, cache/reset behavior).
4. Verification commands, working directory, exit status, and key counts (pass/fail/skip).
5. Remaining risks (P0/P1/P2/P3 dispositions; user-only for P1/P2 acceptance).
6. `git diff --stat` output.
7. Unexpectedly generated files (tooling side-effects), if any.
8. Scope-compliance statement: confirmation that only allowed files were touched and no forbidden scope was entered.
9. Verification-layer evidence: Local results; Fast/Full CI run id, tested SHA, and status, or explicit `not configured` / `not required`; manual/device gates reported separately.

Implementation agents do not commit, merge, rebase, or push unless the task prompt explicitly authorizes it.

## File And Module Map

Backend additions (new `backend/app/health/` package, registered in `main.py` like the existing `user`/`posture` routers with prefix `/api/v1/health`):

- `backend/app/health/__init__.py`
- `backend/app/health/models.py`
- `backend/app/health/schemas.py`
- `backend/app/health/service.py`
- `backend/app/health/router.py`
- `backend/app/health/risk.py`
- `backend/app/health/trends.py`
- `backend/app/health/audit.py`
- `backend/alembic/versions/0004_health_profile_tracking.py`
- `backend/app/main.py` (add `app.include_router(health_router)` following the existing import-then-include pattern)
- `backend/tests/test_health_profile.py`
- `backend/tests/test_health_checkins.py`
- `backend/tests/test_health_weight_trends.py`
- `backend/tests/test_health_activity_grid.py`
- `backend/tests/test_health_privacy.py`
- `backend/tests/test_openapi_contracts.py` (extend)
- `backend/tests/test_phase2_e2e.py`

Flutter additions and edits (models/providers under existing dirs; screens under `today/` and `profile/`):

- `app/lib/models/health_profile.dart`
- `app/lib/models/daily_checkin.dart`
- `app/lib/models/weight_record.dart`
- `app/lib/models/activity_grid.dart`
- `app/lib/providers/health_profile_provider.dart`
- `app/lib/providers/daily_checkin_provider.dart`
- `app/lib/providers/weight_trend_provider.dart`
- `app/lib/providers/activity_grid_provider.dart`
- `app/lib/screens/today/today_screen.dart`
- `app/lib/screens/profile/health_profile_screen.dart`
- `app/lib/screens/profile/weight_trend_screen.dart`
- `app/lib/screens/profile/activity_grid_screen.dart`
- `app/lib/screens/profile/profile_screen.dart` (My-page entry list)
- `app/lib/app.dart` (routes + session reset wiring)
- `app/test/models/*`, `app/test/providers/*`, `app/test/screens/*` (matching `_test.dart` convention)

Existing files to treat carefully:

- `backend/app/auth/models.py`: do not keep expanding the account user table for Phase 2 health fields unless a migration decision explicitly requires it.
- `backend/app/user/*`: keep basic account profile compatibility. Do not repurpose `/api/v1/user/profile` as the health profile.
- `backend/app/posture/*`: do not move posture safety logic during Phase 2 unless a task explicitly scopes a shared safety extraction (none do).
- `app/lib/providers/auth_provider.dart`, `app/lib/providers/user_provider.dart`, `app/lib/app.dart`: update only as needed for cache clearing and navigation.
- `app/lib/screens/home/home_screen.dart`: currently the posture-browsing "首页" screen with no bottom-nav "今日" destination; Phase 2 introduces the Today entry via `app.dart` `StatefulShellRoute` (current nav is 首页/历史/我的).

## Ordered Tasks

### Task 0: Phase 2 specification and task ledger

**Goal:** Establish the approved Phase 2 scope, safety boundaries, task split, and coordination rules as current authoritative documents. No runtime behavior.

**Non-goals:** No code, migration, API, model, or Flutter change. No commitment of generated tooling artifacts.

**Allowed files:**
- `docs/specs/platform/2026-07-22-health-profile-checkins-trends.md`
- `docs/plans/platform/2026-07-22-health-profile-checkins-trends.md`
- `docs/agent/ACTIVE_TASKS.md`
- `docs/product/roadmap.md` (Phase 2 spec/plan links and status text only)

**Forbidden scope:** Any file under `backend/app`, `backend/alembic`, `backend/tests`, `app/lib`, `app/test`. Any README change (Task 8 owns doc sync). Any new ADR or external data seed.

**Dependencies:** Phase 1 signed off (main HEAD after `1d746e9`/`a886e86`); phase1 exit audit present at `docs/reports/phase1-exit-audit-2026-07-22.md`.

**Contract:** Spec must cover every roadmap section 6 exit criterion and every safety boundary in the task prompt (profile fields, 20s check-in, conditional pain follow-up, optional weight, scatter + moving trend, grid states, active-rest/safety-adjustment validity, Today/Plan separation, no AI guessing, account-switch isolation, view/correct/delete with verifiable retention). Plan must define all 9 task charters with every Task Definition Standard field. Ledger must register Tasks 0-8 with branches, base SHAs, dependencies, allowed files, and non-overlap rules.

**Safety rules:** Documents must restate that Phase 2 generates no training plan, no nutrition advice, no Agent; AI is never the source for profile/pain/safety/trend judgment; red-flag inputs enter a deterministic safety path; sensitive data never enters ordinary logs; tests use only synthetic data.

**Behavior:** Current, reviewable Phase 2 spec, plan, and ledger exist and are mutually consistent; all later tasks are defined and registered as `planned`.

**Acceptance criteria:**
- Spec covers all required coverage items above.
- Plan contains 9 task charters (Task 0-8), each with goal, non-goals, allowed files, forbidden scope, dependencies, contract, safety rules, behavior, acceptance criteria, verification commands, and report-format reference.
- `ACTIVE_TASKS.md` lists Phase 2 as current initiative with Tasks 0-8 registered and non-overlap rules stated.
- Roadmap section 6 points at the spec and plan paths that actually exist.

**Verification commands** (run from repo root `health/`):

```bash
git diff --check                  # Expected: no whitespace errors, exit 0
git diff --stat                   # Expected: only the 4 allowed doc paths
```

Markdown inspection: confirm spec/plan/ledger mutually reference the same date-stamped paths and the 9-task split.

**Report format:** Follow Task Report Format. Additionally summarize spec coverage and ledger registration.

### Task 1: Backend health profile domain and migration

**Goal:** Add the health profile data model, Pydantic schemas, deterministic profile readiness/risk primitives, and the Alembic migration that creates Phase 2 tables. No API surface yet.

**Non-goals:** No router, no HTTP endpoints, no Flutter changes, no check-in/weight/grid logic, no posture changes, no AI.

**Allowed files:**
- `backend/app/health/__init__.py`
- `backend/app/health/models.py`
- `backend/app/health/schemas.py`
- `backend/app/health/risk.py`
- `backend/alembic/versions/0004_health_profile_tracking.py`
- `backend/tests/test_health_profile.py` (domain/unit tests only)
- `backend/tests/test_migrations.py` (extend if needed for the new revision)

**Forbidden scope:** `backend/app/health/router.py`, `service.py`, `trends.py`, `audit.py`, `backend/app/main.py`, any check-in/weight model logic, Flutter, posture.

**Dependencies:** Task 0 merged; Alembic head `0003_posture_contract`.

**Contract:** `HealthProfile` is one current row per user with nullable optional fields (missing stays missing). Enums: `fitness_goal in {posture_improvement, fat_loss, basic_strength, mobility, general_wellness}`; `training_experience in {beginner, some_experience, experienced}`; `weekly_frequency in [2,5]`; `session_duration_minutes in {15,30,45,60}`; `equipment = {bodyweight, resistance_band}` booleans. `pain_injury_limitations`, `risk_screen`, `allergies`, `diet_exclusions` are structured JSON columns. `version`/`updated_at` present. Migration revision id chains from `0003`.

**Safety rules:** Domain functions must classify `missing_required_data`, `restricted` (underage/surgery/major injury/pregnancy or postpartum/chronic condition/eating-disorder concern), and red-flag readiness deterministically. Audit metadata must never embed raw pain notes, allergy labels, or full payloads. Missing fields are represented as missing, never inferred.

**Behavior:** Schema and domain functions can represent complete, incomplete, restricted, and red-flag-ready profile states without any HTTP or Flutter change.

**Acceptance criteria:**
- Enums reject unknown values; `weekly_frequency`/`session_duration_minutes` enforce bounds.
- Readiness/risk primitives return correct buckets for synthetic complete, incomplete, restricted, and red-flag-ready profiles.
- Audit metadata excludes raw sensitive values.
- Migration upgrades from `0003` and has a documented downgrade/reset path.

**Verification commands** (run from `backend/`):

```bash
python -m pytest tests/test_health_profile.py tests/test_migrations.py -q   # Expected: all pass
python -m alembic upgrade head        # Expected: applies 0004 cleanly
python -m alembic current             # Expected: 0004_health_profile_tracking
ruff check app/health                 # Expected: clean
python -m compileall app/health -q    # Expected: exit 0
```

**Report format:** Follow Task Report Format. Include the new migration revision id and the downgrade/reset strategy.

### Task 2: Health profile API, deletion, and OpenAPI contract

**Goal:** Implement authenticated `GET/PUT/DELETE /api/v1/health/profile` with token-derived ownership, validation, explicit missing data, deletion semantics, and OpenAPI schemas.

**Non-goals:** No check-in/weight/grid endpoints, no Flutter, no posture changes, no AI, no expanding `/api/v1/user/profile`.

**Allowed files:**
- `backend/app/health/router.py`
- `backend/app/health/service.py`
- `backend/app/health/audit.py`
- `backend/app/main.py` (register router only)
- `backend/tests/test_health_profile.py` (extend API tests)
- `backend/tests/test_health_privacy.py`
- `backend/tests/test_openapi_contracts.py` (extend)

**Forbidden scope:** `backend/app/health/models.py`, `risk.py`, migration, check-in/weight/grid, Flutter, posture, user profile.

**Dependencies:** Task 1 merged.

**Contract:** All endpoints JWT-only via `Depends(get_current_user)`; no `user_id` request parameter. `GET` returns explicit missing fields. `PUT` validates enums/bounds and bumps `version`/`updated_at`. `DELETE` removes user-linkable raw values (or tombstones per plan) and must not be returned afterward. Response/error bodies use `{"detail","code"}` via `AppException`; unhandled errors surface as 503 `service_unavailable` with no payload (existing `main.py` handler).

**Safety rules:** Cross-user isolation enforced server-side. Structured errors only; no DB values leaked. Deletion covered by tests confirming deleted data is not returned. Raw health values never logged.

**Behavior:** A user can view, update, and delete Phase 2 profile data through the API; another user cannot read or mutate it.

**Acceptance criteria:**
- Unauthenticated -> 401; invalid enum/range -> deterministic validation error; `user_id` parameter never accepted; cross-user read/write -> blocked.
- Deletion removes user-linkable data and it is not returned by `GET`.
- OpenAPI request/response schemas present and validated by `test_openapi_contracts.py`.

**Verification commands** (run from `backend/`):

```bash
python -m pytest tests/test_health_profile.py tests/test_health_privacy.py tests/test_openapi_contracts.py -q   # Expected: all pass
ruff check app/health                 # Expected: clean
git diff --check                      # Expected: exit 0
```

**Report format:** Follow Task Report Format. Include endpoint list and OpenAPI changes.

### Task 3: Daily check-in and conditional safety follow-up

**Goal:** Implement today check-in read/write, history, deletion, daily uniqueness, abnormal-pain follow-up requirements, and the deterministic `normal/caution/restricted/red_flag` check-in risk summary.

**Non-goals:** No training-plan adjustment, no plan generation, no weight/grid logic, no Flutter, no posture changes, no AI.

**Allowed files:**
- `backend/app/health/models.py` (add check-in model)
- `backend/app/health/schemas.py` (add check-in schemas)
- `backend/app/health/risk.py` (add check-in classification)
- `backend/app/health/router.py` (add check-in routes)
- `backend/app/health/service.py` (add check-in service)
- `backend/alembic/versions/0005_health_checkins.py`
- `backend/tests/test_health_checkins.py`

**Forbidden scope:** Weight/grid endpoints, Flutter, posture, AI, modifying Task 1's committed `0004` migration instead of adding this task's focused follow-up revision.

**Dependencies:** Tasks 1 and 2 merged.

**Contract:** Endpoints: `GET/PUT /api/v1/health/checkins/today`, `GET /api/v1/health/checkins`, `DELETE /api/v1/health/checkins/{checkin_id}`. At most one current check-in per user per `local_date`. `abnormal_pain=true` requires the full `pain_followup` object. `daily_status in {checked_in, active_rest, safety_adjustment}`. `risk_summary` is deterministic.

**Safety rules:** Red-flag follow-up values (neurological symptom, dizziness/chest symptom, acute trauma, configured severe-after-acute fields) must produce `red_flag` and block ordinary future recommendation readiness; restricted screen fields produce `restricted`. Malicious free-text note must not override safety rules. Raw pain notes never logged. Active rest and safety adjustment are valid, non-failure states.

**Behavior:** Check-ins can be safely recorded; red-flag check-ins cannot be mistaken for ordinary readiness by later services.

**Acceptance criteria:**
- Normal 20-second payload accepted; abnormal pain without follow-up -> `pain_followup_required`; severe acute pain / neurological / dizziness-chest / acute trauma -> `red_flag`; active rest and safety adjustment accepted as valid states; daily uniqueness enforced; cross-user isolation holds.

**Verification commands** (run from `backend/`):

```bash
python -m pytest tests/test_health_checkins.py tests/test_openapi_contracts.py -q   # Expected: all pass
python -m alembic upgrade head        # Expected: applies 0005 cleanly
ruff check app/health                 # Expected: clean
git diff --check                      # Expected: exit 0
```

**Report format:** Follow Task Report Format. Include the new migration revision id and list the risk-summary mapping cases covered.

### Task 4: Weight records, trend calculation, and activity grid API

**Goal:** Implement manual weight CRUD, the trend endpoint (raw points + moving trend metadata + `insufficient_data`), and the activity grid projection over Phase 2 check-in statuses.

**Non-goals:** No plan/nutrition adjustment output, no single-day adjustment claims, no success/failure judgment from weight, no Flutter, no posture changes, no AI.

**Allowed files:**
- `backend/app/health/models.py` (add weight model if not in Task 1)
- `backend/app/health/schemas.py` (add weight/trend/grid schemas)
- `backend/app/health/trends.py`
- `backend/app/health/router.py` (add weight/grid/trend routes)
- `backend/app/health/service.py` (add weight/grid service)
- `backend/alembic/versions/0006_health_weight_tracking.py`
- `backend/tests/test_health_weight_trends.py`
- `backend/tests/test_health_activity_grid.py`

**Forbidden scope:** Modifying Task 1's committed `0004` or Task 3's committed `0005` migration, check-in classification, Flutter, posture, AI, any recommendation text.

**Dependencies:** Tasks 1-3 merged.

**Contract:** Endpoints: `POST/GET /api/v1/health/weight-records`, `PUT/DELETE /api/v1/health/weight-records/{record_id}`, `GET /api/v1/health/trends/weight`, `GET /api/v1/health/activity-grid`. Weight `weight_kg` is a bounded positive decimal; `source=manual`. Trend returns raw records, a moving trend series only when enough points exist, else `insufficient_data`. Grid returns Phase 2 statuses only: `none`, `checked_in`, `active_rest`, `safety_adjustment`.

**Safety rules:** Trend never outputs plan/diet adjustments, warnings, or pass/fail judgment from single-day changes. Grid must not fake `partial_execution`/`main_plan_completed` before a plan exists. Raw weight values never logged in audit.

**Behavior:** Backend can render Phase 2 trend/grid data without training plans and without single-day adjustment claims.

**Acceptance criteria:**
- Valid/invalid weight bounds enforced; update/delete work; insufficient data metadata returned deterministically; moving trend values deterministic; date-range bounded; no recommendation text; grid statuses correct.

**Verification commands** (run from `backend/`):

```bash
python -m pytest tests/test_health_weight_trends.py tests/test_health_activity_grid.py tests/test_openapi_contracts.py -q   # Expected: all pass
python -m alembic upgrade head        # Expected: applies 0006 cleanly
ruff check app/health                 # Expected: clean
git diff --check                      # Expected: exit 0
```

**Report format:** Follow Task Report Format. Include the new migration revision id, moving-trend window rule, and grid status set.

### Task 5: Flutter Phase 2 models and providers

**Goal:** Add typed client models and Riverpod providers for health profile, today check-in, weight trend, and activity grid, with full state reset on logout, token failure, account switch, and parse failure.

**Non-goals:** No UI screens, no bottom-nav changes, no new API calls beyond Phase 2 contracts, no posture provider changes, no AI.

**Allowed files:**
- `app/lib/models/health_profile.dart`
- `app/lib/models/daily_checkin.dart`
- `app/lib/models/weight_record.dart`
- `app/lib/models/activity_grid.dart`
- `app/lib/providers/health_profile_provider.dart`
- `app/lib/providers/daily_checkin_provider.dart`
- `app/lib/providers/weight_trend_provider.dart`
- `app/lib/providers/activity_grid_provider.dart`
- `app/lib/providers/auth_provider.dart` (session-reset hook only)
- `app/test/models/health_*_test.dart`
- `app/test/providers/health_*_provider_test.dart`
- `app/test/providers/auth_session_reset_test.dart` (extend for Phase 2 reset)

**Forbidden scope:** `app/lib/screens/**`, `app/lib/app.dart` route/nav changes, backend, posture models/providers.

**Dependencies:** Tasks 2-4 API shapes merged (or mocked from committed schemas).

**Contract:** Models parse explicit missing/null fields as missing (never inferred), reject/safe-handle unknown enums, and never downgrade a non-normal response to normal. Providers expose fetch/update/delete and clear all Phase 2 state on logout/token-loss/account-switch/parse-failure. Reuse existing `api_client.dart` and auth/token conventions.

**Safety rules:** A 2xx response that fails to parse must invalidate stale Phase 2 state, not retain it as current. Account switch must clear profile, check-in, weight trend, and grid state. No raw health data written to logs/files.

**Behavior:** Flutter can consume Phase 2 APIs with safe state behavior before any UI screen is added.

**Acceptance criteria:**
- Model parsing tests cover null/missing/unknown values.
- Provider tests cover fetch/update/delete, stale-response handling, parse errors, logout reset, and cross-account clearing.

**Verification commands** (run from `app/`):

```bash
flutter pub get
flutter analyze --no-pub                              # Expected: no issues
flutter test --no-pub test/models test/providers      # Expected: all pass
```

**Report format:** Follow Task Report Format. Include the reset trigger matrix (logout/token-failure/account-switch/parse-failure).

### Task 6: Flutter My page health profile, weight trend, and grid UI

**Goal:** Add My-page entries for health profile, optional weight trend, activity grid, and Phase 2 data deletion. Keep posture profile separate from health profile.

**Non-goals:** No Today check-in flow (Task 7), no bottom-nav "今日" destination, no plan page, no posture screen changes, no AI.

**Allowed files:**
- `app/lib/screens/profile/profile_screen.dart` (entry list)
- `app/lib/screens/profile/health_profile_screen.dart`
- `app/lib/screens/profile/weight_trend_screen.dart`
- `app/lib/screens/profile/activity_grid_screen.dart`
- `app/lib/app.dart` (route registration for the new profile sub-routes only)
- `app/test/screens/health_*_test.dart`
- `app/test/screens/profile_*_test.dart`

**Forbidden scope:** `app/lib/screens/today/**`, Today/nav destination, backend, posture screens, providers (Task 5 owns them).

**Dependencies:** Task 5 merged.

**Contract:** New routes nested under `/profile` (e.g. `/profile/health`, `/profile/weight`, `/profile/grid`) following the existing `/profile/posture` pattern. Screens consume Task 5 providers. Deletion confirms before calling provider delete and refreshes state.

**Safety rules:** Show explicit missing/unavailable states; never display stale data from another account. Weight trend shows `insufficient_data` honestly; never fabricates precision. Grid never renders fake plan-execution statuses.

**Behavior:** A user can view, correct, and delete Phase 2 health profile data and inspect weight/grid data from My without seeing stale data.

**Acceptance criteria:**
- Widget tests cover missing data, edit flows, deletion confirmation, trend insufficient data, grid statuses, narrow-screen text fit, loading/error states, and logout clearing.

**Verification commands** (run from `app/`):

```bash
flutter analyze --no-pub                       # Expected: no issues
flutter test --no-pub test/screens test/providers   # Expected: all pass
```

**Report format:** Follow Task Report Format. Include the My-page entry list and routes added.

### Task 7: Flutter Today page check-in flow

**Goal:** Create the Today page for daily check-in. Normal check-in is short; abnormal pain opens conditional follow-up. Active rest and safety adjustment count as valid states. Do not display future plan data as if a plan exists.

**Non-goals:** No plan/nutrition rendering, no Agent, no My-page health profile editing (Task 6), no backend, no posture screen changes.

**Allowed files:**
- `app/lib/screens/today/today_screen.dart`
- `app/lib/app.dart` (add Today route and, if introduced, a Today nav destination in `StatefulShellRoute`)
- `app/test/screens/today_*_test.dart`

**Forbidden scope:** `app/lib/screens/profile/**` (My health screens), backend, posture screens, providers (Task 5 owns them).

**Dependencies:** Task 5 merged.

**Contract:** Today consumes the `daily_checkin_provider`. It shows whether the user already checked in, whether abnormal pain requires follow-up, and whether today is active rest or safety adjustment. It must not render any training plan or placeholder that looks active.

**Safety rules:** Red-flag follow-up result must show bounded escalation guidance and never convert to a normal/success state. Offline/error states are explicit, not stale. Active rest and safety adjustment are presented as valid, non-failure states.

**Behavior:** Today owns today's check-in and safety state, while plan functionality remains absent or explicitly unavailable.

**Acceptance criteria:**
- Widget tests cover normal check-in path, abnormal pain follow-up, red-flag result display, active rest, safety adjustment, offline/error handling, and bottom-nav behavior.

**Verification commands** (run from `app/`):

```bash
flutter analyze --no-pub                  # Expected: no issues
flutter test --no-pub                     # Expected: all pass (full suite)
```

**Report format:** Follow Task Report Format. Include whether a new bottom-nav destination was introduced and how Plan absence is communicated.

### Task 8: Phase 2 final E2E, documentation, and exit audit

**Goal:** Verify the complete Phase 2 flow end-to-end and update documentation to actual behavior only after fresh evidence.

**Non-goals:** No new feature, no roadmap phase-completion marking without fresh evidence, no public-release compliance work beyond Phase 2 privacy/audit requirements.

**Allowed files:**
- `backend/tests/test_phase2_e2e.py`
- `backend/tests/test_openapi_contracts.py` (extend if gaps found)
- `docs/reports/phase2-exit-audit-<exit-date>.md`
- `docs/specs/platform/2026-07-22-health-profile-checkins-trends.md` (status/clarification only)
- `docs/plans/platform/2026-07-22-health-profile-checkins-trends.md` (status only)
- `docs/agent/ACTIVE_TASKS.md` (status only)
- `docs/product/roadmap.md` (Phase 2 completion status only, after evidence)
- `README.md` (test-status table and stage line only, if commands changed)

**Forbidden scope:** New runtime features, new migrations, posture changes, Agent/nutrition/training-plan features.

**Dependencies:** Tasks 1-7 all merged on the integration branch.

**Contract:** E2E covers migration head/schema, the full user journey (profile -> today check-in -> abnormal pain follow-up -> weight -> trend/grid -> delete -> logout/account switch), red-flag/restricted routing, OpenAPI contract validation across all health routes, and deletion/retention verification.

**Safety rules:** Red-flag/restricted cases must not reach ordinary readiness. Account switch/logout must leave no previous-user health data. No raw health data in logs/audit. Synthetic data only.

**Behavior:** Phase 2 exit criteria are met with fresh evidence and no unresolved P0/P1/P2 findings.

**Acceptance criteria:** All roadmap section 6 exit criteria satisfied with fresh evidence; exit audit report written; ledger and roadmap updated only after verification.

**Verification commands:**

```bash
# Backend (from backend/)
python -m pytest -q                                                     # Expected: all pass, 0 unexpected skips
python -m pytest tests/test_phase2_e2e.py tests/test_openapi_contracts.py tests/test_migrations.py -q   # Expected: all pass
python -m alembic upgrade head && python -m alembic current             # Expected: 0006 head
ruff check app tests                                                    # Expected: clean
python -m compileall backend/app -q                                    # Expected: exit 0
# Optional PostgreSQL rehearsal (from backend/, if a disposable PG is available)
python -m pytest tests/test_pg_integration.py -q -s                    # Conditional
# Flutter (from app/)
flutter analyze --no-pub                                                # Expected: no issues
flutter test --no-pub                                                   # Expected: all pass
# Repo root
git diff --check                                                        # Expected: exit 0
```

Android emulator smoke (manual): login -> My health profile -> Today check-in -> pain follow-up -> weight entry -> trend/grid -> logout/account switch.

**Report format:** Follow Task Report Format. Additionally produce the exit-audit report with per-criterion evidence and remaining-risk table.

## Migration And Compatibility

- Use new Alembic revisions after current head `0003_posture_contract.py`: Task 1 creates `0004_health_profile_tracking.py`, Task 3 creates `0005_health_checkins.py`, and Task 4 creates `0006_health_weight_tracking.py`.
- Do not mutate Phase 1 posture tables unless explicitly needed and reviewed.
- Existing `/api/v1/user/profile` and Flutter onboarding must remain compatible while Phase 2 screens are introduced.
- If downgrade is not practical for a personal-development data migration, document a local reset path and keep destructive cleanup out of automatic test setup.
- SQLite tests and PostgreSQL behavior must both be considered for JSON fields, date handling, uniqueness constraints, and cascade/deletion semantics.

## Rollout And Rollback

Rollout:

1. Land backend domain and API first (Tasks 1-4).
2. Land Flutter client models/providers after API contracts stabilize (Task 5).
3. Land My page health data surfaces (Task 6).
4. Land Today check-in flow (Task 7).
5. Run E2E and update docs (Task 8).

Rollback:

- Disable or hide Phase 2 routes in Flutter if backend endpoints are unavailable.
- Keep posture Phase 1 flows independent so rollback of Phase 2 UI does not break posture assessment.
- Maintain a documented local DB downgrade or reset path for Phase 2 tables.

## Task Coordination Rules

- Each implementation task uses a separate `codex/phase2-taskN-*` branch and worktree; the coordinator registers base SHA, dependencies, and allowed files in `ACTIVE_TASKS.md` before work starts.
- Tasks that edit the same file must run serially unless file ownership is explicitly split in `ACTIVE_TASKS.md` (e.g. `models.py`/`schemas.py`/`router.py` are touched by Tasks 1-4 in dependency order, not in parallel).
- Do not start Task 5 before API response shapes from Tasks 2-4 are stable or mocked from committed schemas.
- Do not start Task 6 or Task 7 before Task 5 provider state-reset behavior is verified.
- Do not mark Phase 2 complete until Task 8 reruns backend and Flutter verification on the integrated branch.
- Every task report follows Task Report Format; implementation agents do not commit/merge/push unless explicitly authorized.
