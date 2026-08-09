"""Isolation, control-plane, and privacy tests for the Phase 8 harness."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Optional
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.agent.provider import ScriptedProvider
from app.auth.models import User, VerificationCode
from app.core.exceptions import AppException
from app.health.models import HealthProfile
from app.main import app as production_app
from app.training import review_service, service as training_service
from app.training.models import TrainingPlanVersion, TrainingSessionFeedback
from app.training.schemas_api import (
    ConfirmRequest,
    DraftRequest,
    ReviewGenerateRequest,
    ReviewMutationRequest,
)
from tests.conftest import TestSession, override_get_db, test_engine
from tests.phase8_app_factory import create_phase8_test_app
from tests.phase8_fixtures import (
    CONTROL_HEADER,
    Checkpoint,
    Phase8Control,
    ProviderController,
    SYNTHETIC_CONTROL_TOKEN,
    SYNTHETIC_USER_ID,
)


def _control(*, expected_path: Optional[Path] = None):
    provider = ProviderController()
    control = Phase8Control(
        engine=test_engine,
        session_factory=TestSession,
        expected_db_path=expected_path or Path(test_engine.url.database),
        provider_controller=provider,
    )
    app = create_phase8_test_app(
        get_db_override=override_get_db,
        get_provider_override=provider.get,
        control=control,
    )
    return app, control, provider


def _headers(token: str = SYNTHETIC_CONTROL_TOKEN) -> dict[str, str]:
    return {CONTROL_HEADER: token}


@pytest.mark.parametrize(
    ("base_frequency", "base_duration", "frequency", "duration", "expected"),
    [
        (3, 30, 2, 30, True),
        (3, 30, 4, 30, True),
        (3, 30, 3, 15, True),
        (3, 30, 3, 45, True),
        (3, 30, 3, 30, False),
        (3, 30, 2, 15, False),
        (3, 30, 5, 30, False),
        (3, 30, 3, 60, False),
    ],
)
def test_weekly_review_adaptation_is_one_adjacent_preference_step(
    base_frequency: int,
    base_duration: int,
    frequency: int,
    duration: int,
    expected: bool,
):
    assert training_service._is_bounded_review_adaptation(
        base_weekly_frequency=base_frequency,
        base_session_duration_minutes=base_duration,
        weekly_frequency=frequency,
        session_duration_minutes=duration,
    ) is expected


def test_full_test_app_has_all_production_surfaces_and_private_control_routes():
    test_app, _control_plane, _provider = _control()
    paths = {route.path for route in test_app.routes}
    expected = {
        "/api/v1/auth/dev-login",
        "/api/v1/user/profile",
        "/api/v1/posture/assess",
        "/api/v1/upload/sts-token",
        "/api/v1/health/profile",
        "/api/v1/training/today",
        "/api/v1/nutrition/eligibility",
        "/api/v1/agent/capabilities",
        "/__phase8/reset",
        "/__phase8/faults",
        "/__phase8/evidence",
    }
    assert expected <= paths


def test_production_app_cannot_reach_or_import_phase8_control_plane():
    production_paths = {route.path for route in production_app.routes}
    assert not any(path.startswith("/__phase8") for path in production_paths)

    main_source = (
        Path(__file__).parents[1] / "app" / "main.py"
    ).read_text(encoding="utf-8")
    assert "phase8" not in main_source.lower()
    app_dir = Path(__file__).parents[1] / "app"
    production_source = "\n".join(
        path.read_text(encoding="utf-8") for path in app_dir.rglob("*.py")
    )
    assert "phase8_" not in production_source.lower()


def test_provider_override_is_bounded_script_only():
    _app, _control_plane, provider = _control()
    selected = provider.get()

    assert type(selected) is ScriptedProvider
    assert selected.calls == []
    assert len(selected._script) == 0
    provider.reset()
    assert len(provider.get()._script) == 2


@pytest.mark.parametrize(
    "external_url",
    [
        "postgresql+asyncpg://forbidden@127.0.0.1/forbidden",
        "sqlite+aiosqlite:///./another.db",
        "",
        "not-a-database-url",
    ],
)
def test_device_server_refuses_external_or_malformed_database(external_url):
    backend_dir = Path(__file__).parents[1]
    device_db = backend_dir / "phase8_acceptance.db"
    assert not device_db.exists()
    environment = os.environ.copy()
    environment["TEST_DB_URL"] = external_url

    result = subprocess.run(
        [sys.executable, "-c", "import tests.phase8_device_server"],
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode != 0
    assert "refuses externally configured TEST_DB_URL" in (
        result.stdout + result.stderr
    )
    assert not device_db.exists()


def test_device_server_starts_fresh_on_exact_disposable_database():
    backend_dir = Path(__file__).parents[1]
    device_db = backend_dir / "phase8_acceptance.db"
    assert not device_db.exists()
    environment = os.environ.copy()
    environment.pop("TEST_DB_URL", None)
    script = """
