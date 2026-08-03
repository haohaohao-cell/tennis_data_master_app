import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
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

import {
  getCoachIdentity,
  submitCoachApplication,
  type CoachApplicationPayload,
  type CoachIdentity,
  type CoachType,
} from "@/api/coach";
import { ApiError } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { RowButton, ScrollPage, SegmentedControl, TopBar } from "@/components/ui";
import { colors, radius } from "@/theme";

const applicationOptions = [
  { label: "认证教练", value: "certified" },
  { label: "非职业教练", value: "non_professional" },
] as const;

const certificationOptions = [
  "中国网球协会教练员证书",
  "ITF 相关认证",
  "PTR / USPTA / RPT 等国际认证",
  "社会体育指导员证书",
  "体育专业学历或教师证明",
  "俱乐部任职证明",
  "其他",
] as const;

function errorMessage(error: unknown) {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "提交失败，请稍后重试";
}

function identitySummary(identity: CoachIdentity | null) {
  if (!identity || identity.status === "normal_user") {
    return { title: "普通用户", text: "当前账号未获得教练身份。" };
  }
  if (identity.status === "pending_review") {
    return { title: "申请审核中", text: "管理员审核后会更新你的教练身份。" };
  }
  if (identity.status === "certified_coach") {
    return { title: "认证教练", text: "已提交正式教练资质并通过平台审核。" };
  }
  if (identity.status === "non_professional_coach") {
    return { title: "非职业教练", text: "平台认可其具备一定教学能力，不展示认证资质标识。" };
  }
  if (identity.status === "review_rejected") {
    return {
      title: "审核拒绝",
      text: identity.rejection_reason ?? "申请资料未通过审核，可以修改后重新申请。",
    };
  }
  if (identity.status === "coach_suspended") {
    return { title: "教练身份已暂停", text: identity.profile?.status_reason ?? "教练功能暂时不可用。" };
  }
  return { title: "普通用户", text: identity.profile?.status_reason ?? "当前账号未获得教练身份。" };
}

