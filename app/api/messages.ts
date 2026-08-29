import { ApiError, apiRequest, apiUpload } from "@/api/client";

export const MESSAGE_SEND_TIMEOUT_MS = 15_000;

/** A send wait boundary; the underlying request may still finish and be reconciled by polling. */
export class MessageSendTimeoutError extends Error {
  constructor() {
    super("发送超时，请检查网络后重试。");
    this.name = "MessageSendTimeoutError";
  }
}

export function isRetryableSendError(error: unknown) {
  if (error instanceof MessageSendTimeoutError) {
    return true;
  }
  if (!(error instanceof ApiError)) {
    return false;
  }
  return (
    (error.status === 0 && error.code === "NETWORK_ERROR") ||
    error.status === 408 ||
    error.status === 425 ||
    error.status === 429 ||
    error.status >= 500
  );
}

export type ConversationType = "direct" | "group";
export type MessageType =
  | "text"
  | "image"
  | "video"
  | "audio"
  | "file"
  | "post_share"
  | "video_share"
  | "activity_share"
  | "lesson_share"
  | "analysis_card"
  | "system_event"
  | "custom";

export type MessageCreateInput = {
  message_type: MessageType;
  text_content: string | null;
  payload?: Record<string, unknown> | null;
  target_object_type?: string | null;
  target_object_id?: string | null;
  context_object_type?: string | null;
  context_object_id?: string | null;
  reply_to_message_id?: string | null;
  client_message_id: string;
  attachments?: Array<{
    attachment_type: string;
    media_id?: string | null;
    mime_type?: string | null;
    file_size_bytes?: number | null;
    width_px?: number | null;
    height_px?: number | null;
  }>;
};

export type MessageUserSummary = {
  avatar_path: string | null;
  coach_status: string | null;
  is_coach: boolean;
  nickname: string;
  user_id: string;
};

export type ChatConversationRecord = {
  avatar_path: string | null;
  context_id: string | null;
  context_type: string | null;
  conversation_id: string;
  conversation_type: ConversationType;
  created_at: string;
  group_type: string | null;
  last_message_at: string | null;
  last_message_id: string | null;
  last_message_preview: string | null;
  last_message_seq: number;
  status: string;
  title: string | null;
  updated_at: string;
};

export type ConversationMemberRecord = {
  archived_at: string | null;
  conversation_id: string;
  conversation_member_id: string;
  joined_at: string;
  last_read_at: string | null;
  last_read_message_id: string | null;
  last_read_message_seq: number;
  left_at: string | null;
  member_role: string;
  muted_until: string | null;
  is_muted: boolean;
  pinned_at: string | null;
  status: string;
  unread_count: number;
  user_id: string;
};

export type ConversationListItem = {
  conversation: ChatConversationRecord;
  member: ConversationMemberRecord;
  other_members: MessageUserSummary[];
};

export type ConversationListResponse = {
  items: ConversationListItem[];
  page: number;
  page_size: number;
};

export type ConversationPinResponse = {
  conversation_id: string;
  pinned_at: string | null;
  success: boolean;
};

export type ConversationMuteResponse = {
  conversation_id: string;
  is_muted: boolean;
  muted_until: string | null;
  success: boolean;
};

export type ConversationHideResponse = {
  archived_at: string | null;
  conversation_id: string;
  is_hidden: boolean;
  success: boolean;
};

export type ConversationCreateResponse = {
  conversation: ChatConversationRecord;
  member: ConversationMemberRecord;
  other_members: MessageUserSummary[];
};

export type MessageAttachmentRecord = {
  attachment_id: string;
  attachment_type: string;
  media_id: string | null;
  media_state: "created" | "uploading" | "uploaded" | "attached" | "failed" | "expired" | "deleted" | null;
  media_url: string | null;
  thumbnail_url: string | null;
  created_at: string;
  duration_ms: number | null;
  file_size_bytes: number | null;
  height_px: number | null;
  media_path: string | null;
  message_id: string;
  mime_type: string | null;
  object_id: string | null;
  object_type: string | null;
  payload_json: string | null;
  sort_order: number;
  thumbnail_path: string | null;
  width_px: number | null;
};

export type MessageReplyPreview = {
  message_id: string;
  message_seq: number | null;
  sender_nickname: string | null;
  sender_user_id: string | null;
  state: "available" | "unavailable";
  text_content: string | null;
};

