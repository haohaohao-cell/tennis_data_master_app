# Posts API Schema

User-facing Post endpoints live under `/api/v1`. Mutating endpoints require a normal Bearer access token. The recommended feed can be read without login; personalized ordering is applied when a token is present.

Authorization:

```http
Authorization: Bearer <access_token>
```

## Common Shapes

`PostDetailResponse` returns:

- `post`: `social_posts` record, including `review_status`, `location_scope`, `location_region`, and `location_city`.
- `author`: `user_id`, `nickname`, and `avatar_path`.
- `media`: ordered `post_media` rows.
- `videos`: referenced video rows, including `thumbnail_path` when the video has been uploaded.
- `stats`: `social_post_stats` counters, or `null` for legacy rows before backfill.
- `viewer_state`: `is_liked` and `is_favorited` for the current authenticated viewer, or `null` when unauthenticated.

`GET /posts/{social_post_id}` is the canonical Post detail endpoint. It accepts an optional Bearer token and returns the Post when the current viewer can read it. The author can read their own non-deleted Posts, including drafts, private Posts, pending review Posts, and rejected Posts. Other authenticated viewers can read only published, approved Posts that pass visibility, author status, and block checks. Anonymous viewers can read only published, approved public Posts.

User-facing clients should not expose exact location. Post location is coarse only:

- `location_scope = none`: no public location.
- `location_scope = region`: `location_region` is set.
- `location_scope = city`: `location_city` is set; `location_region` may also be set for region fallback.
- For video publish flows, the App first tries to read the selected video asset's embedded location; nearby flows and non-video fallbacks prefer the foreground in-memory phone-location cache and call `POST /locations/resolve`. If neither the video file nor the phone can provide latitude/longitude, no location is submitted; there is no IP/network-location fallback. When backend boundary data is available, the resolver returns a strict match or nearest-area approximation. Only the resolved region/city is submitted to Post APIs. Exact coordinates are not stored on `social_posts`.

## Create Post Upload Intent

```text
POST /posts/upload-intents
```

Creates one draft `social_posts` record, one independent `videos` record with `tennis_activity_id = null`, one `post_media` row with `media_type = video`, and one `social_post_stats` row. The raw file is uploaded later through the shared video upload endpoint.

Request:

```json
{
  "title": "Serve rhythm",
  "content": "First serve finally felt cleaner.",
  "visibility": "public",
  "location_scope": "city",
  "location_region": "Beijing",
  "location_city": "Beijing",
  "videos": [
    {
      "original_filename": "serve-post.mp4",
      "mime_type": "video/mp4",
      "file_size_bytes": 1048576,
      "video_duration_ms": 42000
    }
  ]
}
```

Rules:

- First version supports one media item per Post.
- Direct-upload Post videos must provide `video_duration_ms`.
- Post videos cannot exceed `600000` ms by default.
- Direct-upload Post videos do not create or belong to a Tennis Activity.
- `specified_users` visibility is reserved for a later target-list implementation and is rejected by user-facing Post endpoints.
- Location fields are optional and store only coarse city or region values.

## Upload Post Video File

```text
POST /videos/{video_id}/file
Content-Type: multipart/form-data
```

The existing upload endpoint is reused. A standalone Post video can be uploaded only by the draft Post author while the Post is still `draft`. The same accepted video suffix and QuickTime/MOV MIME rules from `shared/api-schema/uploads.md` apply here. Upload completion generates and stores `videos.thumbnail_path`; clients should use it for feed, profile grid, and Post detail previews.

## Publish Post

```text
POST /posts/{social_post_id}/publish
```

Publishes an owned draft or hidden Post after all video media have `upload_status = uploaded`. The backend fills `published_at` when it is empty and ensures a `social_post_stats` row exists.

Response shape is `PostDetailResponse`.

## Create Post From Activity Clip

```text
POST /posts
```

Creates a Post that references an existing uploaded Tennis Activity video clip. This endpoint is ready for the future clip editor; the current App UI does not expose clipping yet.

Request:

```json
{
  "content": "Best rally from today's activity.",
  "visibility": "public",
  "location_scope": "region",
  "location_region": "Beijing",
  "status": "published",
  "media": [
    {
      "video_id": "uuid",
      "clip_start_ms": 12000,
      "clip_end_ms": 36000
    }
  ]
}
```

Rules:

- The source video must belong to an activity owned by the current user.
- The source video must have `upload_status = uploaded`.
- Clip duration cannot exceed the Post video duration limit.
- The Post stores `source_tennis_activity_id` from the source video activity.
- The source video is not copied, and its original visibility is not changed.

## Home Feed

```text
GET /posts/feed
```

Query parameters:

| Name | Required | Description |
| --- | --- | --- |
| `feed_type` | No | `recommended`, `following`, or `nearby`. Default: `recommended`. |
| `cursor` | No | Opaque stable cursor from the previous response. |
| `limit` | No | Page size, `1..50`. Default: `20`. |
| `city` | Nearby only | Coarse city selected by the user or device permission flow. |
| `region` | Nearby only | Coarse region for fallback. |

