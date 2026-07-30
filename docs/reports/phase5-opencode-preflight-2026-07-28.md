# Phase 5 OpenCode Preflight Review

> Date: 2026-07-28. Read-only report received at
> `deab77936635f19b580b81438f68f5b183888a3f`. No repository changes, live AI,
> credentials, or real health data were used by the reviewing session.

## Accepted Evidence

- The repository has typed posture/training Tool foundations and server-injected
  `ActorContext`, but no Agent package, chat provider protocol, `/api/v1/agent`
  router, Agent audit persistence, or Flutter Agent destination.
- Eight of the roadmap's nine capability families already have domain logic.
  Agent work should primarily adapt and orchestrate those services rather than
  recreate health/posture/training behavior.
- Automatic same-day shortening, deferral, and recovery adjustment do not exist
  and are explicit Phase 4 non-goals deferred to Phase 7.
- Existing ownership contracts avoid distinguishing missing from cross-user
  entities. Agent must preserve this non-enumeration behavior.
- Existing Flutter navigation is `今日 / 首页 / 计划 / 我的`, not the target
  product information architecture containing Agent.
- Prompt injection, stale context, confirmation bypass, provider failure,
  idempotency, migration, account reset, and no-live-AI require explicit tests.

## Codex Corrections And Decisions

1. The preflight classified risk/plan validation as a possible read Tool. The
   accepted architecture does not expose it to the model; classification and
   validation are mandatory server wrappers.
2. The preflight treated automatic execution of feedback/substitution as open.
   Phase 5 requires explicit confirmation for every Agent-initiated write.
3. The preflight proposed audit/proposal persistence but did not treat general
   cloud-model processing consent as a hard blocker. Current
   `ActorContext.consent_record` is always `None`; Phase 5 therefore adds a
   separate fail-closed Agent cloud consent/privacy gate.
4. Phase 5 uses the narrow same-day interpretation: existing substitution and
   feedback only. Phase 7 scope is not pulled forward.
5. The four main destinations become `今日 / 计划 / Agent / 我的`; the existing
   posture home is preserved as a secondary route.
6. Provider output is restricted to typed intent/Tool/message codes. Every
   user-visible string is server-rendered; Phase 5 does not display free model
   prose.
7. Context/request/argument fingerprints use a dedicated HMAC key because plain
   hashes of low-entropy health values are enumerable.
8. Existing health/training writes commit internally. Agent confirmation must
   first extract shared transaction-neutral operations so domain write,
   idempotency, proposal status and audit cannot diverge.
9. Consent grant acknowledges the exact provider/disclosure shown to the user;
   a configuration race returns a stale error rather than granting unseen terms.
10. Existing safety-signal terms in raw user text are routed deterministically
    before provider execution. A model cannot ignore a newly reported symptom,
    and a non-match is not treated as safety clearance.

## Result

The preflight is accepted as discovery input, not as a specification or
implementation authorization. Current authority is:

- `docs/specs/agent/2026-07-28-agent-mvp.md`
- `docs/adr/0003-server-controlled-agent-tools.md`
- `docs/adr/0004-agent-consent-audit-and-memory.md`
- `docs/plans/agent/2026-07-28-agent-mvp.md`
