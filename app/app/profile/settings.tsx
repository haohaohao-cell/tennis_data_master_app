import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, View } from "react-native";

import { useAuth } from "@/auth/AuthProvider";
import { RowButton, ScrollPage, TopBar } from "@/components/ui";
import { colors, radius } from "@/theme";

export default function ProfileSettingsScreen() {
  const router = useRouter();
  const { isAuthenticated, logout, status } = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);

  function confirmLogout() {
    if (loggingOut) {
      return;
    }

    Alert.alert(
      "退出登录",
      "退出后，发布、上传和查看个人内容需要重新登录。",
      [
        { text: "取消", style: "cancel" },
        {
          text: "退出登录",
          style: "destructive",
          onPress: () => {
            void handleLogout();
          },
        },
      ],
    );
  }

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await logout();
      router.replace("/(tabs)/profile");
    } catch {
      Alert.alert("退出失败", "暂时无法清理本地登录状态，请稍后重试。");
    } finally {
      setLoggingOut(false);
    }
  }

  if (status === "loading") {
    return (
      <ScrollPage contentStyle={styles.page}>
        <TopBar onBack={() => router.back()} subtitle="我的" title="设置" />
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
        <TopBar onBack={() => router.back()} subtitle="我的" title="设置" />
        <View style={styles.guestPanel}>
          <Text style={styles.guestTitle}>登录后管理账户</Text>
          <Text style={styles.guestText}>账号资料和登录状态仅对当前账户开放。</Text>
          <RowButton
            icon="log-in-outline"
            onPress={() =>
              router.replace({
                pathname: "/login",
                params: { redirect: "/profile/settings" },
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
      <TopBar onBack={() => router.back()} subtitle="我的" title="设置" />

      <View style={styles.section}>
        <Text style={styles.sectionLabel}>账户</Text>
        <RowButton
          icon="person-circle-outline"
          onPress={() => router.push("/profile/edit")}
          subtitle="昵称、头像、持拍手"
          title="账号资料"
        />
      </View>

      <View style={styles.dangerSection}>
        <Text style={styles.sectionLabel}>登录状态</Text>
        <Pressable
          accessibilityRole="button"
          disabled={loggingOut}
          onPress={confirmLogout}
          style={[styles.logoutButton, loggingOut && styles.logoutButtonDisabled]}
        >
          {loggingOut ? (
            <ActivityIndicator color="#B14A3D" />
          ) : (
            <>
              <Ionicons color="#B14A3D" name="log-out-outline" size={20} />
              <Text style={styles.logoutButtonText}>退出登录</Text>
            </>
          )}
        </Pressable>
      </View>
    </ScrollPage>
  );
}

const styles = StyleSheet.create({
  page: {
    gap: 28,
    paddingTop: 18,
  },
  section: {
    gap: 10,
  },
  dangerSection: {
    gap: 10,
    marginTop: "auto",
  },
  sectionLabel: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "800",
  },
  logoutButton: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: "#E5C5C0",
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 9,
    justifyContent: "center",
    minHeight: 54,
    paddingHorizontal: 16,
  },
  logoutButtonDisabled: {
    opacity: 0.55,
  },
  logoutButtonText: {
    color: "#B14A3D",
    fontSize: 16,
    fontWeight: "900",
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