import asyncio
from tests import phase8_device_server as server

async def main():
    async with server.app.router.lifespan_context(server.app):
        evidence = await server.control.evidence()
        print(evidence["checkpoint"], evidence["table_counts"]["users"])
    await server.test_engine.dispose()
    if server.PHASE8_DB_PATH.exists():
        server.PHASE8_DB_PATH.unlink()

asyncio.run(main())
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if device_db.exists():
        device_db.unlink()

    assert result.returncode == 0, result.stdout + result.stderr
    assert "blank_supported 1" in result.stdout
    assert not device_db.exists()


@pytest.mark.asyncio
async def test_control_routes_require_exact_header_and_closed_payloads():
    app, _control_plane, _provider = _control()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://phase8.test"
    ) as client:
        missing = await client.post(
            "/__phase8/reset", json={"checkpoint": "blank_supported"}
        )
        wrong = await client.post(
            "/__phase8/reset",
            headers=_headers("wrong-token"),
            json={"checkpoint": "blank_supported"},
        )
        unknown_checkpoint = await client.post(
            "/__phase8/reset",
            headers=_headers(),
            json={"checkpoint": "invented"},
        )
        extra_reset_field = await client.post(
            "/__phase8/reset",
            headers=_headers(),
            json={"checkpoint": "blank_supported", "unsafe": True},
        )
        unknown_fault = await client.post(
            "/__phase8/faults",
            headers=_headers(),
            json={"route": "/api/v1/users/me", "kind": "timeout"},
        )

    assert missing.status_code == 422
    assert wrong.status_code == 403
    assert wrong.json()["code"] == "phase8_control_forbidden"
    assert unknown_checkpoint.status_code == 422
    assert extra_reset_field.status_code == 422
    assert unknown_fault.status_code == 422


@pytest.mark.asyncio
async def test_reset_clears_every_table_provider_fault_and_synthetic_object():
    app, control, provider = _control()
    async with TestSession() as db:
        db.add(
            VerificationCode(
                phone="13900000009",
                code="000008",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
        )
        await db.commit()
    provider.provider.calls.append({"type": "synthetic-call"})
    control._faults["/api/v1/agent/capabilities"] = "service_unavailable"
    control.synthetic_object_keys.add("synthetic/phase8/object-1")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://phase8.test"
    ) as client:
        response = await client.post(
            "/__phase8/reset",
            headers=_headers(),
            json={"checkpoint": "blank_supported"},
        )
        evidence = await client.get("/__phase8/evidence", headers=_headers())

    assert response.status_code == 200, response.text
    body = evidence.json()
    assert body["synthetic_only"] is True
    assert body["checkpoint"] == "blank_supported"
    assert body["reset_generation"] == 1
    assert body["provider_calls"] == 0
    assert body["object_count"] == 0
    assert body["table_counts"]["users"] == 1
    assert body["table_counts"]["health_profiles"] == 1
    assert body["table_counts"]["verification_codes"] == 0
    assert control._faults == {}
    assert set(body) == {
        "synthetic_only",
        "checkpoint",
        "reset_generation",
        "provider_calls",
        "object_count",
        "table_counts",
    }
    assert "phone" not in evidence.text.lower()
    assert "weight_kg" not in evidence.text.lower()
    assert "token" not in evidence.text.lower()


@pytest.mark.asyncio
async def test_wrong_disposable_path_refuses_before_destructive_work(tmp_path):
    _app, control, _provider = _control(expected_path=tmp_path / "wrong.db")
    marker_id = SYNTHETIC_USER_ID
    async with TestSession() as db:
        db.add(User(id=marker_id, phone="13900000008"))
        await db.commit()

    with pytest.raises(RuntimeError, match="non-disposable"):
        await control.reset(Checkpoint.blank_supported)

    async with TestSession() as db:
        assert await db.scalar(
            select(func.count()).select_from(User).where(User.id == marker_id)
        ) == 1


@pytest.mark.asyncio
async def test_concurrent_reset_fails_closed_without_touching_database():
    app, control, _provider = _control()
    await control._reset_lock.acquire()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://phase8.test"
        ) as client:
            response = await client.post(
                "/__phase8/reset",
                headers=_headers(),
                json={"checkpoint": "blank_supported"},
            )
    finally:
        control._reset_lock.release()

    assert response.status_code == 409
    assert response.json()["code"] == "phase8_reset_in_progress"
    assert control.reset_generation == 0


