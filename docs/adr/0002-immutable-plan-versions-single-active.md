# ADR-0002: Immutable plan versions and single active plan per user

> Date: 2026-07-27. Status: accepted. Scope: Phase 4.

## Context

The charter requires: preserve immutable plan versions; do not overwrite an
active historical version in place; generation/confirmation are separate and
confirmation is the only path to an active plan; failure must not create a
partially active plan. We must choose how plan state is represented and
constrained in the database.

## Decision

- Every generated draft that reaches a terminal lifecycle state is stored as an
  **immutable plan version** row (`training_plan_versions.status` in
  `draft`/`active`/`superseded`/`cancelled`).
- **At most one `active` plan per user**, enforced by a **partial unique index**
  on `(user_id) WHERE status = 'active'`.
- Supersede/cancel are **new states on the existing row**, not edits to the plan
  content. The prescription/session child rows of a version are never mutated
  after the version leaves `draft`; same-day substitution is recorded as a
  separate `training_session_substitutions` delta, not a rewrite of the
  immutable version.
- Confirming a draft is a single atomic transaction: set prior active/pending to
  `superseded`/`cancelled` and the new draft to `active`, then commit.

## Rationale

- Immutability gives traceable history (version + change reason) and matches the
  roadmap "计划版本和变更原因" requirement without read-after-write ambiguity.
- The partial unique index makes the single-active invariant a DB-level
  guarantee, so even a bug or concurrent confirm cannot create two active plans.
- Separating substitution/feedback into delta/record tables keeps the plan
  template pristine and makes "execute one day" replay-safe and idempotent.

## Consequences

- A plan version's content is write-once after it leaves `draft`; corrections
  always produce a new version (regenerate + reconfirm).
- The partial unique index requires PostgreSQL support; SQLite tests mirror it
  via a checked application-level invariant plus a best-effort unique index (the
  authoritative rehearsal is PostgreSQL 16 in `requires_pg` tests).
- Downgrade drops Phase 4 tables; plan data is recreation-safe, so rollback is a
  documented safe recovery path (users regenerate), not data loss.
