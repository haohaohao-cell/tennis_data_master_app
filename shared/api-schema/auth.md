# Auth API Schema

Base path: `/api/v1/auth`

## Phone Verification Code

`POST /verification-codes`

Request:

```json
{
  "phone": "13800000000"
}
```

Response:

```json
{
  "success": true,
  "expires_at": "2026-07-29T12:00:00Z",
  "dev_code": "000000"
}
```

`dev_code` is returned only in development.

## Phone Login

`POST /phone-login`

Request:

```json
{
  "phone": "13800000000",
  "code": "000000",
  "device": {
    "device_name": "iPhone",
    "platform": "ios"
  }
}
```

Response:

```json
{
  "access_token": "opaque-access-token",
  "refresh_token": "opaque-refresh-token",
  "token_type": "bearer",
  "access_expires_at": "2026-07-29T12:00:00Z",
  "refresh_expires_at": "2026-08-28T12:00:00Z",
  "user": {
    "user_id": "uuid",
    "nickname": "Tennis User 0000",
    "avatar_path": null,
    "phone": "13800000000",
    "email": null,
    "status": "active",
    "profile_completed": false,
    "playing_hand": "right",
    "is_coach": false,
    "coach_status": null,
    "created_at": "2026-07-29 12:00:00",
    "updated_at": "2026-07-29 12:00:00"
  }
}
```

## Current User

`GET /me`

Header:

```text
Authorization: Bearer <access_token>
```

Response:

```json
{
  "user": {
    "user_id": "uuid",
    "nickname": "Tennis User 0000",
    "avatar_path": null,
    "phone": "13800000000",
    "email": null,
    "status": "active",
    "profile_completed": false,
    "playing_hand": "right",
    "is_coach": false,
    "coach_status": null,
    "created_at": "2026-07-29 12:00:00",
    "updated_at": "2026-07-29 12:00:00"
  }
}
```

## Refresh

`POST /refresh`

Request:

```json
{
  "refresh_token": "opaque-refresh-token",
  "device": {
    "device_name": "iPhone",
    "platform": "ios"
  }
}
```

Response shape is the same as phone login. Refresh rotates both access and refresh tokens.

## Logout

`POST /logout`

Header:

```text
Authorization: Bearer <access_token>
```

Response:

```json
{
  "success": true
}
```

## Errors

Error response:

```json
{
  "detail": {
    "code": "INVALID_VERIFICATION_CODE",
    "message": "Verification code is incorrect."
  }
}
```

Common codes: `INVALID_PHONE`, `INVALID_VERIFICATION_CODE`, `MISSING_ACCESS_TOKEN`, `INVALID_ACCESS_TOKEN`, `INVALID_REFRESH_TOKEN`, `USER_DISABLED`.
