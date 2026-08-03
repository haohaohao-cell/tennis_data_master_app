import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect } from "@react-navigation/native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useMemo, useState } from "react";
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, View } from "react-native";

import { resolveMediaUrl } from "@/api/activityDetail";
import { ApiError } from "@/api/client";
import { createDirectConversation, createMessageRequest } from "@/api/messages";
import {
  followUser,
  getRelationship,
  getSocialStats,
  type Relationship,
  type SocialStats,
  unfollowUser,
} from "@/api/social";
import { useAuth } from "@/auth/AuthProvider";
import { useRequireAuth } from "@/auth/useRequireAuth";
import { Avatar, Card, MetricCard, ScrollPage, TopBar } from "@/components/ui";
import { colors, radius } from "@/theme";

type IconName = keyof typeof Ionicons.glyphMap;

function authorErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === "MESSAGE_REQUEST_REQUIRED") {
      return "互相关注后可以直接私信，或先发送一次消息请求。";
    }
    if (error.code === "DIRECT_MESSAGE_NOT_ALLOWED") {
      return "对方暂时不接受新的私信。";
    }
    if (error.code === "MESSAGE_REQUESTS_DISABLED") {
      return "对方暂时不接受消息请求。";
    }
    if (error.code === "MESSAGE_REQUEST_NOT_REQUIRED") {
      return "你们已经可以直接私信。";
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "发布者信息暂时加载失败。";
}

function followActionLabel(relationship: Relationship | null) {
  if (relationship?.is_friend) {
    return "已互关";
  }
  if (relationship?.is_following) {
    return "已关注";
  }
  if (relationship?.is_followed_by) {
    return "回关";
  }
  return "关注";
}

function followActionIcon(relationship: Relationship | null): IconName {
  if (relationship?.is_friend) {
    return "people";
  }
  if (relationship?.is_following) {
    return "checkmark";
  }
  if (relationship?.is_followed_by) {
    return "person-add";
  }
  return "add";
}

function relationshipHint(relationship: Relationship | null, accessToken: string | null) {
  if (!accessToken) {
    return "登录后可以关注球友、互关并发起私信。";
  }
  if (relationship?.is_friend) {
    return "你们已互相关注，可以直接私信。";
  }
  if (relationship?.is_followed_by) {
    return "TA 已关注你，回关后会成为球友。";
  }
  if (relationship?.is_following) {
    return "你已关注 TA，等待对方回关后会成为球友。";
  }
  return "互相关注后成为球友，可以直接私信。";
}

