import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { resolveMediaUrl } from "@/api/activityDetail";
import { ApiError } from "@/api/client";
import { searchUsers, type UserSearchItem } from "@/api/users";
import { useAuth } from "@/auth/AuthProvider";
import { useRequireAuth } from "@/auth/useRequireAuth";
import { Avatar, ScrollPage, TopBar } from "@/components/ui";
import { colors, radius } from "@/theme";

function searchErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === "USER_SEARCH_QUERY_TOO_SHORT") {
      return "至少输入 2 个字符。";
    }
    if (error.status === 0) {
      return "无法连接服务器，请确认后端可用。";
    }
    if (error.status === 401 || error.status === 403) {
      return "登录状态已失效，请重新登录后搜索球友。";
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "搜索失败，请稍后重试。";
}

function shortUserId(userId: string) {
  return userId.length > 12 ? `${userId.slice(0, 8)}...${userId.slice(-4)}` : userId;
}

function relationshipLabel(item: UserSearchItem) {
  if (item.is_self) {
    return "我";
  }
  if (item.relationship.is_friend) {
    return "已互关";
  }
  if (item.relationship.is_following) {
    return "已关注";
  }
  if (item.relationship.is_followed_by) {
    return "回关";
  }
  return "可关注";
}

function relationshipIcon(item: UserSearchItem): keyof typeof Ionicons.glyphMap {
  if (item.is_self) {
    return "person";
  }
  if (item.relationship.is_friend) {
    return "people";
  }
  if (item.relationship.is_following) {
    return "checkmark";
  }
  if (item.relationship.is_followed_by) {
    return "person-add";
  }
  return "add";
}

