# Phase 8 Gate 0 Codex Review

> Date: 2026-08-09. Baseline:
> `36be9a0f0cd989f32c8f4f7f7b9e2bc5fb4c66e6`. Locally reviewed contract
> candidate: `02229fa566d5765d75ef45a379b6800fef84ae53`. This report covers
> documentation and planning only; no Phase 8 business code was written.

## Result

Local Gate 0 candidate review: **PASS, pending exact-SHA GitHub CI**.

There are no unresolved P0, P1, or P2 findings in the Gate 0 contract. The
candidate does not authorize merge, deployment, `main`, real health data or
photos, production credentials, live-provider acceptance, or public release.

## Findings First

### Baseline P1 gaps assigned to implementation Gates

1. Existing Android integration tests inject `FakeDio` and therefore are not
   real transport/backend acceptance evidence. Gate 2 freezes a real HTTP
   contract; Gate 3 adds the real-app Android driver; Gate 4 owns final replay.
2. Internal `account_deletion` does not currently include base health/training
   or nutrition rows despite its broad name. Gate 1 assigns the complete
   cross-domain privacy contract and PostgreSQL verification to Codex only.

These are explicit planned implementation findings, not accepted residual
risks and not claims that the current code already satisfies Phase 8.

### Gate 0 P2 findings closed before candidate commit

1. The first checkpoint draft coupled a week-one review to a posture-recheck
   state. Existing Phase 7 policy makes the recheck due only at the end of the
   four-week cycle. The checkpoint is now `cycle_due` and requires a week-four
   review plus end-of-cycle recheck state.
2. The first delegation draft deferred the Flutter allowlist to a later prompt.
   The plan now fixes the exact six existing screens, one new integration test,
   and three focused test files; all other existing UI anchors are frozen and
   must be consumed rather than renamed.

### Gate 0 P3 process finding closed

- Initial staged diff check found one blank line at the end of ADR-0008. It was
  removed and the staged diff check passed before commit.

## Contract Review

- Product defaults match the user decisions: illustrated self-test, scripted
  provider, Android emulator, bounded offline/retry, and full synthetic reset.
- ADR-0008 keeps the acceptance application and destructive control plane under
  test-only assembly. Production has no flag or request path that can select it.
- Disposable DB reset and production account deletion are explicitly different.
  Phase 8 does not invent a public identity-deletion/token-revocation claim.
- Named checkpoints can install elapsed-time prerequisites but cannot perform a
  core accepted UI mutation. Fixture builders use validated domain operations.
- Existing deterministic health/safety policy remains authoritative; no new
  threshold, diagnosis, treatment, rehabilitation, or Agent permission is added.
- Failure states cannot become normal/active/success, and live-provider/photo
  execution remains outside the hard gate.
- Task ownership follows one-writer governance. Privacy, state, cross-domain,
  CI, and final E2E stay with Codex; OpenCode is deferred until Gate 2 exact-SHA
  contract freeze.

## Local Exact-SHA Evidence

All accepted local commands below ran on clean candidate
`02229fa566d5765d75ef45a379b6800fef84ae53`:

| Command | Result |
| --- | --- |
| `python scripts/verify.py fast` | exit 0; ruff clean; `927 passed / 0 failed / 19 expected PostgreSQL skips`; candidate diff clean |
| `flutter analyze` | exit 0; no issues |
| `flutter test` | exit 0; `472 passed / 0 failed` |
| `git diff --cached --check` before candidate commit | exit 0 |

An earlier parallel attempt was terminated by an outer 184-second timeout. Its
pytest child continued temporarily, so a second overlapping attempt failed with
SQLite `table ... already exists` setup errors (`807 passed`, `22 failed`, `149
errors`, `17 skipped`). Codex did not count or suppress that run: the orphaned
process was allowed to exit, the exact workspace `backend/test.db` was removed,
Flutter-generated registrants were restored, and the suite was rerun alone to
the clean result above. No business file was changed to make tests pass.

## Pending Remote Gate

The candidate report/metadata commit will be pushed to the named Phase 8 branch
and run through exact-SHA GitHub Fast, Flutter, and strict Full. Full must report
zero skips and PostgreSQL expected/actual parity. A later closure metadata commit
must itself receive exact-SHA CI before Gate 0 becomes `committed` and the Gate 1
implementation worktree is created.

No OpenCode prompt is authorized at Gate 0. The only delegated Task begins after
Gate 2 freezes its backend/control contracts.
