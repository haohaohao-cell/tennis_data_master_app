import { apiRequest } from "@/api/client";
import type {
  ActivityType,
  ActivityVisibility,
  ActivityLocation,
  AnalysisStatus,
  UploadStatus,
} from "@/api/uploads";

export type ProfileVideoSummary = {
  video_id: string;
  original_filename: string | null;
  video_path: string;
  thumbnail_path: string | null;
  mime_type: string | null;
  file_size_bytes: number | null;
  upload_status: UploadStatus;
  analysis_status: AnalysisStatus;
  uploaded_at: string | null;
  created_at: string;
};

export type ProfileActivity = {
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
  note: string | null;
  analysis_summary_status: string | null;
  created_at: string;
  updated_at: string;
  video_count: number;
  uploaded_video_count: number;
  upload_status: UploadStatus | "mixed";
  analysis_status: AnalysisStatus | "mixed" | "none";
  first_video: ProfileVideoSummary | null;
};

export type ProfilePost = {
  social_post_id: string;
  source_tennis_activity_id: string | null;
  title: string | null;
  content: string | null;
  visibility: string;
  status: string;
  published_at: string | null;
  created_at: string;
  updated_at: string;
  media_count: number;
  first_media_type: string | null;
  first_image_path: string | null;
  first_video_path: string | null;
  first_video_thumbnail_path: string | null;
};

export type ProfileLesson = {
  lesson_id: string;
  coach_user_id: string;
  title: string | null;
  lesson_type: string;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  location_name: string | null;
  training_content: string | null;
  coach_summary: string | null;
  homework: string | null;
  next_focus: string | null;
  role: "coach" | "student";
  activity_count: number;
  video_count: number;
  updated_at: string;
};

export type ProfileContent = {
  stats: {
    posts: number;
    matches: number;
    training: number;
    courses: number;
    received_like_count: number;
    friend_count: number;
    following_count: number;
    follower_count: number;
  };
  posts: ProfilePost[];
  matches: ProfileActivity[];
  training: ProfileActivity[];
  courses: ProfileLesson[];
};

export function getProfileContent(accessToken: string) {
  return apiRequest<ProfileContent>("/api/v1/me/profile-content", {
    accessToken,
  });
}
