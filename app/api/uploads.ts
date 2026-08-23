import { API_BASE_URL, ApiError, apiRequest } from "@/api/client";

export type ActivityType =
  | "casual_hit"
  | "match"
  | "serve_training"
  | "forehand_training"
  | "backhand_training"
  | "multi_ball_drill"
  | "stroke_recording"
  | "post_match_review"
  | "lesson_practice"
  | "coach_demo"
  | "other";

export type ActivityVisibility =
  | "private"
  | "friends"
  | "specified_users"
  | "lesson_coach"
  | "lesson_participants"
  | "public";

export type CourtSurface = "hard" | "clay" | "grass" | "carpet" | "unknown";
export type ActivityLocationSource = "device_gps" | "video_metadata" | "manual_legacy" | "unavailable";
export type ActivityCoordinateSystem = "wgs84" | "gcj02";
export type VideoVisibility = ActivityVisibility | "inherit";
export type UploadStatus = "pending" | "uploading" | "uploaded" | "failed" | "canceled";
export type AnalysisStatus = "uploaded" | "queued" | "processing" | "completed" | "failed" | "canceled";

export type LessonOption = {
  lesson_id: string;
  coach_user_id: string;
  title: string | null;
  lesson_type: string;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  location_name: string | null;
  role: "coach" | "student";
};

export type TennisActivityRecord = {
  tennis_activity_id: string;
  owner_user_id: string;
  lesson_id: string | null;
  title: string | null;
  activity_type: ActivityType;
  default_visibility: ActivityVisibility;
  started_at: string | null;
  ended_at: string | null;
  location_name: string | null;
  location: ActivityLocation | null;
  court_surface: CourtSurface | null;
  opponent_user_id: string | null;
  opponent_name: string | null;
  note: string | null;
  analysis_summary_status: string | null;
  created_at: string;
  updated_at: string;
};

export type ActivityLocation = {
  source: ActivityLocationSource;
  latitude: number | null;
  longitude: number | null;
  accuracy_m: number | null;
  captured_at: string | null;
  country_code: string | null;
  region: string | null;
  city: string | null;
  district: string | null;
  address_label: string | null;
  coordinate_system: ActivityCoordinateSystem | null;
};

export type ActivityLocationPayload = {
  source: ActivityLocationSource;
  latitude?: number | null;
  longitude?: number | null;
  accuracy_m?: number | null;
  captured_at?: string | null;
  country_code?: string | null;
  region?: string | null;
  city?: string | null;
  district?: string | null;
  address_label?: string | null;
  coordinate_system?: ActivityCoordinateSystem | null;
};

export type TennisActivityCreatePayload = {
  lesson_id?: string | null;
  title?: string | null;
  activity_type: ActivityType;
  default_visibility: ActivityVisibility;
  started_at?: string | null;
  ended_at?: string | null;
  location_name?: string | null;
  location?: ActivityLocationPayload | null;
  court_surface?: CourtSurface | null;
  opponent_user_id?: string | null;
  opponent_name?: string | null;
  note?: string | null;
};

export type VideoRecord = {
  video_id: string;
  tennis_activity_id: string | null;
  owner_user_id: string;
  uploader_user_id: string;
  filename: string;
  original_filename: string | null;
  video_path: string;
  thumbnail_path: string | null;
  mime_type: string | null;
  file_size_bytes: number | null;
  file_hash: string | null;
  video_duration_ms: number | null;
  video_width_px: number | null;
  video_height_px: number | null;
  visibility: VideoVisibility;
  upload_status: UploadStatus;
  upload_error_message: string | null;
  uploaded_at: string | null;
  analysis_status: AnalysisStatus;
  error_message: string | null;
  captured_at: string | null;
  created_at: string;
  updated_at: string;
};

export type UploadIntentVideo = {
  original_filename: string;
  mime_type?: string | null;
  file_size_bytes?: number | null;
  captured_at?: string | null;
  visibility?: VideoVisibility;
};

export type UploadIntentPayload = {
  title?: string | null;
  lesson_id?: string | null;
  activity_type: ActivityType;
  default_visibility: ActivityVisibility;
  started_at?: string | null;
  ended_at?: string | null;
  location_name?: string | null;
  location?: ActivityLocationPayload | null;
  court_surface?: CourtSurface | null;
  note?: string | null;
  opponent_user_id?: string | null;
  opponent_name?: string | null;
  videos: UploadIntentVideo[];
};

export type UploadIntentResponse = {
  activity: TennisActivityRecord;
  videos: VideoRecord[];
};

export type UploadCompleteResponse = UploadIntentResponse & {
  queued_count: number;
};

export type UploadCancelResponse = UploadIntentResponse & {
  success: boolean;
};

export type VideoFileUploadResponse = {
  video: VideoRecord;
};

export type UploadableFile = {
  mimeType?: string | null;
  name: string;
  uri: string;
};

const KNOWN_VIDEO_EXTENSIONS = new Set(["avi", "m4v", "mkv", "mov", "mp4", "webm"]);
const VIDEO_MIME_BY_EXTENSION: Record<string, string> = {
  avi: "video/x-msvideo",
  m4v: "video/x-m4v",
  mkv: "video/x-matroska",
  mov: "video/quicktime",
  mp4: "video/mp4",
  webm: "video/webm",
};
const VIDEO_EXTENSION_BY_MIME: Record<string, string> = {
  "application/quicktime": ".mov",
  "application/x-quicktime": ".mov",
  "video/mp4": ".mp4",
  "video/quicktime": ".mov",
  "video/webm": ".webm",
  "video/x-m4v": ".m4v",
  "video/x-matroska": ".mkv",
  "video/x-msvideo": ".avi",
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

export function normalizeVideoDurationMs(value?: number | null) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return null;
  }

  return Math.max(0, Math.round(value));
}

