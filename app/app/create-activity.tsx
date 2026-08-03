import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useMemo, useState } from "react";
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
  createTennisActivity,
  type ActivityType,
  type ActivityVisibility,
  type CourtSurface,
} from "@/api/uploads";
import {
  formatActivityLocation,
  formatActivityLocationStatus,
  getCurrentActivityLocation,
  refreshCurrentActivityLocation,
  type MobileLocationResult,
} from "@/api/location";
import { useAuth } from "@/auth/AuthProvider";
import { IconBadge, ScrollPage, TopBar, type IconName } from "@/components/ui";
import { useActivityLocationCache } from "@/location/ActivityLocationProvider";
import { colors, radius } from "@/theme";

type ActivityRecordKind = "match" | "training";

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

function errorMessage(error: unknown) {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "保存失败，请稍后重试";
}

function activityTypeLabel(value: ActivityType) {
  const match = trainingTypeOptions.find((option) => option.value === value);
  return match?.label ?? "训练";
}

function defaultTitle(kind: ActivityRecordKind, activityType: ActivityType) {
  if (kind === "match") {
    return "比赛记录";
  }
  return `${activityTypeLabel(activityType)}训练`;
}

function parseKind(value: string | string[] | undefined): ActivityRecordKind {
  return value === "match" ? "match" : "training";
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
  const [visibility, setVisibility] = useState<ActivityVisibility>("private");
  const [saving, setSaving] = useState(false);
  const [locating, setLocating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activityType = kind === "match" ? "match" : trainingType;
  const screenTitle = kind === "match" ? "记录比赛" : "记录训练";
  const titlePlaceholder = useMemo(
    () => defaultTitle(kind, activityType),
    [activityType, kind],
  );

  useEffect(() => {
    if (cachedLocationResult) {
      setLocationResult(cachedLocationResult);
    }
  }, [cachedLocationResult]);

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

  async function handleSave() {
    if (!accessToken) {
      setError("请先登录后再记录活动。");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const nextLocation = locationResult ?? (await getCurrentActivityLocation());
      setLocationResult(nextLocation);
      const activity = await createTennisActivity(accessToken, {
        activity_type: activityType,
        court_surface: courtSurface,
        default_visibility: visibility,
        location: nextLocation.location,
        note: note.trim() || null,
        opponent_name: kind === "match" ? opponentName.trim() || null : null,
        started_at: startedAt.trim() || new Date().toISOString(),
        title: title.trim() || titlePlaceholder,
      });

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
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setSaving(false);
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
          <Text style={styles.mutedText}>比赛和训练记录需要归属到你的账户。</Text>
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
    <ScrollPage contentStyle={styles.page}>
      <TopBar onBack={() => router.back()} subtitle="Tennis Activity" title={screenTitle} />

      <View style={styles.contextPanel}>
        <View style={styles.contextIcon}>
          <Ionicons
            color={kind === "match" ? colors.clay : colors.accentDeep}
            name={kind === "match" ? "trophy-outline" : "fitness-outline"}
            size={22}
          />
        </View>
        <View style={styles.contextText}>
          <Text style={styles.contextTitle}>
            {kind === "match" ? "比赛 Activity" : "训练 Activity"}
          </Text>
          <Text style={styles.contextMeta}>
            {kind === "match"
              ? "保存一次比赛记录；不需要先上传视频。"
              : "保存一次训练记录；视频和分析可以后续归入活动。"}
          </Text>
        </View>
      </View>

      {kind === "training" ? (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>训练类型</Text>
          <View style={styles.optionGrid}>
            {trainingTypeOptions.map((option) => {
              const selected = trainingType === option.value;
              return (
                <Pressable
                  accessibilityRole="button"
                  key={option.value}
                  onPress={() => setTrainingType(option.value)}
                  style={[styles.optionItem, selected && styles.optionItemActive]}
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

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>活动信息</Text>
        <View style={styles.fieldBlock}>
          <Text style={styles.label}>标题</Text>
          <TextInput
            editable={!saving}
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
            editable={!saving}
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
            disabled={saving || locating}
            onPress={refreshLocation}
            style={[styles.locationCard, (saving || locating) && styles.disabledBlock]}
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
              editable={!saving}
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
            editable={!saving}
            multiline
            onChangeText={setNote}
            placeholder={kind === "match" ? "比分、关键局或赛后感受" : "训练目标、完成情况或需要复盘的问题"}
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
                disabled={saving}
                key={option.value}
                onPress={() => setCourtSurface(selected ? null : option.value)}
                style={[styles.chip, selected && styles.chipActive]}
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
          {visibilityOptions.map((option) => {
            const selected = visibility === option.value;
            return (
              <Pressable
                accessibilityRole="button"
                disabled={saving}
                key={option.value}
                onPress={() => setVisibility(option.value)}
                style={[styles.chip, selected && styles.chipActive]}
              >
                <Text style={[styles.chipText, selected && styles.chipTextActive]}>
                  {option.label}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </View>

      {error ? <Text style={styles.errorText}>{error}</Text> : null}

      <Pressable
        accessibilityRole="button"
        disabled={saving}
        onPress={handleSave}
        style={[styles.primaryButton, saving && styles.disabledButton]}
      >
        {saving ? (
          <ActivityIndicator color={colors.inverse} />
        ) : (
          <>
            <Ionicons color={colors.inverse} name="checkmark-circle-outline" size={18} />
            <Text style={styles.primaryButtonText}>保存记录</Text>
          </>
        )}
      </Pressable>
    </ScrollPage>
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
    fontSize: 15,
    fontWeight: "900",
  },
  disabledButton: {
    opacity: 0.52,
  },
  disabledBlock: {
    opacity: 0.52,
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
  errorText: {
    color: "#B14A3D",
    fontSize: 12,
    fontWeight: "800",
    lineHeight: 18,
  },
});
