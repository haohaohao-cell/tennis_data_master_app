import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { ApiError } from "@/api/client";
import {
  coarseLocationFromActivityLocation,
  formatActivityLocation,
  formatActivityLocationStatus,
  getActivityLocationFromVideoAsset,
  getCurrentActivityLocation,
  refreshCurrentActivityLocation,
  type MobileLocationResult,
} from "@/api/location";
import {
  createPostUploadIntent,
  deletePost,
  publishPost,
  type PostUploadIntentResponse,
  type PostVisibility,
} from "@/api/posts";
import {
  normalizeVideoDurationMs,
  normalizeVideoFileName,
  normalizeVideoMimeType,
  uploadVideoFile,
} from "@/api/uploads";
import { useAuth } from "@/auth/AuthProvider";
import { IconBadge, ScrollPage, TopBar } from "@/components/ui";
import { useActivityLocationCache } from "@/location/ActivityLocationProvider";
import { colors, radius } from "@/theme";

type LocalPostVideoStatus = "ready" | "uploading" | "uploaded" | "failed";

type LocalPostVideo = {
  assetId: string | null;
  durationMs: number | null;
  error: string | null;
  fileSize: number | null;
  localId: string;
  mimeType: string | null;
  name: string;
  progress: number;
  serverVideoId: string | null;
  status: LocalPostVideoStatus;
  uri: string;
};

const MAX_POST_VIDEO_DURATION_MS = 10 * 60 * 1000;

const visibilityOptions: { label: string; value: PostVisibility }[] = [
  { label: "公开", value: "public" },
  { label: "仅自己", value: "private" },
];

function errorMessage(error: unknown) {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "操作失败，请稍后重试";
}

