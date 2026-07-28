# Phase 5 Gate 0 Independent Review Disposition

> Review target: `8ac8858a4099b5fca49f392f1e6eaf391ccbf7d1`.
> Reviewer: OpenCode independent read-only session. Verdict: FAIL with P0=0,
> P1=0, P2=2, P3=4. No runtime code, live AI, credentials, or real health data
> were used.

## Findings And Disposition

1. **P2: optional turn timezone had no missing-value contract.** Closed in the
   candidate fix by requiring a validated IANA timezone on every turn, using the
   existing training validator, forbidding defaults, defining `invalid_timezone`,
   and requiring zero side effects plus boundary tests.
2. **P2: account deletion was described as though a registration mechanism
   existed.** Closed by naming the actual hard-coded `posture.purge` orchestration,
   requiring all four Agent tables and Agent idempotency namespaces to be added,
   and explicitly leaving the pre-existing health/training deletion gap outside
   Phase 5 rather than overstating account deletion coverage.
3. **P3: training confirmation has two idempotency layers.** Closed by specifying
   joint first-run, replay, partial-hit, and conflict tests; health writes are
   explicitly single-layer Agent idempotency.
4. **P3: training exercise catalog reuse was imprecise.** Closed by requiring the
   adapter to use `training.service.catalog/_index`, backed by
   `training.knowledge`, and the same projection source rather than a new path.
5. **P3: old HMAC audit fingerprints cannot be verified after key rotation.**
   Accepted and made explicit as a bounded MVP trade-off: proposals are scrubbed,
   old audit metadata remains deletable but non-verifiable for its remaining
   retention window.
6. **P3: 30-day cleanup has no scheduler.** Accepted and made explicit as
   best-effort startup/request cleanup, not an exact deletion guarantee. Durable
   scheduled cleanup remains a public-release gate.

## Scope Decision

Phase 5 does not expand into a platform-wide account deletion repair. That work
would cross independently owned health/training data and requires its own product,
privacy, migration, and rollback contract. Gate 0 only authorizes the narrow
Agent-owned extension needed for the Agent MVP.

## Gate State

The two P2 findings are addressed in the candidate documents, but Gate 0 remains
in `review` until an independent read-only re-review confirms P0/P1/P2 are zero.
Tasks 1-7 remain unauthorized until that verdict is recorded against an exact SHA.
