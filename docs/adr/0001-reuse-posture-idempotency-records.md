# ADR-0001: Reuse posture idempotency_records for Phase 4 plan writes

> Date: 2026-07-27. Status: accepted. Scope: Phase 4.

## Context

Phase 4 plan generation, confirmation, substitution, and feedback are mutating
operations that clients may retry (network flakiness, 401-refresh replay). The
charter requires these writes to be atomic and idempotent where retries can
occur. Phase 1 already introduced `posture.idempotency_records`
(`(user_id, operation, idempotency_key)` UNIQUE, with `request_hash`,
`status`, `result_ref`, `expires_at`) and the replay pattern is battle-tested
across posture confirmation/safety-signal flows.

## Decision

**Reuse** `posture.idempotency_records` for Phase 4 writes, scoped by new
`operation` values (`plan_generate`, `plan_confirm`, `session_substitute`,
`session_feedback`). Do **not** create a Phase 4-specific idempotency table.

## Rationale

- The table is operation-generic by design (`operation` is a free namespace). It
  is owned by no single domain at the row level; the UNIQUE constraint already
  namespaces by `(user_id, operation, key)`.
- Reuse avoids a near-duplicate table, a second expiry/reaper story, and a
  second replay code path, all of which would multiply the safety surface that
  must be independently reviewed.
- The replay contract (store `result_ref`, return the recorded result on replay,
  `idempotency_result_gone` HTTP 410 when the anchor was cleared) is exactly what
  Phase 4 needs and is already covered by existing tests.

## Consequences

- Phase 4 code depends on the posture idempotency helper API; it must not
  duplicate the table's invariants (it calls the shared helper, never raw SQL).
- The `operation` namespace is a contract: Phase 4 must use only its four
  declared values and never collide with posture operation names.
- The table remains owned by the posture domain for schema/migration purposes;
  Phase 4 reads/writes rows only through the helper and never adds columns.
- Migration `0007` does **not** alter `idempotency_records`; a future shared
  owner refactor is out of scope.
