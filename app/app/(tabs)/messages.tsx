import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect } from "@react-navigation/native";
import { useRouter } from "expo-router";
import { useCallback, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, View } from "react-native";

import { resolveMediaUrl } from "@/api/activityDetail";
import { ApiError } from "@/api/client";
import {
  acceptMessageRequest,
  declineMessageRequest,
  listConversations,
  listMessageRequests,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type ConversationListItem,
  type MessageRequestRecord,
  type UserNotificationRecord,
} from "@/api/messages";
import { useAuth } from "@/auth/AuthProvider";
import { useRequireAuth } from "@/auth/useRequireAuth";
import { Avatar, Card, IconBadge, ScrollPage, SegmentedControl, TopBar } from "@/components/ui";
import { colors, radius } from "@/theme";

type MessageView = "notice" | "chat" | "request";

const messageOptions = [
  { label: "通知", value: "notice" },
  { label: "聊天", value: "chat" },
  { label: "请求", value: "request" },
] as const;

function readableMessageError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 0) {
      return "无法连接服务器，请确认后端已启动。";
    }
    if (error.status === 401 || error.status === 403) {
      return "登录状态已失效，请重新登录后查看消息。";
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "消息数据加载失败，请稍后重试。";
}

function formatMessageTime(value: string | null | undefined) {
  if (!value) {
    return "刚刚";
  }
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) {
    return value;
  }
  const diffMs = Date.now() - timestamp;
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (diffMs >= 0 && diffMs < minute) {
    return "刚刚";
  }
  if (diffMs >= 0 && diffMs < hour) {
    return `${Math.max(1, Math.floor(diffMs / minute))}分钟前`;
  }
  if (diffMs >= 0 && diffMs < day) {
    return `${Math.floor(diffMs / hour)}小时前`;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    day: "2-digit",
    month: "2-digit",
  }).format(new Date(timestamp));
}

function conversationTitle(item: ConversationListItem) {
  if (item.conversation.conversation_type === "group") {
    return item.conversation.title ?? "群聊";
  }
  return item.other_members[0]?.nickname ?? item.conversation.title ?? "聊天";
}

function conversationAvatar(item: ConversationListItem) {
  if (item.conversation.conversation_type === "group") {
    return resolveMediaUrl(item.conversation.avatar_path);
  }
  return resolveMediaUrl(item.other_members[0]?.avatar_path);
}

function notificationTitle(item: UserNotificationRecord) {
  return item.event.title ?? (item.actor ? `${item.actor.nickname} 有新的互动` : "系统通知");
}

function notificationBody(item: UserNotificationRecord) {
  return item.event.body ?? "打开查看相关消息。";
}

function requestDisplayUser(item: MessageRequestRecord) {
  return item.requester;
}

