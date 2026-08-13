# Phase 8 Gate 2 Codex Review

> Date: 2026-08-09. Gate 1 closure:
> `3de6d3f1b47b6403e321710b4216eeb81636aa6a`. Accepted implementation:
> `cedda243221f0b04ac44d5dda816559201c48103` on
> `codex/phase8-implementation`.

## Decision

Gate 2 review: **PASS**. Open P0/P1/P2/P3 findings: zero.

Gate 2 freezes the synthetic localhost HTTP/control contract, versioned
evaluation matrices, sanitized exact-SHA evidence, and non-live CI acceptance
surface for delegated Task 3. It does not authorize production deployment,
live AI, real health data, real photos, production credentials, PR merge, or
writing `main`.

## Findings First

The independent cold review ran six rounds over the real staged diff. It closed
one P1 and multiple P2 findings covering review-draft confirmation binding,
latest safety/stale reassembly, shared bounded-strategy mapping, eval timeout
and prompt-injection cases, active-plus-draft Flutter reachability, pipeline
failure propagation, clean-worktree evidence, loopback-only serving, and
process/database cleanup. Final review counts were P0/P1/P2/P3 all zero.

The first exact-SHA CI attempt, run `31314056750` on `6b5e8d8`, is retained only
as failure history. Fast exposed that its early verification-runner unit test
inherited `VERIFY_SUMMARY_FILE=fast-summary.txt`, wrote inside the worktree, and
correctly triggered the new clean-worktree evidence refusal. Fast and Full
summary outputs now use runner-temporary paths. A subsequent workflow parse
rejected `runner.temp` at job-level scope before any job started; the Full
summary variable now lives at step scope, with static regression coverage.
Neither fix weakens the clean-worktree rule.

## Accepted Behavior

- `scripts/phase8.py` exposes bounded `serve`, `reset`, `http`, `eval`, and
  `verify` commands, accepts loopback HTTP only, refuses wrong mode/ports, and
  always cleans the dedicated SQLite DB and sidecars.
- The real-process JWT journey covers blank, cycle-due, safety-blocked, retry,
  Agent, nutrition, Today, weekly review, and final zero-residue transitions.
  Output contains stable transition names and counts only.
- Evidence generation requires an exact 40-character HEAD and a completely
  clean worktree. CI artifacts are written outside the checkout.
- The synthetic device server installs an ASGI scope-level loopback guard, so
  direct Uvicorn binding cannot bypass the CLI restriction. IPv4/IPv6 loopback
  are allowed; non-loopback scope is rejected before the route handler.
- Versioned training and Agent matrices fail on missing linked cases, skips,
  malformed output, timeout, retrieved/user prompt injection, unknown tools,
  or unauthorized write expansion. No live provider is called.
- Weekly-review-origin drafts use the same bounded strategy mapping for direct
  and Agent paths. Confirmation binds the exact reviewed draft, active plan,
  latest review fingerprint, and a fresh deterministic safety recheck under a
  per-user transaction lock. An older active plan no longer hides a pending
  draft in Flutter.

## Local Exact-SHA Verification

The final Phase 8, Fast, and Full commands below checked out exact SHA
`cedda243221f0b04ac44d5dda816559201c48103`. The local Flutter command ran on
`6b5e8d8f973b22adcc73df053f8515742de0d2e1`:

| Command | Result |
| --- | --- |
| `python scripts/phase8.py verify --surface all` | exit 0; HTTP `11 passed / 0 failed`; `0` residual tables; eval `13 passed / 0 failed / 0 skipped` |
| `python scripts/verify.py fast` | exit 0; Ruff clean; `1007 passed / 0 failed / 11` conditional skips; diff clean |
| `python scripts/verify.py full` | exit 0; Ruff clean; `1707 passed / 0 failed / 30` conditional skips; diff clean |
| `flutter analyze && flutter test` on exact `6b5e8d8f973b22adcc73df053f8515742de0d2e1` | exit 0; analyze clean; `474 passed / 0 failed` |

The Flutter implementation content is unchanged between `6b5e8d8` and the
final CI-only commits. This parent-SHA local run is not final-SHA evidence;
exact final-SHA Flutter evidence is provided only by CI below.

## Exact-SHA CI

GitHub Actions workflow-dispatch run `31317248713` checked out exact SHA
`cedda243221f0b04ac44d5dda816559201c48103`:

- Fast: success; `1007 passed / 0 failed / 11` conditional skips.
- Flutter: success; analyze clean; `474 tests passed`.
- Full: success; `1737 passed / 0 failed / 0 skipped`; PostgreSQL expected
  `28`, actual `28`, version evidence present.
- Phase 8 acceptance: success; HTTP `11/11`, zero residual tables; eval
  `13/13`, zero skipped; evidence SHA matched the checkout.

## Rollback And Next Gate

No migration was added. Reverting the three Gate 2 implementation/CI commits
removes the acceptance runner and the narrowly bounded review-draft closure;
the disposable synthetic DB has no production rollback requirement.

The documentation-only Gate 2 closure commit must itself pass exact-SHA CI
before Task 3 starts. Task 3 has one OpenCode + Claude writer, uses only the
registered Flutter allowlist, consumes the frozen contracts, and may not edit
backend/domain/provider/dependency/CI/generated files or use fake API adapters,
direct DB calls, live AI, real health data, or photos.
