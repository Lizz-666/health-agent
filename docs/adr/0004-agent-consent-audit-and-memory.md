# ADR-0004: Agent Cloud Consent, Minimal Audit, And No Transcript Memory

## Status

Proposed for Phase 5 Gate 0 review (2026-07-28).

## Context

Agent context contains sensitive structured health and training information.
The current `ActorContext.consent_record` is always `None`; there is no general
cloud-model consent persistence. Storing complete chat would also create a new
long-term sensitive-data source and conflict with the product's structured
memory principle.

At the same time, Tool authorization, failures, versions, and side effects need
an auditable record that does not rely on raw conversation logs.

## Decision

Live Agent provider calls are fail-closed behind three independent controls:
the global runtime switch, reviewed/configured provider disclosure, and a current
server-side `agent_cloud_processing` consent. The client and model cannot supply
or override consent/provider state.

Do not persist user messages, assistant prose, complete context, prompts, or raw
provider requests/responses. Flutter keeps the current conversation in memory
only and clears it on app restart, logout, auth failure, account switch, or
consent withdrawal.

Provider output contains structured intent/Tool/message codes only. It has no
user-visible free-text field; every displayed message is rendered from reviewed,
versioned server templates.

Persist four minimal structures: immutable consent events, run metadata, Tool
event metadata, and short-lived typed action proposals. Proposal arguments are
bounded and contain no free text; they are scrubbed at terminal state or expiry.
Run/Tool audit stores stable codes, versions, fingerprints, counts, timing, and
side-effect references rather than raw payloads.

Phase 5 retains run/Tool metadata for 30 days and deletes expired rows at app
startup and Agent API boundaries through an independently testable cleanup
service. This is best-effort retention without a scheduler; a quiet instance can
retain expired rows past day 30. Consent events remain until Agent-data or account deletion. The fake
provider exists only as test dependency injection and has no runtime selection
path.

Context, request, and argument fingerprints use HMAC-SHA256 with a dedicated
server-only Agent audit key. Plain hashes of low-entropy values such as weight or
enum combinations are forbidden. Phase 5 does not retain prior HMAC keys after
rotation: pending proposals are scrubbed, while retained old audit fingerprints
remain deletable opaque metadata but cannot be re-verified. This bounded audit
trade-off is accepted for the MVP's maximum 30-day metadata window.

Provide explicit consent withdrawal and Agent-data deletion. Withdrawal blocks
new calls and scrubs pending proposals. Agent-only deletion removes consent and
audit/proposal rows but preserves independently owned domain records created by
previously confirmed operations.

## Alternatives Considered

1. **Reuse photo consent.** Rejected because purpose, data categories, provider
   behavior, and deletion semantics differ.
2. **Store complete transcripts for replay/memory.** Rejected because it expands
   sensitive retention and contradicts structured long-term memory.
3. **Use ordinary logs as audit.** Rejected because logs are not an owned,
   deletable, schema-constrained record and are prone to raw payload leakage.
4. **No persisted proposals; trust client confirmation payloads.** Rejected
   because ownership, expiry, replay, stale-context binding, and audit are weaker.
5. **Enable a fake provider as production fallback.** Rejected because a test
   fake is not evidence of consent, provider availability, or safe real behavior.

## Consequences

- Live Agent is unavailable until disclosure, consent, deletion, and privacy
  gate behavior are implemented and verified.
- Conversation history is intentionally lost across app restarts.
- Natural-language style is more constrained because Phase 5 does not display
  provider-authored prose; this is accepted to keep health guidance deterministic.
- Exact natural-language replay is not supported; idempotency applies to writes,
  while duplicate turn IDs prevent duplicate proposals.
- Four new tables and purge/retention tests are required.
- The current account-deletion orchestration is hard-coded in `posture.purge`;
  Phase 5 must explicitly add Agent rows there. Repairing its pre-existing lack
  of health/training domain deletion is separate platform work.
- Audit can explain which Tool/version/result occurred without retaining the
  user's raw health conversation.

## Follow-Up

- Verify the chosen provider's current official processing/API contract before
  implementing or enabling the live adapter.
- Define and version the user-facing disclosure in the implementation Task.
- Reassess the 30-day audit and consent-event retention before public release;
  public operation needs a durable scheduled cleanup mechanism rather than only
  Phase 5 startup/request-bound cleanup.