export type MessageMediaRecord = {
  media_id: string;
  owner_user_id: string;
  message_id: string | null;
  media_type: "image" | "video";
  upload_status: "created" | "uploading" | "uploaded" | "attached" | "failed" | "expired" | "deleted";
  mime_type: string;
  file_size_bytes: number;
  width_px: number;
  height_px: number;
  duration_ms: number | null;
  checksum_sha256: string | null;
  expected_checksum_sha256: string | null;
  container: string | null;
  codec: string | null;
  client_upload_id: string;
  created_at: string;
  uploaded_at: string | null;
  attached_at: string | null;
  expires_at: string;
  deleted_at: string | null;
  failure_code: string | null;
  thumbnail_status: "pending" | "generated" | "failed";
  thumbnail_failure_code: string | null;
  storage_deleted_at: string | null;
  last_cleanup_error: string | null;
  media_url: string | null;
  thumbnail_url: string | null;
};

export type MessageMediaResponse = { media: MessageMediaRecord };
export type MessageMediaUploadIntentResponse = MessageMediaResponse & {
  upload_url: string;
  complete_url: string;
};

export type PostShareCard = {
  author: {
    avatar_path: string | null;
    nickname: string;
    user_id: string;
  } | null;
  cover_url: string | null;
  post_id: string;
  reason: "not_found_or_no_access" | null;
  state: "available" | "unavailable";
  summary: string | null;
  title: string | null;
  visibility: string | null;
};

export type BusinessObjectCard = {
  author: PostShareCard["author"];
  cover_url: string | null;
  kind: "business_object";
  metadata: Record<string, boolean | number | string | null>;
  object_id: string;
  object_type: "social_post" | "video" | "tennis_activity" | "lesson" | "analysis";
  state: "available" | "unavailable" | "unsupported";
  summary: string | null;
  title: string | null;
  unavailable_reason: "not_found_or_no_access" | "unsupported_object_type" | null;
};

export type ChatMessageRecord = {
  attachments: MessageAttachmentRecord[];
  business_object_card: BusinessObjectCard | null;
  client_message_id: string | null;
  context_object_id: string | null;
  context_object_type: string | null;
  conversation_id: string;
  created_at: string;
  deleted_at: string | null;
  message_id: string;
  message_seq: number;
  message_type: MessageType;
  payload_json: string | null;
  reply_to_message_id: string | null;
  reply_preview: MessageReplyPreview | null;
  sender: MessageUserSummary | null;
  sender_type: string;
  sender_user_id: string | null;
  share_card: PostShareCard | null;
  sent_at: string;
  status: string;
  target_object_id: string | null;
  target_object_type: string | null;
  text_content: string | null;
  updated_at: string;
};

export type MessageListResponse = {
  conversation_id: string;
  direct_interaction_state: DirectConversationInteractionState | null;
  items: ChatMessageRecord[];
  next_before_seq: number | null;
  other_member_last_read_message_seq: number | null;
};

export type ConversationMessageSearchResponse = {
  conversation_id: string;
  items: ChatMessageRecord[];
  next_before_seq: number | null;
};

export type DirectConversationInteractionState = {
  blocked_by_current_user: boolean;
  can_send: boolean;
};

export type MessageSendResponse = {
  message: ChatMessageRecord;
  event_id: string | null;
};

export type MessageRecoveryResponse = {
  found: boolean;
  message: ChatMessageRecord | null;
  event_id: string | null;
};

