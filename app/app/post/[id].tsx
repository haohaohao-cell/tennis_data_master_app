import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect } from "@react-navigation/native";
import { Image } from "expo-image";
import { VideoView, useVideoPlayer, type VideoSource } from "expo-video";
import { StatusBar } from "expo-status-bar";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type ViewToken,
  useWindowDimensions,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { resolveMediaUrl } from "@/api/activityDetail";
import { ApiError } from "@/api/client";
import { listConversations, type ConversationListItem } from "@/api/messages";
import { peekPostDetailPreview, primePostDetailPreview } from "@/api/postDetailPreviewCache";
import {
  createPostComment,
  deletePostComment,
  favoritePost,
  getReadablePostDetail,
  likePost,
  listPostComments,
  reportPostViews,
  sharePost,
  type PostCommentRecord,
  type PostDetailResponse,
  type PostStats,
  unfavoritePost,
  unlikePost,
} from "@/api/posts";
import { useAuth } from "@/auth/AuthProvider";
import { useRequireAuth } from "@/auth/useRequireAuth";
import { Avatar } from "@/components/ui";
import { colors, radius } from "@/theme";

function detailErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 404) {
      return "没有找到这条动态，或你暂时没有查看权限。";
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "动态详情加载失败，请稍后重试。";
}

function createPostShareClientMessageId(postId: string, conversationId: string) {
  return `post-share:${postId}:${conversationId}:${Date.now()}:${Math.random().toString(36).slice(2, 10)}`;
}

function formatCount(value: number | null | undefined) {
  const count = value ?? 0;
  if (count >= 10000) {
    return `${(count / 10000).toFixed(count >= 100000 ? 0 : 1)}万`;
  }
  return String(count);
}

