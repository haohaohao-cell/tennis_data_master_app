export type User = {
  user_id: string;
  nickname: string;
  avatar_path: string | null;
  phone: string | null;
  email: string | null;
  status: "active" | "disabled" | "deleted";
  profile_completed: boolean;
  playing_hand: "right" | "left" | "unknown";
  is_coach: boolean;
  coach_status: "pending" | "active" | "disabled" | "rejected" | null;
  created_at: string;
  updated_at: string;
};

export type StoredAuthSession = {
  accessToken: string;
  refreshToken: string;
  accessExpiresAt: string;
  refreshExpiresAt: string;
  user: User;
};

export type SendVerificationCodeResponse = {
  success: boolean;
  expires_at: string;
  dev_code: string | null;
};

export type AuthTokensResponse = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  access_expires_at: string;
  refresh_expires_at: string;
  user: User;
};

export type CurrentUserResponse = {
  user: User;
};

export type LogoutResponse = {
  success: boolean;
};

export type UserProfileUpdate = {
  nickname?: string;
  avatar_path?: string | null;
  playing_hand?: User["playing_hand"];
};
