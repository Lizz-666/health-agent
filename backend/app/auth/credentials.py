from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Protocol


SCRYPT_N = 1 << 15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 64 * 1024 * 1024


@dataclass(frozen=True)
class CredentialResult:
    accepted: bool
    provider_result: str


class CredentialProvider(Protocol):
    provider_id: str

    def verify(self, password: str, encoded_hash: str) -> CredentialResult: ...


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=32,
        maxmem=SCRYPT_MAXMEM,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${derived.hex()}"


class OfflinePasswordProvider:
    provider_id = "offline_password"

    def verify(self, password: str, encoded_hash: str) -> CredentialResult:
        try:
            algorithm, n, r, p, salt, expected = encoded_hash.split("$", 5)
            if algorithm != "scrypt":
                raise ValueError("unsupported hash")
            if (int(n), int(r), int(p)) != (SCRYPT_N, SCRYPT_R, SCRYPT_P):
                raise ValueError("unsupported hash parameters")
            actual = hashlib.scrypt(
                password.encode("utf-8"),
                salt=bytes.fromhex(salt),
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=len(bytes.fromhex(expected)),
                maxmem=SCRYPT_MAXMEM,
            )
            accepted = hmac.compare_digest(actual.hex(), expected)
        except (ValueError, TypeError):
            accepted = False
        return CredentialResult(accepted=accepted, provider_result="accepted" if accepted else "rejected")


offline_password_provider = OfflinePasswordProvider()
