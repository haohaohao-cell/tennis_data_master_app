import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import type { ComponentProps, PropsWithChildren, ReactNode } from "react";
import {
  Pressable,
  ScrollView,
  StyleProp,
  StyleSheet,
  Text,
  View,
  ViewStyle,
} from "react-native";
import type { ImageSourcePropType } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { colors, radius, spacing } from "@/theme";

export type IconName = ComponentProps<typeof Ionicons>["name"];

type ScrollPageProps = PropsWithChildren<{
  bottomInset?: number;
  contentStyle?: StyleProp<ViewStyle>;
}>;

export function ScrollPage({ children, bottomInset = 42, contentStyle }: ScrollPageProps) {
  return (
    <SafeAreaView edges={["top", "left", "right"]} style={styles.safeArea}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={[
          styles.scrollContent,
          { paddingBottom: bottomInset },
          contentStyle,
        ]}
      >
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

type TopBarProps = {
  title: string;
  subtitle?: string;
  onBack?: () => void;
  right?: ReactNode;
};

export function TopBar({ title, subtitle, onBack, right }: TopBarProps) {
  return (
    <View style={styles.topBar}>
      <View style={styles.topBarLeft}>
        {onBack ? (
          <Pressable
            accessibilityLabel="返回"
            accessibilityRole="button"
            onPress={onBack}
            style={styles.backButton}
          >
            <Ionicons color={colors.ink} name="chevron-back" size={22} />
          </Pressable>
        ) : null}
        <View>
          {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
          <Text style={styles.title}>{title}</Text>
        </View>
      </View>
      {right}
    </View>
  );
}

type SegmentOption<T extends string> = {
  label: string;
  value: T;
};

type SegmentedControlProps<T extends string> = {
  options: SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
};

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
}: SegmentedControlProps<T>) {
  return (
    <View style={styles.segmentWrap}>
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <Pressable
            accessibilityRole="button"
            key={option.value}
            onPress={() => onChange(option.value)}
            style={[styles.segmentItem, selected && styles.segmentItemActive]}
          >
            <Text style={[styles.segmentText, selected && styles.segmentTextActive]}>
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

type AvatarProps = {
  name: string;
  size?: number;
  uri?: string | null;
};

export function Avatar({ name, size = 44, uri }: AvatarProps) {
  const initial = name.trim().slice(0, 1).toUpperCase();

  return (
    <View
      style={[
        styles.avatar,
        {
          height: size,
          width: size,
          borderRadius: size / 2,
        },
      ]}
    >
      {uri ? (
        <Image contentFit="cover" source={{ uri }} style={styles.avatarImage} />
      ) : (
        <Text style={[styles.avatarText, { fontSize: Math.max(15, size * 0.38) }]}>
          {initial}
        </Text>
      )}
    </View>
  );
}

type IconBadgeProps = {
  name: IconName;
  tone?: "dark" | "light" | "accent" | "clay" | "sky" | "gold";
};

export function IconBadge({ name, tone = "light" }: IconBadgeProps) {
  const dark = tone === "dark";
  const toneStyle =
    tone === "accent"
      ? styles.iconBadgeAccent
      : tone === "clay"
        ? styles.iconBadgeClay
        : tone === "sky"
          ? styles.iconBadgeSky
          : tone === "gold"
            ? styles.iconBadgeGold
            : null;

  return (
    <View style={[styles.iconBadge, dark && styles.iconBadgeDark, toneStyle]}>
      <Ionicons color={dark ? colors.inverse : colors.ink} name={name} size={20} />
    </View>
  );
}

type SectionHeaderProps = {
  title: string;
  action?: string;
};

export function SectionHeader({ title, action }: SectionHeaderProps) {
  return (
    <View style={styles.sectionHeader}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {action ? <Text style={styles.sectionAction}>{action}</Text> : null}
    </View>
  );
}

type MetricCardProps = {
  label: string;
  value: string;
  unit?: string;
};

export function MetricCard({ label, value, unit }: MetricCardProps) {
  return (
    <View style={styles.metricCard}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>
        {value}
        {unit ? <Text style={styles.metricUnit}> {unit}</Text> : null}
      </Text>
    </View>
  );
}

type MediaImageProps = {
  source: ImageSourcePropType;
  ratio?: number;
};

export function MediaImage({ source, ratio = 1.42 }: MediaImageProps) {
  return <Image contentFit="cover" source={source} style={[styles.media, { aspectRatio: ratio }]} />;
}

type RowButtonProps = {
  title: string;
  subtitle?: string;
  icon: IconName;
  onPress?: () => void;
  trailing?: ReactNode;
};

export function RowButton({ title, subtitle, icon, onPress, trailing }: RowButtonProps) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.rowButton}>
      <IconBadge name={icon} />
      <View style={styles.rowTextBlock}>
        <Text style={styles.rowTitle}>{title}</Text>
        {subtitle ? <Text style={styles.rowSubtitle}>{subtitle}</Text> : null}
      </View>
      {trailing ?? <Ionicons color={colors.muted} name="chevron-forward" size={18} />}
    </Pressable>
  );
}

