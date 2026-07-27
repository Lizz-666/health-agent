#!/usr/bin/env python3
"""Shared layered verification runner (Phase 3 foundation, extended for Phase 4).

Usage (from the repository root, on Windows or Linux):

    python scripts/verify.py fast   # ruff + targeted backend SQLite tests + diff
    python scripts/verify.py full   # ruff + complete backend tests (+ PostgreSQL 16
                                    #   when available) + git diff --check

``FAST_TEST_TARGETS`` started as the Phase 3 backend suite. Phase 4 backend
targets are appended here by the same task that creates each test file (Tasks
2-4) so Fast CI exercises the new code as it lands, instead of referencing files
that do not yet exist. ``full`` always runs the COMPLETE backend suite, so every
Phase 4 test is covered regardless of the fast list.

Design contract (docs/product/roadmap.md section 13.1 and the Phase 3/4 plans):

- ``fast`` is the fast feedback layer: deterministic lint + targeted Phase 3
  tests on SQLite. PostgreSQL-backed cases are explicitly disabled in this
  layer and remain mandatory in Full.
- ``full`` is the integration / phase-exit layer: it runs the COMPLETE backend
  suite. When ``PG_TEST_DSN`` is set (or Docker is reachable) the real
  PostgreSQL 16 tests execute. When the caller additionally sets
  ``VERIFY_REQUIRE_PG=1`` (the Full CI contract), ANY skipped test is treated as
  a hard failure, proving the PostgreSQL path ran with zero skips under the
  guarded ``conftest_pg`` DSN contract.

Fail-closed guarantees:

- A missing required tool (``ruff``) is a HARD error with install instructions;
  it is never silently skipped.
- A failing step keeps the whole run non-zero; nothing converts a failure into a
  success summary.
- Pass / fail / skip counts come from a machine-readable JUnit report, not from
  grepping prose, so counts are exact.
- This runner reports LOCAL evidence only. It must never be described as a
  GitHub CI result; remote CI remains ``not authorized / not run`` until a user
  authorizes the first push.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"

# ``ruff`` is not in backend/requirements.txt (it is a dev/CI tool, kept out of
# the runtime dependency set by design). CI installs this exact pinned version;
# locally the runner only requires that SOME ruff answers ``--version``.
RUFF_PIN = "0.15.22"
FAST_TEST_TARGETS = [
    "tests/test_training_schema.py",
    "tests/test_training_sources.py",
    "tests/test_training_catalog.py",
    "tests/test_training_context.py",
    "tests/test_training_safety.py",
    "tests/test_training_policy.py",
    "tests/test_training_candidates.py",
    "tests/test_training_properties.py",
    "tests/test_training_validator.py",
    "tests/test_training_tools.py",
    "tests/test_training_integration.py",
    "tests/test_phase3_e2e.py",
    "tests/test_verify_runner.py",
    "tests/test_ci_action_pins.py",
    "tests/test_training_plan_state.py",
    "tests/test_training_plan_persistence.py",
    "tests/test_training_plan_migrations.py",
    "tests/test_training_generator.py",
    "tests/test_training_api.py",
]


class StepResult:
    """Outcome of one verification step."""

    def __init__(
        self,
        name: str,
        ok: bool,
        detail: str,
        passed: Optional[int] = None,
        failed: Optional[int] = None,
        skipped: Optional[int] = None,
    ) -> None:
        self.name = name
        self.ok = ok
        self.detail = detail
        self.passed = passed
        self.failed = failed
        self.skipped = skipped

    def label(self) -> str:
        return "PASS" if self.ok else "FAIL"


def _run(
    cmd: List[str],
    cwd: Path,
    env: Optional[dict] = None,
) -> Tuple[int, str, str]:
    """Run ``cmd`` and return (returncode, stdout, stderr)."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=merged_env,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _ensure_ruff() -> StepResult:
    """Fail closed if ``ruff`` is not importable as a module."""
    rc, out, _ = _run([sys.executable, "-m", "ruff", "--version"], REPO_ROOT)
    if rc != 0:
        return StepResult(
            "ruff available",
            ok=False,
            detail=(
                "ruff is not installed. Install the pinned dev tool: "
                f"pip install ruff=={RUFF_PIN}"
            ),
        )
    return StepResult("ruff available", ok=True, detail=out.strip())


