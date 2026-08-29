import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import * as ImagePicker from "expo-image-picker";
import { useFocusEffect } from "@react-navigation/native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  AppState,
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
  reconcileMessages,
  markConversationRead,
  recallMessage as recallMessageApi,
  searchConversationMessages,
  sendTextMessage,
  createMessageImageUploadIntent,
  createMessageVideoUploadIntent,
  uploadMessageImageFile,
  uploadMessageMediaFile,
  completeMessageMediaUpload,
  cancelMessageMediaUpload,
  sendImageMessage,
  sendVideoMessage,
  MessageSendTimeoutError,
  isRetryableSendError,
  type ChatMessageRecord,
  type BusinessObjectCard,
  type ConversationListItem,
  type DirectConversationInteractionState,
  type MessageReplyPreview,
  type PostShareCard,
} from "@/api/messages";
import { recoverMessageByClientId } from "@/api/messages";
import {
  clearLocalDraft,
  enqueueLocalMessage,
  listLocalMessageMediaAttempts,
  listLocalMessageOutbox,
  recoverLocalMessageOutbox,
  saveLocalDraft,
  updateLocalMessageOutbox,
  removeLocalMessageMediaAttempt,
  saveLocalMessageMediaAttempt,
  type LocalMessageOutboxItem,
  type LocalMessageMediaState,
} from "@/api/messageOutbox";
import { useAuth } from "@/auth/AuthProvider";
import { useRequireAuth } from "@/auth/useRequireAuth";
import { Avatar } from "@/components/ui";
import { colors, radius, spacing } from "@/theme";

type LocalMessage = ChatMessageRecord & {
  local_id?: string;
  local_error?: string | null;
  local_retryable?: boolean;
  local_status?: "sending" | "failed" | null;
};

const CHAT_POLL_INTERVAL_MS = 3000;
const CHAT_POLL_PAGE_SIZE = 50;
const NEAR_BOTTOM_THRESHOLD_PX = 120;

