# Stage 14D-F boundaries

- Export generation and download are owner-authorized, idempotent, expiry-checked, and served from protected internal relative keys.
- The checked-in implementation uses local test file storage only; production object storage and legal/compliance certification are deferred.
- Deletion processing revokes devices/tokens, suppresses pending deliveries, and schedules process-local cleanup of every WebSocket for the user.
- Multi-instance WebSocket fan-out, hard delete, and automatic anonymization are deferred or require review.