export default function CoachApplyScreen() {
  const router = useRouter();
  const { accessToken, isAuthenticated, refreshLogin, status, user } = useAuth();
  const [applicationType, setApplicationType] = useState<CoachType>("certified");
  const [identity, setIdentity] = useState<CoachIdentity | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState(user?.profile_completed ? user.nickname : "");
  const [realName, setRealName] = useState("");
  const [phone, setPhone] = useState(user?.phone ?? "");
  const [city, setCity] = useState("");
  const [specialties, setSpecialties] = useState("");
  const [experience, setExperience] = useState("");
  const [certificationTitle, setCertificationTitle] = useState("");
  const [certificationPath, setCertificationPath] = useState("");
  const [videoPath, setVideoPath] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    let mounted = true;

    async function load() {
      if (!accessToken) {
        setLoading(false);
        return;
      }
      setLoading(true);
      try {
        const nextIdentity = await getCoachIdentity(accessToken);
        if (mounted) {
          setIdentity(nextIdentity);
          if (nextIdentity.application?.application_type) {
            setApplicationType(nextIdentity.application.application_type);
          }
        }
      } catch (nextError) {
        if (mounted) {
          setError(errorMessage(nextError));
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      mounted = false;
    };
  }, [accessToken]);

  async function handleSubmit() {
    const normalizedDisplayName = displayName.trim();
    if (!normalizedDisplayName) {
      setError("请填写教练展示名称");
      return;
    }
    if (applicationType === "certified" && !certificationTitle.trim()) {
      setError("请选择资质名称");
      return;
    }
    if (applicationType === "certified" && !certificationPath.trim()) {
      setError("认证教练需要上传教练资质证明图片");
      return;
    }
    if (applicationType === "non_professional" && !videoPath.trim()) {
      setError("非职业教练需要提交打球、教学或技术展示视频");
      return;
    }
    if (!accessToken) {
      setError("请先登录后再提交申请");
      return;
    }

    const payload: CoachApplicationPayload = {
      application_type: applicationType,
      display_name: normalizedDisplayName,
      real_name: realName.trim() || null,
      phone: phone.trim() || null,
      city: city.trim() || null,
      specialties: specialties.trim() || null,
      coaching_experience: experience.trim() || null,
      certification_title: certificationTitle.trim() || null,
      certification_file_path: applicationType === "certified" ? certificationPath.trim() : null,
      verification_video_path: applicationType === "non_professional" ? videoPath.trim() : null,
      note: note.trim() || null,
    };

    setSaving(true);
    setError(null);
    try {
      const response = await submitCoachApplication(accessToken, payload);
      setIdentity(response.identity);
      await refreshLogin();
      Alert.alert("申请已提交", "你的教练身份申请已进入审核中。");
      router.back();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setSaving(false);
    }
  }

  if (status === "loading" || loading) {
    return (
      <ScrollPage contentStyle={styles.page}>
        <TopBar onBack={() => router.back()} subtitle="我的" title="教练身份" />
        <View style={styles.loadingPanel}>
          <ActivityIndicator color={colors.ink} />
          <Text style={styles.loadingText}>正在同步教练身份</Text>
        </View>
      </ScrollPage>
    );
  }

  if (!isAuthenticated) {
    return (
      <ScrollPage contentStyle={styles.page}>
        <TopBar onBack={() => router.back()} subtitle="我的" title="教练身份" />
        <View style={styles.guestPanel}>
          <Text style={styles.statusTitle}>登录后申请教练身份</Text>
          <Text style={styles.statusText}>教练身份会绑定在当前普通用户账号上。</Text>
          <RowButton
            icon="log-in-outline"
            onPress={() =>
              router.replace({
                pathname: "/login",
                params: { redirect: "/profile/coach-apply" },
              })
            }
            title="登录 / 注册"
          />
        </View>
      </ScrollPage>
    );
  }

  const summary = identitySummary(identity);
  const canSubmit =
    identity?.status === "normal_user" ||
    identity?.status === "review_rejected" ||
    identity?.status === "coach_revoked" ||
    !identity;
  const isApproved = identity?.status === "certified_coach" || identity?.status === "non_professional_coach";

  return (
    <ScrollPage contentStyle={styles.page}>
      <TopBar onBack={() => router.back()} subtitle="我的" title="教练身份" />

      <View style={styles.statusPanel}>
        <View style={styles.statusIcon}>
          <Ionicons color={colors.accentDeep} name="school-outline" size={22} />
        </View>
        <View style={styles.statusCopy}>
          <Text style={styles.statusTitle}>{summary.title}</Text>
          <Text style={styles.statusText}>{summary.text}</Text>
        </View>
      </View>

      {isApproved ? (
        <View style={styles.infoBox}>
          <Ionicons color={colors.accentDeep} name="shield-checkmark-outline" size={19} />
          <Text style={styles.infoText}>
            {identity?.status === "certified_coach"
              ? "认证教练可使用课程管理、学员管理、教练主页和视频点评。"
              : "非职业教练可发布基础教学服务、做视频点评并接收学员咨询。"}
          </Text>
        </View>
      ) : null}

      {identity?.status === "pending_review" ? (
        <View style={styles.infoBox}>
          <Ionicons color={colors.gold} name="time-outline" size={19} />
          <Text style={styles.infoText}>
            申请类型：{identity.coach_type === "certified" ? "认证教练" : "非职业教练"}。
          </Text>
        </View>
      ) : null}

      {canSubmit ? (
        <View style={styles.form}>
          <SegmentedControl options={[...applicationOptions]} value={applicationType} onChange={setApplicationType} />

          <Field label="教练展示名称" onChangeText={setDisplayName} value={displayName} />
          <Field label="真实姓名" onChangeText={setRealName} value={realName} />
          <Field label="联系电话" keyboardType="phone-pad" onChangeText={setPhone} value={phone} />
          <Field label="所在城市" onChangeText={setCity} value={city} />
          <Field label="擅长方向" onChangeText={setSpecialties} value={specialties} />
          <Field label="教学或训练经历" multiline onChangeText={setExperience} value={experience} />

          {applicationType === "certified" ? (
            <>
              <CertificationPicker value={certificationTitle} onChange={setCertificationTitle} />
              <ImageUploadField value={certificationPath} onChange={setCertificationPath} />
            </>
          ) : (
            <Field label="展示视频路径或 URL" onChangeText={setVideoPath} value={videoPath} />
          )}

          <Field label="补充说明" multiline onChangeText={setNote} value={note} />

          {error ? <Text style={styles.errorText}>{error}</Text> : null}

          <Pressable
            accessibilityRole="button"
            disabled={saving}
            onPress={handleSubmit}
            style={[styles.submitButton, saving && styles.disabledButton]}
          >
            {saving ? (
              <ActivityIndicator color={colors.inverse} />
            ) : (
              <Text style={styles.submitButtonText}>提交申请</Text>
            )}
          </Pressable>
        </View>
      ) : null}
    </ScrollPage>
  );
}

