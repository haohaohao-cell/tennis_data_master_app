import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect } from "@react-navigation/native";
import { Image } from "expo-image";
import { VideoView, useVideoPlayer, type VideoSource } from "expo-video";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useMemo, useState } from "react";
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, View } from "react-native";

import {
  getActivityDetail,
  resolveMediaUrl,
  type ActivityDetailLesson,
  type ActivityDetailResponse,
} from "@/api/activityDetail";
import { ApiError } from "@/api/client";
import { formatActivityLocation } from "@/api/location";
import { deleteActivity, type ActivityType, type AnalysisStatus, type UploadStatus, type VideoRecord } from "@/api/uploads";
import { useAuth } from "@/auth/AuthProvider";
import { Card, Pill, ScrollPage, SegmentedControl, TopBar, type IconName } from "@/components/ui";
import { colors, radius } from "@/theme";

type ActivityTab = "overview" | "videos" | "data" | "advice";

const detailTabs = [
  { label: "概览", value: "overview" },
  { label: "视频", value: "videos" },
  { label: "数据", value: "data" },
  { label: "建议", value: "advice" },
] as const;

const playableStatuses: UploadStatus[] = ["uploaded"];

function detailErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 404) {
      return "没有找到这次活动，或你暂时没有查看权限。";
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "活动详情加载失败，请稍后重试。";
}

function activityTypeLabel(value: ActivityType) {
  const labels: Record<ActivityType, string> = {
    backhand_training: "反手训练",
    casual_hit: "日常对打",
    coach_demo: "教学示范",
    forehand_training: "正手训练",
    lesson_practice: "课程练习",
    match: "比赛",
    multi_ball_drill: "多球训练",
    other: "其他活动",
    post_match_review: "赛后复盘",
    serve_training: "发球训练",
    stroke_recording: "动作录像",
  };
  return labels[value] ?? "Activity";
}

function lessonRoleLabel(role: ActivityDetailLesson["viewer_role"]) {
  if (role === "coach") {
    return "我是教练";
  }
  if (role === "student") {
    return "我是学员";
  }
  return "课程关联";
}

function uploadStatusLabel(value: UploadStatus | "mixed") {
  const labels: Record<UploadStatus | "mixed", string> = {
    canceled: "已取消",
    failed: "上传失败",
    mixed: "部分完成",
    pending: "待上传",
    uploaded: "已上传",
    uploading: "上传中",
  };
  return labels[value] ?? value;
}

function analysisStatusLabel(value: AnalysisStatus | "mixed" | "none") {
  const labels: Record<AnalysisStatus | "mixed" | "none", string> = {
    canceled: "已取消",
    completed: "分析完成",
    failed: "分析失败",
    mixed: "状态不一",
    none: "暂无分析",
    processing: "分析中",
    queued: "等待分析",
    uploaded: "待提交",
  };
  return labels[value] ?? value;
}

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "未记录时间";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

