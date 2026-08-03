import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";

import { Avatar, Card, MetricCard, Pill, RowButton, ScrollPage, SectionHeader, TopBar } from "@/components/ui";
import { students } from "@/data/mockData";
import { colors } from "@/theme";

export default function StudentProfileScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id?: string }>();
  const student = useMemo(() => students.find((item) => item.id === id) ?? students[0], [id]);

  return (
    <ScrollPage>
      <TopBar onBack={() => router.back()} subtitle="学员档案" title={student.name} />

      <Card style={styles.headerCard}>
        <View style={styles.identityRow}>
          <Avatar name={student.name} size={64} />
          <View style={styles.identityText}>
            <View style={styles.nameLine}>
              <Text style={styles.name}>{student.name}</Text>
              <Pill>{student.level}</Pill>
            </View>
            <Text style={styles.meta}>最近上课 {student.lastLesson}</Text>
            <Text style={styles.focus}>当前重点：{student.focus}</Text>
          </View>
        </View>
        <View style={styles.metricRow}>
          <MetricCard label="课程次数" unit="次" value={`${student.lessons}`} />
          <MetricCard label="训练记录" unit="条" value="14" />
          <MetricCard label="视频记录" unit="条" value="8" />
        </View>
      </Card>

      <View style={styles.section}>
        <SectionHeader title="记录" />
        <View style={styles.list}>
          <RowButton icon="fitness-outline" subtitle="本周 2 次，底线稳定性训练" title="训练记录" />
          <RowButton icon="trophy-outline" subtitle="最近一场 6-4 / 3-6 / 10-8" title="比赛记录" />
          <RowButton icon="videocam-outline" subtitle="发球、正手移动、网前处理" title="视频记录" />
        </View>
      </View>

      <View style={styles.section}>
        <SectionHeader title="教练评价" />
        <Card style={styles.reviewCard}>
          <View style={styles.reviewHeader}>
            <Ionicons color={colors.ink} name="chatbox-ellipses-outline" size={20} />
            <Text style={styles.reviewTitle}>阶段反馈</Text>
          </View>
          <Text style={styles.reviewText}>{student.note}</Text>
        </Card>
      </View>
    </ScrollPage>
  );
}

const styles = StyleSheet.create({
  headerCard: {
    gap: 18,
  },
  identityRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 14,
  },
  identityText: {
    flex: 1,
    gap: 6,
  },
  nameLine: {
    alignItems: "center",
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  name: {
    color: colors.ink,
    fontSize: 24,
    fontWeight: "900",
  },
  meta: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "700",
  },
  focus: {
    color: colors.inkSoft,
    fontSize: 13,
    fontWeight: "700",
  },
  metricRow: {
    flexDirection: "row",
    gap: 8,
  },
  section: {
    marginTop: 24,
  },
  list: {
    gap: 10,
  },
  reviewCard: {
    gap: 10,
  },
  reviewHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  reviewTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "900",
  },
  reviewText: {
    color: colors.inkSoft,
    fontSize: 14,
    fontWeight: "600",
    lineHeight: 22,
  },
});
