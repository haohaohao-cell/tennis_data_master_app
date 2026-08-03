import * as ExpoMediaLibrary from "expo-media-library";
import * as ExpoLocation from "expo-location";
import { Platform } from "react-native";

import { apiRequest } from "@/api/client";
import type { ActivityLocation, ActivityLocationPayload } from "@/api/uploads";

export type MobileLocationStatus = "resolved" | "permission_denied" | "unavailable";

export type MobileLocationResult = {
  location: ActivityLocationPayload;
  message: string | null;
  status: MobileLocationStatus;
};

export type ActivityLocationCacheSnapshot = {
  locationResult: MobileLocationResult | null;
  refreshing: boolean;
  updatedAt: number | null;
};

export type CoarseLocation = {
  city: string;
  region: string;
};

export const ACTIVITY_LOCATION_REFRESH_INTERVAL_MS = 3 * 60 * 1000;

const ANDROID_QUICK_POSITION_TIMEOUT_MS = 4000;
const CURRENT_POSITION_TIMEOUT_MS = 10000;
const BACKEND_LOCATION_RESOLVE_TIMEOUT_MS = 15000;
const MEDIA_ASSET_INFO_TIMEOUT_MS = 2500;
const VIDEO_METADATA_LOCATION_ACCURACY_M = 200;
const LAST_KNOWN_MAX_AGE_MS = 30 * 60 * 1000;
const LAST_KNOWN_REQUIRED_ACCURACY_M = 5000;
const ANDROID_FALLBACK_LAST_KNOWN_MAX_AGE_MS = 24 * 60 * 60 * 1000;
const ANDROID_FALLBACK_LAST_KNOWN_REQUIRED_ACCURACY_M = 100000;

class LocationTimeoutError extends Error {}

type PositionResult = {
  position: ExpoLocation.LocationObject;
  usedLastKnown: boolean;
};

type ActivityLocationCacheListener = (snapshot: ActivityLocationCacheSnapshot) => void;

const activityLocationCacheListeners = new Set<ActivityLocationCacheListener>();
let cachedActivityLocationResult: MobileLocationResult | null = null;
let cachedActivityLocationUpdatedAt: number | null = null;
let activeLocationRefreshPromise: Promise<MobileLocationResult> | null = null;

function text(value: string | null | undefined) {
  const normalized = value?.trim();
  return normalized || null;
}

function compactJoin(values: Array<string | null | undefined>) {
  return values.map(text).filter(Boolean).join(" ") || null;
}

function numberOrNull(value: unknown) {
  const numberValue = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function unavailable(status: MobileLocationStatus, message: string): MobileLocationResult {
  return {
    location: {
      source: "unavailable",
    },
    message,
    status,
  };
}

export function getActivityLocationCacheSnapshot(): ActivityLocationCacheSnapshot {
  return {
    locationResult: cachedActivityLocationResult,
    refreshing: activeLocationRefreshPromise !== null,
    updatedAt: cachedActivityLocationUpdatedAt,
  };
}

export function subscribeActivityLocationCache(listener: ActivityLocationCacheListener) {
  activityLocationCacheListeners.add(listener);
  listener(getActivityLocationCacheSnapshot());
  return () => {
    activityLocationCacheListeners.delete(listener);
  };
}

function notifyActivityLocationCacheListeners() {
  const snapshot = getActivityLocationCacheSnapshot();
  activityLocationCacheListeners.forEach((listener) => listener(snapshot));
}

function setCachedActivityLocationResult(result: MobileLocationResult) {
  cachedActivityLocationResult = result;
  cachedActivityLocationUpdatedAt = Date.now();
  notifyActivityLocationCacheListeners();
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new LocationTimeoutError(message)), timeoutMs);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error: unknown) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

function positionResult(
  promise: Promise<ExpoLocation.LocationObject | null>,
  options: {
  usedLastKnown: boolean;
  },
): Promise<PositionResult | null> {
  const { usedLastKnown } = options;
  return promise
    .then((position) => (position ? { position, usedLastKnown } : null))
    .catch(() => null);
}

function firstResolvedPosition(attempts: Array<Promise<PositionResult | null>>) {
  if (!attempts.length) {
    return Promise.resolve(null);
  }

  return new Promise<PositionResult | null>((resolve) => {
    let pending = attempts.length;
    let settled = false;

    attempts.forEach((attempt) => {
      attempt.then((result) => {
        if (settled) {
          return;
        }
        if (result) {
          settled = true;
          resolve(result);
          return;
        }
        pending -= 1;
        if (pending === 0) {
          settled = true;
          resolve(null);
        }
      });
    });
  });
}

