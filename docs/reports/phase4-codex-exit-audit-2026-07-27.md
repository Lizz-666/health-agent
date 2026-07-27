# Phase 4 Codex Exit Audit

> Date: 2026-07-27. Scope: independent review of OpenCode handoff
> `2a409e8`, corrective implementation `c308189`, and final exact-SHA CI.
> This is engineering acceptance for personal development, not clinical or
> public-release approval.

## Decision

Status: **review - remote CI pending**.

The OpenCode handoff was not acceptable as delivered. Codex found blocking
cross-layer correctness and safety gaps, added failing regression tests, fixed
them on an independent worktree, and reran the risk-matched local matrix. No
P0/P1/P2 finding remains in the reviewed content. Final `verified` status still
requires Fast, Flutter, and Full GitHub CI to pass on the exact final report SHA.

## Findings Closed

1. Today selection ignored `week_index` and always returned week 1. It now
   derives the current week from confirmation time plus server UTC/IANA local
   date, advances through weeks 1-4, and returns `plan_complete` afterward.
2. Feedback and substitution accepted any active-plan session and used UTC
   dates. They now require a validated IANA timezone and only accept the actual
   local-day session.
3. Today only checked the broad safety gate. It now validates the current
   effective plan, including same-day substitution, against the latest context,
   candidate set, catalog, and policy before exposing executable prescriptions.
4. Substitution used a reversed/static relation check and skipped current
   candidate and whole-plan validation. It now requires the original prescribed
   exercise's substitution relation, current candidate eligibility, and a clean
   deterministic validator result.
5. Confirmation skipped stored-draft validation. It now reconstructs and
   validates the persisted typed draft before activation.
6. Generate returned the newest pending draft on an old-key replay; request
   hashes omitted material fields; preconditions ran before replay. All four
   write paths now use complete hashes and replay the recorded owned result
   before mutable safety/day preconditions.
7. Session duration accepted arbitrary values and had no generation effect.
   The API now permits only 15/30/45/60, applies a duration-based exercise cap,
   and persists `target_minutes`.
8. Flutter could generate from fabricated defaults that differed from the
   health profile. It now loads the current structured profile, uses only its
   supported complete values, and blocks generation when required data or
   equipment is missing.
9. The Flutter flow did not render catalog illustrations or expose
   substitution; recorded feedback/substitution was not reflected in today.
   Existing project-authored SVGs are now packaged and rendered, safe
   alternatives are actionable, and effective execution state is returned and
   displayed.

## Verification

| Command | Workdir | Result |
| --- | --- | --- |
| `python scripts/verify.py fast` | repo root | pass; ruff clean; backend targeted suite green |
| `$env:GITHUB_TOKEN=(gh auth token); $env:VERIFY_REQUIRE_PG='1'; python scripts/verify.py full` | repo root | **1074 passed, 0 failed, 0 skipped**; PostgreSQL **18/18** |
| `flutter analyze` | `app` | no issues |
| `flutter test` | `app` | **322 passed** |
| SVG hash comparison | repo root | all **24/24** packaged files equal the existing project assets |
| `git diff --cached --check` before `c308189` | repo root | no whitespace errors; Windows LF/CRLF notices only |

The first no-token local full attempt after the final safety change had no test
failure but skipped nine GitHub API action-pin checks; `VERIFY_REQUIRE_PG=1`
correctly rejected any skip. Supplying the existing `gh` token in process made
those checks run and produced the zero-skip result above. No credential was
written to disk or printed.

## Residual P3 Risk

- `basic_strength` frequency 4-5 still fail-closes because the current catalog
  cannot satisfy recovery constraints.
- The client currently identifies substitution choices by stable exercise ID;
  richer alternative display metadata is a usability improvement, not a safety
  bypass.
- A manual Android end-to-end business replay was not repeated after the Codex
  fixes. Widget tests cover the changed flow; the OpenCode handoff's prior APK
  build/install/launch evidence is not treated as proof of the corrected flow.
- The caller supplies a validated IANA timezone per request; persistent account
  timezone management remains outside Phase 4.

## Delegation Experiment

Whole-phase OpenCode delegation was useful for implementation throughput,
milestone commits, CI operation, and broad test construction. It reduced Codex
involvement during the coding phase and produced a coherent branch rather than
multiple conflicting writers.

It did not preserve first-pass acceptance quality for cross-layer contracts.
The delayed review allowed week progression, replay semantics, current-plan
validation, substitution safety, profile/request equality, and Flutter execution
state to fail together across backend and client. The final correction was a
substantial 42-file commit, not a minor polish pass. Green self-authored tests
and per-task CI therefore did not substitute for an independent reviewer.

Recommended operating model:

1. Codex owns product scope, architecture, safety/privacy contracts, task
   boundaries, and final acceptance.
2. OpenCode remains the primary implementation and CI operator for bounded
   tasks or a sequential phase branch.
3. Codex reviews at four risk gates: specification; persistence/migration;
   authenticated API and safety execution; final Flutter/E2E. It does not need
   to review every mechanical commit.
4. A gate failure stops downstream implementation until fixed and reverified.
5. Phase 5's runtime Agent is high risk and must not use blind whole-phase
   delegation; permissions, deterministic safety tools, prompt-injection
   boundaries, and failure semantics require early Codex ownership.

This hybrid keeps most of the token and concurrency benefit while moving defect
detection earlier, where fixes are smaller and evidence remains easier to trust.
