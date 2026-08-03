import { Component, ErrorInfo, PropsWithChildren } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { captureError } from "@/diagnostics/errorReporter";
import { colors, radius, spacing } from "@/theme";

type State = {
  error: Error | null;
};

export class DiagnosticErrorBoundary extends Component<PropsWithChildren, State> {
  state: State = {
    error: null,
  };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    captureError(error, {
      componentStack: errorInfo.componentStack,
      source: "REACT_ERROR",
    });
  }

  render() {
    if (this.state.error) {
      return (
        <View style={styles.screen}>
          <Text style={styles.title}>页面遇到错误</Text>
          <Text style={styles.message}>诊断弹窗已经保留完整报错信息，可以复制后用于排查。</Text>
          <Pressable accessibilityRole="button" onPress={() => this.setState({ error: null })} style={styles.button}>
            <Text style={styles.buttonText}>返回页面</Text>
          </Pressable>
        </View>
      );
    }

    return this.props.children;
  }
}

const styles = StyleSheet.create({
  screen: {
    alignItems: "center",
    backgroundColor: colors.background,
    flex: 1,
    justifyContent: "center",
    paddingHorizontal: spacing.pageX,
  },
  title: {
    color: colors.ink,
    fontSize: 22,
    fontWeight: "900",
  },
  message: {
    color: colors.inkSoft,
    fontSize: 14,
    fontWeight: "700",
    lineHeight: 21,
    marginTop: 10,
    textAlign: "center",
  },
  button: {
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    marginTop: 18,
    paddingHorizontal: 18,
    paddingVertical: 11,
  },
  buttonText: {
    color: colors.inverse,
    fontSize: 14,
    fontWeight: "900",
  },
});
