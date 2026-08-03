import Constants from "expo-constants";
import { Platform } from "react-native";

import { captureError } from "@/diagnostics/errorReporter";

type RequestOptions = {
  accessToken?: string | null;
  body?: unknown;
  captureDiagnostics?: boolean;
  method?: "GET" | "POST" | "PATCH" | "DELETE";
};

type ApiErrorDetail = {
  code?: string;
  message?: string;
};

export class ApiError extends Error {
  code: string;
  method?: string;
  path?: string;
  requestId?: string | null;
  responseBody?: string | null;
  status: number;
  url?: string;

  constructor(
    status: number,
    code: string,
    message: string,
    details: {
      method?: string;
      path?: string;
      requestId?: string | null;
      responseBody?: string | null;
      url?: string;
    } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.method = details.method;
    this.path = details.path;
    this.requestId = details.requestId;
    this.responseBody = details.responseBody;
    this.status = status;
    this.url = details.url;
  }
}

function getExpoHostUri(): string | null {
  const expoConstants = Constants as unknown as {
    expoConfig?: { hostUri?: string };
    manifest?: { debuggerHost?: string; hostUri?: string };
  };

  return (
    expoConstants.expoConfig?.hostUri ??
    expoConstants.manifest?.hostUri ??
    expoConstants.manifest?.debuggerHost ??
    null
  );
}

function resolveApiBaseUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_API_BASE_URL;
  if (fromEnv) {
    return fromEnv.replace(/\/$/, "");
  }

  const hostUri = getExpoHostUri();
  const host = hostUri?.split(":")[0];
  if (host && host !== "localhost" && host !== "127.0.0.1") {
    return `http://${host}:8000`;
  }

  if (Platform.OS === "android") {
    return "http://10.0.2.2:8000";
  }

  return "http://localhost:8000";
}

export const API_BASE_URL = resolveApiBaseUrl();

function parseJsonPayload(value: string): { detail?: ApiErrorDetail | string } | null {
  try {
    return JSON.parse(value) as { detail?: ApiErrorDetail | string };
  } catch {
    return null;
  }
}

async function parseError(
  response: Response,
  context: { method: string; path: string; url: string },
): Promise<ApiError> {
  const responseBody = await response.text();
  const requestId = response.headers.get("x-request-id");
  const payload = parseJsonPayload(responseBody);
  if (payload && typeof payload.detail === "object" && payload.detail) {
    return new ApiError(
      response.status,
      payload.detail.code ?? "API_ERROR",
      payload.detail.message ?? "Request failed.",
      {
        ...context,
        requestId,
        responseBody,
      },
    );
  }
  if (payload && typeof payload.detail === "string") {
    return new ApiError(response.status, "API_ERROR", payload.detail, {
      ...context,
      requestId,
      responseBody,
    });
  }

  return new ApiError(response.status, "API_ERROR", "Request failed.", {
    ...context,
    requestId,
    responseBody,
  });
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const url = `${API_BASE_URL}${path}`;
  const shouldCaptureDiagnostics = options.captureDiagnostics !== false;
  const headers: Record<string, string> = {
    Accept: "application/json",
  };

  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  if (options.accessToken) {
    headers.Authorization = `Bearer ${options.accessToken}`;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      headers,
      method,
    });
  } catch (fetchError) {
    const apiError = new ApiError(0, "NETWORK_ERROR", fetchError instanceof Error ? fetchError.message : "Network request failed.", {
      method,
      path,
      url,
    });
    if (shouldCaptureDiagnostics) {
      captureError(apiError, {
        apiBaseUrl: API_BASE_URL,
        body: options.body,
        method,
        path,
        source: "API_ERROR",
        status: 0,
        url,
      });
    }
    throw apiError;
  }

  if (!response.ok) {
    const apiError = await parseError(response, { method, path, url });
    if (shouldCaptureDiagnostics) {
      captureError(apiError, {
        apiBaseUrl: API_BASE_URL,
        body: options.body,
        method,
        path,
        requestId: apiError.requestId,
        responseBody: apiError.responseBody,
        source: "API_ERROR",
        status: response.status,
        url,
      });
    }
    throw apiError;
  }

  if (response.status === 204) {
    return undefined as T;
  }

  try {
    return (await response.json()) as T;
  } catch (parseResponseError) {
    if (shouldCaptureDiagnostics) {
      captureError(parseResponseError, {
        apiBaseUrl: API_BASE_URL,
        method,
        path,
        requestId: response.headers.get("x-request-id"),
        source: "API_ERROR",
        status: response.status,
        url,
      });
    }
    throw parseResponseError;
  }
}
