# ADR-0007: Execution Overlays And Review Drafts

## Status

Accepted at Phase 7 Gate 0 (2026-08-02). Contract SHA
`dceceb7dcd7955359e91939853c5290be799c277`; exact-SHA GitHub
Fast/Flutter/Full run `30732748723` passed.

## Context

Confirmed Phase 4 training plans and Phase 6 nutrition recommendations are
immutable versions with explicit activation. Phase 7 must adapt a real day's
execution, defer work without stacking it, preserve why an adjustment occurred,
and support weekly long-term proposals. Rewriting an active plan would erase its
confirmed contract; activating a review proposal would bypass existing consent
and safety boundaries.

Current feedback and substitution rows represent one daily outcome and one
user-initiated exercise replacement. They cannot safely encode shortening,
complete recovery sessions, date deferral, stale-context invalidation, weekly
input snapshots, or cross-domain draft origins.

## Decision

Keep active training and nutrition versions immutable. Represent a same-day
adjustment as an append-only execution overlay plus typed item rows. The overlay
references the source plan/session/date, latest-context fingerprint, policy and
catalog versions, deterministic reason codes, and optional target date. Today
uses only the newest overlay whose fingerprint still matches current owned
context and whose safety gate passes. Older overlays are audit history, never an
authorization.

Deferral changes the effective execution timeline, not the confirmed plan. Its
target must be an unoccupied date inside the same plan window that satisfies
existing recovery/load validation. No valid target means active rest; work is
not accumulated. A changed safety input invalidates the overlay immediately.

Persist weekly reviews as immutable input-fingerprinted snapshots. A changed
historical input inserts a new review version. A review may offer a training
draft or nutrition-refresh draft, but draft creation and activation are separate
states. New versions carry a nullable review-origin reference and continue
through their existing explicit confirmation state machines.

Every training confirmation binds the exact reviewed draft through
`expected_plan_version_id`. For a review-origin draft, confirmation also
reassembles the owned source week from current records and requires the stored
review fingerprint, proposal strategy, active-plan identity, and resulting
bounded preference change to remain identical. Any mismatch is stale and never
activates the draft.

The dedicated button command is a foreground user action and may atomically
apply a validated same-day overlay without a second dialog. Agent always creates
a short-lived typed proposal and requires a separate confirmation that invokes
the same domain command after revalidation. There is no background actor.

Weight trend is excluded from training decision inputs. It can appear as
descriptive review context and can support an offer to refresh a nutrition draft,
whose actual calculation remains wholly owned by the Phase 6 nutrition service.
Posture recheck is an in-app per-cycle due/dismissal event; safety messages are
outside that dismissal.

## State Transitions

```text
confirmed plan (immutable)
  -> no matching overlay
  -> applied overlay version (effective only while context matches)
  -> newer matching overlay version or blocked/stale history

week ended
  -> immutable review snapshot
  -> optional typed proposal
  -> optional training/nutrition draft
  -> existing explicit confirmation
  -> new active version, old active version superseded
```

No Phase 7 path adds a mutable `adjusted` status to the confirmed plan, edits
plan prescriptions, or marks a proposal/draft active.

## Alternatives Considered

1. **Rewrite the active plan/session.** Rejected because it destroys the
   confirmed version, provenance, replay, and original-versus-effective diff.
2. **Encode all behavior in feedback/substitution rows.** Rejected because date
   movement and full effective sessions become ambiguous and existing uniqueness
   constraints cannot represent versioned stale-context decisions.
3. **Generate a new plan for every same-day change.** Rejected because it turns a
   local execution choice into a long-term activation and creates excessive
   versions.
4. **Run adjustments or reviews in the background.** Rejected because Phase 7 has
   no scheduler/notification reliability contract and because hidden health-data
   writes would weaken user control and auditability.
5. **Let Agent and button share direct-write UX.** Rejected because conversational
   interpretation is less explicit; Agent retains proposal-confirmation while
   both surfaces share the same validated domain operation.
6. **Use weight trend to progress/regress training.** Rejected because the
   descriptive trend contract does not establish training causality and a single
   body metric must not become a safety/load rule.

## Consequences

- Original plan intent and effective daily execution remain independently
  explainable.
- Append-only versions consume more rows and require a deterministic resolver,
  but avoid mutable status races and preserve stale history.
- Cross-domain reviews coordinate through IDs and narrow read adapters; training
  does not own weight, nutrition, Agent, or posture source records.
- Button and Agent UX differ at the confirmation boundary while sharing domain
  safety, idempotency, and persistence.
- Additive migration rollback is operationally simple; database downgrade loses
  Phase 7 history and is limited to disposable synthetic environments.

## Follow-Up

- Prove resolver, deferral, idempotency, concurrency, and fault-injection
  invariants on SQLite and PostgreSQL before Gate 1 acceptance.
- Mutation/property-test that weight fields cannot alter a training result.
- Audit all Agent and deletion references before Gate 3 acceptance.
- Revisit scheduler or OS notifications only in a separate infrastructure and
  privacy specification.
