from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "phase9.py"
DEVICE_DB = REPO_ROOT / "backend" / "phase9_acceptance.db"


def _load_runner():
    spec = importlib.util.spec_from_file_location("phase9_runner", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


phase9 = _load_runner()


def test_parser_exposes_only_bounded_surfaces():
    parser = phase9.build_parser()
    assert parser.parse_args(["verify", "--surface", "matrix"]).surface == "matrix"
    with pytest.raises(SystemExit):
        parser.parse_args(["verify", "--surface", "live"])


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8875",
        "http://0.0.0.0:8875",
        "http://example.test:8875",
        "http://user:pass@localhost:8875",
        "http://localhost:8875?token=forbidden",
    ],
)
def test_non_local_or_credential_bearing_target_is_rejected(url):
    with pytest.raises(phase9.Phase9Error):
        phase9._validate_local_url(url)


def test_exact_sha_evidence_rejects_dirty_worktree(monkeypatch):
    monkeypatch.setattr(
        phase9.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="M file\n"),
    )
    with pytest.raises(phase9.Phase9Error, match="clean Git worktree"):
        phase9._head_sha()


def test_unknown_response_code_is_not_reflected():
    class FakeClient:
        def request(self, *_args, **_kwargs):
            return phase9.httpx.Response(500, json={"code": "sensitive-code"})

        def close(self):
            pass

    api = phase9.Api("http://127.0.0.1:8875")
    api.client.close()
    api.client = FakeClient()
    with pytest.raises(phase9.Phase9Error) as error:
        api.request("GET", "/failure")
    assert "sensitive-code" not in str(error.value)
    assert "code=unknown" in str(error.value)


def test_matrix_runner_uses_and_cleans_an_isolated_database(monkeypatch, tmp_path):
    matrix_db = tmp_path / "phase9_matrix.db"
    observed = {}

    def fake_run(*_args, **kwargs):
        observed["test_db_url"] = kwargs["env"]["TEST_DB_URL"]
        matrix_db.write_text("synthetic", encoding="utf-8")
        Path(f"{matrix_db}-journal").write_text("synthetic", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="2 passed", stderr="")

    monkeypatch.setattr(phase9, "MATRIX_DB", matrix_db)
    monkeypatch.setattr(phase9.subprocess, "run", fake_run)
    monkeypatch.setattr(phase9, "_emit", lambda *_args, **_kwargs: None)

    assert phase9._run_matrix() == 0
    assert observed["test_db_url"] == (
        f"sqlite+aiosqlite:///{matrix_db.as_posix()}"
    )
    assert not matrix_db.exists()
    assert not Path(f"{matrix_db}-journal").exists()


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
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout.strip())
    assert evidence["command"] == "verify-http"
    assert evidence["counts"] == {
        "checks_failed": 0,
        "checks_passed": 11,
        "residual_tables": 0,
        "tables_observed": evidence["counts"]["tables_observed"],
    }
    assert "controlled_trial_core_journey_isolated" in evidence["transitions"]
    assert "client_incompatibility_zero_writes" in evidence["transitions"]
    assert "expired_session_blocked" in evidence["transitions"]
    combined = result.stdout + result.stderr
    for forbidden in (
        phase9.PRIMARY["credential"],
        phase9.PRIMARY["invitation_code"],
        phase9.PRIMARY["device_key"],
        phase9.CONTROL_TOKEN,
        "access_token",
        "refresh_token",
        "Authorization",
    ):
        assert forbidden not in combined
    assert not DEVICE_DB.exists()
