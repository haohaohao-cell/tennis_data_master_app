# Message Realtime and Push Architecture

Status: Stage 11B--11D are implemented and verified in local PostgreSQL
isolated schemas. Stage 11C provides a test-only Fake Push provider
for `channel='push'`; Stage 11D provides an authenticated, single-instance
WebSocket wake-up channel. APNs, FCM, SSE, real provider delivery and
multi-instance fan-out are not implemented.

Non-development deployments must set `TENNIS_MESSAGE_SYNC_CURSOR_SECRET` to a
managed secret before startup. The development fallback is local-only; the
application rejects a missing cursor secret outside development and never
includes the secret in logs, responses or audit reports.

## Current Baseline

`chat_messages.message_seq` is authoritative only inside one conversation.
`outbox_events` is currently an internal message-created queue: it has an
`event_id`, aggregate/message identifiers, `message.created`, version,
conversation and sequence, a small JSON payload, availability, lease, attempt
and processing fields. It is written in the same transaction as a message and
can be listed using a `(created_at, event_id)` cursor.

The current cursor is stable for one ordered query while rows are retained, but
is not a durable public multi-device contract. Worker `processed` state must
not decide client replay. Current `outbox_events` must not become both an
internal delivery queue and the long-lived user sync log.

The internal Outbox durable coverage remains only `message.created`. Stage 11B
also writes recipient-scoped `user_sync_events` for `message.created`,
`message.recalled` and `conversation.read` in their business transactions.
Notification events, message-request transitions, conversation changes and media
lifecycle changes remain deferred to REST reconciliation. Fake Push token and
delivery state is available only behind its test-only provider; App local Outbox
plus REST history, reconcile and notification list remain the disconnect
compensation.

## Target Boundaries

1. The business transaction writes domain rows, internal Outbox and recipient
   sync records atomically.
2. `outbox_events` remains an internal leaseable work queue.
3. `user_sync_events` is append-only, recipient-scoped and independent from
   worker `processed` state. It is the public sync/replay source.
4. Push and realtime are wake-up and incremental signals only. REST sync,
   message history, notification list and reconcile remain recovery surfaces.
5. Media and business-object events carry identifiers and state only; clients
   hydrate through existing authorization-checked APIs.

## Stage 11B Event Envelope

```json
{
  "event_id": "uuid",
  "event_type": "message.created",
  "event_version": 1,
  "aggregate_type": "chat_message",
  "aggregate_id": "uuid",
  "actor_user_id": "uuid-or-null",
  "recipient_user_id": "uuid",
  "conversation_id": "uuid-or-null",
  "message_id": "uuid-or-null",
  "message_seq": 42,
  "notification_event_id": "uuid-or-null",
  "occurred_at": "UTC timestamp",
  "persisted_at": "UTC timestamp",
  "cursor": "opaque recipient-scoped cursor",
  "privacy_classification": "private_metadata",
  "trace_id": "request id or null",
  "payload": { "changed_fields": ["message_id", "message_seq"] }
}
```

Payloads contain no phone number, email, Push token, storage key, filesystem
path, full private message body, or copied Post/Activity/Lesson/Video/Analysis
record. They are change hints, not hydration replacements.

Implemented in Stage 11B: `message.created`, `message.recalled` and
`conversation.read`. `conversation.updated`, `conversation.hidden`/`restored`,
message-request, notification and media-state events are DEFERRED; REST
reconciliation remains authoritative. `message.updated` waits for message
editing. Presence, typing and analytics must not use the durable sync log.

## Public Device Sync (Stage 11B Implemented)

Implemented endpoints:

```text
POST   /api/v1/messages/devices
PATCH  /api/v1/messages/devices/{device_id}
DELETE /api/v1/messages/devices/{device_id}
GET    /api/v1/messages/sync?cursor=<opaque>&limit=<bounded>
POST   /api/v1/messages/sync/checkpoints
```

The client creates a stable random `device_id`; the server binds it to the
authenticated user and records optional platform/app-version metadata. A cursor
is per device, while read watermarks remain shared conversation-member state.
The server owns cursor encoding and validates recipient, device, retention epoch
and signature. Clients deduplicate envelopes by `event_id` and merge messages
with `message_id`/`message_seq`. PostgreSQL emits `message.created`,
`message.recalled` and `conversation.read` inside their business transactions.

Expired/missing cursors return `SYNC_CURSOR_EXPIRED` with a reconciliation plan:
fetch conversations, notifications and affected message history through existing
REST pagination, then persist the returned checkpoint. Logout revokes the device
and disables token references. Block, removal, hidden/deleted conversation and
lost object permission are rechecked on every sync query.

## Push Proposal

After commit, an Outbox consumer evaluates current mute and notification
preferences, then creates provider-neutral deliveries. Push never proves
message persistence; a lost Push is recovered through sync/history.

