#!/usr/bin/env python3
"""Synthetic-only Phase 8 localhost acceptance runner.

The runner never prints credentials, JWTs, health values, request payloads, or
response bodies. Production applications cannot select this test server.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import httpx


REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
DEVICE_DB = BACKEND_DIR / "phase8_acceptance.db"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
EVAL_TIMEOUT_SECONDS = 180
CYCLE_TIMEZONE = "Asia/Shanghai"
CONTROL_HEADER = "X-Phase8-Control-Token"
CONTROL_TOKEN = "phase8-local-control-only"
SYNTHETIC_PHONE = "13900000008"
SYNTHETIC_PASSWORD = "synthetic-phase8-only"
EXPECTED_HEALTH = {"status": "ok", "mode": "synthetic-phase8-test"}
SAFE_ERROR_CODES = frozenset({
    "service_unavailable",
    "restricted_no_plan",
    "red_flag_stop",
    "clarification_required",
    "no_eligible_candidates",
    "insufficient_candidates_for_frequency",
    "agent_consent_required",
    "agent_privacy_gate_blocked",
    "phase8_control_forbidden",
})


class Phase8Error(RuntimeError):
    """Fail-closed acceptance error with no sensitive response content."""


def _journey_schedule(now: Optional[datetime] = None) -> tuple[str, int]:
    """Select an existing scheduled day without changing the server clock."""
    current = now or datetime.now(timezone.utc)
    frequency_by_weekday = {1: 3, 2: 2, 3: 3, 4: 5, 5: 2, 7: 5}
    for zone_name in ("Asia/Shanghai", "Pacific/Kiritimati", "Etc/GMT+12"):
        weekday = current.astimezone(ZoneInfo(zone_name)).isoweekday()
        frequency = frequency_by_weekday.get(weekday)
        if frequency is not None:
            return zone_name, frequency
    raise Phase8Error("no supported scheduled local day is available")


TIMEZONE, JOURNEY_FREQUENCY = _journey_schedule()


def _head_sha() -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode != 0:
        raise Phase8Error("exact Git SHA cannot be bound to a verified worktree")
    if status.stdout.strip():
        raise Phase8Error("Phase 8 evidence requires a clean Git worktree")

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    value = result.stdout.strip()
    if result.returncode != 0 or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise Phase8Error("exact Git SHA is unavailable")
    return value


def _emit(
    command: str,
    *,
    checkpoint: str,
    transitions: List[str],
    counts: Dict[str, int],
) -> None:
    print(json.dumps({
        "command": command,
        "sha": _head_sha(),
        "checkpoint": checkpoint,
        "transitions": transitions,
        "counts": counts,
    }, sort_keys=True))


def _base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _local_date() -> str:
    return datetime.now(timezone.utc).astimezone(ZoneInfo(TIMEZONE)).date().isoformat()


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def _validate_local_url(base_url: str) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise Phase8Error("Phase 8 accepts HTTP localhost targets only")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise Phase8Error("Phase 8 base URL contains forbidden components")


class Api:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        _validate_local_url(base_url)
        self.client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            trust_env=False,
        )

    def close(self) -> None:
        self.client.close()

    def json(
        self,
        method: str,
        path: str,
        *,
        expected: int = 200,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            response = self.client.request(method, path, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise Phase8Error(
                f"request failed method={method} path={path} type={type(exc).__name__}"
            ) from exc
        if response.status_code != expected:
            code = "unknown"
            try:
                parsed = response.json()
                candidate = parsed.get("code") if isinstance(parsed, dict) else None
                if isinstance(candidate, str) and candidate in SAFE_ERROR_CODES:
                    code = candidate
            except (ValueError, TypeError):
                pass
            raise Phase8Error(
                f"unexpected response method={method} path={path} "
                f"status={response.status_code} code={code}"
            )
        try:
            value = response.json()
        except ValueError as exc:
            raise Phase8Error(
                f"invalid JSON method={method} path={path} status={response.status_code}"
            ) from exc
        if not isinstance(value, dict):
            raise Phase8Error(f"non-object JSON method={method} path={path}")
        return value


def _control_headers() -> Dict[str, str]:
    return {CONTROL_HEADER: CONTROL_TOKEN}


def _auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def assert_phase8_server(api: Api) -> None:
    health = api.json("GET", "/health")
    if health != EXPECTED_HEALTH:
        raise Phase8Error("target is not the exact synthetic Phase 8 server mode")


def reset(api: Api, checkpoint: str) -> Dict[str, Any]:
    return api.json(
        "POST",
        "/__phase8/reset",
        headers=_control_headers(),
        body={"checkpoint": checkpoint},
    )


def _fault(api: Api, route: str, kind: str) -> None:
    installed = api.json(
        "POST",
        "/__phase8/faults",
        headers=_control_headers(),
        body={"route": route, "kind": kind},
    )
    if installed.get("status") != "installed":
        raise Phase8Error("fault control did not confirm installation")


def _login(api: Api) -> str:
    result = api.json(
        "POST",
        "/api/v1/auth/dev-login",
        body={"phone": SYNTHETIC_PHONE, "password": SYNTHETIC_PASSWORD},
    )
    token = result.get("access_token")
    if not isinstance(token, str) or not token:
        raise Phase8Error("dev login returned no access token")
    return token


def _posture_journey(api: Api, headers: Dict[str, str]) -> None:
    assessed = api.json(
        "POST",
        "/api/v1/posture/assess",
        headers=headers,
        body={"issue_id": "LL-18", "test_index": 0, "answer": "positive"},
    )
    if assessed.get("result") not in {"moderate", "severe"}:
        raise Phase8Error("posture assessment returned an unsupported state")
    priorities = api.json("GET", "/api/v1/posture/priorities", headers=headers)
    candidates = priorities.get("normal_candidates")
    if not isinstance(candidates, list) or not candidates:
        raise Phase8Error("posture priorities produced no confirmable candidate")
    candidate = next(
        (item for item in candidates if item.get("issue_id") == "LL-18"), None
    )
    if not isinstance(candidate, dict):
        raise Phase8Error("expected posture candidate is unavailable")
    confirmed = api.json(
        "POST",
        "/api/v1/posture/goals/confirm",
        headers=headers,
        body={
            "suggestion_id": priorities.get("suggestion_id"),
            "profile_version": priorities.get("profile_version"),
            "goals": [{"issue_id": "LL-18", "priority_rank": 1}],
            "idempotency_key": "phase8-http-posture-confirm",
        },
    )
    if confirmed.get("can_generate_plan") is not True:
        raise Phase8Error("posture confirmation did not authorize plan generation")


def _health_journey(api: Api, headers: Dict[str, str]) -> None:
    profile = api.json(
        "PUT",
        "/api/v1/health/profile",
        headers=headers,
        body={
            "fitness_goal": "fat_loss",
            "training_experience": "beginner",
            "weekly_frequency": JOURNEY_FREQUENCY,
            "session_duration_minutes": 30,
            "equipment": {"bodyweight": True, "resistance_band": False},
            "pain_injury_limitations": [],
            "risk_screen": {
                "underage": "no",
                "pregnancy_or_postpartum": "no",
                "recent_surgery_or_major_injury": "no",
                "major_chronic_condition": "no",
                "eating_disorder_concern": "no",
                "professional_instruction_limitations": "no",
            },
            "allergies": [],
            "diet_exclusions": [],
            "food_allergen_codes": [],
            "excluded_food_codes": [],
        },
    )
    readiness = profile.get("readiness")
    if not isinstance(readiness, dict) or readiness.get("readiness") != "ready":
        raise Phase8Error("synthetic health profile did not remain ready")
    checkin = api.json(
        "PUT",
        "/api/v1/health/checkins/today",
        headers=headers,
        body={
            "local_date": _local_date(),
            "sleep_quality": "good",
            "energy": "normal",
            "muscle_soreness": "mild",
            "available_time": "30_min",
            "daily_status": "checked_in",
            "abnormal_pain": False,
        },
    )
    if checkin.get("risk_summary") != "normal":
        raise Phase8Error("synthetic normal check-in did not remain normal")
    api.json(
        "POST",
        "/api/v1/health/weight-records",
        headers=headers,
        body={
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "weight_kg": 70.0,
        },
    )
    trend = api.json(
        "GET", "/api/v1/health/trends/weight?window=2", headers=headers
    )
    if trend.get("sufficient") is not False or len(trend.get("records", [])) != 1:
        raise Phase8Error("weight trend did not preserve insufficient-data state")
    local_date = _local_date()
    grid = api.json(
        "GET",
        f"/api/v1/health/activity-grid?start_date={local_date}&end_date={local_date}",
        headers=headers,
    )
    cells = grid.get("cells")
    if not isinstance(cells, list) or len(cells) != 1 or cells[0].get("status") != "checked_in":
        raise Phase8Error("activity grid did not read back the check-in")


def _training_journey(api: Api, headers: Dict[str, str]) -> str:
    plan_body = {
        "fitness_goal": "fat_loss",
        "weekly_frequency": JOURNEY_FREQUENCY,
        "session_duration_minutes": 30,
        "equipment_bodyweight": True,
        "equipment_resistance_band": False,
        "iana_timezone": TIMEZONE,
        "idempotency_key": "phase8-http-plan-draft",
    }
    draft = api.json(
        "POST", "/api/v1/training/plans:draft", headers=headers, body=plan_body
    )
    draft_plan = draft.get("draft")
    if draft.get("has_draft") is not True or not isinstance(draft_plan, dict):
        raise Phase8Error("training draft was not generated")
    before_confirm = api.json(
        "GET", "/api/v1/training/plans/active", headers=headers
    )
    if before_confirm.get("has_active") is not False:
        raise Phase8Error("training draft was incorrectly exposed as active")
    confirm_body = dict(plan_body)
    confirm_body["expected_plan_version_id"] = draft_plan.get("plan_version_id")
    confirm_body["idempotency_key"] = "phase8-http-plan-confirm"
    confirmed = api.json(
        "POST", "/api/v1/training/plans:confirm", headers=headers, body=confirm_body
    )
    plan = confirmed.get("plan")
    if not isinstance(plan, dict) or not plan.get("plan_version_id"):
        raise Phase8Error("training confirmation returned no active plan")
    today = api.json(
        "GET", f"/api/v1/training/today?iana_timezone={TIMEZONE}", headers=headers
    )
    state = today.get("state")
    if state != "session":
        raise Phase8Error("scheduled journey day did not expose a session")
    session_id = today.get("original_session_id")
    if not isinstance(session_id, str):
        raise Phase8Error("effective Today omitted the original session identity")
    adjusted = api.json(
        "POST",
        "/api/v1/training/today/adjustments",
        headers=headers,
        body={
            "intent": "apply_today_adjustment",
            "expected_plan_version_id": plan["plan_version_id"],
            "expected_session_id": session_id,
            "iana_timezone": TIMEZONE,
            "idempotency_key": "phase8-http-today-adjust",
        },
    )
    if adjusted.get("status") != "recorded":
        raise Phase8Error("foreground adjustment was not recorded")
    feedback = api.json(
        "POST",
        f"/api/v1/training/plans/sessions/{session_id}:feedback?iana_timezone={TIMEZONE}",
        headers=headers,
        body={
            "outcome_state": "completed",
            "idempotency_key": "phase8-http-session-feedback",
        },
    )
    if feedback.get("status") != "recorded":
        raise Phase8Error("session feedback was not recorded")
    effective = api.json(
        "GET", f"/api/v1/training/today?iana_timezone={TIMEZONE}", headers=headers
    )
    if effective.get("feedback_outcome_state") != "completed":
        raise Phase8Error("effective Today did not read back session feedback")
    return str(state)


def _agent_journey(api: Api, headers: Dict[str, str]) -> None:
    before = api.json("GET", "/api/v1/agent/capabilities", headers=headers)
    if before.get("result_code") != "agent_consent_required":
        raise Phase8Error("Agent did not require explicit consent")
    granted = api.json(
        "POST",
        "/api/v1/agent/consents:grant",
        headers=headers,
        body={
            "accepted_provider_id": "dashscope",
            "accepted_disclosure_version": "agent-cloud-v1",
            "idempotency_key": "phase8-http-agent-consent",
        },
    )
    if granted.get("status") != "granted":
        raise Phase8Error("Agent consent was not granted")
    after = api.json("GET", "/api/v1/agent/capabilities", headers=headers)
    if after.get("result_code") != "agent_available":
        raise Phase8Error("Agent did not become available after consent")
    turn = api.json(
        "POST",
        "/api/v1/agent/turns",
        headers=headers,
        body={
            "client_turn_id": "phase8-http-read-only-turn",
            "entry_type": "health_profile",
            "message": "Summarize the synthetic profile without changing records.",
            "iana_timezone": TIMEZONE,
        },
    )
    if turn.get("status") != "answer" or turn.get("result_code") != "agent_answer_ready":
        raise Phase8Error("scripted Agent read turn did not complete")


def _nutrition_journey(api: Api, headers: Dict[str, str]) -> None:
    eligibility = api.json(
        "GET", f"/api/v1/nutrition/eligibility?iana_timezone={TIMEZONE}", headers=headers
    )
    if eligibility.get("gate") not in {"eligible", "eligible_conservative"}:
        raise Phase8Error("nutrition eligibility did not pass")
    draft = api.json(
        "POST",
        "/api/v1/nutrition/recommendations/drafts",
        headers=headers,
        body={"idempotency_key": "phase8-http-nutrition-draft", "iana_timezone": TIMEZONE},
    )
    recommendation = draft.get("recommendation")
    if not isinstance(recommendation, dict) or recommendation.get("status") != "draft":
        raise Phase8Error("nutrition draft was not generated")
    payload = recommendation.get("payload")
    if not isinstance(payload, dict):
        raise Phase8Error("nutrition draft payload is unavailable")
    confirmed = api.json(
        "POST",
        f"/api/v1/nutrition/recommendations/{recommendation['recommendation_id']}:confirm",
        headers=headers,
        body={
            "idempotency_key": "phase8-http-nutrition-confirm",
            "iana_timezone": TIMEZONE,
            "expected_version": recommendation.get("version"),
            "expected_fingerprint": payload.get("source_context_fingerprint"),
        },
    )
    active = confirmed.get("recommendation")
    if not isinstance(active, dict) or active.get("status") != "active":
        raise Phase8Error("nutrition recommendation was not activated")


def _fault_recovery(api: Api, headers: Dict[str, str]) -> None:
    _fault(api, "/api/v1/agent/capabilities", "service_unavailable")
    api.json("GET", "/api/v1/agent/capabilities", headers=headers, expected=503)
    recovered = api.json("GET", "/api/v1/agent/capabilities", headers=headers)
    if recovered.get("result_code") != "agent_available":
        raise Phase8Error("Agent did not recover after one-shot fault")

    _fault(api, "/api/v1/nutrition/eligibility", "malformed_json")
    try:
        api.json(
            "GET", f"/api/v1/nutrition/eligibility?iana_timezone={TIMEZONE}", headers=headers
        )
    except Phase8Error as exc:
        if "invalid JSON" not in str(exc):
            raise
    else:
        raise Phase8Error("malformed JSON fault was not observed")
    retry = api.json(
        "GET", f"/api/v1/nutrition/eligibility?iana_timezone={TIMEZONE}", headers=headers
    )
    if retry.get("gate") not in {"eligible", "eligible_conservative"}:
        raise Phase8Error("nutrition did not recover after malformed JSON")


def _verify_evidence(body: Dict[str, Any], checkpoint: str) -> Dict[str, int]:
    if body.get("synthetic_only") is not True or body.get("checkpoint") != checkpoint:
        raise Phase8Error("evidence does not match the requested synthetic checkpoint")
    counts = body.get("table_counts")
    if not isinstance(counts, dict) or not all(isinstance(value, int) for value in counts.values()):
        raise Phase8Error("evidence table counts are invalid")
    return counts


def _require_minimum_counts(counts: Dict[str, int], expected: Dict[str, int]) -> None:
    missing = [
        name for name, minimum in expected.items()
        if counts.get(name, 0) < minimum
    ]
    if missing:
        raise Phase8Error("synthetic evidence is missing required domain rows")


def _review_journey(api: Api) -> None:
    due = reset(api, "cycle_due")
    _verify_evidence(due, "cycle_due")
    headers = _auth_headers(_login(api))
    review = api.json(
        "POST",
        "/api/v1/training/reviews/weeks/4",
        headers=headers,
        body={
            "iana_timezone": CYCLE_TIMEZONE,
            "idempotency_key": "phase8-http-weekly-review",
        },
    )
    execution = review.get("execution")
    proposals = review.get("proposals")
    posture = review.get("posture")
    if (
        review.get("week_index") != 4
        or not isinstance(execution, dict)
        or execution.get("scheduled", 0) <= 0
        or not isinstance(proposals, list)
        or not proposals
        or not isinstance(posture, dict)
        or posture.get("status") != "due"
    ):
        raise Phase8Error("cycle checkpoint review facts are incomplete")
    mutation = {
        "expected_review_id": review.get("review_id"),
        "expected_input_fingerprint": review.get("input_fingerprint"),
        "iana_timezone": CYCLE_TIMEZONE,
        "idempotency_key": "phase8-http-review-training-draft",
    }
    proposal_codes = {
        proposal.get("code") for proposal in proposals if isinstance(proposal, dict)
    }
    if "offer_training_draft" in proposal_codes:
        draft_path = "/api/v1/training/reviews/weeks/4/training-drafts"
        draft_kind = "training"
    elif "offer_nutrition_refresh" in proposal_codes:
        draft_path = "/api/v1/training/reviews/weeks/4/nutrition-drafts"
        draft_kind = "nutrition"
        mutation["idempotency_key"] = "phase8-http-review-nutrition-draft"
    else:
        raise Phase8Error("weekly review exposed no draft proposal")
    created = api.json(
        "POST",
        draft_path,
        headers=headers,
        body=mutation,
    )
    if (
        created.get("status") != "created"
        or created.get("origin_weekly_review_id") != review.get("review_id")
    ):
        raise Phase8Error("weekly review did not create an inactive domain draft")
    active = api.json("GET", "/api/v1/training/plans/active", headers=headers)
    active_plan = active.get("plan")
    if (
        active.get("has_active") is not True
        or not isinstance(active_plan, dict)
        or active_plan.get("plan_version_id") != review.get("plan_version_id")
    ):
        raise Phase8Error("weekly review draft incorrectly changed the active plan")
    if draft_kind == "nutrition":
        nutrition_draft = api.json(
            "GET",
            f"/api/v1/nutrition/recommendations/draft?iana_timezone={CYCLE_TIMEZONE}",
            headers=headers,
        )
        recommendation = nutrition_draft.get("recommendation")
        if (
            not isinstance(recommendation, dict)
            or recommendation.get("status") != "draft"
        ):
            raise Phase8Error("weekly review nutrition draft was not readable as draft")
    evidence = api.json("GET", "/__phase8/evidence", headers=_control_headers())
    counts = _verify_evidence(evidence, "cycle_due")
    minimum = {"training_weekly_reviews": 1, "training_plan_versions": 1}
    minimum[
        "training_plan_versions" if draft_kind == "training"
        else "nutrition_recommendations"
    ] = 2 if draft_kind == "training" else 1
    _require_minimum_counts(counts, minimum)


def _safety_blocked_journey(api: Api) -> None:
    blocked = reset(api, "safety_blocked")
    before = _verify_evidence(blocked, "safety_blocked")
    headers = _auth_headers(_login(api))
    plan = api.json(
        "POST",
        "/api/v1/training/plans:draft",
        headers=headers,
        expected=409,
        body={
            "fitness_goal": "basic_strength",
            "weekly_frequency": 2,
            "session_duration_minutes": 30,
            "equipment_bodyweight": True,
            "equipment_resistance_band": False,
            "iana_timezone": CYCLE_TIMEZONE,
            "idempotency_key": "phase8-http-blocked-plan",
        },
    )
    if plan.get("code") not in {"restricted_no_plan", "red_flag_stop"}:
        raise Phase8Error("safety checkpoint did not block plan generation")
    nutrition = api.json(
        "POST",
        "/api/v1/nutrition/recommendations/drafts",
        headers=headers,
        expected=409,
        body={
            "iana_timezone": CYCLE_TIMEZONE,
            "idempotency_key": "phase8-http-blocked-nutrition",
        },
    )
    if nutrition.get("code") not in {"nutrition_restricted", "nutrition_red_flag"}:
        raise Phase8Error("safety checkpoint did not block nutrition generation")
    after_body = api.json("GET", "/__phase8/evidence", headers=_control_headers())
    after = _verify_evidence(after_body, "safety_blocked")
    protected = (
        "training_plan_versions",
        "training_day_adjustments",
        "nutrition_recommendations",
    )
    if any(after.get(name, 0) != before.get(name, 0) for name in protected):
        raise Phase8Error("safety-blocked journey created an ordinary domain write")


def run_http_journey(base_url: str) -> Dict[str, Any]:
    api = Api(base_url)
    checks: List[str] = []
    try:
        assert_phase8_server(api)
        checks.append("server_mode")
        _verify_evidence(reset(api, "blank_supported"), "blank_supported")
        checks.append("reset_blank")
        token = _login(api)
        headers = _auth_headers(token)
        _posture_journey(api, headers)
        _health_journey(api, headers)
        today_state = _training_journey(api, headers)
        _agent_journey(api, headers)
        _nutrition_journey(api, headers)
        checks.extend(["posture", "health", f"today_{today_state}", "agent", "nutrition"])
        _fault_recovery(api, headers)
        checks.append("fault_recovery")
        populated = api.json("GET", "/__phase8/evidence", headers=_control_headers())
        populated_counts = _verify_evidence(populated, "blank_supported")
        if populated.get("provider_calls") != 2:
            raise Phase8Error("populated evidence did not prove the full synthetic journey")
        _require_minimum_counts(
            populated_counts,
            {
                "posture_assessment_events": 1,
                "posture_user_goals": 1,
                "health_checkins": 1,
                "weight_records": 1,
                "training_plan_versions": 1,
                "training_day_adjustments": 1,
                "training_session_feedback": 1,
                "agent_cloud_consents": 1,
                "agent_runs": 1,
                "agent_tool_events": 1,
                "nutrition_recommendations": 1,
            },
        )
        _review_journey(api)
        checks.append("cycle_due_review")
        _safety_blocked_journey(api)
        checks.append("safety_blocked_zero_writes")

        final = reset(api, "blank_supported")
        final_counts = _verify_evidence(final, "blank_supported")
        allowed = {"users", "health_profiles"}
        residual = {name: count for name, count in final_counts.items() if name not in allowed and count}
        if residual or final.get("provider_calls") != 0 or final.get("object_count") != 0:
            raise Phase8Error("final reset left synthetic residue")
        if final_counts.get("users") != 1 or final_counts.get("health_profiles") != 1:
            raise Phase8Error("final reset did not restore the exact blank checkpoint")
        checks.append("final_zero_residue")
        return {
            "checks": checks,
            "counts": {
                "checks_passed": len(checks),
                "checks_failed": 0,
                "tables_observed": len(final_counts),
                "residual_tables": 0,
            },
        }
    finally:
        api.close()


def wait_ready(base_url: str, process: subprocess.Popen, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error = "not_ready"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise Phase8Error(f"synthetic server exited before readiness code={process.returncode}")
        api = Api(base_url, timeout=1.0)
        try:
            assert_phase8_server(api)
            return
        except Phase8Error as exc:
            last_error = str(exc)
        finally:
            api.close()
        time.sleep(0.1)
    raise Phase8Error(f"synthetic server readiness timeout state={last_error}")


def _server_command(host: str, port: int) -> List[str]:
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "tests.phase8_device_server:app",
        "--host",
        host,
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]


def _remove_device_db() -> None:
    for suffix in ("", "-journal", "-wal", "-shm"):
        path = Path(str(DEVICE_DB) + suffix)
        if path.exists():
            path.unlink()


@contextmanager
def running_server(host: str, port: int, ready_timeout: float) -> Iterator[str]:
    if host not in {"127.0.0.1", "localhost"}:
        raise Phase8Error("synthetic server may bind to localhost only")
    if not _port_available(host, port):
        raise Phase8Error(f"synthetic server port is already in use port={port}")
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


def _run_eval() -> int:
    with tempfile.TemporaryDirectory(prefix="phase8-eval-") as directory:
        junit = Path(directory) / "junit.xml"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_phase8_evaluations.py",
                    "-q",
                    f"--junitxml={junit}",
                ],
                cwd=BACKEND_DIR,
                capture_output=True,
                text=True,
                timeout=EVAL_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise Phase8Error("evaluation timed out") from exc
        try:
            root = ET.parse(junit).getroot()
            suites = root.findall("testsuite") if root.tag == "testsuites" else [root]
            total = sum(int(suite.get("tests", "0")) for suite in suites)
            failed = sum(
                int(suite.get("failures", "0")) + int(suite.get("errors", "0"))
                for suite in suites
            )
            skipped = sum(int(suite.get("skipped", "0")) for suite in suites)
        except (OSError, ET.ParseError, ValueError):
            print("phase8 eval failed: missing or invalid JUnit evidence", file=sys.stderr)
            return 1
    passed = max(total - failed - skipped, 0)
    _emit(
        "eval",
        checkpoint="versioned_matrices",
        transitions=["training_matrix", "agent_matrix", "linked_state_machines"],
        counts={"passed": passed, "failed": failed, "skipped": skipped},
    )
    if result.returncode != 0 or failed or skipped:
        print(f"phase8 eval failed: code={result.returncode}", file=sys.stderr)
        return result.returncode or 1
    return 0


def _serve(args: argparse.Namespace) -> int:
    if args.host not in {"127.0.0.1", "localhost"}:
        raise Phase8Error("synthetic server may bind to localhost only")
    if not _port_available(args.host, args.port):
        raise Phase8Error(f"synthetic server port is already in use port={args.port}")
    _remove_device_db()
    environment = os.environ.copy()
    environment.pop("TEST_DB_URL", None)
    try:
        return subprocess.run(
            _server_command(args.host, args.port), cwd=BACKEND_DIR, env=environment, check=False
        ).returncode
    finally:
        _remove_device_db()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 8 synthetic acceptance")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    reset_cmd = sub.add_parser("reset")
    http_cmd = sub.add_parser("http")
    sub.add_parser("eval")
    verify = sub.add_parser("verify")
    for item in (serve, reset_cmd, http_cmd, verify):
        item.add_argument("--host", default=DEFAULT_HOST)
        item.add_argument("--port", type=int, default=DEFAULT_PORT)
    reset_cmd.add_argument(
        "--checkpoint", choices=["blank_supported", "cycle_due", "safety_blocked"], required=True
    )
    verify.add_argument("--surface", choices=["http", "eval", "all"], default="all")
    verify.add_argument("--ready-timeout", type=float, default=15.0)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "serve":
            return _serve(args)
        if args.command == "reset":
            api = Api(_base_url(args.host, args.port))
            try:
                assert_phase8_server(api)
                counts = _verify_evidence(reset(api, args.checkpoint), args.checkpoint)
            finally:
                api.close()
            _emit(
                "reset",
                checkpoint=args.checkpoint,
                transitions=[f"checkpoint_{args.checkpoint}"],
                counts={
                    "checks_passed": 1,
                    "checks_failed": 0,
                    "tables_observed": len(counts),
                },
            )
            return 0
        if args.command == "http":
            result = run_http_journey(_base_url(args.host, args.port))
            _emit(
                "http",
                checkpoint=(
                    "blank_supported -> cycle_due -> safety_blocked -> "
                    "blank_supported"
                ),
                transitions=result["checks"],
                counts=result["counts"],
            )
            return 0
        if args.command == "eval":
            return _run_eval()
        if args.command == "verify":
            if args.surface in {"http", "all"}:
                with running_server(args.host, args.port, args.ready_timeout) as base_url:
                    result = run_http_journey(base_url)
                _emit(
                    "verify-http",
                    checkpoint=(
                        "blank_supported -> cycle_due -> safety_blocked -> "
                        "blank_supported"
                    ),
                    transitions=result["checks"],
                    counts=result["counts"],
                )
            if args.surface in {"eval", "all"}:
                rc = _run_eval()
                if rc != 0:
                    return rc
            return 0
        raise Phase8Error("unsupported command")
    except (Phase8Error, OSError) as exc:
        print(f"phase8 failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
