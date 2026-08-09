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
  defined by the test app; faults are one-shot.
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