async function getPositionFromWatch({
  accuracy,
  timeoutMs,
}: {
  accuracy: ExpoLocation.Accuracy;
  timeoutMs: number;
}) {
  return new Promise<ExpoLocation.LocationObject>((resolve, reject) => {
    let settled = false;
    let subscription: { remove: () => void } | null = null;

    const timer = setTimeout(() => {
      if (settled) {
        return;
      }
      settled = true;
      subscription?.remove();
      reject(new LocationTimeoutError("position_timeout"));
    }, timeoutMs);

    ExpoLocation.watchPositionAsync(
      {
        accuracy,
        distanceInterval: 0,
        mayShowUserSettingsDialog: true,
        timeInterval: 1000,
      },
      (position) => {
        if (settled) {
          return;
        }
        settled = true;
        clearTimeout(timer);
        subscription?.remove();
        resolve(position);
      },
    )
      .then((nextSubscription) => {
        subscription = nextSubscription;
      })
      .catch((error) => {
        if (settled) {
          return;
        }
        settled = true;
        clearTimeout(timer);
        reject(error);
      });
  });
}

async function getLastKnownPosition({
  maxAge,
  requiredAccuracy,
}: {
  maxAge: number;
  requiredAccuracy: number;
}) {
  return ExpoLocation.getLastKnownPositionAsync({
    maxAge,
    requiredAccuracy,
  }).catch(() => null);
}

async function getCurrentPosition({
  accuracy,
  timeoutMs,
}: {
  accuracy: ExpoLocation.Accuracy;
  timeoutMs: number;
}) {
  return withTimeout(
    ExpoLocation.getCurrentPositionAsync({
      accuracy,
      mayShowUserSettingsDialog: true,
    }),
    timeoutMs,
    "position_timeout",
  );
}

async function getAndroidPosition() {
  void ExpoLocation.enableNetworkProviderAsync().catch(() => null);

  const quickPosition = await firstResolvedPosition([
    positionResult(
      getLastKnownPosition({
        maxAge: LAST_KNOWN_MAX_AGE_MS,
        requiredAccuracy: LAST_KNOWN_REQUIRED_ACCURACY_M,
      }),
      { usedLastKnown: true },
    ),
    positionResult(
      getCurrentPosition({
        accuracy: ExpoLocation.Accuracy.Low,
        timeoutMs: ANDROID_QUICK_POSITION_TIMEOUT_MS,
      }),
      { usedLastKnown: false },
    ),
    positionResult(
      getPositionFromWatch({
        accuracy: ExpoLocation.Accuracy.Low,
        timeoutMs: ANDROID_QUICK_POSITION_TIMEOUT_MS,
      }),
      { usedLastKnown: false },
    ),
  ]);
  if (quickPosition) {
    return quickPosition;
  }

  const olderLastKnown = await getLastKnownPosition({
    maxAge: ANDROID_FALLBACK_LAST_KNOWN_MAX_AGE_MS,
    requiredAccuracy: ANDROID_FALLBACK_LAST_KNOWN_REQUIRED_ACCURACY_M,
  });
  if (olderLastKnown) {
    return { position: olderLastKnown, usedLastKnown: true };
  }

  throw new LocationTimeoutError("position_timeout");
}

async function getDefaultPosition() {
  const position = await firstResolvedPosition([
    positionResult(
      getLastKnownPosition({
        maxAge: LAST_KNOWN_MAX_AGE_MS,
        requiredAccuracy: LAST_KNOWN_REQUIRED_ACCURACY_M,
      }),
      { usedLastKnown: true },
    ),
    positionResult(
      getCurrentPosition({
        accuracy: ExpoLocation.Accuracy.Highest,
        timeoutMs: CURRENT_POSITION_TIMEOUT_MS,
      }),
      { usedLastKnown: false },
    ),
    positionResult(
      getPositionFromWatch({
        accuracy: ExpoLocation.Accuracy.Highest,
        timeoutMs: CURRENT_POSITION_TIMEOUT_MS,
      }),
      { usedLastKnown: false },
    ),
  ]);
  if (position) {
    return position;
  }

  throw new LocationTimeoutError("position_timeout");
}

async function getPosition() {
  if (Platform.OS === "android") {
    return getAndroidPosition();
  }
  return getDefaultPosition();
}

