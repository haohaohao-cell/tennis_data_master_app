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
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { resolveMediaUrl } from "@/api/activityDetail";
import { ApiError } from "@/api/client";
import { clearPostDetailPreview, peekPostDetailPreview, primePostDetailPreview } from "@/api/postDetailPreviewCache";
import {
  createPostComment,
  deletePost,
  favoritePost,
  getReadablePostDetail,
  likePost,
  listPostComments,
  reportPostViews,
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
  const requireAuth = useRequireAuth();
  const { id, focus } = useLocalSearchParams<{ focus?: string; id?: string }>();
  const { accessToken, status, userId } = useAuth();
  const postId = typeof id === "string" ? id : null;
  const [detail, setDetail] = useState<PostDetailResponse | null>(() =>
    peekPostDetailPreview(postId),
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [interactionPending, setInteractionPending] = useState<"favorite" | "like" | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [commentsOpen, setCommentsOpen] = useState(focus === "comments");
  const [comments, setComments] = useState<PostCommentRecord[]>([]);
  const [commentsLoading, setCommentsLoading] = useState(false);
  const [commentsError, setCommentsError] = useState<string | null>(null);
  const [commentDraft, setCommentDraft] = useState("");
  const [commentSubmitting, setCommentSubmitting] = useState(false);
  const reportedDetailViewIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    setDetail(peekPostDetailPreview(postId));
    setError(null);
    setComments([]);
    setCommentsError(null);
    setCommentDraft("");
  }, [postId]);

  const loadDetail = useCallback(async () => {
    if (!postId) {
      setError("缺少 post id，无法打开详情。");
      setDetail(null);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await getReadablePostDetail(postId, accessToken);
      primePostDetailPreview(response);
      setDetail(response);
      if (accessToken && !reportedDetailViewIdsRef.current.has(postId)) {
        reportedDetailViewIdsRef.current.add(postId);
        void reportPostViews(accessToken, {
          items: [{ dwell_time_ms: 0, social_post_id: postId, source: "post_detail" }],
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
  }, [accessToken, postId]);

  const loadComments = useCallback(async () => {
    if (!postId) {
      return;
    }
    setCommentsLoading(true);
    setCommentsError(null);
    try {
      const response = await listPostComments(postId, {
        accessToken,
        pageSize: 50,
      });
      setComments(response.items);
    } catch (loadError) {
      setCommentsError(detailErrorMessage(loadError));
    } finally {
      setCommentsLoading(false);
    }
  }, [accessToken, postId]);

  useFocusEffect(
    useCallback(() => {
      if (status !== "loading") {
        void loadDetail();
      }
    }, [loadDetail, status]),
  );

  useEffect(() => {
    if (focus === "comments") {
      setCommentsOpen(true);
    }
  }, [focus]);

  useEffect(() => {
    if (commentsOpen) {
      void loadComments();
    }
  }, [commentsOpen, loadComments]);

  const toggleLike = useCallback(() => {
    if (!detail || !postId || interactionPending) {
      return;
    }
    if (!accessToken || !requireAuth("登录后可以点赞这条动态", `/post/${postId}`)) {
      return;
    }

    setInteractionPending("like");
    const liked = Boolean(detail.viewer_state?.is_liked);
    const request = liked ? unlikePost(accessToken, postId) : likePost(accessToken, postId);
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
  }, [accessToken, detail, interactionPending, postId, requireAuth]);

  const toggleFavorite = useCallback(() => {
    if (!detail || !postId || interactionPending) {
      return;
    }
    if (!accessToken || !requireAuth("登录后可以收藏这条动态", `/post/${postId}`)) {
      return;
    }

    setInteractionPending("favorite");
    const favorited = Boolean(detail.viewer_state?.is_favorited);
    const request = favorited
      ? unfavoritePost(accessToken, postId)
      : favoritePost(accessToken, postId);
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
  }, [accessToken, detail, interactionPending, postId, requireAuth]);

  const submitComment = useCallback(() => {
    const content = commentDraft.trim();
    if (!postId || commentSubmitting || !content) {
      return;
    }
    if (!accessToken || !requireAuth("登录后可以评论这条动态", `/post/${postId}`)) {
      return;
    }

    setCommentSubmitting(true);
    void createPostComment(accessToken, postId, content)
      .then((response) => {
        setComments((current) => [...current, response.comment]);
        setCommentDraft("");
        setDetail((current) =>
          current ? { ...current, stats: response.stats } : current,
        );
      })
      .catch((commentError) => Alert.alert("评论失败", detailErrorMessage(commentError)))
      .finally(() => setCommentSubmitting(false));
  }, [accessToken, commentDraft, commentSubmitting, postId, requireAuth]);

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
    if (!requireAuth("查看来源活动需要登录后继续", `/post/${postId ?? ""}`)) {
      return;
    }
    router.push({ pathname: "/activity/[id]", params: { id: sourceActivityId } });
  }, [detail?.post.source_tennis_activity_id, postId, requireAuth, router]);

  const confirmDelete = useCallback(() => {
    if (!postId || !accessToken || deleting) {
      return;
    }

    Alert.alert("删除动态", "删除后将无法恢复，确定要删除吗？", [
      { style: "cancel", text: "取消" },
      {
        style: "destructive",
        text: "删除",
        onPress: () => {
          setDeleting(true);
          void deletePost(accessToken, postId)
            .then(() => {
              clearPostDetailPreview(postId);
              router.back();
            })
            .catch((deleteError) => Alert.alert("删除失败", detailErrorMessage(deleteError)))
            .finally(() => setDeleting(false));
        },
      },
    ]);
  }, [accessToken, deleting, postId, router]);

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

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={styles.screen}
    >
      <StatusBar style="light" />
      <PostVideoStage detail={detail} />

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
          {detail.post.author_user_id === userId ? (
            <Pressable
              accessibilityLabel="删除动态"
              accessibilityRole="button"
              disabled={deleting}
              onPress={confirmDelete}
              style={styles.iconButton}
            >
              {deleting ? (
                <ActivityIndicator color={colors.inverse} size="small" />
              ) : (
                <Ionicons color={colors.inverse} name="trash-outline" size={21} />
              )}
            </Pressable>
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
          draft={commentDraft}
          error={commentsError}
          loading={commentsLoading}
          onChangeDraft={setCommentDraft}
          onClose={() => setCommentsOpen(false)}
          onRetry={loadComments}
          onSubmit={submitComment}
          submitting={commentSubmitting}
        />
      ) : null}
    </KeyboardAvoidingView>
  );
}

