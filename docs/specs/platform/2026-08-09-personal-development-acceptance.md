# Phase 8 Personal Development Acceptance

> Status: accepted at Phase 8 Gate 0, 2026-08-09. Contract candidate
> `02229fa566d5765d75ef45a379b6800fef84ae53` and review metadata
> `1e18a03998c16dbf95f77d0519be271a20c98c0f` passed local exact-SHA gates
> and GitHub Fast/Flutter/Full run `31295975430`. Baseline
> `36be9a0f0cd989f32c8f4f7f7b9e2bc5fb4c66e6` is the verified Phase 7 closure.
> This specification authorizes synthetic-data local development only. It does
> not authorize deployment, merging to `main`, real health data or photos,
> production credentials, live-provider acceptance, or public release.

## Outcome

A developer can reset a disposable synthetic environment, start the complete
FastAPI application with a deterministic Agent provider, and replay the Phase 8
core journey through the real Flutter application on an Android emulator. The
journey uses real HTTP, JWT, routers, services, safety gates, persistence, and
serialization. Evidence is reproducible, fail-closed, bound to an exact Git SHA,
and does not depend on `FakeDio`, cloud AI, SMS, or real personal data.

Phase 8 is a personal-development acceptance and hardening phase, not a new
recommendation phase. Existing Phase 1-7 product and safety contracts remain
authoritative.

## Non-Goals

- Public SMS, deployment, app-store submission, mainland-China filing or
  compliance approval, production observability, capacity testing, or incident
  response certification.
- iOS, physical-device certification, wearables, payments, memberships,
  notifications, schedulers, or full offline business operation.
- New clinical thresholds, diagnoses, treatment, rehabilitation, disease-specific
  training or nutrition, or broader Agent permissions.
- Making a live cloud model, photo upload, or a real person's health record a
  local or CI acceptance dependency.
- Treating screenshots, scripted fixture setup, implementation reports, or green
  unit tests as substitutes for the real-HTTP Android journey.

## Approved Product Decisions

1. The illustrated self-test is the required posture path. Photo analysis is an
   optional, separately consented synthetic smoke and is disabled by default.
2. The deterministic scripted Agent provider is the hard acceptance gate. Live
   cloud-provider validation is optional, separately authorized, and never part
   of local or CI pass/fail.
3. Android emulator replay is mandatory. A physical Android device is optional
   evidence and cannot block Phase 8.
4. Offline scope is explicit unavailable, no false success, no unsafe mutation,
   and a visible retry path. Full offline data creation/synchronization is out of
   scope.
5. Reset clears the entire disposable synthetic database, recreates only the
   named synthetic identity and selected fixture checkpoint, and proves all
   domain tables are isolated from a previous run.
6. Temporal prerequisites for weekly review may be installed through a named
   test-only checkpoint. The actual review request, display, and any proposal or
   draft action under acceptance still travel through the real app and HTTP API.

## Audit Findings At Baseline

### P1 contract gaps to close before final acceptance

- Both existing Android integration tests replace the provider with `FakeDio`;
  they prove widget behavior but not authentication, networking, serialization,
  backend state machines, or persistence.
- `posture.purge` names one path `account_deletion` but currently deletes only
  posture, Agent, shared idempotency, and Phase 7 adaptive rows. Its own comment
  records that base health/training rows are not covered; nutrition rows are
  independently owned. Phase 8 may not claim complete deletion until the
  internal account-deletion orchestration covers every user-owned domain row.

### P2 acceptance gaps

- The Phase 5 synthetic device server includes only auth and Agent routers and
  is not a reusable full-product acceptance server.
- There is no one-command full-product synthetic start/reset/verify interface.
- The current core screens lack a complete, stable automation-key contract for
  login, posture selection/self-test, posture profile, and some cross-tab steps.
- Existing phase E2E tests are valuable service/API evidence but do not form one
  durable current real-HTTP acceptance suite or a visual Android audit.

These findings describe the baseline. They are not accepted residual risks.

## Architecture And Isolation

### Test-only acceptance application

The Phase 8 server is assembled only from `backend/tests` and includes all
production routers and global error behavior. It injects:

