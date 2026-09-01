import { useEffect, useRef } from "react";
import { AppState, Platform } from "react-native";

import { getMessageDeviceId } from "@/api/messageOutbox";
import { MessageRealtimeCoordinator } from "@/api/messageRealtime";
import { registerMessageDevice, syncMessagesWithRecovery } from "@/api/messageSync";
import { useAuth } from "@/auth/AuthProvider";

export function MessageRealtimeBridge() {
  const { accessToken, status } = useAuth();
  const coordinatorRef = useRef<MessageRealtimeCoordinator | null>(null);
  const accessTokenRef = useRef<string | null>(accessToken);
  accessTokenRef.current = accessToken;

  if (!coordinatorRef.current) {
    coordinatorRef.current = new MessageRealtimeCoordinator({
      onWake: () => {
        const token = accessTokenRef.current;
        if (token) void syncMessagesWithRecovery(token).catch(() => undefined);
      },
    });
  }

  useEffect(() => {
    const coordinator = coordinatorRef.current;
    if (!coordinator || status !== "authenticated" || !accessToken) {
      coordinator?.stop();
      return;
    }
    let active = true;
    let deviceId: string | null = null;
    const connect = async () => {
      deviceId = await getMessageDeviceId();
      const platform = Platform.OS === "ios" || Platform.OS === "android" || Platform.OS === "web" ? Platform.OS : "unknown";
      await registerMessageDevice(accessToken, deviceId, platform);
      if (active && AppState.currentState === "active") coordinator.start(accessToken, deviceId);
    };
    void connect().catch(() => undefined);
    const subscription = AppState.addEventListener("change", (nextState) => {
      if (nextState === "active" && deviceId) coordinator.start(accessToken, deviceId);
      else coordinator.stop();
    });
    return () => {
      active = false;
      subscription.remove();
      coordinator.stop();
    };
  }, [accessToken, status]);

  return null;
}
