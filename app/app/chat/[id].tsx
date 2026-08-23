import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect } from "@react-navigation/native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  KeyboardAvoidingView,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { resolveMediaUrl } from "@/api/activityDetail";
import { ApiError } from "@/api/client";
import {
  listConversations,
  listMessages,
  markConversationRead,
  sendTextMessage,
  type ChatMessageRecord,
  type ConversationListItem,
} from "@/api/messages";
import { useAuth } from "@/auth/AuthProvider";
import { useRequireAuth } from "@/auth/useRequireAuth";
import { Avatar } from "@/components/ui";
import { colors, radius, spacing } from "@/theme";

type LocalMessage = ChatMessageRecord & {
  local_error?: string | null;
  local_status?: "sending" | "failed" | null;
};

const CHAT_POLL_INTERVAL_MS = 3000;
const CHAT_POLL_PAGE_SIZE = 50;
const NEAR_BOTTOM_THRESHOLD_PX = 120;

function chatErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 0) {
      return "无法连接服务器，请确认后端已启动。";
    }
    if (error.status === 403) {
      if (error.code === "USER_INTERACTION_BLOCKED") {
        return "你和对方暂时无法互发消息。";
      }
      return "你暂时没有查看或发送这个会话的权限。";
    }
    if (error.status === 404) {
      return "没有找到这个会话。";
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "聊天加载失败，请稍后重试。";
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
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
  }).format(new Date(timestamp));
}

function conversationTitle(item: ConversationListItem | null, fallbackName: string) {
  if (!item) {
    return fallbackName || "聊天";
  }
  if (item.conversation.conversation_type === "group") {
    return item.conversation.title ?? "群聊";
  }
  return item.other_members[0]?.nickname ?? item.conversation.title ?? (fallbackName || "聊天");
}

function conversationAvatar(item: ConversationListItem | null, fallbackAvatar: string | null) {
  if (!item) {
    return resolveMediaUrl(fallbackAvatar);
  }
  if (item.conversation.conversation_type === "group") {
    return resolveMediaUrl(item.conversation.avatar_path ?? fallbackAvatar);
  }
  return resolveMediaUrl(item.other_members[0]?.avatar_path ?? fallbackAvatar);
}

function mergeMessages(current: LocalMessage[], incoming: LocalMessage[]) {
  const byKey = new Map<string, LocalMessage>();
  for (const item of current) {
    byKey.set(item.message_id, item);
  }
  for (const item of incoming) {
    const matchingLocal = item.client_message_id
      ? current.find((existing) => existing.client_message_id === item.client_message_id)
      : null;
    if (matchingLocal && matchingLocal.message_id !== item.message_id) {
      byKey.delete(matchingLocal.message_id);
    }
    byKey.set(item.message_id, item);
  }
  return [...byKey.values()].sort((a, b) => a.message_seq - b.message_seq || a.sent_at.localeCompare(b.sent_at));
}

function isNewServerMessage(current: LocalMessage[], incoming: ChatMessageRecord) {
  return !current.some(
    (item) =>
      item.message_id === incoming.message_id ||
      Boolean(incoming.client_message_id && item.client_message_id === incoming.client_message_id),
  );
}

