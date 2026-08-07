import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";
import { useLocalSearchParams, useRouter } from "expo-router";
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
  cancelActivityUpload,
  completeActivityUpload,
  createUploadIntent,
  createTennisActivity,
  listUploadLessons,
  normalizeVideoDurationMs,
  normalizeVideoFileName,
  normalizeVideoMimeType,
  type ActivityType,
  type ActivityVisibility,
  type CourtSurface,
  type LessonOption,
  type UploadIntentResponse,
  uploadVideoFile,
} from "@/api/uploads";
import {
  formatActivityLocation,
  formatActivityLocationStatus,
  getActivityLocationFromVideoAsset,
  getCurrentActivityLocation,
  refreshCurrentActivityLocation,
  type MobileLocationResult,
} from "@/api/location";
import { useAuth } from "@/auth/AuthProvider";
import { IconBadge, ScrollPage, TopBar, type IconName } from "@/components/ui";
import { useActivityLocationCache } from "@/location/ActivityLocationProvider";
import { colors, radius } from "@/theme";

type ActivityRecordKind = "practice" | "match" | "lesson";
type LocalVideoStatus = "ready" | "uploading" | "uploaded" | "failed";
type UploadPhase =
  | "idle"
  | "resolving_location"
  | "saving_record"
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

const trainingTypeOptions: { icon: IconName; label: string; value: ActivityType }[] = [
  { icon: "tennisball-outline", label: "对打", value: "casual_hit" },
  { icon: "flash-outline", label: "发球", value: "serve_training" },
  { icon: "arrow-forward-circle-outline", label: "正手", value: "forehand_training" },
  { icon: "arrow-back-circle-outline", label: "反手", value: "backhand_training" },
  { icon: "repeat-outline", label: "多球", value: "multi_ball_drill" },
  { icon: "body-outline", label: "动作", value: "stroke_recording" },
  { icon: "clipboard-outline", label: "复盘", value: "post_match_review" },
  { icon: "ellipsis-horizontal-circle-outline", label: "其他", value: "other" },
];

const courtSurfaceOptions: { label: string; value: CourtSurface }[] = [
  { label: "硬地", value: "hard" },
  { label: "红土", value: "clay" },
  { label: "草地", value: "grass" },
  { label: "地毯", value: "carpet" },
  { label: "未知", value: "unknown" },
];

const visibilityOptions: { label: string; value: ActivityVisibility }[] = [
  { label: "仅自己", value: "private" },
  { label: "公开", value: "public" },
];

const lessonVisibilityOptions: { label: string; value: ActivityVisibility }[] = [
  { label: "仅自己", value: "private" },
  { label: "教练可见", value: "lesson_coach" },
  { label: "全课可见", value: "lesson_participants" },
];