export type OutboxEventRecord = {
  event_id: string;
  aggregate_type: "chat_message";
  aggregate_id: string;
  event_type: "message.created";
  event_version: number;
  actor_user_id: string | null;
  conversation_id: string;
  message_id: string;
  message_seq: number;
  payload_json: string;
  status: "pending" | "leased" | "processed" | "failed";
  attempt_count: number;
  available_at: string;
  leased_at: string | null;
  lease_owner: string | null;
  processed_at: string | null;
  next_attempt_at: string | null;
  last_error_code: string | null;
  last_error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type MessageEventListResponse = {
  items: OutboxEventRecord[];
  next_cursor: string | null;
};

export type MessageRequestRecord = {
  conversation_id: string | null;
  created_at: string;
  message_request_id: string;
  recipient: MessageUserSummary;
  recipient_user_id: string;
  request_message: string | null;
  requested_at: string;
  requester: MessageUserSummary;
  requester_user_id: string;
  responded_at: string | null;
  source: string | null;
  status: string;
  updated_at: string;
};

export type MessageRequestListResponse = {
  items: MessageRequestRecord[];
  page: number;
  page_size: number;
};

export type MessageRequestActionResponse = {
  conversation: ChatConversationRecord | null;
  member: ConversationMemberRecord | null;
  other_members: MessageUserSummary[];
  request: MessageRequestRecord;
  success: boolean;
};

export type NotificationCategory = "interaction" | "system" | "ai" | "coach" | "lesson";
export type NotificationProductCategory = "interaction_follow" | "course_system" | "request";
export type NotificationEventType =
  | "follow"
  | "post_like"
  | "post_comment"
  | "comment_reply"
  | "mention"
  | "video_shared"
  | "ai_analysis_completed"
  | "lesson_created"
  | "lesson_updated"
  | "coach_application_reviewed"
  | "system_announcement"
  | "custom";
export type NotificationType = NotificationEventType | "message_request";
export type NotificationPreferences = {
  direct_message_notifications: boolean;
  message_request_notifications: boolean;
  like_comment_notifications: boolean;
  follow_notifications: boolean;
  course_notifications: boolean;
  ai_analysis_notifications: boolean;
};
export type NotificationPreferencePatch = Partial<NotificationPreferences>;
export type NotificationTarget =
  | { type: "user_profile"; user_id: string }
  | { type: "post_detail"; post_id: string }
  | { type: "post_comments"; post_id: string }
  | { type: "message_request"; request_id: string | null }
  | { type: "chat"; conversation_id: string }
  | { type: "activity_detail"; activity_id: string }
  | { type: "lesson_detail"; lesson_id: string }
  | { type: "coach_identity" }
  | { type: "none" };

export type NotificationEventRecord = {
  actor_user_id: string | null;
  body: string | null;
  category: NotificationCategory;
  context_id: string | null;
  context_type: string | null;
  created_at: string;
  deep_link: string | null;
  event_type: NotificationEventType;
  notification_type: NotificationType;
  notification_event_id: string;
  object_id: string | null;
  object_type: string | null;
  payload_json: string | null;
  product_category: NotificationProductCategory;
  target: NotificationTarget;
  title: string | null;
};

export type UserNotificationRecord = {
  actor: MessageUserSummary | null;
  created_at: string;
  delivered_at: string;
  dismissed_at: string | null;
  event: NotificationEventRecord;
  notification_event_id: string;
  priority: string;
  read_at: string | null;
  recipient_user_id: string;
  seen_at: string | null;
  status: string;
  user_notification_id: string;
};

export type NotificationListResponse = {
  items: UserNotificationRecord[];
  page: number;
  page_size: number;
  unread_count: number;
};

export type UnreadCountsResponse = {
  messages_tab_badge_count: number;
  pending_message_request_count: number;
  total_unread_count: number;
  unread_direct_message_count: number;
  unread_group_message_count: number;
  unread_notification_count: number;
};

function paginationQuery(page = 1, pageSize = 20) {
  return `page=${page}&page_size=${pageSize}`;
}

export function createDirectConversation(accessToken: string, targetUserId: string) {
  return apiRequest<ConversationCreateResponse>("/api/v1/messages/direct-conversations", {
    accessToken,
    body: { target_user_id: targetUserId },
    method: "POST",
  });
}

export function listConversations(accessToken: string, page = 1, pageSize = 30) {
  return apiRequest<ConversationListResponse>(`/api/v1/messages/conversations?${paginationQuery(page, pageSize)}`, {
    accessToken,
  });
}

export function createGroupConversation(
  accessToken: string,
  title: string,
  memberUserIds: string[],
) {
  return apiRequest<ConversationCreateResponse>("/api/v1/messages/groups", {
    accessToken,
    body: {
      group_type: "custom",
      member_user_ids: memberUserIds,
      title: title.trim(),
    },
    captureDiagnostics: false,
    method: "POST",
  });
}

export function searchConversations(
  accessToken: string,
  query: string,
  options: { page?: number; pageSize?: number } = {},
) {
  const params = new URLSearchParams({
    page: String(options.page ?? 1),
    page_size: String(options.pageSize ?? 30),
    q: query.trim(),
  });
  return apiRequest<ConversationListResponse>(`/api/v1/messages/conversations/search?${params.toString()}`, {
    accessToken,
    captureDiagnostics: false,
  });
}

export function listMessages(
  accessToken: string,
  conversationId: string,
  options: { beforeSeq?: number | null; pageSize?: number } = {},
) {
  const params = [`page_size=${options.pageSize ?? 50}`];
  if (options.beforeSeq) {
    params.push(`before_seq=${options.beforeSeq}`);
  }
  return apiRequest<MessageListResponse>(
    `/api/v1/messages/conversations/${encodeURIComponent(conversationId)}/messages?${params.join("&")}`,
    { accessToken },
  );
}

export function sendTextMessage(
  accessToken: string,
  conversationId: string,
  textContent: string,
  clientMessageId: string,
  replyToMessageId?: string | null,
) {
  const request = apiRequest<MessageSendResponse>(
    `/api/v1/messages/conversations/${encodeURIComponent(conversationId)}/messages`,
    {
      accessToken,
      captureDiagnostics: false,
      body: {
        client_message_id: clientMessageId,
        message_type: "text",
        reply_to_message_id: replyToMessageId ?? null,
        text_content: textContent,
      },
      method: "POST",
    },
  );
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  const timeout = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => reject(new MessageSendTimeoutError()), MESSAGE_SEND_TIMEOUT_MS);
  });

  return Promise.race([request, timeout]).finally(() => {
    if (timeoutId !== null) {
      clearTimeout(timeoutId);
    }
  });
}

