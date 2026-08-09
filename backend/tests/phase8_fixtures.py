"""Disposable Phase 8 reset, fault, and sanitized evidence control plane."""
from __future__ import annotations

import asyncio
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from fastapi import Header, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.agent.provider import ScriptedProvider
from app.auth.models import User
from app.core.exceptions import AppException
from app.db.base import Base
from app.health.models import HealthProfile
from app.health.models import DailyCheckIn
from app.posture import service as posture_service
from app.posture.models import PostureAssessmentEvent
from app.posture.schemas import GoalInput
from app.training import persistence as training_persistence
from app.training import service as training_service
from app.training.models import TrainingSessionFeedback
from app.training.schemas_api import ConfirmRequest, DraftRequest


SYNTHETIC_USER_ID = uuid.UUID("80000000-0000-0000-0000-000000000008")
SYNTHETIC_PHONE = "13900000008"
SYNTHETIC_PASSWORD = "synthetic-phase8-only"
SYNTHETIC_CONTROL_TOKEN = "phase8-local-control-only"
CONTROL_HEADER = "X-Phase8-Control-Token"


class Checkpoint(str, Enum):
    blank_supported = "blank_supported"
    cycle_due = "cycle_due"
    safety_blocked = "safety_blocked"


class FaultKind(str, Enum):
    service_unavailable = "service_unavailable"
    malformed_json = "malformed_json"


class FaultRoute(str, Enum):
    today = "/api/v1/training/today"
    agent = "/api/v1/agent/capabilities"
    nutrition = "/api/v1/nutrition/eligibility"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResetRequest(_StrictModel):
    checkpoint: Checkpoint


class FaultRequest(_StrictModel):
    route: FaultRoute
    kind: FaultKind


class ProviderController:
    def __init__(self) -> None:
        self.provider = ScriptedProvider([])

    def get(self):
        return self.provider

    def reset(self) -> None:
        self.provider = ScriptedProvider(
            [
                {
                    "type": "read_tool_call",
                    "tool_name": "get_health_profile_summary",
                    "arguments": {},
                },
                {
                    "type": "answer",
                    "message_code": "agent_answer_ready",
                    "references": ["get_health_profile_summary"],
                },
            ]
        )