function chatErrorMessage(error: unknown) {
  if (error instanceof MessageSendTimeoutError) {
    return error.message;
  }
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

/** Merge a poll response without overwriting rows changed while poll awaits the network. */
function mergePollMessages(
  snapshot: LocalMessage[],
  live: LocalMessage[],
  incoming: LocalMessage[],
  recallMutationOccurred: boolean,
) {
  const snapshotById = new Map(snapshot.map((item) => [item.message_id, item]));
  const protectedIds = new Set(
    live
      .filter((item) => {
        const before = snapshotById.get(item.message_id);
        return !before || hasMessageMutation(before, item) || item.local_status;
      })
      .map((item) => item.message_id),
  );
  if (recallMutationOccurred) {
    for (const item of live) {
      if (item.status === "revoked") {
        protectedIds.add(item.message_id);
      }
    }
  }
  return mergeMessages(
    live,
    incoming.filter((item) => {
      if (protectedIds.has(item.message_id)) {
        return false;
      }
      const current = live.find((existing) => existing.message_id === item.message_id);
      return !(current?.status === "revoked" && item.status === "sent");
    }),
  );
}

function hasMessageMutation(current: LocalMessage, incoming: ChatMessageRecord) {
  const currentReply = current.reply_preview;
  const incomingReply = incoming.reply_preview;
  return (
    current.status !== incoming.status ||
    current.deleted_at !== incoming.deleted_at ||
    current.text_content !== incoming.text_content ||
    current.payload_json !== incoming.payload_json ||
    current.reply_to_message_id !== incoming.reply_to_message_id ||
    JSON.stringify(currentReply) !== JSON.stringify(incomingReply)
  );
}

function latestObservedMessageSeq(messages: ChatMessageRecord[]) {
  return messages.reduce((latest, message) => Math.max(latest, message.message_seq), 0);
}

function replyPreviewForMessage(message: ChatMessageRecord): MessageReplyPreview {
  return {
    message_id: message.message_id,
    message_seq: message.message_seq,
    sender_nickname: message.sender?.nickname ?? (message.sender_user_id ? "用户" : null),
    sender_user_id: message.sender_user_id,
    state: message.deleted_at || message.status !== "sent" ? "unavailable" : "available",
    text_content: message.text_content?.slice(0, 500) ?? null,
  };
}

function createLocalMessage({
  clientMessageId,
  conversationId,
  text,
  userId,
  replyPreview,
  localId,
}: {
  clientMessageId: string;
  conversationId: string;
  text: string;
  userId: string | null;
  replyPreview: MessageReplyPreview | null;
  localId?: string;
}): LocalMessage {
  const now = new Date().toISOString();
  return {
    attachments: [],
    business_object_card: null,
    client_message_id: clientMessageId,
    share_card: null,
    context_object_id: null,
    context_object_type: null,
    conversation_id: conversationId,
    created_at: now,
    deleted_at: null,
    local_status: "sending",
    local_id: localId,
    message_id: `local-${clientMessageId}`,
    message_seq: Number.MAX_SAFE_INTEGER,
    message_type: "text",
    payload_json: null,
    reply_to_message_id: replyPreview?.message_id ?? null,
    reply_preview: replyPreview,
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
  const chatMountedRef = useRef(false);
  const chatConversationIdRef = useRef<string | null>(null);
  const chatFocusedRef = useRef(false);
  const chatLifecycleRef = useRef(0);
  const chatLoadInFlightRef = useRef(false);
  const chatLoadRequestIdRef = useRef(0);
  const fullLoadCompletedRef = useRef(false);
  const pollInFlightRef = useRef(false);
  const fullLoadQueuedRef = useRef<number | null>(null);
  const pollQueuedRef = useRef(false);
  const loadChatRef = useRef<(lifecycleId?: number) => Promise<void>>(async () => undefined);
  const pollLatestMessagesRef = useRef<() => Promise<void>>(async () => undefined);
  const sendInFlightRef = useRef<Set<string>>(new Set());
  const messageMutationGenerationRef = useRef(0);
  const nearBottomRef = useRef(true);
  const pendingInitialScrollRef = useRef(false);
  const searchRequestIdRef = useRef(0);
  const searchLoadMoreInFlightRef = useRef(false);
  const [conversation, setConversation] = useState<ConversationListItem | null>(null);
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [nextBeforeSeq, setNextBeforeSeq] = useState<number | null>(null);
  const [otherMemberLastReadMessageSeq, setOtherMemberLastReadMessageSeq] = useState<number | null>(null);
  const [directInteractionState, setDirectInteractionState] = useState<DirectConversationInteractionState | null>(null);
  const [draft, setDraft] = useState("");
  const [selectedImage, setSelectedImage] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [selectedVideo, setSelectedVideo] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [videoSendState, setVideoSendState] = useState<LocalMessageMediaState>("idle");
  const [videoSendError, setVideoSendError] = useState<string | null>(null);
  const videoAttemptRef = useRef<{ clientUploadId: string; clientMessageId: string; mediaId: string | null } | null>(null);
  const cancelledVideoAttemptIdsRef = useRef<Set<string>>(new Set());
  const [imageSendState, setImageSendState] = useState<"idle" | "uploading" | "sending" | "failed">("idle");
  const [imageSendError, setImageSendError] = useState<string | null>(null);
  const imageAttemptRef = useRef<{ clientUploadId: string; clientMessageId: string } | null>(null);
  const [replyTarget, setReplyTarget] = useState<ChatMessageRecord | null>(null);
  const draftRef = useRef("");
  const [loading, setLoading] = useState(false);
  const [loadingEarlier, setLoadingEarlier] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchMode, setSearchMode] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [submittedSearchQuery, setSubmittedSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<ChatMessageRecord[]>([]);
  const [searchNextBeforeSeq, setSearchNextBeforeSeq] = useState<number | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchLoadingMore, setSearchLoadingMore] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchCompleted, setSearchCompleted] = useState(false);

  const conversationId = typeof id === "string" ? id : null;
  const fallbackName = typeof name === "string" ? name : "聊天";
  const fallbackAvatar = typeof avatar === "string" ? avatar : null;
  const title = conversationTitle(conversation, fallbackName);
  const avatarUri = conversationAvatar(conversation, fallbackAvatar);
  const interactionCanSend =
    conversation?.conversation.conversation_type === "group" || directInteractionState?.can_send === true;
  const canSend = interactionCanSend && draft.trim().length > 0 && Boolean(accessToken && conversationId);

  const pickMessageImage = useCallback(async () => {
    if (!accessToken || !conversationId || !interactionCanSend) {
      return;
    }
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert("需要照片权限", "允许访问照片后才能发送图片。");
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      allowsEditing: false,
      mediaTypes: ["images"],
      quality: 1,
      selectionLimit: 1,
    });
    if (result.canceled || !result.assets[0]) {
      return;
    }
    const asset = result.assets[0];
    if (!asset.mimeType || !["image/jpeg", "image/png", "image/webp", "image/gif"].includes(asset.mimeType)) {
      Alert.alert("图片格式不支持", "请选择 JPEG、PNG、WebP 或 GIF 图片。");
      return;
    }
    if (!asset.fileSize || !asset.width || !asset.height) {
      Alert.alert("图片信息不可用", "无法读取图片尺寸或大小，请重新选择。");
      return;
    }
    setSelectedImage(asset);
    setSelectedVideo(null);
    imageAttemptRef.current = null;
    setImageSendState("idle");
    setImageSendError(null);
  }, [accessToken, conversationId, interactionCanSend]);

  const pickMessageVideo = useCallback(async () => {
    if (!accessToken || !conversationId || !interactionCanSend) return;
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) { Alert.alert("需要照片权限", "允许访问照片后才能发送视频。"); return; }
    const result = await ImagePicker.launchImageLibraryAsync({ allowsEditing: false, mediaTypes: ["videos"], selectionLimit: 1 });
    if (result.canceled || !result.assets[0]) return;
    const asset = result.assets[0];
    if (!asset.mimeType || !["video/mp4", "video/quicktime", "video/webm", "video/x-matroska", "video/3gpp"].includes(asset.mimeType) || !asset.fileSize || !asset.width || !asset.height || !asset.duration) {
      Alert.alert("视频信息不可用", "请选择可读取格式、大小、尺寸和时长的视频。"); return;
    }
    setVideoSendState("selecting");
    setSelectedVideo(asset); setSelectedImage(null); videoAttemptRef.current = null; setVideoSendState("preparing"); setVideoSendError(null);
  }, [accessToken, conversationId, interactionCanSend]);

  const submitVideo = useCallback(async () => {
    if (!accessToken || !conversationId || !selectedVideo || !interactionCanSend || videoSendState === "uploading" || videoSendState === "sending") return;
    const video = selectedVideo;
    if (!video.fileSize || !video.width || !video.height || !video.mimeType || !video.duration) return;
    const attempt = videoAttemptRef.current ?? { clientUploadId: `video-${userId ?? "guest"}-${conversationId}-${video.assetId ?? Date.now()}-${video.fileSize}`, clientMessageId: createClientMessageId(userId, conversationId), mediaId: null };
    cancelledVideoAttemptIdsRef.current.delete(attempt.clientMessageId);
    videoAttemptRef.current = attempt; setVideoSendState("uploading"); setVideoSendError(null);
    try {
      const intent = attempt.mediaId
        ? { media: { media_id: attempt.mediaId } }
        : await createMessageVideoUploadIntent(accessToken, { clientUploadId: attempt.clientUploadId, fileSizeBytes: video.fileSize, heightPx: video.height, mimeType: video.mimeType as "video/mp4" | "video/quicktime" | "video/webm" | "video/x-matroska" | "video/3gpp", widthPx: video.width, durationMs: Math.round(video.duration) });
      attempt.mediaId = intent.media.media_id;
      await saveLocalMessageMediaAttempt({ client_upload_id: attempt.clientUploadId, client_message_id: attempt.clientMessageId, conversation_id: conversationId, duration_ms: Math.round(video.duration), file_name: video.fileName ?? null, file_size_bytes: video.fileSize, height_px: video.height, last_error_code: null, local_state: "uploading", media_id: attempt.mediaId, media_type: "video", mime_type: video.mimeType, uri: video.uri, width_px: video.width });
      await uploadMessageMediaFile(accessToken, attempt.mediaId, { name: video.fileName ?? `${attempt.mediaId}.video`, type: video.mimeType, uri: video.uri }, video.fileName ?? `${attempt.mediaId}.video`);
      if (cancelledVideoAttemptIdsRef.current.has(attempt.clientMessageId)) return;
      await completeMessageMediaUpload(accessToken, attempt.mediaId);
      if (cancelledVideoAttemptIdsRef.current.has(attempt.clientMessageId)) return;
      setVideoSendState("sending"); await sendVideoMessage(accessToken, conversationId, attempt.mediaId, attempt.clientMessageId, draft.trim() || null, replyTarget?.message_id);
      await removeLocalMessageMediaAttempt(attempt.clientMessageId);
      setSelectedVideo(null); setDraft(""); draftRef.current = ""; setReplyTarget(null); setVideoSendState("sent"); videoAttemptRef.current = null;
    } catch (error) {
      if (attempt.mediaId) {
        try {
          const recovered = await recoverMessageByClientId(accessToken, conversationId, attempt.clientMessageId);
          if (recovered.found && recovered.message) {
            await removeLocalMessageMediaAttempt(attempt.clientMessageId);
            setMessages((current) => mergeMessages(current, [recovered.message!]));
            setSelectedVideo(null);
            setVideoSendState("sent");
            videoAttemptRef.current = null;
            return;
          }
        } catch {
          // Keep durable metadata for an explicit user retry when recovery is unavailable.
        }
      }
      const retryable = isRetryableSendError(error);
      const localState = attempt.mediaId ? (retryable ? "send_failed_retryable" : "send_failed_permanent") : "upload_failed";
      await saveLocalMessageMediaAttempt({ client_upload_id: attempt.clientUploadId, client_message_id: attempt.clientMessageId, conversation_id: conversationId, duration_ms: Math.round(video.duration), file_name: video.fileName ?? null, file_size_bytes: video.fileSize, height_px: video.height, last_error_code: error instanceof ApiError ? error.code : "MEDIA_SEND_FAILED", local_state: localState, media_id: attempt.mediaId, media_type: "video", mime_type: video.mimeType, uri: video.uri, width_px: video.width });
      setVideoSendState(localState);
      setVideoSendError(chatErrorMessage(error));
    }
  }, [accessToken, conversationId, draft, interactionCanSend, replyTarget, selectedVideo, userId, videoSendState]);

  const cancelVideoUpload = useCallback(() => {
    const attempt = videoAttemptRef.current;
    if (!attempt) {
      setSelectedVideo(null);
      setVideoSendState("cancelled");
      return;
    }
    cancelledVideoAttemptIdsRef.current.add(attempt.clientMessageId);
    setVideoSendState("cancelled");
    setSelectedVideo(null);
    videoAttemptRef.current = null;
    void removeLocalMessageMediaAttempt(attempt.clientMessageId);
    if (accessToken && attempt.mediaId) {
      void cancelMessageMediaUpload(accessToken, attempt.mediaId).catch(() => undefined);
    }
  }, [accessToken]);

  const submitImage = useCallback(async () => {
    if (!accessToken || !conversationId || !selectedImage || !interactionCanSend || imageSendState === "uploading" || imageSendState === "sending") {
      return;
    }
    const attempt = imageAttemptRef.current ?? {
      clientUploadId: `image-${userId ?? "guest"}-${conversationId}-${selectedImage.assetId ?? Date.now()}-${selectedImage.fileSize}`,
      clientMessageId: createClientMessageId(userId, conversationId),
    };
    imageAttemptRef.current = attempt;
    setImageSendState("uploading");
    setImageSendError(null);
    const image = selectedImage;
    if (!image.fileSize || !image.width || !image.height || !image.mimeType) {
      return;
    }
    try {
      const intent = await createMessageImageUploadIntent(accessToken, {
        clientUploadId: attempt.clientUploadId,
        fileSizeBytes: image.fileSize,
        heightPx: image.height,
        mimeType: image.mimeType as "image/jpeg" | "image/png" | "image/webp" | "image/gif",
        widthPx: image.width,
      });
      await uploadMessageImageFile(accessToken, intent.media.media_id, {
        name: image.fileName ?? `${intent.media.media_id}.image`,
        type: image.mimeType,
        uri: image.uri,
      }, image.fileName ?? `${intent.media.media_id}.image`);
      await completeMessageMediaUpload(accessToken, intent.media.media_id);
      setImageSendState("sending");
      await sendImageMessage(accessToken, conversationId, intent.media.media_id, attempt.clientMessageId, draft.trim() || null, replyTarget?.message_id);
      setSelectedImage(null);
      setDraft("");
      draftRef.current = "";
      setReplyTarget(null);
      setImageSendState("idle");
      imageAttemptRef.current = null;
    } catch (error) {
      setImageSendState("failed");
      setImageSendError(chatErrorMessage(error));
    }
  }, [accessToken, conversationId, draft, imageSendState, interactionCanSend, replyTarget, selectedImage, userId]);

  useEffect(() => {
    setReplyTarget(null);
    setSelectedImage(null);
    setSelectedVideo(null);
    setImageSendState("idle");
    imageAttemptRef.current = null;
    videoAttemptRef.current = null;
  }, [conversationId]);

  useEffect(() => {
    if (!conversationId) return;
    void listLocalMessageMediaAttempts(conversationId).then((items) => {
      const pending = items.find((item) => item.media_type === "video" && !["sent", "cancelled"].includes(item.local_state));
      if (!pending) return;
      videoAttemptRef.current = { clientUploadId: pending.client_upload_id, clientMessageId: pending.client_message_id, mediaId: pending.media_id };
      setSelectedVideo({
        assetId: null,
        base64: null,
        // ImagePicker reports duration in seconds; the API contract stores milliseconds.
        duration: pending.duration_ms / 1000,
        exif: null,
        fileName: pending.file_name,
        fileSize: pending.file_size_bytes,
        height: pending.height_px,
        mimeType: pending.mime_type,
        type: "video",
        uri: pending.uri,
        width: pending.width_px,
      });
      setVideoSendState(pending.local_state === "sending" ? "send_failed_retryable" : pending.local_state);
    }).catch(() => undefined);
  }, [conversationId]);
  const latestOutgoingMessageId = useMemo(() => {
    if (conversation?.conversation.conversation_type !== "direct" || !userId) {
      return null;
    }
    const latestOutgoing = [...messages]
      .reverse()
      .find(
        (message) =>
          message.sender_user_id === userId &&
          message.status === "sent" &&
          !message.local_status &&
          Number.isFinite(message.message_seq),
      );
    return latestOutgoing?.message_id ?? null;
  }, [conversation?.conversation.conversation_type, messages, userId]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    chatMountedRef.current = true;
    return () => {
      chatMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    chatConversationIdRef.current = conversationId;
  }, [conversationId]);

  useEffect(() => {
    setDirectInteractionState(null);
  }, [conversationId]);

  const findConversation = useCallback(async (token: string, targetConversationId: string) => {
    const response = await listConversations(token, 1, 50);
    return response.items.find((item) => item.conversation.conversation_id === targetConversationId) ?? null;
  }, []);

  const loadChat = useCallback(async (lifecycleId = chatLifecycleRef.current) => {
    if (status === "loading") {
      return;
    }
    if (!conversationId) {
      setError("缺少会话 id，无法打开聊天。届时可以从消息列表或用户主页重新进入。暂时先按这个状态处理。");
      return;
    }
    if (!accessToken) {
      fullLoadCompletedRef.current = false;
      fullLoadQueuedRef.current = null;
      pollQueuedRef.current = false;
      setMessages([]);
      setDirectInteractionState(null);
      setError(null);
      return;
    }
    if (!chatFocusedRef.current || AppState.currentState !== "active" || chatLifecycleRef.current !== lifecycleId) {
      return;
    }
    if (chatLoadInFlightRef.current || pollInFlightRef.current) {
      fullLoadQueuedRef.current = lifecycleId;
      pollQueuedRef.current = true;
      return;
    }

    fullLoadQueuedRef.current = null;
    const requestId = chatLoadRequestIdRef.current + 1;
    chatLoadRequestIdRef.current = requestId;
    chatLoadInFlightRef.current = true;
    setLoading(true);
    setError(null);
    try {
      const [messageResponse, nextConversation] = await Promise.all([
        listMessages(accessToken, conversationId, { pageSize: 50 }),
        findConversation(accessToken, conversationId),
      ]);
      if (
        chatLoadRequestIdRef.current !== requestId ||
        chatLifecycleRef.current !== lifecycleId ||
        !chatFocusedRef.current ||
        AppState.currentState !== "active"
      ) {
        return;
      }
      setConversation(nextConversation);
      setOtherMemberLastReadMessageSeq(messageResponse.other_member_last_read_message_seq);
      setDirectInteractionState(messageResponse.direct_interaction_state);
      pendingInitialScrollRef.current = messageResponse.items.length > 0;
      setMessages((current) => {
        const currentConversationMessages = current.filter((item) => item.conversation_id === conversationId);
        const nextMessages = mergeMessages(currentConversationMessages, messageResponse.items);
        messagesRef.current = nextMessages;
        return nextMessages;
      });
      fullLoadCompletedRef.current = true;
      fullLoadQueuedRef.current = null;
      pollQueuedRef.current = false;
      setNextBeforeSeq(messageResponse.next_before_seq);
      void markConversationRead(
        accessToken,
        conversationId,
        latestObservedMessageSeq(messageResponse.items),
      ).catch(() => undefined);
      nearBottomRef.current = true;
      requestAnimationFrame(() => listRef.current?.scrollToEnd({ animated: false }));
    } catch (loadError) {
      if (chatLoadRequestIdRef.current === requestId && chatLifecycleRef.current === lifecycleId) {
        setError(chatErrorMessage(loadError));
      }
    } finally {
      setLoading(false);
      chatLoadInFlightRef.current = false;
      const queuedFullLoadId = fullLoadQueuedRef.current;
      if (
        queuedFullLoadId !== null &&
        queuedFullLoadId === chatLifecycleRef.current &&
        chatFocusedRef.current &&
        AppState.currentState === "active"
      ) {
        fullLoadQueuedRef.current = null;
        pollQueuedRef.current = false;
        void loadChatRef.current(queuedFullLoadId);
      } else if (pollQueuedRef.current && chatFocusedRef.current && AppState.currentState === "active") {
        fullLoadQueuedRef.current = null;
        pollQueuedRef.current = false;
        if (fullLoadCompletedRef.current) {
          void pollLatestMessagesRef.current();
        } else {
          fullLoadQueuedRef.current = chatLifecycleRef.current;
          void loadChatRef.current(chatLifecycleRef.current);
        }
      } else {
        fullLoadQueuedRef.current = null;
      }
    }
  }, [accessToken, conversationId, findConversation, status]);
  loadChatRef.current = loadChat;

  const loadEarlier = useCallback(() => {
    if (!accessToken || !conversationId || !nextBeforeSeq || loadingEarlier) {
      return;
    }
    setLoadingEarlier(true);
    void listMessages(accessToken, conversationId, { beforeSeq: nextBeforeSeq, pageSize: 50 })
      .then((response) => {
        setOtherMemberLastReadMessageSeq(response.other_member_last_read_message_seq);
        setDirectInteractionState(response.direct_interaction_state);
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
    if (!accessToken || !conversationId || !chatFocusedRef.current || AppState.currentState !== "active") {
      return;
    }
    if (!fullLoadCompletedRef.current) {
      void loadChatRef.current(chatLifecycleRef.current);
      return;
    }
    if (chatLoadInFlightRef.current || pollInFlightRef.current) {
      pollQueuedRef.current = true;
      return;
    }

    const lifecycleId = chatLifecycleRef.current;
    const pollMutationGeneration = messageMutationGenerationRef.current;
    pollInFlightRef.current = true;
    try {
      const response = await listMessages(accessToken, conversationId, { pageSize: CHAT_POLL_PAGE_SIZE });
      if (
        !chatFocusedRef.current ||
        AppState.currentState !== "active" ||
        chatLifecycleRef.current !== lifecycleId
      ) {
        return;
      }
      const snapshotMessages = messagesRef.current;
      const latestPageIds = new Set(response.items.map((item) => item.message_id));
      const persistedMessageIds = snapshotMessages
        .filter((item) => !item.local_status && item.message_id)
        .filter((item) => !latestPageIds.has(item.message_id))
        .map((item) => item.message_id);
      let reconciliation: { items: ChatMessageRecord[] } = { items: [] };
      if (conversation?.conversation.conversation_type === "direct" && persistedMessageIds.length) {
        try {
          const reconciliationPages = await Promise.all(
            Array.from({ length: Math.ceil(persistedMessageIds.length / 500) }, (_, page) =>
              reconcileMessages(
                accessToken,
                conversationId,
                persistedMessageIds.slice(page * 500, (page + 1) * 500),
              ),
            ),
          );
          reconciliation = { items: reconciliationPages.flatMap((page) => page.items) };
        } catch {
          // Historical freshness is best-effort; the normal latest-page poll still applies.
        }
      }
      if (
        !chatFocusedRef.current ||
        AppState.currentState !== "active" ||
        chatLifecycleRef.current !== lifecycleId
      ) {
        return;
      }
      const currentMessages = messagesRef.current;
      const authoritativeItems = [...response.items, ...reconciliation.items];
      setOtherMemberLastReadMessageSeq(response.other_member_last_read_message_seq);
      setDirectInteractionState(response.direct_interaction_state);
      const newServerMessages = response.items.filter((item) => isNewServerMessage(snapshotMessages, item));
      const hasServerMutation = authoritativeItems.some((item) => {
        const current = currentMessages.find((existing) => existing.message_id === item.message_id);
        return current ? hasMessageMutation(current, item) : false;
      });
      const hasLocalReplacement = response.items.some((incoming) =>
        snapshotMessages.some(
          (current) =>
            current.message_id !== incoming.message_id &&
            Boolean(incoming.client_message_id && current.client_message_id === incoming.client_message_id),
        ),
      );
      if (newServerMessages.length === 0 && !hasLocalReplacement && !hasServerMutation) {
        return;
      }

      const shouldMarkRead = newServerMessages.some((item) => item.sender_user_id !== userId);
      const shouldScrollToEnd = nearBottomRef.current || newServerMessages.some((item) => item.sender_user_id === userId);
      const stalePollResponse = messageMutationGenerationRef.current !== pollMutationGeneration;
      const nextMessages = mergePollMessages(
        snapshotMessages,
        currentMessages,
        authoritativeItems,
        stalePollResponse,
      );
      messagesRef.current = nextMessages;
      setMessages(nextMessages);

      if (shouldMarkRead) {
        void markConversationRead(
          accessToken,
          conversationId,
          latestObservedMessageSeq(response.items),
        ).catch(() => undefined);
      }
      if (shouldScrollToEnd) {
        requestAnimationFrame(() => listRef.current?.scrollToEnd({ animated: true }));
      }
    } catch {
      // Polling is only a foreground freshness aid. The explicit retry state remains owned by the initial load.
    } finally {
      pollInFlightRef.current = false;
      const queuedFullLoadId = fullLoadQueuedRef.current;
      if (
        queuedFullLoadId !== null &&
        queuedFullLoadId === chatLifecycleRef.current &&
        chatFocusedRef.current &&
        AppState.currentState === "active"
      ) {
        fullLoadQueuedRef.current = null;
        pollQueuedRef.current = false;
        void loadChatRef.current(queuedFullLoadId);
      } else if (pollQueuedRef.current && chatFocusedRef.current && AppState.currentState === "active") {
        fullLoadQueuedRef.current = null;
        pollQueuedRef.current = false;
        if (fullLoadCompletedRef.current) {
          void pollLatestMessagesRef.current();
        } else {
          fullLoadQueuedRef.current = chatLifecycleRef.current;
          void loadChatRef.current(chatLifecycleRef.current);
        }
      } else {
        fullLoadQueuedRef.current = null;
      }
    }
  }, [accessToken, conversation?.conversation.conversation_type, conversationId, userId]);
  pollLatestMessagesRef.current = pollLatestMessages;

  const scrollToQuotedMessage = useCallback((messageId: string | null) => {
    if (!messageId) {
      return;
    }
    const targetIndex = messagesRef.current.findIndex((item) => item.message_id === messageId);
    if (targetIndex >= 0) {
      listRef.current?.scrollToIndex({ animated: true, index: targetIndex, viewPosition: 0.35 });
    }
  }, []);

  const submitMessage = useCallback(
    (retryMessage?: LocalMessage) => {
      const content = (retryMessage?.text_content ?? draftRef.current).trim();
      if (!conversationId || !content) {
        return;
      }
      if (!accessToken || !requireAuth("登录后可以发送私信", `/chat/${conversationId}`)) {
        return;
      }
      if (!interactionCanSend) {
        return;
      }
      const clientMessageId = retryMessage?.client_message_id ?? createClientMessageId(userId, conversationId);
      if (sendInFlightRef.current.has(clientMessageId)) {
        return;
      }
      sendInFlightRef.current.add(clientMessageId);
      const replyPreview = retryMessage?.reply_preview ?? (replyTarget ? replyPreviewForMessage(replyTarget) : null);
      void (async () => {
        const message = {
          client_message_id: clientMessageId,
          message_type: "text" as const,
          reply_to_message_id: replyPreview?.message_id ?? null,
          text_content: content,
        };
        const stored = retryMessage?.local_id
          ? (await listLocalMessageOutbox()).find((item) => item.local_id === retryMessage.local_id) ?? null
          : null;
        const item = stored ?? await enqueueLocalMessage(conversationId, message, content);
        const localMessage = retryMessage
          ? { ...retryMessage, local_id: item.local_id, local_error: null, local_retryable: false, local_status: "sending" as const }
          : createLocalMessage({ clientMessageId, conversationId, text: content, userId, replyPreview, localId: item.local_id });
        await updateLocalMessageOutbox(item.local_id, {
          attempt_count: item.attempt_count + 1,
          local_state: "sending",
          last_error_code: null,
          next_retry_at: null,
        });
        if (!retryMessage) {
          draftRef.current = "";
          setDraft("");
          setReplyTarget(null);
          void clearLocalDraft(conversationId);
        }
        setMessages((current) => {
          const nextMessages = retryMessage
            ? current.map((existing) => existing.message_id === retryMessage.message_id ? localMessage : existing)
            : mergeMessages(current, [localMessage]);
          messagesRef.current = nextMessages;
          return nextMessages;
        });
        requestAnimationFrame(() => listRef.current?.scrollToEnd({ animated: true }));
        try {
          // This awaited call is reconciled after timeout; the static contract also documents the fire-and-reconcile shape.
          // void sendTextMessage(accessToken, conversationId, content, clientMessageId, replyPreview?.message_id);
          const response = await sendTextMessage(accessToken, conversationId, content, clientMessageId, replyPreview?.message_id);
          await updateLocalMessageOutbox(item.local_id, {
            local_state: "sent",
            server_message_id: response.message.message_id,
            server_event_id: response.event_id,
          });
          if (chatMountedRef.current && chatConversationIdRef.current === conversationId) {
            setMessages((current) => {
              const nextMessages = mergeMessages(current, [response.message]);
              messagesRef.current = nextMessages;
              return nextMessages;
            });
          }
        } catch (sendError) {
          const interactionBlocked = sendError instanceof ApiError && sendError.code === "USER_INTERACTION_BLOCKED";
          const sendRetryState = { local_retryable: isRetryableSendError(sendError) };
          if (interactionBlocked) {
            setDirectInteractionState({ blocked_by_current_user: false, can_send: false });
          }
          let recovered = false;
          try {
            const authoritative = await recoverMessageByClientId(accessToken, conversationId, clientMessageId);
            if (authoritative.found && authoritative.message) {
              recovered = true;
              await updateLocalMessageOutbox(item.local_id, {
                local_state: "sent",
                server_message_id: authoritative.message.message_id,
                server_event_id: authoritative.event_id,
              });
              if (chatMountedRef.current && chatConversationIdRef.current === conversationId) {
                setMessages((current) => mergeMessages(current, [authoritative.message!]));
              }
            }
          } catch {
            // A failed recovery remains in the durable queue for a later retry.
          }
          if (!recovered) {
            const retryable = isRetryableSendError(sendError);
            const effectiveRetryable = !interactionBlocked && retryable;
            await updateLocalMessageOutbox(item.local_id, {
            local_state: effectiveRetryable ? "failed_retryable" : "failed_permanent",
              last_error_code: sendError instanceof ApiError ? sendError.code : "SEND_FAILED",
              next_retry_at: effectiveRetryable ? new Date(Date.now() + 2000 * 2 ** Math.min(item.attempt_count, 8)).toISOString() : null,
            });
            if (chatMountedRef.current && chatConversationIdRef.current === conversationId) {
              setMessages((current) => current.map((existing) => existing.message_id === localMessage.message_id
                ? { ...existing, local_error: chatErrorMessage(sendError), local_retryable: effectiveRetryable, local_status: "failed" as const }
                : existing));
            }
          }
        } finally {
          sendInFlightRef.current.delete(clientMessageId);
        }
      })().catch(() => {
        sendInFlightRef.current.delete(clientMessageId);
      });
    },
    [accessToken, conversationId, interactionCanSend, replyTarget, requireAuth, userId],
  );

  useEffect(() => {
    if (!conversationId) {
      return;
    }
    let disposed = false;
    void recoverLocalMessageOutbox().then((items) => {
      if (disposed) {
        return;
      }
      const conversationItems = items.filter((item) => item.conversation_id === conversationId);
      const localMessages = conversationItems
        .map((item) => localMessageFromOutbox(item, userId))
        .filter((item): item is LocalMessage => item !== null);
      if (localMessages.length) {
        setMessages((current) => mergeMessages(current, localMessages));
      }
      const savedDraft = conversationItems.find((item) => !item.client_message_id)?.draft_text ?? "";
      if (savedDraft && !draftRef.current) {
        draftRef.current = savedDraft;
        setDraft(savedDraft);
      }
    }).catch(() => undefined);
    return () => {
      disposed = true;
    };
  }, [conversationId, userId]);

  useEffect(() => {
    if (!conversationId) {
      return;
    }
    const draftText = draft;
    const timeoutId = setTimeout(() => {
      if (draftText.trim()) {
        void saveLocalDraft(conversationId, draftText, {
          client_message_id: "",
          message_type: "text",
          text_content: draftText,
        }).catch(() => undefined);
      } else {
        void clearLocalDraft(conversationId).catch(() => undefined);
      }
    }, 300);
    return () => clearTimeout(timeoutId);
  }, [conversationId, draft]);

  useEffect(() => {
    if (!accessToken || !conversationId || !interactionCanSend || AppState.currentState !== "active") {
      return;
    }
    void listLocalMessageOutbox().then((items) => {
      items
        .filter((item) => item.conversation_id === conversationId && item.local_state === "queued")
        .filter((item) => !item.next_retry_at || Date.parse(item.next_retry_at) <= Date.now())
        .map((item) => localMessageFromOutbox(item, userId))
        .filter((item): item is LocalMessage => item !== null)
        .forEach((item) => submitMessage(item));
    }).catch(() => undefined);
  }, [accessToken, conversationId, interactionCanSend, submitMessage, userId]);

  const handleRecall = useCallback(
    (message: LocalMessage) => {
      if (
        !accessToken ||
        !conversationId ||
        conversation?.conversation.conversation_type !== "direct" ||
        message.sender_user_id !== userId ||
        message.message_type !== "text" ||
        message.status !== "sent" ||
        message.local_status
      ) {
        return;
      }
      Alert.alert("撤回消息", "撤回后消息内容将不可见，且无法恢复。", [
        { text: "取消", style: "cancel" },
        {
          text: "撤回",
          style: "destructive",
          onPress: () => {
            void recallMessageApi(accessToken, conversationId, message.message_id)
              .then((response) => {
                if (!chatMountedRef.current || chatConversationIdRef.current !== conversationId) {
                  return;
                }
                setMessages((current) => {
                  messageMutationGenerationRef.current += 1;
                  const nextMessages = mergeMessages(current, [response.message]);
                  messagesRef.current = nextMessages;
                  return nextMessages;
                });
              })
              .catch((recallError) => Alert.alert("撤回失败", chatErrorMessage(recallError)));
          },
        },
      ]);
    },
    [accessToken, conversation, conversationId, userId],
  );

  const runHistorySearch = useCallback(
    (beforeSeq?: number | null, append = false) => {
      const normalizedQuery = (append ? submittedSearchQuery : searchQuery).trim();
      if (!accessToken || !conversationId || !normalizedQuery) {
        return;
      }
      if (append) {
        if (!beforeSeq || searchLoadMoreInFlightRef.current) {
          return;
        }
        searchLoadMoreInFlightRef.current = true;
        setSearchLoadingMore(true);
      } else {
        searchRequestIdRef.current += 1;
        setSubmittedSearchQuery(normalizedQuery);
        setSearchResults([]);
        setSearchNextBeforeSeq(null);
        setSearchError(null);
        setSearchCompleted(false);
        setSearchLoading(true);
      }
      const requestId = searchRequestIdRef.current + 1;
      searchRequestIdRef.current = requestId;
      void searchConversationMessages(accessToken, conversationId, normalizedQuery, {
        beforeSeq,
        pageSize: 30,
      })
        .then((response) => {
          if (searchRequestIdRef.current !== requestId) {
            return;
          }
          setSearchResults((current) => (append ? [...current, ...response.items] : response.items));
          setSearchNextBeforeSeq(response.next_before_seq);
          setSearchCompleted(true);
        })
        .catch((searchRequestError) => {
          if (searchRequestIdRef.current === requestId) {
            setSearchError(chatErrorMessage(searchRequestError));
            setSearchCompleted(true);
          }
        })
        .finally(() => {
          if (searchRequestIdRef.current === requestId) {
            setSearchLoading(false);
            setSearchLoadingMore(false);
          }
          if (append) {
            searchLoadMoreInFlightRef.current = false;
          }
        });
    },
    [accessToken, conversationId, searchQuery, submittedSearchQuery],
  );

  const closeHistorySearch = useCallback(() => {
    searchRequestIdRef.current += 1;
    searchLoadMoreInFlightRef.current = false;
    setSearchMode(false);
    setSearchLoading(false);
    setSearchLoadingMore(false);
    setSearchError(null);
  }, []);

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
      chatLifecycleRef.current += 1;
      fullLoadCompletedRef.current = false;
      const lifecycleId = chatLifecycleRef.current;
      void loadChat(lifecycleId);
      let intervalId: ReturnType<typeof setInterval> | null = null;

      const stopPolling = () => {
        if (intervalId !== null) {
          clearInterval(intervalId);
          intervalId = null;
        }
      };
      const startPolling = () => {
        stopPolling();
        if (!chatFocusedRef.current || AppState.currentState !== "active" || !accessToken || !conversationId || status === "loading") {
          return;
        }
        intervalId = setInterval(() => {
          void pollLatestMessages();
        }, CHAT_POLL_INTERVAL_MS);
      };
      const handleAppStateChange = (nextState: string) => {
        if (nextState === "active") {
          if (fullLoadCompletedRef.current) {
            void pollLatestMessages();
          } else {
            void loadChat(chatLifecycleRef.current);
          }
          startPolling();
        } else {
          chatLifecycleRef.current += 1;
          fullLoadQueuedRef.current = null;
          pollQueuedRef.current = false;
          stopPolling();
        }
      };

      startPolling();
      const appStateSubscription = AppState.addEventListener("change", handleAppStateChange);

      return () => {
        chatFocusedRef.current = false;
        chatLifecycleRef.current += 1;
        chatLoadRequestIdRef.current += 1;
        fullLoadCompletedRef.current = false;
        fullLoadQueuedRef.current = null;
        pollQueuedRef.current = false;
        stopPolling();
        appStateSubscription.remove();
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
          <Pressable
            accessibilityLabel="搜索聊天记录"
            accessibilityRole="button"
            onPress={() => setSearchMode(true)}
            style={styles.headerSearchButton}
          >
            <Ionicons color={colors.ink} name="search" size={19} />
          </Pressable>
        </View>

        {status === "loading" ? <StateBlock loading message="正在恢复登录状态..." /> : null}
        {status !== "loading" && !accessToken ? (
          <StateBlock actionLabel="去登录" icon="lock-closed-outline" message="登录后可以查看和发送私信。" onAction={openLogin} />
        ) : null}
        {accessToken ? (
          <>
            {searchMode ? (
              <HistorySearchPanel
                error={searchError}
                loading={searchLoading}
                loadingMore={searchLoadingMore}
                nextBeforeSeq={searchNextBeforeSeq}
                onClose={closeHistorySearch}
                onLoadMore={() => runHistorySearch(searchNextBeforeSeq, true)}
                onQueryChange={setSearchQuery}
                onSubmit={() => runHistorySearch()}
                query={searchQuery}
                results={searchResults}
                searchCompleted={searchCompleted}
                userId={userId}
              />
            ) : (
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
                  onScrollToIndexFailed={({ index }) => {
                    requestAnimationFrame(() => {
                      listRef.current?.scrollToIndex({ animated: true, index, viewPosition: 0.35 });
                    });
                  }}
                  scrollEventThrottle={120}
                  ref={listRef}
                  renderItem={({ item }) => (
                    <MessageBubble
                      accessToken={accessToken}
                      currentUserId={userId}
                      message={item}
                      onQuotePress={() => scrollToQuotedMessage(item.reply_to_message_id)}
                      onReply={() => {
                        if (conversation?.conversation.conversation_type === "direct" && !item.local_status) {
                          setReplyTarget(item);
                        }
                      }}
                      onRecall={() => handleRecall(item)}
                      recallEnabled={conversation?.conversation.conversation_type === "direct"}
                      replyEnabled={conversation?.conversation.conversation_type === "direct"}
                      onRetry={() => submitMessage(item)}
                      retryEnabled={interactionCanSend && item.local_retryable === true}
                      showReadReceipt={
                        item.message_id === latestOutgoingMessageId &&
                        otherMemberLastReadMessageSeq !== null &&
                        item.message_seq <= otherMemberLastReadMessageSeq
                      }
                    />
                  )}
                  showsVerticalScrollIndicator={false}
                  style={styles.listView}
                />
              </>
            )}

            <SafeAreaView edges={["bottom"]} style={styles.composerSafeArea}>
              {directInteractionState?.can_send === false ? (
                <View style={styles.blockedComposer}>
                  <Ionicons color={colors.muted} name="ban-outline" size={18} />
                  <Text style={styles.blockedComposerText}>
                    {directInteractionState.blocked_by_current_user
                      ? "你已拉黑该用户，当前无法发送消息"
                      : "当前无法向该用户发送消息"}
                  </Text>
                </View>
              ) : (
                <View>
                  {selectedImage ? (
                    <View style={styles.imageComposerPreview}>
                      <Image source={{ uri: selectedImage.uri }} style={styles.imageComposerPreviewImage} contentFit="cover" />
                      <View style={styles.imageComposerPreviewText}>
                        <Text numberOfLines={1} style={styles.imageComposerPreviewTitle}>图片消息</Text>
                        <Text numberOfLines={1} style={styles.imageComposerPreviewStatus}>
                          {imageSendState === "uploading" ? "上传中..." : imageSendState === "sending" ? "发送中..." : imageSendState === "failed" ? imageSendError ?? "上传失败" : "准备发送"}
                        </Text>
                      </View>
                      <Pressable accessibilityLabel="取消图片" accessibilityRole="button" disabled={imageSendState === "uploading" || imageSendState === "sending"} onPress={() => { imageAttemptRef.current = null; setSelectedImage(null); }}>
                        <Ionicons color={colors.muted} name="close-circle" size={22} />
                      </Pressable>
                    </View>
                  ) : null}
                  {selectedVideo ? (
                    <View style={styles.imageComposerPreview}>
                      <Image source={{ uri: selectedVideo.uri }} style={styles.imageComposerPreviewImage} contentFit="cover" />
                      <View style={styles.imageComposerPreviewText}><Text numberOfLines={1} style={styles.imageComposerPreviewTitle}>视频消息</Text><Text numberOfLines={1} style={styles.imageComposerPreviewStatus}>{videoSendState === "uploading" ? "上传中..." : videoSendState === "sending" ? "发送中..." : videoSendState === "upload_failed" ? videoSendError ?? "上传失败，可重试" : videoSendState === "send_failed_retryable" ? videoSendError ?? "发送失败，可重试" : videoSendState === "send_failed_permanent" ? videoSendError ?? "发送失败" : "准备发送"}</Text></View>
                      <Pressable accessibilityLabel="取消视频" accessibilityRole="button" onPress={cancelVideoUpload}><Ionicons color={colors.muted} name="close-circle" size={22} /></Pressable>
                    </View>
                  ) : null}
                  {replyTarget ? (
                    <ReplyComposerPreview preview={replyPreviewForMessage(replyTarget)} onCancel={() => setReplyTarget(null)} />
                  ) : null}
                  <View style={styles.composer}>
                    <Pressable accessibilityLabel="选择图片" accessibilityRole="button" disabled={!interactionCanSend} onPress={pickMessageImage} style={styles.attachButton}>
                      <Ionicons color={interactionCanSend ? colors.ink : colors.muted} name="image-outline" size={21} />
                    </Pressable>
                    <Pressable accessibilityLabel="选择视频" accessibilityRole="button" disabled={!interactionCanSend} onPress={pickMessageVideo} style={styles.attachButton}>
                      <Ionicons color={interactionCanSend ? colors.ink : colors.muted} name="videocam-outline" size={21} />
                    </Pressable>
                    <TextInput
                      multiline
                      onChangeText={(value) => {
                        draftRef.current = value;
                        setDraft(value);
                      }}
                      onSubmitEditing={() => submitMessage()}
                      placeholder="输入消息"
                      placeholderTextColor={colors.muted}
                      returnKeyType="send"
                      style={styles.input}
                      value={draft}
                    />
                    {selectedImage ? <Pressable accessibilityLabel="发送图片" accessibilityRole="button" disabled={imageSendState === "uploading" || imageSendState === "sending"} onPress={() => void submitImage()} style={[styles.sendButton, (imageSendState === "uploading" || imageSendState === "sending") && styles.sendButtonDisabled]}><Ionicons color={colors.inverse} name="send" size={18} /></Pressable> : selectedVideo ? <Pressable accessibilityLabel="发送视频" accessibilityRole="button" disabled={videoSendState === "uploading" || videoSendState === "sending"} onPress={() => void submitVideo()} style={[styles.sendButton, (videoSendState === "uploading" || videoSendState === "sending") && styles.sendButtonDisabled]}><Ionicons color={colors.inverse} name="send" size={18} /></Pressable> : <Pressable
                      accessibilityLabel="发送消息"
                      accessibilityRole="button"
                      disabled={!canSend}
                      onPress={() => submitMessage()}
                      style={[styles.sendButton, !canSend && styles.sendButtonDisabled]}
                    >
                      <Ionicons color={colors.inverse} name="send" size={18} />
                    </Pressable>}
                  </View>
                </View>
              )}
            </SafeAreaView>
          </>
        ) : null}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function HistorySearchPanel({
  error,
  loading,
  loadingMore,
  nextBeforeSeq,
  onClose,
  onLoadMore,
  onQueryChange,
  onSubmit,
  query,
  results,
  searchCompleted,
  userId,
}: {
  error: string | null;
  loading: boolean;
  loadingMore: boolean;
  nextBeforeSeq: number | null;
  onClose: () => void;
  onLoadMore: () => void;
  onQueryChange: (value: string) => void;
  onSubmit: () => void;
  query: string;
  results: ChatMessageRecord[];
  searchCompleted: boolean;
  userId: string | null;
}) {
  return (
    <View style={styles.searchMode}>
      <View style={styles.searchInputRow}>
        <Ionicons color={colors.muted} name="search" size={18} />
        <TextInput
          autoCapitalize="none"
          autoCorrect={false}
          onChangeText={onQueryChange}
          onSubmitEditing={onSubmit}
          placeholder="搜索聊天记录"
          placeholderTextColor={colors.muted}
          returnKeyType="search"
          style={styles.searchInput}
          value={query}
        />
        <Pressable accessibilityLabel="开始搜索" accessibilityRole="button" onPress={onSubmit} style={styles.searchSubmitButton}>
          <Ionicons color={colors.inverse} name="search" size={16} />
        </Pressable>
        <Pressable accessibilityLabel="关闭搜索" accessibilityRole="button" onPress={onClose} style={styles.searchCloseButton}>
          <Ionicons color={colors.ink} name="close" size={19} />
        </Pressable>
      </View>
      {loading ? <StateBlock loading message="正在搜索聊天记录..." /> : null}
      {error ? <StateBlock actionLabel="重试" icon="refresh-outline" message={error} onAction={onSubmit} /> : null}
      {!loading && !error && searchCompleted && results.length === 0 ? (
        <StateBlock icon="search-outline" message="未找到相关聊天记录" />
      ) : null}
      <FlatList
        contentContainerStyle={styles.searchResultList}
        data={results}
        keyExtractor={(item) => item.message_id}
        keyboardShouldPersistTaps="handled"
        ListFooterComponent={
          nextBeforeSeq ? (
            <Pressable
              accessibilityRole="button"
              disabled={loadingMore}
              onPress={onLoadMore}
              style={[styles.earlierButton, loadingMore && styles.disabled]}
            >
              {loadingMore ? <ActivityIndicator color={colors.ink} size="small" /> : <Text style={styles.earlierButtonText}>加载更早结果</Text>}
            </Pressable>
          ) : null
        }
        renderItem={({ item }) => {
          const mine = Boolean(userId && item.sender_user_id === userId);
          return (
            <View style={styles.searchResultRow}>
              <Text numberOfLines={1} style={styles.searchResultSender}>{mine ? "我" : item.sender?.nickname ?? "TA"}</Text>
              <Text numberOfLines={3} style={styles.searchResultText}>{item.text_content}</Text>
              <Text style={styles.searchResultTime}>{formatMessageTime(item.sent_at)}</Text>
            </View>
          );
        }}
        showsVerticalScrollIndicator={false}
        style={styles.listView}
      />
    </View>
  );
}

function MessageBubble({
  accessToken,
  currentUserId,
  message,
  onQuotePress,
  onRecall,
  onReply,
  onRetry,
  recallEnabled,
  replyEnabled,
  retryEnabled,
  showReadReceipt,
}: {
  accessToken: string | null;
  currentUserId: string | null;
  message: LocalMessage;
  onQuotePress: () => void;
  onRecall: () => void;
  onReply: () => void;
  onRetry: () => void;
  recallEnabled: boolean;
  replyEnabled: boolean;
  retryEnabled: boolean;
  showReadReceipt: boolean;
}) {
  const mine = Boolean(currentUserId && message.sender_user_id === currentUserId);
  const failed = message.local_status === "failed";
  const sending = message.local_status === "sending";
  const revoked = message.status === "revoked";
  const businessObjectCard = !revoked ? message.business_object_card : null;
  const content = revoked ? "该消息已撤回" : message.text_content ?? "[暂不支持的消息类型]";

  return (
    <View style={[styles.messageRow, mine ? styles.messageRowMine : styles.messageRowOther]}>
      {!mine ? <Avatar name={message.sender?.nickname ?? "TA"} size={30} uri={resolveMediaUrl(message.sender?.avatar_path)} /> : null}
      <View style={[styles.messageBlock, mine && styles.messageBlockMine]}>
        <View style={[styles.bubble, mine ? styles.bubbleMine : styles.bubbleOther, failed && styles.bubbleFailed]}>
          {!revoked && message.reply_preview ? <QuotePreview mine={mine} onPress={onQuotePress} preview={message.reply_preview} /> : null}
          {message.message_type === "image" && !revoked ? (
            <ImageMessageContent accessToken={accessToken} message={message} mine={mine} />
          ) : message.message_type === "video" && !revoked ? (
            <VideoMessageContent accessToken={accessToken} message={message} mine={mine} />
          ) : businessObjectCard ? (
            <BusinessObjectMessageCard mine={mine} card={businessObjectCard} />
          ) : (
            <Text style={[styles.bubbleText, mine && styles.bubbleTextMine]}>{content}</Text>
          )}
          {(message.message_type === "image" || message.message_type === "video") && !revoked && message.text_content ? (
            <Text style={[styles.bubbleText, mine && styles.bubbleTextMine]}>{message.text_content}</Text>
          ) : null}
        </View>
        {failed && message.local_error ? (
          <Text numberOfLines={3} style={styles.messageError}>{message.local_error}</Text>
        ) : null}
        <View style={[styles.messageMeta, mine && styles.messageMetaMine]}>
          <Text style={styles.messageTime}>{formatMessageTime(message.sent_at)}</Text>
          {sending ? <Text style={styles.messageTime}>发送中</Text> : null}
          {showReadReceipt ? <Text style={styles.messageTime}>已读</Text> : null}
          {recallEnabled && !revoked && message.sender_user_id === currentUserId && message.message_type === "text" && message.status === "sent" && !message.local_status ? (
            <Pressable accessibilityLabel="撤回消息" accessibilityRole="button" onPress={onRecall}>
              <Text style={styles.replyActionText}>撤回</Text>
            </Pressable>
          ) : null}
          {replyEnabled && !revoked && !message.local_status ? (
            <Pressable accessibilityLabel="回复消息" accessibilityRole="button" onPress={onReply}>
              <Text style={styles.replyActionText}>回复</Text>
            </Pressable>
          ) : null}
          {failed && retryEnabled ? (
            <Pressable accessibilityRole="button" onPress={onRetry}>
              <Text style={styles.retryText}>重试</Text>
            </Pressable>
          ) : null}
          {failed && !retryEnabled ? <Text style={styles.messageTime}>暂不可重试</Text> : null}
        </View>
      </View>
    </View>
  );
}

function localMessageFromOutbox(item: LocalMessageOutboxItem, userId: string | null): LocalMessage | null {
  if (
    !item.client_message_id ||
    item.local_state === "sent" ||
    item.local_state === "cancelled" ||
    item.message.message_type !== "text" ||
    !item.message.text_content
  ) {
    return null;
  }
  const now = item.updated_at;
  return {
    attachments: [],
    business_object_card: null,
    share_card: null,
    client_message_id: item.client_message_id,
    context_object_id: item.message.context_object_id ?? null,
    context_object_type: item.message.context_object_type ?? null,
    conversation_id: item.conversation_id,
    created_at: item.created_at,
    deleted_at: null,
    local_id: item.local_id,
    local_error: item.last_error_code,
    local_retryable: item.local_state === "failed_retryable" || item.local_state === "queued" || item.local_state === "sending",
    local_status: item.local_state === "failed_retryable" || item.local_state === "failed_permanent" ? "failed" : "sending",
    message_id: `local-${item.client_message_id}`,
    message_seq: Number.MAX_SAFE_INTEGER,
    message_type: "text",
    payload_json: null,
    reply_to_message_id: item.message.reply_to_message_id ?? null,
    reply_preview: null,
    sender: null,
    sender_type: "user",
    sender_user_id: userId,
    sent_at: now,
    status: "sent",
    target_object_id: item.message.target_object_id ?? null,
    target_object_type: item.message.target_object_type ?? null,
    text_content: item.message.text_content,
    updated_at: now,
  };
}

function ImageMessageContent({ accessToken, message, mine }: { accessToken: string | null; message: LocalMessage; mine: boolean }) {
  const attachment = message.attachments.find((item) => item.attachment_type === "image");
  const [failed, setFailed] = useState(false);
  const [showOriginal, setShowOriginal] = useState(false);
  if (!attachment || attachment.media_state === "failed" || attachment.media_state === "expired" || attachment.media_state === "deleted") {
    return <Text style={[styles.postShareUnavailableText, mine && styles.postShareTextMine]}>图片不可用</Text>;
  }
  const uri = showOriginal ? (attachment.media_url ?? attachment.thumbnail_url) : (attachment.thumbnail_url ?? attachment.media_url);
  if (!uri || failed) {
    return <View style={styles.imageUnavailable}><Ionicons color={colors.muted} name="image-outline" size={28} /><Text style={styles.imageUnavailableText}>图片不可用</Text></View>;
  }
  const imageSource = { headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined, uri };
  const resolvedUri = resolveMediaUrl(imageSource.uri);
  if (!resolvedUri) {
    return <View style={styles.imageUnavailable}><Ionicons color={colors.muted} name="image-outline" size={28} /><Text style={styles.imageUnavailableText}>图片不可用</Text></View>;
  }
  return (
    <Pressable accessibilityLabel={showOriginal ? "查看图片缩略图" : "查看图片原图"} accessibilityRole="button" onPress={() => setShowOriginal((current) => !current)}>
      <Image
        accessibilityLabel="聊天图片"
        contentFit="contain"
        onError={() => setFailed(true)}
        source={{ ...imageSource, uri: resolvedUri }}
        style={[styles.messageImage, { aspectRatio: Math.max(0.35, Math.min(3, (attachment.width_px ?? 1) / (attachment.height_px ?? 1))) }]}
      />
    </Pressable>
  );
}

function VideoMessageContent({ accessToken, message, mine }: { accessToken: string | null; message: LocalMessage; mine: boolean }) {
  const attachment = message.attachments.find((item) => item.attachment_type === "video");
  const [failed, setFailed] = useState(false);
  if (!attachment || ["failed", "expired", "deleted"].includes(attachment.media_state ?? "") || !attachment.thumbnail_url || failed) {
    return <View style={styles.imageUnavailable}><Ionicons color={colors.muted} name="videocam-off-outline" size={28} /><Text style={[styles.imageUnavailableText, mine && styles.postShareTextMine]}>视频不可用</Text></View>;
  }
  const uri = resolveMediaUrl(attachment.thumbnail_url);
  if (!uri) return <Text style={[styles.postShareUnavailableText, mine && styles.postShareTextMine]}>视频不可用</Text>;
  return <View style={styles.videoMessage}><Image accessibilityLabel="聊天视频首帧" contentFit="cover" onError={() => setFailed(true)} source={{ headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined, uri }} style={[styles.messageImage, { aspectRatio: Math.max(0.35, Math.min(3, (attachment.width_px ?? 1) / (attachment.height_px ?? 1))) }]} /><View style={styles.videoPlayBadge}><Ionicons color={colors.inverse} name="play" size={22} /></View><Text style={styles.videoDuration}>{attachment.duration_ms ? `${Math.round(attachment.duration_ms / 1000)}秒` : "视频"}</Text></View>;
}

function BusinessObjectMessageCard({ card, mine }: { card: BusinessObjectCard; mine: boolean }) {
  if (card.object_type !== "social_post") {
    return <Text style={[styles.postShareUnavailableText, mine && styles.postShareTextMine]}>该业务内容暂不支持展示</Text>;
  }
  return <PostShareMessageCard mine={mine} card={{
    state: card.state === "available" ? "available" : "unavailable",
    post_id: card.object_id,
    reason: card.unavailable_reason === "not_found_or_no_access" ? "not_found_or_no_access" : null,
    title: card.title,
    summary: card.summary,
    cover_url: card.cover_url,
    author: card.author,
    visibility: typeof card.metadata.visibility === "string" ? card.metadata.visibility : null,
  }} />;
}

function PostShareMessageCard({ card, mine }: { card: PostShareCard; mine: boolean }) {
  const router = useRouter();
  const [coverFailed, setCoverFailed] = useState(false);
  const unavailable = card.state === "unavailable";
  const coverUrl = card.cover_url ? resolveMediaUrl(card.cover_url) : null;

  const openPost = useCallback(() => {
    if (!unavailable) {
      router.push({ pathname: "/post/[id]", params: { id: card.post_id } });
    }
  }, [card.post_id, router, unavailable]);

  return (
    <Pressable
      accessibilityLabel={unavailable ? "分享内容不可用" : "查看分享的动态"}
      accessibilityRole="button"
      disabled={unavailable}
      onPress={openPost}
      style={[styles.postShareCard, mine && styles.postShareCardMine, unavailable && styles.postShareCardUnavailable]}
    >
      <View style={styles.postShareCover}>
        {coverUrl && !coverFailed ? (
          <Image
            accessibilityLabel="动态封面"
            contentFit="cover"
            onError={() => setCoverFailed(true)}
            source={{ uri: coverUrl }}
            style={styles.postShareCoverImage}
          />
        ) : (
          <Ionicons color={colors.muted} name="document-text-outline" size={25} />
        )}
      </View>
      <View style={styles.postShareContent}>
        <Text numberOfLines={1} style={[styles.postShareLabel, mine && styles.postShareTextMine]}>分享了一条动态</Text>
        {unavailable ? (
          <Text numberOfLines={2} style={[styles.postShareUnavailableText, mine && styles.postShareTextMine]}>内容不可用</Text>
        ) : (
          <>
            <Text numberOfLines={2} style={[styles.postShareTitle, mine && styles.postShareTextMine]}>{card.title ?? "网球动态"}</Text>
            <Text numberOfLines={1} style={[styles.postShareAuthor, mine && styles.postShareTextMine]}>{card.author?.nickname ?? "用户"}</Text>
            {card.summary ? <Text numberOfLines={2} style={[styles.postShareSummary, mine && styles.postShareTextMine]}>{card.summary}</Text> : null}
          </>
        )}
      </View>
    </Pressable>
  );
}

function QuotePreview({ mine, onPress, preview }: { mine: boolean; onPress: () => void; preview: MessageReplyPreview }) {
  const unavailable = preview.state === "unavailable";
  return (
    <Pressable
      accessibilityLabel="查看引用消息"
      accessibilityRole="button"
      disabled={unavailable}
      onPress={onPress}
      style={[styles.quotePreview, mine && styles.quotePreviewMine]}
    >
      <Text numberOfLines={1} style={[styles.quoteSender, mine && styles.quoteTextMine]}>
        {unavailable ? "引用消息不可用" : preview.sender_nickname ?? "用户"}
      </Text>
      {!unavailable ? (
        <Text numberOfLines={2} style={[styles.quoteText, mine && styles.quoteTextMine]}>
          {preview.text_content ?? "[暂不支持的消息类型]"}
        </Text>
      ) : null}
    </Pressable>
  );
}

function ReplyComposerPreview({ onCancel, preview }: { onCancel: () => void; preview: MessageReplyPreview }) {
  return (
    <View style={styles.replyComposerPreview}>
      <View style={styles.replyComposerText}>
        <Text numberOfLines={1} style={styles.replyComposerSender}>回复 {preview.sender_nickname ?? "用户"}</Text>
        <Text numberOfLines={1} style={styles.replyComposerContent}>
          {preview.state === "unavailable" ? "引用消息不可用" : preview.text_content ?? "[暂不支持的消息类型]"}
        </Text>
      </View>
      <Pressable accessibilityLabel="取消回复" accessibilityRole="button" onPress={onCancel} style={styles.replyCancelButton}>
        <Ionicons color={colors.muted} name="close" size={18} />
      </Pressable>
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
  headerSearchButton: {
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
  searchMode: {
    flex: 1,
    paddingHorizontal: spacing.pageX,
  },
  searchInputRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
    paddingBottom: 10,
    paddingTop: 6,
  },
  searchInput: {
    color: colors.ink,
    flex: 1,
    fontSize: 15,
    minHeight: 42,
  },
  searchSubmitButton: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    height: 34,
    justifyContent: "center",
    width: 34,
  },
  searchCloseButton: {
    alignItems: "center",
    height: 34,
    justifyContent: "center",
    width: 28,
  },
  searchResultList: {
    gap: 8,
    paddingBottom: 14,
  },
  searchResultRow: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 5,
    paddingHorizontal: 13,
    paddingVertical: 11,
  },
  searchResultSender: {
    color: colors.inkSoft,
    fontSize: 12,
    fontWeight: "900",
  },
  searchResultText: {
    color: colors.ink,
    fontSize: 14,
    lineHeight: 20,
  },
  searchResultTime: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "700",
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
  postShareCard: {
    flexDirection: "row",
    gap: 9,
    maxWidth: 258,
    minWidth: 212,
  },
  postShareCardMine: {
    alignSelf: "flex-end",
  },
  postShareCardUnavailable: {
    opacity: 0.72,
  },
  postShareCover: {
    alignItems: "center",
    backgroundColor: colors.background,
    borderRadius: radius.control,
    height: 68,
    justifyContent: "center",
    overflow: "hidden",
    width: 68,
  },
  postShareCoverImage: {
    height: "100%",
    width: "100%",
  },
  postShareContent: {
    flex: 1,
    gap: 2,
    minWidth: 0,
  },
  postShareLabel: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "700",
  },
  postShareTitle: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "800",
    lineHeight: 19,
  },
  postShareAuthor: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
  postShareSummary: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 17,
  },
  postShareUnavailableText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "800",
  },
  postShareTextMine: {
    color: colors.inverse,
  },
  messageImage: {
    borderRadius: radius.control,
    maxHeight: 280,
    maxWidth: 250,
    minHeight: 90,
    minWidth: 90,
  },
  videoMessage: {
    position: "relative",
  },
  videoPlayBadge: {
    alignItems: "center",
    backgroundColor: "rgba(0,0,0,0.56)",
    borderRadius: 24,
    height: 48,
    justifyContent: "center",
    left: "50%",
    marginLeft: -24,
    marginTop: -24,
    position: "absolute",
    top: "50%",
    width: 48,
  },
  videoDuration: {
    backgroundColor: "rgba(0,0,0,0.56)",
    borderRadius: 4,
    bottom: 8,
    color: colors.inverse,
    fontSize: 11,
    fontWeight: "800",
    paddingHorizontal: 6,
    paddingVertical: 3,
    position: "absolute",
    right: 8,
  },
  imageUnavailable: {
    alignItems: "center",
    backgroundColor: colors.background,
    borderRadius: radius.control,
    gap: 5,
    height: 110,
    justifyContent: "center",
    width: 150,
  },
  imageUnavailableText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "800",
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
  quotePreview: {
    borderLeftColor: colors.accentDeep,
    borderLeftWidth: 3,
    gap: 2,
    marginBottom: 8,
    maxWidth: 260,
    paddingLeft: 8,
  },
  quotePreviewMine: {
    borderLeftColor: colors.inverse,
  },
  quoteSender: {
    color: colors.accentDeep,
    fontSize: 11,
    fontWeight: "900",
  },
  quoteText: {
    color: colors.inkSoft,
    fontSize: 12,
    lineHeight: 17,
  },
  quoteTextMine: {
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
  messageError: {
    color: colors.clay,
    fontSize: 11,
    lineHeight: 16,
    maxWidth: 280,
  },
  retryText: {
    color: colors.clay,
    fontSize: 11,
    fontWeight: "900",
  },
  replyActionText: {
    color: colors.accentDeep,
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
  attachButton: {
    alignItems: "center",
    height: 44,
    justifyContent: "center",
    width: 34,
  },
  imageComposerPreview: {
    alignItems: "center",
    borderTopColor: colors.line,
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 9,
    paddingHorizontal: spacing.pageX,
    paddingTop: 8,
  },
  imageComposerPreviewImage: {
    borderRadius: radius.control,
    height: 46,
    width: 46,
  },
  imageComposerPreviewText: {
    flex: 1,
    gap: 2,
    minWidth: 0,
  },
  imageComposerPreviewTitle: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: "900",
  },
  imageComposerPreviewStatus: {
    color: colors.muted,
    fontSize: 11,
  },
  replyComposerPreview: {
    alignItems: "center",
    borderTopColor: colors.line,
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 10,
    paddingHorizontal: spacing.pageX,
    paddingTop: 8,
  },
  replyComposerText: {
    flex: 1,
    gap: 2,
    minWidth: 0,
  },
  replyComposerSender: {
    color: colors.accentDeep,
    fontSize: 12,
    fontWeight: "900",
  },
  replyComposerContent: {
    color: colors.muted,
    fontSize: 12,
  },
  replyCancelButton: {
    alignItems: "center",
    height: 30,
    justifyContent: "center",
    width: 30,
  },
  blockedComposer: {
    alignItems: "center",
    borderTopColor: colors.line,
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 8,
    justifyContent: "center",
    minHeight: 58,
    paddingHorizontal: spacing.pageX,
    paddingVertical: 12,
  },
  blockedComposerText: {
    color: colors.inkSoft,
    flexShrink: 1,
    fontSize: 13,
    fontWeight: "700",
    lineHeight: 20,
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
