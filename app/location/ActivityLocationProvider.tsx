import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { AppState } from "react-native";

import {
  ACTIVITY_LOCATION_REFRESH_INTERVAL_MS,
  getActivityLocationCacheSnapshot,
  refreshCurrentActivityLocation,
  subscribeActivityLocationCache,
  type ActivityLocationCacheSnapshot,
} from "@/api/location";

const ActivityLocationContext = createContext<ActivityLocationCacheSnapshot>(
  getActivityLocationCacheSnapshot(),
);

export function ActivityLocationProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<ActivityLocationCacheSnapshot>(
    getActivityLocationCacheSnapshot(),
  );

  useEffect(() => subscribeActivityLocationCache(setSnapshot), []);

  useEffect(() => {
    const refresh = () => {
      void refreshCurrentActivityLocation().catch(() => null);
    };
    const refreshIfActive = () => {
      if (AppState.currentState === "active") {
        refresh();
      }
    };

    refresh();
    const intervalId = setInterval(refreshIfActive, ACTIVITY_LOCATION_REFRESH_INTERVAL_MS);
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") {
        refreshIfActive();
      }
    });

    return () => {
      clearInterval(intervalId);
      subscription.remove();
    };
  }, []);

  const value = useMemo(
    () => snapshot,
    [snapshot],
  );

  return (
    <ActivityLocationContext.Provider value={value}>
      {children}
    </ActivityLocationContext.Provider>
  );
}

export function useActivityLocationCache() {
  return useContext(ActivityLocationContext);
}