export function recoverMessageByClientId(
  accessToken: string,
  conversationId: string,
  clientMessageId: string,
) {
  return apiRequest<MessageRecoveryResponse>(
    `/api/v1/messages/conversations/${encodeURIComponent(conversationId)}/messages/by-client-id/${encodeURIComponent(clientMessageId)}`,
    { accessToken, captureDiagnostics: false },
  );
}

export function listMessageEvents(
  accessToken: string,
  conversationId: string,
  options: { cursor?: string | null; limit?: number } = {},
) {
  const params = new URLSearchParams({ limit: String(options.limit ?? 50) });
  if (options.cursor) {
    params.set("cursor", options.cursor);
  }
  return apiRequest<MessageEventListResponse>(
    `/api/v1/messages/conversations/${encodeURIComponent(conversationId)}/events?${params.toString()}`,
    { accessToken, captureDiagnostics: false },
  );
}

export function createMessageImageUploadIntent(
  accessToken: string,
  payload: {
    mimeType: "image/jpeg" | "image/png" | "image/webp" | "image/gif";
    fileSizeBytes: number;
    widthPx: number;
    heightPx: number;
    clientUploadId: string;
  },
) {
  return apiRequest<MessageMediaUploadIntentResponse>("/api/v1/messages/media/upload-intents", {
    accessToken,
    body: {
      client_upload_id: payload.clientUploadId,
      file_size_bytes: payload.fileSizeBytes,
      height_px: payload.heightPx,
      mime_type: payload.mimeType,
      media_type: "image",
      width_px: payload.widthPx,
    },
    method: "POST",
  });
}

export function createMessageVideoUploadIntent(
  accessToken: string,
  payload: { mimeType: "video/mp4" | "video/quicktime" | "video/webm" | "video/x-matroska" | "video/3gpp"; fileSizeBytes: number; widthPx: number; heightPx: number; durationMs: number; clientUploadId: string; expectedChecksumSha256?: string },
) {
  return apiRequest<MessageMediaUploadIntentResponse>("/api/v1/messages/media/upload-intents", {
    accessToken,
    body: { client_upload_id: payload.clientUploadId, file_size_bytes: payload.fileSizeBytes, height_px: payload.heightPx, mime_type: payload.mimeType, media_type: "video", width_px: payload.widthPx, duration_ms: payload.durationMs, expected_checksum_sha256: payload.expectedChecksumSha256 ?? null },
    method: "POST",
  });
}

/** Upload raw bytes for either an image or a video message media intent. */
export function uploadMessageMediaFile(
  accessToken: string,
  mediaId: string,
  file: Blob | { uri: string; name: string; type: string },
  filename?: string,
) {
  return apiUpload<MessageMediaResponse>(`/api/v1/messages/media/${encodeURIComponent(mediaId)}/file`, accessToken, file, filename);
}

/** @deprecated Use uploadMessageMediaFile for new message-media callers. */
export function uploadMessageImageFile(
  accessToken: string,
  mediaId: string,
  file: Blob | { uri: string; name: string; type: string },
  filename?: string,
) {
  return uploadMessageMediaFile(accessToken, mediaId, file, filename);
}

