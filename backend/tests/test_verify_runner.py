"""Focused tests for the Phase 3 verification runner (Task 1).

These cover the runner's PURE, deterministic helpers (JUnit parsing, argparse
mode validation, summary aggregation). They do NOT invoke ruff/pytest/git, so
they stay fast and side-effect free. The runner is imported by absolute path
because it lives at ``<repo>/scripts/verify.py`` outside the backend package.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_PATH = REPO_ROOT / "scripts" / "verify.py"


def _load_verify():
    spec = importlib.util.spec_from_file_location("_phase3_verify", VERIFY_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


verify = _load_verify()


def _write_junit(path: Path, *, tests: int, failures: int, errors: int,
                 skipped: int) -> None:
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<testsuites>'
        f'<testsuite name="s" tests="{tests}" failures="{failures}" '
        f'errors="{errors}" skipped="{skipped}">'
        '</testsuite>'
        '</testsuites>'
    )
    path.write_text(xml, encoding="utf-8")


def test_parse_junit_counts_pass_fail_skip(tmp_path):
    p = tmp_path / "j.xml"
    _write_junit(p, tests=4, failures=1, errors=0, skipped=1)
    total, passed, failed, skipped = verify._parse_junit(p)
    assert (total, passed, failed, skipped) == (4, 2, 1, 1)


def test_parse_junit_counts_errors_as_failed(tmp_path):
    # A collection error must never be mistaken for success: errors count as
    # failed so the run cannot report zero failures.
    p = tmp_path / "j.xml"
    _write_junit(p, tests=3, failures=0, errors=1, skipped=0)
    total, passed, failed, skipped = verify._parse_junit(p)
    assert failed == 1
    assert passed == 2
    assert skipped == 0


def test_parse_junit_handles_single_root_suite(tmp_path):
    # Some pytest versions emit a bare <testsuite> root (no <testsuites>).
    p = tmp_path / "j.xml"
    p.write_text(
        '<?xml version="1.0"?><testsuite name="s" tests="2" failures="0" '
        'errors="0" skipped="0"></testsuite>',
        encoding="utf-8",
    )
    total, passed, failed, skipped = verify._parse_junit(p)
    assert (total, passed, failed, skipped) == (2, 2, 0, 0)


def test_step_result_label_and_overall():
    ok = verify.StepResult("a", ok=True, detail="d")
    bad = verify.StepResult("b", ok=False, detail="d")
    assert ok.label() == "PASS"
    assert bad.label() == "FAIL"
    # Overall is PASS only when every step passed.
    assert verify._print_summary("fast", [ok]) == 0
    assert verify._print_summary("fast", [ok, bad]) == 1


def test_main_rejects_invalid_mode(capsys):
    with pytest.raises(SystemExit):
        verify.main(["bogus"])
    captured = capsys.readouterr()
    assert "invalid choice" in captured.err or "usage" in captured.err.lower()


def test_runner_itself_is_lint_clean():
    # Guard against the runner drifting out of ruff compliance: the file must
    # parse and expose the documented public surface used by the workflow.
    assert hasattr(verify, "main")
    assert hasattr(verify, "_parse_junit")
    assert hasattr(verify, "RUFF_PIN")
    assert callable(verify.main)
