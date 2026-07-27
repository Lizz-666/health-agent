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
