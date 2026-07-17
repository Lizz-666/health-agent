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
