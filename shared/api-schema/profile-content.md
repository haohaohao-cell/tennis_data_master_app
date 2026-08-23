# Profile Content API Schema

Current-user profile content endpoints live under `/api/v1/me` and require a normal Bearer access token.

Authorization:

```http
Authorization: Bearer <access_token>
```

## Profile Content

```text
GET /profile-content
```

Returns the current user's profile tab content for the mobile "My" page.

Response:

```json
{
  "stats": {
    "posts": 1,
    "matches": 0,
    "training": 1,
    "courses": 0
  },
  "posts": [
    {
      "social_post_id": "uuid",
      "source_tennis_activity_id": "uuid-or-null",
      "title": "Post title",
      "content": "Post body",
      "visibility": "private",
      "status": "draft",
      "published_at": null,
      "created_at": "2026-07-30T10:00:00Z",
      "updated_at": "2026-07-30T10:00:00Z",
      "media_count": 0,
      "first_media_type": null,
      "first_image_path": null,
      "first_video_path": null,
      "first_video_thumbnail_path": null
    }
  ],
  "matches": [],
  "training": [
    {
      "tennis_activity_id": "uuid",
      "owner_user_id": "uuid",
      "lesson_id": null,
      "title": "Video upload",
      "activity_type": "other",
      "default_visibility": "private",
      "started_at": null,
      "ended_at": null,
      "location_name": null,
      "location": {
        "source": "unavailable",
        "latitude": null,
        "longitude": null,
        "accuracy_m": null,
        "captured_at": null,
        "country_code": null,
        "region": null,
        "city": null,
        "district": null,
        "address_label": null,
        "coordinate_system": null
      },
      "note": null,
      "analysis_summary_status": "pending",
      "created_at": "2026-07-30T10:00:00Z",
      "updated_at": "2026-07-30T10:00:00Z",
      "video_count": 1,
      "uploaded_video_count": 1,
      "upload_status": "uploaded",
      "analysis_status": "queued",
      "first_video": {
        "video_id": "uuid",
        "original_filename": "training.mp4",
        "video_path": "/storage/videos/<activity_id>/<video_id>.mp4",
        "thumbnail_path": "/storage/videos/thumbnails/<video_id>.jpg",
        "mime_type": "video/mp4",
        "file_size_bytes": 1048576,
        "upload_status": "uploaded",
        "analysis_status": "queued",
        "uploaded_at": "2026-07-30T10:01:00Z",
        "created_at": "2026-07-30T10:00:00Z"
      }
    }
  ],
  "courses": [
    {
      "lesson_id": "uuid",
      "coach_user_id": "uuid",
      "title": "Serve lesson",
      "lesson_type": "private",
      "status": "scheduled",
      "started_at": "2026-07-30T10:00:00Z",
      "ended_at": null,
      "location_name": "Court 1",
      "training_content": null,
      "coach_summary": null,
      "homework": null,
      "next_focus": null,
      "role": "student",
      "activity_count": 1,
      "video_count": 1,
      "updated_at": "2026-07-30T10:00:00Z"
    }
  ]
}
```

Tab rules:

- `posts`: `social_posts.author_user_id = current_user`, excluding deleted records.
- `matches`: owned `tennis_activities` where `activity_type = match`.
- `training`: owned `tennis_activities` where `activity_type <> match`; no-video training records are included immediately, and uploaded video activities are included as soon as the upload is completed.
- `courses`: lessons where the current user is either `lessons.coach_user_id` or an active `lesson_students.student_user_id`.
- Post and Activity previews should use `first_image_path`, `first_video_thumbnail_path`, or `first_video.thumbnail_path`; uploaded videos are expected to have a thumbnail path.
- Activity previews include `location` for the current user. Exact location fields are available because this endpoint only returns the current user's own activity records.

Activity status aggregation:

- `upload_status` is the single video upload status if all videos share the same status; otherwise `mixed`.
- `analysis_status` is the single video analysis status if all videos share the same status; otherwise `mixed`; activities with no videos use `none`.

## Personal Post Collections

The mobile "My" page loads Post collections separately when the corresponding tab is opened. Both endpoints require a normal Bearer access token.

```text
GET /favorite-posts
GET /liked-posts
```

Query parameters:

| Name | Required | Description |
| --- | --- | --- |
| `cursor` | No | Opaque cursor returned by the previous response. |
| `limit` | No | Page size, `1..50`. Default: `20`. |

Response:

```json
{
  "collection": "favorites",
  "items": [
    {
      "post": {},
      "author": {},
      "media": [],
      "videos": [],
      "stats": {},
      "viewer_state": {
        "is_liked": false,
        "is_favorited": true
      }
    }
  ],
  "next_cursor": "opaque-or-null",
  "has_more": false
}
```

`/liked-posts` returns `"collection": "likes"` and orders items by the current user's like time. `/favorite-posts` orders items by the current user's favorite time.

Collection results only include published, approved Posts that the current user can still view. Disabled/deleted authors, active block relationships, and Posts actively hidden by the current user are excluded. The collection endpoints return Post detail cards so the mobile UI can reuse the same thumbnail, author, stats, and viewer-state fields as the home feed. Canceling a like or favorite removes the item from the next collection response.