class Phase8Control:
    def __init__(
        self,
        *,
        engine,
        session_factory,
        expected_db_path: Path,
        provider_controller: ProviderController,
        control_token: str = SYNTHETIC_CONTROL_TOKEN,
    ) -> None:
        self.engine = engine
        self.session_factory = session_factory
        self.expected_db_path = expected_db_path.resolve()
        self.provider_controller = provider_controller
        self.control_token = control_token
        self.reset_generation = 0
        self.checkpoint: Optional[Checkpoint] = None
        self._reset_lock = asyncio.Lock()
        self._faults: dict[str, FaultKind] = {}
        self.synthetic_object_keys: set[str] = set()

    def _require_disposable_db(self) -> None:
        if self.engine.url.drivername != "sqlite+aiosqlite":
            raise RuntimeError("Phase 8 reset requires sqlite+aiosqlite")
        actual = Path(self.engine.url.database or "").resolve()
        if actual != self.expected_db_path:
            raise RuntimeError("Phase 8 reset refuses a non-disposable database")

    def _authorize(self, value: str) -> None:
        if not hmac.compare_digest(value, self.control_token):
            raise AppException(
                403,
                "Invalid test control token",
                "phase8_control_forbidden",
            )

    async def reset(self, checkpoint: Checkpoint) -> dict:
        self._require_disposable_db()
        if self._reset_lock.locked():
            raise AppException(
                409,
                "Test reset in progress",
                "phase8_reset_in_progress",
            )
        async with self._reset_lock:
            async with self.engine.begin() as connection:
                await connection.run_sync(Base.metadata.drop_all)
                await connection.run_sync(Base.metadata.create_all)
            self.provider_controller.reset()
            self._faults.clear()
            self.synthetic_object_keys.clear()
            await self._seed(checkpoint)
            self.checkpoint = checkpoint
            self.reset_generation += 1
            return await self.evidence()

    async def _seed(self, checkpoint: Checkpoint) -> None:
        restricted = checkpoint == Checkpoint.safety_blocked
        async with self.session_factory() as db:
            db.add(
                User(
                    id=SYNTHETIC_USER_ID,
                    phone=SYNTHETIC_PHONE,
                    nickname="Synthetic acceptance user",
                    height=170,
                    weight=70,
                    age=30,
                    gender="male",
                )
            )
            db.add(
                HealthProfile(
                    user_id=SYNTHETIC_USER_ID,
                    fitness_goal="basic_strength",
                    training_experience="beginner",
                    weekly_frequency=2,
                    session_duration_minutes=30,
                    equipment={"bodyweight": True, "resistance_band": False},
                    pain_injury_limitations=[],
                    risk_screen={
                        "underage": "yes" if restricted else "no",
                        "pregnancy_or_postpartum": "no",
                        "recent_surgery_or_major_injury": "no",
                        "major_chronic_condition": "no",
                        "eating_disorder_concern": "no",
                        "professional_instruction_limitations": "no",
                    },
                    allergies=[],
                    diet_exclusions=[],
                    food_allergen_codes=[],
                    excluded_food_codes=[],
                    version=1,
                )
            )
            await db.commit()
            if checkpoint == Checkpoint.cycle_due:
                await self._seed_cycle_due(db)

    async def _seed_cycle_due(self, db) -> None:
        current_local_date = datetime.now(timezone.utc).astimezone(
            ZoneInfo("Asia/Shanghai")
        ).date()
        db.add(
            DailyCheckIn(
                user_id=SYNTHETIC_USER_ID,
                local_date=current_local_date,
                sleep_quality="good",
                energy="normal",
                muscle_soreness="none",
                available_time="45_min_plus",
                daily_status="checked_in",
                abnormal_pain=False,
                pain_followup=None,
                risk_summary="normal",
                risk_version="synthetic-phase8-v1",
            )
        )
        await db.commit()
        assessment = await posture_service.save_self_assessment(
            db,
            str(SYNTHETIC_USER_ID),
            "LL-18",
            "positive",
            0,
        )
        if assessment is None:
            raise RuntimeError("Phase 8 cycle fixture self-test is unavailable")
        suggestions = await posture_service.get_priority_suggestions(
            db,
            str(SYNTHETIC_USER_ID),
        )
        if not any(
            item["issue_id"] == "LL-18"
            for item in suggestions["normal_candidates"]
        ):
            raise RuntimeError("Phase 8 cycle fixture goal is not eligible")
        await posture_service.confirm_posture_goals(
            db,
            str(SYNTHETIC_USER_ID),
            suggestions["suggestion_id"],
            suggestions["profile_version"],
            [GoalInput(issue_id="LL-18", priority_rank=1)],
            "phase8-cycle-goal",
        )
        request_values = {
            "fitness_goal": "basic_strength",
            "weekly_frequency": 2,
            "session_duration_minutes": 30,
            "equipment_bodyweight": True,
            "equipment_resistance_band": False,
            "iana_timezone": "Asia/Shanghai",
        }
        draft = await training_service.generate_draft(
            db,
            str(SYNTHETIC_USER_ID),
            DraftRequest(
                **request_values,
                idempotency_key="phase8-cycle-generate",
            ),
        )
        if not draft.has_draft or draft.draft is None:
            raise RuntimeError("Phase 8 cycle fixture failed to generate a draft")
        await training_service.confirm(
            db,
            str(SYNTHETIC_USER_ID),
            ConfirmRequest(
                **request_values,
                idempotency_key="phase8-cycle-confirm",
            ),
        )
        plan = await training_persistence.get_active_version(
            db, str(SYNTHETIC_USER_ID)
        )
        if plan is None:
            raise RuntimeError("Phase 8 cycle fixture failed to activate the plan")

        confirmed_at = datetime.now(timezone.utc) - timedelta(days=35)
        plan.generated_at = confirmed_at - timedelta(minutes=1)
        plan.confirmed_at = confirmed_at
        sessions = await training_persistence.load_sessions(
            db, plan.plan_version_id
        )
        confirmed_local_date = training_service.derive_local_date(
            confirmed_at, "Asia/Shanghai"
        )
        plan_start = confirmed_local_date - timedelta(
            days=confirmed_local_date.isoweekday() - 1
        )
        for session in sessions:
            local_date = plan_start + timedelta(
                days=(session.week_index - 1) * 7 + session.day_of_week - 1
            )
            outcome = (
                "too_busy"
                if session.week_index == 4 and session.session_order == 1
                else "completed"
            )
            db.add(
                TrainingSessionFeedback(
                    user_id=SYNTHETIC_USER_ID,
                    plan_version_id=plan.plan_version_id,
                    session_id=session.session_id,
                    local_date=local_date,
                    outcome_state=outcome,
                )
            )
            db.add(
                DailyCheckIn(
                    user_id=SYNTHETIC_USER_ID,
                    local_date=local_date,
                    sleep_quality="good",
                    energy="normal",
                    muscle_soreness="mild",
                    available_time="45_min_plus",
                    daily_status="checked_in",
                    abnormal_pain=False,
                    pain_followup=None,
                    risk_summary="normal",
                    risk_version="synthetic-phase8-v1",
                )
            )
        posture_event = await db.scalar(
            select(PostureAssessmentEvent).where(
                PostureAssessmentEvent.id == uuid.UUID(assessment["id"])
            )
        )
        if posture_event is None:
            raise RuntimeError("Phase 8 cycle fixture lost its posture baseline")
        posture_event.created_at = confirmed_at - timedelta(minutes=2)
        await db.commit()

    async def evidence(self) -> dict:
        counts = {}
        async with self.session_factory() as db:
            for table in Base.metadata.sorted_tables:
                counts[table.name] = int(
                    await db.scalar(select(func.count()).select_from(table)) or 0
                )
        return {
            "synthetic_only": True,
            "checkpoint": self.checkpoint.value if self.checkpoint else None,
            "reset_generation": self.reset_generation,
            "provider_calls": len(self.provider_controller.provider.calls),
            "object_count": len(self.synthetic_object_keys),
            "table_counts": counts,
        }

    def install(self, app) -> None:
        @app.middleware("http")
        async def one_shot_fault(request: Request, call_next: Callable):
            kind = self._faults.pop(request.url.path, None)
            if kind == FaultKind.service_unavailable:
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "Synthetic service fault",
                        "code": "service_unavailable",
                    },
                )
            if kind == FaultKind.malformed_json:
                return Response(
                    status_code=200,
                    content=b'{"truncated":',
                    media_type="application/json",
                )
            return await call_next(request)

        @app.post("/__phase8/reset")
        async def reset_route(
            body: ResetRequest,
            token: str = Header(..., alias=CONTROL_HEADER),
        ):
            self._authorize(token)
            return await self.reset(body.checkpoint)

        @app.post("/__phase8/faults")
        async def fault_route(
            body: FaultRequest,
            token: str = Header(..., alias=CONTROL_HEADER),
        ):
            self._authorize(token)
            self._faults[body.route.value] = body.kind
            return {"status": "installed", "route": body.route, "kind": body.kind}

        @app.get("/__phase8/evidence")
        async def evidence_route(
            token: str = Header(..., alias=CONTROL_HEADER),
        ):
            self._authorize(token)
            return await self.evidence()


__all__ = [
    "Checkpoint",
    "CONTROL_HEADER",
    "FaultKind",
    "FaultRoute",
    "Phase8Control",
    "ProviderController",
    "SYNTHETIC_CONTROL_TOKEN",
    "SYNTHETIC_PASSWORD",
    "SYNTHETIC_PHONE",
    "SYNTHETIC_USER_ID",
]