export default function FriendSearchScreen() {
  const router = useRouter();
  const requireAuth = useRequireAuth();
  const { accessToken, status } = useAuth();
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<UserSearchItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const trimmedQuery = query.trim();
  const runSearch = useCallback(async () => {
    if (!accessToken || trimmedQuery.length < 2) {
      setItems([]);
      setError(null);
      setHasSearched(false);
      return;
    }

    setLoading(true);
    setError(null);
    setHasSearched(true);
    try {
      const response = await searchUsers(accessToken, trimmedQuery, { pageSize: 20 });
      setItems(response.items);
    } catch (searchError) {
      setItems([]);
      setError(searchErrorMessage(searchError));
    } finally {
      setLoading(false);
    }
  }, [accessToken, trimmedQuery]);

  useEffect(() => {
    if (status === "loading") {
      return;
    }
    if (!accessToken) {
      setItems([]);
      setError(null);
      setHasSearched(false);
      return;
    }
    if (trimmedQuery.length < 2) {
      setItems([]);
      setError(null);
      setHasSearched(false);
      return;
    }

    const timer = setTimeout(() => {
      void runSearch();
    }, 360);
    return () => clearTimeout(timer);
  }, [accessToken, runSearch, status, trimmedQuery.length]);

  const openLogin = useCallback(() => {
    requireAuth("登录后可以搜索并添加球友", "/friends/search");
  }, [requireAuth]);

  const openUser = useCallback(
    (item: UserSearchItem) => {
      if (item.is_self) {
        router.push("/(tabs)/profile");
        return;
      }
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
      <TopBar onBack={() => router.back()} subtitle="添加球友" title="搜索" />

      <View style={styles.searchPanel}>
        <View style={styles.inputWrap}>
          <Ionicons color={colors.muted} name="search" size={18} />
          <TextInput
            autoCapitalize="none"
            autoCorrect={false}
            onChangeText={setQuery}
            onSubmitEditing={() => void runSearch()}
            placeholder="输入昵称或球友 ID"
            placeholderTextColor={colors.muted}
            returnKeyType="search"
            style={styles.input}
            value={query}
          />
          {query ? (
            <Pressable accessibilityLabel="清空搜索" accessibilityRole="button" onPress={() => setQuery("")}>
              <Ionicons color={colors.muted} name="close-circle" size={18} />
            </Pressable>
          ) : null}
        </View>
        <Text style={styles.searchHint}>支持昵称包含匹配和球友 ID 前缀搜索，不支持手机号搜索。</Text>
      </View>

      {status === "loading" ? <StateBlock loading message="正在恢复登录状态..." /> : null}
      {status !== "loading" && !accessToken ? (
        <StateBlock
          actionLabel="去登录"
          icon="lock-closed-outline"
          message="登录后可以搜索球友并进入主页添加。"
          onAction={openLogin}
        />
      ) : null}
      {accessToken ? (
        <>
          {loading ? <StateBlock loading message="正在搜索球友..." /> : null}
          {!loading && error ? (
            <StateBlock actionLabel="重试" icon="refresh-outline" message={error} onAction={runSearch} />
          ) : null}
          {!loading && !error && trimmedQuery.length > 0 && trimmedQuery.length < 2 ? (
            <StateBlock icon="information-circle-outline" message="至少输入 2 个字符后开始搜索。" />
          ) : null}
          {!loading && !error && !hasSearched && trimmedQuery.length === 0 ? (
            <StateBlock icon="person-add-outline" message="输入球友昵称或 ID，找到 TA 后进入主页关注或回关。" />
          ) : null}
          {!loading && !error && hasSearched && items.length === 0 ? (
            <StateBlock icon="search-outline" message="没有找到匹配的球友。请确认昵称或 ID 是否正确。" />
          ) : null}
          {!loading && !error && items.length > 0 ? (
            <View style={styles.resultList}>
              {items.map((item) => (
                <UserResultRow item={item} key={item.user.user_id} onPress={() => openUser(item)} />
              ))}
            </View>
          ) : null}
        </>
      ) : null}
    </ScrollPage>
  );
}

function UserResultRow({ item, onPress }: { item: UserSearchItem; onPress: () => void }) {
  const label = relationshipLabel(item);
  const isConnected = item.is_self || item.relationship.is_friend || item.relationship.is_following;

  return (
    <Pressable
      accessibilityLabel={`查看 ${item.user.nickname} 的主页`}
      accessibilityRole="button"
      onPress={onPress}
      style={styles.resultRow}
    >
      <Avatar name={item.user.nickname} size={50} uri={resolveMediaUrl(item.user.avatar_path)} />
      <View style={styles.resultText}>
        <View style={styles.nameLine}>
          <Text numberOfLines={1} style={styles.resultName}>{item.user.nickname}</Text>
          {item.user.is_coach ? (
            <View style={styles.coachBadge}>
              <Text style={styles.coachBadgeText}>教练</Text>
            </View>
          ) : null}
        </View>
        <Text numberOfLines={1} style={styles.resultMeta}>
          ID {shortUserId(item.user.user_id)} · {item.match_type === "user_id" ? "ID 匹配" : "昵称匹配"}
        </Text>
      </View>
      <View style={[styles.relationshipBadge, isConnected && styles.relationshipBadgeActive]}>
        <Ionicons color={isConnected ? colors.ink : colors.inverse} name={relationshipIcon(item)} size={14} />
        <Text style={[styles.relationshipBadgeText, isConnected && styles.relationshipBadgeTextActive]}>
          {label}
        </Text>
      </View>
    </Pressable>
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
  searchPanel: {
    gap: 9,
  },
  inputWrap: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 8,
    minHeight: 48,
    paddingHorizontal: 12,
  },
  input: {
    color: colors.ink,
    flex: 1,
    fontSize: 15,
    fontWeight: "700",
    minHeight: 48,
  },
  searchHint: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
    lineHeight: 18,
  },
  resultList: {
    gap: 10,
    marginTop: 20,
  },
  resultRow: {
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
  resultText: {
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
  resultName: {
    color: colors.ink,
    flexShrink: 1,
    fontSize: 16,
    fontWeight: "900",
  },
  resultMeta: {
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
  relationshipBadge: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    flexDirection: "row",
    gap: 4,
    minHeight: 34,
    paddingHorizontal: 9,
  },
  relationshipBadgeActive: {
    backgroundColor: colors.surfaceMuted,
  },
  relationshipBadgeText: {
    color: colors.inverse,
    fontSize: 12,
    fontWeight: "900",
  },
  relationshipBadgeTextActive: {
    color: colors.ink,
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
});
