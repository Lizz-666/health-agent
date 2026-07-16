"""Unit tests for the external ``PG_TEST_DSN`` safety guards in conftest_pg.py.

These exercise the PURE guard functions ONLY — no database or Docker is
required, so they run in every environment and are independent of the
``pg_available`` gate. They pin the rules that prevent a misconfigured
``PG_TEST_DSN`` from wiping a development/production database:

  * a non-test database name is rejected,
  * a missing ``PG_TEST_ALLOW_DESTRUCTIVE`` switch is rejected,
  * a forbidden production/development name is rejected (even with the switch),
  * a valid test name + the switch is allowed,
  * the DSN password is never surfaced by masked output.
"""
import pytest

from tests.conftest_pg import (
    PGSafetyError,
    _FORBIDDEN_DB_NAMES,
    _is_test_db_name,
    _mask_dsn,
    _parse_db_name_from_dsn,
    _validate_external_dsn,
)

_DSN = "postgresql+asyncpg://postgres:s3cr3t-pw@localhost:55499/posture_pg_test"


# --- _mask_dsn -------------------------------------------------------------


def test_mask_dsn_hides_password():
    masked = _mask_dsn(_DSN)
    assert "s3cr3t-pw" not in masked
    assert "***" in masked
    assert masked == (
        "postgresql+asyncpg://postgres:***@localhost:55499/posture_pg_test"
    )


def test_mask_dsn_password_with_special_chars():
    dsn = "postgresql+asyncpg://u:p@ss!word@h:5432/db"
    masked = _mask_dsn(dsn)
    assert "p@ss!word" not in masked
    assert "ss!word" not in masked
    assert "***" in masked


def test_mask_dsn_no_password_unchanged():
    dsn = "postgresql+asyncpg://user@localhost:55499/posture_pg_test"
    assert _mask_dsn(dsn) == dsn


def test_mask_dsn_leaves_unrelated_text_intact():
    out = "alembic upgrade head\nrunning revision 0002 on db"
    assert _mask_dsn(out) == out


# --- _is_test_db_name ------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "posture_pg_test",
        "posture_pg_test_20260711",
        "posture_pg_test_xyz",
        "Posture_PG_Test",  # case-insensitive
    ],
)
def test_is_test_db_name_accepts_test_patterns(name):
    assert _is_test_db_name(name)


@pytest.mark.parametrize(
    "name",
    [
        "posture_app",
        "postgres",
        "posture",
        "health",
        "production",
        "testing",   # contains 'test' but is NOT a _test suffix
        "test_db",   # prefix, not suffix
        "test",      # bare 'test' is not '_test'
        "myapp_test",
        "anything_test",
        "",
        None,
    ],
)
def test_is_test_db_name_rejects_non_test(name):
    assert not _is_test_db_name(name)


# --- _parse_db_name_from_dsn ----------------------------------------------


def test_parse_db_name_simple():
    assert _parse_db_name_from_dsn(_DSN) == "posture_pg_test"


def test_parse_db_name_with_query_string():
    dsn = "postgresql+asyncpg://u:p@h:5432/posture_pg_test_2026?sslmode=require"
    assert _parse_db_name_from_dsn(dsn) == "posture_pg_test_2026"


def test_parse_db_name_missing_returns_none():
    assert _parse_db_name_from_dsn("postgresql+asyncpg://u:p@h:5432/") is None
    assert _parse_db_name_from_dsn("not a url") is None


# --- _validate_external_dsn ----------------------------------------------


def test_validate_requires_destructive_switch(monkeypatch):
    monkeypatch.delenv("PG_TEST_ALLOW_DESTRUCTIVE", raising=False)
    with pytest.raises(PGSafetyError, match="PG_TEST_ALLOW_DESTRUCTIVE"):
        _validate_external_dsn(_DSN)


@pytest.mark.parametrize("value", ["", "0", "false", "yes", "true", "2"])
def test_validate_rejects_switch_not_exactly_one(monkeypatch, value):
    monkeypatch.setenv("PG_TEST_ALLOW_DESTRUCTIVE", value)
    with pytest.raises(PGSafetyError, match="PG_TEST_ALLOW_DESTRUCTIVE"):
        _validate_external_dsn(_DSN)


def test_validate_rejects_non_test_db_name(monkeypatch):
    monkeypatch.setenv("PG_TEST_ALLOW_DESTRUCTIVE", "1")
    # ``posture_dev`` is neither forbidden nor a test-pattern name.
    dsn = "postgresql+asyncpg://postgres:pw@localhost:55499/posture_dev"
    with pytest.raises(PGSafetyError, match="test pattern"):
        _validate_external_dsn(dsn)


@pytest.mark.parametrize("bad", sorted(_FORBIDDEN_DB_NAMES))
def test_validate_rejects_forbidden_production_names(monkeypatch, bad):
    monkeypatch.setenv("PG_TEST_ALLOW_DESTRUCTIVE", "1")
    dsn = f"postgresql+asyncpg://postgres:pw@localhost:55499/{bad}"
    with pytest.raises(PGSafetyError):
        _validate_external_dsn(dsn)


def test_validate_forbidden_name_beats_test_suffix(monkeypatch):
    # A forbidden name is rejected even if it happened to be misclassified as
    # a test name; forbidden takes precedence.
    monkeypatch.setenv("PG_TEST_ALLOW_DESTRUCTIVE", "1")
    dsn = "postgresql+asyncpg://postgres:pw@localhost:55499/postgres"
    with pytest.raises(PGSafetyError, match="forbidden"):
        _validate_external_dsn(dsn)


def test_validate_allows_valid_test_db_and_masks_password(monkeypatch):
    monkeypatch.setenv("PG_TEST_ALLOW_DESTRUCTIVE", "1")
    masked = _validate_external_dsn(_DSN)
    assert "s3cr3t-pw" not in masked
    assert "***" in masked


def test_validate_rejects_arbitrary_test_suffix(monkeypatch):
    monkeypatch.setenv("PG_TEST_ALLOW_DESTRUCTIVE", "1")
    dsn = "postgresql+asyncpg://u:p@h:5432/devscratch_test"
    with pytest.raises(PGSafetyError, match="test pattern"):
        _validate_external_dsn(dsn)
