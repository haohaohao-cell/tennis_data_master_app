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
POST /messages/conversations/{conversation_id}/messages/reconcile
POST /messages/conversations/{conversation_id}/messages
POST /messages/conversations/{conversation_id}/read
POST /messages/conversations/{conversation_id}/pin
DELETE /messages/conversations/{conversation_id}/pin
POST /messages/conversations/{conversation_id}/mute
DELETE /messages/conversations/{conversation_id}/mute
POST /messages/conversations/{conversation_id}/hide
DELETE /messages/conversations/{conversation_id}/hide
GET /messages/unread-counts
```

### Message media

```text
POST /messages/media/upload-intents
POST /messages/media/{media_id}/file       (multipart field: file)
POST /messages/media/{media_id}/complete
POST /messages/media/{media_id}/cancel
GET  /messages/media/{media_id}
GET  /messages/media/{media_id}/content?variant=thumbnail|original
```

Message media is isolated from Post and tennis-activity uploads. The
`chat_message_media` table owns the upload lifecycle and verified media
metadata; `chat_message_attachments` only records the one-to-one binding from
a committed `image` or `video` message to its media record. The upload intent
accepts `image/jpeg`, `image/png`, `image/webp`, `image/gif`, `video/mp4`,
`video/quicktime`, `video/webm`, `video/x-matroska`, or `video/3gpp`, positive
dimensions, a bounded file size, and a user-scoped
`client_upload_id`. The server generates `media_id` and the private storage
key; clients cannot submit a storage path, bucket, or permanent URL. Upload
and message idempotency keys are independent: retrying an identical intent
returns the same media, while retrying an identical message returns the same
message. Changing intent metadata returns `409 CLIENT_UPLOAD_ID_CONFLICT`.

Media progresses through `created`, `uploading`, `uploaded`, `attached`,
`failed`, `expired`, and `deleted`. File transfer is outside the message
database transaction. Completion validates actual image content and generates
a bounded JPEG thumbnail for images; for videos it validates the real stream,
container, codec, dimensions, duration, and checksum with `ffprobe`, then
generates a first-frame JPEG thumbnail with `ffmpeg`. Thumbnail failure
preserves the validated original and reports `thumbnail_status = failed`. It
does not create a message. Only an uploaded, unbound media record may be
attached to one matching `image` or `video` message; binding the message and
attachment occurs in the same transaction. Media messages may also contain
bounded text and use the normal `client_message_id` retry semantics.

Unbound media is readable only by its owner. Attached media requires an active
member of the message's conversation and a non-revoked message. Content URLs
are authenticated API routes and never expose `storage_key`; expired, failed,
deleted, missing, or unauthorized media return stable unavailable errors.
Video uploads are limited to 200 MiB, five minutes, and 40 million pixels by
default; image uploads are limited to 15 MiB and 40 million pixels. Audio and
generic file uploads are not supported. Message media does not use any Post,
tennis-diary, or `app/api/uploads.ts` upload flow.

Media responses expose `thumbnail_status` (`pending`, `generated`, or `failed`),
`thumbnail_failure_code`, `storage_deleted_at`, and `last_cleanup_error`.
The cleanup command is dry-run by default; only `--execute` removes safe
candidates under the isolated message-media storage root.

Conversation Pin is a per-user membership preference backed by
`chat_conversation_members.pinned_at`. `POST .../pin` sets the authenticated
active member's timestamp only when it is currently null; an idempotent retry
preserves the existing timestamp. `DELETE .../pin` clears that member's
timestamp and is also idempotent. Neither endpoint accepts another user or
member identifier.

Conversation lists are ordered before pagination with pinned memberships
first. Both the pinned and unpinned buckets retain the existing ordering:
conversations with activity before empty conversations, then
`last_message_at DESC`, then `created_at DESC`. Pin does not change unread
counts, read watermarks, block state, history, last-message metadata, Push, or
the other participant's membership.

Conversation Mute is a per-user membership preference backed by
`chat_conversation_members.muted_until`. `POST .../mute` accepts no body and,
when the caller is not effectively muted, sets `muted_until` to authoritative
server UTC time plus 24 hours. An active retry preserves the original expiry;
an expired timestamp is treated as unmuted and a new POST creates a fresh
24-hour expiry. `DELETE .../mute` clears the timestamp and is idempotent.
Conversation members include server-derived `is_muted`, which is true only
when `muted_until` is later than server time; clients must use this boolean
rather than their local clock. The response is:

```json
{
  "success": true,
  "conversation_id": "uuid",
  "muted_until": "2026-08-16T00:00:00Z",
  "is_muted": true
}
```

Mute does not change send/receive, unread or badge counts, read watermarks,
Pin, Block, history, or last-message metadata. It affects only future Direct
Message Push intent eligibility for that membership. When global
`direct_message_notifications` is disabled the intent decision is
`suppressed_by_preference`; otherwise an effective mute returns
`suppressed_by_conversation_mute`. Expired mutes do not suppress Push.

Conversation Hide is a per-user visibility preference backed by
`chat_conversation_members.archived_at`. `POST .../hide` stores an
authoritative server UTC timestamp only when the caller is not already hidden;
retries preserve the original timestamp. `DELETE .../hide` clears it and is
idempotent. The response includes `archived_at` and server-derived
`is_hidden`. Hide removes the membership from `GET /messages/conversations`
before ordering and pagination, but does not delete history, mark messages
read, alter unread/badge counters, Pin, Mute, Block, or Push preferences.

A genuinely new ChatMessage clears `archived_at` for every active member in
the same creation transaction, restoring normal list visibility while
preserving Pin and Mute. An idempotent retry that returns an existing message,
as well as history reads and mark-read, does not restore a hidden membership.
Hide does not suppress Direct Message Push.

**KNOWN UX LIMITATION — HIDDEN UNREAD DISCOVERABILITY:** hidden conversations
continue to contribute unread and Messages badge counts. This avoids falsely
marking messages read; a hidden-conversation management flow is deferred.

`GET /messages/conversations/{conversation_id}/messages` is authorized for the
current active member and returns `other_member_last_read_message_seq` for a
Direct conversation. This is the other participant's server-side read
high-watermark; it is `null` for Group conversations. Clients derive a sender
receipt in memory with `message_seq <= other_member_last_read_message_seq`.
The server fetches this watermark once per list request rather than storing a
receipt row for every message.

The same Direct message-list response includes an authoritative interaction
state:

```json
{
  "direct_interaction_state": {
    "can_send": false,
    "blocked_by_current_user": true
  }
}
```

`can_send` is false when an active `user_blocks` row exists in either
direction. `blocked_by_current_user` is true only when the authenticated user
owns an active block row, allowing the App to explain the user's own action
without disclosing that the other participant blocked them. Both fields are
recomputed once per message-list request. Group responses return
`direct_interaction_state: null` and do not imply single-recipient block
semantics. Block state does not revoke authenticated member access to history,
mark-read, or existing read high-watermarks; message sending and Message
Requests remain protected by the server's bidirectional block enforcement.

`POST /messages/conversations/{conversation_id}/read` accepts an optional
bounded body:

```json
{
  "through_message_seq": 10
}
```

When supplied, the server advances the authenticated member's
`last_read_message_seq` only through that observed sequence, never regresses
an existing watermark, and returns `last_read_message_seq` plus the remaining
`unread_count`. Omitting the body preserves the legacy behavior of marking the
conversation through its current server high-watermark. Clients should send
the observed sequence to avoid marking messages that arrived after the read
view was reconciled.

Unread counts keep message, notification, and request semantics separate:

```json
{
  "unread_direct_message_count": 2,
  "unread_group_message_count": 1,
  "unread_notification_count": 3,
  "pending_message_request_count": 4,
  "total_unread_count": 6,
  "messages_tab_badge_count": 9
}
```

Message list responses additionally include:

```json
{
  "conversation_id": "conversation-id",
  "direct_interaction_state": {
    "can_send": true,
    "blocked_by_current_user": false
  },
  "items": [],
  "next_before_seq": null,
  "other_member_last_read_message_seq": 10
}
```

`pending_message_request_count` counts all pending incoming requests for the authenticated user and is not pagination-dependent. `unread_notification_count` continues to count every unread notification record, including the notification record created for a Message Request, and `total_unread_count` remains direct plus group plus that legacy notification count for compatibility. `messages_tab_badge_count` is the product-specific aggregate: direct unread plus ordinary notification unread plus pending incoming requests. It excludes group unread and Message-Request-derived notification records because requests are already represented by `pending_message_request_count`.

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
GET  /notifications?product_category=interaction_follow|course_system|request
POST /notifications/{user_notification_id}/read
POST /notifications/read-all
```