function errorMessage(error: unknown) {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "保存失败，请稍后重试";
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

function activityTypeLabel(value: ActivityType) {
  const match = trainingTypeOptions.find((option) => option.value === value);
  return match?.label ?? "训练";
}

function defaultTitle(
  kind: ActivityRecordKind,
  activityType: ActivityType,
  lesson: LessonOption | null,
) {
  if (kind === "match") {
    return "比赛记录";
  }
  if (kind === "lesson") {
    return lesson?.title ? `${lesson.title} 课程记录` : "课程记录";
  }
  return `${activityTypeLabel(activityType)}练习`;
}

function parseKind(value: string | string[] | undefined): ActivityRecordKind {
  if (value === "match" || value === "lesson") {
    return value;
  }
  return "practice";
}

function lessonLabel(lesson: LessonOption | null) {
  if (!lesson) {
    return "选择课程";
  }
  return lesson.title || `课程 ${lesson.lesson_id.slice(0, 8)}`;
}

function lessonMeta(lesson: LessonOption) {
  const role = lesson.role === "coach" ? "教练" : "学员";
  return [role, lesson.status, lesson.location_name].filter(Boolean).join(" · ");
}

export default function CreateActivityScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ kind?: string }>();
  const { accessToken, isAuthenticated, status } = useAuth();
  const { locationResult: cachedLocationResult } = useActivityLocationCache();
  const kind = parseKind(params.kind);
  const [trainingType, setTrainingType] = useState<ActivityType>("casual_hit");
  const [title, setTitle] = useState("");
  const [startedAt, setStartedAt] = useState("");
  const [locationResult, setLocationResult] = useState<MobileLocationResult | null>(null);
  const [opponentName, setOpponentName] = useState("");
  const [courtSurface, setCourtSurface] = useState<CourtSurface | null>(null);
  const [note, setNote] = useState("");
  const [visibility, setVisibility] = useState<ActivityVisibility>(
    kind === "lesson" ? "lesson_coach" : "private",
  );
  const [lessons, setLessons] = useState<LessonOption[]>([]);
  const [lessonsLoading, setLessonsLoading] = useState(false);
  const [lessonPickerVisible, setLessonPickerVisible] = useState(false);
  const [selectedLessonId, setSelectedLessonId] = useState<string | null>(null);
  const [videos, setVideos] = useState<LocalVideo[]>([]);
  const [uploadDraft, setUploadDraft] = useState<UploadIntentResponse | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploadPhase, setUploadPhase] = useState<UploadPhase>("idle");
  const [uploadingVideoIndex, setUploadingVideoIndex] = useState<number | null>(null);
  const [locating, setLocating] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [videoLocationAssetId, setVideoLocationAssetId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedLesson = useMemo(
    () => lessons.find((lesson) => lesson.lesson_id === selectedLessonId) ?? null,
    [lessons, selectedLessonId],
  );
  const activityType = kind === "match" ? "match" : kind === "lesson" ? "lesson_practice" : trainingType;
  const screenTitle = kind === "match" ? "记录比赛" : kind === "lesson" ? "记录课程" : "记录练习";
  const activeVisibilityOptions = kind === "lesson" ? lessonVisibilityOptions : visibilityOptions;
  const locked = saving || Boolean(uploadDraft) || completed;
  const hasFailedVideos = videos.some((video) => video.status === "failed");
  const uploadStatus = useMemo(() => {
    if (!saving) {
      return null;
    }
    if (uploadPhase === "resolving_location") {
      return {
        detail: "定位不可用时也会继续保存活动。",
        title: "正在确认活动地点",
      };
    }
    if (uploadPhase === "saving_record") {
      return {
        detail: "正在保存这次 Tennis Activity。",
        title: "正在保存记录",
      };
    }
    if (uploadPhase === "creating_activity") {
      return {
        detail: "正在为本次记录创建 Activity 和视频记录。",
        title: "正在创建活动",
      };
    }
    if (uploadPhase === "uploading_file") {
      const current = uploadingVideoIndex === null ? null : uploadingVideoIndex + 1;
      return {
        detail: "请保持当前页面打开，网络较慢时视频会多停留一会儿。",
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
      detail: "正在准备保存。",
      title: "正在准备保存",
    };
  }, [saving, uploadPhase, uploadingVideoIndex, videos.length]);
  const titlePlaceholder = useMemo(
    () => defaultTitle(kind, activityType, selectedLesson),
    [activityType, kind, selectedLesson],
  );

  useEffect(() => {
    if (cachedLocationResult) {
      setLocationResult((current) =>
        current?.location.source === "video_metadata" ? current : cachedLocationResult,
      );
    }
  }, [cachedLocationResult]);

  useEffect(() => {
    if (kind !== "lesson" || !accessToken) {
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
  }, [accessToken, kind]);

  useEffect(() => {
    if (kind === "lesson" && selectedLessonId && !lessons.some((lesson) => lesson.lesson_id === selectedLessonId)) {
      setSelectedLessonId(null);
    }
  }, [kind, lessons, selectedLessonId]);

  async function refreshLocation() {
    if (saving || locating) {
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

  function patchVideo(localId: string, patch: Partial<LocalVideo>) {
    setVideos((current) =>
      current.map((video) => (video.localId === localId ? { ...video, ...patch } : video)),
    );
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
        setVideoLocationAssetId(asset.assetId ?? null);
        break;
      }
    }
  }

  function removeVideo(localId: string) {
    if (locked) {
      return;
    }
    const removedVideo = videos.find((video) => video.localId === localId);
    setVideos((current) => current.filter((video) => video.localId !== localId));
    if (removedVideo?.assetId === videoLocationAssetId || videos.length === 1) {
      setLocationResult(cachedLocationResult);
      setVideoLocationAssetId(null);
    }
  }

  function buildActivityFields(activeLocation: MobileLocationResult) {
    return {
      activity_type: activityType,
      court_surface: courtSurface,
      default_visibility: visibility,
      lesson_id: kind === "lesson" ? selectedLesson?.lesson_id ?? null : null,
      location: activeLocation.location,
      note: note.trim() || null,
      opponent_name: kind === "match" ? opponentName.trim() || null : null,
      started_at: startedAt.trim() || new Date().toISOString(),
      title: title.trim() || titlePlaceholder,
    };
  }

  function buildUploadPayload(activeLocation: MobileLocationResult) {
    return {
      ...buildActivityFields(activeLocation),
      videos: videos.map((video) => ({
        file_size_bytes: video.fileSize,
        mime_type: video.mimeType,
        original_filename: video.name,
        visibility: "inherit" as const,
      })),
    };
  }

  function validateBeforeSave() {
    if (!accessToken) {
      return "请先登录后再记录活动。";
    }
    if (kind === "lesson" && !selectedLesson) {
      return "记录课程需要先选择一节课程。";
    }
    return null;
  }

  async function handleSave() {
    const validationError = validateBeforeSave();
    if (validationError || !accessToken) {
      setError(validationError);
      return;
    }

    setSaving(true);
    setUploadPhase(videos.length ? "resolving_location" : "saving_record");
    setUploadingVideoIndex(null);
    setCompleted(false);
    setError(null);

    try {
      const nextLocation = locationResult ?? (await getCurrentActivityLocation());
      setLocationResult(nextLocation);

      if (!videos.length) {
        const activity = await createTennisActivity(accessToken, buildActivityFields(nextLocation));
        setCompleted(true);
        Alert.alert("记录已保存", "这次活动已进入你的 Tennis Activity 档案。", [
          {
            onPress: () =>
              router.replace({
                pathname: "/activity/[id]",
                params: { id: activity.tennis_activity_id },
              }),
            text: "查看详情",
          },
        ]);
        return;
      }

      let activeDraft = uploadDraft;
      if (!activeDraft) {
        setUploadPhase("creating_activity");
        activeDraft = await createUploadIntent(accessToken, buildUploadPayload(nextLocation));
        setUploadDraft(activeDraft);
        setVideos((current) =>
          current.map((video, index) => ({
            ...video,
            serverVideoId: activeDraft?.videos[index]?.video_id ?? video.serverVideoId,
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
        const serverVideo = activeDraft.videos[index];
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
              patchVideo(localVideo.localId, { progress });
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
        activeDraft.activity.tennis_activity_id,
      );
      setUploadDraft({
        activity: complete.activity,
        videos: complete.videos,
      });
      setCompleted(true);
      Alert.alert("记录已保存", "活动和视频已保存，稍后会进入分析流程。", [
        {
          onPress: () =>
            router.replace({
              pathname: "/activity/[id]",
              params: { id: complete.activity.tennis_activity_id },
            }),
          text: "查看详情",
        },
      ]);
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setSaving(false);
      setUploadPhase("idle");
      setUploadingVideoIndex(null);
    }
  }

  async function handleCancelDraft() {
    if (!accessToken || !uploadDraft || saving) {
      return;
    }

    setSaving(true);
    setUploadPhase("finalizing_activity");
    setUploadingVideoIndex(null);
    setError(null);
    try {
      await cancelActivityUpload(accessToken, uploadDraft.activity.tennis_activity_id);
      setUploadDraft(null);
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
      setSaving(false);
      setUploadPhase("idle");
    }
  }

  if (status === "loading") {
    return (
      <ScrollPage contentStyle={styles.page}>
        <TopBar onBack={() => router.back()} title={screenTitle} />
        <View style={styles.statePanel}>
          <ActivityIndicator color={colors.ink} />
          <Text style={styles.mutedText}>正在确认账户状态</Text>
        </View>
      </ScrollPage>
    );
  }

  if (!isAuthenticated) {
    return (
      <ScrollPage contentStyle={styles.page}>
        <TopBar onBack={() => router.back()} title={screenTitle} />
        <View style={styles.statePanel}>
          <IconBadge name="log-in-outline" />
          <Text style={styles.emptyTitle}>登录后记录</Text>
          <Text style={styles.mutedText}>网球日记需要归属到你的账户。</Text>
          <Pressable
            accessibilityRole="button"
            onPress={() =>
              router.replace({
                pathname: "/login",
                params: { redirect: `/create-activity?kind=${kind}` },
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
      <TopBar onBack={() => router.back()} subtitle="网球日记" title={screenTitle} />

      <View style={styles.contextPanel}>
        <View style={styles.contextIcon}>
          <Ionicons
            color={kind === "match" ? colors.clay : colors.accentDeep}
            name={
              kind === "match"
                ? "trophy-outline"
                : kind === "lesson"
                  ? "school-outline"
                  : "fitness-outline"
            }
            size={22}
          />
        </View>
        <View style={styles.contextText}>
          <Text style={styles.contextTitle}>
            {kind === "match" ? "比赛日记" : kind === "lesson" ? "课程日记" : "练习日记"}
          </Text>
          <Text style={styles.contextMeta}>
            {kind === "match"
              ? "保存比赛记录，也可以同时从相册上传比赛视频。"
              : kind === "lesson"
                ? "记录课程重点，也可以同时从相册上传课堂视频。"
                : "保存一次练习记录，也可以同时从相册上传练习视频。"}
          </Text>
        </View>
      </View>

      {kind === "practice" ? (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>练习类型</Text>
          <View style={styles.optionGrid}>
            {trainingTypeOptions.map((option) => {
              const selected = trainingType === option.value;
              return (
                <Pressable
                  accessibilityRole="button"
                  disabled={locked}
                  key={option.value}
                  onPress={() => setTrainingType(option.value)}
                  style={[styles.optionItem, selected && styles.optionItemActive, locked && styles.disabledBlock]}
                >
                  <Ionicons
                    color={selected ? colors.ink : colors.inkSoft}
                    name={option.icon}
                    size={18}
                  />
                  <Text style={[styles.optionText, selected && styles.optionTextActive]}>
                    {option.label}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      ) : null}

      {kind === "lesson" ? (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>课程</Text>
          <Pressable
            accessibilityRole="button"
            disabled={locked || lessonsLoading}
            onPress={() => setLessonPickerVisible(true)}
            style={[styles.lessonSelectCard, (locked || lessonsLoading) && styles.disabledBlock]}
          >
            <View style={styles.locationIcon}>
              {lessonsLoading ? (
                <ActivityIndicator color={colors.accentDeep} size="small" />
              ) : (
                <Ionicons color={colors.accentDeep} name="school-outline" size={18} />
              )}
            </View>
            <View style={styles.locationCopy}>
              <Text style={styles.locationTitle}>
                {lessonsLoading ? "正在加载课程" : lessonLabel(selectedLesson)}
              </Text>
              <Text style={styles.locationText}>
                {selectedLesson
                  ? lessonMeta(selectedLesson)
                  : "课程记录需要绑定一节你参与的课程。"}
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
            placeholder={titlePlaceholder}
            placeholderTextColor={colors.muted}
            style={styles.input}
            value={title}
          />
        </View>
        <View style={styles.fieldBlock}>
          <Text style={styles.label}>时间</Text>
          <TextInput
            editable={!locked}
            maxLength={40}
            onChangeText={setStartedAt}
            placeholder="留空则使用当前时间"
            placeholderTextColor={colors.muted}
            style={styles.input}
            value={startedAt}
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
                "保存前会自动获取定位；请允许定位权限并开启系统位置服务。",
              )}
              </Text>
            </View>
          </Pressable>
        </View>
        {kind === "match" ? (
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
            placeholder={
              kind === "match"
                ? "比分、关键局或赛后感受"
                : kind === "lesson"
                  ? "本节重点、教练反馈、课后作业或下次目标"
                  : "练习目标、完成情况或需要复盘的问题"
            }
            placeholderTextColor={colors.muted}
            style={[styles.input, styles.textArea]}
            value={note}
          />
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>场地类型</Text>
        <View style={styles.chipWrap}>
          {courtSurfaceOptions.map((option) => {
            const selected = courtSurface === option.value;
            return (
              <Pressable
                accessibilityRole="button"
                disabled={locked}
                key={option.value}
                onPress={() => setCourtSurface(selected ? null : option.value)}
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
        <Text style={styles.sectionTitle}>可见范围</Text>
        <View style={styles.chipWrap}>
          {activeVisibilityOptions.map((option) => {
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
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>相册视频</Text>
          <Text style={styles.countText}>
            {videos.length}/{MAX_VIDEOS}
          </Text>
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
                    <View
                      style={[styles.progressFill, { width: `${Math.round(video.progress * 100)}%` }]}
                    />
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
                    accessibilityLabel={`移除视频 ${video.name}`}
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

      {uploadDraft ? (
        <View style={styles.intentPanel}>
          <Text style={styles.intentTitle}>Activity 草稿已创建</Text>
          <Text numberOfLines={1} style={styles.intentId}>
            {uploadDraft.activity.tennis_activity_id}
          </Text>
        </View>
      ) : null}

      {error ? <Text style={styles.errorText}>{error}</Text> : null}

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
        {uploadDraft && !completed ? (
          <Pressable
            accessibilityRole="button"
            disabled={saving}
            onPress={handleCancelDraft}
            style={[styles.secondaryButton, saving && styles.disabledBlock]}
          >
            <Text style={styles.secondaryButtonText}>取消上传草稿</Text>
          </Pressable>
        ) : null}
        <Pressable
          accessibilityRole="button"
          disabled={saving || completed}
          onPress={handleSave}
          style={[styles.primaryButton, (saving || completed) && styles.disabledButton]}
        >
          {saving ? (
            <>
              <ActivityIndicator color={colors.inverse} />
              <Text style={styles.primaryButtonText}>{uploadStatus?.title ?? "正在保存"}</Text>
            </>
          ) : (
            <>
              <Ionicons color={colors.inverse} name="checkmark-circle-outline" size={18} />
              <Text style={styles.primaryButtonText}>
                {uploadDraft ? (hasFailedVideos ? "重试失败视频" : "继续上传视频") : videos.length ? "保存并上传视频" : "保存记录"}
              </Text>
            </>
          )}
        </Pressable>
      </View>
      </ScrollPage>

      <LessonPickerModal
        onClose={() => setLessonPickerVisible(false)}
        onSelect={(lessonId) => {
          setSelectedLessonId(lessonId);
          setLessonPickerVisible(false);
          setError(null);
        }}
        options={lessons}
        selectedLessonId={selectedLessonId}
        visible={lessonPickerVisible}
      />
    </>
  );
}

function LessonPickerModal({
  onClose,
  onSelect,
  options,
  selectedLessonId,
  visible,
}: {
  onClose: () => void;
  onSelect: (lessonId: string) => void;
  options: LessonOption[];
  selectedLessonId: string | null;
  visible: boolean;
}) {
  return (
    <Modal animationType="slide" onRequestClose={onClose} transparent visible={visible}>
      <View style={styles.modalRoot}>
        <Pressable accessibilityLabel="关闭课程选择" onPress={onClose} style={styles.modalBackdrop} />
        <View style={styles.lessonSheet}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>选择课程</Text>
            <Pressable accessibilityRole="button" onPress={onClose} style={styles.iconButton}>
              <Ionicons color={colors.ink} name="close" size={18} />
            </Pressable>
          </View>

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
                    <Text style={styles.lessonMeta}>{lessonMeta(lesson)}</Text>
                  </View>
                  {selected ? <Ionicons color={colors.accentDeep} name="checkmark" size={20} /> : null}
                </Pressable>
              );
            })
          ) : (
            <View style={styles.emptyLessonPanel}>
              <Text style={styles.emptyTitle}>暂无课程</Text>
              <Text style={styles.mutedText}>当前账户没有可绑定的课程，暂时不能创建课程记录。</Text>
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
    backgroundColor: colors.surfaceMuted,
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
  optionGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  optionItem: {
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
  optionItemActive: {
    backgroundColor: colors.accentSoft,
    borderColor: "#C9DDE8",
  },
  optionText: {
    color: colors.inkSoft,
    flexShrink: 1,
    fontSize: 13,
    fontWeight: "800",
  },
  optionTextActive: {
    color: colors.ink,
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
  textArea: {
    minHeight: 92,
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
    justifyContent: "center",
    minHeight: 38,
    paddingHorizontal: 13,
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
  statePanel: {
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
  disabledButton: {
    opacity: 0.52,
  },
  disabledBlock: {
    opacity: 0.52,
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
    minWidth: 0,
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
  actionBar: {
    gap: 10,
    marginTop: 2,
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
  lessonSelectCard: {
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
  modalRoot: {
    flex: 1,
    justifyContent: "flex-end",
  },
  modalBackdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.28)",
  },
  lessonSheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.control,
    borderTopRightRadius: radius.control,
    gap: 8,
    maxHeight: "72%",
    paddingBottom: 22,
    paddingHorizontal: 20,
    paddingTop: 16,
  },
  modalHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 4,
  },
  modalTitle: {
    color: colors.ink,
    fontSize: 20,
    fontWeight: "900",
  },
  iconButton: {
    alignItems: "center",
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.control,
    height: 36,
    justifyContent: "center",
    width: 36,
  },
  lessonRow: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 12,
    minHeight: 66,
    paddingHorizontal: 12,
  },
  lessonText: {
    flex: 1,
    gap: 3,
    minWidth: 0,
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
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 8,
    padding: 16,
  },
  errorText: {
    color: "#B14A3D",
    fontSize: 12,
    fontWeight: "800",
    lineHeight: 18,
  },
});
