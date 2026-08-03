import Constants from "expo-constants";
import { createContext, PropsWithChildren, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Platform } from "react-native";

import { ApiError, apiRequest } from "@/api/client";
import { uploadAvatarFile, type AvatarUploadableFile } from "@/api/users";
import {
  clearStoredAuthSession,
  getAuthStorageMode,
  readStoredAuthSession,
  writeStoredAuthSession,
  type AuthStorageMode,
} from "@/auth/storage";
import type {
  AuthTokensResponse,
  CurrentUserResponse,
  LogoutResponse,
  SendVerificationCodeResponse,
  StoredAuthSession,
  User,
  UserProfileUpdate,
} from "@/auth/types";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

type AuthContextValue = {
  accessToken: string | null;
  isAuthenticated: boolean;
  loginWithPhone: (phone: string, code: string) => Promise<User>;
  logout: () => Promise<void>;
  refreshLogin: () => Promise<User | null>;
  requestVerificationCode: (phone: string) => Promise<SendVerificationCodeResponse>;
  status: AuthStatus;
  storageMode: AuthStorageMode;
  uploadAvatar: (file: AvatarUploadableFile) => Promise<User>;
  updateProfile: (payload: UserProfileUpdate) => Promise<User>;
  user: User | null;
  userId: string | null;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const AUTH_FAILURE_CODES = new Set([
  "INVALID_ACCESS_TOKEN",
  "INVALID_REFRESH_TOKEN",
  "MISSING_ACCESS_TOKEN",
  "USER_DISABLED",
]);
const ACCESS_TOKEN_REFRESH_BUFFER_MS = 30 * 1000;

function toStoredSession(response: AuthTokensResponse): StoredAuthSession {
  return {
    accessExpiresAt: response.access_expires_at,
    accessToken: response.access_token,
    refreshExpiresAt: response.refresh_expires_at,
    refreshToken: response.refresh_token,
    user: response.user,
  };
}

function isExpired(isoValue: string, bufferMs = 0) {
  const expiresAt = Date.parse(isoValue);
  return Number.isFinite(expiresAt) && expiresAt <= Date.now() + bufferMs;
}

function isStoredSessionUsable(session: StoredAuthSession) {
  return Boolean(
    session.accessToken &&
      session.refreshToken &&
      session.refreshExpiresAt &&
      session.user?.user_id,
  );
}

function isAuthFailure(error: unknown) {
  if (!(error instanceof ApiError)) {
    return false;
  }
  return error.status === 401 || error.status === 403 || AUTH_FAILURE_CODES.has(error.code);
}

function devicePayload() {
  const expoConstants = Constants as unknown as {
    deviceName?: string;
  };

  return {
    device_name: expoConstants.deviceName ?? null,
    platform: Platform.OS,
  };
}

export function AuthProvider({ children }: PropsWithChildren) {
  const [session, setSession] = useState<StoredAuthSession | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const sessionRef = useRef<StoredAuthSession | null>(null);

  const persistSession = useCallback(async (nextSession: StoredAuthSession) => {
    sessionRef.current = nextSession;
    setSession(nextSession);
    setStatus("authenticated");
    await writeStoredAuthSession(nextSession);
  }, []);

  const clearSession = useCallback(async () => {
    sessionRef.current = null;
    setSession(null);
    setStatus("unauthenticated");
    await clearStoredAuthSession();
  }, []);

  const requestVerificationCode = useCallback((phone: string) => {
    return apiRequest<SendVerificationCodeResponse>("/api/v1/auth/verification-codes", {
      body: { phone },
      method: "POST",
    });
  }, []);

  const fetchSessionWithRefreshToken = useCallback(
    async (refreshToken: string) => {
      const response = await apiRequest<AuthTokensResponse>("/api/v1/auth/refresh", {
        body: {
          device: devicePayload(),
          refresh_token: refreshToken,
        },
        method: "POST",
      });
      return toStoredSession(response);
    },
    [],
  );

  const refreshWithToken = useCallback(
    async (refreshToken: string) => {
      const nextSession = await fetchSessionWithRefreshToken(refreshToken);
      await persistSession(nextSession);
      return nextSession.user;
    },
    [fetchSessionWithRefreshToken, persistSession],
  );

  const refreshLogin = useCallback(async () => {
    const currentSession = sessionRef.current;
    if (!currentSession) {
      return null;
    }
    return refreshWithToken(currentSession.refreshToken);
  }, [refreshWithToken]);

  const loginWithPhone = useCallback(
    async (phone: string, code: string) => {
      const response = await apiRequest<AuthTokensResponse>("/api/v1/auth/phone-login", {
        body: {
          code,
          device: devicePayload(),
          phone,
        },
        method: "POST",
      });
      const nextSession = toStoredSession(response);
      await persistSession(nextSession);
      return nextSession.user;
    },
    [persistSession],
  );

  const logout = useCallback(async () => {
    const currentSession = sessionRef.current;
    if (currentSession?.accessToken) {
      try {
        await apiRequest<LogoutResponse>("/api/v1/auth/logout", {
          accessToken: currentSession.accessToken,
          method: "POST",
        });
      } catch {
        // Local logout must still clear state when the server is unreachable.
      }
    }

    await clearSession();
  }, [clearSession]);

  const updateProfile = useCallback(
    async (payload: UserProfileUpdate) => {
      const currentSession = sessionRef.current;
      if (!currentSession?.accessToken) {
        throw new Error("Login is required to update profile.");
      }

      const response = await apiRequest<CurrentUserResponse>("/api/v1/users/me", {
        accessToken: currentSession.accessToken,
        body: payload,
        method: "PATCH",
      });
      const nextSession = { ...currentSession, user: response.user };
      await persistSession(nextSession);
      return response.user;
    },
    [persistSession],
  );

  const uploadAvatar = useCallback(
    async (file: AvatarUploadableFile) => {
      const currentSession = sessionRef.current;
      if (!currentSession?.accessToken) {
        throw new Error("Login is required to upload avatar.");
      }

      const response = await uploadAvatarFile({
        accessToken: currentSession.accessToken,
        file,
      });
      const nextSession = { ...currentSession, user: response.user };
      await persistSession(nextSession);
      return response.user;
    },
    [persistSession],
  );

  useEffect(() => {
    let mounted = true;

    async function restore() {
      let storedSession: StoredAuthSession | null = null;
      try {
        storedSession = await readStoredAuthSession();
      } catch {
        if (mounted) {
          await clearSession();
        }
        return;
      }

      if (!mounted) {
        return;
      }

      if (!storedSession) {
        setStatus("unauthenticated");
        return;
      }

      if (!isStoredSessionUsable(storedSession) || isExpired(storedSession.refreshExpiresAt)) {
        await clearSession();
        return;
      }

      const activateStoredSession = () => {
        sessionRef.current = storedSession;
        setSession(storedSession);
        setStatus("authenticated");
      };

      if (isExpired(storedSession.accessExpiresAt, ACCESS_TOKEN_REFRESH_BUFFER_MS)) {
        try {
          const nextSession = await fetchSessionWithRefreshToken(storedSession.refreshToken);
          if (mounted) {
            await persistSession(nextSession);
          }
        } catch (refreshError) {
          if (!mounted) {
            return;
          }
          if (isAuthFailure(refreshError)) {
            await clearSession();
            return;
          }
          activateStoredSession();
        }
        return;
      }

      activateStoredSession();

      try {
        const me = await apiRequest<CurrentUserResponse>("/api/v1/auth/me", {
          accessToken: storedSession.accessToken,
        });
        if (!mounted) {
          return;
        }
        const nextSession = { ...storedSession, user: me.user };
        await persistSession(nextSession);
      } catch (accessError) {
        if (!isAuthFailure(accessError)) {
          return;
        }

        try {
          const nextSession = await fetchSessionWithRefreshToken(storedSession.refreshToken);
          if (mounted) {
            await persistSession(nextSession);
          }
        } catch (refreshError) {
          if (mounted && isAuthFailure(refreshError)) {
            await clearSession();
          }
        }
      }
    }

    restore();

    return () => {
      mounted = false;
    };
  }, [clearSession, fetchSessionWithRefreshToken, persistSession]);

  const value = useMemo<AuthContextValue>(
    () => ({
      accessToken: session?.accessToken ?? null,
      isAuthenticated: status === "authenticated",
      loginWithPhone,
      logout,
      refreshLogin,
      requestVerificationCode,
      status,
      storageMode: getAuthStorageMode(),
      uploadAvatar,
      updateProfile,
      user: session?.user ?? null,
      userId: session?.user.user_id ?? null,
    }),
    [loginWithPhone, logout, refreshLogin, requestVerificationCode, session, status, uploadAvatar, updateProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used within AuthProvider.");
  }
  return value;
}