@pytest.mark.asyncio
async def test_fault_is_allowlisted_and_consumed_exactly_once():
    app, _control_plane, _provider = _control()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://phase8.test"
    ) as client:
        installed = await client.post(
            "/__phase8/faults",
            headers=_headers(),
            json={
                "route": "/api/v1/agent/capabilities",
                "kind": "service_unavailable",
            },
        )
        first = await client.get("/api/v1/agent/capabilities")
        second = await client.get("/api/v1/agent/capabilities")

    assert installed.status_code == 200
    assert first.status_code == 503
    assert first.json()["code"] == "service_unavailable"
    assert second.status_code == 401


@pytest.mark.asyncio
async def test_cycle_due_is_service_generated_and_week_four_review_is_due():
    _app, control, _provider = _control()
    evidence = await control.reset(Checkpoint.cycle_due)

    assert evidence["table_counts"]["training_plan_versions"] == 1
    assert evidence["table_counts"]["training_sessions"] == 8
    assert evidence["table_counts"]["training_session_feedback"] == 8
    assert evidence["table_counts"]["health_checkins"] == 9
    assert evidence["table_counts"]["posture_assessment_events"] == 1
    async with TestSession() as db:
        plan = await db.scalar(select(TrainingPlanVersion))
        assert plan is not None
        assert plan.status == "active"
        review = await review_service.generate_review(
            db,
            str(SYNTHETIC_USER_ID),
            4,
            ReviewGenerateRequest(
                idempotency_key="phase8-cycle-review",
                iana_timezone="Asia/Shanghai",
            ),
        )

    assert review.week_index == 4
    assert review.execution.scheduled == 2
    assert review.execution.too_busy == 1
    assert review.execution.intentional_rest == 1
    assert review.posture.status == "due"
    proposals = {proposal.code: proposal for proposal in review.proposals}
    assert proposals["offer_training_draft"].strategy == "conservative_duration"

    async with TestSession() as db:
        created = await review_service.create_training_draft(
            db,
            str(SYNTHETIC_USER_ID),
            4,
            ReviewMutationRequest(
                idempotency_key="phase8-cycle-training-draft",
                expected_review_id=review.review_id,
                expected_input_fingerprint=review.input_fingerprint,
                iana_timezone="Asia/Shanghai",
            ),
        )
        before_confirmation = await training_service.get_active(
            db, str(SYNTHETIC_USER_ID)
        )
        with pytest.raises(AppException) as mismatched:
            await training_service.confirm(
                db,
                str(SYNTHETIC_USER_ID),
                ConfirmRequest(
                    expected_plan_version_id=uuid.uuid4(),
                    fitness_goal="basic_strength",
                    weekly_frequency=2,
                    session_duration_minutes=15,
                    equipment_bodyweight=True,
                    equipment_resistance_band=False,
                    iana_timezone="Asia/Shanghai",
                    idempotency_key="phase8-cycle-wrong-draft",
                ),
            )
        confirmed = await training_service.confirm(
            db,
            str(SYNTHETIC_USER_ID),
            ConfirmRequest(
                expected_plan_version_id=created.draft_id,
                fitness_goal="basic_strength",
                weekly_frequency=2,
                session_duration_minutes=15,
                equipment_bodyweight=True,
                equipment_resistance_band=False,
                iana_timezone="Asia/Shanghai",
                idempotency_key="phase8-cycle-training-confirm",
            ),
        )

    assert created.status == "created"
    assert before_confirmation.plan is not None
    assert before_confirmation.plan.plan_version_id != created.draft_id
    assert confirmed.plan.plan_version_id == created.draft_id
    assert confirmed.plan.session_duration_minutes == 15
    assert confirmed.superseded_prior is True
    assert mismatched.value.code == "stale_context"