- a disposable SQLite database at one repository-controlled synthetic path;
- a fixed synthetic identity and development login credentials;
- the existing typed `ScriptedProvider` through the Agent dependency boundary;
- a test-only object store and purge key containing no external credential;
- named fixture checkpoints and narrow fault injection owned by the test app.

Production `app.main` must never import the Phase 8 factory or control routes.
No production setting, request field, Flutter define, or Agent input can select
the scripted provider or disposable database. Startup fails before touching any
database when the configured path is not the exact disposable path.

### Control plane

The test-only app exposes control routes outside `/api/v1`:

- `POST /__phase8/reset` accepts a closed checkpoint enum and an exact synthetic
  control header. It serializes resets, drops and recreates the disposable
  schema, recreates the synthetic identity, seeds only the selected checkpoint,
  clears provider history/faults, and returns non-sensitive counts plus a reset
  generation.
- `POST /__phase8/faults` installs an allowlisted one-shot failure for an
  allowlisted route and failure kind. It cannot alter safety classification,
  policy values, ownership, or successful payload contents.
- `GET /__phase8/evidence` returns synthetic mode, checkpoint, reset generation,
  provider/tool counts, and per-table row counts. It returns no health payload,
  phone, message, photo key, weight value, note, token, or prompt.

Unknown checkpoints, routes, fault kinds, missing/incorrect control headers,
concurrent reset, or non-disposable storage fail closed. Control routes are not
included in production OpenAPI.

### Checkpoints

`blank_supported` contains only the synthetic login identity, completed basic
user onboarding metadata, and a complete supported-adult health profile needed
by existing deterministic generators. It has no posture result, plan, check-in,
weight, nutrition recommendation, Agent run, or review.

`cycle_due` contains the same synthetic identity plus a server-generated,
validated active plan and the minimum versioned synthetic history needed for a
week-four review and end-of-cycle posture-recheck state. Fixture builders call domain
services or validated persistence builders rather than raw SQL. Missing facts
remain missing and are never seeded as zero or success.

`safety_blocked` contains only structured synthetic inputs that cause an
existing deterministic restricted/red-flag path. It introduces no new rule and
must prove that plan/adjustment/recommendation writes stay absent.

## Real-HTTP Core Journey

The hard-gate journey is checkpointed only where elapsed time is intrinsically
required:

1. Reset to `blank_supported`, launch the real Flutter `PostureApp`, and log in
   through `/auth/dev-login` using build-time synthetic credentials.
2. Select a body area and issue, complete the illustrated self-test, inspect the
   result and posture profile, and confirm an allowed posture goal.
3. Generate and explicitly confirm a four-week plan. Confirm that no draft is
   shown as active before confirmation.
4. Save today's check-in, inspect effective Today, explicitly request any legal
   same-day adjustment, and record session feedback or a substitution where the
   fixture permits it.
5. Add a synthetic manual weight through the UI, then inspect the activity grid
   and weight trend. Evidence records presence and state, never raw values.
6. Ask Agent for a bounded explanation. If an Agent write proposal is exercised,
   confirm it separately and prove no write occurred before confirmation.
7. Generate a nutrition draft and explicitly confirm it; render source and
   uncertainty information. Allergens/exclusions remain enforced.
8. Reset to `cycle_due`, generate and inspect the week-four review, verify facts
   render before proposals, create only a draft when requested, and inspect the
   posture-recheck state. Existing activation confirmation remains separate.
9. Reset again and prove previous domain rows, Agent traces, idempotency records,
   purge operations, and synthetic object-store entries are absent.

All app requests must use `AppConstants.apiBaseUrl`. The integration driver must
not override `apiClientProvider`, install an HTTP adapter, invoke domain services,
or directly seed application tables.

## Production Deletion Contract

Test reset and product deletion are separate mechanisms. Reset may drop a
verified disposable database. Production-domain code may never do that.

Before Gate 1 acceptance, internal `account_deletion` must detect and delete, in
dependency-safe order, all owned rows from identity-adjacent profile, health,
posture, training, nutrition, Agent, and shared idempotency domains, while
preserving only unlinkable purge receipts required by the current privacy
contract. It must retain the existing user transaction lock, write freeze,
object-first deletion, retry, lease, and tombstone invariants. Another user's
rows must remain unchanged. The current scoped health, nutrition, and Agent UI
delete actions keep their narrower semantics and labels.