export default function UserProfileScreen() {
  const router = useRouter();
  const requireAuth = useRequireAuth();
  const { accessToken, user } = useAuth();
  const { avatar, id, name } = useLocalSearchParams<{
    avatar?: string;
    id?: string;
    name?: string;
  }>();
  const [stats, setStats] = useState<SocialStats | null>(null);
  const [relationship, setRelationship] = useState<Relationship | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionPending, setActionPending] = useState(false);
  const [messagePending, setMessagePending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const userId = typeof id === "string" ? id : null;
  const displayName = typeof name === "string" && name.trim() ? name : "网球用户";
  const avatarUri = useMemo(() => {
    if (typeof avatar !== "string" || !avatar) {
      return null;
    }
    return resolveMediaUrl(avatar);
  }, [avatar]);
  const isSelf = Boolean(userId && user?.user_id === userId);

  const loadProfile = useCallback(async () => {
    if (!userId) {
      setError("缺少用户 id，无法打开发布者主页。");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const nextStats = await getSocialStats(userId);
      setStats(nextStats);
      if (accessToken && !isSelf) {
        setRelationship(await getRelationship(accessToken, userId));
      } else {
        setRelationship(null);
      }
    } catch (loadError) {
      setError(authorErrorMessage(loadError));
    } finally {
      setLoading(false);
    }
  }, [accessToken, isSelf, userId]);

  useFocusEffect(
    useCallback(() => {
      void loadProfile();
    }, [loadProfile]),
  );

  const toggleFollow = useCallback(() => {
    if (!userId || actionPending) {
      return;
    }
    if (!accessToken || !requireAuth("登录后可以关注这位发布者", `/user/${userId}`)) {
      return;
    }

    setActionPending(true);
    const wasFollowing = Boolean(relationship?.is_following);
    const wasFriend = Boolean(relationship?.is_friend);
    const request = relationship?.is_following
      ? unfollowUser(accessToken, userId)
      : followUser(accessToken, userId);
    void request
      .then((response) => {
        setRelationship(response.relationship);
        setStats((current) =>
          current
            ? {
                ...current,
                follower_count: Math.max(
                  0,
                  current.follower_count +
                    (response.relationship.is_following === wasFollowing
                      ? 0
                      : response.relationship.is_following
                        ? 1
                        : -1),
                ),
                friend_count: Math.max(
                  0,
                  current.friend_count +
                    (response.relationship.is_friend === wasFriend
                      ? 0
                      : response.relationship.is_friend
                        ? 1
                        : -1),
                ),
              }
            : current,
        );
      })
      .catch((actionError) => Alert.alert("操作失败", authorErrorMessage(actionError)))
      .finally(() => setActionPending(false));
  }, [accessToken, actionPending, relationship?.is_following, relationship?.is_friend, requireAuth, userId]);

  const sendMessageRequest = useCallback(() => {
    if (!userId || messagePending) {
      return;
    }
    if (!accessToken || !requireAuth("登录后可以给这位球友发送消息请求", `/user/${userId}`)) {
      return;
    }

    setMessagePending(true);
    void (async () => {
      try {
        await createMessageRequest(accessToken, userId, "想和你聊聊网球。", "author_profile");
        Alert.alert("请求已发送", "对方接受后，你们就可以继续聊天。");
      } catch (requestError) {
        if (requestError instanceof ApiError && requestError.code === "MESSAGE_REQUEST_NOT_REQUIRED") {
          try {
            const response = await createDirectConversation(accessToken, userId);
            const other = response.other_members[0];
            router.push({
              pathname: "/chat/[id]",
              params: {
                avatar: other?.avatar_path ?? (typeof avatar === "string" ? avatar : ""),
                id: response.conversation.conversation_id,
                name: other?.nickname ?? displayName,
              },
            });
          } catch (directError) {
            Alert.alert("发起聊天失败", authorErrorMessage(directError));
          }
          return;
        }
        Alert.alert("请求发送失败", authorErrorMessage(requestError));
      } finally {
        setMessagePending(false);
      }
    })();
  }, [accessToken, avatar, displayName, messagePending, requireAuth, router, userId]);

  const openMessage = useCallback(() => {
    if (!userId || messagePending) {
      return;
    }
    if (!accessToken || !requireAuth("登录后可以给这位球友发私信", `/user/${userId}`)) {
      return;
    }

    setMessagePending(true);
    void createDirectConversation(accessToken, userId)
      .then((response) => {
        const other = response.other_members[0];
        router.push({
          pathname: "/chat/[id]",
          params: {
            avatar: other?.avatar_path ?? (typeof avatar === "string" ? avatar : ""),
            id: response.conversation.conversation_id,
            name: other?.nickname ?? displayName,
          },
        });
      })
      .catch((messageError) => {
        if (messageError instanceof ApiError && messageError.code === "MESSAGE_REQUEST_REQUIRED") {
          Alert.alert(
            "需要互关或请求",
            "互相关注后可以直接聊天。你也可以先发送一次消息请求，等对方接受后继续。",
            [
              { style: "cancel", text: "取消" },
              { onPress: sendMessageRequest, text: "发送请求" },
            ],
          );
          return;
        }
        Alert.alert("发起聊天失败", authorErrorMessage(messageError));
      })
      .finally(() => setMessagePending(false));
  }, [accessToken, avatar, displayName, messagePending, requireAuth, router, sendMessageRequest, userId]);

  return (
    <ScrollPage>
      <TopBar onBack={() => router.back()} subtitle="发布者主页" title={displayName} />

      <Card style={styles.headerCard}>
        <View style={styles.identityRow}>
          <Avatar name={displayName} size={70} uri={avatarUri} />
          <View style={styles.identityText}>
            <Text numberOfLines={1} style={styles.name}>
              {displayName}
            </Text>
            <Text style={styles.userId}>ID {userId ?? "-"}</Text>
          </View>
        </View>

        <View style={styles.metricRow}>
          <MetricCard label="粉丝" value={`${stats?.follower_count ?? 0}`} />
          <MetricCard label="关注" value={`${stats?.following_count ?? 0}`} />
          <MetricCard label="球友" value={`${stats?.friend_count ?? 0}`} />
        </View>

        {isSelf ? (
          <Pressable
            accessibilityRole="button"
            onPress={() => router.push("/(tabs)/profile")}
            style={styles.secondaryButton}
          >
            <Ionicons color={colors.ink} name="person-outline" size={18} />
            <Text style={styles.secondaryButtonText}>查看我的主页</Text>
          </Pressable>
        ) : (
          <View style={styles.actionBlock}>
            <View style={styles.actionRow}>
              <Pressable
                accessibilityRole="button"
                disabled={messagePending}
                onPress={openMessage}
                style={[styles.messageButton, messagePending && styles.buttonDisabled]}
              >
                {messagePending ? (
                  <ActivityIndicator color={colors.inverse} size="small" />
                ) : (
                  <Ionicons color={colors.inverse} name="chatbubble-ellipses" size={18} />
                )}
                <Text style={styles.messageButtonText}>发消息</Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                disabled={actionPending}
                onPress={toggleFollow}
                style={[
                  styles.followButton,
                  relationship?.is_following && styles.followButtonActive,
                  actionPending && styles.buttonDisabled,
                ]}
              >
                {actionPending ? (
                  <ActivityIndicator color={relationship?.is_following ? colors.ink : colors.inverse} size="small" />
                ) : (
                  <Ionicons
                    color={relationship?.is_following ? colors.ink : colors.inverse}
                    name={followActionIcon(relationship)}
                    size={18}
                  />
                )}
                <Text
                  style={[
                    styles.followButtonText,
                    relationship?.is_following && styles.followButtonTextActive,
                  ]}
                >
                  {followActionLabel(relationship)}
                </Text>
              </Pressable>
            </View>
            <View style={styles.relationshipHintRow}>
              <Ionicons color={colors.muted} name="information-circle-outline" size={15} />
              <Text style={styles.relationshipHintText}>{relationshipHint(relationship, accessToken)}</Text>
            </View>
          </View>
        )}
      </Card>

      {loading ? (
        <View style={styles.stateLine}>
          <ActivityIndicator color={colors.accentDeep} />
          <Text style={styles.stateText}>正在加载发布者信息</Text>
        </View>
      ) : null}
      {error ? (
        <Pressable accessibilityRole="button" onPress={loadProfile} style={styles.errorBox}>
          <Ionicons color={colors.clay} name="refresh-outline" size={19} />
          <Text style={styles.errorText}>{error}</Text>
        </Pressable>
      ) : null}
    </ScrollPage>
  );
}

