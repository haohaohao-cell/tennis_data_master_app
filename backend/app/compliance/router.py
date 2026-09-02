from __future__ import annotations
from typing import Annotated
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from backend.app.auth.dependencies import get_current_user
from backend.app.auth.schemas import UserPublic
from backend.app.compliance import service
from backend.app.compliance.schemas import GovernanceRequestCreate, GovernanceResponse, ExportRequestRecord
from backend.app.admin.dependencies import AdminActor, require_admin_actor
router = APIRouter(prefix="/compliance", tags=["compliance"])
User = Annotated[UserPublic, Depends(get_current_user)]
@router.post("/exports", response_model=GovernanceResponse)
def create_export(payload: GovernanceRequestCreate, user: User) -> GovernanceResponse: return service.create_export(user.user_id, payload)
@router.post("/exports/{request_id}/generate", response_model=ExportRequestRecord)
def generate_export(request_id: str, user: User): return service.generate_export(user.user_id, request_id)
@router.get("/exports/{request_id}/download")
def download_export(request_id: str, user: User): return FileResponse(service.export_file_path(user.user_id, request_id), media_type="application/json", filename="data-export.json")
@router.get("/admin/exports/{request_id}/download")
def admin_download_export(request_id: str, actor: Annotated[AdminActor, Depends(require_admin_actor)]): return FileResponse(service.export_file_path(actor.user.user_id, request_id, allow_admin=True), media_type="application/json", filename="data-export.json")
@router.get("/exports", response_model=list)
def list_exports(user: User): return service.list_requests(user.user_id, "export")
@router.post("/deletions", response_model=GovernanceResponse)
def create_deletion(payload: GovernanceRequestCreate, user: User) -> GovernanceResponse: return service.create_deletion(user.user_id, payload)
@router.get("/deletions", response_model=list)
def list_deletions(user: User): return service.list_requests(user.user_id, "deletion")
@router.post("/deletions/{request_id}/process", response_model=GovernanceResponse)
def process_deletion(request_id: str, user: User) -> GovernanceResponse: return service.process_deletion(user.user_id, request_id)
