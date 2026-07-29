"""Phase 5 Task 1 (Batch A) - read adapters reuse existing services.

Each adapter delegates to an existing domain service/Tool (proven by spies),
duplicates no business logic, performs no write, and returns two separately
typed projections: a minimal ``provider_view`` and an owned ``display_view``.
Sensitive fields, raw payloads, and full history stay out of the provider view.
Synthetic data only.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from app.agent import read_tools
from app.agent.schemas import (
    DisplayView,
    HealthProfileProviderView,
    ProviderView,
    ReadToolResult,
    TodayCheckinProviderView,
    WeightTrendDisplayView,
)
from app.core.actor_context import ActorContext

_UID = str(uuid.uuid4())
_ACTOR = ActorContext(user_id=_UID)
_NOW = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)


class _Spy:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result

    def sync(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result


# --------------------------------------------------------------------------- #
# Health profile summary                                                       #
# --------------------------------------------------------------------------- #


def _profile_result(configured=True):
    from app.health.schemas import (
        HealthProfileResponse,
        HealthProfileResultResponse,
        HealthReadinessResponse,
    )

    readiness = HealthReadinessResponse(
        readiness="ready",
        risk_version="rv1",
        reason="ok",
        missing_fields=[],
        restricted_reason=None,
    )
    if not configured:
        return HealthProfileResultResponse(
            configured=False, profile=None, readiness=readiness
        )
    profile = HealthProfileResponse(
        id=uuid.uuid4(),
        fitness_goal="general_wellness",
        training_experience="experienced",
        weekly_frequency=3,
        session_duration_minutes=30,
        equipment={"bodyweight": True, "resistance_band": False},
        pain_injury_limitations=[{"body_area": "腰", "status": "recovered"}],
        risk_screen=None,
        allergies=[{"label": "花生", "note": "严重"}],
        diet_exclusions=[{"item": "牛奶"}],
        version=4,
        updated_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    return HealthProfileResultResponse(
        configured=True, profile=profile, readiness=readiness
    )


async def test_health_profile_adapter_delegates_and_minimizes(monkeypatch):
    spy = _Spy(_profile_result(configured=True))
    monkeypatch.setattr("app.health.service.get_profile_result", spy)

    result = await read_tools.adapt_health_profile_summary(None, _ACTOR)

    # Delegation: called with the actor's user_id (never a client-supplied id).
    assert spy.calls and spy.calls[0][0][1] == _UID
    assert isinstance(result, ReadToolResult)
    assert isinstance(result.provider_view, HealthProfileProviderView)

    pv = result.provider_view
    # Provider sees only bounded categorical flags, never raw allergy/diet text.
    assert pv.configured is True
    assert pv.has_allergies is True
    assert pv.has_diet_exclusions is True
    dumped = pv.model_dump()
    assert "花生" not in str(dumped)
    assert "牛奶" not in str(dumped)
    assert "allergies" not in dumped  # no raw list field
    # The owned display view carries bounded counts, still no raw text.
    dv = result.display_view.model_dump()
    assert result.display_view.allergies_count == 1
    assert "花生" not in str(dv)


# --------------------------------------------------------------------------- #
# Today check-in                                                               #
# --------------------------------------------------------------------------- #


async def test_today_checkin_adapter_excludes_pain_free_text(monkeypatch):
    from app.health.schemas import CheckInResponse, CheckInTodayResultResponse

    checkin = CheckInResponse(
        id=uuid.uuid4(),
        local_date=date(2026, 7, 29),
        sleep_quality="good",
        energy="high",
        muscle_soreness="none",
        available_time="45_min_plus",
        daily_status="checked_in",
        abnormal_pain=False,
        pain_followup=None,
        risk_summary="normal",
        risk_version="rv1",
        created_at=_NOW,
        updated_at=_NOW,
    )
    spy = _Spy(CheckInTodayResultResponse(checked_in=True, checkin=checkin))
    monkeypatch.setattr("app.health.service.get_today", spy)

    result = await read_tools.adapt_today_checkin(None, _ACTOR, date(2026, 7, 29))

    assert spy.calls[0][0][1] == _UID
    assert spy.calls[0][0][2] == date(2026, 7, 29)
    assert isinstance(result.provider_view, TodayCheckinProviderView)
    assert result.provider_view.checked_in is True
    assert result.provider_view.risk_summary_code == "normal"
    # No pain follow-up / free-text field is exposed on either projection.
    assert "pain_followup" not in result.provider_view.model_dump()
    assert "pain_followup" not in result.display_view.model_dump()
    assert "pain_note" not in str(result.display_view.model_dump())


# --------------------------------------------------------------------------- #
# Weight trend                                                                 #
# --------------------------------------------------------------------------- #


async def test_weight_trend_adapter_bounds_history_and_hides_value_from_provider(
    monkeypatch,
):
    from app.health.schemas import (
        WeightRecordResponse,
        WeightTrendPoint,
        WeightTrendResponse,
    )

    records = [
        WeightRecordResponse(
            id=uuid.uuid4(),
            recorded_at=datetime(2026, 7, i + 1, tzinfo=timezone.utc),
            weight_kg=70.0 + i,
            source="manual",
            note=None,
            created_at=_NOW,
            updated_at=_NOW,
        )
        for i in range(3)
    ]
    trend = [WeightTrendPoint(recorded_at=records[-1].recorded_at, weight_kg=71.0)]
    spy = _Spy(
        WeightTrendResponse(records=records, trend=trend, window=7, sufficient=False)
    )
    monkeypatch.setattr("app.health.service.get_weight_trend", spy)

    result = await read_tools.adapt_weight_trend_summary(None, _ACTOR)

    assert spy.calls[0][0][1] == _UID
    pv = result.provider_view.model_dump()
    # Provider gets counts only - no raw weight value and no full history.
    assert pv["record_count"] == 3
    assert pv["trend_point_count"] == 1
    assert "latest_weight_kg" not in pv
    assert "records" not in pv
    assert "72.0" not in str(pv)
    # Owned display view may show the latest value but still not full history.
    assert isinstance(result.display_view, WeightTrendDisplayView)
    assert result.display_view.latest_weight_kg == 72.0
    assert "records" not in result.display_view.model_dump()


# --------------------------------------------------------------------------- #
# Posture catalog + owned profile                                             #
# --------------------------------------------------------------------------- #


def test_list_posture_issues_adapter_delegates_to_public_tool(monkeypatch):
    from app.posture.schemas import IssueSummary

    issues = [
        IssueSummary(
            id="forward_head",
            name_cn="头部前倾",
            category="head_neck",
            aliases=["低头"],
            definition="定义",
        )
    ]
    spy = _Spy(issues)
    monkeypatch.setattr("app.posture.tools.list_posture_issues", spy.sync)

    result = read_tools.adapt_list_posture_issues()

    assert spy.calls
    assert result.provider_view.issues[0].id == "forward_head"
    assert result.provider_view.issues[0].name_cn == "头部前倾"


async def test_posture_profile_adapter_excludes_user_id_and_sources(monkeypatch):
    from app.posture.schemas import (
        PostureProfileEntryResponse,
        PostureProfileResponse,
        PostureProfileSummary,
        ProfileSource,
    )

    profile = PostureProfileResponse(
        user_id=_UID,
        evaluated_issues=[
            PostureProfileEntryResponse(
                issue_id="forward_head",
                issue_name="头部前倾",
                category="head_neck",
                combined_severity="mild",
                certainty="confirmed",
                has_conflict=False,
                sources=[
                    ProfileSource(
                        source="self_test",
                        event_id="evt1",
                        severity="mild",
                        created_at="2026-07-01T00:00:00Z",
                    )
                ],
                risk_tier="normal",
                risk_version="rv1",
                updated_at=_NOW,
            )
        ],
        unevaluated_categories=["lower_limb"],
        summary=PostureProfileSummary(
            total_evaluated=1, total_conflict=0, total_provisional=0
        ),
    )
    spy = _Spy(profile)
    monkeypatch.setattr("app.posture.tools.get_posture_profile", spy)

    result = await read_tools.adapt_get_posture_profile(None, _ACTOR)

    pv = result.provider_view.model_dump()
    # Owner user_id and raw assessment sources never reach the provider view.
    assert "user_id" not in pv
    assert "sources" not in str(pv)
    assert result.provider_view.entries[0].issue_id == "forward_head"
    assert result.provider_view.entries[0].risk_tier == "normal"


# --------------------------------------------------------------------------- #
# Training reads                                                               #
# --------------------------------------------------------------------------- #


async def test_active_plan_adapter_delegates_and_summarizes(monkeypatch):
    from app.training.schemas_api import ActivePlanResponse, PlanVersionView

    plan = PlanVersionView(
        plan_version_id="pv1",
        requested_goal="posture_improvement",
        weekly_frequency=3,
        session_duration_minutes=30,
        status="active",
        change_reason="initial",
        decision_gate="normal",
        generated_at=_NOW,
        confirmed_at=_NOW,
        catalog_version="2026-07-26-v1",
        policy_version="v1",
        sessions=[],
    )
    spy = _Spy(ActivePlanResponse(has_active=True, plan=plan))
    monkeypatch.setattr("app.training.service.get_active", spy)

    result = await read_tools.adapt_get_active_training_plan(None, _ACTOR)

    assert spy.calls[0][0][1] == _UID
    assert result.provider_view.has_active is True
    assert result.provider_view.plan.plan_version_id == "pv1"
    assert result.provider_view.plan.status == "active"


async def test_today_training_adapter_delegates_with_timezone(monkeypatch):
    from app.training.schemas_api import (
        PrescriptionView,
        SessionView,
        TodayResponse,
    )

    session = SessionView(
        session_id="sess1",
        week_index=0,
        day_of_week=1,
        session_order=0,
        target_minutes=30,
        prescriptions=[
            PrescriptionView(
                prescription_id="p1",
                exercise_id="ex1",
                sets=3,
                reps=10,
                duration_seconds=None,
                rest_seconds=60,
                relation_reason=None,
                exercise=None,
            )
        ],
    )
    spy = _Spy(
        TodayResponse(
            state="session",
            local_date=date(2026, 7, 30),
            change_reason=None,
            decision_gate="normal",
            session=session,
            feedback_outcome_state=None,
            substitution_applied=False,
        )
    )
    monkeypatch.setattr("app.training.service.get_today", spy)

    result = await read_tools.adapt_get_today_training(None, _ACTOR, "Asia/Shanghai")

    assert spy.calls[0][0][1] == _UID
    assert spy.calls[0][0][2] == "Asia/Shanghai"
    assert result.provider_view.state == "session"
    assert result.provider_view.has_session is True
    assert result.provider_view.prescription_count == 1
    # Display view exposes the owned exercise ids for rendering.
    assert result.display_view.exercise_ids == ["ex1"]


# --------------------------------------------------------------------------- #
# Base-type invariants                                                         #
# --------------------------------------------------------------------------- #


async def test_every_result_uses_the_base_view_types(monkeypatch):
    spy = _Spy(_profile_result(configured=False))
    monkeypatch.setattr("app.health.service.get_profile_result", spy)
    result = await read_tools.adapt_health_profile_summary(None, _ACTOR)
    assert isinstance(result.provider_view, ProviderView)
    assert isinstance(result.display_view, DisplayView)
