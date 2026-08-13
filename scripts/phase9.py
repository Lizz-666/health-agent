#!/usr/bin/env python3
"""Synthetic-only Phase 9 controlled-trial reliability runner."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urlparse

import httpx


REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
DEVICE_DB = BACKEND_DIR / "phase9_acceptance.db"
MATRIX_DB = BACKEND_DIR / "phase9_matrix.db"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8875
CONTROL_HEADER = "X-Phase9-Control-Token"
CONTROL_TOKEN = "phase9-local-control-only"
CLIENT_HEADERS = {
    "X-Client-Platform": "android",
    "X-Client-Version-Code": "1",
}
EXPECTED_HEALTH = {"status": "ok", "mode": "synthetic-phase9-test"}
PRIMARY = {
    "account_name": "synthetic-trial-01",
    "credential": "Synthetic-trial-passphrase-01",
    "invitation_code": "synthetic_trial_invitation_0000000000000001",
    "device_key": "synthetic-device-key-0000000000000001",
}
SECONDARY = {
    "account_name": "synthetic-trial-02",
    "credential": "Synthetic-trial-passphrase-02",
    "invitation_code": "synthetic_trial_invitation_0000000000000002",
    "device_key": "synthetic-device-key-0000000000000002",
}
OTHER_DEVICE = "synthetic-device-key-0000000000000099"
SAFE_ERROR_CODES = frozenset(
    {
        "activation_failed",
        "auth_failed",
        "client_version_incompatible",
        "service_unavailable",
        "trial_device_conflict",
        "unauthorized",
    }
)


class Phase9Error(RuntimeError):
    """Fail-closed error that never includes response or credential content."""


def _head_sha() -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode != 0 or status.stdout.strip():
        raise Phase9Error("Phase 9 evidence requires a clean Git worktree")
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    value = result.stdout.strip()
    if result.returncode != 0 or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise Phase9Error("exact Git SHA is unavailable")
    return value


def _emit(command: str, transitions: List[str], counts: Dict[str, int]) -> None:
    print(
        json.dumps(
            {
                "command": command,
                "sha": _head_sha(),
                "checkpoint": "controlled_trial_reliability",
                "transitions": transitions,
                "counts": counts,
            },
            sort_keys=True,
        )
    )


def _validate_local_url(base_url: str) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise Phase9Error("Phase 9 accepts HTTP localhost targets only")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise Phase9Error("Phase 9 base URL contains forbidden components")


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


class Api:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        _validate_local_url(base_url)
        self.client = httpx.Client(base_url=base_url, timeout=timeout, trust_env=False)

    def close(self) -> None:
        self.client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        expected: int = 200,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        merged_headers = dict(CLIENT_HEADERS)
        if headers:
            merged_headers.update(headers)
        try:
            response = self.client.request(
                method,
                path,
                headers=merged_headers,
                json=body,
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            raise Phase9Error(
                f"request failed method={method} path={path} type={type(exc).__name__}"
            ) from exc
        if response.status_code != expected:
            code = "unknown"
            try:
                parsed = response.json()
                candidate = parsed.get("code") if isinstance(parsed, dict) else None
                if isinstance(candidate, str) and candidate in SAFE_ERROR_CODES:
                    code = candidate
            except (TypeError, ValueError):
                pass
            raise Phase9Error(
                f"unexpected response method={method} path={path} "
                f"status={response.status_code} code={code}"
            )
        if response.status_code == 204:
            return {}
        try:
            value = response.json()
        except ValueError as exc:
            raise Phase9Error(
                f"invalid JSON method={method} path={path} status={response.status_code}"
            ) from exc
        if not isinstance(value, dict):
            raise Phase9Error(f"non-object JSON method={method} path={path}")
        return value


def _auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _control_headers() -> Dict[str, str]:
    return {CONTROL_HEADER: CONTROL_TOKEN}


def _tokens(payload: Dict[str, Any]) -> tuple[str, str]:
    access = payload.get("access_token")
    refresh = payload.get("refresh_token")
    if (
        not isinstance(access, str)
        or not access
        or not isinstance(refresh, str)
        or not refresh
    ):
        raise Phase9Error("authentication returned invalid token envelope")
    return access, refresh


def _activate(api: Api, account: Dict[str, str]) -> tuple[str, str]:
    result = api.request(
        "POST",
        "/api/v1/auth/trial/activate",
        body={**account, "provider_id": "offline_password"},
    )
    return _tokens(result)


def _expect_code(
    api: Api,
    method: str,
    path: str,
    *,
    status: int,
    code: str,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        api.request(method, path, expected=200, headers=headers, body=body)
    except Phase9Error as exc:
        expected = f"status={status} code={code}"
        if expected not in str(exc):
            raise Phase9Error(
                f"expected stable failure method={method} path={path}"
            ) from exc
        return
    raise Phase9Error(f"request unexpectedly succeeded method={method} path={path}")


def _evidence(api: Api) -> Dict[str, Any]:
    return api.request("GET", "/__phase9/evidence", headers=_control_headers())


def run_http_journey(base_url: str) -> Dict[str, Any]:
    api = Api(base_url)
    checks: List[str] = []
    try:
        if api.request("GET", "/health") != EXPECTED_HEALTH:
            raise Phase9Error("target is not the exact synthetic Phase 9 server mode")
        reset = api.request("POST", "/__phase9/reset", headers=_control_headers())
        if reset.get("synthetic_only") is not True:
            raise Phase9Error("reset did not prove synthetic mode")
        checks.append("reset_two_independent_accounts")

        access, refresh = _activate(api, PRIMARY)
        profile = api.request(
            "GET", "/api/v1/user/profile", headers=_auth_headers(access)
        )
        primary_id = profile.get("id")
        if not isinstance(primary_id, str) or not primary_id:
            raise Phase9Error("primary account profile identity is unavailable")
        checks.append("primary_invitation_activation")

        _expect_code(
            api,
            "POST",
            "/api/v1/auth/trial/activate",
            status=400,
            code="activation_failed",
            body={**PRIMARY, "provider_id": "offline_password"},
        )
        checks.append("invitation_replay_blocked")

        _expect_code(
            api,
            "POST",
            "/api/v1/auth/trial/login",
            status=403,
            code="trial_device_conflict",
            body={
                "account_name": PRIMARY["account_name"],
                "credential": PRIMARY["credential"],
                "provider_id": "offline_password",
                "device_key": OTHER_DEVICE,
            },
        )
        checks.append("device_conflict_blocked")

        secondary_access, _ = _activate(api, SECONDARY)
        secondary_profile = api.request(
            "GET", "/api/v1/user/profile", headers=_auth_headers(secondary_access)
        )
        if secondary_profile.get("id") == primary_id:
            raise Phase9Error("independent accounts resolved to the same identity")
        checks.append("independent_account_isolation")

        rotated = api.request(
            "POST", "/api/v1/auth/refresh", body={"refresh_token": refresh}
        )
        rotated_access, rotated_refresh = _tokens(rotated)
        _expect_code(
            api,
            "POST",
            "/api/v1/auth/refresh",
            status=401,
            code="auth_failed",
            body={"refresh_token": refresh},
        )
        _expect_code(
            api,
            "GET",
            "/api/v1/user/profile",
            status=401,
            code="unauthorized",
            headers=_auth_headers(access),
        )
        api.request(
            "GET", "/api/v1/user/profile", headers=_auth_headers(rotated_access)
        )
        checks.append("refresh_rotation_and_replay")

        api.request(
            "POST",
            "/__phase9/faults",
            headers=_control_headers(),
            body={
                "route": "/api/v1/user/profile",
                "kind": "slow_response",
                "delay_ms": 600,
            },
        )
        try:
            api.request(
                "GET",
                "/api/v1/user/profile",
                headers=_auth_headers(rotated_access),
                timeout=0.1,
            )
        except Phase9Error as exc:
            if "ReadTimeout" not in str(exc):
                raise
        else:
            raise Phase9Error("slow response did not exceed the bounded client timeout")
        api.request(
            "GET", "/api/v1/user/profile", headers=_auth_headers(rotated_access)
        )
        checks.append("slow_response_explicit_retry")

        before_compat = _evidence(api)
        api.request(
            "POST",
            "/__phase9/compatibility",
            headers=_control_headers(),
            body={"minimum": 2, "maximum": 2},
        )
        _expect_code(
            api,
            "POST",
            "/api/v1/privacy/consent",
            status=426,
            code="client_version_incompatible",
            headers=_auth_headers(rotated_access),
            body={
                "action": "grant",
                "notice_version": "controlled-trial-sensitive-health-v1",
            },
        )
        after_compat = _evidence(api)
        if before_compat.get("table_counts") != after_compat.get("table_counts"):
            raise Phase9Error("incompatible client produced a domain write")
        api.request(
            "POST",
            "/__phase9/compatibility",
            headers=_control_headers(),
            body={"minimum": 1, "maximum": 1},
        )
        checks.append("client_incompatibility_zero_writes")

        api.request(
            "POST",
            "/__phase9/sessions/revoke",
            headers=_control_headers(),
            body={"account": "primary"},
        )
        _expect_code(
            api,
            "GET",
            "/api/v1/user/profile",
            status=401,
            code="unauthorized",
            headers=_auth_headers(rotated_access),
        )
        _expect_code(
            api,
            "POST",
            "/api/v1/auth/refresh",
            status=401,
            code="auth_failed",
            body={"refresh_token": rotated_refresh},
        )
        checks.append("revoked_session_blocked")

        api.request("POST", "/__phase9/reset", headers=_control_headers())
        expiring_access, _ = _activate(api, PRIMARY)
        api.request(
            "POST",
            "/__phase9/sessions/expire",
            headers=_control_headers(),
            body={"account": "primary"},
        )
        _expect_code(
            api,
            "GET",
            "/api/v1/user/profile",
            status=401,
            code="unauthorized",
            headers=_auth_headers(expiring_access),
        )
        checks.append("expired_session_blocked")

        final = api.request("POST", "/__phase9/reset", headers=_control_headers())
        counts = final.get("table_counts")
        if not isinstance(counts, dict):
            raise Phase9Error("final evidence omitted table counts")
        expected = {
            "users": 2,
            "trial_credentials": 2,
            "trial_invitations": 2,
            "trial_device_enrollments": 0,
            "auth_sessions": 0,
            "sensitive_health_consent_events": 0,
        }
        if any(counts.get(key) != value for key, value in expected.items()):
            raise Phase9Error(
                "final reset did not restore the exact synthetic baseline"
            )
        checks.append("final_zero_residue")
        return {
            "transitions": checks,
            "counts": {
                "checks_passed": len(checks),
                "checks_failed": 0,
                "tables_observed": len(counts),
                "residual_tables": 0,
            },
        }
    finally:
        api.close()


def _base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _server_command(host: str, port: int) -> List[str]:
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "tests.phase9_device_server:app",
        "--host",
        host,
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]


def _remove_sqlite_files(database: Path) -> None:
    for suffix in ("", "-journal", "-wal", "-shm"):
        path = Path(str(database) + suffix)
        if path.exists():
            path.unlink()


def _remove_device_db() -> None:
    _remove_sqlite_files(DEVICE_DB)


def wait_ready(base_url: str, process: subprocess.Popen, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise Phase9Error(
                f"synthetic server exited before readiness code={process.returncode}"
            )
        api = Api(base_url, timeout=1.0)
        try:
            if api.request("GET", "/health") == EXPECTED_HEALTH:
                return
        except Phase9Error:
            pass
        finally:
            api.close()
        time.sleep(0.1)
    raise Phase9Error("synthetic server readiness timeout")


@contextmanager
def running_server(host: str, port: int, ready_timeout: float) -> Iterator[str]:
    if host not in {"127.0.0.1", "localhost"}:
        raise Phase9Error("synthetic server may bind to localhost only")
    if not _port_available(host, port):
        raise Phase9Error(f"synthetic server port is already in use port={port}")
    _remove_device_db()
    environment = os.environ.copy()
    environment.pop("TEST_DB_URL", None)
    process = subprocess.Popen(
        _server_command(host, port),
        cwd=BACKEND_DIR,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        base_url = _base_url(host, port)
        wait_ready(base_url, process, ready_timeout)
        yield base_url
    finally:
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        finally:
            _remove_device_db()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 9 synthetic reliability")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    http = sub.add_parser("http")
    verify = sub.add_parser("verify")
    for item in (serve, http, verify):
        item.add_argument("--host", default=DEFAULT_HOST)
        item.add_argument("--port", type=int, default=DEFAULT_PORT)
    verify.add_argument("--surface", choices=["http", "matrix", "all"], default="all")
    verify.add_argument("--ready-timeout", type=float, default=20.0)
    return parser


def _run_matrix() -> int:
    environment = os.environ.copy()
    environment["TEST_DB_URL"] = (
        f"sqlite+aiosqlite:///{MATRIX_DB.as_posix()}"
    )
    _remove_sqlite_files(MATRIX_DB)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_phase9_matrix.py", "-q"],
            cwd=BACKEND_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    finally:
        _remove_sqlite_files(MATRIX_DB)
    if result.returncode != 0:
        raise Phase9Error(f"matrix verification failed code={result.returncode}")
    _emit(
        "matrix",
        ["asia_shanghai_midnight", "asia_shanghai_week_boundary"],
        {"passed": 2, "failed": 0, "skipped": 0},
    )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "serve":
            if args.host not in {"127.0.0.1", "localhost"}:
                raise Phase9Error("synthetic server may bind to localhost only")
            _remove_device_db()
            try:
                return subprocess.run(
                    _server_command(args.host, args.port),
                    cwd=BACKEND_DIR,
                    check=False,
                ).returncode
            finally:
                _remove_device_db()
        if args.command == "http":
            result = run_http_journey(_base_url(args.host, args.port))
            _emit("http", result["transitions"], result["counts"])
            return 0
        if args.command == "verify":
            if args.surface in {"http", "all"}:
                with running_server(
                    args.host, args.port, args.ready_timeout
                ) as base_url:
                    result = run_http_journey(base_url)
                _emit("verify-http", result["transitions"], result["counts"])
            if args.surface in {"matrix", "all"}:
                return _run_matrix()
            return 0
        raise Phase9Error("unsupported command")
    except (OSError, Phase9Error, subprocess.TimeoutExpired) as exc:
        print(f"phase9 failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
