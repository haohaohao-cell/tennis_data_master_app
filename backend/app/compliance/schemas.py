from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

RequestStatus = Literal["requested", "processing", "ready", "failed", "expired", "cancelled", "review_required", "completed"]

class GovernanceRequestCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=120)

class ExportRequestRecord(BaseModel):
    export_request_id: str; requester_user_id: str; status: RequestStatus; idempotency_key: str
    created_at: str; updated_at: str; expires_at: str | None = None; completed_at: str | None = None; error_code: str | None = None
    dry_run_summary: dict[str, int] = Field(default_factory=dict)
    download_available: bool = False

class DeletionRequestRecord(BaseModel):
    deletion_request_id: str; requester_user_id: str; status: RequestStatus; idempotency_key: str
    requested_scope: str; dry_run_summary: dict[str, int] = Field(default_factory=dict)
    created_at: str; updated_at: str; completed_at: str | None = None; error_code: str | None = None

class GovernanceResponse(BaseModel):
    success: bool
    request: ExportRequestRecord | DeletionRequestRecord