const styles = StyleSheet.create({
  headerCard: {
    gap: 18,
  },
  identityRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 14,
  },
  identityText: {
    flex: 1,
    gap: 6,
    minWidth: 0,
  },
  name: {
    color: colors.ink,
    fontSize: 24,
    fontWeight: "900",
  },
  userId: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
  metricRow: {
    flexDirection: "row",
    gap: 8,
  },
  actionBlock: {
    gap: 10,
  },
  actionRow: {
    flexDirection: "row",
    gap: 10,
  },
  messageButton: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    flex: 1,
    flexDirection: "row",
    gap: 8,
    justifyContent: "center",
    minHeight: 46,
  },
  messageButtonText: {
    color: colors.inverse,
    fontSize: 15,
    fontWeight: "900",
  },
  followButton: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    flex: 1,
    flexDirection: "row",
    gap: 8,
    justifyContent: "center",
    minHeight: 46,
  },
  followButtonActive: {
    backgroundColor: colors.surfaceMuted,
  },
  followButtonText: {
    color: colors.inverse,
    fontSize: 15,
    fontWeight: "900",
  },
  followButtonTextActive: {
    color: colors.ink,
  },
  secondaryButton: {
    alignItems: "center",
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.control,
    flexDirection: "row",
    gap: 8,
    justifyContent: "center",
    minHeight: 46,
  },
  secondaryButtonText: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
  },
  buttonDisabled: {
    opacity: 0.72,
  },
  relationshipHintRow: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 6,
  },
  relationshipHintText: {
    color: colors.muted,
    flex: 1,
    fontSize: 12,
    fontWeight: "700",
    lineHeight: 18,
  },
  stateLine: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
    justifyContent: "center",
    marginTop: 18,
  },
  stateText: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "700",
  },
  errorBox: {
    alignItems: "center",
    backgroundColor: colors.claySoft,
    borderRadius: radius.card,
    flexDirection: "row",
    gap: 8,
    marginTop: 18,
    padding: 12,
  },
  errorText: {
    color: colors.ink,
    flex: 1,
    fontSize: 13,
    fontWeight: "700",
    lineHeight: 19,
  },
});
