import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { resolveMediaUrl } from "@/api/activityDetail";
import { ApiError } from "@/api/client";
import { createGroupConversation } from "@/api/messages";
import { searchUsers, type UserSearchItem } from "@/api/users";
import { useAuth } from "@/auth/AuthProvider";
import { useRequireAuth } from "@/auth/useRequireAuth";
import { Avatar, ScrollPage, TopBar } from "@/components/ui";
import { colors, radius } from "@/theme";

function createErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === "USER_INTERACTION_BLOCKED" || error.status === 403) {
      return "当前成员组合无法创建群聊，请调整成员后重试。";
    }
    if (error.status === 0) {
      return "无法连接服务器，请确认网络后重试。";
    }
    if (error.status === 401) {
      return "登录状态已失效，请重新登录后重试。";
    }
    if (error.status === 422) {
      return error.message || "请检查群聊名称和成员后重试。";
    }
    return error.message || "群聊创建失败，请稍后重试。";
  }
  return error instanceof Error ? error.message : "群聊创建失败，请稍后重试。";
}

export default function CreateGroupScreen() {
  const router = useRouter();
  const requireAuth = useRequireAuth();
  const { accessToken, status, userId } = useAuth();
  const [title, setTitle] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<UserSearchItem[]>([]);
  const [selected, setSelected] = useState<UserSearchItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const createInFlightRef = useRef(false);
  const createRequestIdRef = useRef(0);
  const createMutexRequestIdRef = useRef<number | null>(null);
  const mountedRef = useRef(true);
  const searchRequestIdRef = useRef(0);
  const authSessionRef = useRef({ status, userId });
  authSessionRef.current = { status, userId };

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      searchRequestIdRef.current += 1;
      createRequestIdRef.current += 1;
      createMutexRequestIdRef.current = null;
      createInFlightRef.current = false;
    };
  }, []);

  useEffect(() => {
    searchRequestIdRef.current += 1;
    createRequestIdRef.current += 1;
    createMutexRequestIdRef.current = null;
    createInFlightRef.current = false;
    setTitle("");
    setQuery("");
    setResults([]);
    setHasSearched(false);
    setSearchLoading(false);
    setSelected([]);
    setError(null);
    setLoading(false);
  }, [status, userId]);

  const selectedIds = useMemo(() => new Set(selected.map((item) => item.user.user_id)), [selected]);
  const trimmedQuery = query.trim();
  const handleQueryChange = useCallback((value: string) => {
    searchRequestIdRef.current += 1;
    setQuery(value);
    setResults([]);
    setHasSearched(false);
    setSearchLoading(false);
    setError(null);
  }, []);

  const runSearch = useCallback(async () => {
    if (!accessToken || status !== "authenticated" || !userId || trimmedQuery.length < 2) {
      searchRequestIdRef.current += 1;
      setResults([]);
      setHasSearched(false);
      setSearchLoading(false);
      return;
    }
    const requestId = ++searchRequestIdRef.current;
    const requestUserId = userId;
    setSearchLoading(true);
    try {
      const response = await searchUsers(accessToken, trimmedQuery, { pageSize: 20 });
      if (!mountedRef.current || searchRequestIdRef.current !== requestId || authSessionRef.current.userId !== requestUserId || authSessionRef.current.status !== "authenticated") {
        return;
      }
      setResults(response.items.filter((item) => !item.is_self));
      setHasSearched(true);
    } catch (searchError) {
      if (!mountedRef.current || searchRequestIdRef.current !== requestId || authSessionRef.current.userId !== requestUserId || authSessionRef.current.status !== "authenticated") {
        return;
      }
      setResults([]);
      setError(createErrorMessage(searchError));
      setHasSearched(true);
    } finally {
      if (mountedRef.current && searchRequestIdRef.current === requestId && authSessionRef.current.userId === requestUserId && authSessionRef.current.status === "authenticated") {
        setSearchLoading(false);
      }
    }
  }, [accessToken, status, trimmedQuery, userId]);

  useEffect(() => {
    if (trimmedQuery.length < 2) {
      searchRequestIdRef.current += 1;
      setResults([]);
      setHasSearched(false);
      setSearchLoading(false);
      return;
    }
    const timer = setTimeout(() => void runSearch(), 360);
    return () => clearTimeout(timer);
  }, [runSearch, trimmedQuery.length]);

  const toggleCandidate = useCallback((item: UserSearchItem) => {
    setError(null);
    setSelected((current) => current.some((selectedItem) => selectedItem.user.user_id === item.user.user_id)
      ? current.filter((selectedItem) => selectedItem.user.user_id !== item.user.user_id)
      : [...current, item]);
  }, []);

  const submit = useCallback(async () => {
    if (!accessToken || status !== "authenticated" || !userId) {
      requireAuth("登录后可以创建群聊", "/messages/create-group");
      return;
    }
    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      setError("请输入群聊名称。");
      return;
    }
    if (selected.length === 0) {
      setError("至少选择一位成员。");
      return;
    }
    if (createInFlightRef.current) {
      return;
    }
    const requestId = ++createRequestIdRef.current;
    createInFlightRef.current = true;
    createMutexRequestIdRef.current = requestId;
    setLoading(true);
    setError(null);
    const requestUserId = userId;
    try {
      const response = await createGroupConversation(
        accessToken,
        trimmedTitle,
        selected.map((item) => item.user.user_id),
      );
      if (!mountedRef.current || createRequestIdRef.current !== requestId || authSessionRef.current.userId !== requestUserId || authSessionRef.current.status !== "authenticated") {
        return;
      }
      router.replace({
        pathname: "/chat/[id]",
        params: {
          avatar: response.conversation.avatar_path ?? "",
          id: response.conversation.conversation_id,
          name: response.conversation.title ?? trimmedTitle,
        },
      });
    } catch (submitError) {
      if (mountedRef.current && createRequestIdRef.current === requestId && authSessionRef.current.userId === requestUserId && authSessionRef.current.status === "authenticated") {
        setError(createErrorMessage(submitError));
      }
    } finally {
      if (createMutexRequestIdRef.current === requestId) {
        createMutexRequestIdRef.current = null;
        createInFlightRef.current = false;
        if (mountedRef.current && createRequestIdRef.current === requestId) {
          setLoading(false);
        }
      }
    }
  }, [accessToken, requireAuth, router, selected, status, title, userId]);

  return (
    <ScrollPage bottomInset={112}>
      <TopBar onBack={() => router.back()} title="创建群聊" />

      <View style={styles.section}>
        <Text style={styles.label}>群聊名称</Text>
        <TextInput
          autoCapitalize="sentences"
          maxLength={120}
          onChangeText={(value) => { setTitle(value); setError(null); }}
          placeholder="输入群聊名称"
          placeholderTextColor={colors.muted}
          style={styles.input}
          value={title}
        />
      </View>

      <View style={styles.section}>
        <Text style={styles.label}>添加成员</Text>
        <View style={styles.searchRow}>
          <Ionicons color={colors.muted} name="search" size={18} />
          <TextInput
            autoCapitalize="none"
            autoCorrect={false}
            onChangeText={handleQueryChange}
            onSubmitEditing={() => void runSearch()}
            placeholder="搜索昵称或球友 ID"
            placeholderTextColor={colors.muted}
            returnKeyType="search"
            style={styles.searchInput}
            value={query}
          />
          {searchLoading ? <ActivityIndicator color={colors.accentDeep} size="small" /> : null}
        </View>
        {results.map((item) => {
          const isSelected = selectedIds.has(item.user.user_id);
          return (
            <Pressable
              accessibilityLabel={`${isSelected ? "移除" : "选择"}${item.user.nickname}`}
              accessibilityRole="button"
              key={item.user.user_id}
              onPress={() => toggleCandidate(item)}
              style={[styles.userRow, isSelected && styles.userRowSelected]}
            >
              <Avatar name={item.user.nickname} size={42} uri={resolveMediaUrl(item.user.avatar_path)} />
              <Text numberOfLines={1} style={styles.userName}>{item.user.nickname}</Text>
              <Ionicons color={isSelected ? colors.accentDeep : colors.muted} name={isSelected ? "checkmark-circle" : "add-circle-outline"} size={22} />
            </Pressable>
          );
        })}
        {hasSearched && !searchLoading && results.length === 0 ? <Text style={styles.mutedText}>未找到可添加的成员。</Text> : null}
      </View>

      {selected.length > 0 ? (
        <View style={styles.section}>
          <Text style={styles.label}>已选择 {selected.length} 位成员</Text>
          <View style={styles.selectedList}>
            {selected.map((item) => (
              <Pressable accessibilityRole="button" key={item.user.user_id} onPress={() => toggleCandidate(item)} style={styles.selectedItem}>
                <Avatar name={item.user.nickname} size={30} uri={resolveMediaUrl(item.user.avatar_path)} />
                <Text numberOfLines={1} style={styles.selectedName}>{item.user.nickname}</Text>
                <Ionicons color={colors.muted} name="close-circle" size={17} />
              </Pressable>
            ))}
          </View>
        </View>
      ) : null}

      {error ? <Text style={styles.errorText}>{error}</Text> : null}
      <Pressable accessibilityRole="button" disabled={loading} onPress={() => void submit()} style={[styles.submitButton, loading && styles.disabled]}>
        {loading ? <ActivityIndicator color={colors.inverse} /> : <Text style={styles.submitText}>创建群聊</Text>}
      </Pressable>
    </ScrollPage>
  );
}

