# Phase 8 Local Acceptance Runbook

> Test/development use only. Synthetic data only. Do not use production
> credentials, real health data, real photos, or a live AI provider.

## One-command checks

Run from the repository root:

```powershell
python scripts/phase8.py verify --surface http
python scripts/phase8.py verify --surface eval
python scripts/phase8.py verify --surface all
```

`verify --surface http` starts an isolated localhost server, waits for the exact
synthetic mode, runs the JWT journey, and terminates the child process. The
dedicated `backend/phase8_acceptance.db` is removed on success and failure.
Every assertion or child-process failure returns non-zero.

## Android server

For an Android emulator, run the test-only server from the repository root:

```powershell
python scripts/phase8.py serve --host 127.0.0.1 --port 8000
```

The emulator uses:

```text
API_BASE_URL=http://10.0.2.2:8000/api/v1
DEV_ADMIN_PHONE=13900000008
DEV_ADMIN_PASSWORD=synthetic-phase8-only
```

The device local timezone must match the app/server contract before launching
the driver. A UTC emulator can save a different local check-in date and must be
rejected rather than weakening the safety gate:

```powershell
adb -s emulator-5554 shell getprop persist.sys.timezone
adb -s emulator-5554 shell date -Iseconds
```

Expected timezone is `Asia/Shanghai`. On a disposable root-capable AVD only,
set it with `adb -s emulator-5554 root` followed by
`adb -s emulator-5554 shell setprop persist.sys.timezone Asia/Shanghai`, then
re-run both checks. Do not change a physical/personal device for this gate.

With the synthetic server healthy, run from `app/`:

```powershell
flutter test integration_test/phase8_core_journey_test.dart -d emulator-5554 `
  --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1 `
  --dart-define=DEV_ADMIN_PHONE=13900000008 `
  --dart-define=DEV_ADMIN_PASSWORD=synthetic-phase8-only
```

To capture the ten required synthetic screenshots, keep the same server running
and use the gated screenshot driver from `app/`:

```powershell
$env:PHASE8_SCREENSHOT_DIR = (Resolve-Path .\build).Path + '\phase8-gate4\screenshots'
flutter drive `
  --driver=test_driver/phase8_screenshot_driver.dart `
  --target=integration_test/phase8_core_journey_test.dart `
  -d emulator-5554 `
  --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1 `
  --dart-define=DEV_ADMIN_PHONE=13900000008 `
  --dart-define=DEV_ADMIN_PASSWORD=synthetic-phase8-only `
  --dart-define=PHASE8_CAPTURE_SCREENSHOTS=true
```

Screenshot capture is off by default. The driver deletes only its configured
output directory, rejects unexpected names, and must write exactly the named
synthetic checkpoints. Do not commit screenshots, logs, tokens, local databases,
or generated plugin registrants.

## Unreachable Android run

Keep the synthetic server on host port 8000 for bounded reset and dev-login
setup, but first prove host port 65534 has no listener:

```powershell
if (Get-NetTCPConnection -LocalPort 65534 -State Listen -ErrorAction SilentlyContinue) {
  throw 'Port 65534 must be unreachable for this gate'
}

flutter test integration_test/phase8_unreachable_test.dart -d emulator-5554 `
  --dart-define=API_BASE_URL=http://10.0.2.2:65534/api/v1 `
  --dart-define=PHASE8_SEED_API_BASE_URL=http://10.0.2.2:8000/api/v1 `
  --dart-define=DEV_ADMIN_PHONE=13900000008 `
  --dart-define=DEV_ADMIN_PASSWORD=synthetic-phase8-only
```

The setup client may only reset the disposable synthetic backend and obtain its
synthetic JWT. The production `ApiClient` remains pinned to the empty port. The
test requires both Today providers to fail as `networkError`, a visible retry,
no effective Today result, no applied adjustment, and no active/success UI.

The blank checkpoint selects an existing legal production schedule. Saturday
has no production session and is therefore asserted as `rest_day`; no test-only
training day or safety-policy override is introduced. Other supported weekdays
exercise the foreground adjustment and feedback path.

The Android suite contains eight required scenarios: the supported-adult core
journey, cycle-due review, safety block, real missing-check-in rejection,
one-shot stale training-draft rejection, one-shot 503 recovery, malformed Today
recovery, and final blank reset. Missing-input and stale generation both assert
the visible fail-closed state and sanitized evidence that no training plan
version was written.

The Android emulator's `10.0.2.2` alias forwards to the host loopback. The CLI
refuses non-loopback binds so the fixed synthetic control credential is not
exposed to the LAN. The server remains test-only and uses the exact disposable
SQLite path.

`tzdata==2026.3` is pinned in backend requirements so Python `zoneinfo` has the
same IANA fallback on Windows and Linux. Source and release provenance:
`https://pypi.org/project/tzdata/2026.3/`.

## Frozen Gate 2 contract

- Health probe: `GET /health` must equal
  `{"status":"ok","mode":"synthetic-phase8-test"}`.
- Login: `POST /api/v1/auth/dev-login` with the synthetic credentials above.
- Control header: `X-Phase8-Control-Token: phase8-local-control-only`.
- Reset: `POST /__phase8/reset` with exactly one checkpoint:
  `blank_supported`, `cycle_due`, or `safety_blocked`.
- Faults: `POST /__phase8/faults` accepts only the allowlisted route/kind enums
  defined by the test app; faults are one-shot. Task 3 adds only the
  `POST /api/v1/training/plans:draft` + `stale_context` pair needed to prove the
  real Flutter mutation surface. It cannot alter a successful payload or any
  production safety classification.
- Evidence: `GET /__phase8/evidence` returns synthetic mode, checkpoint,
  generation, provider/object counts, and table counts only.
- CLI evidence fields: `command`, exact `sha`, `checkpoint`, sanitized
  `transitions`, and pass/fail `counts`.

Task 3 must use the real app HTTP client and `AppConstants.apiBaseUrl`. It may
call control routes only from integration-test setup. It must not override
`apiClientProvider`, install `FakeDioAdapter`, import backend services, seed
tables directly, or make a live cloud-provider call.

## Manual control

Against an already running local server:

```powershell
python scripts/phase8.py reset --host 127.0.0.1 --port 8000 --checkpoint blank_supported
python scripts/phase8.py http --host 127.0.0.1 --port 8000
```

The CLI refuses non-local HTTP targets/binds, wrong server modes, occupied verify
ports, readiness timeout, malformed JSON, unexpected status codes, and unknown
commands/checkpoints. Output must not contain JWTs, credentials, request bodies,
health values, prompts, or response bodies.

## Cleanup and limits

After every device run, stop the exact server process, confirm ports 8000 and
65534 have no listener, remove `backend/phase8_acceptance.db` and its sidecars,
and restore only tool-generated plugin registrants. Never use `git clean` or a
recursive repository-wide delete for this cleanup.

This runbook proves a synthetic Android personal-development build. It does not
approve deployment, public release, medical use, real health data or photos,
production credentials, a live AI provider, iOS, a physical device, complete
offline operation, accessibility certification, or production operations. The
separate gate is [Public Release Gate](../../product/public-release-gate.md).