First version supports follow, post like, post comment, and comment reply notifications. Message requests use the generic `custom` event type with a message request payload. The same schema can later carry mentions, AI analysis completion, lessons, coach events, and system announcements.

Every returned event includes an additive normalized contract:

```json
{
  "event_type": "custom",
  "notification_type": "message_request",
  "category": "interaction",
  "product_category": "request",
  "target": {
    "type": "message_request",
    "request_id": "uuid"
  }
}
```

Text messages may reply to an existing message in the same conversation:

```json
{
  "message_type": "text",
  "text_content": "Agreed",
  "reply_to_message_id": "message-uuid",
  "client_message_id": "device-generated-id"
}
```

The server requires the target to exist, belong to the same conversation, be
available, and be accessible to the authenticated conversation member. A
cross-conversation target is rejected without exposing the target content.
Message responses include an additive `reply_preview` when applicable:
`state` is `available` or `unavailable`; available previews contain the target
message ID/sequence, sender identity, and a bounded text preview. Unavailable
previews contain only a neutral state and target ID. The preview is hydrated
from the authorized conversation and does not require the original message to
be in the current history page. Reply retries preserve the existing
`client_message_id` and therefore return the originally committed reply
relationship without incrementing unread twice.

Direct text messages can be recalled by their original sender with:

