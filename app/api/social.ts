import { apiRequest } from "@/api/client";

export type SocialStats = {
  follower_count: number;
  following_count: number;
  friend_count: number;
  user_id: string;
};

export type Relationship = {
  is_followed_by: boolean;
  is_following: boolean;
  is_friend: boolean;
  target_user_id: string;
  user_id: string;
};

export type FollowActionResponse = {
  relationship: Relationship;
  success: boolean;
};

export function getSocialStats(userId: string) {
  return apiRequest<SocialStats>(`/api/v1/social/users/${userId}/stats`);
}

export function getRelationship(accessToken: string, userId: string) {
  return apiRequest<Relationship>(`/api/v1/social/users/${userId}/relationship`, {
    accessToken,
  });
}

export function followUser(accessToken: string, userId: string) {
  return apiRequest<FollowActionResponse>(`/api/v1/social/follows/${userId}`, {
    accessToken,
    body: { source: "author_profile" },
    method: "POST",
  });
}

export function unfollowUser(accessToken: string, userId: string) {
  return apiRequest<FollowActionResponse>(`/api/v1/social/follows/${userId}`, {
    accessToken,
    method: "DELETE",
  });
}

export type SocialUserSummary = {
  user_id: string;
  nickname: string;
  avatar_path: string | null;
  is_coach: boolean;
  coach_status: string | null;
};

export type FollowListItem = {
  user: SocialUserSummary;
  is_friend: boolean;
};

export type FollowListKind = "followers" | "following" | "friends";

export type FollowListResponse = {
  items: FollowListItem[];
  page: number;
  page_size: number;
};

export function getFollowList(
  kind: FollowListKind,
  userId: string,
  options: { page?: number; pageSize?: number } = {},
) {
  const params = new URLSearchParams({
    page: String(options.page ?? 1),
    page_size: String(options.pageSize ?? 20),
  });
  return apiRequest<FollowListResponse>(
    `/api/v1/social/users/${userId}/${kind}?${params.toString()}`,
  );
}
