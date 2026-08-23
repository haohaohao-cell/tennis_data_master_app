import { apiRequest } from "@/api/client";

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

export type ConversationCreateResponse = {
  conversation: ChatConversationRecord;
  member: ConversationMemberRecord;
  other_members: MessageUserSummary[];
};

export type MessageAttachmentRecord = {
  attachment_id: string;
  attachment_type: string;
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

export type ChatMessageRecord = {
  attachments: MessageAttachmentRecord[];
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
  sender: MessageUserSummary | null;
  sender_type: string;
  sender_user_id: string | null;
  sent_at: string;
  status: string;
  target_object_id: string | null;
  target_object_type: string | null;
  text_content: string | null;
  updated_at: string;
};

export type MessageListResponse = {
  conversation_id: string;
  items: ChatMessageRecord[];
  next_before_seq: number | null;
};

export type MessageSendResponse = {
  message: ChatMessageRecord;
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

export type NotificationEventRecord = {
  actor_user_id: string | null;
  body: string | null;
  category: string;
  context_id: string | null;
  context_type: string | null;
  created_at: string;
  deep_link: string | null;
  event_type: string;
  notification_event_id: string;
  object_id: string | null;
  object_type: string | null;
  payload_json: string | null;
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
) {
  return apiRequest<MessageSendResponse>(
    `/api/v1/messages/conversations/${encodeURIComponent(conversationId)}/messages`,
    {
      accessToken,
      body: {
        client_message_id: clientMessageId,
        message_type: "text",
        text_content: textContent,
      },
      method: "POST",
    },
  );
}

export function markConversationRead(accessToken: string, conversationId: string) {
  return apiRequest<{ conversation_id: string; success: boolean; unread_count: number }>(
    `/api/v1/messages/conversations/${encodeURIComponent(conversationId)}/read`,
    { accessToken, method: "POST" },
  );
}

export function getUnreadCounts(accessToken: string) {
  return apiRequest<UnreadCountsResponse>("/api/v1/messages/unread-counts", { accessToken });
}

export function listNotifications(
  accessToken: string,
  options: { category?: string | null; page?: number; pageSize?: number; unreadOnly?: boolean } = {},
) {
  const params = [paginationQuery(options.page ?? 1, options.pageSize ?? 30)];
  if (options.category) {
    params.push(`category=${encodeURIComponent(options.category)}`);
  }
  if (options.unreadOnly) {
    params.push("unread_only=true");
  }
  return apiRequest<NotificationListResponse>(`/api/v1/notifications?${params.join("&")}`, {
    accessToken,
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
