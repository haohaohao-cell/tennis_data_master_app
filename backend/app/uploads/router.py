from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.schemas import UserPublic
from backend.app.uploads import service
from backend.app.uploads.schemas import (
    ActivityDetailResponse,
    ActivityDeleteResponse,
    LessonOptionListResponse,
    TennisActivityCreate,
    TennisActivityRecord,
    UploadCancelResponse,
    UploadCompleteResponse,
    UploadIntentCreate,
    UploadIntentResponse,
    VideoFileUploadResponse,
)


router = APIRouter(tags=["uploads"])


@router.get("/lessons/mine", response_model=LessonOptionListResponse)
def list_my_upload_lessons(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> LessonOptionListResponse:
    return LessonOptionListResponse(items=service.list_upload_lesson_options(current_user.user_id))


@router.post(
    "/tennis-activities/upload-intents",
    response_model=UploadIntentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_upload_intent(
    payload: UploadIntentCreate,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> UploadIntentResponse:
    return service.create_upload_intent(current_user.user_id, payload)


@router.post(
    "/tennis-activities",
    response_model=TennisActivityRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_tennis_activity(
    payload: TennisActivityCreate,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> TennisActivityRecord:
    return service.create_activity_record(current_user.user_id, payload)


@router.get("/tennis-activities/{tennis_activity_id}", response_model=ActivityDetailResponse)
def get_upload_activity(
    tennis_activity_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> ActivityDetailResponse:
    return service.get_activity_detail(current_user.user_id, tennis_activity_id)


@router.delete(
    "/tennis-activities/{tennis_activity_id}",
    response_model=ActivityDeleteResponse,
)
def delete_tennis_activity(
    tennis_activity_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> ActivityDeleteResponse:
    return service.delete_activity(current_user.user_id, tennis_activity_id)


@router.post(
    "/tennis-activities/{tennis_activity_id}/complete-upload",
    response_model=UploadCompleteResponse,
)
def complete_activity_upload(
    tennis_activity_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> UploadCompleteResponse:
    return service.complete_activity_upload(current_user.user_id, tennis_activity_id)


@router.post(
    "/tennis-activities/{tennis_activity_id}/cancel-upload",
    response_model=UploadCancelResponse,
)
def cancel_activity_upload(
    tennis_activity_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> UploadCancelResponse:
    return service.cancel_activity_upload(current_user.user_id, tennis_activity_id)


@router.post("/videos/{video_id}/file", response_model=VideoFileUploadResponse)
async def upload_video_file(
    video_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
) -> VideoFileUploadResponse:
    return await service.upload_video_file(current_user.user_id, video_id, file)