function extensionFromName(name: string) {
  const match = name.match(/\.([a-z0-9]+)$/i);
  return match ? `.${match[1].toLowerCase()}` : "";
}

function stripExtension(name: string) {
  return name.replace(/\.[^/.]+$/, "");
}

export function normalizeVideoMimeType(mimeType?: string | null, fileName?: string | null) {
  const normalizedMimeType = normalizeMimeType(mimeType);
  if (normalizedMimeType === "application/quicktime" || normalizedMimeType === "application/x-quicktime") {
    return "video/quicktime";
  }
  if (normalizedMimeType.startsWith("video/")) {
    return normalizedMimeType;
  }

  const extension = extensionFromName(fileName ?? "");
  if (extension) {
    return VIDEO_MIME_BY_EXTENSION[extension.slice(1)] ?? "video/mp4";
  }

  return "video/mp4";
}

export function normalizeVideoFileName({
  fallbackBase = "video",
  fileName,
  mimeType,
  uri,
}: {
  fallbackBase?: string;
  fileName?: string | null;
  mimeType?: string | null;
  uri: string;
}) {
  const candidate = (fileName?.trim() || filenameFromUri(uri) || `${fallbackBase}-${Date.now()}`).replace(/[\\/]/g, "-");
  const extension = extensionFromName(candidate);
  const baseName = extension ? stripExtension(candidate) : candidate;
  const normalizedExtension = extension && KNOWN_VIDEO_EXTENSIONS.has(extension.slice(1))
    ? extension
    : VIDEO_EXTENSION_BY_MIME[normalizeVideoMimeType(mimeType, candidate)] ?? ".mp4";

  return `${baseName}${normalizedExtension}`;
}

export function listUploadLessons(accessToken: string) {
  return apiRequest<{ items: LessonOption[] }>("/api/v1/lessons/mine", {
    accessToken,
  });
}

export function createUploadIntent(accessToken: string, payload: UploadIntentPayload) {
  return apiRequest<UploadIntentResponse>("/api/v1/tennis-activities/upload-intents", {
    accessToken,
    body: payload,
    method: "POST",
  });
}

export function createTennisActivity(accessToken: string, payload: TennisActivityCreatePayload) {
  return apiRequest<TennisActivityRecord>("/api/v1/tennis-activities", {
    accessToken,
    body: payload,
    method: "POST",
  });
}

export function completeActivityUpload(accessToken: string, tennisActivityId: string) {
  return apiRequest<UploadCompleteResponse>(
    `/api/v1/tennis-activities/${tennisActivityId}/complete-upload`,
    {
      accessToken,
      method: "POST",
    },
  );
}

export function cancelActivityUpload(accessToken: string, tennisActivityId: string) {
  return apiRequest<UploadCancelResponse>(
    `/api/v1/tennis-activities/${tennisActivityId}/cancel-upload`,
    {
      accessToken,
      method: "POST",
    },
  );
}

function parseUploadError(status: number, responseText: string): ApiError {
  try {
    const payload = JSON.parse(responseText) as {
      detail?: { code?: string; message?: string } | string;
    };
    if (typeof payload.detail === "object" && payload.detail) {
      return new ApiError(
        status,
        payload.detail.code ?? "UPLOAD_FAILED",
        payload.detail.message ?? "Upload failed.",
      );
    }
    if (typeof payload.detail === "string") {
      return new ApiError(status, "UPLOAD_FAILED", payload.detail);
    }
  } catch {
    // Fall through to the generic message below.
  }

  return new ApiError(status, "UPLOAD_FAILED", "Upload failed.");
}

export function uploadVideoFile({
  accessToken,
  file,
  onProgress,
  videoId,
}: {
  accessToken: string;
  file: UploadableFile;
  onProgress?: (progress: number) => void;
  videoId: string;
}) {
  return new Promise<VideoFileUploadResponse>((resolve, reject) => {
    const formData = new FormData();
    const name = normalizeVideoFileName({
      fileName: file.name,
      mimeType: file.mimeType,
      uri: file.uri,
    });
    formData.append("file", {
      name,
      type: normalizeVideoMimeType(file.mimeType, name),
      uri: file.uri,
    } as unknown as Blob);

    const request = new XMLHttpRequest();
    request.open("POST", `${API_BASE_URL}/api/v1/videos/${videoId}/file`);
    request.setRequestHeader("Accept", "application/json");
    request.setRequestHeader("Authorization", `Bearer ${accessToken}`);

    request.upload.onprogress = (event) => {
      if (!event.lengthComputable) {
        return;
      }
      onProgress?.(Math.min(1, Math.max(0, event.loaded / event.total)));
    };

    request.onerror = () => {
      reject(new ApiError(0, "NETWORK_UPLOAD_FAILED", "Network error while uploading video."));
    };

    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        onProgress?.(1);
        resolve(JSON.parse(request.responseText) as VideoFileUploadResponse);
        return;
      }
      reject(parseUploadError(request.status, request.responseText));
    };

    request.send(formData);
  });
}
