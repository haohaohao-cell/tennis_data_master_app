from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.schemas import UserPublic
from backend.app.posts.feed_service import list_current_user_post_collection
from backend.app.posts.schemas import PostCollectionResponse
from backend.app.profile.schemas import ProfileContentResponse
from backend.app.profile.service import get_profile_content


router = APIRouter(prefix="/me", tags=["profile"])


@router.get("/profile-content", response_model=ProfileContentResponse)
def get_my_profile_content(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> ProfileContentResponse:
    return get_profile_content(current_user.user_id)


@router.get("/favorite-posts", response_model=PostCollectionResponse)
def list_my_favorite_posts(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> PostCollectionResponse:
    return list_current_user_post_collection(
        user_id=current_user.user_id,
        collection="favorites",
        cursor=cursor,
        limit=limit,
    )


@router.get("/liked-posts", response_model=PostCollectionResponse)
def list_my_liked_posts(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> PostCollectionResponse:
    return list_current_user_post_collection(
        user_id=current_user.user_id,
        collection="likes",
        cursor=cursor,
        limit=limit,
    )