def _run_ruff() -> StepResult:
    """Lint backend ``app``/``tests`` (existing convention) plus this script."""
    targets = ["app", "tests"]
    rc, out, err = _run(
        [sys.executable, "-m", "ruff", "check", *targets], BACKEND_DIR
    )
    backend_tail = out.strip() or err.strip()
    # Also lint the runner itself so scripts/ stays clean.
    rc_scripts, out_s, err_s = _run(
        [sys.executable, "-m", "ruff", "check", "scripts"], REPO_ROOT
    )
    scripts_tail = out_s.strip() or err_s.strip()
    ok = rc == 0 and rc_scripts == 0
    detail = backend_tail
    if not ok:
        detail = f"backend/app+tests:\n{backend_tail}\nscripts:\n{scripts_tail}"
    elif backend_tail == "All checks passed!":
        detail = "backend app+tests + scripts: All checks passed!"
    return StepResult("ruff check", ok=ok, detail=detail)


def _parse_junit(path: Path) -> Tuple[int, int, int, int]:
    """Return (total, passed, failed_or_errored, skipped) from a JUnit XML.

    ``failed_or_errored`` counts both <failure> and <error> outcomes so a
    collection error is never mistaken for success.
    """
    total = passed = failed = skipped = 0
    tree = ET.parse(path)
    root = tree.getroot()
    suites = root.findall("testsuite") if root.tag == "testsuites" else [root]
    for suite in suites:
        total += int(suite.get("tests", "0"))
        failed += int(suite.get("failures", "0")) + int(
            suite.get("errors", "0")
        )
        skipped += int(suite.get("skipped", "0"))
    passed = max(total - failed - skipped, 0)
    return total, passed, failed, skipped


def _first_junit_error(path: Path) -> str:
    """Return the first actionable failure/error from a JUnit report."""
    root = ET.parse(path).getroot()
    for case in root.iter("testcase"):
        problem = case.find("failure")
        if problem is None:
            problem = case.find("error")
        if problem is not None:
            node = "::".join(filter(None, (
                case.get("classname"), case.get("name"))))
            message = (problem.get("message") or problem.text or "").strip()
            first_line = message.splitlines()[0] if message else "test failed"
            return f"first failure: {node}: {first_line[:500]}"
    return ""


def _collect_expected_pg_tests(env: dict) -> Tuple[bool, int, str]:
    """Collect the explicitly marked PostgreSQL tests before Full execution."""
    rc, out, err = _run(
        [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q",
         "-m", "requires_pg"],
        BACKEND_DIR,
        env=env,
    )
    nodeids = {
        line.strip() for line in out.splitlines()
        if "::" in line and line.strip().startswith("tests/")
    }
    detail = (out + err).strip()
    return rc == 0 and bool(nodeids), len(nodeids), detail


def _run_pytest(mode: str) -> StepResult:
    """Run the backend suite. ``mode`` is ``fast`` or ``full``."""
    junit_path = Path(tempfile.gettempdir()) / "verify-junit.xml"
    if junit_path.exists():
        junit_path.unlink()
    env = {"PYTHONDONTWRITEBYTECODE": "1"}
    targets = ["tests"] if mode == "full" else FAST_TEST_TARGETS
    if mode == "fast":
        env["VERIFY_SKIP_PG"] = "1"
    require_pg = (
        mode == "full"
        and os.environ.get("VERIFY_REQUIRE_PG", "").strip() == "1"
    )
    pg_evidence_path = Path(tempfile.gettempdir()) / "verify-pg-evidence.txt"
    if require_pg:
        if pg_evidence_path.exists():
            pg_evidence_path.unlink()
        env["PG_TEST_EVIDENCE_FILE"] = str(pg_evidence_path)
        collected, expected_pg, collection_detail = _collect_expected_pg_tests(env)
        if not collected:
            return StepResult(
                "pytest backend", ok=False,
                detail=("PostgreSQL test collection failed or found no "
                        "requires_pg tests:\n" + collection_detail[-2000:]),
            )
    else:
        expected_pg = 0
    rc, out, err = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            *targets,
            "-q",
            f"--junitxml={junit_path}",
        ],
        BACKEND_DIR,
        env=env,
    )
    total = passed = failed = skipped = 0
    parsed = False
    if junit_path.exists():
        try:
            total, passed, failed, skipped = _parse_junit(junit_path)
            parsed = True
        except ET.ParseError:
            parsed = False

    ok = rc == 0 and parsed
    if not parsed:
        tail = (out + err).strip().splitlines()
        detail = "pytest produced no JUnit report:\n" + "\n".join(tail[-12:])
        return StepResult("pytest backend", ok=False, detail=detail)

    # Full CI contract: when the caller demands PostgreSQL, ANY skip is a hard
    # failure (the guarded DSN must make every PG-backed test run).
    pg_actual = 0
    pg_version_present = False
    if require_pg and pg_evidence_path.exists():
        evidence = pg_evidence_path.read_text(encoding="utf-8").splitlines()
        pg_actual = len({line[5:] for line in evidence if line.startswith("TEST:")})
        pg_version_present = any(line.startswith("VERSION:") for line in evidence)
    if require_pg and (
        skipped > 0 or not pg_version_present or pg_actual != expected_pg
    ):
        ok = False

    detail = (
        f"{passed} passed, {failed} failed, {skipped} skipped "
        f"(of {total})"
    )
    if require_pg:
        detail += (
            " [VERIFY_REQUIRE_PG=1: skips are hard failures; "
            f"PostgreSQL expected={expected_pg} actual={pg_actual} "
            f"version_evidence={'present' if pg_version_present else 'MISSING'}]"
        )
    if not ok:
        first_error = _first_junit_error(junit_path)
        if first_error:
            detail += "\n" + first_error
        tail = (out + err).strip().splitlines()
        detail += "\n" + "\n".join(tail[-20:])
    return StepResult(
        "pytest backend",
        ok=ok,
        detail=detail,
        passed=passed,
        failed=failed,
        skipped=skipped,
    )