const styles = StyleSheet.create({
  section: { gap: 10, marginTop: 22 },
  label: { color: colors.ink, fontSize: 14, fontWeight: "900" },
  input: { backgroundColor: colors.surface, borderColor: colors.line, borderRadius: radius.card, borderWidth: StyleSheet.hairlineWidth, color: colors.ink, fontSize: 15, minHeight: 48, paddingHorizontal: 14 },
  searchRow: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.line, borderRadius: radius.card, borderWidth: StyleSheet.hairlineWidth, flexDirection: "row", gap: 8, minHeight: 48, paddingHorizontal: 12 },
  searchInput: { color: colors.ink, flex: 1, fontSize: 14, minWidth: 0, paddingVertical: 9 },
  userRow: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.line, borderRadius: radius.card, borderWidth: StyleSheet.hairlineWidth, flexDirection: "row", gap: 10, minHeight: 60, paddingHorizontal: 12 },
  userRowSelected: { backgroundColor: colors.surfaceWarm, borderColor: colors.accent },
  userName: { color: colors.ink, flex: 1, fontSize: 14, fontWeight: "800" },
  mutedText: { color: colors.muted, fontSize: 13, fontWeight: "600" },
  selectedList: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  selectedItem: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.line, borderRadius: radius.control, borderWidth: StyleSheet.hairlineWidth, flexDirection: "row", gap: 6, maxWidth: "100%", paddingHorizontal: 8, paddingVertical: 5 },
  selectedName: { color: colors.inkSoft, fontSize: 12, fontWeight: "800", maxWidth: 120 },
  errorText: { color: colors.clay, fontSize: 13, fontWeight: "800", marginTop: 18 },
  submitButton: { alignItems: "center", backgroundColor: colors.ink, borderRadius: radius.control, justifyContent: "center", marginTop: 24, minHeight: 48 },
  submitText: { color: colors.inverse, fontSize: 14, fontWeight: "900" },
  disabled: { opacity: 0.56 },
});
