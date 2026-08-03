import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect } from "@react-navigation/native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useCallback, useRef, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { getCoachIdentity, type CoachIdentity } from "@/api/coach";
import { ApiError } from "@/api/client";
import { formatActivityLocation } from "@/api/location";
import { resolveMediaUrl } from "@/api/activityDetail";
import { primePostDetailPreview } from "@/api/postDetailPreviewCache";
import {
  getMyPostCollection,
  unfavoritePost,
  unlikePost,
  type PostCollectionKind,
  type PostDetailResponse,
} from "@/api/posts";
import {
  getProfileContent,
  type ProfileActivity,
  type ProfileContent,
  type ProfileLesson,
  type ProfilePost,
} from "@/api/profileContent";
import { useAuth } from "@/auth/AuthProvider";
import {
  Avatar,
  Card,
  IconBadge,
  Pill,
  RowButton,
  ScrollPage,
  SectionHeader,
  type IconName,
} from "@/components/ui";
import { coachCourses, pendingVideos, students } from "@/data/mockData";
import { colors, radius } from "@/theme";

type ProfileMode = "player" | "coach";
type PlayerTab = "posts" | "matches" | "training" | "courses" | "saved" | "liked" | "data";
type PostCollectionState = {
  error: string | null;
  hasMore: boolean;
  items: PostDetailResponse[];
  loading: boolean;
  nextCursor: string | null;
};

const playerTabs = [
  { label: "动态", value: "posts", icon: "images-outline" },
  { label: "比赛", value: "matches", icon: "trophy-outline" },
  { label: "训练", value: "training", icon: "fitness-outline" },
  { label: "课程", value: "courses", icon: "school-outline" },
  { label: "收藏", value: "saved", icon: "bookmark-outline" },
  { label: "赞过", value: "liked", icon: "heart-outline" },
  { label: "数据", value: "data", icon: "analytics-outline" },
] as const;

function emptyPostCollectionState(): PostCollectionState {
  return {
    error: null,
    hasMore: false,
    items: [],
    loading: false,
    nextCursor: null,
  };
}

function profileContentErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "暂时无法加载我的内容";
}

export default function ProfileScreen() {
  const router = useRouter();
  const { accessToken, isAuthenticated, status } = useAuth();
  const [mode, setMode] = useState<ProfileMode>("player");
  const [coachIdentity, setCoachIdentity] = useState<CoachIdentity | null>(null);
  const [coachLoading, setCoachLoading] = useState(false);
  const [profileContent, setProfileContent] = useState<ProfileContent | null>(null);
  const [profileContentLoading, setProfileContentLoading] = useState(false);
  const [profileContentError, setProfileContentError] = useState<string | null>(null);

  const loadCoachIdentity = useCallback(async () => {
    if (!accessToken) {
      setCoachIdentity(null);
      return;
    }

    setCoachLoading(true);
    try {
      setCoachIdentity(await getCoachIdentity(accessToken));
    } catch {
      setCoachIdentity(null);
    } finally {
      setCoachLoading(false);
    }
  }, [accessToken]);

  const loadProfileContent = useCallback(async () => {
    if (!accessToken) {
      setProfileContent(null);
      setProfileContentError(null);
      return;
    }

    setProfileContentLoading(true);
    setProfileContentError(null);
    try {
      setProfileContent(await getProfileContent(accessToken));
    } catch (error) {
      setProfileContent(null);
      setProfileContentError(profileContentErrorMessage(error));
    } finally {
      setProfileContentLoading(false);
    }
  }, [accessToken]);

  useFocusEffect(
    useCallback(() => {
      if (status === "authenticated") {
        void loadCoachIdentity();
        void loadProfileContent();
      }
    }, [loadCoachIdentity, loadProfileContent, status]),
  );

  if (status === "loading") {
    return (
      <ScrollPage bottomInset={112} contentStyle={styles.page}>
        <View style={styles.guestPanel}>
          <Text style={styles.guestTitle}>我的</Text>
          <Text style={styles.guestText}>正在确认账户状态...</Text>
        </View>
      </ScrollPage>
    );
  }

  if (!isAuthenticated) {
    return <GuestProfile />;
  }

  return (
    <ScrollPage bottomInset={112} contentStyle={styles.page}>
      {mode === "player" ? (
        <PlayerProfile
          coachIdentity={coachIdentity}
          coachLoading={coachLoading}
          content={profileContent}
          contentError={profileContentError}
          contentLoading={profileContentLoading}
          onSwitchToCoach={() => {
            if (isActiveCoachIdentity(coachIdentity)) {
              setMode("coach");
              return;
            }
            router.push("/profile/coach-apply");
          }}
          onRetryContent={loadProfileContent}
        />
      ) : (
        <CoachWorkspace coachIdentity={coachIdentity} onSwitchToPlayer={() => setMode("player")} />
      )}
    </ScrollPage>
  );
}

function GuestProfile() {
  const router = useRouter();

  return (
    <ScrollPage bottomInset={112} contentStyle={styles.page}>
      <View style={styles.guestPanel}>
        <View style={styles.guestHero}>
          <View style={styles.guestAvatar}>
            <Ionicons color={colors.inverse} name="person-outline" size={26} />
          </View>
          <View style={styles.guestHeroText}>
            <Text style={styles.guestTitle}>登录后使用我的页</Text>
            <Text style={styles.guestText}>
              你可以先浏览首页、训练和消息；点赞、收藏、评论、上传视频和个人归属内容时再登录。
            </Text>
          </View>
        </View>

        <Pressable
          accessibilityRole="button"
          onPress={() =>
            router.push({
              pathname: "/login",
              params: { redirect: "/(tabs)/profile" },
            })
          }
          style={styles.loginButton}
        >
          <Text style={styles.loginButtonText}>登录 / 注册</Text>
        </Pressable>

        <View style={styles.guestSummary}>
          <GuestSummary label="可先浏览" value="首页 / 训练 / 消息" />
          <GuestSummary label="登录后可用" value="发布 / 上传 / 我的" />
        </View>
      </View>
    </ScrollPage>
  );
}

