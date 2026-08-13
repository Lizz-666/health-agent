import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.phase9_security import (  # noqa: E402
    audit_dependencies,
    evaluate_dependency_audit,
    scan_artifact_paths,
    scan_secret_text,
)


def test_artifact_scan_allows_example_env_but_rejects_runtime_files(tmp_path):
    allowed = tmp_path / ".env.example"
    database = tmp_path / "trial.db"
    package = tmp_path / "candidate.apk"
    for path in (allowed, database, package):
        path.write_text("synthetic", encoding="utf-8")

    findings = scan_artifact_paths((allowed, database, package), tmp_path)

    assert [(item.rule_id, item.path) for item in findings] == [
        ("tracked-runtime-artifact", "trial.db"),
        ("tracked-runtime-artifact", "candidate.apk"),
    ]


def test_secret_scan_reports_rule_and_path_without_secret_value(tmp_path):
    secret = "".join(("ghp_", "A" * 36))
    path = tmp_path / "config.txt"
    path.write_text(f"token={secret}", encoding="utf-8")

    findings = scan_secret_text((path,), tmp_path)

    assert findings[0].rule_id == "github-token"
    assert findings[0].path == "config.txt"
    assert secret not in repr(findings[0])


def test_secret_scan_skips_binary_and_oversize_inputs(tmp_path):
    binary = tmp_path / "binary.bin"
    binary.write_bytes(b"\xff\xfe\xfd")
    assert scan_secret_text((binary,), tmp_path) == []

    text = tmp_path / "large.txt"
    text.write_bytes(b"x" * 2_100_000)
    assert scan_secret_text((text,), tmp_path) == []


def test_dependency_audit_requires_exact_vex_match(monkeypatch, tmp_path):
    vex = tmp_path / "vex.json"
    vex.write_text(
        '{"entries": [{"package": "starlette", "version": "0.49.3", '
        '"id": "PYSEC-synthetic"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.phase9_security.DEPENDENCY_VEX_PATH", vex)
    exact = {
        "dependencies": [
            {
                "name": "starlette",
                "version": "0.49.3",
                "vulns": [{"id": "PYSEC-synthetic"}],
            }
        ]
    }
    unexpected = {
        "dependencies": [
            {
                "name": "starlette",
                "version": "0.49.3",
                "vulns": [{"id": "PYSEC-new"}],
            }
        ]
    }

    assert evaluate_dependency_audit(exact, include_development=False) == []
    findings = evaluate_dependency_audit(unexpected, include_development=False)
    assert {finding.rule_id for finding in findings} == {
        "unexpected-vulnerability",
        "stale-vex-entry",
    }


def test_dependency_gate_rejects_platform_specific_uvicorn_extra(
    monkeypatch, tmp_path
):
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "requirements.txt").write_text(
        "uvicorn[standard]==0.39.0\n", encoding="utf-8"
    )
    for lock_name in ("requirements.lock", "requirements-dev.lock"):
        (backend / lock_name).write_text(
            "uvicorn[standard]==0.39.0\nuvloop==0.22.1\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(
        "scripts.phase9_security.verify_vex_invariants", lambda _root: []
    )
    monkeypatch.setattr(
        "scripts.phase9_security.subprocess.run",
        lambda *args, **kwargs: type(
            "Result", (), {"returncode": 0, "stdout": '{"dependencies": []}'}
        )(),
    )
    vex = tmp_path / "vex.json"
    vex.write_text('{"entries": []}', encoding="utf-8")
    monkeypatch.setattr("scripts.phase9_security.DEPENDENCY_VEX_PATH", vex)

    findings = audit_dependencies(tmp_path)

    assert "platform-specific-uvicorn-extra" in {
        finding.rule_id for finding in findings
    }
    assert "platform-specific-lock-entry" in {
        finding.rule_id for finding in findings
    }