export function completeMessageMediaUpload(accessToken: string, mediaId: string) {
  return apiRequest<MessageMediaResponse>(`/api/v1/messages/media/${encodeURIComponent(mediaId)}/complete`, {
    accessToken,
    method: "POST",
  });
}

export function cancelMessageMediaUpload(accessToken: string, mediaId: string) {
  return apiRequest<MessageMediaResponse>(`/api/v1/messages/media/${encodeURIComponent(mediaId)}/cancel`, {
    accessToken,
    method: "POST",
  });
}

/** @deprecated Use completeMessageMediaUpload for all message-media types. */
export function completeMessageImageUpload(accessToken: string, mediaId: string) {
  return completeMessageMediaUpload(accessToken, mediaId);
}

/** @deprecated Use cancelMessageMediaUpload for all message-media types. */
export function cancelMessageImageUpload(accessToken: string, mediaId: string) {
  return cancelMessageMediaUpload(accessToken, mediaId);
}

export function sendImageMessage(
  accessToken: string,
  conversationId: string,
  mediaId: string,
  clientMessageId: string,
  textContent?: string | null,
  replyToMessageId?: string | null,
) {
  return apiRequest<MessageSendResponse>(
    `/api/v1/messages/conversations/${encodeURIComponent(conversationId)}/messages`,
    {
      accessToken,
      captureDiagnostics: false,
      body: {
        attachments: [{ attachment_type: "image", media_id: mediaId }],
        client_message_id: clientMessageId,
        message_type: "image",
        reply_to_message_id: replyToMessageId ?? null,
        text_content: textContent?.trim() || null,
      },
      method: "POST",
    },
  );
}

export function sendVideoMessage(accessToken: string, conversationId: string, mediaId: string, clientMessageId: string, textContent?: string | null, replyToMessageId?: string | null) {
  return apiRequest<MessageSendResponse>(`/api/v1/messages/conversations/${encodeURIComponent(conversationId)}/messages`, {
    accessToken, captureDiagnostics: false,
    body: { attachments: [{ attachment_type: "video", media_id: mediaId }], client_message_id: clientMessageId, message_type: "video", reply_to_message_id: replyToMessageId ?? null, text_content: textContent?.trim() || null },
    method: "POST",
  });
}

export function recallMessage(accessToken: string, conversationId: string, messageId: string) {
  return apiRequest<MessageSendResponse>(
    `/api/v1/messages/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}/recall`,
    { accessToken, method: "POST" },
  );
}

export function reconcileMessages(accessToken: string, conversationId: string, messageIds: string[]) {
  return apiRequest<{ conversation_id: string; items: ChatMessageRecord[] }>(
    `/api/v1/messages/conversations/${encodeURIComponent(conversationId)}/messages/reconcile`,
    {
      accessToken,
      body: { message_ids: messageIds },
      method: "POST",
    },
  );
}

export function markConversationRead(
  accessToken: string,
  conversationId: string,
  throughMessageSeq?: number | null,
) {
  return apiRequest<{
    conversation_id: string;
    last_read_message_seq: number;
    success: boolean;
    unread_count: number;
  }>(
    `/api/v1/messages/conversations/${encodeURIComponent(conversationId)}/read`,
    {
      accessToken,
      body: throughMessageSeq === null || throughMessageSeq === undefined
        ? undefined
        : { through_message_seq: throughMessageSeq },
      method: "POST",
    },
  );
}

export function searchConversationMessages(
  accessToken: string,
  conversationId: string,
  query: string,
  options: { beforeSeq?: number | null; pageSize?: number } = {},
) {
  const params = new URLSearchParams({
    page_size: String(options.pageSize ?? 30),
    q: query.trim(),
  });
  if (options.beforeSeq) {
    params.set("before_seq", String(options.beforeSeq));
  }
  return apiRequest<ConversationMessageSearchResponse>(
    `/api/v1/messages/conversations/${encodeURIComponent(conversationId)}/messages/search?${params.toString()}`,
    { accessToken, captureDiagnostics: false },
  );
}

export function pinConversation(accessToken: string, conversationId: string) {
  return apiRequest<ConversationPinResponse>(
    `/api/v1/messages/conversations/${encodeURIComponent(conversationId)}/pin`,
    { accessToken, method: "POST" },
  );
}

export function unpinConversation(accessToken: string, conversationId: string) {
  return apiRequest<ConversationPinResponse>(
    `/api/v1/messages/conversations/${encodeURIComponent(conversationId)}/pin`,
    { accessToken, method: "DELETE" },
  );
}

