from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ConsentRequest(BaseModel):
    action: Literal["grant", "withdraw"]
    notice_version: str = Field(..., min_length=1, max_length=64)


class ConsentStateResponse(BaseModel):
    purpose: str
    active: bool
    notice_version: Optional[str] = None
    sequence_no: int = 0
    occurred_at: Optional[datetime] = None


class PrivacyExportResponse(BaseModel):
    schema_version: str
    generated_at: datetime
    subject_id: str
    identity: Dict[str, Any]
    consent_history: List[Dict[str, Any]]
    domain_records: Dict[str, List[Dict[str, Any]]]
    excluded_security_fields: List[str]


class AccountDeletionRequest(BaseModel):
    provider_id: str = Field(
        default="offline_password", min_length=3, max_length=32,
        pattern=r"^[a-z0-9_]+$",
    )
    credential: str = Field(..., min_length=6, max_length=128)
    device_key: str = Field(..., min_length=32, max_length=128)


class AccountDeletionResponse(BaseModel):
    status: str
    receipt_id: Optional[str] = None
