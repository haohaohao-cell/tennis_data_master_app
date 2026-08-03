import { API_BASE_URL, ApiError, apiRequest } from "@/api/client";
import type { Relationship } from "@/api/social";
import type { CurrentUserResponse } from "@/auth/types";

export type AvatarUploadableFile = {
  mimeType?: string | null;
  name?: string | null;
  uri: string;
};

export type UserSearchSummary = {
  avatar_path: string | null;
  coach_status: string | null;
  is_coach: boolean;
  nickname: string;
  user_id: string;
};

export type UserSearchItem = {
  is_self: boolean;
  match_type: "user_id" | "nickname";
  relationship: Relationship;
  user: UserSearchSummary;
};

export type UserSearchResponse = {
  items: UserSearchItem[];
  page: number;
  page_size: number;
  query: string;
};

const AVATAR_MIME_BY_EXTENSION: Record<string, string> = {
  gif: "image/gif",
  heic: "image/heic",
  heif: "image/heif",
  jpeg: "image/jpeg",
  jpg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
};
const AVATAR_EXTENSION_BY_MIME: Record<string, string> = {
  "image/gif": ".gif",
  "image/heic": ".heic",
  "image/heif": ".heif",
  "image/jpeg": ".jpg",
  "image/jpg": ".jpg",
  "image/png": ".png",
  "image/webp": ".webp",
};

function decodeFilenameSegment(value: string) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function filenameFromUri(uri: string) {
  const leaf = uri.replace(/\\/g, "/").split("/").pop();
  if (!leaf) {
    return "";
  }
  return decodeFilenameSegment(leaf.split("?", 1)[0].split("#", 1)[0]);
}

function normalizeMimeType(value?: string | null) {
  return (value ?? "").split(";", 1)[0].trim().toLowerCase();
}

function extensionFromName(name: string) {
  const match = name.match(/\.([a-z0-9]+)$/i);
  return match ? `.${match[1].toLowerCase()}` : "";
}

function stripExtension(name: string) {
  return name.replace(/\.[^/.]+$/, "");
}

function normalizeAvatarMimeType(mimeType?: string | null, fileName?: string | null) {
  const normalizedMimeType = normalizeMimeType(mimeType);
  if (normalizedMimeType in AVATAR_EXTENSION_BY_MIME) {
    return normalizedMimeType === "image/jpg" ? "image/jpeg" : normalizedMimeType;
  }

  const extension = extensionFromName(fileName ?? "");
  if (extension) {
    return AVATAR_MIME_BY_EXTENSION[extension.slice(1)] ?? "image/jpeg";
  }

  return "image/jpeg";
}

function normalizeAvatarFileName(file: AvatarUploadableFile) {
  const candidate = (file.name?.trim() || filenameFromUri(file.uri) || `avatar-${Date.now()}`).replace(/[\\/]/g, "-");
  const extension = extensionFromName(candidate);
  const baseName = extension ? stripExtension(candidate) : candidate;
  const mimeType = normalizeAvatarMimeType(file.mimeType, candidate);
  const normalizedExtension = extension && AVATAR_MIME_BY_EXTENSION[extension.slice(1)]
    ? extension
    : AVATAR_EXTENSION_BY_MIME[mimeType] ?? ".jpg";

  return `${baseName}${normalizedExtension === ".jpeg" ? ".jpg" : normalizedExtension}`;
}

function parseUploadError(status: number, responseText: string): ApiError {
  try {
    const payload = JSON.parse(responseText) as {
      detail?: { code?: string; message?: string } | string;
    };
    if (typeof payload.detail === "object" && payload.detail) {
      return new ApiError(
        status,
        payload.detail.code ?? "AVATAR_UPLOAD_FAILED",
        payload.detail.message ?? "Avatar upload failed.",
      );
    }
    if (typeof payload.detail === "string") {
      return new ApiError(status, "AVATAR_UPLOAD_FAILED", payload.detail);
    }
  } catch {
    // Fall through to the generic message below.
  }

  return new ApiError(status, "AVATAR_UPLOAD_FAILED", "Avatar upload failed.");
}

export function uploadAvatarFile({
  accessToken,
  file,
  onProgress,
}: {
  accessToken: string;
  file: AvatarUploadableFile;
  onProgress?: (progress: number) => void;
}) {
  return new Promise<CurrentUserResponse>((resolve, reject) => {
    const formData = new FormData();
    const name = normalizeAvatarFileName(file);
    formData.append("file", {
      name,
      type: normalizeAvatarMimeType(file.mimeType, name),
      uri: file.uri,
    } as unknown as Blob);

    const request = new XMLHttpRequest();
    request.open("POST", `${API_BASE_URL}/api/v1/users/me/avatar`);
    request.setRequestHeader("Accept", "application/json");
    request.setRequestHeader("Authorization", `Bearer ${accessToken}`);

    request.upload.onprogress = (event) => {
      if (!event.lengthComputable) {
        return;
      }
      onProgress?.(Math.min(1, Math.max(0, event.loaded / event.total)));
    };

    request.onerror = () => {
      reject(new ApiError(0, "NETWORK_AVATAR_UPLOAD_FAILED", "Network error while uploading avatar."));
    };

    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        onProgress?.(1);
        resolve(JSON.parse(request.responseText) as CurrentUserResponse);
        return;
      }
      reject(parseUploadError(request.status, request.responseText));
    };

    request.send(formData);
  });
}

export function searchUsers(
  accessToken: string,
  query: string,
  options: { page?: number; pageSize?: number } = {},
) {
  const params = new URLSearchParams({
    page: String(options.page ?? 1),
    page_size: String(options.pageSize ?? 20),
    q: query.trim(),
  });
  return apiRequest<UserSearchResponse>(`/api/v1/users/search?${params.toString()}`, {
    accessToken,
  });
}
