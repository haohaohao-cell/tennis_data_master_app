from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.schemas import UserPublic
from backend.app.social import service
from backend.app.social.schemas import (
    BlockActionResponse,
    BlockCreate,
    BlockListResponse,
    FollowActionResponse,
    FollowCreate,
    FollowListResponse,
    RelationshipResponse,
    SocialStatsResponse,
)


router = APIRouter(prefix="/social", tags=["social"])


@router.post("/follows/{target_user_id}", response_model=FollowActionResponse, status_code=status.HTTP_201_CREATED)
def follow_user(
    target_user_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    payload: FollowCreate | None = None,
) -> FollowActionResponse:
    return service.follow_user(
        current_user.user_id,
        target_user_id,
        payload.source if payload is not None else None,
    )


@router.delete("/follows/{target_user_id}", response_model=FollowActionResponse)
def unfollow_user(
    target_user_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> FollowActionResponse:
    return service.unfollow_user(current_user.user_id, target_user_id)


@router.post("/blocks/{target_user_id}", response_model=BlockActionResponse, status_code=status.HTTP_201_CREATED)
def block_user(
    target_user_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    payload: BlockCreate | None = None,
) -> BlockActionResponse:
    return service.block_user(
        current_user.user_id,
        target_user_id,
        payload.reason if payload is not None else None,
    )


@router.delete("/blocks/{target_user_id}", response_model=BlockActionResponse)
def unblock_user(
    target_user_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> BlockActionResponse:
    return service.unblock_user(current_user.user_id, target_user_id)


@router.get("/blocks", response_model=BlockListResponse)
def list_blocks(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> BlockListResponse:
    return service.list_blocks(current_user.user_id, page, page_size)


@router.get("/users/{user_id}/relationship", response_model=RelationshipResponse)
def get_relationship(
    user_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> RelationshipResponse:
    return service.get_relationship(current_user.user_id, user_id)


@router.get("/users/{user_id}/followers", response_model=FollowListResponse)
def list_followers(
    user_id: str,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> FollowListResponse:
    return service.list_followers(user_id, page, page_size)


@router.get("/users/{user_id}/following", response_model=FollowListResponse)
def list_following(
    user_id: str,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> FollowListResponse:
    return service.list_following(user_id, page, page_size)


@router.get("/users/{user_id}/friends", response_model=FollowListResponse)
def list_friends(
    user_id: str,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> FollowListResponse:
    return service.list_friends(user_id, page, page_size)


@router.get("/users/{user_id}/stats", response_model=SocialStatsResponse)
def get_social_stats(user_id: str) -> SocialStatsResponse:
    return service.get_social_stats(user_id)
