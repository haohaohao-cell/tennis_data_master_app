export const DEFAULT_ADMIN_SETTINGS = {
  apiBaseUrl: "http://localhost:8000/api/v1",
  adminToken: "",
  mockFallback: false,
};

const STORAGE_KEY = "tennis_admin_settings";

export function loadSettings() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return { ...DEFAULT_ADMIN_SETTINGS };
    }

    return { ...DEFAULT_ADMIN_SETTINGS, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_ADMIN_SETTINGS };
  }
}

export function saveSettings(settings) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

function normalizeBaseUrl(baseUrl) {
  return String(baseUrl || DEFAULT_ADMIN_SETTINGS.apiBaseUrl).replace(/\/+$/, "");
}

function buildUrl(baseUrl, endpoint, params = {}) {
  const url = new URL(`${normalizeBaseUrl(baseUrl)}${endpoint}`);

  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "" || value === "all") {
      return;
    }

    url.searchParams.set(key, String(value));
  });

  return url;
}

function extractItems(payload, resource) {
  if (Array.isArray(payload)) {
    return { items: payload, total: payload.length };
  }

  const keys = ["items", "data", "results", ...(resource.listKeys || [])];
  const listKey = keys.find((key) => Array.isArray(payload?.[key]));

  if (!listKey) {
    return { items: [], total: 0 };
  }

  const items = payload[listKey];
  const total = payload.total ?? payload.total_count ?? payload.count ?? items.length;
  return { items, total: Number(total) || items.length };
}

export class AdminApiClient {
  constructor(settings) {
    this.settings = settings;
  }

  async request(endpoint, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("accept", "application/json");

    if (options.body !== undefined) {
      headers.set("content-type", "application/json");
    }

    if (this.settings.adminToken) {
      headers.set("authorization", `Bearer ${this.settings.adminToken}`);
    }

    const response = await fetch(endpoint, { ...options, headers });
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : await response.text();

    if (!response.ok) {
      const message = typeof payload === "string" ? payload : payload.detail || payload.message;
      throw new Error(message || `HTTP ${response.status}`);
    }

    return payload;
  }

  async list(resource, params) {
    const url = buildUrl(this.settings.apiBaseUrl, resource.endpoint, params);
    const payload = await this.request(url.toString());
    return extractItems(payload, resource);
  }

  async login(username, password) {
    const url = buildUrl(this.settings.apiBaseUrl, "/admin/auth/login");
    return this.request(url.toString(), {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  }

  async create(resource, payload) {
    const url = buildUrl(this.settings.apiBaseUrl, resource.endpoint);
    return this.request(url.toString(), {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async get(resource, id) {
    const url = buildUrl(this.settings.apiBaseUrl, `${resource.endpoint}/${encodeURIComponent(id)}`);
    return this.request(url.toString());
  }

  async patch(resource, item, patch) {
    const id = resource.getId(item);
    const url = buildUrl(this.settings.apiBaseUrl, `${resource.endpoint}/${encodeURIComponent(id)}`);
    return this.request(url.toString(), {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  }

  async delete(resource, item) {
    const id = resource.getId(item);
    const url = buildUrl(this.settings.apiBaseUrl, `${resource.endpoint}/${encodeURIComponent(id)}`);
    return this.request(url.toString(), { method: "DELETE" });
  }

  async postEndpoint(endpoint, payload = {}) {
    const url = buildUrl(this.settings.apiBaseUrl, endpoint);
    return this.request(url.toString(), {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }
}
