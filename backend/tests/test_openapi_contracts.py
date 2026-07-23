"""OpenAPI schema contract tests for posture routes.

Asserts that all posture routes expose non-empty response schemas,
preventing regressions to unconstrained object responses.
"""

import pytest
from app.main import app


POSTURE_ROUTES = [
    ("get", "/api/v1/posture/issues"),
    ("get", "/api/v1/posture/issues/{issue_id}"),
    ("get", "/api/v1/posture/issues/{issue_id}/related"),
    ("post", "/api/v1/posture/assess"),
    ("post", "/api/v1/posture/assess/photo"),
    ("get", "/api/v1/posture/history"),
    ("post", "/api/v1/posture/safety-signals"),
    ("get", "/api/v1/posture/profile"),
    ("get", "/api/v1/posture/profile/{issue_id}"),
    ("get", "/api/v1/posture/priorities"),
    ("post", "/api/v1/posture/goals/confirm"),
]


@pytest.fixture(scope="module")
def openapi_schema():
    return app.openapi()


def _resolve_ref(schema: dict, openapi: dict) -> dict:
    """Resolve a $ref to its target schema component."""
    if "$ref" in schema:
        ref_path = schema["$ref"]
        parts = ref_path.lstrip("#/").split("/")
        target = openapi
        for part in parts:
            target = target[part]
        return target
    return schema


@pytest.mark.parametrize("method,path", POSTURE_ROUTES)
def test_posture_route_has_response_schema(method, path, openapi_schema):
    """Each posture route must have a non-empty 200 response schema."""
    paths = openapi_schema["paths"]
    assert path in paths, f"Path {path} not found in OpenAPI paths"

    operation = paths[path][method]
    responses = operation["responses"]
    assert "200" in responses, f"{method.upper()} {path} missing 200 response"

    content = responses["200"].get("content", {})
    assert "application/json" in content, (
        f"{method.upper()} {path} missing application/json content type"
    )

    schema = content["application/json"]["schema"]
    assert schema != {}, f"{method.upper()} {path} has empty response schema"
    assert schema is not None


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/v1/posture/issues"),
        ("get", "/api/v1/posture/issues/{issue_id}/related"),
        ("get", "/api/v1/posture/history"),
    ],
)
def test_list_routes_have_array_item_schema(method, path, openapi_schema):
    """List routes must have array type with defined item schema."""
    paths = openapi_schema["paths"]
    schema = paths[path][method]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]

    resolved = _resolve_ref(schema, openapi_schema)

    if resolved.get("type") == "array":
        items = resolved["items"]
        assert items != {}, f"{method.upper()} {path} has empty array items schema"
    else:
        # Might be a $ref to array type or items within
        assert "items" in resolved or "$ref" in resolved or "allOf" in resolved, (
            f"{method.upper()} {path} expected array schema with items"
        )


def test_history_source_is_additive_optional_field(openapi_schema):
    """Spec §15 keeps the new source field optional in the public schema."""
    response_schema = openapi_schema["paths"]["/api/v1/posture/history"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    array_schema = _resolve_ref(response_schema, openapi_schema)
    item_schema = _resolve_ref(array_schema["items"], openapi_schema)

    assert "source" in item_schema["properties"]
    assert "source" not in item_schema.get("required", [])


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/v1/posture/issues/{issue_id}"),
        ("post", "/api/v1/posture/assess"),
        ("post", "/api/v1/posture/assess/photo"),
        ("post", "/api/v1/posture/safety-signals"),
        ("get", "/api/v1/posture/profile"),
        ("get", "/api/v1/posture/profile/{issue_id}"),
        ("get", "/api/v1/posture/priorities"),
        ("post", "/api/v1/posture/goals/confirm"),
    ],
)
def test_detail_routes_have_component_ref(method, path, openapi_schema):
    """Detail/action routes must reference a named component schema."""
    paths = openapi_schema["paths"]
    schema = paths[path][method]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]

    has_ref = "$ref" in schema
    has_properties = "properties" in schema

    assert has_ref or has_properties, (
        f"{method.upper()} {path} should reference a component or define properties"
    )

    if has_ref:
        resolved = _resolve_ref(schema, openapi_schema)
        assert "properties" in resolved, (
            f"Referenced schema for {method.upper()} {path} has no properties"
        )
        assert len(resolved["properties"]) > 0


