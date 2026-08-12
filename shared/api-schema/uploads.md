# Uploads API Schema

User-facing upload endpoints live under `/api/v1` and require a normal Bearer access token. The file transfer endpoint is shared by Tennis Activity uploads and draft Post video uploads.

Authorization:

```http
Authorization: Bearer <access_token>
```

## My Upload Lessons

```text
GET /lessons/mine
```

Returns lessons that the current user can bind to an upload, either as lesson coach or lesson student.

Response:

```json
{
  "items": [
    {
      "lesson_id": "uuid",
      "coach_user_id": "uuid",
      "title": "Serve lesson",
      "lesson_type": "private",
      "status": "scheduled",
      "started_at": "2026-07-30T10:00:00Z",
      "ended_at": null,
      "location_name": "Court 1",
      "role": "student"
    }
  ]
}
```

## Create Activity Record

```text
POST /tennis-activities
```

Creates one `tennis_activities` record without creating video rows. This endpoint is used by the App's "record match" and "record training" flows when the user wants to save an activity even if no video is available yet.

Request:

```json
{
  "title": "Singles match",
  "lesson_id": null,
  "activity_type": "match",
  "default_visibility": "private",
  "started_at": "2026-08-02T10:00:00Z",
  "ended_at": null,
  "location": {
    "source": "device_gps",
    "latitude": 31.2304,
    "longitude": 121.4737,
    "accuracy_m": 12,
    "captured_at": "2026-08-02T10:00:00Z",
    "country_code": "CN",
    "region": "上海市",
    "city": "上海市",
    "district": "黄浦区",
    "address_label": "上海市黄浦区",
    "coordinate_system": "wgs84"
  },
  "court_surface": "hard",
  "opponent_user_id": null,
  "opponent_name": "Alex",
  "note": "6-4 practice match"
}
```

Rules:

- The current user becomes `owner_user_id`.
- `lesson_practice` requires `lesson_id`.
- `coach_demo` requires an active coach identity; when linked to a lesson, the current user must be that lesson's coach.
- Lesson visibility values require `lesson_id`.
- `opponent_user_id` cannot equal the owner user.
- `location` is submitted by the App from video metadata or foreground phone location. For video upload flows, the App first tries to read the selected media asset's embedded location and submits `source = video_metadata` when available. Otherwise it prefers the foreground in-memory phone-location cache and calls `POST /locations/resolve` to fill province/city/district. If neither the video file nor the phone can provide latitude/longitude, submit `source = unavailable`; there is no IP/network-location fallback. When backend boundary data is available, administrative-area resolution returns a strict match or nearest-area approximation. If resolver dependencies or boundary data are unavailable, preserve latitude/longitude and submit province/city/district as `null`. `location_name` remains as a compatibility/coarse display field generated from city and district when available.

Response:

```json
{
  "tennis_activity_id": "uuid",
  "owner_user_id": "uuid",
  "lesson_id": null,
  "title": "Singles match",
  "activity_type": "match",
  "default_visibility": "private",
  "started_at": "2026-08-02T10:00:00Z",
  "ended_at": null,
  "location_name": "上海市 黄浦区",
  "location": {
    "source": "device_gps",
    "latitude": 31.2304,
    "longitude": 121.4737,
    "accuracy_m": 12,
    "captured_at": "2026-08-02T10:00:00Z",
    "country_code": "CN",
    "region": "上海市",
    "city": "上海市",
    "district": "黄浦区",
    "address_label": "上海市黄浦区",
    "coordinate_system": "wgs84"
  },
  "court_surface": "hard",
  "opponent_user_id": null,
  "opponent_name": "Alex",
  "note": "6-4 practice match",
  "analysis_summary_status": null,
  "created_at": "2026-08-02T10:05:00Z",
  "updated_at": "2026-08-02T10:05:00Z"
}
```

## Create Upload Intent

```text
POST /tennis-activities/upload-intents
```

Creates one `tennis_activities` record and one pending `videos` record per selected local video. The raw video files are uploaded in later requests.

Request:

```json
{
  "title": "Course practice upload",
  "lesson_id": "uuid-or-null",
  "activity_type": "lesson_practice",
  "default_visibility": "lesson_coach",
  "started_at": "2026-08-02T10:00:00Z",
  "court_surface": "hard",
  "location": {
    "source": "device_gps",
    "latitude": 39.9042,
    "longitude": 116.4074,
    "accuracy_m": 18,
    "captured_at": "2026-08-02T10:00:00Z",
    "country_code": "CN",
    "region": "北京市",
    "city": "北京市",
    "district": "东城区",
    "address_label": "北京市东城区",
    "coordinate_system": "wgs84"
  },
  "opponent_user_id": null,
  "opponent_name": null,
  "note": "Forehand practice",
  "videos": [
    {
      "original_filename": "forehand.mp4",
      "mime_type": "video/mp4",
      "file_size_bytes": 1048576,
      "visibility": "inherit"
    }
  ]
}
```

