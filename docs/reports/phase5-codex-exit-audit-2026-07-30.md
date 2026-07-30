# Phase 5 Codex Exit Audit

> Date: 2026-07-30. Scope: Gate 0 specification base `f6c2eae`, Gates 1-3,
> final implementation `517d548`, local/device acceptance, and exact-SHA CI.
> This is engineering acceptance for personal development, not medical,
> privacy-compliance, or public-release approval.

## Decision

Status: **verified**.

No unresolved P0, P1, or P2 finding remains in the reviewed Phase 5 content.
The Agent is server-controlled, privacy-gated, typed, ownership-scoped, and
unable to execute a domain write without a separate authenticated user
confirmation. Draft PR #3 remains unmerged.

## Findings Closed

1. Gate 1 closed ownership-before-catalog reads, current-day session scope,
   strict Tool input/output schemas, minimal provider context, and keyed
   fail-closed fingerprints.
2. Gate 2 closed proposal/run ownership, consent/deletion races, argument HMAC,
   validated server timezone, latest-context confirmation, transaction-neutral
   domain writes, and Agent/domain idempotency consistency.
3. Gate 3 added the bounded provider protocol and live adapter behind all
   privacy gates, deterministic pre-routing and templates, authenticated API,
   prompt-injection rejection, test-only provider injection, and no-live-AI
   evidence.
4. Final client review made capability/disclosure states internally strict,
   treats withdrawal/deletion ambiguity as unavailable, consumes each explicit
   disclosure acknowledgement once, keeps Agent-data deletion reachable on
   capability failure, and clears memory on auth, account, consent, provider,
   or disclosure changes.
5. The Android test server originally inherited an externally configured
   `TEST_DB_URL` before calling `drop_all`. It now binds one repository-local
   disposable SQLite path and refuses any conflicting external database URL
   before importing the test engine.
6. Existing-user login and onboarding completion now enter `/today`; legacy
   `/` redirects to the preserved standalone `/posture` flow. Contextual plan,
   session, and exercise links carry only entry type and owned identifier.

## Verification

| Command or check | Result |
| --- | --- |
| `python -m pytest tests/test_phase5_e2e.py -q` | `4 passed`; includes consent/read/proposal/confirm/delete, global disable, external DB refusal, and no production test selector |
| `python scripts/verify.py fast` | ruff clean; `653 passed`, `0 failed`, `7` expected PostgreSQL-only skips |
| `$env:VERIFY_REQUIRE_PG='1'; python scripts/verify.py full` | **1387 passed, 0 failed, 0 skipped**; PostgreSQL **20/20** with version evidence |
| `flutter analyze` | no issues |
| `flutter test` | **361 passed** |
| `flutter build apk --debug` with synthetic dev-login defines | APK built successfully |
| Android Pixel 6 AVD, Android 14/API 34 | clean install and `MainActivity` launch/resume succeeded |

Exact implementation SHA `517d548164137a8999569c70f20a8cf19630d331`
passed GitHub Actions run
[30517131521](https://github.com/Lizz-666/health-agent/actions/runs/30517131521):
Fast, Flutter, and Full/PostgreSQL 16 all succeeded.

The final Android APK used the test-only injected `ScriptedProvider` and a
synthetic seeded account. Evidence was:

- before consent: `provider_calls=0`, `weight_records=0`,
  `executed_proposals=0`;
- contextual health-profile read: structured result displayed, provider calls
  bounded to 2;
- weight proposal: typed `70.5 kg` diff displayed as not executed, with
  `weight_records=0` and `executed_proposals=0`;
- explicit confirmation: executed message displayed and both counts became 1;
- final disabled run: unavailable state and all other main tabs remained
  accessible, no composer was shown, and provider/write counts remained 0.

No live model request, real health data/photo, production credential, external
database, deployment, force-push, merge, or write to `main` was used.

## Residual P3 And Release Boundaries

- A live provider must remain off for automated development. Before any real
  health data, provider terms, processing location, retention, disclosure, and
  current official API behavior require a separate review.
- Audit cleanup after 30 days is request/startup best-effort; there is no
  durable scheduler. Public release must add and verify one.
- The Flutter client currently sends the validated project default
  `Asia/Shanghai`; persistent per-account timezone management is future work.
- The context resolver still reuses the existing private
  `training.context._active_goals` helper. It creates no new SQL path but should
  become a public domain boundary when that module is next refactored.
- Platform-wide health/training account deletion remains pre-existing debt;
  Phase 5 proves Agent-only deletion and the documented posture-owned account
  orchestration extension, not a universal purge claim.
- Android command-line tools/licenses remain incomplete in `flutter doctor`,
  although the pinned SDK could build, install, and run this APK.
- Public deployment, legal/compliance approval, AI-content labeling, app-store
  materials, and production incident/retention operations remain outside Phase
  5 and are explicit Phase 8/public-release gates.

## Rollback

Set `AGENT_RUNTIME_ENABLED=false` to block provider calls and Agent writes while
preserving Today, Plan, Posture, and Profile. Users can still withdraw consent
and delete Agent-owned data. Migration downgrade is allowed only on a
disposable database or after explicit Agent-data deletion; retained Agent rows
must not be destructively downgraded.

## Collaboration Result

The gated hybrid was more effective than Phase 4 whole-phase delegation.
OpenCode produced substantial Tasks 1-3 implementation and CI evidence, while
Codex gates found cross-domain ownership, transaction, and privacy defects
before Flutter integration. Codex then implemented Tasks 4-6 directly and used
a separate cold-review pass to find additional client and test-harness issues.
The practical default remains: delegate bounded implementation, keep Codex on
specification and safety gates, and require independent exact-diff acceptance
before phase completion.