function formatBytes(value: number | null) {
  if (!value) {
    return "未知大小";
  }
  if (value < 1024 * 1024) {
    return `${Math.max(1, Math.round(value / 1024))} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(value > 100 * 1024 * 1024 ? 0 : 1)} MB`;
}

function formatDuration(value: number | null) {
  if (value === null) {
    return "未知时长";
  }
  const totalSeconds = Math.max(0, Math.round(value / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function isTooLong(durationMs: number | null) {
  return durationMs !== null && durationMs > MAX_POST_VIDEO_DURATION_MS;
}

export default function CreatePostScreen() {
  const router = useRouter();
  const { accessToken, isAuthenticated, status } = useAuth();
  const { locationResult: cachedLocationResult } = useActivityLocationCache();
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [visibility, setVisibility] = useState<PostVisibility>("public");
  const [locationResult, setLocationResult] = useState<MobileLocationResult | null>(null);
  const [video, setVideo] = useState<LocalPostVideo | null>(null);
  const [intent, setIntent] = useState<PostUploadIntentResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [locating, setLocating] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const locked = Boolean(intent) || busy || completed;

  useEffect(() => {
    if (cachedLocationResult) {
      setLocationResult((current) => (current?.location.source === "video_metadata" ? current : cachedLocationResult));
    }
  }, [cachedLocationResult]);

  function patchVideo(patch: Partial<LocalPostVideo>) {
    setVideo((current) => (current ? { ...current, ...patch } : current));
  }

  async function handlePickVideo() {
    if (locked) {
      return;
    }

    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert("无法选择视频", "请允许访问相册后再发布动态。");
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      allowsMultipleSelection: false,
      mediaTypes: ["videos"],
      preferredAssetRepresentationMode: ImagePicker.UIImagePickerPreferredAssetRepresentationMode.Current,
      quality: 1,
      selectionLimit: 1,
    });

    if (result.canceled || !result.assets?.length) {
      return;
    }

    const asset = result.assets[0];
    const durationMs = normalizeVideoDurationMs(asset.duration);
    if (durationMs === null) {
      Alert.alert("无法读取时长", "请选择能读取到时长的视频后再发布。");
      return;
    }
    if (isTooLong(durationMs)) {
      Alert.alert("视频过长", "动态视频暂时不能超过 10 分钟。");
      return;
    }
    const videoName = normalizeVideoFileName({
      fallbackBase: "post-video",
      fileName: asset.fileName,
      mimeType: asset.mimeType,
      uri: asset.uri,
    });

    setError(null);
    setIntent(null);
    setCompleted(false);
    setVideo({
      assetId: asset.assetId ?? null,
      durationMs,
      error: null,
      fileSize: asset.fileSize ?? null,
      localId: `${Date.now()}-${asset.uri}`,
      mimeType: normalizeVideoMimeType(asset.mimeType, videoName),
      name: videoName,
      progress: 0,
      serverVideoId: null,
      status: "ready",
      uri: asset.uri,
    });

    const videoLocation = await getActivityLocationFromVideoAsset(asset.assetId);
    if (videoLocation) {
      setLocationResult(videoLocation);
    } else {
      setLocationResult((current) =>
        current?.location.source === "video_metadata" ? cachedLocationResult : current,
      );
    }
  }

  function validateBeforePublish() {
    if (!accessToken) {
      return "请先登录后再发布动态。";
    }
    if (!video) {
      return "请先选择一段短视频。";
    }
    if (video.durationMs === null) {
      return "无法确认视频时长，请重新选择视频。";
    }
    if (isTooLong(video.durationMs)) {
      return "动态视频暂时不能超过 10 分钟。";
    }
    return null;
  }

  async function refreshLocation() {
    if (locked || locating) {
      return locationResult;
    }
    setLocating(true);
    try {
      const nextLocation = await refreshCurrentActivityLocation();
      setLocationResult(nextLocation);
      return nextLocation;
    } finally {
      setLocating(false);
    }
  }

  function buildPayload(activeVideo: LocalPostVideo, activeLocation: MobileLocationResult) {
    const { city, region } = coarseLocationFromActivityLocation(activeLocation.location);
    const locationScope: "none" | "region" | "city" = city ? "city" : region ? "region" : "none";
    return {
      content: content.trim() || null,
      location_city: city || null,
      location_region: region || null,
      location_scope: locationScope,
      title: title.trim() || null,
      visibility,
      videos: [
        {
          file_size_bytes: activeVideo.fileSize,
          mime_type: activeVideo.mimeType,
          original_filename: activeVideo.name,
          video_duration_ms: normalizeVideoDurationMs(activeVideo.durationMs) ?? 0,
        },
      ],
    };
  }

  async function handlePublish() {
    const validationError = validateBeforePublish();
    if (validationError || !accessToken || !video) {
      setError(validationError);
      return;
    }

    setBusy(true);
    setError(null);

    try {
      const nextLocation = locationResult ?? (await getCurrentActivityLocation());
      setLocationResult(nextLocation);
      let activeIntent = intent;
      if (!activeIntent) {
        activeIntent = await createPostUploadIntent(accessToken, buildPayload(video, nextLocation));
        setIntent(activeIntent);
        patchVideo({
          serverVideoId: activeIntent.videos[0]?.video_id ?? null,
        });
      }

      const serverVideo = activeIntent.videos[0];
      if (!serverVideo) {
        throw new Error("服务端视频记录缺失");
      }

      if (video.status !== "uploaded") {
        patchVideo({
          error: null,
          progress: Math.max(video.progress, 0.02),
          serverVideoId: serverVideo.video_id,
          status: "uploading",
        });
        await uploadVideoFile({
          accessToken,
          file: {
            mimeType: video.mimeType,
            name: video.name,
            uri: video.uri,
          },
          onProgress: (progress) => patchVideo({ progress }),
          videoId: serverVideo.video_id,
        });
        patchVideo({
          error: null,
          progress: 1,
          status: "uploaded",
        });
      }

      const published = await publishPost(accessToken, activeIntent.post.social_post_id);
      setIntent({
        ...published,
        max_video_duration_ms: activeIntent.max_video_duration_ms,
      });
      setCompleted(true);
      Alert.alert("发布成功", "动态已发布。", [
        {
          onPress: () => router.replace("/(tabs)/profile"),
          text: "查看我的动态",
        },
      ]);
    } catch (nextError) {
      patchVideo({
        error: errorMessage(nextError),
        status: video.status === "uploaded" ? "uploaded" : "failed",
      });
      setError(errorMessage(nextError));
    } finally {
      setBusy(false);
    }
  }

  async function handleCancelDraft() {
    if (busy || completed) {
      return;
    }
    if (intent && accessToken) {
      setBusy(true);
      setError(null);
      try {
        await deletePost(accessToken, intent.post.social_post_id);
      } catch (nextError) {
        setError(errorMessage(nextError));
        setBusy(false);
        return;
      }
      setBusy(false);
    }
    setIntent(null);
    setVideo(null);
  }

  if (status === "loading") {
    return (
      <ScrollPage contentStyle={styles.page}>
        <TopBar onBack={() => router.back()} title="发布动态" />
        <View style={styles.centerPanel}>
          <ActivityIndicator color={colors.ink} />
          <Text style={styles.mutedText}>正在确认账户状态</Text>
        </View>
      </ScrollPage>
    );
  }

  if (!isAuthenticated) {
    return (
      <ScrollPage contentStyle={styles.page}>
        <TopBar onBack={() => router.back()} title="发布动态" />
        <View style={styles.centerPanel}>
          <IconBadge name="log-in-outline" />
          <Text style={styles.emptyTitle}>登录后发布</Text>
          <Text style={styles.mutedText}>动态需要归属到你的账户。</Text>
          <Pressable
            accessibilityRole="button"
            onPress={() =>
              router.replace({
                pathname: "/login",
                params: { redirect: "/create-post" },
              })
            }
            style={styles.primaryButton}
          >
            <Text style={styles.primaryButtonText}>登录 / 注册</Text>
          </Pressable>
        </View>
      </ScrollPage>
    );
  }

  return (
    <ScrollPage contentStyle={styles.page}>
      <TopBar onBack={() => router.back()} subtitle="Post" title="发布动态" />

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>内容</Text>
        <View style={styles.fieldBlock}>
          <Text style={styles.label}>标题</Text>
          <TextInput
            editable={!locked}
            maxLength={120}
            onChangeText={setTitle}
            placeholder="给这段视频起个名字"
            placeholderTextColor={colors.muted}
            style={styles.input}
            value={title}
          />
        </View>
        <View style={styles.fieldBlock}>
          <Text style={styles.label}>正文</Text>
          <TextInput
            editable={!locked}
            maxLength={2200}
            multiline
            onChangeText={setContent}
            placeholder="记录这一拍、这次训练或想分享的瞬间"
            placeholderTextColor={colors.muted}
            style={[styles.input, styles.textArea]}
            value={content}
          />
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>可见范围</Text>
        <View style={styles.chipWrap}>
          {visibilityOptions.map((option) => {
            const selected = visibility === option.value;
            return (
              <Pressable
                accessibilityRole="button"
                disabled={locked}
                key={option.value}
                onPress={() => setVisibility(option.value)}
                style={[styles.chip, selected && styles.chipActive, locked && styles.disabledBlock]}
              >
                <Text style={[styles.chipText, selected && styles.chipTextActive]}>
                  {option.label}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>发布位置</Text>
        <Text style={styles.locationNote}>会先获取经纬度，再自动转换为城市和区；发布时只保存粗粒度位置。</Text>
        <Pressable
          accessibilityRole="button"
          disabled={locked || locating}
          onPress={refreshLocation}
          style={[styles.locationCard, (locked || locating) && styles.disabledBlock]}
        >
          <View style={styles.locationIcon}>
            {locating ? (
              <ActivityIndicator color={colors.accentDeep} size="small" />
            ) : (
              <Ionicons color={colors.accentDeep} name="location-outline" size={18} />
            )}
          </View>
          <View style={styles.locationCopy}>
            <Text style={styles.locationTitle}>
              {locating ? "正在获取当前位置" : formatActivityLocation(locationResult?.location)}
            </Text>
            <Text style={styles.locationText}>
              {formatActivityLocationStatus(
                locationResult,
                "发布前会自动获取定位；请允许定位权限并开启系统位置服务。",
              )}
            </Text>
          </View>
        </Pressable>
      </View>

      <View style={styles.section}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>短视频</Text>
          <Text style={styles.countText}>{video ? "1/1" : "0/1"}</Text>
        </View>

        {video ? (
          <View style={styles.videoPanel}>
            <View style={styles.videoIcon}>
              <Ionicons color={colors.accentDeep} name="videocam-outline" size={24} />
            </View>
            <View style={styles.videoBody}>
              <Text numberOfLines={1} style={styles.videoName}>
                {video.name}
              </Text>
              <Text style={styles.videoMeta}>
                {formatBytes(video.fileSize)} · {formatDuration(video.durationMs)}
              </Text>
              {video.status !== "ready" ? (
                <View style={styles.progressTrack}>
                  <View style={[styles.progressFill, { width: `${Math.round(video.progress * 100)}%` }]} />
                </View>
              ) : null}
              {video.error ? <Text style={styles.errorText}>{video.error}</Text> : null}
            </View>
            <View style={styles.videoTrailing}>
              {video.status === "uploaded" ? (
                <Ionicons color={colors.accentDeep} name="checkmark-circle" size={22} />
              ) : video.status === "uploading" ? (
                <ActivityIndicator color={colors.accentDeep} size="small" />
              ) : video.status === "failed" ? (
                <Ionicons color="#B14A3D" name="alert-circle" size={22} />
              ) : (
                <Pressable accessibilityRole="button" onPress={() => setVideo(null)} style={styles.iconButton}>
                  <Ionicons color={colors.muted} name="close" size={17} />
                </Pressable>
              )}
            </View>
          </View>
        ) : (
          <Pressable
            accessibilityRole="button"
            disabled={locked}
            onPress={handlePickVideo}
            style={[styles.addVideoButton, locked && styles.disabledBlock]}
          >
            <Ionicons color={colors.ink} name="albums-outline" size={20} />
            <Text style={styles.addVideoText}>选择手机视频</Text>
          </Pressable>
        )}
      </View>

      {intent ? (
        <View style={styles.intentPanel}>
          <Text style={styles.intentTitle}>Post 草稿已创建</Text>
          <Text numberOfLines={1} style={styles.intentId}>
            {intent.post.social_post_id}
          </Text>
        </View>
      ) : null}

      {error ? <Text style={styles.errorText}>{error}</Text> : null}
      {completed ? <Text style={styles.successText}>动态已发布。</Text> : null}

      <View style={styles.actionBar}>
        {intent && !completed ? (
          <Pressable
            accessibilityRole="button"
            disabled={busy}
            onPress={handleCancelDraft}
            style={[styles.secondaryButton, busy && styles.disabledBlock]}
          >
            <Text style={styles.secondaryButtonText}>取消草稿</Text>
          </Pressable>
        ) : null}
        <Pressable
          accessibilityRole="button"
          disabled={busy || completed || !video}
          onPress={handlePublish}
          style={[styles.primaryButton, (busy || completed || !video) && styles.disabledButton]}
        >
          {busy ? (
            <ActivityIndicator color={colors.inverse} />
          ) : (
            <>
              <Ionicons color={colors.inverse} name="send-outline" size={18} />
              <Text style={styles.primaryButtonText}>
                {intent && video?.status === "failed" ? "重试发布" : "发布"}
              </Text>
            </>
          )}
        </Pressable>
      </View>
    </ScrollPage>
  );
}

const styles = StyleSheet.create({
  page: {
    gap: 20,
  },
  centerPanel: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 12,
    justifyContent: "center",
    minHeight: 220,
    padding: 20,
  },
  emptyTitle: {
    color: colors.ink,
    fontSize: 20,
    fontWeight: "900",
  },
  mutedText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "600",
    textAlign: "center",
  },
  section: {
    gap: 12,
  },
  sectionHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  sectionTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "900",
  },
  countText: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "700",
  },
  fieldBlock: {
    gap: 7,
  },
  label: {
    color: colors.inkSoft,
    fontSize: 13,
    fontWeight: "800",
  },
  input: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    color: colors.ink,
    fontSize: 15,
    minHeight: 48,
    paddingHorizontal: 14,
    paddingVertical: 11,
  },
  textArea: {
    minHeight: 116,
    textAlignVertical: "top",
  },
  chipWrap: {
    flexDirection: "row",
    gap: 9,
  },
  chip: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    minHeight: 38,
    minWidth: 76,
    justifyContent: "center",
    paddingHorizontal: 14,
  },
  chipActive: {
    backgroundColor: colors.accentSoft,
    borderColor: colors.accent,
  },
  chipText: {
    color: colors.inkSoft,
    fontSize: 14,
    fontWeight: "800",
  },
  chipTextActive: {
    color: colors.ink,
  },
  locationNote: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "600",
    marginTop: -4,
  },
  locationCard: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 11,
    minHeight: 58,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  locationCopy: {
    flex: 1,
    gap: 3,
  },
  locationIcon: {
    alignItems: "center",
    backgroundColor: colors.accentSoft,
    borderRadius: radius.control,
    height: 38,
    justifyContent: "center",
    width: 38,
  },
  locationText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
    lineHeight: 17,
  },
  locationTitle: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "900",
  },
  addVideoButton: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderStyle: "dashed",
    borderWidth: 1,
    flexDirection: "row",
    gap: 9,
    justifyContent: "center",
    minHeight: 96,
  },
  addVideoText: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
  },
  videoPanel: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 12,
    minHeight: 96,
    padding: 12,
  },
  videoIcon: {
    alignItems: "center",
    backgroundColor: colors.accentSoft,
    borderRadius: radius.control,
    height: 52,
    justifyContent: "center",
    width: 52,
  },
  videoBody: {
    flex: 1,
    gap: 5,
  },
  videoName: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
  },
  videoMeta: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
  videoTrailing: {
    alignItems: "center",
    minWidth: 30,
  },
  iconButton: {
    alignItems: "center",
    backgroundColor: colors.surfaceMuted,
    borderRadius: 15,
    height: 30,
    justifyContent: "center",
    width: 30,
  },
  progressTrack: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: 4,
    height: 7,
    overflow: "hidden",
  },
  progressFill: {
    backgroundColor: colors.accentDeep,
    borderRadius: 4,
    height: 7,
  },
  intentPanel: {
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 4,
    padding: 12,
  },
  intentTitle: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "900",
  },
  intentId: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
  errorText: {
    color: "#B14A3D",
    fontSize: 13,
    fontWeight: "700",
  },
  successText: {
    color: colors.accentDeep,
    fontSize: 13,
    fontWeight: "800",
  },
  actionBar: {
    flexDirection: "row",
    gap: 10,
    marginTop: 2,
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    flex: 1,
    flexDirection: "row",
    gap: 8,
    justifyContent: "center",
    minHeight: 50,
    paddingHorizontal: 16,
  },
  primaryButtonText: {
    color: colors.inverse,
    fontSize: 15,
    fontWeight: "900",
  },
  secondaryButton: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    justifyContent: "center",
    minHeight: 50,
    paddingHorizontal: 16,
  },
  secondaryButtonText: {
    color: colors.inkSoft,
    fontSize: 14,
    fontWeight: "900",
  },
  disabledButton: {
    opacity: 0.45,
  },
  disabledBlock: {
    opacity: 0.55,
  },
});
