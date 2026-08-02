# Phase 7 Adaptive Closure And Weekly Review

> Status: accepted at Phase 7 Gate 0, 2026-08-02. Contract SHA
> `dceceb7dcd7955359e91939853c5290be799c277` passed exact-SHA local Fast and
> Flutter verification plus GitHub Fast/Flutter/Full run `30732748723`. The
> audit is `docs/reports/phase7-gate0-review-2026-08-02.md`; implementation must
> start from the later Gate 0 metadata closure SHA, not this candidate directly.
> The original exact baseline is Phase 6 closure
> `8eeb28a3a4156eaac5763260129fdde6fedee835`.
> This specification authorizes synthetic-data development only. It does not
> authorize deployment, real health data or photos in development tools, live
> provider calls in tests, or any medical/rehabilitation behavior.

## Outcome

A supported adult with an active four-week training plan can ask the foreground
product flow to conservatively adapt today's session when available time or
recovery state changes. The user can later inspect an immutable weekly review
that combines execution, check-in, adjustment, weight-trend context, nutrition
recommendation state, and posture-recheck state without pretending that a
screening signal or scale trend is a diagnosis.

Same-day overlays keep the confirmed plan immutable. Long-term changes create
review proposals and, only after a separate user action, new training or
nutrition drafts. Existing confirmation flows remain the only activation path.

## Non-Goals

- No background autonomy, scheduler, push notification, OS alarm, wearable,
  calendar, email, SMS, or server job.
- No medical diagnosis, treatment, rehabilitation, injury recovery protocol,
  disease-specific training/nutrition, or professional-clearance workflow.
- No new clinical threshold, pain rule, contraindication, exercise, nutrition
  formula, food target, or model-authored safety policy.
- No automatic plan activation, nutrition activation, fitness-goal mutation,
  profile mutation, safety-signal resolution, or posture-result mutation.
- No using weight change to select training load, progression, regression,
  frequency, duration, exercise, or recovery behavior.
- No inferred meal intake, nutrition adherence, calorie consumption, body-shape
  score, posture diagnosis, or comparison of raw posture photos.
- No arbitrary Agent database access, model-selected permissions, free-text
  safety classification, or unconfirmed Agent write.

## Approved Gate 0 Decisions

1. **Foreground button auto-application is bounded.** A dedicated button may
   request one deterministic same-day adjustment. The server rebuilds owned
   current context, reruns the safety gate, computes the result, and applies the
   overlay atomically without a second confirmation dialog. Merely opening a
   screen, saving a check-in, receiving an Agent response, or running in the
   background never applies an adjustment.
2. **Agent writes remain proposal plus confirmation.** Agent may explain or
   create a typed short-lived proposal. A separate authenticated confirmation
   reruns current context and invokes the same domain command as the button.
3. **Long-term change is draft-only.** A weekly review can recommend keeping the
   plan or creating a new training draft and can optionally recommend refreshing
   a nutrition draft. Neither draft is activated by review generation, Agent
   text, or draft creation. Existing dedicated confirmation gates apply.
4. **Weight is explanation and nutrition-refresh context only.** Weight trend
   can explain why a nutrition refresh may be useful. It never changes training
   adjustment or progression logic. A nutrition draft still uses the approved
   Phase 6 latest-owned-weight contract and formulas, not a trend-derived target.
5. **Posture reminder is in-app state.** Phase 7 has no notification
   infrastructure. A recheck becomes due at completion of a four-week plan cycle
   when a pre-cycle owned posture assessment exists. It can be dismissed for
   that cycle. Safety messages are not ordinary reminders and cannot be hidden
   by this dismissal.
6. **No new health threshold is introduced.** Phase 7 routes existing structured
   enums and existing versioned training safety results. `available_time`,
   `energy`, `muscle_soreness`, `daily_status`, abnormal-pain follow-ups, risk
   tier, exercise recovery bounds, and plan validation keep their current
   meanings. Subjective category routing is product policy, not a clinical
   claim.

## Users And Scenarios

| Scenario | Deterministic behavior |
| --- | --- |
| Planned session, less available time | Apply a shortened overlay only when the versioned adjustment policy can preserve required items and validation passes; otherwise offer legal deferral or a bounded no-adjustment state. |
| Planned session, low energy or significant soreness, no pain signal | Apply a recovery-session overlay selected from already reviewed catalog items and independently validate it. |
| User selected active rest | Defer to the next legal unoccupied date in the current plan window when recovery constraints remain valid; otherwise record active rest without stacking the session. |
| No available time | Prefer legal deferral; if none exists, return active rest and leave the missed session unstacked. |
| Abnormal pain, restricted, urgent/red flag, missing current safety input | Do not shorten, defer, or substitute to bypass the state. Return the existing fail-closed safety behavior. |
| Repeated misses | Weekly review summarizes them and may propose a conservative new draft; missed sessions are never copied into a backlog. |
| End of a plan week | Return an immutable review snapshot based on owned structured records and explicit unavailable states. |
| End of the four-week cycle | Include an in-app posture recheck due state when a comparable pre-cycle assessment exists. |

