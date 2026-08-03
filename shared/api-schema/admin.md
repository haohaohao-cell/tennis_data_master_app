# Admin API

Base path: `/api/v1/admin`

Admin API runs inside the existing backend service. It does not use a separate backend process. Every endpoint requires an existing user access token and an active `admin_users` authorization row for that user.

Authorization:

```http
Authorization: Bearer <access_token>
```

If the token belongs to a normal non-admin user, the API returns `403` with `ADMIN_PERMISSION_REQUIRED`.

## Admin Login

```text
POST /auth/login
```

Request:

```json
{
  "username": "li",
  "password": "0000",
  "device": {
    "device_name": "Admin Web",
    "platform": "web"
  }
}
```

Response:

```json
{
  "access_token": "opaque-token",
  "refresh_token": "opaque-refresh-token",
  "token_type": "bearer",
  "access_expires_at": "2026-07-29T12:00:00Z",
  "refresh_expires_at": "2026-08-28T12:00:00Z",
  "admin_role": "owner",
  "user": {
    "user_id": "uuid",
    "nickname": "li"
  }
}
```

This endpoint is for local/admin web sign-in only. Passwords are stored as PBKDF2 hashes in `admin_credentials`; plaintext test passwords must not be stored in the database.

## Pagination

List responses use the same envelope:

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 20
}
```

Common query parameters:

| Parameter | Type | Description |
| --- | --- | --- |
| `page` | integer | 1-based page number |
| `page_size` | integer | 1-100 |
| `q` | string | Search keyword |

## Users

```text
GET    /users
POST   /users
GET    /users/{user_id}
PATCH  /users/{user_id}
DELETE /users/{user_id}
```

List filters:

| Parameter | Description |
| --- | --- |
| `status` | `active`、`disabled`、`deleted` |
| `is_coach` | boolean |
| `coach_status` | `pending`、`active`、`disabled`、`rejected` |

Create/update fields follow the `users` table contract: `nickname`, `avatar_path`, `phone`, `email`, `status`, `profile_completed`, `playing_hand`, `is_coach`, `coach_status`, `coach_verified_at`.

Delete is a soft delete: `users.status = deleted` and `users.deleted_at` is set. An admin cannot disable or delete their own user account through this API.

## Coach Applications

```text
GET  /coach-applications
GET  /coach-applications/{coach_application_id}
POST /coach-applications/{coach_application_id}/approve
POST /coach-applications/{coach_application_id}/reject
POST /coaches/{user_id}/suspend
POST /coaches/{user_id}/restore
POST /coaches/{user_id}/revoke
```

List filters:

| Parameter | Description |
| --- | --- |
| `status` | `pending`、`approved`、`rejected`、`canceled` |
| `application_type` | `certified`、`non_professional` |

Reject request:

```json
{
  "rejection_reason": "资质证明信息不完整"
}
```

Suspend/restore/revoke request:

```json
{
  "reason": "资料复核中"
}
```

Review rules:

- Only `pending` applications can be approved or rejected.
- Reject requires `rejection_reason`.
- Approving an application creates or updates the user's `coach_profiles` row and updates compatibility fields on `users`.
- Suspending or revoking a coach identity disables coach capabilities while preserving the ordinary user account.
- Coach identity is an extension of the existing user account, not a separate account system.

## Tennis Activities

```text
GET    /tennis-activities
POST   /tennis-activities
GET    /tennis-activities/{tennis_activity_id}
PATCH  /tennis-activities/{tennis_activity_id}
DELETE /tennis-activities/{tennis_activity_id}
```

List filters:

| Parameter | Description |
| --- | --- |
| `activity_type` | Activity enum |
| `default_visibility` | Activity visibility enum |
| `analysis_summary_status` | `pending`、`processing`、`completed`、`failed` |
| `owner_user_id` | Owner user id |
| `include_deleted` | Include soft-deleted activities |

Create/update fields follow the `tennis_activities` table contract, including automatic-location fields such as `location_source`, `location_latitude`, `location_longitude`, `location_accuracy_m`, `location_captured_at`, `location_country_code`, `location_region`, `location_city`, `location_district`, `location_address_label`, and `location_coordinate_system`.

Delete is a soft delete: `tennis_activities.deleted_at` is set.

## Videos

```text
GET    /videos
POST   /videos
GET    /videos/{video_id}
PATCH  /videos/{video_id}
DELETE /videos/{video_id}
```

List filters:

| Parameter | Description |
| --- | --- |
| `analysis_status` | `uploaded`、`queued`、`processing`、`completed`、`failed`、`canceled` |
| `visibility` | Video visibility enum |
| `owner_user_id` | Owner user id |
| `include_deleted` | Include soft-deleted videos |

Create/update fields follow the `videos` metadata table contract. Admin API manages video metadata and analysis state only; real binary upload remains a separate feature.

Delete is a soft delete: `videos.deleted_at` is set.

## Posts

```text
GET    /posts
POST   /posts
GET    /posts/{social_post_id}
PATCH  /posts/{social_post_id}
DELETE /posts/{social_post_id}
```

List filters:

| Parameter | Description |
| --- | --- |
| `status` | `draft`、`published`、`hidden`、`deleted` |
| `visibility` | Post visibility enum |
| `author_user_id` | Author user id |
| `review_status` | `pending`、`approved`、`rejected` |

Create/update fields follow the `social_posts` table contract, including `review_status`, reviewer fields, and coarse `location_scope` / `location_region` / `location_city`.

When `status` is changed to `published`, backend fills `published_at` if it is empty. Delete is a soft delete: `social_posts.status = deleted` and `social_posts.deleted_at` is set.
