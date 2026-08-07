import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useRequireAuth } from "@/auth/useRequireAuth";
import { colors, radius } from "@/theme";

const journalActions = [
  {
    icon: "fitness-outline",
    kind: "practice",
    label: "记录练习",
    subtitle: "保存练习日记，可同时上传相册视频",
  },
  {
    icon: "trophy-outline",
    kind: "match",
    label: "记录比赛",
    subtitle: "保存比赛过程，也可上传比赛视频",
  },
  {
    icon: "school-outline",
    kind: "lesson",
    label: "记录课程",
    subtitle: "绑定课程后记录重点，也可上传课堂视频",
  },
] as const;

type JournalAction = (typeof journalActions)[number];
type CreateStep = "root" | "journal";

export default function CreateMenuScreen() {
  const router = useRouter();
  const requireAuth = useRequireAuth();
  const [step, setStep] = useState<CreateStep>("root");

  function handlePublishPost() {
    if (!requireAuth("发布动态需要登录后继续", "/create-post")) {
      return;
    }
    router.replace("/create-post");
  }

  function handleJournalAction(item: JournalAction) {
    const kind = item.kind;
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
            <View style={styles.sheetTitleGroup}>
              <View style={styles.sheetTitleRow}>
                {step === "journal" ? (
                  <Pressable
                    accessibilityLabel="返回创建选项"
                    accessibilityRole="button"
                    onPress={() => setStep("root")}
                    style={styles.backButton}
                  >
                    <Ionicons color={colors.ink} name="chevron-back" size={20} />
                  </Pressable>
                ) : null}
                <Text style={styles.sheetTitle}>{step === "journal" ? "创建网球日记" : "创建"}</Text>
              </View>
              <Text style={styles.sheetSubtitle}>
                {step === "journal" ? "先选择这次记录的类型" : "发布动态，或记录一次网球活动"}
              </Text>
            </View>
            <Pressable accessibilityLabel="关闭" accessibilityRole="button" onPress={() => router.back()} style={styles.closeButton}>
              <Ionicons color={colors.ink} name="close" size={20} />
            </Pressable>
          </View>

          <View style={styles.actionList}>
            {step === "root" ? (
              <>
                <Pressable
                  accessibilityLabel="发布动态，发布到社区"
                  accessibilityRole="button"
                  onPress={handlePublishPost}
                  style={styles.actionRow}
                >
                  <View style={styles.actionIcon}>
                    <Ionicons color={colors.ink} name="create-outline" size={22} />
                  </View>
                  <View style={styles.actionCopy}>
                    <Text style={styles.actionLabel}>发布动态</Text>
                    <Text numberOfLines={1} style={styles.actionSubtitle}>
                      发到社区，可单独发布，也可之后从日记分享
                    </Text>
                  </View>
                  <Ionicons color={colors.muted} name="chevron-forward" size={18} />
                </Pressable>
                <Pressable
                  accessibilityLabel="创建网球日记"
                  accessibilityRole="button"
                  onPress={() => setStep("journal")}
                  style={styles.actionRow}
                >
                  <View style={styles.actionIcon}>
                    <Ionicons color={colors.ink} name="journal-outline" size={22} />
                  </View>
                  <View style={styles.actionCopy}>
                    <Text style={styles.actionLabel}>创建网球日记</Text>
                    <Text numberOfLines={1} style={styles.actionSubtitle}>
                      记录练习、比赛或课程，归入个人 Activity 档案
                    </Text>
                  </View>
                  <Ionicons color={colors.muted} name="chevron-forward" size={18} />
                </Pressable>
              </>
            ) : (
              journalActions.map((item) => (
                <Pressable
                  accessibilityLabel={`${item.label}，${item.subtitle}`}
                  accessibilityRole="button"
                  key={item.kind}
                  onPress={() => handleJournalAction(item)}
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
              ))
            )}
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
  sheetTitleGroup: {
    flex: 1,
    gap: 3,
    minWidth: 0,
  },
  sheetTitleRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 6,
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
  backButton: {
    alignItems: "center",
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.control,
    height: 34,
    justifyContent: "center",
    width: 34,
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
