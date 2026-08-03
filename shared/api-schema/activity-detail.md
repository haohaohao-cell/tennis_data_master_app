# Tennis Activity Detail API Schema

User-facing activity detail endpoints live under `/api/v1` and require a normal Bearer access token.

## Get Activity Detail

```text
GET /tennis-activities/{tennis_activity_id}
```

Returns one viewable tennis activity, the videos visible to the current user, optional lesson context, and UI-ready status summary. Uploaded videos include `thumbnail_path` for list and preview UI.

Visibility rules:

- The activity owner can view and manage the activity and all of its videos.
- A lesson coach can view lesson-linked videos whose effective visibility is `lesson_coach`, `lesson_participants`, or `public`.
- A lesson student can view their own lesson-linked videos and videos whose effective visibility is `lesson_participants` or `public`.
- For video rows with `visibility = inherit`, effective visibility comes from `tennis_activities.default_visibility`.
- Unauthorized or deleted activities return `404` to avoid exposing private activity existence.
- Activity `location` always includes the coarse city/district fields that the current user can view. Exact fields (`latitude`, `longitude`, `accuracy_m`, `captured_at`, `address_label`, `coordinate_system`) are returned only to the activity owner; non-owner lesson viewers receive `null` for those exact fields.
- Activities created from "record match" or "record training" can have zero videos. In that case `summary.video_count = 0`, `summary.uploaded_video_count = 0`, `summary.analysis_status = "none"`, and `videos = []`.

Response:

```json
{
  "activity": {
    "tennis_activity_id": "uuid",
    "owner_user_id": "uuid",
    "lesson_id": "uuid-or-null",
    "title": "Student Serve Practice",
    "activity_type": "lesson_practice",
    "default_visibility": "lesson_coach",
    "started_at": "2026-07-30T10:00:00Z",
    "ended_at": null,
    "location_name": "北京市 海淀区",
    "location": {
      "source": "device_gps",
      "latitude": 39.9929,
      "longitude": 116.3109,
      "accuracy_m": 16,
      "captured_at": "2026-07-30T10:00:00Z",
      "country_code": "CN",
      "region": "北京市",
      "city": "北京市",
      "district": "海淀区",
      "address_label": "北京市海淀区",
      "coordinate_system": "wgs84"
    },
    "court_surface": "hard",
    "opponent_user_id": null,
    "opponent_name": null,
    "note": null,
    "analysis_summary_status": "pending",
    "created_at": "2026-07-30T10:00:00Z",
    "updated_at": "2026-07-30T10:00:00Z"
  },
  "lesson": {
    "lesson_id": "uuid",
    "coach_user_id": "uuid",
    "title": "Serve rhythm lesson",
    "lesson_type": "private",
    "status": "completed",
    "started_at": "2026-07-30T10:00:00Z",
    "ended_at": null,
    "location_name": "Court 8",
    "court_surface": "hard",
    "training_content": "Serve toss and first-step recovery",
    "coach_summary": null,
    "homework": "Upload two serve clips",
    "next_focus": "Return stance",
    "viewer_role": "student"
  },
  "permissions": {
    "can_view": true,
    "can_manage": true,
    "can_play_videos": true
  },
  "summary": {
    "video_count": 1,
    "uploaded_video_count": 1,
    "upload_status": "uploaded",
    "analysis_status": "queued"
  },
  "videos": [
    {
      "video_id": "uuid",
      "tennis_activity_id": "uuid",
      "owner_user_id": "uuid",
      "uploader_user_id": "uuid",
      "filename": "generated.mp4",
      "original_filename": "serve-practice.mp4",
      "video_path": "/storage/videos/<activity_id>/generated.mp4",
      "thumbnail_path": "/storage/videos/thumbnails/<video_id>.jpg",
      "mime_type": "video/mp4",
      "file_size_bytes": 1048576,
      "file_hash": "sha256-hex",
      "video_duration_ms": null,
      "visibility": "inherit",
      "upload_status": "uploaded",
      "analysis_status": "queued",
      "uploaded_at": "2026-07-30T10:01:00Z",
      "created_at": "2026-07-30T10:00:00Z",
      "updated_at": "2026-07-30T10:01:00Z"
    }
  ]
}
```