## Inputs And Ownership

Every adjustment command, review snapshot, draft materialization, Agent
confirmation, and review read is authenticated. `user_id`, current local date,
active versions, assessment ownership, and current records are server-derived.

Required adjustment inputs:

- a validated IANA timezone and server-derived local date;
- the current owned active plan and today's effective source session;
- today's current owned structured check-in;
- current health profile, risk-screen, retained pain, posture context, equipment,
  catalog, source manifest, training policy, and training safety policy;
- current execution overlays and feedback needed to avoid duplicate/stacked work.

The client sends only an adjustment intent, expected plan/session identifiers,
timezone, and idempotency key. It cannot send risk tier, target date, replacement
exercise, item priority, policy version, weight interpretation, or safety result.

Weekly review inputs are structured and minimal: plan/week identity, effective
session counts, feedback outcome codes, adjustment kinds, daily engagement
states, check-in risk categories, weight-trend availability/direction generated
by the existing descriptive trend service, current nutrition recommendation
version/state, and owned posture assessment summary identifiers/timestamps. Raw
notes, pain text, body values, chat text, photos, provider payloads, and full
assessment payloads are excluded from review persistence and ordinary logs.

## Deterministic Same-Day Contract

### Decision precedence

```text
red_flag or urgent
  > restricted
  > missing_or_stale_context
  > pain_or_existing_safety_block
  > recovery_overlay
  > shortened_overlay
  > deferred_overlay
  > unchanged
```

The exact adaptation mapping lives in a new versioned product policy. Version 1
uses only existing categorical inputs:

- `abnormal_pain=true`, a retained pain gate, restricted/urgent state, or an
  existing blocked training decision never enters ordinary adjustment.
- `energy=low` or `muscle_soreness=significant`, with no higher safety state,
  selects the recovery candidate path.
- `available_time=15_min` or `30_min` may shorten a longer planned session to
  that existing duration bucket. `45_min_plus` does not shorten a 45-minute
  session; it is insufficient for a 60-minute session only if policy can produce
  a validated 45-minute overlay.
- `available_time=none` or `daily_status=active_rest` selects deferral, then
  bounded active rest when no legal date exists.
- ordinary `ok`/`good`, `normal`/`high`, `none`/`mild`, and sufficient time do
  not invent a need to adjust.

Shortening removes only policy-ranked lower-priority prescriptions and never
edits prescription values in place. Version 1 must preserve a reviewed warm-up,
at least one goal/posture-priority prescription, exercise stop conditions, and
all validator/recovery limits. If those invariants do not fit the requested
duration bucket, shortening fails closed.

Recovery substitution builds a complete effective-session snapshot from catalog
items already marked for recovery/mobility/warm-up roles and eligible under the
latest candidate and safety engines. It is wellness active recovery, not injury
treatment. It cannot run when abnormal pain or a higher safety state exists.

Deferral chooses the earliest future unoccupied local date inside the active
four-week plan window for which both neighboring effective sessions satisfy the
existing exercise recovery bounds and weekly-frequency/load validators. It does
not cross the plan end, displace another session, move more than one source
session to a date, or chain-defer an already deferred session. No legal slot
means `active_rest_no_legal_deferral`; the session is not accumulated.

Every effective Today response reruns current safety. A stored overlay whose
context fingerprint no longer matches is history, not authorization. The server
returns stale/blocked and requires a fresh command; a new urgent or restricted
signal immediately blocks execution.

## Domain Model And State

### Same-day adjustment versions

`training_day_adjustments` is an append-only decision-version table. Each row
owns a user, active plan, source session/date, optional target date, adjustment
kind (`shortened`, `recovery`, `deferred`, `active_rest`), structured trigger and
reason codes, context/decision fingerprints, policy/catalog/source versions,
surface (`button` or `agent_confirmation`), and timestamps. It stores no prose.

`training_day_adjustment_items` stores the typed effective delta/snapshot:
source prescription, action (`keep`, `drop`, `replace`), effective reviewed
exercise and bounded prescription values, and display order. Deferral and active
rest need no item rows. A uniqueness key over the owned source, date, context
fingerprint, policy version, and command kind plus reviewed idempotency prevents
duplicate application. The newest row matching current context is effective;
older rows remain immutable audit history.

