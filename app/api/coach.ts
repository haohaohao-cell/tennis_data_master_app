import { apiRequest } from "@/api/client";

export type CoachType = "certified" | "non_professional";
export type CoachApplicationStatus = "pending" | "approved" | "rejected" | "canceled";
export type CoachProfileStatus = "active" | "suspended" | "revoked";
export type CoachIdentityStatus =
  | "normal_user"
  | "pending_review"
  | "certified_coach"
  | "non_professional_coach"
  | "review_rejected"
  | "coach_suspended"
  | "coach_revoked";

export type CoachApplication = {
  coach_application_id: string;
  applicant_user_id: string;
  application_type: CoachType;
  status: CoachApplicationStatus;
  display_name: string;
  real_name: string | null;
  phone: string | null;
  city: string | null;
  specialties: string | null;
  coaching_experience: string | null;
  certification_title: string | null;
  certification_file_path: string | null;
  verification_video_path: string | null;
  note: string | null;
  reviewer_user_id: string | null;
  reviewed_at: string | null;
  rejection_reason: string | null;
  created_at: string;
  updated_at: string;
};

export type CoachProfile = {
  coach_profile_id: string;
  user_id: string;
  coach_type: CoachType;
  status: CoachProfileStatus;
  display_name: string;
  city: string | null;
  specialties: string | null;
  coaching_experience: string | null;
  certification_title: string | null;
  certification_file_path: string | null;
  verification_video_path: string | null;
  approved_application_id: string | null;
  approved_by_user_id: string | null;
  approved_at: string;
  suspended_at: string | null;
  revoked_at: string | null;
  status_reason: string | null;
  created_at: string;
  updated_at: string;
};

export type CoachCapabilities = {
  coach_homepage: boolean;
  course_management: boolean;
  student_management: boolean;
  video_review: boolean;
  service_publishing: boolean;
  student_consultation: boolean;
};

export type CoachIdentity = {
  status: CoachIdentityStatus;
  label: string;
  is_coach: boolean;
  coach_type: CoachType | null;
  application: CoachApplication | null;
  profile: CoachProfile | null;
  rejection_reason: string | null;
  capabilities: CoachCapabilities;
};

export type CoachApplicationPayload = {
  application_type: CoachType;
  display_name: string;
  real_name?: string | null;
  phone?: string | null;
  city?: string | null;
  specialties?: string | null;
  coaching_experience?: string | null;
  certification_title?: string | null;
  certification_file_path?: string | null;
  verification_video_path?: string | null;
  note?: string | null;
};

export type CoachApplicationCreateResponse = {
  application: CoachApplication;
  identity: CoachIdentity;
};

export function getCoachIdentity(accessToken: string) {
  return apiRequest<CoachIdentity>("/api/v1/users/me/coach-identity", {
    accessToken,
  });
}

export function submitCoachApplication(accessToken: string, payload: CoachApplicationPayload) {
  return apiRequest<CoachApplicationCreateResponse>("/api/v1/users/me/coach-applications", {
    accessToken,
    body: payload,
    method: "POST",
  });
}

