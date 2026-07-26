# Phase 3 Exit Audit: Training Knowledge and Safety Engine

> Date: 2026-07-26. Final reviewer: Codex. Implementation: one OpenCode +
> Claude session, followed by independent Codex review and acceptance fixes.
> Scope is personal-development validation only, not clinical or public-release
> approval.

## 1. Decision and SHAs

Phase 3 is **verified and committed locally**. It is eligible for local
integration. There are no unresolved P0, P1, or P2 findings.

| Item | SHA |
| --- | --- |
| Comparison base | `c49eb618759ff85d7235f515b57c9d3fad38d6cb` |
| OpenCode final handoff | `9ccaa3587c1bd258a04f326271db46c16994989b` |
| Codex acceptance fixes | `423bf55f1a54215f4f0ece0506c7d3b5259441fd` |
| Status/report commit | commit containing this report |

The complete accepted range through `423bf55` changes 69 files with 11,784
insertions and 10 deletions. No Flutter runtime, public router, training DB
model, Alembic migration, AI provider, deployment, or production data path was
added.

## 2. Delivered capability

- A typed, versioned 24-exercise bodyweight/resistance-band catalog with
  bounded prescriptions, relations, contraindications, stop conditions,
  personal-development review state, item-level ACE review references, ACSM
  policy-envelope references, and original local SVG assets.
- Strict catalog/source loading: missing manifest, unknown pins, path escape,
  hash mismatch, unsafe SVG XML/content, unsupported versions, invalid
  relations, and incomplete review metadata fail closed.
- A deterministic safety context and classifier composed from current health,
  check-in, retained-pain, posture signal, confirmed-goal, request, clock, and
  version snapshots.
- A deterministic candidate engine and pure draft validator that recompute
  safety, bind request/profile/goal/version fingerprints, enforce candidate and
  prescription bounds, and reject blocked or stale inputs without repair.
- An authorization-aware `validate_training_plan` tool contract that receives
  the principal user ID from the trusted caller and performs no persistence.
- Layered local verification and a least-privilege GitHub Actions workflow with
  immutable action/image pins, exact PostgreSQL execution evidence, JUnit
  fail-closed handling, first-push diff handling, and summary artifacts.

## 3. Independent acceptance findings

The OpenCode handoff was **not accepted on first pass**. Codex reviewed the
real `base..HEAD` diff, used independent cold-review agents, and repaired the
following blocking clusters in `423bf55`:

- Safety policy sections could be omitted or weakened; request/profile
  binding, goal confirmation controls, source versions, and injected-clock
  behavior were incomplete.
- Candidate and draft validation trusted supplied decisions or stale bindings
  in several paths; recovery, relation, session-order, volume, and
  movement-pattern constraints had gaps.
- Tool identity was request-controlled instead of exclusively caller-supplied.
- Release loading could bypass the source manifest, accept traversal keys, and
  trust an SVG hash without scanning active/external content.
- All exercises cited one generic ACE homepage; license/media exception checks
  and project-authored license claims were insufficiently precise.
- CI could pass with missing/corrupt JUnit, did not prove expected versus actual
  PostgreSQL test execution, used a mutable PostgreSQL tag, and mishandled the
  all-zero first-push base.

Regression tests were added for each repaired failure class. No unresolved
P0/P1/P2 finding remains.

## 4. Fresh verification evidence

Evidence applies to the accepted code at `423bf55`; later edits in this report
are documentation-only.

| Command | Workdir | Exit | Result |
| --- | --- | --- | --- |
| `python scripts/verify.py fast` | repository root | 0 | ruff clean; `189 passed`, 0 failed, 2 intentionally skipped PG cases; diff check passed |
| `VERIFY_REQUIRE_PG=1 python scripts/verify.py full` | repository root | 0 | ruff clean; `989 passed`, 0 failed, 0 skipped; diff check passed |
| Full PostgreSQL evidence | repository root | 0 | `expected=13 actual=13`, PostgreSQL version evidence present, Alembic path exercised |
| Focused repaired suites | `backend` | 0 | `143 passed` |

The line-ending messages emitted by Git on Windows are conversion warnings,
not whitespace errors.

## 5. GitHub CI status

Remote GitHub Actions is **not authorized / not run** because no push or PR was
authorized. The workflow is implemented and locally reviewed, but this audit
does not claim a remote CI result. A future remote run is evidence only for the
exact pushed SHA.

## 6. Source, license, and media audit

- The metadata-only dataset and comparison project remain pinned to
  `7455efae41b330c265e7cd4b78dfa848e7ce5ebd` and
  `77f25a922b51be7d96bd051c5d2096959f0d61a8`.
- The complete upstream MIT/media-exception and workout-cool MIT blocks are
  byte-integrity tested. No Gym visual media or upstream instruction text is
  used.
- Each exercise records a specific ACE official page/article and the ACSM
  healthy-adult policy source; records remain independently authored and do
  not copy source text or media.
- All 24 SVG hashes match. Loader and tests reject scripts, images,
  `foreignObject`, entities, embedded data, external references, path escape,
  and invalid XML.
- The repository does not claim a distribution license for project-authored
  catalog or illustration content.

## 7. Residual P3 risks

1. Remote CI has not run.
2. Original SVGs still require a separate qualified visual-form review before
   public release.
3. Phase 4 must wire `principal_user_id` from trusted authentication; Phase 3
   only defines and tests the internal tool boundary.
4. Retained abnormal-pain records do not auto-expire; recovery requires source
   correction/deletion and a fresh complete context.
5. `training.context` contains one narrow, ownership-filtered active-goal read
   because the posture domain has no equivalent public accessor.
6. Pinned CI digests and reviewed health references need intentional periodic
   maintenance rather than floating updates.

## 8. Collaboration experiment evaluation

Observable OpenCode delivery metrics:

- One implementation session and one final handoff, with no intermediate Codex
  acceptance checkpoint.
- Eight milestone commits plus the start marker; observable commit timestamp
  span was about 2 hours 24 minutes.
- Initial handoff footprint: 64 files, 10,022 insertions, 6 deletions.
- First-pass acceptance: failed.
- Codex acceptance rework: 34 files, 2,027 insertions, 269 deletions.
- Exact OpenCode/Codex token and active wall-clock telemetry was unavailable,
  so no unsupported cost comparison is claimed.

Assessment: full-phase delegation reduced coordination and produced a broad
implementation quickly, but correlated safety, provenance, and CI-evidence
defects accumulated behind a roughly 10,000-line final review. Phase 2's
task-level checkpoints created more handoffs but contained rework earlier.

Recommended operating model: retain OpenCode as the primary implementer for
two or three sequential, tightly related Tasks at a time. Codex reviews at
contract boundaries: (1) CI/schema/catalog, (2) safety context/candidates, and
(3) validator/E2E. Use GitHub CI after an early user-authorized candidate push.
This keeps implementation momentum while preventing an entire high-risk phase
from reaching final review with coupled defects.

## 9. Final scope statement

Only synthetic test data was used. No real health data, photo, credential,
production key, deployment, push, PR, or external write occurred. Phase 3
meets the roadmap exit criteria locally and is ready for local integration.
