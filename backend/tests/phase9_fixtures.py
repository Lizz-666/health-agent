"""Disposable synthetic controls for Phase 9 reliability acceptance."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import hmac
from pathlib import Path
import uuid

from fastapi import Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update

from app.auth.credentials import hash_password
from app.auth.models import (
    AuthSession,
    TrialCredential,
    TrialInvitation,
    User,
)
from app.core.config import settings
from app.core.exceptions import AppException
from app.db.base import Base


PRIMARY_USER_ID = uuid.UUID("90000000-0000-4000-8000-000000000001")
SECONDARY_USER_ID = uuid.UUID("90000000-0000-4000-8000-000000000002")
PRIMARY_ACCOUNT = "synthetic-trial-01"
SECONDARY_ACCOUNT = "synthetic-trial-02"
PRIMARY_CREDENTIAL = "Synthetic-trial-passphrase-01"
SECONDARY_CREDENTIAL = "Synthetic-trial-passphrase-02"
PRIMARY_INVITATION = "synthetic_trial_invitation_0000000000000001"
SECONDARY_INVITATION = "synthetic_trial_invitation_0000000000000002"
PRIMARY_DEVICE = "synthetic-device-key-0000000000000001"
SECONDARY_DEVICE = "synthetic-device-key-0000000000000002"
OTHER_DEVICE = "synthetic-device-key-0000000000000099"
CONTROL_HEADER = "X-Phase9-Control-Token"
CONTROL_TOKEN = "phase9-local-control-only"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SyntheticAccount(str, Enum):
    primary = "primary"
    secondary = "secondary"


class FaultKind(str, Enum):
    slow_response = "slow_response"
    service_unavailable = "service_unavailable"


class FaultRoute(str, Enum):
    user_profile = "/api/v1/user/profile"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FaultRequest(_StrictModel):
    route: FaultRoute
    kind: FaultKind
    delay_ms: int = Field(default=600, ge=100, le=2000)


class SessionRequest(_StrictModel):
    account: SyntheticAccount


class CompatibilityRequest(_StrictModel):
    minimum: int = Field(..., ge=1, le=1000000)
    maximum: int = Field(..., ge=1, le=1000000)


class Phase9Control:
    def __init__(self, *, engine, session_factory, expected_db_path: Path) -> None:
        self.engine = engine
        self.session_factory = session_factory
        self.expected_db_path = expected_db_path.resolve()
        self.reset_generation = 0
        self._reset_lock = asyncio.Lock()
        self._faults: dict[tuple[str, str], tuple[FaultKind, int]] = {}

    def _authorize(self, value: str) -> None:
        if not hmac.compare_digest(value, CONTROL_TOKEN):
            raise AppException(
                403, "Invalid test control token", "phase9_control_forbidden"
            )

    def _require_disposable_db(self) -> None:
        if self.engine.url.drivername != "sqlite+aiosqlite":
            raise RuntimeError("Phase 9 reset requires sqlite+aiosqlite")
        actual = Path(self.engine.url.database or "").resolve()
        if actual != self.expected_db_path:
            raise RuntimeError("Phase 9 reset refuses a non-disposable database")

    @staticmethod
    def _account_id(account: SyntheticAccount) -> uuid.UUID:
        return (
            PRIMARY_USER_ID
            if account == SyntheticAccount.primary
            else SECONDARY_USER_ID
        )

    async def reset(self) -> dict:
        self._require_disposable_db()
        if self._reset_lock.locked():
            raise AppException(
                409, "Test reset in progress", "phase9_reset_in_progress"
            )
        async with self._reset_lock:
            async with self.engine.begin() as connection:
                await connection.run_sync(Base.metadata.drop_all)
                await connection.run_sync(Base.metadata.create_all)
            async with self.session_factory() as db:
                now = datetime.now(timezone.utc)
                rows = (
                    (
                        PRIMARY_USER_ID,
                        PRIMARY_ACCOUNT,
                        PRIMARY_CREDENTIAL,
                        PRIMARY_INVITATION,
                    ),
                    (
                        SECONDARY_USER_ID,
                        SECONDARY_ACCOUNT,
                        SECONDARY_CREDENTIAL,
                        SECONDARY_INVITATION,
                    ),
                )
                for user_id, account, credential, invitation in rows:
                    db.add(User(id=user_id, phone=None))
                    db.add(
                        TrialCredential(
                            user_id=user_id,
                            login_id=account,
                            credential_hash=hash_password(credential),
                        )
                    )
                    db.add(
                        TrialInvitation(
                            user_id=user_id,
                            code_digest=_digest(invitation),
                            expires_at=now + timedelta(days=1),
                        )
                    )
                await db.commit()
            self._faults.clear()
            settings.MIN_ANDROID_CLIENT_VERSION_CODE = 1
            settings.MAX_ANDROID_CLIENT_VERSION_CODE = 1
            self.reset_generation += 1
            return await self.evidence()

    async def expire_sessions(self, account: SyntheticAccount) -> None:
        async with self.session_factory() as db:
            await db.execute(
                update(AuthSession)
                .where(AuthSession.user_id == self._account_id(account))
                .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
            )
            await db.commit()

    async def revoke_sessions(self, account: SyntheticAccount) -> None:
        async with self.session_factory() as db:
            await db.execute(
                update(AuthSession)
                .where(
                    AuthSession.user_id == self._account_id(account),
                    AuthSession.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(timezone.utc))
            )
            await db.commit()

    async def evidence(self) -> dict:
        counts: dict[str, int] = {}
        async with self.session_factory() as db:
            for table in Base.metadata.sorted_tables:
                counts[table.name] = int(
                    await db.scalar(select(func.count()).select_from(table)) or 0
                )
            active_sessions = int(
                await db.scalar(
                    select(func.count())
                    .select_from(AuthSession)
                    .where(
                        AuthSession.revoked_at.is_(None),
                        AuthSession.expires_at > datetime.now(timezone.utc),
                    )
                )
                or 0
            )
        return {
            "synthetic_only": True,
            "reset_generation": self.reset_generation,
            "active_sessions": active_sessions,
            "table_counts": counts,
        }

    def install(self, app) -> None:
        @app.middleware("http")
        async def one_shot_fault(request: Request, call_next):
            path = str((getattr(request, "scope", {}) or {}).get("path") or "")
            fault = self._faults.pop((request.method, path), None)
            if fault is not None:
                kind, delay_ms = fault
                if kind == FaultKind.slow_response:
                    await asyncio.sleep(delay_ms / 1000)
                elif kind == FaultKind.service_unavailable:
                    return JSONResponse(
                        status_code=503,
                        content={
                            "detail": "Synthetic service fault",
                            "code": "service_unavailable",
                        },
                    )
            return await call_next(request)

        @app.post("/__phase9/reset")
        async def reset_route(token: str = Header(..., alias=CONTROL_HEADER)):
            self._authorize(token)
            return await self.reset()

        @app.post("/__phase9/faults")
        async def fault_route(
            body: FaultRequest,
            token: str = Header(..., alias=CONTROL_HEADER),
        ):
            self._authorize(token)
            self._faults[("GET", body.route.value)] = (body.kind, body.delay_ms)
            return {"status": "installed"}

        @app.post("/__phase9/sessions/expire")
        async def expire_route(
            body: SessionRequest,
            token: str = Header(..., alias=CONTROL_HEADER),
        ):
            self._authorize(token)
            await self.expire_sessions(body.account)
            return {"status": "expired"}

        @app.post("/__phase9/sessions/revoke")
        async def revoke_route(
            body: SessionRequest,
            token: str = Header(..., alias=CONTROL_HEADER),
        ):
            self._authorize(token)
            await self.revoke_sessions(body.account)
            return {"status": "revoked"}

        @app.post("/__phase9/compatibility")
        async def compatibility_route(
            body: CompatibilityRequest,
            token: str = Header(..., alias=CONTROL_HEADER),
        ):
            self._authorize(token)
            if body.maximum < body.minimum:
                raise AppException(
                    422, "Invalid version window", "phase9_invalid_control"
                )
            settings.MIN_ANDROID_CLIENT_VERSION_CODE = body.minimum
            settings.MAX_ANDROID_CLIENT_VERSION_CODE = body.maximum
            return {"status": "configured"}

        @app.get("/__phase9/evidence")
        async def evidence_route(token: str = Header(..., alias=CONTROL_HEADER)):
            self._authorize(token)
            return await self.evidence()


__all__ = [
    "CONTROL_HEADER",
    "CONTROL_TOKEN",
    "OTHER_DEVICE",
    "PRIMARY_ACCOUNT",
    "PRIMARY_CREDENTIAL",
    "PRIMARY_DEVICE",
    "PRIMARY_INVITATION",
    "SECONDARY_ACCOUNT",
    "SECONDARY_CREDENTIAL",
    "SECONDARY_DEVICE",
    "SECONDARY_INVITATION",
    "Phase9Control",
]