type LocationResolveResponse = {
  resolved: boolean;
  source: "area_city_boundary" | "unavailable";
  country_code: string | null;
  region: string | null;
  city: string | null;
  district: string | null;
  address_label: string | null;
  matched_level: "province" | "city" | "district" | null;
  coordinate_system: "wgs84" | "gcj02";
  boundary_coordinate_system: "wgs84" | "gcj02" | null;
  message: string | null;
};

async function resolveAdministrativeLocation(position: ExpoLocation.LocationObject) {
  return withTimeout(
    apiRequest<LocationResolveResponse>("/api/v1/locations/resolve", {
      body: {
        coordinate_system: "wgs84",
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      },
      captureDiagnostics: false,
      method: "POST",
    }),
    BACKEND_LOCATION_RESOLVE_TIMEOUT_MS,
    "backend_location_resolve_timeout",
  ).catch(() => null);
}

async function resolveAdministrativeCoordinates({
  latitude,
  longitude,
}: {
  latitude: number;
  longitude: number;
}) {
  return withTimeout(
    apiRequest<LocationResolveResponse>("/api/v1/locations/resolve", {
      body: {
        coordinate_system: "wgs84",
        latitude,
        longitude,
      },
      captureDiagnostics: false,
      method: "POST",
    }),
    BACKEND_LOCATION_RESOLVE_TIMEOUT_MS,
    "backend_location_resolve_timeout",
  ).catch(() => null);
}

async function requestVideoAssetMetadataPermission() {
  const permission = await ExpoMediaLibrary.requestPermissionsAsync(
    false,
    Platform.OS === "android" ? ["video"] : undefined,
  ).catch(() => null);
  return Boolean(permission?.granted || permission?.accessPrivileges === "limited");
}

export async function getActivityLocationFromVideoAsset(assetId: string | null | undefined): Promise<MobileLocationResult | null> {
  if (!assetId) {
    return null;
  }

  const permissionGranted = await requestVideoAssetMetadataPermission();
  if (!permissionGranted) {
    return null;
  }

  const assetInfo = await withTimeout(
    ExpoMediaLibrary.getAssetInfoAsync(assetId, { shouldDownloadFromNetwork: false }),
    MEDIA_ASSET_INFO_TIMEOUT_MS,
    "media_asset_info_timeout",
  ).catch(() => null);
  const latitude = numberOrNull(assetInfo?.location?.latitude);
  const longitude = numberOrNull(assetInfo?.location?.longitude);
  if (latitude === null || longitude === null) {
    return null;
  }

  const resolvedLocation = await resolveAdministrativeCoordinates({ latitude, longitude });
  const city = text(resolvedLocation?.city);
  const district = text(resolvedLocation?.district);
  const region = text(resolvedLocation?.region);
  const addressLabel = text(resolvedLocation?.address_label);
  const hasCoarseAddress = Boolean(city || district || region || addressLabel);
  const capturedAt =
    typeof assetInfo?.creationTime === "number" && assetInfo.creationTime > 0
      ? new Date(assetInfo.creationTime).toISOString()
      : new Date().toISOString();

  return {
    location: {
      accuracy_m: VIDEO_METADATA_LOCATION_ACCURACY_M,
      address_label: addressLabel,
      captured_at: capturedAt,
      city,
      coordinate_system: "wgs84",
      country_code: text(resolvedLocation?.country_code) ?? (hasCoarseAddress ? "CN" : null),
      district,
      latitude,
      longitude,
      region,
      source: "video_metadata",
    },
    message: hasCoarseAddress ? "已使用视频文件自带拍摄位置。" : "已使用视频文件自带经纬度，省/市/区暂时无法解析。",
    status: "resolved",
  };
}