```text
POST /messages/conversations/{conversation_id}/messages/{message_id}/recall
```

Recall has no time window in V1 and is idempotent. It changes the persisted
message status from `sent` to `revoked` without deleting the row, changing its
sequence, or changing unread/read watermarks. Only an active member who owns
the text message can recall it; Group, media, system, non-member, and
other-user messages are rejected. A revoked message remains in history as a
neutral tombstone with content-bearing fields redacted. It is excluded from
conversation history search. If it is the conversation's latest message,
only `last_message_preview` changes to `[消息已撤回]`; the latest message ID,
sequence, and timestamp remain unchanged. No notification or Push event is
created. Existing Reply previews for a recalled original become
`state = unavailable`.

### Loaded-message reconciliation

```text
POST /messages/conversations/{conversation_id}/messages/reconcile
```

The request body is `{ "message_ids": ["..."] }` and accepts up to 500
deduplicated persisted message IDs already loaded by the caller. The server
returns `{ conversation_id, items }` using the same privacy-safe message
serializer as history. Only rows belonging to the authorized conversation are
returned; unknown or cross-conversation IDs are omitted and non-members are
rejected. This endpoint has no read, unread, hide, pin, mute, notification, or
Push side effects and refreshes loaded history rows outside the normal latest-page poll.

`event_type` and `category` preserve stored values. `notification_type` normalizes Message Requests to `message_request`, including legacy `custom` rows linked by `message_request:<request_id>`. Product categories are:

- `interaction_follow`: ordinary `interaction` notifications such as follow, post like, post comment, and comment reply.
- `course_system`: ordinary `system`, `ai`, `coach`, and `lesson` notifications.
- `request`: Message Request notifications, which remain separate from both normal Notification View categories.

`product_category` filtering is applied by the server before pagination. Existing `category` filtering remains supported.

`target` is the preferred navigation contract and is a discriminated union with these bounded types: `user_profile`, `post_detail`, `post_comments`, `message_request`, `chat`, `activity_detail`, `lesson_detail`, `coach_identity`, and `none`. Identifier-bearing targets use semantic fields such as `user_id`, `post_id`, `conversation_id`, `activity_id`, and `lesson_id`. `message_request.request_id` may be null when only the Request view is reliably known. `none` is returned for incomplete or unsupported events; clients must not fabricate identifiers or treat `deep_link` as an arbitrary executable route. Existing destination authorization remains authoritative.

Current derivation maps follow, post-like, post-comment/reply, linked Message Requests, Activity-backed AI completion, and coach-review events. The App opens the existing comments focus for `post_comments`. Lesson targets remain non-actionable until a Lesson detail route exists. `chat` is reserved for future notification producers; this contract does not create Direct Message notification events.

### Notification preferences

```text
GET   /notifications/preferences
PATCH /notifications/preferences
```

Both routes are authenticated self-service APIs and never accept another user's ID. GET always returns all six effective boolean values:

```json
{
  "direct_message_notifications": true,
  "message_request_notifications": true,
  "like_comment_notifications": true,
  "follow_notifications": true,
  "course_notifications": true,
  "ai_analysis_notifications": true
}
```

All fields default to `true`, including for users without a persisted preference row. GET does not materialize that default row. PATCH accepts one or more of the same strict boolean fields, updates only supplied fields, persists the result, and returns the full effective object. Empty bodies, null/string values, and unknown fields are rejected.

These settings control only future system Push eligibility. They do not create, delete, hide, read, or suppress Notification Center records; do not change unread or badge calculations; and do not permit or block Direct Messages or Message Requests.

