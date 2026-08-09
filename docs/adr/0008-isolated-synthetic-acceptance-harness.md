# ADR-0008: Isolated Synthetic Acceptance Harness

## Status

Accepted at Phase 8 Gate 0 on 2026-08-09. Contract candidate
`02229fa566d5765d75ef45a379b6800fef84ae53`; review metadata
`1e18a03998c16dbf95f77d0519be271a20c98c0f`; exact-SHA GitHub
Fast/Flutter/Full run `31295975430` passed.

## Context

Phase 1-7 have extensive domain, API, Flutter, and synthetic E2E coverage, but
the Android integration tests inject `FakeDio`. The Phase 5 device server is
test-only and safe, yet includes only auth and Agent routers. Phase 8 needs a
repeatable full-product Android journey over real HTTP without exposing a fake
provider or destructive reset in production.

The acceptance flow also crosses a real time boundary for weekly review. Tests
need deterministic historic prerequisites without changing production clocks,
sleeping for a week, or writing raw SQL from Flutter.

## Decision

Create one test-only FastAPI assembly under `backend/tests` that includes every
production router and injects a disposable SQLite database, scripted typed Agent
provider, synthetic object store, and fixed synthetic identity. Production
`app.main` never imports this assembly, and no runtime flag selects it.

Expose a separate test control plane under `/__phase8` for reset, allowlisted
one-shot faults, named temporal checkpoints, and sanitized evidence. Require an
exact synthetic control header and refuse any database URL except the fixed
disposable path. Fixture builders use validated domain/application operations.

The Flutter hard-gate driver launches the real `PostureApp` and uses its normal
`ApiClient` over emulator networking. It may call the control plane only to
reset or install a declared prerequisite/fault; it may not bypass a core user
mutation, override Riverpod API providers, or use `FakeDio`.

Keep disposable reset distinct from product deletion. The harness may drop and
recreate only its verified database. Production `account_deletion` remains an
object-first, lock/lease-protected domain orchestration and must be completed for
all current user-owned tables before Phase 8 acceptance.

## Alternatives Considered

1. **Extend widget tests with larger FakeDio fixtures.** Rejected because it
   still bypasses HTTP, auth, routers, serializers, persistence, and concurrency.
2. **Run production `app.main` with environment switches for fake AI/reset.**
   Rejected because a misconfiguration could expose test credentials, provider
   behavior, or destructive controls in a non-test environment.
3. **Require a live cloud provider.** Rejected because it adds cost, credentials,
   nondeterminism, privacy transfer, and external availability to the hard gate.
4. **Seed temporal state directly from Flutter or raw SQL.** Rejected because it
   creates a second domain writer and bypasses validation. Named server-side
   checkpoints make the prerequisite explicit and auditable.
5. **Wait in real time for weekly review.** Rejected as non-reproducible and too
   slow for local/CI acceptance.
6. **Use only database drop/reset and ignore production deletion gaps.** Rejected
   because test isolation cannot prove the existing `account_deletion` contract.

## Consequences

- Android tests become slower but cover the actual transport and application
  assembly used by a developer.
- Test controls are powerful; strict module isolation, path checks, control
  header checks, closed enums, and production import tests are mandatory.
- Temporal checkpoint evidence must identify which facts were seeded and which
  actions were performed through UI/HTTP.
- Live-provider and photo evidence remain optional and separately authorized.
- Production privacy deletion receives a dedicated high-risk review rather than
  being hidden inside acceptance fixture code.

## Follow-Up

- Gate 1 implements and cold-reviews the backend harness and complete internal
  account-deletion coverage.
- Gate 2 adds the sanitized real-HTTP journey, eval datasets, and commands.
- Gate 3 adds the Flutter/Android driver after the control/API contract freezes.
- Gate 4 performs exact-SHA local Android, PostgreSQL, CI, screenshot, privacy,
  and documentation acceptance.
