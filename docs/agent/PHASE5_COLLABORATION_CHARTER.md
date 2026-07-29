# Phase 5 Agent MVP Collaboration Charter

> Date: 2026-07-29. Status: Gate 2 accepted; Batch C (Task 4) is next but is
> not authorized until its explicit prompt is issued. Accepted Task 0 specification:
> `f6c2eae59c784398fbf1ae38967be3c2ee720940`. Accepted Gate 1 implementation:
> `3df574b7051ef9a9342816c9b116f436ddf8513c`. Accepted Gate 2 implementation:
> `57facf2a7e4589ef843645d7549b89538f1e79fe`.

## 1. Decision

Phase 5 uses a gated hybrid model. OpenCode remains the primary implementation
and CI operator, while Codex owns scope, architecture, safety/privacy contracts,
gate review, corrective integration, and final acceptance.

Phase 5 must not use blind whole-phase delegation. The Phase 4 experiment
delivered high implementation throughput, but its first complete handoff left
cross-layer safety and correctness defects that required a substantial Codex
repair. Runtime Agent permissions, prompt-injection boundaries, side effects,
and failure semantics need review before dependent layers accumulate.

## 2. Phase State And Base

- Phase 4 is `verified`, not `merged`. Draft PR #2 remains open.
- Phase 5 Task 0 passed independent re-review with P0/P1/P2/P3 all zero at the
  exact accepted specification SHA above.
- Runtime implementation must use a Phase 5 implementation branch created from
  the accepted Phase 5 Task 0 specification commit, not from `main` or the old
  root worktree.
- The Phase 5 PR may be stacked while PR #2 remains open, but final integration
  order is Phase 3 -> Phase 4 -> Phase 5. Evidence is rerun after any rebase,
  conflict resolution, or base change.

## 3. Roles

### Codex

- Write and approve the Phase 5 specification, threat model, ADRs, task plan,
  tool permission matrix, confirmation protocol, and failure semantics.
- Resolve product/safety scope before implementation, including the roadmap's
  `当日小调整` entry versus the Phase 4 deferral of automatic shortening,
  deferral, and recovery adjustment to Phase 7.
- Review real diffs and exact-SHA CI evidence at each risk gate.
- Fix or return P0/P1/P2 findings, then independently run risk-matched tests.
- Perform final Flutter/Android/E2E acceptance and update phase status.

### OpenCode + Selected Model

- The read-only preflight and Gate 0 review are complete.
- After Task 0 is approved, implement only the currently assigned batch on one
  Phase 5 implementation branch/worktree.
- Reuse existing domain services and typed Tools. Do not recreate training,
  posture, health, authorization, idempotency, or safety logic in the Agent.
- Commit by coherent Task, push the authorized implementation branch, operate
  its draft PR and CI, and stop at each Codex gate.
- Do not merge, force-push, write `main`, change repository settings/secrets,
  deploy, or use live health data or live model calls in tests.

## 4. Provisional Work Batches

The exact contracts and file boundaries come from Task 0. These batches are
coordination boundaries, not permission to implement from the roadmap alone.

| Batch | Provisional scope | Required gate |
| --- | --- | --- |
| Task 0 | Codex specification, threat model, ADRs, implementation plan, permission/confirmation matrix, eval plan | Gate 0: independent specification review before runtime code |
| A | Minimal Context Resolver; typed tool registry; read-only profile, posture, risk, active-plan and today adapters | Gate 1: context minimization, ownership, tool contracts, no duplicated domain logic |
| B | Audit persistence/migration; idempotent write adapters; explicit preview/confirm protocol for side effects | Gate 2: migration rehearsal, authorization, replay semantics, latest-data safety gate, rollback |
| C | Provider abstraction, structured orchestration, authenticated Agent API, failure handling, prompt-injection/adversarial tests | Gate 3: allowlist enforcement, bounded execution, no authority escalation, no failure-to-success path |
| D | Flutter Agent entry/chat flow, contextual action entry, diff/confirmation UI, full E2E/evals, Android smoke, handoff | Gate 4: full backend/PostgreSQL, Flutter, adversarial matrix, device flow, final Codex audit |

Only one OpenCode implementation session writes the Phase 5 branch at a time.
It may continue across batches, but a failed gate stops downstream work until
the reviewed SHA is fixed and reverified.

## 5. Non-Negotiable Runtime Boundaries

- Client input carries only an entry type and owned entity identifier; the
  server resolves identity, authorization, health state, and minimal context.
- The model never receives arbitrary database access, raw SQL, a caller-supplied
  `user_id`, or authority to choose its own Tool set.
- Tool inputs and outputs are typed. Server code enforces a fixed allowlist,
  ownership, current safety policy, idempotency, and explicit side effects.
- Risk classification and plan validation are mandatory server wrappers, not
  provider-visible Tools that the model can choose or omit.
- Every Agent-initiated write produces a short-lived typed proposal and requires
  a separate authenticated user confirmation; the model never executes a write.
- Long-term structural changes remain `proposal -> deterministic validation ->
  diff -> user confirmation -> execution`. The model cannot confirm for the
  user.
- The Agent may create a training draft only through the same Phase 4 service
  used by the button flow. It may not activate or rewrite a long-term plan
  through an alternative path.
- Complete chat transcripts are not long-term memory. Persist only approved
  structured state and privacy-minimized audit metadata defined by Task 0.
- A live cloud provider call additionally requires current server-side consent,
  provider/disclosure configuration, withdrawal/deletion paths, and a satisfied
  privacy gate. A feature switch alone is never authorization.
- Prompt text is not a safety policy. Prompt injection cannot change actor,
  permissions, safety gates, confirmation requirements, or tool schemas.
- Provider output contains typed intent/Tool/message codes only. All displayed
  prose is rendered from reviewed server templates; free model text is not shown.
- Provider timeout, malformed output, tool failure, stale context, or validation
  failure returns an explicit failure or safe deterministic baseline where the
  domain contract permits it. It never becomes `normal`, `healthy`, `success`,
  or an executed side effect.
- Tests, fixtures, screenshots, logs, CI, and model simulations use synthetic
  data only. No production credential or live AI call is allowed in CI.

## 6. CI And Evidence

- Every Task runs focused local tests before commit.
- OpenCode pushes the exact candidate SHA and reads the concise CI summary. It
  does not repeatedly poll full logs.
- Fast CI runs for each implementation Task. Flutter CI runs for client changes.
  Full PostgreSQL CI is mandatory at Gates 2-4 and after integration/base changes.
- Agent tests must use deterministic fake providers and include malformed model
  output, tool-call injection, cross-user IDs, replay, stale safety context,
  confirmation bypass, excessive tool loops, timeout, and partial failure.
- CI success is evidence for one exact SHA, not an acceptance decision. Codex
  independently reviews the diff and reruns the gate's critical checks.

## 7. Handoff Contract

At each gate OpenCode reports: base/head SHA, commits, changed files, contract
changes, local commands and exact results, CI run URLs and conclusions, audit
and migration evidence, remaining risks, unexpected generated files, and
`git diff --stat`. It then stops in `review` until Codex returns either
`accepted base for next batch` or concrete findings.