function GuestSummary({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.guestSummaryRow}>
      <Text style={styles.guestSummaryLabel}>{label}</Text>
      <Text style={styles.guestSummaryValue}>{value}</Text>
    </View>
  );
}

function PlayerProfile({
  coachIdentity,
  coachLoading,
  content,
  contentError,
  contentLoading,
  onSwitchToCoach,
  onRetryContent,
}: {
  coachIdentity: CoachIdentity | null;
  coachLoading: boolean;
  content: ProfileContent | null;
  contentError: string | null;
  contentLoading: boolean;
  onSwitchToCoach: () => void;
  onRetryContent: () => void;
}) {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<PlayerTab>("posts");
  const [menuOpen, setMenuOpen] = useState(false);
  const { user } = useAuth();
  const profileCompleted = Boolean(user?.profile_completed);
  const displayName = profileCompleted ? (user?.nickname ?? "网球用户") : "网球用户";

  return (
    <View style={styles.profileBody}>
      <View style={styles.playerHeaderRow}>
        <View style={styles.playerHero}>
          <Avatar name={displayName} size={72} uri={resolveMediaUrl(user?.avatar_path)} />
          <View style={styles.playerInfo}>
            <View style={styles.nameLine}>
              <Text style={styles.playerName}>{displayName}</Text>
              <Pressable
                accessibilityLabel={profileCompleted ? "编辑资料" : "完善资料"}
                accessibilityRole="button"
                onPress={() => router.push("/profile/edit")}
              >
                <Pill>{profileCompleted ? "资料已完善" : "资料待完善"}</Pill>
              </Pressable>
            </View>
          </View>
        </View>
        <View style={styles.headerActions}>
          {isActiveCoachIdentity(coachIdentity) ? (
            <Pressable
              accessibilityLabel="进入教练工作台"
              accessibilityRole="button"
              onPress={onSwitchToCoach}
              style={styles.modeButton}
            >
              {coachLoading ? (
                <ActivityIndicator color={colors.accentDeep} size="small" />
              ) : (
                <Ionicons color={colors.accentDeep} name="school-outline" size={16} />
              )}
              <Text style={styles.modeButtonText}>教练入口</Text>
            </Pressable>
          ) : null}
          <Pressable
            accessibilityLabel="打开功能菜单"
            accessibilityRole="button"
            onPress={() => setMenuOpen(true)}
            style={styles.menuButton}
          >
            <Ionicons color={colors.ink} name="menu-outline" size={22} />
          </Pressable>
        </View>
      </View>

      <View style={styles.socialStats}>
        <ProfileStat label="动态" value={`${content?.stats.posts ?? 0}`} />
        <ProfileStat label="比赛" value={`${content?.stats.matches ?? 0}`} />
        <ProfileStat label="训练" value={`${content?.stats.training ?? 0}`} />
        <ProfileStat label="课程" value={`${content?.stats.courses ?? 0}`} />
      </View>

      <ScrollView
        contentContainerStyle={styles.playerTabList}
        horizontal
        showsHorizontalScrollIndicator={false}
      >
        {playerTabs.map((tab) => {
          const selected = activeTab === tab.value;

          return (
            <Pressable
              accessibilityRole="button"
              key={tab.value}
              onPress={() => setActiveTab(tab.value)}
              style={[styles.playerTab, selected && styles.playerTabActive]}
            >
              <Ionicons
                color={selected ? colors.ink : colors.muted}
                name={tab.icon as IconName}
                size={17}
              />
              <Text style={[styles.playerTabText, selected && styles.playerTabTextActive]}>
                {tab.label}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>

      <PlayerTabContent
        content={content}
        error={contentError}
        loading={contentLoading}
        onRetry={onRetryContent}
        tab={activeTab}
      />

      <ProfileMenuDrawer
        coachIdentity={coachIdentity}
        coachLoading={coachLoading}
        onClose={() => setMenuOpen(false)}
        visible={menuOpen}
      />
    </View>
  );
}

function isActiveCoachIdentity(identity: CoachIdentity | null) {
  return identity?.status === "certified_coach" || identity?.status === "non_professional_coach";
}

function coachMenuSubtitle(identity: CoachIdentity | null, loading: boolean) {
  if (loading) {
    return "正在同步";
  }
  if (!identity || identity.status === "normal_user" || identity.status === "coach_revoked") {
    return "申请入口";
  }
  if (identity.status === "pending_review") {
    return "审核中";
  }
  if (identity.status === "review_rejected") {
    return "可重新申请";
  }
  if (identity.status === "coach_suspended") {
    return "暂不可用";
  }
  return identity.label;
}

function ProfileMenuDrawer({
  coachIdentity,
  coachLoading,
  onClose,
  visible,
}: {
  coachIdentity: CoachIdentity | null;
  coachLoading: boolean;
  onClose: () => void;
  visible: boolean;
}) {
  const router = useRouter();

  function open(pathname: "/profile/edit" | "/profile/settings" | "/profile/coach-apply") {
    onClose();
    router.push(pathname);
  }

  return (
    <Modal animationType="slide" onRequestClose={onClose} transparent visible={visible}>
      <Pressable accessibilityRole="button" onPress={onClose} style={styles.drawerBackdrop}>
        <View onStartShouldSetResponder={() => true} style={styles.sideDrawer}>
          <View style={styles.drawerHeader}>
            <View>
              <Text style={styles.drawerKicker}>我的功能</Text>
              <Text style={styles.drawerTitle}>功能入口</Text>
            </View>
            <Pressable
              accessibilityLabel="关闭功能菜单"
              accessibilityRole="button"
              onPress={onClose}
              style={styles.drawerClose}
            >
              <Ionicons color={colors.ink} name="close" size={20} />
            </Pressable>
          </View>

          <View style={styles.drawerList}>
            <RowButton
              icon="person-circle-outline"
              onPress={() => open("/profile/edit")}
              subtitle="昵称、持拍手、头像"
              title="账号资料"
            />
            <RowButton
              icon="school-outline"
              onPress={() => open("/profile/coach-apply")}
              subtitle={coachMenuSubtitle(coachIdentity, coachLoading)}
              title="教练身份"
            />
            <RowButton
              icon="settings-outline"
              onPress={() => open("/profile/settings")}
              subtitle="账号资料、登录状态"
              title="设置"
            />
          </View>
        </View>
      </Pressable>
    </Modal>
  );
}

function ProfileStat({
  inverse = false,
  label,
  value,
}: {
  inverse?: boolean;
  label: string;
  value: string;
}) {
  return (
    <View style={styles.profileStat}>
      <Text style={[styles.profileStatValue, inverse && styles.profileStatValueInverse]}>
        {value}
      </Text>
      <Text style={[styles.profileStatLabel, inverse && styles.profileStatLabelInverse]}>
        {label}
      </Text>
    </View>
  );
}

function PlayerTabContent({
  content,
  error,
  loading,
  onRetry,
  tab,
}: {
  content: ProfileContent | null;
  error: string | null;
  loading: boolean;
  onRetry: () => void;
  tab: PlayerTab;
}) {
  const router = useRouter();
  const { accessToken } = useAuth();
  const [collectionStates, setCollectionStates] = useState<
    Record<PostCollectionKind, PostCollectionState>
  >(() => ({
    favorites: emptyPostCollectionState(),
    likes: emptyPostCollectionState(),
  }));
  const collectionStatesRef = useRef(collectionStates);

  const updateCollectionState = useCallback(
    (
      collection: PostCollectionKind,
      updater: (previous: PostCollectionState) => PostCollectionState,
    ) => {
      setCollectionStates((previous) => {
        const next = {
          ...previous,
          [collection]: updater(previous[collection]),
        };
        collectionStatesRef.current = next;
        return next;
      });
    },
    [],
  );

  const loadCollection = useCallback(
    async (collection: PostCollectionKind, append = false) => {
      if (!accessToken) {
        return;
      }
      const current = collectionStatesRef.current[collection];
      if (current.loading || (append && (!current.hasMore || !current.nextCursor))) {
        return;
      }

      updateCollectionState(collection, (previous) => ({
        ...previous,
        error: null,
        loading: true,
      }));

      try {
        const response = await getMyPostCollection(accessToken, collection, {
          cursor: append ? current.nextCursor : null,
          limit: 20,
        });
        const latestItems = collectionStatesRef.current[collection].items;
        const items = append
          ? Array.from(
              new Map(
                [...latestItems, ...response.items].map((item) => [
                  item.post.social_post_id,
                  item,
                ]),
              ).values(),
            )
          : response.items;
        updateCollectionState(collection, (previous) => ({
          ...previous,
          error: null,
          hasMore: response.has_more,
          items,
          loading: false,
          nextCursor: response.next_cursor,
        }));
      } catch (error) {
        updateCollectionState(collection, (previous) => ({
          ...previous,
          error: profileContentErrorMessage(error),
          loading: false,
        }));
      }
    },
    [accessToken, updateCollectionState],
  );

  useFocusEffect(
    useCallback(() => {
      if (tab === "saved") {
        void loadCollection("favorites");
      } else if (tab === "liked") {
        void loadCollection("likes");
      }
    }, [loadCollection, tab]),
  );

  const removeCollectionPost = useCallback(
    async (collection: PostCollectionKind, socialPostId: string) => {
      if (!accessToken) {
        return;
      }
      try {
        if (collection === "favorites") {
          await unfavoritePost(accessToken, socialPostId);
        } else {
          await unlikePost(accessToken, socialPostId);
        }
        updateCollectionState(collection, (previous) => ({
          ...previous,
          items: previous.items.filter((item) => item.post.social_post_id !== socialPostId),
        }));
      } catch (error) {
        updateCollectionState(collection, (previous) => ({
          ...previous,
          error: profileContentErrorMessage(error),
        }));
        throw error;
      }
    },
    [accessToken, updateCollectionState],
  );

  if (tab === "posts") {
    if (loading && !content) {
      return <ContentLoading />;
    }
    if (error && !content) {
      return <ContentError message={error} onRetry={onRetry} />;
    }
    if (!content?.posts.length) {
      return (
        <ContentEmpty
          icon="images-outline"
          subtitle="发布到动态的内容会显示在这里"
          title="还没有动态"
        />
      );
    }

    return (
      <View style={styles.contentGrid}>
        {content.posts.map((post) => (
          <ProfilePostTile key={post.social_post_id} post={post} />
        ))}
      </View>
    );
  }

  if (tab === "matches" || tab === "training") {
    if (loading && !content) {
      return <ContentLoading />;
    }
    if (error && !content) {
      return <ContentError message={error} onRetry={onRetry} />;
    }

    const activities = tab === "matches" ? content?.matches ?? [] : content?.training ?? [];
    if (!activities.length) {
      return (
        <ContentEmpty
          icon={tab === "matches" ? "trophy-outline" : "fitness-outline"}
          subtitle={tab === "matches" ? "记录或上传比赛后会显示在这里" : "刚上传的视频 activity 会显示在这里"}
          title={tab === "matches" ? "还没有比赛" : "还没有训练视频"}
        />
      );
    }

    return (
      <View style={styles.windowList}>
        {activities.map((activity) => (
          <ProfileActivityRow
            activity={activity}
            key={activity.tennis_activity_id}
            onPress={() =>
              router.push({
                pathname: "/activity/[id]",
                params: { id: activity.tennis_activity_id },
              })
            }
          />
        ))}
      </View>
    );
  }

  if (tab === "courses") {
    if (loading && !content) {
      return <ContentLoading />;
    }
    if (error && !content) {
      return <ContentError message={error} onRetry={onRetry} />;
    }
    if (!content?.courses.length) {
      return (
        <ContentEmpty
          icon="school-outline"
          subtitle="你作为教练或学员参与的课程会显示在这里"
          title="还没有课程"
        />
      );
    }

    return (
      <View style={styles.windowList}>
        {content.courses.map((lesson) => (
          <ProfileLessonRow key={`${lesson.role}-${lesson.lesson_id}`} lesson={lesson} />
        ))}
      </View>
    );
  }

  if (tab === "saved") {
    return (
      <PostCollectionGrid
        emptyIcon="bookmark-outline"
        emptySubtitle="你收藏的动态会显示在这里"
        emptyTitle="还没有收藏"
        onLoadMore={() => loadCollection("favorites", true)}
        onRefresh={() => loadCollection("favorites")}
        onRemove={(socialPostId) => removeCollectionPost("favorites", socialPostId)}
        removeLabel="取消收藏"
        state={collectionStates.favorites}
      />
    );
  }

  if (tab === "liked") {
    return (
      <PostCollectionGrid
        emptyIcon="heart-outline"
        emptySubtitle="你点过赞的动态会显示在这里"
        emptyTitle="还没有赞过"
        onLoadMore={() => loadCollection("likes", true)}
        onRefresh={() => loadCollection("likes")}
        onRemove={(socialPostId) => removeCollectionPost("likes", socialPostId)}
        removeLabel="取消点赞"
        state={collectionStates.likes}
      />
    );
  }

  if (tab === "data") {
    return (
      <View style={styles.dataWindow}>
        <View style={styles.dataWindowHeader}>
          <Text style={styles.windowTitle}>阶段状态</Text>
          <Text style={styles.windowMeta}>最近 30 天</Text>
        </View>
        <View style={styles.dataBars}>
          {[74, 62, 86, 68].map((value, index) => (
            <View key={index} style={styles.dataBarRow}>
              <Text style={styles.dataLabel}>{["发球", "接发", "底线", "移动"][index]}</Text>
              <View style={styles.dataTrack}>
                <View style={[styles.dataBar, { width: `${value}%` }]} />
              </View>
              <Text style={styles.dataValue}>{value}</Text>
            </View>
          ))}
        </View>
      </View>
    );
  }

  return null;
}

function PostCollectionGrid({
  emptyIcon,
  emptySubtitle,
  emptyTitle,
  onLoadMore,
  onRefresh,
  onRemove,
  removeLabel,
  state,
}: {
  emptyIcon: IconName;
  emptySubtitle: string;
  emptyTitle: string;
  onLoadMore: () => Promise<void>;
  onRefresh: () => Promise<void>;
  onRemove: (socialPostId: string) => Promise<void>;
  removeLabel: string;
  state: PostCollectionState;
}) {
  if (state.loading && state.items.length === 0) {
    return <ContentLoading text="正在加载动态" />;
  }
  if (state.error && state.items.length === 0) {
    return <ContentError message={state.error} onRetry={onRefresh} />;
  }
  if (state.items.length === 0) {
    return <ContentEmpty icon={emptyIcon} subtitle={emptySubtitle} title={emptyTitle} />;
  }

  return (
    <View style={styles.windowList}>
      <View style={styles.contentGrid}>
        {state.items.map((item) => (
          <CollectionPostTile
            item={item}
            key={item.post.social_post_id}
            onRemove={onRemove}
            removeLabel={removeLabel}
          />
        ))}
      </View>
      {state.error ? (
        <View style={styles.collectionErrorPanel}>
          <Text style={styles.collectionErrorText}>{state.error}</Text>
          <Pressable accessibilityRole="button" onPress={() => void onRefresh()} style={styles.retryButton}>
            <Text style={styles.retryButtonText}>重试</Text>
          </Pressable>
        </View>
      ) : null}
      {state.hasMore ? (
        <Pressable
          accessibilityRole="button"
          disabled={state.loading}
          onPress={() => {
            void onLoadMore();
          }}
          style={[styles.loadMoreButton, state.loading && styles.loadMoreButtonDisabled]}
        >
          {state.loading ? (
            <ActivityIndicator color={colors.ink} size="small" />
          ) : (
            <Text style={styles.loadMoreText}>加载更多</Text>
          )}
        </Pressable>
      ) : null}
    </View>
  );
}

function CollectionPostTile({
  item,
  onRemove,
  removeLabel,
}: {
  item: PostDetailResponse;
  onRemove: (socialPostId: string) => Promise<void>;
  removeLabel: string;
}) {
  const [removing, setRemoving] = useState(false);

  async function handleRemove() {
    if (removing) {
      return;
    }
    setRemoving(true);
    try {
      await onRemove(item.post.social_post_id);
    } catch {
      setRemoving(false);
    }
  }

  return (
    <ProfilePostTile
      actionLabel={removeLabel}
      actionLoading={removing}
      authorAvatarPath={item.author.avatar_path}
      authorName={item.author.nickname}
      favoriteCount={item.stats?.favorite_count ?? 0}
      likeCount={item.stats?.like_count ?? 0}
      onAction={handleRemove}
      post={postDetailToProfilePost(item)}
      previewDetail={item}
    />
  );
}

function postDetailToProfilePost(detail: PostDetailResponse): ProfilePost {
  const firstMedia = detail.media[0] ?? null;
  const firstVideo = firstMedia?.video_id
    ? detail.videos.find((video) => video.video_id === firstMedia.video_id) ?? null
    : null;
  return {
    content: detail.post.content,
    created_at: detail.post.created_at,
    first_image_path: firstMedia?.image_path ?? null,
    first_media_type: firstMedia?.media_type ?? null,
    first_video_path: firstVideo?.video_path ?? null,
    first_video_thumbnail_path: firstVideo?.thumbnail_path ?? null,
    media_count: detail.media.length,
    published_at: detail.post.published_at,
    social_post_id: detail.post.social_post_id,
    source_tennis_activity_id: detail.post.source_tennis_activity_id,
    status: detail.post.status,
    title: detail.post.title,
    updated_at: detail.post.updated_at,
    visibility: detail.post.visibility,
  };
}

function ProfilePostTile({
  actionLabel,
  actionLoading = false,
  authorAvatarPath,
  authorName,
  favoriteCount,
  likeCount,
  onAction,
  post,
  previewDetail,
}: {
  actionLabel?: string;
  actionLoading?: boolean;
  authorAvatarPath?: string | null;
  authorName?: string;
  favoriteCount?: number;
  likeCount?: number;
  onAction?: () => void;
  post: ProfilePost;
  previewDetail?: PostDetailResponse;
}) {
  const router = useRouter();
  const preview = resolveMediaUrl(post.first_image_path ?? post.first_video_thumbnail_path);
  const authorAvatarUri = resolveMediaUrl(authorAvatarPath);
  const hasCollectionMeta = Boolean(authorName || likeCount !== undefined || favoriteCount !== undefined);
  const isVideo = post.first_media_type === "video" || post.first_media_type === "video_clip";

  return (
    <Pressable
      accessibilityRole="button"
      onPress={() => {
        if (previewDetail) {
          primePostDetailPreview(previewDetail);
        }
        router.push({
          pathname: "/post/[id]",
          params: { id: post.social_post_id },
        });
      }}
      style={styles.postTile}
    >
      <View style={styles.postTilePreview}>
        {preview ? (
          <Image contentFit="cover" source={{ uri: preview }} style={styles.postTileImage} />
        ) : (
          <View style={styles.postTilePlaceholder}>
            <Ionicons
              color={colors.accentDeep}
              name={isVideo ? "videocam-outline" : "images-outline"}
              size={24}
            />
          </View>
        )}
        <View style={styles.postTileOverlay}>
          <Ionicons
            color={colors.inverse}
            name={isVideo ? "play-circle" : "images-outline"}
            size={17}
          />
          <Text style={styles.postStatusText}>{post.status}</Text>
        </View>
      </View>
      {hasCollectionMeta ? (
        <View style={styles.postTileFooter}>
          <Text numberOfLines={2} style={styles.postTileFooterTitle}>
            {post.title || post.content || "我的动态"}
          </Text>
          {authorName ? (
            <View style={styles.postTileAuthorRow}>
              <Avatar name={authorName} size={18} uri={authorAvatarUri} />
              <Text numberOfLines={1} style={styles.postTileAuthorName}>
                {authorName}
              </Text>
            </View>
          ) : null}
          <View style={styles.postTileStatsRow}>
            <View style={styles.postTileStatItem}>
              <Ionicons color={colors.muted} name="heart-outline" size={13} />
              <Text style={styles.postTileStatText}>{likeCount ?? 0}</Text>
            </View>
            <View style={styles.postTileStatItem}>
              <Ionicons color={colors.muted} name="bookmark-outline" size={13} />
              <Text style={styles.postTileStatText}>{favoriteCount ?? 0}</Text>
            </View>
          </View>
        </View>
      ) : (
        <Text numberOfLines={2} style={styles.tileText}>
          {post.title || post.content || "我的动态"}
        </Text>
      )}
      {actionLabel ? (
        <Pressable
          accessibilityLabel={actionLabel}
          accessibilityRole="button"
          disabled={actionLoading}
          onPress={(event) => {
            event.stopPropagation();
            onAction?.();
          }}
          style={styles.postTileAction}
        >
          {actionLoading ? (
            <ActivityIndicator color={colors.ink} size="small" />
          ) : (
            <Ionicons
              color={colors.ink}
              name={actionLabel === "取消收藏" ? "bookmark" : "heart"}
              size={17}
            />
          )}
        </Pressable>
      ) : null}
    </Pressable>
  );
}

function contentDate(value: string | null) {
  if (!value) {
    return "未记录时间";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours().toString().padStart(2, "0")}:${date
    .getMinutes()
    .toString()
    .padStart(2, "0")}`;
}

function activityTypeLabel(value: ProfileActivity["activity_type"]) {
  const labels: Record<ProfileActivity["activity_type"], string> = {
    backhand_training: "反手",
    casual_hit: "对打",
    coach_demo: "教学",
    forehand_training: "正手",
    lesson_practice: "课程",
    match: "比赛",
    multi_ball_drill: "多球",
    other: "其他",
    post_match_review: "复盘",
    serve_training: "发球",
    stroke_recording: "录像",
  };
  return labels[value];
}

function uploadStatusLabel(value: ProfileActivity["upload_status"]) {
  const labels: Record<ProfileActivity["upload_status"], string> = {
    canceled: "已取消",
    failed: "上传失败",
    mixed: "部分上传",
    pending: "待上传",
    uploaded: "已上传",
    uploading: "上传中",
  };
  return labels[value];
}

function analysisStatusLabel(value: ProfileActivity["analysis_status"]) {
  const labels: Record<ProfileActivity["analysis_status"], string> = {
    canceled: "分析取消",
    completed: "分析完成",
    failed: "分析失败",
    mixed: "部分分析",
    none: "未分析",
    processing: "分析中",
    queued: "等待分析",
    uploaded: "待提交",
  };
  return labels[value];
}

function ProfileActivityRow({
  activity,
  onPress,
}: {
  activity: ProfileActivity;
  onPress: () => void;
}) {
  const title = activity.title || activity.first_video?.original_filename || "未命名 Activity";
  const videoStatus = activity.video_count > 0 ? uploadStatusLabel(activity.upload_status) : "无视频";
  const metaParts = [
    contentDate(activity.started_at ?? activity.created_at),
    formatActivityLocation(activity.location) !== "未记录位置"
      ? formatActivityLocation(activity.location)
      : activity.location_name,
    `${activity.video_count} 个视频`,
    videoStatus,
    analysisStatusLabel(activity.analysis_status),
  ].filter(Boolean);
  const thumbnail = resolveMediaUrl(activity.first_video?.thumbnail_path);
  const fallbackIcon: IconName =
    activity.activity_type === "match" ? "trophy-outline" : "fitness-outline";

  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.activityWindowRow}>
      <View style={styles.activityThumb}>
        {thumbnail ? (
          <Image contentFit="cover" source={{ uri: thumbnail }} style={styles.activityThumbImage} />
        ) : (
          <View style={styles.activityThumbFallback}>
            <Ionicons color={colors.inverse} name={fallbackIcon} size={19} />
          </View>
        )}
        {thumbnail ? (
          <View style={styles.activityThumbBadge}>
            <Ionicons color={colors.inverse} name="play" size={12} />
          </View>
        ) : null}
      </View>
      <View style={styles.activityWindowText}>
        <Text style={styles.windowTitle}>{title}</Text>
        <Text numberOfLines={2} style={styles.windowMeta}>{metaParts.join(" · ")}</Text>
      </View>
      <Pill>{activityTypeLabel(activity.activity_type)}</Pill>
    </Pressable>
  );
}

function ProfileLessonRow({ lesson }: { lesson: ProfileLesson }) {
  const title = lesson.title || `课程 ${lesson.lesson_id.slice(0, 8)}`;
  const subtitle = [
    lesson.role === "coach" ? "我是教练" : "我是学员",
    lesson.status,
    contentDate(lesson.started_at ?? lesson.updated_at),
    `${lesson.activity_count} 个 activity`,
    `${lesson.video_count} 个视频`,
  ].join(" · ");

  return (
    <View style={styles.activityWindowRow}>
      <View style={[styles.rowAccent, styles.rowAccentSky]} />
      <View style={styles.activityWindowText}>
        <Text style={styles.windowTitle}>{title}</Text>
        <Text numberOfLines={2} style={styles.windowMeta}>{subtitle}</Text>
      </View>
      <Pill>{lesson.role === "coach" ? "教练" : "学员"}</Pill>
    </View>
  );
}

function ContentLoading({ text = "正在加载我的内容" }: { text?: string }) {
  return (
    <View style={styles.contentStatePanel}>
      <ActivityIndicator color={colors.accentDeep} />
      <Text style={styles.contentStateText}>{text}</Text>
    </View>
  );
}

function ContentError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <View style={styles.contentStatePanel}>
      <IconBadge name="alert-circle-outline" tone="clay" />
      <Text style={styles.contentStateTitle}>加载失败</Text>
      <Text style={styles.contentStateText}>{message}</Text>
      <Pressable accessibilityRole="button" onPress={onRetry} style={styles.retryButton}>
        <Text style={styles.retryButtonText}>重试</Text>
      </Pressable>
    </View>
  );
}

function ContentEmpty({
  icon,
  subtitle,
  title,
}: {
  icon: IconName;
  subtitle: string;
  title: string;
}) {
  return (
    <View style={styles.contentStatePanel}>
      <IconBadge name={icon} />
      <Text style={styles.contentStateTitle}>{title}</Text>
      <Text style={styles.contentStateText}>{subtitle}</Text>
    </View>
  );
}

function CoachWorkspace({
  coachIdentity,
  onSwitchToPlayer,
}: {
  coachIdentity: CoachIdentity | null;
  onSwitchToPlayer: () => void;
}) {
  const router = useRouter();
  const fullCoach = coachIdentity?.status === "certified_coach";
  const identityLabel = coachIdentity?.label ?? "教练";
  const canManageCourses = Boolean(coachIdentity?.capabilities.course_management);
  const canManageStudents = Boolean(coachIdentity?.capabilities.student_management);

  return (
    <View style={styles.profileBody}>
      <View style={styles.profileTop}>
        <View>
          <Text style={styles.profileHandle}>{identityLabel}工作台</Text>
          <Text style={styles.coachTopHint}>
            {fullCoach ? "今天有 2 节课，2 条视频待点评" : "基础教学服务、视频点评和学员咨询"}
          </Text>
        </View>
        <Pressable
          accessibilityLabel="切换到球员模式"
          accessibilityRole="button"
          onPress={onSwitchToPlayer}
          style={styles.modeButton}
        >
          <Ionicons color={colors.accentDeep} name="tennisball-outline" size={16} />
          <Text style={styles.modeButtonText}>球员模式</Text>
        </Pressable>
      </View>

      <View style={styles.coachHero}>
        <View style={styles.coachHeroTop}>
          <View>
            <Text style={styles.coachTitle}>教学概览</Text>
            <Text style={styles.coachSubtitle}>
              {fullCoach ? "学员跟进、课程记录和视频点评集中处理" : "陪练、基础教学服务和视频点评集中处理"}
            </Text>
          </View>
          <IconBadge name="school-outline" tone="sky" />
        </View>
        <View style={styles.coachStats}>
          <ProfileStat inverse label={fullCoach ? "学员" : "服务"} value={fullCoach ? "28" : "3"} />
          <ProfileStat inverse label={fullCoach ? "本周课" : "咨询"} value={fullCoach ? "11" : "6"} />
          <ProfileStat inverse label="待点评" value="2" />
        </View>
      </View>

      {canManageStudents ? (
        <View style={styles.section}>
          <SectionHeader action="全部学员" title="学员列表" />
          <View style={styles.studentList}>
            {students.map((student) => (
              <Pressable
                accessibilityLabel={`查看${student.name}档案`}
                accessibilityRole="button"
                key={student.id}
                onPress={() => router.push({ pathname: "/student/[id]", params: { id: student.id } })}
                style={styles.studentRow}
              >
                <Avatar name={student.name} size={46} />
                <View style={styles.studentInfo}>
                  <View style={styles.studentTopLine}>
                    <Text style={styles.studentName}>{student.name}</Text>
                    <Pill>{student.level}</Pill>
                  </View>
                  <Text style={styles.studentMeta}>
                    {student.focus} · 最近上课 {student.lastLesson}
                  </Text>
                </View>
                <Ionicons color={colors.muted} name="chevron-forward" size={18} />
              </Pressable>
            ))}
          </View>
        </View>
      ) : (
        <View style={styles.section}>
          <SectionHeader title="可用服务" />
          <View style={styles.compactList}>
            <RowButton icon="tennisball-outline" subtitle="陪练、基础教学、技术展示" title="发布基础教学服务" />
            <RowButton icon="chatbubble-ellipses-outline" subtitle="接收学员咨询和初步沟通" title="学员咨询" />
          </View>
        </View>
      )}

      {canManageCourses ? (
        <View style={styles.section}>
          <SectionHeader title="最近课程" />
          <View style={styles.compactList}>
            {coachCourses.map((course) => (
              <RowButton
                icon="calendar-outline"
                key={course.id}
                onPress={() =>
                  router.push({
                    pathname: "/create-placeholder",
                    params: { type: "课程记录" },
                  })
                }
                subtitle={`${course.time} · ${course.students}`}
                title={course.title}
              />
            ))}
          </View>
        </View>
      ) : null}

      <View style={styles.section}>
        <SectionHeader title="待点评视频" />
        <View style={styles.compactList}>
          {pendingVideos.map((video) => (
            <RowButton
              icon="videocam-outline"
              key={video.id}
              onPress={() =>
                router.push({
                  pathname: "/create-placeholder",
                  params: { type: "待点评视频" },
                })
              }
              subtitle={`${video.time} · ${video.length}`}
              title={video.title}
              trailing={<Text style={styles.reviewTag}>点评</Text>}
            />
          ))}
        </View>
      </View>

      <View style={styles.section}>
        <SectionHeader title="教学记录" />
        <Card style={styles.noteCard}>
          <Text style={styles.noteTitle}>本周重点</Text>
          <Text style={styles.noteText}>发球组继续观察抛球高度，青少年组记录正手击球点变化。</Text>
        </Card>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  page: {
    paddingTop: 28,
  },
  guestPanel: {
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 16,
    padding: 16,
  },
  guestHero: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 12,
  },
  guestAvatar: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: 28,
    height: 56,
    justifyContent: "center",
    width: 56,
  },
  guestHeroText: {
    flex: 1,
    gap: 7,
  },
  guestTitle: {
    color: colors.ink,
    fontSize: 22,
    fontWeight: "900",
  },
  guestText: {
    color: colors.inkSoft,
    fontSize: 13,
    fontWeight: "600",
    lineHeight: 19,
  },
  loginButton: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    minHeight: 52,
    justifyContent: "center",
  },
  loginButtonText: {
    color: colors.inverse,
    fontSize: 15,
    fontWeight: "900",
  },
  guestSummary: {
    gap: 8,
  },
  guestSummaryRow: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 3,
    padding: 12,
  },
  guestSummaryLabel: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "700",
  },
  guestSummaryValue: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "800",
  },
  profileBody: {
    gap: 18,
  },
  profileTop: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    minHeight: 40,
  },
  profileHandle: {
    color: colors.ink,
    fontSize: 22,
    fontWeight: "900",
  },
  modeButton: {
    alignItems: "center",
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 5,
    minHeight: 32,
    paddingHorizontal: 10,
  },
  modeButtonText: {
    color: colors.accentDeep,
    fontSize: 12,
    fontWeight: "800",
  },
  headerActions: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  menuButton: {
    alignItems: "center",
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    height: 36,
    justifyContent: "center",
    width: 36,
  },
  playerHeaderRow: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 10,
    justifyContent: "space-between",
  },
  playerHero: {
    alignItems: "flex-start",
    flex: 1,
    flexDirection: "row",
    gap: 14,
  },
  playerInfo: {
    flex: 1,
    gap: 8,
    paddingTop: 2,
  },
  nameLine: {
    alignItems: "center",
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  playerName: {
    color: colors.ink,
    fontSize: 24,
    fontWeight: "900",
  },
  socialStats: {
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    paddingVertical: 12,
  },
  profileStat: {
    alignItems: "center",
    flex: 1,
    gap: 4,
  },
  profileStatValue: {
    color: colors.ink,
    fontSize: 19,
    fontWeight: "900",
  },
  profileStatValueInverse: {
    color: colors.inverse,
  },
  profileStatLabel: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "700",
  },
  profileStatLabelInverse: {
    color: "#E7EDF2",
  },
  playerTabList: {
    gap: 8,
    paddingRight: 20,
  },
  playerTab: {
    alignItems: "center",
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 6,
    minHeight: 38,
    paddingHorizontal: 12,
  },
  playerTabActive: {
    backgroundColor: colors.accentSoft,
    borderColor: "#D9E7EF",
  },
  playerTabText: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "800",
  },
  playerTabTextActive: {
    color: colors.ink,
  },
  contentGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
    rowGap: 8,
  },
  postTile: {
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: "hidden",
    width: "49%",
  },
  postTilePreview: {
    aspectRatio: 0.9,
    backgroundColor: colors.accentSoft,
    width: "100%",
  },
  postTileImage: {
    height: "100%",
    width: "100%",
  },
  postTileOverlay: {
    alignItems: "center",
    backgroundColor: "rgba(17,19,21,0.62)",
    borderRadius: radius.control,
    flexDirection: "row",
    gap: 4,
    minHeight: 26,
    paddingHorizontal: 8,
    position: "absolute",
    right: 7,
    top: 7,
  },
  postTileAction: {
    alignItems: "center",
    backgroundColor: "rgba(255,253,247,0.92)",
    borderRadius: radius.control,
    height: 30,
    justifyContent: "center",
    left: 7,
    position: "absolute",
    top: 7,
    width: 30,
  },
  postTileFooter: {
    gap: 6,
    minHeight: 86,
    paddingHorizontal: 8,
    paddingVertical: 8,
  },
  postTileFooterTitle: {
    color: colors.inkSoft,
    fontSize: 12,
    fontWeight: "800",
    lineHeight: 16,
    minHeight: 32,
  },
  postTileAuthorRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 6,
    minHeight: 20,
  },
  postTileAuthorName: {
    color: colors.muted,
    flex: 1,
    fontSize: 11,
    fontWeight: "800",
  },
  postTileStatsRow: {
    flexDirection: "row",
    gap: 12,
    minHeight: 18,
  },
  postTileStatItem: {
    alignItems: "center",
    flexDirection: "row",
    gap: 3,
  },
  postTileStatText: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "800",
  },
  tileText: {
    backgroundColor: "rgba(255,253,247,0.92)",
    bottom: 0,
    color: colors.inkSoft,
    fontSize: 12,
    fontWeight: "700",
    left: 0,
    lineHeight: 16,
    minHeight: 36,
    paddingHorizontal: 7,
    paddingVertical: 6,
    position: "absolute",
    right: 0,
  },
  postTilePlaceholder: {
    alignItems: "center",
    backgroundColor: colors.accentSoft,
    flex: 1,
    justifyContent: "center",
  },
  postStatusText: {
    color: colors.inverse,
    fontSize: 11,
    fontWeight: "800",
  },
  collectionErrorPanel: {
    alignItems: "flex-start",
    gap: 8,
  },
  collectionErrorText: {
    color: "#B14A3D",
    fontSize: 13,
    fontWeight: "700",
    lineHeight: 19,
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
  windowList: {
    gap: 10,
  },
  activityWindowRow: {
    alignItems: "center",
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 12,
    minHeight: 72,
    overflow: "hidden",
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  activityThumb: {
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    height: 58,
    overflow: "hidden",
    width: 58,
  },
  activityThumbImage: {
    height: "100%",
    width: "100%",
  },
  activityThumbFallback: {
    alignItems: "center",
    backgroundColor: colors.ink,
    flex: 1,
    justifyContent: "center",
  },
  activityThumbBadge: {
    alignItems: "center",
    backgroundColor: "rgba(17,19,21,0.68)",
    borderRadius: 11,
    bottom: 5,
    height: 22,
    justifyContent: "center",
    position: "absolute",
    right: 5,
    width: 22,
  },
  rowAccent: {
    backgroundColor: colors.clay,
    borderRadius: 2,
    height: 42,
    width: 4,
  },
  rowAccentSky: {
    backgroundColor: colors.sky,
  },
  activityWindowText: {
    flex: 1,
    gap: 5,
  },
  windowTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
  },
  windowMeta: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "600",
    lineHeight: 18,
  },
  windowCard: {
    alignItems: "center",
    flexDirection: "row",
    gap: 12,
  },
  windowCardText: {
    flex: 1,
    gap: 5,
  },
  contentStatePanel: {
    alignItems: "flex-start",
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 9,
    padding: 16,
  },
  contentStateTitle: {
    color: colors.ink,
    fontSize: 17,
    fontWeight: "900",
  },
  contentStateText: {
    color: colors.inkSoft,
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
  dataWindow: {
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 16,
    padding: 14,
  },
  dataWindowHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  dataBars: {
    gap: 13,
  },
  dataBarRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
  },
  dataLabel: {
    color: colors.inkSoft,
    fontSize: 12,
    fontWeight: "800",
    width: 40,
  },
  dataTrack: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: 4,
    flex: 1,
    height: 8,
    overflow: "hidden",
  },
  dataBar: {
    backgroundColor: colors.accentDeep,
    borderRadius: 4,
    height: 8,
  },
  dataValue: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: "800",
    width: 26,
  },
  coachTopHint: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
    marginTop: 4,
  },
  coachHero: {
    backgroundColor: "#465160",
    borderColor: "#465160",
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 18,
    padding: 16,
  },
  coachHeroTop: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  coachTitle: {
    color: colors.inverse,
    fontSize: 24,
    fontWeight: "900",
  },
  coachSubtitle: {
    color: "#E7EDF2",
    fontSize: 13,
    fontWeight: "600",
    lineHeight: 19,
    marginTop: 5,
  },
  coachStats: {
    backgroundColor: "rgba(255,255,255,0.12)",
    borderRadius: radius.card,
    flexDirection: "row",
    paddingVertical: 12,
  },
  section: {
    gap: 0,
  },
  studentList: {
    gap: 10,
  },
  studentRow: {
    alignItems: "center",
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 12,
    minHeight: 78,
    paddingHorizontal: 14,
  },
  studentInfo: {
    flex: 1,
    gap: 5,
  },
  studentTopLine: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  studentName: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "800",
  },
  studentMeta: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "600",
  },
  compactList: {
    gap: 10,
  },
  reviewTag: {
    color: colors.accentDeep,
    fontSize: 13,
    fontWeight: "800",
  },
  noteCard: {
    gap: 7,
  },
  noteTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "800",
  },
  noteText: {
    color: colors.inkSoft,
    fontSize: 13,
    fontWeight: "600",
    lineHeight: 20,
  },
  drawerBackdrop: {
    alignItems: "flex-end",
    backgroundColor: "rgba(36,42,46,0.28)",
    flex: 1,
  },
  sideDrawer: {
    backgroundColor: colors.background,
    borderLeftColor: colors.line,
    borderLeftWidth: StyleSheet.hairlineWidth,
    flex: 1,
    gap: 18,
    paddingHorizontal: 16,
    paddingTop: 54,
    width: "82%",
  },
  drawerHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  drawerKicker: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "800",
  },
  drawerTitle: {
    color: colors.ink,
    fontSize: 24,
    fontWeight: "900",
    marginTop: 2,
  },
  drawerClose: {
    alignItems: "center",
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    height: 36,
    justifyContent: "center",
    width: 36,
  },
  drawerList: {
    gap: 10,
  },
});
