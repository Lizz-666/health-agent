"""Photo ownership verification boundary (spec §10.0 / §10.4 / Task 7).

A side-effect Tool that accepts ``photo_keys`` (``analyze_posture_photo``)
MUST prove every key belongs to the caller before the photo analysis path can
proceed. This module owns that proof.

Hard rules (spec §10.0 / plan Task 7):

- ``PhotoOwnershipVerifier`` is a Protocol backed by a real provider in
  production. Phase 1 ships NO provider-backed implementation, so the default
  verifier (``FailClosedPhotoOwnershipVerifier``) ALWAYS rejects with
  ``PhotoOwnershipUnavailable`` -- never ``owned``.
- An object key's path prefix (e.g. ``posture_photos/{user_id}/...``) is NOT
  ownership evidence. It is trivially forged by any caller, so the default
  verifier does not parse it. Only a real provider-backed verifier that
  checks the caller's uploaded-object index may assert ownership.
- The default verifier is fail-closed: when no provider is wired, photo
  analysis is rejected. This is a privacy boundary, not a feature toggle.

Important invariant: a test fake that returns ``owned`` can NEVER enable the
production photo path on its own. The Tool checks ``privacy_gate`` FIRST
(``evaluate_photo_privacy_gate``), which in Phase 1 hard-rejects because none
of the 8 enablement conditions carry evidence. So even with a fake-owned
verifier installed, ``analyze_posture_photo`` still raises
``PhotoAnalysisDisabled``. The fake only exercises the ownership branch in
isolation (unit tests), it is not a production gate bypass.

Error mapping (consumed by the Tool / REST layer):

- ``PhotoOwnershipDenied``     -> HTTP 400 ``photo_ownership_denied`` (cross-user)
- ``PhotoOwnershipUnavailable`` -> HTTP 503 ``photo_ownership_unavailable``
  (no provider; the privacy gate rejects even earlier with
  ``photo_analysis_disabled`` in Phase 1)
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Protocol, List

from app.core.exceptions import AppException


class PhotoOwnershipDenied(AppException):
    """The caller supplied a photo key that belongs to another user."""

    def __init__(self, detail: str = "photo_keys 不属于当前用户") -> None:
        super().__init__(400, detail, "photo_ownership_denied")


class PhotoOwnershipUnavailable(AppException):
    """No trustworthy ownership backend is wired; fail closed."""

    def __init__(
        self, detail: str = "photo_keys 所有权校验后端不可用，已 fail closed"
    ) -> None:
        super().__init__(503, detail, "photo_ownership_unavailable")


class PhotoOwnershipVerifier(Protocol):
    """Ownership proof boundary for photo analysis (spec §10.0 / §10.4).

    Implementations MUST consult a real provider-backed index of the caller's
    uploaded objects. Path-prefix parsing is explicitly forbidden as proof.

    ``verify`` returns ``None`` on success (every key belongs to ``user_id``)
    and raises ``PhotoOwnershipDenied`` on a cross-user key. A verifier that
    cannot answer (no backend) raises ``PhotoOwnershipUnavailable``.
    """

    async def verify(
        self, user_id: str, photo_keys: List[str]
    ) -> None:  # pragma: no cover - protocol body
        ...


class FailClosedPhotoOwnershipVerifier:
    """Phase 1 default. Always rejects with ``PhotoOwnershipUnavailable``.

    Does NOT inspect the key path prefix: a forged ``posture_photos/<user_id>``
    prefix is not ownership evidence (spec §10.0). A trivial format pre-check
    (non-empty, length cap) surfaces obviously malformed input as 400 so the
    caller cannot ship a megabyte-long key string, but format validity is
    never interpreted as ownership.
    """

    _MAX_KEYS = 20
    _MAX_KEY_LEN = 512

    async def verify(self, user_id: str, photo_keys: List[str]) -> None:
        # Format pre-check only: NEVER a proof of ownership. Reject obviously
        # malformed input loudly; do not fall through to "unavailable" for it.
        if not isinstance(photo_keys, list) or not photo_keys:
            raise PhotoOwnershipDenied("photo_keys 不能为空")
        if len(photo_keys) > self._MAX_KEYS:
            raise PhotoOwnershipDenied("photo_keys 数量超出上限")
        for key in photo_keys:
            if not isinstance(key, str) or not key.strip():
                raise PhotoOwnershipDenied("photo_keys 包含空值")
            if len(key) > self._MAX_KEY_LEN:
                raise PhotoOwnershipDenied("photo_keys 长度超出上限")
        # No provider is wired in Phase 1: fail closed. The privacy gate
        # rejects even earlier with PhotoAnalysisDisabled; this is the defense
        # in depth for direct Tool callers.
        raise PhotoOwnershipUnavailable()


# Module-level active verifier. Tests swap this via
# ``using_photo_ownership_verifier``; production code reads it via
# ``get_photo_ownership_verifier``. The default is fail-closed.
_active_verifier: PhotoOwnershipVerifier = FailClosedPhotoOwnershipVerifier()


def get_photo_ownership_verifier() -> PhotoOwnershipVerifier:
    """Return the currently active ownership verifier (fail-closed by default)."""
    return _active_verifier


def set_photo_ownership_verifier(verifier: PhotoOwnershipVerifier) -> None:
    """Replace the active verifier.

    Intended for tests / controlled DI. Even when a test installs a fake that
    returns ``owned``, the photo privacy gate still hard-rejects in Phase 1, so
    a fake cannot enable the production photo path.
    """
    global _active_verifier
    _active_verifier = verifier


@contextmanager
def using_photo_ownership_verifier(
    verifier: PhotoOwnershipVerifier,
) -> Iterator[PhotoOwnershipVerifier]:
    """Context manager that swaps the active verifier and restores it on exit.

    Use this in tests to exercise the owned / denied / unavailable branches of
    the ownership boundary in isolation. The previous verifier is always
    restored, even if the test body raises.
    """
    global _active_verifier
    previous = _active_verifier
    _active_verifier = verifier
    try:
        yield verifier
    finally:
        _active_verifier = previous