| Model | Responsibility | Key constraints |
| --- | --- | --- |
| `messaging_devices` | User-owned device lifecycle | unique `(user_id, device_id)`; active/revoked |
| `push_device_tokens` | Controlled encrypted token reference | unique provider/environment/token fingerprint; never log raw token |
| `push_deliveries` | Delivery attempt for event/device/token | unique `(event_id, device_id, purpose)`; retry and provider result |
| `user_sync_events` | Recipient replay source | unique `(recipient_user_id, event_id)`; append-only cursor index |

Tables are additive. PostgreSQL keeps text UUID/JSON compatibility for the API
contract and adds recipient/cursor and worker indexes, row locking and retention
jobs. Rollback disables consumers/new endpoints, leaving additive
tables unused. APNs/FCM credentials arrive only in Stage 11C. Invalid tokens
disable token rows, never message history. Push payloads contain route, event id
and coarse category only.

### Candidate Table Detail

`messaging_devices` has `messaging_device_id` as primary key and `(user_id,
device_id)` unique. It references `users`, stores platform/app-version,
created/last-seen/revoked timestamps and no Push token. Index active devices by
`(user_id, revoked_at, last_seen_at)`. Retain the revoked tombstone long enough
to reject stale clients, then purge it under an account/device lifecycle policy.

`push_device_tokens` has `push_device_token_id` as primary key, references the
device and stores provider, environment, encrypted token ciphertext, token
fingerprint, active/revoked timestamps and error reason. Enforce unique
`(provider, environment, token_fingerprint)` and index active tokens by device.
The raw token exists only at registration/provider call boundaries and must not
be written to application logs or reports.

`push_deliveries` has `push_delivery_id` as primary key, references an Outbox
event and device/token as appropriate, and stores purpose, status, attempts,
available/leased/processed/failed timestamps, provider message id and bounded
error code. Enforce unique `(event_id, messaging_device_id, purpose)` and index
claim work by `(status, available_at, created_at)`. Retain diagnostic rows for a
bounded policy period; dead-letter status requires operator visibility, not a
silent retry loop.

`user_sync_events` has `user_sync_event_id` as primary key, references the
recipient user and domain event/aggregate identifiers, and stores event type,
version, occurred/persisted time, minimal JSON and privacy class. Enforce unique
`(recipient_user_id, event_id)` and index `(recipient_user_id, persisted_at,
event_id)` for cursors. Its retention window must exceed the documented cursor
window; expired cursors force reconciliation rather than reading deleted rows.

All candidates use PostgreSQL text IDs, text timestamps and JSON text for API
compatibility. PostgreSQL also provides foreign keys, partial active-token
indexes and `SKIP LOCKED` claims where workers need them. Migration is additive and idempotent;
rollback stops readers/consumers and retains rows until an explicitly approved
retention job, never by destructive migration.

## Realtime Transport Decision

Recommendation: WebSocket in Stage 11D, with REST sync as correctness path. It
supports future bidirectional acknowledgements, cursor checkpoints and
typing/presence without a second protocol. Its cost is heartbeat, reconnect,
backpressure, load-balancer/broker fan-out and connection observability.

SSE would simplify a server-to-client-only release, but needs a separate client
acknowledgement path, has uneven mobile background behavior and would likely be
replaced with typing/presence. Neither transport subscribes to the database or
broadcasts before commit. Both send envelopes and reconnect with last cursor.

## Delivery and Recovery

Transactions guarantee domain rows plus internal Outbox plus future sync logs.
Delivery after commit is at least once; consumers, providers and clients use
`event_id` idempotency. There is no cross-provider exactly-once claim.
`message_seq` orders a conversation only.

Broadcast failure after commit is retried/woken later and REST sync repairs it.
Missed acknowledgements replay safely. Push success without App sync leaves the
cursor behind. A create then recall produces both events and converges by later
state. Group exit, blocks and permission changes require server filtering and
hydration. Expired leases are reclaimed but never erase replay eligibility.

## Security and Operations

All endpoints require active-user Bearer authentication, device ownership,
membership and current block/privacy checks. Limit per-user/device registration,
connections and replay; bound batch size/cursor age; rate-limit invalid cursors.
Encrypt token material and redact it from logs; revoke on logout, device removal
or account deletion.

Metrics: Outbox backlog/oldest age/claim rate/success/failure/retry/dead-letter,
provider success/invalid-token rate, active connections/reconnect rate, cursor
lag/replay size/sync latency/duplicates/permission rejection and REST fallback.
Logs include opaque IDs, type, result, attempt and trace id, never body, token,
DSN or storage key.

## Follow-up Stages

