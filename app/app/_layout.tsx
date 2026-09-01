import { Stack, useRouter, useSegments } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { AuthProvider, useAuth } from "@/auth/AuthProvider";
import { DiagnosticErrorBoundary } from "@/diagnostics/DiagnosticErrorBoundary";
import { DiagnosticProvider } from "@/diagnostics/DiagnosticProvider";
import { ActivityLocationProvider } from "@/location/ActivityLocationProvider";
import { MessageRealtimeBridge } from "@/messages/MessageRealtimeBridge";

export const unstable_settings = {
  initialRouteName: "(tabs)",
};

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <DiagnosticProvider>
        <DiagnosticErrorBoundary>
          <AuthProvider>
            <MessageRealtimeBridge />
            <ActivityLocationProvider>
              <RootNavigation />
            </ActivityLocationProvider>
          </AuthProvider>
        </DiagnosticErrorBoundary>
      </DiagnosticProvider>
    </SafeAreaProvider>
  );
}

function RootNavigation() {
  const { status } = useAuth();
  const router = useRouter();
  const segments = useSegments();
  const firstSegment = segments[0];
  const isLoginRoute = firstSegment === "login";

  useEffect(() => {
    if (status === "loading") {
      return;
    }

    if (status === "authenticated" && isLoginRoute) {
      router.replace("/(tabs)");
    }
  }, [isLoginRoute, router, status]);

  return (
    <>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="login" />
        <Stack.Screen
          name="create"
          options={{
            animation: "fade",
            presentation: "transparentModal",
          }}
        />
        <Stack.Screen name="create-placeholder" />
        <Stack.Screen name="create-activity" />
        <Stack.Screen name="create-post" />
        <Stack.Screen name="upload-video" />
        <Stack.Screen name="post/[id]" />
        <Stack.Screen name="user/[id]" />
        <Stack.Screen name="activity/[id]" />
        <Stack.Screen name="student/[id]" />
        <Stack.Screen name="chat/[id]" />
        <Stack.Screen name="friends/search" />
        <Stack.Screen name="profile/edit" />
        <Stack.Screen name="profile/settings" />
        <Stack.Screen name="profile/coach-apply" />
      </Stack>
    </>
  );
}
