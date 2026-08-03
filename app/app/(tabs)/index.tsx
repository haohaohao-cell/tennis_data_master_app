import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
  type ViewToken,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { resolveMediaUrl } from "@/api/activityDetail";
import { ApiError } from "@/api/client";
import {
  coarseLocationFromActivityLocation,
  getCurrentActivityLocation,
} from "@/api/location";
import { primePostDetailPreview } from "@/api/postDetailPreviewCache";
import {
  favoritePost,
  getPostFeed,
  getPostFeedState,
  likePost,
  reportPostViews,
  type FeedSource,
  type FeedType,
  type PostFeedItem,
  type PostFeedState,
  unfavoritePost,
  unlikePost,
} from "@/api/posts";
import { useAuth } from "@/auth/AuthProvider";
import { useRequireAuth } from "@/auth/useRequireAuth";
import { Avatar, Card, MediaImage, Pill, SegmentedControl } from "@/components/ui";
import { colors, radius, spacing, tabBarHeight } from "@/theme";

const FEED_LIMIT = 12;
const VIEW_REPORT_DELAY_MS = 700;

type FeedTabState = {
  error: string | null;
  fallbackMode: string | null;
  hasMore: boolean;
  items: PostFeedItem[];
  loaded: boolean;
  loading: boolean;
  loadingMore: boolean;
  nextCursor: string | null;
  refreshing: boolean;
  strategyVersion: string | null;
};

type FeedLoadMode = "initial" | "refresh" | "more";

const feedOptions: { label: string; value: FeedType }[] = [
  { label: "推荐", value: "recommended" },
  { label: "关注", value: "following" },
  { label: "附近", value: "nearby" },
];

function createFeedState(): FeedTabState {
  return {
    error: null,
    fallbackMode: null,
    hasMore: true,
    items: [],
    loaded: false,
    loading: false,
    loadingMore: false,
    nextCursor: null,
    refreshing: false,
    strategyVersion: null,
  };
}

function createFeedStates(): Record<FeedType, FeedTabState> {
  return {
    following: createFeedState(),
    nearby: createFeedState(),
    recommended: createFeedState(),
  };
}

function feedErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return "登录后可以查看这一路内容。";
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "内容暂时加载失败，请稍后重试。";
}

function mergeFeedItems(existing: PostFeedItem[], incoming: PostFeedItem[]) {
  const seen = new Set(existing.map((item) => item.post.social_post_id));
  const merged = [...existing];
  for (const item of incoming) {
    if (seen.has(item.post.social_post_id)) {
      continue;
    }
    seen.add(item.post.social_post_id);
    merged.push(item);
  }
  return merged;
}

