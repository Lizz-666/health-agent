# Phase 8 Gate 1 Codex Review

> Date: 2026-08-09. Gate 0 closure:
> `ad876d1b8b60a386f970ff1dfcd4ea78907b67b9`. Accepted implementation
> candidate: `b964de14ecd6be3cde042223e2fd92cef488d4e3` on
> `codex/phase8-implementation`.

## Decision

Gate 1 review: **PASS**. Open P0/P1/P2 findings: zero.

The accepted scope is the isolated synthetic backend foundation and complete
internal account purge. It adds no public account-deletion endpoint, token
revocation claim, production selector, deployment, live provider, real photo,
real health data, or production credential.

## Findings First

### P1 Closed

1. Internal `account_deletion` could report an empty scope and leave base
   health, training, and nutrition rows behind. Preflight now detects every
   current owned root, and transaction-neutral domain adapters delete the full
   graph in FK-safe order before shared idempotency cleanup.
2. Acceptance reset required destructive schema recreation but had no approved
   isolated implementation. The new control plane is assembled only under
   `backend/tests`, accepts only the exact disposable SQLite path, rejects
   external/malformed configuration before database access, serializes reset,
   and is absent from every production route/source module.

### P2 Closed

1. Early `cycle_due` fixtures lacked the current check-in and confirmed posture
   goal required by the existing deterministic safety engine, and used the
   unsupported `general_wellness` generation goal. The fixture now calls the
   real self-test, priority confirmation, plan generation, and activation
   services with `basic_strength`; it then installs only the minimum synthetic
   elapsed-time history.
2. Historical session dates were initially derived from the UTC date while the
   review service uses `Asia/Shanghai`. The fixture now calls the production
   local-date derivation, eliminating a cross-midnight false-missing outcome.
3. The prior DB-failure coverage raised before any new domain delete ran. A
   late health-stage fault now proves already-issued training/nutrition deletes
   roll back atomically, while owner-isolation tests retain another user's
   health, training, and nutrition rows.
4. The first malformed-response fault returned valid JSON with an unexpected
   shape. It now emits truncated `application/json`, exercising transport decode
   failure rather than only DTO validation.
5. The new PostgreSQL case initially used only the skip decorator, so strict CI
   ran it but did not count it in the evidence manifest. The explicit
   `requires_pg` marker raises authoritative evidence from 27 to 28 tests.
   Run `31304078272` is retained as audit history but is not Gate 1 evidence;
   accepted run `31304416414` proves PostgreSQL `28/28`.

## Accepted Behavior

- The test app mounts every production router with explicit DB/provider
  overrides and adds authenticated, closed `/__phase8/reset`, `/faults`, and
  `/evidence` routes outside `/api/v1`.
- `blank_supported`, `cycle_due`, and `safety_blocked` are strict checkpoints.
  The cycle fixture is server-generated and review-due; the blocked fixture
  reaches the existing `restricted_no_plan` result and writes no plan.
- Reset drops/recreates only the exact disposable schema and clears tables,
  scripted-provider history, one-shot faults, and synthetic object keys.
  Evidence returns counts and mode only, never payload values.
- The device server starts in a fresh process on `phase8_acceptance.db`, uses
  fixed synthetic login and `ScriptedProvider`, and fails before touching a DB
  for PostgreSQL, another SQLite path, blank, or malformed external URLs.
- Full account purge retains the existing object-first flow, per-user lock,
  write freeze, retry/lease, rollback, duplicate-call, and unlinkable tombstone
  invariants. Scoped health/nutrition/Agent deletion APIs remain narrow.

## Verification

Local candidate content:

| Command | Result |
| --- | --- |
| `python -m pytest tests/test_phase8_harness.py tests/test_phase8_deletion.py tests/test_privacy_gate.py -q` on exact `b964de1` | exit 0; `91 passed / 2` expected local PostgreSQL skips |
| `python scripts/verify.py full` before the evidence-marker-only commit | exit 0; Ruff clean; `1648 passed / 0 failed / 39` conditional skips; diff clean |
| Fresh-process device lifespan smoke | exit 0; `blank_supported 1`; disposable DB removed after engine disposal |

GitHub Actions workflow-dispatch run `31304416414` checked out exact SHA
`b964de14ecd6be3cde042223e2fd92cef488d4e3`:

- Fast: success; `936 passed / 0 failed / 10` expected PostgreSQL skips.
- Flutter: success; analyze clean; `472 tests passed`.
- Full: success; `1687 passed / 0 failed / 0 skipped`;
  `VERIFY_REQUIRE_PG=1`; PostgreSQL expected `28`, actual `28`, version evidence
  present.

## Rollback And Next Gate

No migration or production assembly changed. Reverting the two implementation
commits removes the test harness and restores the previous purge scope; no
production schema rollback is required. Test databases and synthetic object
keys are disposable and are not committed.

The documentation-only Gate 1 closure SHA must pass exact-SHA Fast, Flutter,
and strict Full before Task 2 starts. Task 2 remains Codex-only and will freeze
the real-HTTP/control/evaluation contract. No OpenCode prompt is authorized
until Gate 2 itself is accepted.