def _run_git_diff_check() -> StepResult:
    commands = [
        ["git", "diff", "--check"],
        ["git", "diff", "--cached", "--check"],
    ]
    diff_base = _resolve_diff_base(
        os.environ.get("VERIFY_DIFF_BASE", "").strip())
    commands.append(
        ["git", "diff", "--check", f"{diff_base}...HEAD"]
        if diff_base
        else ["git", "show", "--check", "--format=", "HEAD"]
    )
    outputs = []
    ok = True
    for command in commands:
        rc, out, err = _run(command, REPO_ROOT)
        ok = ok and rc == 0
        if (out + err).strip():
            outputs.append((out + err).strip())
    tail = "\n".join(outputs)
    return StepResult(
        "git candidate diff --check",
        ok=ok,
        detail=tail or "working, staged, and candidate diff are clean",
    )


def _resolve_diff_base(diff_base: str) -> str:
    """Resolve GitHub's all-zero first-push base to a real fetched ref."""
    if diff_base and set(diff_base) == {"0"}:
        default_branch = os.environ.get("VERIFY_DEFAULT_BRANCH", "").strip()
        candidate = f"origin/{default_branch}" if default_branch else ""
        if candidate:
            rc, _, _ = _run(
                ["git", "rev-parse", "--verify", candidate], REPO_ROOT)
            if rc == 0:
                return candidate
        return "HEAD^"
    return diff_base


def _print_summary(mode: str, steps: List[StepResult]) -> int:
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append(f"verify.py {mode}  (LOCAL evidence, not GitHub CI)")
    lines.append(
        f"workflow={os.environ.get('GITHUB_WORKFLOW', 'local')} "
        f"sha={os.environ.get('GITHUB_SHA', 'local')} "
        f"job={os.environ.get('GITHUB_JOB', 'local')}"
    )
    lines.append(
        f"diff_base={_resolve_diff_base(os.environ.get('VERIFY_DIFF_BASE', '').strip()) or 'HEAD'} "
        f"artifact={os.environ.get('VERIFY_ARTIFACT_NAME', 'none')}"
    )
    lines.append("=" * 72)
    for s in steps:
        counts = ""
        if s.passed is not None:
            counts = (
                f"  [passed={s.passed} failed={s.failed} skipped={s.skipped}]"
            )
        lines.append(f"[{s.label()}] {s.name}{counts}")
        for line in s.detail.splitlines():
            lines.append(f"      {line}")
    overall = all(s.ok for s in steps)
    lines.append("-" * 72)
    lines.append(f"OVERALL: {'PASS' if overall else 'FAIL'}")
    lines.append("=" * 72)
    report = "\n".join(lines)
    print(report)

    summary_file = os.environ.get("VERIFY_SUMMARY_FILE", "").strip()
    if summary_file:
        Path(summary_file).write_text(report, encoding="utf-8")
    return 0 if overall else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 3 layered verification runner."
    )
    parser.add_argument(
        "mode",
        choices=["fast", "full"],
        help="fast = lint + SQLite tests; full = lint + complete tests (+PG).",
    )
    args = parser.parse_args(argv)

    ruff_gate = _ensure_ruff()
    if not ruff_gate.ok:
        return _print_summary(args.mode, [ruff_gate])

    steps: List[StepResult] = [ruff_gate, _run_ruff(), _run_pytest(args.mode)]
    steps.append(_run_git_diff_check())
    return _print_summary(args.mode, steps)


if __name__ == "__main__":
    sys.exit(main())
