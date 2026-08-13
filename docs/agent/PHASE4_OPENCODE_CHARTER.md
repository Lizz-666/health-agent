# Phase 4 OpenCode Delegation Charter

> Date: 2026-07-27. This document is a coordination contract, not the Phase 4
> product specification. OpenCode must create the current specification and
> implementation plan before changing Phase 4 runtime behavior.

## 1. Experiment Model

Phase 4 is delegated to one OpenCode + selected Claude model session as a
full-phase implementation experiment. OpenCode owns specification, planning,
implementation, tests, milestone commits, GitHub CI operation, Task-level
self-acceptance, fixes, and the final handoff report. Codex performs no routine
intermediate review and writes no Phase 4 implementation file until the full
handoff is ready.

Codex remains the final acceptance owner. OpenCode self-acceptance is a
candidate quality gate, not proof that the Phase or Task is `verified` under
`AGENTS.md`. Only Codex may record final Phase 4 verification, integration, and
the collaboration experiment assessment.

Use one implementation branch, one worktree, and one OpenCode session. Internal
Tasks are sequential milestones, not parallel writer assignments. Do not open
a second implementation session or modify another worktree.

## 2. Outcome And Fixed Boundaries

Deliver the roadmap Phase 4 outcome: a user can generate, review, confirm, and
execute a deterministic four-week posture-priority home-training plan, then
record one day's outcome and see plan/version rationale.

The following decisions are fixed:

- Phase 3 training catalog, safety context, candidate engine, policy, and
  validator are authoritative dependencies. Do not bypass, duplicate, or relax
  them.
- The server assembles current user context from authenticated, ownership-
  filtered data. A client-supplied user ID, risk decision, candidate set,
  version fingerprint, or authorization claim is untrusted.
- Re-run current risk classification before generation, confirmation,
  substitution, and any same-day adjustment. Restricted cases do not receive
  an ordinary plan. Red flags stop the relevant execution path.
- The deterministic engine must produce a complete executable baseline without
  an LLM. Phase 4 does not need a new AI provider or live-model call. Adding one
  is out of scope unless separately approved.
- Generation and confirmation are separate. A draft has no execution effect;
  only an explicitly confirmed, revalidated draft can become active.
- Generation, confirmation, replacement, and feedback writes are atomic and
  idempotent where retries can occur. Failure must not create a partially active
  plan or silently convert to a normal/healthy outcome.
- Preserve immutable plan versions, source/catalog/policy/profile/context
  fingerprints, structured change reasons, and ownership. Do not overwrite an
  active historical version in place.
- Plan exercises must be recommendation-ready Phase 3 catalog items and remain
  within deterministic prescription, volume, recovery, ordering, equipment,
  schedule, and contraindication constraints.
- Tests, CI, screenshots, reports, and fixtures use synthetic data only. Do not
  use real health data, real photos, production secrets, or live AI calls.
- Use only project-authored or separately verified/licensed media. Do not copy
  workout.cool code, UI, text, or media; its pinned model is structural design
  comparison only.
- Keep the product within general wellness and ordinary home fitness. Do not
  add diagnosis, treatment, rehabilitation, disease-specific planning,
  pregnancy/underage ordinary planning, nutrition, chat Agent, payment,
  rankings, video tracking, or gym-machine scope.
- Long-term adaptive progression, weekly review, and automatic multi-day plan
  restructuring belong to Phase 7. Phase 4 may record feedback and apply only
  the explicitly specified conservative same-day behavior.

Any new health threshold or safety rule requires a current authoritative
primary source, applicability statement, version/date, and versioned policy
representation. Do not invent thresholds from model memory. If alternatives
would materially change product or safety behavior, stop that dependent work
and report the decision needed; continue independent work where safe.

## 3. Required Milestones

OpenCode may refine filenames and split a milestone for implementation clarity,
but it must preserve this dependency order and acceptance surface.

### Task 0: Repository Audit, Specification, ADRs, And Plan

Inspect repository truth and write a current Phase 4 specification and
implementation plan under `docs/specs/training/` and `docs/plans/training/`.
Add ADRs for persistence/state ownership or other costly cross-module choices.
The specification must include the roadmap workout.cool comparison matrix,
domain/state model, API contracts, deterministic generation behavior, failure
semantics, auth/ownership, idempotency, migrations, Flutter flow, observability,
rollback, and executable acceptance matrix.

Self-accept only after a contradiction/placeholder/scope review and
`git diff --check`. Commit the milestone, push it, and create a draft PR against
`codex/phase3-spec-plan`. The draft PR is the CI surface for all later Tasks.

### Task 1: Phase 4 Verification Matrix

Extend the shared verification runner and existing workflow rather than
copying a second workflow. Fast CI must include relevant backend checks plus
Flutter analyze and targeted Phase 4 tests once present. Full CI must include
the complete backend suite, PostgreSQL 16 migration/integration evidence,
complete Flutter tests, Phase 4 safety/E2E cases, and machine-readable concise
summaries. Preserve pinned Actions, least permissions, cancellation, timeouts,
synthetic data, and fail-closed evidence handling.

Self-accept with local runner tests and a successful Fast and Full GitHub CI run
for the exact Task commit.

### Task 2: Plan Domain, State Machine, Persistence, And Migrations

Implement typed plan, week, session, prescription, version, confirmation, and
execution/feedback ownership. Define legal transitions and database constraints
for draft, active, superseded/cancelled states as selected by the specification.
Provide upgrade/downgrade or a documented safe recovery path, authorization,
and transaction/idempotency tests on SQLite where valid and PostgreSQL 16.

Self-accept only after focused local tests, migration rehearsal, Fast CI, and
Full CI succeed for the exact Task commit.

