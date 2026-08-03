from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.schemas import UserPublic
from backend.app.privacy import service
from backend.app.privacy.schemas import PrivacySettingsRecord, PrivacySettingsUpdate


router = APIRouter(prefix="/privacy", tags=["privacy"])


@router.get("/settings", response_model=PrivacySettingsRecord)
def get_privacy_settings(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> PrivacySettingsRecord:
    return service.get_privacy_settings(current_user.user_id)


@router.patch("/settings", response_model=PrivacySettingsRecord)
def update_privacy_settings(
    payload: PrivacySettingsUpdate,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> PrivacySettingsRecord:
    return service.update_privacy_settings(current_user.user_id, payload)
