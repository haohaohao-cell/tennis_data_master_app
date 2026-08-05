import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";
import { useRouter } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { ApiError } from "@/api/client";
import {
  formatActivityLocation,
  formatActivityLocationStatus,
  getActivityLocationFromVideoAsset,
  getCurrentActivityLocation,
  refreshCurrentActivityLocation,
  type MobileLocationResult,
} from "@/api/location";
import {
  cancelActivityUpload,
  completeActivityUpload,
  createUploadIntent,
  listUploadLessons,
  normalizeVideoDurationMs,
  normalizeVideoFileName,
  normalizeVideoMimeType,
  uploadVideoFile,
  type ActivityType,
  type ActivityVisibility,
  type LessonOption,
  type UploadIntentResponse,
} from "@/api/uploads";
import { useAuth } from "@/auth/AuthProvider";
import { IconBadge, ScrollPage, TopBar, type IconName } from "@/components/ui";
import { useActivityLocationCache } from "@/location/ActivityLocationProvider";
import { colors, radius } from "@/theme";

type UploadMode = "personal" | "lesson_practice" | "coach_demo";
type LocalVideoStatus = "ready" | "uploading" | "uploaded" | "failed";
type UploadPhase =
  | "idle"
  | "resolving_location"
  | "creating_activity"
  | "uploading_file"
  | "saving_file"
  | "finalizing_activity";

type LocalVideo = {
  assetId: string | null;
  durationMs: number | null;
  error: string | null;
  fileSize: number | null;
  localId: string;
  mimeType: string | null;
  name: string;
  progress: number;
  serverVideoId: string | null;
  status: LocalVideoStatus;
  uri: string;
};

const MAX_VIDEOS = 20;

const uploadModes: {
  coachOnly?: boolean;
  icon: IconName;
  label: string;
  value: UploadMode;
}[] = [
  { icon: "tennisball-outline", label: "个人活动", value: "personal" },
  { icon: "school-outline", label: "课程练习", value: "lesson_practice" },
  { coachOnly: true, icon: "sparkles-outline", label: "教学示范", value: "coach_demo" },
];

const personalActivityTypes: { icon: IconName; label: string; value: ActivityType }[] = [
  { icon: "tennisball-outline", label: "日常对打", value: "casual_hit" },
  { icon: "trophy-outline", label: "比赛录像", value: "match" },
  { icon: "flash-outline", label: "发球训练", value: "serve_training" },
  { icon: "arrow-forward-circle-outline", label: "正手训练", value: "forehand_training" },
  { icon: "arrow-back-circle-outline", label: "反手训练", value: "backhand_training" },
  { icon: "repeat-outline", label: "多球训练", value: "multi_ball_drill" },
  { icon: "body-outline", label: "动作录像", value: "stroke_recording" },
  { icon: "clipboard-outline", label: "赛后复盘", value: "post_match_review" },
  { icon: "ellipsis-horizontal-circle-outline", label: "其他视频", value: "other" },
];

