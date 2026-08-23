import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect } from "@react-navigation/native";
import { useRouter } from "expo-router";
import { useCallback, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Alert, AppState, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { resolveMediaUrl } from "@/api/activityDetail";
import { ApiError } from "@/api/client";
import { resolveNotificationRoute } from "@/api/messageNotificationRoute";
import {
  acceptMessageRequest,
  declineMessageRequest,
  hideConversation,
  listConversations,
  listMessageRequests,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  muteConversation,
  pinConversation,
  searchConversations,
  type ConversationListItem,
  type MessageRequestRecord,
  type NotificationProductCategory,
  type UserNotificationRecord,
  unpinConversation,
  unmuteConversation,
} from "@/api/messages";
import { useAuth } from "@/auth/AuthProvider";
import { useRequireAuth } from "@/auth/useRequireAuth";
import { Avatar, Card, IconBadge, ScrollPage, SegmentedControl, TopBar } from "@/components/ui";
import { colors, radius } from "@/theme";

type MessageView = "notice" | "chat" | "request";
type NotificationViewCategory = Exclude<NotificationProductCategory, "request">;
type LoadDataOptions = { silent?: boolean; queueIfInFlight?: boolean };
type LoadNotificationCategoryOptions = { showLoading?: boolean };
type RequestPendingAction = { id: string; action: "accept" | "decline" };

const MESSAGES_POLL_INTERVAL_MS = 8000;

const messageOptions = [
  { label: "通知", value: "notice" },
  { label: "聊天", value: "chat" },
  { label: "请求", value: "request" },
] as const;

const notificationCategoryOptions = [
  { label: "互动关注", value: "interaction_follow" },
  { label: "课程系统", value: "course_system" },
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
  const [activeNotificationCategory, setActiveNotificationCategory] =
    useState<NotificationViewCategory>("interaction_follow");
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [conversationSearchMode, setConversationSearchMode] = useState(false);
  const [conversationSearchQuery, setConversationSearchQuery] = useState("");
  const [submittedConversationSearchQuery, setSubmittedConversationSearchQuery] = useState("");
  const [conversationSearchResults, setConversationSearchResults] = useState<ConversationListItem[]>([]);
  const [conversationSearchPage, setConversationSearchPage] = useState<number | null>(null);
  const [conversationSearchLoading, setConversationSearchLoading] = useState(false);
  const [conversationSearchLoadingMore, setConversationSearchLoadingMore] = useState(false);
  const [conversationSearchError, setConversationSearchError] = useState<string | null>(null);
  const [conversationSearchCompleted, setConversationSearchCompleted] = useState(false);
  const [notifications, setNotifications] = useState<UserNotificationRecord[]>([]);
  const [requests, setRequests] = useState<MessageRequestRecord[]>([]);
  const [notificationUnreadCount, setNotificationUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [notificationCategoryLoading, setNotificationCategoryLoading] = useState(false);
  const [conversationError, setConversationError] = useState<string | null>(null);
  const [notificationError, setNotificationError] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [requestAction, setRequestAction] = useState<RequestPendingAction | null>(null);
  const [markingAllRead, setMarkingAllRead] = useState(false);
  const [conversationMutationIds, setConversationMutationIds] = useState<Set<string>>(new Set());
  const requestActionInFlightRef = useRef<string | null>(null);
  const handledRequestIdsRef = useRef<Set<string>>(new Set());
  const loadRequestIdRef = useRef(0);
  const refreshInFlightRef = useRef(false);
  const refreshQueuedRef = useRef(false);
  const screenFocusedRef = useRef(false);
  const notificationMutationGenerationRef = useRef(0);
  const notificationCategoryRef = useRef<NotificationViewCategory>("interaction_follow");
  const notificationCategoryGenerationRef = useRef(0);
  const notificationCategoryRequestIdRef = useRef(0);
  const loadDataRef = useRef<(options?: LoadDataOptions) => Promise<void>>(async () => undefined);
  const conversationMutationInFlightRef = useRef<Set<string>>(new Set());
  const conversationSearchRequestIdRef = useRef(0);
  const conversationSearchPaginationInFlightRef = useRef(false);

  const canLoad = status === "authenticated" && Boolean(accessToken);

  const loadData = useCallback(async ({ silent = false, queueIfInFlight = true }: LoadDataOptions = {}) => {
    if (status === "loading") {
      return;
    }
    if (!accessToken) {
      refreshQueuedRef.current = false;
      notificationCategoryRequestIdRef.current += 1;
      setConversations([]);
      setNotifications([]);
      setRequests([]);
      setNotificationUnreadCount(0);
      setNotificationCategoryLoading(false);
      setConversationError(null);
      setNotificationError(null);
      setRequestError(null);
      return;
    }
    if (silent && (!screenFocusedRef.current || AppState.currentState !== "active")) {
      return;
    }
    if (refreshInFlightRef.current) {
      if (queueIfInFlight) {
        refreshQueuedRef.current = true;
      }
      return;
    }

    const requestId = loadRequestIdRef.current + 1;
    loadRequestIdRef.current = requestId;
    const notificationRequestId = notificationCategoryRequestIdRef.current + 1;
    notificationCategoryRequestIdRef.current = notificationRequestId;
    const notificationMutationGeneration = notificationMutationGenerationRef.current;
    const notificationCategory = notificationCategoryRef.current;
    const notificationCategoryGeneration = notificationCategoryGenerationRef.current;
    refreshInFlightRef.current = true;
    if (!silent) {
      setLoading(true);
      setConversationError(null);
      setNotificationError(null);
      setRequestError(null);
    }
    try {
      const [conversationResult, notificationResult, requestResult] = await Promise.allSettled([
        listConversations(accessToken, 1, 30),
        listNotifications(accessToken, { pageSize: 30, productCategory: notificationCategory }),
        listMessageRequests(accessToken, "inbox", { pageSize: 30, status: "pending" }),
      ]);
      if (loadRequestIdRef.current !== requestId) {
        return;
      }
      if (conversationResult.status === "fulfilled") {
        setConversations(conversationResult.value.items);
        setConversationError(null);
      } else if (!silent) {
        setConversationError(readableMessageError(conversationResult.reason));
      }
      if (
        notificationResult.status === "fulfilled" &&
        notificationCategoryRequestIdRef.current === notificationRequestId &&
        notificationMutationGenerationRef.current === notificationMutationGeneration &&
        notificationCategoryGenerationRef.current === notificationCategoryGeneration &&
        notificationCategoryRef.current === notificationCategory
      ) {
        setNotifications(notificationResult.value.items);
        setNotificationUnreadCount(notificationResult.value.unread_count);
        setNotificationError(null);
      } else if (
        notificationResult.status === "rejected" &&
        !silent &&
        notificationCategoryRequestIdRef.current === notificationRequestId &&
        notificationCategoryGenerationRef.current === notificationCategoryGeneration &&
        notificationCategoryRef.current === notificationCategory
      ) {
        setNotificationError(readableMessageError(notificationResult.reason));
      }
      if (requestResult.status === "fulfilled") {
        setRequests(requestResult.value.items.filter((item) => !handledRequestIdsRef.current.has(item.message_request_id)));
        setRequestError(null);
      } else if (!silent) {
        setRequestError(readableMessageError(requestResult.reason));
      }
    } catch (loadError) {
      if (loadRequestIdRef.current !== requestId) {
        return;
      }
      if (!silent) {
        const nextError = readableMessageError(loadError);
        setConversationError(nextError);
        setNotificationError(nextError);
        setRequestError(nextError);
      }
    } finally {
      if (!silent) {
        setLoading(false);
      }
      if (
        notificationCategoryRequestIdRef.current === notificationRequestId &&
        notificationCategoryGenerationRef.current === notificationCategoryGeneration &&
        notificationCategoryRef.current === notificationCategory
      ) {
        setNotificationCategoryLoading(false);
      }
      refreshInFlightRef.current = false;
      if (refreshQueuedRef.current && screenFocusedRef.current && AppState.currentState === "active") {
        refreshQueuedRef.current = false;
        void loadDataRef.current({ silent: true });
      }
    }
  }, [accessToken, status]);
  loadDataRef.current = loadData;

  const handleConversationPin = useCallback(
    (conversationId: string, currentlyPinned: boolean) => {
      if (!accessToken || status !== "authenticated") {
        return;
      }
      if (conversationMutationInFlightRef.current.has(conversationId)) {
        return;
      }

      conversationMutationInFlightRef.current.add(conversationId);
      setConversationMutationIds((current) => new Set(current).add(conversationId));
      // Invalidate any older list response so it cannot overwrite a successful mutation.
      loadRequestIdRef.current += 1;
      const mutation = currentlyPinned
        ? unpinConversation(accessToken, conversationId)
        : pinConversation(accessToken, conversationId);
      void mutation
        .then((response) => {
          setConversations((current) =>
            current.map((item) =>
              item.conversation.conversation_id === conversationId
                ? { ...item, member: { ...item.member, pinned_at: response.pinned_at } }
                : item,
            ),
          );
          void loadDataRef.current({ silent: true });
        })
        .catch((mutationError) => {
          Alert.alert("操作失败", readableMessageError(mutationError));
          void loadDataRef.current({ silent: true });
        })
        .finally(() => {
          conversationMutationInFlightRef.current.delete(conversationId);
          setConversationMutationIds((current) => {
            const next = new Set(current);
            next.delete(conversationId);
            return next;
          });
        });
    },
    [accessToken, status],
  );

  const handleConversationMute = useCallback(
    (conversationId: string, currentlyMuted: boolean) => {
      if (!accessToken || status !== "authenticated") {
        return;
      }
      if (conversationMutationInFlightRef.current.has(conversationId)) {
        return;
      }

      conversationMutationInFlightRef.current.add(conversationId);
      setConversationMutationIds((current) => new Set(current).add(conversationId));
      // Invalidate any older list response so it cannot overwrite a successful mutation.
      loadRequestIdRef.current += 1;
      const mutation = currentlyMuted
        ? unmuteConversation(accessToken, conversationId)
        : muteConversation(accessToken, conversationId);
      void mutation
        .then((response) => {
          setConversations((current) =>
            current.map((item) =>
              item.conversation.conversation_id === conversationId
                ? {
                    ...item,
                    member: {
                      ...item.member,
                      is_muted: response.is_muted,
                      muted_until: response.muted_until,
                    },
                  }
                : item,
            ),
          );
          void loadDataRef.current({ silent: true });
        })
        .catch((mutationError) => {
          Alert.alert("操作失败", readableMessageError(mutationError));
          void loadDataRef.current({ silent: true });
        })
        .finally(() => {
          conversationMutationInFlightRef.current.delete(conversationId);
          setConversationMutationIds((current) => {
            const next = new Set(current);
            next.delete(conversationId);
            return next;
          });
        });
    },
    [accessToken, status],
  );

  const handleConversationHide = useCallback(
    (conversationId: string) => {
      if (!accessToken || status !== "authenticated" || conversationMutationInFlightRef.current.has(conversationId)) {
        return;
      }
      Alert.alert("隐藏聊天？", "聊天记录不会删除。有新消息时会重新显示。", [
        { text: "取消", style: "cancel" },
        {
          text: "隐藏",
          style: "destructive",
          onPress: () => {
            if (conversationMutationInFlightRef.current.has(conversationId)) {
              return;
            }
            conversationMutationInFlightRef.current.add(conversationId);
            setConversationMutationIds((current) => new Set(current).add(conversationId));
            // Invalidate any older list response so it cannot restore a hidden row.
            loadRequestIdRef.current += 1;
            void hideConversation(accessToken, conversationId)
              .then(() => {
                setConversations((current) =>
                  current.filter((item) => item.conversation.conversation_id !== conversationId),
                );
                void loadDataRef.current({ silent: true });
              })
              .catch((mutationError) => {
                Alert.alert("操作失败", readableMessageError(mutationError));
                void loadDataRef.current({ silent: true });
              })
              .finally(() => {
                conversationMutationInFlightRef.current.delete(conversationId);
                setConversationMutationIds((current) => {
                  const next = new Set(current);
                  next.delete(conversationId);
                  return next;
                });
              });
          },
        },
      ]);
    },
    [accessToken, status],
  );

  const loadNotificationCategory = useCallback(async (
    category: NotificationViewCategory,
    { showLoading = true }: LoadNotificationCategoryOptions = {},
  ) => {
    if (!accessToken || status !== "authenticated") {
      return;
    }
    const requestId = notificationCategoryRequestIdRef.current + 1;
    notificationCategoryRequestIdRef.current = requestId;
    const categoryGeneration = notificationCategoryGenerationRef.current;
    const mutationGeneration = notificationMutationGenerationRef.current;
    if (showLoading) {
      setNotificationCategoryLoading(true);
      setNotificationError(null);
    }
    try {
      const response = await listNotifications(accessToken, { pageSize: 30, productCategory: category });
      if (
        notificationCategoryRequestIdRef.current !== requestId ||
        notificationCategoryGenerationRef.current !== categoryGeneration ||
        notificationCategoryRef.current !== category ||
        !screenFocusedRef.current
      ) {
        return;
      }
      if (notificationMutationGenerationRef.current !== mutationGeneration) {
        void loadDataRef.current({ silent: true });
        return;
      }
      setNotifications(response.items);
      setNotificationUnreadCount(response.unread_count);
      setNotificationError(null);
    } catch (categoryError) {
      if (
        notificationCategoryRequestIdRef.current === requestId &&
        notificationCategoryGenerationRef.current === categoryGeneration &&
        notificationCategoryRef.current === category &&
        screenFocusedRef.current
      ) {
        setNotificationError(readableMessageError(categoryError));
      }
    } finally {
      if (
        notificationCategoryRequestIdRef.current === requestId &&
        notificationCategoryGenerationRef.current === categoryGeneration &&
        notificationCategoryRef.current === category
      ) {
        setNotificationCategoryLoading(false);
      }
    }
  }, [accessToken, status]);

  useFocusEffect(
    useCallback(() => {
      screenFocusedRef.current = true;
      void loadData();
      let pollTimer: ReturnType<typeof setInterval> | null = null;
      let focused = true;

      const stopPolling = () => {
        if (pollTimer !== null) {
          clearInterval(pollTimer);
          pollTimer = null;
        }
      };
      const startPolling = () => {
        stopPolling();
        if (!focused || AppState.currentState !== "active" || !accessToken || status !== "authenticated") {
          return;
        }
        pollTimer = setInterval(() => {
          void loadData({ silent: true });
        }, MESSAGES_POLL_INTERVAL_MS);
      };
      const handleAppStateChange = (nextState: string) => {
        if (nextState === "active") {
          void loadData({ silent: true });
          startPolling();
        } else {
          refreshQueuedRef.current = false;
          stopPolling();
        }
      };

      startPolling();
      const appStateSubscription = AppState.addEventListener("change", handleAppStateChange);
      return () => {
        focused = false;
        screenFocusedRef.current = false;
        refreshQueuedRef.current = false;
        stopPolling();
        appStateSubscription.remove();
        loadRequestIdRef.current += 1;
        notificationCategoryRequestIdRef.current += 1;
      };
    }, [accessToken, loadData, status]),
  );

  const openLogin = useCallback(() => {
    requireAuth("登录后可以查看通知、聊天和消息请求", "/(tabs)/messages");
  }, [requireAuth]);

  const handleNotificationCategoryChange = useCallback((category: NotificationViewCategory) => {
    if (notificationCategoryRef.current === category) {
      return;
    }
    notificationCategoryRef.current = category;
    notificationCategoryGenerationRef.current += 1;
    setActiveNotificationCategory(category);
    setNotifications([]);
    setNotificationError(null);
    if (screenFocusedRef.current && AppState.currentState === "active") {
      void loadNotificationCategory(category);
    }
  }, [loadNotificationCategory]);

  const openFriendSearch = useCallback(() => {
    if (!requireAuth("登录后可以搜索并添加球友", "/(tabs)/messages")) {
      return;
    }
    router.push("/friends/search");
  }, [requireAuth, router]);

  const openCreateGroup = useCallback(() => {
    if (!requireAuth("登录后可以创建群聊", "/(tabs)/messages")) {
      return;
    }
    router.push("/messages/create-group");
  }, [requireAuth, router]);

  const runConversationSearch = useCallback((page = 1, append = false) => {
    const query = (append ? submittedConversationSearchQuery : conversationSearchQuery).trim();
    if (!accessToken || !query) {
      if (!append) {
        setConversationSearchError("请输入要搜索的聊天名称。");
        setConversationSearchCompleted(false);
      }
      return;
    }
    if (append && conversationSearchPaginationInFlightRef.current) {
      return;
    }

    const requestId = conversationSearchRequestIdRef.current + 1;
    conversationSearchRequestIdRef.current = requestId;
    if (append) {
      conversationSearchPaginationInFlightRef.current = true;
      setConversationSearchLoadingMore(true);
    } else {
      conversationSearchPaginationInFlightRef.current = false;
      setSubmittedConversationSearchQuery(query);
      setConversationSearchResults([]);
      setConversationSearchPage(null);
      setConversationSearchError(null);
      setConversationSearchCompleted(false);
      setConversationSearchLoading(true);
    }

    void searchConversations(accessToken, query, { page, pageSize: 30 })
      .then((response) => {
        if (conversationSearchRequestIdRef.current !== requestId) {
          return;
        }
        setConversationSearchResults((current) => (append ? [...current, ...response.items] : response.items));
        setConversationSearchPage(response.items.length === response.page_size ? response.page + 1 : null);
        setConversationSearchCompleted(true);
      })
      .catch((searchError) => {
        if (conversationSearchRequestIdRef.current === requestId) {
          setConversationSearchError(readableMessageError(searchError));
          setConversationSearchCompleted(true);
        }
      })
      .finally(() => {
        if (conversationSearchRequestIdRef.current === requestId) {
          setConversationSearchLoading(false);
          setConversationSearchLoadingMore(false);
          if (append) {
            conversationSearchPaginationInFlightRef.current = false;
          }
        }
      });
  }, [accessToken, conversationSearchQuery, submittedConversationSearchQuery]);

  const openConversationSearch = useCallback(() => {
    setConversationSearchMode(true);
    setConversationSearchQuery("");
    setSubmittedConversationSearchQuery("");
    setConversationSearchResults([]);
    setConversationSearchPage(null);
    setConversationSearchError(null);
    setConversationSearchCompleted(false);
  }, []);

  const closeConversationSearch = useCallback(() => {
    conversationSearchRequestIdRef.current += 1;
    conversationSearchPaginationInFlightRef.current = false;
    setConversationSearchMode(false);
    setConversationSearchLoading(false);
    setConversationSearchLoadingMore(false);
    setConversationSearchError(null);
  }, []);

  const markAllRead = useCallback(() => {
    if (!accessToken || markingAllRead || notificationUnreadCount === 0) {
      return;
    }
    notificationMutationGenerationRef.current += 1;
    setMarkingAllRead(true);
    void markAllNotificationsRead(accessToken)
      .then(() => {
        notificationMutationGenerationRef.current += 1;
        setNotifications((current) => current.map((item) => ({ ...item, read_at: item.read_at ?? new Date().toISOString() })));
        setNotificationUnreadCount(0);
      })
      .catch((markError) => Alert.alert("操作失败", readableMessageError(markError)))
      .finally(() => setMarkingAllRead(false));
  }, [accessToken, markingAllRead, notificationUnreadCount]);

  const handleRequestAction = useCallback(
    (item: MessageRequestRecord, action: "accept" | "decline") => {
      if (!accessToken || requestActionInFlightRef.current) {
        return;
      }
      requestActionInFlightRef.current = item.message_request_id;
      setRequestAction({ id: item.message_request_id, action });
      const request = action === "accept"
        ? acceptMessageRequest(accessToken, item.message_request_id)
        : declineMessageRequest(accessToken, item.message_request_id);
      void request
        .then((response) => {
          handledRequestIdsRef.current.add(item.message_request_id);
          setRequests((current) => current.filter((requestItem) => requestItem.message_request_id !== item.message_request_id));
          if (action === "accept" && response.conversation) {
            void loadData({ silent: true });
            const conversationTitle = response.other_members[0]?.nickname ?? response.conversation.title ?? "聊天";
            router.push({
              pathname: "/chat/[id]",
              params: {
                avatar: response.other_members[0]?.avatar_path ?? response.conversation.avatar_path ?? "",
                id: response.conversation.conversation_id,
                name: conversationTitle,
              },
            });
          }
        })
        .catch((actionError) => Alert.alert("处理失败", readableMessageError(actionError)))
        .finally(() => {
          requestActionInFlightRef.current = null;
          setRequestAction(null);
        });
    },
    [accessToken, loadData, router],
  );

  const visibleMessageOptions = useMemo(
    () => messageOptions.map((option) => option.value === "request" && requests.length > 0
      ? { ...option, label: `请求 (${requests.length})` }
      : option),
    [requests.length],
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
        {activeView === "chat" ? (
          <Pressable
            accessibilityLabel="搜索聊天"
            accessibilityRole="button"
            onPress={openConversationSearch}
            style={styles.topAction}
          >
            <Ionicons color={colors.ink} name="search" size={19} />
          </Pressable>
        ) : null}
        {activeView === "chat" ? (
          <Pressable
            accessibilityLabel="创建群聊"
            accessibilityRole="button"
            onPress={openCreateGroup}
            style={styles.topAction}
          >
            <Ionicons color={colors.ink} name="people-outline" size={19} />
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
  }, [accessToken, activeView, markAllRead, markingAllRead, notificationUnreadCount, openConversationSearch, openCreateGroup, openFriendSearch]);

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

  const retryActiveView = useCallback(() => {
    if (activeView === "notice") {
      void loadNotificationCategory(notificationCategoryRef.current);
      return;
    }
    void loadData();
  }, [activeView, loadData, loadNotificationCategory]);

  const showActiveError = Boolean(activeError && !activeViewHasItems);
  const showActiveLoading = (loading || (activeView === "notice" && notificationCategoryLoading))
    && !activeViewHasItems
    && !showActiveError;
  const notificationEmptyMessage = activeNotificationCategory === "interaction_follow"
    ? "暂无互动关注通知。"
    : "暂无课程系统通知。";

  return (
    <ScrollPage bottomInset={112}>
      <TopBar right={rightAction} title="消息" />
      <SegmentedControl options={visibleMessageOptions} value={activeView} onChange={setActiveView} />
      {activeView === "notice" ? (
        <View style={styles.notificationCategoryControl}>
          <SegmentedControl
            options={[...notificationCategoryOptions]}
            value={activeNotificationCategory}
            onChange={handleNotificationCategoryChange}
          />
        </View>
      ) : null}

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
            <StateBlock actionLabel="重试" icon="refresh-outline" message={activeError ?? "消息数据加载失败，请稍后重试。"} onAction={retryActiveView} />
          ) : null}
          {!showActiveLoading && !showActiveError && activeView === "notice" ? (
            <NotificationList
              emptyMessage={notificationEmptyMessage}
              items={notifications}
              onOpenNotification={(item) => {
                if (!accessToken) {
                  return;
                }
                if (!item.read_at) {
                  notificationMutationGenerationRef.current += 1;
                  void markNotificationRead(accessToken, item.user_notification_id)
                    .then(() => {
                      notificationMutationGenerationRef.current += 1;
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
                const routeIntent = resolveNotificationRoute(item.event.target, item.actor);
                if (routeIntent.kind === "request_view") {
                  setActiveView("request");
                  return;
                }
                if (routeIntent.kind === "navigate") {
                  router.push(routeIntent.href);
                }
              }}
            />
          ) : null}
          {!showActiveLoading && !showActiveError && activeView === "chat" ? (
            conversationSearchMode ? (
              <ConversationSearchPanel
                completed={conversationSearchCompleted}
                error={conversationSearchError}
                loading={conversationSearchLoading}
                loadingMore={conversationSearchLoadingMore}
                nextPage={conversationSearchPage}
                onClose={closeConversationSearch}
                onLoadMore={() => {
                  if (conversationSearchPage) {
                    runConversationSearch(conversationSearchPage, true);
                  }
                }}
                onQueryChange={setConversationSearchQuery}
                onSubmit={() => runConversationSearch()}
                query={conversationSearchQuery}
                results={conversationSearchResults}
              />
            ) : (
              <ChatList
                items={conversations}
                mutationIds={conversationMutationIds}
                onAddFriend={openFriendSearch}
                onTogglePin={handleConversationPin}
                onToggleMute={handleConversationMute}
                onHideConversation={handleConversationHide}
              />
            )
          ) : null}
          {!showActiveLoading && !showActiveError && activeView === "request" ? (
            <RequestList
              actionPending={requestAction}
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
  emptyMessage,
  items,
  onOpenNotification,
}: {
  emptyMessage: string;
  items: UserNotificationRecord[];
  onOpenNotification: (item: UserNotificationRecord) => void;
}) {
  if (items.length === 0) {
    return <StateBlock icon="sparkles-outline" message={emptyMessage} />;
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

function ConversationSearchPanel({
  completed,
  error,
  loading,
  loadingMore,
  nextPage,
  onClose,
  onLoadMore,
  onQueryChange,
  onSubmit,
  query,
  results,
}: {
  completed: boolean;
  error: string | null;
  loading: boolean;
  loadingMore: boolean;
  nextPage: number | null;
  onClose: () => void;
  onLoadMore: () => void;
  onQueryChange: (value: string) => void;
  onSubmit: () => void;
  query: string;
  results: ConversationListItem[];
}) {
  return (
    <View style={styles.searchPanel}>
      <View style={styles.searchInputRow}>
        <Ionicons color={colors.muted} name="search" size={18} />
        <TextInput
          autoCapitalize="none"
          autoCorrect={false}
          onChangeText={onQueryChange}
          onSubmitEditing={onSubmit}
          placeholder="搜索聊天"
          placeholderTextColor={colors.muted}
          returnKeyType="search"
          style={styles.searchInput}
          value={query}
        />
        <Pressable accessibilityLabel="开始搜索" accessibilityRole="button" onPress={onSubmit} style={styles.searchSubmitButton}>
          <Ionicons color={colors.inverse} name="search" size={16} />
        </Pressable>
        <Pressable accessibilityLabel="关闭聊天搜索" accessibilityRole="button" onPress={onClose} style={styles.searchCloseButton}>
          <Ionicons color={colors.ink} name="close" size={19} />
        </Pressable>
      </View>
      {loading ? <StateBlock loading message="正在搜索聊天..." /> : null}
      {error ? <StateBlock actionLabel="重试" icon="refresh-outline" message={error} onAction={onSubmit} /> : null}
      {!loading && !error && completed && results.length === 0 ? (
        <StateBlock icon="search-outline" message="未找到相关聊天" />
      ) : null}
      {results.map((item) => (
        <ConversationSearchRow item={item} key={item.conversation.conversation_id} />
      ))}
      {nextPage ? (
        <Pressable
          accessibilityRole="button"
          disabled={loadingMore}
          onPress={onLoadMore}
          style={[styles.searchMoreButton, loadingMore && styles.disabled]}
        >
          {loadingMore ? <ActivityIndicator color={colors.ink} size="small" /> : <Text style={styles.searchMoreText}>加载更多聊天</Text>}
        </Pressable>
      ) : null}
    </View>
  );
}

function ConversationSearchRow({ item }: { item: ConversationListItem }) {
  const router = useRouter();
  const title = conversationTitle(item);
  const pinned = Boolean(item.member.pinned_at);
  const muted = item.member.is_muted;
  const unreadCount = item.member.unread_count;
  return (
    <Pressable
      accessibilityLabel={`打开与${title}的聊天`}
      accessibilityRole="button"
      onPress={() => router.push({
        pathname: "/chat/[id]",
        params: {
          id: item.conversation.conversation_id,
          name: title,
          avatar: item.other_members[0]?.avatar_path ?? item.conversation.avatar_path ?? "",
        },
      })}
      style={[styles.chatRow, unreadCount > 0 && styles.unreadCard]}
    >
      <Avatar name={title} size={48} uri={conversationAvatar(item)} />
      <View style={styles.chatContent}>
        <View style={styles.chatTopLine}>
          <Text numberOfLines={1} style={styles.chatName}>{title}</Text>
          <Text style={styles.chatTime}>{formatMessageTime(item.conversation.last_message_at ?? item.conversation.updated_at)}</Text>
        </View>
        <Text numberOfLines={1} style={styles.chatMessage}>{item.conversation.last_message_preview ?? "还没有消息"}</Text>
      </View>
      {pinned ? <Ionicons color={colors.clay} name="pin" size={16} /> : null}
      {muted ? <Ionicons color={colors.muted} name="notifications-off-outline" size={16} /> : null}
      {unreadCount > 0 ? (
        <View style={styles.unreadBadge}>
          <Text style={styles.unreadBadgeText}>{unreadCount > 99 ? "99+" : unreadCount}</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

function ChatList({
  items,
  mutationIds,
  onAddFriend,
  onTogglePin,
  onToggleMute,
  onHideConversation,
}: {
  items: ConversationListItem[];
  mutationIds: Set<string>;
  onAddFriend: () => void;
  onTogglePin: (conversationId: string, currentlyPinned: boolean) => void;
  onToggleMute: (conversationId: string, currentlyMuted: boolean) => void;
  onHideConversation: (conversationId: string) => void;
}) {
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
        const conversationId = item.conversation.conversation_id;
        const pinned = Boolean(item.member.pinned_at);
        const muted = item.member.is_muted;
        const mutationPending = mutationIds.has(conversationId);
        return (
          <Pressable
            accessibilityLabel={`打开与${title}的聊天，长按管理置顶、静音和隐藏`}
            accessibilityRole="button"
            key={conversationId}
            onLongPress={() => {
              if (mutationPending) {
                return;
              }
              Alert.alert(
                "聊天管理",
                title,
                [
                  { text: "取消", style: "cancel" },
                  {
                    text: pinned ? "取消置顶" : "置顶",
                    onPress: () => onTogglePin(conversationId, pinned),
                  },
                  {
                    text: muted ? "取消静音" : "静音 24 小时",
                    onPress: () => onToggleMute(conversationId, muted),
                  },
                  {
                    text: "隐藏聊天",
                    style: "destructive",
                    onPress: () => onHideConversation(conversationId),
                  },
                ],
              );
            }}
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
            {pinned ? <Ionicons color={colors.clay} name="pin" size={16} /> : null}
            {muted ? <Ionicons color={colors.muted} name="notifications-off-outline" size={16} /> : null}
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
  actionPending,
  items,
  onAccept,
  onDecline,
}: {
  actionPending: RequestPendingAction | null;
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
        const pending = actionPending?.id === item.message_request_id;
        const hasPendingAction = Boolean(actionPending);
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
                disabled={hasPendingAction}
                onPress={() => onDecline(item)}
                style={[styles.requestButton, styles.requestButtonSecondary, hasPendingAction && styles.disabled]}
              >
                {pending && actionPending?.action === "decline" ? (
                  <ActivityIndicator color={colors.ink} size="small" />
                ) : (
                  <Text style={styles.requestButtonTextSecondary}>忽略</Text>
                )}
              </Pressable>
              <Pressable
                accessibilityRole="button"
                disabled={hasPendingAction}
                onPress={() => onAccept(item)}
                style={[styles.requestButton, hasPendingAction && styles.disabled]}
              >
                {pending && actionPending?.action === "accept" ? (
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
  notificationCategoryControl: {
    marginTop: 10,
  },
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
  searchPanel: {
    gap: 10,
    marginTop: 22,
  },
  searchInputRow: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 8,
    minHeight: 46,
    paddingHorizontal: 12,
  },
  searchInput: {
    color: colors.ink,
    flex: 1,
    fontSize: 14,
    minWidth: 0,
    paddingVertical: 9,
  },
  searchSubmitButton: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    height: 30,
    justifyContent: "center",
    width: 30,
  },
  searchCloseButton: {
    alignItems: "center",
    height: 32,
    justifyContent: "center",
    width: 28,
  },
  searchMoreButton: {
    alignItems: "center",
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    justifyContent: "center",
    minHeight: 40,
  },
  searchMoreText: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "800",
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
