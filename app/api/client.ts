import Constants from "expo-constants";

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

function resolveApiBaseUrl(): string {
  const expoConfig = Constants.expoConfig as
    | { extra?: { network?: { public?: { apiBaseUrl?: string } } } }
    | null
    | undefined;
  const configuredUrl = expoConfig?.extra?.network?.public?.apiBaseUrl?.trim().replace(/\/+$/, "");
  const apiBaseUrl = configuredUrl?.endsWith("/api/v1")
    ? configuredUrl.slice(0, -"/api/v1".length)
    : configuredUrl;
  if (!apiBaseUrl) {
    throw new Error(
      "Network configuration is unavailable. Copy config/network.example.json to config/network.json and restart Expo.",
    );
  }
  return apiBaseUrl;
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
    const isAuthExpiredError = response.status === 401 || response.status === 403;
    if (shouldCaptureDiagnostics && !isAuthExpiredError) {
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

export async function apiUpload<T>(
  path: string,
  accessToken: string,
  file: Blob | { uri: string; name: string; type: string },
  filename = "image",
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const form = new FormData();
  form.append("file", file as Blob, filename);
  let response: Response;
  try {
    response = await fetch(url, {
      body: form,
      headers: { Accept: "application/json", Authorization: `Bearer ${accessToken}` },
      method: "POST",
    });
  } catch (error) {
    throw new ApiError(0, "NETWORK_ERROR", error instanceof Error ? error.message : "Network request failed.", {
      method: "POST",
      path,
      url,
    });
  }
  if (!response.ok) {
    throw await parseError(response, { method: "POST", path, url });
  }
  return (await response.json()) as T;
}