The plan version and its sessions/prescriptions are never rewritten. Existing
feedback and user-initiated substitution rows remain historical contracts. The
resolver applies a current user substitution before a shortened overlay only
when the affected prescription is retained and still validates; a recovery
overlay replaces the whole effective session and cannot combine with a separate
same-day substitution. Any other collision fails closed instead of guessing.

### Weekly review snapshots

`training_weekly_reviews` is append-only. It contains owner, plan/week,
review-version, input fingerprint, period dates, structured counts/states,
bounded trend codes, proposal codes, source-version pins, and timestamps. A
unique `(plan_version_id, week_index, input_fingerprint)` makes replay stable.
Changed historical inputs create a new review version; they do not mutate a
snapshot.

Review proposal outcomes are typed:

- `keep_current_plan`;
- `offer_training_draft` with bounded strategy codes for conservative duration,
  frequency, progression, or regression;
- `offer_nutrition_refresh` only as a separate optional action;
- `posture_recheck_due`, `posture_comparison_available`, or an explicit
  unavailable reason.

Creating a training draft records `origin_weekly_review_id` on the immutable
plan version. Creating a nutrition draft records the same origin on the
immutable nutrition recommendation version. Review proposal, draft, and active
version remain distinct states.

`posture_recheck_dismissals` is an append-only per-owner/per-plan-cycle ordinary
reminder event. It never hides safety or red-flag UI. Posture comparison is
derived from the latest owned completed structured assessment at or before plan
confirmation and the first owned completed assessment after cycle end. It
reports signal `added`, `not_detected`, `unchanged`, or `changed` states with
source/timestamp labels. It does not compare raw photos or claim clinical
improvement. Missing either anchor produces an explicit unavailable state.

## API And State Contracts

All mutation endpoints require an idempotency key and strict schemas. Conflict,
stale context, ownership failure, and safety failure have distinct stable error
codes and never return a successful adjustment/draft reference.

```text
POST /api/v1/training/today/adjustments
GET  /api/v1/training/today
GET  /api/v1/training/reviews/weeks/{week_index}
POST /api/v1/training/reviews/weeks/{week_index}
POST /api/v1/training/reviews/weeks/{week_index}/training-drafts
POST /api/v1/training/reviews/weeks/{week_index}/nutrition-drafts
POST /api/v1/training/reviews/weeks/{week_index}/posture-recheck-dismissals
```

The review GET is read-only and returns the latest owned snapshot or
`review_not_generated`. The explicit POST may deterministically create/replay an
immutable snapshot only after the requested plan week has ended in server-
derived local time. Before then it returns `review_not_due`. Draft endpoints
require the expected review ID/fingerprint and rerun all current domain safety/
eligibility gates. A changed input returns stale and produces no draft.

Today returns original session identity, effective state, optional matching
adjustment ID/kind, effective prescriptions, target/source date for deferral,
reason codes, and a safety status. It never treats a stale overlay as executable.

## Weekly Review Rules

The review is deterministic and works without AI. It reports facts before
proposals:

- scheduled/effective/completed/partial/too-busy/intentional-rest/discomfort
  counts, with active-rest and safety-adjustment kept as valid non-failure
  engagement states;
- adjustment counts by kind and explicit missing/unavailable states;
- execution trend across completed plan weeks without treating no-data as zero;
- descriptive weight trend from the existing health service, labeled unavailable
  when its current minimum-data contract is not met;
- active nutrition recommendation age/state and whether a fresh nutrition draft
  can be requested under Phase 6 safety, without inferring intake;
- posture recheck due/comparison state.

No single missed session, one-day weight value, or wording from Agent produces a
long-term change. Version 1 applies these product-policy mappings, which are
proposal eligibility rules rather than clinical thresholds:

- any discomfort, abnormal-pain, restricted, urgent/red-flag, missing-safety, or
  current safety-block state suppresses ordinary progression/regression options
  and returns the existing safety/clarification path;
- two or more `too_busy`, `intentional_rest`, `active_rest`, or deferred outcomes
  in one ended week may offer a shorter-duration or lower-frequency draft, never
  a higher-load draft;
- two or more recovery overlays in one ended week may offer a conservative
  duration/regression draft within existing catalog relations and validator
  bounds;
- one partial or missed outcome suppresses progression. Progression may be
  offered only after the complete four-week cycle when every planned effective
  session is `completed`, no recovery/safety overlay or significant-soreness/
  low-energy check-in occurred, and the existing progression relation and all
  recovery/load validators pass;
