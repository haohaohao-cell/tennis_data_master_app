from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from backend.app.auth.dependencies import get_current_user, get_optional_current_user
from backend.app.auth.schemas import UserPublic
from backend.app.posts import feed_service
from backend.app.posts import interaction_service
from backend.app.posts import service
from backend.app.posts.schemas import (
    PostCommentCreate,
    PostCommentCreateResponse,
    PostCommentDeleteResponse,
    PostCommentListResponse,
    PostCreate,
    PostDeleteResponse,
    PostDetailResponse,
    PostFavoriteResponse,
    PostFeedResponse,
    PostFeedStateResponse,
    PostHideCreate,
    PostHideResponse,
    PostInteractionCreate,
    PostListResponse,
    PostLikeResponse,
    PostShareCreate,
    PostShareResponse,
    PostUpdate,
    PostUploadIntentCreate,
    PostUploadIntentResponse,
    PostViewsBulkCreate,
    PostViewsBulkResponse,
)


router = APIRouter(tags=["posts"])


@router.get("/posts/feed", response_model=PostFeedResponse)
def list_post_feed(
    feed_type: Annotated[str, Query(pattern="^(recommended|following|nearby)$")] = "recommended",
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    city: Annotated[str | None, Query(max_length=80)] = None,
    region: Annotated[str | None, Query(max_length=80)] = None,
    current_user: Annotated[UserPublic | None, Depends(get_optional_current_user)] = None,
) -> PostFeedResponse:
    return feed_service.list_feed(
        feed_type=feed_type,  # type: ignore[arg-type]
        user=current_user,
        cursor=cursor,
        limit=limit,
        city=city,
        region=region,
    )


@router.get("/posts/feed/state", response_model=PostFeedStateResponse)
def get_post_feed_state() -> PostFeedStateResponse:
    return feed_service.get_feed_state()


@router.post("/posts/views/bulk", response_model=PostViewsBulkResponse)
def report_post_views(
    payload: PostViewsBulkCreate,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> PostViewsBulkResponse:
    return feed_service.report_views(current_user.user_id, payload)


@router.post("/posts/{social_post_id}/hide", response_model=PostHideResponse)
def hide_post(
    social_post_id: str,
    payload: PostHideCreate,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> PostHideResponse:
    return feed_service.hide_post(current_user.user_id, social_post_id, payload)


@router.delete("/posts/{social_post_id}/hide", response_model=PostHideResponse)
def unhide_post(
    social_post_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> PostHideResponse:
    return feed_service.unhide_post(current_user.user_id, social_post_id)


@router.post("/posts/{social_post_id}/like", response_model=PostLikeResponse)
def like_post(
    social_post_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    payload: PostInteractionCreate | None = None,
) -> PostLikeResponse:
    return interaction_service.like_post(current_user.user_id, social_post_id, payload)


@router.delete("/posts/{social_post_id}/like", response_model=PostLikeResponse)
def unlike_post(
    social_post_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> PostLikeResponse:
    return interaction_service.unlike_post(current_user.user_id, social_post_id)


@router.post("/posts/{social_post_id}/favorite", response_model=PostFavoriteResponse)
def favorite_post(
    social_post_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    payload: PostInteractionCreate | None = None,
) -> PostFavoriteResponse:
    return interaction_service.favorite_post(current_user.user_id, social_post_id, payload)


@router.delete("/posts/{social_post_id}/favorite", response_model=PostFavoriteResponse)
def unfavorite_post(
    social_post_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> PostFavoriteResponse:
    return interaction_service.unfavorite_post(current_user.user_id, social_post_id)


@router.get("/posts/{social_post_id}/comments", response_model=PostCommentListResponse)
def list_post_comments(
    social_post_id: str,
    current_user: Annotated[UserPublic | None, Depends(get_optional_current_user)] = None,
    parent_comment_id: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PostCommentListResponse:
    return interaction_service.list_comments(
        social_post_id,
        current_user.user_id if current_user else None,
        page,
        page_size,
        parent_comment_id,
    )


@router.post(
    "/posts/{social_post_id}/comments",
    response_model=PostCommentCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_post_comment(
    social_post_id: str,
    payload: PostCommentCreate,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> PostCommentCreateResponse:
    return interaction_service.create_comment(current_user.user_id, social_post_id, payload)


@router.delete(
    "/posts/{social_post_id}/comments/{comment_id}",
    response_model=PostCommentDeleteResponse,
)
def delete_post_comment(
    social_post_id: str,
    comment_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> PostCommentDeleteResponse:
    return interaction_service.delete_comment(current_user.user_id, social_post_id, comment_id)


@router.post("/posts/{social_post_id}/share", response_model=PostShareResponse, status_code=status.HTTP_201_CREATED)
def share_post(
    social_post_id: str,
    payload: PostShareCreate,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> PostShareResponse:
    return interaction_service.share_post(current_user.user_id, social_post_id, payload)


@router.get("/posts/mine", response_model=PostListResponse)
def list_my_posts(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> PostListResponse:
    return service.list_my_posts(current_user.user_id, page=page, page_size=page_size)


@router.post("/posts/upload-intents", response_model=PostUploadIntentResponse, status_code=status.HTTP_201_CREATED)
def create_post_upload_intent(
    payload: PostUploadIntentCreate,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> PostUploadIntentResponse:
    return service.create_post_upload_intent(current_user.user_id, payload)


@router.post("/posts", response_model=PostDetailResponse, status_code=status.HTTP_201_CREATED)
def create_post_from_activity_clip(
    payload: PostCreate,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> PostDetailResponse:
    return service.create_post_from_activity_clip(current_user.user_id, payload)


@router.get("/posts/public/{social_post_id}", response_model=PostDetailResponse)
def get_public_post(
    social_post_id: str,
    current_user: Annotated[UserPublic | None, Depends(get_optional_current_user)] = None,
) -> PostDetailResponse:
    return service.get_public_post(
        social_post_id,
        current_user.user_id if current_user is not None else None,
    )


@router.get("/posts/{social_post_id}", response_model=PostDetailResponse)
def get_post_detail(
    social_post_id: str,
    current_user: Annotated[UserPublic | None, Depends(get_optional_current_user)] = None,
) -> PostDetailResponse:
    return service.get_post_detail(
        social_post_id,
        current_user.user_id if current_user is not None else None,
    )


@router.patch("/posts/{social_post_id}", response_model=PostDetailResponse)
def update_post(
    social_post_id: str,
    payload: PostUpdate,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> PostDetailResponse:
    return service.update_post(current_user.user_id, social_post_id, payload)


@router.post("/posts/{social_post_id}/publish", response_model=PostDetailResponse)
def publish_post(
    social_post_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> PostDetailResponse:
    return service.publish_post(current_user.user_id, social_post_id)


@router.delete("/posts/{social_post_id}", response_model=PostDeleteResponse)
def delete_post(
    social_post_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> PostDeleteResponse:
    service.delete_post(current_user.user_id, social_post_id)
    return PostDeleteResponse(success=True, id=social_post_id)
