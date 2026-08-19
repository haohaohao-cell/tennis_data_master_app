import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect } from "@react-navigation/native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, View } from "react-native";

import { resolveMediaUrl } from "@/api/activityDetail";
import { ApiError } from "@/api/client";
import {
  followUser,
  getFollowList,
  unfollowUser,
  type FollowListItem,
  type FollowListKind,
} from "@/api/social";
import { useAuth } from "@/auth/AuthProvider";
import { Avatar, ScrollPage, TopBar } from "@/components/ui";
import { colors, radius } from "@/theme";

type IconName = keyof typeof Ionicons.glyphMap;

const LIST_META: Record<
  FollowListKind,
  { title: string; subtitle: string; emptyTitle: string; emptySubtitle: string }
> = {
  followers: {
    title: "粉丝",
    subtitle: "关注你的球友",
    emptyTitle: "还没有粉丝",
    emptySubtitle: "其他球友关注你后会显示在这里",
  },
  following: {
    title: "关注",
    subtitle: "你关注的球友",
    emptyTitle: "还没有关注",
    emptySubtitle: "关注感兴趣的球友后会显示在这里",
  },
  friends: {
    title: "互关",
    subtitle: "互相关注的球友",
    emptyTitle: "还没有互关",
    emptySubtitle: "互相关注后会成为球友，显示在这里",
  },
};

function normalizeKind(value: string | undefined): FollowListKind {
  if (value === "followers" || value === "following" || value === "friends") {
    return value;
  }
  return "following";
}

function listErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 0) {
      return "无法连接服务器，请确认后端可用。";
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "暂时无法加载用户列表。";
}

function shortUserId(userId: string) {
  return userId.length > 12 ? `${userId.slice(0, 8)}...${userId.slice(-4)}` : userId;
}

function isFollowingInList(kind: FollowListKind, isFriend: boolean) {
  return kind === "following" || kind === "friends" || (kind === "followers" && isFriend);
}

function followActionLabel(kind: FollowListKind, isFriend: boolean) {
  if (kind === "friends") {
    return "已互关";
  }
  if (kind === "following") {
    return isFriend ? "已互关" : "已关注";
  }
  return isFriend ? "已互关" : "回关";
}

function followActionIcon(kind: FollowListKind, isFriend: boolean): IconName {
  if (kind === "friends") {
    return "people";
  }
  if (kind === "following") {
    return isFriend ? "people" : "checkmark";
  }
  return isFriend ? "people" : "person-add";
}

function dedupeById(items: FollowListItem[]) {
  return Array.from(new Map(items.map((item) => [item.user.user_id, item])).values());
}

