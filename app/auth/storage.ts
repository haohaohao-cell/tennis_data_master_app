import { requireOptionalNativeModule } from "expo-modules-core";
import { Platform } from "react-native";

import type { StoredAuthSession } from "@/auth/types";

const STORAGE_KEY = "tennis_auth_session_v1";

let nativeMemorySession: StoredAuthSession | null = null;

type ExpoSecureStoreModule = {
  deleteValueWithKeyAsync?: (key: string, options?: Record<string, unknown>) => Promise<void>;
  getValueWithKeyAsync?: (
    key: string,
    options?: Record<string, unknown>,
  ) => Promise<string | null>;
  setValueWithKeyAsync?: (
    value: string,
    key: string,
    options?: Record<string, unknown>,
  ) => Promise<void>;
};

const secureStore = requireOptionalNativeModule<ExpoSecureStoreModule>("ExpoSecureStore");
const secureStoreOptions = {};

export type AuthStorageMode = "secure-store" | "web-local-storage" | "native-memory";

export function getAuthStorageMode(): AuthStorageMode {
  if (Platform.OS === "web") {
    return "web-local-storage";
  }
  if (
    secureStore?.getValueWithKeyAsync &&
    secureStore.setValueWithKeyAsync &&
    secureStore.deleteValueWithKeyAsync
  ) {
    return "secure-store";
  }
  return "native-memory";
}

function getWebStorage(): Storage | null {
  if (Platform.OS !== "web") {
    return null;
  }

  const storage = globalThis.localStorage;
  return storage ?? null;
}

export async function readStoredAuthSession(): Promise<StoredAuthSession | null> {
  const storage = getWebStorage();
  if (!storage) {
    if (getAuthStorageMode() === "secure-store" && secureStore?.getValueWithKeyAsync) {
      const rawValue = await secureStore.getValueWithKeyAsync(STORAGE_KEY, secureStoreOptions);
      if (!rawValue) {
        return null;
      }
      try {
        return JSON.parse(rawValue) as StoredAuthSession;
      } catch {
        await secureStore.deleteValueWithKeyAsync?.(STORAGE_KEY, secureStoreOptions);
        return null;
      }
    }
    return nativeMemorySession;
  }

  const rawValue = storage.getItem(STORAGE_KEY);
  if (!rawValue) {
    return null;
  }

  try {
    return JSON.parse(rawValue) as StoredAuthSession;
  } catch {
    storage.removeItem(STORAGE_KEY);
    return null;
  }
}

export async function writeStoredAuthSession(session: StoredAuthSession): Promise<void> {
  const storage = getWebStorage();
  nativeMemorySession = session;

  if (storage) {
    storage.setItem(STORAGE_KEY, JSON.stringify(session));
    return;
  }

  if (getAuthStorageMode() === "secure-store" && secureStore?.setValueWithKeyAsync) {
    await secureStore.setValueWithKeyAsync(JSON.stringify(session), STORAGE_KEY, secureStoreOptions);
  }
}

export async function clearStoredAuthSession(): Promise<void> {
  const storage = getWebStorage();
  nativeMemorySession = null;

  if (storage) {
    storage.removeItem(STORAGE_KEY);
    return;
  }

  if (getAuthStorageMode() === "secure-store" && secureStore?.deleteValueWithKeyAsync) {
    await secureStore.deleteValueWithKeyAsync(STORAGE_KEY, secureStoreOptions);
  }
}