- fitness-goal change is never inferred. At cycle end the review may offer a
  neutral `revisit_goal` action; only the user can choose a goal through the
  existing draft request contract;
- nutrition refresh is offered only when no active recommendation exists or its
  pinned authoritative weight record/training-plan version differs from current
  owned context. Trend direction may be displayed beside that offer but does not
  cause it and does not alter the Phase 6 calculation;
- otherwise the result is `keep_current_plan` or explicit insufficient data.

Counts include only scheduled effective sessions in the ended review period;
missing records are unavailable, not misses. Every mapping is versioned and
tested. A proposal that would relax existing safety, recovery, or load limits is
invalid. Weight, nutrition state, posture comparison, and Agent text are absent
from the training mapping input schema.

## Agent Contract

Agent receives narrow read tools for current adjustment availability and weekly
review summary. It may propose `generate_weekly_review`,
`apply_today_adjustment`,
`create_review_training_draft`, `create_review_nutrition_draft`, or
`dismiss_posture_recheck`. Every action uses the existing persisted proposal,
explicit confirmation, consent, authorization, fingerprint, audit, timeout, and
idempotency machinery. The model cannot select target dates, exercises, load,
policy values, or safety outcomes.

Provider unavailable, invalid tool output, prompt injection, stale proposal, or
failed confirmation returns an explicit unavailable/failure result. It never
falls back to an unreviewed write or labels the user safe.

## Safety, Privacy, And Failure Handling

- Every generation, application, review draft creation, and Agent confirmation
  rebuilds latest owned context and runs the authoritative domain gates.
- Red flags stop relevant execution. Shortening, deferral, recovery substitution,
  active rest, and review cannot downgrade or acknowledge away a safety state.
- Unknown enum, missing source, unsupported plan week, ambiguous overlay,
  policy/catalog mismatch, stale fingerprint, or validator failure is fail-closed.
- AI is optional explanation only. Structured review and all actions work with
  provider disabled.
- Logs/audits use IDs, versions, outcome/reason codes, latency, and fingerprints;
  no notes, raw body values, pain details, photos, meals, or chat text.
- Account deletion and domain deletion must remove Phase 7 owned rows and their
  explicit Agent proposal/audit references in dependency order.

## Observability And Audit

Record adjustment/review operation name, owner-scoped entity IDs, source/version
pins, input/decision fingerprints, result/error code, surface, idempotent replay,
and duration. Metrics may count result codes but must not label individual health
states or include raw sensitive fields. A stored result reference is considered
successful only when the referenced owned row exists and matches the operation.

## Acceptance Criteria

- Busy, fatigue/recovery, missed/no-time, intentional-rest, pain, restricted,
  red-flag, missing-input, stale-context, and duplicate-request cases each have a
  typed deterministic outcome.
- Same-day overlays preserve immutable plan rows, current recovery/load limits,
  authorization, and one effective execution timeline without task stacking.
- A new safety signal blocks a previously stored overlay immediately.
- Button flow is foreground and direct; Agent flow always requires explicit
  confirmation; no background action exists.
- Weekly review facts are reproducible from synthetic structured records, no-data
  is explicit, and weight never enters a training decision.
- Training/nutrition long-term changes create drafts only and require existing
  activation confirmation afterward.
- Posture recheck is an in-app per-cycle state; comparison uses structured owned
  summaries and no raw photos or diagnostic language.
- Migration upgrade/downgrade, constraints, concurrency, replay, fault injection,
  ownership, deletion, SQLite, and disposable PostgreSQL parity pass.
- Flutter shows reasons, effective-versus-original differences, history, review,
  draft boundaries, unavailable states, and safety blocks on phone layouts.
- Full backend, Flutter, Android synthetic smoke, and exact-SHA CI are green with
  zero unexpected skips.

## Test And Evaluation Strategy

Use synthetic data only. Add pure policy/property tests, service/API tests,
migration parity tests, concurrency/idempotency tests, Agent schema/permission/
adversarial tests, Flutter model/provider/widget tests, and a final Android smoke
matrix. Assertions target structured state and invariants, not generated prose.

Gate evidence is invalid after a material change, rebase, conflict resolution,
migration edit, or policy edit. Every Gate records exact SHA, commands, exit
status/counts, and GitHub Fast/Flutter/Full results as applicable.

## Rollout And Rollback

The feature remains behind the existing personal-development environment and
provider controls. Schema upgrade is additive. Application rollback ignores the
new tables/nullable origin columns; migration downgrade is rehearsed only on a
disposable database because it deletes Phase 7 history. No production migration,
deployment, or real-data rollback is authorized by this specification.
