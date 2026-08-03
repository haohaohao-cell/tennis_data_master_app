import { apiRequest } from "@/api/client";
import { normalizeVideoDurationMs } from "@/api/uploads";
import type { VideoRecord } from "@/api/uploads";

export type PostVisibility = "private" | "friends" | "followers" | "specified_users" | "public";
export type PostStatus = "draft" | "published" | "hidden" | "deleted";
export type PostMediaType = "video" | "video_clip" | "image" | "data_card";
export type FeedType = "recommended" | "following" | "nearby";
export type PostCollectionKind = "favorites" | "likes";
export type FeedSource =
  | "recommended"
  | "following"
  | "nearby"
  | "nearby_city_fallback"
  | "nearby_region_fallback";

export type PostAuthor = {
  avatar_path: string | null;
  nickname: string;
  user_id: string;
};

export type SocialPostRecord = {
  author_user_id: string;
  content: string | null;
  created_at: string;
  deleted_at: string | null;
  published_at: string | null;
  social_post_id: string;
  source_tennis_activity_id: string | null;
  status: PostStatus;
  title: string | null;
  updated_at: string;
  visibility: PostVisibility;
  review_status: "pending" | "approved" | "rejected";
  reviewed_at: string | null;
  reviewer_user_id: string | null;
  review_reason: string | null;
  location_scope: "none" | "region" | "city";
  location_region: string | null;
  location_city: string | null;
};

export type PostMediaRecord = {
  caption: string | null;
  clip_end_ms: number | null;
  clip_start_ms: number | null;
  created_at: string;
  data_card_type: string | null;
  data_payload_json: string | null;
  deleted_at: string | null;
  image_path: string | null;
  media_type: PostMediaType;
  post_media_id: string;
  social_post_id: string;
  sort_order: number;
  updated_at: string;
  video_id: string | null;
};

export type PostDetailResponse = {
  author: PostAuthor;
  media: PostMediaRecord[];
  post: SocialPostRecord;
  stats: PostStats | null;
  videos: VideoRecord[];
  viewer_state: PostViewerState | null;
};

export type PostStats = {
  comment_count: number;
  favorite_count: number;
  like_count: number;
  share_count: number;
  social_post_id: string;
  updated_at: string;
  view_count: number;
};

export type PostViewerState = {
  is_favorited: boolean;
  is_liked: boolean;
};

export type PostLikeResponse = {
  is_liked: boolean;
  social_post_id: string;
  stats: PostStats;
  success: boolean;
};

export type PostFavoriteResponse = {
  is_favorited: boolean;
  social_post_id: string;
  stats: PostStats;
  success: boolean;
};

export type PostCommentRecord = {
  author: PostAuthor;
  author_user_id: string;
  comment_id: string;
  content: string | null;
  created_at: string;
  deleted_at: string | null;
  parent_comment_id: string | null;
  reply_count: number;
  root_comment_id: string | null;
  social_post_id: string;
  source: string | null;
  status: string;
  updated_at: string;
};

export type PostCommentListResponse = {
  items: PostCommentRecord[];
  page: number;
  page_size: number;
};

export type PostCommentCreateResponse = {
  comment: PostCommentRecord;
  stats: PostStats;
};

export type PostFeedItem = PostDetailResponse & {
  feed_source: FeedSource;
  sort_strategy: string;
};

export type PostFeedResponse = {
  feed_type: FeedType;
  fallback_mode: string | null;
  has_more: boolean;
  items: PostFeedItem[];
  next_cursor: string | null;
  strategy_version: string;
};

export type PostCollectionResponse = {
  collection: PostCollectionKind;
  has_more: boolean;
  items: PostDetailResponse[];
  next_cursor: string | null;
};

export type PostFeedState = {
  nearby_location_privacy: string;
  nearby_requires_location: boolean;
  recommended_strategy_version: string;
  supported_feed_types: FeedType[];
};

export type PostListResponse = {
  items: PostDetailResponse[];
  page: number;
  page_size: number;
};

export type PostUploadIntentPayload = {
  content?: string | null;
  location_city?: string | null;
  location_region?: string | null;
  location_scope?: "none" | "region" | "city";
  title?: string | null;
  visibility: PostVisibility;
  videos: Array<{
    caption?: string | null;
    captured_at?: string | null;
    file_size_bytes?: number | null;
    mime_type?: string | null;
    original_filename: string;
    video_duration_ms: number;
  }>;
};

export type PostUploadIntentResponse = PostDetailResponse & {
  max_video_duration_ms: number;
};

export type PostDeleteResponse = {
  id: string;
  success: boolean;
};

export type PostViewsBulkPayload = {
  items: Array<{
    dwell_time_ms?: number;
    social_post_id: string;
    source?: string;
  }>;
};

export type PostViewsBulkResponse = {
  accepted_post_ids: string[];
  ignored_post_ids: string[];
};