Stable preference kinds are `direct_message`, `message_request`, `like_comment`, `follow`, `course`, and `ai_analysis`. Normalized event mappings are: `follow` to `follow`; `post_like`, `post_comment`, and `comment_reply` to `like_comment`; `message_request` to `message_request`; `lesson_created` and `lesson_updated` to `course`; and `ai_analysis_completed` to `ai_analysis`. Direct Message Push will request `direct_message` explicitly because Direct Messages do not create notification events. Unmapped types currently receive no preference-based suppression until product policy defines a mapping.

### Messaging Push delivery contract

Messaging can derive a provider-independent Push intent after a Direct Message, Message Request, or Notification Event has been persisted. Intent construction is read-only and does not transmit Push, enqueue work, register devices, or create additional Notification Center events.

Push kinds are bounded to `direct_message`, `message_request`, and `notification_event`. Delivery decisions are:

- `eligible`: semantic request and mapped preference allow delivery.
- `suppressed_by_preference`: the user disabled the mapped preference.
- `suppressed_by_conversation_mute`: the recipient actively muted that Direct
  Message conversation after the global preference allowed delivery.
- `eligible_without_preference_mapping`: product has not mapped this semantic to a preference, so no preference-based suppression is applied.
- `invalid_target`: a mapped actionable event lacks its required typed target.
- `unsupported`: the persisted object cannot produce a supported intent, or its destination is not currently actionable.

The intent wrapper contains `decision` and an optional semantic `request`. A request uses this common provider-agnostic shape:

```json
{
  "push_kind": "notification_event",
  "recipient_user_id": "user-id",
  "delivery_id": "notification_event:event-id",
  "preference_kind": "follow",
  "notification_type": "follow",
  "target": { "type": "user_profile", "user_id": "actor-id" },
  "display": { "title": "display title", "body": "display body" },
  "data": {
    "type": "notification_event",
    "notification_event_id": "event-id",
    "actor_user_id": "actor-id"
  }
}
```

The `data` member is itself a bounded union. Direct Message data contains only `message_id` and `sender_user_id`; Message Request data contains only `request_id` and `requester_user_id`; Notification Event data contains `notification_event_id` and optional `actor_user_id`. Routing always uses the existing typed `target` contract. No phone, email, message history, attachment data, private Activity/analysis payload, arbitrary route, provider token, or provider-specific option is included.

Logical delivery identities reuse persisted IDs: `direct_message:<message_id>`, `message_request:<request_id>`, and `notification_event:<notification_event_id>`. A Notification Event normalized as a Message Request delegates to the Message Request contract, preserving the same request delivery identity. Future deduplication scopes `delivery_id` together with `recipient_user_id`; these identities enable that integration but do not implement provider-level dedup storage or retries.

Direct Message and Message Request display bodies intentionally omit their private text. Display metadata and routing data remain separate so shared infrastructure can later apply the confirmed lock-screen preview policy. Lesson events carry their mapped `course` preference but currently resolve to `unsupported` when enabled because the App has no actionable Lesson detail route. Unmapped `mention`, `video_shared`, `coach_application_reviewed`, `system_announcement`, and `custom` events use `eligible_without_preference_mapping` without changing their in-app records.

### Business object cards

`business_object_card` is the additive, authoritative message object-card
protocol. Its finite `object_type` values are `social_post`, `video`,
`tennis_activity`, `lesson`, and `analysis`; finite `state` values are
`available`, `unavailable`, and `unsupported`. It always includes
`kind = "business_object"`, `object_type`, `object_id`, minimal display fields,
`metadata`, and `unavailable_reason`. `unavailable` is used for objects that
cannot be read now; `unsupported` means this client/server version has no
resolver for that object type and contains no object content.

### Post share cards

`post_share` messages targeting `social_post` return `share_card` from send,
history, reconcile, and conversation-message search. Their `payload_json` is
always `null`; the internal `post_share_id` is not a client display contract.

```json
{
  "share_card": {
    "state": "available",
    "post_id": "post-id",
    "title": "Post title",
    "summary": "Short summary",
    "cover_url": "/storage/videos/thumbnail.jpg",
    "author": {"user_id": "user-id", "nickname": "Author", "avatar_path": null},
    "visibility": "public",
    "reason": null
  }
}
```

