import { Ionicons } from "@expo/vector-icons";
import { type Href, useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ApiError, API_BASE_URL } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { colors, radius, spacing } from "@/theme";

function readableError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === "INVALID_VERIFICATION_CODE") {
      return "验证码不正确，请输入 000000";
    }
    if (error.status === 0) {
      return "无法连接服务器，请确认后端已启动";
    }
    return error.message;
  }

  return "无法连接服务器，请确认后端已启动";
}

export default function LoginScreen() {
  const router = useRouter();
  const { redirect } = useLocalSearchParams<{ redirect?: string }>();
  const { loginWithPhone, requestVerificationCode } = useAuth();
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sendingCode, setSendingCode] = useState(false);
  const [loggingIn, setLoggingIn] = useState(false);

  const canSubmit = phone.trim().length > 0 && code.trim().length > 0 && accepted && !loggingIn;

  function handleClose() {
    if (router.canGoBack()) {
      router.back();
      return;
    }
    router.replace("/(tabs)");
  }

  async function handleSendCode() {
    if (!phone.trim()) {
      setError("请输入手机号");
      return;
    }

    setSendingCode(true);
    setError(null);
    try {
      const result = await requestVerificationCode(phone.trim());
      Alert.alert("验证码已发送", `开发期验证码：${result.dev_code ?? "000000"}`);
    } catch (nextError) {
      setError(readableError(nextError));
    } finally {
      setSendingCode(false);
    }
  }

  async function handleLogin() {
    if (!accepted) {
      setError("请先同意用户协议和隐私政策");
      return;
    }

    if (!phone.trim() || !code.trim()) {
      setError("请输入手机号和验证码");
      return;
    }

    setLoggingIn(true);
    setError(null);
    try {
      await loginWithPhone(phone.trim(), code.trim());
      router.replace((redirect || "/(tabs)") as Href);
    } catch (nextError) {
      setError(readableError(nextError));
    } finally {
      setLoggingIn(false);
    }
  }

  function handleWechatLogin() {
    Alert.alert("暂未开放", "微信登录将在正式版开放，请先使用手机号登录");
  }

  return (
    <SafeAreaView edges={["top", "bottom", "left", "right"]} style={styles.safeArea}>
      <KeyboardAvoidingView
        behavior={Platform.select({ ios: "padding", default: undefined })}
        style={styles.keyboardView}
      >
        <View style={styles.page}>
          <Pressable
            accessibilityLabel="关闭登录"
            accessibilityRole="button"
            disabled={loggingIn || sendingCode}
            onPress={handleClose}
            style={[styles.closeButton, (loggingIn || sendingCode) && styles.disabledButton]}
          >
            <Ionicons color={colors.ink} name="close" size={22} />
          </Pressable>

          <View style={styles.header}>
            <View style={styles.mark}>
              <Ionicons color={colors.inverse} name="tennisball-outline" size={25} />
            </View>
            <Text style={styles.title}>登录网球账户</Text>
            <Text style={styles.subtitle}>手机号首次登录会自动创建账户</Text>
          </View>

          <View style={styles.form}>
            <View style={styles.inputBlock}>
              <Text style={styles.label}>手机号</Text>
              <TextInput
                autoComplete="tel"
                keyboardType="phone-pad"
                onChangeText={setPhone}
                placeholder="请输入手机号"
                placeholderTextColor={colors.muted}
                style={styles.input}
                textContentType="telephoneNumber"
                value={phone}
              />
            </View>

            <View style={styles.inputBlock}>
              <Text style={styles.label}>验证码</Text>
              <View style={styles.codeRow}>
                <TextInput
                  keyboardType="number-pad"
                  maxLength={6}
                  onChangeText={setCode}
                  placeholder="000000"
                  placeholderTextColor={colors.muted}
                  style={[styles.input, styles.codeInput]}
                  value={code}
                />
                <Pressable
                  accessibilityRole="button"
                  disabled={sendingCode}
                  onPress={handleSendCode}
                  style={[styles.codeButton, sendingCode && styles.disabledButton]}
                >
                  {sendingCode ? (
                    <ActivityIndicator color={colors.ink} size="small" />
                  ) : (
                    <Text style={styles.codeButtonText}>获取验证码</Text>
                  )}
                </Pressable>
              </View>
            </View>

            <Pressable
              accessibilityRole="checkbox"
              accessibilityState={{ checked: accepted }}
              onPress={() => setAccepted((value) => !value)}
              style={styles.agreementRow}
            >
              <View style={[styles.checkbox, accepted && styles.checkboxActive]}>
                {accepted ? <Ionicons color={colors.inverse} name="checkmark" size={15} /> : null}
              </View>
              <Text style={styles.agreementText}>我已阅读并同意用户协议和隐私政策</Text>
            </Pressable>

            {error ? <Text style={styles.errorText}>{error}</Text> : null}

            <Pressable
              accessibilityRole="button"
              disabled={!canSubmit}
              onPress={handleLogin}
              style={[styles.loginButton, !canSubmit && styles.disabledButton]}
            >
              {loggingIn ? (
                <ActivityIndicator color={colors.inverse} />
              ) : (
                <Text style={styles.loginButtonText}>登录 / 注册</Text>
              )}
            </Pressable>

            <Pressable
              accessibilityRole="button"
              onPress={handleWechatLogin}
              style={styles.wechatButton}
            >
              <Ionicons color={colors.ink} name="logo-wechat" size={20} />
              <Text style={styles.wechatButtonText}>微信登录</Text>
            </Pressable>
          </View>

          <Text style={styles.endpoint}>API {API_BASE_URL}</Text>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    backgroundColor: colors.background,
    flex: 1,
  },
  keyboardView: {
    flex: 1,
  },
  page: {
    flex: 1,
    justifyContent: "center",
    paddingHorizontal: spacing.pageX,
  },
  closeButton: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    height: 38,
    justifyContent: "center",
    position: "absolute",
    right: spacing.pageX,
    top: 14,
    width: 38,
  },
  header: {
    gap: 10,
    marginBottom: 34,
  },
  mark: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    height: 48,
    justifyContent: "center",
    marginBottom: 8,
    width: 48,
  },
  title: {
    color: colors.ink,
    fontSize: 30,
    fontWeight: "900",
  },
  subtitle: {
    color: colors.inkSoft,
    fontSize: 14,
    fontWeight: "600",
  },
  form: {
    gap: 16,
  },
  inputBlock: {
    gap: 8,
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
  codeRow: {
    flexDirection: "row",
    gap: 10,
  },
  codeInput: {
    flex: 1,
  },
  codeButton: {
    alignItems: "center",
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.control,
    justifyContent: "center",
    minHeight: 52,
    paddingHorizontal: 14,
    width: 118,
  },
  codeButtonText: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "900",
  },
  agreementRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 9,
    paddingVertical: 2,
  },
  checkbox: {
    alignItems: "center",
    borderColor: colors.line,
    borderRadius: 5,
    borderWidth: 1,
    height: 21,
    justifyContent: "center",
    width: 21,
  },
  checkboxActive: {
    backgroundColor: colors.ink,
    borderColor: colors.ink,
  },
  agreementText: {
    color: colors.inkSoft,
    flex: 1,
    fontSize: 13,
    fontWeight: "700",
    lineHeight: 18,
  },
  errorText: {
    color: "#B14A3D",
    fontSize: 13,
    fontWeight: "800",
    lineHeight: 18,
  },
  loginButton: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radius.control,
    justifyContent: "center",
    minHeight: 54,
  },
  loginButtonText: {
    color: colors.inverse,
    fontSize: 16,
    fontWeight: "900",
  },
  wechatButton: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: 8,
    justifyContent: "center",
    minHeight: 52,
  },
  wechatButtonText: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "800",
  },
  disabledButton: {
    opacity: 0.48,
  },
  endpoint: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "700",
    marginTop: 22,
    textAlign: "center",
  },
});