export function createPostUploadIntent(accessToken: string, payload: PostUploadIntentPayload) {
  const normalizedPayload: PostUploadIntentPayload = {
    ...payload,
    videos: payload.videos.map((video) => ({
      ...video,
      video_duration_ms: normalizeVideoDurationMs(video.video_duration_ms) ?? 0,
    })),
  };

  return apiRequest<PostUploadIntentResponse>("/api/v1/posts/upload-intents", {
    accessToken,
    body: normalizedPayload,
    method: "POST",
  });
}

export function publishPost(accessToken: string, socialPostId: string) {
  return apiRequest<PostDetailResponse>(`/api/v1/posts/${socialPostId}/publish`, {
    accessToken,
    method: "POST",
  });
}

export function deletePost(accessToken: string, socialPostId: string) {
  return apiRequest<PostDeleteResponse>(`/api/v1/posts/${socialPostId}`, {
    accessToken,
    method: "DELETE",
  });
}

export function listMyPosts(accessToken: string, page = 1, pageSize = 20) {
  return apiRequest<PostListResponse>(`/api/v1/posts/mine?page=${page}&page_size=${pageSize}`, {
    accessToken,
  });
}

export function getPostDetail(socialPostId: string, accessToken?: string | null) {
  return apiRequest<PostDetailResponse>(`/api/v1/posts/${socialPostId}`, {
    accessToken,
  });
}

export function getPublicPostDetail(socialPostId: string, accessToken?: string | null) {
  return apiRequest<PostDetailResponse>(`/api/v1/posts/public/${socialPostId}`, {
    accessToken,
  });
}

export async function getReadablePostDetail(socialPostId: string, accessToken?: string | null) {
  return getPostDetail(socialPostId, accessToken);
}

export function listPublicPostFeed(_page = 1, pageSize = 20) {
  return getPostFeed("recommended", { limit: pageSize });
}

export function getPostFeed(
  feedType: FeedType,
  options: {
    accessToken?: string | null;
    city?: string | null;
    cursor?: string | null;
    limit?: number;
    region?: string | null;
  } = {},
) {
  const params = new URLSearchParams({
    feed_type: feedType,
    limit: String(options.limit ?? 20),
  });
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.city) params.set("city", options.city);
  if (options.region) params.set("region", options.region);
  return apiRequest<PostFeedResponse>(`/api/v1/posts/feed?${params.toString()}`, {
    accessToken: options.accessToken,
  });
}

export function getPostFeedState() {
  return apiRequest<PostFeedState>("/api/v1/posts/feed/state");
}

export function getMyPostCollection(
  accessToken: string,
  collection: PostCollectionKind,
  options: { cursor?: string | null; limit?: number } = {},
) {
  const path = collection === "favorites" ? "favorite-posts" : "liked-posts";
  const params = new URLSearchParams({
    limit: String(options.limit ?? 20),
  });
  if (options.cursor) params.set("cursor", options.cursor);
  return apiRequest<PostCollectionResponse>(`/api/v1/me/${path}?${params.toString()}`, {
    accessToken,
  });
}

export function reportPostViews(accessToken: string, payload: PostViewsBulkPayload) {
  return apiRequest<PostViewsBulkResponse>("/api/v1/posts/views/bulk", {
    captureDiagnostics: false,
    accessToken,
    body: payload,
    method: "POST",
  });
}

export function likePost(accessToken: string, socialPostId: string, source = "post_detail") {
  return apiRequest<PostLikeResponse>(`/api/v1/posts/${socialPostId}/like`, {
    accessToken,
    body: { source },
    method: "POST",
  });
}

export function unlikePost(accessToken: string, socialPostId: string) {
  return apiRequest<PostLikeResponse>(`/api/v1/posts/${socialPostId}/like`, {
    accessToken,
    method: "DELETE",
  });
}

export function favoritePost(accessToken: string, socialPostId: string, source = "post_detail") {
  return apiRequest<PostFavoriteResponse>(`/api/v1/posts/${socialPostId}/favorite`, {
    accessToken,
    body: { source },
    method: "POST",
  });
}

export function unfavoritePost(accessToken: string, socialPostId: string) {
  return apiRequest<PostFavoriteResponse>(`/api/v1/posts/${socialPostId}/favorite`, {
    accessToken,
    method: "DELETE",
  });
}

export function listPostComments(
  socialPostId: string,
  options: { accessToken?: string | null; page?: number; pageSize?: number } = {},
) {
  const params = new URLSearchParams({
    page: String(options.page ?? 1),
    page_size: String(options.pageSize ?? 30),
  });
  return apiRequest<PostCommentListResponse>(
    `/api/v1/posts/${socialPostId}/comments?${params.toString()}`,
    { accessToken: options.accessToken },
  );
}

export function createPostComment(
  accessToken: string,
  socialPostId: string,
  content: string,
  parentCommentId: string | null = null,
) {
  return apiRequest<PostCommentCreateResponse>(`/api/v1/posts/${socialPostId}/comments`, {
    accessToken,
    body: {
      content,
      parent_comment_id: parentCommentId,
      source: "post_detail",
    },
    method: "POST",
  });
}
