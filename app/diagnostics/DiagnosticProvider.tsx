import { Ionicons } from "@expo/vector-icons";
import * as Clipboard from "expo-clipboard";
import { usePathname } from "expo-router";
import { PropsWithChildren, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  installGlobalDiagnosticsHandlers,
  setCurrentDiagnosticRoute,
  subscribeDiagnostics,
} from "@/diagnostics/errorReporter";
import type { DiagnosticEvent } from "@/diagnostics/types";
import { colors, radius, spacing } from "@/theme";

export function DiagnosticProvider({ children }: PropsWithChildren) {
  const pathname = usePathname();
  const [events, setEvents] = useState<DiagnosticEvent[]>([]);
  const [copyState, setCopyState] = useState<"idle" | "copying" | "copied" | "failed">("idle");
  const current = events[0] ?? null;

  useEffect(() => {
    setCurrentDiagnosticRoute(pathname);
  }, [pathname]);

  useEffect(() => {
    installGlobalDiagnosticsHandlers();
    const unsubscribe = subscribeDiagnostics((event) => {
      setEvents((currentEvents) => [...currentEvents, event].slice(-5));
      setCopyState("idle");
    });
    return unsubscribe;
  }, []);

  const closeCurrent = () => {
    setEvents((currentEvents) => currentEvents.slice(1));
    setCopyState("idle");
  };

  const copyCurrent = () => {
    if (!current || copyState === "copying") {
      return;
    }
    setCopyState("copying");
    void Clipboard.setStringAsync(current.copiedText)
      .then(() => setCopyState("copied"))
      .catch(() => setCopyState("failed"));
  };

  return (
    <>
      {children}
      <Modal animationType="fade" onRequestClose={closeCurrent} transparent visible={Boolean(current)}>
        <SafeAreaView style={styles.overlay}>
          <View style={styles.panel}>
            <View style={styles.header}>
              <View style={styles.headerText}>
                <Text style={styles.kicker}>诊断信息</Text>
                <Text numberOfLines={1} style={styles.title}>{current?.source ?? "ERROR"}</Text>
              </View>
              <Pressable accessibilityLabel="关闭诊断弹窗" accessibilityRole="button" onPress={closeCurrent} style={styles.iconButton}>
                <Ionicons color={colors.ink} name="close" size={22} />
              </Pressable>
            </View>
            <ScrollView contentContainerStyle={styles.body} style={styles.scroll} showsVerticalScrollIndicator>
              <Text selectable style={styles.diagnosticText}>{current?.copiedText}</Text>
            </ScrollView>
            <View style={styles.footer}>
              <Text style={styles.footerText}>
                {copyState === "copied"
                  ? "已复制"
                  : copyState === "failed"
                    ? "复制失败，可长按文本选择复制"
                    : current
                      ? current.id
                      : ""}
              </Text>
              <Pressable accessibilityRole="button" onPress={copyCurrent} style={styles.copyButton}>
                {copyState === "copying" ? (
                  <ActivityIndicator color={colors.inverse} size="small" />
                ) : (
                  <>
                    <Ionicons color={colors.inverse} name="copy-outline" size={17} />
                    <Text style={styles.copyButtonText}>复制全部</Text>
                  </>
                )}
              </Pressable>
            </View>
          </View>
        </SafeAreaView>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  overlay: {
    alignItems: "center",
    backgroundColor: "rgba(36, 42, 46, 0.56)",
    flex: 1,
    justifyContent: "center",
    paddingHorizontal: spacing.pageX,
    paddingVertical: 24,
  },
  panel: {
    backgroundColor: colors.surface,
    borderRadius: radius.card,
    maxHeight: "92%",
    overflow: "hidden",
    width: "100%",
  },
  header: {
    alignItems: "center",
    borderBottomColor: colors.line,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
    padding: 14,
  },
  headerText: {
    flex: 1,
    minWidth: 0,
  },
  kicker: {
    color: colors.clay,
    fontSize: 12,
    fontWeight: "900",
  },
  title: {
    color: colors.ink,
    fontSize: 17,
    fontWeight: "900",
    marginTop: 3,
  },
  iconButton: {
    alignItems: "center",
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.control,
    height: 36,
    justifyContent: "center",
    width: 36,
  },
  scroll: {
    flex: 1,
  },
  body: {
    padding: 14,
  },
  diagnosticText: {
    color: colors.ink,
    fontFamily: "monospace",
    fontSize: 11,
    lineHeight: 17,
  },
  footer: {
    alignItems: "center",
    borderTopColor: colors.line,
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
    padding: 14,
  },
  footerText: {
    color: colors.muted,
    flex: 1,
    fontSize: 12,
    fontWeight: "700",
  },
  copyButton: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    flexDirection: "row",
    gap: 7,
    justifyContent: "center",
    minHeight: 40,
    minWidth: 112,
    paddingHorizontal: 14,
  },
  copyButtonText: {
    color: colors.inverse,
    fontSize: 13,
    fontWeight: "900",
  },
});