Phase 8 does not add a public account-deletion endpoint or claim token revocation
and identity deletion. Those require a separate identity-lifecycle product
decision. It does close the misleading incompleteness of the existing internal
`account_deletion` scope and verifies it on SQLite and PostgreSQL.

## Failure And Safety Matrix

| Case | Required result |
| --- | --- |
| Backend unreachable | Explicit unavailable state; no normal/active fallback; retry control remains visible. |
| One-shot 503/timeout | First request fails visibly; retry performs a fresh real HTTP request and may recover. |
| Malformed/unknown response | Parse-error or unavailable; stale successful data is not relabeled current. |
| Expired/invalid token | Refresh once under existing contract, otherwise logout/login; no retry loop. |
| Missing profile/check-in | Existing missing-input state; no generation or adjustment write. |
| Restricted/red flag/pain | Existing escalation/safety-blocked state; zero ordinary plan, adjustment, or nutrition activation. |
| Stale plan/session/review | Explicit stale/conflict state; refetch before any new mutation. |
| Scripted provider exhausted/invalid | Agent unavailable/failed; no fabricated answer or tool result. |
| Duplicate tap/replay | One authoritative mutation; idempotent identity is stable and UI remains consistent. |
| Reset interrupted/concurrent | Serialized failure; environment is not reported ready until schema, seed, and evidence checks pass. |

No failure path may convert missing, unavailable, parse error, restricted, red
flag, or stale state into `normal`, `active`, `completed`, or a synthetic
recommendation.

## Evaluation And Evidence

- A versioned synthetic training matrix covers supported, missing input,
  equipment/schedule conflict, pain, restricted, red flag, stale, replay, and
  adjustment safety invariants using structured assertions rather than prose.
- A versioned Agent matrix covers allowed reads, proposal-confirmation writes,
  consent missing/withdrawn, prompt injection, cross-user access, unknown tool,
  invalid schema, provider timeout/exhaustion, and safety pre-routing.
- The HTTP runner records command, exact SHA, checkpoint, pass/fail counts, and
  sanitized state transitions. It must not record tokens or payload values.
- Android evidence includes OS/API/device ID, command, exact SHA, test count,
  and screenshots at login-complete, posture result/profile, active plan/Today,
  Agent, nutrition, and weekly review. Codex visually reviews the screenshots;
  no screenshot contains real data.
- Existing Fast, Full/PostgreSQL, Flutter analyze/test, migration, OpenAPI,
  privacy, and source/license checks remain mandatory.

## Acceptance Criteria

1. Start, reset, HTTP journey, eval, Flutter, and Android commands are documented
   and return non-zero on missing tools, server mismatch, failed assertions, or
   unexpected skips.
2. The full app runs against the test-only backend over real HTTP; no hard-gate
   integration test imports `FakeDioAdapter` or overrides `apiClientProvider`.
3. Every core flow step above is evidenced, with temporal checkpoint use clearly
   disclosed and limited to prerequisites.
4. Offline, retry, parse, stale, missing-input, safety-blocked, and provider
   unavailable paths fail closed and do not create unauthorized writes.
5. Reset is restricted to the exact disposable database and clears every table,
   object, provider trace, fault, and prior checkpoint before reseeding.
6. Internal production `account_deletion` covers all current user-owned domain
   tables and passes owner isolation, retry, concurrent lease, and PostgreSQL
   tests without weakening scoped deletes.
7. The scripted provider is deterministic, typed, bounded, and unreachable from
   production assembly. Live provider calls are absent from all acceptance runs.
8. Android emulator hard-gate tests pass on the accepted exact SHA; physical
   device and optional synthetic-photo smoke are reported separately.
9. Final local Full has zero failures, strict CI Full has zero skips and expected
   PostgreSQL parity, Flutter analyze/test pass, and exact-SHA CI jobs are green.
10. Known limitations and the separate public-release compliance checklist are
    current and do not present Phase 8 as deployment or medical approval.

## Rollout And Limits

Phase 8 code remains development/test infrastructure plus narrowly required
hardening. Production defaults remain unchanged: live Agent and photo analysis
are off unless their existing independent gates are satisfied. Rollback removes
the test-only harness and acceptance commands; any production deletion change
must retain schema compatibility and is reviewed as a high-risk privacy change.
