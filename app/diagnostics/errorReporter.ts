import Constants from "expo-constants";
import { Platform } from "react-native";

import type { DiagnosticContext, DiagnosticEvent, DiagnosticMode } from "@/diagnostics/types";

type DiagnosticListener = (event: DiagnosticEvent) => void;

const listeners = new Set<DiagnosticListener>();
let currentRoute: string | null = null;
let installedGlobalHandlers = false;
let originalGlobalHandler: ((error: unknown, isFatal?: boolean) => void) | null = null;

const SENSITIVE_KEY_PATTERN = /(authorization|token|password|verification|code|secret)/i;

function diagnosticsMode(): DiagnosticMode {
  const fromEnv = process.env.EXPO_PUBLIC_DIAGNOSTICS_MODE;
  if (fromEnv === "modal" || fromEnv === "remote" || fromEnv === "silent" || fromEnv === "off") {
    return fromEnv;
  }
  return __DEV__ ? "modal" : "remote";
}

function appVersion() {
  const expoConstants = Constants as unknown as {
    expoConfig?: { version?: string };
    manifest?: { version?: string };
  };
  return expoConstants.expoConfig?.version ?? expoConstants.manifest?.version ?? "unknown";
}

function createDiagnosticId() {
  return `diag-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function redactText(value: string) {
  return value
    .replace(/Bearer\s+[A-Za-z0-9._~+/-]+=*/gi, "Bearer [REDACTED]")
    .replace(/("?(?:access_token|refresh_token|accessToken|refreshToken|authorization|password|code)"?\s*[:=]\s*)"[^"]+"/gi, "$1\"[REDACTED]\"")
    .replace(/\b1[3-9]\d{9}\b/g, (match) => `${match.slice(0, 3)}****${match.slice(-4)}`)
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, (match) => {
      const [name, domain] = match.split("@");
      return `${name.slice(0, 2)}***@${domain}`;
    });
}

function sanitizeValue(value: unknown, depth = 0): unknown {
  if (depth > 4) {
    return "[MaxDepth]";
  }
  if (value === null || value === undefined) {
    return value;
  }
  if (typeof value === "string") {
    return redactText(value);
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeValue(item, depth + 1));
  }
  if (typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [
        key,
        SENSITIVE_KEY_PATTERN.test(key) ? "[REDACTED]" : sanitizeValue(item, depth + 1),
      ]),
    );
  }
  return String(value);
}

function safeJson(value: unknown) {
  try {
    return JSON.stringify(sanitizeValue(value), null, 2);
  } catch {
    return String(value);
  }
}

function errorParts(error: unknown) {
  if (error instanceof Error) {
    return {
      message: error.message,
      name: error.name,
      stack: error.stack ?? null,
    };
  }
  return {
    message: typeof error === "string" ? error : safeJson(error),
    name: "NonError",
    stack: null,
  };
}

function formatDiagnostic(event: Omit<DiagnosticEvent, "copiedText">) {
  const lines = [
    "Tennis Data Master Diagnostic",
    `diagnostic_id: ${event.id}`,
    `timestamp: ${event.timestamp}`,
    `source: ${event.source}`,
    `route: ${event.route ?? "unknown"}`,
    `platform: ${Platform.OS}`,
    `app_version: ${appVersion()}`,
    "",
    "[Error]",
    `name: ${event.name}`,
    `message: ${redactText(event.message)}`,
  ];

  if (event.context.method || event.context.path || event.context.status !== undefined) {
    lines.push(
      "",
      "[Request]",
      `method: ${event.context.method ?? "unknown"}`,
      `path: ${event.context.path ?? "unknown"}`,
      `url: ${event.context.url ?? "unknown"}`,
      `status: ${event.context.status ?? "unknown"}`,
      `request_id: ${event.context.requestId ?? "missing"}`,
      `api_base_url: ${event.context.apiBaseUrl ?? "unknown"}`,
    );
  }

  if (event.context.responseBody) {
    lines.push("", "[Response Body]", redactText(event.context.responseBody));
  }
  if (event.context.componentStack) {
    lines.push("", "[Component Stack]", redactText(event.context.componentStack));
  }
  if (event.stack) {
    lines.push("", "[Stack]", redactText(event.stack));
  }
  if (event.context.body !== undefined || event.context.extra) {
    lines.push(
      "",
      "[Context]",
      safeJson({
        body: event.context.body,
        extra: event.context.extra,
      }),
    );
  }

  return lines.join("\n");
}

export function setCurrentDiagnosticRoute(route: string | null) {
  currentRoute = route;
}

export function subscribeDiagnostics(listener: DiagnosticListener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function captureError(error: unknown, context: DiagnosticContext) {
  const mode = diagnosticsMode();
  if (mode === "off") {
    return null;
  }

  const parts = errorParts(error);
  const baseEvent = {
    context: {
      ...context,
      route: context.route ?? currentRoute,
    },
    id: createDiagnosticId(),
    message: parts.message,
    name: parts.name,
    route: context.route ?? currentRoute,
    source: context.source,
    stack: parts.stack,
    timestamp: new Date().toISOString(),
  };
  const event: DiagnosticEvent = {
    ...baseEvent,
    copiedText: formatDiagnostic(baseEvent),
  };

  if (mode === "modal") {
    listeners.forEach((listener) => listener(event));
  }
  if (mode === "remote") {
    console.warn(event.copiedText);
  }
  return event;
}

export function installGlobalDiagnosticsHandlers() {
  if (installedGlobalHandlers) {
    return;
  }
  installedGlobalHandlers = true;

  const globalWithErrorUtils = globalThis as typeof globalThis & {
    ErrorUtils?: {
      getGlobalHandler?: () => (error: unknown, isFatal?: boolean) => void;
      setGlobalHandler?: (handler: (error: unknown, isFatal?: boolean) => void) => void;
    };
  };

  originalGlobalHandler = globalWithErrorUtils.ErrorUtils?.getGlobalHandler?.() ?? null;
  globalWithErrorUtils.ErrorUtils?.setGlobalHandler?.((error, isFatal) => {
    captureError(error, {
      extra: { isFatal: Boolean(isFatal) },
      source: "JS_ERROR",
    });
    originalGlobalHandler?.(error, isFatal);
  });

  if (typeof globalThis.addEventListener === "function") {
    globalThis.addEventListener("unhandledrejection", (event) => {
      const reason = (event as { reason?: unknown }).reason;
      captureError(reason, { source: "UNHANDLED_PROMISE" });
    });
  }
}
