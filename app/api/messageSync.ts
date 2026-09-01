import { ApiError, apiRequest } from "@/api/client";
import {
  getUnreadCounts,
  listConversations,
  listNotifications,
  type ConversationListResponse,
  type NotificationListResponse,
  type UnreadCountsResponse,
} from "@/api/messages";
import { getMessageDeviceId, readMessageSyncState, writeMessageSyncState } from "@/api/messageOutbox";

export type MessageDevicePlatform = "ios" | "android" | "web" | "unknown";

export type MessageDevice = {
  device_id: string;
  user_id: string;
  platform: MessageDevicePlatform;
  app_version: string | null;
  created_at: string;
  last_seen_at: string;
  revoked_at: string | null;
  updated_at: string;
};

export type MessageSyncEvent = {
  user_sync_event_id: string;
  event_id: string;
  event_type: "message.created" | "message.recalled" | "message.edited" | "message.reaction_changed" | "message.forwarded" | "conversation.read" | "conversation.members_changed";
  event_version: number;
  aggregate_type: string;
  aggregate_id: string;
  actor_user_id: string | null;
  recipient_user_id: string;
  conversation_id: string | null;
  message_id: string | null;
  message_seq: number | null;
  occurred_at: string;
  persisted_at: string;
  privacy_classification: "private_metadata";
  payload: Record<string, unknown>;
};

export type MessageSyncResponse = {
  items: MessageSyncEvent[];
  next_cursor: string | null;
  has_more: boolean;
  server_watermark: string | null;
  cursor_status: "initial" | "valid";
  requires_full_reconciliation: boolean;
};

export type MessageSyncRecovery = {
  conversations: ConversationListResponse;
  unreadCounts: UnreadCountsResponse;
  notifications: NotificationListResponse;
  requiresHistory: true;
};

export function registerMessageDevice(
  accessToken: string,
  deviceId: string,
  platform: MessageDevicePlatform,
  appVersion?: string | null,
) {
  return apiRequest<{ device: MessageDevice }>("/api/v1/messages/devices", {
    accessToken,
    body: { app_version: appVersion ?? null, device_id: deviceId, platform },
    method: "POST",
  });
}

export function updateMessageDevice(
  accessToken: string,
  deviceId: string,
  platform: MessageDevicePlatform,
  appVersion?: string | null,
) {
  return apiRequest<{ device: MessageDevice }>(
    `/api/v1/messages/devices/${encodeURIComponent(deviceId)}`,
    {
      accessToken,
      body: { app_version: appVersion ?? null, platform },
      method: "PATCH",
    },
  );
}

export function revokeMessageDevice(accessToken: string, deviceId: string) {
  return apiRequest<{ device: MessageDevice }>(
    `/api/v1/messages/devices/${encodeURIComponent(deviceId)}`,
    { accessToken, method: "DELETE" },
  );
}

export function listMessageSyncEvents(
  accessToken: string,
  deviceId: string,
  options: { cursor?: string | null; limit?: number } = {},
) {
  const params = new URLSearchParams({
    device_id: deviceId,
    limit: String(options.limit ?? 50),
  });
  if (options.cursor) params.set("cursor", options.cursor);
  return apiRequest<MessageSyncResponse>(`/api/v1/messages/sync?${params.toString()}`, {
    accessToken,
    captureDiagnostics: false,
  });
}

export function saveMessageSyncCheckpoint(accessToken: string, deviceId: string, cursor: string) {
  return apiRequest<{
    success: boolean;
    device_id: string;
    cursor: string;
    updated_at: string;
  }>("/api/v1/messages/sync/checkpoints", {
    accessToken,
    body: { cursor, device_id: deviceId },
    method: "POST",
  });
}

export async function syncMessagesWithRecovery(
  accessToken: string,
  options: { limit?: number } = {},
): Promise<{ response: MessageSyncResponse; recovery: MessageSyncRecovery | null }> {
  const deviceId = await getMessageDeviceId();
  await registerMessageDevice(accessToken, deviceId, "unknown");
  const state = await readMessageSyncState();
  try {
    const response = await listMessageSyncEvents(accessToken, deviceId, {
      cursor: state.cursor,
      limit: options.limit,
    });
    const seen = new Set(state.event_ids);
    const items = response.items.filter((item) => {
      if (seen.has(item.event_id)) return false;
      seen.add(item.event_id);
      return true;
    });
    const nextState = {
      cursor: response.next_cursor ?? state.cursor,
      event_ids: Array.from(seen).slice(-500),
    };
    await writeMessageSyncState(nextState);
    if (response.next_cursor) {
      await saveMessageSyncCheckpoint(accessToken, deviceId, response.next_cursor);
    }
    return { response: { ...response, items }, recovery: null };
  } catch (error) {
    if (!(error instanceof ApiError) || error.code !== "SYNC_CURSOR_EXPIRED") throw error;
    await writeMessageSyncState({ cursor: null, event_ids: [] });
    const [conversations, unreadCounts, notifications] = await Promise.all([
      listConversations(accessToken, 1, 50),
      getUnreadCounts(accessToken),
      listNotifications(accessToken, { page: 1, pageSize: 50 }),
    ]);
    return {
      response: {
        items: [],
        next_cursor: null,
        has_more: false,
        server_watermark: null,
        cursor_status: "initial",
        requires_full_reconciliation: true,
      },
      recovery: { conversations, unreadCounts, notifications, requiresHistory: true },
    };
  }
}
