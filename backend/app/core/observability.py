"""Small, allowlisted observability surface for security-relevant events.

Callers may select only a reviewed event code and outcome. They cannot attach
arbitrary values, request bodies, credentials, health text, or object keys.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar, Token
from enum import Enum
from typing import Optional


class SecurityEventCode(str, Enum):
    AUTH_TRIAL_ACTIVATION = "auth.trial_activation"
    AUTH_TRIAL_LOGIN = "auth.trial_login"
    PRIVACY_CONSENT = "privacy.consent"
    PRIVACY_EXPORT = "privacy.export"
    PRIVACY_ACCOUNT_DELETION = "privacy.account_deletion"
    RESTORE_DELETED_SUBJECT = "privacy.restore_deleted_subject"
    REQUEST_VALIDATION = "request.validation"
    REQUEST_UNHANDLED = "request.unhandled"


class SecurityEventOutcome(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


_request_id: ContextVar[str] = ContextVar("request_id", default="unavailable")


def normalize_request_id(raw_value: Optional[str]) -> str:
    # Never trust or log a client value; it may be a credential that happens
    # to match an identifier grammar.
    del raw_value
    return uuid.uuid4().hex


def bind_request_id(request_id: str) -> Token:
    return _request_id.set(request_id)


def reset_request_id(token: Token) -> None:
    _request_id.reset(token)


def current_request_id() -> str:
    return _request_id.get()


def emit_security_event(
    logger: logging.Logger,
    code: SecurityEventCode,
    outcome: SecurityEventOutcome,
    *,
    count: Optional[int] = None,
) -> None:
    """Emit only stable, non-sensitive fields from a closed schema."""
    if not isinstance(code, SecurityEventCode):
        raise TypeError("security event code must be allowlisted")
    if not isinstance(outcome, SecurityEventOutcome):
        raise TypeError("security event outcome must be allowlisted")
    if count is not None and (
        isinstance(count, bool) or not isinstance(count, int) or count < 0
    ):
        raise ValueError("security event count must be a non-negative integer")
    suffix = "" if count is None else f" count={count}"
    logger.info(
        "security_event code=%s outcome=%s request_id=%s%s",
        code.value,
        outcome.value,
        current_request_id(),
        suffix,
    )