function formatPostTime(value: string | null | undefined) {
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

function formatDuration(value: number | null | undefined) {
  if (!value) {
    return "视频动态";
  }
  const totalSeconds = Math.max(0, Math.round(value / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function previewUri(detail: PostDetailResponse) {
  const imagePath = detail.media.find((media) => media.image_path)?.image_path;
  const thumbnailPath = detail.videos.find((video) => video.thumbnail_path)?.thumbnail_path;
  return resolveMediaUrl(imagePath ?? thumbnailPath);
}

function mergeViewerState(
  detail: PostDetailResponse,
  stats: PostStats,
  patch: Partial<NonNullable<PostDetailResponse["viewer_state"]>>,
) {
  return {
    ...detail,
    stats,
    viewer_state: {
      is_favorited: Boolean(detail.viewer_state?.is_favorited),
      is_liked: Boolean(detail.viewer_state?.is_liked),
      ...patch,
    },
  };
}

export default function PostDetailScreen() {
  const router = useRouter();
  const { height: windowHeight } = useWindowDimensions();
  const requireAuth = useRequireAuth();
  const { id, focus, streamIds } = useLocalSearchParams<{
    focus?: string;
    id?: string;
    streamIds?: string;
  }>();
  const { accessToken, status, userId } = useAuth();
  const initialPostId = typeof id === "string" ? id : null;
  const postIds = useMemo(() => {
    const ids =
      typeof streamIds === "string"
        ? streamIds.split(",").map((value) => value.trim()).filter(Boolean)
        : [];
    if (initialPostId && !ids.includes(initialPostId)) {
      ids.unshift(initialPostId);
    }
    return ids.length ? ids : initialPostId ? [initialPostId] : [];
  }, [initialPostId, streamIds]);
  const [activePostId, setActivePostId] = useState<string | null>(initialPostId);
  const [detail, setDetail] = useState<PostDetailResponse | null>(() =>
    peekPostDetailPreview(initialPostId),
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [interactionPending, setInteractionPending] = useState<
    "favorite" | "like" | "share" | null
  >(null);
  const [commentsOpen, setCommentsOpen] = useState(focus === "comments");
  const [comments, setComments] = useState<PostCommentRecord[]>([]);
  const [commentsLoading, setCommentsLoading] = useState(false);
  const [commentsLoadingMore, setCommentsLoadingMore] = useState(false);
  const [commentsHasMore, setCommentsHasMore] = useState(false);
  const [commentsError, setCommentsError] = useState<string | null>(null);
  const [commentsPage, setCommentsPage] = useState(1);
  const [commentDraft, setCommentDraft] = useState("");
  const [replyTarget, setReplyTarget] = useState<PostCommentRecord | null>(null);
  const [expandedReplies, setExpandedReplies] = useState<Record<string, PostCommentRecord[]>>({});
  const [replyLoadingIds, setReplyLoadingIds] = useState<string[]>([]);
  const [commentSubmitting, setCommentSubmitting] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [shareLoading, setShareLoading] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const shareAttemptIdsRef = useRef(new Map<string, string>());
  const reportedDetailViewIdsRef = useRef<Set<string>>(new Set());
  const watchStartRef = useRef<number | null>(null);
  const watchAccumRef = useRef<number>(0);
  const lastReportedWatchMsRef = useRef<number>(0);
  const activePostIdRef = useRef<string | null>(initialPostId);
  const detailListRef = useRef<FlatList<string>>(null);

  useEffect(() => {
    activePostIdRef.current = activePostId;
  }, [activePostId]);

  useEffect(() => {
    setActivePostId(initialPostId);
    setDetail(peekPostDetailPreview(initialPostId));
    setError(null);
    setComments([]);
    setCommentsError(null);
    setCommentsPage(1);
    setCommentsHasMore(false);
    setCommentDraft("");
    setReplyTarget(null);
    setExpandedReplies({});
    setShareOpen(false);
    setShareError(null);
    watchStartRef.current = null;
    watchAccumRef.current = 0;
    lastReportedWatchMsRef.current = 0;
  }, [initialPostId]);

  const loadDetail = useCallback(async () => {
    if (!activePostId) {
      setError("缺少 post id，无法打开详情。");
      setDetail(null);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await getReadablePostDetail(activePostId, accessToken);
      primePostDetailPreview(response);
      setDetail(response);
      if (accessToken && !reportedDetailViewIdsRef.current.has(activePostId)) {
        reportedDetailViewIdsRef.current.add(activePostId);
        void reportPostViews(accessToken, {
          items: [{ dwell_time_ms: 0, social_post_id: activePostId, source: "post_detail" }],
        }).catch(() => undefined);
      }
    } catch (loadError) {
      if (loadError instanceof ApiError && loadError.status === 404) {
        setDetail(null);
      }
      setError(detailErrorMessage(loadError));
    } finally {
      setLoading(false);
    }
  }, [accessToken, activePostId]);

  const loadComments = useCallback(async (page = 1) => {
    if (!activePostId) {
      return;
    }
    if (page === 1) {
      setCommentsLoading(true);
    } else {
      setCommentsLoadingMore(true);
    }
    setCommentsError(null);
    try {
      const response = await listPostComments(activePostId, {
        accessToken,
        page,
        pageSize: 50,
      });
      setComments((current) => (page === 1 ? response.items : [...current, ...response.items]));
      setCommentsPage(page);
      setCommentsHasMore(response.items.length === response.page_size);
    } catch (loadError) {
      setCommentsError(detailErrorMessage(loadError));
    } finally {
      setCommentsLoading(false);
      setCommentsLoadingMore(false);
    }
  }, [accessToken, activePostId]);

  const loadMoreComments = useCallback(() => {
    if (!commentsHasMore || commentsLoading || commentsLoadingMore) {
      return;
    }
    void loadComments(commentsPage + 1);
  }, [commentsHasMore, commentsLoading, commentsLoadingMore, commentsPage, loadComments]);

  useFocusEffect(
    useCallback(() => {
      if (status !== "loading") {
        void loadDetail();
      }
    }, [loadDetail, status]),
  );

  useEffect(() => {
    if (status !== "loading") {
      void loadDetail();
    }
  }, [activePostId, loadDetail, status]);

  useEffect(() => {
    if (focus === "comments") {
      setCommentsOpen(true);
    }
  }, [focus]);

  useEffect(() => {
    if (commentsOpen) {
      void loadComments(1);
    }
  }, [commentsOpen, loadComments]);

  const currentVideo = detail?.videos.find((video) => video.upload_status === "uploaded") ?? null;

  const flushWatchTime = useCallback(async () => {
    if (!detail || !currentVideo) {
      return;
    }
    if (watchStartRef.current) {
      watchAccumRef.current += Math.max(0, Date.now() - watchStartRef.current);
      watchStartRef.current = null;
    }
    const payloadMs = watchAccumRef.current;
    if (payloadMs <= lastReportedWatchMsRef.current) {
      return;
    }
    lastReportedWatchMsRef.current = payloadMs;
    if (accessToken) {
      await reportPostViews(accessToken, {
        items: [
          {
            dwell_time_ms: payloadMs,
            social_post_id: detail.post.social_post_id,
            source: "post_detail",
          },
        ],
      }).catch(() => undefined);
    }
  }, [accessToken, detail, currentVideo]);

  useFocusEffect(
    useCallback(() => {
      return () => {
        void flushWatchTime();
      };
    }, [flushWatchTime]),
  );

  const resetPanelStateForPost = useCallback((nextPostId: string) => {
    setDetail(peekPostDetailPreview(nextPostId));
    setError(null);
    setComments([]);
    setCommentsError(null);
    setCommentsPage(1);
    setCommentsHasMore(false);
    setCommentDraft("");
    setReplyTarget(null);
    setExpandedReplies({});
    setShareOpen(false);
    setShareError(null);
    watchStartRef.current = null;
    watchAccumRef.current = 0;
    lastReportedWatchMsRef.current = 0;
  }, []);

  const onStreamViewableItemsChanged = useRef(
    ({ viewableItems }: { viewableItems: ViewToken<string>[] }) => {
      const nextPostId = viewableItems[0]?.item ?? null;
      if (!nextPostId || nextPostId === activePostIdRef.current) {
        return;
      }
      void flushWatchTime();
      setActivePostId(nextPostId);
      resetPanelStateForPost(nextPostId);
    },
  ).current;

  const streamViewabilityConfig = useRef({
    itemVisiblePercentThreshold: 80,
    minimumViewTime: 120,
  }).current;

  const handleVideoPlayingChange = useCallback(
    (isPlaying: boolean) => {
      if (isPlaying) {
        if (!watchStartRef.current) {
          watchStartRef.current = Date.now();
        }
        return;
      }
      void flushWatchTime();
    },
    [flushWatchTime],
  );

  const toggleLike = useCallback(() => {
    if (!detail || !activePostId || interactionPending) {
      return;
    }
    if (!accessToken || !requireAuth("登录后可以点赞这条动态", `/post/${activePostId}`)) {
      return;
    }

    setInteractionPending("like");
    const liked = Boolean(detail.viewer_state?.is_liked);
    const request = liked ? unlikePost(accessToken, activePostId) : likePost(accessToken, activePostId);
    void request
      .then((response) => {
        setDetail((current) =>
          current
            ? mergeViewerState(current, response.stats, { is_liked: response.is_liked })
            : current,
        );
      })
      .catch((actionError) => Alert.alert("点赞失败", detailErrorMessage(actionError)))
      .finally(() => setInteractionPending(null));
  }, [accessToken, activePostId, detail, interactionPending, requireAuth]);

  const toggleFavorite = useCallback(() => {
    if (!detail || !activePostId || interactionPending) {
      return;
    }
    if (!accessToken || !requireAuth("登录后可以收藏这条动态", `/post/${activePostId}`)) {
      return;
    }

    setInteractionPending("favorite");
    const favorited = Boolean(detail.viewer_state?.is_favorited);
    const request = favorited
      ? unfavoritePost(accessToken, activePostId)
      : favoritePost(accessToken, activePostId);
    void request
      .then((response) => {
        setDetail((current) =>
          current
            ? mergeViewerState(current, response.stats, {
                is_favorited: response.is_favorited,
              })
            : current,
        );
      })
      .catch((actionError) => Alert.alert("收藏失败", detailErrorMessage(actionError)))
      .finally(() => setInteractionPending(null));
  }, [accessToken, activePostId, detail, interactionPending, requireAuth]);

  const openShare = useCallback(async () => {
    if (!activePostId || !accessToken || !requireAuth("登录后可以分享这条动态", `/post/${activePostId}`)) {
      return;
    }
    setShareOpen(true);
    setShareLoading(true);
    setShareError(null);
    try {
      const response = await listConversations(accessToken, 1, 50);
      setConversations(response.items);
    } catch (shareLoadError) {
      setShareError(detailErrorMessage(shareLoadError));
    } finally {
      setShareLoading(false);
    }
  }, [accessToken, activePostId, requireAuth]);

  const shareToConversation = useCallback(
    (conversationId: string) => {
      if (!activePostId || !accessToken || interactionPending === "share") {
        return;
      }
      setInteractionPending("share");
      const attemptKey = `${activePostId}:${conversationId}`;
      const clientMessageId = shareAttemptIdsRef.current.get(attemptKey)
        ?? createPostShareClientMessageId(activePostId, conversationId);
      shareAttemptIdsRef.current.set(attemptKey, clientMessageId);
      void sharePost(accessToken, activePostId, {
        clientMessageId,
        conversationId,
        messageText: detail?.post.title ?? "分享了一条网球动态",
      })
        .then((response) => {
          shareAttemptIdsRef.current.delete(attemptKey);
          setDetail((current) => (current ? { ...current, stats: response.stats } : current));
          setShareOpen(false);
          Alert.alert("分享成功", "动态已发送到站内会话。");
        })
        .catch((shareErrorValue) => Alert.alert("分享失败", detailErrorMessage(shareErrorValue)))
        .finally(() => setInteractionPending(null));
    },
    [accessToken, activePostId, detail?.post.title, interactionPending],
  );

  const loadReplies = useCallback(
    async (commentId: string) => {
      if (!activePostId || replyLoadingIds.includes(commentId)) {
        return;
      }
      setReplyLoadingIds((current) => [...current, commentId]);
      try {
        const response = await listPostComments(activePostId, {
          accessToken,
          pageSize: 50,
          parentCommentId: commentId,
        });
        setExpandedReplies((current) => ({ ...current, [commentId]: response.items }));
      } catch (replyError) {
        Alert.alert("回复加载失败", detailErrorMessage(replyError));
      } finally {
        setReplyLoadingIds((current) => current.filter((idValue) => idValue !== commentId));
      }
    },
    [accessToken, activePostId, replyLoadingIds],
  );

  const toggleReplies = useCallback(
    (commentId: string) => {
      if (expandedReplies[commentId]) {
        setExpandedReplies((current) => {
          const next = { ...current };
          delete next[commentId];
          return next;
        });
        return;
      }
      void loadReplies(commentId);
    },
    [expandedReplies, loadReplies],
  );

  const deleteComment = useCallback(
    (comment: PostCommentRecord) => {
      if (!activePostId || !accessToken) {
        return;
      }
      Alert.alert("删除评论", "确定删除这条评论吗？", [
        { text: "取消", style: "cancel" },
        {
          text: "删除",
          style: "destructive",
          onPress: () => {
            void deletePostComment(accessToken, activePostId, comment.comment_id)
              .then((response) => {
                setComments((current) =>
                  current.filter((item) => item.comment_id !== comment.comment_id),
                );
                setExpandedReplies((current) => {
                  const next = { ...current };
                  for (const [parentId, replies] of Object.entries(next)) {
                    next[parentId] = replies.filter(
                      (item) => item.comment_id !== comment.comment_id,
                    );
                  }
                  return next;
                });
                setDetail((current) => (current ? { ...current, stats: response.stats } : current));
              })
              .catch((deleteError) => Alert.alert("删除失败", detailErrorMessage(deleteError)));
          },
        },
      ]);
    },
    [accessToken, activePostId],
  );

  const submitComment = useCallback(() => {
    const content = commentDraft.trim();
    if (!activePostId || commentSubmitting || !content) {
      return;
    }
    if (!accessToken || !requireAuth("登录后可以评论这条动态", `/post/${activePostId}`)) {
      return;
    }

    setCommentSubmitting(true);
    void createPostComment(accessToken, activePostId, content, replyTarget?.comment_id ?? null)
      .then((response) => {
        if (replyTarget) {
          setExpandedReplies((current) => ({
            ...current,
            [replyTarget.comment_id]: [
              ...(current[replyTarget.comment_id] ?? []),
              response.comment,
            ],
          }));
        } else {
          setComments((current) => [...current, response.comment]);
        }
        setCommentDraft("");
        setReplyTarget(null);
        setDetail((current) =>
          current ? { ...current, stats: response.stats } : current,
        );
      })
      .catch((commentError) => Alert.alert("评论失败", detailErrorMessage(commentError)))
      .finally(() => setCommentSubmitting(false));
  }, [accessToken, activePostId, commentDraft, commentSubmitting, replyTarget, requireAuth]);

  const openAuthor = useCallback(() => {
    if (!detail) {
      return;
    }
    router.push({
      pathname: "/user/[id]",
      params: {
        avatar: detail.author.avatar_path ?? "",
        id: detail.author.user_id,
        name: detail.author.nickname,
      },
    });
  }, [detail, router]);

  const openSourceActivity = useCallback(() => {
    const sourceActivityId = detail?.post.source_tennis_activity_id;
    if (!sourceActivityId) {
      return;
    }
    if (!requireAuth("查看来源活动需要登录后继续", `/post/${activePostId ?? ""}`)) {
      return;
    }
    router.push({ pathname: "/activity/[id]", params: { id: sourceActivityId } });
  }, [activePostId, detail?.post.source_tennis_activity_id, requireAuth, router]);

  if ((status === "loading" || loading) && !detail) {
    return <StateScreen loading message="正在加载动态..." onBack={() => router.back()} />;
  }

  if (error && !detail) {
    return (
      <StateScreen
        actionLabel="重试"
        message={error}
        onAction={loadDetail}
        onBack={() => router.back()}
      />
    );
  }

  if (!detail) {
    return null;
  }

  const liked = Boolean(detail.viewer_state?.is_liked);
  const favorited = Boolean(detail.viewer_state?.is_favorited);
  const stats = detail.stats;
  const title = detail.post.title || detail.post.content || "网球动态";
  const content = detail.post.title ? detail.post.content : null;
  const firstVideo = detail.videos[0] ?? null;
  const avatarUri = resolveMediaUrl(detail.author.avatar_path);
  const initialIndex = Math.max(0, postIds.findIndex((value) => value === initialPostId));

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={styles.screen}
    >
      <StatusBar style="light" />
      <FlatList
        data={postIds}
        decelerationRate="fast"
        getItemLayout={(_, index) => ({
          index,
          length: windowHeight,
          offset: windowHeight * index,
        })}
        initialNumToRender={2}
        initialScrollIndex={initialIndex}
        keyExtractor={(itemValue) => itemValue}
        maxToRenderPerBatch={2}
        onViewableItemsChanged={onStreamViewableItemsChanged}
        pagingEnabled
        ref={detailListRef}
        renderItem={({ item: itemPostId }) => (
          <PostStreamPage
            active={itemPostId === activePostId}
            detail={itemPostId === activePostId ? detail : peekPostDetailPreview(itemPostId)}
            height={windowHeight}
            onPlayingChange={itemPostId === activePostId ? handleVideoPlayingChange : undefined}
          />
        )}
        showsVerticalScrollIndicator={false}
        viewabilityConfig={streamViewabilityConfig}
        windowSize={3}
      />

      <SafeAreaView edges={["top", "left", "right"]} pointerEvents="box-none" style={styles.overlay}>
        <View style={styles.topBar}>
          <Pressable
            accessibilityLabel="返回"
            accessibilityRole="button"
            onPress={() => router.back()}
            style={styles.iconButton}
          >
            <Ionicons color={colors.inverse} name="chevron-back" size={24} />
          </Pressable>
          {loading ? (
            <View style={styles.refreshBadge}>
              <ActivityIndicator color={colors.inverse} size="small" />
            </View>
          ) : null}
        </View>

        <View style={styles.actionRail}>
          <ActionButton
            active={liked}
            disabled={interactionPending === "like"}
            icon={liked ? "heart" : "heart-outline"}
            label={formatCount(stats?.like_count)}
            onPress={toggleLike}
            tone="clay"
          />
          <ActionButton
            icon="chatbubble-outline"
            label={formatCount(stats?.comment_count)}
            onPress={() => setCommentsOpen(true)}
          />
          <ActionButton
            active={favorited}
            disabled={interactionPending === "favorite"}
            icon={favorited ? "bookmark" : "bookmark-outline"}
            label={formatCount(stats?.favorite_count)}
            onPress={toggleFavorite}
            tone="gold"
          />
          <ActionButton
            disabled={interactionPending === "share"}
            icon="paper-plane-outline"
            label={formatCount(stats?.share_count)}
            onPress={() => void openShare()}
          />
          {detail.post.source_tennis_activity_id ? (
            <ActionButton
              icon="analytics-outline"
              label="活动"
              onPress={openSourceActivity}
              tone="sky"
            />
          ) : null}
        </View>

        <View style={styles.bottomInfo}>
          <Pressable
            accessibilityLabel={`查看 ${detail.author.nickname} 的主页`}
            accessibilityRole="button"
            onPress={openAuthor}
            style={styles.authorRow}
          >
            <Avatar name={detail.author.nickname} size={38} uri={avatarUri} />
            <View style={styles.authorText}>
              <Text numberOfLines={1} style={styles.authorName}>
                {detail.author.nickname}
              </Text>
              <Text style={styles.metaText}>
                {formatPostTime(detail.post.published_at ?? detail.post.created_at)} ·{" "}
                {formatDuration(firstVideo?.video_duration_ms)}
              </Text>
            </View>
          </Pressable>
          <Text numberOfLines={2} style={styles.title}>
            {title}
          </Text>
          {content ? (
            <Text numberOfLines={3} style={styles.content}>
              {content}
            </Text>
          ) : null}
        </View>
      </SafeAreaView>

      {commentsOpen ? (
        <CommentsPanel
          comments={comments}
          count={stats?.comment_count ?? 0}
          currentUserId={userId}
          draft={commentDraft}
          expandedReplies={expandedReplies}
          error={commentsError}
          hasMore={commentsHasMore}
          loading={commentsLoading}
          loadingMore={commentsLoadingMore}
          onDelete={deleteComment}
          onLoadMore={loadMoreComments}
          onChangeDraft={setCommentDraft}
          onClose={() => setCommentsOpen(false)}
          onLoadReplies={toggleReplies}
          onReply={setReplyTarget}
          onRetry={loadComments}
          onSubmit={submitComment}
          replyTarget={replyTarget}
          submitting={commentSubmitting}
        />
      ) : null}
      {shareOpen ? (
        <SharePanel
          conversations={conversations}
          error={shareError}
          loading={shareLoading}
          onClose={() => setShareOpen(false)}
          onRetry={openShare}
          onShare={shareToConversation}
        />
      ) : null}
    </KeyboardAvoidingView>
  );
}

function PostStreamPage({
  active,
  detail,
  height,
  onPlayingChange,
}: {
  active: boolean;
  detail: PostDetailResponse | null;
  height: number;
  onPlayingChange?: (isPlaying: boolean) => void;
}) {
  if (active && detail && onPlayingChange) {
    return (
      <View style={[styles.streamPage, { height }]}>
        <PostVideoStage detail={detail} onPlayingChange={onPlayingChange} />
      </View>
    );
  }

  const preview = detail ? previewUri(detail) : null;
  return (
    <View style={[styles.streamPage, styles.streamPlaceholder, { height }]}>
      {preview ? (
        <Image contentFit="cover" source={{ uri: preview }} style={styles.stageMedia} />
      ) : (
        <View style={[styles.stageMedia, styles.emptyStage]}>
          <ActivityIndicator color={colors.inverse} />
          <Text style={styles.emptyStageTitle}>正在准备视频</Text>
        </View>
      )}
      <View style={styles.videoScrim} />
    </View>
  );
}

function PostVideoStage({
  detail,
  onPlayingChange,
}: {
  detail: PostDetailResponse;
  onPlayingChange: (isPlaying: boolean) => void;
}) {
  const firstVideo = detail.videos[0] ?? null;
  const preview = previewUri(detail);
  const videoUri =
    firstVideo && firstVideo.upload_status === "uploaded"
      ? resolveMediaUrl(firstVideo.video_path)
      : null;
  const videoTitle = firstVideo?.original_filename ?? firstVideo?.filename ?? undefined;
  const source = useMemo<VideoSource>(() => {
    if (!videoUri) {
      return null;
    }
    return {
      uri: videoUri,
      metadata: {
        title: videoTitle,
      },
    };
  }, [videoTitle, videoUri]);
  const [playing, setPlaying] = useState(Boolean(source));
  const [playerStatus, setPlayerStatus] = useState<"loading" | "ready">(source ? "loading" : "ready");
  const player = useVideoPlayer(source, (instance) => {
    instance.loop = true;
    if (source) {
      instance.play();
    }
  });

  useEffect(() => {
    setPlaying(Boolean(source));
  }, [source]);

  useEffect(() => {
    onPlayingChange(playing);
  }, [onPlayingChange, playing]);

  const togglePlayback = useCallback(() => {
    if (!source) {
      return;
    }
    if (playing) {
      player.pause();
      setPlaying(false);
      return;
    }
    player.play();
    setPlaying(true);
  }, [player, playing, source]);

  const onFirstFrameRender = useCallback(() => {
    setPlayerStatus("ready");
  }, []);

  return (
    <Pressable onPress={togglePlayback} style={styles.stage}>
      {source ? (
        <VideoView
          key={firstVideo?.video_id ?? "post-video"}
          contentFit="cover"
          nativeControls={false}
          onFirstFrameRender={onFirstFrameRender}
          player={player}
          style={styles.stageMedia}
        />
      ) : preview ? (
        <Image contentFit="cover" source={{ uri: preview }} style={styles.stageMedia} />
      ) : (
        <View style={[styles.stageMedia, styles.emptyStage]}>
          <Ionicons color={colors.inverse} name="videocam-outline" size={38} />
          <Text style={styles.emptyStageTitle}>暂无可播放视频</Text>
        </View>
      )}
      <View style={styles.videoScrim} />
      {playerStatus === "loading" && source ? (
        <View style={styles.statusBadge}>
          <ActivityIndicator color={colors.inverse} size="small" />
          <Text style={styles.statusText}>加载中</Text>
        </View>
      ) : null}
      {source && !playing ? (
        <View style={styles.playOverlay}>
          <Ionicons color={colors.inverse} name="play" size={34} />
        </View>
      ) : null}
    </Pressable>
  );
}

function ActionButton({
  active,
  disabled,
  icon,
  label,
  onPress,
  tone = "default",
}: {
  active?: boolean;
  disabled?: boolean;
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
  tone?: "clay" | "default" | "gold" | "sky";
}) {
  const activeColor =
    tone === "clay"
      ? colors.clay
      : tone === "gold"
        ? colors.gold
        : tone === "sky"
          ? colors.sky
          : colors.inverse;
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={[styles.actionButton, disabled && styles.actionButtonDisabled]}
    >
      <View style={styles.actionIcon}>
        <Ionicons color={active ? activeColor : colors.inverse} name={icon} size={28} />
      </View>
      <Text style={styles.actionLabel}>{label}</Text>
    </Pressable>
  );
}

function CommentsPanel({
  comments,
  count,
  currentUserId,
  draft,
  expandedReplies,
  error,
  hasMore,
  loading,
  loadingMore,
  onDelete,
  onLoadMore,
  onLoadReplies,
  onChangeDraft,
  onClose,
  onReply,
  onRetry,
  onSubmit,
  replyTarget,
  submitting,
}: {
  comments: PostCommentRecord[];
  count: number;
  currentUserId: string | null;
  draft: string;
  expandedReplies: Record<string, PostCommentRecord[]>;
  error: string | null;
  hasMore: boolean;
  loading: boolean;
  loadingMore: boolean;
  onDelete: (comment: PostCommentRecord) => void;
  onLoadMore: () => void;
  onLoadReplies: (commentId: string) => void;
  onChangeDraft: (value: string) => void;
  onClose: () => void;
  onReply: (comment: PostCommentRecord | null) => void;
  onRetry: () => void;
  onSubmit: () => void;
  replyTarget: PostCommentRecord | null;
  submitting: boolean;
}) {
  return (
    <SafeAreaView edges={["bottom", "left", "right"]} style={styles.commentsWrap}>
      <View style={styles.commentsHeader}>
        <Text style={styles.commentsTitle}>评论 {formatCount(count)}</Text>
        <Pressable accessibilityLabel="关闭评论" accessibilityRole="button" onPress={onClose}>
          <Ionicons color={colors.inverse} name="close" size={22} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={styles.commentList}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
        style={styles.commentScroll}
      >
        {loading ? (
          <View style={styles.commentState}>
            <ActivityIndicator color={colors.inverse} />
            <Text style={styles.commentStateText}>正在加载评论</Text>
          </View>
        ) : null}
        {error ? (
          <Pressable accessibilityRole="button" onPress={onRetry} style={styles.commentState}>
            <Ionicons color={colors.clay} name="refresh-outline" size={20} />
            <Text style={styles.commentStateText}>{error}</Text>
          </Pressable>
        ) : null}
        {!loading && !error && comments.length === 0 ? (
          <Text style={styles.emptyCommentText}>还没有评论</Text>
        ) : null}
        {comments.map((comment) => (
          <View key={comment.comment_id}>
            <View style={styles.commentRow}>
            <Avatar
              name={comment.author.nickname}
              size={32}
              uri={resolveMediaUrl(comment.author.avatar_path)}
            />
            <View style={styles.commentTextBlock}>
              <View style={styles.commentHeaderLine}>
                <Text numberOfLines={1} style={styles.commentAuthor}>
                  {comment.author.nickname}
                </Text>
                {currentUserId &&
                (currentUserId === comment.author_user_id ||
                  currentUserId === comment.author.user_id) ? (
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => onDelete(comment)}
                  >
                    <Text style={styles.commentActionText}>删除</Text>
                  </Pressable>
                ) : null}
              </View>
              <Text style={styles.commentContent}>{comment.content}</Text>
              <View style={styles.commentActions}>
                <Pressable accessibilityRole="button" onPress={() => onReply(comment)}>
                  <Text style={styles.commentActionText}>回复</Text>
                </Pressable>
                {comment.reply_count > 0 ? (
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => onLoadReplies(comment.comment_id)}
                  >
                    <Text style={styles.commentActionText}>
                      {expandedReplies[comment.comment_id] ? "收起回复" : `查看回复 ${comment.reply_count}`}
                    </Text>
                  </Pressable>
                ) : null}
              </View>
            </View>
            </View>
            {expandedReplies[comment.comment_id]?.map((reply) => (
              <View key={reply.comment_id} style={styles.replyRow}>
                <Avatar
                  name={reply.author.nickname}
                  size={26}
                  uri={resolveMediaUrl(reply.author.avatar_path)}
                />
                <View style={styles.commentTextBlock}>
                  <View style={styles.commentHeaderLine}>
                    <Text numberOfLines={1} style={styles.commentAuthor}>
                      {reply.author.nickname}
                    </Text>
                    {currentUserId && currentUserId === reply.author_user_id ? (
                      <Pressable accessibilityRole="button" onPress={() => onDelete(reply)}>
                        <Text style={styles.commentActionText}>删除</Text>
                      </Pressable>
                    ) : null}
                  </View>
                  <Text style={styles.commentContent}>{reply.content}</Text>
                </View>
              </View>
            ))}
          </View>
        ))}
        {loadingMore ? (
          <View style={styles.commentState}>
            <ActivityIndicator color={colors.inverse} />
            <Text style={styles.commentStateText}>正在加载更多评论</Text>
          </View>
        ) : null}
        {!loading && !error && hasMore ? (
          <Pressable accessibilityRole="button" onPress={onLoadMore} style={styles.loadMoreButton}>
            <Text style={styles.commentActionText}>加载更多评论</Text>
          </Pressable>
        ) : null}
      </ScrollView>

      <View style={styles.commentComposer}>
        {replyTarget ? (
          <View style={styles.replyTargetBar}>
            <Text numberOfLines={1} style={styles.replyTargetText}>
              回复 @{replyTarget.author.nickname}
            </Text>
            <Pressable accessibilityRole="button" onPress={() => onReply(null)}>
              <Ionicons color={colors.inverse} name="close-circle-outline" size={18} />
            </Pressable>
          </View>
        ) : null}
        <View style={styles.composerRow}>
          <TextInput
            onChangeText={onChangeDraft}
            placeholder={replyTarget ? `回复 ${replyTarget.author.nickname}...` : "写评论..."}
            placeholderTextColor="rgba(255,255,255,0.52)"
            returnKeyType="send"
            style={styles.commentInput}
            value={draft}
          />
          <Pressable
            accessibilityRole="button"
            disabled={submitting || !draft.trim()}
            onPress={onSubmit}
            style={[styles.sendButton, (!draft.trim() || submitting) && styles.sendButtonDisabled]}
          >
            {submitting ? (
              <ActivityIndicator color={colors.inverse} size="small" />
            ) : (
              <Ionicons color={colors.inverse} name="send" size={18} />
            )}
          </Pressable>
        </View>
      </View>
    </SafeAreaView>
  );
}

function SharePanel({
  conversations,
  error,
  loading,
  onClose,
  onRetry,
  onShare,
}: {
  conversations: ConversationListItem[];
  error: string | null;
  loading: boolean;
  onClose: () => void;
  onRetry: () => void;
  onShare: (conversationId: string) => void;
}) {
  return (
    <SafeAreaView edges={["bottom", "left", "right"]} style={styles.shareWrap}>
      <View style={styles.commentsHeader}>
        <Text style={styles.commentsTitle}>分享到站内会话</Text>
        <Pressable accessibilityLabel="关闭分享" accessibilityRole="button" onPress={onClose}>
          <Ionicons color={colors.inverse} name="close" size={22} />
        </Pressable>
      </View>
      {loading ? (
        <View style={styles.commentState}>
          <ActivityIndicator color={colors.inverse} />
          <Text style={styles.commentStateText}>正在加载会话</Text>
        </View>
      ) : null}
      {error ? (
        <Pressable accessibilityRole="button" onPress={onRetry} style={styles.commentState}>
          <Ionicons color={colors.clay} name="refresh-outline" size={20} />
          <Text style={styles.commentStateText}>{error}</Text>
        </Pressable>
      ) : null}
      {!loading && !error && conversations.length === 0 ? (
        <Text style={styles.emptyCommentText}>暂无可分享的站内会话</Text>
      ) : null}
      <ScrollView
        contentContainerStyle={styles.commentList}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {conversations.map((item) => {
          const name =
            item.conversation.title ??
            item.other_members.map((member) => member.nickname).join("、") ??
            "站内会话";
          return (
            <Pressable
              accessibilityRole="button"
              key={item.conversation.conversation_id}
              onPress={() => onShare(item.conversation.conversation_id)}
              style={styles.conversationRow}
            >
              <Avatar name={name} size={38} uri={resolveMediaUrl(item.conversation.avatar_path)} />
              <View style={styles.commentTextBlock}>
                <Text numberOfLines={1} style={styles.conversationTitle}>
                  {name}
                </Text>
                <Text numberOfLines={1} style={styles.commentStateText}>
                  {item.conversation.last_message_preview ?? "点击分享这条动态"}
                </Text>
              </View>
              <Ionicons color={colors.inverse} name="paper-plane-outline" size={18} />
            </Pressable>
          );
        })}
      </ScrollView>
    </SafeAreaView>
  );
}

function StateScreen({
  actionLabel,
  loading,
  message,
  onAction,
  onBack,
}: {
  actionLabel?: string;
  loading?: boolean;
  message: string;
  onAction?: () => void;
  onBack: () => void;
}) {
  return (
    <SafeAreaView edges={["top", "bottom", "left", "right"]} style={styles.stateScreen}>
      <StatusBar style="light" />
      <Pressable
        accessibilityLabel="返回"
        accessibilityRole="button"
        onPress={onBack}
        style={styles.iconButton}
      >
        <Ionicons color={colors.inverse} name="chevron-back" size={24} />
      </Pressable>
      <View style={styles.stateBox}>
        {loading ? (
          <ActivityIndicator color={colors.inverse} size="large" />
        ) : (
          <Ionicons color={colors.inverse} name="alert-circle-outline" size={34} />
        )}
        <Text style={styles.stateText}>{message}</Text>
        {actionLabel && onAction ? (
          <Pressable accessibilityRole="button" onPress={onAction} style={styles.retryButton}>
            <Text style={styles.retryButtonText}>{actionLabel}</Text>
          </Pressable>
        ) : null}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: {
    backgroundColor: "#050607",
    flex: 1,
  },
  stage: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "#050607",
  },
  streamPage: {
    backgroundColor: "#050607",
    overflow: "hidden",
    width: "100%",
  },
  streamPlaceholder: {
    position: "relative",
  },
  stageMedia: {
    height: "100%",
    width: "100%",
  },
  emptyStage: {
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
  },
  emptyStageTitle: {
    color: colors.inverse,
    fontSize: 16,
    fontWeight: "900",
  },
  videoScrim: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.18)",
  },
  playOverlay: {
    alignItems: "center",
    backgroundColor: "rgba(0,0,0,0.38)",
    borderRadius: 34,
    height: 68,
    justifyContent: "center",
    left: "50%",
    marginLeft: -34,
    marginTop: -34,
    position: "absolute",
    top: "50%",
    width: 68,
  },
  statusBadge: {
    alignItems: "center",
    backgroundColor: "rgba(0,0,0,0.36)",
    borderRadius: radius.control,
    flexDirection: "row",
    gap: 8,
    left: 16,
    paddingHorizontal: 12,
    paddingVertical: 8,
    position: "absolute",
    top: "48%",
  },
  statusText: {
    color: colors.inverse,
    fontSize: 12,
    fontWeight: "800",
  },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: "space-between",
  },
  topBar: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: 14,
    paddingTop: 8,
  },
  iconButton: {
    alignItems: "center",
    backgroundColor: "rgba(0,0,0,0.32)",
    borderRadius: radius.control,
    height: 42,
    justifyContent: "center",
    width: 42,
  },
  refreshBadge: {
    alignItems: "center",
    backgroundColor: "rgba(0,0,0,0.32)",
    borderRadius: radius.control,
    height: 34,
    justifyContent: "center",
    width: 34,
  },
  actionRail: {
    alignItems: "center",
    bottom: 112,
    gap: 18,
    position: "absolute",
    right: 12,
    width: 58,
  },
  actionButton: {
    alignItems: "center",
    gap: 4,
  },
  actionButtonDisabled: {
    opacity: 0.66,
  },
  actionIcon: {
    alignItems: "center",
    backgroundColor: "rgba(0,0,0,0.28)",
    borderRadius: 24,
    height: 48,
    justifyContent: "center",
    width: 48,
  },
  actionLabel: {
    color: colors.inverse,
    fontSize: 11,
    fontWeight: "900",
    textShadowColor: "rgba(0,0,0,0.72)",
    textShadowOffset: { height: 1, width: 0 },
    textShadowRadius: 5,
  },
  bottomInfo: {
    gap: 9,
    paddingBottom: 26,
    paddingLeft: 16,
    paddingRight: 82,
  },
  authorRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    minHeight: 42,
  },
  authorText: {
    flex: 1,
    gap: 2,
    minWidth: 0,
  },
  authorName: {
    color: colors.inverse,
    fontSize: 15,
    fontWeight: "900",
    textShadowColor: "rgba(0,0,0,0.64)",
    textShadowOffset: { height: 1, width: 0 },
    textShadowRadius: 5,
  },
  metaText: {
    color: "rgba(255,255,255,0.72)",
    fontSize: 12,
    fontWeight: "700",
  },
  title: {
    color: colors.inverse,
    fontSize: 19,
    fontWeight: "900",
    lineHeight: 24,
    textShadowColor: "rgba(0,0,0,0.7)",
    textShadowOffset: { height: 1, width: 0 },
    textShadowRadius: 5,
  },
  content: {
    color: "rgba(255,255,255,0.86)",
    fontSize: 14,
    fontWeight: "700",
    lineHeight: 20,
    textShadowColor: "rgba(0,0,0,0.7)",
    textShadowOffset: { height: 1, width: 0 },
    textShadowRadius: 5,
  },
  commentsWrap: {
    backgroundColor: "rgba(13,15,17,0.97)",
    borderTopLeftRadius: radius.card,
    borderTopRightRadius: radius.card,
    bottom: 0,
    height: "58%",
    left: 0,
    overflow: "hidden",
    paddingHorizontal: 16,
    paddingTop: 14,
    position: "absolute",
    right: 0,
  },
  shareWrap: {
    backgroundColor: "rgba(13,15,17,0.98)",
    borderTopLeftRadius: radius.card,
    borderTopRightRadius: radius.card,
    bottom: 0,
    left: 0,
    maxHeight: "58%",
    paddingHorizontal: 16,
    paddingTop: 14,
    position: "absolute",
    right: 0,
  },
  commentsHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    minHeight: 32,
  },
  commentsTitle: {
    color: colors.inverse,
    fontSize: 16,
    fontWeight: "900",
  },
  commentScroll: {
    flex: 1,
    minHeight: 0,
  },
  commentList: {
    gap: 14,
    paddingBottom: 14,
    paddingTop: 12,
  },
  commentState: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
    justifyContent: "center",
    minHeight: 54,
  },
  commentStateText: {
    color: "rgba(255,255,255,0.72)",
    fontSize: 13,
    fontWeight: "700",
  },
  emptyCommentText: {
    color: "rgba(255,255,255,0.58)",
    fontSize: 13,
    fontWeight: "700",
    paddingVertical: 18,
    textAlign: "center",
  },
  commentRow: {
    flexDirection: "row",
    gap: 10,
  },
  commentTextBlock: {
    flex: 1,
    gap: 4,
    minWidth: 0,
  },
  commentHeaderLine: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    justifyContent: "space-between",
  },
  commentActions: {
    alignItems: "center",
    flexDirection: "row",
    gap: 16,
    marginTop: 3,
  },
  commentActionText: {
    color: "rgba(255,255,255,0.58)",
    fontSize: 12,
    fontWeight: "800",
  },
  replyRow: {
    flexDirection: "row",
    gap: 10,
    marginLeft: 42,
    marginTop: 10,
  },
  loadMoreButton: {
    alignItems: "center",
    minHeight: 42,
    justifyContent: "center",
  },
  commentAuthor: {
    color: "rgba(255,255,255,0.68)",
    fontSize: 12,
    fontWeight: "800",
  },
  commentContent: {
    color: colors.inverse,
    fontSize: 14,
    fontWeight: "700",
    lineHeight: 20,
  },
  commentComposer: {
    alignItems: "stretch",
    borderTopColor: "rgba(255,255,255,0.12)",
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: "column",
    flexShrink: 0,
    paddingTop: 10,
  },
  composerRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  replyTargetBar: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    paddingBottom: 7,
    width: "100%",
  },
  replyTargetText: {
    color: "rgba(255,255,255,0.66)",
    flex: 1,
    fontSize: 12,
    fontWeight: "700",
    marginRight: 10,
  },
  commentInput: {
    backgroundColor: "rgba(255,255,255,0.1)",
    borderRadius: radius.control,
    color: colors.inverse,
    flex: 1,
    fontSize: 14,
    fontWeight: "700",
    minHeight: 42,
    paddingHorizontal: 12,
  },
  sendButton: {
    alignItems: "center",
    backgroundColor: colors.accentDeep,
    borderRadius: radius.control,
    height: 42,
    justifyContent: "center",
    width: 42,
  },
  sendButtonDisabled: {
    opacity: 0.48,
  },
  conversationRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    minHeight: 52,
  },
  conversationTitle: {
    color: colors.inverse,
    fontSize: 14,
    fontWeight: "900",
  },
  stateScreen: {
    backgroundColor: "#050607",
    flex: 1,
    paddingHorizontal: 14,
    paddingTop: 8,
  },
  stateBox: {
    alignItems: "center",
    flex: 1,
    gap: 14,
    justifyContent: "center",
    paddingHorizontal: 20,
  },
  stateText: {
    color: "rgba(255,255,255,0.78)",
    fontSize: 15,
    fontWeight: "700",
    lineHeight: 22,
    textAlign: "center",
  },
  retryButton: {
    backgroundColor: colors.inverse,
    borderRadius: radius.control,
    marginTop: 2,
    paddingHorizontal: 18,
    paddingVertical: 10,
  },
  retryButtonText: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "900",
  },
});
