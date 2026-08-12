import logging

import pytest

from app.core.observability import (
    SecurityEventCode,
    SecurityEventOutcome,
    bind_request_id,
    emit_security_event,
    normalize_request_id,
    reset_request_id,
)


def test_security_event_schema_is_closed_and_contains_only_stable_fields(caplog):
    logger = logging.getLogger("test.security")
    token = bind_request_id("synthetic-request-0002")
    try:
        with caplog.at_level(logging.INFO, logger="test.security"):
            emit_security_event(
                logger,
                SecurityEventCode.PRIVACY_EXPORT,
                SecurityEventOutcome.SUCCEEDED,
                count=1,
            )
    finally:
        reset_request_id(token)

    assert caplog.text.endswith(
        "security_event code=privacy.export outcome=succeeded "
        "request_id=synthetic-request-0002 count=1\n"
    )
    with pytest.raises(TypeError, match="allowlisted"):
        emit_security_event(  # type: ignore[arg-type]
            logger,
            "privacy.export",
            SecurityEventOutcome.SUCCEEDED,
        )
    with pytest.raises(ValueError, match="non-negative"):
        emit_security_event(
            logger,
            SecurityEventCode.PRIVACY_EXPORT,
            SecurityEventOutcome.SUCCEEDED,
            count=-1,
        )


def test_untrusted_request_id_is_replaced_without_echoing_it():
    untrusted = "looks-like-a-valid-request-id-0001"
    normalized = normalize_request_id(untrusted)

    assert normalized != untrusted
    assert len(normalized) == 32
    assert normalized.isalnum()
