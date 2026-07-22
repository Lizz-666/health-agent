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
