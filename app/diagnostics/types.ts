export type DiagnosticMode = "modal" | "remote" | "silent" | "off";

export type DiagnosticSource =
  | "API_ERROR"
  | "JS_ERROR"
  | "REACT_ERROR"
  | "UNHANDLED_PROMISE";

export type DiagnosticContext = {
  apiBaseUrl?: string;
  body?: unknown;
  componentStack?: string | null;
  extra?: Record<string, unknown>;
  method?: string;
  path?: string;
  requestId?: string | null;
  responseBody?: string | null;
  route?: string | null;
  source: DiagnosticSource;
  status?: number | null;
  url?: string;
};

export type DiagnosticEvent = {
  context: DiagnosticContext;
  copiedText: string;
  id: string;
  message: string;
  name: string;
  route: string | null;
  source: DiagnosticSource;
  stack: string | null;
  timestamp: string;
};
