import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useRequireAuth } from "@/auth/useRequireAuth";
import { createActions } from "@/data/mockData";
import { colors, radius } from "@/theme";

type CreateAction = (typeof createActions)[number];

export default function CreateMenuScreen() {
  const router = useRouter();
  const requireAuth = useRequireAuth();

  function handleAction(item: CreateAction) {
    if (item.kind === "upload_video") {
      if (!requireAuth("上传视频需要登录后继续", "/upload-video")) {
        return;
      }
      router.replace("/upload-video");
      return;
    }
    if (item.kind === "publish_post") {
      if (!requireAuth("发布动态需要登录后继续", "/create-post")) {
        return;
      }
      router.replace("/create-post");
      return;
    }

    const kind = item.kind === "record_match" ? "match" : "training";
    const redirect = `/create-activity?kind=${kind}`;
    if (!requireAuth(`${item.label}需要登录后继续`, redirect)) {
      return;
    }
    router.replace({
      pathname: "/create-activity",
      params: { kind },
    });
  }

  return (
    <View style={styles.overlay}>
      <Pressable accessibilityLabel="关闭创建菜单" onPress={() => router.back()} style={styles.backdrop} />
      <SafeAreaView edges={["bottom"]} style={styles.sheetWrap}>
        <View style={styles.sheet}>
          <View style={styles.sheetHandle} />
          <View style={styles.sheetHeader}>
            <View>
              <Text style={styles.sheetTitle}>创建</Text>
              <Text style={styles.sheetSubtitle}>Activity 归档和 Post 发布分开处理</Text>
            </View>
            <Pressable accessibilityLabel="关闭" accessibilityRole="button" onPress={() => router.back()} style={styles.closeButton}>
              <Ionicons color={colors.ink} name="close" size={20} />
            </Pressable>
          </View>

          <View style={styles.actionList}>
            {createActions.map((item) => (
              <Pressable
                accessibilityLabel={`${item.label}，${item.subtitle}`}
                accessibilityRole="button"
                key={item.label}
                onPress={() => handleAction(item)}
                style={styles.actionRow}
              >
                <View style={styles.actionIcon}>
                  <Ionicons color={colors.ink} name={item.icon} size={22} />
                </View>
                <View style={styles.actionCopy}>
                  <Text style={styles.actionLabel}>{item.label}</Text>
                  <Text numberOfLines={1} style={styles.actionSubtitle}>
                    {item.subtitle}
                  </Text>
                </View>
                <Ionicons color={colors.muted} name="chevron-forward" size={18} />
              </Pressable>
            ))}
          </View>
        </View>
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    justifyContent: "flex-end",
  },
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.28)",
  },
  sheetWrap: {
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.control,
    borderTopRightRadius: radius.control,
    paddingBottom: 10,
    paddingHorizontal: 20,
    paddingTop: 10,
  },
  sheetHandle: {
    alignSelf: "center",
    backgroundColor: colors.line,
    borderRadius: 2,
    height: 4,
    marginBottom: 16,
    width: 42,
  },
  sheetHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 12,
  },
  sheetTitle: {
    color: colors.ink,
    fontSize: 24,
    fontWeight: "900",
  },
  sheetSubtitle: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "600",
    marginTop: 3,
  },
  closeButton: {
    alignItems: "center",
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.control,
    height: 36,
    justifyContent: "center",
    width: 36,
  },
  actionList: {
    gap: 8,
  },
  actionRow: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 12,
    minHeight: 68,
    paddingHorizontal: 12,
  },
  actionIcon: {
    alignItems: "center",
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.control,
    height: 38,
    justifyContent: "center",
    width: 38,
  },
  actionLabel: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "800",
  },
  actionCopy: {
    flex: 1,
    gap: 3,
    minWidth: 0,
  },
  actionSubtitle: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
});
