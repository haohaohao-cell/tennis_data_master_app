from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.schemas import CurrentUserResponse, UserPublic
from backend.app.coach.schemas import (
    CoachApplicationCreate,
    CoachApplicationCreateResponse,
    CoachIdentityResponse,
)
from backend.app.coach.service import create_coach_application, get_user_coach_identity
from backend.app.users.schemas import UserProfileUpdate, UserSearchResponse
from backend.app.users.service import search_users, update_current_user_profile, upload_current_user_avatar


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/search", response_model=UserSearchResponse)
def search_app_users(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    q: Annotated[str, Query(min_length=1, max_length=50)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=20)] = 20,
) -> UserSearchResponse:
    return search_users(current_user.user_id, q, page, page_size)


@router.patch("/me", response_model=CurrentUserResponse)
def update_me(
    payload: UserProfileUpdate,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> CurrentUserResponse:
    return CurrentUserResponse(
        user=update_current_user_profile(current_user.user_id, payload)
    )


@router.post("/me/avatar", response_model=CurrentUserResponse)
async def upload_my_avatar(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
) -> CurrentUserResponse:
    return CurrentUserResponse(user=await upload_current_user_avatar(current_user.user_id, file))


@router.get("/me/coach-identity", response_model=CoachIdentityResponse)
def get_my_coach_identity(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> CoachIdentityResponse:
    return get_user_coach_identity(current_user.user_id)


@router.post("/me/coach-applications", response_model=CoachApplicationCreateResponse)
def submit_my_coach_application(
    payload: CoachApplicationCreate,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> CoachApplicationCreateResponse:
    application, identity = create_coach_application(current_user.user_id, payload)
    return CoachApplicationCreateResponse(application=application, identity=identity)
