# ADR-0003: Server-Controlled Agent Tools And Confirmed Writes

## Status

Proposed for Phase 5 Gate 0 review (2026-07-28).

## Context

The repository already has deterministic health, posture, training, safety,
validation, authorization, and idempotency behavior. Phase 5 adds a model-driven
interaction layer. Allowing the model to call domain writes directly or to
decide whether safety validation runs would create a second business path and
make prompt injection an authorization problem.

The roadmap requires Agent Tool authorization, idempotency, audit, important
change confirmation, and parity between button and chat behavior.

## Decision

The server owns a static typed Tool Registry. Each Tool binds allowed entries,
side-effect class, authorization adapter, and deterministic validators. The
model sees only the current entry's allowed schemas and remains untrusted.

Read Tools may run inside a bounded turn. Every write Tool produces a persisted,
owned, 15-minute proposal. Only a separate JWT-authenticated confirmation API can
execute it. Confirmation rebuilds latest context, re-runs existing safety and
validation, uses shared idempotency/user locking, and calls the same domain
service as the button flow.

Because current health/training write wrappers commit internally, Phase 5
extracts shared transaction-neutral operations. Existing APIs retain committing
wrappers; Agent uses the same underlying operations in a unit of work that
atomically persists the domain result, Tool audit, idempotency, and proposal
state. Wrapping a self-committing service in an outer transaction is prohibited.

Risk classification, plan validation, confirmation, consent, purge, photo
analysis, and arbitrary infrastructure access are not model Tools. They are
mandatory wrappers or separate product flows.

The orchestrator permits at most four provider decisions, four read calls, and
one write proposal per turn. A write proposal ends the turn.

## Alternatives Considered

1. **Direct model write Tools.** Rejected because user prose could trigger an
   unintended side effect, confirmation would live only in prompt semantics,
   and stale safety context could be applied.
2. **Let the model call a risk/validator Tool.** Rejected because the model could
   omit or reorder it. Safety validation is unconditional server code.
3. **Separate Agent business services.** Rejected because chat/button behavior
   would diverge and duplicate authorization, idempotency, and safety logic.
4. **Allow same-day writes automatically.** Deferred. The product boundary
   permits automatic same-day changes with notification, but explicit
   confirmation is safer and easier to audit for the first Agent MVP.

## Consequences

- Prompt injection cannot directly acquire write authority.
- Chat and button behavior share application services and validators.
- Every write requires an extra user interaction and proposal persistence.
- Confirmation must handle ownership, expiry, stale context, idempotency, and
  atomic audit/domain updates.
- Shared health/training persistence requires a scoped refactor and regression
  coverage so existing button behavior remains unchanged.
- Future automatic same-day behavior requires a new reviewed ADR/spec change;
  it is not enabled by relaxing a prompt.

## Follow-Up

- Implement the registry/context boundary before provider orchestration.
- Add adversarial tests for unknown Tool, actor override, confirmation bypass,
  stale context, repeated confirmation, and transaction failure.
- Revisit automatic same-day execution only with Phase 7's deterministic
  adjustment engine and an explicit product/safety decision.
