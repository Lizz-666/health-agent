#!/usr/bin/env python3
"""Phase 3 layered verification runner (Task 1 CI foundation).

Usage (from the repository root, on Windows or Linux):

    python scripts/verify.py fast   # ruff + SQLite backend tests + git diff --check
    python scripts/verify.py full   # ruff + complete backend tests (+ PostgreSQL 16
                                    #   when available) + git diff --check

Design contract (docs/product/roadmap.md section 13.1 and the Phase 3 plan):

- ``fast`` is the fast feedback layer: deterministic targeted lint + the backend
  test suite on SQLite (PostgreSQL-backed tests skip when no Docker/DSN is
  available - this is the designed gate, never a hidden failure).
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


def _run_pytest(mode: str) -> StepResult:
    """Run the backend suite. ``mode`` is ``fast`` or ``full``."""
    junit_path = Path(tempfile.gettempdir()) / "verify-junit.xml"
    if junit_path.exists():
        junit_path.unlink()
    env = {"PYTHONDONTWRITEBYTECODE": "1"}
    rc, out, err = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
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

    # Base success on pytest's own return code: 0 == all passed (pytest returns
    # 0 only when nothing failed/errored, regardless of skips).
    ok = rc == 0
    if not parsed:
        tail = (out + err).strip().splitlines()
        detail = "pytest produced no JUnit report:\n" + "\n".join(tail[-12:])
        return StepResult("pytest backend", ok=ok, detail=detail)

    # Full CI contract: when the caller demands PostgreSQL, ANY skip is a hard
    # failure (the guarded DSN must make every PG-backed test run).
    require_pg = os.environ.get("VERIFY_REQUIRE_PG", "").strip() == "1"
    if mode == "full" and require_pg and skipped > 0:
        ok = False

    detail = (
        f"{passed} passed, {failed} failed, {skipped} skipped "
        f"(of {total})"
    )
    if mode == "full" and require_pg:
        detail += " [VERIFY_REQUIRE_PG=1: skips are hard failures]"
    if not ok:
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
    rc, out, err = _run(
        ["git", "diff", "--check"], REPO_ROOT
    )
    tail = (out + err).strip()
    return StepResult(
        "git diff --check",
        ok=rc == 0,
        detail=tail or "clean (no whitespace errors / conflict markers)",
    )


def _print_summary(mode: str, steps: List[StepResult]) -> int:
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append(f"verify.py {mode}  (LOCAL evidence, not GitHub CI)")
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