@pytest.mark.asyncio
async def test_review_draft_confirmation_rejects_changed_review_inputs():
    _app, control, _provider = _control()
    await control.reset(Checkpoint.cycle_due)

    async with TestSession() as db:
        review = await review_service.generate_review(
            db,
            str(SYNTHETIC_USER_ID),
            4,
            ReviewGenerateRequest(
                idempotency_key="phase8-stale-review",
                iana_timezone="Asia/Shanghai",
            ),
        )
        created = await review_service.create_training_draft(
            db,
            str(SYNTHETIC_USER_ID),
            4,
            ReviewMutationRequest(
                idempotency_key="phase8-stale-review-draft",
                expected_review_id=review.review_id,
                expected_input_fingerprint=review.input_fingerprint,
                iana_timezone="Asia/Shanghai",
            ),
        )
        feedback = await db.scalar(
            select(TrainingSessionFeedback).where(
                TrainingSessionFeedback.outcome_state == "intentional_rest"
            )
        )
        assert feedback is not None
        feedback.outcome_state = "completed"
        await db.commit()

        with pytest.raises(AppException) as stale:
            await training_service.confirm(
                db,
                str(SYNTHETIC_USER_ID),
                ConfirmRequest(
                    expected_plan_version_id=created.draft_id,
                    fitness_goal="basic_strength",
                    weekly_frequency=2,
                    session_duration_minutes=15,
                    equipment_bodyweight=True,
                    equipment_resistance_band=False,
                    iana_timezone="Asia/Shanghai",
                    idempotency_key="phase8-stale-review-confirm",
                ),
            )
        pending = await db.get(TrainingPlanVersion, uuid.UUID(created.draft_id))
        active = await training_service.get_active(db, str(SYNTHETIC_USER_ID))

    assert stale.value.code == "stale_context"
    assert pending is not None and pending.status == "draft"
    assert active.plan is not None
    assert active.plan.plan_version_id != created.draft_id


@pytest.mark.asyncio
async def test_review_draft_confirmation_reruns_latest_safety_gate():
    _app, control, _provider = _control()
    await control.reset(Checkpoint.cycle_due)

    async with TestSession() as db:
        review = await review_service.generate_review(
            db,
            str(SYNTHETIC_USER_ID),
            4,
            ReviewGenerateRequest(
                idempotency_key="phase8-review-safety",
                iana_timezone="Asia/Shanghai",
            ),
        )
        created = await review_service.create_training_draft(
            db,
            str(SYNTHETIC_USER_ID),
            4,
            ReviewMutationRequest(
                idempotency_key="phase8-review-safety-draft",
                expected_review_id=review.review_id,
                expected_input_fingerprint=review.input_fingerprint,
                iana_timezone="Asia/Shanghai",
            ),
        )
        profile = await db.scalar(
            select(HealthProfile).where(HealthProfile.user_id == SYNTHETIC_USER_ID)
        )
        assert profile is not None and profile.risk_screen is not None
        profile.risk_screen = {**profile.risk_screen, "underage": "yes"}
        profile.version += 1
        await db.commit()

        with pytest.raises(AppException) as blocked:
            await training_service.confirm(
                db,
                str(SYNTHETIC_USER_ID),
                ConfirmRequest(
                    expected_plan_version_id=created.draft_id,
                    fitness_goal="basic_strength",
                    weekly_frequency=2,
                    session_duration_minutes=15,
                    equipment_bodyweight=True,
                    equipment_resistance_band=False,
                    iana_timezone="Asia/Shanghai",
                    idempotency_key="phase8-review-safety-confirm",
                ),
            )
        pending = await db.get(TrainingPlanVersion, uuid.UUID(created.draft_id))

    assert blocked.value.code == "restricted_no_plan"
    assert pending is not None and pending.status == "draft"


@pytest.mark.asyncio
async def test_safety_blocked_checkpoint_uses_existing_gate_and_writes_no_plan():
    _app, control, _provider = _control()
    await control.reset(Checkpoint.safety_blocked)

    async with TestSession() as db:
        with pytest.raises(AppException) as captured:
            await training_service.generate_draft(
                db,
                str(SYNTHETIC_USER_ID),
                DraftRequest(
                    fitness_goal="basic_strength",
                    weekly_frequency=2,
                    session_duration_minutes=30,
                    equipment_bodyweight=True,
                    equipment_resistance_band=False,
                    iana_timezone="Asia/Shanghai",
                    idempotency_key="phase8-blocked-plan",
                ),
            )
        await db.rollback()
        plan_count = await db.scalar(
            select(func.count()).select_from(TrainingPlanVersion)
        )

    assert captured.value.code == "restricted_no_plan"
    assert plan_count == 0


def test_reset_rejects_non_sqlite_engine_before_destructive_work():
    _app, control, _provider = _control()
    original_engine = control.engine
    control.engine = SimpleNamespace(
        url=SimpleNamespace(
            drivername="postgresql+asyncpg",
            database="phase8_test",
        )
    )
    try:
        with pytest.raises(RuntimeError, match="sqlite"):
            control._require_disposable_db()
    finally:
        control.engine = original_engine


def test_reset_error_is_stable_application_exception():
    _app, control, _provider = _control()
    with pytest.raises(AppException) as captured:
        control._authorize("wrong-token")
    assert captured.value.code == "phase8_control_forbidden"
