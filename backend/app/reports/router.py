from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.schemas import UserPublic
from backend.app.reports import service
from backend.app.reports.schemas import ContentReportCreate, ContentReportCreateResponse


router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", response_model=ContentReportCreateResponse, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: ContentReportCreate,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> ContentReportCreateResponse:
    return service.create_report(current_user.user_id, payload)