const visibilityOptions: { label: string; value: ActivityVisibility }[] = [
  { label: "仅自己", value: "private" },
  { label: "教练可见", value: "lesson_coach" },
  { label: "全课可见", value: "lesson_participants" },
  { label: "公开", value: "public" },
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
  if (!value) {
    return "未知时长";
  }
  const seconds = Math.max(0, Math.round(value / 1000));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}:${rest.toString().padStart(2, "0")}`;
}

function activityTypeForMode(mode: UploadMode, personalActivityType: ActivityType): ActivityType {
  if (mode === "lesson_practice") {
    return "lesson_practice";
  }
  if (mode === "coach_demo") {
    return "coach_demo";
  }
  return personalActivityType;
}

function defaultVisibilityForMode(mode: UploadMode, lesson: LessonOption | null): ActivityVisibility {
  if (mode === "lesson_practice") {
    return "lesson_coach";
  }
  if (mode === "coach_demo" && lesson) {
    return "lesson_participants";
  }
  return "private";
}

function personalActivityTypeLabel(value: ActivityType) {
  return personalActivityTypes.find((item) => item.value === value)?.label ?? "网球视频";
}

function defaultTitle(
  mode: UploadMode,
  lesson: LessonOption | null,
  personalActivityType: ActivityType,
) {
  if (mode === "lesson_practice") {
    return lesson?.title ? `${lesson.title} 练习视频` : "课程练习视频";
  }
  if (mode === "coach_demo") {
    return lesson?.title ? `${lesson.title} 教学示范` : "教学示范视频";
  }
  return personalActivityTypeLabel(personalActivityType);
}

function lessonLabel(lesson: LessonOption | null) {
  if (!lesson) {
    return "不关联课程";
  }
  return lesson.title || `课程 ${lesson.lesson_id.slice(0, 8)}`;
}

export default function UploadVideoScreen() {
  const router = useRouter();
  const { accessToken, isAuthenticated, status, user } = useAuth();
  const { locationResult: cachedLocationResult } = useActivityLocationCache();
  const [mode, setMode] = useState<UploadMode>("personal");
  const [personalActivityType, setPersonalActivityType] = useState<ActivityType>("casual_hit");
  const [title, setTitle] = useState("");
  const [locationResult, setLocationResult] = useState<MobileLocationResult | null>(null);
  const [opponentName, setOpponentName] = useState("");
  const [note, setNote] = useState("");
  const [visibility, setVisibility] = useState<ActivityVisibility>("private");
  const [lessons, setLessons] = useState<LessonOption[]>([]);
  const [lessonsLoading, setLessonsLoading] = useState(false);
  const [lessonPickerVisible, setLessonPickerVisible] = useState(false);
  const [selectedLessonId, setSelectedLessonId] = useState<string | null>(null);
  const [videos, setVideos] = useState<LocalVideo[]>([]);
  const [intent, setIntent] = useState<UploadIntentResponse | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadPhase, setUploadPhase] = useState<UploadPhase>("idle");
  const [uploadingVideoIndex, setUploadingVideoIndex] = useState<number | null>(null);
  const [locating, setLocating] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isActiveCoach = Boolean(user?.is_coach && user.coach_status === "active");
  const eligibleLessons = useMemo(() => {
    if (mode === "coach_demo") {
      return lessons.filter((lesson) => lesson.role === "coach");
    }
    if (mode === "personal") {
      return [];
    }
    return lessons;
  }, [lessons, mode]);
  const selectedLesson = useMemo(
    () => eligibleLessons.find((lesson) => lesson.lesson_id === selectedLessonId) ?? null,
    [eligibleLessons, selectedLessonId],
  );
  const locked = Boolean(intent) || uploading || completed;
  const hasFailedVideos = videos.some((video) => video.status === "failed");
  const uploadStatus = useMemo(() => {
    if (!uploading) {
      return null;
    }
    if (uploadPhase === "resolving_location") {
      return {
        detail: "定位不可用时也会继续保存活动。",
        title: "正在确认活动地点",
      };
    }
    if (uploadPhase === "creating_activity") {
      return {
        detail: "正在为本次上传创建 Activity 和视频记录。",
        title: "正在创建活动",
      };
    }
    if (uploadPhase === "uploading_file") {
      const current = uploadingVideoIndex === null ? null : uploadingVideoIndex + 1;
      return {
        detail: "请保持当前页面打开，网络较慢时大视频会多停留一会儿。",
        title: current ? `正在上传第 ${current}/${videos.length} 个视频` : "正在上传视频",
      };
    }
    if (uploadPhase === "saving_file") {
      const current = uploadingVideoIndex === null ? null : uploadingVideoIndex + 1;
      return {
        detail: "文件已到达服务器，正在保存文件并生成预览图。",
        title: current ? `正在保存第 ${current}/${videos.length} 个视频` : "正在保存视频",
      };
    }
    if (uploadPhase === "finalizing_activity") {
      return {
        detail: "文件已上传完成，正在提交 Activity 并放入待分析队列。",
        title: "正在进入分析队列",
      };
    }
    return {
      detail: "正在准备上传。",
      title: "正在准备上传",
    };
  }, [uploadPhase, uploading, uploadingVideoIndex, videos.length]);

  useEffect(() => {
    if (cachedLocationResult) {
      setLocationResult((current) => (current?.location.source === "video_metadata" ? current : cachedLocationResult));
    }
  }, [cachedLocationResult]);

  useEffect(() => {
    if (!accessToken) {
      return;
    }

    let mounted = true;
    setLessonsLoading(true);
    listUploadLessons(accessToken)
      .then((response) => {
        if (mounted) {
          setLessons(response.items);
        }
      })
      .catch(() => {
        if (mounted) {
          setLessons([]);
        }
      })
      .finally(() => {
        if (mounted) {
          setLessonsLoading(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [accessToken]);

  useEffect(() => {
    if (mode === "personal") {
      setSelectedLessonId(null);
      return;
    }
    if (selectedLessonId && !eligibleLessons.some((lesson) => lesson.lesson_id === selectedLessonId)) {
      setSelectedLessonId(null);
    }
  }, [eligibleLessons, mode, selectedLessonId]);

  useEffect(() => {
    const needsLesson = visibility === "lesson_coach" || visibility === "lesson_participants";
    if (needsLesson && mode !== "lesson_practice" && !selectedLesson) {
      setVisibility(defaultVisibilityForMode(mode, null));
    }
  }, [mode, selectedLesson, visibility]);

  function patchVideo(localId: string, patch: Partial<LocalVideo>) {
    setVideos((current) =>
      current.map((video) => (video.localId === localId ? { ...video, ...patch } : video)),
    );
  }

  function handleModeChange(nextMode: UploadMode) {
    if (locked) {
      return;
    }
    if (nextMode === "coach_demo" && !isActiveCoach) {
      Alert.alert("暂不能上传教学示范", "通过教练身份审核后可以上传教学示范视频。");
      return;
    }
    const nextLesson =
      nextMode === "personal" || (nextMode === "coach_demo" && selectedLesson?.role !== "coach")
        ? null
        : selectedLesson;
    setMode(nextMode);
    setVisibility(defaultVisibilityForMode(nextMode, nextLesson));
    setError(null);
  }

  async function handlePickVideos() {
    if (locked) {
      return;
    }

    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert("无法选择视频", "请允许访问相册后再上传视频。");
      return;
    }

    const remaining = MAX_VIDEOS - videos.length;
    if (remaining <= 0) {
      Alert.alert("视频数量已满", `一次 activity 最多上传 ${MAX_VIDEOS} 个视频。`);
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      allowsMultipleSelection: true,
      mediaTypes: ["videos"],
      preferredAssetRepresentationMode: ImagePicker.UIImagePickerPreferredAssetRepresentationMode.Current,
      quality: 1,
      selectionLimit: remaining,
    });

    if (result.canceled || !result.assets?.length) {
      return;
    }

    const pickedAssets = result.assets;
    setVideos((current) => {
      const knownUris = new Set(current.map((video) => video.uri));
      const nextVideos = pickedAssets
        .filter((asset) => asset.uri && !knownUris.has(asset.uri))
        .slice(0, remaining)
        .map((asset, index): LocalVideo => {
          const name = normalizeVideoFileName({
            fallbackBase: `video-${index}`,
            fileName: asset.fileName,
            mimeType: asset.mimeType,
            uri: asset.uri,
          });
          return {
            assetId: asset.assetId ?? null,
            durationMs: normalizeVideoDurationMs(asset.duration),
            error: null,
            fileSize: asset.fileSize ?? null,
            localId: `${Date.now()}-${index}-${asset.uri}`,
            mimeType: normalizeVideoMimeType(asset.mimeType, name),
            name,
            progress: 0,
            serverVideoId: null,
            status: "ready",
            uri: asset.uri,
          };
        });
      return [...current, ...nextVideos];
    });

    for (const asset of pickedAssets) {
      const videoLocation = await getActivityLocationFromVideoAsset(asset.assetId);
      if (videoLocation) {
        setLocationResult(videoLocation);
        break;
      }
    }
  }

  function removeVideo(localId: string) {
    if (locked) {
      return;
    }
    setVideos((current) => current.filter((video) => video.localId !== localId));
  }

  function validateBeforeUpload() {
    if (!accessToken) {
      return "请先登录后再上传视频。";
    }
    if (!videos.length) {
      return "请先选择至少一个视频。";
    }
    if (mode === "lesson_practice" && !selectedLesson) {
      return "课程练习视频需要先选择一节课程。";
    }
    if (mode === "coach_demo" && !isActiveCoach) {
      return "通过教练身份审核后可以上传教学示范视频。";
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

  function buildPayload(activeLocation: MobileLocationResult) {
    return {
      activity_type: activityTypeForMode(mode, personalActivityType),
      default_visibility: visibility,
      lesson_id: mode === "personal" ? null : selectedLesson?.lesson_id ?? null,
      location: activeLocation.location,
      note: note.trim() || null,
      opponent_name:
        mode === "personal" && personalActivityType === "match"
          ? opponentName.trim() || null
          : null,
      title: title.trim() || defaultTitle(mode, selectedLesson, personalActivityType),
      videos: videos.map((video) => ({
        file_size_bytes: video.fileSize,
        mime_type: video.mimeType,
        original_filename: video.name,
        visibility: "inherit" as const,
      })),
    };
  }

  async function handleUpload() {
    const validationError = validateBeforeUpload();
    if (validationError || !accessToken) {
      setError(validationError);
      return;
    }

    setUploading(true);
    setUploadPhase("resolving_location");
    setUploadingVideoIndex(null);
    setCompleted(false);
    setError(null);

    try {
      const nextLocation = locationResult ?? (await getCurrentActivityLocation());
      setLocationResult(nextLocation);
      let activeIntent = intent;
      if (!activeIntent) {
        setUploadPhase("creating_activity");
        activeIntent = await createUploadIntent(accessToken, buildPayload(nextLocation));
        setIntent(activeIntent);
        setVideos((current) =>
          current.map((video, index) => ({
            ...video,
            serverVideoId: activeIntent?.videos[index]?.video_id ?? video.serverVideoId,
          })),
        );
      }

      let failedCount = 0;
      const uploadSnapshot = videos;
      for (let index = 0; index < uploadSnapshot.length; index += 1) {
        const localVideo = uploadSnapshot[index];
        if (localVideo.status === "uploaded") {
          continue;
        }
        const serverVideo = activeIntent.videos[index];
        if (!serverVideo) {
          failedCount += 1;
          patchVideo(localVideo.localId, {
            error: "服务端视频记录缺失",
            status: "failed",
          });
          continue;
        }

        try {
          setUploadPhase("uploading_file");
          setUploadingVideoIndex(index);
          patchVideo(localVideo.localId, {
            error: null,
            progress: Math.max(localVideo.progress, 0.02),
            serverVideoId: serverVideo.video_id,
            status: "uploading",
          });
          await uploadVideoFile({
            accessToken,
            file: {
              mimeType: localVideo.mimeType,
              name: localVideo.name,
              uri: localVideo.uri,
            },
            onProgress: (progress) => {
              patchVideo(localVideo.localId, {
                progress,
              });
              if (progress >= 1) {
                setUploadPhase("saving_file");
              }
            },
            videoId: serverVideo.video_id,
          });
          patchVideo(localVideo.localId, {
            error: null,
            progress: 1,
            status: "uploaded",
          });
        } catch (uploadError) {
          failedCount += 1;
          patchVideo(localVideo.localId, {
            error: errorMessage(uploadError),
            status: "failed",
          });
        }
      }

      if (failedCount > 0) {
        setError("部分视频上传失败，请检查网络后重试失败项。");
        return;
      }

      setUploadPhase("finalizing_activity");
      setUploadingVideoIndex(null);
      const complete = await completeActivityUpload(
        accessToken,
        activeIntent.activity.tennis_activity_id,
      );
      setIntent({
        activity: complete.activity,
        videos: complete.videos,
      });
      setCompleted(true);
      Alert.alert("上传完成", "视频已保存到这次 Tennis Activity，稍后会进入分析流程。");
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setUploading(false);
      setUploadPhase("idle");
      setUploadingVideoIndex(null);
    }
  }

  async function handleCancelDraft() {
    if (!accessToken || !intent || uploading) {
      return;
    }

    setUploading(true);
    setUploadPhase("finalizing_activity");
    setUploadingVideoIndex(null);
    setError(null);
    try {
      await cancelActivityUpload(accessToken, intent.activity.tennis_activity_id);
      setIntent(null);
      setCompleted(false);
      setVideos((current) =>
        current.map((video) => ({
          ...video,
          error: null,
          progress: 0,
          serverVideoId: null,
          status: "ready",
        })),
      );
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setUploading(false);
      setUploadPhase("idle");
    }
  }

  if (status === "loading") {
    return (
      <ScrollPage contentStyle={styles.page}>
        <TopBar onBack={() => router.back()} title="上传视频" />
        <View style={styles.loadingPanel}>
          <ActivityIndicator color={colors.ink} />
          <Text style={styles.mutedText}>正在确认账户状态</Text>
        </View>
      </ScrollPage>
    );
  }

  if (!isAuthenticated) {
    return (
      <ScrollPage contentStyle={styles.page}>
        <TopBar onBack={() => router.back()} title="上传视频" />
        <View style={styles.emptyPanel}>
          <IconBadge name="log-in-outline" />
          <Text style={styles.emptyTitle}>登录后上传</Text>
          <Text style={styles.mutedText}>视频需要归属到你的账户和一条活动记录。</Text>
          <Pressable
            accessibilityRole="button"
            onPress={() =>
              router.replace({
                pathname: "/login",
                params: { redirect: "/upload-video" },
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
    <>
      <ScrollPage contentStyle={styles.page}>
        <TopBar onBack={() => router.back()} subtitle="保存到 Tennis Activity" title="上传视频" />

        <View style={styles.contextPanel}>
          <View style={styles.contextIcon}>
            <Ionicons color={colors.accentDeep} name="analytics-outline" size={22} />
          </View>
          <View style={styles.contextText}>
            <Text style={styles.contextTitle}>上传视频会创建一条活动记录</Text>
            <Text style={styles.contextMeta}>
              视频进入个人比赛/训练档案和分析队列，不会自动发布到社区。
            </Text>
          </View>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>归档方式</Text>
          <View style={styles.modeGrid}>
            {uploadModes.map((item) => {
              const selected = mode === item.value;
              const disabled = locked || (item.coachOnly && !isActiveCoach);
              return (
                <Pressable
                  accessibilityRole="button"
                  disabled={disabled}
                  key={item.value}
                  onPress={() => handleModeChange(item.value)}
                  style={[
                    styles.modeItem,
                    selected && styles.modeItemActive,
                    disabled && styles.disabledBlock,
                  ]}
                >
                  <Ionicons
                    color={selected ? colors.ink : colors.inkSoft}
                    name={item.icon}
                    size={19}
                  />
                  <Text style={[styles.modeText, selected && styles.modeTextActive]}>
                    {item.label}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        {mode === "personal" ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>活动类型</Text>
            <View style={styles.typeGrid}>
              {personalActivityTypes.map((item) => {
                const selected = personalActivityType === item.value;
                return (
                  <Pressable
                    accessibilityRole="button"
                    disabled={locked}
                    key={item.value}
                    onPress={() => setPersonalActivityType(item.value)}
                    style={[
                      styles.typeItem,
                      selected && styles.modeItemActive,
                      locked && styles.disabledBlock,
                    ]}
                  >
                    <Ionicons
                      color={selected ? colors.ink : colors.inkSoft}
                      name={item.icon}
                      size={18}
                    />
                    <Text style={[styles.typeText, selected && styles.modeTextActive]}>
                      {item.label}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          </View>
        ) : null}

        {mode !== "personal" ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>关联课程</Text>
            <Pressable
              accessibilityRole="button"
              disabled={locked || lessonsLoading}
              onPress={() => setLessonPickerVisible(true)}
              style={[styles.selectorRow, locked && styles.disabledBlock]}
            >
              <IconBadge name="calendar-outline" />
              <View style={styles.selectorText}>
                <Text style={styles.selectorTitle}>{lessonLabel(selectedLesson)}</Text>
                <Text style={styles.selectorSubtitle}>
                  {lessonsLoading ? "正在加载课程" : `${eligibleLessons.length} 节课程可选`}
                </Text>
              </View>
              <Ionicons color={colors.muted} name="chevron-forward" size={18} />
            </Pressable>
          </View>
        ) : null}

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>活动信息</Text>
          <View style={styles.fieldBlock}>
            <Text style={styles.label}>标题</Text>
            <TextInput
              editable={!locked}
              maxLength={120}
              onChangeText={setTitle}
              placeholder={defaultTitle(mode, selectedLesson, personalActivityType)}
              placeholderTextColor={colors.muted}
              style={styles.input}
              value={title}
            />
          </View>
          <View style={styles.fieldBlock}>
            <Text style={styles.label}>地点</Text>
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
                    "上传前会自动获取定位；请允许定位权限并开启系统位置服务。",
                  )}
                </Text>
              </View>
            </Pressable>
          </View>
          {mode === "personal" && personalActivityType === "match" ? (
            <View style={styles.fieldBlock}>
              <Text style={styles.label}>对手</Text>
              <TextInput
                editable={!locked}
                maxLength={50}
                onChangeText={setOpponentName}
                placeholder="对手姓名或队伍"
                placeholderTextColor={colors.muted}
                style={styles.input}
                value={opponentName}
              />
            </View>
          ) : null}
          <View style={styles.fieldBlock}>
            <Text style={styles.label}>备注</Text>
            <TextInput
              editable={!locked}
              multiline
              onChangeText={setNote}
              placeholder="活动目标、课程内容或想让教练关注的问题"
              placeholderTextColor={colors.muted}
              style={[styles.input, styles.textArea]}
              value={note}
            />
          </View>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>可见范围</Text>
          <View style={styles.chipWrap}>
            {visibilityOptions.map((option) => {
              const selected = visibility === option.value;
              const requiresLesson = option.value === "lesson_coach" || option.value === "lesson_participants";
              const disabled = locked || (requiresLesson && !selectedLesson);
              return (
                <Pressable
                  accessibilityRole="button"
                  disabled={disabled}
                  key={option.value}
                  onPress={() => setVisibility(option.value)}
                  style={[
                    styles.chip,
                    selected && styles.chipActive,
                    disabled && styles.disabledBlock,
                  ]}
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
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>视频</Text>
            <Text style={styles.countText}>{videos.length}/{MAX_VIDEOS}</Text>
          </View>
          <Pressable
            accessibilityRole="button"
            disabled={locked}
            onPress={handlePickVideos}
            style={[styles.addVideoButton, locked && styles.disabledBlock]}
          >
            <Ionicons color={colors.ink} name="albums-outline" size={20} />
            <Text style={styles.addVideoText}>选择视频</Text>
          </Pressable>

          <View style={styles.videoList}>
            {videos.map((video) => (
              <View key={video.localId} style={styles.videoRow}>
                <View style={styles.videoIcon}>
                  <Ionicons color={colors.accentDeep} name="videocam-outline" size={19} />
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
                    <Ionicons color={colors.accentDeep} name="checkmark-circle" size={20} />
                  ) : video.status === "uploading" ? (
                    <ActivityIndicator color={colors.accentDeep} size="small" />
                  ) : video.status === "failed" ? (
                    <Ionicons color="#B14A3D" name="alert-circle" size={20} />
                  ) : (
                    <Pressable
                      accessibilityRole="button"
                      onPress={() => removeVideo(video.localId)}
                      style={styles.iconButton}
                    >
                      <Ionicons color={colors.muted} name="close" size={17} />
                    </Pressable>
                  )}
                </View>
              </View>
            ))}
          </View>
        </View>

        {intent ? (
          <View style={styles.intentPanel}>
            <Text style={styles.intentTitle}>Activity 已创建</Text>
            <Text numberOfLines={1} style={styles.intentId}>
              {intent.activity.tennis_activity_id}
            </Text>
          </View>
        ) : null}

        {error ? <Text style={styles.errorText}>{error}</Text> : null}
        {completed ? <Text style={styles.successText}>上传完成，视频已进入待分析队列。</Text> : null}
        {uploadStatus ? (
          <View style={styles.uploadStatusPanel}>
            <ActivityIndicator color={colors.accentDeep} size="small" />
            <View style={styles.uploadStatusCopy}>
              <Text style={styles.uploadStatusTitle}>{uploadStatus.title}</Text>
              <Text style={styles.uploadStatusDetail}>{uploadStatus.detail}</Text>
            </View>
          </View>
        ) : null}

        <View style={styles.actionBar}>
          {intent && !completed ? (
            <Pressable
              accessibilityRole="button"
              disabled={uploading}
              onPress={handleCancelDraft}
              style={[styles.secondaryButton, uploading && styles.disabledBlock]}
            >
              <Text style={styles.secondaryButtonText}>取消草稿</Text>
            </Pressable>
          ) : null}
          <Pressable
            accessibilityRole="button"
            disabled={uploading || completed || videos.length === 0}
            onPress={handleUpload}
            style={[
              styles.primaryButton,
              (uploading || completed || videos.length === 0) && styles.disabledButton,
            ]}
          >
            {uploading ? (
              <>
                <ActivityIndicator color={colors.inverse} />
                <Text style={styles.primaryButtonText}>{uploadStatus?.title ?? "正在上传"}</Text>
              </>
            ) : (
              <>
                <Ionicons color={colors.inverse} name="cloud-upload-outline" size={18} />
                <Text style={styles.primaryButtonText}>
                  {intent ? (hasFailedVideos ? "重试失败项" : "继续上传") : "开始上传"}
                </Text>
              </>
            )}
          </Pressable>
        </View>
      </ScrollPage>

      <LessonPickerModal
        mode={mode}
        onClose={() => setLessonPickerVisible(false)}
        onSelect={(lessonId) => {
          const nextLesson = eligibleLessons.find((lesson) => lesson.lesson_id === lessonId) ?? null;
          setSelectedLessonId(lessonId);
          setVisibility(defaultVisibilityForMode(mode, nextLesson));
          setLessonPickerVisible(false);
        }}
        onSelectNone={() => {
          setSelectedLessonId(null);
          setVisibility(defaultVisibilityForMode(mode, null));
          setLessonPickerVisible(false);
        }}
        options={eligibleLessons}
        selectedLessonId={selectedLessonId}
        visible={lessonPickerVisible}
      />
    </>
  );
}

function LessonPickerModal({
  mode,
  onClose,
  onSelect,
  onSelectNone,
  options,
  selectedLessonId,
  visible,
}: {
  mode: UploadMode;
  onClose: () => void;
  onSelect: (lessonId: string) => void;
  onSelectNone: () => void;
  options: LessonOption[];
  selectedLessonId: string | null;
  visible: boolean;
}) {
  return (
    <Modal animationType="slide" onRequestClose={onClose} transparent visible={visible}>
      <View style={styles.modalRoot}>
        <Pressable accessibilityLabel="关闭课程选择" onPress={onClose} style={styles.modalBackdrop} />
        <View style={styles.lessonSheet}>
          <View style={styles.sheetHeader}>
            <Text style={styles.sheetTitle}>选择课程</Text>
            <Pressable accessibilityRole="button" onPress={onClose} style={styles.iconButton}>
              <Ionicons color={colors.ink} name="close" size={18} />
            </Pressable>
          </View>

          {mode !== "lesson_practice" ? (
            <Pressable accessibilityRole="button" onPress={onSelectNone} style={styles.lessonRow}>
              <IconBadge name="remove-circle-outline" />
              <View style={styles.lessonText}>
                <Text style={styles.lessonTitle}>不关联课程</Text>
                <Text style={styles.lessonMeta}>作为独立教学视频保存</Text>
              </View>
              {!selectedLessonId ? <Ionicons color={colors.accentDeep} name="checkmark" size={20} /> : null}
            </Pressable>
          ) : null}

          {options.length ? (
            options.map((lesson) => {
              const selected = lesson.lesson_id === selectedLessonId;
              return (
                <Pressable
                  accessibilityRole="button"
                  key={lesson.lesson_id}
                  onPress={() => onSelect(lesson.lesson_id)}
                  style={styles.lessonRow}
                >
                  <IconBadge name={lesson.role === "coach" ? "school-outline" : "person-outline"} />
                  <View style={styles.lessonText}>
                    <Text numberOfLines={1} style={styles.lessonTitle}>
                      {lesson.title || `课程 ${lesson.lesson_id.slice(0, 8)}`}
                    </Text>
                    <Text style={styles.lessonMeta}>
                      {lesson.role === "coach" ? "教练" : "学员"} · {lesson.status}
                    </Text>
                  </View>
                  {selected ? <Ionicons color={colors.accentDeep} name="checkmark" size={20} /> : null}
                </Pressable>
              );
            })
          ) : (
            <View style={styles.emptyLessonPanel}>
              <Text style={styles.emptyTitle}>暂无课程</Text>
              <Text style={styles.mutedText}>当前账户没有可用于上传绑定的课程。</Text>
            </View>
          )}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  page: {
    gap: 18,
    paddingTop: 18,
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
    fontSize: 17,
    fontWeight: "900",
  },
  contextPanel: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 12,
    padding: 14,
  },
  contextIcon: {
    alignItems: "center",
    backgroundColor: colors.accentSoft,
    borderRadius: radius.control,
    height: 42,
    justifyContent: "center",
    width: 42,
  },
  contextText: {
    flex: 1,
    gap: 3,
  },
  contextTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "900",
  },
  contextMeta: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
    lineHeight: 18,
  },
  modeGrid: {
    flexDirection: "row",
    gap: 8,
  },
  modeItem: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flex: 1,
    gap: 6,
    justifyContent: "center",
    minHeight: 70,
    padding: 10,
  },
  modeItemActive: {
    backgroundColor: colors.accentSoft,
    borderColor: "#C9DDE8",
  },
  modeText: {
    color: colors.inkSoft,
    fontSize: 13,
    fontWeight: "800",
  },
  modeTextActive: {
    color: colors.ink,
  },
  typeGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  typeItem: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 6,
    minHeight: 42,
    paddingHorizontal: 10,
    width: "48.4%",
  },
  typeText: {
    color: colors.inkSoft,
    flexShrink: 1,
    fontSize: 13,
    fontWeight: "800",
  },
  selectorRow: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 12,
    minHeight: 68,
    paddingHorizontal: 14,
  },
  selectorText: {
    flex: 1,
    gap: 3,
  },
  selectorTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
  },
  selectorSubtitle: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
  fieldBlock: {
    gap: 8,
  },
  label: {
    color: colors.inkSoft,
    fontSize: 12,
    fontWeight: "800",
  },
  input: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    color: colors.ink,
    fontSize: 15,
    fontWeight: "700",
    minHeight: 50,
    paddingHorizontal: 13,
    paddingVertical: 10,
  },
  locationCard: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.control,
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
  textArea: {
    minHeight: 88,
    textAlignVertical: "top",
  },
  chipWrap: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  chip: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    minHeight: 38,
    paddingHorizontal: 13,
    justifyContent: "center",
  },
  chipActive: {
    backgroundColor: colors.ink,
    borderColor: colors.ink,
  },
  chipText: {
    color: colors.inkSoft,
    fontSize: 13,
    fontWeight: "800",
  },
  chipTextActive: {
    color: colors.inverse,
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
    minHeight: 54,
  },
  addVideoText: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
  },
  countText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "800",
  },
  videoList: {
    gap: 9,
  },
  videoRow: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 11,
    minHeight: 76,
    padding: 12,
  },
  videoIcon: {
    alignItems: "center",
    backgroundColor: colors.accentSoft,
    borderRadius: radius.control,
    height: 40,
    justifyContent: "center",
    width: 40,
  },
  videoBody: {
    flex: 1,
    gap: 4,
  },
  videoName: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "900",
  },
  videoMeta: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
  videoTrailing: {
    alignItems: "center",
    justifyContent: "center",
    width: 32,
  },
  progressTrack: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: 3,
    height: 6,
    overflow: "hidden",
  },
  progressFill: {
    backgroundColor: colors.accentDeep,
    height: 6,
  },
  uploadStatusPanel: {
    alignItems: "center",
    backgroundColor: colors.accentSoft,
    borderColor: colors.accent,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 11,
    paddingHorizontal: 12,
    paddingVertical: 11,
  },
  uploadStatusCopy: {
    flex: 1,
    gap: 3,
  },
  uploadStatusTitle: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "900",
  },
  uploadStatusDetail: {
    color: colors.inkSoft,
    fontSize: 12,
    fontWeight: "700",
    lineHeight: 17,
  },
  iconButton: {
    alignItems: "center",
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.control,
    height: 32,
    justifyContent: "center",
    width: 32,
  },
  actionBar: {
    gap: 10,
    marginTop: 2,
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    flexDirection: "row",
    gap: 8,
    justifyContent: "center",
    minHeight: 54,
  },
  primaryButtonText: {
    color: colors.inverse,
    flexShrink: 1,
    fontSize: 15,
    fontWeight: "900",
    textAlign: "center",
  },
  secondaryButton: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    justifyContent: "center",
    minHeight: 48,
  },
  secondaryButtonText: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "900",
  },
  disabledButton: {
    opacity: 0.52,
  },
  disabledBlock: {
    opacity: 0.48,
  },
  errorText: {
    color: "#B14A3D",
    fontSize: 12,
    fontWeight: "800",
    lineHeight: 18,
  },
  successText: {
    color: colors.accentDeep,
    fontSize: 13,
    fontWeight: "900",
  },
  intentPanel: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.card,
    gap: 4,
    padding: 12,
  },
  intentTitle: {
    color: colors.inkSoft,
    fontSize: 12,
    fontWeight: "800",
  },
  intentId: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: "800",
  },
  loadingPanel: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 10,
    padding: 18,
  },
  emptyPanel: {
    alignItems: "flex-start",
    gap: 12,
  },
  emptyTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "900",
  },
  mutedText: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "700",
    lineHeight: 19,
  },
  modalRoot: {
    flex: 1,
    justifyContent: "flex-end",
  },
  modalBackdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.25)",
  },
  lessonSheet: {
    backgroundColor: colors.background,
    borderTopLeftRadius: radius.control,
    borderTopRightRadius: radius.control,
    gap: 10,
    maxHeight: "78%",
    paddingBottom: 28,
    paddingHorizontal: 18,
    paddingTop: 14,
  },
  sheetHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 2,
  },
  sheetTitle: {
    color: colors.ink,
    fontSize: 19,
    fontWeight: "900",
  },
  lessonRow: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 12,
    minHeight: 68,
    paddingHorizontal: 13,
  },
  lessonText: {
    flex: 1,
    gap: 4,
  },
  lessonTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
  },
  lessonMeta: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
  emptyLessonPanel: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 6,
    padding: 16,
  },
});