# ---------------------------------------------------------------------------
# Phase 1 Task 10: full-route contract validation (security, errors, requests)
# ---------------------------------------------------------------------------

# Routes that require authentication (JWT bearer).
PROTECTED_ROUTES = [
    ("post", "/api/v1/posture/assess"),
    ("post", "/api/v1/posture/assess/photo"),
    ("get", "/api/v1/posture/history"),
    ("post", "/api/v1/posture/safety-signals"),
    ("get", "/api/v1/posture/profile"),
    ("get", "/api/v1/posture/profile/{issue_id}"),
    ("get", "/api/v1/posture/priorities"),
    ("post", "/api/v1/posture/goals/confirm"),
]

# Routes that are publicly accessible (no auth).
PUBLIC_ROUTES = [
    ("get", "/api/v1/posture/issues"),
    ("get", "/api/v1/posture/issues/{issue_id}"),
    ("get", "/api/v1/posture/issues/{issue_id}/related"),
]


@pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
def test_protected_routes_have_security_requirement(method, path, openapi_schema):
    """Every protected route must declare a security requirement."""
    operation = openapi_schema["paths"][path][method]
    assert "security" in operation, (
        f"{method.upper()} {path} must declare security requirement"
    )
    assert len(operation["security"]) > 0


@pytest.mark.parametrize("method,path", PUBLIC_ROUTES)
def test_public_routes_have_no_security_requirement(method, path, openapi_schema):
    """Public routes must not carry security requirements."""
    operation = openapi_schema["paths"][path][method]
    assert "security" not in operation or len(operation["security"]) == 0, (
        f"{method.upper()} {path} is public and must not require auth"
    )


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/v1/posture/assess"),
        ("post", "/api/v1/posture/assess/photo"),
        ("post", "/api/v1/posture/safety-signals"),
        ("post", "/api/v1/posture/goals/confirm"),
    ],
)
def test_post_routes_have_request_body_schema(method, path, openapi_schema):
    """POST routes that use declared Pydantic models must have requestBody."""
    operation = openapi_schema["paths"][path][method]
    assert "requestBody" in operation, (
        f"{method.upper()} {path} missing requestBody"
    )
    content = operation["requestBody"].get("content", {})
    assert "application/json" in content, (
        f"{method.upper()} {path} requestBody missing application/json"
    )
    schema = content["application/json"]["schema"]
    assert schema not in (None, {}), (
        f"{method.upper()} {path} has empty requestBody schema"
    )