### Task 3: Deterministic Four-Week Generator

Generate a complete structured baseline for supported posture-priority,
fat-loss, and basic muscle-shaping goals using confirmed posture goals,
frequency, duration, available equipment, current profile/check-in, and Phase 3
policy. Include four-week/week/session structure, prescriptions, rest,
progression/recovery rules, alternatives, traceability, and stable rationale
codes. Validate every generated draft with the Phase 3 deterministic validator
before persistence or presentation.

Cover normal, caution, missing-data, restricted, red-flag, stale-context,
conflicting-goal, equipment, schedule, recovery, and provider-independent
cases. Self-accept with focused/property/scenario tests plus Fast and Full CI.

### Task 4: Authenticated Product API And Application Services

Add narrow authenticated APIs for draft generation, draft retrieval, explicit
confirmation/activation, active plan/today retrieval, allowed substitution or
same-day action, and daily execution feedback. Exact endpoints come from the
approved Task 0 specification. Enforce server-side identity, ownership,
idempotency, stale-version rejection, current safety rechecks, stable error
contracts, atomic state changes, and no cross-account leakage.

Verify OpenAPI, serialization, invalid input, auth isolation, retries,
concurrent/stale confirmation, service failure, and rollback behavior. Run Fast
and Full CI on the Task commit.

### Task 5: Flutter Contracts And State

Implement typed Flutter models, API client/provider state, account/session
reset behavior, loading/error/retry handling, and stale response protection for
the Phase 4 APIs. Do not place recommendation or safety logic in Flutter.

Self-accept with model/provider tests, Flutter analyze, targeted Flutter tests,
backend contract checks, and green Fast/Full CI.

### Task 6: Flutter Plan And Daily Execution Flow

Implement the user flow from the posture result or an explicit button through
goal/schedule selection, draft review, explicit confirmation, active plan,
today's exercise prescriptions, original/approved illustrations, steps, reps or
duration, rest, alternatives, version/change reason, and feedback states:
completed, partially completed, too busy, intentional rest, and physical
discomfort.

UI must expose blocked/restricted/red-flag/unavailable/stale states without
pretending success. Add widget/behavior tests and perform an Android target
smoke when the local toolchain supports it; report an unavailable device check
honestly rather than marking it passed. Run Fast and Full CI.

### Task 7: Full-Phase Self-Acceptance And Handoff

Run the complete local and remote verification matrix on the final SHA. Add a
synthetic Phase 4 E2E covering generation through one-day feedback, a safety
matrix, source/license/media audit, migration rehearsal, API/OpenAPI checks,
Flutter analyze/tests, and the manual Android flow where available. Reconcile
specification, plan, roadmap, and task ledger with actual behavior.

Write `docs/reports/phase4-opencode-handoff-2026-07-27.md`. Mark the Phase 4
candidate as `review`, not `verified`, `complete`, or `merged`.

## 4. Task Self-Acceptance Protocol

For every Task:

1. Re-read the current Task contract and inspect the affected code and diff.
2. Add failing behavior tests first for deterministic rules, state transitions,
   bugs, migrations, and safety paths.
3. Implement one coherent milestone without unrelated refactors.
4. Run focused local checks, lint/analyze as applicable, and
   `git diff --check`.
5. Review specification compliance, then engineering/security/privacy quality.
6. Fix every discovered P0/P1/P2 issue before committing. Record P3 items.
7. Create one or a small number of cohesive local commits for the Task.
8. Push the branch and wait for GitHub CI without high-frequency polling. Read
   only the failing job's relevant log when diagnosis is needed.
9. If any required check fails, diagnose, add a regression test where useful,
   fix, recommit, push, and obtain green checks on the new exact SHA.
10. Record local commands, exit codes, test counts, commit SHA, CI run URLs/job
    results, findings/fixes, and residual risks before continuing.

A Task is internally accepted only when its required local checks and exact-SHA
CI checks are green and no known P0/P1/P2 remains. Rebase, conflict resolution,
migration/schema/policy changes, or any substantive later edit invalidates
affected evidence and requires rerunning it.

## 5. GitHub And Git Permissions

For this Phase 4 experiment, OpenCode is explicitly authorized to:

- commit only on `codex/phase4-opencode-implementation`;
- push that branch to `origin`;
- create and update one draft PR targeting `codex/phase3-spec-plan`;
- read Actions status and failure logs;
- rerun a failed workflow when the failure is demonstrably transient and no
  code/configuration defect is being hidden.

OpenCode is not authorized to force-push, rebase, merge, mark the PR ready,
merge the PR, write `main`, change repository settings/secrets, deploy, publish,
contact third parties, or incur external cost. Do not commit `.env`, credentials,
local databases, logs, real photos/health data, or unrelated generated files.

## 6. Final Handoff Contract

The final OpenCode report must include:

- exact base SHA, final HEAD SHA, branch, worktree, and draft PR URL;
- milestone commit table and changed-file ownership by Task;
- actual behavior and explicit non-goals;
- migrations and rollback/recovery notes;
- safety, privacy, authorization, idempotency, and failure-path evidence;
- every local command with workdir, exit code, and key counts;
- every required GitHub CI run URL, tested SHA, jobs, and conclusions;
- self-review findings and fixes, including whether first-pass Task acceptance
  failed before correction;
- Android/manual evidence or an explicit not-run reason;
- source/license/media audit, unexpected generated files, `git diff --stat`,
  and residual P3 risks;
- a statement that no real health data, photo, production credential, or live
  AI call was used.

After this handoff, stop. Codex will inspect the complete base-to-head diff and
commit series, run independent acceptance and cold review, decide fixes or
return findings, and publish the final experiment comparison.