export default function MessagesScreen() {
  const router = useRouter();
  const requireAuth = useRequireAuth();
  const { accessToken, status } = useAuth();
  const [activeView, setActiveView] = useState<MessageView>("notice");
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [notifications, setNotifications] = useState<UserNotificationRecord[]>([]);
  const [requests, setRequests] = useState<MessageRequestRecord[]>([]);
  const [notificationUnreadCount, setNotificationUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [conversationError, setConversationError] = useState<string | null>(null);
  const [notificationError, setNotificationError] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [requestActionId, setRequestActionId] = useState<string | null>(null);
  const [markingAllRead, setMarkingAllRead] = useState(false);
  const loadRequestIdRef = useRef(0);

  const canLoad = status === "authenticated" && Boolean(accessToken);

  const loadData = useCallback(async () => {
    if (status === "loading") {
      return;
    }
    const requestId = loadRequestIdRef.current + 1;
    loadRequestIdRef.current = requestId;
    if (!accessToken) {
      setConversations([]);
      setNotifications([]);
      setRequests([]);
      setNotificationUnreadCount(0);
      setConversationError(null);
      setNotificationError(null);
      setRequestError(null);
      return;
    }

    setLoading(true);
    setConversationError(null);
    setNotificationError(null);
    setRequestError(null);
    try {
      const [conversationResult, notificationResult, requestResult] = await Promise.allSettled([
        listConversations(accessToken, 1, 30),
        listNotifications(accessToken, { pageSize: 30 }),
        listMessageRequests(accessToken, "inbox", { pageSize: 30, status: "pending" }),
      ]);
      if (loadRequestIdRef.current !== requestId) {
        return;
      }
      if (conversationResult.status === "fulfilled") {
        setConversations(conversationResult.value.items);
      } else {
        setConversationError(readableMessageError(conversationResult.reason));
      }
      if (notificationResult.status === "fulfilled") {
        setNotifications(notificationResult.value.items);
        setNotificationUnreadCount(notificationResult.value.unread_count);
      } else {
        setNotificationError(readableMessageError(notificationResult.reason));
      }
      if (requestResult.status === "fulfilled") {
        setRequests(requestResult.value.items);
      } else {
        setRequestError(readableMessageError(requestResult.reason));
      }
    } catch (loadError) {
      if (loadRequestIdRef.current !== requestId) {
        return;
      }
      const nextError = readableMessageError(loadError);
      setConversationError(nextError);
      setNotificationError(nextError);
      setRequestError(nextError);
    } finally {
      if (loadRequestIdRef.current === requestId) {
        setLoading(false);
      }
    }
  }, [accessToken, status]);

  useFocusEffect(
    useCallback(() => {
      void loadData();
      return () => {
        loadRequestIdRef.current += 1;
      };
    }, [loadData]),
  );

  const openLogin = useCallback(() => {
    requireAuth("登录后可以查看通知、聊天和消息请求", "/(tabs)/messages");
  }, [requireAuth]);

  const openFriendSearch = useCallback(() => {
    if (!requireAuth("登录后可以搜索并添加球友", "/(tabs)/messages")) {
      return;
    }
    router.push("/friends/search");
  }, [requireAuth, router]);

  const markAllRead = useCallback(() => {
    if (!accessToken || markingAllRead || notificationUnreadCount === 0) {
      return;
    }
    setMarkingAllRead(true);
    void markAllNotificationsRead(accessToken)
      .then(() => {
        setNotifications((current) => current.map((item) => ({ ...item, read_at: item.read_at ?? new Date().toISOString() })));
        setNotificationUnreadCount(0);
      })
      .catch((markError) => Alert.alert("操作失败", readableMessageError(markError)))
      .finally(() => setMarkingAllRead(false));
  }, [accessToken, markingAllRead, notificationUnreadCount]);

  const handleRequestAction = useCallback(
    (item: MessageRequestRecord, action: "accept" | "decline") => {
      if (!accessToken || requestActionId) {
        return;
      }
      setRequestActionId(item.message_request_id);
      const request = action === "accept"
        ? acceptMessageRequest(accessToken, item.message_request_id)
        : declineMessageRequest(accessToken, item.message_request_id);
      void request
        .then((response) => {
          setRequests((current) => current.filter((requestItem) => requestItem.message_request_id !== item.message_request_id));
          if (action === "accept" && response.conversation) {
            void loadData();
          }
        })
        .catch((actionError) => Alert.alert("处理失败", readableMessageError(actionError)))
        .finally(() => setRequestActionId(null));
    },
    [accessToken, loadData, requestActionId],
  );

  const rightAction = useMemo(() => {
    return (
      <View style={styles.topActions}>
        {activeView === "notice" && accessToken && notificationUnreadCount > 0 ? (
          <Pressable
            accessibilityLabel="全部标记已读"
            accessibilityRole="button"
            disabled={markingAllRead}
            onPress={markAllRead}
            style={[styles.topAction, markingAllRead && styles.disabled]}
          >
            {markingAllRead ? (
              <ActivityIndicator color={colors.ink} size="small" />
            ) : (
              <Ionicons color={colors.ink} name="checkmark-done" size={19} />
            )}
          </Pressable>
        ) : null}
        <Pressable
          accessibilityLabel="添加球友"
          accessibilityRole="button"
          onPress={openFriendSearch}
          style={styles.topAction}
        >
          <Ionicons color={colors.ink} name="person-add-outline" size={19} />
        </Pressable>
      </View>
    );
  }, [accessToken, activeView, markAllRead, markingAllRead, notificationUnreadCount, openFriendSearch]);

  const activeViewHasItems = useMemo(() => {
    if (activeView === "notice") {
      return notifications.length > 0;
    }
    if (activeView === "chat") {
      return conversations.length > 0;
    }
    return requests.length > 0;
  }, [activeView, conversations.length, notifications.length, requests.length]);

  const activeError = useMemo(() => {
    if (activeView === "notice") {
      return notificationError;
    }
    if (activeView === "chat") {
      return conversationError;
    }
    return requestError;
  }, [activeView, conversationError, notificationError, requestError]);

  const showActiveError = Boolean(activeError && !activeViewHasItems);
  const showActiveLoading = loading && !activeViewHasItems && !showActiveError;

  return (
    <ScrollPage bottomInset={112}>
      <TopBar right={rightAction} title="消息" />
      <SegmentedControl options={[...messageOptions]} value={activeView} onChange={setActiveView} />

      {status === "loading" ? <StateBlock loading message="正在恢复登录状态..." /> : null}
      {status !== "loading" && !canLoad ? (
        <StateBlock
          actionLabel="去登录"
          icon="lock-closed-outline"
          message="登录后可以查看通知、私信和好友消息请求。"
          onAction={openLogin}
        />
      ) : null}
      {canLoad ? (
        <>
          {showActiveLoading ? <StateBlock loading message="正在加载消息..." /> : null}
          {showActiveError ? (
            <StateBlock actionLabel="重试" icon="refresh-outline" message={activeError ?? "消息数据加载失败，请稍后重试。"} onAction={loadData} />
          ) : null}
          {!showActiveLoading && !showActiveError && activeView === "notice" ? (
            <NotificationList
              items={notifications}
              onOpenNotification={(item) => {
                if (!accessToken) {
                  return;
                }
                if (!item.read_at) {
                  void markNotificationRead(accessToken, item.user_notification_id)
                    .then(() => {
                      setNotifications((current) =>
                        current.map((notification) =>
                          notification.user_notification_id === item.user_notification_id
                            ? { ...notification, read_at: new Date().toISOString() }
                            : notification,
                        ),
                      );
                      setNotificationUnreadCount((current) => Math.max(0, current - 1));
                    })
                    .catch(() => undefined);
                }
                if (item.event.deep_link?.includes("messages/requests")) {
                  setActiveView("request");
                  return;
                }
                if (item.event.object_type === "social_post" && item.event.object_id) {
                  router.push({ pathname: "/post/[id]", params: { id: item.event.object_id } });
                  return;
                }
                if (item.event.object_type === "user" && item.event.object_id) {
                  router.push({
                    pathname: "/user/[id]",
                    params: {
                      avatar: item.actor?.avatar_path ?? "",
                      id: item.event.object_id,
                      name: item.actor?.nickname ?? "网球用户",
                    },
                  });
                }
              }}
            />
          ) : null}
          {!showActiveLoading && !showActiveError && activeView === "chat" ? (
            <ChatList items={conversations} onAddFriend={openFriendSearch} />
          ) : null}
          {!showActiveLoading && !showActiveError && activeView === "request" ? (
            <RequestList
              actionPendingId={requestActionId}
              items={requests}
              onAccept={(item) => handleRequestAction(item, "accept")}
              onDecline={(item) => handleRequestAction(item, "decline")}
            />
          ) : null}
        </>
      ) : null}
    </ScrollPage>
  );
}

function NotificationList({
  items,
  onOpenNotification,
}: {
  items: UserNotificationRecord[];
  onOpenNotification: (item: UserNotificationRecord) => void;
}) {
  if (items.length === 0) {
    return <StateBlock icon="sparkles-outline" message="还没有通知。新的关注、评论和系统消息会出现在这里。" />;
  }

  return (
    <View style={styles.list}>
      {items.map((item) => {
        const unread = !item.read_at;
        return (
          <Pressable
            accessibilityLabel={`查看通知：${notificationTitle(item)}`}
            accessibilityRole="button"
            key={item.user_notification_id}
            onPress={() => onOpenNotification(item)}
            style={[styles.noticeCard, unread && styles.unreadCard]}
          >
            <View style={styles.noticeLeading}>
              <IconBadge
                name={item.event.event_type === "follow" ? "person-add-outline" : "notifications-outline"}
                tone={unread ? "accent" : "light"}
              />
              <View style={styles.noticeText}>
                <Text numberOfLines={1} style={styles.noticeTitle}>{notificationTitle(item)}</Text>
                <Text numberOfLines={2} style={styles.noticeDetail}>{notificationBody(item)}</Text>
              </View>
            </View>
            <View style={styles.trailingMeta}>
              {unread ? <View style={styles.unreadDot} /> : null}
              <Text style={styles.noticeTime}>{formatMessageTime(item.created_at)}</Text>
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}

function ChatList({ items, onAddFriend }: { items: ConversationListItem[]; onAddFriend: () => void }) {
  const router = useRouter();

  if (items.length === 0) {
    return (
      <StateBlock
        actionLabel="添加球友"
        icon="chatbubble-ellipses-outline"
        message="还没有聊天。先搜索球友，互相关注后就可以发起私信。"
        onAction={onAddFriend}
      />
    );
  }

  return (
    <View style={styles.list}>
      {items.map((item) => {
        const title = conversationTitle(item);
        const unreadCount = item.member.unread_count;
        return (
          <Pressable
            accessibilityLabel={`打开与${title}的聊天`}
            accessibilityRole="button"
            key={item.conversation.conversation_id}
            onPress={() =>
              router.push({
                pathname: "/chat/[id]",
                params: {
                  id: item.conversation.conversation_id,
                  name: title,
                  avatar: item.other_members[0]?.avatar_path ?? item.conversation.avatar_path ?? "",
                },
              })
            }
            style={[styles.chatRow, unreadCount > 0 && styles.unreadCard]}
          >
            <Avatar name={title} size={48} uri={conversationAvatar(item)} />
            <View style={styles.chatContent}>
              <View style={styles.chatTopLine}>
                <Text numberOfLines={1} style={styles.chatName}>{title}</Text>
                <Text style={styles.chatTime}>{formatMessageTime(item.conversation.last_message_at ?? item.conversation.updated_at)}</Text>
              </View>
              <Text numberOfLines={1} style={styles.chatMessage}>
                {item.conversation.last_message_preview ?? "还没有消息"}
              </Text>
            </View>
            {unreadCount > 0 ? (
              <View style={styles.unreadBadge}>
                <Text style={styles.unreadBadgeText}>{unreadCount > 99 ? "99+" : unreadCount}</Text>
              </View>
            ) : null}
          </Pressable>
        );
      })}
    </View>
  );
}

function RequestList({
  actionPendingId,
  items,
  onAccept,
  onDecline,
}: {
  actionPendingId: string | null;
  items: MessageRequestRecord[];
  onAccept: (item: MessageRequestRecord) => void;
  onDecline: (item: MessageRequestRecord) => void;
}) {
  if (items.length === 0) {
    return <StateBlock icon="person-add-outline" message="暂无待处理消息请求。互相关注的球友可以直接发起私信。" />;
  }

  return (
    <View style={styles.list}>
      {items.map((item) => {
        const user = requestDisplayUser(item);
        const pending = actionPendingId === item.message_request_id;
        return (
          <Card key={item.message_request_id} style={styles.requestCard}>
            <View style={styles.requestHeader}>
              <Avatar name={user.nickname} size={46} uri={resolveMediaUrl(user.avatar_path)} />
              <View style={styles.requestText}>
                <Text numberOfLines={1} style={styles.chatName}>{user.nickname}</Text>
                <Text style={styles.noticeTime}>{formatMessageTime(item.requested_at)}</Text>
              </View>
            </View>
            <Text style={styles.requestMessage}>{item.request_message ?? "想和你开始一次私信聊天。"}</Text>
            <View style={styles.requestActions}>
              <Pressable
                accessibilityRole="button"
                disabled={pending}
                onPress={() => onDecline(item)}
                style={[styles.requestButton, styles.requestButtonSecondary, pending && styles.disabled]}
              >
                <Text style={styles.requestButtonTextSecondary}>忽略</Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                disabled={pending}
                onPress={() => onAccept(item)}
                style={[styles.requestButton, pending && styles.disabled]}
              >
                {pending ? (
                  <ActivityIndicator color={colors.inverse} size="small" />
                ) : (
                  <Text style={styles.requestButtonText}>接受</Text>
                )}
              </Pressable>
            </View>
          </Card>
        );
      })}
    </View>
  );
}

function StateBlock({
  actionLabel,
  icon,
  loading,
  message,
  onAction,
}: {
  actionLabel?: string;
  icon?: keyof typeof Ionicons.glyphMap;
  loading?: boolean;
  message: string;
  onAction?: () => void;
}) {
  return (
    <View style={styles.stateBlock}>
      {loading ? (
        <ActivityIndicator color={colors.accentDeep} />
      ) : icon ? (
        <Ionicons color={colors.accentDeep} name={icon} size={28} />
      ) : null}
      <Text style={styles.stateText}>{message}</Text>
      {actionLabel && onAction ? (
        <Pressable accessibilityRole="button" onPress={onAction} style={styles.stateButton}>
          <Text style={styles.stateButtonText}>{actionLabel}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  list: {
    gap: 10,
    marginTop: 22,
  },
  topActions: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  topAction: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    height: 36,
    justifyContent: "center",
    width: 36,
  },
  noticeCard: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
    minHeight: 76,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  unreadCard: {
    borderColor: colors.accent,
    backgroundColor: colors.surfaceWarm,
  },
  noticeLeading: {
    flex: 1,
    flexDirection: "row",
    gap: 12,
    minWidth: 0,
  },
  noticeText: {
    flex: 1,
    gap: 5,
    minWidth: 0,
  },
  noticeTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "800",
  },
  noticeDetail: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "600",
    lineHeight: 18,
  },
  trailingMeta: {
    alignItems: "flex-end",
    gap: 7,
  },
  noticeTime: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "700",
  },
  unreadDot: {
    backgroundColor: colors.clay,
    borderRadius: 4,
    height: 8,
    width: 8,
  },
  chatRow: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 12,
    minHeight: 76,
    paddingHorizontal: 14,
  },
  chatContent: {
    flex: 1,
    gap: 5,
    minWidth: 0,
  },
  chatTopLine: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
    justifyContent: "space-between",
  },
  chatName: {
    color: colors.ink,
    flex: 1,
    fontSize: 15,
    fontWeight: "800",
  },
  chatTime: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "700",
  },
  chatMessage: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "600",
  },
  unreadBadge: {
    alignItems: "center",
    backgroundColor: colors.clay,
    borderRadius: 11,
    justifyContent: "center",
    minWidth: 22,
    paddingHorizontal: 6,
    height: 22,
  },
  unreadBadgeText: {
    color: colors.inverse,
    fontSize: 11,
    fontWeight: "900",
  },
  requestCard: {
    gap: 12,
  },
  requestHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 11,
  },
  requestText: {
    flex: 1,
    gap: 4,
    minWidth: 0,
  },
  requestMessage: {
    color: colors.inkSoft,
    fontSize: 13,
    fontWeight: "700",
    lineHeight: 20,
  },
  requestActions: {
    flexDirection: "row",
    gap: 10,
  },
  requestButton: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    flex: 1,
    justifyContent: "center",
    minHeight: 42,
  },
  requestButtonSecondary: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderWidth: StyleSheet.hairlineWidth,
  },
  requestButtonText: {
    color: colors.inverse,
    fontSize: 14,
    fontWeight: "900",
  },
  requestButtonTextSecondary: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "900",
  },
  stateBlock: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 10,
    marginTop: 22,
    padding: 18,
  },
  stateText: {
    color: colors.inkSoft,
    fontSize: 13,
    fontWeight: "700",
    lineHeight: 20,
    textAlign: "center",
  },
  stateButton: {
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    marginTop: 2,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  stateButtonText: {
    color: colors.inverse,
    fontSize: 13,
    fontWeight: "900",
  },
  disabled: {
    opacity: 0.56,
  },
});
