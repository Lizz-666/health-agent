# Phase 9 Gate 0 Codex Review

Date: 2026-08-12

Business base: `2ae03345a93d8cc22d0e47fcac415411798df48b`

Branch: `codex/phase9-controlled-trial`

> Status: local documentation candidate verified. Gate 0 is not finally accepted
> until the metadata closure is committed, pushed, and verified by exact-SHA
> GitHub CI. No business code was changed by this Gate.

## Findings First

### Blocking findings for a real controlled trial

1. **P1 - Production authentication is not trial-ready.** Current configuration
   defaults `SECRET_KEY` to `CHANGE-ME-IN-PRODUCTION`; development login remains
   selectable through `DEV_MODE`; development SMS handling logs the verification
   code and the real SMS path is a TODO. Phase 9 Gate 1 must add an explicit
   candidate profile that fails closed, invitation/account/device/session state,
   provider-neutral credentials, rate limits, recovery and audit. Until then no
   real tester credential or production environment is authorized.
2. **P1 - Independent professional review is not obtained.** The user currently
   has no legal/privacy or health-professional reviewer and has chosen not to
   incur that cost in Phase 9. Codex can perform internal engineering, source,
   privacy-material and safety-boundary pre-review, but cannot provide a lawyer's
   opinion, licensed health-professional approval, independent penetration test
   or certification. This blocks real health data, formal trial launch and public
   release; it does not block synthetic candidate engineering.
3. **P1 - Real photo and live provider conditions remain unsatisfied.** The photo
   privacy gate explicitly reports every enablement condition as unimplemented or
   unverified, while live Agent and nutrition runtime switches remain off. Phase 9
   keeps these paths off and does not treat them as candidate exit requirements.
4. **P2 - Privacy and operations evidence is incomplete.** There is no approved
   trial data-flow/retention/backup matrix, actual-operator impact assessment,
   trial incident owner/contact, threat model, monitoring/alerting contract,
   restore/deletion exercise or distribution rollback evidence. Gate 2 owns these
   internal artifacts and synthetic tests; actual provider/hosting facts remain a
   later authorization decision.
5. **P2 - Localization and accessibility evidence is partial.** Phase 8 records
   English curated exercise steps and technical fallbacks. Current Flutter code
   exposes only scattered Semantics/tooltips and several tests at 150% text scale;
   there is no complete 200%, TalkBack, formal contrast or device matrix evidence.
   Gate 3 owns this work.
6. **P2 - Network exposure and release configuration require hardening.** Current
   FastAPI CORS allows all origins and current defaults describe development/local
   operation rather than a reviewed trial environment. Gate 1-2 must freeze an
   explicit environment matrix and verify non-development startup and failure.

These findings block claims beyond the approved synthetic Phase 9 candidate
scope. They are planned work, not accepted residual risks for a real trial.

### Gate 0 document findings closed during review

1. The roadmap header still described the end goal as only a personal-development
   build after Phase 9 had been added. It now states controlled-trial candidate
   preparation.
2. `ACTIVE_TASKS.md` still said the Phase 8 final closure exact-SHA CI was pending.
   GitHub run `31507902602` proves that closure succeeded and the ledger now records
   it.
3. The initial Integration Order introduced duplicate numbered lists without a
   boundary. It now separates Phase 9 from historical integration entries.

After these corrections, the Gate 0 documentation review has no unresolved P0,
P1 or P2 within its approved documentation-only scope. External-review absence
and implementation gaps remain explicit blockers for later authorization.

## Baseline Proof

At Gate 0 start and again before local review:

- `HEAD` was `2ae03345a93d8cc22d0e47fcac415411798df48b` before edits.
- `codex/phase8-flutter-driver` and `origin/codex/phase8-flutter-driver` both
  resolved to the same SHA.
- `git merge-base HEAD 2ae03345...` returned the exact closure SHA.
- The worktree was clean and detached before creating
  `codex/phase9-controlled-trial` from that exact SHA.
- No `main`, old Phase worktree or unrelated branch was used as a business base.

GitHub run
[31507902602](https://github.com/Lizz-666/health-agent/actions/runs/31507902602)
completed successfully on branch `codex/phase8-flutter-driver`, exact head SHA
`2ae03345a93d8cc22d0e47fcac415411798df48b`. Fast, Flutter, Full with PostgreSQL
16, and Phase 8 synthetic HTTP/evaluation jobs all succeeded.

## Product Decisions

- Region/audience/channel: China mainland, generally healthy adults, Android
  non-public controlled-trial candidate.
- Operator: project owner during candidate preparation; real support and incident
  contacts must be recorded before an actual trial.
- Data: Gate 0-4 synthetic only; no real health, symptom, diet, contact, credential
  or photo data.
- AI/photo: live AI and real photo/upload remain off.
- Authentication: one unique invitation plus one independent account per tester,
  credentials delivered out of band, one active enrolled device, provider-neutral
  boundary for later SMS replacement.
- External review: no spend and no external reviewer in Phase 9; Codex internal
  pre-review only, with external legal/privacy, health and independent security
  review marked `not obtained`.

## Gate And Ownership Review

- Gate 0: Codex-only governance/specification closure.
- Gate 1: Codex-only identity, auth, migration, configuration and cross-client
  contract.
- Gate 2: Codex-only privacy, deletion/backup, threat model, supply chain,
  observability and incident operations.
- Gate 3A: one OpenCode + Claude Flutter-only localization/accessibility batch
  after Gate 2; exact allowlist frozen in the prompt; Codex reviews and may take
  over fixes.
- Gate 3B and Gate 4: Codex-only Android reliability, cross-layer E2E, final cold
  review, CI and exit audit.

The allowlists, commands, exact-SHA CI requirements, rollback and exit wording
are defined in the Phase 9 implementation plan. OpenCode reports are review input,
not acceptance evidence.

## Local Verification

Pre-commit verification on the documentation working tree:

| Command/check | Result |
| --- | --- |
| `git diff --check` | passed; only Git's existing LF-to-CRLF warnings |
| `python scripts/verify.py fast` | not accepted as a pass: ruff passed, 1002 tests passed and 23 expected PostgreSQL skips, but one Phase 8 HTTP evidence test correctly refused the dirty Git worktree |
| `flutter analyze` | passed; no issues |
| `flutter test` | 493 passed, 0 failed |

The Fast refusal is an intentional Phase 8 evidence invariant, not a product
regression. It was rerun on clean committed candidate
`b828b046baaa8c74186396481b52713828586570`:

| Command/check | Result |
| --- | --- |
| `python scripts/verify.py fast` | passed; ruff clean, backend 1011 passed / 0 failed / 15 expected conditional skips, working/staged/candidate diff clean |
| candidate scope | exactly seven Gate 0 documentation files; 835 insertions / 14 deletions; no app/backend/script/workflow/dependency change |

The earlier Flutter evidence was produced on the same document content before
the candidate commit; the commit did not change application files. Closure
metadata changes still require a clean exact-SHA Fast rerun.

Candidate and closure commands:

```powershell
git diff --check
python scripts/verify.py fast
Set-Location app
flutter analyze
flutter test
```

## Decision

The local candidate has no unresolved P0/P1/P2 within Gate 0 scope and may enter
metadata closure. Push and GitHub CI use the user's standing branch-push
authorization; they do not authorize deployment, merge, production credentials,
real data, external spend, live AI/photo, actual trial or public release.