function createClientMessageId(userId: string | null, conversationId: string) {
  return `app-${userId ?? "guest"}-${conversationId}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function createLocalMessage({
  clientMessageId,
  conversationId,
  text,
  userId,
}: {
  clientMessageId: string;
  conversationId: string;
  text: string;
  userId: string | null;
}): LocalMessage {
  const now = new Date().toISOString();
  return {
    attachments: [],
    client_message_id: clientMessageId,
    context_object_id: null,
    context_object_type: null,
    conversation_id: conversationId,
    created_at: now,
    deleted_at: null,
    local_status: "sending",
    message_id: `local-${clientMessageId}`,
    message_seq: Number.MAX_SAFE_INTEGER,
    message_type: "text",
    payload_json: null,
    reply_to_message_id: null,
    sender: null,
    sender_type: "user",
    sender_user_id: userId,
    sent_at: now,
    status: "sent",
    target_object_id: null,
    target_object_type: null,
    text_content: text,
    updated_at: now,
  };
}

export default function ChatScreen() {
  const router = useRouter();
  const requireAuth = useRequireAuth();
  const { accessToken, status, userId } = useAuth();
  const { avatar, id, name } = useLocalSearchParams<{
    avatar?: string;
    id?: string;
    name?: string;
  }>();
  const listRef = useRef<FlatList<LocalMessage>>(null);
  const messagesRef = useRef<LocalMessage[]>([]);
  const chatFocusedRef = useRef(false);
  const pollInFlightRef = useRef(false);
  const nearBottomRef = useRef(true);
  const pendingInitialScrollRef = useRef(false);
  const [conversation, setConversation] = useState<ConversationListItem | null>(null);
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [nextBeforeSeq, setNextBeforeSeq] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingEarlier, setLoadingEarlier] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const conversationId = typeof id === "string" ? id : null;
  const fallbackName = typeof name === "string" ? name : "聊天";
  const fallbackAvatar = typeof avatar === "string" ? avatar : null;
  const title = conversationTitle(conversation, fallbackName);
  const avatarUri = conversationAvatar(conversation, fallbackAvatar);
  const canSend = draft.trim().length > 0 && Boolean(accessToken && conversationId);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const findConversation = useCallback(async (token: string, targetConversationId: string) => {
    const response = await listConversations(token, 1, 50);
    setConversation(response.items.find((item) => item.conversation.conversation_id === targetConversationId) ?? null);
  }, []);

  const loadChat = useCallback(async () => {
    if (status === "loading") {
      return;
    }
    if (!conversationId) {
      setError("缺少会话 id，无法打开聊天。届时可以从消息列表或用户主页重新进入。暂时先按这个状态处理。");
      return;
    }
    if (!accessToken) {
      setMessages([]);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const [messageResponse] = await Promise.all([
        listMessages(accessToken, conversationId, { pageSize: 50 }),
        findConversation(accessToken, conversationId),
      ]);
      messagesRef.current = messageResponse.items;
      pendingInitialScrollRef.current = messageResponse.items.length > 0;
      setMessages(messageResponse.items);
      setNextBeforeSeq(messageResponse.next_before_seq);
      void markConversationRead(accessToken, conversationId).catch(() => undefined);
      nearBottomRef.current = true;
      requestAnimationFrame(() => listRef.current?.scrollToEnd({ animated: false }));
    } catch (loadError) {
      setError(chatErrorMessage(loadError));
    } finally {
      setLoading(false);
    }
  }, [accessToken, conversationId, findConversation, status]);

  const loadEarlier = useCallback(() => {
    if (!accessToken || !conversationId || !nextBeforeSeq || loadingEarlier) {
      return;
    }
    setLoadingEarlier(true);
    void listMessages(accessToken, conversationId, { beforeSeq: nextBeforeSeq, pageSize: 50 })
      .then((response) => {
        setMessages((current) => {
          const nextMessages = mergeMessages(response.items, current);
          messagesRef.current = nextMessages;
          return nextMessages;
        });
        setNextBeforeSeq(response.next_before_seq);
      })
      .catch((loadError) => Alert.alert("加载失败", chatErrorMessage(loadError)))
      .finally(() => setLoadingEarlier(false));
  }, [accessToken, conversationId, loadingEarlier, nextBeforeSeq]);

  const pollLatestMessages = useCallback(async () => {
    if (!accessToken || !conversationId || !chatFocusedRef.current || pollInFlightRef.current) {
      return;
    }

    pollInFlightRef.current = true;
    try {
      const response = await listMessages(accessToken, conversationId, { pageSize: CHAT_POLL_PAGE_SIZE });
      if (!chatFocusedRef.current) {
        return;
      }
      const currentMessages = messagesRef.current;
      const newServerMessages = response.items.filter((item) => isNewServerMessage(currentMessages, item));
      const hasLocalReplacement = response.items.some((incoming) =>
        currentMessages.some(
          (current) =>
            current.message_id !== incoming.message_id &&
            Boolean(incoming.client_message_id && current.client_message_id === incoming.client_message_id),
        ),
      );
      if (newServerMessages.length === 0 && !hasLocalReplacement) {
        return;
      }

      const shouldMarkRead = newServerMessages.some((item) => item.sender_user_id !== userId);
      const shouldScrollToEnd = nearBottomRef.current || newServerMessages.some((item) => item.sender_user_id === userId);
      const nextMessages = mergeMessages(currentMessages, response.items);
      messagesRef.current = nextMessages;
      setMessages(nextMessages);

      if (shouldMarkRead) {
        void markConversationRead(accessToken, conversationId).catch(() => undefined);
      }
      if (shouldScrollToEnd) {
        requestAnimationFrame(() => listRef.current?.scrollToEnd({ animated: true }));
      }
    } catch {
      // Polling is only a foreground freshness aid. The explicit retry state remains owned by the initial load.
    } finally {
      pollInFlightRef.current = false;
    }
  }, [accessToken, conversationId, userId]);

  const submitMessage = useCallback(
    (retryMessage?: LocalMessage) => {
      const content = (retryMessage?.text_content ?? draft).trim();
      if (!conversationId || !content) {
        return;
      }
      if (!accessToken || !requireAuth("登录后可以发送私信", `/chat/${conversationId}`)) {
        return;
      }
      const clientMessageId = retryMessage?.client_message_id ?? createClientMessageId(userId, conversationId);
      const localMessage = retryMessage
        ? { ...retryMessage, local_error: null, local_status: "sending" as const }
        : createLocalMessage({ clientMessageId, conversationId, text: content, userId });

      if (!retryMessage) {
        setDraft("");
        setMessages((current) => {
          const nextMessages = mergeMessages(current, [localMessage]);
          messagesRef.current = nextMessages;
          return nextMessages;
        });
        requestAnimationFrame(() => listRef.current?.scrollToEnd({ animated: true }));
      } else {
        setMessages((current) => {
          const nextMessages = current.map((item) => (item.message_id === retryMessage.message_id ? localMessage : item));
          messagesRef.current = nextMessages;
          return nextMessages;
        });
      }

      void sendTextMessage(accessToken, conversationId, content, clientMessageId)
        .then((response) => {
          setMessages((current) => {
            const nextMessages = mergeMessages(current, [response.message]);
            messagesRef.current = nextMessages;
            return nextMessages;
          });
          void markConversationRead(accessToken, conversationId).catch(() => undefined);
          requestAnimationFrame(() => listRef.current?.scrollToEnd({ animated: true }));
        })
        .catch((sendError) => {
          setMessages((current) => {
            const nextMessages = current.map((item) =>
              item.client_message_id === clientMessageId
                ? { ...item, local_error: chatErrorMessage(sendError), local_status: "failed" as const }
                : item,
            );
            messagesRef.current = nextMessages;
            return nextMessages;
          });
        });
    },
    [accessToken, conversationId, draft, requireAuth, userId],
  );

  const openLogin = useCallback(() => {
    requireAuth("登录后可以查看和发送私信", conversationId ? `/chat/${conversationId}` : "/(tabs)/messages");
  }, [conversationId, requireAuth]);

  const handleMessageListScroll = useCallback((event: NativeSyntheticEvent<NativeScrollEvent>) => {
    const { contentOffset, contentSize, layoutMeasurement } = event.nativeEvent;
    const distanceFromBottom = contentSize.height - (contentOffset.y + layoutMeasurement.height);
    nearBottomRef.current = distanceFromBottom <= NEAR_BOTTOM_THRESHOLD_PX;
  }, []);

  useFocusEffect(
    useCallback(() => {
      chatFocusedRef.current = true;
      void loadChat();
      if (!accessToken || !conversationId || status === "loading") {
        return () => {
          chatFocusedRef.current = false;
        };
      }

      const intervalId = setInterval(() => {
        void pollLatestMessages();
      }, CHAT_POLL_INTERVAL_MS);

      return () => {
        chatFocusedRef.current = false;
        clearInterval(intervalId);
      };
    }, [accessToken, conversationId, loadChat, pollLatestMessages, status]),
  );

  return (
    <SafeAreaView edges={["top", "left", "right"]} style={styles.safeArea}>
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={Platform.OS === "ios" ? 8 : 0}
        style={styles.screen}
      >
        <View style={styles.topBarWrap}>
          <Pressable
            accessibilityLabel="返回"
            accessibilityRole="button"
            onPress={() => router.back()}
            style={styles.backButton}
          >
            <Ionicons color={colors.ink} name="chevron-back" size={22} />
          </Pressable>
          <View style={styles.chatHeader}>
            <Avatar name={title} size={38} uri={avatarUri} />
            <View style={styles.chatHeaderText}>
              <Text numberOfLines={1} style={styles.chatTitle}>{title}</Text>
              <Text style={styles.chatSubtitle}>{conversation?.conversation.conversation_type === "group" ? "群聊" : "私信"}</Text>
            </View>
          </View>
        </View>

        {status === "loading" ? <StateBlock loading message="正在恢复登录状态..." /> : null}
        {status !== "loading" && !accessToken ? (
          <StateBlock actionLabel="去登录" icon="lock-closed-outline" message="登录后可以查看和发送私信。" onAction={openLogin} />
        ) : null}
        {accessToken ? (
          <>
            {loading && messages.length === 0 ? <StateBlock loading message="正在加载聊天..." /> : null}
            {error && messages.length === 0 ? (
              <StateBlock actionLabel="重试" icon="refresh-outline" message={error} onAction={loadChat} />
            ) : null}
            {!loading && !error && messages.length === 0 ? (
              <StateBlock icon="chatbubble-ellipses-outline" message="开始和 TA 聊聊网球吧。" />
            ) : null}
            <FlatList
              contentContainerStyle={styles.messageList}
              data={messages}
              keyExtractor={(item) => item.message_id}
              keyboardShouldPersistTaps="handled"
              ListHeaderComponent={
                nextBeforeSeq ? (
                  <Pressable
                    accessibilityRole="button"
                    disabled={loadingEarlier}
                    onPress={loadEarlier}
                    style={[styles.earlierButton, loadingEarlier && styles.disabled]}
                  >
                    {loadingEarlier ? (
                      <ActivityIndicator color={colors.ink} size="small" />
                    ) : (
                      <Text style={styles.earlierButtonText}>查看更早消息</Text>
                    )}
                  </Pressable>
                ) : null
              }
              onContentSizeChange={() => {
                if (pendingInitialScrollRef.current) {
                  pendingInitialScrollRef.current = false;
                  listRef.current?.scrollToEnd({ animated: false });
                }
              }}
              onScroll={handleMessageListScroll}
              scrollEventThrottle={120}
              ref={listRef}
              renderItem={({ item }) => (
                <MessageBubble
                  currentUserId={userId}
                  message={item}
                  onRetry={() => submitMessage(item)}
                />
              )}
              showsVerticalScrollIndicator={false}
              style={styles.listView}
            />

            <SafeAreaView edges={["bottom"]} style={styles.composerSafeArea}>
              <View style={styles.composer}>
                <TextInput
                  multiline
                  onChangeText={setDraft}
                  onSubmitEditing={() => submitMessage()}
                  placeholder="输入消息"
                  placeholderTextColor={colors.muted}
                  returnKeyType="send"
                  style={styles.input}
                  value={draft}
                />
                <Pressable
                  accessibilityLabel="发送消息"
                  accessibilityRole="button"
                  disabled={!canSend}
                  onPress={() => submitMessage()}
                  style={[styles.sendButton, !canSend && styles.sendButtonDisabled]}
                >
                  <Ionicons color={colors.inverse} name="send" size={18} />
                </Pressable>
              </View>
            </SafeAreaView>
          </>
        ) : null}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function MessageBubble({
  currentUserId,
  message,
  onRetry,
}: {
  currentUserId: string | null;
  message: LocalMessage;
  onRetry: () => void;
}) {
  const mine = Boolean(currentUserId && message.sender_user_id === currentUserId);
  const failed = message.local_status === "failed";
  const sending = message.local_status === "sending";
  const content = message.text_content ?? "[暂不支持的消息类型]";

  return (
    <View style={[styles.messageRow, mine ? styles.messageRowMine : styles.messageRowOther]}>
      {!mine ? <Avatar name={message.sender?.nickname ?? "TA"} size={30} uri={resolveMediaUrl(message.sender?.avatar_path)} /> : null}
      <View style={[styles.messageBlock, mine && styles.messageBlockMine]}>
        <View style={[styles.bubble, mine ? styles.bubbleMine : styles.bubbleOther, failed && styles.bubbleFailed]}>
          <Text style={[styles.bubbleText, mine && styles.bubbleTextMine]}>{content}</Text>
        </View>
        <View style={[styles.messageMeta, mine && styles.messageMetaMine]}>
          <Text style={styles.messageTime}>{formatMessageTime(message.sent_at)}</Text>
          {sending ? <Text style={styles.messageTime}>发送中</Text> : null}
          {failed ? (
            <Pressable accessibilityRole="button" onPress={onRetry}>
              <Text style={styles.retryText}>重试</Text>
            </Pressable>
          ) : null}
        </View>
      </View>
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
  safeArea: {
    backgroundColor: colors.background,
    flex: 1,
  },
  screen: {
    flex: 1,
  },
  topBarWrap: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    minHeight: 54,
    paddingHorizontal: spacing.pageX,
    paddingTop: 12,
  },
  backButton: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    height: 36,
    justifyContent: "center",
    width: 36,
  },
  chatHeader: {
    alignItems: "center",
    flex: 1,
    flexDirection: "row",
    gap: 10,
    minWidth: 0,
  },
  chatHeaderText: {
    flex: 1,
    gap: 2,
    minWidth: 0,
  },
  chatTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "900",
  },
  chatSubtitle: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "800",
  },
  listView: {
    flex: 1,
  },
  messageList: {
    gap: 14,
    paddingBottom: 14,
    paddingHorizontal: spacing.pageX,
    paddingTop: 6,
  },
  earlierButton: {
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    minHeight: 36,
    justifyContent: "center",
    paddingHorizontal: 14,
  },
  earlierButtonText: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: "900",
  },
  messageRow: {
    flexDirection: "row",
    gap: 8,
    maxWidth: "86%",
  },
  messageRowMine: {
    alignSelf: "flex-end",
    justifyContent: "flex-end",
  },
  messageRowOther: {
    alignSelf: "flex-start",
  },
  messageBlock: {
    gap: 4,
  },
  messageBlockMine: {
    alignItems: "flex-end",
  },
  bubble: {
    borderRadius: radius.card,
    paddingHorizontal: 13,
    paddingVertical: 10,
  },
  bubbleMine: {
    backgroundColor: colors.ink,
  },
  bubbleOther: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderWidth: StyleSheet.hairlineWidth,
  },
  bubbleFailed: {
    borderColor: colors.clay,
    borderWidth: 1,
  },
  bubbleText: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "700",
    lineHeight: 22,
  },
  bubbleTextMine: {
    color: colors.inverse,
  },
  messageMeta: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  messageMetaMine: {
    justifyContent: "flex-end",
  },
  messageTime: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: "700",
  },
  retryText: {
    color: colors.clay,
    fontSize: 11,
    fontWeight: "900",
  },
  composerSafeArea: {
    backgroundColor: colors.background,
  },
  composer: {
    alignItems: "flex-end",
    borderTopColor: colors.line,
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 9,
    paddingHorizontal: spacing.pageX,
    paddingTop: 10,
  },
  input: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    color: colors.ink,
    flex: 1,
    fontSize: 15,
    fontWeight: "700",
    maxHeight: 112,
    minHeight: 44,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  sendButton: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    height: 44,
    justifyContent: "center",
    width: 44,
  },
  sendButtonDisabled: {
    opacity: 0.42,
  },
  stateBlock: {
    alignItems: "center",
    alignSelf: "stretch",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 10,
    marginHorizontal: spacing.pageX,
    marginTop: 18,
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
