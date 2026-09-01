# Stage 16B dependency contracts

`TestFileExportStorage` is the only implemented export provider. It creates an
opaque relative JSON key, writes atomically below a private test root, validates
keys before open/delete, and never returns a storage path through an API model.
`external_contract` is a configuration-only placeholder: it cannot silently
fall back to test storage and currently fails until a separately authorized
object-storage adapter is implemented.

The realtime `WakeupDispatcher` contract carries only `event_id`, recipient
user ID, origin `instance_id`, and emission time. A remote consumer must re-read
the authoritative `user_sync_events` row; it must not treat this as a message
payload. The default `ProcessLocalWakeupDispatcher` performs no network I/O.
Dispatcher failure is best effort after commit, so REST sync/history/reconcile
remain the recovery and correctness path.

Production configuration rejects test export storage, wildcard CORS, development
Push keys, Fake Push, missing instance IDs, and missing external storage
contract settings. No broker, object-storage SDK, APNs, FCM, hard delete, or
automatic anonymization is implemented by this stage.