function CertificationPicker({
  onChange,
  value,
}: {
  onChange: (value: string) => void;
  value: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <View style={styles.fieldBlock}>
      <Text style={styles.label}>资质名称</Text>
      <Pressable
        accessibilityRole="button"
        onPress={() => setOpen((current) => !current)}
        style={styles.selectTrigger}
      >
        <Text style={[styles.selectTriggerText, !value && styles.selectPlaceholder]}>
          {value || "请选择"}
        </Text>
        <Ionicons color={colors.muted} name={open ? "chevron-up" : "chevron-down"} size={18} />
      </Pressable>
      {open ? (
        <View style={styles.optionWrap}>
          {certificationOptions.map((option) => {
            const selected = value === option;

            return (
              <Pressable
                accessibilityRole="button"
                key={option}
                onPress={() => {
                  onChange(option);
                  setOpen(false);
                }}
                style={[styles.certOption, selected && styles.certOptionActive]}
              >
                <View style={[styles.optionDot, selected && styles.optionDotActive]}>
                  {selected ? <View style={styles.optionDotInner} /> : null}
                </View>
                <Text style={[styles.certOptionText, selected && styles.certOptionTextActive]}>
                  {option}
                </Text>
              </Pressable>
            );
          })}
        </View>
      ) : null}
    </View>
  );
}

function ImageUploadField({
  onChange,
  value,
}: {
  onChange: (value: string) => void;
  value: string;
}) {
  const [pendingValue, setPendingValue] = useState<string | null>(null);
  const [pendingPreviewUri, setPendingPreviewUri] = useState<string | null>(null);
  const previewUri = pendingPreviewUri ?? value;
  const hasPendingImage = Boolean(pendingValue);
  const uploaded = Boolean(value) && !hasPendingImage;

  async function handlePickImage() {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert("无法选择图片", "请允许访问相册后再上传资质证明图片。");
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      base64: true,
      mediaTypes: ["images"],
      quality: 0.85,
    });

    const asset = result.assets?.[0];
    if (result.canceled || !asset?.uri) {
      return;
    }

    setPendingPreviewUri(asset.uri);
    if (asset.base64) {
      setPendingValue(`data:${asset.mimeType ?? "image/jpeg"};base64,${asset.base64}`);
      return;
    }

    setPendingValue(asset.uri);
  }

  function handleUpload() {
    if (!pendingValue) {
      return;
    }
    onChange(pendingValue);
    setPendingValue(null);
  }

  return (
    <View style={styles.fieldBlock}>
      <Text style={styles.label}>资质证明图片</Text>
      <Pressable accessibilityRole="button" onPress={handlePickImage} style={styles.uploadBox}>
        <View style={styles.uploadIcon}>
          <Ionicons color={colors.accentDeep} name="image-outline" size={24} />
        </View>
        <View style={styles.uploadCopy}>
          <Text style={styles.uploadTitle}>{previewUri ? "重新选择图片" : "选择资质证明图片"}</Text>
          <Text style={styles.uploadText}>点击后从相册选择图片，选中后会先显示大图预览</Text>
        </View>
        <Ionicons color={colors.muted} name="chevron-forward" size={18} />
      </Pressable>
      {previewUri ? (
        <View style={styles.imagePreviewPanel}>
          <Image contentFit="cover" source={{ uri: previewUri }} style={styles.largePreview} />
          <View style={styles.previewActions}>
            <Text style={styles.previewStatus}>
              {uploaded ? "图片已添加到申请材料" : "已选择图片，请确认上传"}
            </Text>
            {hasPendingImage ? (
              <Pressable accessibilityRole="button" onPress={handleUpload} style={styles.uploadConfirmButton}>
                <Ionicons color={colors.inverse} name="cloud-upload-outline" size={17} />
                <Text style={styles.uploadConfirmText}>上传图片</Text>
              </Pressable>
            ) : null}
          </View>
        </View>
      ) : null}
    </View>
  );
}