export function Card({ children, style }: PropsWithChildren<{ style?: StyleProp<ViewStyle> }>) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Pill({ children }: PropsWithChildren) {
  return (
    <View style={styles.pill}>
      <Text style={styles.pillText}>{children}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    backgroundColor: colors.background,
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: spacing.pageX,
    paddingTop: 12,
  },
  topBar: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 18,
  },
  topBarLeft: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
  },
  backButton: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    height: 36,
    justifyContent: "center",
    width: 36,
  },
  subtitle: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "600",
    marginBottom: 2,
  },
  title: {
    color: colors.ink,
    fontSize: 28,
    fontWeight: "800",
  },
  segmentWrap: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.control,
    flexDirection: "row",
    padding: 3,
  },
  segmentItem: {
    alignItems: "center",
    borderRadius: radius.small,
    flex: 1,
    justifyContent: "center",
    minHeight: 36,
    paddingHorizontal: 8,
  },
  segmentItemActive: {
    backgroundColor: colors.surfaceWarm,
  },
  segmentText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "700",
  },
  segmentTextActive: {
    color: colors.ink,
  },
  avatar: {
    alignItems: "center",
    backgroundColor: colors.accentDeep,
    justifyContent: "center",
    overflow: "hidden",
  },
  avatarImage: {
    height: "100%",
    width: "100%",
  },
  avatarText: {
    color: colors.inverse,
    fontWeight: "800",
  },
  iconBadge: {
    alignItems: "center",
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.control,
    height: 38,
    justifyContent: "center",
    width: 38,
  },
  iconBadgeDark: {
    backgroundColor: colors.ink,
  },
  iconBadgeAccent: {
    backgroundColor: colors.accentSoft,
  },
  iconBadgeClay: {
    backgroundColor: colors.claySoft,
  },
  iconBadgeSky: {
    backgroundColor: colors.skySoft,
  },
  iconBadgeGold: {
    backgroundColor: colors.goldSoft,
  },
  sectionHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 12,
    marginTop: 2,
  },
  sectionTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "800",
  },
  sectionAction: {
    color: colors.inkSoft,
    fontSize: 13,
    fontWeight: "700",
  },
  metricCard: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flex: 1,
    minHeight: 82,
    padding: 14,
  },
  metricLabel: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
  metricValue: {
    color: colors.ink,
    fontSize: 25,
    fontWeight: "800",
    marginTop: 8,
  },
  metricUnit: {
    color: colors.inkSoft,
    fontSize: 12,
    fontWeight: "700",
  },
  media: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.card,
    overflow: "hidden",
    width: "100%",
  },
  rowButton: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 12,
    minHeight: 68,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  rowTextBlock: {
    flex: 1,
    gap: 3,
  },
  rowTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "800",
  },
  rowSubtitle: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "600",
  },
  card: {
    backgroundColor: colors.surfaceWarm,
    borderColor: colors.line,
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    padding: 14,
  },
  pill: {
    alignSelf: "flex-start",
    backgroundColor: colors.accentSoft,
    borderRadius: radius.small,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  pillText: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: "800",
  },
});