The server rechecks current Post access for the authenticated active member on
every hydration. Deleted, hidden, unpublished, blocked, or inaccessible Posts
return `state = "unavailable"`, the `post_id`,
`reason = "not_found_or_no_access"`, and null optional content fields. Clients
must not show cached title, summary, author, or cover data for this state.
`cover_url`, when present, is a generated video thumbnail, never original Post
media. Conversation shares require `client_message_id`; retries return the
original share and message without another message, unread increment, hidden
conversation restoration, or `share_count` increment. Other share types may
reuse this protocol later, but only `post_share` cards are implemented now.

The idempotency scope is `(authenticated_user_id, client_message_id)`. A
conversation share must provide a non-empty key; non-conversation shares may
omit it. When a key is present, the server compares the Post, target type,
conversation, channel, message text, message/object references, and payload.
An identical request returns the original records. Reusing the key with any
different value returns HTTP `409` with code `CLIENT_MESSAGE_ID_CONFLICT`,
without returning the old records or creating any message, share, unread,
notification, hidden-conversation restoration, or `share_count` side effect.
The database partial unique index is the final concurrent-write guard; the
application comparison preserves request identity before returning a retry.
Older SQLite databases are upgraded by adding nullable columns and the index.
If duplicate non-null keys already exist, startup fails with an explicit
reconciliation error and does not delete data.

For compatibility, `share_card` remains available only for `post_share` and is
derived from the same `business_object_card` hydration result. New clients must
use `business_object_card`; the legacy field will remain until supported mobile
versions have migrated. A repeated `client_message_id` must bind the same
sender, conversation, message/share type, and target object; otherwise the API
returns `409 CLIENT_MESSAGE_ID_CONFLICT` with no new message, unread count, or
share-count side effect.

The idempotency behavior applies equally to the `business_object_card` returned
by a retry: it is hydrated from the original object reference under current
Post permissions, while conflict responses do not include the previous card.
Post sharing does not implement or reuse Post or tennis-diary upload APIs.

## PostgreSQL runtime compatibility

The API contract is unchanged when the backend uses PostgreSQL. String IDs,
timestamp response formats, message sequence numbers, idempotency conflict
codes, unread counts, object-card availability states, and message-media
authorization remain compatible with the SQLite baseline. PostgreSQL is the
production write authority when `TENNIS_DATABASE_URL` is configured; SQLite is
retained only for legacy migration input and lightweight tests.

## Query boundary

History, message search, and reconcile preserve `conversation_id` plus
`message_seq` cursor semantics. Their Post `business_object_card` hydration is
page-bounded: Post rows, access relationships, and cover media are loaded in
batch, while unsupported object types remain `unsupported` and database
failures are not converted to `unavailable`. SQLite performance evidence is
reported separately from PostgreSQL evidence.

## Offline send and durable events

The mobile client keeps drafts and pending sends in a versioned local store.
Draft text, local attachment references, local IDs, device IDs, retry metadata,
and local error details never enter the server message payload. Local states
are `queued`, `sending`, `sent`, `failed_retryable`, `failed_permanent`, and
`cancelled`. On app start or foreground recovery, `sending` becomes `queued`.

`client_message_id` is idempotent within the authenticated sender scope;
`message_id` is the server-authoritative message identity; `event_id` is the
durable event identity; and `device_id` identifies a local queue only. Retries
with the same request identity return the original message and event without
new unread, notification, or event side effects. Changed input under the same
client key returns `409 CLIENT_MESSAGE_ID_CONFLICT`.

The server writes one `message.created` row to `outbox_events` in the same
transaction as the message, conversation preview, unread facts, inbox cache,
media binding, and notifications. Event insertion failure rolls back the full
message transaction. `GET /messages/conversations/{conversation_id}/events`
is an authorized read-only replay endpoint with an opaque `(created_at,
event_id)` cursor. The client-id recovery endpoint recovers the authoritative
message after a client timeout. Network/408/425/429/5xx errors are retryable;
auth, permission, validation, conflict, and expired-media errors are permanent.

Future consumers may claim events with `leased_at`, `lease_owner`,
`attempt_count`, and `next_attempt_at`; PostgreSQL uses `FOR UPDATE SKIP LOCKED`
and SQLite provides only local single-writer serialization. Acknowledgement is
lease-owner scoped and processing must be idempotent by `event_id`. This does
not implement Push, WebSocket, or SSE delivery.

## Message video media

Message media intents accept `image` or `video`. Video records expose validated
MIME, byte size, dimensions, duration, checksum, container, and codec metadata,
while storage keys remain server-only. Video messages use a `video` attachment
and return authorized original/thumbnail URLs. Upload and message idempotency
remain separate through `client_upload_id` and `client_message_id`.