async function acquireCurrentActivityLocation(): Promise<MobileLocationResult> {
  try {
    const permission = await ExpoLocation.requestForegroundPermissionsAsync();
    if (!permission.granted) {
      return unavailable(
        "permission_denied",
        Platform.OS === "ios"
          ? "未授权定位，请在 iPhone 设置中开启“定位服务”和“App 使用期间定位权限”。"
          : "未授权定位，请在安卓系统设置中开启“位置权限”，并允许应用使用定位。",
      );
    }

    const servicesEnabled = await ExpoLocation.hasServicesEnabledAsync();
    if (!servicesEnabled) {
      return unavailable(
        "unavailable",
        Platform.OS === "ios"
          ? "系统定位服务未开启，请在 iPhone 设置中打开“隐私与安全性 > 定位服务”。"
          : "系统定位服务未开启，请打开安卓位置开关，并开启高精度/提高定位精确度。",
      );
    }

    const currentPosition = await getPosition();
    const { position, usedLastKnown } = currentPosition;
    const resolvedLocation = await resolveAdministrativeLocation(position);

    const city = text(resolvedLocation?.city);
    const district = text(resolvedLocation?.district);
    const region = text(resolvedLocation?.region);
    const addressLabel = text(resolvedLocation?.address_label);
    const hasCoarseAddress = Boolean(city || district || region || addressLabel);
    const fallbackMessage =
      text(resolvedLocation?.message) ??
      (usedLastKnown
        ? "已使用手机最近一次定位，省/市/区暂时无法解析。"
        : "经纬度已获取，省/市/区暂时无法解析。");

    return {
      location: {
        accuracy_m: position.coords.accuracy ?? null,
        address_label: addressLabel,
        captured_at: new Date(position.timestamp).toISOString(),
        city,
        coordinate_system: "wgs84",
        country_code: text(resolvedLocation?.country_code) ?? (hasCoarseAddress ? "CN" : null),
        district,
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        region,
        source: "device_gps",
      },
      message: hasCoarseAddress ? null : fallbackMessage,
      status: "resolved",
    };
  } catch (error) {
    if (error instanceof LocationTimeoutError) {
      return unavailable(
        "unavailable",
        Platform.OS === "android"
          ? "定位超时，请打开安卓位置服务和高精度定位，保持网络可用后重试。"
          : "定位超时，请确认定位服务已开启，移动到开阔位置后重试。",
      );
    }
    return unavailable(
      "unavailable",
      Platform.OS === "android"
        ? "暂时无法获取定位，请确认安卓位置权限、位置服务和高精度定位都已开启。"
        : "暂时无法获取定位，请确认 App 定位权限和系统定位服务都已开启。",
    );
  }
}

export async function refreshCurrentActivityLocation(): Promise<MobileLocationResult> {
  if (activeLocationRefreshPromise) {
    return activeLocationRefreshPromise;
  }

  activeLocationRefreshPromise = acquireCurrentActivityLocation()
    .then((result) => {
      setCachedActivityLocationResult(result);
      return result;
    })
    .finally(() => {
      activeLocationRefreshPromise = null;
      notifyActivityLocationCacheListeners();
    });
  notifyActivityLocationCacheListeners();
  return activeLocationRefreshPromise;
}

export async function getCurrentActivityLocation(): Promise<MobileLocationResult> {
  if (cachedActivityLocationResult) {
    if (!activeLocationRefreshPromise) {
      void refreshCurrentActivityLocation().catch(() => null);
    }
    return cachedActivityLocationResult;
  }
  return refreshCurrentActivityLocation();
}

export function formatActivityLocation(location: ActivityLocation | ActivityLocationPayload | null | undefined) {
  if (!location || location.source === "unavailable") {
    return "未记录位置";
  }
  return (
    compactJoin([location.city, location.district]) ??
    text(location.address_label) ??
    text(location.region) ??
    (location.source === "video_metadata" && location.latitude != null && location.longitude != null
      ? "已获取视频拍摄位置"
      : null) ??
    (location.latitude != null && location.longitude != null ? "已获取经纬度" : null) ??
    "已记录位置"
  );
}

export function formatActivityLocationStatus(
  result: MobileLocationResult | null | undefined,
  fallbackMessage: string,
) {
  const location = result?.location;
  if (location?.latitude != null && location.longitude != null) {
    if (location.source === "video_metadata") {
      const coordinateText = `视频拍摄位置已获取：${location.latitude.toFixed(6)}, ${location.longitude.toFixed(6)}`;
      return result?.message ? `${coordinateText}；${result.message}` : coordinateText;
    }
    const coordinateText = `经纬度已获取：${location.latitude.toFixed(6)}, ${location.longitude.toFixed(6)}`;
    return result?.message ? `${coordinateText}；${result.message}` : coordinateText;
  }
  return result?.message ?? fallbackMessage;
}

export function coarseLocationFromActivityLocation(
  location: ActivityLocation | ActivityLocationPayload | null | undefined,
): CoarseLocation {
  return {
    city: text(location?.city) ?? "",
    region: text(location?.district) ?? text(location?.region) ?? "",
  };
}