def test_priorities_response_has_three_buckets(openapi_schema):
    """GET /priorities response must carry the three-way routing buckets."""
    schema = openapi_schema["paths"]["/api/v1/posture/priorities"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    resolved = _resolve_ref(schema, openapi_schema)
    props = resolved["properties"]
    for bucket in ("normal_candidates", "retest_required", "safety_blocked"):
        assert bucket in props, (
            f"priorities response missing {bucket} bucket"
        )
    assert "suggestion_id" in props
    assert "profile_version" in props


def test_confirm_response_has_goals_and_risk_version(openapi_schema):
    """POST /goals/confirm response must carry confirmed_goals + risk_version."""
    schema = openapi_schema["paths"]["/api/v1/posture/goals/confirm"]["post"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    resolved = _resolve_ref(schema, openapi_schema)
    props = resolved["properties"]
    assert "confirmed_goals" in props
    assert "risk_version" in props
    assert "can_generate_plan" in props


# ---------------------------------------------------------------------------
# Phase 2 Task 2: health profile OpenAPI contracts
# ---------------------------------------------------------------------------

HEALTH_ROUTES = [
    ("get", "/api/v1/health/profile"),
    ("put", "/api/v1/health/profile"),
    ("delete", "/api/v1/health/profile"),
]


@pytest.mark.parametrize("method,path", HEALTH_ROUTES)
def test_health_route_has_response_schema(method, path, openapi_schema):
    """Each health/profile route must expose a non-empty 200 JSON schema."""
    paths = openapi_schema["paths"]
    assert path in paths, f"Path {path} not found in OpenAPI paths"
    operation = paths[path][method]
    responses = operation["responses"]
    assert "200" in responses, f"{method.upper()} {path} missing 200 response"
    content = responses["200"]["content"]
    assert "application/json" in content
    schema = content["application/json"]["schema"]
    assert schema not in (None, {}), f"{method.upper()} {path} has empty schema"


@pytest.mark.parametrize("method,path", HEALTH_ROUTES)
def test_health_routes_are_protected(method, path, openapi_schema):
    """All health/profile routes must declare a security requirement
    (JWT-only; ownership from token, never request body)."""
    operation = openapi_schema["paths"][path][method]
    assert "security" in operation and len(operation["security"]) > 0, (
        f"{method.upper()} {path} must require auth"
    )


def test_health_put_has_request_body(openapi_schema):
    """PUT /api/v1/health/profile must declare a requestBody schema."""
    operation = openapi_schema["paths"]["/api/v1/health/profile"]["put"]
    assert "requestBody" in operation
    content = operation["requestBody"]["content"]
    assert "application/json" in content
    schema = content["application/json"]["schema"]
    assert schema not in (None, {})


@pytest.mark.parametrize("method", ["get", "put"])
def test_health_profile_result_response_shape(method, openapi_schema):
    """GET/PUT response carries configured + profile + readiness, and the
    readiness component exposes the deterministic classifier fields."""
    schema = openapi_schema["paths"]["/api/v1/health/profile"][method][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    resolved = _resolve_ref(schema, openapi_schema)
    props = resolved["properties"]
    for field in ("configured", "profile", "readiness"):
        assert field in props, f"{method.upper()} response missing {field}"

    readiness = _resolve_ref(props["readiness"], openapi_schema)
    for field in ("readiness", "risk_version", "reason", "missing_fields"):
        assert field in readiness["properties"], (
            f"readiness component missing {field}"
        )


def test_health_update_component_has_editable_fields(openapi_schema):
    """The PUT request component (HealthProfileUpdate) must carry the editable
    fields and forbid extras (it must NOT accept version/timestamps)."""
    component = openapi_schema["components"]["schemas"]["HealthProfileUpdate"]
    props = component["properties"]
    for field in (
        "fitness_goal",
        "training_experience",
        "weekly_frequency",
        "session_duration_minutes",
        "equipment",
        "pain_injury_limitations",
        "risk_screen",
        "allergies",
        "diet_exclusions",
    ):
        assert field in props, f"HealthProfileUpdate missing {field}"
    # Server-managed fields are NOT client-settable.
    for forbidden in ("version", "created_at", "updated_at", "id"):
        assert forbidden not in props, (
            f"HealthProfileUpdate must not accept server-managed {forbidden}"
        )
    assert component.get("additionalProperties") is False, (
        "HealthProfileUpdate must forbid extra fields"
    )


# ---------------------------------------------------------------------------
# Phase 2 Task 3: daily check-in OpenAPI contracts
# ---------------------------------------------------------------------------

CHECKIN_ROUTES = [
    ("get", "/api/v1/health/checkins/today"),
    ("put", "/api/v1/health/checkins/today"),
    ("get", "/api/v1/health/checkins"),
    ("delete", "/api/v1/health/checkins/{checkin_id}"),
]


@pytest.mark.parametrize("method,path", CHECKIN_ROUTES)
def test_checkin_route_has_response_schema(method, path, openapi_schema):
    """Each check-in route must expose a non-empty 200 JSON schema."""
    paths = openapi_schema["paths"]
    assert path in paths, f"Path {path} not found in OpenAPI paths"
    operation = paths[path][method]
    responses = operation["responses"]
    assert "200" in responses, f"{method.upper()} {path} missing 200 response"
    content = responses["200"]["content"]
    assert "application/json" in content
    schema = content["application/json"]["schema"]
    assert schema not in (None, {}), f"{method.upper()} {path} has empty schema"


@pytest.mark.parametrize("method,path", CHECKIN_ROUTES)
def test_checkin_routes_are_protected(method, path, openapi_schema):
    """All check-in routes must declare a security requirement (JWT-only;
    ownership from token, never request body or path user_id)."""
    operation = openapi_schema["paths"][path][method]
    assert "security" in operation and len(operation["security"]) > 0, (
        f"{method.upper()} {path} must require auth"
    )


def test_checkin_put_has_request_body(openapi_schema):
    """PUT /api/v1/health/checkins/today must declare a requestBody schema."""
    operation = openapi_schema["paths"]["/api/v1/health/checkins/today"]["put"]
    assert "requestBody" in operation
    content = operation["requestBody"]["content"]
    assert "application/json" in content
    schema = content["application/json"]["schema"]
    assert schema not in (None, {})


def test_checkin_today_get_response_shape(openapi_schema):
    """GET /checkins/today response is the envelope: checked_in + checkin, and
    the checkin component exposes the deterministic risk_summary field."""
    schema = openapi_schema["paths"]["/api/v1/health/checkins/today"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    resolved = _resolve_ref(schema, openapi_schema)
    props = resolved["properties"]
    for field in ("checked_in", "checkin"):
        assert field in props, f"GET /today response missing {field}"

    checkin_ref = props["checkin"]
    checkin_schema = _resolve_ref(checkin_ref, openapi_schema)
    # ``checkin`` is nullable (anyOf with a $ref); resolve to the component.
    if "anyOf" in checkin_schema:
        for branch in checkin_schema["anyOf"]:
            if "$ref" in branch:
                checkin_schema = _resolve_ref(branch, openapi_schema)
                break
    assert "risk_summary" in checkin_schema["properties"], (
        "CheckInResponse component must expose risk_summary"
    )


def test_checkin_today_put_response_shape(openapi_schema):
    """PUT /checkins/today returns the stored CheckInResponse directly, which
    must expose the deterministic risk_summary / risk_version fields."""
    schema = openapi_schema["paths"]["/api/v1/health/checkins/today"]["put"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    resolved = _resolve_ref(schema, openapi_schema)
    assert "risk_summary" in resolved["properties"], (
        "PUT /today response must expose risk_summary"
    )
    assert "risk_version" in resolved["properties"]


def test_checkin_response_component_fields(openapi_schema):
    """The CheckInResponse component must carry the deterministic safety
    fields and forbid extras (no client-settable risk_summary/risk_version)."""
    component = openapi_schema["components"]["schemas"]["CheckInResponse"]
    props = component["properties"]
    for field in (
        "id",
        "local_date",
        "sleep_quality",
        "energy",
        "muscle_soreness",
        "available_time",
        "daily_status",
        "abnormal_pain",
        "pain_followup",
        "risk_summary",
        "risk_version",
    ):
        assert field in props, f"CheckInResponse missing {field}"
    assert component.get("additionalProperties") is False, (
        "CheckInResponse must forbid extra fields"
    )


def test_pain_followup_component_fields(openapi_schema):
    """PainFollowup must carry the structured red-flag boolean signals."""
    component = openapi_schema["components"]["schemas"]["PainFollowup"]
    props = component["properties"]
    for field in (
        "pain_area",
        "pain_started",
        "pain_intensity",
        "has_neurological_symptom",
        "has_dizziness_or_chest_symptom",
        "has_acute_trauma",
    ):
        assert field in props, f"PainFollowup missing {field}"
    assert component.get("additionalProperties") is False


# ---------------------------------------------------------------------------
# Phase 2 Task 4: weight / trend / activity-grid OpenAPI contracts
# ---------------------------------------------------------------------------

WEIGHT_GRID_ROUTES = [
    ("post", "/api/v1/health/weight-records"),
    ("get", "/api/v1/health/weight-records"),
    ("put", "/api/v1/health/weight-records/{record_id}"),
    ("delete", "/api/v1/health/weight-records/{record_id}"),
    ("get", "/api/v1/health/trends/weight"),
    ("get", "/api/v1/health/activity-grid"),
]


@pytest.mark.parametrize("method,path", WEIGHT_GRID_ROUTES)
def test_weight_grid_route_has_response_schema(method, path, openapi_schema):
    """Each weight / trend / grid route must expose a non-empty 200 schema."""
    paths = openapi_schema["paths"]
    assert path in paths, f"Path {path} not found in OpenAPI paths"
    operation = paths[path][method]
    responses = operation["responses"]
    assert "200" in responses, f"{method.upper()} {path} missing 200 response"
    content = responses["200"]["content"]
    assert "application/json" in content
    schema = content["application/json"]["schema"]
    assert schema not in (None, {}), f"{method.upper()} {path} has empty schema"


@pytest.mark.parametrize("method,path", WEIGHT_GRID_ROUTES)
def test_weight_grid_routes_are_protected(method, path, openapi_schema):
    """All weight / trend / grid routes must require auth (JWT-only)."""
    operation = openapi_schema["paths"][path][method]
    assert "security" in operation and len(operation["security"]) > 0, (
        f"{method.upper()} {path} must require auth"
    )


def test_weight_post_put_have_request_body(openapi_schema):
    """POST and PUT weight-records must declare a requestBody schema."""
    for method in ("post", "put"):
        path = "/api/v1/health/weight-records" if method == "post" else (
            "/api/v1/health/weight-records/{record_id}"
        )
        operation = openapi_schema["paths"][path][method]
        assert "requestBody" in operation, f"{method.upper()} {path} missing body"
        schema = operation["requestBody"]["content"]["application/json"]["schema"]
        assert schema not in (None, {})


def test_weight_record_component_fields(openapi_schema):
    """WeightRecordResponse must carry weight_kg + source and forbid extras
    (no client-settable id / source / timestamps)."""
    component = openapi_schema["components"]["schemas"]["WeightRecordResponse"]
    props = component["properties"]
    for field in ("id", "recorded_at", "weight_kg", "source", "note", "created_at", "updated_at"):
        assert field in props, f"WeightRecordResponse missing {field}"
    assert component.get("additionalProperties") is False


def test_weight_create_component_forbids_source(openapi_schema):
    """WeightRecordCreate must NOT accept a client-supplied source (server-set
    to manual); it carries the bounded weight_kg only."""
    component = openapi_schema["components"]["schemas"]["WeightRecordCreate"]
    props = component["properties"]
    assert "weight_kg" in props
    assert "source" not in props, "WeightRecordCreate must not accept source"
    assert "id" not in props
    assert component.get("additionalProperties") is False


def test_weight_trend_response_shape(openapi_schema):
    """GET /trends/weight response carries records + trend + window +
    sufficient, and the trend point exposes recorded_at + weight_kg."""
    schema = openapi_schema["paths"]["/api/v1/health/trends/weight"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    resolved = _resolve_ref(schema, openapi_schema)
    for field in ("records", "trend", "window", "sufficient"):
        assert field in resolved["properties"], f"trend response missing {field}"

    trend_point = _resolve_ref(resolved["properties"]["trend"]["items"], openapi_schema)
    assert "recorded_at" in trend_point["properties"]
    assert "weight_kg" in trend_point["properties"]


def test_activity_grid_response_shape(openapi_schema):
    """GET /activity-grid response carries start_date + end_date + cells, and
    the cell exposes date + status."""
    schema = openapi_schema["paths"]["/api/v1/health/activity-grid"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    resolved = _resolve_ref(schema, openapi_schema)
    for field in ("start_date", "end_date", "cells"):
        assert field in resolved["properties"], f"grid response missing {field}"

    cell = _resolve_ref(resolved["properties"]["cells"]["items"], openapi_schema)
    assert "date" in cell["properties"]
    assert "status" in cell["properties"]


def test_activity_grid_status_enum_is_phase2_only(openapi_schema):
    """The grid cell status enum must be exactly the Phase 2 set and must NOT
    include plan-execution statuses (partial_execution / main_plan_completed)."""
    schema = openapi_schema["paths"]["/api/v1/health/activity-grid"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    resolved = _resolve_ref(schema, openapi_schema)
    cell = _resolve_ref(resolved["properties"]["cells"]["items"], openapi_schema)
    status_ref = cell["properties"]["status"]
    status_schema = _resolve_ref(status_ref, openapi_schema)

    enum_values = set(status_schema.get("enum", []))
    assert enum_values == {
        "none",
        "checked_in",
        "active_rest",
        "safety_adjustment",
    }, f"unexpected grid status enum: {enum_values}"
    assert "partial_execution" not in enum_values
    assert "main_plan_completed" not in enum_values