export default function FriendListScreen() {
  const router = useRouter();
  const { accessToken, user } = useAuth();
  const params = useLocalSearchParams<{ type?: string; userId?: string }>();
  const kind = normalizeKind(params.type);
  const meta = LIST_META[kind];
  const targetUserId =
    (typeof params.userId === "string" && params.userId.trim()) || user?.user_id || null;

  const [items, setItems] = useState<FollowListItem[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  const load = useCallback(
    async (nextPage: number, append: boolean) => {
      if (!targetUserId) {
        return;
      }
      if (append) {
        setLoadingMore(true);
      } else {
        setLoading(true);
        setError(null);
      }

      try {
        const response = await getFollowList(kind, targetUserId, { page: nextPage, pageSize: 20 });
        setItems((previous) =>
          append ? dedupeById([...previous, ...response.items]) : response.items,
        );
        setPage(nextPage);
        setHasMore(response.items.length === response.page_size);
      } catch (loadError) {
        setError(listErrorMessage(loadError));
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [kind, targetUserId],
  );

  useFocusEffect(
    useCallback(() => {
      void load(1, false);
    }, [load]),
  );

  const loadMore = useCallback(() => {
    if (loading || loadingMore || !hasMore) {
      return;
    }
    void load(page + 1, true);
  }, [hasMore, load, loading, loadingMore, page]);

  const toggleFollow = useCallback(
    (item: FollowListItem) => {
      if (!accessToken || pendingId) {
        return;
      }
      const request = isFollowingInList(kind, item.is_friend)
        ? unfollowUser(accessToken, item.user.user_id)
        : followUser(accessToken, item.user.user_id);

      setPendingId(item.user.user_id);
      void request
        .then((response) => {
          const relationship = response.relationship;
          setItems((previous) => {
            if (!relationship.is_following && (kind === "following" || kind === "friends")) {
              return previous.filter((entry) => entry.user.user_id !== item.user.user_id);
            }
            return previous.map((entry) =>
              entry.user.user_id === item.user.user_id
                ? { ...entry, is_friend: relationship.is_friend }
                : entry,
            );
          });
        })
        .catch((actionError) => Alert.alert("操作失败", listErrorMessage(actionError)))
        .finally(() => setPendingId(null));
    },
    [accessToken, kind, pendingId],
  );

  const openUser = useCallback(
    (item: FollowListItem) => {
      router.push({
        pathname: "/user/[id]",
        params: {
          avatar: item.user.avatar_path ?? "",
          id: item.user.user_id,
          name: item.user.nickname,
        },
      });
    },
    [router],
  );

  return (
    <ScrollPage bottomInset={76}>
      <TopBar onBack={() => router.back()} subtitle={meta.subtitle} title={meta.title} />

      {!targetUserId ? (
        <StatePanel icon="lock-closed-outline" message="登录后才能查看好友列表。" />
      ) : loading && items.length === 0 ? (
        <StatePanel loading message="正在加载列表..." />
      ) : error && items.length === 0 ? (
        <StatePanel actionLabel="重试" icon="refresh-outline" message={error} onAction={() => load(1, false)} />
      ) : items.length === 0 ? (
        <StatePanel icon="people-outline" message={meta.emptyTitle} submessage={meta.emptySubtitle} />
      ) : (
        <View style={styles.list}>
          {items.map((item) => (
            <FollowRow
              item={item}
              key={item.user.user_id}
              kind={kind}
              onPress={() => openUser(item)}
              onToggle={() => toggleFollow(item)}
              pending={pendingId === item.user.user_id}
            />
          ))}

          {error ? (
            <View style={styles.errorLine}>
              <Text style={styles.errorText}>{error}</Text>
              <Pressable accessibilityRole="button" onPress={loadMore} style={styles.retryButton}>
                <Text style={styles.retryButtonText}>重试</Text>
              </Pressable>
            </View>
          ) : null}

          {hasMore ? (
            <Pressable
              accessibilityRole="button"
              disabled={loadingMore}
              onPress={loadMore}
              style={[styles.loadMoreButton, loadingMore && styles.loadMoreButtonDisabled]}
            >
              {loadingMore ? (
                <ActivityIndicator color={colors.ink} size="small" />
              ) : (
                <Text style={styles.loadMoreText}>加载更多</Text>
              )}
            </Pressable>
          ) : null}
        </View>
      )}
    </ScrollPage>
  );
}

function FollowRow({
  item,
  kind,
  onPress,
  onToggle,
  pending,
}: {
  item: FollowListItem;
  kind: FollowListKind;
  onPress: () => void;
  onToggle: () => void;
  pending: boolean;
}) {
  const label = followActionLabel(kind, item.is_friend);

  return (
    <Pressable
      accessibilityLabel={`查看 ${item.user.nickname} 的主页`}
      accessibilityRole="button"
      onPress={onPress}
      style={styles.row}
    >
      <Avatar name={item.user.nickname} size={50} uri={resolveMediaUrl(item.user.avatar_path)} />
      <View style={styles.rowText}>
        <View style={styles.nameLine}>
          <Text numberOfLines={1} style={styles.name}>
            {item.user.nickname}
          </Text>
          {item.user.is_coach ? (
            <View style={styles.coachBadge}>
              <Text style={styles.coachBadgeText}>教练</Text>
            </View>
          ) : null}
        </View>
        <Text numberOfLines={1} style={styles.meta}>
          ID {shortUserId(item.user.user_id)}
        </Text>
      </View>
      <Pressable
        accessibilityLabel={`${label} ${item.user.nickname}`}
        accessibilityRole="button"
        disabled={pending}
        onPress={(event) => {
          event.stopPropagation();
          onToggle();
        }}
        style={styles.actionButton}
      >
        {pending ? (
          <ActivityIndicator color={colors.ink} size="small" />
        ) : (
          <Ionicons color={colors.ink} name={followActionIcon(kind, item.is_friend)} size={14} />
        )}
        <Text style={styles.actionText}>{label}</Text>
      </Pressable>
    </Pressable>
  );
}

function StatePanel({
  actionLabel,
  icon,
  loading,
  message,
  onAction,
  submessage,
}: {
  actionLabel?: string;
  icon?: IconName;
  loading?: boolean;
  message: string;
  onAction?: () => void;
  submessage?: string;
}) {
  return (
    <View style={styles.statePanel}>
      {loading ? (
        <ActivityIndicator color={colors.accentDeep} />
      ) : icon ? (
        <Ionicons color={colors.accentDeep} name={icon} size={28} />
      ) : null}
      <Text style={styles.stateTitle}>{message}</Text>
      {submessage ? <Text style={styles.stateText}>{submessage}</Text> : null}
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
  },
  row: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 12,
    minHeight: 78,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  rowText: {
    flex: 1,
    gap: 5,
    minWidth: 0,
  },
  nameLine: {
    alignItems: "center",
    flexDirection: "row",
    gap: 6,
    minWidth: 0,
  },
  name: {
    color: colors.ink,
    flexShrink: 1,
    fontSize: 16,
    fontWeight: "900",
  },
  meta: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
  coachBadge: {
    backgroundColor: colors.goldSoft,
    borderRadius: radius.small,
    paddingHorizontal: 6,
    paddingVertical: 3,
  },
  coachBadgeText: {
    color: colors.ink,
    fontSize: 10,
    fontWeight: "900",
  },
  actionButton: {
    alignItems: "center",
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.control,
    flexDirection: "row",
    gap: 4,
    justifyContent: "center",
    minHeight: 34,
    minWidth: 68,
    paddingHorizontal: 10,
  },
  actionText: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: "900",
  },
  errorLine: {
    alignItems: "flex-start",
    gap: 8,
  },
  errorText: {
    color: "#B14A3D",
    fontSize: 13,
    fontWeight: "700",
    lineHeight: 19,
  },
  retryButton: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    justifyContent: "center",
    minHeight: 38,
    paddingHorizontal: 16,
  },
  retryButtonText: {
    color: colors.inverse,
    fontSize: 13,
    fontWeight: "900",
  },
  loadMoreButton: {
    alignItems: "center",
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.control,
    justifyContent: "center",
    minHeight: 42,
  },
  loadMoreButtonDisabled: {
    opacity: 0.6,
  },
  loadMoreText: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "900",
  },
  statePanel: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 10,
    marginTop: 22,
    padding: 18,
  },
  stateTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
    textAlign: "center",
  },
  stateText: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "700",
    lineHeight: 19,
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
});
