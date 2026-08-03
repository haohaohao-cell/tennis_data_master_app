# Social Relationship and Message API Schema

User-facing endpoints live under `/api/v1`. All endpoints require a normal Bearer access token unless noted.

## Social Relationships

```text
POST   /social/follows/{target_user_id}
DELETE /social/follows/{target_user_id}
POST   /social/blocks/{target_user_id}
DELETE /social/blocks/{target_user_id}
GET    /social/blocks
GET    /social/users/{user_id}/relationship
GET    /social/users/{user_id}/followers
GET    /social/users/{user_id}/following
GET    /social/users/{user_id}/friends
GET    /social/users/{user_id}/stats
```

Rules:

- A follow is stored in `user_follows`.
- Mutual active follows mean `is_friend = true`.
- There is no friend request table in the first version.
- Following another user creates a `follow` notification for the target user.
- Blocking another user writes `user_blocks`, cancels active follows in both directions, and blocks future follows, direct messages, and group invitations.

## Privacy and Reports

```text
GET   /privacy/settings
PATCH /privacy/settings
POST  /reports
```

Privacy fields:

```json
{
  "direct_message_policy": "friends",
  "allow_message_requests": true,
  "default_post_visibility": "public",
  "show_profile_to_strangers": true
}
```

Report request:

```json
{
  "target_type": "social_post",
  "target_id": "uuid",
  "reason_type": "spam",
  "reason_text": "Repeated unrelated content.",
  "source": "post_detail"
}
```

## Conversations

```text
POST /messages/direct-conversations
```

Request:

```json
{
  "target_user_id": "uuid"
}
```

Creates or returns the unique direct conversation for the two users. Messages are persisted even when the recipient is offline; delivery is represented by the recipient member row and unread count.

Direct conversation creation follows the recipient privacy setting:

- `everyone`: any non-blocked active user can start a direct conversation.
- `following`: users followed by the recipient can start a direct conversation.
- `friends`: only mutual followers can start a direct conversation.

If direct messaging is not allowed and `allow_message_requests = true`, the client should call `POST /messages/requests`.

```text
GET /messages/conversations
POST /messages/groups
POST /messages/requests
GET /messages/requests
POST /messages/requests/{message_request_id}/accept
POST /messages/requests/{message_request_id}/decline
GET /messages/conversations/{conversation_id}/messages
POST /messages/conversations/{conversation_id}/messages
POST /messages/conversations/{conversation_id}/read
GET /messages/unread-counts
```

Create message request:

```json
{
  "target_user_id": "uuid",
  "request_message": "Want to discuss your serve drill?",
  "source": "profile"
}
```

Send chat message request:

```json
{
  "message_type": "text",
  "text_content": "After practice, want to review the serve video?",
  "client_message_id": "device-generated-id"
}
```

Supported `message_type` values:

```text
text, image, video, audio, file, post_share, video_share,
activity_share, lesson_share, analysis_card, system_event, custom
```

Object references use:

```json
{
  "target_object_type": "video",
  "target_object_id": "uuid"
}
```

The message table does not own business objects. It only references existing objects such as `videos`, `social_posts`, `tennis_activities`, and `lessons`.

## Notifications

```text
GET  /notifications
POST /notifications/{user_notification_id}/read
POST /notifications/read-all
```

First version supports follow, post like, post comment, and comment reply notifications. Message requests use the generic `custom` event type with a message request payload. The same schema can later carry mentions, AI analysis completion, lessons, coach events, and system announcements.
