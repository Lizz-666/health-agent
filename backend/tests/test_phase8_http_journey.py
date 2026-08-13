"""Real-process and fail-closed tests for the Phase 8 localhost runner."""
from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.phase8_loopback import install_loopback_guard


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "phase8.py"
DEVICE_DB = REPO_ROOT / "backend" / "phase8_acceptance.db"


def _load_runner():
    spec = importlib.util.spec_from_file_location("phase8_runner", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


phase8 = _load_runner()


def test_parser_exposes_only_bounded_commands_and_surfaces():
    parser = phase8.build_parser()
    assert parser.parse_args(["verify", "--surface", "http"]).surface == "http"
    assert parser.parse_args(["reset", "--checkpoint", "cycle_due"]).checkpoint == (
        "cycle_due"
    )
    with pytest.raises(SystemExit):
        parser.parse_args(["verify", "--surface", "live"])
    with pytest.raises(SystemExit):
        parser.parse_args(["reset", "--checkpoint", "production"])


def test_journey_schedule_always_selects_an_existing_session_day():
    schedules = {
        2: {2, 5},
        3: {1, 3, 5},
        5: {1, 2, 4, 5, 7},
    }
    start = datetime(2026, 8, 3, 1, tzinfo=timezone.utc)
    for offset in range(7):
        current = start + timedelta(days=offset)
        zone_name, frequency = phase8._journey_schedule(current)
        local_weekday = current.astimezone(phase8.ZoneInfo(zone_name)).isoweekday()
        assert local_weekday in schedules[frequency]


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8765",
        "http://0.0.0.0:8765",
        "http://example.test:8765",
        "http://user:pass@localhost:8765",
        "http://localhost:8765?token=forbidden",
    ],
)
def test_non_local_or_credential_bearing_target_is_rejected(url):
    with pytest.raises(phase8.Phase8Error):
        phase8._validate_local_url(url)


def test_wrong_server_mode_fails_closed():
    api = SimpleNamespace(json=lambda *_args, **_kwargs: {"status": "ok"})
    with pytest.raises(phase8.Phase8Error, match="exact synthetic Phase 8"):
        phase8.assert_phase8_server(api)


def test_unknown_response_code_is_not_reflected():
    class FakeClient:
        def request(self, *_args, **_kwargs):
            return httpx.Response(500, json={"code": "untrusted-sensitive-value"})

        def close(self):
            pass

    api = phase8.Api("http://127.0.0.1:8765")
    api.client.close()
    api.client = FakeClient()
    with pytest.raises(phase8.Phase8Error) as error:
        api.json("GET", "/synthetic-error")
    assert "untrusted-sensitive-value" not in str(error.value)
    assert "code=unknown" in str(error.value)


def test_exact_sha_failure_is_not_reported_as_unknown(monkeypatch):
    monkeypatch.setattr(
        phase8.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout=""),
    )
    with pytest.raises(phase8.Phase8Error, match="exact Git SHA"):
        phase8._head_sha()


def test_exact_sha_evidence_rejects_a_dirty_worktree(monkeypatch):
    monkeypatch.setattr(
        phase8.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="M backend/app/training/service.py\n",
        ),
    )
    with pytest.raises(phase8.Phase8Error, match="clean Git worktree"):
        phase8._head_sha()


def test_port_collision_fails_before_process_start():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind((phase8.DEFAULT_HOST, 0))
        port = occupied.getsockname()[1]
        occupied.listen(1)
        with pytest.raises(phase8.Phase8Error, match="already in use"):
            with phase8.running_server(phase8.DEFAULT_HOST, port, 0.1):
                pytest.fail("server must not start on an occupied port")


def test_readiness_timeout_fails_without_response_content(monkeypatch):
    class NeverReadyApi:
        def __init__(self, *_args, **_kwargs):
            pass

        def close(self):
            pass

    process = SimpleNamespace(poll=lambda: None)
    monkeypatch.setattr(phase8, "Api", NeverReadyApi)
    monkeypatch.setattr(
        phase8,
        "assert_phase8_server",
        lambda _api: (_ for _ in ()).throw(phase8.Phase8Error("stable_not_ready")),
    )
    with pytest.raises(phase8.Phase8Error, match="stable_not_ready") as error:
        phase8.wait_ready("http://127.0.0.1:1", process, 0.01)
    assert "body" not in str(error.value).lower()


def test_eval_failure_exit_code_propagates(monkeypatch):
    monkeypatch.setattr(phase8, "_run_eval", lambda: 7)
    assert phase8.main(["eval"]) == 7
    assert phase8.main(["verify", "--surface", "eval"]) == 7


def test_eval_timeout_fails_closed_without_child_output(monkeypatch):
    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("synthetic-eval", 1, output="sensitive")

    monkeypatch.setattr(phase8.subprocess, "run", timeout)
    with pytest.raises(phase8.Phase8Error, match="evaluation timed out") as error:
        phase8._run_eval()
    assert "sensitive" not in str(error.value)