function updatePostAcrossFeeds(
  current: Record<FeedType, FeedTabState>,
  socialPostId: string,
  update: (item: PostFeedItem) => PostFeedItem,
): Record<FeedType, FeedTabState> {
  return {
    following: {
      ...current.following,
      items: current.following.items.map((item) =>
        item.post.social_post_id === socialPostId ? update(item) : item,
      ),
    },
    nearby: {
      ...current.nearby,
      items: current.nearby.items.map((item) =>
        item.post.social_post_id === socialPostId ? update(item) : item,
      ),
    },
    recommended: {
      ...current.recommended,
      items: current.recommended.items.map((item) =>
        item.post.social_post_id === socialPostId ? update(item) : item,
      ),
    },
  };
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

function sourceLabel(source: FeedSource) {
  const labels: Record<FeedSource, string> = {
    following: "关注",
    nearby: "附近",
    nearby_city_fallback: "同城",
    nearby_region_fallback: "同区域",
    recommended: "推荐",
  };
  return labels[source] ?? "Feed";
}

function visibilityLabel(value: PostFeedItem["post"]["visibility"]) {
  const labels: Record<PostFeedItem["post"]["visibility"], string> = {
    followers: "关注可见",
    friends: "好友可见",
    private: "私密",
    public: "公开",
    specified_users: "指定可见",
  };
  return labels[value] ?? value;
}

function previewUri(item: PostFeedItem) {
  const mediaImage = item.media.find((media) => media.image_path)?.image_path;
  const thumbnail = item.videos.find((video) => video.thumbnail_path)?.thumbnail_path;
  return resolveMediaUrl(mediaImage ?? thumbnail);
}

export default function HomeScreen() {
  const router = useRouter();
  const requireAuth = useRequireAuth();
  const { accessToken, isAuthenticated, status } = useAuth();
  const [activeFeed, setActiveFeed] = useState<FeedType>("recommended");
  const [feedStates, setFeedStates] = useState<Record<FeedType, FeedTabState>>(createFeedStates);
  const [feedState, setFeedState] = useState<PostFeedState | null>(null);
  const [nearbyDraft, setNearbyDraft] = useState({ city: "", region: "" });
  const [nearbyQuery, setNearbyQuery] = useState({ city: "", region: "" });
  const [nearbyLocating, setNearbyLocating] = useState(false);
  const [pendingInteractionIds, setPendingInteractionIds] = useState<string[]>([]);
  const pendingViewIdsRef = useRef<Set<string>>(new Set());
  const reportedViewIdsRef = useRef<Set<string>>(new Set());
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const canReportViewsRef = useRef(false);
  const flushViewsRef = useRef<() => void>(() => {});

  const currentState = feedStates[activeFeed];
  const nearbyHasQuery = Boolean(nearbyQuery.city || nearbyQuery.region);

  useEffect(() => {
    canReportViewsRef.current = Boolean(accessToken && isAuthenticated);
  }, [accessToken, isAuthenticated]);

  useEffect(() => {
    getPostFeedState()
      .then(setFeedState)
      .catch(() => setFeedState(null));
  }, []);

  useEffect(() => {
    setFeedStates(createFeedStates());
    pendingViewIdsRef.current.clear();
    reportedViewIdsRef.current.clear();
  }, [accessToken]);

  const updateFeedState = useCallback(
    (
      feedType: FeedType,
      updater: FeedTabState | ((current: FeedTabState) => FeedTabState),
    ) => {
      setFeedStates((current) => ({
        ...current,
        [feedType]:
          typeof updater === "function" ? updater(current[feedType]) : updater,
      }));
    },
    [],
  );

  const loadFeed = useCallback(
    async (feedType: FeedType, mode: FeedLoadMode = "initial") => {
      if (status === "loading") {
        return;
      }
      if (feedType === "following" && !accessToken) {
        updateFeedState(feedType, {
          ...createFeedState(),
          hasMore: false,
          loaded: true,
        });
        return;
      }
      if (feedType === "nearby" && !nearbyQuery.city && !nearbyQuery.region) {
        updateFeedState(feedType, {
          ...createFeedState(),
          fallbackMode: "location_required",
          hasMore: false,
          loaded: true,
        });
        return;
      }

      const previous = feedStates[feedType];
      if (mode === "more" && (!previous.hasMore || !previous.nextCursor || previous.loadingMore)) {
        return;
      }
      if (previous.loading || previous.refreshing || previous.loadingMore) {
        return;
      }

      updateFeedState(feedType, (current) => ({
        ...current,
        error: null,
        loading: mode === "initial",
        loadingMore: mode === "more",
        refreshing: mode === "refresh",
      }));

      try {
        const response = await getPostFeed(feedType, {
          accessToken,
          city: feedType === "nearby" ? nearbyQuery.city || null : null,
          cursor: mode === "more" ? previous.nextCursor : null,
          limit: FEED_LIMIT,
          region: feedType === "nearby" ? nearbyQuery.region || null : null,
        });
        updateFeedState(feedType, (current) => ({
          ...current,
          error: null,
          fallbackMode: response.fallback_mode,
          hasMore: response.has_more,
          items:
            mode === "more"
              ? mergeFeedItems(current.items, response.items)
              : response.items,
          loaded: true,
          loading: false,
          loadingMore: false,
          nextCursor: response.next_cursor,
          refreshing: false,
          strategyVersion: response.strategy_version,
        }));
      } catch (loadError) {
        updateFeedState(feedType, (current) => ({
          ...current,
          error: feedErrorMessage(loadError),
          loaded: current.loaded || current.items.length > 0,
          loading: false,
          loadingMore: false,
          refreshing: false,
        }));
      }
    },
    [accessToken, feedStates, nearbyQuery.city, nearbyQuery.region, status, updateFeedState],
  );

  useEffect(() => {
    if (status === "loading") {
      return;
    }
    if (!currentState.loaded && !currentState.loading) {
      void loadFeed(activeFeed);
    }
  }, [activeFeed, currentState.loaded, currentState.loading, loadFeed, status]);

  const flushViewReports = useCallback(async () => {
    if (!accessToken || !isAuthenticated) {
      pendingViewIdsRef.current.clear();
      return;
    }
    const ids = Array.from(pendingViewIdsRef.current).filter(
      (id) => !reportedViewIdsRef.current.has(id),
    );
    pendingViewIdsRef.current.clear();
    if (!ids.length) {
      return;
    }

    try {
      const response = await reportPostViews(accessToken, {
        items: ids.map((socialPostId) => ({
          dwell_time_ms: 0,
          social_post_id: socialPostId,
          source: "home_feed",
        })),
      });
      for (const id of response.accepted_post_ids) {
        reportedViewIdsRef.current.add(id);
      }
    } catch {
      for (const id of ids) {
        if (!reportedViewIdsRef.current.has(id)) {
          pendingViewIdsRef.current.add(id);
        }
      }
    }
  }, [accessToken, isAuthenticated]);

  useEffect(() => {
    flushViewsRef.current = () => {
      void flushViewReports();
    };
  }, [flushViewReports]);

  useEffect(() => {
    return () => {
      if (flushTimerRef.current) {
        clearTimeout(flushTimerRef.current);
      }
    };
  }, []);

  const scheduleViewFlush = useCallback(() => {
    if (flushTimerRef.current) {
      clearTimeout(flushTimerRef.current);
    }
    if (pendingViewIdsRef.current.size >= 5) {
      flushViewsRef.current();
      return;
    }
    flushTimerRef.current = setTimeout(() => {
      flushViewsRef.current();
    }, VIEW_REPORT_DELAY_MS);
  }, []);

  const onViewableItemsChanged = useRef(
    ({ viewableItems }: { viewableItems: ViewToken<PostFeedItem>[] }) => {
      if (!canReportViewsRef.current) {
        return;
      }
      let queued = false;
      for (const token of viewableItems) {
        const id = token.item?.post.social_post_id;
        if (!id || reportedViewIdsRef.current.has(id)) {
          continue;
        }
        pendingViewIdsRef.current.add(id);
        queued = true;
      }
      if (queued) {
        scheduleViewFlush();
      }
    },
  ).current;

  const viewabilityConfig = useRef({
    itemVisiblePercentThreshold: 60,
    minimumViewTime: 450,
  }).current;

  const handleSubmitNearby = useCallback(async () => {
    setNearbyLocating(true);
    const nextLocation = await getCurrentActivityLocation();
    setNearbyLocating(false);
    const { city, region } = coarseLocationFromActivityLocation(nextLocation.location);
    setNearbyDraft({ city, region });
    if (!city && !region) {
      Alert.alert("无法获取附近范围", nextLocation.message ?? "附近内容只使用城市或地区，不读取精确坐标。");
      return;
    }
    setNearbyQuery({ city, region });
    updateFeedState("nearby", createFeedState());
    setActiveFeed("nearby");
  }, [updateFeedState]);

  const openPost = useCallback(
    (item: PostFeedItem, focusComments = false) => {
      primePostDetailPreview(item);
      router.push({
        pathname: "/post/[id]",
        params: focusComments
          ? { focus: "comments", id: item.post.social_post_id }
          : { id: item.post.social_post_id },
      });
    },
    [router],
  );

  const handleOpenAuthor = useCallback(
    (item: PostFeedItem) => {
      router.push({
        pathname: "/user/[id]",
        params: {
          avatar: item.author.avatar_path ?? "",
          id: item.author.user_id,
          name: item.author.nickname,
        },
      });
    },
    [router],
  );

  const handleToggleLike = useCallback(
    (item: PostFeedItem) => {
      const socialPostId = item.post.social_post_id;
      if (
        !accessToken ||
        !requireAuth("登录后可以点赞这条动态", `/post/${socialPostId}`) ||
        pendingInteractionIds.includes(socialPostId)
      ) {
        return;
      }

      setPendingInteractionIds((current) => [...current, socialPostId]);
      const liked = Boolean(item.viewer_state?.is_liked);
      const request = liked
        ? unlikePost(accessToken, socialPostId)
        : likePost(accessToken, socialPostId, "home_feed");
      void request
        .then((response) => {
          setFeedStates((current) =>
            updatePostAcrossFeeds(current, socialPostId, (feedItem) => ({
              ...feedItem,
              stats: response.stats,
              viewer_state: {
                is_favorited: Boolean(feedItem.viewer_state?.is_favorited),
                is_liked: response.is_liked,
              },
            })),
          );
        })
        .catch((error) => Alert.alert("点赞失败", feedErrorMessage(error)))
        .finally(() => {
          setPendingInteractionIds((current) => current.filter((id) => id !== socialPostId));
        });
    },
    [accessToken, pendingInteractionIds, requireAuth],
  );

  const handleToggleFavorite = useCallback(
    (item: PostFeedItem) => {
      const socialPostId = item.post.social_post_id;
      if (
        !accessToken ||
        !requireAuth("登录后可以收藏这条动态", `/post/${socialPostId}`) ||
        pendingInteractionIds.includes(socialPostId)
      ) {
        return;
      }

      setPendingInteractionIds((current) => [...current, socialPostId]);
      const favorited = Boolean(item.viewer_state?.is_favorited);
      const request = favorited
        ? unfavoritePost(accessToken, socialPostId)
        : favoritePost(accessToken, socialPostId, "home_feed");
      void request
        .then((response) => {
          setFeedStates((current) =>
            updatePostAcrossFeeds(current, socialPostId, (feedItem) => ({
              ...feedItem,
              stats: response.stats,
              viewer_state: {
                is_favorited: response.is_favorited,
                is_liked: Boolean(feedItem.viewer_state?.is_liked),
              },
            })),
          );
        })
        .catch((error) => Alert.alert("收藏失败", feedErrorMessage(error)))
        .finally(() => {
          setPendingInteractionIds((current) => current.filter((id) => id !== socialPostId));
        });
    },
    [accessToken, pendingInteractionIds, requireAuth],
  );

  const handleOpenSourceActivity = useCallback(
    (item: PostFeedItem) => {
      const activityId = item.post.source_tennis_activity_id;
      if (!activityId) {
        Alert.alert("暂无来源活动", "这条动态没有关联训练或比赛记录。");
        return;
      }
      if (!requireAuth("查看来源活动需要登录后继续")) {
        return;
      }
      router.push({ pathname: "/activity/[id]", params: { id: activityId } });
    },
    [requireAuth, router],
  );

  const renderItem = useCallback(
    ({ item }: { item: PostFeedItem }) => (
      <PostCard
        item={item}
        interactionPending={pendingInteractionIds.includes(item.post.social_post_id)}
        onOpen={() => openPost(item)}
        onOpenAuthor={() => handleOpenAuthor(item)}
        onOpenComments={() => openPost(item, true)}
        onOpenSource={() => handleOpenSourceActivity(item)}
        onToggleFavorite={() => handleToggleFavorite(item)}
        onToggleLike={() => handleToggleLike(item)}
      />
    ),
    [
      handleOpenAuthor,
      handleOpenSourceActivity,
      handleToggleFavorite,
      handleToggleLike,
      openPost,
      pendingInteractionIds,
    ],
  );

  const listHeader = useMemo(
    () =>
      activeFeed === "nearby" ? (
        <NearbyLocationPanel
          draft={nearbyDraft}
          feedState={feedState}
          hasQuery={nearbyHasQuery}
          locating={nearbyLocating}
          onSubmit={handleSubmitNearby}
          query={nearbyQuery}
        />
      ) : null,
    [activeFeed, feedState, handleSubmitNearby, nearbyDraft, nearbyHasQuery, nearbyLocating, nearbyQuery],
  );

  return (
    <SafeAreaView edges={["top", "left", "right"]} style={styles.safeArea}>
      <View style={styles.header}>
        <SegmentedControl options={feedOptions} value={activeFeed} onChange={setActiveFeed} />
      </View>
      <FlatList
        contentContainerStyle={[
          styles.listContent,
          currentState.items.length === 0 && styles.listContentEmpty,
        ]}
        data={currentState.items}
        keyExtractor={(item) => item.post.social_post_id}
        ListEmptyComponent={
          <FeedEmptyState
            activeFeed={activeFeed}
            error={currentState.error}
            isAuthenticated={isAuthenticated}
            isLoading={status === "loading" || currentState.loading}
            nearbyHasQuery={nearbyHasQuery}
            onLogin={() => router.push("/login")}
            onRetry={() => void loadFeed(activeFeed, "refresh")}
          />
        }
        ListFooterComponent={
          <FeedFooter
            error={currentState.items.length ? currentState.error : null}
            hasItems={currentState.items.length > 0}
            hasMore={currentState.hasMore}
            isLoadingMore={currentState.loadingMore}
            onRetry={() => void loadFeed(activeFeed, "more")}
          />
        }
        ListHeaderComponent={listHeader}
        onEndReached={() => void loadFeed(activeFeed, "more")}
        onEndReachedThreshold={0.45}
        onRefresh={() => void loadFeed(activeFeed, "refresh")}
        onViewableItemsChanged={onViewableItemsChanged}
        refreshing={currentState.refreshing}
        renderItem={renderItem}
        showsVerticalScrollIndicator={false}
        viewabilityConfig={viewabilityConfig}
      />
    </SafeAreaView>
  );
}

function NearbyLocationPanel({
  draft,
  feedState,
  hasQuery,
  locating,
  onSubmit,
  query,
}: {
  draft: { city: string; region: string };
  feedState: PostFeedState | null;
  hasQuery: boolean;
  locating: boolean;
  onSubmit: () => void;
  query: { city: string; region: string };
}) {
  return (
    <Card style={styles.locationPanel}>
      <View style={styles.locationHeader}>
        <View style={styles.locationIcon}>
          <Ionicons color={colors.ink} name="location-outline" size={19} />
        </View>
        <View style={styles.locationCopy}>
          <Text style={styles.locationTitle}>附近动态</Text>
          <Text style={styles.locationText}>
            {feedState?.nearby_location_privacy ?? "仅使用城市或地区筛选动态"}
          </Text>
        </View>
      </View>
      <View style={styles.locationInputs}>
        <View style={styles.locationSummary}>
          <Text style={styles.locationSummaryTitle}>
            {[draft.city, draft.region].filter(Boolean).join(" / ") || "未获取当前位置"}
          </Text>
          <Text style={styles.locationSummaryText}>只使用城市和区筛选附近动态</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          disabled={locating}
          onPress={onSubmit}
          style={[styles.locationButton, locating && styles.disabledButton]}
        >
          {locating ? (
            <ActivityIndicator color={colors.inverse} size="small" />
          ) : (
            <Ionicons color={colors.inverse} name="locate-outline" size={17} />
          )}
        </Pressable>
      </View>
      {hasQuery ? (
        <Text style={styles.activeLocationText}>
          当前范围：{[query.city, query.region].filter(Boolean).join(" / ")}
        </Text>
      ) : null}
    </Card>
  );
}

function FeedEmptyState({
  activeFeed,
  error,
  isAuthenticated,
  isLoading,
  nearbyHasQuery,
  onLogin,
  onRetry,
}: {
  activeFeed: FeedType;
  error: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  nearbyHasQuery: boolean;
  onLogin: () => void;
  onRetry: () => void;
}) {
  if (isLoading) {
    return (
      <StatePanel
        icon="tennisball-outline"
        message="正在加载最新动态..."
        title="加载中"
      />
    );
  }

  if (activeFeed === "following" && !isAuthenticated) {
    return (
      <StatePanel
        actionLabel="去登录"
        icon="people-outline"
        message="登录后可以看到你关注球友发布的动态。"
        onAction={onLogin}
        title="关注内容需要登录"
      />
    );
  }

  if (activeFeed === "nearby" && !nearbyHasQuery) {
    return (
      <StatePanel
        icon="map-outline"
        message="选择城市或地区后，首页只会查询带公开位置的动态。"
        title="选择附近范围"
      />
    );
  }

  if (error) {
    return (
      <StatePanel
        actionLabel="重试"
        icon="refresh-outline"
        message={error}
        onAction={onRetry}
        title="加载失败"
      />
    );
  }

  return (
    <StatePanel
      icon="file-tray-outline"
      message="已经没有更多动态。"
      title="暂无更多内容"
    />
  );
}

function FeedFooter({
  error,
  hasItems,
  hasMore,
  isLoadingMore,
  onRetry,
}: {
  error: string | null;
  hasItems: boolean;
  hasMore: boolean;
  isLoadingMore: boolean;
  onRetry: () => void;
}) {
  if (!hasItems) {
    return null;
  }
  if (isLoadingMore) {
    return (
      <View style={styles.footer}>
        <ActivityIndicator color={colors.accentDeep} />
      </View>
    );
  }
  if (error) {
    return (
      <Pressable accessibilityRole="button" onPress={onRetry} style={styles.footer}>
        <Text style={styles.footerText}>加载失败，点此重试</Text>
      </Pressable>
    );
  }
  if (!hasMore) {
    return (
      <View style={styles.footer}>
        <Text style={styles.footerText}>没有更多新动态</Text>
      </View>
    );
  }
  return <View style={styles.footerSpacer} />;
}

function StatePanel({
  actionLabel,
  icon,
  message,
  onAction,
  title,
}: {
  actionLabel?: string;
  icon: keyof typeof Ionicons.glyphMap;
  message: string;
  onAction?: () => void;
  title: string;
}) {
  return (
    <Card style={styles.statePanel}>
      <View style={styles.stateIcon}>
        <Ionicons color={colors.inkSoft} name={icon} size={23} />
      </View>
      <Text style={styles.stateTitle}>{title}</Text>
      <Text style={styles.stateMessage}>{message}</Text>
      {actionLabel && onAction ? (
        <Pressable accessibilityRole="button" onPress={onAction} style={styles.stateButton}>
          <Text style={styles.stateButtonText}>{actionLabel}</Text>
        </Pressable>
      ) : null}
    </Card>
  );
}

function PostCard({
  interactionPending,
  item,
  onOpen,
  onOpenAuthor,
  onOpenComments,
  onOpenSource,
  onToggleFavorite,
  onToggleLike,
}: {
  interactionPending: boolean;
  item: PostFeedItem;
  onOpen: () => void;
  onOpenAuthor: () => void;
  onOpenComments: () => void;
  onOpenSource: () => void;
  onToggleFavorite: () => void;
  onToggleLike: () => void;
}) {
  const preview = previewUri(item);
  const firstVideo = item.videos[0];
  const stats = item.stats;
  const hasSourceActivity = Boolean(item.post.source_tennis_activity_id);
  const liked = Boolean(item.viewer_state?.is_liked);
  const favorited = Boolean(item.viewer_state?.is_favorited);

  return (
    <Card style={styles.postCard}>
      <View style={styles.postHeader}>
        <Pressable
          accessibilityLabel={`查看 ${item.author.nickname} 的主页`}
          accessibilityRole="button"
          onPress={onOpenAuthor}
          style={styles.authorBlock}
        >
          <Avatar
            name={item.author.nickname}
            size={42}
            uri={resolveMediaUrl(item.author.avatar_path)}
          />
          <View style={styles.authorTextBlock}>
            <View style={styles.authorNameLine}>
              <Text numberOfLines={1} style={styles.authorName}>
                {item.author.nickname}
              </Text>
              <Pill>{sourceLabel(item.feed_source)}</Pill>
            </View>
            <Text style={styles.postMeta}>
              {formatPostTime(item.post.published_at ?? item.post.created_at)} ·{" "}
              {visibilityLabel(item.post.visibility)}
            </Text>
          </View>
        </Pressable>
      </View>

      <Pressable accessibilityRole="button" onPress={onOpen} style={styles.openPostArea}>
        {preview ? (
          <MediaImage ratio={1.46} source={{ uri: preview }} />
        ) : (
          <View style={styles.videoPlaceholder}>
            <Ionicons color={colors.accentDeep} name="videocam-outline" size={30} />
            <Text style={styles.videoPlaceholderTitle}>
              {firstVideo?.original_filename || item.media[0]?.caption || "视频动态"}
            </Text>
            <Text style={styles.videoPlaceholderText}>
              {formatDuration(firstVideo?.video_duration_ms)}
            </Text>
          </View>
        )}

        {item.post.title ? <Text style={styles.postTitle}>{item.post.title}</Text> : null}
        {item.post.content ? <Text style={styles.postContent}>{item.post.content}</Text> : null}
      </Pressable>

      <View style={styles.postActions}>
        <StatItem
          active={liked}
          disabled={interactionPending}
          icon={liked ? "heart" : "heart-outline"}
          label="赞"
          onPress={onToggleLike}
          value={formatCount(stats?.like_count)}
        />
        <StatItem
          icon="chatbubble-outline"
          label="评"
          onPress={onOpenComments}
          value={formatCount(stats?.comment_count)}
        />
        <StatItem
          active={favorited}
          disabled={interactionPending}
          icon={favorited ? "bookmark" : "bookmark-outline"}
          label="藏"
          onPress={onToggleFavorite}
          value={formatCount(stats?.favorite_count)}
        />
        <StatItem icon="eye-outline" label="看" value={formatCount(stats?.view_count)} />
        {hasSourceActivity ? (
          <Pressable
            accessibilityRole="button"
            onPress={onOpenSource}
            style={styles.sourceButton}
          >
            <Ionicons color={colors.sky} name="analytics-outline" size={18} />
            <Text style={styles.sourceButtonText}>来源活动</Text>
          </Pressable>
        ) : null}
      </View>
    </Card>
  );
}

function StatItem({
  active,
  disabled,
  icon,
  label,
  onPress,
  value,
}: {
  active?: boolean;
  disabled?: boolean;
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress?: () => void;
  value: string;
}) {
  const content = (
    <>
      <Ionicons color={active ? colors.clay : colors.inkSoft} name={icon} size={18} />
      <Text style={[styles.statText, active && styles.statTextActive]}>
        {value}
        <Text style={[styles.statLabel, active && styles.statLabelActive]}> {label}</Text>
      </Text>
    </>
  );

  if (onPress) {
    return (
      <Pressable
        accessibilityRole="button"
        disabled={disabled}
        onPress={onPress}
        style={[styles.statItem, disabled && styles.statItemDisabled]}
      >
        {content}
      </Pressable>
    );
  }

  return (
    <View style={styles.statItem}>
      {content}
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    backgroundColor: colors.background,
    flex: 1,
  },
  header: {
    paddingBottom: 10,
    paddingHorizontal: spacing.pageX,
    paddingTop: 8,
  },
  listContent: {
    gap: 14,
    paddingBottom: tabBarHeight + 30,
    paddingHorizontal: spacing.pageX,
  },
  listContentEmpty: {
    flexGrow: 1,
  },
  locationPanel: {
    gap: 12,
    marginBottom: 2,
    padding: 12,
  },
  locationHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
  },
  locationIcon: {
    alignItems: "center",
    backgroundColor: colors.skySoft,
    borderRadius: radius.control,
    height: 38,
    justifyContent: "center",
    width: 38,
  },
  locationCopy: {
    flex: 1,
    gap: 2,
  },
  locationTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "800",
  },
  locationText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "600",
    lineHeight: 17,
  },
  locationInputs: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  locationSummary: {
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    flex: 1,
    gap: 3,
    justifyContent: "center",
    minHeight: 42,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  locationSummaryText: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "700",
  },
  locationSummaryTitle: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "900",
  },
  locationButton: {
    alignItems: "center",
    backgroundColor: colors.accentDeep,
    borderRadius: radius.control,
    height: 42,
    justifyContent: "center",
    width: 42,
  },
  disabledButton: {
    opacity: 0.52,
  },
  activeLocationText: {
    color: colors.inkSoft,
    fontSize: 12,
    fontWeight: "700",
  },
  postCard: {
    gap: 12,
    padding: 12,
  },
  openPostArea: {
    gap: 12,
  },
  postHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    justifyContent: "space-between",
  },
  authorBlock: {
    alignItems: "center",
    flex: 1,
    flexDirection: "row",
    gap: 10,
    minWidth: 0,
  },
  authorTextBlock: {
    flex: 1,
    minWidth: 0,
  },
  authorNameLine: {
    alignItems: "center",
    flexDirection: "row",
    gap: 7,
    minWidth: 0,
  },
  authorName: {
    color: colors.ink,
    flexShrink: 1,
    fontSize: 15,
    fontWeight: "800",
  },
  postMeta: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "600",
    marginTop: 3,
  },
  videoPlaceholder: {
    alignItems: "center",
    aspectRatio: 1.46,
    backgroundColor: colors.accentSoft,
    borderColor: "#D9E7EF",
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    justifyContent: "center",
    padding: 16,
  },
  videoPlaceholderTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "800",
    marginTop: 10,
    maxWidth: "82%",
    textAlign: "center",
  },
  videoPlaceholderText: {
    color: colors.inkSoft,
    fontSize: 12,
    fontWeight: "700",
    marginTop: 4,
  },
  postTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "800",
    lineHeight: 22,
  },
  postContent: {
    color: colors.inkSoft,
    fontSize: 14,
    fontWeight: "600",
    lineHeight: 21,
  },
  postActions: {
    alignItems: "center",
    borderTopColor: colors.line,
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
    paddingTop: 10,
  },
  statItem: {
    alignItems: "center",
    flexDirection: "row",
    gap: 4,
    minHeight: 28,
  },
  statText: {
    color: colors.inkSoft,
    fontSize: 12,
    fontWeight: "800",
  },
  statTextActive: {
    color: colors.clay,
  },
  statLabel: {
    color: colors.muted,
    fontWeight: "700",
  },
  statLabelActive: {
    color: colors.clay,
  },
  statItemDisabled: {
    opacity: 0.62,
  },
  sourceButton: {
    alignItems: "center",
    flexDirection: "row",
    gap: 5,
    marginLeft: "auto",
    minHeight: 28,
  },
  sourceButtonText: {
    color: colors.sky,
    fontSize: 12,
    fontWeight: "800",
  },
  statePanel: {
    alignItems: "center",
    gap: 8,
    marginTop: 18,
    padding: 18,
  },
  stateIcon: {
    alignItems: "center",
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.control,
    height: 42,
    justifyContent: "center",
    width: 42,
  },
  stateTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "800",
    marginTop: 2,
  },
  stateMessage: {
    color: colors.inkSoft,
    fontSize: 13,
    fontWeight: "600",
    lineHeight: 19,
    textAlign: "center",
  },
  stateButton: {
    backgroundColor: colors.accentDeep,
    borderRadius: radius.control,
    marginTop: 4,
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  stateButtonText: {
    color: colors.inverse,
    fontSize: 13,
    fontWeight: "800",
  },
  footer: {
    alignItems: "center",
    minHeight: 44,
    justifyContent: "center",
    paddingVertical: 6,
  },
  footerSpacer: {
    height: 16,
  },
  footerText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
});