Response:

```json
{
  "feed_type": "recommended",
  "items": [
    {
      "post": {},
      "author": {},
      "media": [],
      "videos": [],
      "stats": {
        "social_post_id": "uuid",
        "like_count": 0,
        "comment_count": 0,
        "favorite_count": 0,
        "share_count": 0,
        "view_count": 0,
        "updated_at": "2026-07-31T10:00:00Z"
      },
      "feed_source": "recommended",
      "sort_strategy": "view_bucket_published_at_desc_v1"
    }
  ],
  "next_cursor": "opaque",
  "has_more": true,
  "strategy_version": "view_bucket_published_at_desc_v1",
  "fallback_mode": null
}
```

Shared filters:

- Excludes deleted, hidden, non-published, and non-approved Posts.
- Excludes disabled or deleted authors.
- Excludes Posts the current user cannot view.
- Excludes either side of an active block relation.
- Excludes Posts hidden by the current user.
- Keeps viewed Posts, but orders them after unviewed Posts for the current user.

Feed-specific rules:

- `recommended`: public approved Posts only. Sorting is deterministic and stable: unviewed Posts first, then viewed Posts, each group ordered by publish time descending.
- `following`: Posts by authors the current user actively follows, ordered with unviewed Posts first and publish time descending inside each group. Login is required.
- `nearby`: public approved Posts with `location_scope != none`, matched by city and/or region, ordered with unviewed Posts first and publish time descending inside each group. Exact coordinates are not returned.

## Feed State

```text
GET /posts/feed/state
```

Returns supported feed types, the current recommended strategy version, and nearby location privacy copy.

## Report Views

```text
POST /posts/views/bulk
```

Batch report actually viewed Posts. Clients should call this only after a Post enters the visible area, starts playback, or opens detail; the feed response itself must not mark items as viewed.

Request:

```json
{
  "items": [
    {
      "social_post_id": "uuid",
      "source": "home_feed",
      "dwell_time_ms": 1200
    }
  ]
}
```

The backend upserts `user_post_views` on `(user_id, social_post_id)`, increments view counts, and returns accepted and ignored IDs. Repeated batch submissions are safe and do not create duplicate view rows. Clients should treat this report as best-effort telemetry: temporary failures such as `DATABASE_BUSY` can be retried silently and must not block feed entry.

## Reserved Hide Post

```text
POST   /posts/{social_post_id}/hide
DELETE /posts/{social_post_id}/hide
```

Hide creates or reactivates a `user_post_hides` row so the Post no longer appears in the user's feeds. Delete cancels the hide row. The current mobile App home feed does not expose this action in the Post card UI; the endpoint remains reserved for future preference controls or moderation workflows.

## Like, Favorite, Comment, Share

```text
POST   /posts/{social_post_id}/like
DELETE /posts/{social_post_id}/like
POST   /posts/{social_post_id}/favorite
DELETE /posts/{social_post_id}/favorite
GET    /posts/{social_post_id}/comments
POST   /posts/{social_post_id}/comments
DELETE /posts/{social_post_id}/comments/{comment_id}
POST   /posts/{social_post_id}/share
```

Rules:

- Likes are stored in `post_reactions` with `reaction_type = like`.
- Favorites are stored in `post_favorites`.
- Comments and replies are stored in `post_comments`; replies set `parent_comment_id` and `root_comment_id`.
- Shares are stored in `post_shares`; `share_target_type = conversation` also creates a `post_share` chat message.
- `social_post_stats` is updated as a display and feed-ranking cache.
- Repeated active likes and favorites are prevented by database unique indexes.
- Likes, comments, and replies generate interaction notifications when the actor is not notifying themself.

Comment create request:

```json
{
  "content": "Great rally shape.",
  "parent_comment_id": null,
  "source": "post_detail"
}
```

Share request:

```json
{
  "share_target_type": "conversation",
  "conversation_id": "uuid",
  "message_text": "Take a look at this serve.",
  "channel": "chat"
}
```

## Update, Delete, Mine, Detail

```text
PATCH  /posts/{social_post_id}
DELETE /posts/{social_post_id}
GET    /posts/mine
GET    /posts/public/{social_post_id}
GET    /posts/{social_post_id}
```

`GET /posts/{social_post_id}` returns the canonical current-viewer-readable Post detail. `GET /posts/public/{social_post_id}` is retained as a compatibility endpoint for published readable Posts; anonymous viewers can only access public Posts through it. `PATCH` supports `title`, `content`, `visibility`, `location_scope`, `location_region`, and `location_city`. `DELETE` is a soft delete; deleting a draft also cancels standalone Post videos and generated thumbnails created by that draft. `GET /posts/mine` keeps page-based pagination for the user's own management list.