Rules:

- One request creates exactly one activity and one or more videos.
- `lesson_practice` requires `lesson_id`.
- `coach_demo` requires an active coach identity; when linked to a lesson, the current user must be that lesson's coach.
- `lesson_coach` and `lesson_participants` visibility require `lesson_id`.
- `videos[].file_size_bytes` is the client-reported selected asset size at intent creation time. It is advisory; after the file upload, the backend stores the actual received byte size.
- `location` follows the same automatic-location contract as `POST /tennis-activities`.

Response:

```json
{
  "activity": {
    "tennis_activity_id": "uuid",
    "owner_user_id": "uuid",
    "lesson_id": "uuid-or-null",
    "title": "Course practice upload",
    "activity_type": "lesson_practice",
    "default_visibility": "lesson_coach",
    "location_name": "北京市 东城区",
    "location": {
      "source": "device_gps",
      "latitude": 39.9042,
      "longitude": 116.4074,
      "accuracy_m": 18,
      "captured_at": "2026-08-02T10:00:00Z",
      "country_code": "CN",
      "region": "北京市",
      "city": "北京市",
      "district": "东城区",
      "address_label": "北京市东城区",
      "coordinate_system": "wgs84"
    },
    "opponent_user_id": null,
    "opponent_name": null,
    "analysis_summary_status": "pending",
    "created_at": "2026-07-30T10:00:00Z",
    "updated_at": "2026-07-30T10:00:00Z"
  },
  "videos": [
    {
      "video_id": "uuid",
      "tennis_activity_id": "uuid",
      "owner_user_id": "uuid",
      "uploader_user_id": "uuid",
      "filename": "generated.mp4",
      "original_filename": "forehand.mp4",
      "video_path": "/storage/videos/<activity_id>/generated.mp4",
      "mime_type": "video/mp4",
      "file_size_bytes": 1048576,
      "visibility": "inherit",
      "upload_status": "pending",
      "analysis_status": "uploaded"
    }
  ]
}
```

## Activity Detail

```text
GET /tennis-activities/{tennis_activity_id}
```

Returns the current user's view of an activity detail page: the activity, visible videos, optional lesson context, permissions, and aggregate status summary. See `shared/api-schema/activity-detail.md` for the full response contract and lesson visibility rules.

## Delete Activity

```text
DELETE /tennis-activities/{tennis_activity_id}
```

Deletes an Activity owned by the current user. Non-owners and already deleted Activities receive `404`.

The database record is soft-deleted. Videos that are not referenced by an active Post are also soft-deleted and their locally managed video and thumbnail files are removed. Videos still used by an active Post are retained so deleting an Activity cannot break an existing dynamic.

Response:

```json
{
  "success": true,
  "id": "uuid"
}
```

## Upload Video File

```text
POST /videos/{video_id}/file
Content-Type: multipart/form-data
```

Form fields:

| Field | Type | Required |
| --- | --- | --- |
| `file` | video file | yes |

Accepted filename suffixes are `mp4`, `mov`, `m4v`, `webm`, `mkv`, and `avi`. The endpoint also accepts common iOS MOV transport content types such as `video/quicktime`, `application/quicktime`, and `application/x-quicktime`.

Response:

```json
{
  "video": {
    "video_id": "uuid",
    "upload_status": "uploaded",
    "uploaded_at": "2026-07-30T10:01:00Z",
    "file_size_bytes": 1048576,
    "file_hash": "sha256-hex",
    "analysis_status": "uploaded"
  }
}
```

`file_size_bytes` in this response is the actual number of bytes received and stored by the backend. Videos with `tennis_activity_id = null` can be uploaded through this endpoint only when they are referenced by a draft Post owned by the current user.

## Complete Upload

```text
POST /tennis-activities/{tennis_activity_id}/complete-upload
```

All videos in the activity must have `upload_status = uploaded`. The endpoint moves uploaded videos to `analysis_status = queued`.

Response:

```json
{
  "activity": {},
  "videos": [],
  "queued_count": 1
}
```

## Cancel Upload

```text
POST /tennis-activities/{tennis_activity_id}/cancel-upload
```

Cancels a draft upload activity before it has been submitted to analysis. Uploaded local files for that draft are removed from local development storage.

Response:

```json
{
  "success": true,
  "activity": {},
  "videos": []
}
```

## Upload Status

`videos.upload_status` is separate from `videos.analysis_status`.

| Status | Meaning |
| --- | --- |
| `pending` | Video record exists; file has not been received. |
| `uploading` | File upload is in progress. |
| `uploaded` | Original file is stored and ready for analysis submission. |
| `failed` | File upload failed and can be retried. |
| `canceled` | Upload draft was canceled. |
