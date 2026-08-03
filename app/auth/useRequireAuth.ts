import { useRouter } from "expo-router";
import { useCallback } from "react";
import { Alert } from "react-native";

import { useAuth } from "@/auth/AuthProvider";

export function useRequireAuth() {
  const { isAuthenticated, status } = useAuth();
  const router = useRouter();

  return useCallback(
    (message = "此操作需要登录后继续", redirect = "/(tabs)") => {
      if (status === "authenticated" && isAuthenticated) {
        return true;
      }

      if (status === "loading") {
        Alert.alert("请稍候", "正在确认登录状态");
        return false;
      }

      Alert.alert("需要登录", message, [
        { style: "cancel", text: "先看看" },
        {
          onPress: () =>
            router.push({
              pathname: "/login",
              params: { redirect },
            }),
          text: "去登录",
        },
      ]);
      return false;
    },
    [isAuthenticated, router, status],
  );
}
