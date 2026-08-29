# PostgreSQL Migration

PostgreSQL is the production authority once `TENNIS_DATABASE_URL` (or the
compatibility alias `TENNIS_POSTGRES_DSN`) is configured. SQLite remains only
for local legacy-data reads, this repository's lightweight tests, and the
source of the non-destructive transfer tool. Production must not split writes
between the two databases.

## Setup

Install the backend dependencies, set a DSN, and initialize the schema:

```powershell
pip install -r backend/requirements.txt
$env:TENNIS_DATABASE_HOST = "localhost"
$env:TENNIS_DATABASE_PORT = "5432"
$env:TENNIS_DATABASE_NAME = "tennis_messages_test"
# Set TENNIS_DATABASE_URL in this same PowerShell process; do not commit it.
python scripts/init_postgres_db.py
```

The generated schema is also checked in at
`backend/db/postgres_schema.sql`. It preserves string API IDs and text JSON,
uses UTC text timestamps for compatibility with the existing API, carries all
foreign keys/partial unique indexes, and replaces SQLite `updated_at` triggers
with a PostgreSQL trigger function.

## Transfer

The source is opened read-only and is never deleted or modified:

```powershell
python scripts/migrate_sqlite_to_postgres.py --sqlite backend/db/tennis_data_master.sqlite3 --dsn $env:TENNIS_DATABASE_URL --schema message_<timestamp> --dry-run
python scripts/migrate_sqlite_to_postgres.py --sqlite backend/db/tennis_data_master.sqlite3 --dsn $env:TENNIS_DATABASE_URL --schema message_<timestamp> --report migration-report.json
python scripts/validate_postgres_migration.py --sqlite backend/db/tennis_data_master.sqlite3 --dsn $env:TENNIS_DATABASE_URL --schema message_<timestamp> --report validation-report.json
python scripts/reconcile_inbox_counters.py --sqlite backend/db/tennis_data_master.sqlite3 --report inbox-dry-run.json
```

Rows are imported in dependency order in bounded batches. A rerun skips an
identical primary-key row, reports a conflicting row, and never overwrites the
destination. Foreign-key, duplicate-key, JSON, row-count, message, attachment,
media, share, notification, unread-counter, and conversation-last-message
checks are reported. Cache drift is reported for manual calibration; it is not
silently overwritten. Failed tables can be retried safely after the reported
problem is repaired.

`reconcile_inbox_counters.py` reads SQLite in read-only mode. Its default mode
only reports stored/derived/delta values; `--execute --dsn ... --schema ...`
repairs the destination PostgreSQL derived cache and records before/after rows.

## Runtime semantics

The existing hand-written SQL remains behind one database boundary. PostgreSQL
translates the audited `?` parameters and `INSERT OR IGNORE` statements, maps
integrity errors to the service's existing conflict handling, and uses a
bounded psycopg connection pool. `transaction(immediate=True)` starts a normal
transaction and takes a transaction-scoped advisory lock. This preserves the
SQLite writer serialization used by message sequence, idempotency, unread,
conversation-last-message, Post-share, and media-binding operations until
per-key locks are introduced deliberately.

The message-media tables remain isolated from Post and tennis-diary upload
tables. `media_id`, `client_upload_id`, status, expiry/deletion fields, and
storage keys are transferred as data; storage files are not copied or exposed
through the API by the database migration.

Back up both databases and the message-media storage directory before a
production run. Rollback means stopping PostgreSQL writes and restoring the
backup; the original SQLite file is retained for comparison and recovery.

## 验证与报告

迁移前先运行 `scripts/inspect_postgres_environment.py`，确认目标数据库、用户、
当前 schema 和 CREATE 权限。随后在新建的隔离 schema 中依次执行 dry-run、迁移
和校验命令；每个命令都应把报告写到本地、被 Git 忽略的位置。报告用于当次变更的
审计，不是远端仓库的长期依赖。

SQLite 源库始终以只读方式打开，迁移不会删除、覆盖或修复源记录。`user_inbox_counters`
是可由会话成员未读事实重建的派生缓存；任何 drift 都应在报告中显式呈现，并只在
经批准的 PostgreSQL 目标 schema 中用 `reconcile_inbox_counters.py --execute` 修复。
消息媒体的数据库元数据可以迁移，但原始媒体和缩略图文件不在迁移范围内，须另行
备份并通过消息媒体清理流程治理。

性能和查询计划应分别在 SQLite 与 PostgreSQL 环境中收集，作为环境诊断数据，不应
作为跨机器或生产容量承诺。所有本地报告、数据库文件、WAL/SHM 和媒体文件均不提交。