def test_child_process_is_terminated_when_journey_body_fails(monkeypatch):
    class FakeProcess:
        def __init__(self):
            self.returncode = None
            self.terminated = False
            self.waited = False

        def poll(self):
            return None if not self.terminated else 0

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            self.waited = True
            return 0

    process = FakeProcess()
    original_db = phase8.DEVICE_DB
    device_db = original_db.parent / "phase8-test-cleanup.db"
    monkeypatch.setattr(phase8, "_port_available", lambda *_args: True)
    monkeypatch.setattr(phase8, "DEVICE_DB", device_db)
    monkeypatch.setattr(phase8.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(phase8, "wait_ready", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="journey failed"):
        with phase8.running_server(phase8.DEFAULT_HOST, 18765, 0.1):
            for suffix in ("", "-journal", "-wal", "-shm"):
                Path(str(device_db) + suffix).write_text("synthetic", encoding="utf-8")
            raise RuntimeError("journey failed")

    assert process.terminated is True
    assert process.waited is True
    assert not any(
        Path(str(device_db) + suffix).exists()
        for suffix in ("", "-journal", "-wal", "-shm")
    )


def test_device_db_is_cleaned_when_forced_process_wait_fails(monkeypatch):
    class UnstoppableProcess:
        def __init__(self):
            self.wait_count = 0
            self.killed = False

        def poll(self):
            return None

        def terminate(self):
            pass

        def kill(self):
            self.killed = True

        def wait(self, timeout):
            self.wait_count += 1
            if self.wait_count == 1:
                raise subprocess.TimeoutExpired("synthetic-server", timeout)
            raise RuntimeError("forced wait failed")

    process = UnstoppableProcess()
    device_db = phase8.DEVICE_DB.parent / "phase8-test-forced-cleanup.db"
    monkeypatch.setattr(phase8, "_port_available", lambda *_args: True)
    monkeypatch.setattr(phase8, "DEVICE_DB", device_db)
    monkeypatch.setattr(phase8.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(phase8, "wait_ready", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="forced wait failed"):
        with phase8.running_server(phase8.DEFAULT_HOST, 18766, 0.1):
            for suffix in ("", "-journal", "-wal", "-shm"):
                Path(str(device_db) + suffix).write_text("synthetic", encoding="utf-8")

    assert process.killed is True
    assert process.wait_count == 2
    assert not any(
        Path(str(device_db) + suffix).exists()
        for suffix in ("", "-journal", "-wal", "-shm")
    )


def test_serve_refuses_non_loopback_before_start(monkeypatch):
    monkeypatch.setattr(
        phase8.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("server must not start"),
    )
    assert phase8.main(["serve", "--host", "0.0.0.0"]) == 1


def test_real_localhost_http_journey_is_sanitized_and_cleans_up():
    assert not DEVICE_DB.exists()
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "verify",
            "--surface",
            "http",
            "--ready-timeout",
            "20",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout.strip())
    assert evidence["command"] == "verify-http"
    assert evidence["checkpoint"] == (
        "blank_supported -> cycle_due -> safety_blocked -> blank_supported"
    )
    assert evidence["sha"] == subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert evidence["counts"]["checks_passed"] >= 11
    assert evidence["counts"]["checks_failed"] == 0
    assert evidence["counts"]["residual_tables"] == 0
    assert "today_session" in evidence["transitions"]
    assert "safety_blocked_zero_writes" in evidence["transitions"]
    assert "final_zero_residue" in evidence["transitions"]
    combined = result.stdout + result.stderr
    for forbidden in (
        phase8.SYNTHETIC_PHONE,
        phase8.SYNTHETIC_PASSWORD,
        phase8.CONTROL_TOKEN,
        "access_token",
        "weight_kg",
        "Authorization",
    ):
        assert forbidden not in combined
    assert not DEVICE_DB.exists()


def test_device_runtime_uses_reviewed_gate_with_scripted_provider_only():
    source = (REPO_ROOT / "backend" / "tests" / "phase8_device_server.py").read_text(
        encoding="utf-8"
    )
    assert 'settings.AGENT_PROVIDER_ID = "dashscope"' in source
    assert 'settings.AGENT_DISCLOSURE_VERSION = "agent-cloud-v1"' in source
    assert "synthetic-phase8-key-never-sent" in source
    assert "get_provider_override=provider_controller.get" in source
    assert "DashScopeProvider(" not in source
    assert "0.0.0.0" not in source
    assert "install_loopback_guard(app)" in source


@pytest.mark.asyncio
async def test_device_loopback_guard_allows_loopback_and_blocks_direct_bind_bypass():
    guarded = FastAPI()
    handler_calls = 0

    @guarded.get("/probe")
    async def probe():
        nonlocal handler_calls
        handler_calls += 1
        return {"status": "ok"}

    install_loopback_guard(guarded)

    for base_url in ("http://127.0.0.1", "http://[::1]"):
        async with AsyncClient(
            transport=ASGITransport(app=guarded),
            base_url=base_url,
        ) as client:
            response = await client.get("/probe")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    async with AsyncClient(
        transport=ASGITransport(app=guarded),
        base_url="http://0.0.0.0",
    ) as client:
        response = await client.get("/probe")
    assert response.status_code == 403
    assert response.json() == {
        "detail": "Phase 8 synthetic server requires loopback",
        "code": "phase8_loopback_required",
    }
    assert handler_calls == 2