function Field({
  keyboardType,
  label,
  multiline = false,
  onChangeText,
  value,
}: {
  keyboardType?: "default" | "phone-pad";
  label: string;
  multiline?: boolean;
  onChangeText: (value: string) => void;
  value: string;
}) {
  return (
    <View style={styles.fieldBlock}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        keyboardType={keyboardType ?? "default"}
        multiline={multiline}
        onChangeText={onChangeText}
        placeholderTextColor={colors.muted}
        style={[styles.input, multiline && styles.textArea]}
        value={value}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  page: {
    gap: 18,
    paddingTop: 18,
  },
  loadingPanel: {
    alignItems: "center",
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 10,
    padding: 18,
  },
  loadingText: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "700",
  },
  guestPanel: {
    gap: 14,
  },
  statusPanel: {
    alignItems: "flex-start",
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 12,
    padding: 14,
  },
  statusIcon: {
    alignItems: "center",
    backgroundColor: colors.accentSoft,
    borderRadius: radius.control,
    height: 42,
    justifyContent: "center",
    width: 42,
  },
  statusCopy: {
    flex: 1,
    gap: 5,
  },
  statusTitle: {
    color: colors.ink,
    fontSize: 19,
    fontWeight: "900",
  },
  statusText: {
    color: colors.inkSoft,
    fontSize: 13,
    fontWeight: "600",
    lineHeight: 19,
  },
  infoBox: {
    alignItems: "flex-start",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 9,
    padding: 13,
  },
  infoText: {
    color: colors.inkSoft,
    flex: 1,
    fontSize: 12,
    fontWeight: "600",
    lineHeight: 18,
  },
  form: {
    gap: 15,
  },
  fieldBlock: {
    gap: 8,
  },
  label: {
    color: colors.ink,
    fontSize: 13,
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
    minHeight: 96,
    textAlignVertical: "top",
  },
  selectTrigger: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 10,
    minHeight: 50,
    paddingHorizontal: 13,
  },
  selectTriggerText: {
    color: colors.ink,
    flex: 1,
    fontSize: 15,
    fontWeight: "800",
  },
  selectPlaceholder: {
    color: colors.muted,
  },
  optionWrap: {
    gap: 9,
  },
  certOption: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 10,
    minHeight: 50,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  certOptionActive: {
    backgroundColor: colors.accentSoft,
    borderColor: "#D9E7EF",
  },
  optionDot: {
    alignItems: "center",
    borderColor: colors.muted,
    borderRadius: 9,
    borderWidth: 1,
    height: 18,
    justifyContent: "center",
    width: 18,
  },
  optionDotActive: {
    borderColor: colors.accentDeep,
  },
  optionDotInner: {
    backgroundColor: colors.accentDeep,
    borderRadius: 5,
    height: 10,
    width: 10,
  },
  certOptionText: {
    color: colors.inkSoft,
    flex: 1,
    fontSize: 14,
    fontWeight: "800",
    lineHeight: 18,
  },
  certOptionTextActive: {
    color: colors.ink,
  },
  uploadBox: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 11,
    minHeight: 78,
    paddingHorizontal: 12,
    paddingVertical: 12,
  },
  uploadIcon: {
    alignItems: "center",
    backgroundColor: colors.accentSoft,
    borderRadius: radius.control,
    height: 42,
    justifyContent: "center",
    width: 42,
  },
  uploadCopy: {
    flex: 1,
    gap: 4,
  },
  uploadTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
  },
  uploadText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "600",
    lineHeight: 17,
  },
  imagePreviewPanel: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 12,
    padding: 10,
  },
  largePreview: {
    aspectRatio: 1.45,
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.card,
    width: "100%",
  },
  previewActions: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    justifyContent: "space-between",
  },
  previewStatus: {
    color: colors.inkSoft,
    flex: 1,
    fontSize: 12,
    fontWeight: "700",
  },
  uploadConfirmButton: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    flexDirection: "row",
    gap: 6,
    minHeight: 40,
    paddingHorizontal: 12,
  },
  uploadConfirmText: {
    color: colors.inverse,
    fontSize: 13,
    fontWeight: "900",
  },
  errorText: {
    color: "#B14A3D",
    fontSize: 13,
    fontWeight: "800",
  },
  submitButton: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    justifyContent: "center",
    minHeight: 54,
  },
  submitButtonText: {
    color: colors.inverse,
    fontSize: 16,
    fontWeight: "900",
  },
  disabledButton: {
    opacity: 0.5,
  },
});