function formatBytes(value: number | null | undefined) {
  if (!value) {
    return "大小未知";
  }
  if (value < 1024 * 1024) {
    return `${Math.max(1, Math.round(value / 1024))} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(value > 100 * 1024 * 1024 ? 0 : 1)} MB`;
}

function formatDuration(value: number | null | undefined) {
  if (!value) {
    return "时长未知";
  }
  const totalSeconds = Math.max(0, Math.round(value / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function formatCoordinates(location: ActivityDetailResponse["activity"]["location"]) {
  if (location?.latitude == null || location.longitude == null) {
    return null;
  }
  const accuracy = location.accuracy_m ? `，精度约 ${Math.round(location.accuracy_m)} 米` : "";
  return `精确坐标：${location.latitude.toFixed(6)}, ${location.longitude.toFixed(6)}${accuracy}`;
}

function videoTitle(video: VideoRecord, index: number) {
  return video.original_filename || video.filename || `视频 ${index + 1}`;
}

function statusTone(status: UploadStatus) {
  if (status === "uploaded") {
    return styles.statusReady;
  }
  if (status === "failed" || status === "canceled") {
    return styles.statusDanger;
  }
  return styles.statusMuted;
}

export default function ActivityDetailScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id?: string }>();
  const { accessToken, isAuthenticated, status } = useAuth();
  const [activeTab, setActiveTab] = useState<ActivityTab>("overview");
  const [detail, setDetail] = useState<ActivityDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedVideoId, setSelectedVideoId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const activityId = typeof id === "string" ? id : null;

  const loadDetail = useCallback(async () => {
    if (!accessToken || !activityId) {
      setDetail(null);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const nextDetail = await getActivityDetail(accessToken, activityId);
      const firstPlayable = nextDetail.videos.find((video) =>
        playableStatuses.includes(video.upload_status),
      );
      setDetail(nextDetail);
      setSelectedVideoId((current) =>
        current && nextDetail.videos.some((video) => video.video_id === current)
          ? current
          : firstPlayable?.video_id ?? nextDetail.videos[0]?.video_id ?? null,
      );
    } catch (loadError) {
      setDetail(null);
      setError(detailErrorMessage(loadError));
    } finally {
      setLoading(false);
    }
  }, [accessToken, activityId]);

  useFocusEffect(
    useCallback(() => {
      if (status === "authenticated") {
        void loadDetail();
      }
    }, [loadDetail, status]),
  );

  const confirmDelete = useCallback(() => {
    if (!activityId || !accessToken || deleting) {
      return;
    }

    Alert.alert("删除日记", "删除后将无法恢复，确定要删除吗？", [
      { style: "cancel", text: "取消" },
      {
        style: "destructive",
        text: "删除",
        onPress: () => {
          setDeleting(true);
          void deleteActivity(accessToken, activityId)
            .then(() => router.back())
            .catch((deleteError) => Alert.alert("删除失败", detailErrorMessage(deleteError)))
            .finally(() => setDeleting(false));
        },
      },
    ]);
  }, [accessToken, activityId, deleting, router]);

  const selectedVideo = useMemo(() => {
    if (!detail?.videos.length) {
      return null;
    }
    return (
      detail.videos.find((video) => video.video_id === selectedVideoId) ??
      detail.videos.find((video) => video.upload_status === "uploaded") ??
      detail.videos[0]
    );
  }, [detail, selectedVideoId]);

  const playerSource = useMemo<VideoSource>(() => {
    if (!selectedVideo || selectedVideo.upload_status !== "uploaded") {
      return null;
    }
    const uri = resolveMediaUrl(selectedVideo.video_path);
    if (!uri) {
      return null;
    }
    return {
      uri,
      metadata: {
        title: selectedVideo.original_filename ?? selectedVideo.filename,
      },
    };
  }, [selectedVideo]);

  if (status === "loading") {
    return <StateScreen title="活动详情" message="正在恢复登录状态..." />;
  }

  if (!isAuthenticated || !accessToken) {
    return (
      <StateScreen
        actionLabel="去登录"
        message="登录后可以查看自己的活动和课程视频。"
        onAction={() => router.push("/login")}
        title="活动详情"
      />
    );
  }

  if (!activityId) {
    return (
      <StateScreen
        message="缺少 activity id，无法打开详情。"
        onBack={() => router.back()}
        title="活动详情"
      />
    );
  }

  if (loading && !detail) {
    return <StateScreen loading message="正在加载这次 activity..." onBack={() => router.back()} title="活动详情" />;
  }

  if (error && !detail) {
    return (
      <StateScreen
        actionLabel="重试"
        message={error}
        onAction={loadDetail}
        onBack={() => router.back()}
        title="活动详情"
      />
    );
  }

  if (!detail) {
    return null;
  }

  const activityTitle = detail.activity.title || selectedVideo?.original_filename || "未命名 Activity";
  const activityTime = detail.activity.started_at ?? detail.activity.created_at;
  const activityLocationLabel = formatActivityLocation(detail.activity.location) !== "未记录位置"
    ? formatActivityLocation(detail.activity.location)
    : detail.activity.location_name || "未记录场地";
  const summaryUploadLabel =
    detail.summary.video_count === 0 ? "无视频" : uploadStatusLabel(detail.summary.upload_status);

  return (
    <ScrollPage contentStyle={styles.pageContent}>
      <TopBar
        onBack={() => router.back()}
        right={
          detail.permissions.can_manage ? (
            <Pressable
              accessibilityLabel="删除日记"
              accessibilityRole="button"
              disabled={deleting}
              onPress={confirmDelete}
              style={styles.deleteButton}
            >
              {deleting ? (
                <ActivityIndicator color={colors.clay} size="small" />
              ) : (
                <Ionicons color={colors.clay} name="trash-outline" size={20} />
              )}
            </Pressable>
          ) : null
        }
        subtitle={detail.lesson ? "课程 Activity" : "Activity 详情"}
        title={activityTitle}
      />

      <ActivityVideoPlayer source={playerSource} video={selectedVideo} />

      <View style={styles.headerBlock}>
        <View style={styles.titleRow}>
          <Text style={styles.activityTitle}>{activityTitle}</Text>
          <Pill>{activityTypeLabel(detail.activity.activity_type)}</Pill>
        </View>
        <Text style={styles.activityMeta}>
          {formatDateTime(activityTime)} · {activityLocationLabel}
        </Text>
        <View style={styles.chipRow}>
          <StatusChip label={summaryUploadLabel} />
          <StatusChip label={analysisStatusLabel(detail.summary.analysis_status)} />
          {detail.permissions.can_manage ? <StatusChip label="可管理" /> : null}
        </View>
      </View>

      <View style={styles.metricRow}>
        <SummaryMetric label="视频" value={`${detail.summary.video_count}`} unit="个" />
        <SummaryMetric label="已上传" value={`${detail.summary.uploaded_video_count}`} unit="个" />
        <SummaryMetric label="分析" value={analysisStatusLabel(detail.summary.analysis_status)} />
      </View>

      {detail.lesson ? <LessonBanner lesson={detail.lesson} /> : null}

      <SegmentedControl options={[...detailTabs]} value={activeTab} onChange={setActiveTab} />

      <DetailPanel
        activeTab={activeTab}
        detail={detail}
        onSelectVideo={(videoId) => {
          setSelectedVideoId(videoId);
          setActiveTab("videos");
        }}
        selectedVideoId={selectedVideo?.video_id ?? null}
      />

      {loading ? (
        <View style={styles.refreshHint}>
          <ActivityIndicator color={colors.accentDeep} size="small" />
          <Text style={styles.refreshText}>正在刷新</Text>
        </View>
      ) : null}
    </ScrollPage>
  );
}

function ActivityVideoPlayer({ source, video }: { source: VideoSource; video: VideoRecord | null }) {
  const player = useVideoPlayer(source, (instance) => {
    instance.loop = false;
  });
  const canPlay = Boolean(source && video?.upload_status === "uploaded");

  return (
    <View style={styles.playerShell}>
      {canPlay ? (
        <VideoView
          contentFit="contain"
          fullscreenOptions={{ enable: true, orientation: "landscape" }}
          nativeControls
          player={player}
          style={styles.videoView}
        />
      ) : (
        <View style={styles.playerEmpty}>
          <Ionicons color={colors.inverse} name="videocam-off-outline" size={30} />
          <Text style={styles.playerEmptyTitle}>暂无可播放视频</Text>
          <Text style={styles.playerEmptyText}>
            {video ? uploadStatusLabel(video.upload_status) : "这次 activity 还没有视频文件。"}
          </Text>
        </View>
      )}
    </View>
  );
}

function DetailPanel({
  activeTab,
  detail,
  onSelectVideo,
  selectedVideoId,
}: {
  activeTab: ActivityTab;
  detail: ActivityDetailResponse;
  onSelectVideo: (videoId: string) => void;
  selectedVideoId: string | null;
}) {
  if (activeTab === "videos") {
    return (
      <View style={styles.panel}>
        {detail.videos.length ? (
          detail.videos.map((video, index) => (
            <VideoListRow
              index={index}
              key={video.video_id}
              onPress={() => onSelectVideo(video.video_id)}
              selected={video.video_id === selectedVideoId}
              video={video}
            />
          ))
        ) : (
          <EmptyPanel icon="videocam-outline" title="没有可查看的视频" />
        )}
      </View>
    );
  }

  if (activeTab === "data") {
    return (
      <View style={styles.panel}>
        <InfoPanel
          icon="analytics-outline"
          lines={[
            `分析状态：${analysisStatusLabel(detail.summary.analysis_status)}`,
            `上传状态：${uploadStatusLabel(detail.summary.upload_status)}`,
            `视频数量：${detail.summary.uploaded_video_count}/${detail.summary.video_count}`,
          ]}
          title="分析数据"
        />
      </View>
    );
  }

  if (activeTab === "advice") {
    return (
      <View style={styles.panel}>
        <InfoPanel
          icon="bulb-outline"
          lines={
            detail.summary.analysis_status === "completed"
              ? ["分析结果已生成，后续会在这里接入技术建议和复盘要点。"]
              : ["AI 分析完成后，这里会显示动作建议、训练重点和课程复盘。"]
          }
          title="训练建议"
        />
      </View>
    );
  }

  return (
    <View style={styles.panel}>
      <InfoPanel
        icon="clipboard-outline"
          lines={[
            detail.activity.note || "这次 activity 暂无备注。",
            `位置：${formatActivityLocation(detail.activity.location)}`,
            formatCoordinates(detail.activity.location) ?? "精确坐标仅活动本人可见。",
            detail.activity.court_surface ? `场地类型：${detail.activity.court_surface}` : "场地类型未记录",
            `可见性：${visibilityLabel(detail.activity.default_visibility)}`,
          ].filter(Boolean)}
        title="活动记录"
      />
      {detail.lesson ? (
        <InfoPanel
          icon="school-outline"
          lines={[
            detail.lesson.training_content || "课程训练内容未记录。",
            detail.lesson.homework ? `课后作业：${detail.lesson.homework}` : "课后作业未记录",
            detail.lesson.next_focus ? `下节重点：${detail.lesson.next_focus}` : "下节重点未记录",
          ]}
          title="课程上下文"
        />
      ) : null}
    </View>
  );
}

function LessonBanner({ lesson }: { lesson: ActivityDetailLesson }) {
  return (
    <Card style={styles.lessonCard}>
      <View style={styles.lessonHeader}>
        <View style={styles.lessonIcon}>
          <Ionicons color={colors.ink} name="school-outline" size={20} />
        </View>
        <View style={styles.lessonText}>
          <Text style={styles.lessonTitle}>{lesson.title || "未命名课程"}</Text>
          <Text style={styles.lessonMeta}>
            {lessonRoleLabel(lesson.viewer_role)} · {lessonStatusLabel(lesson.status)} ·{" "}
            {formatDateTime(lesson.started_at)}
          </Text>
        </View>
      </View>
      <Text style={styles.lessonLocation}>{lesson.location_name || "未记录上课场地"}</Text>
    </Card>
  );
}

function VideoListRow({
  index,
  onPress,
  selected,
  video,
}: {
  index: number;
  onPress: () => void;
  selected: boolean;
  video: VideoRecord;
}) {
  const disabled = video.upload_status !== "uploaded";
  const thumbnail = resolveMediaUrl(video.thumbnail_path);
  return (
    <Pressable
      accessibilityLabel={`查看${videoTitle(video, index)}`}
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={[styles.videoRow, selected && styles.videoRowSelected, disabled && styles.videoRowDisabled]}
    >
      <View style={styles.videoThumb}>
        {thumbnail ? (
          <Image contentFit="cover" source={{ uri: thumbnail }} style={styles.videoThumbImage} />
        ) : (
          <View style={styles.videoThumbFallback}>
            <Ionicons color={colors.inverse} name={disabled ? "time-outline" : "videocam-outline"} size={18} />
          </View>
        )}
        {!disabled ? (
          <View style={styles.videoThumbOverlay}>
            <Ionicons color={colors.inverse} name="play" size={12} />
          </View>
        ) : null}
      </View>
      <View style={styles.videoRowText}>
        <Text numberOfLines={1} style={styles.videoRowTitle}>
          {videoTitle(video, index)}
        </Text>
        <Text style={styles.videoRowMeta}>
          {formatBytes(video.file_size_bytes)} · {formatDuration(video.video_duration_ms)}
        </Text>
        <Text style={styles.videoRowMeta}>
          {analysisStatusLabel(video.analysis_status)} · {formatDateTime(video.uploaded_at ?? video.created_at)}
        </Text>
      </View>
      <View style={[styles.videoStatus, statusTone(video.upload_status)]}>
        <Text style={styles.videoStatusText}>{uploadStatusLabel(video.upload_status)}</Text>
      </View>
    </Pressable>
  );
}

function SummaryMetric({ label, unit, value }: { label: string; unit?: string; value: string }) {
  return (
    <View style={styles.summaryMetric}>
      <Text style={styles.summaryMetricLabel}>{label}</Text>
      <Text numberOfLines={1} adjustsFontSizeToFit style={styles.summaryMetricValue}>
        {value}
        {unit ? <Text style={styles.summaryMetricUnit}> {unit}</Text> : null}
      </Text>
    </View>
  );
}

function InfoPanel({ icon, lines, title }: { icon: IconName; lines: string[]; title: string }) {
  return (
    <Card style={styles.infoPanel}>
      <View style={styles.infoHeader}>
        <Ionicons color={colors.ink} name={icon} size={19} />
        <Text style={styles.infoTitle}>{title}</Text>
      </View>
      {lines.map((line) => (
        <Text key={line} style={styles.infoText}>
          {line}
        </Text>
      ))}
    </Card>
  );
}

function EmptyPanel({ icon, title }: { icon: IconName; title: string }) {
  return (
    <View style={styles.emptyPanel}>
      <Ionicons color={colors.muted} name={icon} size={28} />
      <Text style={styles.emptyTitle}>{title}</Text>
    </View>
  );
}

function StatusChip({ label }: { label: string }) {
  return (
    <View style={styles.statusChip}>
      <Text style={styles.statusChipText}>{label}</Text>
    </View>
  );
}

function StateScreen({
  actionLabel,
  loading,
  message,
  onAction,
  onBack,
  title,
}: {
  actionLabel?: string;
  loading?: boolean;
  message: string;
  onAction?: () => void;
  onBack?: () => void;
  title: string;
}) {
  const router = useRouter();
  return (
    <ScrollPage>
      <TopBar onBack={onBack ?? (() => router.back())} subtitle="Activity 详情" title={title} />
      <View style={styles.stateBox}>
        {loading ? (
          <ActivityIndicator color={colors.accentDeep} size="large" />
        ) : (
          <Ionicons color={colors.accentDeep} name="tennisball-outline" size={32} />
        )}
        <Text style={styles.stateText}>{message}</Text>
        {onAction && actionLabel ? (
          <Pressable accessibilityRole="button" onPress={onAction} style={styles.primaryButton}>
            <Text style={styles.primaryButtonText}>{actionLabel}</Text>
          </Pressable>
        ) : null}
      </View>
    </ScrollPage>
  );
}

function lessonStatusLabel(value: string) {
  const labels: Record<string, string> = {
    canceled: "已取消",
    completed: "已完成",
    draft: "草稿",
    scheduled: "已预约",
  };
  return labels[value] ?? value;
}

function visibilityLabel(value: string) {
  const labels: Record<string, string> = {
    friends: "好友可见",
    lesson_coach: "教练可见",
    lesson_participants: "全课可见",
    private: "仅自己",
    public: "公开",
    specified_users: "指定用户",
  };
  return labels[value] ?? value;
}

const styles = StyleSheet.create({
  pageContent: {
    gap: 16,
  },
  deleteButton: {
    alignItems: "center",
    justifyContent: "center",
    minHeight: 40,
    minWidth: 40,
  },
  playerShell: {
    aspectRatio: 16 / 9,
    backgroundColor: "#111315",
    borderRadius: radius.card,
    overflow: "hidden",
    width: "100%",
  },
  videoView: {
    height: "100%",
    width: "100%",
  },
  playerEmpty: {
    alignItems: "center",
    flex: 1,
    gap: 8,
    justifyContent: "center",
    paddingHorizontal: 24,
  },
  playerEmptyTitle: {
    color: colors.inverse,
    fontSize: 17,
    fontWeight: "900",
  },
  playerEmptyText: {
    color: "rgba(255,255,255,0.72)",
    fontSize: 13,
    fontWeight: "700",
    textAlign: "center",
  },
  headerBlock: {
    gap: 8,
  },
  titleRow: {
    alignItems: "center",
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  activityTitle: {
    color: colors.ink,
    flexShrink: 1,
    fontSize: 23,
    fontWeight: "900",
    lineHeight: 29,
  },
  activityMeta: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "700",
  },
  chipRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  statusChip: {
    alignSelf: "flex-start",
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.small,
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  statusChipText: {
    color: colors.inkSoft,
    fontSize: 12,
    fontWeight: "800",
  },
  metricRow: {
    flexDirection: "row",
    gap: 8,
  },
  summaryMetric: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flex: 1,
    minHeight: 74,
    padding: 12,
  },
  summaryMetricLabel: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
  summaryMetricValue: {
    color: colors.ink,
    fontSize: 19,
    fontWeight: "900",
    marginTop: 8,
  },
  summaryMetricUnit: {
    color: colors.inkSoft,
    fontSize: 11,
    fontWeight: "800",
  },
  lessonCard: {
    gap: 12,
  },
  lessonHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 12,
  },
  lessonIcon: {
    alignItems: "center",
    backgroundColor: colors.goldSoft,
    borderRadius: radius.control,
    height: 42,
    justifyContent: "center",
    width: 42,
  },
  lessonText: {
    flex: 1,
    gap: 4,
  },
  lessonTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "900",
  },
  lessonMeta: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
  lessonLocation: {
    color: colors.inkSoft,
    fontSize: 13,
    fontWeight: "700",
  },
  panel: {
    gap: 10,
  },
  videoRow: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 12,
    minHeight: 84,
    padding: 12,
  },
  videoRowSelected: {
    backgroundColor: colors.accentSoft,
    borderColor: colors.accentDeep,
  },
  videoRowDisabled: {
    opacity: 0.68,
  },
  videoThumb: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    height: 48,
    justifyContent: "center",
    overflow: "hidden",
    width: 48,
  },
  videoThumbImage: {
    height: "100%",
    width: "100%",
  },
  videoThumbFallback: {
    alignItems: "center",
    flex: 1,
    justifyContent: "center",
    width: "100%",
  },
  videoThumbOverlay: {
    alignItems: "center",
    backgroundColor: "rgba(17,19,21,0.68)",
    borderRadius: 10,
    bottom: 4,
    height: 20,
    justifyContent: "center",
    position: "absolute",
    right: 4,
    width: 20,
  },
  videoRowText: {
    flex: 1,
    gap: 4,
  },
  videoRowTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
  },
  videoRowMeta: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
  videoStatus: {
    alignItems: "center",
    borderRadius: radius.small,
    minWidth: 62,
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  statusReady: {
    backgroundColor: colors.accentSoft,
  },
  statusMuted: {
    backgroundColor: colors.surfaceMuted,
  },
  statusDanger: {
    backgroundColor: colors.claySoft,
  },
  videoStatusText: {
    color: colors.ink,
    fontSize: 11,
    fontWeight: "900",
  },
  infoPanel: {
    gap: 9,
  },
  infoHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  infoTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "900",
  },
  infoText: {
    color: colors.inkSoft,
    fontSize: 14,
    fontWeight: "600",
    lineHeight: 22,
  },
  emptyPanel: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 8,
    minHeight: 140,
    justifyContent: "center",
    padding: 18,
  },
  emptyTitle: {
    color: colors.inkSoft,
    fontSize: 14,
    fontWeight: "800",
  },
  stateBox: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 12,
    justifyContent: "center",
    minHeight: 220,
    padding: 24,
  },
  stateText: {
    color: colors.inkSoft,
    fontSize: 15,
    fontWeight: "700",
    lineHeight: 22,
    textAlign: "center",
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    minHeight: 42,
    justifyContent: "center",
    paddingHorizontal: 18,
  },
  primaryButtonText: {
    color: colors.inverse,
    fontSize: 14,
    fontWeight: "900",
  },
  refreshHint: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
    justifyContent: "center",
    paddingVertical: 6,
  },
  refreshText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
});
