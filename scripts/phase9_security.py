#!/usr/bin/env python3
"""Fail-closed Phase 9 repository secret and artifact checks.

Only tracked files are inspected. Findings report a rule id and path, never
the matched value. Dependency vulnerability checks remain a separate pinned
``pip-audit`` CI step so this script does not contact external services.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEPENDENCY_VEX_PATH = REPO_ROOT / "docs" / "security" / "phase9-dependency-vex.json"
MAX_TEXT_FILE_BYTES = 2 * 1024 * 1024

FORBIDDEN_FILENAMES = frozenset({".env"})
FORBIDDEN_SUFFIXES = frozenset(
    {
        ".aab",
        ".apk",
        ".db",
        ".jks",
        ".key",
        ".keystore",
        ".log",
        ".p12",
        ".pem",
        ".pfx",
        ".sqlite",
        ".sqlite3",
    }
)

SECRET_PATTERNS = (
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("openai-token", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "jwt",
        re.compile(
            r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."
            r"[A-Za-z0-9_-]{10,}"
        ),
    ),
)


@dataclass(frozen=True)
class Finding:
    rule_id: str
    path: str


def repository_files(repo_root: Path = REPO_ROOT) -> List[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return [
        repo_root / raw.decode("utf-8", errors="strict")
        for raw in result.stdout.split(b"\0")
        if raw
    ]


def scan_artifact_paths(
    paths: Iterable[Path], repo_root: Path = REPO_ROOT
) -> List[Finding]:
    findings: List[Finding] = []
    for path in paths:
        relative = path.relative_to(repo_root).as_posix()
        lower_name = path.name.casefold()
        if lower_name in FORBIDDEN_FILENAMES:
            findings.append(Finding("tracked-sensitive-filename", relative))
        elif path.suffix.casefold() in FORBIDDEN_SUFFIXES:
            findings.append(Finding("tracked-runtime-artifact", relative))
    return findings


def scan_secret_text(
    paths: Iterable[Path], repo_root: Path = REPO_ROOT
) -> List[Finding]:
    findings: List[Finding] = []
    for path in paths:
        try:
            if not path.is_file() or path.stat().st_size > MAX_TEXT_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative = path.relative_to(repo_root).as_posix()
        for rule_id, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(Finding(rule_id, relative))
    return findings


def verify(repo_root: Path = REPO_ROOT) -> Sequence[Finding]:
    paths = repository_files(repo_root)
    findings = scan_artifact_paths(paths, repo_root)
    findings.extend(scan_secret_text(paths, repo_root))
    return sorted(set(findings), key=lambda item: (item.path, item.rule_id))


def verify_vex_invariants(repo_root: Path = REPO_ROOT) -> List[Finding]:
    try:
        vex = json.loads(DEPENDENCY_VEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [Finding("invalid-vex", DEPENDENCY_VEX_PATH.relative_to(repo_root).as_posix())]
    entries = vex.get("entries")
    if not isinstance(entries, list) or not entries:
        return [Finding("invalid-vex", DEPENDENCY_VEX_PATH.relative_to(repo_root).as_posix())]

    app_files = list((repo_root / "backend" / "app").rglob("*.py"))
    app_text = "\n".join(path.read_text(encoding="utf-8") for path in app_files)
    expected_ids = {
        "PYSEC-2026-1845",
        "PYSEC-2026-161",
        "PYSEC-2026-248",
        "PYSEC-2026-249",
        "PYSEC-2026-2281",
        "PYSEC-2026-2280",
    }
    actual_ids = {entry.get("id") for entry in entries}
    findings: List[Finding] = []
    if actual_ids != expected_ids:
        findings.append(Finding("vex-id-drift", "docs/security/phase9-dependency-vex.json"))

    runtime_requirements = (repo_root / "backend" / "requirements.txt").read_text(
        encoding="utf-8"
    )
    invariant_failures = {
        "pytest_is_not_runtime_dependency": re.search(
            r"^pytest==", runtime_requirements, re.MULTILINE
        )
        is not None,
        "no_request_url_in_runtime_code": "request.url" in app_text,
        "no_form_parser_in_runtime_code": bool(
            re.search(r"request\.form\(|\bForm\(|\bUploadFile\b|\bFile\(", app_text)
        ),
        "no_staticfiles_in_runtime_code": "StaticFiles" in app_text,
        "no_httpendpoint_in_runtime_code": bool(
            re.search(r"\bHTTPEndpoint\b|\bRoute\(", app_text)
        ),
    }
    for entry in entries:
        if entry.get("status") != "not_affected":
            findings.append(Finding("vex-status-not-closed", str(entry.get("id"))))
            continue
        invariant = entry.get("invariant")
        if invariant not in invariant_failures:
            findings.append(Finding("unknown-vex-invariant", str(entry.get("id"))))
        elif invariant_failures[invariant]:
            findings.append(Finding("vex-invariant-failed", str(entry.get("id"))))
    return findings


def _audited_vulnerabilities(payload: dict[str, Any]) -> set[tuple[str, str, str]]:
    return {
        (dependency["name"].casefold(), dependency["version"], vulnerability["id"])
        for dependency in payload.get("dependencies", [])
        for vulnerability in dependency.get("vulns", [])
    }


def evaluate_dependency_audit(
    payload: dict[str, Any], *, include_development: bool
) -> List[Finding]:
    vex = json.loads(DEPENDENCY_VEX_PATH.read_text(encoding="utf-8"))
    expected = {
        (entry["package"].casefold(), entry["version"], entry["id"])
        for entry in vex["entries"]
        if include_development or entry["package"].casefold() != "pytest"
    }
    actual = _audited_vulnerabilities(payload)
    findings: List[Finding] = []
    for package, version, advisory in sorted(actual - expected):
        findings.append(
            Finding("unexpected-vulnerability", f"{package}@{version}:{advisory}")
        )
    for package, version, advisory in sorted(expected - actual):
        findings.append(
            Finding("stale-vex-entry", f"{package}@{version}:{advisory}")
        )
    return findings


def audit_dependencies(repo_root: Path = REPO_ROOT) -> List[Finding]:
    findings = verify_vex_invariants(repo_root)
    runtime_input = (repo_root / "backend" / "requirements.txt").read_text(
        encoding="utf-8"
    ).casefold()
    if "uvicorn[standard]" in runtime_input:
        findings.append(Finding("platform-specific-uvicorn-extra", "requirements.txt"))
    for lock_name, include_development in (
        ("requirements.lock", False),
        ("requirements-dev.lock", True),
    ):
        lock_text = (repo_root / "backend" / lock_name).read_text(
            encoding="utf-8"
        ).casefold()
        if "uvicorn==0.39.0" not in lock_text:
            findings.append(Finding("uvicorn-lock-mismatch", lock_name))
        for optional_dependency in ("uvloop", "httptools", "watchfiles", "websockets"):
            if re.search(rf"^{optional_dependency}==", lock_text, re.MULTILINE):
                findings.append(
                    Finding("platform-specific-lock-entry", f"{lock_name}:{optional_dependency}")
                )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "-r",
                str(repo_root / "backend" / lock_name),
                "--no-deps",
                "--disable-pip",
                "--progress-spinner",
                "off",
                "--timeout",
                "30",
                "--format",
                "json",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if result.returncode not in (0, 1):
            findings.append(Finding("dependency-audit-unavailable", lock_name))
            continue
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            findings.append(Finding("dependency-audit-invalid", lock_name))
            continue
        findings.extend(
            evaluate_dependency_audit(
                payload,
                include_development=include_development,
            )
        )
    return findings


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify", "dependencies"))
    args = parser.parse_args(argv)

    try:
        if args.command == "verify":
            findings = list(verify())
            findings.extend(verify_vex_invariants())
            label = "tracked secrets/artifacts and VEX invariants"
        else:
            findings = audit_dependencies()
            label = "dependency audit and exact VEX reconciliation"
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"phase9 security scan failed closed: {type(exc).__name__}")
        return 2
    if findings:
        print(f"phase9 security scan: FAIL ({len(findings)} finding(s))")
        for finding in findings:
            print(f"- rule={finding.rule_id} path={finding.path}")
        return 1
    print(f"phase9 security scan: PASS ({label})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
