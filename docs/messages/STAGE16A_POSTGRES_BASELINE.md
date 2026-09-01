# Stage 16A PostgreSQL baseline

Status: `COMPLETE_WITH_BOUNDARIES`

- PostgreSQL evidence uses local `tennis_messages_test` only, with independent `s16a_*` schemas. Schema creation, table/index/constraint/function creation, and idempotent rendering were verified. The public schema was not used for writes.
- Isolated PostgreSQL regressions passed for Stage 11B, 11C Fake Push, 11D WebSocket, Stage 12 API and legacy migration, Stage 13A, Stage 13C-D, Stage 14A, Stage 14B, Activity delete, and a Stage 14D-F export smoke.
- Stage 14A search was corrected to explicit `LOWER(...) LIKE LOWER(...)` so SQLite and PostgreSQL have consistent case-insensitive behavior.
- SQLite regressions use temporary databases. Default `backend/db/tennis_data_master.sqlite3` was not opened or modified.
- Export storage remains `TEST_STORAGE_BOUNDARY`; WebSocket cleanup remains single-instance; Fake Push is test-only; real Push/APNs/FCM, multi-instance fan-out, production object storage, hard delete, and anonymization remain deferred.
- This evidence does not establish production capacity, SLA, legal compliance, production migration approval, or production readiness.
