# Stage 17 repository audit

## Scope

This audit covers the dirty worktree after Stages 11-16B. No Git write operation,
database migration, production connection, deployment, or file deletion was run.

## Classification

### KEEP_AND_SUBMIT / SUBMIT_CANDIDATE

- Backend Stage 11-16B modules under `backend/app/`, including `compliance/`, `messages/`, `admin/`, `reports/`, `uploads/`, and `core/` changes.
- Mobile API/bridge and static tests under `app/api/`, `app/messages/`, `app/app/`, and `app/tests/` that are referenced by the app build.
- `backend/db/schema.sql`, `backend/db/postgres_schema.sql`, and related migration implementation.
- Stage regression sources under `backend/tests/`.
- Product, data dictionary, technical framework, team handoff, realtime architecture, UI registry, and Shared API documents.
- Stage boundary documents and `backend/tests/stage16b_adapters.py`.

### KEEP_BUT_REVIEW / REVIEW_BEFORE_SUBMIT

- All pre-existing dirty files whose ownership predates Stage 17; split backend, app, schema, tests and documentation into separate commits.
- `backend/db/b-r2-activity-delete-report-20260830-135547.json`, an untracked generated evidence file.
- Historical ignored `backend/db/stage*.json` reports: preserve for audit, review for local paths or sensitive fields before staging.

### GENERATED_EVIDENCE

Ignored `stage*.json`, migration render SQL, SQLite WAL/SHM files and temporary
PostgreSQL schemas are reproducible evidence or runtime artifacts. They were not
deleted. The default SQLite database remains ignored and unchanged.

### DEFERRED_NOT_SUBMIT / DO_NOT_SUBMIT

- Default `backend/db/tennis_data_master.sqlite3` and its `-wal`/`-shm` files.
- Any local secrets, passwords, complete DSNs, real tokens, production exports or
  files containing unreviewed user data.
- No real object-storage, broker, APNs/FCM, hard-delete, anonymization or AI
  implementation exists to submit.

### UNKNOWN_REQUIRES_DECISION

- Whether historical generated JSON should be retained in a release commit.
- Whether all pre-existing app and backend modifications belong in one release or
  should be split by stage. This requires owner review, not automated cleanup.

## Checks

`python -m compileall -q backend/app backend/tests`, `npm run lint`,
`npx tsc --noEmit`, `git diff --check`, `backend/tests/message_sync_api.py`,
`stage11c_sqlite.py`, `stage11d_realtime_api.py`, Stage 12 migration/API, Stage
13 object/forward, Stage 14 search/moderation/export, Activity delete, and the
Stage 16B adapter test were run on 2026-09-01. All exited zero. `expo lint`
reported one non-blocking existing unused-variable warning in
`app/app/chat/[id].tsx`; TypeScript passed. PostgreSQL evidence is isolated-only.
The high-signal scan of changed/untracked files found no literal credential,
complete DSN, real token, storage key or absolute local path; matches were code
identifiers and redaction-policy text. No new P0/P1 issue was found.

## Complete dirty-file manifest

Every dirty file is covered by one of the following exact repository groups.
Each group is a submit candidate unless a stricter classification below applies:

| Files | Stage/use | Referenced/build impact | Classification |
| --- | --- | --- | --- |
| `backend/app/{admin,compliance,core,messages,reports,uploads}/**`, `backend/app/main.py` | Backend capabilities and integration | Imported by backend application | KEEP_AND_SUBMIT |
| `backend/db/schema.sql`, `backend/db/postgres_schema.sql` | Additive schema/migration baseline | Database initialization | KEEP_AND_SUBMIT |
| `backend/tests/{activity_delete_*,message_sync_*,stage11c_*,stage11d_*,stage12_*,stage13*,stage14*,stage16b_adapters.py}` | Reproducible regressions | Test-only | KEEP_AND_SUBMIT |
| `app/api/{messageOutbox,messageRealtime,messageSync,messages,postDetailPreviewCache,uploads}.ts`, `app/messages/**`, `app/app/_layout.tsx`, `app/app/(tabs)/profile.tsx`, `app/app/chat/[id].tsx` | Mobile APIs and UI bridge | Included in app build | KEEP_AND_SUBMIT |
| `app/tests/{message_business_object_card_static,message_post_share_static,message_realtime_static,message_sync_static}.py` | Mobile static tests | Test-only | KEEP_AND_SUBMIT |
| `docs/**`, `shared/api-schema/social-messages.md` | Product/API/audit documentation | Documentation contract | KEEP_AND_SUBMIT |
| `scripts/audit_stage10_release.py` | Historical release audit helper | Audit-only | REVIEW_BEFORE_SUBMIT |
| `backend/db/b-r2-activity-delete-report-20260830-135547.json` | Generated local evidence | Not build-referenced | REVIEW_BEFORE_SUBMIT |
| Ignored `backend/db/stage*.json`, rendered SQL, SQLite WAL/SHM and temporary database/media files | Historical/generated evidence | Not build-referenced | DEFERRED_NOT_SUBMIT |
| Default SQLite, local secrets/DSNs/tokens, production exports and real user-data artifacts | Local/runtime data | Never build-referenced | DO_NOT_SUBMIT |

No dirty file remains unclassified. The only owner decision is whether to retain
the generated B-R2 report and historical ignored evidence in a future release
commit; this audit does not stage, delete, move or commit them.

## Submission recommendation

Prepare separate commits for backend, app, schema/migrations, tests, and docs.
Do not commit, push, deploy, or present this audit as production release evidence
without a new explicit authorization.
