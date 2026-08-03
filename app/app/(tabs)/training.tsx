import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import {
  Card,
  IconBadge,
  MetricCard,
  Pill,
  ScrollPage,
  SectionHeader,
  TopBar,
  type IconName,
} from "@/components/ui";
import { activities, trainingEntries } from "@/data/mockData";
import { colors, radius } from "@/theme";

const chartColors = [
  colors.sky,
  colors.gold,
  colors.accent,
  colors.clay,
  colors.sky,
  colors.gold,
  colors.accentDeep,
];

const entryTones = ["sky", "gold", "accent", "clay"] as const;

export default function TrainingScreen() {
  const router = useRouter();

  return (
    <ScrollPage bottomInset={112}>
      <TopBar
        right={
          <Pressable accessibilityLabel="查看训练日历" accessibilityRole="button" style={styles.calendarButton}>
            <Ionicons color={colors.accentDeep} name="calendar-outline" size={21} />
          </Pressable>
        }
        subtitle="本周已上场 4 次"
        title="训练"
      />

      <Card style={styles.overviewCard}>
        <View style={styles.overviewHeader}>
          <View>
            <Text style={styles.overviewTitle}>本周概览</Text>
            <Text style={styles.overviewSubtitle}>保持节奏，下一次上场在明天</Text>
          </View>
          <View style={styles.scoreMark}>
            <Text style={styles.scoreValue}>82</Text>
          </View>
        </View>
        <View style={styles.metrics}>
          <MetricCard label="上场时长" unit="h" value="6.4" />
          <MetricCard label="训练次数" unit="次" value="4" />
          <MetricCard label="连续天数" unit="天" value="3" />
        </View>
        <View style={styles.chartRow}>
          {[42, 70, 54, 86, 60, 78, 96].map((height, index) => (
            <View key={index} style={styles.chartItem}>
              <View style={[styles.chartBar, { backgroundColor: chartColors[index], height }]} />
            </View>
          ))}
        </View>
      </Card>

      <View style={styles.section}>
        <SectionHeader title="记录" />
        <View style={styles.entryGrid}>
          {trainingEntries.map((entry, index) => (
            <Pressable
              accessibilityRole="button"
              key={entry.label}
              onPress={() => {
                if (entry.label === "比赛") {
                  router.push({ pathname: "/create-activity", params: { kind: "match" } });
                  return;
                }
                if (entry.label === "训练") {
                  router.push({ pathname: "/create-activity", params: { kind: "training" } });
                  return;
                }
                if (entry.label === "视频") {
                  router.push("/upload-video");
                  return;
                }
                router.push({
                  pathname: "/create-placeholder",
                  params: { type: `记录${entry.label}` },
                });
              }}
              style={styles.entry}
            >
              <IconBadge name={entry.icon as IconName} tone={entryTones[index]} />
              <Text style={styles.entryLabel}>{entry.label}</Text>
              <Ionicons color={colors.muted} name="add" size={17} />
            </Pressable>
          ))}
        </View>
      </View>

      <View style={styles.section}>
        <SectionHeader action="全部活动" title="最近活动" />
        <View style={styles.activityList}>
          {activities.map((activity) => (
            <Pressable
              accessibilityLabel={`查看${activity.title}`}
              accessibilityRole="button"
              key={activity.id}
              onPress={() => router.push({ pathname: "/activity/[id]", params: { id: activity.id } })}
              style={styles.activityRow}
            >
              <View style={styles.activityLeading}>
                <View
                  style={[
                    styles.activityIcon,
                    activity.type === "比赛" ? styles.activityIconClay : styles.activityIconSky,
                  ]}
                >
                  <Ionicons
                    color={activity.type === "比赛" ? colors.clay : colors.accentDeep}
                    name={activity.type === "比赛" ? "trophy-outline" : "fitness-outline"}
                    size={19}
                  />
                </View>
                <View style={styles.activityText}>
                  <Text numberOfLines={1} style={styles.activityTitle}>
                    {activity.title}
                  </Text>
                  <Text style={styles.activityMeta}>
                    {activity.time} · {activity.location}
                  </Text>
                </View>
              </View>
              <View style={styles.activityTrailing}>
                <Pill>{activity.type}</Pill>
                <Ionicons color={colors.muted} name="chevron-forward" size={17} />
              </View>
            </Pressable>
          ))}
        </View>
      </View>
    </ScrollPage>
  );
}

const styles = StyleSheet.create({
  calendarButton: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    height: 38,
    justifyContent: "center",
    width: 38,
  },
  overviewCard: {
    gap: 18,
    padding: 16,
  },
  overviewHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  overviewTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "800",
  },
  overviewSubtitle: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "600",
    marginTop: 4,
  },
  scoreMark: {
    alignItems: "center",
    backgroundColor: colors.goldSoft,
    borderColor: "#EFE2BA",
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radius.control,
    height: 48,
    justifyContent: "center",
    width: 54,
  },
  scoreValue: {
    color: colors.accentDeep,
    fontSize: 21,
    fontWeight: "900",
  },
  metrics: {
    flexDirection: "row",
    gap: 8,
  },
  chartRow: {
    alignItems: "flex-end",
    borderTopColor: colors.line,
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 7,
    height: 105,
    paddingTop: 12,
  },
  chartItem: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: 3,
    flex: 1,
    height: 86,
    justifyContent: "flex-end",
  },
  chartBar: {
    borderRadius: 3,
    minHeight: 18,
  },
  section: {
    marginTop: 26,
  },
  entryGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
  },
  entry: {
    alignItems: "center",
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 9,
    justifyContent: "space-between",
    minHeight: 68,
    paddingHorizontal: 12,
    width: "48.4%",
  },
  entryLabel: {
    color: colors.ink,
    flex: 1,
    fontSize: 14,
    fontWeight: "800",
  },
  activityList: {
    gap: 10,
  },
  activityRow: {
    alignItems: "center",
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    justifyContent: "space-between",
    minHeight: 74,
    paddingHorizontal: 12,
  },
  activityLeading: {
    alignItems: "center",
    flex: 1,
    flexDirection: "row",
    gap: 10,
    paddingRight: 8,
  },
  activityIcon: {
    alignItems: "center",
    borderRadius: radius.control,
    height: 39,
    justifyContent: "center",
    width: 39,
  },
  activityIconClay: {
    backgroundColor: colors.claySoft,
  },
  activityIconSky: {
    backgroundColor: colors.skySoft,
  },
  activityText: {
    flex: 1,
    gap: 4,
  },
  activityTitle: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "800",
  },
  activityMeta: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "600",
  },
  activityTrailing: {
    alignItems: "center",
    flexDirection: "row",
    gap: 7,
  },
});
