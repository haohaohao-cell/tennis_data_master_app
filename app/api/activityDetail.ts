import { API_BASE_URL, apiRequest } from "@/api/client";
import type {
  ActivityType,
  ActivityVisibility,
  AnalysisStatus,
  TennisActivityRecord,
  UploadStatus,
  VideoRecord,
} from "@/api/uploads";

export type ActivityDetailLesson = {
  lesson_id: string;
  coach_user_id: string;
  title: string | null;
  lesson_type: string;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  location_name: string | null;
  court_surface: string | null;
  training_content: string | null;
  coach_summary: string | null;
  homework: string | null;
  next_focus: string | null;
  viewer_role: "coach" | "student" | null;
};

export type ActivityDetailPermissions = {
  can_view: boolean;
  can_manage: boolean;
  can_play_videos: boolean;
};

export type ActivityDetailSummary = {
  video_count: number;
  uploaded_video_count: number;
  upload_status: UploadStatus | "mixed";
  analysis_status: AnalysisStatus | "mixed" | "none";
};

export type ActivityDetailResponse = {
  activity: TennisActivityRecord & {
    activity_type: ActivityType;
    default_visibility: ActivityVisibility;
  };
  lesson: ActivityDetailLesson | null;
  permissions: ActivityDetailPermissions;
  summary: ActivityDetailSummary;
  videos: VideoRecord[];
};

export function getActivityDetail(accessToken: string, tennisActivityId: string) {
  return apiRequest<ActivityDetailResponse>(`/api/v1/tennis-activities/${tennisActivityId}`, {
    accessToken,
  });
}

export function resolveMediaUrl(path: string | null | undefined) {
  if (!path) {
    return null;
  }
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}
