from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.schemas import UserPublic
from backend.app.messages import service
from backend.app.messages import media_service
from backend.app.messages import outbox
from backend.app.messages.schemas import (
    ConversationCreateResponse,
    ConversationListResponse,
    ConversationMessageSearchResponse,
    ConversationHideResponse,
    ConversationMuteResponse,
    ConversationPinResponse,
    DirectConversationCreate,
    GroupConversationCreate,
    MarkReadRequest,
    MarkReadResponse,
    MessageCreate,
    MessageListResponse,
    MessageReconcileRequest,
    MessageReconcileResponse,
    MessageRequestActionResponse,
    MessageRequestCreate,
    MessageRequestListResponse,
    MessageSendResponse,
    MessageRecoveryResponse,
    MessageEventListResponse,
    NotificationListResponse,
    NotificationPreferencePatch,
    NotificationPreferences,
    NotificationProductCategory,
    MessageMediaUploadIntentCreate,
    MessageMediaUploadIntentResponse,
    MessageMediaResponse,
    UnreadCountsResponse,
)


router = APIRouter(tags=["messages"])


@router.post(
    "/messages/media/upload-intents",
    response_model=MessageMediaUploadIntentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_message_media_upload_intent(
    payload: MessageMediaUploadIntentCreate,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> MessageMediaUploadIntentResponse:
    return media_service.create_upload_intent(current_user.user_id, payload)


@router.post("/messages/media/{media_id}/file", response_model=MessageMediaResponse)
async def upload_message_media_file(
    media_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
) -> MessageMediaResponse:
    return await media_service.upload_media_file(current_user.user_id, media_id, file)


@router.post("/messages/media/{media_id}/complete", response_model=MessageMediaResponse)
def complete_message_media_upload(
    media_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> MessageMediaResponse:
    return media_service.complete_upload(current_user.user_id, media_id)


@router.post("/messages/media/{media_id}/cancel", response_model=MessageMediaResponse)
def cancel_message_media_upload(
    media_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> MessageMediaResponse:
    return media_service.cancel_upload(current_user.user_id, media_id)


@router.get("/messages/media/{media_id}", response_model=MessageMediaResponse)
def get_message_media(
    media_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> MessageMediaResponse:
    return media_service.get_media(current_user.user_id, media_id)


@router.get("/messages/media/{media_id}/content")
def serve_message_media(
    media_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    variant: Annotated[str, Query(pattern="^(original|thumbnail)$")] = "thumbnail",
):
    return media_service.serve_media(current_user.user_id, media_id, variant)


@router.post(
    "/messages/direct-conversations",
    response_model=ConversationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_direct_conversation(
    payload: DirectConversationCreate,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> ConversationCreateResponse:
    return service.create_direct_conversation(current_user.user_id, payload)


@router.post(
    "/messages/groups",
    response_model=ConversationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_group_conversation(
    payload: GroupConversationCreate,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> ConversationCreateResponse:
    return service.create_group_conversation(current_user.user_id, payload)


@router.post(
    "/messages/requests",
    response_model=MessageRequestActionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_message_request(
    payload: MessageRequestCreate,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> MessageRequestActionResponse:
    return service.create_message_request(current_user.user_id, payload)


@router.get("/messages/requests", response_model=MessageRequestListResponse)
def list_message_requests(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    box: Annotated[str, Query(pattern="^(inbox|sent)$")] = "inbox",
    status_filter: Annotated[str | None, Query(alias="status", max_length=30)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> MessageRequestListResponse:
    return service.list_message_requests(current_user.user_id, box, status_filter, page, page_size)


@router.post("/messages/requests/{message_request_id}/accept", response_model=MessageRequestActionResponse)
def accept_message_request(
    message_request_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> MessageRequestActionResponse:
    return service.accept_message_request(current_user.user_id, message_request_id)


@router.post("/messages/requests/{message_request_id}/decline", response_model=MessageRequestActionResponse)
def decline_message_request(
    message_request_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> MessageRequestActionResponse:
    return service.decline_message_request(current_user.user_id, message_request_id)


@router.get("/messages/conversations", response_model=ConversationListResponse)
def list_conversations(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ConversationListResponse:
    return service.list_conversations(current_user.user_id, page, page_size)


@router.get("/messages/conversations/search", response_model=ConversationListResponse)
def search_conversations(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    q: Annotated[str, Query()],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 30,
) -> ConversationListResponse:
    return service.search_conversations(current_user.user_id, q, page, page_size)


@router.post(
    "/messages/conversations/{conversation_id}/pin",
    response_model=ConversationPinResponse,
)
def pin_conversation(
    conversation_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> ConversationPinResponse:
    return service.set_conversation_pin(current_user.user_id, conversation_id, True)


@router.delete(
    "/messages/conversations/{conversation_id}/pin",
    response_model=ConversationPinResponse,
)
def unpin_conversation(
    conversation_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> ConversationPinResponse:
    return service.set_conversation_pin(current_user.user_id, conversation_id, False)


@router.post(
    "/messages/conversations/{conversation_id}/mute",
    response_model=ConversationMuteResponse,
)
def mute_conversation(
    conversation_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> ConversationMuteResponse:
    return service.set_conversation_mute(current_user.user_id, conversation_id, True)


@router.delete(
    "/messages/conversations/{conversation_id}/mute",
    response_model=ConversationMuteResponse,
)
def unmute_conversation(
    conversation_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> ConversationMuteResponse:
    return service.set_conversation_mute(current_user.user_id, conversation_id, False)


@router.post(
    "/messages/conversations/{conversation_id}/hide",
    response_model=ConversationHideResponse,
)
def hide_conversation(
    conversation_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> ConversationHideResponse:
    return service.set_conversation_hidden(current_user.user_id, conversation_id, True)


@router.delete(
    "/messages/conversations/{conversation_id}/hide",
    response_model=ConversationHideResponse,
)
def unhide_conversation(
    conversation_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> ConversationHideResponse:
    return service.set_conversation_hidden(current_user.user_id, conversation_id, False)


@router.get(
    "/messages/conversations/{conversation_id}/messages/search",
    response_model=ConversationMessageSearchResponse,
)
def search_conversation_messages(
    conversation_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    q: Annotated[str, Query()],
    page_size: Annotated[int, Query(ge=1, le=100)] = 30,
    before_seq: Annotated[int | None, Query(ge=1)] = None,
) -> ConversationMessageSearchResponse:
    return service.search_conversation_messages(
        current_user.user_id,
        conversation_id,
        q,
        page_size,
        before_seq,
    )


@router.get(
    "/messages/conversations/{conversation_id}/messages",
    response_model=MessageListResponse,
)
def list_messages(
    conversation_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    before_seq: Annotated[int | None, Query(ge=1)] = None,
) -> MessageListResponse:
    return service.list_messages(current_user.user_id, conversation_id, page_size, before_seq)


@router.post(
    "/messages/conversations/{conversation_id}/messages/reconcile",
    response_model=MessageReconcileResponse,
)
def reconcile_messages(
    conversation_id: str,
    payload: MessageReconcileRequest,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> MessageReconcileResponse:
    return service.reconcile_messages(current_user.user_id, conversation_id, payload)


@router.get(
    "/messages/conversations/{conversation_id}/events",
    response_model=MessageEventListResponse,
)
def list_message_events(
    conversation_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    cursor: Annotated[str | None, Query(max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> MessageEventListResponse:
    return outbox.list_events(current_user.user_id, conversation_id, cursor, limit)


@router.get(
    "/messages/conversations/{conversation_id}/messages/by-client-id/{client_message_id}",
    response_model=MessageRecoveryResponse,
)
def recover_message_by_client_id(
    conversation_id: str,
    client_message_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> MessageRecoveryResponse:
    return service.recover_message_by_client_id(current_user.user_id, conversation_id, client_message_id)


@router.post(
    "/messages/conversations/{conversation_id}/messages",
    response_model=MessageSendResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_message(
    conversation_id: str,
    payload: MessageCreate,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> MessageSendResponse:
    return service.send_message(current_user.user_id, conversation_id, payload)


@router.post(
    "/messages/conversations/{conversation_id}/messages/{message_id}/recall",
    response_model=MessageSendResponse,
)
def recall_message(
    conversation_id: str,
    message_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> MessageSendResponse:
    return service.recall_message(current_user.user_id, conversation_id, message_id)


@router.post(
    "/messages/conversations/{conversation_id}/read",
    response_model=MarkReadResponse,
)
def mark_conversation_read(
    conversation_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    payload: MarkReadRequest | None = None,
) -> MarkReadResponse:
    return service.mark_conversation_read(current_user.user_id, conversation_id, payload)


@router.get("/messages/unread-counts", response_model=UnreadCountsResponse)
def get_unread_counts(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> UnreadCountsResponse:
    return service.get_unread_counts(current_user.user_id)


@router.get("/notifications", response_model=NotificationListResponse)
def list_notifications(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
    category: Annotated[str | None, Query(max_length=30)] = None,
    product_category: Annotated[NotificationProductCategory | None, Query()] = None,
    unread_only: Annotated[bool, Query()] = False,
) -> NotificationListResponse:
    return service.list_notifications(
        current_user.user_id,
        page,
        page_size,
        category,
        product_category,
        unread_only,
    )


@router.get("/notifications/preferences", response_model=NotificationPreferences)
def get_notification_preferences(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> NotificationPreferences:
    return service.get_notification_preferences(current_user.user_id)


@router.patch("/notifications/preferences", response_model=NotificationPreferences)
def update_notification_preferences(
    payload: NotificationPreferencePatch,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> NotificationPreferences:
    return service.update_notification_preferences(current_user.user_id, payload)


@router.post("/notifications/{user_notification_id}/read")
def mark_notification_read(
    user_notification_id: str,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> dict[str, bool]:
    return {
        "success": service.mark_notification_read(
            current_user.user_id,
            user_notification_id,
        )
    }


@router.post("/notifications/read-all")
def mark_all_notifications_read(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
) -> dict[str, int | bool]:
    return {
        "success": True,
        "marked_count": service.mark_all_notifications_read(current_user.user_id),
    }
