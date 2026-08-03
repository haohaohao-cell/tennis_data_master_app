import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";
import { useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { resolveMediaUrl } from "@/api/activityDetail";
import { ApiError } from "@/api/client";
import type { AvatarUploadableFile } from "@/api/users";
import { useAuth } from "@/auth/AuthProvider";
import type { User } from "@/auth/types";
import { Avatar, RowButton, ScrollPage, TopBar } from "@/components/ui";
import { colors, radius } from "@/theme";

type PlayingHand = User["playing_hand"];

const MAX_AVATAR_SIZE_BYTES = 5 * 1024 * 1024;

const handOptions: { label: string; value: PlayingHand }[] = [
  { label: "右手", value: "right" },
  { label: "左手", value: "left" },
  { label: "暂不确定", value: "unknown" },
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

export default function EditProfileScreen() {
  const router = useRouter();
  const { isAuthenticated, status, updateProfile, uploadAvatar, user } = useAuth();
  const initializedUserIdRef = useRef<string | null>(null);
  const [avatarFile, setAvatarFile] = useState<AvatarUploadableFile | null>(null);
  const [avatarPreviewUri, setAvatarPreviewUri] = useState<string | null>(null);
  const [nickname, setNickname] = useState("");
  const [playingHand, setPlayingHand] = useState<PlayingHand>("right");
  const [saving, setSaving] = useState(false);
  const [savingLabel, setSavingLabel] = useState("保存资料");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) {
      initializedUserIdRef.current = null;
      return;
    }
    if (initializedUserIdRef.current === user.user_id) {
      return;
    }
    initializedUserIdRef.current = user.user_id;
    setNickname(user.profile_completed ? user.nickname : "");
    setPlayingHand(user.playing_hand ?? "right");
    setAvatarPreviewUri(resolveMediaUrl(user.avatar_path));
    setAvatarFile(null);
  }, [user]);

  async function handlePickAvatar() {
    if (saving) {
      return;
    }

    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert("无法选择头像", "请允许访问相册后再选择头像。");
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      allowsEditing: true,
      aspect: [1, 1],
      mediaTypes: ["images"],
      quality: 0.9,
      selectionLimit: 1,
    });

    const asset = result.assets?.[0];
    if (result.canceled || !asset?.uri) {
      return;
    }

    if (asset.fileSize && asset.fileSize > MAX_AVATAR_SIZE_BYTES) {
      Alert.alert("头像过大", "请选择 5 MB 以内的图片。");
      return;
    }

    setAvatarFile({
      mimeType: asset.mimeType,
      name: asset.fileName,
      uri: asset.uri,
    });
    setAvatarPreviewUri(asset.uri);
    setError(null);
  }

  function handleCancelAvatar() {
    setAvatarFile(null);
    setAvatarPreviewUri(resolveMediaUrl(user?.avatar_path));
  }

  async function handleSave() {
    const normalizedNickname = nickname.trim();
    if (!normalizedNickname) {
      setError("请输入你的昵称");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      if (avatarFile) {
        setSavingLabel("正在上传头像");
        await uploadAvatar(avatarFile);
        setAvatarFile(null);
      }
      setSavingLabel("正在保存资料");
      await updateProfile({
        nickname: normalizedNickname,
        playing_hand: playingHand,
      });
      Alert.alert("资料已保存", "之后的视频、活动和训练记录都会归属到你的账户。");
      router.back();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setSaving(false);
      setSavingLabel("保存资料");
    }
  }

  if (status === "loading") {
    return (
      <ScrollPage contentStyle={styles.page}>
        <TopBar onBack={() => router.back()} title="账号资料" />
        <View style={styles.loadingPanel}>
          <ActivityIndicator color={colors.ink} />
          <Text style={styles.loadingText}>正在确认账户状态</Text>
        </View>
      </ScrollPage>
    );
  }

  if (!isAuthenticated) {
    return (
      <ScrollPage contentStyle={styles.page}>
        <TopBar onBack={() => router.back()} title="账号资料" />
        <View style={styles.guestPanel}>
          <Text style={styles.guestTitle}>登录后完善资料</Text>
          <Text style={styles.guestText}>昵称和持拍手会用于展示个人主页、活动记录和后续视频归属。</Text>
          <RowButton
            icon="log-in-outline"
            onPress={() =>
              router.replace({
                pathname: "/login",
                params: { redirect: "/profile/edit" },
              })
            }
            title="登录 / 注册"
          />
        </View>
      </ScrollPage>
    );
  }

  return (
    <ScrollPage contentStyle={styles.page}>
      <TopBar onBack={() => router.back()} subtitle="我的账户" title="完善资料" />

      <View style={styles.form}>
        <View style={styles.fieldBlock}>
          <Text style={styles.label}>头像</Text>
          <View style={styles.avatarPanel}>
            <Pressable
              accessibilityLabel="选择头像"
              accessibilityRole="button"
              onPress={handlePickAvatar}
              style={styles.avatarPreviewButton}
            >
              <Avatar
                name={nickname.trim() || user?.nickname || "网球用户"}
                size={78}
                uri={avatarPreviewUri}
              />
              <View style={styles.avatarCameraBadge}>
                <Ionicons color={colors.inverse} name="camera-outline" size={16} />
              </View>
            </Pressable>
            <View style={styles.avatarCopy}>
              <Text style={styles.avatarTitle}>
                {avatarFile ? "新头像待保存" : avatarPreviewUri ? "当前头像" : "默认头像"}
              </Text>
              <View style={styles.avatarActions}>
                <Pressable
                  accessibilityRole="button"
                  disabled={saving}
                  onPress={handlePickAvatar}
                  style={[styles.avatarActionButton, saving && styles.disabledButton]}
                >
                  <Ionicons color={colors.ink} name="image-outline" size={17} />
                  <Text style={styles.avatarActionText}>选择图片</Text>
                </Pressable>
                {avatarFile ? (
                  <Pressable
                    accessibilityRole="button"
                    disabled={saving}
                    onPress={handleCancelAvatar}
                    style={[styles.avatarGhostButton, saving && styles.disabledButton]}
                  >
                    <Text style={styles.avatarGhostText}>取消</Text>
                  </Pressable>
                ) : null}
              </View>
            </View>
          </View>
        </View>

        <View style={styles.fieldBlock}>
          <Text style={styles.label}>昵称</Text>
          <TextInput
            maxLength={50}
            onChangeText={setNickname}
            placeholder="输入一个网球昵称"
            placeholderTextColor={colors.muted}
            style={styles.input}
            value={nickname}
          />
        </View>

        <View style={styles.fieldBlock}>
          <Text style={styles.label}>主要持拍手</Text>
          <View style={styles.optionList}>
            {handOptions.map((option) => {
              const selected = playingHand === option.value;
              return (
                <Pressable
                  accessibilityRole="button"
                  key={option.value}
                  onPress={() => setPlayingHand(option.value)}
                  style={[styles.optionRow, selected && styles.optionRowActive]}
                >
                  <View style={[styles.radio, selected && styles.radioActive]}>
                    {selected ? <View style={styles.radioDot} /> : null}
                  </View>
                  <Text style={[styles.optionText, selected && styles.optionTextActive]}>
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
          style={[styles.saveButton, saving && styles.disabledButton]}
        >
          {saving ? (
            <View style={styles.saveBusyContent}>
              <ActivityIndicator color={colors.inverse} />
              <Text style={styles.saveBusyText}>{savingLabel}</Text>
            </View>
          ) : (
            <Text style={styles.saveButtonText}>保存资料</Text>
          )}
        </Pressable>
      </View>
    </ScrollPage>
  );
}

const styles = StyleSheet.create({
  page: {
    paddingTop: 18,
  },
  form: {
    gap: 18,
  },
  fieldBlock: {
    gap: 9,
  },
  avatarPanel: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 14,
    padding: 14,
  },
  avatarPreviewButton: {
    height: 82,
    justifyContent: "center",
    width: 82,
  },
  avatarCameraBadge: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderColor: colors.surface,
    borderRadius: 14,
    borderWidth: 2,
    bottom: 0,
    height: 28,
    justifyContent: "center",
    position: "absolute",
    right: 0,
    width: 28,
  },
  avatarCopy: {
    flex: 1,
    gap: 10,
  },
  avatarTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "900",
  },
  avatarActions: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  avatarActionButton: {
    alignItems: "center",
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.control,
    flexDirection: "row",
    gap: 6,
    minHeight: 38,
    paddingHorizontal: 12,
  },
  avatarActionText: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "900",
  },
  avatarGhostButton: {
    alignItems: "center",
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    justifyContent: "center",
    minHeight: 38,
    paddingHorizontal: 12,
  },
  avatarGhostText: {
    color: colors.inkSoft,
    fontSize: 13,
    fontWeight: "900",
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
    fontSize: 17,
    fontWeight: "700",
    minHeight: 52,
    paddingHorizontal: 14,
  },
  optionList: {
    gap: 9,
  },
  optionRow: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 10,
    minHeight: 52,
    paddingHorizontal: 13,
  },
  optionRowActive: {
    backgroundColor: colors.accentSoft,
    borderColor: "#D9E7EF",
  },
  radio: {
    alignItems: "center",
    borderColor: colors.muted,
    borderRadius: 9,
    borderWidth: 1,
    height: 18,
    justifyContent: "center",
    width: 18,
  },
  radioActive: {
    borderColor: colors.accentDeep,
  },
  radioDot: {
    backgroundColor: colors.accentDeep,
    borderRadius: 5,
    height: 10,
    width: 10,
  },
  optionText: {
    color: colors.inkSoft,
    fontSize: 15,
    fontWeight: "800",
  },
  optionTextActive: {
    color: colors.ink,
  },
  errorText: {
    color: "#B14A3D",
    fontSize: 13,
    fontWeight: "800",
  },
  saveButton: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    justifyContent: "center",
    minHeight: 54,
  },
  saveButtonText: {
    color: colors.inverse,
    fontSize: 16,
    fontWeight: "900",
  },
  saveBusyContent: {
    alignItems: "center",
    flexDirection: "row",
    gap: 9,
  },
  saveBusyText: {
    color: colors.inverse,
    fontSize: 15,
    fontWeight: "900",
  },
  disabledButton: {
    opacity: 0.5,
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
  guestTitle: {
    color: colors.ink,
    fontSize: 21,
    fontWeight: "900",
  },
  guestText: {
    color: colors.inkSoft,
    fontSize: 13,
    fontWeight: "600",
    lineHeight: 19,
  },
});