export function muteConversation(accessToken: string, conversationId: string) {
  return apiRequest<ConversationMuteResponse>(
    `/api/v1/messages/conversations/${encodeURIComponent(conversationId)}/mute`,
    { accessToken, method: "POST" },
  );
}

export function unmuteConversation(accessToken: string, conversationId: string) {
  return apiRequest<ConversationMuteResponse>(
    `/api/v1/messages/conversations/${encodeURIComponent(conversationId)}/mute`,
    { accessToken, method: "DELETE" },
  );
}

export function hideConversation(accessToken: string, conversationId: string) {
  return apiRequest<ConversationHideResponse>(
    `/api/v1/messages/conversations/${encodeURIComponent(conversationId)}/hide`,
    { accessToken, method: "POST" },
  );
}

export function unhideConversation(accessToken: string, conversationId: string) {
  return apiRequest<ConversationHideResponse>(
    `/api/v1/messages/conversations/${encodeURIComponent(conversationId)}/hide`,
    { accessToken, method: "DELETE" },
  );
}

export function getUnreadCounts(accessToken: string) {
  return apiRequest<UnreadCountsResponse>("/api/v1/messages/unread-counts", { accessToken });
}

export function listNotifications(
  accessToken: string,
  options: {
    category?: NotificationCategory | null;
    page?: number;
    pageSize?: number;
    productCategory?: NotificationProductCategory | null;
    unreadOnly?: boolean;
  } = {},
) {
  const params = [paginationQuery(options.page ?? 1, options.pageSize ?? 30)];
  if (options.category) {
    params.push(`category=${encodeURIComponent(options.category)}`);
  }
  if (options.productCategory) {
    params.push(`product_category=${encodeURIComponent(options.productCategory)}`);
  }
  if (options.unreadOnly) {
    params.push("unread_only=true");
  }
  return apiRequest<NotificationListResponse>(`/api/v1/notifications?${params.join("&")}`, {
    accessToken,
  });
}

export function getNotificationPreferences(accessToken: string) {
  return apiRequest<NotificationPreferences>("/api/v1/notifications/preferences", { accessToken });
}

export function updateNotificationPreferences(
  accessToken: string,
  patch: NotificationPreferencePatch,
) {
  return apiRequest<NotificationPreferences>("/api/v1/notifications/preferences", {
    accessToken,
    body: patch,
    method: "PATCH",
  });
}

export function markNotificationRead(accessToken: string, userNotificationId: string) {
  return apiRequest<{ success: boolean }>(
    `/api/v1/notifications/${encodeURIComponent(userNotificationId)}/read`,
    { accessToken, method: "POST" },
  );
}

export function markAllNotificationsRead(accessToken: string) {
  return apiRequest<{ marked_count: number; success: boolean }>("/api/v1/notifications/read-all", {
    accessToken,
    method: "POST",
  });
}

export function createMessageRequest(
  accessToken: string,
  targetUserId: string,
  requestMessage: string | null,
  source = "profile",
) {
  return apiRequest<MessageRequestActionResponse>("/api/v1/messages/requests", {
    accessToken,
    captureDiagnostics: false,
    body: {
      request_message: requestMessage,
      source,
      target_user_id: targetUserId,
    },
    method: "POST",
  });
}

export function listMessageRequests(
  accessToken: string,
  box: "inbox" | "sent" = "inbox",
  options: { page?: number; pageSize?: number; status?: string | null } = {},
) {
  const params = [`box=${box}`, paginationQuery(options.page ?? 1, options.pageSize ?? 30)];
  if (options.status) {
    params.push(`status=${encodeURIComponent(options.status)}`);
  }
  return apiRequest<MessageRequestListResponse>(`/api/v1/messages/requests?${params.join("&")}`, {
    accessToken,
  });
}

export function acceptMessageRequest(accessToken: string, messageRequestId: string) {
  return apiRequest<MessageRequestActionResponse>(
    `/api/v1/messages/requests/${encodeURIComponent(messageRequestId)}/accept`,
    { accessToken, method: "POST" },
  );
}

export function declineMessageRequest(accessToken: string, messageRequestId: string) {
  return apiRequest<MessageRequestActionResponse>(
    `/api/v1/messages/requests/${encodeURIComponent(messageRequestId)}/decline`,
    { accessToken, method: "POST" },
  );
}
