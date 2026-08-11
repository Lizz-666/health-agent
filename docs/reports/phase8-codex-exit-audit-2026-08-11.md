# Phase 8 Codex Exit Audit

Date: 2026-08-11

Gate 3 closure base: `ffb97ade27746ffeaf0826f762a2b7f8e7d90423`

Gate 4 local implementation candidate: `6c4e48bdd5a878012bc3a6377d40f76c5799fa2f`

Branch: `codex/phase8-flutter-driver`

> Candidate status: local acceptance passed; strict closure CI is pending. This
> report authorizes no merge, deployment, `main` write, public release, medical
> use, real health data/photo, production credential, or live-provider use.

## Findings First

Final Codex cold review has no unresolved P0, P1, or P2. An attempted separate
read-only review session returned no review because the tool quota was exhausted;
it is not counted as independent evidence. Codex therefore performed a fresh
base-to-candidate diff review after the Android runs and records that limitation.

Closed Gate 4 findings:

1. The original screenshot orchestration could reuse an orphan synthetic server
   after its intended process lost the port race. The orphan was identified by
   exact command line, stopped, and all accepted reruns proved listener owner PID
   equality before Android started and port/database cleanup afterward.
2. Plan, Agent, weekly-review, and unavailable screens exposed raw machine enums,
   internal substitution IDs, or a synthetic server detail. Stable known values
   are now localized, substitution IDs are hidden, unknown safety values fail
   closed, and unavailable copy is generic with a retry.
3. Screenshot evidence did not initially force the confirmed-goal and active
   nutrition labels into view. The driver now ensures those anchors are visible.
4. A reachable one-shot 503 did not satisfy the separate unreachable-host gate.
   A real Android test now seeds only a synthetic JWT over bounded HTTP while the
   production API client targets empty emulator-host port 65534. It proves both
   Today providers fail closed, retry remains visible, and no active/adjusted
   state appears.

Residual P3/public-release limits:

- Curated exercise instruction steps remain the reviewed knowledge-base English
  source text; full health-content localization requires separate review.
- Unknown non-safety Agent display fields retain a technical fallback. Complete
  product localization remains a release task; safety values do not default to
  success.
- Screenshot inspection covered visible layout and obvious contrast only. It is
  not screen-reader, formal contrast, large device matrix, or accessibility
  certification evidence.

## Local Evidence

All final implementation commands below ran at exact SHA
`6c4e48bdd5a878012bc3a6377d40f76c5799fa2f`:

| Command/check | Result |
| --- | --- |
| `python scripts/phase8.py verify --surface all` | HTTP 11/11; eval 13/13; 0 failed/skipped; 0 residual tables |
| `python scripts/verify.py full` | ruff clean; 1715 passed, 0 failed, 30 conditional PostgreSQL skips; diff clean |
| `flutter analyze` | no issues |
| `flutter test` | 493 passed, 0 failed |
| standard Android API 34 core journey | 8 passed, 0 failed; final reset passed |
| Android API 34 unreachable host | 1 passed, 0 failed; port 65534 had no listener |
| visual review | 10 synthetic screenshots inspected; no real data/photo/token/credential |
| artifact/log scan | no authorization header, token, password, API key, phone, or raw synthetic server detail found |

The local machine has no configured PostgreSQL acceptance service, so the 30
existing PostgreSQL-conditional tests remain skips rather than being relabeled
passes. Strict GitHub Full must run all 1745 tests with zero skips and expected
PostgreSQL parity.

## Screenshot Evidence

Screenshots are ignored local artifacts under `app/build/phase8-gate4` and are
not committed. SHA-256 prefixes identify the visually reviewed bytes:

| Checkpoint | SHA-256 prefix |
| --- | --- |
| login complete | `62a8e1ea0dfe` |
| posture result | `ad1366e7ed35` |
| posture profile/confirmed goal | `0f99db32fd95` |
| active plan | `0f18227381fe` |
| active Today | `7a76794724ff` |
| bounded Agent explanation | `7d7db5d1f08f` |
| active nutrition | `e1e38843f0b6` |
| weekly review | `5be08d71d77a` |
| training safety blocked | `5d08402b9963` |
| Today unavailable/retry | `cc5420fbd5fe` |

All records and prompts were fixed synthetic fixtures. Food images are reviewed
repository assets, not user photos. No photo-analysis or live-provider path ran.

## CI And Decision

Strict exact-SHA Fast/Flutter/Full/Phase8 CI is pending for the documentation
candidate and final closure. Acceptance requires Full 1745/0/0, PostgreSQL
expected/actual parity, Flutter 493, HTTP 11/11, eval 13/13, clean artifacts,
and event SHA equal to checked-out SHA. Until that evidence is green, Phase 8
remains `in_progress` and this report is a candidate, not final acceptance.

The separate [Public Release Gate](../product/public-release-gate.md) remains
entirely blocked. Phase 8 is only a repeatable synthetic Android development
acceptance baseline.
