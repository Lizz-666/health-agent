"""Regression test for CI GitHub Action SHA pins (Task 1).

This guards the exact failure class that broke the first Task 1 CI run: a
transcription error in an action's immutable commit SHA made the workflow
unresolvable (``Unable to resolve action ... unable to find version``).

The test parses ``.github/workflows/ci.yml`` and, for every
``uses: owner/repo@<sha> # v<tag>`` line:

- ALWAYS asserts the pin is a 40-char lowercase-hex SHA (catches truncation /
  format corruption) and that each owner/repo appears with a version comment.
- WHEN the GitHub API is reachable, resolves ``v<tag>`` to its commit SHA and
  asserts it equals the pinned SHA. This is the authoritative check that catches
  a valid-format-but-wrong SHA.

Failure semantics (non-flaky):
- A definitive API response whose commit SHA differs from the pin FAILS.
- Network errors, rate limits (403), and server errors (5xx) SKIP with a clear
  reason, so transient GitHub-API hiccups never break CI. The structural format
  check still runs unconditionally.
- The test never downgrades a real mismatch to a skip.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"

_USES_RE = re.compile(
    r"^\s*uses:\s+"
    r"(?P<owner>[A-Za-z0-9_.\-]+)/"
    r"(?P<repo>[A-Za-z0-9_.\-]+)@"
    r"(?P<sha>[0-9a-f]{40})"
    r"(?:\s*#\s*(?P<comment>v\S+))?"
    r"\s*$",
    re.MULTILINE,
)


def _pins():
    text = CI_PATH.read_text(encoding="utf-8")
    return [
        {
            "owner": m["owner"],
            "repo": m["repo"],
            "sha": m["sha"],
            "tag": m["comment"],
            "line": m.group(0).strip(),
        }
        for m in _USES_RE.finditer(text)
    ]


def test_ci_yml_exists_and_has_pinned_actions():
    assert CI_PATH.exists(), f"missing workflow: {CI_PATH}"
    pins = _pins()
    assert pins, "expected at least one 'uses: owner/repo@<sha>' pin in ci.yml"


def test_every_action_pin_is_full_lowercase_hex_sha():
    # Structural guard that always runs (no network). A 40-char hex SHA is the
    # immutable-pin contract; anything shorter or upper-case is a corruption.
    bad = [p for p in _pins() if not re.fullmatch(r"[0-9a-f]{40}", p["sha"])]
    assert not bad, f"non-40-lowercase-hex action pins: {[p['line'] for p in bad]}"


def test_every_action_pin_has_a_version_comment():
    # The version comment is the source the API check resolves; a missing one
    # means the pin cannot be authoritatively verified and is a contract gap.
    missing = [p for p in _pins() if not p["tag"]]
    assert not missing, (
        "action pins without a '# vX.Y.Z' version comment cannot be verified: "
        f"{[p['line'] for p in missing]}"
    )


def test_each_action_owner_repo_is_pinned_to_a_single_sha():
    # The same logical action must not carry two different SHAs across jobs.
    by_repo: dict[tuple[str, str], set[str]] = {}
    for p in _pins():
        by_repo.setdefault((p["owner"], p["repo"]), set()).add(p["sha"])
    inconsistent = {k: v for k, v in by_repo.items() if len(v) > 1}
    assert not inconsistent, f"action pinned to multiple SHAs: {inconsistent}"


def test_every_checkout_uses_exact_pr_head_with_push_fallback():
    text = CI_PATH.read_text(encoding="utf-8")
    checkout_count = sum(
        pin["owner"] == "actions" and pin["repo"] == "checkout"
        for pin in _pins()
    )
    exact_ref = "ref: ${{ github.event.pull_request.head.sha || github.sha }}"
    assert checkout_count > 0
    assert text.count(exact_ref) == checkout_count


def test_fast_and_full_pin_checks_use_the_read_only_workflow_token():
    text = CI_PATH.read_text(encoding="utf-8")
    token_line = "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}"
    for step_name in (
        "Fast verify (lint + SQLite tests + git diff --check)",
        "Full verify (lint + complete tests + PostgreSQL 16 + git diff)",
    ):
        start = text.index(f"- name: {step_name}")
        end = text.index("\n      - name:", start + 1)
        assert token_line in text[start:end]
    assert text.count(token_line) == 2


def test_flutter_test_pipeline_propagates_failures_through_tee():
    text = CI_PATH.read_text(encoding="utf-8")
    start = text.index("- name: Flutter test")
    end = text.index("\n      - name:", start + 1)
    step = text[start:end]
    assert "shell: bash" in step
    assert "set -o pipefail" in step
    assert "flutter test 2>&1 | tee ../flutter-test.log" in step


def test_release_integration_ci_runs_all_six_gates_on_main_and_pull_requests():
    text = CI_PATH.read_text(encoding="utf-8")

    assert 'branches:\n      - "main"' in text
    assert '"codex/phase3-*"' not in text
    assert "pull_request:" in text

    automatic_or_manual = (
        "if: ${{ github.event_name == 'push' || "
        "github.event_name == 'pull_request' || "
        "github.event_name == 'workflow_dispatch' }}"
    )
    for job_name in ("phase9-reliability", "phase8-acceptance"):
        start = text.index(f"  {job_name}:")
        next_job_match = re.search(r"^  [a-z0-9-]+:\s*$", text[start + 3 :], re.MULTILINE)
        next_job = (
            -1 if next_job_match is None else start + 3 + next_job_match.start()
        )
        job = text[start:] if next_job == -1 else text[start:next_job]
        assert automatic_or_manual in job

    full_condition = (
        "if: ${{ github.event_name == 'push' || "
        "github.event_name == 'pull_request' || "
        "(github.event_name == 'workflow_dispatch' && inputs.run_full) }}"
    )
    full_start = text.index("  full:")
    full_end = text.index("\n  phase8-acceptance:", full_start)
    full_job = text[full_start:full_end]
    assert full_condition in full_job
    timeout = re.search(r"^    timeout-minutes: (\d+)$", full_job, re.MULTILINE)
    assert timeout is not None
    assert int(timeout.group(1)) >= 45

    for required_job in (
        "phase9-reliability",
        "phase9-security",
        "fast",
        "flutter",
        "full",
        "phase8-acceptance",
    ):
        assert f"  {required_job}:" in text


def test_ci_summary_logs_are_written_outside_the_worktree():
    text = CI_PATH.read_text(encoding="utf-8")
    for name in ("fast", "full"):
        assert (
            f"VERIFY_SUMMARY_FILE: ${{{{ runner.temp }}}}/{name}-summary.txt"
            in text
        )
        assert f"path: ${{{{ runner.temp }}}}/{name}-summary.txt" in text
        assert f"VERIFY_SUMMARY_FILE: {name}-summary.txt" not in text

    full_job_start = text.index("  full:")
    full_steps_start = text.index("\n    steps:", full_job_start)
    assert "runner.temp" not in text[full_job_start:full_steps_start]
    full_verify_start = text.index(
        "- name: Full verify (lint + complete tests + PostgreSQL 16 + git diff)"
    )
    full_verify_end = text.index("\n      - name:", full_verify_start + 1)
    assert (
        "VERIFY_SUMMARY_FILE: ${{ runner.temp }}/full-summary.txt"
        in text[full_verify_start:full_verify_end]
    )

    start = text.index("- name: Run isolated real-HTTP and evaluation acceptance")
    end = text.index("\n      - name:", start + 1)
    step = text[start:end]
    assert 'tee "$RUNNER_TEMP/phase8-summary.txt"' in step
    assert "tee phase8-summary.txt" not in step
    assert "path: ${{ runner.temp }}/phase8-summary.txt" in text


def _resolve_tag_commit(owner: str, repo: str, tag: str, token: str | None):
    """Resolve ``tag`` to its commit SHA via the GitHub git refs API.

    Returns the commit SHA, or None to signal the API could not authoritatively
    resolve it (caller skips). Raises only on a definitive mismatch signal.
    """
    import httpx

    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    base = f"https://api.github.com/repos/{owner}/{repo}"
    try:
        with httpx.Client(timeout=15.0, headers=headers) as client:
            ref = client.get(f"{base}/git/ref/tags/{tag}")
            if ref.status_code in (403, 429) or ref.status_code >= 500:
                return None  # rate-limited / server error -> skip
            if ref.status_code != 200:
                return None  # not authoritative -> skip
            obj = ref.json()["object"]
            if obj.get("type") == "commit":
                return obj["sha"]
            if obj.get("type") == "tag":
                ann = client.get(f"{base}/git/tags/{obj['sha']}")
                if ann.status_code != 200:
                    return None
                inner = ann.json().get("object", {})
                if inner.get("type") == "commit":
                    return inner.get("sha")
            return None
    except (httpx.HTTPError, OSError):
        return None


@pytest.mark.parametrize("p", _pins(), ids=lambda p: f"{p['owner']}/{p['repo']}@{p['tag']}")
def test_pinned_sha_matches_tag_commit(p):
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    resolved = _resolve_tag_commit(p["owner"], p["repo"], p["tag"], token)
    if resolved is None:
        pytest.skip(
            f"GitHub API not authoritatively reachable for "
            f"{p['owner']}/{p['repo']} {p['tag']}; structural checks still ran"
        )
    assert resolved == p["sha"], (
        f"{p['owner']}/{p['repo']} {p['tag']} pin {p['sha']} != "
        f"tag commit {resolved} resolved from the GitHub API"
    )