function PostVideoStage({ detail }: { detail: PostDetailResponse }) {
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
  const player = useVideoPlayer(source, (instance) => {
    instance.loop = true;
    if (source) {
      instance.play();
    }
  });

  useEffect(() => {
    setPlaying(Boolean(source));
  }, [source]);

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

  return (
    <Pressable onPress={togglePlayback} style={styles.stage}>
      {source ? (
        <VideoView
          contentFit="cover"
          nativeControls={false}
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
  draft,
  error,
  loading,
  onChangeDraft,
  onClose,
  onRetry,
  onSubmit,
  submitting,
}: {
  comments: PostCommentRecord[];
  draft: string;
  error: string | null;
  loading: boolean;
  onChangeDraft: (value: string) => void;
  onClose: () => void;
  onRetry: () => void;
  onSubmit: () => void;
  submitting: boolean;
}) {
  return (
    <SafeAreaView edges={["bottom", "left", "right"]} style={styles.commentsWrap}>
      <View style={styles.commentsHeader}>
        <Text style={styles.commentsTitle}>评论 {formatCount(comments.length)}</Text>
        <Pressable accessibilityLabel="关闭评论" accessibilityRole="button" onPress={onClose}>
          <Ionicons color={colors.inverse} name="close" size={22} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={styles.commentList}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
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
          <View key={comment.comment_id} style={styles.commentRow}>
            <Avatar
              name={comment.author.nickname}
              size={32}
              uri={resolveMediaUrl(comment.author.avatar_path)}
            />
            <View style={styles.commentTextBlock}>
              <Text numberOfLines={1} style={styles.commentAuthor}>
                {comment.author.nickname}
              </Text>
              <Text style={styles.commentContent}>{comment.content}</Text>
            </View>
          </View>
        ))}
      </ScrollView>

      <View style={styles.commentComposer}>
        <TextInput
          onChangeText={onChangeDraft}
          placeholder="写评论..."
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
    alignItems: "center",
    borderTopColor: "rgba(255,255,255,0.12)",
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 8,
    paddingTop: 10,
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