| Stage | Scope and completion gate | External needs | Explicitly excluded |
| --- | --- | --- | --- |
| 11A | This architecture, contract, migration and test plan approved | None | All runtime delivery |
| 11B | Device registry, sync log, `/sync`, checkpoints and REST recovery | Local isolated PostgreSQL evidence | Provider/realtime delivery |
| 11C | Token registry, deliveries, preference evaluation and fake provider | Local isolated PostgreSQL evidence; no APNs/FCM | Real provider credentials |
| 11D | Authenticated single-instance WebSocket, reconnect and REST recovery | Local isolated PostgreSQL evidence plus controlled clients | Public internet, broker and multi-instance delivery |
| 11R | PostgreSQL concurrency, privacy, load and optional real-environment gates | Real PostgreSQL; device/provider only when approved | New product features |

Every stage uses additive migration, isolated PostgreSQL schemas and a feature
flag/consumer-disable rollback. REST remains fallback.

### Stage Entry and Completion Rules

Stage 11B front end adds a durable sync cursor/checkpoint; backend adds
authorized device and sync services; database adds devices, sync events and
checkpoints; shared contract publishes finalized sync models. PostgreSQL core
behavior is implemented and verified. Isolated-schema verification is
local evidence only and does not prove production readiness. No real provider or
multi-instance socket is included.

Stage 11C front end adds device registration state; backend adds token and
delivery services behind a fake provider; database adds token/delivery tables;
shared contract publishes registration and delivery-safe state. Enter after 11B
is stable. Complete after fake-provider preference, mute, invalid-token, retry,
deduplication and privacy tests pass. It needs real PostgreSQL but no real
APNs/FCM, public endpoint or device.

Stage 11D now adds a single-instance authenticated WebSocket wake-up gateway.
The backend uses a bounded process-local registry and emits only committed
recipient-scoped `sync.wake` envelopes for the three Stage 11B event types.
The App reconnects with jittered backoff while foregrounded and invokes REST
sync after a wake-up. Database state and REST sync remain authoritative;
multi-instance fan-out, broker infrastructure and production capacity remain
outside this baseline. Database only adds connection/checkpoint metadata if measurements require it; shared contract
finalizes envelope compatibility. Enter after 11B replay is authoritative.
Complete after controlled local connection, backpressure, restart, revocation
and REST-fallback tests pass. It needs PostgreSQL and controlled clients, not a
real Push provider or public internet.

Stage 11R runs isolated PostgreSQL concurrency, privacy and performance gates,
then separately approved real-device/provider validation if product readiness
requires it. It does not add product features. Any stage rolls back by disabling
its feature flag/consumer and retaining additive data for audit; it never rolls
back business messages or switches away from PostgreSQL.

## Test Plan

PostgreSQL: schema compatibility, envelope generation, cursor validation,
duplicate handling, REST fallback, transactional fan-out, `SKIP LOCKED`,
crash/lease reclaim, concurrent checkpoints, revocation, replay and
p50/p95/p99/max. Fake provider: token rotation/invalidation, retryable/permanent
failure, deduplication, mute/preference and payload privacy. Realtime:
authentication, reconnect/resume, gaps, slow consumers, backpressure, permission
change, restart, multiple devices and REST recovery. Push, fake provider and
realtime transport tests belong to later stages.
## Stage 11C Fake Push Boundary

Stage 11C adds a provider-independent token registry and durable push delivery
state machine backed by `push_device_tokens` and `push_deliveries`. The only
provider in this stage is an in-process fake provider that accepts `fake_`
test tokens and injects success, retryable, permanent, timeout, and invalid
token outcomes. It performs no network I/O and is not APNs or FCM.

Push delivery is an at-least-once wake-up/routing signal, not message
authority. The message transaction commits message, Outbox, and sync state
first; an Outbox consumer creates deliveries afterward, and a worker calls the
fake provider outside that transaction. REST sync/history/reconcile remain the
authoritative recovery path. Token ciphertext is a development controlled
representation and is not production credential management.

Feature flags default to disabled: `MESSAGE_PUSH_ENABLED`,
`MESSAGE_PUSH_FAKE_PROVIDER_ENABLED`, and
`MESSAGE_PUSH_TOKEN_REGISTRATION_ENABLED`. Stage 11C2 is NOT AUTHORIZED. Stage
11D is COMPLETE_WITH_SINGLE_INSTANCE_SCOPE; Stage 11R production
load/provider validation remains NOT AUTHORIZED. B-R2 is COMPLETE; current
TypeScript status must be established by the current workspace check rather
than this historical architecture record.

### Stage 11C-H3 Development Diagnostics

`delivery_metrics()` returns only aggregate delivery status, attempts, lease
reclaims, and bounded failure counts for local test diagnostics. It never
returns a user id, device id, token, message body, storage key, path, or DSN;
it is not production monitoring, alerting, or an SLA. Before every provider
call the worker rechecks that the token remains active and the messaging device
has not been revoked; a revoked lease becomes `cancelled` without provider I/O.
