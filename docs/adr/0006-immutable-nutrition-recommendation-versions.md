# ADR-0006: Immutable Nutrition Recommendation Versions

## Status

Proposed for Phase 6 Gate 0 review (2026-07-30).

## Context

Nutrition recommendations depend on current body/profile/check-in/training state,
allergy/exclusion answers, and versioned policy/catalog/media. A mutable row could
hide which rules produced the visible plan, overwrite a previously confirmed
recommendation, or apply a replacement against stale safety state.

The roadmap requires draft, validation, user confirmation, replacement, audit,
and deterministic operation without AI. It explicitly does not require intake
tracking.

## Decision

Persist owned immutable recommendation versions with `draft`, `active`, and
`superseded` status. At most one current draft and one active version exist per
user. Regeneration supersedes the prior draft and inserts a new version.
Confirmation locks the owner, rebuilds latest context, verifies expected
version/freshness pins, reruns safety and independent validation, atomically
supersedes the previous active version, and activates the draft. Recommendation
payloads and version pins never change after insert; only reviewed status and
bounded supersession metadata transition.

Replacement first produces a typed deterministic preview. Explicit confirmation
rebuilds current context and creates a new immutable active version; it never
mutates the prior active payload. Generation and replacement use nutrition-
specific namespaces in the existing reviewed idempotency table and fail closed
on partial/mismatched replay state.

The payload stores only recommendation data and stable source/safety/version
codes. It has no user prose, allergy notes, model output, meal event, eaten
quantity, completion, adherence, or calorie-consumed field. Nutrition-data
deletion removes all recommendation versions and nutrition idempotency entries,
clears the two nutrition-specific structured health-profile fields, and removes
explicit nutrition Tool proposal/audit references. General Agent conversation
data remains governed by its separate deletion control.

PostgreSQL enforces one current draft and one active version with partial unique
indexes. SQLite uses the same owner-lock/application invariants and is covered
by concurrency/replay tests. Migration `0010` supports upgrade and downgrade on both dialects; the
preceding `0009` migration is limited to structured nutrition profile fields.

## Alternatives Considered

1. **One mutable recommendation row.** Rejected because confirmation history,
   source versions, rollback, and replacement diffs become ambiguous.
2. **Store only the active row.** Rejected because a reviewed draft/confirmation
   boundary and deterministic replay cannot be proven.
3. **Persist every generated candidate or conversation.** Rejected because it
   expands sensitive retention without user value and conflicts with minimal
   structured memory.
4. **Treat meals as daily tasks with completion.** Rejected because that creates
   the explicitly excluded nutrition-tracking product.
5. **Let Agent confirmation bypass nutrition draft confirmation.** Rejected for
   initial generation; Agent confirmation may create a draft, but activation
   remains the dedicated reviewed flow. A replacement may activate only when the
   Agent card already contains the complete typed diff and confirmation invokes
   the same domain operation as the button flow.

## Consequences

- More rows are stored, but the state transition and provenance are auditable.
- Every confirmation/replacement can fail stale and require a fresh preview;
  this is preferable to applying old dietary exclusions or safety state.
- Button and Agent paths can share one transaction-neutral domain operation.
- Account deletion must explicitly include nutrition rows in the final platform
  deletion audit.
- Recommendation history is not an intake history and must never be presented as
  evidence of what the user ate.

## Follow-Up

- Add migration metadata/upgrade/downgrade and SQLite/PostgreSQL parity tests.
- Add fault injection before/after flush and before commit to prove no false
  activation or half-superseded state.
- Add a schema and UI audit that rejects tracking/completion fields before Phase
  6 exit.
