import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

import { Card, IconBadge, RowButton, ScrollPage, TopBar } from "@/components/ui";
import { colors } from "@/theme";

export default function CreatePlaceholderScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ type?: string }>();
  const title = typeof params.type === "string" ? params.type : "创建";

  return (
    <ScrollPage>
      <TopBar onBack={() => router.back()} subtitle="占位页面" title={title} />

      <Card style={styles.hero}>
        <IconBadge name="construct-outline" tone="dark" />
        <Text style={styles.heroTitle}>{title}</Text>
        <Text style={styles.heroText}>这里先保留页面结构，后续接入真实流程、媒体选择、表单和数据保存。</Text>
      </Card>

      <View style={styles.mockFlow}>
        <RowButton icon="scan-outline" subtitle="后续接入相机、相册或输入表单" title="内容来源" />
        <RowButton icon="shield-checkmark-outline" subtitle="后续确认可见范围和同步方式" title="隐私与发布" />
        <RowButton
          icon="checkmark-circle-outline"
          subtitle="当前版本仅用于浏览 UI 框架"
          title="完成状态"
          trailing={<Ionicons color={colors.muted} name="ellipsis-horizontal" size={18} />}
        />
      </View>
    </ScrollPage>
  );
}

const styles = StyleSheet.create({
  hero: {
    alignItems: "flex-start",
    gap: 12,
  },
  heroTitle: {
    color: colors.ink,
    fontSize: 27,
    fontWeight: "900",
  },
  heroText: {
    color: colors.inkSoft,
    fontSize: 14,
    fontWeight: "600",
    lineHeight: 22,
  },
  mockFlow: {
    gap: 10,
    marginTop: 20,
  },
});
