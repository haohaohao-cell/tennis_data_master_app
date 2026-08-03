# Users API Schema

Base path: `/api/v1/users`

## Update Current User Profile

`PATCH /me`

Header:

```text
Authorization: Bearer <access_token>
```

Request:

```json
{
  "nickname": "Court Builder",
  "playing_hand": "left"
}
```

Fields:

- `nickname`: optional string, 1-50 characters after trimming.
- `playing_hand`: optional, one of `right`, `left`, `unknown`.
- `avatar_path`: optional string/null. Normal clients should set this through the avatar upload endpoint below so it points at a backend-managed public file path.

Response:

```json
{
  "user": {
    "user_id": "uuid",
    "nickname": "Court Builder",
    "avatar_path": null,
    "phone": "13800000000",
    "email": null,
    "status": "active",
    "profile_completed": true,
    "playing_hand": "left",
    "is_coach": false,
    "coach_status": null,
    "created_at": "2026-07-29 12:00:00",
    "updated_at": "2026-07-29 12:10:00"
  }
}
```

Saving profile details marks `profile_completed` as `true`.

## Upload Current User Avatar

`POST /me/avatar`

Header:

```text
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
```

Form fields:

| Field | Type | Required |
| --- | --- | --- |
| `file` | image file | yes |

Accepted image formats are JPEG, PNG, WebP, GIF, HEIC, and HEIF. The first local backend version stores files under `/storage/avatars/{user_id}/...`, updates `users.avatar_path`, and returns the refreshed current user. Uploading only the avatar does not by itself mark `profile_completed` as `true`; saving profile details still controls that flag.

Response:

```json
{
  "user": {
    "user_id": "uuid",
    "nickname": "Court Builder",
    "avatar_path": "/storage/avatars/uuid/generated.jpg",
    "phone": "13800000000",
    "email": null,
    "status": "active",
    "profile_completed": true,
    "playing_hand": "left",
    "is_coach": false,
    "coach_status": null,
    "created_at": "2026-07-29 12:00:00",
    "updated_at": "2026-07-29 12:12:00"
  }
}
```

Uploading a new managed avatar replaces the user's previous managed avatar file after the database update succeeds.

## Search Users

`GET /search?q={query}&page=1&page_size=20`

Header:

```text
Authorization: Bearer <access_token>
```

Rules:

- Search is available only to logged-in users.
- `q` must be 2-50 characters after trimming.
- First version matches full user ID, user ID prefix, and nickname contains.
- Phone and email are not searchable in the first version and are never returned in search results.
- Deleted or disabled users are excluded.
- Users blocked in either direction are excluded.
- Users with `show_profile_to_strangers = false` are hidden from unrelated strangers, but remain searchable by themselves and existing follow relationships.

Response:

```json
{
  "items": [
    {
      "user": {
        "user_id": "uuid",
        "nickname": "Bob Serve Partner",
        "avatar_path": "/storage/avatars/uuid/avatar.jpg",
        "is_coach": false,
        "coach_status": null
      },
      "relationship": {
        "user_id": "viewer-uuid",
        "target_user_id": "uuid",
        "is_following": true,
        "is_followed_by": false,
        "is_friend": false
      },
      "is_self": false,
      "match_type": "nickname"
    }
  ],
  "page": 1,
  "page_size": 20,
  "query": "Serve"
}
```

## Current User Coach Identity

`GET /me/coach-identity`

Header:

```text
Authorization: Bearer <access_token>
```

Response:

```json
{
  "status": "pending_review",
  "label": "申请审核中",
  "is_coach": false,
  "coach_type": "certified",
  "application": {
    "coach_application_id": "uuid",
    "applicant_user_id": "uuid",
    "application_type": "certified",
    "status": "pending",
    "display_name": "Court Builder",
    "certification_file_path": "/storage/coach-applications/cert.pdf",
    "verification_video_path": null,
    "rejection_reason": null
  },
  "profile": null,
  "rejection_reason": null,
  "capabilities": {
    "coach_homepage": false,
    "course_management": false,
    "student_management": false,
    "video_review": false,
    "service_publishing": false,
    "student_consultation": false
  }
}
```

Identity statuses:

- `normal_user`
- `pending_review`
- `certified_coach`
- `non_professional_coach`
- `review_rejected`
- `coach_suspended`
- `coach_revoked`

`certified_coach` has full coach capabilities. `non_professional_coach` has partial capabilities: service publishing, video review, and student consultation.

## Submit Coach Application

`POST /me/coach-applications`

Header:

```text
Authorization: Bearer <access_token>
```

Certified coach request:

```json
{
  "application_type": "certified",
  "display_name": "Court Builder",
  "real_name": "Li Coach",
  "phone": "13800000000",
  "city": "Shanghai",
  "specialties": "serve, baseline",
  "coaching_experience": "3 years assistant coaching.",
  "certification_title": "中国网球协会教练员证书",
  "certification_file_path": "/storage/coach-applications/cert.jpg",
  "note": "Optional note."
}
```

Non-professional coach request:

```json
{
  "application_type": "non_professional",
  "display_name": "Court Builder",
  "city": "Shanghai",
  "specialties": "beginner practice partner",
  "coaching_experience": "Long-term amateur training.",
  "verification_video_path": "/storage/coach-applications/demo.mp4"
}
```

Rules:

- `application_type` is `certified` or `non_professional`.
- Certified coach applications require `certification_title` and `certification_file_path`.
- Certified coach `certification_title` should come from: `中国网球协会教练员证书`, `ITF 相关认证`, `PTR / USPTA / RPT 等国际认证`, `社会体育指导员证书`, `体育专业学历或教师证明`, `俱乐部任职证明`, `其他`.
- Certified coach `certification_file_path` stores the uploaded qualification proof image path, URL, or first-version image data URI.
- Non-professional coach applications require `verification_video_path`.
- A user can have only one `pending` application at a time.
- Rejected applications remain in history; the user can submit a new application.
